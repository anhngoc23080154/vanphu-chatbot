"""Nạp dữ liệu dự án lên Supabase.

Ví dụ:
    python -m scripts.ingest --dry-run            # chỉ xem trước, không gọi API
    python -m scripts.ingest --sources qa,units   # nạp Q&A và giỏ hàng
    python -m scripts.ingest                      # nạp tất cả
    python -m scripts.ingest --offline            # dùng lại file xlsx đã tải
"""

from __future__ import annotations

import argparse
import asyncio

from scripts._bootstrap import setup_logging  # noqa: F401  (thiết lập sys.path + UTF-8)

from rag.ingest.pipeline import ALL_SOURCES, run_ingest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Nạp dữ liệu chatbot Văn Phú lên Supabase")
    parser.add_argument(
        "--sources",
        default=",".join(ALL_SOURCES),
        help=f"Danh sách nguồn, phân tách bằng dấu phẩy. Mặc định: {','.join(ALL_SOURCES)}",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Chỉ in ra kết quả tách đoạn, không gọi API"
    )
    parser.add_argument(
        "--offline", action="store_true", help="Dùng file xlsx đã tải trong data/cache"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Embedding lại cả đoạn đã có (mặc định chỉ nạp phần còn thiếu)",
    )
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Chỉ ghi bảng units, bỏ qua embedding (dùng khi chưa có API key Gemini)",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    setup_logging(args.log_level)
    asyncio.run(
        run_ingest(
            args.sources.split(","),
            dry_run=args.dry_run,
            offline=args.offline,
            skip_embeddings=args.skip_embeddings,
            force=args.force,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
