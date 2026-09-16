import type {
  ApiErrorBody,
  ChatHistoryItem,
  ChatRequest,
  ChatResponse,
} from '../types/chat'

/** Base URL backend. Để trống trong dev -> gọi "/api/chat" và Vite proxy sang FastAPI. */
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

/** Bật chế độ giả lập khi backend chưa sẵn sàng. */
const USE_MOCK = import.meta.env.VITE_CHAT_MOCK === 'true'

const REQUEST_TIMEOUT_MS = 30_000

export const CHAT_ENDPOINT = `${API_BASE_URL}/api/chat`

export class ChatApiError extends Error {
  readonly status?: number

  constructor(message: string, status?: number) {
    super(message)
    this.name = 'ChatApiError'
    this.status = status
  }
}

const MOCK_REPLIES = [
  'Cảm ơn bạn đã quan tâm tới Văn Phú. Hiện trợ lý đang chạy ở chế độ thử nghiệm nên chưa kết nối tới hệ thống tri thức. Bạn cứ để lại câu hỏi, đội ngũ sẽ phản hồi sớm nhất.',
  'Văn Phú có 23 năm kinh nghiệm phát triển bất động sản, tổng quỹ đất 1.905 ha và 18 công ty thành viên. Bạn muốn tìm hiểu thêm về dự án nào ạ?',
  'Đây là câu trả lời giả lập để kiểm thử giao diện. Khi backend FastAPI được kết nối, trợ lý sẽ trả lời dựa trên dữ liệu thật của Văn Phú.',
]

let mockIndex = 0

function mockRequest(message: string): Promise<ChatResponse> {
  const reply = MOCK_REPLIES[mockIndex % MOCK_REPLIES.length]
  mockIndex += 1
  return new Promise((resolve) => {
    setTimeout(
      () => resolve({ reply: `${reply}\n\n(Bạn vừa hỏi: "${message}")` }),
      800,
    )
  })
}

/**
 * Gửi một tin nhắn tới backend.
 *
 * Hợp đồng API (backend làm ở session sau):
 *   POST {API_BASE_URL}/api/chat
 *   Request : { message, session_id, history: [{ role, content }] }
 *   Response: { reply: string, session_id?: string }
 *   Lỗi     : HTTP 4xx/5xx kèm { detail: string }
 */
export async function sendChatMessage(
  message: string,
  sessionId: string,
  history: ChatHistoryItem[],
  signal?: AbortSignal,
): Promise<ChatResponse> {
  if (USE_MOCK) {
    return mockRequest(message)
  }

  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

  // Huỷ request khi component gọi abort (ví dụ đóng panel).
  signal?.addEventListener('abort', () => controller.abort(), { once: true })

  const payload: ChatRequest = {
    message,
    session_id: sessionId,
    history,
  }

  try {
    const response = await fetch(CHAT_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })

    if (!response.ok) {
      let detail = `Máy chủ trả về lỗi ${response.status}.`
      try {
        const body = (await response.json()) as ApiErrorBody
        if (body?.detail) detail = body.detail
      } catch {
        // Body không phải JSON - giữ thông báo mặc định.
      }
      throw new ChatApiError(detail, response.status)
    }

    const data = (await response.json()) as ChatResponse
    if (typeof data?.reply !== 'string') {
      throw new ChatApiError('Phản hồi từ máy chủ không đúng định dạng.')
    }
    return data
  } catch (error) {
    if (error instanceof ChatApiError) throw error
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ChatApiError(
        'Yêu cầu mất quá nhiều thời gian. Bạn vui lòng thử lại.',
      )
    }
    throw new ChatApiError(
      'Không kết nối được tới trợ lý. Bạn kiểm tra kết nối mạng rồi thử lại nhé.',
    )
  } finally {
    clearTimeout(timeoutId)
  }
}
