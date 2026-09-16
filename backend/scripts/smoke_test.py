"""Gửi bộ câu hỏi mẫu tới API và in kết quả để kiểm tra chất lượng trả lời.

Chạy backend trước:  uvicorn main:app --port 8000
Rồi:                 python -m scripts.smoke_test
Tùy chọn:            python -m scripts.smoke_test --url https://<backend>.vercel.app
                     python -m scripts.smoke_test --only 3,7
"""

from __future__ import annotations

import argparse
import asyncio
import time
import uuid

import httpx

from scripts._bootstrap import setup_logging  # noqa: F401  (thiết lập sys.path + UTF-8)

# Mỗi mục: (câu hỏi, điều cần kiểm tra bằng mắt)
QUESTIONS: list[tuple[str, str]] = [
    ("Chủ đầu tư dự án là ai?", "Công ty Cổ phần Đầu tư Xây dựng New Tech"),
    ("Chính sách bán hàng hiện tại ra sao?", "Nêu được thông tin hoặc mời liên hệ tư vấn"),
    ("Căn A-06-01 diện tích bao nhiêu?", "Tim tường 102,33 m2, thông thủy 90,48 m2"),
    ("Căn 2 phòng ngủ tháp B rộng bao nhiêu?", "Khoảng 68-72 m2 thông thủy"),
    ("Tầng 10 tháp A có những căn nào hướng Nam?", "Liệt kê mã căn, nêu tổng số"),
    ("Dự án có bao nhiêu căn penthouse, diện tích thế nào?", "8 căn penthouse"),
    ("Shophouse SH-A01-01 có mấy tầng, tổng diện tích bao nhiêu?", "2 tầng, tổng 179,33 m2"),
    ("Cho tôi xem poster và mặt bằng dự án", "Có mục đính kèm (attachments)"),
    ("Phí quản lý bao nhiêu một mét vuông mỗi tháng?", "16.500 đồng/m2/tháng"),
    ("Dự án bàn giao khi nào?", "Quý 4 năm 2027"),
    ("Tiện ích của dự án gồm những gì?", "Bể bơi, gym, golf 3D, rạp phim..."),
    ("Người nước ngoài có mua được không?", "Theo Luật Nhà ở 2023, hợp đồng thuê dài hạn"),
    ("Căn Z-99-99 còn không?", "Nói rõ không tìm thấy căn này"),
    ("Giá vàng hôm nay bao nhiêu?", "Từ chối lịch sự, kéo về chủ đề dự án"),
]

# Cặp câu hỏi kiểm tra khả năng hiểu ngữ cảnh nối tiếp.
FOLLOWUP = [
    ("Căn A-06-01 diện tích bao nhiêu?", "Còn hướng ban công thì sao?"),
]


async def ask(
    client: httpx.AsyncClient, url: str, message: str, history: list[dict[str, str]], session: str
) -> tuple[dict, float]:
    started = time.perf_counter()
    response = await client.post(
        f"{url.rstrip('/')}/api/chat",
        json={"message": message, "session_id": session, "history": history},
        headers={"Content-Type": "application/json"},
        timeout=40.0,
    )
    elapsed = time.perf_counter() - started
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text[:200])
        except Exception:  # noqa: BLE001
            detail = response.text[:200]
        return {"error": f"HTTP {response.status_code}: {detail}"}, elapsed
    return response.json(), elapsed


async def run(url: str, only: set[int] | None) -> int:
    session = str(uuid.uuid4())
    failures = 0

    async with httpx.AsyncClient() as client:
        try:
            health = await client.get(f"{url.rstrip('/')}/api/health", timeout=20.0)
            print(f"Health: {health.status_code} {health.text}\n")
        except httpx.HTTPError as exc:
            print(f"Không kết nối được tới {url}: {exc}")
            return 1

        for index, (question, expectation) in enumerate(QUESTIONS, start=1):
            if only and index not in only:
                continue
            data, elapsed = await ask(client, url, question, [], session)
            print("=" * 78)
            print(f"[{index}] {question}")
            print(f"    Kỳ vọng: {expectation}")
            print(f"    Thời gian: {elapsed:.2f}s")
            if "error" in data:
                failures += 1
                print(f"    LỖI: {data['error']}")
                continue
            print(f"    Trả lời:\n{_indent(data.get('reply', ''))}")
            attachments = data.get("attachments") or []
            if attachments:
                for item in attachments:
                    print(f"    Đính kèm [{item.get('type')}]: {item.get('title')} -> {item.get('url')}")
            print()

        if not only:
            for first, second in FOLLOWUP:
                print("=" * 78)
                print(f"[nối tiếp] {first}  ->  {second}")
                data1, _ = await ask(client, url, first, [], session)
                history = [
                    {"role": "user", "content": first},
                    {"role": "assistant", "content": data1.get("reply", "")},
                ]
                data2, elapsed = await ask(client, url, second, history, session)
                print(f"    Thời gian: {elapsed:.2f}s")
                print(f"    Trả lời:\n{_indent(data2.get('reply', data2.get('error', '')))}")
                print()

    print("=" * 78)
    print("Hoàn tất." if not failures else f"Hoàn tất với {failures} câu lỗi.")
    return 1 if failures else 0


def _indent(text: str, prefix: str = "      ") -> str:
    return "\n".join(prefix + line for line in text.split("\n"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Kiểm thử nhanh API chatbot")
    parser.add_argument("--url", default="http://localhost:8000", help="Địa chỉ backend")
    parser.add_argument("--only", default="", help="Chỉ chạy các câu theo số thứ tự, ví dụ 3,7")
    args = parser.parse_args()
    setup_logging("WARNING")
    only = {int(x) for x in args.only.split(",") if x.strip().isdigit()} or None
    return asyncio.run(run(args.url, only))


if __name__ == "__main__":
    raise SystemExit(main())
