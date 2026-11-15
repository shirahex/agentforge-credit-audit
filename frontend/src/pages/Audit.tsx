import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { FactorBars } from '../components/FactorBars'
import { Pipeline } from '../components/Pipeline'
import { RiskRuler } from '../components/RiskRuler'
import { Trail } from '../components/Trail'
import { getAudit, getSchema, sendReview, streamEvents } from '../lib/api'
import { clock, dm, pct, pipelineView } from '../lib/format'
import type { AgentEvent, AuditRecord, Counterfactual, Decision, Review, Schema } from '../types'

const PROTECTED_LABEL: Record<string, string> = { sex: 'Sex', foreign_worker: 'Foreign worker status', age: 'Age' }

function Section({ title, aside, children }: { title: string; aside?: string; children: React.ReactNode }) {
  return (
    <section className="settle border-t border-hairline pt-8">
      <div className="mb-5 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 className="text-2xl font-semibold">{title}</h2>
        {aside && <p className="text-sm text-muted">{aside}</p>}
      </div>
      {children}
    </section>
  )
}

function Path({ cf, from, threshold }: { cf: Counterfactual; from: number; threshold: number }) {
  return (
    <li className="py-5">
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2">
        <p className="max-w-xl text-[17px] font-medium leading-snug">{cf.statement}</p>
        <p className="num shrink-0 text-right">
          <span className="text-muted line-through decoration-faint">{pct(from)}</span>
          <span className="ml-2 text-[17px] font-semibold text-positive">{pct(cf.new_probability)}</span>
        </p>
      </div>
      <div className="mt-3 max-w-xl">
        <RiskRuler value={from} to={cf.new_probability} threshold={threshold} compact />
      </div>
      <p className="mt-2 text-sm text-muted">
        {cf.effort === 'immediate'
          ? 'Can be done now, by changing the request.'
          : 'Takes time: it needs a change in the financial situation.'}{' '}
        Found by {cf.source === 'dice' ? 'DiCE' : 'exhaustive search'} and re-scored by the model.
      </p>
    </li>
  )
}

function ReviewPanel({ reason, review, onSend }: { reason: string; review: Review | null; onSend: (o: Decision, who: string, why: string) => Promise<void> }) {
  const [who, setWho] = useState('')
  const [why, setWhy] = useState('')
  const [busy, setBusy] = useState<Decision | null>(null)
  const [error, setError] = useState<string | null>(null)

  if (review)
    return (
      <div className="rounded-panel bg-surface p-7 ring-1 ring-hairline">
        <p className="text-sm text-muted">Reviewed at {clock(review.at)}</p>
        <p className="mt-1 text-2xl font-semibold">
          {review.outcome === 'approved' ? 'Approved' : 'Refused'} by {review.reviewer}
        </p>
        {review.comment && <p className="mt-3 max-w-2xl text-soft">{review.comment}</p>}
      </div>
    )

  async function send(outcome: Decision) {
    setBusy(outcome)
    setError(null)
    try {
      await onSend(outcome, who.trim() || 'Reviewer', why.trim())
    } catch {
      setError('The decision was not saved. Check that the backend is running, then choose again.')
    }
    setBusy(null)
  }

  const input = 'w-full rounded-control border border-hairline bg-surface px-3 py-2 text-[15px] focus:border-accent focus:outline-none'
  return (
    <div className="rounded-panel bg-surface p-7 ring-1 ring-caution/40">
      <p className="text-sm font-medium text-caution">A person decides this file</p>
      <p className="mt-1 max-w-2xl text-xl font-semibold leading-snug">The agents stopped because {reason}.</p>
      <div className="mt-6 grid gap-4 sm:grid-cols-[14rem_minmax(0,1fr)]">
        <label className="text-sm text-soft">
          Reviewer
          <input className={`${input} mt-1.5`} value={who} onChange={(e) => setWho(e.target.value)} placeholder="Name" />
        </label>
        <label className="text-sm text-soft">
          Reason for the decision
          <textarea className={`${input} mt-1.5`} rows={2} value={why} onChange={(e) => setWhy(e.target.value)} />
        </label>
      </div>
      {error && <p className="mt-3 text-sm text-negative">{error}</p>}
      <div className="mt-5 flex flex-wrap gap-3">
        <button
          onClick={() => send('approved')}
          disabled={busy !== null}
          className="h-11 rounded-full bg-ink px-6 text-[15px] font-medium text-white transition hover:bg-soft disabled:opacity-40"
        >
          {busy === 'approved' ? 'Saving' : 'Approve the loan'}
        </button>
        <button
          onClick={() => send('refused')}
          disabled={busy !== null}
          className="h-11 rounded-full px-6 text-[15px] font-medium ring-1 ring-ink/25 transition hover:bg-canvas disabled:opacity-40"
        >
          {busy === 'refused' ? 'Saving' : 'Refuse the loan'}
        </button>
      </div>
    </div>
  )
}

