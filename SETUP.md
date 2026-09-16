# Các bước bạn cần làm để chatbot chạy được

Backend đã hoàn tất và kiểm thử. Còn ba việc cần tài khoản của bạn.

## 1. Tạo lại Gemini API key (bắt buộc)

Key hiện tại trong `.env` bị Google từ chối:

```
403 PERMISSION_DENIED - "Your project has been denied access"
```

Key vẫn liệt kê được model nhưng mọi lệnh sinh văn bản và embedding đều bị chặn,
nghĩa là project Google Cloud gắn với key đó đang bị khoá.

Cách xử lý:

1. Vào https://aistudio.google.com/apikey
2. Tạo API key mới, nên chọn **một project Google Cloud khác** với project của key cũ
3. Thay giá trị `GEMINI_API_KEY` trong `.env` ở thư mục gốc (file này dùng chung cho cả backend và frontend)
4. Kiểm tra lại:

```bash
cd backend
.venv/Scripts/python.exe -m scripts.check_models
```

Script sẽ in ra model nào dùng được. Nếu `gemini-3.1-flash-lite` báo lỗi mà model
khác báo OK, đổi `GEMINI_CHAT_MODEL` trong `.env` sang model đó.

## 2. Tạo bảng trên Supabase

1. Mở https://supabase.com/dashboard, chọn project, vào **SQL Editor**
2. Dán toàn bộ nội dung `backend/supabase/001_schema.sql` rồi bấm **Run**
3. Vào **Storage**, bấm **New bucket**, đặt tên `media`, bật **Public bucket**
4. Kiểm tra:

```bash
cd backend
.venv/Scripts/python.exe -m scripts.check_supabase
```

Phải thấy tất cả dòng đều `OK`.

## 3. Nạp dữ liệu

```bash
cd backend
.venv/Scripts/python.exe -m scripts.ingest
```

Lệnh này tải file Excel từ Google Sheets, tách thành 164 đoạn, gọi Gemini để
embedding rồi ghi lên Supabase. Mất khoảng một đến hai phút.

Muốn xem trước mà không gọi API nào:

```bash
.venv/Scripts/python.exe -m scripts.ingest --dry-run
```

## 4. Chạy thử

Hai cửa sổ terminal:

```bash
# Cửa sổ 1
cd backend
.venv/Scripts/python.exe -m uvicorn main:app --reload --port 8000

# Cửa sổ 2
cd frontend
npm run dev
```

Mở http://localhost:5173 và bấm vào bong bóng chat góc dưới bên phải.

Kiểm thử tự động bộ 14 câu hỏi mẫu:

```bash
cd backend
.venv/Scripts/python.exe -m scripts.smoke_test
```

## 5. Thêm ảnh poster dự án (khi nào có ảnh)

1. Chép ảnh vào `backend/data/media/`
2. Sửa `backend/data/media_manifest.json`, mỗi ảnh một mục với `file`, `title`,
   `description`, `tags`. Mô tả càng chi tiết thì chatbot tìm càng đúng.
3. Chạy:

```bash
cd backend
.venv/Scripts/python.exe -m scripts.upload_media
.venv/Scripts/python.exe -m scripts.ingest --sources media
```

File `media_manifest.json` hiện có sẵn ba mục mẫu. Xoá hoặc sửa theo ảnh thật của bạn.

## 6. Triển khai Vercel

Xem hướng dẫn chi tiết trong [DEPLOY.md](DEPLOY.md).
