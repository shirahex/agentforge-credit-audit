import { useEffect, useState } from 'react'
import { Plot, polyline } from '../components/Plot'
import { getModelCard } from '../lib/api'
import { pct } from '../lib/format'
import type { AttributeFairness, AuditStats, FairnessComparison, ModelCard } from '../types'

const INK = 'var(--color-ink)'
const ACCENT = 'var(--color-accent)'
const FAINT = 'var(--color-faint)'
const f3 = (v: number) => v.toFixed(3)
const p0 = (v: number) => `${Math.round(v * 100)}%`

function Th({ children, right = false }: { children: React.ReactNode; right?: boolean }) {
  return <th className={`px-5 py-3 font-normal ${right ? 'text-right' : ''}`}>{children}</th>
}
function Td({ children, right = false, strong = false }: { children: React.ReactNode; right?: boolean; strong?: boolean }) {
  return <td className={`num px-5 py-3.5 ${right ? 'text-right' : ''} ${strong ? 'font-medium' : ''}`}>{children}</td>
}

function RecourseBar({ s }: { s: AuditStats }) {
  const parts = [
    { n: s.solved_attempt_1 ?? 0, label: 'Solved at attempt 1', color: 'var(--color-ink)' },
    { n: s.solved_attempt_2 ?? 0, label: 'attempt 2', color: 'var(--color-soft)' },
    { n: s.solved_attempt_3 ?? 0, label: 'attempt 3', color: 'var(--color-faint)' },
    { n: s.no_path ?? 0, label: 'No way to approval', color: 'var(--color-negative)' },
  ]
  return (
    <div>
      <div className="flex h-3 overflow-hidden rounded-full" role="img" aria-label={parts.map((p) => `${p.label}: ${p.n}`).join(', ')}>
        {parts.map((p) => (
          <span key={p.label} style={{ width: `${(p.n / s.refused) * 100}%`, background: p.color }} />
        ))}
      </div>
      <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-sm text-muted">
        {parts.map((p) => (
          <li key={p.label} className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full" style={{ background: p.color }} />
            {p.label} <span className="num text-ink">{p.n}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function GroupRates({ a }: { a: AttributeFairness }) {
  const small = Object.values(a.groups).some((g) => g.small_sample)
  const ci = a.ci95?.demographic_parity_difference
  return (
    <div>
      <ul className="space-y-2">
        {Object.entries(a.groups).map(([name, g]) => (
          <li key={name} className="grid grid-cols-[5.5rem_minmax(0,1fr)_5.5rem] items-center gap-3 text-sm">
            <span className="truncate">{name.replace('_', ' ')}</span>
            <span className="h-2 rounded-full bg-hairline">
              <span
                className={`block h-2 rounded-full ${g.small_sample ? 'bg-faint' : 'bg-ink'}`}
                style={{ width: `${g.selection_rate * 100}%` }}
              />
            </span>
            <span className="num text-right text-muted">
              {p0(g.selection_rate)} <span className="text-faint">n={g.n}</span>
            </span>
          </li>
        ))}
      </ul>
      <p className="num mt-3 text-sm">
        <span className={`font-medium ${a.alert ? 'text-caution' : ''}`}>
          Approval gap {(a.demographic_parity_difference * 100).toFixed(0)} points
        </span>
        {ci && (
          <span className="text-muted">
            {' '}
            (95% interval {(ci[0] * 100).toFixed(0)} to {(ci[1] * 100).toFixed(0)})
          </span>
        )}
      </p>
      <p className="num mt-0.5 text-sm text-muted">
        Ratio {a.demographic_parity_ratio.toFixed(2)}, equalized odds gap {(a.equalized_odds_difference * 100).toFixed(0)} points
        {small ? '. Too few files in one group to conclude.' : a.alert ? '. Above the tolerance.' : '.'}
      </p>
    </div>
  )
}

function FairnessSection({ f }: { f: FairnessComparison }) {
  return (
    <section className="mt-16">
      <h2 className="text-[18px] font-semibold">Fairness across groups</h2>
      <p className="mt-2 max-w-3xl text-muted">
        Share of files approved in each group of the {f.full.files} test files, computed with Fairlearn. The approval gap
        is the demographic parity difference; the equalized odds gap compares how often good payers, and bad payers, are
        approved in each group. The right column is a model that never sees sex, age or foreign-worker status: what it
        still shows reaches the decision through correlated attributes.
      </p>
      <div className="mt-6 overflow-x-auto card">
        <table className="w-full min-w-[44rem] text-left">
          <thead className="border-b border-hairline text-sm text-muted">
            <tr>
              <Th> </Th>
              <Th>Audited model</Th>
              <Th>Without protected attributes</Th>
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline">
            {Object.keys(f.full.attributes).map((key) => (
              <tr key={key} className="align-top">
                <td className="px-5 py-5 font-medium">{f.full.attributes[key].label}</td>
                <td className="px-5 py-5">
                  <GroupRates a={f.full.attributes[key]} />
                </td>
                <td className="px-5 py-5">
                  <GroupRates a={f.unaware.attributes[key]} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="mt-4 max-w-3xl space-y-1.5 text-sm text-soft">
        {f.reading.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      <p className="mt-3 max-w-3xl text-sm text-muted">
        A gap above {(f.tolerance * 100).toFixed(0)} points between groups of at least {f.min_group} files is reported as a
        disparity. The ratio is the lowest approval rate divided by the highest; the four-fifths rule asks for 0.80 or
        more. With 200 files the intervals are wide.
      </p>
    </section>
  )
}

export function Model() {
  const [card, setCard] = useState<ModelCard | null>(null)
  const [error, setError] = useState(false)
  useEffect(() => {
    getModelCard().then(setCard).catch(() => setError(true))
  }, [])

  if (error) return <p className="text-sm text-negative">The model card could not be loaded because the backend does not answer.</p>
  if (!card) return <p className="text-muted">Loading the model card.</p>

  const { meta, comparison, summary } = card
  const t = meta.test
  const full = summary?.audit.full
  const unaware = summary?.audit.unaware
  const maxShap = Math.max(...(summary?.shap_importance.map((s) => s.value) ?? [1]))
  const histMax = summary ? Math.max(...summary.histogram.repaid.map((r, i) => r + summary.histogram.defaulted[i])) : 1
  const costMax = summary ? Math.ceil(Math.max(...summary.cost_curve.map((c) => c[1])) / 0.4) * 0.4 : 1

  return (
    <>
      <header className="max-w-3xl">
        <h1 className="text-[26px] font-semibold leading-tight">Model and fairness</h1>
        <p className="mt-1 text-muted">
          A calibrated LightGBM model trained on {meta.data.train_rows} German Credit files and tested on {meta.data.test_rows}{' '}
          it never saw. Predicted risk can only grow with the duration, the amount and the instalment rate, so a smaller
          request never scores worse.
        </p>
        <p className="num mt-2 text-sm text-faint">{meta.version}</p>
      </header>

      <section className="mt-10">
        <h2 className="text-[18px] font-semibold">Accuracy on the test set</h2>
        <div className="mt-5 overflow-x-auto card">
          <table className="w-full min-w-[36rem] text-left">
            <thead className="border-b border-hairline text-sm text-muted">
              <tr>
                <Th>Model</Th>
                <Th right>Cross-validation AUC</Th>
                <Th right>Test AUC</Th>
                <Th right>95% interval</Th>
                <Th right>KS</Th>
                <Th right>Brier</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              <tr>
                <Td strong>LightGBM, retained</Td>
                <Td right>{f3(meta.cv.lightgbm_auc)}</Td>
                <Td right strong>{f3(t.auc)}</Td>
                <Td right>
                  {f3(t.auc_ci95[0])} to {f3(t.auc_ci95[1])}
                </Td>
                <Td right>{f3(t.ks)}</Td>
                <Td right>{f3(t.brier)}</Td>
              </tr>
              <tr className="text-muted">
                <Td>Logistic regression, baseline</Td>
                <Td right>{f3(meta.cv.baseline_logreg_auc)}</Td>
                <Td right>{f3(meta.test_baseline_logreg.auc)}</Td>
                <Td right> </Td>
                <Td right>{f3(meta.test_baseline_logreg.ks)}</Td>
                <Td right>{f3(meta.test_baseline_logreg.brier)}</Td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="mt-3 max-w-2xl text-sm text-muted">
          Hyperparameters chosen among {meta.cv.configs_tried} configurations on {meta.cv.scheme}. With 200 test files
          the interval is wide: the ranking of the two models is reliable in cross-validation, less so on the test set
          alone.
        </p>
      </section>

      {summary && (
        <section className="mt-14 grid gap-x-10 gap-y-12 md:grid-cols-2">
          <Plot
            title="Ranking quality"
            xLabel="Good payers refused (false positive rate)"
            yLabel="Bad payers caught"
            xFormat={p0}
            yFormat={p0}
            legend={[
              { label: 'LightGBM', color: ACCENT },
              { label: 'Logistic regression', color: FAINT },
              { label: 'Chance', color: 'var(--color-hairline)', dashed: true },
            ]}
          >
            {(sx, sy) => (
              <>
                <line x1={sx(0)} y1={sy(0)} x2={sx(1)} y2={sy(1)} stroke="var(--color-faint)" strokeDasharray="3 4" strokeWidth="1" />
                <polyline points={polyline(summary.roc_baseline, sx, sy)} fill="none" stroke={FAINT} strokeWidth="1.5" />
                <polyline points={polyline(summary.roc, sx, sy)} fill="none" stroke={ACCENT} strokeWidth="2.25" />
              </>
            )}
          </Plot>

          <Plot
            title="Are the probabilities honest?"
            xLabel="Predicted default risk"
            yLabel="Defaults observed"
            xFormat={p0}
            yFormat={p0}
            legend={[
              { label: 'Model, by group of files', color: ACCENT },
              { label: 'Perfect calibration', color: 'var(--color-faint)', dashed: true },
            ]}
          >
            {(sx, sy) => (
              <>
                <line x1={sx(0)} y1={sy(0)} x2={sx(1)} y2={sy(1)} stroke="var(--color-faint)" strokeDasharray="3 4" strokeWidth="1" />
                <polyline
                  points={polyline(summary.calibration.map((c) => [c.predicted, c.observed]), sx, sy)}
                  fill="none"
                  stroke={ACCENT}
                  strokeWidth="2"
                />
                {summary.calibration.map((c) => (
                  <circle key={c.predicted} cx={sx(c.predicted)} cy={sy(c.observed)} r="3.5" fill="var(--color-surface)" stroke={ACCENT} strokeWidth="2" />
                ))}
              </>
            )}
          </Plot>

          <Plot
            title="Where the test files fall"
            xLabel="Predicted default risk"
            yLabel="Files"
            y={[0, Math.ceil(histMax / 8) * 8]}
            xFormat={p0}
            legend={[
              { label: 'Repaid', color: 'var(--color-faint)' },
              { label: 'Defaulted', color: INK },
              { label: `Threshold ${pct(meta.threshold)}`, color: ACCENT, dashed: true },
            ]}
          >
            {(sx, sy) => (
              <>
                {summary.histogram.repaid.map((r, i) => {
                  const x0 = sx(summary.histogram.edges[i]) + 1
                  const w = sx(summary.histogram.edges[i + 1]) - x0 - 1
                  const d = summary.histogram.defaulted[i]
                  return (
                    <g key={i}>
                      <rect x={x0} y={sy(r)} width={w} height={sy(0) - sy(r)} fill="var(--color-faint)" opacity="0.55" />
                      <rect x={x0} y={sy(r + d)} width={w} height={sy(0) - sy(d)} fill={INK} />
                    </g>
                  )
                })}
                <line x1={sx(meta.threshold)} x2={sx(meta.threshold)} y1={sy(0)} y2={10} stroke={ACCENT} strokeWidth="1.5" strokeDasharray="4 3" />
              </>
            )}
          </Plot>

          <Plot
            title="Cost of each possible threshold"
            xLabel="Refusal threshold"
            yLabel="Expected cost per file"
            y={[0, costMax]}
            xFormat={p0}
            yFormat={(v) => v.toFixed(1)}
            legend={Object.entries(meta.policies).map(([name, pol]) => ({
              label: `${name === 'balanced' ? 'Balanced, in use' : 'Cost-optimal'} ${pct(pol.threshold)}`,
              color: name === 'balanced' ? ACCENT : 'var(--color-muted)',
              dashed: true,
            }))}
          >
            {(sx, sy) => (
              <>
                <polyline points={polyline(summary.cost_curve, sx, sy)} fill="none" stroke={INK} strokeWidth="2" />
                {Object.entries(meta.policies).map(([name, pol]) => (
                  <line
                    key={name}
                    x1={sx(pol.threshold)}
                    x2={sx(pol.threshold)}
                    y1={sy(0)}
                    y2={10}
                    stroke={name === 'balanced' ? ACCENT : 'var(--color-muted)'}
                    strokeWidth="1.5"
                    strokeDasharray="4 3"
                  />
                ))}
              </>
            )}
          </Plot>
        </section>
      )}

      <section className="mt-16">
        <h2 className="text-[18px] font-semibold">Decision policy</h2>
        <p className="mt-2 max-w-2xl text-muted">
          The dataset states that approving a bad payer costs five times more than refusing a good one. Two thresholds
          are computed on out-of-fold predictions; the balanced one is in use.
        </p>
        <div className="mt-5 overflow-x-auto card">
          <table className="w-full min-w-[40rem] text-left">
            <thead className="border-b border-hairline text-sm text-muted">
              <tr>
                <Th>Policy</Th>
                <Th right>Threshold</Th>
                <Th right>Files refused</Th>
                <Th right>Bad payers approved</Th>
                <Th right>Good payers refused</Th>
                <Th right>Expected cost</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {Object.entries(meta.policies).map(([name, pol]) => (
                <tr key={name} className={pol.threshold === meta.threshold ? '' : 'text-muted'}>
                  <Td strong={pol.threshold === meta.threshold}>
                    {name === 'balanced' ? 'Balanced (maximum KS)' : 'Cost-optimal (5 to 1)'}
                  </Td>
                  <Td right>{pct(pol.threshold)}</Td>
                  <Td right>{pct(pol.refusal_rate)}</Td>
                  <Td right>
                    {pol.confusion.bad_approved} of {pol.confusion.bad_approved + pol.confusion.bad_refused}
                  </Td>
                  <Td right>
                    {pol.confusion.good_refused} of {pol.confusion.good_refused + pol.confusion.good_approved}
                  </Td>
                  <Td right>{pol.expected_cost.toFixed(3)}</Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-sm text-muted">
          For reference, approving every file costs {t.cost_approve_all.toFixed(2)} per file and refusing every file{' '}
          {t.cost_refuse_all.toFixed(2)}.
        </p>
      </section>

      {full && unaware && (
        <section className="mt-16">
          <h2 className="text-[18px] font-semibold">What the audit delivers</h2>
          <p className="mt-2 max-w-2xl text-muted">
            The five agents replayed on the {full.files} test files, for the audited model and for a variant trained
            without sex, age and foreign-worker status.
          </p>
          <div className="mt-6 grid gap-10 lg:grid-cols-2">
            <div>
              <p className="num text-5xl font-semibold tracking-tight">{pct(full.recourse_rate)}</p>
              <p className="mt-1 max-w-sm text-soft">
                of the {full.refused} refusals leave with at least one verified way to approval, {full.mean_paths.toFixed(1)}{' '}
                on average.
              </p>
              <div className="mt-6">
                <RecourseBar s={full} />
              </div>
            </div>
            <div className="overflow-x-auto card">
              <table className="w-full text-left">
                <thead className="border-b border-hairline text-sm text-muted">
                  <tr>
                    <Th> </Th>
                    <Th right>Audited model</Th>
                    <Th right>Without protected attributes</Th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-hairline">
                  <tr>
                    <Td>Decision changes with a protected attribute</Td>
                    <Td right strong>
                      <span className="text-negative">{pct(full.flip_test_failure_rate, 1)}</span>
                    </Td>
                    <Td right strong>
                      <span className="text-positive">{pct(unaware.flip_test_failure_rate, 1)}</span>
                    </Td>
                  </tr>
                  <tr>
                    <Td>Test AUC</Td>
                    <Td right>{f3(t.auc)}</Td>
                    <Td right>{comparison ? f3(comparison.test.auc) : ''}</Td>
                  </tr>
                  <tr>
                    <Td>Refusals with a way to approval</Td>
                    <Td right>{pct(full.recourse_rate)}</Td>
                    <Td right>{pct(unaware.recourse_rate)}</Td>
                  </tr>
                  <tr>
                    <Td>Refusals solvable by loan terms alone</Td>
                    <Td right>{pct(full.immediate_recourse_rate)}</Td>
                    <Td right>{pct(unaware.immediate_recourse_rate)}</Td>
                  </tr>
                  <tr>
                    <Td>Files sent to a human</Td>
                    <Td right>{full.escalated ?? 0}</Td>
                    <Td right>{unaware.escalated ?? 0}</Td>
                  </tr>
                  <tr>
                    <Td>Time per audit, agents on rules</Td>
                    <Td right>{full.ms_per_audit.toFixed(0)} ms</Td>
                    <Td right>{unaware.ms_per_audit.toFixed(0)} ms</Td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}

      {card.fairness && <FairnessSection f={card.fairness} />}

      {summary && (
        <section className="mt-16 max-w-3xl">
          <h2 className="text-[18px] font-semibold">What the model looks at</h2>
          <p className="mt-2 text-muted">Average weight of each attribute in the score across the test files (mean absolute SHAP value).</p>
          <ul className="mt-6 space-y-2.5">
            {summary.shap_importance.map((s) => (
              <li key={s.feature} className="grid grid-cols-[minmax(0,14rem)_minmax(0,1fr)_3rem] items-center gap-4 text-sm">
                <span className="truncate">{s.label}</span>
                <span className="h-2 rounded-full bg-hairline">
                  <span className="block h-2 rounded-full bg-ink" style={{ width: `${(s.value / maxShap) * 100}%` }} />
                </span>
                <span className="num text-right text-muted">{s.value.toFixed(2)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  )
}
