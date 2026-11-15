import { FilePlus2, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { AuditTable } from '../components/AuditTable'
import { Card, Empty, PageHeader, Tabs, buttonClass } from '../components/ui'
import { useAudits, useHealth } from '../lib/hooks'
import { auditStatus, type Status } from '../lib/status'

type Filter = 'all' | Status['key']

/** All audits, or the review inbox when `review` is set. */
export function Audits({ review = false }: { review?: boolean }) {
  const { audits, error } = useAudits()
  const { health } = useHealth()
  const [filter, setFilter] = useState<Filter>('all')
  const [q, setQ] = useState('')

  const counts = useMemo(() => {
    const c: Record<Filter, number> = { all: 0, running: 0, review: 0, approved: 0, refused: 0, error: 0 }
    for (const a of audits ?? []) {
      c.all += 1
      c[auditStatus(a).key] += 1
    }
    return c
  }, [audits])

  const shown = (audits ?? []).filter((a) => {
    const key = auditStatus(a).key
    if (review ? key !== 'review' : filter !== 'all' && key !== filter) return false
    return !q || a.applicant_id.toLowerCase().includes(q.toLowerCase()) || a.run_id.startsWith(q.toLowerCase())
  })

  return (
    <>
      <PageHeader
        title={review ? 'Review inbox' : 'Audits'}
        sub={
          review
            ? 'Files the agents did not close on their own. A person reads the case and takes the decision; the graph then resumes and issues the final report and letter.'
            : 'Every audit, most recent first. Audits are stored on disk and survive a restart of the API.'
        }
        actions={
          <Link to="/app/new" className={buttonClass('primary')}>
            <FilePlus2 size={15} /> New audit
          </Link>
        }
      />
      <Card>
        <div className="flex flex-wrap items-end justify-between gap-3 px-5 pt-2">
          {!review ? (
            <Tabs<Filter>
              value={filter}
              onChange={setFilter}
              tabs={[
                { id: 'all', label: 'All', count: counts.all },
                { id: 'review', label: 'Needs review', count: counts.review },
                { id: 'refused', label: 'Refused', count: counts.refused },
                { id: 'approved', label: 'Approved', count: counts.approved },
                { id: 'running', label: 'Running', count: counts.running },
              ]}
            />
          ) : (
            <span />
          )}
          <label className="relative mb-2 block w-full sm:w-64">
            <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Filter by applicant"
              className="h-8 w-full rounded-control border border-hairline bg-surface pl-8 pr-3 text-[13.5px] outline-none placeholder:text-faint focus:border-accent"
            />
          </label>
        </div>
        {error && !audits && <p className="px-5 py-6 text-[13.5px] text-negative">The audits could not be loaded: the API does not answer.</p>}
        {!audits && !error && (
          <div className="space-y-3 p-5">
            {[0, 1, 2, 3, 4].map((i) => (
              <div key={i} className="skeleton h-5" />
            ))}
          </div>
        )}
        {audits && shown.length > 0 && <AuditTable audits={shown} threshold={health?.threshold ?? 0.26} />}
        {audits && shown.length === 0 && (
          <Empty title={review ? 'The inbox is empty' : 'No audit matches'}>
            {review
              ? 'Run the "Borderline score" or "Sensitive attribute" sample to see an escalation.'
              : 'Change the filter or start a new audit.'}
          </Empty>
        )}
      </Card>
    </>
  )
}
