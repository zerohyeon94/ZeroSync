import { useState, useEffect } from 'react'
import ChatWindow from './components/ChatWindow'
import PersonaSelector from './components/PersonaSelector'
import SettingsPanel from './components/SettingsPanel'
import type { Persona } from '../../main/types'

type View = 'chat' | 'settings'

export default function App() {
  const [persona, setPersona] = useState<Persona>('alpha')
  const [view, setView] = useState<View>('chat')
  const [hasApiKey, setHasApiKey] = useState(false)

  useEffect(() => {
    window.zab.getApiKey().then((key) => {
      if (key) setHasApiKey(true)
      else setView('settings')
    })
  }, [])

  return (
    <div style={styles.root}>
      <div style={styles.titleBar}>
        <span style={styles.appName}>Z.A.B</span>
        <div style={styles.titleActions}>
          <button
            style={{
              ...styles.iconBtn,
              color: view === 'settings' ? 'var(--text-primary)' : 'var(--text-muted)',
            }}
            onClick={() => setView(view === 'settings' ? 'chat' : 'settings')}
            title="설정"
          >
            {view === 'settings' ? '← 돌아가기' : '설정'}
          </button>
        </div>
      </div>

      {view === 'settings' ? (
        <SettingsPanel
          onSave={() => {
            setHasApiKey(true)
            setView('chat')
          }}
        />
      ) : (
        <>
          <PersonaSelector current={persona} onChange={setPersona} />
          <ChatWindow persona={persona} />
        </>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  root: {
    display: 'flex',
    flexDirection: 'column',
    height: '100vh',
    background: 'var(--bg-primary)',
    overflow: 'hidden',
  },
  titleBar: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '12px 16px 8px',
    borderBottom: '1px solid var(--border)',
    WebkitAppRegion: 'drag' as unknown as undefined,
    flexShrink: 0,
  },
  appName: {
    fontFamily: 'var(--font-mono)',
    fontSize: 13,
    fontWeight: 600,
    letterSpacing: '0.1em',
    color: 'var(--text-primary)',
  },
  titleActions: {
    WebkitAppRegion: 'no-drag' as unknown as undefined,
  },
  iconBtn: {
    fontSize: 12,
    color: 'var(--text-muted)',
    padding: '2px 8px',
    borderRadius: 'var(--radius-sm)',
    transition: 'color 0.15s',
    fontFamily: 'var(--font-mono)',
  },
}
