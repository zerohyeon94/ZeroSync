import type { Message, Persona } from '../../../main/types'

interface Props {
  message: Message
  persona: Persona
}

const PERSONA_COLOR = {
  alpha: 'var(--alpha-primary)',
  beta: 'var(--beta-primary)',
}

const PERSONA_BG = {
  alpha: 'rgba(59, 130, 246, 0.08)',
  beta: 'rgba(245, 158, 11, 0.08)',
}

export default function MessageBubble({ message, persona }: Props) {
  const isUser = message.role === 'user'
  const color = PERSONA_COLOR[persona]
  const bg = PERSONA_BG[persona]

  if (isUser) {
    return (
      <div style={styles.userWrap}>
        <div style={styles.userBubble}>{message.content}</div>
      </div>
    )
  }

  return (
    <div style={styles.assistantWrap}>
      <div
        style={{
          ...styles.assistantLabel,
          color,
          fontFamily: 'var(--font-mono)',
        }}
      >
        {persona === 'alpha' ? 'Alpha' : 'Beta'}
      </div>
      <div style={{ ...styles.assistantBubble, background: bg, borderColor: color + '33' }}>
        <FormattedContent content={message.content} />
      </div>
    </div>
  )
}

function FormattedContent({ content }: { content: string }) {
  const parts = content.split(/(```[\s\S]*?```)/g)
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith('```')) {
          const lines = part.slice(3, -3).split('\n')
          const lang = lines[0].trim()
          const code = lines.slice(1).join('\n')
          return (
            <pre key={i} style={styles.codeBlock}>
              {lang && <span style={styles.codeLang}>{lang}</span>}
              <code>{code}</code>
            </pre>
          )
        }
        return (
          <p key={i} style={styles.text}>
            {part}
          </p>
        )
      })}
    </>
  )
}

const styles: Record<string, React.CSSProperties> = {
  userWrap: {
    display: 'flex',
    justifyContent: 'flex-end',
    padding: '4px 16px',
  },
  userBubble: {
    background: 'var(--bg-surface)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-md)',
    padding: '8px 12px',
    maxWidth: '75%',
    fontSize: 13,
    color: 'var(--text-primary)',
    lineHeight: 1.5,
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
  },
  assistantWrap: {
    display: 'flex',
    flexDirection: 'column',
    padding: '4px 16px',
    gap: 4,
  },
  assistantLabel: {
    fontSize: 11,
    fontWeight: 600,
    letterSpacing: '0.05em',
    paddingLeft: 2,
  },
  assistantBubble: {
    border: '1px solid',
    borderRadius: 'var(--radius-md)',
    padding: '10px 14px',
    fontSize: 13,
    lineHeight: 1.6,
    color: 'var(--text-primary)',
  },
  text: {
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
    marginBottom: 4,
  },
  codeBlock: {
    background: 'var(--bg-primary)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-sm)',
    padding: '10px 12px',
    fontSize: 12,
    fontFamily: 'var(--font-mono)',
    overflowX: 'auto',
    margin: '6px 0',
    whiteSpace: 'pre',
  },
  codeLang: {
    display: 'block',
    color: 'var(--text-muted)',
    fontSize: 10,
    marginBottom: 6,
    fontFamily: 'var(--font-mono)',
  },
}
