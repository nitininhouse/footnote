import { useState } from 'react'
import { api, type Config } from '../api'
import { go } from '../App'

const SAMPLES = [
  { name: 'Greg Edwards', company: 'Superdry', what: 'normal case' },
  { name: 'Mac Kern', company: 'Zipline', what: 'two people, same name' },
  { name: 'Kristin Schaefer', company: 'Postmates', what: 'left the company' },
  { name: 'Jane Doe', company: 'Instacart', what: 'already a customer' },
]

// A real Footnote draft (Greg Edwards, Superdry, Oct 2026) with the sources it cited.
const NOTES = [
  { n: 1, src: 'Retail Gazette · Financial Times', d: '23 Oct 2026', what: 'Superdry opens first Argentina store' },
  { n: 2, src: 'zamp.ai customer results', d: '', what: 'Mindbody: 95%+ of invoices end to end' },
]

function Specimen() {
  const [on, setOn] = useState(0)
  const f = (n: number, text: string) => (
    <span className={`fact${on === n ? ' on' : ''}`} onMouseEnter={() => setOn(n)} onMouseLeave={() => setOn(0)}>{text}<sup>[{n}]</sup></span>
  )
  return (
    <aside className="specimen">
      <p className="eyebrow">What you get back · a real draft</p>
      <div className="paper">
        <div className="bar"><span>Draft</span><b>● Ready for review</b></div>
        <div className="meta">
          <span className="k">To</span><span>Greg Edwards, Interim CFO, Superdry</span>
          <span className="k">Subject</span><span>argentina store</span>
        </div>
        <div className="body">
          <p>Hi Greg,</p>
          <p>{f(1, 'Superdry opened its first store in Argentina.')} Expanding into a new country usually brings a wave of new local suppliers and bills in different formats. Who is keying all those invoices in today?</p>
          <p>{f(2, 'Mindbody processes 95%+ of invoices end to end with Zamp.')}</p>
          <p style={{ margin: 0 }}>Worth a look?</p>
        </div>
        <div className="notes">
          {NOTES.map(x => (
            <div key={x.n} className={`note${on === x.n ? ' on' : ''}`} onMouseEnter={() => setOn(x.n)} onMouseLeave={() => setOn(0)}>
              <b>[{x.n}]</b><span>{x.what} <span className="faint">· {x.src}</span></span><span className="d">{x.d}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="pipeline">
        <div><b>Crustdata</b>profile, company, news, jobs</div>
        <div><b>Gemini</b>picks one hook, writes</div>
        <div><b>Code</b>checks every citation</div>
        <div><b>You</b>approve, edit, reject</div>
      </div>
    </aside>
  )
}

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
          <p className="eyebrow">Prospect research · Crustdata + Gemini</p>
          <h1>Cold emails where every<br />sentence has a source.</h1>
          <p className="sub">Name a prospect. Footnote reads their profile and company news, picks the one reason to write now, and drafts a short email for you to review.</p>
        </div>
      </div>
      <div className="newrun">
        <form className="panel" onSubmit={e => { e.preventDefault(); start() }}>
          <div className="step">
            <div className="step-head"><span className="n">01</span><span className="t">Who</span></div>
            <div className="form-grid">
              <div className="field"><label>Full name</label><input className="input" value={f.name} onChange={set('name')} placeholder="e.g. Greg Edwards" autoFocus autoComplete="off" /></div>
              <div className="field"><label>Company</label><input className="input" value={f.company} onChange={set('company')} placeholder="e.g. Superdry" autoComplete="off" /></div>
            </div>
            <div className="examples">
              {SAMPLES.map(s => (
                <button key={s.name + s.company} type="button" className="example" title={s.what} onClick={() => setF({ name: s.name, company: s.company, title: '', linkedin: '', notes: '' })}>
                  <b>{s.name}</b><span className="what">{s.company}</span>
                </button>
              ))}
            </div>
          </div>
          <div className="step">
            <div className="step-head"><span className="n">02</span><span className="t">Help it find the right person</span><span className="hint" style={{ marginLeft: 'auto' }}>optional</span></div>
            <div className="form-grid">
              <div className="field"><label>Title</label><input className="input" value={f.title} onChange={set('title')} placeholder="e.g. CFO" autoComplete="off" /></div>
              <div className="field"><label>LinkedIn profile</label><input className="input" value={f.linkedin} onChange={set('linkedin')} placeholder="linkedin.com/in/…" autoComplete="off" /><span className="hint">Use it when the name is common. It skips the name search.</span></div>
              <div className="field wide"><label>Notes</label><textarea className="textarea" value={f.notes} onChange={set('notes')} placeholder="Where you met, what you talked about" /><span className="hint">For your own context. Never sent to the prospect.</span></div>
            </div>
          </div>
          <div className="form-foot">
            <span />
            <button className="btn primary lg" disabled={busy || (!f.linkedin && (!f.name || !f.company))}>{busy ? 'Starting…' : 'Research and draft'}</button>
          </div>
          {err && <div className="banner bad" style={{ margin: '0 20px 16px' }}>{err}</div>}
        </form>
        <Specimen />
      </div>
    </div>
  )
}
