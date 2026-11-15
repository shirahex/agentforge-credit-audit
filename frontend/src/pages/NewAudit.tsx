import { ArrowRight, Loader2 } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, PageHeader, buttonClass } from '../components/ui'
import { getSamples, getSchema, scoreFile, startAudit } from '../lib/api'
import { pct } from '../lib/format'
import type { FeatureSpec, LoanApplication, Sample, Schema, ScoreResult, Value } from '../types'

const CONTROL =
  'h-9 w-full rounded-control border border-hairline bg-surface px-3 text-[14px] transition-colors hover:border-faint focus:border-accent focus:outline-none'

const ROUTE_TONE: Record<string, string> = {
  terms: 'bg-positive',
  second_attempt: 'bg-accent',
  approved: 'bg-positive',
  borderline: 'bg-caution',
  sensitive: 'bg-caution',
  no_path: 'bg-negative',
}

function Field({ spec, value, onChange }: { spec: FeatureSpec; value: Value; onChange: (v: Value) => void }) {
  const id = `f-${spec.name}`
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 flex items-baseline justify-between gap-2 text-[13px] text-soft">
        <span>{spec.label}</span>
        {spec.protected && <span className="rounded bg-caution/12 px-1.5 text-[11px] font-medium text-caution">Protected</span>}
      </label>
      {spec.kind === 'categorical' && (
        <select id={id} className={CONTROL} value={String(value)} onChange={(e) => onChange(e.target.value)}>
          {spec.options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      )}
      {spec.kind === 'numeric' && (
        <div className="relative">
          <input
            id={id}
            type="number"
            className={`${CONTROL} num ${spec.unit && !spec.unit.startsWith('level') ? 'pr-16' : ''}`}
            value={Number(value)}
            min={spec.min ?? undefined}
            max={spec.max ?? undefined}
            onChange={(e) => onChange(e.target.value === '' ? 0 : Number(e.target.value))}
          />
          {spec.unit && !spec.unit.startsWith('level') && (
            <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[13px] text-faint">{spec.unit}</span>
          )}
        </div>
      )}
      {spec.kind === 'boolean' && (
        <button id={id} type="button" role="switch" aria-checked={Boolean(value)} onClick={() => onChange(!value)} className="flex h-9 items-center gap-3">
          <span className={`relative h-5 w-9 rounded-full transition-colors ${value ? 'bg-accent' : 'bg-hairline'}`}>
            <span
              className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-transform ${value ? 'translate-x-[18px]' : 'translate-x-0.5'}`}
            />
          </span>
          <span className="text-[14px]">{value ? 'Yes' : 'No'}</span>
        </button>
      )}
    </div>
  )
}

/** Score of the file as it is typed, from the model alone, before any agent runs. */
function Preview({ score, loading }: { score: ScoreResult | null; loading: boolean }) {
  if (!score) return <div className="skeleton h-16" />
  const refused = score.decision === 'refused'
  const tone = refused ? 'text-negative' : 'text-positive'
  return (
    <div>
      <div className="flex items-end justify-between">
        <div>
          <p className="text-[12.5px] text-muted">Model score, before the audit</p>
          <p className={`num text-[40px] font-semibold leading-none tracking-tight ${tone}`}>{pct(score.default_probability)}</p>
        </div>
        <div className="pb-1 text-right">
          {loading && <Loader2 size={14} className="ml-auto animate-spin text-faint" />}
          <p className={`text-[14px] font-semibold ${tone}`}>{refused ? 'Would be refused' : 'Would be approved'}</p>
          <p className="num text-[12.5px] text-muted">threshold {pct(score.threshold)}</p>
        </div>
      </div>
      <div className="relative mt-3 h-2 rounded-full bg-hairline">
        <span
          className={`absolute inset-y-0 left-0 rounded-full transition-all duration-500 ${refused ? 'bg-negative' : 'bg-positive'}`}
          style={{ width: `${score.default_probability * 100}%` }}
        />
        <span className="absolute -top-1 h-4 w-0.5 rounded bg-ink" style={{ left: `${score.threshold * 100}%` }} />
      </div>
      <ul className="mt-4 space-y-1.5 text-[13px]">
        {score.top_factors.slice(0, 3).map((f) => (
          <li key={f.feature} className="flex justify-between gap-3">
            <span className="truncate text-soft">
              {f.label}: <span className="text-muted">{f.value_label}</span>
            </span>
            <span className={`num shrink-0 font-medium ${f.contribution > 0 ? 'text-negative' : 'text-positive'}`}>
              {f.contribution > 0 ? '+' : '−'}
              {Math.abs(f.contribution).toFixed(2)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function NewAudit() {
  const navigate = useNavigate()
  const [schema, setSchema] = useState<Schema | null>(null)
  const [samples, setSamples] = useState<Sample[]>([])
  const [tag, setTag] = useState<string | null>(null)
  const [form, setForm] = useState<LoanApplication | null>(null)
  const [score, setScore] = useState<ScoreResult | null>(null)
  const [scoring, setScoring] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const debounce = useRef<ReturnType<typeof setTimeout>>(undefined)

  useEffect(() => {
    Promise.all([getSchema(), getSamples()])
      .then(([sc, sa]) => {
        setSchema(sc)
        setSamples(sa)
        if (sa[0]) {
          setTag(sa[0].tag)
          setForm(sa[0].application)
        }
      })
      .catch(() => setError('The applicant form could not be loaded because the API does not answer.'))
  }, [])

  useEffect(() => {
    if (!form) return
    clearTimeout(debounce.current)
    setScoring(true)
    debounce.current = setTimeout(() => {
      scoreFile(form)
        .then(setScore)
        .catch(() => {})
        .finally(() => setScoring(false))
    }, 220)
    return () => clearTimeout(debounce.current)
  }, [form])

  const groups = useMemo(() => {
    const out: [string, FeatureSpec[]][] = []
    for (const f of schema?.features ?? []) {
      const g = out.find(([name]) => name === f.group)
      if (g) g[1].push(f)
      else out.push([f.group, [f]])
    }
    return out
  }, [schema])

  async function run(e?: React.FormEvent) {
    e?.preventDefault()
    if (!form) return
    setBusy(true)
    setError(null)
    try {
      navigate(`/app/audit/${await startAudit(form)}`)
    } catch (err) {
      setError(`The audit could not start. ${err instanceof Error ? err.message : ''}`)
      setBusy(false)
    }
  }

  return (
    <>
      <PageHeader
        title="New audit"
        sub="Start from one of six real applicants of the held-out test set, or edit any field. The score on the right updates as you type."
      />
      {error && <p className="mb-6 rounded-control bg-negative/10 px-4 py-3 text-[13.5px] text-negative">{error}</p>}

      <section aria-label="Sample files" className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
        {samples.map((s) => {
          const on = s.tag === tag
          return (
            <button
              key={s.tag}
              type="button"
              onClick={() => {
                setTag(s.tag)
                setForm(s.application)
                setError(null)
              }}
              aria-pressed={on}
              className={`group relative overflow-hidden rounded-panel border p-4 text-left transition ${
                on ? 'border-accent bg-surface shadow-lift ring-1 ring-accent' : 'border-hairline bg-surface/70 hover:-translate-y-px hover:bg-surface hover:shadow-lift'
              }`}
            >
              <span className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-2 text-[14px] font-medium">
                  <span className={`h-2 w-2 rounded-full ${ROUTE_TONE[s.tag] ?? 'bg-faint'}`} />
                  {s.title}
                </span>
                <span className="num text-[12px] text-faint">{s.application.applicant_id}</span>
              </span>
              <span className="mt-1.5 block text-[13px] leading-snug text-muted">{s.description}</span>
            </button>
          )
        })}
      </section>

      <div className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <form id="applicant-form" onSubmit={run} className="space-y-4">
          {!form && !error && <div className="skeleton h-64" />}
          {form &&
            groups.map(([name, fields]) => (
              <Card key={name}>
                <fieldset className="p-5">
                  <legend className="sr-only">{name}</legend>
                  <h2 className="mb-4 text-[14px] font-semibold">{name}</h2>
                  <div className="grid gap-x-4 gap-y-3.5 sm:grid-cols-2 xl:grid-cols-3">
                    {fields.map((f) => (
                      <Field
                        key={f.name}
                        spec={f}
                        value={form[f.name]}
                        onChange={(v) => {
                          setForm({ ...form, [f.name]: v, applicant_id: 'CUSTOM' })
                          setTag(null)
                        }}
                      />
                    ))}
                  </div>
                </fieldset>
              </Card>
            ))}
        </form>

        <aside className="lg:sticky lg:top-20 lg:self-start">
          <Card className="p-5">
            <Preview score={score} loading={scoring} />
            <button form="applicant-form" type="submit" disabled={!form || busy} className={`${buttonClass('primary')} mt-5 h-10 w-full`}>
              {busy ? (
                <>
                  <Loader2 size={15} className="animate-spin" /> Starting the agents
                </>
              ) : (
                <>
                  Run the five agents <ArrowRight size={15} />
                </>
              )}
            </button>
            <p className="mt-3 text-[12.5px] leading-relaxed text-muted">
              The audit explains the score, searches for a realistic way to approval when the file is refused, tests the decision for fairness and writes
              the report and the applicant letter.
            </p>
          </Card>
        </aside>
      </div>
    </>
  )
}
