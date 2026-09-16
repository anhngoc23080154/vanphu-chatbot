"""Truy cập Supabase qua PostgREST/Storage bằng httpx.

Không dùng supabase-py để bundle trên Vercel nhỏ và cold start nhanh.
Dùng SUPABASE_SECRET_KEY (service role) nên bỏ qua RLS.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from ..config import Settings, get_settings
from ..errors import ConfigurationError, UpstreamUnavailable

logger = logging.getLogger(__name__)


@dataclass
class Doc:
    """Một đoạn tri thức lấy từ bảng `documents`."""

    id: str
    source: str
    section: str | None
    title: str | None
    content: str
    metadata: dict[str, Any]
    similarity: float

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Doc":
        metadata = row.get("metadata") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata = {}
        return cls(
            id=str(row.get("id", "")),
            source=row.get("source") or "",
            section=row.get("section"),
            title=row.get("title"),
            content=row.get("content") or "",
            metadata=metadata,
            similarity=float(row.get("similarity") or 0.0),
        )


class SupabaseRepo:
    """Các truy vấn backend cần: vector search, tra cứu căn, ghi dữ liệu."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client: httpx.AsyncClient | None = None

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            settings = self._settings
            if not settings.supabase_url or not settings.supabase_secret_key:
                raise ConfigurationError(
                    "Thiếu cấu hình Supabase. Bạn vui lòng liên hệ quản trị viên."
                )
            self._client = httpx.AsyncClient(
                base_url=settings.supabase_url.rstrip("/"),
                headers={
                    "apikey": settings.supabase_secret_key,
                    "Authorization": f"Bearer {settings.supabase_secret_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(15.0, connect=5.0),
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        client = self._ensure_client()
        try:
            response = await client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            logger.exception("Không gọi được Supabase: %s %s", method, url)
            raise UpstreamUnavailable() from exc
        if response.status_code >= 400:
            logger.error(
                "Supabase %s %s -> %s: %s",
                method,
                url,
                response.status_code,
                response.text[:500],
            )
            raise UpstreamUnavailable()
        return response

    # --- đọc dữ liệu cho runtime -----------------------------------------
    async def ping(self) -> int:
        """Truy vấn nhẹ giữ cho project Supabase không bị pause sau 7 ngày."""
        response = await self._request(
            "GET",
            "/rest/v1/documents",
            params={"select": "id", "limit": "1"},
        )
        return len(response.json())

    async def match_documents(
        self,
        embedding: list[float],
        *,
        match_count: int,
        sources: list[str] | None = None,
    ) -> list[Doc]:
        """Tìm đoạn tri thức gần nhất theo cosine similarity."""
        payload: dict[str, Any] = {
            "query_embedding": embedding,
            "match_count": match_count,
            "filter_sources": sources,
        }
        response = await self._request("POST", "/rest/v1/rpc/match_documents", json=payload)
        return [Doc.from_row(row) for row in response.json()]

    async def find_units(
        self,
        *,
        codes_plain: list[str] | None = None,
        codes_commercial: list[str] | None = None,
        codes_alt: list[str] | None = None,
        tower: str | None = None,
        floor: int | None = None,
        bedroom_count: int | None = None,
        product_type: str | None = None,
        direction: str | None = None,
        limit: int | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Tra cứu bảng `units`. Trả về (danh sách dòng, tổng số dòng khớp)."""
        limit = limit or self._settings.units_limit
        params: dict[str, str] = {
            "select": "*",
            "order": "tower.asc,floor.asc,unit_no.asc,sheet_row.asc",
            "limit": str(limit),
        }

        codes_plain = codes_plain or []
        codes_commercial = codes_commercial or []
        codes_alt = codes_alt or []
        has_codes = bool(codes_plain or codes_commercial or codes_alt)

        if has_codes:
            clauses: list[str] = []
            if codes_plain:
                clauses.append(f"unit_code.in.({','.join(codes_plain)})")
            if codes_commercial:
                clauses.append(f"unit_code_commercial.in.({','.join(codes_commercial)})")
            if codes_alt:
                clauses.append(f"unit_code_alt.in.({','.join(codes_alt)})")
            params["or"] = f"({','.join(clauses)})"
            # Giữ cả dòng phụ (diện tích từng tầng của penthouse/shophouse).
            params["order"] = "sheet_row.asc"
        else:
            # Lọc theo tiêu chí: chỉ lấy dòng chính, mỗi căn 1 dòng.
            params["is_primary"] = "eq.true"
            params["is_total_row"] = "eq.false"
            if tower:
                params["tower"] = f"eq.{tower}"
            if floor is not None:
                params["floor"] = f"eq.{floor}"
            if bedroom_count is not None:
                params["bedroom_count"] = f"eq.{bedroom_count}"
            if product_type:
                params["product_type"] = f"eq.{product_type}"
            if direction:
                params["balcony_dir"] = f"ilike.*{direction}*"

        response = await self._request(
            "GET",
            "/rest/v1/units",
            params=params,
            headers={"Prefer": "count=exact"},
        )
        rows = response.json()
        total = len(rows)
        content_range = response.headers.get("content-range", "")
        if "/" in content_range:
            tail = content_range.split("/")[-1]
            if tail.isdigit():
                total = int(tail)
        return rows, total

    # --- ghi dữ liệu (dùng bởi script ingest) -----------------------------
    async def upsert_documents(self, rows: list[dict[str, Any]], *, batch_size: int = 50) -> None:
        for start in range(0, len(rows), batch_size):
            await self._request(
                "POST",
                "/rest/v1/documents",
                json=rows[start : start + batch_size],
                headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
            )

    async def delete_stale_documents(self, source: str, keep_ids: list[str]) -> None:
        """Xoá các đoạn cũ của một nguồn không còn trong lần nạp mới nhất."""
        params = {"source": f"eq.{source}"}
        if keep_ids:
            params["id"] = f"not.in.({','.join(keep_ids)})"
        await self._request(
            "DELETE",
            "/rest/v1/documents",
            params=params,
            headers={"Prefer": "return=minimal"},
        )

    async def list_document_ids(self, source: str) -> set[str]:
        """Id các đoạn đã có của một nguồn, dùng để chạy tiếp từ chỗ dừng."""
        ids: set[str] = set()
        offset = 0
        page_size = 1000
        while True:
            response = await self._request(
                "GET",
                "/rest/v1/documents",
                params={
                    "select": "id",
                    "source": f"eq.{source}",
                    "limit": str(page_size),
                    "offset": str(offset),
                },
            )
            rows = response.json()
            ids.update(str(row["id"]) for row in rows)
            if len(rows) < page_size:
                return ids
            offset += page_size

    async def count_documents(self, source: str | None = None) -> int:
        params = {"select": "id"}
        if source:
            params["source"] = f"eq.{source}"
        response = await self._request(
            "GET", "/rest/v1/documents", params=params, headers={"Prefer": "count=exact"}
        )
        content_range = response.headers.get("content-range", "")
        tail = content_range.split("/")[-1] if "/" in content_range else ""
        return int(tail) if tail.isdigit() else len(response.json())

    async def replace_units(
        self, project_code: str, rows: list[dict[str, Any]], *, batch_size: int = 200
    ) -> None:
        """Xoá toàn bộ căn của dự án rồi ghi lại (nguồn là bảng đầy đủ)."""
        await self._request(
            "DELETE",
            "/rest/v1/units",
            params={"project_code": f"eq.{project_code}"},
            headers={"Prefer": "return=minimal"},
        )
        for start in range(0, len(rows), batch_size):
            await self._request(
                "POST",
                "/rest/v1/units",
                json=rows[start : start + batch_size],
                headers={"Prefer": "return=minimal"},
            )

    async def count_units(self) -> int:
        response = await self._request(
            "GET", "/rest/v1/units", params={"select": "id"}, headers={"Prefer": "count=exact"}
        )
        content_range = response.headers.get("content-range", "")
        tail = content_range.split("/")[-1] if "/" in content_range else ""
        return int(tail) if tail.isdigit() else len(response.json())

    # --- Storage ----------------------------------------------------------
    async def upload_object(self, bucket: str, path: str, data: bytes, content_type: str) -> str:
        """Tải file lên bucket public, trả về URL công khai."""
        client = self._ensure_client()
        base = self._settings.supabase_url.rstrip("/")
        try:
            response = await client.post(
                f"/storage/v1/object/{bucket}/{path}",
                content=data,
                headers={"Content-Type": content_type, "x-upsert": "true"},
                timeout=httpx.Timeout(60.0, connect=10.0),
            )
        except httpx.HTTPError as exc:
            raise UpstreamUnavailable() from exc
        if response.status_code >= 400:
            logger.error("Upload thất bại %s: %s", path, response.text[:500])
            raise UpstreamUnavailable()
        return f"{base}/storage/v1/object/public/{bucket}/{path}"


_repo: SupabaseRepo | None = None


def get_repo() -> SupabaseRepo:
    global _repo
    if _repo is None:
        _repo = SupabaseRepo()
    return _repo
