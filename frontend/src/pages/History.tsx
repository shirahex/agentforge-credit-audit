import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { listAudits } from '../lib/api'
import { dateTime, pct } from '../lib/format'
import type { AuditSummary } from '../types'

function outcome(a: AuditSummary): { text: string; tone: string } {
  if (!a.done) return { text: 'Running', tone: 'text-accent' }
  if (a.review) return { text: `${a.review.outcome === 'approved' ? 'Approved' : 'Refused'} by ${a.review.reviewer}`, tone: 'text-ink' }
  if (a.escalated) return { text: 'Waiting for a reviewer', tone: 'text-caution' }
  return a.decision === 'approved' ? { text: 'Approved', tone: 'text-positive' } : { text: 'Refused', tone: 'text-negative' }
}

export function History() {
  const navigate = useNavigate()
  const [audits, setAudits] = useState<AuditSummary[] | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    listAudits().then(setAudits).catch(() => setError(true))
  }, [])

  return (
    <>
      <h1 className="text-4xl font-semibold sm:text-5xl">History</h1>
      <p className="mt-3 max-w-2xl text-lg text-muted">Every audit run since the backend started, most recent first.</p>

      {error && <p className="mt-8 text-sm text-negative">The list could not be loaded because the backend does not answer.</p>}
      {audits?.length === 0 && (
        <div className="mt-12 max-w-md">
          <p className="text-lg">No audit has been run yet.</p>
          <Link to="/" className="mt-4 inline-flex h-11 items-center rounded-full bg-accent px-6 font-medium text-white">
            Run the first audit
          </Link>
        </div>
      )}
      {audits && audits.length > 0 && (
        <div className="mt-10 overflow-x-auto rounded-panel bg-surface ring-1 ring-hairline">
          <table className="w-full min-w-[42rem] text-left">
            <thead className="text-sm text-muted">
              <tr className="border-b border-hairline">
                {['Applicant', 'Outcome', 'Default risk', 'Attempts', 'Ways to approval', 'Started'].map((h, i) => (
                  <th key={h} className={`px-6 py-3.5 font-normal ${i >= 2 && i <= 4 ? 'text-right' : ''}`}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {audits.map((a) => {
                const o = outcome(a)
                return (
                  <tr
                    key={a.run_id}
                    onClick={() => navigate(`/audit/${a.run_id}`)}
                    className="cursor-pointer transition-colors hover:bg-canvas/70"
                  >
                    <td className="px-6 py-4 font-medium">
                      <Link to={`/audit/${a.run_id}`} onClick={(e) => e.stopPropagation()}>
                        {a.applicant_id}
                      </Link>
                    </td>
                    <td className={`px-6 py-4 ${o.tone}`}>{o.text}</td>
                    <td className="num px-6 py-4 text-right">{a.default_probability === null ? '' : pct(a.default_probability)}</td>
                    <td className="num px-6 py-4 text-right text-muted">{a.attempts}</td>
                    <td className="num px-6 py-4 text-right text-muted">{a.paths}</td>
                    <td className="num px-6 py-4 text-muted">{dateTime(a.started_at)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
