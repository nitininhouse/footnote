export type Stage = { key: string; title: string; status: string; started?: string; summary: string; ms: number | null; log: { t: number; msg: string; level: string }[] }
export type Source = { label: string; url: string | null; title?: string; date?: string }
export type Signal = {
  id: string; kind: string; about: string; date: string | null; text: string; label?: string; event_type?: string
  coverage: number; flags: string[]; sources: Source[]; age_days?: number | null
  score?: { relevance: number; recency: number; personal: number; source: number; bonus: number; penalty: number; total: number }
  eligible?: boolean; why_not?: string; why_chosen?: string; consequence?: string; trigger?: string; no_numbers?: boolean
}
export type Claim = { text: string; facts: string[]; proof: number[]; verdict?: string; reason?: string; removed?: boolean }
export type Draft = {
  subject: string; body: string; claims: Claim[]; lint: string[]; words: number; genericness?: number
  genericness_reason?: string; unlisted?: string[]; approve_blocked?: string; edited?: boolean
  original?: { subject: string; body: string }; low_personalisation?: boolean
}
export type Check = { kind: string; status: 'pass' | 'warn' | 'block'; title: string; detail: string; signal_ids: string[] }
export type Question = { kind: string; text: string; options: { id: string; label: string; detail?: string; url?: string; input?: boolean }[] }
export type Run = {
  id: string; created: string; updated: string; mode: string; status: string
  input: { name: string; company: string; title: string; linkedin: string; notes: string }
  stages: Stage[]; credits: number; calls: { path: string; label: string; credits: number; cached: boolean }[]
  company: { id: number; name: string; domain: string } | null
  company_candidates?: { id: number; name: string; domain: string; size: string }[]
  person: { name: string; title: string; headline: string; url: string; start: string; tenure_days: number; location: string; past: { title: string; company: string; start: string; end: string }[] } | null
  company_data?: { headcount: number; headcount_yoy: number; last_round: { type: string; amount: number; date: string } | null; news_count: number; description: string }
  signals: Signal[]; hook: { id: string | null; support: string | null; context: string | null; ranking: string[] } | null
  draft: Draft | null; checks: Check[]; question: Question | null
  review: { action: string; at: string; reviewer: string; reason?: string; edited?: boolean } | null
  error?: { code: string; msg: string }; note?: string
}
export type Row = {
  id: string; created: string; mode: string; status: string; name: string; title: string; company: string
  hook: string | null; hook_kind: string | null; claims_ok: number; claims: number; credits: number; ms: number
  edge: string[]; reviewer: string | null; question: string | null
}
export type Stats = { runs: number; awaiting: number; approved: number; approval_rate: number | null; edit_rate: number | null; median_ms: number | null; claim_pass: number | null; credits: number }
export type Config = { default_mode: string; live_needs_code: boolean; live_available: boolean; seller: string; run_cap: number; spent_today: number; daily_cap: number }

async function j<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let msg = r.statusText
    try { msg = (await r.json()).detail || msg } catch { /* not json */ }
    throw new Error(msg)
  }
  return r.json()
}
const post = (u: string, b: unknown) => fetch(u, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(b) })

export const api = {
  config: () => fetch('/api/config').then(j<Config>),
  runs: () => fetch('/api/runs').then(j<Row[]>),
  stats: () => fetch('/api/stats').then(j<Stats>),
  run: (id: string) => fetch(`/api/runs/${id}`).then(j<Run>),
  create: (b: Record<string, string>) => post('/api/runs', b).then(j<{ id: string }>),
  answer: (id: string, option: string, value = '') => post(`/api/runs/${id}/answer`, { option, value }).then(j<{ ok: boolean }>),
  review: (id: string, b: Record<string, unknown>) => post(`/api/runs/${id}/review`, b).then(j<Run>),
}

export const STATUS: Record<string, { label: string; tone: string }> = {
  running: { label: 'Running', tone: 'accent' },
  ready: { label: 'Ready for review', tone: 'ok' },
  ready_with_warnings: { label: 'Review with care', tone: 'warn' },
  needs_input: { label: 'Needs your input', tone: 'warn' },
  approved: { label: 'Approved', tone: 'ink' },
  rejected: { label: 'Rejected', tone: '' },
  stopped: { label: 'Stopped', tone: '' },
  blocked: { label: 'Blocked', tone: 'bad' },
  not_found: { label: 'Not found', tone: 'bad' },
  needs_review: { label: 'Identity mismatch', tone: 'bad' },
  low_signal: { label: 'Low signal', tone: 'warn' },
  failed: { label: 'Failed', tone: 'bad' },
}

export const EDGE: Record<string, string> = {
  crowded: 'Crowded hook', conflict: 'Sources disagree', anomaly: 'Odd statistic', sensitive: 'Sensitive news',
  job_change: 'Job change', identity: 'Name collision', title: 'Title mismatch', stale: 'Stale', competitor: 'Competitor',
  recontact: 'Recently drafted', off_topic: 'Off-topic news',
}

export function ago(iso: string) {
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}
export const secs = (ms: number | null | undefined) => ms == null ? '' : ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`
