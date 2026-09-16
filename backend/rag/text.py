"""Tiện ích xử lý chuỗi/số tiếng Việt dùng chung cho runtime và ingest."""

from __future__ import annotations

import re
import unicodedata

# Mọi khoảng trắng (gồm xuống dòng) - dùng khi chuẩn hoá khoá so khớp.
_WS_RE = re.compile(r"\s+")
# Chỉ khoảng trắng ngang (space, tab) - giữ lại ký tự xuống dòng.
_HSPACE_RE = re.compile(r"[ \t\r\f\v ]+")

# Bảng chuẩn hoá hướng (khoá là dạng không dấu, viết hoa).
_DIRECTIONS = {
    "DONG BAC": "Đông Bắc",
    "DONG NAM": "Đông Nam",
    "TAY BAC": "Tây Bắc",
    "TAY NAM": "Tây Nam",
    "DONG": "Đông",
    "TAY": "Tây",
    "NAM": "Nam",
    "BAC": "Bắc",
}


def strip_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt, giữ nguyên chữ cái ASCII."""
    if not text:
        return ""
    text = text.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def clean(value: object) -> str:
    """Chuỗi đã bỏ khoảng trắng thừa; None -> ''.

    Giữ lại ký tự xuống dòng vì nhiều câu trả lời trong sheet Q&A trình bày
    dạng danh sách nhiều dòng; chỉ gộp khoảng trắng ngang trong từng dòng.
    """
    if value is None:
        return ""
    lines = [_HSPACE_RE.sub(" ", line).strip() for line in str(value).splitlines()]
    return "\n".join(lines).strip()


def normalize_key(text: str) -> str:
    """Dạng chuẩn để so khớp từ khoá: không dấu, viết hoa, gọn khoảng trắng."""
    return _WS_RE.sub(" ", strip_accents(clean(text))).upper()


def to_float(value: object) -> float | None:
    """'102.33' / '102,33' / 102.33 -> float; rác -> None."""
    text = clean(value)
    if not text:
        return None
    text = text.replace(" ", "")
    # Dạng '1.234,56' (phân cách nghìn bằng dấu chấm).
    if "," in text and "." in text and text.rfind(",") > text.rfind("."):
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def to_int(value: object) -> int | None:
    """'6.0' -> 6; '1+2' -> None (dòng tổng hợp nhiều tầng)."""
    number = to_float(value)
    if number is None:
        return None
    if abs(number - round(number)) > 1e-6:
        return None
    return int(round(number))


def pad2(value: object) -> str:
    """'1' / '1.0' -> '01'; giữ nguyên chuỗi không phải số."""
    number = to_int(value)
    if number is None:
        return clean(value)
    return f"{number:02d}"


def norm_dir(value: object) -> str:
    """Chuẩn hoá hướng, sửa lỗi gõ kiểu 'ĐÔng' -> 'Đông'."""
    text = clean(value)
    if not text:
        return ""
    key = normalize_key(text)
    return _DIRECTIONS.get(key, text)


def parse_bedrooms(value: object) -> tuple[str, int | None]:
    """'3BR' -> ('3BR', 3); '1BR+1' -> ('1BR+1', 1); '' -> ('', None)."""
    raw = clean(value)
    if not raw:
        return "", None
    match = re.search(r"(\d+)\s*(?:BR|PN)", normalize_key(raw))
    if match:
        return raw, int(match.group(1))
    if "STUDIO" in normalize_key(raw):
        return raw, 0
    return raw, None


def bedrooms_label(raw: str) -> str:
    """'3BR' -> '3 phòng ngủ'; '1BR+1' -> '1 phòng ngủ + 1 phòng đa năng'."""
    key = normalize_key(raw)
    match = re.match(r"^(\d+)\s*BR(\+1)?$", key)
    if not match:
        return raw
    label = f"{match.group(1)} phòng ngủ"
    if match.group(2):
        label += " + 1 phòng đa năng"
    return label


def compress_ranges(numbers: list[int]) -> str:
    """[6,7,8,10] -> '6-8, 10' (dùng để mô tả dải tầng)."""
    values = sorted({n for n in numbers if n is not None})
    if not values:
        return ""
    parts: list[str] = []
    start = prev = values[0]
    for current in values[1:]:
        if current == prev + 1:
            prev = current
            continue
        parts.append(str(start) if start == prev else f"{start}-{prev}")
        start = prev = current
    parts.append(str(start) if start == prev else f"{start}-{prev}")
    return ", ".join(parts)


def fmt_area(value: float | None) -> str:
    """102.33 -> '102,33 m2' (dấu phẩy thập phân kiểu Việt Nam)."""
    if value is None:
        return "n/a"
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{text.replace('.', ',')} m2"
