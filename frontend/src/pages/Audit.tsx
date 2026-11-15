import { ChevronRight, Download, FileText, ListTree } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { FactorBars } from '../components/FactorBars'
import { Pipeline } from '../components/Pipeline'
import { RiskRuler } from '../components/RiskRuler'
import { Trail } from '../components/Trail'
import { WhatIf } from '../components/WhatIf'
import { Card, CardHeader, Pill, StatusPill, Tabs, buttonClass } from '../components/ui'
import { getAudit, getSchema, letterUrl, reportUrl, sendReview, streamEvents, traceUrl } from '../lib/api'
import { clock, dm, pct, pipelineView } from '../lib/format'
import { auditStatus } from '../lib/status'
import type { AgentEvent, AuditDecision, AuditRecord, Counterfactual, Decision, FairnessVerdict, Review, Schema } from '../types'

type Tab = 'overview' | 'recourse' | 'whatif' | 'fairness' | 'documents'

const PROTECTED_LABEL: Record<string, string> = { sex: 'Sex', foreign_worker: 'Foreign worker status', age: 'Age' }
const GROUP_NAME: Record<string, string> = { foreign: 'foreign workers', non_foreign: 'non-foreign workers', male: 'men', female: 'women' }
const groupName = (g: string) => GROUP_NAME[g] ?? `applicants aged ${g.replace('-', ' to ').replace('+', ' and over')}`
const sentence = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)
const similar = (s: number) => `${s >= 1 ? 100 : Math.min(99, Math.floor(s * 100))}%`

function Stamp({ decision, pending }: { decision: Decision; pending: boolean }) {
  const color = pending ? 'var(--color-caution)' : decision === 'approved' ? 'var(--color-positive)' : 'var(--color-negative)'
  const word = pending ? 'Review' : decision === 'approved' ? 'Approved' : 'Refused'
  return (
    <div
      className="stamp pointer-events-none select-none rounded-[10px] border-[3px] px-4 py-1.5 text-center"
      style={{ borderColor: color, color, boxShadow: `inset 0 0 0 2px var(--color-surface), inset 0 0 0 3.5px ${color}` }}
      aria-hidden="true"
    >
      <span className="block text-[22px] font-bold uppercase leading-none tracking-[0.12em]">{word}</span>
      <span className="mt-1 block text-[9.5px] font-semibold uppercase tracking-[0.2em] opacity-80">AgentForge audit</span>
    </div>
  )
}

function Path({ cf, from, threshold }: { cf: Counterfactual; from: number; threshold: number }) {
  return (
    <li className="px-5 py-4">
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2">
        <p className="max-w-xl text-[15px] font-medium leading-snug">{cf.statement}</p>
        <p className="num shrink-0 text-right">
          <span className="text-muted line-through decoration-faint">{pct(from)}</span>
          <span className="ml-2 text-[16px] font-semibold text-positive">{pct(cf.new_probability)}</span>
        </p>
      </div>
      <div className="mt-3 max-w-xl">
        <RiskRuler value={from} to={cf.new_probability} threshold={threshold} compact />
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        <Pill tone={cf.effort === 'immediate' ? 'positive' : 'accent'}>{cf.effort === 'immediate' ? 'Can be done now' : 'Takes time'}</Pill>
        <Pill tone="muted">{cf.source === 'dice' ? 'Found by DiCE' : 'Exhaustive search'}</Pill>
        {cf.robust && <Pill tone="muted">Robust margin</Pill>}
        {cf.plausibility && <Pill tone="muted">{pct(cf.plausibility.neighbours_repaid)} of nearest past applicants repaid</Pill>}
      </div>
    </li>
  )
}