export function Audit() {
  const { id = '' } = useParams()
  const [record, setRecord] = useState<AuditRecord | null>(null)
  const [schema, setSchema] = useState<Schema | null>(null)
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [done, setDone] = useState(false)
  const [missing, setMissing] = useState(false)

  useEffect(() => {
    setEvents([])
    setDone(false)
    setMissing(false)
    setRecord(null)
    getSchema().then(setSchema).catch(() => {})
    let close = () => {}
    getAudit(id)
      .then((r) => {
        setRecord(r)
        close = streamEvents(
          id,
          (e) => setEvents((prev) => (prev.some((p) => p.seq === e.seq) ? prev : [...prev, e])),
          () => {
            setDone(true)
            getAudit(id).then(setRecord).catch(() => {})
          },
        )
      })
      .catch(() => setMissing(true))
    return () => close()
  }, [id])

  const view = useMemo(() => pipelineView(events, done, schema?.max_attempts ?? 3), [events, done, schema])
  const last = <K extends keyof AgentEvent['payload']>(key: K) => events.findLast((e) => e.payload[key] !== undefined)?.payload[key]

  if (missing)
    return (
      <div className="max-w-xl">
        <h1 className="text-4xl font-semibold">This audit is no longer in memory.</h1>
        <p className="mt-4 text-lg text-muted">Audits are kept until the backend restarts. Run the file again to see its result.</p>
        <Link to="/" className="mt-6 inline-flex h-11 items-center rounded-full bg-accent px-6 font-medium text-white">
          Start a new audit
        </Link>
      </div>
    )

  const app = record?.application
  const analysis = last('analysis')
  const score = last('score')
  const fairness = last('fairness')
  const decision = last('decision')
  const scoreEvent = events.find((e) => e.node === 'modele_scoring')
  const attempts = events.filter((e) => e.node === 'generateur_contrefactuels')
  const verdicts = events.filter((e) => e.node === 'verificateur_equite')
  const paths = decision?.counterfactuals ?? (verdicts.at(-1)?.payload.counterfactuals ?? [])
  const searching = !done && score?.decision === 'refused' && !decision
  const closest = attempts.at(-1)?.payload.counterfactuals?.find((c) => !c.valid && c.actionable)
  const purpose = schema?.features.find((f) => f.name === 'purpose')?.options.find((o) => o.value === app?.purpose)?.label
  const failure = events.find((e) => e.status === 'error')
  const tone = score?.decision === 'refused' ? 'text-negative' : 'text-positive'

  return (
    <>
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-muted">{done ? 'Audit complete' : 'Audit in progress'}</p>
          <h1 className="mt-1 text-4xl font-semibold sm:text-5xl">Applicant {app?.applicant_id ?? ''}</h1>
          {app && (
            <p className="mt-2 text-lg text-muted">
              {dm(Number(app.credit_amount))} over {String(app.duration_months)} months{purpose ? `, ${purpose.toLowerCase()}` : ''}
            </p>
          )}
        </div>
        <Link to="/" className="text-sm text-accent hover:underline">
          Audit another file
        </Link>
      </header>

      <div className="mt-10 rounded-panel bg-surface px-4 pb-5 pt-6 ring-1 ring-hairline sm:px-8">
        <Pipeline view={view} maxAttempts={schema?.max_attempts ?? 3} />
      </div>

      {failure && (
        <p className="mt-6 rounded-control bg-negative/10 px-4 py-3 text-sm text-negative">
          The audit stopped on an error: {failure.message}
        </p>
      )}

      <div className="mt-12 grid gap-12 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="space-y-12">
          {!score && !failure && <p className="text-lg text-muted">The file is being checked before it is scored.</p>}

          {score && (
            <section className="settle">
              <div className="flex flex-wrap items-end gap-x-8 gap-y-2">
                <p className={`num font-display text-8xl font-semibold leading-none tracking-tighter ${tone}`}>
                  {pct(score.default_probability)}
                </p>
                <div className="pb-2">
                  <p className={`text-3xl font-semibold ${tone}`}>{score.decision === 'refused' ? 'Refused' : 'Approved'}</p>
                  <p className="text-muted">Estimated risk of default</p>
                </div>
              </div>
              <div className="mt-6">
                <RiskRuler value={score.default_probability} threshold={score.threshold} margin={schema?.borderline_margin} />
              </div>
              <p className="mt-6 max-w-2xl text-lg leading-relaxed text-soft">{last('explanation')}</p>
              <p className="mt-2 text-sm text-muted">
                {scoreEvent?.mode === 'llm'
                  ? 'Written by the language model and accepted only after its factors and numbers were checked against SHAP.'
                  : 'Rule-based wording from the SHAP values.'}
              </p>
            </section>
          )}

          {score && (
            <Section title="What drives the score" aside="Exact SHAP contributions, in log-odds">
              <FactorBars factors={score.top_factors} />
            </Section>
          )}

          {score?.decision === 'refused' && attempts.length > 0 && (
            <Section
              title="Ways to approval"
              aside={paths.length > 0 ? `${paths.length} verified after ${attempts.length} attempt${attempts.length > 1 ? 's' : ''}` : undefined}
            >
              {paths.length > 0 && (
                <ul className="-mt-5 divide-y divide-hairline">
                  {paths.map((cf, i) => (
                    <Path key={i} cf={cf} from={score.default_probability} threshold={score.threshold} />
                  ))}
                </ul>
              )}
              {paths.length === 0 && searching && <p className="text-muted">The search is running.</p>}
              {paths.length === 0 && !searching && (
                <p className="max-w-2xl text-lg text-soft">
                  No realistic change brings this file under the threshold.
                  {closest && ` With every permitted change applied, the risk would still be ${pct(closest.new_probability)}.`}
                </p>
              )}
              {attempts.length > 0 && (
                <ol className="mt-6 space-y-2 rounded-2xl bg-surface p-5 text-sm ring-1 ring-hairline">
                  {attempts.map((a, i) => (
                    <li key={a.seq} className="grid gap-x-4 gap-y-0.5 sm:grid-cols-[5.5rem_minmax(0,1fr)]">
                      <span className="font-medium">Attempt {i + 1}</span>
                      <span className="text-soft">
                        {a.reasoning}{' '}
                        <span className={verdicts[i]?.status === 'rejected' ? 'text-negative' : 'text-muted'}>
                          {verdicts[i]?.message ?? 'Waiting for the auditor.'}
                        </span>
                      </span>
                    </li>
                  ))}
                </ol>
              )}
            </Section>
          )}

          {fairness && (
            <Section title="Fairness check">
              <p className={`max-w-2xl text-lg ${fairness.flip_test_passed ? 'text-soft' : 'font-medium text-negative'}`}>
                {fairness.flip_test_passed
                  ? 'The decision stays the same when a protected attribute is changed and nothing else.'
                  : 'The decision changes when only a protected attribute is changed.'}
              </p>
              <ul className="mt-4 max-w-2xl divide-y divide-hairline">
                {Object.entries(fairness.metrics)
                  .filter(([k]) => k.startsWith('flip_delta_'))
                  .map(([k, v]) => (
                    <li key={k} className="flex justify-between gap-4 py-2.5">
                      <span>{PROTECTED_LABEL[k.replace('flip_delta_', '')] ?? k} changed</span>
                      <span className="num text-muted">
                        risk moves by {v >= 0 ? '+' : '−'}
                        {Math.abs(v * 100).toFixed(1)} points
                      </span>
                    </li>
                  ))}
              </ul>
            </Section>
          )}

          {decision && (
            <section className="settle">
              {decision.escalated ? (
                <ReviewPanel
                  reason={decision.escalation_reason ?? 'a rule required it'}
                  review={record?.review ?? null}
                  onSend={async (o, who, why) => setRecord(await sendReview(id, o, who, why))}
                />
              ) : (
                <div className="rounded-panel bg-ink p-7 text-white">
                  <p className="text-sm text-white/60">Closed by the agents, no human review needed</p>
                  <p className="mt-1 max-w-2xl text-xl font-medium leading-snug">{decision.summary}</p>
                </div>
              )}
            </section>
          )}
        </div>

        <aside className="space-y-10 lg:sticky lg:top-20 lg:self-start">
          {analysis && (
            <section className="settle">
              <h2 className="text-lg font-semibold">File check</h2>
              <p className="mt-2 text-sm text-soft">{analysis.note}</p>
              <div className="mt-4 flex gap-1.5" role="img" aria-label={`${Math.round((analysis.peer_default_rate ?? 0) * analysis.peer_count)} of ${analysis.peer_count} similar past applicants defaulted`}>
                {Array.from({ length: analysis.peer_count }, (_, i) => (
                  <span
                    key={i}
                    className={`h-3 w-3 rounded-full ${
                      i < Math.round((analysis.peer_default_rate ?? 0) * analysis.peer_count) ? 'bg-ink' : 'bg-hairline'
                    }`}
                  />
                ))}
              </div>
              <p className="mt-2 text-xs text-muted">Similar past applicants. Dark: defaulted.</p>
            </section>
          )}
          <section>
            <h2 className="mb-4 text-lg font-semibold">Audit trail</h2>
            <Trail events={events} running={!done} />
            {events.length > 0 && <p className="mt-4 text-xs text-muted">Select a step to see its tool calls.</p>}
          </section>
        </aside>
      </div>
    </>
  )
}
