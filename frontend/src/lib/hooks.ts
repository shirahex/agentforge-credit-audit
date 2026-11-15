import { useEffect, useRef, useState } from 'react'
import { getHealth, listAudits } from './api'
import type { AuditSummary, Health } from '../types'

/** Light or dark console, remembered per browser. */
export function useTheme(): [string, () => void] {
  const [theme, setTheme] = useState<string>(() => {
    try {
      return localStorage.getItem('af-theme') ?? 'light'
    } catch {
      return 'light'
    }
  })
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      localStorage.setItem('af-theme', theme)
    } catch {
      /* storage unavailable: the choice lasts for this visit */
    }
  }, [theme])
  return [theme, () => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))]
}

export function useHealth(): { health: Health | null; down: boolean } {
  const [health, setHealth] = useState<Health | null>(null)
  const [down, setDown] = useState(false)
  useEffect(() => {
    let alive = true
    const load = () =>
      getHealth()
        .then((h) => alive && (setHealth(h), setDown(false)))
        .catch(() => alive && setDown(true))
    load()
    const t = setInterval(load, 15000)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [])
  return { health, down }
}

/** Audit list, refreshed while any audit is still running. */
export function useAudits(): { audits: AuditSummary[] | null; error: boolean } {
  const [audits, setAudits] = useState<AuditSummary[] | null>(null)
  const [error, setError] = useState(false)
  useEffect(() => {
    let alive = true
    let timer: ReturnType<typeof setTimeout>
    const load = () =>
      listAudits()
        .then((a) => {
          if (!alive) return
          setAudits(a)
          setError(false)
          timer = setTimeout(load, a.some((x) => !x.done) ? 2500 : 12000)
        })
        .catch(() => {
          if (!alive) return
          setError(true)
          timer = setTimeout(load, 8000)
        })
    load()
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [])
  return { audits, error }
}

/** Adds the class "in" to elements with the class "reveal" when they scroll into view. */
export function useReveal(deps: unknown[] = []) {
  useEffect(() => {
    const els = document.querySelectorAll('.reveal:not(.in)')
    if (!('IntersectionObserver' in window)) {
      els.forEach((e) => e.classList.add('in'))
      return
    }
    const io = new IntersectionObserver(
      (entries) =>
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add('in')
            io.unobserve(e.target)
          }
        }),
      { rootMargin: '0px 0px -12% 0px' },
    )
    els.forEach((e) => io.observe(e))
    return () => io.disconnect()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
}

/** Progress (0 to 1) of an element scrolling through the viewport. */
export function useScrollProgress<T extends HTMLElement>(): [React.RefObject<T | null>, number] {
  const ref = useRef<T>(null)
  const [progress, setProgress] = useState(0)
  useEffect(() => {
    let frame = 0
    const update = () => {
      frame = 0
      const el = ref.current
      if (!el) return
      const r = el.getBoundingClientRect()
      const total = r.height - window.innerHeight
      setProgress(total > 0 ? Math.min(1, Math.max(0, -r.top / total)) : r.top < 0 ? 1 : 0)
    }
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(update)
    }
    update()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
      cancelAnimationFrame(frame)
    }
  }, [])
  return [ref, progress]
}

/** Window scroll position, throttled to animation frames (for parallax). */
export function useScrollY(): number {
  const [y, setY] = useState(0)
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    let frame = 0
    const onScroll = () => {
      if (!frame)
        frame = requestAnimationFrame(() => {
          frame = 0
          setY(window.scrollY)
        })
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      window.removeEventListener('scroll', onScroll)
      cancelAnimationFrame(frame)
    }
  }, [])
  return y
}

/** Animates a number from 0 to `target` once `active` turns true. */
export function useCountUp(target: number, active: boolean, ms = 1100): number {
  const [v, setV] = useState(0)
  useEffect(() => {
    if (!active) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setV(target)
      return
    }
    let raf = 0
    const t0 = performance.now()
    const tick = (t: number) => {
      const k = Math.min(1, (t - t0) / ms)
      setV(target * (1 - Math.pow(1 - k, 3)))
      if (k < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, active, ms])
  return v
}
