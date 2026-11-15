import { ArrowUpRight } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { AuditTable } from '../components/AuditTable'
import { Card, CardHeader, Empty, Kpi, PageHeader, StatusPill, buttonClass } from '../components/ui'
import { getModelCard } from '../lib/api'
import { pct } from '../lib/format'
import { useAudits, useHealth } from '../lib/hooks'
import { ago, auditStatus, durationSeconds } from '../lib/status'
import type { ModelCard } from '../types'

function median(xs: number[]): number | null {
  if (!xs.length) return null
  const s = [...xs].sort((a, b) => a - b)
  return s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2
}

const SEGMENTS = [
  { key: 'approved', label: 'Approved', color: 'bg-positive' },
  { key: 'refused', label: 'Refused, with or without a path', color: 'bg-negative' },
  { key: 'review', label: 'With a reviewer', color: 'bg-caution' },
  { key: 'running', label: 'Running', color: 'bg-accent' },
] as const

export function Dashboard() {
  const { audits, error } = useAudits()
  const { health } = useHealth()
  const [card, setCard] = useState<ModelCard | null>(null)
  useEffect(() => {
    getModelCard().then(setCard).catch(() => {})
  }, [])

  const threshold = health?.threshold ?? card?.meta.threshold ?? 0.26
  const stats = useMemo(() => {
    const list = audits ?? []
    const by = { approved: 0, refused: 0, review: 0, running: 0, error: 0 }
    for (const a of list) by[auditStatus(a).key] += 1
    const closed = by.approved + by.refused
    const refusedWithPath = list.filter((a) => a.done && a.decision === 'refused' && a.paths > 0).length
    const refusedTotal = list.filter((a) => a.done && a.decision === 'refused').length
    const reviewed = list.filter((a) => a.escalated).length
    const times = list.map(durationSeconds).filter((s): s is number => s !== null)
    return {
      total: list.length,
      by,
      approvalRate: closed ? by.approved / closed : null,
      recourse: refusedTotal ? refusedWithPath / refusedTotal : null,
      escalation: list.length ? reviewed / list.length : null,
      medianTime: median(times),
    }
  }, [audits])

  const queue = (audits ?? []).filter((a) => a.status === 'awaiting_review')
  const full = card?.summary?.audit?.full

  return (
    <>
      <PageHeader
        title="Dashboard"
        sub="Every credit decision scored, explained, given a verified way to approval when refused, and checked for fairness."
      />

      {error && !audits && <p className="mb-6 text-[13.5px] text-negative">The audits could not be loaded: the API does not answer.</p>}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi label="Audits run" value={audits ? stats.total : '...'} hint={health ? `${health.store.cases} closed cases in memory` : undefined} />
        <Kpi
          label="Refusals with a verified path"
          value={stats.recourse === null ? '...' : pct(stats.recourse)}
          tone="positive"
          hint={full ? `${pct(full.recourse_rate)} on the 99 refusals of the test set` : 'Share of refused files'}
        />
        <Kpi
          label="Sent to a person"
          value={stats.escalation === null ? '...' : pct(stats.escalation)}
          tone="caution"
          hint={`${queue.length} waiting in the review inbox`}
        />
        <Kpi
          label="Median audit time"
          value={stats.medianTime === null ? '...' : `${stats.medianTime.toFixed(0)} s`}
          hint={health?.llm.enabled ? `Five agents on ${health.llm.model.replace('openai/', '')}` : 'Agents on rules'}
        />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Card>
          <CardHeader
            title="Recent audits"
            aside={
              <Link to="/app/audits" className="inline-flex items-center gap-1 text-accent-ink hover:underline">
                View all <ArrowUpRight size={13} />
              </Link>
            }
          />
          {audits && audits.length > 0 && (
            <>
              <div className="px-5 pt-4">
                <div className="flex h-2 overflow-hidden rounded-full bg-hairline" role="img" aria-label="Outcome of the audits">
                  {SEGMENTS.map((s) =>
                    stats.by[s.key] ? (
                      <span key={s.key} className={`${s.color} transition-all`} style={{ width: `${(stats.by[s.key] / stats.total) * 100}%` }} />
                    ) : null,
                  )}
                </div>
                <div className="mt-2.5 flex flex-wrap gap-x-5 gap-y-1 text-[12.5px] text-muted">
                  {SEGMENTS.map((s) => (
                    <span key={s.key} className="flex items-center gap-1.5">
                      <span className={`h-2 w-2 rounded-sm ${s.color}`} />
                      {s.label}
                      <span className="num font-medium text-soft">{stats.by[s.key]}</span>
                    </span>
                  ))}
                </div>
              </div>
              <div className="mt-3">
                <AuditTable audits={audits.slice(0, 8)} threshold={threshold} compact />
              </div>
            </>
          )}
          {audits && audits.length === 0 && (
            <Empty
              title="No audit yet"
              action={
                <Link to="/app/new" className={buttonClass('primary', 'sm')}>
                  Run the first audit
                </Link>
              }
            >
              Pick one of the six sample files from the test set to see the five agents at work.
            </Empty>
          )}
          {!audits && !error && (
            <div className="space-y-3 p-5">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="skeleton h-5" />
              ))}
            </div>
          )}
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader title="Review inbox" aside={<span className="num">{queue.length}</span>} />
            {queue.length === 0 ? (
              <Empty title="Nothing to review">Escalated files land here: borderline scores, a failed fairness test, or no way to approval.</Empty>
            ) : (
              <ul className="divide-y divide-hairline">
                {queue.slice(0, 5).map((a) => (
                  <li key={a.run_id}>
                    <Link to={`/app/audit/${a.run_id}`} className="flex items-center justify-between gap-3 px-5 py-3 transition-colors hover:bg-raised">
                      <span>
                        <span className="block text-[14px] font-medium">{a.applicant_id}</span>
                        <span className="text-[12.5px] text-muted">
                          Risk {a.default_probability !== null ? pct(a.default_probability) : '...'}, {ago(a.started_at)}
                        </span>
                      </span>
                      <StatusPill status={auditStatus(a)} />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {card && (
            <Card>
              <CardHeader
                title="Model at a glance"
                aside={
                  <Link to="/app/model" className="inline-flex items-center gap-1 text-accent-ink hover:underline">
                    Details <ArrowUpRight size={13} />
                  </Link>
                }
              />
              <dl className="grid grid-cols-2 gap-px bg-hairline">
                {[
                  ['Test AUC', card.meta.test.auc.toFixed(3)],
                  ['Cross-validation AUC', card.meta.cv.lightgbm_auc.toFixed(3)],
                  ['Refusal threshold', pct(card.meta.threshold)],
                  ['Training files', String(card.meta.data.train_rows)],
                ].map(([k, v]) => (
                  <div key={k} className="bg-surface px-5 py-3">
                    <dt className="text-[12.5px] text-muted">{k}</dt>
                    <dd className="num mt-0.5 text-[17px] font-semibold">{v}</dd>
                  </div>
                ))}
              </dl>
            </Card>
          )}
        </div>
      </div>
    </>
  )
}
