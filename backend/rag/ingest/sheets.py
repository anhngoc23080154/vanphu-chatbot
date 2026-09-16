"""Đọc workbook Excel của dự án thành dữ liệu có cấu trúc.

Đặc thù của file nguồn cần xử lý:
  * Số được xuất ra dạng chuỗi ('6.0'), có ô trống, có lỗi gõ dấu ('ĐÔng').
  * Xen giữa dữ liệu là các dòng tiêu đề nhóm ('2/ Căn Hộ Ở Tháp A').
  * Penthouse và shophouse có dòng phụ chỉ chứa diện tích từng tầng và dòng
    tổng ('1+2', '34+35'); các cột mã để trống nên phải kế thừa từ dòng chính.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Iterator

from ..text import clean, normalize_key, norm_dir, pad2, parse_bedrooms, to_float, to_int
from .units import LinkItem, ParsedSheets, QAItem, UnitRow

logger = logging.getLogger(__name__)

SHEET_APARTMENTS = "Bảng diện tích căn hộ"
SHEET_SHOPHOUSE = "diện tích shophouse"
SHEET_QA = "Q&A"

# Dòng tiêu đề nhóm kiểu '1/ Shophouse & TMDV', '2/ Căn Hộ Ở Tháp A'.
_SECTION_RE = re.compile(r"^\s*\d+\s*/")
_URL_RE = re.compile(r"https?://\S+")

_VALID_PRODUCTS = {"CH", "PH", "SH", "TM"}


def _stt(value: Any) -> str:
    """Chuẩn hoá số thứ tự: '1.0' -> '1'; giữ nguyên nếu là chữ."""
    number = to_int(value)
    return str(number) if number is not None else clean(value)


def _floor_label(value: Any) -> str:
    """Nhãn tầng: '6.0' -> '6'; giữ nguyên dạng gộp tầng '1+2', '34+35'."""
    return _stt(value)


def _rows(worksheet: Any) -> Iterator[tuple[int, list[Any]]]:
    for index, row in enumerate(worksheet.iter_rows(values_only=True), start=1):
        yield index, list(row)


def _cell(row: list[Any], index: int) -> Any:
    return row[index] if 0 <= index < len(row) else None


def _is_blank(row: list[Any]) -> bool:
    return all(clean(value) == "" for value in row)


def _find_sheet(workbook: Any, wanted: str) -> Any:
    """Tìm sheet theo tên, bỏ qua khác biệt dấu/hoa thường/khoảng trắng thừa."""
    target = normalize_key(wanted)
    for name in workbook.sheetnames:
        if normalize_key(name) == target:
            return workbook[name]
    for name in workbook.sheetnames:
        if target in normalize_key(name):
            return workbook[name]
    raise KeyError(f"Không tìm thấy sheet {wanted!r}. Có: {workbook.sheetnames}")


# ---------------------------------------------------------------------------
# Bảng diện tích căn hộ
# ---------------------------------------------------------------------------
# Vị trí cột (0-indexed) của sheet căn hộ:
#  0 STT | 1 Mã Căn | 2 Mã Căn (BVTĐ-GPXD) | 3 Mã Căn Thương Mại | 4 Tầng
#  5 Loại SP | 6 Tháp | 7 Tầng | 8 Căn (theo mã thi công) | 9 Căn (thương mại)
#  10 DT tim tường | 11 DT thông thủy | 12 Số PN | 13 Hướng ban công
#  14 Hướng cửa | 15 Ghi chú
_APT = {
    "stt": 0,
    "unit_code": 1,
    "unit_code_alt": 2,
    "unit_code_commercial": 3,
    "floor": 4,
    "product_type": 5,
    "tower": 6,
    "unit_no": 9,
    "area_gross": 10,
    "area_net": 11,
    "bedrooms": 12,
    "balcony_dir": 13,
    "door_dir": 14,
    "note": 15,
}

# Sheet shophouse thiếu cột 'Mã Căn' nên các chỉ số lùi 1 so với sheet căn hộ.
#  0 STT | 1 Mã Căn (BVTĐ-GPXD) | 2 Mã Căn Thương Mại | 3 Tầng | 4 Loại SP
#  5 Tháp | 6 Tầng | 7 Căn | 8 DT tim tường | 9 DT thông thủy | 10 Số PN
#  11 Hướng ban công | 12 Hướng cửa | 13 Ghi chú
_SHOP = {
    "stt": 0,
    "unit_code": 1,
    "unit_code_alt": None,
    "unit_code_commercial": 2,
    "floor": 3,
    "product_type": 4,
    "tower": 5,
    "unit_no": 7,
    "area_gross": 8,
    "area_net": 9,
    "bedrooms": 10,
    "balcony_dir": 11,
    "door_dir": 12,
    "note": 13,
}


def _parse_units_sheet(
    worksheet: Any, columns: dict[str, int | None], first_data_row: int, sheet_name: str
) -> list[UnitRow]:
    units: list[UnitRow] = []
    parent: UnitRow | None = None

    def col(row: list[Any], key: str) -> Any:
        index = columns.get(key)
        return None if index is None else _cell(row, index)

    for row_index, row in _rows(worksheet):
        if row_index < first_data_row or _is_blank(row):
            continue

        first = clean(col(row, "stt"))
        # Dòng tiêu đề nhóm: chỉ có chữ ở cột đầu, không có số thứ tự.
        if first and _SECTION_RE.match(first):
            continue
        if first and to_float(first) is None:
            continue

        is_primary = bool(first)
        floor_label = _floor_label(col(row, "floor"))
        area_gross = to_float(col(row, "area_gross"))
        area_net = to_float(col(row, "area_net"))

        if not is_primary:
            # Dòng phụ: chỉ có diện tích theo tầng, kế thừa mã từ dòng chính.
            if parent is None or (area_gross is None and area_net is None):
                continue
            units.append(
                UnitRow(
                    unit_code=parent.unit_code,
                    unit_code_alt=parent.unit_code_alt,
                    unit_code_commercial=parent.unit_code_commercial,
                    tower=parent.tower,
                    floor=to_int(floor_label),
                    floor_label=floor_label or parent.floor_label,
                    unit_no=parent.unit_no,
                    product_type=parent.product_type,
                    area_gross=area_gross,
                    area_net=area_net,
                    bedrooms=parent.bedrooms,
                    bedroom_count=parent.bedroom_count,
                    balcony_dir=parent.balcony_dir,
                    door_dir=parent.door_dir,
                    note=clean(col(row, "note")),
                    is_primary=False,
                    is_total_row="+" in floor_label,
                    sheet_row=row_index,
                    sheet_name=sheet_name,
                )
            )
            continue

        product_type = normalize_key(col(row, "product_type"))
        if product_type not in _VALID_PRODUCTS:
            logger.debug("Bỏ qua dòng %s: loại sản phẩm %r", row_index, product_type)
            continue

        bedrooms_raw, bedroom_count = parse_bedrooms(col(row, "bedrooms"))
        unit = UnitRow(
            unit_code=clean(col(row, "unit_code")) or None,
            unit_code_alt=clean(col(row, "unit_code_alt")) or None,
            unit_code_commercial=clean(col(row, "unit_code_commercial")) or None,
            tower=normalize_key(col(row, "tower")) or None,
            floor=to_int(floor_label),
            floor_label=floor_label,
            unit_no=pad2(col(row, "unit_no")),
            product_type=product_type,
            area_gross=area_gross,
            area_net=area_net,
            bedrooms=bedrooms_raw,
            bedroom_count=bedroom_count,
            balcony_dir=norm_dir(col(row, "balcony_dir")),
            door_dir=norm_dir(col(row, "door_dir")),
            note=clean(col(row, "note")),
            is_primary=True,
            is_total_row="+" in floor_label,
            sheet_row=row_index,
            sheet_name=sheet_name,
        )
        units.append(unit)
        parent = unit

    return units


def parse_apartments(workbook: Any) -> list[UnitRow]:
    worksheet = _find_sheet(workbook, SHEET_APARTMENTS)
    return _parse_units_sheet(worksheet, _APT, first_data_row=2, sheet_name=worksheet.title)


def parse_shophouse(workbook: Any) -> list[UnitRow]:
    worksheet = _find_sheet(workbook, SHEET_SHOPHOUSE)
    return _parse_units_sheet(worksheet, _SHOP, first_data_row=5, sheet_name=worksheet.title)


# ---------------------------------------------------------------------------
# Sheet Q&A
# ---------------------------------------------------------------------------
def parse_qa(workbook: Any) -> list[QAItem]:
    worksheet = _find_sheet(workbook, SHEET_QA)
    items: list[QAItem] = []
    section = "Thông tin chung"

    for row_index, row in _rows(worksheet):
        if _is_blank(row):
            continue
        stt = _stt(_cell(row, 0))
        question = clean(_cell(row, 1))
        answer = clean(_cell(row, 2))
        note = clean(_cell(row, 4))

        # Dòng tiêu đề bảng.
        if normalize_key(stt) == "STT":
            continue
        # Tiêu đề toàn sheet / đoạn miễn trừ trách nhiệm nằm ở cột A.
        if stt and not question and not answer:
            if len(stt) > 120:
                items.append(
                    QAItem(
                        stt="disclaimer",
                        section="Miễn trừ trách nhiệm",
                        question="Thông tin trong tài liệu có ràng buộc pháp lý không?",
                        answer=stt,
                        sheet_row=row_index,
                    )
                )
            continue
        # Dòng tiêu đề nhóm: không có số thứ tự, chỉ có chữ ở cột câu hỏi.
        if not stt and question and not answer:
            section = question
            continue
        if not question or not answer:
            if question and not answer:
                logger.warning("Câu hỏi STT %s không có câu trả lời, bỏ qua", stt or row_index)
            continue

        items.append(
            QAItem(
                stt=stt or str(row_index),
                section=section,
                question=question,
                answer=answer,
                note=note,
                sheet_row=row_index,
            )
        )
    return items


# ---------------------------------------------------------------------------
# Các tab phụ chứa link tài liệu / media
# ---------------------------------------------------------------------------
_LINK_CATEGORIES = {
    "MAP VI TRI": "map",
    "ANH 3D": "anh_3d",
    "TAI LIEU BAN HANG": "tai_lieu",
    "MAT BANG 2D": "mat_bang",
    "MAT BANG 3D": "mat_bang",
}


def parse_links(workbook: Any) -> list[LinkItem]:
    """Thu các URL nằm rải rác trong những tab phụ (map 360, ảnh 3D, salekit...)."""
    links: list[LinkItem] = []
    known = {normalize_key(name) for name in (SHEET_APARTMENTS, SHEET_SHOPHOUSE, SHEET_QA)}

    for name in workbook.sheetnames:
        key = normalize_key(name)
        if key in known:
            continue
        category = _LINK_CATEGORIES.get(key, "khac")
        worksheet = workbook[name]
        for _, row in _rows(worksheet):
            for value in row:
                text = clean(value)
                if not text:
                    continue
                for url in _URL_RE.findall(text):
                    url = url.rstrip(").,;")
                    title = text.split(":", 1)[0].strip() if ":" in text else clean(name)
                    links.append(
                        LinkItem(title=title or clean(name), url=url, category=category, sheet_name=name)
                    )
    return links


# ---------------------------------------------------------------------------
def parse_workbook(path: Path) -> ParsedSheets:
    """Đọc toàn bộ workbook. openpyxl chỉ import ở đây (không dùng lúc chạy API)."""
    import openpyxl  # import lười: thư viện này không có trong bundle runtime

    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        units = [*parse_apartments(workbook), *parse_shophouse(workbook)]
        qa = parse_qa(workbook)
        links = parse_links(workbook)
    finally:
        workbook.close()
    return ParsedSheets(units=units, qa=qa, links=links)


def summarize(parsed: ParsedSheets) -> str:
    """Chuỗi thống kê để đối chiếu với dữ liệu gốc sau khi đọc."""
    from collections import Counter

    primary = [unit for unit in parsed.units if unit.is_primary]
    by_type = Counter(unit.product_type for unit in primary)
    lines = [
        f"Tổng số dòng giỏ hàng: {len(parsed.units)} (dòng chính: {len(primary)})",
        "  " + ", ".join(f"{key}: {value}" for key, value in sorted(by_type.items())),
        f"Số cặp Q&A: {len(parsed.qa)}",
        f"Số link tài liệu/media: {len(parsed.links)}",
    ]
    return "\n".join(lines)
