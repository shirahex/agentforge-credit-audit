import {
  BarChart3,
  FilePlus2,
  Files,
  Inbox,
  LayoutDashboard,
  Moon,
  Search,
  Sun,
  type LucideIcon,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAudits, useHealth, useTheme } from '../lib/hooks'
import { auditStatus } from '../lib/status'
import { pct } from '../lib/format'
import { Kbd, StatusPill, buttonClass } from './ui'
import { Logo } from './Logo'
import type { AuditSummary } from '../types'

interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  end?: boolean
  badge?: number
}

function SideLink({ item, onClick }: { item: NavItem; onClick?: () => void }) {
  const Icon = item.icon
  return (
    <NavLink
      to={item.to}
      end={item.end}
      onClick={onClick}
      className={({ isActive }) =>
        `group flex h-9 items-center gap-3 rounded-control px-2.5 text-[14px] transition-colors ${
          isActive ? 'bg-surface font-medium text-ink shadow-card ring-1 ring-hairline' : 'text-soft hover:bg-hairline/50 hover:text-ink'
        }`
      }
    >
      <Icon size={16} strokeWidth={1.8} className="shrink-0 opacity-80" />
      <span className="flex-1">{item.label}</span>
      {item.badge ? (
        <span className="num rounded-full bg-caution px-1.5 text-[11px] font-semibold leading-[18px] text-white">{item.badge}</span>
      ) : null}
    </NavLink>
  )
}

