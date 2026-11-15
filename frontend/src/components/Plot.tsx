import type { ReactNode } from 'react'

interface Props {
  title: string
  x?: [number, number]
  y?: [number, number]
  xLabel: string
  yLabel: string
  xFormat?: (v: number) => string
  yFormat?: (v: number) => string
  children: (sx: (v: number) => number, sy: (v: number) => number) => ReactNode
  legend?: { label: string; color: string; dashed?: boolean }[]
}

const W = 380
const H = 270
const M = { l: 46, r: 12, t: 10, b: 38 }

/** Minimal chart frame: axes, five ticks each, a render callback for the marks. */
export function Plot({ title, x = [0, 1], y = [0, 1], xLabel, yLabel, xFormat = String, yFormat = String, children, legend }: Props) {
  const sx = (v: number) => M.l + ((v - x[0]) / (x[1] - x[0])) * (W - M.l - M.r)
  const sy = (v: number) => H - M.b - ((v - y[0]) / (y[1] - y[0])) * (H - M.t - M.b)
  const ticks = (d: [number, number]) => Array.from({ length: 5 }, (_, i) => d[0] + ((d[1] - d[0]) * i) / 4)
  return (
    <figure>
      <figcaption className="mb-2 font-medium">{title}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={title}>
        {ticks(y).map((t) => (
          <g key={t}>
            <line x1={M.l} x2={W - M.r} y1={sy(t)} y2={sy(t)} stroke="var(--color-hairline)" />
            <text x={M.l - 8} y={sy(t) + 4} textAnchor="end" fontSize="10.5" fill="var(--color-muted)">
              {yFormat(t)}
            </text>
          </g>
        ))}
        {ticks(x).map((t) => (
          <text key={t} x={sx(t)} y={H - M.b + 15} textAnchor="middle" fontSize="10.5" fill="var(--color-muted)">
            {xFormat(t)}
          </text>
        ))}
        <text x={(M.l + W - M.r) / 2} y={H - 4} textAnchor="middle" fontSize="11" fill="var(--color-soft)">
          {xLabel}
        </text>
        <text transform={`translate(11 ${(M.t + H - M.b) / 2}) rotate(-90)`} textAnchor="middle" fontSize="11" fill="var(--color-soft)">
          {yLabel}
        </text>
        {children(sx, sy)}
      </svg>
      {legend && (
        <ul className="mt-1 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
          {legend.map((l) => (
            <li key={l.label} className="flex items-center gap-2">
              <svg width="18" height="4" aria-hidden="true">
                <line x1="0" x2="18" y1="2" y2="2" stroke={l.color} strokeWidth="2" strokeDasharray={l.dashed ? '3 3' : undefined} />
              </svg>
              {l.label}
            </li>
          ))}
        </ul>
      )}
    </figure>
  )
}

export const polyline = (pts: [number, number][], sx: (v: number) => number, sy: (v: number) => number) =>
  pts.map(([a, b]) => `${sx(a).toFixed(1)},${sy(b).toFixed(1)}`).join(' ')
