"""Tính lãi vay mua bất động sản - dữ liệu mô phỏng cho bản demo.

Toàn bộ phép tính chạy bằng Python, KHÔNG nhờ mô hình ngôn ngữ làm toán, vì mô
hình dễ sai số học. Mô hình chỉ diễn đạt lại con số đã tính sẵn.

Hai cách tính được trình bày song song:
  * Lãi đơn trên toàn bộ gốc: gốc x lãi suất x số năm. Dễ hiểu, dùng làm con số
    tham chiếu chính.
  * Dư nợ giảm dần, gốc trả đều: cách các ngân hàng Việt Nam thực dùng cho vay
    mua nhà. Lãi mỗi tháng tính trên phần gốc còn lại nên giảm dần.

Mọi con số chỉ mang tính tham khảo, không phải cam kết của chủ đầu tư hay ngân hàng.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..text import normalize_key

# --- Giới hạn hợp lý, tránh con số vô nghĩa ---------------------------------
MIN_PRINCIPAL = 1_000_000  # 1 triệu đồng
MAX_PRINCIPAL = 1_000_000_000_000  # 1000 tỷ đồng
MIN_MONTHS = 1
MAX_MONTHS = 480  # 40 năm
MAX_ANNUAL_RATE = 30.0  # phần trăm mỗi năm

BILLION = 1_000_000_000
MILLION = 1_000_000

# Đơn vị tiền trong tiếng Việt, viết theo dạng đã bỏ dấu và viết hoa.
_MONEY_UNITS = {
    "TY": BILLION,
    "TI": BILLION,
    "TRIEU": MILLION,
    "TR": MILLION,
    "NGHIN": 1_000,
    "NGAN": 1_000,
    "K": 1_000,
}

# Số kèm đơn vị: '10 TY', '1,5 TY', '500 TRIEU'. Đơn vị dài đặt trước đơn vị ngắn.
_RE_MONEY_UNIT = re.compile(
    r"(\d[\d.,]*)\s*(TRIEU|NGHIN|NGAN|TY|TI|TR|K)\b"
)
# Số tiền viết đầy đủ: '10000000000' hoặc '10.000.000.000'.
_RE_MONEY_BARE = re.compile(r"\b(\d[\d.]{5,}\d|\d{7,})\b")

_RE_YEARS = re.compile(r"(\d+(?:[.,]\d+)?)\s*NAM\b")
_RE_MONTHS = re.compile(r"(\d+)\s*THANG\b")
# Lãi suất ghi kèm từ khoá, ví dụ 'LAI SUAT 8,5%'.
_RE_RATE_LABELED = re.compile(r"LAI SUAT[^\d%]{0,12}(\d+(?:[.,]\d+)?)\s*%")
_RE_RATE_BARE = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")

# Từ khoá cho biết câu hỏi có liên quan tới vay vốn, dùng để bắt đầu đọc số tiền.
_LOAN_KEYWORDS = (
    "VAY", "TRA GOP", "GOP", "LAI SUAT", "KHOAN VAY", "GOI VAY",
    "TIEN LAI", "TRA LAI", "THE CHAP", "TRA NO",
)
# Từ khoá hẹp hơn, cho biết khách thực sự muốn vay. Cần thiết vì "lãi suất" còn
# xuất hiện trong câu hỏi khác, ví dụ lãi suất phạt khi chậm thanh toán.
_BORROW_KEYWORDS = ("VAY", "TRA GOP", "GOI VAY", "KHOAN VAY", "THE CHAP")
# Động từ cho biết khách muốn được tính toán cụ thể.
_CALC_KEYWORDS = (
    "TINH", "BAO NHIEU", "MAY TIEN", "TONG SO TIEN", "PHAI TRA", "MOI THANG",
    "HANG THANG", "MOT THANG",
)


def parse_vn_number(raw: str) -> float | None:
    """Đọc số theo cách viết Việt Nam.

    '1,5' -> 1.5 (dấu phẩy là thập phân)
    '1.500' -> 1500 (dấu chấm là phân cách nghìn)
    '10.000.000.000' -> 10000000000
    '1.5' -> 1.5 (dấu chấm kèm 1-2 chữ số là thập phân)
    """
    text = raw.strip().replace(" ", "")
    if not text:
        return None

    if "," in text:
        # Dấu phẩy là thập phân, dấu chấm còn lại là phân cách nghìn.
        text = text.replace(".", "").replace(",", ".")
    elif "." in text:
        parts = text.split(".")
        if all(len(part) == 3 for part in parts[1:]):
            # Mọi nhóm sau dấu chấm đủ 3 chữ số => phân cách nghìn.
            text = "".join(parts)
        elif len(parts) == 2 and len(parts[1]) <= 2:
            pass  # giữ nguyên, dấu chấm là thập phân
        else:
            text = "".join(parts)

    try:
        return float(text)
    except ValueError:
        return None


def parse_principal(text: str) -> int | None:
    """Số tiền vay từ câu hỏi đã chuẩn hoá. Cộng dồn '2 tỷ 500 triệu'."""
    total = 0.0
    found = False
    for number, unit in _RE_MONEY_UNIT.findall(text):
        value = parse_vn_number(number)
        if value is None:
            continue
        total += value * _MONEY_UNITS[unit]
        found = True

    if not found:
        for candidate in _RE_MONEY_BARE.findall(text):
            value = parse_vn_number(candidate)
            if value is not None and value >= MIN_PRINCIPAL:
                total = value
                found = True
                break

    if not found:
        return None
    amount = int(round(total))
    if amount < MIN_PRINCIPAL or amount > MAX_PRINCIPAL:
        return None
    return amount


def parse_term_months(text: str) -> int | None:
    """Thời hạn vay quy về số tháng. Hỗ trợ '1 năm 6 tháng'."""
    months = 0.0
    found = False

    match = _RE_YEARS.search(text)
    if match:
        years = parse_vn_number(match.group(1))
        if years is not None:
            months += years * 12
            found = True

    match = _RE_MONTHS.search(text)
    if match:
        value = parse_vn_number(match.group(1))
        if value is not None:
            months += value
            found = True

    if not found:
        return None
    total = int(round(months))
    if total < MIN_MONTHS or total > MAX_MONTHS:
        return None
    return total


def parse_rate(text: str) -> float | None:
    """Lãi suất phần trăm mỗi năm do khách nêu, nếu có.

    Ưu tiên con số đứng cạnh từ 'lãi suất'. Nếu chỉ có phần trăm trơ thì chỉ nhận
    khi nhỏ hơn ngưỡng hợp lý, tránh nhầm với kiểu 'vay 70% giá trị căn hộ'.
    """
    match = _RE_RATE_LABELED.search(text)
    if match:
        value = parse_vn_number(match.group(1))
        if value is not None and 0 < value <= MAX_ANNUAL_RATE:
            return value

    for candidate in _RE_RATE_BARE.findall(text):
        value = parse_vn_number(candidate)
        if value is not None and 0 < value <= MAX_ANNUAL_RATE:
            return value
    return None


def has_loan_intent(text: str) -> bool:
    return any(keyword in text for keyword in _LOAN_KEYWORDS)


def has_borrow_intent(text: str) -> bool:
    """Khách nói tới việc đi vay, không chỉ nhắc tới hai chữ lãi suất."""
    return any(keyword in text for keyword in _BORROW_KEYWORDS)


def wants_calculation(text: str) -> bool:
    return any(keyword in text for keyword in _CALC_KEYWORDS)


# --- Định dạng tiền ---------------------------------------------------------
def _trim(value: float, decimals: int) -> str:
    text = f"{value:.{decimals}f}".rstrip("0").rstrip(".")
    return text.replace(".", ",") or "0"


def fmt_money(amount: float) -> str:
    """10_500_000_000 -> '10,5 tỷ đồng'; 875_000_000 -> '875 triệu đồng'."""
    if amount >= BILLION:
        return f"{_trim(amount / BILLION, 3)} tỷ đồng"
    if amount >= MILLION:
        return f"{_trim(amount / MILLION, 2)} triệu đồng"
    return f"{int(round(amount)):,}".replace(",", ".") + " đồng"


def fmt_term(months: int) -> str:
    if months % 12 == 0:
        return f"{months // 12} năm ({months} tháng)"
    if months > 12:
        return f"{months // 12} năm {months % 12} tháng ({months} tháng)"
    return f"{months} tháng"


# --- Phép tính --------------------------------------------------------------
@dataclass
class LoanResult:
    """Kết quả tính lãi vay theo hai cách, cùng dữ liệu đầu vào."""

    principal: int
    annual_rate: float  # phần trăm mỗi năm
    months: int
    rate_from_customer: bool

    # Lãi đơn trên toàn bộ gốc.
    simple_interest: float
    simple_total: float

    # Dư nợ giảm dần, gốc trả đều.
    monthly_principal: float
    first_payment: float
    last_payment: float
    declining_interest: float
    declining_total: float

    @property
    def years(self) -> float:
        return self.months / 12


def calculate(principal: int, annual_rate: float, months: int) -> LoanResult:
    """Tính lãi theo cả hai cách. `annual_rate` là phần trăm mỗi năm."""
    if principal <= 0:
        raise ValueError("Số tiền vay phải lớn hơn 0")
    if months <= 0:
        raise ValueError("Thời hạn vay phải lớn hơn 0")

    rate = annual_rate / 100
    monthly_rate = rate / 12

    # Lãi đơn: gốc x lãi suất x số năm.
    simple_interest = principal * rate * (months / 12)

    # Dư nợ giảm dần, gốc trả đều mỗi tháng.
    monthly_principal = principal / months
    first_interest = principal * monthly_rate
    last_interest = monthly_principal * monthly_rate
    # Tổng lãi = lãi suất tháng x gốc x (số tháng + 1) / 2, do dư nợ giảm đều.
    declining_interest = monthly_rate * principal * (months + 1) / 2

    return LoanResult(
        principal=principal,
        annual_rate=annual_rate,
        months=months,
        rate_from_customer=False,
        simple_interest=simple_interest,
        simple_total=principal + simple_interest,
        monthly_principal=monthly_principal,
        first_payment=monthly_principal + first_interest,
        last_payment=monthly_principal + last_interest,
        declining_interest=declining_interest,
        declining_total=principal + declining_interest,
    )


def describe(result: LoanResult) -> str:
    """Khối văn bản chứa số liệu đã tính, đưa vào ngữ cảnh cho mô hình."""
    nguon = "theo mức khách đưa ra" if result.rate_from_customer else "mức tham chiếu của chương trình demo"
    lines = [
        f"Số tiền vay: {fmt_money(result.principal)}.",
        f"Lãi suất: {_trim(result.annual_rate, 2)}% mỗi năm ({nguon}).",
        f"Thời hạn: {fmt_term(result.months)}.",
        "",
        "Cách 1 - lãi đơn trên toàn bộ gốc (công thức gốc x lãi suất x số năm):",
        f"- Tiền lãi: {fmt_money(result.simple_interest)}.",
        f"- Tổng phải trả: {fmt_money(result.simple_total)}.",
        "",
        "Cách 2 - dư nợ giảm dần, gốc trả đều mỗi tháng (cách ngân hàng thường áp dụng):",
        f"- Gốc trả mỗi tháng: {fmt_money(result.monthly_principal)}.",
        f"- Tháng đầu trả: {fmt_money(result.first_payment)}.",
        f"- Tháng cuối trả: {fmt_money(result.last_payment)}.",
        f"- Tổng tiền lãi: {fmt_money(result.declining_interest)}.",
        f"- Tổng phải trả: {fmt_money(result.declining_total)}.",
    ]
    return "\n".join(lines)
