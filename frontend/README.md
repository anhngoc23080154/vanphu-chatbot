# Văn Phú - Frontend (landing page + chatbot widget)

Clone landing page của [vanphu.vn](https://vanphu.vn) (phần header + section "Về chúng tôi")
kèm box chat sẵn sàng kết nối backend FastAPI.

Stack: **Vite 8 + React 19 + TypeScript + CSS thuần** (không dùng UI framework).

## Chạy dự án

```bash
cd frontend
npm install
cp .env.example .env
npm run dev          # http://localhost:5173
```

Các lệnh khác:

| Lệnh | Tác dụng |
| --- | --- |
| `npm run dev` | Dev server, hot reload |
| `npm run build` | Kiểm tra kiểu + build production vào `dist/` |
| `npm run preview` | Chạy thử bản build |
| `npm run lint` | Lint bằng oxlint |

## Biến môi trường

| Biến | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `VITE_API_BASE_URL` | rỗng | Base URL backend FastAPI. Để trống khi dev, Vite sẽ proxy `/api` sang `http://localhost:8000`. |
| `VITE_CHAT_MOCK` | `true` | `true` = trả lời giả lập, không gọi backend. Đặt `false` khi backend đã sẵn sàng. |

## Hợp đồng API cho backend (làm ở session sau)

Box chat gọi đúng một endpoint:

```
POST {VITE_API_BASE_URL}/api/chat
Content-Type: application/json
```

Request body:

```json
{
  "message": "Văn Phú có những dự án nào?",
  "session_id": "6f1c...-uuid",
  "history": [
    { "role": "user", "content": "Xin chào" },
    { "role": "assistant", "content": "Chào bạn, tôi có thể giúp gì?" }
  ]
}
```

Response body:

```json
{
  "reply": "Văn Phú hiện có các dự án ...",
  "session_id": "6f1c...-uuid"
}
```

Quy ước:

- `session_id` do frontend sinh bằng `crypto.randomUUID()` và lưu ở `localStorage`
  (khóa `vanphu_chat_session`). Nếu backend trả về `session_id` khác, frontend sẽ ghi đè.
- `history` chỉ gồm tối đa 10 tin nhắn gần nhất, không kèm tin chào mừng.
- Lỗi trả về HTTP 4xx/5xx với body `{ "detail": "mô tả lỗi" }`. Frontend hiển thị
  nguyên văn `detail` cho người dùng.
- Timeout phía frontend là 30 giây.
- Backend cần bật CORS cho domain frontend khi chạy production.

Toàn bộ phần gọi API nằm gọn trong `src/lib/chatApi.ts`.

## Deploy lên Vercel (free tier)

1. Tạo project mới trên Vercel, trỏ tới repo này.
2. Đặt **Root Directory = `frontend`**.
3. Framework preset: Vite. Build command `npm run build`, output directory `dist`.
4. Thêm biến môi trường:
   - `VITE_API_BASE_URL` = URL của backend FastAPI (ví dụ `https://vanphu-chatbot-api.vercel.app`)
   - `VITE_CHAT_MOCK` = `false`
5. Deploy. File `vercel.json` đã cấu hình sẵn rewrite về `index.html`.

Backend FastAPI deploy thành project Vercel riêng, nhớ bật CORS cho domain frontend.

## Cấu trúc

```
src/
├── components/
│   ├── About/          # Section "Về chúng tôi" + counter đếm số
│   ├── ChatWidget/     # Bong bóng chat, panel, state, tin nhắn
│   ├── Footer/         # Footer nền tối
│   ├── Header/         # Header fixed + drawer mobile
│   ├── ScrollToTop/    # Nút cuộn lên có vòng tiến trình
│   └── icons/          # SVG inline
├── data/site.ts        # Toàn bộ nội dung tiếng Việt
├── hooks/              # useCountUp, useInView, useScrollProgress, useMediaQuery
├── lib/chatApi.ts      # Lớp gọi backend + chế độ mock
├── styles/             # variables.css (design token), global.css (reset)
└── types/chat.ts       # Kiểu dữ liệu của API chat
```

## Ghi chú

- Landing page gốc có thêm video hero, slider dự án, giải thưởng và tin tức. Bản clone này
  cố ý chỉ giữ header + "Về chúng tôi" + footer theo phạm vi đã thống nhất.
- Các link menu và footer đều trỏ `#` vì không clone trang con.
- Ảnh trong `public/images/` tải từ vanphu.vn, dùng cho mục đích đồ án.
