import { useNavigate } from 'react-router-dom'
import { pct } from '../lib/format'
import { ago, auditStatus, durationSeconds } from '../lib/status'
import type { AuditSummary } from '../types'
import { StatusPill } from './ui'

/** Risk of default as a small bar against the refusal threshold. */
export function RiskCell({ p, threshold }: { p: number | null; threshold: number }) {
  if (p === null) return <span className="skeleton inline-block h-2 w-24" />
  const over = p >= threshold
  return (
    <span className="flex items-center gap-2.5">
      <span className="relative h-1.5 w-20 rounded-full bg-hairline">
        <span className={`absolute inset-y-0 left-0 rounded-full ${over ? 'bg-negative' : 'bg-positive'}`} style={{ width: `${Math.min(100, p * 100)}%` }} />
        <span className="absolute -top-1 h-3.5 w-px bg-ink/60" style={{ left: `${threshold * 100}%` }} />
      </span>
      <span className="num w-9 text-right text-[13px] font-medium">{pct(p)}</span>
    </span>
  )
}

export function AuditTable({ audits, threshold, compact = false }: { audits: AuditSummary[]; threshold: number; compact?: boolean }) {
  const navigate = useNavigate()
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[620px] text-left text-[13.5px]">
        <thead>
          <tr className="border-b border-hairline text-[12.5px] text-muted">
            <th className="px-5 py-2.5 font-medium">Applicant</th>
            <th className="px-3 py-2.5 font-medium">Status</th>
            <th className="px-3 py-2.5 font-medium">Default risk</th>
            {!compact && <th className="px-3 py-2.5 font-medium">Ways to approval</th>}
            {!compact && <th className="px-3 py-2.5 font-medium">Duration</th>}
            <th className="px-5 py-2.5 text-right font-medium">Started</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-hairline">
          {audits.map((a) => {
            const secs = durationSeconds(a)
            return (
              <tr
                key={a.run_id}
                onClick={() => navigate(`/app/audit/${a.run_id}`)}
                className="cursor-pointer transition-colors hover:bg-raised"
              >
                <td className="px-5 py-3">
                  <a
                    href={`/app/audit/${a.run_id}`}
                    onClick={(e) => e.preventDefault()}
                    className="font-medium text-ink"
                  >
                    {a.applicant_id}
                  </a>
                  <span className="ml-2 text-[12px] text-faint">{a.run_id.slice(0, 6)}</span>
                </td>
                <td className="px-3 py-3">
                  <StatusPill status={auditStatus(a)} />
                </td>
                <td className="px-3 py-3">
                  <RiskCell p={a.default_probability} threshold={threshold} />
                </td>
                {!compact && (
                  <td className="num px-3 py-3 text-soft">
                    {a.decision === 'refused' ? `${a.paths} after ${a.attempts} attempt${a.attempts === 1 ? '' : 's'}` : a.done ? 'Not needed' : ''}
                  </td>
                )}
                {!compact && <td className="num px-3 py-3 text-soft">{secs === null ? '' : `${secs.toFixed(0)} s`}</td>}
                <td className="px-5 py-3 text-right text-muted">{ago(a.started_at)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
