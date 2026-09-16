# Backend chatbot Văn Phú - Vlasta Premier Phú Thuận

API FastAPI trả lời câu hỏi khách hàng bằng kỹ thuật RAG: tìm kiếm ngữ nghĩa trên
Supabase (pgvector) rồi sinh câu trả lời bằng Gemini.

## Kiến trúc

```
Khách hỏi
   |
   v
POST /api/chat  --> query_analyzer (regex, không gọi LLM)
                        |
                        +--> Gemini embed (1 lần) --> match_documents (Q&A, tóm tắt giỏ hàng, media)
                        |                          \-> find_units (SQL, tra cứu chính xác theo mã căn)
                        v
                    prompt + ngữ cảnh --> Gemini generate (1 lần) --> câu trả lời + ảnh đính kèm
```

Mỗi lượt chat tốn đúng **1 lần embed + 1 lần generate** để phù hợp hạn mức miễn phí
của Gemini (khoảng 10 request/phút).

## Chuẩn bị

```bash
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
```

Biến môi trường: toàn dự án dùng chung MỘT file `.env` ở thư mục gốc, cho cả
backend lẫn frontend. Sao chép `.env.example` ở thư mục gốc thành `.env` rồi điền
giá trị. Frontend đọc cùng file đó nhờ tuỳ chọn `envDir` trong `vite.config.ts`,
nhưng chỉ nhúng vào trình duyệt các biến có tiền tố `VITE_`.

## Tạo cơ sở dữ liệu

1. Mở Supabase Dashboard > SQL Editor, dán toàn bộ `supabase/001_schema.sql` và chạy.
2. Vào Storage, tạo bucket **public** tên `media`.

## Nạp dữ liệu

```bash
# Xem trước kết quả tách đoạn, không gọi API nào
.venv/Scripts/python.exe -m scripts.ingest --dry-run

# Nạp Q&A và giỏ hàng lên Supabase
.venv/Scripts/python.exe -m scripts.ingest --sources qa,units

# Nạp tất cả (gồm cả media)
.venv/Scripts/python.exe -m scripts.ingest

# Chỉ ghi bảng units, bỏ qua embedding (khi chưa có API key Gemini hợp lệ)
.venv/Scripts/python.exe -m scripts.ingest --sources units --skip-embeddings

# Embedding lại toàn bộ, kể cả đoạn đã có
.venv/Scripts/python.exe -m scripts.ingest --force
```

### Về hạn mức Gemini khi nạp dữ liệu

Gemini tính hạn mức embedding theo **từng đoạn** trong lô chứ không theo số lần
gọi API. Script tự điều tiết để không vượt `EMBED_ITEMS_PER_MINUTE` đoạn mỗi phút,
và khi bị lỗi 429 thì chờ đúng khoảng thời gian Google yêu cầu rồi thử lại.

Nếu lệnh bị ngắt giữa chừng, **không cần xoá gì cả**: cứ chạy lại lệnh cũ. Mỗi đoạn
có id cố định sinh từ nội dung khoá, nên script sẽ bỏ qua phần đã nạp và chỉ
embedding phần còn thiếu. Việc dọn các đoạn cũ không còn dùng chỉ diễn ra sau khi
một nguồn đã hoàn tất, nên dữ liệu không bị mất khi chạy dở.

Dùng `--force` khi bạn sửa nội dung nguồn và muốn embedding lại tất cả.

Script tự tải file Excel từ Google Sheets (link công khai). Thêm `--offline` để
dùng lại file đã tải trong `data/cache/`.

Dữ liệu được nạp:

| Nguồn | Nội dung | Số lượng |
|---|---|---|
| `qa` | 79 cặp hỏi - đáp từ sheet Q&A | 79 đoạn |
| `units` | 805 dòng giỏ hàng vào bảng `units` + tóm tắt layout/thống kê | 83 đoạn |
| `media` | Mô tả ảnh, poster, link tài liệu | tùy manifest |

Giỏ hàng **không** embedding từng căn. Lý do: 739 căn phần lớn trùng layout, và câu
hỏi về mã căn cần độ chính xác tuyệt đối. Thay vào đó bảng `units` phục vụ tra cứu
SQL, còn các đoạn tóm tắt phục vụ câu hỏi ngữ nghĩa ("căn 2 phòng ngủ rộng bao nhiêu").

## Thêm ảnh, poster dự án

1. Chép ảnh vào `data/media/`.
2. Khai báo trong `data/media_manifest.json`:

```json
{
  "file": "poster-tong-quan.jpg",
  "type": "image",
  "title": "Poster tổng quan dự án",
  "description": "Mô tả càng chi tiết càng dễ tìm đúng ảnh: nội dung, góc nhìn, hạng mục, tháp, tiện ích...",
  "tags": ["poster", "tổng quan", "phối cảnh"],
  "category": "poster"
}
```

3. Tải lên và nạp:

```bash
.venv/Scripts/python.exe -m scripts.upload_media
.venv/Scripts/python.exe -m scripts.ingest --sources media
```

Chatbot tìm ảnh bằng cách embedding phần `title + description + tags`, so khớp với
câu hỏi của khách. Mô tả càng rõ ràng thì truy xuất càng đúng. Mục chỉ có `url`
(không có `file`) dùng cho link ngoài như bản đồ 360 độ hay thư mục Google Drive.

## Chạy và kiểm thử

```bash
.venv/Scripts/python.exe -m uvicorn main:app --reload --port 8000
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m scripts.smoke_test
.venv/Scripts/python.exe -m scripts.check_models     # kiểm tra API key Gemini
```

Frontend ở chế độ dev proxy `/api` sang `http://localhost:8000`. Nhớ đặt
`VITE_CHAT_MOCK=false` trong `.env` ở thư mục gốc.

## Triển khai Vercel

Tạo project Vercel riêng cho backend:

- Root Directory: `backend`
- Framework Preset: Other
- Environment Variables: `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY`,
  `CORS_ORIGINS` (thêm domain frontend), `CRON_SECRET`

Vercel tự nhận `main.py` làm entrypoint. `vercel.json` đặt `maxDuration` 60 giây và
khai báo cron job giữ Supabase không bị tạm dừng.

## Giữ Supabase không bị tạm dừng

Supabase gói miễn phí tạm dừng project sau 7 ngày không hoạt động. `vercel.json`
khai báo cron gọi `GET /api/cron/keepalive` lúc 03:00 UTC (10:00 giờ Việt Nam) mỗi ngày.
Endpoint chạy một truy vấn đọc thật lên bảng `documents`.

Kiểm tra thủ công:

```bash
curl -H "Authorization: Bearer $CRON_SECRET" https://<backend>.vercel.app/api/cron/keepalive
```

Nếu không muốn phụ thuộc Vercel Cron, có thể dùng GitHub Actions với lịch
`schedule: cron: '0 3 * * *'` gọi tới cùng endpoint.

## Xử lý sự cố

| Hiện tượng | Nguyên nhân thường gặp |
|---|---|
| `403 PERMISSION_DENIED` từ Gemini | API key thuộc project bị chặn. Tạo key mới tại Google AI Studio. |
| `503` khi chat | Hết hạn mức Gemini trong phút, hoặc Supabase chưa cấu hình. Xem log. |
| Chat trả lời "chưa có thông tin" | Chưa chạy `scripts.ingest`, hoặc bảng `documents` rỗng. |
| Frontend báo lỗi CORS | Thiếu domain frontend trong `CORS_ORIGINS`. |
