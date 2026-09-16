import { useEffect, useRef, useState } from 'react'
import { CloseIcon, SendIcon, TrashIcon } from '../icons'
import { MessageBubble } from './MessageBubble'
import { useChat } from './useChat'

interface ChatPanelProps {
  open: boolean
  onClose: () => void
}

const SUGGESTIONS = [
  'Văn Phú có những dự án nào?',
  'Thông tin dự án Vlasta Phú Thuận?',
  'Liên hệ tư vấn bằng cách nào?',
]

export function ChatPanel({ open, onClose }: ChatPanelProps) {
  const { messages, isLoading, error, send, reset } = useChat()
  const [input, setInput] = useState('')
  const listRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Luôn cuộn xuống tin nhắn mới nhất.
  useEffect(() => {
    if (!open) return
    const list = listRef.current
    if (list) list.scrollTop = list.scrollHeight
  }, [messages, isLoading, open])

  // Focus ô nhập khi mở panel.
  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  // Đóng bằng phím Esc.
  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  const submit = (text: string) => {
    if (!text.trim() || isLoading) return
    void send(text)
    setInput('')
  }

  return (
    <div
      className={`chat-panel${open ? ' is-open' : ''}`}
      role="dialog"
      aria-modal="false"
      aria-label="Trợ lý ảo Văn Phú"
      aria-hidden={!open}
    >
      <header className="chat-panel__head">
        <div className="chat-panel__identity">
          <span className="chat-panel__avatar" aria-hidden="true">
            VP
          </span>
          <div>
            <p className="chat-panel__name">Trợ lý ảo Văn Phú</p>
            <p className="chat-panel__status">
              {isLoading ? 'Đang soạn trả lời…' : 'Trực tuyến'}
            </p>
          </div>
        </div>
        <div className="chat-panel__actions">
          <button
            type="button"
            onClick={reset}
            aria-label="Xoá hội thoại"
            title="Xoá hội thoại"
            tabIndex={open ? 0 : -1}
          >
            <TrashIcon />
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label="Đóng cửa sổ chat"
            tabIndex={open ? 0 : -1}
          >
            <CloseIcon width={20} height={20} />
          </button>
        </div>
      </header>

      <div className="chat-panel__body" ref={listRef}>
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}

        {isLoading && (
          <div className="chat-msg chat-msg--bot">
            <div className="chat-msg__bubble chat-typing" aria-label="Đang trả lời">
              <span />
              <span />
              <span />
            </div>
          </div>
        )}

        {error && (
          <div className="chat-panel__error" role="alert">
            {error}
          </div>
        )}

        {messages.length <= 1 && !isLoading && (
          <div className="chat-panel__suggestions">
            {SUGGESTIONS.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                onClick={() => submit(suggestion)}
                tabIndex={open ? 0 : -1}
              >
                {suggestion}
              </button>
            ))}
          </div>
        )}
      </div>

      <form
        className="chat-panel__form"
        onSubmit={(event) => {
          event.preventDefault()
          submit(input)
        }}
      >
        <textarea
          ref={inputRef}
          className="chat-panel__input"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              submit(input)
            }
          }}
          placeholder="Nhập câu hỏi của bạn…"
          rows={1}
          aria-label="Nội dung tin nhắn"
          tabIndex={open ? 0 : -1}
        />
        <button
          type="submit"
          className="chat-panel__send"
          disabled={!input.trim() || isLoading}
          aria-label="Gửi tin nhắn"
          tabIndex={open ? 0 : -1}
        >
          <SendIcon />
        </button>
      </form>
    </div>
  )
}
