import { useEffect, useState } from 'react'
import { api, ago, type Config, type Row } from '../api'
import { go } from '../App'
import { Chip, initials } from './bits'

const SAMPLES = [
  { name: 'Sendil Palani', company: 'Zipline', title: 'CFO', what: 'New CFO (ex-Tesla). The $1.5B round ran on 55 outlets, so it becomes context and the email opens on his first months and the Walmart expansion.' },
  { name: 'Kristin Schaefer', company: 'Whatnot', title: 'CFO', what: 'Sources disagree on the funding amount and a sensitive story is blocked; it opens on the new Dublin HQ.' },
  { name: 'Kristin Schaefer', company: 'Atomic', title: 'General Partner', what: 'Job change: she left Atomic in May 2026. The process stops and offers to follow her.' },
]

export default function NewRun(_: { cfg: Config | null }) {
  const [f, setF] = useState({ name: '', company: '', title: '', linkedin: '', notes: '' })
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [recent, setRecent] = useState<Row[]>([])
  useEffect(() => { api.runs().then(r => setRecent(r.slice(0, 6))).catch(() => {}) }, [])

  async function start(v = f) {
    setErr(''); setBusy(true)
    try {
      const { id } = await api.create({ ...v })
      go(`/run/${id}`)
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value })

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>New prospect</h1>
          <p className="sub">Name a prospect. Hookline reads their profile and company news, finds the one reason to write now, and drafts an email for you to review.</p>
        </div>
      </div>
      <div className="newrun">
        <form className="panel panel-pad" onSubmit={e => { e.preventDefault(); start() }}>
          <div className="form-grid">
            <div className="field"><label>Full name</label><input className="input" value={f.name} onChange={set('name')} autoFocus autoComplete="off" /></div>
            <div className="field"><label>Company</label><input className="input" value={f.company} onChange={set('company')} autoComplete="off" /></div>
            <div className="field"><label>Title <span className="optl">optional</span></label><input className="input" value={f.title} onChange={set('title')} autoComplete="off" /></div>
            <div className="field"><label>LinkedIn profile <span className="optl">optional</span></label><input className="input" value={f.linkedin} onChange={set('linkedin')} autoComplete="off" /><span className="hint">Use it when the name is common. It skips the name search.</span></div>
            <div className="field wide"><label>Notes <span className="optl">optional</span></label><textarea className="textarea" value={f.notes} onChange={set('notes')} /><span className="hint">For your own context, like where you met. Never sent to the prospect.</span></div>
          </div>
          <div className="divider" />
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, justifyContent: 'space-between', flexWrap: 'wrap' }}>
            <span className="muted" style={{ fontSize: 13 }}>Takes about a minute. You review the draft before anything goes out.</span>
            <button className="btn primary" disabled={busy || (!f.linkedin && (!f.name || !f.company))}>Research and draft</button>
          </div>
          {err && <div className="banner bad" style={{ marginTop: 12, marginBottom: 0 }}>{err}</div>}
        </form>

        <div style={{ display: 'grid', gap: 16 }}>
          <div className="panel panel-pad">
            <h2 style={{ marginBottom: 4 }}>Examples</h2>
            <p className="muted" style={{ fontSize: 13, margin: '0 0 8px' }}>Click one to fill the form.</p>
            {SAMPLES.map(s => (
              <button key={s.company} type="button" className="example" onClick={() => setF({ name: s.name, company: s.company, title: s.title, linkedin: '', notes: '' })}>
                <span><b>{s.name}</b>, {s.company}</span>
                <span className="what">{s.what}</span>
              </button>
            ))}
          </div>
          {recent.length > 0 && <div className="panel">
            <div className="panel-head" style={{ paddingBottom: 10 }}><h2 style={{ margin: 0 }}>Recent</h2><a href="#/runs" style={{ fontSize: 13 }}>View all</a></div>
            {recent.map(r => <div key={r.id} className="recent-row" onClick={() => go(`/run/${r.id}`)}>
              <span className="avatar">{initials(r.name)}</span>
              <div style={{ flex: 1, minWidth: 0 }}><div style={{ fontWeight: 500 }}>{r.name?.replace(/,?\s+(CPA|CIA|CISA)\b,?/g, '')}</div><div className="muted" style={{ fontSize: 12.5 }}>{r.company} · {ago(r.created)}</div></div>
              <Chip s={r.status} />
            </div>)}
          </div>}
        </div>
      </div>
    </div>
  )
}


