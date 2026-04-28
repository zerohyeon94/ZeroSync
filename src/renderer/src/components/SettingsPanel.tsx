import { useState, useEffect } from 'react'

interface Props {
  onSave: () => void
}

export default function SettingsPanel({ onSave }: Props) {
  const [apiKey, setApiKey] = useState('')
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    window.zab.getApiKey().then((key) => {
      if (key) setApiKey(key)
    })
  }, [])

  async function handleSave() {
    if (!apiKey.trim()) return
    await window.zab.setApiKey(apiKey.trim())
    setSaved(true)
    setTimeout(() => {
      setSaved(false)
      onSave()
    }, 800)
  }

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <span style={styles.title}>API 설정</span>
        <span style={styles.subtitle}>Anthropic Claude API 키를 입력하세요</span>
      </div>

      <div style={styles.field}>
        <label style={styles.label}>Claude API Key</label>
        <input
          style={styles.input}
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder="sk-ant-..."
          onKeyDown={(e) => e.key === 'Enter' && handleSave()}
        />
        <span style={styles.hint}>
          console.anthropic.com에서 발급받을 수 있습니다
        </span>
      </div>

      <div style={styles.personaInfo}>
        <div style={styles.personaCard}>
          <span style={{ ...styles.personaName, color: 'var(--alpha-primary)', fontFamily: 'var(--font-mono)' }}>
            Alpha — INTJ
          </span>
          <span style={styles.personaDesc}>냉철한 전략가. 논리와 효율 중심의 기술 분석.</span>
        </div>
        <div style={styles.personaCard}>
          <span style={{ ...styles.personaName, color: 'var(--beta-primary)', fontFamily: 'var(--font-mono)' }}>
            Beta — ISFJ
          </span>
          <span style={styles.personaDesc}>따뜻한 수호자. 일정 관리와 감정적 서포트.</span>
        </div>
      </div>

      <button
        style={{
          ...styles.saveBtn,
          background: saved ? '#16a34a' : apiKey.trim() ? 'var(--text-primary)' : 'var(--bg-hover)',
          color: apiKey.trim() ? 'var(--bg-primary)' : 'var(--text-muted)',
        }}
        onClick={handleSave}
        disabled={!apiKey.trim()}
      >
        {saved ? '저장됨' : '저장하고 시작'}
      </button>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    flex: 1,
    padding: '24px 20px',
    gap: 24,
    overflowY: 'auto',
  },
  header: {
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
  },
  title: {
    fontSize: 16,
    fontWeight: 600,
    color: 'var(--text-primary)',
    fontFamily: 'var(--font-mono)',
  },
  subtitle: {
    fontSize: 12,
    color: 'var(--text-muted)',
  },
  field: {
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
  },
  label: {
    fontSize: 11,
    fontWeight: 600,
    color: 'var(--text-secondary)',
    fontFamily: 'var(--font-mono)',
    letterSpacing: '0.05em',
  },
  input: {
    background: 'var(--bg-surface)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-md)',
    padding: '10px 12px',
    color: 'var(--text-primary)',
    outline: 'none',
    fontSize: 13,
    fontFamily: 'var(--font-mono)',
    letterSpacing: '0.05em',
  },
  hint: {
    fontSize: 11,
    color: 'var(--text-muted)',
  },
  personaInfo: {
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
  },
  personaCard: {
    background: 'var(--bg-surface)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-md)',
    padding: '12px 14px',
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
  },
  personaName: {
    fontSize: 13,
    fontWeight: 600,
    letterSpacing: '0.05em',
  },
  personaDesc: {
    fontSize: 12,
    color: 'var(--text-muted)',
  },
  saveBtn: {
    padding: '12px',
    borderRadius: 'var(--radius-md)',
    fontSize: 13,
    fontWeight: 600,
    fontFamily: 'var(--font-mono)',
    transition: 'background 0.2s, color 0.2s',
    marginTop: 'auto',
  },
}
