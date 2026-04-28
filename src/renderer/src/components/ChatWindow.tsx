import { useState, useEffect, useRef, KeyboardEvent } from 'react'
import MessageBubble from './MessageBubble'
import type { Message, Persona } from '../../../main/types'

interface Props {
  persona: Persona
}

const PLACEHOLDER = {
  alpha: '알파에게 분석을 요청하세요...',
  beta: '베타에게 일정이나 고민을 말해주세요...',
}

export default function ChatWindow({ persona }: Props) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [listening, setListening] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const recognitionRef = useRef<SpeechRecognition | null>(null)

  useEffect(() => {
    window.zab.getHistory(persona).then(setMessages)
  }, [persona])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  async function send() {
    const text = input.trim()
    if (!text || loading) return

    const userMsg: Message = { role: 'user', content: text }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setLoading(true)

    const result = await window.zab.chat(persona, text)

    if (result.error) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `[오류] ${result.error}` },
      ])
    } else if (result.content) {
      setMessages((prev) => [...prev, { role: 'assistant', content: result.content! }])
    }

    setLoading(false)
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  function toggleVoice() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SpeechRecognition) return

    if (listening) {
      recognitionRef.current?.stop()
      setListening(false)
      return
    }

    const recognition = new SpeechRecognition()
    recognition.lang = 'ko-KR'
    recognition.continuous = false
    recognition.interimResults = false

    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript
      setInput((prev) => prev + transcript)
    }
    recognition.onend = () => setListening(false)

    recognition.start()
    recognitionRef.current = recognition
    setListening(true)
  }

  async function clearChat() {
    await window.zab.clearHistory(persona)
    setMessages([])
  }

  const accentColor = persona === 'alpha' ? 'var(--alpha-primary)' : 'var(--beta-primary)'

  return (
    <div style={styles.container}>
      <div style={styles.toolbar}>
        <span style={styles.messageCount}>{messages.length}개의 메시지</span>
        <button style={styles.clearBtn} onClick={clearChat} title="대화 초기화">
          초기화
        </button>
      </div>

      <div style={styles.messageList}>
        {messages.length === 0 && (
          <div style={styles.empty}>
            <div style={{ ...styles.emptyDot, background: accentColor }} />
            <p style={styles.emptyText}>
              {persona === 'alpha'
                ? '알파가 분석을 기다리고 있습니다.'
                : '베타가 당신의 이야기를 듣고 있어요.'}
            </p>
          </div>
        )}
        {messages.map((msg, i) => (
          <MessageBubble key={i} message={msg} persona={persona} />
        ))}
        {loading && (
          <div style={styles.typingWrap}>
            <span style={{ ...styles.typingDot, animationDelay: '0ms' }} />
            <span style={{ ...styles.typingDot, animationDelay: '150ms' }} />
            <span style={{ ...styles.typingDot, animationDelay: '300ms' }} />
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div style={styles.inputArea}>
        <button
          style={{
            ...styles.voiceBtn,
            color: listening ? accentColor : 'var(--text-muted)',
          }}
          onClick={toggleVoice}
          title={listening ? '음성 입력 중지' : '음성 입력'}
        >
          {listening ? '...' : 'mic'}
        </button>
        <textarea
          style={styles.textarea}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={PLACEHOLDER[persona]}
          rows={1}
          disabled={loading}
        />
        <button
          style={{
            ...styles.sendBtn,
            background: input.trim() && !loading ? accentColor : 'var(--bg-hover)',
            color: input.trim() && !loading ? '#fff' : 'var(--text-muted)',
          }}
          onClick={send}
          disabled={!input.trim() || loading}
        >
          전송
        </button>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    flex: 1,
    overflow: 'hidden',
  },
  toolbar: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '6px 16px',
    borderBottom: '1px solid var(--border)',
    flexShrink: 0,
  },
  messageCount: {
    fontSize: 11,
    color: 'var(--text-muted)',
    fontFamily: 'var(--font-mono)',
  },
  clearBtn: {
    fontSize: 11,
    color: 'var(--text-muted)',
    padding: '2px 8px',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--border)',
    transition: 'color 0.15s, border-color 0.15s',
  },
  messageList: {
    flex: 1,
    overflowY: 'auto',
    padding: '12px 0',
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
  },
  empty: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    flex: 1,
    gap: 12,
    padding: '60px 24px',
  },
  emptyDot: {
    width: 8,
    height: 8,
    borderRadius: '50%',
    opacity: 0.6,
  },
  emptyText: {
    fontSize: 12,
    color: 'var(--text-muted)',
    textAlign: 'center',
    lineHeight: 1.6,
  },
  typingWrap: {
    display: 'flex',
    gap: 4,
    padding: '4px 20px',
    alignItems: 'center',
  },
  typingDot: {
    display: 'inline-block',
    width: 5,
    height: 5,
    borderRadius: '50%',
    background: 'var(--text-muted)',
    animation: 'pulse 1s ease-in-out infinite',
  },
  inputArea: {
    display: 'flex',
    alignItems: 'flex-end',
    gap: 8,
    padding: '10px 12px',
    borderTop: '1px solid var(--border)',
    flexShrink: 0,
  },
  voiceBtn: {
    fontSize: 11,
    fontFamily: 'var(--font-mono)',
    padding: '6px 8px',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--border)',
    flexShrink: 0,
    transition: 'color 0.15s',
  },
  textarea: {
    flex: 1,
    background: 'var(--bg-surface)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-md)',
    padding: '8px 12px',
    color: 'var(--text-primary)',
    resize: 'none',
    outline: 'none',
    fontSize: 13,
    lineHeight: 1.5,
    maxHeight: 120,
    overflowY: 'auto',
  },
  sendBtn: {
    padding: '7px 14px',
    borderRadius: 'var(--radius-md)',
    fontSize: 12,
    fontWeight: 600,
    flexShrink: 0,
    transition: 'background 0.15s, color 0.15s',
    fontFamily: 'var(--font-mono)',
  },
}
