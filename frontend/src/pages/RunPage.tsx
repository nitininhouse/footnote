import { useEffect, useMemo, useRef, useState } from 'react'
import { api, EDGE, secs, type Claim, type Run, type Signal } from '../api'
import { Chip, Icon, host } from './bits'

const ALL_STAGES = [
  ['intake', 'Check the request'], ['company', 'Find the company'], ['person', 'Confirm the person'],
  ['profile', 'Read their profile'], ['company_data', 'Read company data'], ['roles', 'Scan open roles'],
  ['signals', 'Number every fact'], ['hook', 'Agent: choose the hook and write'], ['factcheck', 'Check the citations'],
]
const DONE = ['ready', 'ready_with_warnings', 'approved', 'rejected']

function useRun(id: string) {
  const [run, setRun] = useState<Run | null>(null)
  const [gone, setGone] = useState(false)
  const [conn, setConn] = useState(0)   // bump to reconnect after the rep answers a question
  useEffect(() => {
    let es: EventSource | null = null
    let stop = false
    const open = () => {
      es = new EventSource(`/api/runs/${id}/stream`)
      es.onmessage = e => setRun(JSON.parse(e.data))
      es.addEventListener('gone', () => setGone(true))
      es.onerror = () => { es?.close(); if (!stop) setTimeout(() => api.run(id).then(r => { setRun(r); if (r.status === 'running') open() }).catch(() => setGone(true)), 1200) }
    }
    open()
    return () => { stop = true; es?.close() }
  }, [id, conn])
  return { run, setRun, gone, reconnect: () => setConn(c => c + 1) }
}

function Timer({ run }: { run: Run }) {
  const [, tick] = useState(0)
  useEffect(() => { if (run.status !== 'running') return; const t = setInterval(() => tick(x => x + 1), 200); return () => clearInterval(t) }, [run.status])
  const ms = run.status === 'running' ? Date.now() - new Date(run.stages[0]?.started ?? run.created).getTime()
    : run.stages.reduce((a, s) => a + (s.ms || 0), 0)
  return <span className="mono">{(Math.max(0, ms) / 1000).toFixed(1)} s</span>
}

export default function RunPage({ id }: { id: string }) {
  const { run, setRun, gone, reconnect } = useRun(id)
  const [sel, setSel] = useState<string | null>(null)
  if (gone) return <div className="page"><div className="empty">This run doesn't exist. <a href="#/runs">See all runs</a></div></div>
  if (!run) return <div className="page"><div className="empty">Loading…</div></div>

  const byKey = Object.fromEntries(run.stages.map(s => [s.key, s]))
  const active = run.stages[run.stages.length - 1]?.key
  const finished = DONE.includes(run.status) && run.draft
  const view = sel ?? (finished ? 'review' : active)
  const p = run.person

  return (
    <div className="page">
      <div className="run-head">
        <div>
          <div className="who">{p?.name || run.input.name || 'Prospect'}</div>
          <div className="run-meta">
            <span>{p?.title || run.input.title}{(run.company?.name || run.input.company) && <> at <b style={{ color: 'var(--ink)' }}>{run.company?.name || run.input.company}</b></>}</span>
            {p?.tenure_days != null && <span>{p.tenure_days} days in role</span>}
            {p?.url && <a href={p.url} target="_blank" rel="noreferrer">LinkedIn ↗</a>}
          </div>
        </div>
        <div className="run-meta">
          <Chip s={run.status} />
          <span className={`tag ${run.mode === 'live' ? 'warn' : ''}`}>{run.mode}</span>
          <Timer run={run} />
          <span className="mono" title="Crustdata credits spent by this run">{run.credits.toFixed(2)} cr</span>
        </div>
      </div>
      {run.note && <div className="banner ok">{run.note}</div>}

      {view === 'review' && run.draft ? <>
        <div className="processbar">
          <span className="steps">{ALL_STAGES.map(([k, t]) => <span key={k} title={`${t}: ${byKey[k]?.summary || ''}`}><Icon status={byKey[k]?.status ?? 'pending'} /></span>)}</span>
          <span className="muted">{run.stages.filter(s => s.status === 'done').length} of {ALL_STAGES.length} steps · {run.signals.length} signals · {run.checks.filter(c => c.status !== 'pass').length} checks fired</span>
          <button className="btn sm" style={{ marginLeft: 'auto' }} onClick={() => setSel(active ?? 'intake')}>View the process</button>
        </div>
        <Review run={run} setRun={setRun} />
      </> :
      <div className="run-grid">
        <div className="panel stages">
          {ALL_STAGES.map(([k, t]) => {
            const s = byKey[k]
            const st = s?.status ?? 'pending'
            return (
              <button key={k} className={`stage ${st} ${view === k ? 'sel' : ''}`} onClick={() => s && setSel(k)} disabled={!s}>
                <span className="ic"><Icon status={st} /></span>
                <span className="t">{t}</span>
                <span className="ms">{s?.ms != null ? secs(s.ms) : ''}</span>
                {s?.summary && <span className="s">{s.summary}</span>}
              </button>
            )
          })}
          {finished && <div style={{ padding: '8px 14px 6px', borderTop: '1px solid var(--line)', marginTop: 6 }}>
            <button className="btn sm primary" onClick={() => setSel('review')}>Open the draft</button>
          </div>}
        </div>
        <div>
          {run.question && run.status === 'needs_input' && <Ask run={run} onAnswered={reconnect} />}
          {run.error && <div className="banner bad"><b>Stopped:</b> {run.error.msg}</div>}
          <StageDetail run={run} k={view} />
        </div>
      </div>}
    </div>
  )
}

