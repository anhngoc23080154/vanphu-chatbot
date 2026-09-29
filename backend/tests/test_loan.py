"""Kiểm thử tính lãi vay: đọc dữ kiện từ câu hỏi và phép tính."""

from __future__ import annotations

import pytest

from rag.schemas import HistoryItem
from rag.services import loan
from rag.services.query_analyzer import analyze
from rag.text import normalize_key


def key(text: str) -> str:
    return normalize_key(text)


# --- Đọc số tiền ------------------------------------------------------------
@pytest.mark.parametrize(
    "message,expected",
    [
        ("Tôi dự định vay 10 tỷ", 10_000_000_000),
        ("vay 1,5 tỷ", 1_500_000_000),
        ("vay 1.5 tỷ", 1_500_000_000),
        ("vay 3 tỉ", 3_000_000_000),
        ("vay 500 triệu", 500_000_000),
        ("vay 2 tỷ 500 triệu", 2_500_000_000),
        ("vay 1.500 triệu", 1_500_000_000),
        ("vay 10000000000 đồng", 10_000_000_000),
        ("vay 10.000.000.000 đồng", 10_000_000_000),
        ("vay 800 tr", 800_000_000),
    ],
)
def test_doc_so_tien_vay(message: str, expected: int):
    assert loan.parse_principal(key(message)) == expected


def test_khong_co_so_tien_thi_tra_ve_none():
    assert loan.parse_principal(key("tôi muốn vay tiền")) is None


def test_tu_choi_so_tien_ngoai_gioi_han():
    assert loan.parse_principal(key("vay 5000 tỷ")) is None
    assert loan.parse_principal(key("vay 100 nghìn")) is None


# --- Đọc thời hạn -----------------------------------------------------------
@pytest.mark.parametrize(
    "message,expected",
    [
        ("sau 1 năm", 12),
        ("vay 20 năm", 240),
        ("trong 18 tháng", 18),
        ("1 năm 6 tháng", 18),
    ],
)
def test_doc_thoi_han(message: str, expected: int):
    assert loan.parse_term_months(key(message)) == expected


def test_huong_nam_khong_bi_hieu_thanh_so_nam():
    """'hướng Nam' bỏ dấu thành 'HUONG NAM', không được nhận là số năm."""
    assert loan.parse_term_months(key("căn hộ hướng Nam")) is None


def test_thoi_han_qua_dai_bi_tu_choi():
    assert loan.parse_term_months(key("vay 50 năm")) is None


# --- Đọc lãi suất -----------------------------------------------------------
@pytest.mark.parametrize(
    "message,expected",
    [
        ("lãi suất 5%", 5.0),
        ("lãi suất 8,5%/năm", 8.5),
        ("lãi suất là 10.5%", 10.5),
        ("với 5 %", 5.0),
    ],
)
def test_doc_lai_suat(message: str, expected: float):
    assert loan.parse_rate(key(message)) == pytest.approx(expected)


def test_khong_nham_ty_le_vay_voi_lai_suat():
    """'vay 70% giá trị căn hộ' là tỷ lệ vay, không phải lãi suất."""
    assert loan.parse_rate(key("tôi muốn vay 70% giá trị căn hộ")) is None


# --- Phép tính --------------------------------------------------------------
def test_vi_du_chinh_10_ty_5_phan_tram_1_nam():
    """Ví dụ gốc của yêu cầu: 10 tỷ, 5%/năm, 1 năm, lãi đơn ra 10,5 tỷ."""
    result = loan.calculate(10_000_000_000, 5.0, 12)
    assert result.simple_interest == pytest.approx(500_000_000)
    assert result.simple_total == pytest.approx(10_500_000_000)


def test_du_no_giam_dan_cho_vi_du_chinh():
    result = loan.calculate(10_000_000_000, 5.0, 12)
    assert result.monthly_principal == pytest.approx(833_333_333, rel=1e-6)
    # Tháng đầu: gốc + lãi trên toàn bộ dư nợ.
    assert result.first_payment == pytest.approx(875_000_000, rel=1e-6)
    # Tháng cuối: gốc + lãi trên phần dư nợ còn lại nhỏ nhất.
    assert result.last_payment == pytest.approx(836_805_555, rel=1e-6)
    assert result.declining_interest == pytest.approx(270_833_333, rel=1e-6)
    assert result.declining_total == pytest.approx(10_270_833_333, rel=1e-6)


