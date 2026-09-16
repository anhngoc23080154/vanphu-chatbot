import { useCallback, useEffect, useRef, useState } from 'react'
import { ChatApiError, sendChatMessage } from '../../lib/chatApi'
import { createId } from '../../lib/id'
import type { ChatHistoryItem, ChatMessage } from '../../types/chat'

const SESSION_KEY = 'vanphu_chat_session'
const HISTORY_KEY = 'vanphu_chat_history'
/** Số cặp hội thoại gần nhất gửi kèm lên backend làm ngữ cảnh. */
const HISTORY_LIMIT = 10

export const WELCOME_MESSAGE: ChatMessage = {
  id: 'welcome',
  role: 'assistant',
  content:
    'Xin chào! Tôi là trợ lý ảo của Văn Phú. Tôi có thể giúp bạn tìm hiểu về các dự án, chính sách bán hàng và thông tin doanh nghiệp. Bạn cần hỗ trợ gì ạ?',
  createdAt: new Date().toISOString(),
}

function readSessionId(): string {
  try {
    const stored = localStorage.getItem(SESSION_KEY)
    if (stored) return stored
    const created = createId()
    localStorage.setItem(SESSION_KEY, created)
    return created
  } catch {
    // Trình duyệt chặn storage (chế độ ẩn danh) - dùng id tạm trong bộ nhớ.
    return createId()
  }
}

function readHistory(): ChatMessage[] {
  try {
    const raw = sessionStorage.getItem(HISTORY_KEY)
    if (!raw) return [WELCOME_MESSAGE]
    const parsed = JSON.parse(raw) as ChatMessage[]
    return Array.isArray(parsed) && parsed.length > 0
      ? parsed
      : [WELCOME_MESSAGE]
  } catch {
    return [WELCOME_MESSAGE]
  }
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>(readHistory)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  // Lazy initializer: chỉ chạy ở lần render đầu, không đọc ref trong lúc render.
  const [initialSessionId] = useState(readSessionId)
  const sessionIdRef = useRef<string>(initialSessionId)

  // Giữ lịch sử khi người dùng tải lại trang.
  useEffect(() => {
    try {
      sessionStorage.setItem(HISTORY_KEY, JSON.stringify(messages))
    } catch {
      // Bỏ qua khi storage không khả dụng.
    }
  }, [messages])

  // Huỷ request đang chạy khi unmount.
  useEffect(() => () => abortRef.current?.abort(), [])

  const send = useCallback(
    async (rawText: string) => {
      const text = rawText.trim()
      if (!text || isLoading) return

      const userMessage: ChatMessage = {
        id: createId(),
        role: 'user',
        content: text,
        createdAt: new Date().toISOString(),
      }

      // Lấy ngữ cảnh trước khi thêm tin nhắn mới, bỏ tin chào mừng.
      const history: ChatHistoryItem[] = messages
        .filter((m) => m.id !== 'welcome')
        .slice(-HISTORY_LIMIT)
        .map((m) => ({ role: m.role, content: m.content }))

      setMessages((prev) => [...prev, userMessage])
      setIsLoading(true)
      setError(null)

      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      try {
        const response = await sendChatMessage(
          text,
          sessionIdRef.current,
          history,
          controller.signal,
        )

        if (response.session_id) {
          sessionIdRef.current = response.session_id
          try {
            localStorage.setItem(SESSION_KEY, response.session_id)
          } catch {
            // Bỏ qua khi storage không khả dụng.
          }
        }

        setMessages((prev) => [
          ...prev,
          {
            id: createId(),
            role: 'assistant',
            content: response.reply,
            createdAt: new Date().toISOString(),
            attachments: response.attachments ?? [],
          },
        ])
      } catch (err) {
        const message =
          err instanceof ChatApiError
            ? err.message
            : 'Đã xảy ra lỗi không mong muốn. Bạn vui lòng thử lại.'
        setError(message)
      } finally {
        setIsLoading(false)
        abortRef.current = null
      }
    },
    [isLoading, messages],
  )

  const reset = useCallback(() => {
    abortRef.current?.abort()
    setMessages([{ ...WELCOME_MESSAGE, createdAt: new Date().toISOString() }])
    setError(null)
    setIsLoading(false)
    try {
      sessionStorage.removeItem(HISTORY_KEY)
    } catch {
      // Bỏ qua khi storage không khả dụng.
    }
  }, [])

  return { messages, isLoading, error, send, reset }
}
