"""Quy trình nạp dữ liệu: tải nguồn -> tách đoạn -> embedding -> ghi Supabase."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterable

from ..config import DATA_DIR, get_settings
from ..services.gemini import GeminiService
from ..services.supabase_repo import SupabaseRepo
from .chunks import (
    SOURCE_MEDIA,
    SOURCE_QA,
    SOURCE_UNITS,
    DocChunk,
    link_entries,
    media_chunks,
    qa_chunks,
    unit_summary_chunks,
)
from .download import fetch_workbook
from .sheets import parse_workbook, summarize
from .units import PROJECT_CODE

logger = logging.getLogger(__name__)

MANIFEST_PATH = DATA_DIR / "media_manifest.json"

ALL_SOURCES = ("qa", "units", "media")

# Số liệu kỳ vọng từ file nguồn, dùng để cảnh báo khi dữ liệu thay đổi bất thường.
EXPECTED_COUNTS = {"CH": 594, "PH": 8, "SH": 25, "TM": 112}


def load_manifest(path: Path = MANIFEST_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"{path} phải chứa một danh sách JSON")
    return data


def save_manifest(entries: list[dict[str, Any]], path: Path = MANIFEST_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(entries, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _check_counts(units: list[Any]) -> None:
    from collections import Counter

    actual = Counter(unit.product_type for unit in units if unit.is_primary)
    for product_type, expected in EXPECTED_COUNTS.items():
        if actual.get(product_type, 0) != expected:
            logger.warning(
                "Số căn %s là %s, khác kỳ vọng %s. Kiểm tra lại file nguồn.",
                product_type,
                actual.get(product_type, 0),
                expected,
            )


def _preview(chunks: Iterable[DocChunk], limit: int = 3) -> None:
    for index, chunk in enumerate(chunks):
        if index >= limit:
            break
        print(f"\n--- [{chunk.source}] {chunk.title or chunk.key}")
        print(chunk.content[:500])


async def _write_chunks(
    repo: SupabaseRepo,
    gemini: GeminiService,
    source: str,
    chunks: list[DocChunk],
    *,
    resume: bool = True,
) -> None:
    """Embedding rồi ghi các đoạn của một nguồn lên Supabase.

    `resume=True` bỏ qua những đoạn đã có sẵn trên Supabase, nhờ vậy chạy lại
    sau khi bị ngắt giữa chừng sẽ không tốn thêm hạn mức embedding.
    """
    if not chunks:
        logger.warning("Nguồn %s không có đoạn nào để ghi", source)
        return

    all_ids = [chunk.id for chunk in chunks]
    pending = chunks
    if resume:
        existing = await repo.list_document_ids(source)
        pending = [chunk for chunk in chunks if chunk.id not in existing]
        skipped = len(chunks) - len(pending)
        if skipped:
            print(f"  Bỏ qua {skipped} đoạn đã có trên Supabase")

    if pending:
        print(f"  Đang embedding {len(pending)} đoạn...")
        vectors = await gemini.embed_documents(
            [chunk.content for chunk in pending], progress=True
        )
        rows = [chunk.to_db_row(vector) for chunk, vector in zip(pending, vectors)]
        await repo.upsert_documents(rows)
        print(f"  Đã ghi {len(rows)} đoạn mới")
    else:
        print("  Không có đoạn nào cần embedding thêm")

    # Chỉ dọn đoạn cũ khi toàn bộ nguồn đã hoàn tất, tránh xoá nhầm lúc dở dang.
    await repo.delete_stale_documents(source, all_ids)


async def run_ingest(
    sources: Iterable[str] = ALL_SOURCES,
    *,
    dry_run: bool = False,
    offline: bool = False,
    skip_embeddings: bool = False,
    force: bool = False,
) -> None:
    """Nạp các nguồn được chọn.

    dry_run         chỉ in kết quả tách đoạn, không gọi API nào.
    skip_embeddings chỉ ghi bảng `units` (dữ liệu có cấu trúc), bỏ qua bước
                    embedding. Dùng khi chưa có API key Gemini hợp lệ.
    force           embedding lại cả những đoạn đã có trên Supabase. Mặc định
                    chỉ nạp phần còn thiếu để tiết kiệm hạn mức.
    """
    resume = not force
    sources = {source.strip().lower() for source in sources if source.strip()}
    unknown = sources - set(ALL_SOURCES)
    if unknown:
        raise ValueError(f"Nguồn không hợp lệ: {sorted(unknown)}. Chọn trong {ALL_SOURCES}")

    settings = get_settings()
    parsed = parse_workbook(fetch_workbook(offline=offline))
    print(summarize(parsed))
    _check_counts(parsed.units)

    repo: SupabaseRepo | None = None
    gemini: GeminiService | None = None
    if not dry_run:
        repo = SupabaseRepo(settings)
        if not skip_embeddings:
            gemini = GeminiService(settings)

    try:
        if "qa" in sources:
            chunks = qa_chunks(parsed.qa)
            print(f"\n[qa] {len(chunks)} đoạn")
            if dry_run:
                _preview(chunks)
            elif skip_embeddings:
                print("  Bỏ qua (chế độ --skip-embeddings)")
            else:
                await _write_chunks(repo, gemini, SOURCE_QA, chunks, resume=resume)

        if "units" in sources:
            chunks = unit_summary_chunks(parsed.units)
            rows = [unit.to_db_row() for unit in parsed.units]
            print(f"\n[units] {len(rows)} dòng giỏ hàng, {len(chunks)} đoạn tóm tắt")
            if dry_run:
                _preview(chunks)
            else:
                # Bảng `units` là dữ liệu có cấu trúc, không cần embedding.
                await repo.replace_units(PROJECT_CODE, rows)
                print(f"  Đã ghi {len(rows)} dòng vào bảng units")
                if skip_embeddings:
                    print("  Bỏ qua phần tóm tắt cần embedding (--skip-embeddings)")
                else:
                    await _write_chunks(repo, gemini, SOURCE_UNITS, chunks, resume=resume)

        if "media" in sources:
            entries = load_manifest()
            known_urls = {entry.get("url") for entry in entries}
            # Bổ sung các link lấy tự động từ tab phụ của sheet nếu chưa có.
            extra = [item for item in link_entries(parsed.links) if item["url"] not in known_urls]
            chunks = media_chunks([*entries, *extra])
            print(f"\n[media] {len(entries)} mục trong manifest + {len(extra)} link từ sheet")
            if dry_run:
                _preview(chunks)
            elif skip_embeddings:
                print("  Bỏ qua (chế độ --skip-embeddings)")
            else:
                await _write_chunks(repo, gemini, SOURCE_MEDIA, chunks, resume=resume)

        if not dry_run:
            total = await repo.count_documents()
            print(f"\nTổng số đoạn hiện có trong bảng documents: {total}")
            for source in ALL_SOURCES:
                key = {"qa": SOURCE_QA, "units": SOURCE_UNITS, "media": SOURCE_MEDIA}[source]
                print(f"  {key}: {await repo.count_documents(key)}")
            print(f"  units (bảng riêng): {await repo.count_units()}")
    finally:
        if repo is not None:
            await repo.aclose()
