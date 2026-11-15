import { NODES, type PipelineView, type StepState } from '../lib/format'

const X = [90, 295, 500, 705, 910]
const Y = 104
const R = 23
const LOOP = `M${X[3]} ${Y - R - 6} C ${X[3]} 22, ${X[2]} 22, ${X[2]} ${Y - R - 6}`

const FILL: Record<StepState, string> = {
  idle: 'var(--color-surface)',
  skipped: 'var(--color-canvas)',
  running: 'var(--color-surface)',
  done: 'var(--color-ink)',
  rejected: 'var(--color-surface)',
  escalated: 'var(--color-caution)',
}
const STROKE: Record<StepState, string> = {
  idle: 'var(--color-hairline)',
  skipped: 'var(--color-hairline)',
  running: 'var(--color-accent)',
  done: 'var(--color-ink)',
  rejected: 'var(--color-negative)',
  escalated: 'var(--color-caution)',
}

function Glyph({ state, index, x }: { state: StepState; index: number; x: number }) {
  if (state === 'done' || state === 'escalated')
    return (
      <path
        d={`M${x - 8} ${Y} l5.5 5.5 l10.5 -11`}
        fill="none"
        stroke="var(--color-surface)"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    )
  if (state === 'rejected')
    return (
      <path
        d={`M${x - 6.5} ${Y - 6.5} l13 13 M${x + 6.5} ${Y - 6.5} l-13 13`}
        stroke="var(--color-negative)"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
    )
  return (
    <text
      x={x}
      y={Y + 5}
      textAnchor="middle"
      fontSize="15"
      fontWeight="600"
      fill={state === 'running' ? 'var(--color-accent)' : 'var(--color-faint)'}
    >
      {index + 1}
    </text>
  )
}

/** The five agents and the rejection loop, drawn from the event stream. */
export function Pipeline({ view, maxAttempts }: { view: PipelineView; maxAttempts: number }) {
  const states = NODES.map((n) => view.states[n.id])
  const showLoop = view.attempts > 1 || view.looping
  const attemptShown = Math.min(view.attempts + (view.looping ? 1 : 0), maxAttempts)
  const loopColor = view.looping ? 'var(--color-negative)' : 'var(--color-soft)'
  const loopText = view.looping
    ? `Rejected by the auditor, attempt ${attemptShown} of ${maxAttempts}`
    : `${view.attempts} attempts, ${view.rejections} rejected by the auditor`

  return (
    <>
      <svg viewBox="0 0 1000 178" className="hidden w-full md:block" role="img" aria-label="Progress of the five agents">
        {X.slice(0, -1).map((x, i) => {
          const passed = ['done', 'rejected', 'escalated', 'skipped'].includes(states[i]) && states[i + 1] !== 'idle'
          return (
            <line
              key={x}
              x1={x + R + 8}
              x2={X[i + 1] - R - 8}
              y1={Y}
              y2={Y}
              stroke={passed ? 'var(--color-ink)' : 'var(--color-hairline)'}
              strokeWidth="1.5"
              strokeDasharray={states[i] === 'skipped' || states[i + 1] === 'skipped' ? '3 5' : undefined}
            />
          )
        })}

        {showLoop && (
          <g>
            <path d={LOOP} fill="none" stroke={loopColor} strokeWidth="1.5" />
            <path
              d={`M${X[2] - 5} ${Y - R - 13} l5 8 l5 -8`}
              fill="none"
              stroke={loopColor}
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <text x={(X[2] + X[3]) / 2} y="20" textAnchor="middle" fontSize="12.5" fontWeight="500" fill={loopColor}>
              {loopText}
            </text>
          </g>
        )}

        {NODES.map((n, i) => (
          <g key={n.id} opacity={states[i] === 'skipped' ? 0.45 : 1}>
            {states[i] === 'running' && <circle cx={X[i]} cy={Y} r={R + 3} fill="var(--color-accent)" className="breathe" />}
            <circle cx={X[i]} cy={Y} r={R} fill={FILL[states[i]]} stroke={STROKE[states[i]]} strokeWidth={states[i] === 'idle' || states[i] === 'skipped' ? 1.25 : 2} />
            <Glyph state={states[i]} index={i} x={X[i]} />
            <text x={X[i]} y={Y + 46} textAnchor="middle" fontSize="13.5" fontWeight="600" fill={states[i] === 'idle' || states[i] === 'skipped' ? 'var(--color-muted)' : 'var(--color-ink)'}>
              {n.name}
            </text>
            <text x={X[i]} y={Y + 64} textAnchor="middle" fontSize="12" fill="var(--color-muted)">
              {states[i] === 'skipped' ? 'Not needed' : n.role}
            </text>
          </g>
        ))}
      </svg>

      <ol className="space-y-3 md:hidden">
        {NODES.map((n, i) => (
          <li key={n.id} className="flex items-center gap-3">
            <span
              className="h-2.5 w-2.5 shrink-0 rounded-full"
              style={{ background: states[i] === 'idle' || states[i] === 'skipped' ? 'var(--color-hairline)' : STROKE[states[i]] }}
            />
            <span className={states[i] === 'idle' || states[i] === 'skipped' ? 'text-muted' : 'font-medium'}>{n.name}</span>
            {states[i] === 'running' && <span className="text-sm text-accent">working</span>}
          </li>
        ))}
        {showLoop && (
          <li className="text-sm" style={{ color: loopColor }}>
            {loopText}
          </li>
        )}
      </ol>
    </>
  )
}
