"""Tải tài liệu nguồn từ Google Sheets / Google Docs (link công khai)."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from ..config import DATA_DIR

logger = logging.getLogger(__name__)

# Bảng giỏ hàng + bộ Q&A của dự án Vlasta Premier - Phú Thuận.
SHEET_ID = "1H-lJfcd05rTks3afAwmgPKIZ2stP5RYDmaWLVlJxZxQ"
# Tài liệu mô tả tính năng chatbot (dùng để viết prompt, không nạp vào KB).
DOC_ID = "18UkcGgLZuvc0CNt66-3cBG9nC9-4I5v8ZsKW6IZ0lyg"

CACHE_DIR = DATA_DIR / "cache"
SHEET_CACHE = CACHE_DIR / "vlasta_premier.xlsx"


def _download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Đang tải %s", url)
    with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(90.0, connect=15.0)) as client:
        response = client.get(url)
        response.raise_for_status()
        dest.write_bytes(response.content)
    logger.info("Đã lưu %s (%.1f KB)", dest.name, len(response.content) / 1024)
    return dest


def fetch_workbook(*, offline: bool = False, sheet_id: str = SHEET_ID) -> Path:
    """Tải workbook xlsx của Google Sheet. `offline=True` dùng lại file đã tải."""
    if offline:
        if not SHEET_CACHE.exists():
            raise FileNotFoundError(
                f"Chưa có file cache {SHEET_CACHE}. Bỏ cờ --offline để tải mới."
            )
        logger.info("Dùng file cache %s", SHEET_CACHE)
        return SHEET_CACHE
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    return _download(url, SHEET_CACHE)


def fetch_doc_text(*, doc_id: str = DOC_ID) -> str:
    """Tải nội dung Google Doc dạng text thuần (tham khảo, không nạp vào KB)."""
    url = f"https://docs.google.com/document/d/{doc_id}/export?format=txt"
    with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(60.0, connect=15.0)) as client:
        response = client.get(url)
        response.raise_for_status()
    return response.content.decode("utf-8-sig", errors="replace")
