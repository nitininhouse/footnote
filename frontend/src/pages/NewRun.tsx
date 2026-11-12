import { useState } from 'react'
import { api, type Config } from '../api'
import { go } from '../App'

const SAMPLES = [
  { name: 'Greg Edwards', company: 'Superdry', what: 'Normal case: a retailer opening its first store in Argentina.' },
  { name: 'Mac Kern', company: 'Zipline', what: 'Two people with this name work there. You pick the right one.' },
  { name: 'Kristin Schaefer', company: 'Postmates', what: 'She left the company. You choose to follow her, find who has the role now, or stop.' },
  { name: 'Jane Doe', company: 'Instacart', what: 'Already a Zamp customer. Stops before any lookup is paid for.' },
]

export default function NewRun(_: { cfg: Config | null }) {
  const [f, setF] = useState({ name: '', company: '', title: '', linkedin: '', notes: '' })
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

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
          <p className="sub">Name a prospect. Footnote reads their profile and company news, finds the one reason to write now, and drafts an email for you to review.</p>
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

        <div>
          <div className="panel panel-pad">
            <h2 style={{ marginBottom: 4 }}>Examples</h2>
            <p className="muted" style={{ fontSize: 13, margin: '0 0 8px' }}>Click one to fill the form. These are saved, so they cost no credits.</p>
            {SAMPLES.map(s => (
              <button key={s.name + s.company} type="button" className="example" onClick={() => setF({ name: s.name, company: s.company, title: '', linkedin: '', notes: '' })}>
                <span><b>{s.name}</b>, {s.company}</span>
                <span className="what">{s.what}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}