function GroupFairness({ fairness }: { fairness: FairnessVerdict }) {
  if (!fairness.group_context?.length) return null
  const m = fairness.metrics
  return (
    <Card>
      <CardHeader title="How the model treats this applicant's groups">Fairlearn approval rates on the 200 held-out files. They describe the model, not this file.</CardHeader>
      <ul className="divide-y divide-hairline">
        {fairness.group_context.map((c) => (
          <li key={c.attribute} className="grid gap-x-4 gap-y-1 px-5 py-3.5 sm:grid-cols-[9rem_minmax(0,1fr)]">
            <span className="text-[13.5px] text-muted">{c.label}</span>
            <span>
              <span className="flex items-center gap-3">
                <span className="h-2 flex-1 rounded-full bg-hairline">
                  <span className={`block h-2 rounded-full ${c.disadvantaged ? 'bg-caution' : 'bg-ink'}`} style={{ width: `${c.approval_rate * 100}%` }} />
                </span>
                <span className="num w-10 text-right text-[13px] font-medium">{pct(c.approval_rate)}</span>
              </span>
              <span className="mt-1 block text-[13px] text-soft">
                {!c.comparable
                  ? 'Too few test files in the other group to compare.'
                  : c.gap > 0.005
                    ? sentence(`${groupName(c.group)} are approved ${(c.gap * 100).toFixed(0)} points less often than ${groupName(c.best_group)}.`)
                    : sentence(`${groupName(c.group)} are approved as often as the most approved group.`)}{' '}
                {c.comparable && (
                  <span className="num text-muted">
                    Largest gap {((m[`dp_diff_${c.attribute}`] ?? 0) * 100).toFixed(0)} pts, equalized odds {((m[`eo_diff_${c.attribute}`] ?? 0) * 100).toFixed(0)} pts.
                  </span>
                )}
              </span>
            </span>
          </li>
        ))}
      </ul>
      {fairness.notes.map((n) => (
        <p key={n} className="mx-5 mb-4 rounded-control bg-caution/10 px-4 py-3 text-[13px] text-caution">
          {n} Recorded for the reviewer; it does not change the decision.
        </p>
      ))}
    </Card>
  )
}

function ReviewPanel({ reason, review, onSend }: { reason: string; review: Review | null; onSend: (o: Decision, who: string, why: string) => Promise<void> }) {
  const [who, setWho] = useState('')
  const [why, setWhy] = useState('')
  const [busy, setBusy] = useState<Decision | null>(null)
  const [error, setError] = useState<string | null>(null)

  if (review)
    return (
      <Card className="p-5">
        <p className="text-[12.5px] text-muted">Reviewed at {clock(review.at)}</p>
        <p className="mt-1 text-[18px] font-semibold">
          {review.outcome === 'approved' ? 'Approved' : 'Refused'} by {review.reviewer}
        </p>
        {review.comment && <p className="mt-2 max-w-2xl text-soft">{review.comment}</p>}
      </Card>
    )

  async function send(outcome: Decision) {
    setBusy(outcome)
    setError(null)
    try {
      await onSend(outcome, who.trim() || 'Reviewer', why.trim())
    } catch {
      setError('The decision was not saved. Check that the API is running, then choose again.')
    }
    setBusy(null)
  }
  const input = 'w-full rounded-control border border-hairline bg-surface px-3 py-2 text-[14px] focus:border-accent focus:outline-none'
  return (
    <div className="settle rounded-panel border border-caution/40 bg-caution/[0.06] p-5">
      <Pill tone="caution">A person decides this file</Pill>
      <p className="mt-3 max-w-2xl text-[17px] font-semibold leading-snug">The agents stopped because {reason}.</p>
      <div className="mt-4 grid gap-3 sm:grid-cols-[12rem_minmax(0,1fr)]">
        <label className="text-[13px] text-soft">
          Reviewer
          <input className={`${input} mt-1`} value={who} onChange={(e) => setWho(e.target.value)} placeholder="Name" />
        </label>
        <label className="text-[13px] text-soft">
          Reason for the decision
          <input className={`${input} mt-1`} value={why} onChange={(e) => setWhy(e.target.value)} placeholder="Recorded in the report" />
        </label>
      </div>
      {error && <p className="mt-3 text-[13px] text-negative">{error}</p>}
      <div className="mt-4 flex flex-wrap gap-2">
        <button onClick={() => send('approved')} disabled={busy !== null} className={buttonClass('dark')}>
          {busy === 'approved' ? 'Saving' : 'Approve the loan'}
        </button>
        <button onClick={() => send('refused')} disabled={busy !== null} className={buttonClass('secondary')}>
          {busy === 'refused' ? 'Saving' : 'Refuse the loan'}
        </button>
      </div>
    </div>
  )
}

