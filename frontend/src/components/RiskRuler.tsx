import { pct } from '../lib/format'

interface Props {
  value: number
  threshold: number
  margin?: number
  /** Risk after a proposed change: draws the movement from `value` to `to`. */
  to?: number
  compact?: boolean
}

const W = 600
const PAD = 8
const x = (p: number) => PAD + Math.max(0, Math.min(1, p)) * (W - 2 * PAD)

/** Default risk on a 0 to 100% scale, against the refusal threshold. */
export function RiskRuler({ value, threshold, margin = 0, to, compact = false }: Props) {
  const y = 12
  const refused = (to ?? value) >= threshold
  const label =
    to === undefined
      ? `Default risk ${pct(value)}, refusal threshold ${pct(threshold)}`
      : `Default risk moves from ${pct(value)} to ${pct(to)}, threshold ${pct(threshold)}`

  return (
    <div>
      {!compact && (
        <div className="relative h-6 text-sm text-soft" aria-hidden="true">
          <span
            className="absolute -translate-x-1/2 whitespace-nowrap"
            style={{ left: `clamp(5.5rem, ${(x(threshold) / W) * 100}%, calc(100% - 5.5rem))` }}
          >
            Refusal threshold {pct(threshold)}
          </span>
        </div>
      )}
      <svg viewBox={`0 0 ${W} 24`} preserveAspectRatio="none" className="h-6 w-full" role="img" aria-label={label}>
        <rect x={x(0)} y={y - 3} width={x(threshold) - x(0)} height="6" rx="3" fill="var(--color-positive)" opacity="0.22" />
        <rect x={x(threshold)} y={y - 3} width={x(1) - x(threshold)} height="6" rx="3" fill="var(--color-negative)" opacity="0.16" />
        {margin > 0 && !compact && (
          <rect x={x(threshold - margin)} y={y - 7} width={x(threshold + margin) - x(threshold - margin)} height="14" rx="3" fill="var(--color-caution)" opacity="0.22" />
        )}
        <line x1={x(threshold)} x2={x(threshold)} y1={y - 10} y2={y + 10} stroke="var(--color-ink)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
        {to !== undefined && <line x1={x(value)} x2={x(to)} y1={y} y2={y} stroke="var(--color-ink)" strokeWidth="2" vectorEffect="non-scaling-stroke" />}
      </svg>
      {/* Markers are HTML so they stay round whatever the width of the ruler. */}
      <div className="relative -mt-6 h-6" aria-hidden="true">
        {to !== undefined && (
          <span
            className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-[1.5px] border-ink bg-surface"
            style={{ left: `${(x(value) / W) * 100}%` }}
          />
        )}
        <span
          className={`absolute top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full border-[2.5px] border-surface ${
            compact ? 'h-3.5 w-3.5' : 'h-5 w-5'
          } ${refused ? 'bg-negative' : 'bg-positive'}`}
          style={{ left: `${(x(to ?? value) / W) * 100}%` }}
        />
      </div>
      {!compact && (
        <div className="mt-0.5 flex justify-between text-xs text-faint" aria-hidden="true">
          <span>0%</span>
          <span>100%</span>
        </div>
      )}
    </div>
  )
}
