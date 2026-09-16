export type ChatRole = 'user' | 'assistant'

/** Ảnh hoặc liên kết backend gửi kèm câu trả lời (poster, mặt bằng, map 360...). */
export interface ChatAttachment {
  type: 'image' | 'link'
  url: string
  title?: string
}

export interface ChatMessage {
  id: string
  role: ChatRole
  content: string
  /** ISO timestamp, dùng để hiển thị giờ gửi. */
  createdAt: string
  attachments?: ChatAttachment[]
}

/** Phần lịch sử gửi kèm lên backend (bỏ id/createdAt cho gọn payload). */
export interface ChatHistoryItem {
  role: ChatRole
  content: string
}

export interface ChatRequest {
  message: string
  session_id: string
  history: ChatHistoryItem[]
}

export interface ChatResponse {
  reply: string
  session_id?: string
  attachments?: ChatAttachment[]
}

/** Body lỗi chuẩn của FastAPI. */
export interface ApiErrorBody {
  detail?: string
}
