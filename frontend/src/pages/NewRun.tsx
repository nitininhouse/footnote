import { useEffect, useState } from 'react'
import { api, ago, type Config, type Row } from '../api'
import { go } from '../App'
import { Chip } from './bits'

const SAMPLES = [
  { name: 'Sendil Palani', company: 'Zipline', title: 'CFO', what: 'New CFO (ex-Tesla). The $1.5B round ran on 55 outlets, so it becomes context and the email opens on his first months and the Walmart expansion.' },
  { name: 'Kristin Schaefer', company: 'Whatnot', title: 'CFO', what: 'Sources disagree on the funding amount and a sensitive story is blocked; it opens on the new Dublin HQ.' },
  { name: 'Kristin Schaefer', company: 'Atomic', title: 'General Partner', what: 'Job change: she left Atomic in May 2026. The process stops and offers to follow her.' },
]

export default function NewRun({ cfg }: { cfg: Config | null }) {
  const [f, setF] = useState({ name: '', company: '', title: '', linkedin: '', notes: '' })
  const [mode, setMode] = useState<string>('')
  const [code, setCode] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [recent, setRecent] = useState<Row[]>([])
  useEffect(() => { api.runs().then(r => setRecent(r.slice(0, 6))).catch(() => {}) }, [])
  const m = mode || cfg?.default_mode || 'replay'

  async function start(v = f) {
    setErr(''); setBusy(true)
    try {
      const { id } = await api.create({ ...v, mode: m, access_code: code })
      go(`/run/${id}`)
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value })

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>New prospect</h1>
          <p className="sub">Name someone. Hookline researches them, picks one reason to write, drafts the email and checks every claim. You approve it.</p>
        </div>
      </div>
      <div className="newrun">
        <form className="panel panel-pad" onSubmit={e => { e.preventDefault(); start() }}>
          <div className="form-grid">
            <div className="field"><label>Full name</label><input className="input" value={f.name} onChange={set('name')} autoFocus autoComplete="off" /></div>
            <div className="field"><label>Company</label><input className="input" value={f.company} onChange={set('company')} autoComplete="off" /></div>
            <div className="field"><label>Title <span className="faint">optional</span></label><input className="input" value={f.title} onChange={set('title')} autoComplete="off" /></div>
            <div className="field"><label>LinkedIn profile link <span className="faint">optional</span></label><input className="input" value={f.linkedin} onChange={set('linkedin')} autoComplete="off" /><span className="hint">Use it when the name is common. It skips the name search.</span></div>
            <div className="field wide"><label>Your notes <span className="faint">optional</span></label><textarea className="textarea" value={f.notes} onChange={set('notes')} /><span className="hint">For your own context, like where you met. Never sent to the prospect.</span></div>
          </div>
          <div className="divider" />
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <div className="seg" role="group" aria-label="Data mode">
              <button type="button" className={m === 'replay' ? 'on' : ''} onClick={() => setMode('replay')}>Replay</button>
              <button type="button" className={m === 'live' ? 'on' : ''} onClick={() => setMode('live')} disabled={!cfg?.live_available}>Live</button>
            </div>
            <span className="muted" style={{ fontSize: 12.5, flex: 1 }}>
              {m === 'replay' ? 'Uses recorded Crustdata answers. Free and repeatable.' : `Fetches fresh data from Crustdata. Up to ${cfg?.run_cap ?? 6} credits per run.`}
            </span>
            {m === 'live' && cfg?.live_needs_code && <input className="input" style={{ width: 140 }} placeholder="Access code" value={code} onChange={e => setCode(e.target.value)} />}
            <button className="btn primary" disabled={busy || (!f.linkedin && (!f.name || !f.company))}>Research and draft</button>
          </div>
          {err && <div className="banner bad" style={{ marginTop: 12, marginBottom: 0 }}>{err}</div>}
        </form>

        <div style={{ display: 'grid', gap: 16 }}>
          <div className="panel panel-pad">
            <h3>Demo examples</h3>
            <p className="muted" style={{ fontSize: 12.5, margin: '0 0 8px' }}>Real people, recorded answers. Clicking one fills the form; nothing runs until you press the button.</p>
            {SAMPLES.map(s => (
              <button key={s.company} type="button" className="example" onClick={() => setF({ name: s.name, company: s.company, title: s.title, linkedin: '', notes: '' })}>
                <span><b>{s.name}</b>, {s.company}</span>
                <span className="what">{s.what}</span>
              </button>
            ))}
          </div>
          {recent.length > 0 && <div className="panel">
            <div style={{ padding: '12px 12px 4px' }}><h3>Recent runs</h3></div>
            <table className="tbl"><tbody>
              {recent.map(r => <tr key={r.id} className="click" onClick={() => go(`/run/${r.id}`)}>
                <td><b>{r.name}</b> <span className="muted">· {r.company}</span><div className="faint" style={{ fontSize: 12 }}>{ago(r.created)}</div></td>
                <td className="r"><Chip s={r.status} /></td>
              </tr>)}
            </tbody></table>
          </div>}
        </div>
      </div>
    </div>
  )
}


