"""Kiểm thử luồng chat đầu-cuối với Gemini và Supabase giả lập.

Mục đích: xác nhận phần điều phối, dựng ngữ cảnh và chọn ảnh đính kèm hoạt động
đúng mà không cần gọi dịch vụ ngoài.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from rag.api import create_app
from rag.config import Settings
from rag.errors import UpstreamRateLimited
from rag.schemas import ChatRequest
from rag.services.chat import ChatService, get_chat_service
from rag.services.supabase_repo import Doc


class FakePart:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeContent:
    def __init__(self, role: str, parts: list[FakePart]) -> None:
        self.role = role
        self.parts = parts


class FakeTypes:
    """Bản sao tối giản của google.genai.types dùng trong test."""

    Part = FakePart
    Content = FakeContent


class FakeGemini:
    def __init__(self, reply: str = "Dạ, em xin trả lời.", error: Exception | None = None) -> None:
        self.reply = reply
        self.error = error
        self.types = FakeTypes()
        self.last_contents: list[Any] = []
        self.last_system = ""
        self.embed_calls = 0
        self.generate_calls = 0

    async def embed_query(self, text: str) -> list[float]:
        self.embed_calls += 1
        self.last_query = text
        return [0.1] * 768

    async def generate(self, contents: list[Any], system_instruction: str) -> tuple[str, str]:
        self.generate_calls += 1
        self.last_contents = contents
        self.last_system = system_instruction
        if self.error:
            raise self.error
        return self.reply, "fake-model"

    @property
    def context_text(self) -> str:
        return self.last_contents[-1].parts[0].text if self.last_contents else ""


class FakeRepo:
    def __init__(
        self,
        docs: list[Doc] | None = None,
        media: list[Doc] | None = None,
        units: list[dict[str, Any]] | None = None,
        units_total: int = 0,
    ) -> None:
        self.docs = docs or []
        self.media = media or []
        self.units = units or []
        self.units_total = units_total
        self.find_units_kwargs: dict[str, Any] | None = None

    async def match_documents(self, embedding, *, match_count, sources=None):
        if sources == ["media"]:
            return self.media[:match_count]
        return self.docs[:match_count]

    async def find_units(self, **kwargs):
        self.find_units_kwargs = kwargs
        return self.units, self.units_total

    async def aclose(self) -> None:
        return None


def make_doc(content: str, *, source="qa", similarity=0.8, metadata=None, title="") -> Doc:
    return Doc(
        id="1",
        source=source,
        section=source,
        title=title,
        content=content,
        metadata=metadata or {},
        similarity=similarity,
    )


def make_settings(**overrides) -> Settings:
    base = dict(
        gemini_api_key="x",
        supabase_url="https://x.supabase.co",
        supabase_secret_key="x",
        top_k=6,
        media_top_k=3,
        media_sim_threshold=0.62,
        units_limit=20,
    )
    base.update(overrides)
    return Settings(**base)


def service(gemini: FakeGemini, repo: FakeRepo, **settings_overrides) -> ChatService:
    return ChatService(gemini=gemini, repo=repo, settings=make_settings(**settings_overrides))


# --- Luồng cơ bản -----------------------------------------------------------
async def test_tra_loi_cau_hoi_thong_thuong():
    gemini = FakeGemini(reply="Dạ, chủ đầu tư là New Tech ạ.")
    repo = FakeRepo(docs=[make_doc("Câu hỏi: Chủ đầu tư\nTrả lời: New Tech")])
    response = await service(gemini, repo).answer(
        ChatRequest(message="Chủ đầu tư dự án là ai?", session_id="s1", history=[])
    )
    assert response.reply == "Dạ, chủ đầu tư là New Tech ạ."
    assert response.session_id == "s1"
    assert response.attachments == []
    # Đúng một lần embed và một lần generate (hạn mức free tier).
    assert gemini.embed_calls == 1 and gemini.generate_calls == 1
    assert "New Tech" in gemini.context_text
    assert "Trợ lý ảo Văn Phú" in gemini.last_system


async def test_sinh_session_id_khi_frontend_khong_gui():
    gemini = FakeGemini()
    repo = FakeRepo(docs=[make_doc("nội dung")])
    response = await service(gemini, repo).answer(
        ChatRequest(message="Xin chào", session_id="", history=[])
    )
    assert response.session_id and len(response.session_id) >= 32


async def test_khong_co_ngu_canh_thi_khong_goi_model():
    gemini = FakeGemini()
    repo = FakeRepo()
    response = await service(gemini, repo).answer(
        ChatRequest(message="Câu hỏi lạ", session_id="s1", history=[])
    )
    assert "chưa có thông tin" in response.reply
    assert gemini.generate_calls == 0


# --- Tra cứu giỏ hàng -------------------------------------------------------
async def test_cau_hoi_ma_can_kich_hoat_tra_cuu_sql():
    gemini = FakeGemini()
    repo = FakeRepo(
        docs=[make_doc("thông tin chung")],
        units=[
            {
                "unit_code": "A-06-01",
                "unit_code_commercial": "CH-A06-01",
                "tower": "A",
                "floor": 6,
                "floor_label": "6",
                "product_type": "CH",
                "area_gross": 102.33,
                "area_net": 90.48,
                "bedrooms": "3BR",
                "balcony_dir": "Nam",
                "door_dir": "Bắc",
            }
        ],
        units_total=1,
    )
    await service(gemini, repo).answer(
        ChatRequest(message="Căn A-06-01 diện tích bao nhiêu?", session_id="s1", history=[])
    )
    assert repo.find_units_kwargs["codes_plain"] == ["A-06-01"]
    context = gemini.context_text
    assert "DỮ LIỆU GIỎ HÀNG" in context
    assert "102,33 m2" in context and "90,48 m2" in context


async def test_bao_tong_so_khi_ket_qua_bi_cat_bot():
    gemini = FakeGemini()
    units = [
        {
            "unit_code": f"B-{floor:02d}-03",
            "tower": "B",
            "floor": floor,
            "floor_label": str(floor),
            "product_type": "CH",
            "area_gross": 77.6,
            "area_net": 69.7,
            "bedrooms": "2BR",
        }
        for floor in range(6, 26)
    ]
    repo = FakeRepo(docs=[make_doc("x")], units=units, units_total=162)
    await service(gemini, repo).answer(
        ChatRequest(message="Căn 2 phòng ngủ tháp B rộng bao nhiêu?", session_id="s1", history=[])
    )
    assert repo.find_units_kwargs["tower"] == "B"
    assert repo.find_units_kwargs["bedroom_count"] == 2
    assert "tổng cộng 162 căn phù hợp" in gemini.context_text


async def test_bao_khong_tim_thay_khi_ma_can_khong_ton_tai():
    gemini = FakeGemini()
    repo = FakeRepo(docs=[make_doc("thông tin chung")], units=[], units_total=0)
    await service(gemini, repo).answer(
        ChatRequest(message="Căn A-99-99 còn không?", session_id="s1", history=[])
    )
    assert "Không tìm thấy căn nào khớp" in gemini.context_text


async def test_cau_hoi_thuong_khong_goi_tra_cuu_giỏ_hang():
    gemini = FakeGemini()
    repo = FakeRepo(docs=[make_doc("thông tin chung")])
    await service(gemini, repo).answer(
        ChatRequest(message="Tiện ích dự án gồm những gì?", session_id="s1", history=[])
    )
    assert repo.find_units_kwargs is None


# --- Ảnh đính kèm -----------------------------------------------------------
def _media(similarity: float, url="https://x/p.jpg", media_type="image") -> Doc:
    return make_doc(
        "Poster tổng quan dự án",
        source="media",
        similarity=similarity,
        title="Poster tổng quan",
        metadata={"url": url, "type": media_type},
    )


async def test_dinh_kem_anh_khi_khach_hoi_hinh():
    gemini = FakeGemini()
    repo = FakeRepo(
        docs=[make_doc("x")],
        media=[_media(0.55), _media(0.52, url="https://x/mb.jpg"), _media(0.2, url="https://x/z.jpg")],
    )
    response = await service(gemini, repo).answer(
        ChatRequest(message="Cho tôi xem poster dự án", session_id="s1", history=[])
    )
    # Ngưỡng được nới khi khách hỏi thẳng về hình ảnh.
    assert len(response.attachments) == 2
    assert response.attachments[0].type == "image"
    assert "HÌNH ẢNH - TÀI LIỆU" in gemini.context_text


async def test_khong_dinh_kem_anh_khi_do_lien_quan_thap():
    gemini = FakeGemini()
    repo = FakeRepo(docs=[make_doc("x")], media=[_media(0.4)])
    response = await service(gemini, repo).answer(
        ChatRequest(message="Phí quản lý bao nhiêu?", session_id="s1", history=[])
    )
    assert response.attachments == []


async def test_dinh_kem_mot_anh_khi_rat_lien_quan():
    gemini = FakeGemini()
    repo = FakeRepo(docs=[make_doc("x")], media=[_media(0.9), _media(0.88, url="https://x/b.jpg")])
    response = await service(gemini, repo).answer(
        ChatRequest(message="Dự án có tiện ích gì?", session_id="s1", history=[])
    )
    assert len(response.attachments) == 1


async def test_bo_qua_media_thieu_url():
    gemini = FakeGemini()
    bad = make_doc("x", source="media", similarity=0.9, metadata={})
    repo = FakeRepo(docs=[make_doc("x")], media=[bad])
    response = await service(gemini, repo).answer(
        ChatRequest(message="Xem ảnh dự án", session_id="s1", history=[])
    )
    assert response.attachments == []


# --- Lịch sử hội thoại và lỗi ------------------------------------------------
async def test_lich_su_duoc_chuyen_thanh_luot_hoi_thoai():
    from rag.schemas import HistoryItem

    gemini = FakeGemini()
    repo = FakeRepo(docs=[make_doc("x")])
    history = [
        HistoryItem(role="user", content="Căn A-06-01 diện tích bao nhiêu?"),
        HistoryItem(role="assistant", content="Dạ 102,33 m2 ạ."),
    ]
    await service(gemini, repo).answer(
        ChatRequest(message="Còn hướng ban công?", session_id="s1", history=history)
    )
    roles = [content.role for content in gemini.last_contents]
    assert roles == ["user", "model", "user"]
    # Câu hỏi nối tiếp kế thừa mã căn từ lượt trước.
    assert repo.find_units_kwargs["codes_plain"] == ["A-06-01"]


async def test_loi_gemini_duoc_chuyen_thanh_thong_bao_tieng_viet():
    gemini = FakeGemini(error=UpstreamRateLimited())
    repo = FakeRepo(docs=[make_doc("x")])
    with pytest.raises(UpstreamRateLimited) as exc:
        await service(gemini, repo).answer(
            ChatRequest(message="Câu hỏi", session_id="s1", history=[])
        )
    assert "quá tải" in exc.value.detail


async def test_markdown_bi_loai_bo_khoi_cau_tra_loi():
    gemini = FakeGemini(reply="**Diện tích** là 90,48 m2.\n* Ban công hướng Nam")
    repo = FakeRepo(docs=[make_doc("x")])
    response = await service(gemini, repo).answer(
        ChatRequest(message="Căn A-06-01?", session_id="s1", history=[])
    )
    assert "**" not in response.reply
    assert "- Ban công hướng Nam" in response.reply


# --- Tầng HTTP ---------------------------------------------------------------
def test_api_tra_loi_dung_dinh_dang():
    gemini = FakeGemini(reply="Dạ em trả lời.")
    repo = FakeRepo(docs=[make_doc("x")], media=[_media(0.9)])
    app = create_app()
    app.dependency_overrides[get_chat_service] = lambda: service(gemini, repo)

    with TestClient(app) as client:
        response = client.post(
            "/api/chat",
            json={"message": "Xin chào", "session_id": "abc", "history": []},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "Dạ em trả lời."
    assert body["session_id"] == "abc"
    assert isinstance(body["attachments"], list)


def test_api_loi_validation_tra_detail_dang_chuoi():
    with TestClient(create_app()) as client:
        response = client.post("/api/chat", json={"message": "", "session_id": "a", "history": []})
    assert response.status_code == 422
    # Frontend hiển thị detail nguyên văn nên bắt buộc phải là chuỗi.
    assert isinstance(response.json()["detail"], str)


def test_api_health():
    with TestClient(create_app()) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_keepalive_tu_choi_khi_sai_secret(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "dung-secret")
    from rag import config

    config.get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            assert client.get("/api/cron/keepalive").status_code == 401
            assert (
                client.get(
                    "/api/cron/keepalive", headers={"Authorization": "Bearer sai-secret"}
                ).status_code
                == 401
            )
    finally:
        config.get_settings.cache_clear()
