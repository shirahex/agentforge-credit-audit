import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getSamples, getSchema, startAudit } from '../lib/api'
import type { FeatureSpec, LoanApplication, Sample, Schema, Value } from '../types'

const CONTROL =
  'h-10 w-full rounded-control border border-hairline bg-surface px-3 text-[15px] transition-colors hover:border-faint focus:border-accent focus:outline-none'

function Field({ spec, value, onChange }: { spec: FeatureSpec; value: Value; onChange: (v: Value) => void }) {
  const id = `f-${spec.name}`
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 flex items-baseline justify-between gap-2 text-sm text-soft">
        <span>{spec.label}</span>
        {spec.protected && <span className="text-xs text-caution">Protected</span>}
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
            <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-faint">{spec.unit}</span>
          )}
        </div>
      )}
      {spec.kind === 'boolean' && (
        <button
          id={id}
          type="button"
          role="switch"
          aria-checked={Boolean(value)}
          onClick={() => onChange(!value)}
          className="flex h-10 items-center gap-3"
        >
          <span className={`relative h-6 w-10 rounded-full transition-colors ${value ? 'bg-accent' : 'bg-hairline'}`}>
            <span
              className={`absolute left-0 top-0.5 h-5 w-5 rounded-full bg-surface shadow-sm transition-transform ${
                value ? 'translate-x-[18px]' : 'translate-x-0.5'
              }`}
            />
          </span>
          <span className="text-[15px]">{value ? 'Yes' : 'No'}</span>
        </button>
      )}
    </div>
  )
}

export function NewAudit() {
  const navigate = useNavigate()
  const [schema, setSchema] = useState<Schema | null>(null)
  const [samples, setSamples] = useState<Sample[]>([])
  const [tag, setTag] = useState<string | null>(null)
  const [form, setForm] = useState<LoanApplication | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

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
      .catch(() => setError('The applicant form could not be loaded because the backend does not answer.'))
  }, [])

  const groups = useMemo(() => {
    const out: [string, FeatureSpec[]][] = []
    for (const f of schema?.features ?? []) {
      const g = out.find(([name]) => name === f.group)
      if (g) g[1].push(f)
      else out.push([f.group, [f]])
    }
    return out
  }, [schema])

  function pick(s: Sample) {
    setTag(s.tag)
    setForm(s.application)
    setError(null)
  }

  async function run(e: React.FormEvent) {
    e.preventDefault()
    if (!form) return
    setBusy(true)
    setError(null)
    try {
      navigate(`/audit/${await startAudit(form)}`)
    } catch (err) {
      setError(`The audit could not start. ${err instanceof Error ? err.message : ''}`)
      setBusy(false)
    }
  }

  return (
    <>
      <header className="max-w-3xl">
        <h1 className="text-5xl font-semibold leading-[1.05] sm:text-6xl">Audit a credit decision.</h1>
        <p className="mt-5 text-xl leading-snug text-muted">
          Five agents score a loan file, explain the score, look for a realistic way to approval and test the decision
          for fairness. Every figure comes from the model and its tools.
        </p>
      </header>

      {error && <p className="mt-8 rounded-control bg-negative/10 px-4 py-3 text-sm text-negative">{error}</p>}

      <div className="mt-14 grid gap-10 lg:grid-cols-[minmax(0,4fr)_minmax(0,7fr)]">
        <section aria-labelledby="files" className="lg:sticky lg:top-20 lg:self-start">
          <h2 id="files" className="text-xl font-semibold">
            Start from a real file
          </h2>
          <p className="mt-1 text-sm text-muted">
            Six applicants from the held-out test set, one for each route an audit can take.
          </p>
          <ul className="mt-5 space-y-1">
            {samples.map((s) => {
              const on = s.tag === tag
              return (
                <li key={s.tag}>
                  <button
                    type="button"
                    onClick={() => pick(s)}
                    aria-pressed={on}
                    className={`w-full rounded-2xl px-4 py-3 text-left transition-colors ${
                      on ? 'bg-surface shadow-[0_1px_2px_rgba(0,0,0,0.06)] ring-1 ring-hairline' : 'hover:bg-surface/60'
                    }`}
                  >
                    <span className="flex items-baseline justify-between gap-3">
                      <span className="font-medium">{s.title}</span>
                      <span className="num shrink-0 whitespace-nowrap text-xs text-faint">{s.application.applicant_id}</span>
                    </span>
                    <span className={`mt-0.5 block text-sm ${on ? 'text-soft' : 'text-muted'}`}>{s.description}</span>
                  </button>
                </li>
              )
            })}
          </ul>
        </section>

        <form id="applicant-form" onSubmit={run} className="rounded-panel bg-surface p-7 ring-1 ring-hairline sm:p-9" aria-labelledby="form">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 id="form" className="text-xl font-semibold">
                Applicant file
              </h2>
              <p className="mt-0.5 text-sm text-muted">Any value can be edited before the audit.</p>
            </div>
            <button
              type="submit"
              disabled={!form || busy}
              className="h-11 rounded-full bg-accent px-7 text-[15px] font-medium text-white transition hover:brightness-110 disabled:opacity-40"
            >
              {busy ? 'Starting the audit' : 'Run the audit'}
            </button>
          </div>
          {!form && !error && <p className="mt-6 text-sm text-muted">Loading the form.</p>}
          {form &&
            groups.map(([name, fields]) => (
              <fieldset key={name} className="mt-8">
                <legend className="mb-4 w-full border-b border-hairline pb-2 text-sm font-semibold">{name}</legend>
                <div className="grid gap-x-5 gap-y-4 sm:grid-cols-2">
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
            ))}
          <button
            type="submit"
            disabled={!form || busy}
            className="mt-9 h-12 w-full rounded-full bg-accent text-[15px] font-medium text-white transition hover:brightness-110 disabled:opacity-40"
          >
            {busy ? 'Starting the audit' : 'Run the audit'}
          </button>
        </form>
      </div>
    </>
  )
}
