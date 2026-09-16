"""Kiểm thử bộ tạo đoạn văn bản cho embedding."""

from __future__ import annotations

import pytest

from rag.ingest.chunks import (
    MAX_CHUNK_CHARS,
    SOURCE_MEDIA,
    SOURCE_QA,
    SOURCE_UNITS,
    media_chunks,
    qa_chunks,
    unit_summary_chunks,
)
from rag.ingest.units import QAItem, UnitRow
from rag.services.chat import sanitize_reply


def _apartment(floor: int, unit_no: str = "01", **kwargs) -> UnitRow:
    defaults = dict(
        unit_code=f"A-{floor:02d}-{unit_no}",
        unit_code_alt=f"A-NN-{unit_no}",
        unit_code_commercial=f"CH-A{floor:02d}-{unit_no}",
        tower="A",
        floor=floor,
        floor_label=str(floor),
        unit_no=unit_no,
        product_type="CH",
        area_gross=102.33,
        area_net=90.48,
        bedrooms="3BR",
        bedroom_count=3,
        balcony_dir="Nam",
        door_dir="Bắc",
        sheet_row=floor,
    )
    defaults.update(kwargs)
    return UnitRow(**defaults)


def test_qa_chunk_giu_ca_cau_hoi_va_tra_loi():
    chunks = qa_chunks([QAItem(stt="1", section="Chung", question="Tên dự án", answer="Vlasta Premier")])
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.source == SOURCE_QA
    assert "Tên dự án" in chunk.content and "Vlasta Premier" in chunk.content
    assert chunk.title == "Tên dự án"


def test_qa_chunk_tach_cau_tra_loi_qua_dai():
    answer = "\n".join(f"Đoạn nội dung số {i} " + "x" * 400 for i in range(30))
    chunks = qa_chunks([QAItem(stt="9", section="Pháp lý", question="Quy định?", answer=answer)])
    assert len(chunks) > 1
    assert all(len(chunk.content) <= MAX_CHUNK_CHARS for chunk in chunks)
    assert "phần 1/" in chunks[0].content
    # Mỗi phần có id riêng để không ghi đè nhau.
    assert len({chunk.id for chunk in chunks}) == len(chunks)


def test_id_on_dinh_giua_cac_lan_chay():
    item = QAItem(stt="5", section="Chung", question="Hỏi", answer="Đáp")
    assert qa_chunks([item])[0].id == qa_chunks([item])[0].id


def test_layout_gom_cac_can_giong_nhau():
    units = [_apartment(floor) for floor in range(6, 15)]
    chunks = [chunk for chunk in unit_summary_chunks(units) if chunk.section == "layout"]
    assert len(chunks) == 1
    content = chunks[0].content
    assert "Có 9 căn giống nhau" in content
    assert "6-14" in content
    assert "102,33 m2" in content and "90,48 m2" in content
    assert "A-06-01" in content


def test_layout_tach_nhom_khi_dien_tich_khac():
    units = [_apartment(6), _apartment(7, area_net=91.13)]
    chunks = [chunk for chunk in unit_summary_chunks(units) if chunk.section == "layout"]
    assert len(chunks) == 2


def test_penthouse_gom_dien_tich_tung_tang_va_tong():
    units = [
        _apartment(34, product_type="PH", unit_code="A-34-01", unit_code_commercial="PH-A34-03"),
        UnitRow(
            unit_code="A-34-01", unit_code_commercial="PH-A34-03", tower="A", floor=35,
            floor_label="35", product_type="PH", area_gross=141.06, area_net=123.67,
            is_primary=False, sheet_row=35,
        ),
        UnitRow(
            unit_code="A-34-01", unit_code_commercial="PH-A34-03", tower="A", floor=None,
            floor_label="34+35", product_type="PH", area_gross=307.06, area_net=275.5,
            is_primary=False, is_total_row=True, sheet_row=36,
        ),
    ]
    chunks = [chunk for chunk in unit_summary_chunks(units) if chunk.section == "ph"]
    assert len(chunks) == 1
    content = chunks[0].content
    assert "Tầng 34" in content and "Tầng 35" in content and "Tổng cộng" in content
    assert "307,06 m2" in content


