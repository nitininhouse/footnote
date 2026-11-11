import { STATUS } from '../api'

export function Chip({ s }: { s: string }) {
  const st = STATUS[s] || { label: s, tone: '' }
  return <span className={`chip ${st.tone}`}>{s === 'running' ? <span className="icon running" style={{ width: 8, height: 8 }} /> : <span className="dot" />}{st.label}</span>
}

export function Icon({ status }: { status: string }) {
  return <span className={`icon ${status}`} />
}

export function Score({ label, v, max = 5 }: { label: string; v: number; max?: number }) {
  return <div className="score-bar"><span>{label}</span><span className="bar"><i style={{ width: `${Math.max(0, Math.min(1, v / max)) * 100}%` }} /></span><span className="mono r">{v.toFixed(1)}</span></div>
}

export function host(u: string | null | undefined) {
  if (!u) return ''
  try { return new URL(u).hostname.replace(/^www\./, '') } catch { return '' }
}

export function initials(name: string | null | undefined) {
  return (name || '?').split(/\s+/).filter(w => /^[A-Za-z]/.test(w) && !/^(CPA|CIA|CISA|MBA|CFA)[,.]?$/.test(w)).slice(0, 2).map(w => w[0].toUpperCase()).join('')
}
