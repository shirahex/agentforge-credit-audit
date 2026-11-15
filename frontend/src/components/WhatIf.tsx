import { Lock, RotateCcw } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { scoreFile } from '../lib/api'
import { pct } from '../lib/format'
import type { Counterfactual, FeatureSpec, LoanApplication, ScoreResult, Schema, Value } from '../types'
import { buttonClass } from './ui'

const STEP: Record<string, number> = { credit_amount: 50, duration_months: 1 }

/** Live simulator: change what the applicant can change and watch the model re-score the file. */
export function WhatIf({
  application,
  schema,
  base,
  paths,
}: {
  application: LoanApplication
  schema: Schema
  base: ScoreResult
  paths: Counterfactual[]
}) {
  const [file, setFile] = useState<LoanApplication>(application)
  const [score, setScore] = useState<ScoreResult>(base)
  const [busy, setBusy] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined)

  useEffect(() => {
    clearTimeout(timer.current)
    setBusy(true)
    timer.current = setTimeout(() => {
      scoreFile(file)
        .then(setScore)
        .catch(() => {})
        .finally(() => setBusy(false))
    }, 120)
    return () => clearTimeout(timer.current)
  }, [file])

  const set = (name: string, v: Value) => setFile((f) => ({ ...f, [name]: v }))
  const request = schema.features.filter((f) => f.recourse === 'request')
  const situation = schema.features.filter((f) => f.recourse === 'situation')
  const fixed = schema.features.filter((f) => f.recourse === 'fixed')
  const changed = schema.features.filter((f) => String(file[f.name]) !== String(application[f.name]))
  const refused = score.default_probability >= score.threshold
  const delta = score.default_probability - base.default_probability

  const slider = (f: FeatureSpec) => {
    const lo = f.min ?? 0
    // Recourse never asks for more: the amount and the duration can only go down.
    const hi = Number(application[f.name])
    return (
      <div key={f.name}>
        <div className="mb-1.5 flex items-baseline justify-between text-[13px]">
          <label htmlFor={`w-${f.name}`} className="text-soft">
            {f.label}
          </label>
          <span className="num font-medium">
            {Number(file[f.name]).toLocaleString('en-US')} {f.unit}
          </span>
        </div>
        <input
          id={`w-${f.name}`}
          type="range"
          className="w-full"
          min={lo}
          max={hi}
          step={STEP[f.name] ?? 1}
          value={Number(file[f.name])}
          onChange={(e) => set(f.name, Number(e.target.value))}
        />
        <div className="flex justify-between text-[11.5px] text-faint">
          <span className="num">{lo.toLocaleString('en-US')}</span>
          <span>requested: {hi.toLocaleString('en-US')}</span>
        </div>
      </div>
    )
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
      <div className="space-y-6">
        <section>
          <h3 className="text-[14px] font-semibold">The request</h3>
          <p className="mb-4 text-[13px] text-muted">Can change today. Amount and duration only go down.</p>
          <div className="grid gap-5 sm:grid-cols-2">
            {request.filter((f) => f.kind === 'numeric').map(slider)}
            {request
              .filter((f) => f.kind !== 'numeric')
              .map((f) => (
                <Choice key={f.name} spec={f} value={file[f.name]} original={application[f.name]} onChange={(v) => set(f.name, v)} />
              ))}
          </div>
        </section>
        <section>
          <h3 className="text-[14px] font-semibold">The financial situation</h3>
          <p className="mb-4 text-[13px] text-muted">Takes time to change.</p>
          <div className="grid gap-x-4 gap-y-3.5 sm:grid-cols-2">
            {situation.map((f) =>
              f.kind === 'numeric' ? (
                slider(f)
              ) : (
                <Choice key={f.name} spec={f} value={file[f.name]} original={application[f.name]} onChange={(v) => set(f.name, v)} />
              ),
            )}
          </div>
        </section>
        <section>
          <h3 className="flex items-center gap-1.5 text-[14px] font-semibold">
            <Lock size={13} /> Not changeable
          </h3>
          <p className="mt-1 text-[13px] text-muted">
            {fixed.map((f) => f.label.toLowerCase()).join(', ')}. Protected attributes and history are never part of a recommendation.
          </p>
        </section>
      </div>

      <aside className="lg:sticky lg:top-20 lg:self-start">
        <div className={`rounded-panel border p-5 transition-colors ${refused ? 'border-hairline bg-raised' : 'border-positive/40 bg-positive/[0.06]'}`}>
          <p className="text-[12.5px] text-muted">Default risk with these changes</p>
          <div className="mt-1 flex items-end justify-between">
            <p className={`num text-[44px] font-semibold leading-none tracking-tight ${refused ? 'text-negative' : 'text-positive'}`}>
              {pct(score.default_probability)}
            </p>
            <p className={`num pb-1 text-[13px] font-medium ${delta <= 0 ? 'text-positive' : 'text-negative'}`}>
              {delta === 0 ? 'no change' : `${delta < 0 ? '−' : '+'}${Math.abs(delta * 100).toFixed(1)} pts`}
            </p>
          </div>
          <div className="relative mt-4 h-2 rounded-full bg-hairline">
            <span className="absolute -top-1 h-4 w-0.5 rounded bg-ink" style={{ left: `${score.threshold * 100}%` }} />
            <span className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-ink bg-surface" style={{ left: `${base.default_probability * 100}%` }} />
            <span
              className={`absolute top-1/2 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-surface shadow transition-[left] duration-300 ${
                refused ? 'bg-negative' : 'bg-positive'
              }`}
              style={{ left: `${Math.min(100, score.default_probability * 100)}%` }}
            />
          </div>
          <p className={`mt-4 text-[15px] font-semibold ${refused ? 'text-negative' : 'text-positive'}`}>
            {busy ? 'Re-scoring' : refused ? 'Still refused' : 'Approved by the model'}
          </p>
          <p className="mt-1 text-[12.5px] text-muted">
            {changed.length === 0 ? 'No change yet.' : `${changed.length} change${changed.length > 1 ? 's' : ''}: ${changed.map((f) => f.label.toLowerCase()).join(', ')}.`}{' '}
            Scored by the same model, without the agents.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <button className={buttonClass('secondary', 'sm')} onClick={() => setFile(application)} disabled={changed.length === 0}>
              <RotateCcw size={13} /> Reset
            </button>
          </div>
          {paths.length > 0 && (
            <div className="mt-5 border-t border-hairline pt-4">
              <p className="text-[12.5px] font-medium text-soft">Load a path verified by the agents</p>
              <ul className="mt-2 space-y-1.5">
                {paths.map((p, i) => (
                  <li key={i}>
                    <button
                      onClick={() => setFile({ ...application, ...Object.fromEntries(p.changes.map((c) => [c.feature, c.to_value])) })}
                      className="w-full rounded-control border border-hairline bg-surface px-3 py-2 text-left text-[12.5px] leading-snug text-soft transition hover:border-accent hover:text-ink"
                    >
                      <span className="num float-right ml-2 font-semibold text-positive">{pct(p.new_probability)}</span>
                      {p.statement}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </aside>
    </div>
  )
}

function Choice({ spec, value, original, onChange }: { spec: FeatureSpec; value: Value; original: Value; onChange: (v: Value) => void }) {
  const moved = String(value) !== String(original)
  if (spec.kind === 'boolean')
    return (
      <label className="flex items-center justify-between gap-3 text-[13px]">
        <span className="text-soft">{spec.label}</span>
        <button
          type="button"
          role="switch"
          aria-checked={Boolean(value)}
          onClick={() => onChange(!value)}
          className={`relative h-5 w-9 rounded-full transition-colors ${value ? 'bg-accent' : 'bg-hairline'}`}
        >
          <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-transform ${value ? 'translate-x-[18px]' : 'translate-x-0.5'}`} />
        </button>
      </label>
    )
  return (
    <div>
      <label htmlFor={`w-${spec.name}`} className="mb-1.5 flex justify-between text-[13px] text-soft">
        {spec.label}
        {moved && <span className="text-[11.5px] font-medium text-accent-ink">changed</span>}
      </label>
      <select
        id={`w-${spec.name}`}
        value={String(value)}
        onChange={(e) => onChange(e.target.value)}
        className={`h-9 w-full rounded-control border bg-surface px-3 text-[13.5px] outline-none focus:border-accent ${moved ? 'border-accent/60' : 'border-hairline'}`}
      >
        {spec.options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  )
}
