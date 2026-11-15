import type { ReactNode } from 'react'
import type { Status, Tone } from '../lib/status'

const TONE: Record<Tone, string> = {
  positive: 'bg-positive/10 text-positive ring-positive/20',
  negative: 'bg-negative/10 text-negative ring-negative/20',
  caution: 'bg-caution/12 text-caution ring-caution/25',
  accent: 'bg-accent-wash text-accent-ink ring-accent/20',
  muted: 'bg-canvas text-muted ring-hairline',
}
const DOT: Record<Tone, string> = {
  positive: 'bg-positive',
  negative: 'bg-negative',
  caution: 'bg-caution',
  accent: 'bg-accent',
  muted: 'bg-faint',
}

export function Pill({ tone, children, live = false }: { tone: Tone; children: ReactNode; live?: boolean }) {
  return (
    <span className={`inline-flex h-6 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 text-xs font-medium ring-1 ring-inset ${TONE[tone]}`}>
      <span className="relative flex h-1.5 w-1.5">
        {live && <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 ${DOT[tone]}`} />}
        <span className={`relative inline-flex h-1.5 w-1.5 rounded-full ${DOT[tone]}`} />
      </span>
      {children}
    </span>
  )
}

export function StatusPill({ status }: { status: Status }) {
  return (
    <Pill tone={status.tone} live={status.key === 'running'}>
      {status.label}
    </Pill>
  )
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`card overflow-hidden ${className}`}>{children}</div>
}

export function CardHeader({ title, aside, children }: { title: string; aside?: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-hairline px-5 py-3.5">
      <div>
        <h2 className="text-[15px] font-semibold">{title}</h2>
        {children && <p className="text-[13px] text-muted">{children}</p>}
      </div>
      {aside && <div className="text-[13px] text-muted">{aside}</div>}
    </div>
  )
}

export function PageHeader({ title, sub, actions }: { title: string; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-[26px] font-semibold leading-tight">{title}</h1>
        {sub && <p className="mt-1 max-w-2xl text-muted">{sub}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

type ButtonKind = 'primary' | 'secondary' | 'ghost' | 'dark'
const BUTTON: Record<ButtonKind, string> = {
  primary: 'bg-accent text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.18)] hover:bg-accent-ink',
  secondary: 'bg-surface text-ink ring-1 ring-inset ring-hairline shadow-card hover:bg-raised',
  ghost: 'text-soft hover:bg-hairline/60 hover:text-ink',
  dark: 'bg-ink text-canvas hover:opacity-90',
}
export const buttonClass = (kind: ButtonKind = 'secondary', size: 'sm' | 'md' = 'md') =>
  `inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-control font-medium transition disabled:pointer-events-none disabled:opacity-45 ${
    size === 'sm' ? 'h-8 px-3 text-[13px]' : 'h-9 px-4 text-[14px]'
  } ${BUTTON[kind]}`

export function Kpi({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: Tone }) {
  const color = tone === 'positive' ? 'text-positive' : tone === 'negative' ? 'text-negative' : tone === 'caution' ? 'text-caution' : 'text-ink'
  return (
    <div className="card px-5 py-4">
      <p className="text-[13px] text-muted">{label}</p>
      <p className={`num mt-1.5 text-[28px] font-semibold leading-none tracking-tight ${color}`}>{value}</p>
      {hint && <p className="mt-2 text-[12.5px] text-muted">{hint}</p>}
    </div>
  )
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { id: T; label: string; count?: number }[]; value: T; onChange: (t: T) => void }) {
  return (
    <div role="tablist" className="flex gap-1 overflow-x-auto border-b border-hairline">
      {tabs.map((t) => (
        <button
          key={t.id}
          role="tab"
          aria-selected={value === t.id}
          onClick={() => onChange(t.id)}
          className={`relative -mb-px flex h-10 items-center gap-2 whitespace-nowrap border-b-2 px-3 text-[14px] transition-colors ${
            value === t.id ? 'border-ink font-medium text-ink' : 'border-transparent text-muted hover:text-ink'
          }`}
        >
          {t.label}
          {t.count !== undefined && (
            <span className="num rounded-full bg-canvas px-1.5 text-[11px] text-muted ring-1 ring-inset ring-hairline">{t.count}</span>
          )}
        </button>
      ))}
    </div>
  )
}

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center px-6 py-14 text-center">
      <p className="font-medium">{title}</p>
      {children && <p className="mt-1 max-w-sm text-[13.5px] text-muted">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="rounded border border-hairline bg-raised px-1.5 py-px font-sans text-[11px] text-muted">{children}</kbd>
  )
}
