import { useEffect, useState } from 'react'
import { ChatIcon, CloseIcon } from '../icons'
import { ChatPanel } from './ChatPanel'
import './ChatWidget.css'

export function ChatWidget() {
  const [open, setOpen] = useState(false)
  const [tooltipReady, setTooltipReady] = useState(false)
  const [tooltipDismissed, setTooltipDismissed] = useState(false)

  // Nhắc người dùng sau vài giây nếu chưa mở chat.
  useEffect(() => {
    const timer = setTimeout(() => setTooltipReady(true), 4000)
    return () => clearTimeout(timer)
  }, [])

  const showTooltip = tooltipReady && !open && !tooltipDismissed

  return (
    <div className="chat-widget">
      <ChatPanel open={open} onClose={() => setOpen(false)} />

      {showTooltip && (
        <div className="chat-widget__tooltip">
          Bạn cần tư vấn? Hỏi trợ lý Văn Phú nhé!
          <button
            type="button"
            aria-label="Ẩn gợi ý"
            onClick={() => setTooltipDismissed(true)}
          >
            <CloseIcon width={14} height={14} />
          </button>
        </div>
      )}

      <button
        type="button"
        className={`chat-widget__bubble${open ? ' is-open' : ''}`}
        onClick={() => setOpen((value) => !value)}
        aria-label={open ? 'Đóng cửa sổ chat' : 'Mở trợ lý ảo Văn Phú'}
        aria-expanded={open}
      >
        {open ? <CloseIcon /> : <ChatIcon />}
      </button>
    </div>
  )
}
