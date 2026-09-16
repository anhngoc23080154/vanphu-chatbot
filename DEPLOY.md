# Triển khai lên Vercel

Dự án dùng **Vercel Services**: một project Vercel duy nhất chứa cả frontend Vite
và backend FastAPI, chạy chung một tên miền.

File cấu hình là [vercel.json](vercel.json) ở thư mục gốc. Nó khai báo hai service
và bảng định tuyến:

- Đường dẫn bắt đầu bằng `/api/` đi vào service backend.
- Mọi đường dẫn còn lại đi vào service frontend.

## Vì sao chọn cách này

Vì frontend và backend dùng chung một tên miền nên trình duyệt coi đây là cùng
nguồn gốc. Hệ quả:

- **Không cần CORS.** Không phải khai báo domain, không có lỗi bị chặn.
- **Không còn phụ thuộc vòng tròn.** Trước đây frontend cần biết domain backend,
  backend lại cần biết domain frontend. Giờ cả hai biến mất.
- `VITE_API_BASE_URL` để trống, frontend gọi thẳng đường dẫn tương đối `/api/chat`.
- Một lần deploy, một bộ biến môi trường, một tên miền.

## Các bước

### 1. Tạo project

Vào https://vercel.com/new, chọn repository `vanphu-chatbot`.

**Để nguyên Root Directory là thư mục gốc**, đừng trỏ vào `frontend` hay `backend`.
Vercel đọc `vercel.json` ở gốc và tự dựng hai service.

### 2. Khai báo biến môi trường

Biến dùng chung cho cả project, chọn cả ba môi trường Production, Preview, Development:

| Tên | Giá trị |
|---|---|
| `GEMINI_API_KEY` | key trong `.env` ở máy bạn |
| `SUPABASE_URL` | `https://xnxyebqqnblrzecjaijl.supabase.co` |
| `SUPABASE_SECRET_KEY` | secret key trong `.env` |
| `CRON_SECRET` | chuỗi ngẫu nhiên, xem lệnh bên dưới |
| `VITE_CHAT_MOCK` | `false` |

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Không cần `CORS_ORIGINS` và không cần `VITE_API_BASE_URL`.

Các khoá bí mật không lọt vào frontend: Vite chỉ nhúng biến có tiền tố `VITE_`
vào mã nguồn phía trình duyệt, nên `GEMINI_API_KEY` và `SUPABASE_SECRET_KEY`
chỉ tồn tại phía máy chủ.

### 3. Deploy và kiểm tra

```bash
# Sức khoẻ backend, mong đợi "status":"ok" và "configured":true
curl https://<domain>.vercel.app/api/health

# Hỏi thử một câu
curl -X POST https://<domain>.vercel.app/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Chủ đầu tư dự án là ai?","session_id":"test","history":[]}'

# Cron giữ Supabase không bị tạm dừng
curl -H "Authorization: Bearer <CRON_SECRET>" \
  https://<domain>.vercel.app/api/cron/keepalive

# Không có token thì phải bị từ chối
curl -i https://<domain>.vercel.app/api/cron/keepalive   # mong đợi 401
```

Bộ câu hỏi mẫu chạy thẳng vào tên miền thật:

```bash
cd backend
.venv/Scripts/python.exe -m scripts.smoke_test --url https://<domain>.vercel.app
```

Cuối cùng mở website, bấm bong bóng chat góc dưới bên phải và hỏi vài câu.

### 4. Xác nhận cron job

Vào project trên Vercel, tab **Cron Jobs**. Phải thấy `/api/cron/keepalive` với
lịch `0 3 * * *`, tức 10 giờ sáng giờ Việt Nam mỗi ngày. Bấm Run để chạy thử.

Gói Hobby cho tối đa hai cron job, mỗi job một lần mỗi ngày, thời điểm có thể lệch
trong vòng một giờ. Vẫn dư an toàn so với mốc 7 ngày Supabase dùng để tạm dừng project.

---

## Nếu tài khoản chưa bật được Services

Services là tính năng tương đối mới và có thể bị giới hạn theo tài khoản. Nếu khi
deploy Vercel báo không nhận `services` trong `vercel.json`, hãy quay về cách tạo
**hai project riêng**:

1. Xoá `vercel.json` ở thư mục gốc.
2. Đổi tên `backend/vercel.two-projects.json.bak` thành `backend/vercel.json`.
3. Tạo project thứ nhất, Root Directory là `backend`, Framework Preset là Other.
   Thêm các biến ở bước 2 phía trên, và thêm `CORS_ORIGINS` tạm bằng
   `http://localhost:5173`.
4. Tạo project thứ hai, Root Directory là `frontend`, Framework Preset là Vite.
   Thêm `VITE_API_BASE_URL` bằng domain backend và `VITE_CHAT_MOCK` bằng `false`.
5. Quay lại project backend, sửa `CORS_ORIGINS` thành
   `https://<domain-frontend>.vercel.app,http://localhost:5173` rồi **Redeploy**.
   Biến môi trường chỉ được đọc lại khi có deploy mới.

Cách này chạy được nhưng phải quản lý hai tên miền, hai bộ biến môi trường, và
phải nhớ mở CORS đúng domain.

---

## Những điểm đã kiểm chứng

| Hạng mục | Kết quả |
|---|---|
| Ứng dụng khởi động khi không có file `.env`, chỉ có biến môi trường | Đạt |
| CORS cho đúng domain, chặn domain lạ (chỉ cần ở chế độ hai project) | Đạt |
| Cron từ chối request không có token | Đạt |
| Kích thước thư viện runtime | khoảng 75 MB, giới hạn 500 MB |
| Độ trễ trả lời thực tế | 2 đến 3,5 giây, giới hạn frontend 30 giây |
| Bí mật không bị commit | Đạt, `.env` nằm trong `.gitignore` |

Cấu hình service backend đã khai báo loại trừ thư mục `tests`, `scripts`, `data`
và `supabase` khỏi bundle, vì runtime Python của Vercel gộp toàn bộ file trong
thư mục chứ không tự lọc.

---

## Xử lý sự cố

| Hiện tượng | Nguyên nhân và cách xử lý |
|---|---|
| Vẫn thấy câu trả lời giả lập | `VITE_CHAT_MOCK` chưa đặt `false`, hoặc chưa deploy lại sau khi sửa biến |
| `/api/chat` trả về trang HTML | Thứ tự rewrite bị sai. Luật `/api/(.*)` phải đứng trước luật `/(.*)` |
| Lỗi 503 khi hỏi | Hết hạn mức Gemini trong phút đó, hoặc thiếu biến môi trường. Xem log function |
| Lỗi 504 | Câu trả lời quá 27 giây. Hiếm, thường do Gemini chậm bất thường |
| `/api/health` trả `configured: false` | Thiếu một trong ba biến `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY` |
| Supabase bị tạm dừng | Cron chưa chạy. Vào dashboard Supabase bấm Restore, rồi kiểm tra tab Cron Jobs |

Xem log: project trên Vercel, tab **Logs**, lọc theo service `backend`.
