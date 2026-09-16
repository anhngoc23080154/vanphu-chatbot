"""Kiểm tra kết nối Supabase: bảng, hàm RPC, bucket ảnh đã sẵn sàng chưa.

Chạy:  python -m scripts.check_supabase
"""

from __future__ import annotations

import asyncio

import httpx

from scripts._bootstrap import setup_logging  # noqa: F401  (thiết lập sys.path + UTF-8)

from rag.config import get_settings  # noqa: E402
from rag.services.supabase_repo import SupabaseRepo  # noqa: E402

OK = "OK "
FAIL = "LỖI"


async def main() -> int:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_secret_key:
        print("Thiếu SUPABASE_URL hoặc SUPABASE_SECRET_KEY trong .env")
        return 1

    print(f"Supabase: {settings.supabase_url}\n")
    problems: list[str] = []
    headers = {
        "apikey": settings.supabase_secret_key,
        "Authorization": f"Bearer {settings.supabase_secret_key}",
    }
    base = settings.supabase_url.rstrip("/")

    async with httpx.AsyncClient(timeout=20.0) as client:
        # 1. Bảng documents và units
        for table in ("documents", "units"):
            response = await client.get(
                f"{base}/rest/v1/{table}",
                params={"select": "*", "limit": "1"},
                headers={**headers, "Prefer": "count=exact"},
            )
            # PostgREST trả 206 Partial Content khi có limit và còn dòng phía sau.
            if response.status_code in (200, 206):
                count = response.headers.get("content-range", "?").split("/")[-1]
                print(f"{OK} bảng {table}: {count} dòng")
            else:
                problems.append(f"bảng {table}")
                print(f"{FAIL} bảng {table}: {response.status_code} {response.text[:120]}")

        # 2. Hàm match_documents
        response = await client.post(
            f"{base}/rest/v1/rpc/match_documents",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "query_embedding": [0.0] * settings.embed_dim,
                "match_count": 1,
                "filter_sources": None,
            },
        )
        if response.status_code == 200:
            print(f"{OK} hàm match_documents (vector {settings.embed_dim} chiều)")
        else:
            problems.append("hàm match_documents")
            print(f"{FAIL} hàm match_documents: {response.status_code} {response.text[:160]}")

        # 3. Bucket ảnh
        response = await client.get(f"{base}/storage/v1/bucket", headers=headers)
        if response.status_code == 200:
            buckets = {item["name"]: item.get("public") for item in response.json()}
            if settings.media_bucket in buckets:
                public = buckets[settings.media_bucket]
                print(f"{OK} bucket '{settings.media_bucket}' (public={public})")
                if not public:
                    problems.append(f"bucket '{settings.media_bucket}' chưa để chế độ public")
            else:
                problems.append(f"bucket '{settings.media_bucket}'")
                print(
                    f"{FAIL} chưa có bucket '{settings.media_bucket}'. "
                    f"Bucket hiện có: {sorted(buckets) or 'không có'}"
                )
        else:
            print(f"{FAIL} không đọc được danh sách bucket: {response.status_code}")

    # 4. Thử hàm ping dùng cho cron keep-alive
    repo = SupabaseRepo(settings)
    try:
        await repo.ping()
        print(f"{OK} keep-alive ping hoạt động")
    except Exception as exc:  # noqa: BLE001
        problems.append("keep-alive ping")
        print(f"{FAIL} keep-alive ping: {exc}")
    finally:
        await repo.aclose()

    if problems:
        print(f"\nCòn thiếu: {', '.join(problems)}")
        print("Hãy chạy backend/supabase/001_schema.sql trong Supabase SQL Editor")
        print("và tạo bucket public tên 'media' trong mục Storage.")
        return 1

    print("\nSupabase đã sẵn sàng. Bước tiếp theo: python -m scripts.ingest")
    return 0


if __name__ == "__main__":
    setup_logging("WARNING")
    raise SystemExit(asyncio.run(main()))
