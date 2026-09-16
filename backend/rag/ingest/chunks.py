"""Biến dữ liệu đã đọc thành các đoạn văn bản để embedding.

Nguyên tắc:
  * Mỗi cặp Q&A là một đoạn (tách nhỏ nếu câu trả lời quá dài).
  * Giỏ hàng KHÔNG embedding từng căn (739 căn, phần lớn trùng layout) mà
    tóm tắt theo loại layout + thống kê; tra cứu chính xác đã có bảng `units`.
  * Ảnh/link được embedding phần mô tả để tìm được theo ngữ cảnh câu hỏi.
"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

from ..text import bedrooms_label, clean, compress_ranges, fmt_area
from .units import PRODUCT_LABELS, LinkItem, QAItem, UnitRow

# Không gian tên cố định để id sinh ra luôn giống nhau giữa các lần nạp.
NAMESPACE = uuid.UUID("6f0a9d5c-1c2b-4f3e-9a7d-2b8c4e6f1a30")

SOURCE_QA = "qa"
SOURCE_UNITS = "units_summary"
SOURCE_MEDIA = "media"

# gemini-embedding-001 nhận tối đa 2048 token; ~6000 ký tự tiếng Việt là ngưỡng an toàn.
MAX_CHUNK_CHARS = 6000


@dataclass
class DocChunk:
    """Một hàng sắp ghi vào bảng `documents`."""

    key: str
    source: str
    content: str
    title: str = ""
    section: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return str(uuid.uuid5(NAMESPACE, f"{self.source}:{self.key}"))

    def to_db_row(self, embedding: list[float]) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "section": self.section or None,
            "title": self.title or None,
            "content": self.content,
            "metadata": self.metadata,
            "embedding": embedding,
        }


# ---------------------------------------------------------------------------
# Q&A
# ---------------------------------------------------------------------------
def _split_answer(answer: str, budget: int) -> list[str]:
    """Cắt câu trả lời dài theo đoạn văn, không cắt giữa câu."""
    if len(answer) <= budget:
        return [answer]
    parts: list[str] = []
    current = ""
    for paragraph in answer.split("\n"):
        candidate = f"{current}\n{paragraph}" if current else paragraph
        if len(candidate) > budget and current:
            parts.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


def qa_chunks(items: Iterable[QAItem]) -> list[DocChunk]:
    chunks: list[DocChunk] = []
    for item in items:
        question = clean(item.question)
        answer = clean(item.answer)
        if item.note:
            answer = f"{answer}\nGhi chú: {clean(item.note)}"

        budget = MAX_CHUNK_CHARS - len(question) - 40
        pieces = _split_answer(answer, max(budget, 1000))
        for index, piece in enumerate(pieces, start=1):
            suffix = "" if len(pieces) == 1 else f" (phần {index}/{len(pieces)})"
            chunks.append(
                DocChunk(
                    key=item.stt if len(pieces) == 1 else f"{item.stt}#p{index}",
                    source=SOURCE_QA,
                    section=item.section,
                    title=question,
                    content=f"Câu hỏi: {question}{suffix}\nTrả lời: {piece}",
                    metadata={"stt": item.stt, "sheet_row": item.sheet_row},
                )
            )
    return assert_unique_ids(chunks)


# ---------------------------------------------------------------------------
# Tóm tắt giỏ hàng
# ---------------------------------------------------------------------------
def _layout_chunks(units: list[UnitRow]) -> list[DocChunk]:
    """Gom các căn hộ cùng layout (tháp, số căn, diện tích, hướng) thành 1 đoạn."""
    groups: dict[tuple, list[UnitRow]] = defaultdict(list)
    for unit in units:
        if unit.product_type != "CH" or not unit.is_primary:
            continue
        key = (
            unit.tower,
            unit.unit_no,
            unit.bedrooms,
            unit.area_gross,
            unit.area_net,
            unit.balcony_dir,
            unit.door_dir,
        )
        groups[key].append(unit)

    chunks: list[DocChunk] = []
    for key, members in sorted(groups.items(), key=lambda item: (str(item[0][0]), str(item[0][1]))):
        tower, unit_no, bedrooms, area_gross, area_net, balcony, door = key
        floors = compress_ranges([unit.floor for unit in members if unit.floor is not None])
        sample = members[0]
        content = (
            f"Căn hộ số {unit_no} tháp {tower} dự án Vlasta Premier - Phú Thuận. "
            f"Loại {bedrooms_label(bedrooms)} ({bedrooms}). "
            f"Diện tích tim tường {fmt_area(area_gross)}, "
            f"diện tích thông thủy {fmt_area(area_net)}. "
            f"Ban công hướng {balcony or 'chưa cập nhật'}, "
            f"cửa chính hướng {door or 'chưa cập nhật'}. "
            f"Có {len(members)} căn giống nhau ở các tầng {floors}. "
            f"Mã căn theo bản vẽ dạng {tower}-<tầng>-{unit_no} (ví dụ {sample.unit_code}), "
            f"mã thương mại dạng CH-{tower}<tầng>-{unit_no} (ví dụ {sample.unit_code_commercial})."
        )
        # Khoá phải chứa ĐỦ các trường dùng để gom nhóm, nếu không hai nhóm chỉ
        # khác diện tích thông thủy sẽ sinh cùng một id và ghi đè lẫn nhau.
        chunks.append(
            DocChunk(
                key=(
                    f"layout:{tower}:{unit_no}:{bedrooms}"
                    f":{area_gross}:{area_net}:{balcony}:{door}"
                ),
                source=SOURCE_UNITS,
                section="layout",
                title=f"Layout căn {unit_no} tháp {tower} ({bedrooms})",
                content=content,
                metadata={
                    "tower": tower,
                    "unit_no": unit_no,
                    "bedrooms": bedrooms,
                    "count": len(members),
                    "area_gross": area_gross,
                    "area_net": area_net,
                },
            )
        )
    return chunks


def _multi_floor_chunks(units: list[UnitRow], product_type: str, label: str) -> list[DocChunk]:
    """Mỗi penthouse / shophouse là một đoạn, gồm diện tích từng tầng và tổng."""
    by_unit: dict[str, list[UnitRow]] = defaultdict(list)
    for unit in units:
        if unit.product_type != product_type:
            continue
        code = unit.unit_code or unit.unit_code_commercial or ""
        if code:
            by_unit[code].append(unit)

    chunks: list[DocChunk] = []
    for code, rows in sorted(by_unit.items()):
        rows = sorted(rows, key=lambda row: row.sheet_row)
        head = rows[0]
        lines = [
            f"{label} {code} (mã thương mại {head.unit_code_commercial or 'n/a'}) "
            f"thuộc tháp {head.tower}, dự án Vlasta Premier - Phú Thuận."
        ]
        for row in rows:
            prefix = "Tổng cộng" if row.is_total_row else f"Tầng {row.floor_label}"
            lines.append(
                f"- {prefix}: tim tường {fmt_area(row.area_gross)}, "
                f"thông thủy {fmt_area(row.area_net)}."
            )
        if head.bedrooms:
            lines.append(f"Số phòng ngủ: {bedrooms_label(head.bedrooms)} ({head.bedrooms}).")
        if head.balcony_dir or head.door_dir:
            lines.append(
                f"Ban công hướng {head.balcony_dir or 'chưa cập nhật'}, "
                f"cửa hướng {head.door_dir or 'chưa cập nhật'}."
            )
        chunks.append(
            DocChunk(
                key=f"{product_type.lower()}:{code}",
                source=SOURCE_UNITS,
                section=product_type.lower(),
                title=f"{label} {code}",
                content="\n".join(lines),
                metadata={"unit_code": code, "product_type": product_type},
            )
        )
    return chunks


def _tmdv_chunks(units: list[UnitRow]) -> list[DocChunk]:
    """Gom căn thương mại dịch vụ theo tháp và tầng."""
    groups: dict[tuple[str, str], list[UnitRow]] = defaultdict(list)
    for unit in units:
        if unit.product_type != "TM" or not unit.is_primary:
            continue
        groups[(unit.tower or "?", unit.floor_label or "?")].append(unit)

    chunks: list[DocChunk] = []
    for (tower, floor), members in sorted(groups.items()):
        areas_gross = [unit.area_gross for unit in members if unit.area_gross is not None]
        areas_net = [unit.area_net for unit in members if unit.area_net is not None]
        codes = ", ".join(
            sorted({unit.unit_code_commercial or unit.unit_code or "" for unit in members} - {""})
        )
        content = (
            f"Sàn thương mại dịch vụ (TMDV) tháp {tower}, tầng {floor}: có {len(members)} căn. "
            f"Diện tích tim tường từ {fmt_area(min(areas_gross) if areas_gross else None)} "
            f"đến {fmt_area(max(areas_gross) if areas_gross else None)}; "
            f"thông thủy từ {fmt_area(min(areas_net) if areas_net else None)} "
            f"đến {fmt_area(max(areas_net) if areas_net else None)}. "
            f"Mã căn: {codes}."
        )
        chunks.append(
            DocChunk(
                key=f"tmdv:{tower}:{floor}",
                source=SOURCE_UNITS,
                section="tmdv",
                title=f"TMDV tháp {tower} tầng {floor}",
                content=content,
                metadata={"tower": tower, "floor_label": floor, "count": len(members)},
            )
        )
    return chunks


def _stats_chunks(units: list[UnitRow]) -> list[DocChunk]:
    """Các đoạn thống kê tổng quan để trả lời câu hỏi 'có bao nhiêu căn...'."""
    primary = [unit for unit in units if unit.is_primary]
    by_type = Counter(unit.product_type for unit in primary)

    lines = ["Thống kê sản phẩm dự án Vlasta Premier - Phú Thuận:"]
    for product_type, count in sorted(by_type.items()):
        lines.append(f"- {PRODUCT_LABELS.get(product_type, product_type)} ({product_type}): {count} căn.")
    lines.append(f"Tổng cộng {len(primary)} căn trong bảng hàng.")
    chunks = [
        DocChunk(
            key="stats:product_type",
            source=SOURCE_UNITS,
            section="stats",
            title="Thống kê số lượng sản phẩm theo loại hình",
            content="\n".join(lines),
            metadata=dict(by_type),
        )
    ]

    # Thống kê theo số phòng ngủ (chỉ căn hộ ở).
    by_bedroom: dict[str, list[UnitRow]] = defaultdict(list)
    for unit in primary:
        if unit.product_type in {"CH", "PH"} and unit.bedrooms:
            by_bedroom[unit.bedrooms].append(unit)

    lines = ["Thống kê căn hộ theo số phòng ngủ tại Vlasta Premier - Phú Thuận:"]
    for bedrooms, members in sorted(by_bedroom.items()):
        areas = [unit.area_net for unit in members if unit.area_net is not None]
        gross = [unit.area_gross for unit in members if unit.area_gross is not None]
        lines.append(
            f"- {bedrooms_label(bedrooms)} ({bedrooms}): {len(members)} căn, "
            f"diện tích thông thủy từ {fmt_area(min(areas) if areas else None)} "
            f"đến {fmt_area(max(areas) if areas else None)}, "
            f"tim tường từ {fmt_area(min(gross) if gross else None)} "
            f"đến {fmt_area(max(gross) if gross else None)}."
        )
    chunks.append(
        DocChunk(
            key="stats:bedrooms",
            source=SOURCE_UNITS,
            section="stats",
            title="Thống kê căn hộ theo số phòng ngủ",
            content="\n".join(lines),
            metadata={"bedrooms": {key: len(value) for key, value in by_bedroom.items()}},
        )
    )

    # Thống kê theo tháp.
    by_tower: dict[str, list[UnitRow]] = defaultdict(list)
    for unit in primary:
        by_tower[unit.tower or "?"].append(unit)

    lines = ["Cơ cấu sản phẩm theo tháp tại Vlasta Premier - Phú Thuận:"]
    for tower, members in sorted(by_tower.items()):
        floors = compress_ranges([unit.floor for unit in members if unit.floor is not None])
        types = Counter(unit.product_type for unit in members)
        detail = ", ".join(
            f"{PRODUCT_LABELS.get(key, key)} {value} căn" for key, value in sorted(types.items())
        )
        lines.append(f"- Tháp {tower}: {len(members)} căn ({detail}); các tầng {floors}.")
    chunks.append(
        DocChunk(
            key="stats:tower",
            source=SOURCE_UNITS,
            section="stats",
            title="Cơ cấu sản phẩm theo tháp",
            content="\n".join(lines),
            metadata={"towers": {key: len(value) for key, value in by_tower.items()}},
        )
    )
    return chunks


def _guide_chunk() -> DocChunk:
    """Giải thích quy ước mã căn và khái niệm diện tích cho mô hình."""
    content = (
        "Cách đọc mã căn tại dự án Vlasta Premier - Phú Thuận (mã dự án 03HNCM008):\n"
        "- Mã theo bản vẽ có dạng <Tháp>-<Tầng>-<Số căn>, ví dụ A-06-01 là tháp A, tầng 6, căn số 01.\n"
        "- Mã thương mại có tiền tố theo loại sản phẩm: CH là căn hộ ở, PH là penthouse, "
        "SH là shophouse, TM là sàn thương mại dịch vụ. Ví dụ CH-A06-01, SH-A01-02, TM-A03-09.\n"
        "- Mã theo bản vẽ thẩm định/giấy phép xây dựng có dạng <Tháp>-NN-<Số căn>, ví dụ A-NN-01, "
        "dùng chung cho mọi tầng có cùng layout.\n"
        "Hai loại diện tích:\n"
        "- Diện tích tim tường (diện tích sàn xây dựng): tính từ tim tường bao và tường ngăn căn hộ, "
        "bao gồm cả diện tích cột và hộp kỹ thuật bên trong căn.\n"
        "- Diện tích thông thủy (diện tích sử dụng): tính theo kích thước lọt lòng, không tính tường bao "
        "và hộp kỹ thuật; đây là diện tích ghi trên giấy chứng nhận.\n"
        "Diện tích thông thủy luôn nhỏ hơn diện tích tim tường."
    )
    return DocChunk(
        key="guide:codes",
        source=SOURCE_UNITS,
        section="guide",
        title="Quy ước mã căn và cách tính diện tích",
        content=content,
    )


def assert_unique_ids(chunks: list[DocChunk]) -> list[DocChunk]:
    """Chặn trường hợp hai đoạn sinh ra cùng id (sẽ ghi đè nhau trên Supabase)."""
    seen: dict[str, DocChunk] = {}
    for chunk in chunks:
        existing = seen.get(chunk.id)
        if existing is not None:
            raise ValueError(
                "Hai đoạn có cùng id, khoá bị thiếu trường phân biệt:\n"
                f"  khoá: {chunk.key}\n"
                f"  đoạn 1: {existing.title} | {existing.metadata}\n"
                f"  đoạn 2: {chunk.title} | {chunk.metadata}"
            )
        seen[chunk.id] = chunk
    return chunks


def unit_summary_chunks(units: list[UnitRow]) -> list[DocChunk]:
    return assert_unique_ids(
        [
            *_layout_chunks(units),
            *_multi_floor_chunks(units, "PH", "Penthouse"),
            *_multi_floor_chunks(units, "SH", "Shophouse"),
            *_tmdv_chunks(units),
            *_stats_chunks(units),
            _guide_chunk(),
        ]
    )


# ---------------------------------------------------------------------------
# Ảnh / link tài liệu
# ---------------------------------------------------------------------------
def media_chunks(entries: Iterable[dict[str, Any]]) -> list[DocChunk]:
    """Tạo đoạn mô tả ảnh/link từ manifest (data/media_manifest.json)."""
    chunks: list[DocChunk] = []
    for entry in entries:
        url = clean(entry.get("url"))
        file_name = clean(entry.get("file"))
        if not url:
            continue
        title = clean(entry.get("title")) or file_name or url
        description = clean(entry.get("description"))
        tags = [clean(tag) for tag in entry.get("tags", []) if clean(tag)]
        category = clean(entry.get("category")) or "khac"
        media_type = clean(entry.get("type")) or "image"

        content_parts = [title]
        if description:
            content_parts.append(description)
        if tags:
            content_parts.append("Từ khóa: " + ", ".join(tags))
        content_parts.append(f"Loại tài liệu: {category}.")

        chunks.append(
            DocChunk(
                key=file_name or url,
                source=SOURCE_MEDIA,
                section=category,
                title=title,
                content=" ".join(content_parts),
                metadata={
                    "url": url,
                    "type": media_type,
                    "file": file_name or None,
                    "tags": tags,
                    "category": category,
                },
            )
        )
    return assert_unique_ids(chunks)


def link_entries(links: Iterable[LinkItem]) -> list[dict[str, Any]]:
    """Chuyển link lấy từ các tab phụ của sheet thành mục manifest."""
    entries: list[dict[str, Any]] = []
    descriptions = {
        "map": "Bản đồ tương tác 360 độ giúp xem vị trí dự án, tiện ích xung quanh và kết nối vùng.",
        "anh_3d": "Thư viện ảnh phối cảnh 3D của dự án: ngoại cảnh, tiện ích, mặt bằng minh họa.",
        "tai_lieu": "Bộ tài liệu bán hàng: salekit, brochure điện tử của dự án.",
        "mat_bang": "Mặt bằng tầng và layout căn hộ của dự án.",
    }
    tags = {
        "map": ["bản đồ", "vị trí", "360", "kết nối vùng"],
        "anh_3d": ["ảnh 3D", "phối cảnh", "hình ảnh", "poster"],
        "tai_lieu": ["salekit", "brochure", "tài liệu"],
        "mat_bang": ["mặt bằng", "layout", "sơ đồ"],
    }
    for link in links:
        entries.append(
            {
                "url": link.url,
                "type": "link",
                "title": f"{link.title} - Vlasta Premier Phú Thuận",
                "description": descriptions.get(link.category, ""),
                "tags": tags.get(link.category, []),
                "category": link.category,
            }
        )
    return entries
