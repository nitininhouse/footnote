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
          <span className="brand-mark"><svg width="10" height="10" viewBox="0 0 16 16"><path d="M3 2v12M3 8h6a4 4 0 0 0 0-8" stroke="#FAF9F7" strokeWidth="2.2" fill="none" /></svg></span>
          Hookline
        </div>
        <a className={on('/')} href="#/">New prospect</a>
        <a className={on('/runs/review')} href="#/runs/review">Review queue <span className="count">{queue || ''}</span></a>
        <a className={on('/runs')} href="#/runs">All runs</a>
        <div className="side-foot">
          <span>Selling for <b>{cfg?.seller ?? 'Zamp'}</b></span>
          {cfg && <span className="mono">{cfg.spent_today.toFixed(2)} / {cfg.daily_cap} credits today</span>}
          <span>Nothing is sent from here.</span>
        </div>
      </aside>
      <main className="main">{page}</main>
    </div>
  )
}
