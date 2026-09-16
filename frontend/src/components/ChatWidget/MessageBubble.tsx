import type { ChatAttachment, ChatMessage } from '../../types/chat'

const timeFormatter = new Intl.DateTimeFormat('vi-VN', {
  hour: '2-digit',
  minute: '2-digit',
})

function Attachment({ item }: { item: ChatAttachment }) {
  if (item.type === 'image') {
    return (
      <a
        className="chat-msg__image-link"
        href={item.url}
        target="_blank"
        rel="noreferrer"
        title={item.title}
      >
        <img
          className="chat-msg__image"
          src={item.url}
          alt={item.title ?? 'Hình ảnh dự án'}
          loading="lazy"
        />
      </a>
    )
  }

  return (
    <a className="chat-msg__link" href={item.url} target="_blank" rel="noreferrer">
      {item.title ?? item.url}
    </a>
  )
}

export function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user'
  const attachments = message.attachments ?? []

  return (
    <div className={`chat-msg chat-msg--${isUser ? 'user' : 'bot'}`}>
      <div className="chat-msg__bubble">
        {message.content.split('\n').map((line, index) => (
          <p key={index}>{line || ' '}</p>
        ))}

        {attachments.length > 0 && (
          <div className="chat-msg__attachments">
            {attachments.map((item) => (
              <Attachment key={item.url} item={item} />
            ))}
          </div>
        )}
      </div>
      <time className="chat-msg__time" dateTime={message.createdAt}>
        {timeFormatter.format(new Date(message.createdAt))}
      </time>
    </div>
  )
}
