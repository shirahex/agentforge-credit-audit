import { useEffect, useRef, useState } from 'react'
import { fetchSamples, startAudit, streamEvents } from './lib/api'
import type { AgentEvent, AuditDecision, LoanApplication } from './types'

// Starting screen: proves the full chain (form data, API, agent graph, live
// event stream). The designed screens of task M5 replace this file.

const STATUS_STYLE: Record<AgentEvent['status'], string> = {
  completed: 'bg-ink',
  finished: 'bg-positive',
  rejected: 'bg-negative',
  escalated: 'bg-caution',
  error: 'bg-negative',
}

const FIELDS: [keyof LoanApplication, string][] = [
  ['credit_amount', 'Amount'],
  ['duration_months', 'Duration (months)'],
  ['age', 'Age'],
  ['employment_years', 'Employment (years)'],
  ['housing', 'Housing'],
  ['savings', 'Savings'],
  ['checking_status', 'Checking account'],
  ['purpose', 'Purpose'],
]

export default function App() {
  const [samples, setSamples] = useState<LoanApplication[]>([])
  const [selected, setSelected] = useState(0)
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const close = useRef<() => void>(() => {})

  useEffect(() => {
    fetchSamples()
      .then(setSamples)
      .catch(() => setError('Backend unreachable. Start it with: uvicorn app.main:app --reload'))
    return () => close.current()
  }, [])

  const application = samples[selected]
  const decision: AuditDecision | undefined = events.findLast((e) => e.payload.decision)?.payload.decision

  async function run() {
    if (!application) return
    close.current()
    setEvents([])
    setError(null)
    setRunning(true)
    try {
      const runId = await startAudit(application)
      close.current = streamEvents(
        runId,
        (e) => setEvents((prev) => [...prev, e]),
        () => setRunning(false),
      )
    } catch (e) {
      setError(String(e))
      setRunning(false)
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-14">
      <header className="mb-12">
        <p className="text-sm font-medium text-muted">AgentForge</p>
        <h1 className="font-display mt-1 text-5xl font-semibold tracking-tight">Credit audit</h1>
        <p className="mt-3 max-w-xl text-lg text-muted">
          Five agents score a loan file, search for a realistic path to approval and audit the decision for fairness.
        </p>
      </header>

      {error && <p className="mb-6 rounded-xl bg-negative/10 px-4 py-3 text-sm text-negative">{error}</p>}

      <div className="grid items-start gap-6 md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <section className="rounded-card border border-hairline bg-surface p-6">
          <h2 className="text-sm font-semibold">Applicant file</h2>
          <div className="mt-4 inline-flex rounded-full bg-canvas p-1">
            {samples.map((s, i) => (
              <button
                key={s.applicant_id}
                onClick={() => setSelected(i)}
                className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                  i === selected ? 'bg-surface shadow-sm' : 'text-muted hover:text-ink'
                }`}
              >
                {s.applicant_id.replace('DEMO-', '').toLowerCase()}
              </button>
            ))}
          </div>
          {application && (
            <dl className="mt-5 divide-y divide-hairline text-sm">
              {FIELDS.map(([key, label]) => (
                <div key={key} className="flex justify-between py-2">
                  <dt className="text-muted">{label}</dt>
                  <dd className="font-medium tabular-nums">{String(application[key])}</dd>
                </div>
              ))}
            </dl>
          )}
          <button
            onClick={run}
            disabled={running || !application}
            className="mt-6 w-full rounded-full bg-accent py-2.5 text-sm font-medium text-white transition hover:brightness-110 disabled:opacity-40"
          >
            {running ? 'Audit in progress' : 'Run audit'}
          </button>
        </section>

        <section className="rounded-card border border-hairline bg-surface p-6">
          <h2 className="text-sm font-semibold">Audit trail</h2>
          {events.length === 0 && (
            <p className="mt-4 text-sm text-muted">Agent steps appear here as the audit runs.</p>
          )}
          <ol className="mt-4 space-y-4">
            {events.map((e) => (
              <li key={e.seq} className="rise flex gap-3">
                <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${STATUS_STYLE[e.status]}`} />
                <div>
                  <p className="text-sm font-medium">{e.agent}</p>
                  <p className="text-sm text-muted">{e.message}</p>
                </div>
              </li>
            ))}
          </ol>

          {decision && !running && (
            <div className="rise mt-6 rounded-2xl bg-canvas p-5">
              <p className="text-xs font-medium uppercase tracking-wide text-muted">
                {decision.escalated ? 'Sent to human review' : 'Decision'}
              </p>
              <p className="font-display mt-1 text-2xl font-semibold tracking-tight">
                <span className="capitalize">{decision.decision}</span>
                <span className="ml-2 text-base font-normal text-muted tabular-nums">
                  default risk {(decision.default_probability * 100).toFixed(0)}%
                </span>
              </p>
              <p className="mt-2 text-sm text-muted">{decision.summary}</p>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
