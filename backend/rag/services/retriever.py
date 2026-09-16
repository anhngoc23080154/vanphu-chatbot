"""Lấy ngữ cảnh cho câu hỏi: tìm kiếm ngữ nghĩa + tra cứu giỏ hàng."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from ..config import Settings, get_settings
from .gemini import GeminiService
from .query_analyzer import QueryIntent
from .supabase_repo import Doc, SupabaseRepo

logger = logging.getLogger(__name__)


@dataclass
class RetrievalBundle:
    """Toàn bộ ngữ cảnh thu được cho một câu hỏi."""

    docs: list[Doc] = field(default_factory=list)
    media: list[Doc] = field(default_factory=list)
    units: list[dict[str, Any]] = field(default_factory=list)
    units_total: int = 0

    @property
    def is_empty(self) -> bool:
        return not self.docs and not self.units and not self.media


class Retriever:
    def __init__(
        self,
        gemini: GeminiService,
        repo: SupabaseRepo,
        settings: Settings | None = None,
    ) -> None:
        self._gemini = gemini
        self._repo = repo
        self._settings = settings or get_settings()

    async def retrieve(self, query_text: str, intent: QueryIntent) -> RetrievalBundle:
        """Một lần embedding, sau đó chạy song song các truy vấn Supabase."""
        embedding = await self._gemini.embed_query(query_text)
        settings = self._settings

        tasks: list[asyncio.Future[Any]] = [
            asyncio.ensure_future(
                self._repo.match_documents(
                    embedding,
                    match_count=settings.top_k,
                    sources=["qa", "units_summary"],
                )
            ),
            asyncio.ensure_future(
                self._repo.match_documents(
                    embedding, match_count=settings.media_top_k, sources=["media"]
                )
            ),
        ]
        if intent.needs_units():
            tasks.append(asyncio.ensure_future(self._find_units(intent)))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        bundle = RetrievalBundle()
        docs_result = results[0]
        if isinstance(docs_result, Exception):
            logger.warning("Tìm kiếm tri thức thất bại: %s", docs_result)
        else:
            bundle.docs = docs_result

        media_result = results[1]
        if isinstance(media_result, Exception):
            logger.warning("Tìm kiếm media thất bại: %s", media_result)
        else:
            bundle.media = media_result

        if len(results) > 2:
            units_result = results[2]
            if isinstance(units_result, Exception):
                logger.warning("Tra cứu giỏ hàng thất bại: %s", units_result)
            else:
                bundle.units, bundle.units_total = units_result

        return bundle

    async def _find_units(self, intent: QueryIntent) -> tuple[list[dict[str, Any]], int]:
        return await self._repo.find_units(
            codes_plain=intent.unit_codes_plain,
            codes_commercial=intent.unit_codes_commercial,
            codes_alt=intent.unit_codes_alt,
            tower=intent.tower,
            floor=intent.floor,
            bedroom_count=intent.bedroom_count,
            product_type=intent.product_type,
            direction=intent.direction,
            limit=self._settings.units_limit,
        )


def select_attachments(bundle: RetrievalBundle, intent: QueryIntent, settings: Settings) -> list[Doc]:
    """Chọn ảnh/link đính kèm câu trả lời.

    Khách hỏi thẳng về hình ảnh thì nới ngưỡng và cho tối đa 3 mục;
    ngược lại chỉ đính kèm 1 mục khi thật sự liên quan.
    """
    if not bundle.media:
        return []
    if intent.wants_image:
        threshold = max(settings.media_sim_threshold - 0.12, 0.3)
        limit = 3
    else:
        threshold = settings.media_sim_threshold
        limit = 1
    selected = [doc for doc in bundle.media if doc.similarity >= threshold]
    return selected[:limit]
