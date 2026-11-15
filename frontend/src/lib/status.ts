import type { AuditSummary } from '../types'

export type Tone = 'positive' | 'negative' | 'caution' | 'accent' | 'muted'

export interface Status {
  key: 'running' | 'review' | 'approved' | 'refused' | 'error'
  label: string
  tone: Tone
}

/** One status per audit, the same everywhere in the console. */
export function auditStatus(a: Pick<AuditSummary, 'done' | 'status' | 'escalated' | 'decision' | 'review' | 'final_outcome'>): Status {
  if (!a.done || a.status === 'running') return { key: 'running', label: 'Running', tone: 'accent' }
  if (a.status === 'error') return { key: 'error', label: 'Error', tone: 'negative' }
  if (a.status === 'awaiting_review') return { key: 'review', label: 'Needs review', tone: 'caution' }
  const outcome = a.review?.outcome ?? a.final_outcome ?? a.decision
  return outcome === 'approved'
    ? { key: 'approved', label: a.review ? 'Approved by reviewer' : 'Approved', tone: 'positive' }
    : { key: 'refused', label: a.review ? 'Refused by reviewer' : 'Refused', tone: 'negative' }
}

export function durationSeconds(a: Pick<AuditSummary, 'started_at' | 'finished_at'>): number | null {
  if (!a.finished_at) return null
  return (new Date(a.finished_at).getTime() - new Date(a.started_at).getTime()) / 1000
}

export function ago(iso: string): string {
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
}
