import type { Factor } from '../types'

/** Exact SHAP contributions: bars to the right raise the default risk. */
export function FactorBars({ factors }: { factors: Factor[] }) {
  const max = Math.max(...factors.map((f) => Math.abs(f.contribution)), 0.01)
  return (
    <div>
      <ul className="divide-y divide-hairline">
        {factors.map((f) => {
          const width = (Math.abs(f.contribution) / max) * 50
          const up = f.contribution > 0
          return (
            <li
              key={f.feature}
              className="grid grid-cols-[minmax(0,1fr)_3.2rem] items-center gap-x-4 gap-y-2 py-3 sm:grid-cols-[minmax(0,5fr)_minmax(0,6fr)_3.2rem]"
            >
              <div className="col-span-2 min-w-0 sm:col-span-1">
                <p className="truncate font-medium">{f.label}</p>
                <p className="truncate text-sm text-muted">{f.value_label}</p>
              </div>
              <div className="relative h-5" aria-hidden="true">
                <span className="absolute inset-y-0 left-1/2 w-px bg-hairline" />
                <span
                  className={`absolute inset-y-1 rounded-sm ${up ? 'bg-negative' : 'bg-positive'}`}
                  style={up ? { left: '50%', width: `${width}%` } : { right: '50%', width: `${width}%` }}
                />
              </div>
              <p className={`num text-right text-sm font-medium ${up ? 'text-negative' : 'text-positive'}`}>
                {up ? '+' : '−'}
                {Math.abs(f.contribution).toFixed(2)}
              </p>
            </li>
          )
        })}
      </ul>
      <div className="mt-3 grid grid-cols-[minmax(0,1fr)_3.2rem] gap-4 text-xs text-muted sm:grid-cols-[minmax(0,5fr)_minmax(0,6fr)_3.2rem]">
        <span className="hidden sm:block" />
        <span className="flex justify-between">
          <span>Lowers the risk</span>
          <span>Raises the risk</span>
        </span>
        <span />
      </div>
    </div>
  )
}
