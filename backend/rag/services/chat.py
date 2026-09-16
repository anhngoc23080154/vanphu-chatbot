"""Điều phối một lượt hội thoại: phân tích -> truy xuất -> sinh câu trả lời."""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from dataclasses import dataclass

from ..config import Settings, get_settings
from ..errors import UpstreamTimeout
from ..schemas import Attachment, ChatRequest, ChatResponse
from .gemini import GeminiService, get_gemini_service
from .prompt import NO_CONTEXT_REPLY, SYSTEM_PROMPT, build_context, build_contents
from .query_analyzer import analyze, build_retrieval_text
from .retriever import Retriever, select_attachments
from .supabase_repo import SupabaseRepo, get_repo

logger = logging.getLogger(__name__)

# Markdown lọt ra ngoài sẽ hiển thị thành ký tự thô vì frontend render text thuần.
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_MD_ITALIC = re.compile(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", re.DOTALL)
_MD_HEADING = re.compile(r"^#{1,6}\s*", re.MULTILINE)
_MD_BULLET = re.compile(r"^\s*[\*•]\s+", re.MULTILINE)
_MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")


def sanitize_reply(text: str) -> str:
    """Bỏ cú pháp Markdown vì frontend chỉ hiển thị văn bản thuần."""
    text = _MD_LINK.sub(r"\1: \2", text)
    text = _MD_BOLD.sub(r"\1", text)
    text = _MD_ITALIC.sub(r"\1", text)
    text = _MD_HEADING.sub("", text)
    text = _MD_BULLET.sub("- ", text)
    text = text.replace("`", "")
    # Gộp các dòng trống liên tiếp.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


@dataclass
class ChatService:
    """Gộp các phụ thuộc lại để dễ thay thế khi viết test."""

    gemini: GeminiService
    repo: SupabaseRepo
    settings: Settings

    async def answer(self, request: ChatRequest) -> ChatResponse:
        started = time.perf_counter()
        session_id = request.session_id or str(uuid.uuid4())
        try:
            reply, attachments, model = await asyncio.wait_for(
                self._answer(request),
                timeout=self.settings.request_budget,
            )
        except asyncio.TimeoutError as exc:
            raise UpstreamTimeout() from exc

        elapsed = time.perf_counter() - started
        logger.info(
            "Trả lời session=%s model=%s %.2fs, %s đính kèm",
            session_id[:8],
            model,
            elapsed,
            len(attachments),
        )
        return ChatResponse(reply=reply, session_id=session_id, attachments=attachments)

    async def _answer(self, request: ChatRequest) -> tuple[str, list[Attachment], str]:
        intent = analyze(request.message, request.history)
        query_text = build_retrieval_text(request.message, request.history, intent)

        retriever = Retriever(self.gemini, self.repo, self.settings)
        bundle = await retriever.retrieve(query_text, intent)

        media_docs = select_attachments(bundle, intent, self.settings)
        attachments = [
            Attachment(
                type=doc.metadata.get("type", "image"),
                url=doc.metadata.get("url", ""),
                title=doc.title,
            )
            for doc in media_docs
            if doc.metadata.get("url")
        ]

        if bundle.is_empty:
            logger.info("Không tìm thấy ngữ cảnh cho câu hỏi: %s", request.message[:80])
            return NO_CONTEXT_REPLY, [], "none"

        context = build_context(bundle, media_docs, intent)
        contents = build_contents(
            self.gemini.types, request.history, request.message, context, intent
        )
        raw_reply, model = await self.gemini.generate(contents, SYSTEM_PROMPT)
        return sanitize_reply(raw_reply), attachments, model


_service: ChatService | None = None


def get_chat_service() -> ChatService:
    global _service
    if _service is None:
        _service = ChatService(
            gemini=get_gemini_service(), repo=get_repo(), settings=get_settings()
        )
    return _service
