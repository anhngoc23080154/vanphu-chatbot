"""Kiểm thử bộ phân tích câu hỏi (định tuyến không dùng LLM)."""

from __future__ import annotations

import pytest

from rag.schemas import HistoryItem
from rag.services.query_analyzer import analyze, build_retrieval_text


def test_ma_can_theo_ban_ve():
    intent = analyze("Căn A-06-01 diện tích bao nhiêu?")
    assert intent.unit_codes_plain == ["A-06-01"]
    assert intent.needs_units()


def test_ma_can_viet_thuong_va_thieu_so_khong():
    intent = analyze("cho hỏi căn a-6-1 nhé")
    assert intent.unit_codes_plain == ["A-06-01"]


def test_ma_can_thuong_mai():
    intent = analyze("Thông tin căn CH-A06-01")
    assert intent.unit_codes_commercial == ["CH-A06-01"]
    assert intent.product_type == "CH"


def test_ma_shophouse():
    intent = analyze("Shophouse SH-A01-01 có mấy tầng?")
    assert intent.unit_codes_commercial == ["SH-A01-01"]
    assert intent.product_type == "SH"


def test_ma_theo_giay_phep():
    intent = analyze("Căn A-NN-01 là căn nào?")
    assert intent.unit_codes_alt == ["A-NN-01"]


def test_loc_theo_thap_va_phong_ngu():
    intent = analyze("Căn 2 phòng ngủ tháp B rộng bao nhiêu?")
    assert intent.tower == "B"
    assert intent.bedroom_count == 2
    assert intent.needs_units()


def test_loc_theo_tang_va_huong():
    intent = analyze("Tầng 10 tháp A có những căn nào hướng Nam?")
    assert intent.tower == "A"
    assert intent.floor == 10
    assert intent.direction == "Nam"


def test_huong_ghep():
    intent = analyze("Có căn nào hướng Đông Nam không?")
    assert intent.direction == "Đông Nam"


def test_penthouse_va_thong_ke():
    intent = analyze("Dự án có bao nhiêu căn penthouse?")
    assert intent.product_type == "PH"
    assert intent.wants_stats


def test_y_dinh_xem_hinh():
    for message in ("Cho tôi xem poster dự án", "Có mặt bằng căn hộ không?", "Gửi tôi ảnh 3D"):
        assert analyze(message).wants_image, message


def test_cau_hoi_thuong_khong_kich_hoat_tra_cuu():
    intent = analyze("Chủ đầu tư dự án là ai?")
    assert not intent.needs_units()
    assert not intent.wants_image


def test_cau_hoi_noi_tiep_ke_thua_ma_can():
    history = [
        HistoryItem(role="user", content="Căn A-06-01 diện tích bao nhiêu?"),
        HistoryItem(role="assistant", content="Dạ căn A-06-01 có diện tích tim tường 102,33 m2."),
    ]
    intent = analyze("Còn hướng ban công thì sao?", history)
    assert intent.is_followup
    assert intent.unit_codes_plain == ["A-06-01"]


def test_cau_hoi_noi_tiep_ghep_text_de_embed():
    history = [HistoryItem(role="user", content="Căn 2 phòng ngủ tháp B rộng bao nhiêu?")]
    intent = analyze("Thế còn hướng cửa?", history)
    text = build_retrieval_text("Thế còn hướng cửa?", history, intent)
    assert "tháp B" in text and "hướng cửa" in text


def test_cau_hoi_moi_khong_ke_thua():
    history = [HistoryItem(role="user", content="Căn A-06-01 diện tích bao nhiêu?")]
    intent = analyze("Phí quản lý dự án là bao nhiêu tiền một mét vuông mỗi tháng?", history)
    assert not intent.is_followup
    assert intent.unit_codes_plain == []


@pytest.mark.parametrize(
    "message,expected",
    [
        ("Căn hộ 1PN giá bao nhiêu", 1),
        ("Loại 3 BR còn không", 3),
        ("Tôi cần căn 2 phòng ngủ", 2),
    ],
)
def test_so_phong_ngu_nhieu_cach_viet(message: str, expected: int):
    assert analyze(message).bedroom_count == expected
