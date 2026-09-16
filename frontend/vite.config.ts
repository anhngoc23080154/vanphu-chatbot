import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],

  // Dùng chung file .env ở thư mục gốc dự án với backend, thay vì frontend/.env.
  // An toàn: Vite chỉ nhúng vào mã trình duyệt các biến có tiền tố VITE_,
  // nên GEMINI_API_KEY và SUPABASE_SECRET_KEY trong cùng file không bị lộ.
  envDir: fileURLToPath(new URL('..', import.meta.url)),

  server: {
    port: 5173,
    proxy: {
      // Dev: chuyển tiếp /api tới backend FastAPI chạy local.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
