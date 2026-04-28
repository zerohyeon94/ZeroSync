import type { Persona } from '../../../main/types'

interface Props {
  current: Persona
  onChange: (p: Persona) => void
}

const PERSONA_META = {
  alpha: {
    label: 'Alpha',
    mbti: 'INTJ',
    desc: '전략가 — 논리와 효율',
    color: 'var(--alpha-primary)',
    glow: 'var(--alpha-glow)',
    textColor: 'var(--alpha-text)',
  },
  beta: {
    label: 'Beta',
    mbti: 'ISFJ',
    desc: '수호자 — 일정과 감정',
    color: 'var(--beta-primary)',
    glow: 'var(--beta-glow)',
    textColor: 'var(--beta-text)',
  },
}

export default function PersonaSelector({ current, onChange }: Props) {
  return (
    <div style={styles.container}>
      {(['alpha', 'beta'] as Persona[]).map((p) => {
        const meta = PERSONA_META[p]
        const isActive = current === p
        return (
          <button
            key={p}
            style={{
              ...styles.tab,
              borderBottomColor: isActive ? meta.color : 'transparent',
              background: isActive ? meta.glow : 'transparent',
            }}
            onClick={() => onChange(p)}
          >
            <span
              style={{
                ...styles.label,
                color: isActive ? meta.color : 'var(--text-muted)',
                fontFamily: 'var(--font-mono)',
              }}
            >
              {meta.label}
            </span>
            <span
              style={{
                ...styles.mbti,
                color: isActive ? meta.textColor : 'var(--text-muted)',
              }}
            >
              {meta.mbti} · {meta.desc}
            </span>
          </button>
        )
      })}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    borderBottom: '1px solid var(--border)',
    flexShrink: 0,
  },
  tab: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'flex-start',
    padding: '10px 16px',
    borderBottom: '2px solid transparent',
    transition: 'all 0.15s',
    gap: 2,
  },
  label: {
    fontSize: 13,
    fontWeight: 600,
    letterSpacing: '0.05em',
  },
  mbti: {
    fontSize: 11,
    transition: 'color 0.15s',
  },
}
