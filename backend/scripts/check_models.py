"""Kiểm tra API key Gemini: model nào dùng được, embedding trả về bao nhiêu chiều.

Chạy:  python -m scripts.check_models
"""

from __future__ import annotations

import asyncio

from scripts import _bootstrap  # noqa: F401  (thiết lập sys.path + UTF-8)

from rag.config import get_settings  # noqa: E402
from rag.services.gemini import GeminiService  # noqa: E402


async def main() -> int:
    settings = get_settings()
    if not settings.gemini_api_key:
        print("Thiếu GEMINI_API_KEY trong .env")
        return 1

    service = GeminiService(settings)
    types = service.types

    print("=== Embedding ===")
    print(f"Model: {settings.gemini_embed_model}, số chiều mong muốn: {settings.embed_dim}")
    try:
        vector = await service.embed_query("Dự án Vlasta Premier Phú Thuận ở đâu?")
        norm = sum(value * value for value in vector) ** 0.5
        print(f"OK - nhận được {len(vector)} chiều, độ dài vector = {norm:.4f}")
        if len(vector) != settings.embed_dim:
            print(f"CẢNH BÁO: số chiều khác EMBED_DIM ({settings.embed_dim})")
    except Exception as exc:  # noqa: BLE001
        print(f"LỖI: {exc}")
        return 1

    print("\n=== Model sinh câu trả lời ===")
    for model in settings.chat_model_chain:
        contents = [types.Content(role="user", parts=[types.Part(text="Trả lời đúng một từ: xin chào")])]
        config = types.GenerateContentConfig(temperature=0.0, max_output_tokens=64)
        try:
            client, _ = service._ensure_client()  # noqa: SLF001 - script chẩn đoán
            response = await client.aio.models.generate_content(
                model=model, contents=contents, config=config
            )
            text = (getattr(response, "text", None) or "").strip()
            print(f"  {model:<28} OK  -> {text[:60]!r}")
        except Exception as exc:  # noqa: BLE001
            code = getattr(exc, "code", "?")
            print(f"  {model:<28} LỖI (code={code}): {str(exc)[:140]}")

    print("\nGợi ý: đặt GEMINI_CHAT_MODEL là model đầu tiên báo OK ở trên.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