/** Ctrl+K: jump to a page or to any audit by applicant. */
function Palette({ open, onClose, audits }: { open: boolean; onClose: () => void; audits: AuditSummary[] }) {
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [index, setIndex] = useState(0)
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) {
      setQ('')
      setIndex(0)
      setTimeout(() => input.current?.focus(), 10)
    }
  }, [open])

  const items = useMemo(() => {
    const pages = [
      { id: 'p-dash', label: 'Dashboard', hint: 'Page', to: '/app' },
      { id: 'p-new', label: 'New audit', hint: 'Page', to: '/app/new' },
      { id: 'p-audits', label: 'All audits', hint: 'Page', to: '/app/audits' },
      { id: 'p-review', label: 'Review inbox', hint: 'Page', to: '/app/review' },
      { id: 'p-model', label: 'Model and fairness', hint: 'Page', to: '/app/model' },
      { id: 'p-home', label: 'Product page', hint: 'Page', to: '/' },
    ]
    const files = audits.map((a) => ({
      id: a.run_id,
      label: `Applicant ${a.applicant_id}`,
      hint: `${auditStatus(a).label}${a.default_probability !== null ? `, risk ${pct(a.default_probability)}` : ''}`,
      to: `/app/audit/${a.run_id}`,
    }))
    const all = [...pages, ...files]
    const s = q.trim().toLowerCase()
    return (s ? all.filter((i) => `${i.label} ${i.hint}`.toLowerCase().includes(s)) : all).slice(0, 9)
  }, [q, audits])

  if (!open) return null
  const go = (to: string) => {
    onClose()
    navigate(to)
  }
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-night/40 px-4 pt-[14vh] backdrop-blur-[2px]" onMouseDown={onClose}>
      <div
        role="dialog"
        aria-label="Search"
        className="settle w-full max-w-lg overflow-hidden rounded-panel border border-hairline bg-surface shadow-lift"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 border-b border-hairline px-4">
          <Search size={16} className="text-muted" />
          <input
            ref={input}
            value={q}
            onChange={(e) => {
              setQ(e.target.value)
              setIndex(0)
            }}
            onKeyDown={(e) => {
              if (e.key === 'Escape') onClose()
              if (e.key === 'ArrowDown') setIndex((i) => Math.min(items.length - 1, i + 1))
              if (e.key === 'ArrowUp') setIndex((i) => Math.max(0, i - 1))
              if (e.key === 'Enter' && items[index]) go(items[index].to)
            }}
            placeholder="Search an applicant or a page"
            className="h-12 flex-1 bg-transparent text-[15px] outline-none placeholder:text-faint"
          />
          <Kbd>Esc</Kbd>
        </div>
        <ul className="max-h-80 overflow-y-auto p-1.5">
          {items.length === 0 && <li className="px-3 py-6 text-center text-[13.5px] text-muted">Nothing matches "{q}".</li>}
          {items.map((i, k) => (
            <li key={i.id}>
              <button
                onMouseEnter={() => setIndex(k)}
                onClick={() => go(i.to)}
                className={`flex w-full items-center justify-between gap-3 rounded-control px-3 py-2 text-left text-[14px] ${
                  k === index ? 'bg-accent-wash text-ink' : 'text-soft'
                }`}
              >
                <span className="truncate">{i.label}</span>
                <span className="shrink-0 text-[12.5px] text-muted">{i.hint}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

export function Shell() {
  const [theme, toggleTheme] = useTheme()
  const { health, down } = useHealth()
  const { audits } = useAudits()
  const [palette, setPalette] = useState(false)
  const [menu, setMenu] = useState(false)
  const location = useLocation()

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setPalette((p) => !p)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
  useEffect(() => setMenu(false), [location.pathname])

  const waiting = audits?.filter((a) => a.status === 'awaiting_review').length ?? 0
  const running = audits?.filter((a) => !a.done).length ?? 0
  const nav: NavItem[] = [
    { to: '/app', label: 'Dashboard', icon: LayoutDashboard, end: true },
    { to: '/app/audits', label: 'Audits', icon: Files },
    { to: '/app/review', label: 'Review inbox', icon: Inbox, badge: waiting },
    { to: '/app/model', label: 'Model and fairness', icon: BarChart3 },
  ]

  const sidebar = (
    <div className="flex h-full flex-col gap-6 px-3 py-4">
      <Link to="/" className="flex items-center gap-2.5 px-2.5 pt-1">
        <Logo />
        <span className="text-[15px] font-semibold tracking-tight">AgentForge</span>
      </Link>
      <Link to="/app/new" className={`${buttonClass('primary')} mx-0.5`}>
        <FilePlus2 size={15} strokeWidth={2} /> New audit
      </Link>
      <nav className="space-y-0.5" aria-label="Console">
        {nav.map((n) => (
          <SideLink key={n.to} item={n} />
        ))}
      </nav>
      <div className="mt-auto space-y-3 px-1">
        <div className="rounded-control border border-hairline bg-surface/60 px-3 py-2.5 text-[12.5px] leading-relaxed text-muted">
          <p className="flex items-center gap-2 font-medium text-soft">
            <span className={`h-1.5 w-1.5 rounded-full ${down ? 'bg-negative' : health ? 'bg-positive' : 'bg-faint'}`} />
            {down ? 'API unreachable' : health ? 'All systems running' : 'Connecting'}
          </p>
          {health && (
            <p className="mt-1">
              LightGBM {health.variant}, threshold {pct(health.threshold)}
              <br />
              Agents on {health.llm.enabled ? health.llm.model.replace('openai/', '') : 'rules'}
            </p>
          )}
        </div>
        <p className="px-2 text-[11.5px] text-faint">AgentForge, Master IA, FSBM Casablanca</p>
      </div>
    </div>
  )

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      <aside className="sticky top-0 hidden h-screen border-r border-hairline lg:block">{sidebar}</aside>
      {menu && (
        <div className="fixed inset-0 z-40 lg:hidden" onClick={() => setMenu(false)}>
          <div className="absolute inset-0 bg-night/40" />
          <aside className="settle absolute inset-y-0 left-0 w-[260px] border-r border-hairline bg-canvas" onClick={(e) => e.stopPropagation()}>
            {sidebar}
          </aside>
        </div>
      )}
      <div className="min-w-0">
        <header className="sticky top-0 z-30 border-b border-hairline bg-canvas/85 backdrop-blur-xl">
          <div className="mx-auto flex h-14 max-w-[1240px] items-center gap-3 px-4 sm:px-6">
            <button className={`${buttonClass('ghost', 'sm')} lg:hidden`} onClick={() => setMenu(true)} aria-label="Open the menu">
              <span className="flex flex-col gap-[3px]">
                <span className="h-px w-4 bg-ink" />
                <span className="h-px w-4 bg-ink" />
                <span className="h-px w-4 bg-ink" />
              </span>
            </button>
            <button
              onClick={() => setPalette(true)}
              className="flex h-9 w-full max-w-sm items-center gap-2.5 rounded-control border border-hairline bg-surface px-3 text-[13.5px] text-faint shadow-card transition hover:text-muted"
            >
              <Search size={15} />
              <span className="flex-1 text-left">Search applicants, pages</span>
              <Kbd>Ctrl K</Kbd>
            </button>
            <div className="ml-auto flex items-center gap-2">
              {running > 0 && <StatusPill status={{ key: 'running', label: `${running} running`, tone: 'accent' }} />}
              <button onClick={toggleTheme} className={buttonClass('ghost', 'sm')} aria-label="Switch light or dark mode">
                {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
              </button>
            </div>
          </div>
        </header>
        {down && (
          <p className="mx-auto mt-4 max-w-[1240px] px-6 text-[13.5px] text-negative">
            The API does not answer. Start it from the backend folder with: uvicorn app.main:app --reload
          </p>
        )}
        <main className="mx-auto max-w-[1240px] px-4 pb-20 pt-8 sm:px-6">
          <Outlet />
        </main>
      </div>
      <Palette open={palette} onClose={() => setPalette(false)} audits={audits ?? []} />
    </div>
  )
}