/* ------------------------------------------------------------------ question */
function Ask({ run, onAnswered }: { run: Run; onAnswered: () => void }) {
  const q = run.question!
  const [val, setVal] = useState('')
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')
  const choose = async (o: string) => {
    setBusy(o); setErr('')
    try { await api.answer(run.id, o, val); onAnswered() }
    catch (e) { setErr((e as Error).message); onAnswered() }   // either way, show the run's real state
    finally { setBusy('') }
  }
  return (
    <div className="ask">
      <p>{q.text}</p>
      <div className="opts">
        {q.options.map(o => o.input
          ? <div key={o.id} className="opt" style={{ cursor: 'default' }}>
              <input className="input" placeholder="https://www.linkedin.com/in/…" value={val} onChange={e => setVal(e.target.value)} />
              <button className="btn primary" disabled={!val || !!busy} onClick={() => choose(o.id)}>{o.label}</button>
            </div>
          : <button key={o.id} className="opt" disabled={!!busy} onClick={() => choose(o.id)}>
              <span>{o.label}{o.detail && <small>{o.detail}</small>}{o.url && <small><a href={o.url} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}>{o.url.replace('https://www.', '')}</a></small>}</span>
              <span className="muted">{busy === o.id ? 'Working…' : '→'}</span>
            </button>)}
      </div>
      {err && <div className="banner bad" style={{ marginTop: 10, marginBottom: 0 }}>{err}</div>}
    </div>
  )
}

