import type {
  AgentEvent,
  AuditRecord,
  AuditSummary,
  Decision,
  Health,
  LoanApplication,
  ModelCard,
  Sample,
  Schema,
} from '../types'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) throw new Error(`${path} answered ${res.status}`)
  return res.json()
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    const first = Array.isArray(detail?.detail) ? detail.detail[0] : null
    throw new Error(first ? `${first.loc?.at(-1)}: ${first.msg}` : (detail?.detail ?? `${path} answered ${res.status}`))
  }
  return res.json()
}

export const getHealth = () => get<Health>('/health')
export const getSchema = () => get<Schema>('/api/schema')
export const getSamples = () => get<Sample[]>('/api/samples')
export const getModelCard = () => get<ModelCard>('/api/model')
export const listAudits = () => get<AuditSummary[]>('/api/audits')
export const getAudit = (id: string) => get<AuditRecord>(`/api/audits/${id}`)
export const startAudit = (application: LoanApplication) =>
  post<{ run_id: string }>('/api/audits', application).then((r) => r.run_id)
export const sendReview = (id: string, outcome: Decision, reviewer: string, comment: string) =>
  post<AuditRecord>(`/api/audits/${id}/review`, { outcome, reviewer, comment })

export const reportUrl = (id: string) => `/api/audits/${id}/report`
export const letterUrl = (id: string) => `/api/audits/${id}/letter`
export const traceUrl = (id: string) => `/api/audits/${id}/trace`

/** Subscribes to the audit trail. Returns a function that closes the stream. */
export function streamEvents(runId: string, onEvent: (event: AgentEvent) => void, onEnd: () => void): () => void {
  const source = new EventSource(`/api/audits/${runId}/events`)
  let closed = false
  const finish = () => {
    if (closed) return
    closed = true
    source.close()
    onEnd()
  }
  source.onmessage = (msg) => onEvent(JSON.parse(msg.data))
  source.addEventListener('end', finish)
  source.onerror = finish
  return () => {
    closed = true
    source.close()
  }
}