def test_co_du_cac_doan_thong_ke_va_huong_dan():
    units = [_apartment(floor) for floor in range(6, 10)]
    sections = {chunk.section for chunk in unit_summary_chunks(units)}
    assert {"layout", "stats", "guide"} <= sections
    assert all(chunk.source == SOURCE_UNITS for chunk in unit_summary_chunks(units))


def test_media_chunk_giu_url_trong_metadata():
    chunks = media_chunks(
        [
            {
                "file": "poster.jpg",
                "url": "https://example.supabase.co/storage/v1/object/public/media/poster.jpg",
                "type": "image",
                "title": "Phối cảnh tổng thể",
                "description": "Poster hai tháp nhìn từ sông",
                "tags": ["poster", "phối cảnh"],
                "category": "poster",
            }
        ]
    )
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.source == SOURCE_MEDIA
    assert chunk.metadata["type"] == "image"
    assert chunk.metadata["url"].endswith("poster.jpg")
    assert "poster" in chunk.content and "phối cảnh" in chunk.content


def test_media_bo_qua_muc_thieu_url():
    assert media_chunks([{"file": "a.jpg", "title": "Chưa upload"}]) == []


# --- Làm sạch câu trả lời ---
def test_sanitize_bo_markdown():
    raw = "## Tiêu đề\n**Diện tích** là *90,48 m2*.\n* Mục một\n* Mục hai\n[Xem](https://a.vn)"
    clean = sanitize_reply(raw)
    assert "**" not in clean and "##" not in clean and "[Xem]" not in clean
    assert "Diện tích là 90,48 m2." in clean
    assert "- Mục một" in clean
    assert "https://a.vn" in clean


def test_sanitize_giu_xuong_dong_don():
    assert sanitize_reply("Dòng 1\nDòng 2\n\n\n\nDòng 3") == "Dòng 1\nDòng 2\n\nDòng 3"


def test_layout_khong_trung_id_khi_chi_khac_dien_tich_thong_thuy():
    """Hai nhóm cùng diện tích tim tường nhưng khác thông thủy phải có id khác nhau.

    Dữ liệu thật có 6 cặp như vậy (ví dụ căn 02 tháp A: 77,61 m2 tim tường
    nhưng thông thủy 69,73 ở tầng thấp và 69,77 ở tầng cao).
    """
    units = [
        _apartment(6, "02", area_gross=77.61, area_net=69.73, bedrooms="2BR", bedroom_count=2),
        _apartment(16, "02", area_gross=77.61, area_net=69.77, bedrooms="2BR", bedroom_count=2),
    ]
    chunks = [chunk for chunk in unit_summary_chunks(units) if chunk.section == "layout"]
    assert len(chunks) == 2
    assert chunks[0].id != chunks[1].id


def test_phat_hien_id_trung():
    from rag.ingest.chunks import DocChunk, assert_unique_ids

    duplicate = [
        DocChunk(key="k", source="qa", content="a", title="Đoạn 1"),
        DocChunk(key="k", source="qa", content="b", title="Đoạn 2"),
    ]
    with pytest.raises(ValueError, match="cùng id"):
        assert_unique_ids(duplicate)


def test_moi_doan_cua_units_summary_co_id_rieng():
    units = [
        _apartment(floor, unit_no, area_gross=area, area_net=area - 8)
        for floor in range(6, 12)
        for unit_no, area in (("01", 102.33), ("02", 77.61), ("03", 79.39))
    ]
    chunks = unit_summary_chunks(units)
    assert len({chunk.id for chunk in chunks}) == len(chunks)