/* ------------------------------------------------------------------ stage detail */
function StageDetail({ run, k }: { run: Run; k: string | undefined }) {
  const s = run.stages.find(x => x.key === k)
  if (!s) return <div className="panel empty">Waiting to start…</div>
  return (
    <div style={{ display: 'grid', gap: 16 }}>
      {k === 'company' && run.company_candidates && run.company_candidates.length > 0 && <div className="panel">
        <div className="panel-pad" style={{ paddingBottom: 4 }}><h2>Companies with this name</h2></div>
        <table className="tbl"><thead><tr><th>Name</th><th>Domain</th><th>Size</th><th /></tr></thead><tbody>
          {run.company_candidates.map(c => <tr key={c.id} className={run.company?.id === c.id ? 'chosen' : ''}>
            <td>{c.name}</td><td className="mono">{c.domain || '—'}</td><td>{c.size || '—'}</td>
            <td className="r">{run.company?.id === c.id && <span className="chip accent">Their employer</span>}</td></tr>)}
        </tbody></table>
      </div>}
      {k === 'profile' && run.person && <div className="panel panel-pad">
        <h2>{run.person.name}</h2>
        <dl className="kv">
          <dt>Now</dt><dd>{run.person.title} at {run.company?.name}, since {run.person.start?.slice(0, 7)}</dd>
          <dt>Headline</dt><dd>{run.person.headline}</dd>
          <dt>Location</dt><dd>{run.person.location || '—'}</dd>
          <dt>Before</dt><dd>{run.person.past.slice(0, 4).map((j, i) => <div key={i}>{j.title} at {j.company} <span className="faint mono">{j.start?.slice(0, 4)}–{j.end?.slice(0, 4)}</span></div>)}</dd>
        </dl>
      </div>}
      {(k === 'signals' || k === 'hook') && run.signals.length > 0 && <Signals run={run} />}
      {k === 'guards' && run.checks.length > 0 && <Checks run={run} />}
      <div className="panel panel-pad">
        <h3>{s.title} · log</h3>
        <div className="log">
          {s.log.length === 0 && <div className="faint">{s.status === 'running' ? 'Working…' : 'Nothing logged.'}</div>}
          {s.log.map((l, i) => <div className="row" key={i}><span className="tt">{l.t.toFixed(1)}s</span><span className={l.level === 'warn' ? 'warn' : ''}>{l.msg}</span></div>)}
        </div>
      </div>
    </div>
  )
}

function Checks({ run }: { run: Run }) {
  const order = { block: 0, warn: 1, pass: 2 }
  const cs = [...run.checks].sort((a, b) => order[a.status] - order[b.status])
  return <div className="panel panel-pad">
    <h2>Safety checks</h2>
    {cs.map((c, i) => <div className="check" key={i}>
      <span><span className={`tag ${c.status === 'block' ? 'bad' : c.status === 'warn' ? 'warn' : 'ok'}`}>{EDGE[c.kind] || c.kind}</span></span>
      <span>{c.title}{c.detail && <div className="d">{c.detail}</div>}</span>
    </div>)}
  </div>
}

function Signals({ run }: { run: Run }) {
  const [showOff, setShowOff] = useState(false)
  const sig = run.signals.filter(s => showOff || !s.flags.includes('off_topic'))
    const hookIds = run.hook?.ids ?? (run.hook?.id ? [run.hook.id] : [])
  const sorted = [...sig].sort((a, b) => (hookIds.includes(b.id) ? 9 : b.fit ?? -1) - (hookIds.includes(a.id) ? 9 : a.fit ?? -1))
  const off = run.signals.filter(s => s.flags.includes('off_topic')).length
  return <div className="panel">
    <div className="panel-pad" style={{ paddingBottom: 4, display: 'flex', justifyContent: 'space-between' }}>
      <h2>Signals, as the strategist judged them</h2>
      {off > 0 && <button className="btn sm" onClick={() => setShowOff(!showOff)}>{showOff ? 'Hide' : 'Show'} {off} off-topic</button>}
    </div>
    <table className="tbl"><thead><tr><th>Signal</th><th>Date</th><th className="r">Outlets</th><th className="r">Fit</th></tr></thead><tbody>
      {sorted.map(s => {
        const chosen = hookIds.includes(s.id)
        return <tr key={s.id} className={chosen ? 'chosen' : s.eligible === false ? 'out' : ''}>
          <td>
            <div>{s.label || s.text}</div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 3 }}>
              <span className="tag">{(s.event_type || s.kind).replace('_', ' ')}</span>
              {s.flags.filter(f => f !== 'off_topic').map(f => <span key={f} className={`tag ${['sensitive', 'competitor'].includes(f) ? 'bad' : 'warn'}`}>{f}</span>)}
              {chosen && <span className="tag ok">chosen hook</span>}
              {!chosen && s.use && s.use !== 'skip' && <span className="tag">{s.use}</span>}
              {s.reason && <span className="faint" style={{ fontSize: 12 }}>{s.reason}</span>}
              {s.judge2 && <span className="faint" style={{ fontSize: 12 }}>· bad news? {s.judge1?.model.split('-')[0]}: {s.judge1?.sensitive ? 'yes' : 'no'}, {s.judge2.model.split('-')[0]}: {s.judge2.sensitive ? 'yes' : 'no'}</span>}
            </div>
          </td>
          <td className="mono" style={{ whiteSpace: 'nowrap' }}>{s.date?.slice(0, 10) || '—'}</td>
          <td className="r mono">{s.kind === 'news' ? s.coverage : ''}</td>
          <td className="r mono">{s.fit != null ? `${s.fit}/5` : '—'}</td>
        </tr>
      })}
    </tbody></table>
  </div>
}

