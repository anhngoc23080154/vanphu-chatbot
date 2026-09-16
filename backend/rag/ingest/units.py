"""Mô hình dữ liệu cho một dòng giỏ hàng (căn hộ / shophouse)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..text import bedrooms_label, fmt_area

PROJECT_CODE = "03HNCM008"

PRODUCT_LABELS = {
    "CH": "Căn hộ",
    "PH": "Penthouse",
    "SH": "Shophouse",
    "TM": "Thương mại dịch vụ",
}


@dataclass
class UnitRow:
    """Một dòng trong bảng diện tích, đã chuẩn hoá và điền đầy giá trị kế thừa."""

    unit_code: str | None = None
    unit_code_alt: str | None = None
    unit_code_commercial: str | None = None
    tower: str | None = None
    floor: int | None = None
    floor_label: str = ""
    unit_no: str = ""
    product_type: str = "CH"
    area_gross: float | None = None
    area_net: float | None = None
    bedrooms: str = ""
    bedroom_count: int | None = None
    balcony_dir: str = ""
    door_dir: str = ""
    note: str = ""
    is_primary: bool = True
    is_total_row: bool = False
    sheet_row: int = 0
    sheet_name: str = ""

    @property
    def display_code(self) -> str:
        """Mã hiển thị ưu tiên: mã thi công, rồi mã thương mại, rồi mã GPXD."""
        return self.unit_code or self.unit_code_commercial or self.unit_code_alt or "n/a"

    def to_db_row(self) -> dict[str, Any]:
        return {
            "project_code": PROJECT_CODE,
            "unit_code": self.unit_code or None,
            "unit_code_alt": self.unit_code_alt or None,
            "unit_code_commercial": self.unit_code_commercial or None,
            "tower": self.tower or None,
            "floor": self.floor,
            "floor_label": self.floor_label or None,
            "unit_no": self.unit_no or None,
            "product_type": self.product_type,
            "area_gross": self.area_gross,
            "area_net": self.area_net,
            "bedrooms": self.bedrooms or None,
            "bedroom_count": self.bedroom_count,
            "balcony_dir": self.balcony_dir or None,
            "door_dir": self.door_dir or None,
            "note": self.note or None,
            "is_primary": self.is_primary,
            "is_total_row": self.is_total_row,
            "sheet_row": self.sheet_row,
            "sheet_name": self.sheet_name,
        }


def describe_unit(unit: UnitRow) -> str:
    """Một dòng mô tả căn, dùng trong ngữ cảnh gửi cho mô hình."""
    parts: list[str] = [unit.display_code]
    if unit.unit_code_commercial and unit.unit_code_commercial != unit.display_code:
        parts.append(f"mã thương mại {unit.unit_code_commercial}")
    parts.append(PRODUCT_LABELS.get(unit.product_type, unit.product_type))
    if unit.tower:
        parts.append(f"tháp {unit.tower}")
    if unit.floor_label:
        parts.append(f"tầng {unit.floor_label}")
    if unit.bedrooms:
        parts.append(bedrooms_label(unit.bedrooms))
    parts.append(f"tim tường {fmt_area(unit.area_gross)}")
    parts.append(f"thông thủy {fmt_area(unit.area_net)}")
    if unit.balcony_dir:
        parts.append(f"ban công hướng {unit.balcony_dir}")
    if unit.door_dir:
        parts.append(f"cửa hướng {unit.door_dir}")
    if unit.note:
        parts.append(f"ghi chú: {unit.note}")
    return " | ".join(parts)


def describe_db_row(row: dict[str, Any]) -> str:
    """Như describe_unit nhưng nhận dict lấy từ Supabase."""
    unit = UnitRow(
        unit_code=row.get("unit_code"),
        unit_code_alt=row.get("unit_code_alt"),
        unit_code_commercial=row.get("unit_code_commercial"),
        tower=row.get("tower"),
        floor=row.get("floor"),
        floor_label=row.get("floor_label") or "",
        unit_no=row.get("unit_no") or "",
        product_type=row.get("product_type") or "CH",
        area_gross=_as_float(row.get("area_gross")),
        area_net=_as_float(row.get("area_net")),
        bedrooms=row.get("bedrooms") or "",
        balcony_dir=row.get("balcony_dir") or "",
        door_dir=row.get("door_dir") or "",
        note=row.get("note") or "",
        is_total_row=bool(row.get("is_total_row")),
    )
    text = describe_unit(unit)
    if unit.is_total_row:
        text = f"{text} (tổng nhiều tầng)"
    return text


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class ParsedSheets:
    """Kết quả đọc toàn bộ workbook."""

    units: list[UnitRow] = field(default_factory=list)
    qa: list["QAItem"] = field(default_factory=list)
    links: list["LinkItem"] = field(default_factory=list)


@dataclass
class QAItem:
    """Một cặp hỏi - đáp trong sheet Q&A."""

    stt: str
    section: str
    question: str
    answer: str
    note: str = ""
    sheet_row: int = 0


@dataclass
class LinkItem:
    """Link tài liệu/media lấy từ các tab phụ của sheet."""

    title: str
    url: str
    category: str
    sheet_name: str = ""
