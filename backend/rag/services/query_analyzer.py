"""Phân tích câu hỏi bằng regex/từ khoá, KHÔNG gọi LLM.

Mục tiêu: mỗi request chỉ tốn đúng 1 lần embed + 1 lần generate của Gemini
(free tier ~10 request/phút), nên việc định tuyến phải làm bằng luật.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..schemas import HistoryItem
from ..text import clean, normalize_key

# --- Mã căn -----------------------------------------------------------------
# A-06-01 / a 06 01 (mã theo bản vẽ thi công)
_RE_UNIT_PLAIN = re.compile(r"\b([AB])\s*-\s*(\d{1,2})\s*-\s*(\d{1,2})\b")
# CH-A06-01, PH-B34-01, SH-A01-02, TM-A03-09 (mã thương mại)
_RE_UNIT_COMMERCIAL = re.compile(r"\b(CH|PH|SH|TM)\s*-?\s*([AB])\s*(\d{2})\s*-\s*(\d{2})\b")
# A-NN-01 (mã điển hình theo giấy phép xây dựng)
_RE_UNIT_ALT = re.compile(r"\b([AB])\s*-\s*NN\s*-\s*(\d{1,2})\b")

_RE_TOWER = re.compile(r"\b(?:THAP|TOWER|TOA)\s*([AB])\b")
_RE_FLOOR = re.compile(r"\b(?:TANG|LAU|FLOOR)\s*(\d{1,2})\b")
_RE_BEDROOM = re.compile(r"\b(\d)\s*(?:PN|BR|PHONG NGU)\b")
_RE_DIRECTION = re.compile(
    r"\bHUONG\s*(?:BAN CONG\s*|CUA\s*)?"
    r"(DONG BAC|DONG NAM|TAY BAC|TAY NAM|DONG|TAY|NAM|BAC)\b"
)

_PRODUCT_KEYWORDS: list[tuple[str, str]] = [
    ("PENTHOUSE", "PH"),
    ("SHOPHOUSE", "SH"),
    ("SHOP HOUSE", "SH"),
    ("TMDV", "TM"),
    ("THUONG MAI DICH VU", "TM"),
    ("THUONG MAI", "TM"),
    ("CAN HO", "CH"),
    ("CHUNG CU", "CH"),
]

_IMAGE_KEYWORDS = (
    "ANH", "HINH", "POSTER", "MAT BANG", "LAYOUT", "BROCHURE", "PHOI CANH",
    "BAN DO", "MAP", "VIDEO", "TAI LIEU", "SALEKIT", "3D", "360", "XEM QUA",
    "MINH HOA", "SO DO",
)

_STATS_KEYWORDS = (
    "BAO NHIEU CAN", "CO MAY CAN", "TONG SO", "SO LUONG", "THONG KE",
    "MAY CAN", "CO BAO NHIEU",
)

# Từ chỉ định (anaphora) -> câu hỏi nối tiếp lượt trước.
_FOLLOWUP_KEYWORDS = (
    "CAN DO", "CAN NAY", "CAN AY", "NO", "VAY", "THE CON", "CON ", "THE THI",
    "TUONG TU", "O DO", "CAI DO", "CAI NAY", "LOAI DO",
)

_DIRECTION_LABELS = {
    "DONG BAC": "Đông Bắc",
    "DONG NAM": "Đông Nam",
    "TAY BAC": "Tây Bắc",
    "TAY NAM": "Tây Nam",
    "DONG": "Đông",
    "TAY": "Tây",
    "NAM": "Nam",
    "BAC": "Bắc",
}


@dataclass
class QueryIntent:
    """Kết quả phân tích, quyết định có truy vấn bảng `units` hay không."""

    unit_codes_plain: list[str] = field(default_factory=list)
    unit_codes_commercial: list[str] = field(default_factory=list)
    unit_codes_alt: list[str] = field(default_factory=list)
    tower: str | None = None
    floor: int | None = None
    bedroom_count: int | None = None
    product_type: str | None = None
    direction: str | None = None
    wants_image: bool = False
    wants_stats: bool = False
    is_followup: bool = False

    @property
    def unit_codes(self) -> list[str]:
        return [*self.unit_codes_plain, *self.unit_codes_commercial, *self.unit_codes_alt]

    def has_codes(self) -> bool:
        return bool(self.unit_codes)

    def has_filters(self) -> bool:
        return any(
            value is not None
            for value in (self.tower, self.floor, self.bedroom_count, self.product_type, self.direction)
        )

    def needs_units(self) -> bool:
        """Có nên truy vấn bảng `units` không."""
        return self.has_codes() or self.has_filters()


def _extract_codes(text: str, intent: QueryIntent) -> None:
    for tower, floor, unit in _RE_UNIT_PLAIN.findall(text):
        code = f"{tower}-{int(floor):02d}-{int(unit):02d}"
        if code not in intent.unit_codes_plain:
            intent.unit_codes_plain.append(code)

    for kind, tower, floor, unit in _RE_UNIT_COMMERCIAL.findall(text):
        code = f"{kind}-{tower}{floor}-{unit}"
        if code not in intent.unit_codes_commercial:
            intent.unit_codes_commercial.append(code)

    for tower, unit in _RE_UNIT_ALT.findall(text):
        code = f"{tower}-NN-{int(unit):02d}"
        if code not in intent.unit_codes_alt:
            intent.unit_codes_alt.append(code)


def _analyze_text(text: str) -> QueryIntent:
    """Phân tích một câu (đã chuẩn hoá không dấu, viết hoa)."""
    intent = QueryIntent()
    _extract_codes(text, intent)

    # Mã thương mại đã hàm ý loại sản phẩm.
    for code in intent.unit_codes_commercial:
        intent.product_type = code.split("-", 1)[0]
        break

    match = _RE_TOWER.search(text)
    if match:
        intent.tower = match.group(1)

    match = _RE_FLOOR.search(text)
    if match:
        floor = int(match.group(1))
        if 1 <= floor <= 40:
            intent.floor = floor

    match = _RE_BEDROOM.search(text)
    if match:
        intent.bedroom_count = int(match.group(1))

    if intent.product_type is None:
        for keyword, product in _PRODUCT_KEYWORDS:
            if keyword in text:
                intent.product_type = product
                break

    match = _RE_DIRECTION.search(text)
    if match:
        intent.direction = _DIRECTION_LABELS.get(match.group(1))

    intent.wants_image = any(keyword in text for keyword in _IMAGE_KEYWORDS)
    intent.wants_stats = any(keyword in text for keyword in _STATS_KEYWORDS)
    return intent


def _merge(primary: QueryIntent, previous: QueryIntent) -> QueryIntent:
    """Bổ sung thực thể còn thiếu từ lượt hỏi trước (câu hỏi nối tiếp)."""
    for name in ("unit_codes_plain", "unit_codes_commercial", "unit_codes_alt"):
        if not getattr(primary, name):
            setattr(primary, name, list(getattr(previous, name)))
    for name in ("tower", "floor", "bedroom_count", "product_type"):
        if getattr(primary, name) is None:
            setattr(primary, name, getattr(previous, name))
    return primary


def _last_user_message(history: list[HistoryItem]) -> str:
    for item in reversed(history):
        if item.role == "user" and clean(item.content):
            return clean(item.content)
    return ""


def analyze(message: str, history: list[HistoryItem] | None = None) -> QueryIntent:
    """Trả về ý định của câu hỏi, có kế thừa ngữ cảnh lượt trước khi cần."""
    history = history or []
    normalized = normalize_key(message)
    intent = _analyze_text(normalized)

    is_short = len(normalized.split()) <= 6
    has_anaphora = any(keyword in normalized for keyword in _FOLLOWUP_KEYWORDS)
    if (is_short or has_anaphora) and not intent.needs_units():
        previous_raw = _last_user_message(history)
        if previous_raw:
            previous = _analyze_text(normalize_key(previous_raw))
            if previous.needs_units():
                intent.is_followup = True
                _merge(intent, previous)
    return intent


def build_retrieval_text(message: str, history: list[HistoryItem] | None, intent: QueryIntent) -> str:
    """Chuỗi đem đi embed. Câu hỏi nối tiếp được ghép thêm lượt hỏi trước."""
    message = clean(message)
    if intent.is_followup:
        previous = _last_user_message(history or [])
        if previous:
            return f"{previous} {message}"
    return message