/* ------------------------------------------------------------------ review */
type Cited = { n: number; sig?: Signal; proof?: number }

function Review({ run, setRun }: { run: Run; setRun: (r: Run) => void }) {
  const dr = run.draft!
  const sigs = useMemo(() => Object.fromEntries(run.signals.map(s => [s.id, s])), [run.signals])
  const [edit, setEdit] = useState(false)
  const [subj, setSubj] = useState(dr.subject)
  const [body, setBody] = useState(dr.body)
  const [hl, setHl] = useState<number | null>(null)
  const [reason, setReason] = useState('')
  const [rejecting, setRejecting] = useState(false)
  const [err, setErr] = useState('')
  const [copied, setCopied] = useState(false)
  const done = run.status === 'approved' || run.status === 'rejected'
  const ta = useRef<HTMLTextAreaElement>(null)
  useEffect(() => { setSubj(dr.subject); setBody(dr.body) }, [dr.subject, dr.body])

  // number the sources in order of first citation
  const cites: Cited[] = []
  const claimNums: number[][] = dr.claims.map(c => {
    const ns: number[] = []
    for (const f of c.facts || []) {
      let x = cites.find(y => y.sig?.id === f)
      if (!x && sigs[f]) { x = { n: cites.length + 1, sig: sigs[f] }; cites.push(x) }
      if (x) ns.push(x.n)
    }
    for (const pi of c.proof || []) {
      let x = cites.find(y => y.proof === pi)
      if (!x) { x = { n: cites.length + 1, proof: pi }; cites.push(x) }
      ns.push(x.n)
    }
    return ns
  })

  async function act(action: string, extra: Record<string, unknown> = {}) {
    setErr('')
    try {
      const r = await api.review(run.id, { action, subject: subj, body, reason, ...extra })
      setRun(r); setEdit(false); setRejecting(false)
    } catch (e) { setErr((e as Error).message) }
  }
  useEffect(() => {
    if (done) return
    const k = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).tagName.match(/INPUT|TEXTAREA/)) { if (e.key === 'Escape') setEdit(false); return }
      if (e.metaKey || e.ctrlKey) return
      if (e.key === 'a' && !dr.approve_blocked) act('approve')
      if (e.key === 'e') { setEdit(true); setTimeout(() => ta.current?.focus(), 0) }
      if (e.key === 'r') setRejecting(true)
    }
    addEventListener('keydown', k)
    return () => removeEventListener('keydown', k)
  })

  const hookIds = run.hook?.ids ?? (run.hook?.id ? [run.hook.id] : [])
  const hooks = hookIds.map(i => sigs[i]).filter(Boolean)
  const notChosen = ((run.hook as { not_chosen?: string[] } | null)?.not_chosen ?? []).map(i => sigs[i]).filter(Boolean)
  const verdictTone = (c: Claim) => c.removed ? '' : c.verdict || 'unsupported'

  return (
    <div className="review">
      {/* sources */}
      <div className="panel">
        <div className="panel-pad" style={{ paddingBottom: 6 }}><h2>Sources</h2></div>
        <div className="src-list">
          {cites.map(c => {
            const on = hl != null && claimNums[hl]?.includes(c.n)
            if (c.proof != null) return <div key={c.n} className={`src ${on ? 'hl' : ''}`}><span className="n">{c.n}</span><span><b>Zamp customer result</b><div className="muted">zamp.ai</div></span></div>
            const s = c.sig!
            const src = s.sources[0]
            return <div key={c.n} className={`src ${on ? 'hl' : ''}`}><span className="n">{c.n}</span><span>
              <div>{s.label || s.text}</div>
              <div className="muted">{src?.url ? <a href={src.url} target="_blank" rel="noreferrer">{host(src.url) || src.label} ↗</a> : src?.label}
                {s.sources.length > 1 && <> +{s.sources.length - 1} more</>}{s.date && <span className="mono"> · {s.date.slice(0, 10)}</span>}</div>
            </span></div>
          })}
          {cites.length === 0 && <div className="src">No sources cited.</div>}
        </div>
      </div>

      {/* email */}
      <div>
        {dr.approve_blocked && !done && <div className="banner bad">{dr.approve_blocked}</div>}
        {dr.low_personalisation && <div className="banner warn">Low personalisation: no specific hook was strong enough.</div>}
        {run.status === 'approved' && <div className="banner ok">Approved by {run.review?.reviewer}{run.review?.edited ? ' after edits' : ''}. Copy it into your email tool to send.</div>}
        {run.status === 'rejected' && <div className="banner warn">Rejected{run.review?.reason ? `: ${run.review.reason}` : ''}.</div>}
        <div className="email">
          <div className="email-head">
            <span className="k">To</span><span>{run.person?.name} <span className="faint">· {run.person?.title}, {run.company?.name}</span></span>
            <span className="k">Subject</span>
            {edit ? <input className="subject-edit" value={subj} onChange={e => setSubj(e.target.value)} /> : <span>{dr.subject}</span>}
          </div>
          {edit
            ? <textarea ref={ta} className="email-edit" value={body} onChange={e => setBody(e.target.value)} />
            : <div className="email-body"><Marked body={dr.body} claims={dr.claims} nums={claimNums} hl={hl} setHl={setHl} tone={verdictTone} /></div>}
          <div className="actionbar">
            {done ? <>
              <button className="btn" onClick={() => { navigator.clipboard.writeText(`Subject: ${dr.subject}\n\n${dr.body}`); setCopied(true) }}>{copied ? 'Copied' : 'Copy email'}</button>
              <span className="muted" style={{ fontSize: 12.5 }}>{dr.words} words</span>
            </> : edit ? <>
              <button className="btn primary" onClick={() => act('save')}>Save edits</button>
              <button className="btn" onClick={() => { setEdit(false); setSubj(dr.subject); setBody(dr.body) }}>Cancel <span className="kbd">esc</span></button>
            </> : rejecting ? <>
              <input className="input" style={{ flex: 1, minWidth: 200 }} autoFocus placeholder="Why? e.g. wrong angle, too salesy" value={reason} onChange={e => setReason(e.target.value)} />
              <button className="btn danger" onClick={() => act('reject')}>Reject</button>
              <button className="btn" onClick={() => setRejecting(false)}>Cancel</button>
            </> : <>
              <button className="btn primary" disabled={!!dr.approve_blocked} onClick={() => act('approve')}>Approve <span className="kbd">A</span></button>
              <button className="btn" onClick={() => setEdit(true)}>Edit <span className="kbd">E</span></button>
              <button className="btn" onClick={() => setRejecting(true)}>Reject <span className="kbd">R</span></button>
              <span className="muted" style={{ marginLeft: 'auto', fontSize: 12.5 }}>{dr.words} words · confidence {run.hook?.confidence ?? '–'}</span>
            </>}
          </div>
        </div>
        {err && <div className="banner bad" style={{ marginTop: 10 }}>{err}</div>}
        <div className="panel panel-pad" style={{ marginTop: 16 }}>
          <h2>Citations</h2>
          <p className="muted" style={{ fontSize: 12.5, margin: '-4px 0 8px' }}>Written by {dr.writer}. Each factual sentence points to the Crustdata fact it came from; hover a sentence to see its source on the left.</p>
          {dr.claims.map((c, i) => <div className="check" key={i} onMouseEnter={() => setHl(i)} onMouseLeave={() => setHl(null)}>
            <span><span className={`tag ${c.removed ? '' : c.verdict === 'cited' ? 'ok' : 'warn'}`}>{c.removed ? 'removed' : c.verdict}</span></span>
            <span>“{c.text}”<div className="d">{c.reason} {claimNums[i].length > 0 && <span className="mono">[{claimNums[i].join(', ')}]</span>}</div></span>
          </div>)}
          {(dr.unlisted || []).map((u, i) => <div className="check" key={'u' + i}><span><span className="tag bad">no source</span></span><span>“{u}”</span></div>)}
          {(dr.issues || []).map((x, i) => <div className="check" key={'i' + i}><span><span className={`tag ${x.severity === 'block' ? 'bad' : 'warn'}`}>{x.severity === 'block' ? 'must fix' : 'note'}</span></span><span>{x.problem}{x.sentence && <div className="d">“{x.sentence}”</div>}</span></div>)}
          {dr.lint?.length > 0 && <div className="check"><span><span className="tag warn">note</span></span><span>{dr.lint.join('; ')}</span></div>}
          {dr.original && <details style={{ marginTop: 10 }}><summary className="muted" style={{ cursor: 'pointer' }}>Original draft before edits</summary><div className="email-body" style={{ padding: '10px 0 0', fontSize: 14 }}>{dr.original.body}</div></details>}
        </div>
      </div>

      {/* hook */}
      <div className="panel panel-pad">
        <h2>Why this hook</h2>
        {hooks.length > 0 ? <div className="hook-card">
          {hooks.map(h => <div key={h.id} style={{ fontWeight: 500 }}>{h.label || h.text}</div>)}
          {run.hook?.angle && <div className="muted" style={{ fontSize: 13, margin: '6px 0' }}>{run.hook.angle}</div>}
          {run.hook?.why && <div style={{ fontSize: 13 }}>{run.hook.why}</div>}
          <div className="faint" style={{ fontSize: 12, marginTop: 6 }}>Chosen by {run.hook?.model} · confidence {run.hook?.confidence}</div>
        </div> : <div className="muted">No hook was strong enough.</div>}
        <h3 style={{ marginTop: 16 }}>Not chosen</h3>
        {notChosen.map(s => <div key={s.id} className="rej">
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}><span>{s.label || s.text}</span><span className="mono faint">{s.id}</span></div>
          <div className="why">{s.reason}</div>
        </div>)}
        <h3 style={{ marginTop: 16 }}>Checks that fired</h3>
        {run.checks.filter(c => c.status !== 'pass' || c.kind === 'identity').slice(0, 8).map((c, i) =>
          <div key={i} className="rej"><span className={`tag ${c.status === 'block' ? 'bad' : c.status === 'warn' ? 'warn' : 'ok'}`}>{EDGE[c.kind] || c.kind}</span> <span className="why">{c.title}</span></div>)}
      </div>
    </div>
  )
}

function Marked({ body, claims, nums, hl, setHl, tone }: { body: string; claims: Claim[]; nums: number[][]; hl: number | null; setHl: (n: number | null) => void; tone: (c: Claim) => string }) {
  // split the body around claim sentences that appear verbatim
  const parts: (string | { i: number; t: string })[] = []
  let rest = body
  const found = claims.map((c, i) => ({ i, at: body.indexOf(c.text), t: c.text })).filter(x => x.at >= 0 && x.t).sort((a, b) => a.at - b.at)
  let cursor = 0
  for (const f of found) {
    if (f.at < cursor) continue
    parts.push(body.slice(cursor, f.at)); parts.push({ i: f.i, t: f.t }); cursor = f.at + f.t.length
  }
  rest = body.slice(cursor)
  parts.push(rest)
  return <>{parts.map((p, k) => typeof p === 'string' ? <span key={k}>{p}</span>
    : <span key={k} className={`claim ${tone(claims[p.i])} ${hl === p.i ? 'hl' : ''}`} onMouseEnter={() => setHl(p.i)} onMouseLeave={() => setHl(null)}>{p.t}<sup>{nums[p.i].join(',')}</sup></span>)}</>
}


