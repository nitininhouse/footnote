import { useEffect, useState } from 'react'
import { api, type Config } from './api'
import NewRun from './pages/NewRun'
import RunPage from './pages/RunPage'
import Runs from './pages/Runs'

function useHash() {
  const [h, setH] = useState(location.hash.slice(1) || '/')
  useEffect(() => {
    const f = () => { setH(location.hash.slice(1) || '/'); window.scrollTo(0, 0) }
    addEventListener('hashchange', f)
    return () => removeEventListener('hashchange', f)
  }, [])
  return h
}

export const go = (p: string) => { location.hash = p }

function Ico({ d }: { d: string }) {
  return <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d={d} /></svg>
}

export default function App() {
  const path = useHash()
  const [cfg, setCfg] = useState<Config | null>(null)
  const [queue, setQueue] = useState(0)
  useEffect(() => {
    api.config().then(setCfg).catch(() => {})
    const tick = () => api.runs().then(rs => setQueue(rs.filter(r => ['ready', 'ready_with_warnings', 'needs_input'].includes(r.status)).length)).catch(() => {})
    tick()
    const t = setInterval(tick, 5000)
    return () => clearInterval(t)
  }, [path])

  const runId = path.startsWith('/run/') ? path.slice(5) : null
  const page = runId ? <RunPage key={runId} id={runId} />
    : path.startsWith('/runs') ? <Runs key={path} initialTab={path.includes('review') ? 'review' : 'all'} />
    : <NewRun cfg={cfg} />
  const on = (p: string) => path === p ? 'nav on' : 'nav'

  return (
    <div className="shell">
      <aside className="side">
        <div className="brand">
          <span className="brand-mark"><svg width="12" height="12" viewBox="0 0 16 16"><path d="M4 14V2h8M4 8h6" stroke="#fff" strokeWidth="2.2" fill="none" /></svg></span>
          <div><div className="brand-name">Footnote</div><div className="brand-sub">Zamp outbound</div></div>
        </div>
        <a className={on('/')} href="#/"><Ico d="M8 3v10M3 8h10" />New prospect</a>
        <div className="nav-label">Drafts</div>
        <a className={on('/runs/review')} href="#/runs/review"><Ico d="M2.5 4.5h11v7h-11zM2.5 4.5l5.5 4 5.5-4" />Review queue {queue > 0 && <span className="count">{queue}</span>}</a>
        <a className={on('/runs')} href="#/runs"><Ico d="M3 4h10M3 8h10M3 12h10" />All prospects</a>
        <div className="side-foot">
          <span className="avatar">NG</span>
          <div style={{ lineHeight: 1.3 }}><div style={{ fontWeight: 500, fontSize: 13.5 }}>Nitin Gupta</div><div className="muted" style={{ fontSize: 12 }}>Sales development</div></div>
        </div>
      </aside>
      <main className="main">{page}</main>
    </div>
  )
}