function Documents({ id, decision }: { id: string; decision: AuditDecision }) {
  const draft = decision.letter_status === 'draft'
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card>
        <CardHeader
          title="Applicant letter"
          aside={<Pill tone={draft ? 'caution' : 'positive'}>{draft ? 'Draft, sent after review' : 'Final'}</Pill>}
        >
          In French, written by the Arbitre et Rédacteur
        </CardHeader>
        <div className="p-5">
          <div className="rounded-md border border-hairline bg-white px-7 py-8 text-[13.5px] leading-relaxed text-[#1f2633] shadow-lift" lang="fr">
            <p className="whitespace-pre-line">{decision.letter || 'No letter for this audit.'}</p>
          </div>
          <a href={letterUrl(id)} className={`${buttonClass('secondary', 'sm')} mt-4`}>
            <Download size={13} /> Download as text
          </a>
        </div>
      </Card>
      <Card>
        <CardHeader title="Audit report" aside={decision.report_id ?? undefined}>
          {draft ? 'Interim: issued again with the reviewer decision' : 'PDF with every step, figure and tool call'}
        </CardHeader>
        <div className="p-5">
          <iframe title="Audit report" src={reportUrl(id)} className="h-[520px] w-full rounded-md border border-hairline bg-white" />
          <div className="mt-4 flex flex-wrap gap-2">
            <a href={reportUrl(id)} className={buttonClass('primary', 'sm')}>
              <Download size={13} /> Download PDF
            </a>
            <a href={traceUrl(id)} className={buttonClass('secondary', 'sm')}>
              <ListTree size={13} /> Trace (JSONL)
            </a>
          </div>
        </div>
      </Card>
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
  const [tab, setTab] = useState<Tab>('overview')

  useEffect(() => {
    setEvents([])
    setDone(false)
    setMissing(false)
    setRecord(null)
    setTab('overview')
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
      <Card className="mx-auto mt-10 max-w-lg p-8 text-center">
        <h1 className="text-[20px] font-semibold">This audit does not exist</h1>
        <p className="mt-2 text-muted">No audit is stored under this address.</p>
        <Link to="/app/audits" className={`${buttonClass('primary')} mt-5`}>
          Open the audits
        </Link>
      </Card>
    )

  const app = record?.application
  const analysis = last('analysis')
  const score = last('score')
  const fairness = last('fairness')
  const decision = record?.result ?? last('decision')
  const scoreEvent = events.find((e) => e.node === 'modele_scoring')
  const attempts = events.filter((e) => e.node === 'generateur_contrefactuels')
  const verdicts = events.filter((e) => e.node === 'verificateur_equite')
  const paths = decision?.counterfactuals ?? verdicts.at(-1)?.payload.counterfactuals ?? []
  const searching = !done && score?.decision === 'refused' && !decision
  const closest = attempts.at(-1)?.payload.counterfactuals?.find((c) => !c.valid && c.actionable)
  const purpose = schema?.features.find((f) => f.name === 'purpose')?.options.find((o) => o.value === app?.purpose)?.label
  const failure = events.find((e) => e.status === 'error')
  const tone = score?.decision === 'refused' ? 'text-negative' : 'text-positive'
  const status = record ? auditStatus({ ...record, done: done && record.status !== 'running' ? true : record.done }) : null
  const pending = record?.status === 'awaiting_review'
  const llmSteps = events.filter((e) => e.mode === 'llm').length

  const tabs: { id: Tab; label: string; count?: number }[] = [
    { id: 'overview', label: 'Overview' },
    ...(score?.decision === 'refused' ? [{ id: 'recourse' as Tab, label: 'Ways to approval', count: paths.length }] : []),
    ...(score ? [{ id: 'whatif' as Tab, label: 'What-if simulator' }] : []),
    ...(fairness ? [{ id: 'fairness' as Tab, label: 'Fairness' }] : []),
    ...(decision && done ? [{ id: 'documents' as Tab, label: 'Documents' }] : []),
  ]

  return (
    <>
      <nav className="mb-3 flex items-center gap-1 text-[13px] text-muted" aria-label="Breadcrumb">
        <Link to="/app/audits" className="hover:text-ink">
          Audits
        </Link>
        <ChevronRight size={13} />
        <span className="text-soft">{app?.applicant_id ?? '...'}</span>
      </nav>
      <header className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-[26px] font-semibold leading-tight">Applicant {app?.applicant_id ?? ''}</h1>
            {status && <StatusPill status={status} />}
          </div>
          {app && (
            <p className="mt-1 text-muted">
              {dm(Number(app.credit_amount))} over {String(app.duration_months)} months{purpose ? `, ${purpose.toLowerCase()}` : ''}
              {llmSteps > 0 && <span className="text-faint"> ({llmSteps} of {events.length} steps written by the language model)</span>}
            </p>
          )}
        </div>
        {decision && done && (
          <div className="flex flex-wrap gap-2">
            <a href={reportUrl(id)} className={buttonClass('secondary', 'sm')}>
              <FileText size={14} /> Report
            </a>
            <button onClick={() => setTab('documents')} className={buttonClass('secondary', 'sm')}>
              Letter
            </button>
            <Link to="/app/new" className={buttonClass('primary', 'sm')}>
              New audit
            </Link>
          </div>
        )}
      </header>

      <Card className="px-3 pb-3 pt-4 sm:px-6">
        <Pipeline view={view} maxAttempts={schema?.max_attempts ?? 3} />
      </Card>

      {failure && <p className="mt-4 rounded-control bg-negative/10 px-4 py-3 text-[13.5px] text-negative">The audit stopped on an error: {failure.message}</p>}

      <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0">
          <Tabs<Tab> tabs={tabs} value={tab} onChange={setTab} />
          <div className="mt-5 space-y-4">
            {tab === 'overview' && (
              <>
                {decision?.escalated && (
                  <ReviewPanel
                    reason={decision.escalation_reason ?? 'a rule required it'}
                    review={record?.review ?? null}
                    onSend={async (o, who, why) => {
                      const updated = await sendReview(id, o, who, why)
                      setRecord(updated)
                      setEvents(updated.events)
                    }}
                  />
                )}
                {!score && !failure && (
                  <Card className="p-6">
                    <div className="skeleton h-12 w-40" />
                    <div className="skeleton mt-4 h-3" />
                    <p className="mt-4 text-[13.5px] text-muted">The Analyste-Dossier is checking the file before it is scored.</p>
                  </Card>
                )}
                {score && (
                  <Card className="settle relative overflow-hidden p-6">
                    <div className="flex flex-wrap items-start justify-between gap-6">
                      <div>
                        <p className="text-[13px] text-muted">Estimated risk of default</p>
                        <p className={`num mt-1 text-[64px] font-semibold leading-none tracking-tighter ${tone}`}>{pct(score.default_probability)}</p>
                      </div>
                      {decision && <Stamp decision={record?.review?.outcome ?? decision.final_outcome ?? decision.decision} pending={pending} />}
                    </div>
                    <div className="mt-6">
                      <RiskRuler value={score.default_probability} threshold={score.threshold} margin={schema?.borderline_margin} />
                    </div>
                    <p className="mt-5 max-w-2xl text-[15.5px] leading-relaxed text-soft">{last('explanation')}</p>
                    <p className="mt-2 text-[12.5px] text-muted">
                      {scoreEvent?.mode === 'llm'
                        ? 'Written by the language model, accepted only after its factors and numbers were checked against SHAP.'
                        : 'Rule-based wording from the SHAP values.'}
                    </p>
                  </Card>
                )}
                {score && (
                  <Card>
                    <CardHeader title="What drives the score" aside="Exact SHAP contributions, log-odds" />
                    <div className="px-5 pb-4">
                      <FactorBars factors={score.top_factors} />
                    </div>
                  </Card>
                )}
                {decision && !decision.escalated && (
                  <div className="settle rounded-panel bg-ink p-5 text-canvas">
                    <p className="text-[12.5px] opacity-60">Closed by the agents, no human review needed</p>
                    <p className="mt-1 max-w-2xl text-[16px] font-medium leading-snug">{decision.summary}</p>
                  </div>
                )}
                {decision?.precedent_conflict && <p className="text-[13px] text-caution">Consistency with past audits: {decision.precedent_conflict}.</p>}
              </>
            )}

            {tab === 'recourse' && score && (
              <>
                <Card>
                  <CardHeader
                    title="Verified ways to approval"
                    aside={paths.length > 0 ? `${paths.length} after ${attempts.length} attempt${attempts.length > 1 ? 's' : ''}` : undefined}
                  >
                    Re-scored by the model and audited for realism and fairness
                  </CardHeader>
                  {paths.length > 0 && (
                    <ul className="divide-y divide-hairline">
                      {paths.map((cf, i) => (
                        <Path key={i} cf={cf} from={score.default_probability} threshold={score.threshold} />
                      ))}
                    </ul>
                  )}
                  {paths.length === 0 && (
                    <p className="px-5 py-5 text-soft">
                      {searching
                        ? 'The search is running.'
                        : `No realistic change brings this file under the threshold.${closest ? ` With every permitted change applied, the risk would still be ${pct(closest.new_probability)}.` : ''}`}
                    </p>
                  )}
                </Card>
                {attempts.length > 0 && (
                  <Card>
                    <CardHeader title="Search attempts">The generator plans, the auditor rejects what is unrealistic or unfair, and the loop widens the search</CardHeader>
                    <ol className="divide-y divide-hairline">
                      {attempts.map((a, i) => (
                        <li key={a.seq} className="grid gap-x-4 gap-y-1 px-5 py-3.5 text-[13.5px] sm:grid-cols-[6rem_minmax(0,1fr)]">
                          <span className="font-medium">Attempt {i + 1}</span>
                          <span className="text-soft">
                            {a.reasoning}{' '}
                            <span className={verdicts[i]?.status === 'rejected' ? 'text-negative' : 'text-muted'}>{verdicts[i]?.message ?? 'Waiting for the auditor.'}</span>
                          </span>
                        </li>
                      ))}
                    </ol>
                  </Card>
                )}
              </>
            )}

            {tab === 'whatif' && score && app && schema && (
              <Card className="p-5">
                <WhatIf application={app} schema={schema} base={score} paths={paths} />
              </Card>
            )}

            {tab === 'fairness' && fairness && (
              <>
                <Card>
                  <CardHeader title="Flip test">The decision is computed again with one protected attribute changed and nothing else</CardHeader>
                  <div className="px-5 py-4">
                    <Pill tone={fairness.flip_test_passed ? 'positive' : 'negative'}>
                      {fairness.flip_test_passed ? 'Decision unchanged' : 'Decision changes with a protected attribute'}
                    </Pill>
                    <ul className="mt-3 divide-y divide-hairline">
                      {Object.entries(fairness.metrics)
                        .filter(([k]) => k.startsWith('flip_delta_'))
                        .map(([k, v]) => (
                          <li key={k} className="flex justify-between gap-4 py-2.5 text-[14px]">
                            <span>{PROTECTED_LABEL[k.replace('flip_delta_', '')] ?? k} changed</span>
                            <span className="num text-muted">
                              risk moves by {v >= 0 ? '+' : '−'}
                              {Math.abs(v * 100).toFixed(1)} points
                            </span>
                          </li>
                        ))}
                    </ul>
                    {fairness.verdict && <p className="mt-3 text-[13px] text-muted">Auditor's verdict: {fairness.verdict}</p>}
                  </div>
                </Card>
                <GroupFairness fairness={fairness} />
              </>
            )}

            {tab === 'documents' && decision && done && <Documents id={id} decision={decision} />}
          </div>
        </div>

        <aside className="space-y-4 xl:sticky xl:top-20 xl:self-start">
          <Card>
            <CardHeader title="Agent activity" aside={!done ? <Pill tone="accent" live>Live</Pill> : `${events.length} steps`} />
            <div className="max-h-[560px] overflow-y-auto px-5 py-4">
              <Trail events={events} running={!done} />
            </div>
          </Card>
          {analysis && (
            <Card className="settle">
              <CardHeader title="File check" />
              <div className="px-5 py-4">
                <p className="text-[13.5px] text-soft">{analysis.note}</p>
                <div
                  className="mt-3 flex flex-wrap gap-1.5"
                  role="img"
                  aria-label={`${Math.round((analysis.peer_default_rate ?? 0) * analysis.peer_count)} of ${analysis.peer_count} similar past applicants defaulted`}
                >
                  {Array.from({ length: analysis.peer_count }, (_, i) => (
                    <span key={i} className={`h-2.5 w-2.5 rounded-full ${i < Math.round((analysis.peer_default_rate ?? 0) * analysis.peer_count) ? 'bg-ink' : 'bg-hairline'}`} />
                  ))}
                </div>
                <p className="mt-1.5 text-[12px] text-muted">Similar past applicants. Dark: defaulted.</p>
                {analysis.precedents?.length > 0 && (
                  <div className="mt-4 border-t border-hairline pt-3">
                    <p className="text-[12.5px] font-medium text-soft">Similar files already audited</p>
                    <ul className="mt-1.5 space-y-1 text-[13px]">
                      {analysis.precedents.map((p) => (
                        <li key={p.run_id} className="flex justify-between gap-2">
                          <Link to={`/app/audit/${p.run_id}`} className="text-accent-ink hover:underline">
                            {p.applicant_id}
                          </Link>
                          <span className="num text-muted">
                            {similar(p.similarity)} similar, {p.final_outcome}
                            {p.reviewed ? ' by a reviewer' : ''}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </Card>
          )}
        </aside>
      </div>
    </>
  )
}
