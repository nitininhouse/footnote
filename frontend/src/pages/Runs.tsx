import { useEffect, useState } from 'react'
import { api, ago, EDGE, secs, type Row, type Stats } from '../api'
import { go } from '../App'
import { Chip, initials } from './bits'

const TABS: [string, string, (r: Row) => boolean][] = [
  ['all', 'All', () => true],
  ['review', 'Needs review', r => ['ready', 'ready_with_warnings', 'needs_input'].includes(r.status)],
  ['approved', 'Approved', r => r.status === 'approved'],
  ['rejected', 'Rejected', r => r.status === 'rejected'],
  ['stopped', 'Stopped or failed', r => ['failed', 'blocked', 'not_found', 'stopped', 'needs_review', 'low_signal'].includes(r.status)],
]
const pct = (v: number | null) => v == null ? '—' : `${Math.round(v * 100)}%`

export default function Runs({ initialTab }: { initialTab: string }) {
  const [rows, setRows] = useState<Row[] | null>(null)
  const [stats, setStats] = useState<Stats | null>(null)
  const [tab, setTab] = useState(initialTab)
  const [q, setQ] = useState('')
  useEffect(() => {
    const load = () => { api.runs().then(setRows).catch(() => {}); api.stats().then(setStats).catch(() => {}) }
    load()
    const t = setInterval(load, 4000)
    return () => clearInterval(t)
  }, [])
  const f = TABS.find(t => t[0] === tab)![2]
  const shown = (rows || []).filter(f).filter(r => !q || `${r.name} ${r.company} ${r.hook}`.toLowerCase().includes(q.toLowerCase()))

  return (
    <div className="page">
      <div className="page-head">
        <div><h1>{tab === 'review' ? 'Review queue' : 'All prospects'}</h1><p className="sub">Everyone you've researched and where each draft stands.</p></div>
        <button className="btn primary" onClick={() => go('/')}>New prospect</button>
      </div>
      {stats && <div className="stats">
        <div className="stat"><div className="l">Prospects researched</div><div className="v">{stats.runs}</div></div>
        <div className="stat"><div className="l">Waiting on you</div><div className="v">{stats.awaiting}</div></div>
        <div className="stat"><div className="l">Approval rate</div><div className="v">{pct(stats.approval_rate)}</div></div>
        <div className="stat"><div className="l">Sentences with a source</div><div className="v">{pct(stats.claim_pass)}</div></div>
        <div className="stat"><div className="l">Median time to draft</div><div className="v">{stats.median_ms ? secs(stats.median_ms) : '—'}</div></div>
      </div>}
      <div className="toolbar">
      <div className="tabs">
        {TABS.map(([k, l, fn]) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{l}<span className="c">{(rows || []).filter(fn).length}</span></button>)}
      </div>
        <input className="input" style={{ maxWidth: 260 }} aria-label="Search" placeholder="Search" value={q} onChange={e => setQ(e.target.value)} />
      </div>
      <div className="panel">
        {rows && shown.length === 0 ? <div className="empty">{rows.length === 0 ? <>No runs yet. <a href="#/">Research your first prospect</a>.</> : 'Nothing here.'}</div> :
          <table className="tbl">
            <thead><tr><th>Prospect</th><th>Reason to write</th><th>Flags</th><th>Status</th><th className="r">Sourced</th><th className="r">Time</th><th className="r">Created</th></tr></thead>
            <tbody>{shown.map(r => <tr key={r.id} className="click" onClick={() => go(`/run/${r.id}`)}>
              <td><div className="cell-person"><span className="avatar">{initials(r.name)}</span><div><div style={{ fontWeight: 500 }}>{r.name?.replace(/,?\s+(CPA|CIA|CISA)\b,?/g, '')}</div><div className="muted" style={{ fontSize: 12.5 }}>{r.title}{r.company ? `, ${r.company}` : ''}</div></div></div></td>
              <td style={{ maxWidth: 280 }}>{r.hook ? <span className="clamp2" title={r.hook}>{r.hook}</span> : <span className="faint">—</span>}</td>
              <td><div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', maxWidth: 220 }}>{r.edge.filter(e => e !== 'off_topic').map(e => <span key={e} className="tag">{EDGE[e] || e}</span>)}</div></td>
              <td><Chip s={r.status} /></td>
              <td className="r mono">{r.claims ? `${r.claims_ok}/${r.claims}` : '—'}</td>
              <td className="r mono">{secs(r.ms)}</td>
              <td className="r muted">{ago(r.created)}</td>
            </tr>)}</tbody>
          </table>}
      </div>
    </div>
  )
}
