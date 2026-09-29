"""Kiểm thử khả năng chịu lỗi tạm thời của lớp bọc Gemini.

Bối cảnh: Gemini thỉnh thoảng trả 503 vì quá tải phía Google (đo thực tế khoảng
30 phần trăm số lần vào giờ cao điểm). Nếu không thử lại thì khách nhận lỗi 503.
"""

from __future__ import annotations

import pytest

from rag.config import Settings
from rag.errors import UpstreamRateLimited
from rag.services.gemini import GeminiService


class FakeAPIError(Exception):
    """Giả lập google.genai.errors.APIError."""

    def __init__(self, code: int, message: str = "loi gia lap") -> None:
        self.code = code
        self.details = {
            "error": {
                "code": code,
                "message": message,
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.RetryInfo",
                        "retryDelay": "2s",
                    }
                ],
            }
        }
        super().__init__(f"{code} {message}")


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeModels:
    """Trả kết quả theo kịch bản định sẵn cho từng model."""

    def __init__(self, script: dict[str, list]) -> None:
        self.script = {name: list(items) for name, items in script.items()}
        self.calls: list[str] = []

    async def generate_content(self, *, model, contents, config):
        self.calls.append(model)
        queue = self.script.get(model)
        if not queue:
            raise FakeAPIError(404, "model khong con dung duoc")
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return FakeResponse(item)

    async def embed_content(self, *, model, contents, config):
        queue = self.script.get("embed", [])
        self.calls.append("embed")
        if queue:
            item = queue.pop(0)
            if isinstance(item, Exception):
                raise item

        class Emb:
            values = [0.3, 0.4]

        class Res:
            embeddings = [Emb()]

        return Res()


class FakeAio:
    def __init__(self, models: FakeModels) -> None:
        self.models = models


class FakeClient:
    def __init__(self, models: FakeModels) -> None:
        self.aio = FakeAio(models)


class FakeTypes:
    class Content:
        def __init__(self, role, parts):
            self.role, self.parts = role, parts

    class Part:
        def __init__(self, text):
            self.text = text

    class GenerateContentConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class EmbedContentConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs


def make_service(script: dict[str, list], **overrides) -> tuple[GeminiService, FakeModels]:
    base = dict(
        gemini_api_key="x",
        supabase_url="https://x.supabase.co",
        supabase_secret_key="x",
        gemini_chat_model="model-chinh",
        gemini_fallback_models="model-du-phong",
        generate_timeout=20.0,
        embed_timeout=8.0,
    )
    base.update(overrides)
    service = GeminiService(Settings(**base))
    models = FakeModels(script)
    service._client = FakeClient(models)  # noqa: SLF001 - thay client thật khi test
    service._types = FakeTypes()  # noqa: SLF001
    return service, models


@pytest.fixture(autouse=True)
def _nhanh(monkeypatch):
    """Bỏ thời gian chờ để test chạy nhanh."""
    import rag.services.gemini as module

    async def khong_cho(_seconds):
        return None

    monkeypatch.setattr(module.asyncio, "sleep", khong_cho)


async def test_thu_lai_cung_model_khi_gemini_bao_503():
    """Đây là ca thường gặp nhất: Gemini quá tải một nhịp rồi trả lời bình thường."""
    service, models = make_service(
        {"model-chinh": [FakeAPIError(503, "high demand"), "Dạ em trả lời."]}
    )
    text, model = await service.generate([], "system")
    assert text == "Dạ em trả lời."
    assert model == "model-chinh"
    # Gọi hai lần cùng một model, không cần đụng tới model dự phòng.
    assert models.calls == ["model-chinh", "model-chinh"]


async def test_chuyen_model_du_phong_khi_model_chinh_bi_404():
    """Model bị Google ngừng cấp trả về 404, thử lại vô ích nên chuyển ngay."""
    service, models = make_service({"model-du-phong": ["Trả lời từ dự phòng."]})
    text, model = await service.generate([], "system")
    assert text == "Trả lời từ dự phòng."
    assert model == "model-du-phong"
    # Chỉ gọi model chính đúng một lần, không thử lại với mã 404.
    assert models.calls.count("model-chinh") == 1


async def test_chuyen_model_du_phong_khi_model_chinh_503_lien_tiep():
    service, models = make_service(
        {
            "model-chinh": [FakeAPIError(503), FakeAPIError(503)],
            "model-du-phong": ["Trả lời từ dự phòng."],
        }
    )
    text, model = await service.generate([], "system")
    assert model == "model-du-phong"
    assert models.calls == ["model-chinh", "model-chinh", "model-du-phong"]


async def test_bao_loi_khi_moi_model_deu_hong():
    service, _ = make_service({})
    with pytest.raises(UpstreamRateLimited):
        await service.generate([], "system")


async def test_noi_dung_rong_thi_chuyen_model_khac():
    service, models = make_service(
        {"model-chinh": ["   "], "model-du-phong": ["Trả lời hợp lệ."]}
    )
    text, model = await service.generate([], "system")
    assert text == "Trả lời hợp lệ."
    assert model == "model-du-phong"


async def test_embed_thu_lai_khi_gap_loi_tam_thoi():
    service, models = make_service({"embed": [FakeAPIError(503)]})
    vector = await service.embed_query("câu hỏi")
    assert len(vector) == 2
    assert models.calls.count("embed") == 2


async def test_embed_bao_loi_khi_thu_lai_van_hong():
    service, _ = make_service({"embed": [FakeAPIError(503), FakeAPIError(503)]})
    with pytest.raises(UpstreamRateLimited):
        await service.embed_query("câu hỏi")


async def test_vector_duoc_chuan_hoa_do_dai_bang_mot():
    """gemini-embedding-001 không tự chuẩn hoá khi số chiều nhỏ hơn 3072."""
    service, _ = make_service({})
    vector = await service.embed_query("câu hỏi")
    do_dai = sum(x * x for x in vector) ** 0.5
    assert do_dai == pytest.approx(1.0)


def test_doc_duoc_thoi_gian_cho_google_yeu_cau():
    from rag.services.gemini import quota_summary, retry_delay_seconds

    error = FakeAPIError(429)
    assert retry_delay_seconds(error) == pytest.approx(2.0)
    assert isinstance(quota_summary(error), str)
