import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { getHealth } from '../lib/api'
import { pct } from '../lib/format'
import type { Health } from '../types'

const LINKS = [
  { to: '/', label: 'New audit' },
  { to: '/history', label: 'History' },
  { to: '/model', label: 'Model' },
]

export function Layout() {
  const [health, setHealth] = useState<Health | null>(null)
  const [down, setDown] = useState(false)

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() => setDown(true))
  }, [])

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-hairline bg-canvas/80 backdrop-blur-xl">
        <nav className="mx-auto flex h-12 max-w-6xl items-center gap-8 px-6 text-sm" aria-label="Main">
          <NavLink to="/" className="font-display text-[15px] font-semibold tracking-tight">
            AgentForge
          </NavLink>
          <ul className="flex gap-6">
            {LINKS.map((l) => (
              <li key={l.to}>
                <NavLink
                  to={l.to}
                  end={l.to === '/'}
                  className={({ isActive }) => (isActive ? 'text-ink' : 'text-muted transition-colors hover:text-ink')}
                >
                  {l.label}
                </NavLink>
              </li>
            ))}
          </ul>
          <p className="ml-auto hidden items-center gap-2 text-xs text-muted sm:flex">
            <span className={`h-1.5 w-1.5 rounded-full ${down ? 'bg-negative' : health ? 'bg-positive' : 'bg-faint'}`} />
            {down && 'Backend unreachable'}
            {health &&
              `Model ${health.variant}, threshold ${pct(health.threshold)}, agents on ${
                health.llm.enabled ? health.llm.model : 'rules'
              }`}
          </p>
        </nav>
      </header>
      {down && (
        <p className="mx-auto mt-6 max-w-6xl px-6 text-sm text-negative">
          The backend does not answer. Start it from the backend folder with: uvicorn app.main:app --reload
        </p>
      )}
      <main className="mx-auto max-w-6xl px-6 pb-24 pt-12">
        <Outlet />
      </main>
    </div>
  )
}
