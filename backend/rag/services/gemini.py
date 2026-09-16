"""Lớp bọc Gemini API: embedding và sinh câu trả lời.

Thiết kế cho free tier: mỗi request chat chỉ 1 lần embed + 1 lần generate.
Khi model chính bị 429/503 sẽ tự chuyển sang model dự phòng.
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
import time
from collections import deque
from typing import Any

from ..config import Settings, get_settings
from ..errors import ConfigurationError, UpstreamRateLimited, UpstreamTimeout

logger = logging.getLogger(__name__)

# Mã lỗi nên thử model khác thay vì báo lỗi ngay.
_RETRYABLE_CODES = {429, 500, 502, 503, 504}

_RETRY_DELAY_RE = re.compile(r"(\d+(?:\.\d+)?)s")


def _error_code(error: Exception) -> int | None:
    code = getattr(error, "code", None)
    if isinstance(code, int):
        return code
    status = getattr(error, "status_code", None)
    if isinstance(status, int):
        return status
    text = str(error)
    for candidate in _RETRYABLE_CODES:
        if str(candidate) in text:
            return candidate
    return None


def _error_details(error: Exception) -> list[dict[str, Any]]:
    """Danh sách `error.details` trong phản hồi lỗi của Gemini."""
    payload = getattr(error, "details", None)
    if isinstance(payload, dict):
        inner = payload.get("error")
        if isinstance(inner, dict):
            details = inner.get("details")
            if isinstance(details, list):
                return [item for item in details if isinstance(item, dict)]
    return []


def retry_delay_seconds(error: Exception) -> float | None:
    """Thời gian Google yêu cầu chờ trước khi thử lại (RetryInfo.retryDelay)."""
    for item in _error_details(error):
        if "RetryInfo" not in str(item.get("@type", "")):
            continue
        raw = item.get("retryDelay")
        if isinstance(raw, (int, float)):
            return float(raw)
        if isinstance(raw, str):
            match = _RETRY_DELAY_RE.search(raw)
            if match:
                return float(match.group(1))
    return None


def quota_summary(error: Exception) -> str:
    """Mô tả ngắn hạn mức bị vượt, để ghi log cho dễ chẩn đoán."""
    parts: list[str] = []
    for item in _error_details(error):
        if "QuotaFailure" not in str(item.get("@type", "")):
            continue
        for violation in item.get("violations", []) or []:
            metric = violation.get("quotaMetric", "?").split("/")[-1]
            value = violation.get("quotaValue", "?")
            parts.append(f"{metric}={value}")
    return ", ".join(parts) or "không rõ hạn mức"


class _RateLimiter:
    """Giới hạn số đoạn văn bản gửi đi trong mỗi 60 giây.

    Gemini tính hạn mức theo từng đoạn trong lô, không phải theo số lần gọi,
    nên phải đếm theo đoạn thì mới tránh được lỗi 429.
    """

    def __init__(self, items_per_minute: int) -> None:
        self._limit = max(items_per_minute, 1)
        self._events: deque[tuple[float, int]] = deque()

    def _used(self, now: float) -> int:
        while self._events and now - self._events[0][0] >= 60.0:
            self._events.popleft()
        return sum(count for _, count in self._events)

    async def acquire(self, count: int) -> None:
        while True:
            now = time.monotonic()
            used = self._used(now)
            if used + count <= self._limit or not self._events:
                self._events.append((now, count))
                return
            wait = 60.0 - (now - self._events[0][0]) + 0.5
            logger.info(
                "Đã dùng %s/%s suất embedding trong phút này, chờ %.0fs",
                used,
                self._limit,
                wait,
            )
            await asyncio.sleep(wait)

    def penalize(self) -> None:
        """Coi như đã dùng hết hạn mức sau khi bị 429."""
        self._events.append((time.monotonic(), self._limit))


def _l2_normalize(vector: list[float]) -> list[float]:
    """gemini-embedding-001 KHÔNG tự chuẩn hoá khi output_dimensionality < 3072."""
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


class GeminiService:
    """Client Gemini dùng chung, khởi tạo lười để cold start nhanh."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client: Any = None
        self._types: Any = None
        self._limiter = _RateLimiter(self._settings.embed_items_per_minute)

    # --- hạ tầng ---------------------------------------------------------
    def _ensure_client(self) -> tuple[Any, Any]:
        if self._client is None:
            if not self._settings.gemini_api_key:
                raise ConfigurationError("Thiếu GEMINI_API_KEY. Bạn vui lòng liên hệ quản trị viên.")
            from google import genai  # import lười: giảm thời gian cold start
            from google.genai import types

            self._client = genai.Client(api_key=self._settings.gemini_api_key)
            self._types = types
        return self._client, self._types

    @property
    def types(self) -> Any:
        _, types = self._ensure_client()
        return types

    # --- embedding -------------------------------------------------------
    async def _embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        client, types = self._ensure_client()
        config = types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=self._settings.embed_dim,
        )
        response = await client.aio.models.embed_content(
            model=self._settings.gemini_embed_model,
            contents=texts,
            config=config,
        )
        return [_l2_normalize(list(item.values)) for item in response.embeddings]

    async def embed_query(self, text: str) -> list[float]:
        """Vector cho câu hỏi của khách (task_type RETRIEVAL_QUERY)."""
        try:
            vectors = await asyncio.wait_for(
                self._embed([text], "RETRIEVAL_QUERY"),
                timeout=self._settings.embed_timeout,
            )
        except asyncio.TimeoutError as exc:
            raise UpstreamTimeout() from exc
        except Exception as exc:  # noqa: BLE001 - phân loại lại bên dưới
            if _error_code(exc) == 429:
                logger.warning("Gemini embed bị giới hạn tần suất: %s", exc)
                raise UpstreamRateLimited() from exc
            logger.exception("Gemini embed thất bại")
            raise UpstreamRateLimited(
                "Trợ lý chưa truy cập được hệ thống tri thức. Bạn vui lòng thử lại sau ít phút."
            ) from exc
        return vectors[0]

    async def embed_documents(
        self,
        texts: list[str],
        *,
        batch_size: int | None = None,
        pause: float = 0.0,
        max_attempts: int = 5,
        progress: bool = False,
    ) -> list[list[float]]:
        """Embed nhiều đoạn văn bản khi nạp dữ liệu (task_type RETRIEVAL_DOCUMENT).

        Tự điều tiết theo số đoạn mỗi phút và tôn trọng thời gian chờ mà Google
        yêu cầu khi trả về lỗi 429, nên chạy được trên hạn mức miễn phí.
        """
        settings = self._settings
        batch_size = batch_size or settings.embed_batch_size
        limiter = self._limiter

        vectors: list[list[float]] = []
        total = len(texts)
        for start in range(0, total, batch_size):
            batch = texts[start : start + batch_size]
            attempt = 0
            while True:
                await limiter.acquire(len(batch))
                try:
                    vectors.extend(await self._embed(batch, "RETRIEVAL_DOCUMENT"))
                    break
                except Exception as exc:  # noqa: BLE001
                    attempt += 1
                    code = _error_code(exc)
                    if code not in _RETRYABLE_CODES or attempt >= max_attempts:
                        if code == 429:
                            logger.error(
                                "Hết hạn mức embedding (%s). Đã embed %s/%s đoạn. "
                                "Chạy lại lệnh ingest để tiếp tục từ chỗ dừng.",
                                quota_summary(exc),
                                len(vectors),
                                total,
                            )
                        raise
                    if code == 429:
                        limiter.penalize()
                        wait = retry_delay_seconds(exc) or min(60.0 * attempt, 180.0)
                        logger.warning(
                            "Vượt hạn mức embedding (%s), chờ %.0fs rồi thử lại (lần %s/%s)",
                            quota_summary(exc),
                            wait,
                            attempt,
                            max_attempts,
                        )
                    else:
                        wait = min(5.0 * attempt, 30.0)
                        logger.warning(
                            "Embed lỗi %s, chờ %.0fs rồi thử lại (lần %s/%s)",
                            code,
                            wait,
                            attempt,
                            max_attempts,
                        )
                    await asyncio.sleep(wait)
            if progress:
                logger.info("Đã embed %s/%s đoạn", len(vectors), total)
            if pause and start + batch_size < total:
                await asyncio.sleep(pause)
        return vectors

    # --- sinh câu trả lời -------------------------------------------------
    async def generate(self, contents: list[Any], system_instruction: str) -> tuple[str, str]:
        """Trả về (câu trả lời, tên model đã dùng). Thử lần lượt các model."""
        client, types = self._ensure_client()
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.3,
            max_output_tokens=1024,
        )

        last_error: Exception | None = None
        deadline = asyncio.get_running_loop().time() + self._settings.generate_timeout

        for model in self._settings.chat_model_chain:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 1:
                break
            try:
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(model=model, contents=contents, config=config),
                    timeout=remaining,
                )
            except asyncio.TimeoutError as exc:
                last_error = exc
                logger.warning("Model %s phản hồi quá lâu", model)
                continue
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if _error_code(exc) in _RETRYABLE_CODES:
                    logger.warning("Model %s lỗi %s, thử model tiếp theo", model, _error_code(exc))
                    continue
                logger.exception("Model %s lỗi không thể thử lại", model)
                continue

            text = (getattr(response, "text", None) or "").strip()
            if text:
                return text, model
            logger.warning("Model %s trả về nội dung rỗng (có thể bị chặn an toàn)", model)

        if isinstance(last_error, asyncio.TimeoutError):
            raise UpstreamTimeout()
        logger.error("Tất cả model đều thất bại: %s", last_error)
        raise UpstreamRateLimited()


_service: GeminiService | None = None


def get_gemini_service() -> GeminiService:
    global _service
    if _service is None:
        _service = GeminiService()
    return _service
