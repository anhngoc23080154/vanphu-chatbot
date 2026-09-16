"""Cấu hình ứng dụng, đọc từ biến môi trường hoặc file .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent
DATA_DIR = BACKEND_DIR / "data"


def _split_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


class Settings(BaseSettings):
    """Biến môi trường của backend.

    Toàn dự án dùng chung MỘT file .env ở thư mục gốc, cho cả backend lẫn
    frontend (Vite đọc file này qua tuỳ chọn envDir trong vite.config.ts).
    Biến môi trường thật luôn được ưu tiên hơn nội dung file.
    File không tồn tại thì bỏ qua, như khi chạy trên Vercel.
    Các biến VITE_ trong file được bỏ qua ở đây nhờ extra="ignore".
    """

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Gemini ---
    gemini_api_key: str = ""
    gemini_chat_model: str = "gemini-3.1-flash-lite"
    gemini_fallback_models: str = "gemini-2.5-flash-lite,gemini-2.5-flash"
    gemini_embed_model: str = "gemini-embedding-001"
    embed_dim: int = 768
    # Gemini tính hạn mức theo TỪNG đoạn trong lô, không phải theo số lần gọi.
    # Hạn mức miễn phí khoảng 100 đoạn/phút; để 80 cho có khoảng an toàn.
    embed_items_per_minute: int = 80
    embed_batch_size: int = 25

    # --- Supabase ---
    supabase_url: str = ""
    supabase_secret_key: str = ""
    media_bucket: str = "media"

    # --- API ---
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    cron_secret: str = ""
    log_level: str = "INFO"

    # --- Tinh chỉnh RAG ---
    top_k: int = 6
    media_top_k: int = 3
    # Đo trên dữ liệu thật: câu hỏi không liên quan tới hình ảnh vẫn đạt ~0.63
    # với mục media, còn câu hỏi đúng chủ đề đạt ~0.76. Lấy 0.72 để tách hai nhóm.
    # Khi khách hỏi thẳng về hình ảnh, ngưỡng được nới bớt 0.12 trong retriever.
    media_sim_threshold: float = 0.72
    units_limit: int = 20

    # --- Ngân sách thời gian (giây); client timeout 30s ---
    embed_timeout: float = 8.0
    generate_timeout: float = 20.0
    request_budget: float = 27.0

    @property
    def chat_model_chain(self) -> list[str]:
        """Model chính + các model dự phòng, đã loại trùng và giữ thứ tự."""
        chain: list[str] = []
        for name in [self.gemini_chat_model, *_split_csv(self.gemini_fallback_models)]:
            name = name.strip()
            if name and name not in chain:
                chain.append(name)
        return chain

    @property
    def cors_origin_list(self) -> list[str]:
        return _split_csv(self.cors_origins)

    @property
    def is_configured(self) -> bool:
        return bool(self.gemini_api_key and self.supabase_url and self.supabase_secret_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
