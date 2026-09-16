"""Tải ảnh/poster dự án lên Supabase Storage và cập nhật manifest.

Cách dùng:
  1. Chép ảnh vào thư mục backend/data/media/
  2. Khai báo từng ảnh trong backend/data/media_manifest.json (xem README)
  3. Chạy:  python -m scripts.upload_media
  4. Chạy:  python -m scripts.ingest --sources media

Script chỉ upload mục có "file" mà chưa có "url"; chạy lại nhiều lần an toàn.
Dùng --force để upload đè tất cả.
"""

from __future__ import annotations

import argparse
import asyncio
import mimetypes
from pathlib import Path

from scripts._bootstrap import setup_logging  # noqa: F401  (thiết lập sys.path + UTF-8)

from rag.config import DATA_DIR, get_settings  # noqa: E402
from rag.ingest.pipeline import load_manifest, save_manifest  # noqa: E402
from rag.services.supabase_repo import SupabaseRepo  # noqa: E402

MEDIA_DIR = DATA_DIR / "media"


async def run(force: bool) -> int:
    settings = get_settings()
    entries = load_manifest()
    if not entries:
        print(
            f"Chưa có mục nào trong {DATA_DIR / 'media_manifest.json'}.\n"
            "Xem hướng dẫn khai báo trong backend/README.md."
        )
        return 1

    repo = SupabaseRepo(settings)
    uploaded = skipped = 0
    try:
        for entry in entries:
            file_name = (entry.get("file") or "").strip()
            if not file_name:
                continue  # mục chỉ có URL ngoài, không cần upload
            if entry.get("url") and not force:
                skipped += 1
                continue

            path = MEDIA_DIR / file_name
            if not path.exists():
                print(f"  BỎ QUA: không tìm thấy {path}")
                continue

            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            url = await repo.upload_object(
                settings.media_bucket, file_name, path.read_bytes(), content_type
            )
            entry["url"] = url
            entry.setdefault("type", "image" if content_type.startswith("image/") else "link")
            uploaded += 1
            print(f"  ĐÃ TẢI LÊN: {file_name} -> {url}")
    finally:
        await repo.aclose()

    save_manifest(entries)
    print(f"\nHoàn tất: {uploaded} file đã tải lên, {skipped} file bỏ qua (đã có URL).")
    print("Bước tiếp theo: python -m scripts.ingest --sources media")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Tải ảnh dự án lên Supabase Storage")
    parser.add_argument("--force", action="store_true", help="Tải lên lại cả file đã có URL")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    setup_logging(args.log_level)
    return asyncio.run(run(args.force))


if __name__ == "__main__":
    raise SystemExit(main())