def test_du_no_giam_dan_re_hon_lai_don():
    """Trả dần gốc thì tổng lãi luôn thấp hơn lãi đơn trên toàn bộ gốc."""
    for months in (12, 60, 240):
        result = loan.calculate(10_000_000_000, 10.0, months)
        assert result.declining_interest < result.simple_interest


def test_lai_don_ty_le_thuan_voi_thoi_gian():
    one_year = loan.calculate(1_000_000_000, 6.0, 12)
    two_years = loan.calculate(1_000_000_000, 6.0, 24)
    assert two_years.simple_interest == pytest.approx(one_year.simple_interest * 2)


def test_lai_suat_bang_khong():
    result = loan.calculate(1_000_000_000, 0.0, 12)
    assert result.simple_interest == 0
    assert result.declining_interest == 0
    assert result.simple_total == result.declining_total == 1_000_000_000


def test_tu_choi_dau_vao_khong_hop_le():
    with pytest.raises(ValueError):
        loan.calculate(0, 5.0, 12)
    with pytest.raises(ValueError):
        loan.calculate(1_000_000_000, 5.0, 0)


# --- Định dạng --------------------------------------------------------------
@pytest.mark.parametrize(
    "amount,expected",
    [
        (10_500_000_000, "10,5 tỷ đồng"),
        (10_000_000_000, "10 tỷ đồng"),
        (875_000_000, "875 triệu đồng"),
        (500_000_000, "500 triệu đồng"),
    ],
)
def test_dinh_dang_tien(amount: int, expected: str):
    assert loan.fmt_money(amount) == expected


def test_dinh_dang_thoi_han():
    assert loan.fmt_term(12) == "1 năm (12 tháng)"
    assert loan.fmt_term(240) == "20 năm (240 tháng)"
    assert loan.fmt_term(18) == "1 năm 6 tháng (18 tháng)"
    assert loan.fmt_term(6) == "6 tháng"


def test_mo_ta_chua_du_hai_cach_tinh():
    text = loan.describe(loan.calculate(10_000_000_000, 5.0, 12))
    assert "10,5 tỷ đồng" in text
    assert "10,271 tỷ đồng" in text
    assert "lãi đơn" in text and "dư nợ giảm dần" in text


# --- Nhận diện ý định trong câu hỏi -----------------------------------------
def test_nhan_dien_cau_hoi_tinh_vay():
    intent = analyze("Tôi dự định vay 10 tỷ, tính cho tôi số tiền phải trả sau 1 năm")
    assert intent.needs_loan()
    assert intent.loan_principal == 10_000_000_000
    assert intent.loan_months == 12
    assert intent.loan_rate is None  # dùng mức tham chiếu của hệ thống


def test_nhan_dien_khi_khach_tu_neu_lai_suat():
    intent = analyze("Vay 2 tỷ trong 20 năm lãi suất 8,5% thì mỗi tháng trả bao nhiêu?")
    assert intent.needs_loan()
    assert (intent.loan_principal, intent.loan_months, intent.loan_rate) == (
        2_000_000_000,
        240,
        8.5,
    )


@pytest.mark.parametrize(
    "message",
    [
        "Khách hàng chậm thanh toán sẽ bị phạt lãi suất bao nhiêu?",
        "Chủ đầu tư giao nhà trễ bị phạt lãi suất bao nhiêu?",
        "Dự án có ngân hàng bảo lãnh hay không?",
        "Phí quản lý bao nhiêu một tháng?",
    ],
)
def test_khong_chiem_cau_hoi_khac(message: str):
    """Câu hỏi có chữ 'lãi suất' nhưng không phải yêu cầu tính vay."""
    intent = analyze(message)
    assert not intent.needs_loan()
    assert not intent.loan_missing_amount()


def test_hoi_so_tien_khi_khach_chua_neu():
    intent = analyze("Tôi muốn vay tiền mua căn hộ, tính giúp tôi")
    assert not intent.needs_loan()
    assert intent.loan_missing_amount()


def test_cau_hoi_noi_tiep_ke_thua_so_tien_vay():
    history = [
        HistoryItem(role="user", content="Vay 10 tỷ tính cho tôi sau 1 năm"),
        HistoryItem(role="assistant", content="Dạ tổng phải trả 10,5 tỷ đồng."),
    ]
    intent = analyze("Thế vay 20 năm thì sao?", history)
    assert intent.needs_loan()
    assert intent.loan_principal == 10_000_000_000
    assert intent.loan_months == 240  # kỳ hạn mới của lượt này
