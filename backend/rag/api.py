"""Khởi tạo ứng dụng FastAPI: CORS, route và xử lý lỗi."""

from __future__ import annotations

import logging
import os
import secrets
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .errors import AppError
from .schemas import ChatRequest, ChatResponse, HealthResponse
from .services.chat import ChatService, get_chat_service
from .services.supabase_repo import get_repo

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )


def _warn_misconfiguration(settings: Any) -> None:
    """Cảnh báo sớm các thiếu sót hay gặp khi deploy, thay vì để lỗi khó hiểu."""
    if not settings.gemini_api_key:
        logger.error("Thiếu GEMINI_API_KEY. Mọi câu hỏi sẽ trả về lỗi 503.")
    if not settings.supabase_url or not settings.supabase_secret_key:
        logger.error("Thiếu cấu hình Supabase. Mọi câu hỏi sẽ trả về lỗi 503.")

    # Trên Vercel mà CORS chỉ cho phép localhost thì trình duyệt sẽ chặn frontend.
    if os.getenv("VERCEL"):
        public = [
            origin
            for origin in settings.cors_origin_list
            if "localhost" not in origin and "127.0.0.1" not in origin
        ]
        if not public:
            logger.error(
                "CORS_ORIGINS chưa có domain frontend (%s). "
                "Trình duyệt sẽ chặn mọi request từ website.",
                settings.cors_origins,
            )
        if not settings.cron_secret:
            logger.warning(
                "Chưa đặt CRON_SECRET, endpoint keep-alive đang mở cho mọi người gọi."
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    settings = get_settings()
    logger.info(
        "Khởi động backend chatbot. Model: %s | Supabase: %s",
        settings.gemini_chat_model,
        "đã cấu hình" if settings.supabase_url else "CHƯA cấu hình",
    )
    _warn_misconfiguration(settings)
    yield
    await get_repo().aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Trợ lý ảo Văn Phú",
        description="API chatbot RAG cho dự án Vlasta Premier - Phú Thuận",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
        max_age=86400,
    )

    # --- Xử lý lỗi: frontend hiển thị `detail` nguyên văn cho khách hàng ---
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # FastAPI mặc định trả `detail` dạng danh sách; frontend cần một chuỗi.
        logger.warning("Dữ liệu gửi lên không hợp lệ: %s", exc.errors())
        return JSONResponse(
            status_code=422,
            content={"detail": "Nội dung tin nhắn không hợp lệ. Bạn vui lòng nhập lại."},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Lỗi không lường trước: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Đã xảy ra lỗi hệ thống. Bạn vui lòng thử lại sau."},
        )

    # --- Route ---
    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            chat_model=settings.gemini_chat_model,
            embed_model=settings.gemini_embed_model,
            configured=settings.is_configured,
        )

    @app.post("/api/chat", response_model=ChatResponse)
    async def chat(
        request: ChatRequest,
        service: ChatService = Depends(get_chat_service),
    ) -> ChatResponse:
        return await service.answer(request)

    @app.get("/api/cron/keepalive")
    async def keepalive(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        """Giữ cho project Supabase free tier không bị tạm dừng sau 7 ngày.

        Vercel Cron gọi mỗi ngày một lần kèm header Authorization: Bearer CRON_SECRET.
        """
        expected = settings.cron_secret
        if expected:
            token = (authorization or "").removeprefix("Bearer ").strip()
            if not secrets.compare_digest(token, expected):
                return JSONResponse(status_code=401, content={"detail": "Không có quyền truy cập."})

        rows = await get_repo().ping()
        logger.info("Keep-alive Supabase thành công (%s dòng)", rows)
        return {"status": "ok", "documents_seen": rows}

    return app
