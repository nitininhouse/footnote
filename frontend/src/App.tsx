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
      <header className="top">
        <a className="brand" href="#/"><span className="brand-name">Footnote</span><sup className="brand-mark">1</sup></a>
        <nav className="top-nav">
          <a className={on('/runs/review')} href="#/runs/review">Review queue{queue > 0 && <span className="count">{queue}</span>}</a>
          <a className={on('/runs')} href="#/runs">All prospects</a>
        </nav>
        <div className="top-right">
          <span className="who"><span className="avatar">NG</span>Nitin Gupta</span>
          <a className="btn primary pill" href="#/">New prospect</a>
        </div>
      </header>
      <main className="main">{page}</main>
    </div>
  )
}
