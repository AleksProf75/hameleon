import { useEffect, useRef, useState } from 'react'

import './ChatWidget.css'

const TOKEN_KEY = 'hameleonChatToken'
const POLL_MS = 4000

function readToken() {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

function saveToken(token) {
  try {
    if (token) {
      localStorage.setItem(TOKEN_KEY, token)
    } else {
      localStorage.removeItem(TOKEN_KEY)
    }
  } catch {
    // Без localStorage чат работает до перезагрузки страницы
  }
}

function ChatWidget() {
  const [isOpen, setIsOpen] = useState(false)
  const [token, setToken] = useState(readToken)
  const [messages, setMessages] = useState([])
  const [name, setName] = useState('')
  const [text, setText] = useState('')
  const [error, setError] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [hasUnread, setHasUnread] = useState(false)
  const listRef = useRef(null)
  const lastIdRef = useRef(0)

  const isOpenRef = useRef(false)
  const pollRef = useRef(null)

  // Новые сообщения от менеджера проверяем, пока на сайте есть начатый чат
  useEffect(() => {
    if (!token) {
      return undefined
    }

    let isActive = true
    let isFirstPoll = true

    const poll = async () => {
      try {
        const response = await fetch(
          `/api/chat/messages?after=${lastIdRef.current}`,
          { headers: { 'X-Chat-Token': token } },
        )

        if (!isActive) {
          return
        }

        if (response.status === 404) {
          saveToken(null)
          setToken(null)
          setMessages([])
          lastIdRef.current = 0
          return
        }

        if (!response.ok) {
          return
        }

        const { messages: incoming } = await response.json()

        if (!incoming.length) {
          return
        }

        lastIdRef.current = incoming[incoming.length - 1].id

        setMessages((prev) => {
          const known = new Set(prev.map((message) => message.id))
          return [...prev, ...incoming.filter((message) => !known.has(message.id))]
        })

        if (
          !isFirstPoll
          && !isOpenRef.current
          && incoming.some((message) => message.author === 'manager')
        ) {
          setHasUnread(true)
        }
      } catch {
        // Сеть недоступна — попробуем при следующем опросе
      } finally {
        isFirstPoll = false
      }
    }

    pollRef.current = poll
    poll()
    const timer = setInterval(poll, POLL_MS)

    return () => {
      isActive = false
      pollRef.current = null
      clearInterval(timer)
    }
  }, [token])

  useEffect(() => {
    if (isOpen) {
      listRef.current?.scrollTo({ top: listRef.current.scrollHeight })
    }
  }, [isOpen, messages])

  const toggle = () => {
    isOpenRef.current = !isOpen
    setIsOpen(!isOpen)
    setHasUnread(false)
  }

  const handleSubmit = async (event) => {
    event.preventDefault()

    const trimmed = text.trim()

    if (!trimmed || isSending) {
      return
    }

    setIsSending(true)
    setError('')

    try {
      const response = token
        ? await fetch('/api/chat/messages', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Chat-Token': token,
          },
          body: JSON.stringify({ text: trimmed }),
        })
        : await fetch('/api/chat/start', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: name.trim() || null,
            text: trimmed,
            website: event.target.elements.website.value,
          }),
        })

      if (response.status === 429) {
        setError('Слишком много сообщений. Попробуйте через несколько минут.')
        return
      }

      if (!response.ok) {
        throw new Error('Ошибка отправки')
      }

      if (!token) {
        // Историю чата загрузит опрос, который запустится с новым токеном
        const data = await response.json()
        saveToken(data.token)
        setToken(data.token)
      } else {
        await pollRef.current?.()
      }

      setText('')
    } catch {
      setError('Не удалось отправить сообщение. Попробуйте ещё раз.')
    } finally {
      setIsSending(false)
    }
  }

  return (
    <div className="chat-widget">
      {isOpen && (
        <div
          className="chat-widget__window"
          role="dialog"
          aria-label="Онлайн-чат"
        >
          <div className="chat-widget__header">
            <div>
              <strong>Онлайн-консультант</strong>
              <span>Ответим в рабочее время</span>
            </div>

            <button
              type="button"
              className="chat-widget__close"
              onClick={toggle}
              aria-label="Закрыть чат"
            >
              ×
            </button>
          </div>

          <div
            className="chat-widget__messages"
            ref={listRef}
          >
            {messages.length === 0 && (
              <p className="chat-widget__hint">
                Задайте вопрос о потолках, ценах или замере —
                менеджер ответит здесь же.
              </p>
            )}

            {messages.map((message) => (
              <div
                key={message.id}
                className={`chat-widget__message chat-widget__message--${message.author}`}
              >
                {message.text}

                {(message.manager || message.time) && (
                  <span className="chat-widget__meta">
                    {message.manager ? `${message.manager} · ` : ''}
                    {message.time}
                  </span>
                )}
              </div>
            ))}
          </div>

          <form
            className="chat-widget__form"
            onSubmit={handleSubmit}
          >
            {!token && (
              <input
                className="chat-widget__input"
                type="text"
                placeholder="Как к вам обращаться (необязательно)"
                maxLength={100}
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            )}

            {/* Поле-ловушка для ботов: человек его не видит */}
            <input
              type="text"
              name="website"
              tabIndex={-1}
              autoComplete="off"
              aria-hidden="true"
              style={{ position: 'absolute', left: '-10000px' }}
            />

            <div className="chat-widget__row">
              <textarea
                className="chat-widget__input"
                placeholder="Ваше сообщение"
                rows={2}
                maxLength={1000}
                value={text}
                onChange={(event) => setText(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault()
                    event.currentTarget.form.requestSubmit()
                  }
                }}
                required
              />

              <button
                type="submit"
                className="chat-widget__send"
                disabled={isSending}
                aria-label="Отправить"
              >
                ➤
              </button>
            </div>

            {error && (
              <p className="chat-widget__error">
                {error}
              </p>
            )}

            {!token && (
              <p className="chat-widget__consent">
                Отправляя сообщение, вы соглашаетесь с{' '}
                <a
                  href="/privacy.html"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  политикой обработки персональных данных
                </a>
              </p>
            )}
          </form>
        </div>
      )}

      <button
        type="button"
        className="chat-widget__toggle"
        onClick={toggle}
        aria-label={isOpen ? 'Закрыть чат' : 'Открыть чат'}
      >
        {isOpen ? '×' : '💬'}

        {hasUnread && !isOpen && (
          <span className="chat-widget__badge" />
        )}
      </button>
    </div>
  )
}

export default ChatWidget
