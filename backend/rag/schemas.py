"""Kiểu dữ liệu vào/ra của API, khớp với frontend/src/types/chat.ts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["user", "assistant"]


class HistoryItem(BaseModel):
    role: Role
    content: str = Field(default="", max_length=8000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str = Field(default="", max_length=128)
    history: list[HistoryItem] = Field(default_factory=list, max_length=40)


class Attachment(BaseModel):
    """Ảnh hoặc link đính kèm câu trả lời (frontend render dưới bong bóng chat)."""

    type: Literal["image", "link"] = "image"
    url: str
    title: str | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str | None = None
    attachments: list[Attachment] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    chat_model: str
    embed_model: str
    configured: bool
