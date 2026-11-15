import { ArrowRight, Check, FileSearch, Gauge, Route, Scale, ScrollText } from 'lucide-react'
import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { Logo } from '../components/Logo'
import { useCountUp, useReveal, useScrollProgress, useScrollY } from '../lib/hooks'

/* Figures published by eval/run_eval.py on the 200 held-out files (99 refusals). */
const SYSTEMS = [
  { name: 'AgentForge, five agents with the verification loop', sound: 0.778, unsound: 0, highlight: true },
  { name: 'Without the rejection loop', sound: 0.394, unsound: 0 },
  { name: 'Without the auditor agent', sound: 0.394, unsound: 0.222 },
  { name: 'Model and DiCE alone, no agents', sound: 0.354, unsound: 1 },
  { name: 'One prompt to a language model, no tools', sound: 0, unsound: 1 },
]

const AGENTS = [
  {
    name: 'Analyste-Dossier',
    role: 'Checks the file',
    icon: FileSearch,
    text: 'Validates every field, flags inconsistencies, and finds the fifteen most similar past applicants and how many of them defaulted.',
    tool: 'validate_application, similar_cases, past_audits',
    out: '1 warning: no guarantor, overdrawn account. 6 of 15 similar applicants defaulted.',
  },
  {
    name: 'Modèle-Scoring',
    role: 'Scores and explains',
    icon: Gauge,
    text: 'A calibrated LightGBM model gives the risk of default. Exact TreeSHAP values say which factors raised it and which lowered it, and the explanation is checked against them.',
    tool: 'score_applicant, explain (TreeSHAP)',
    out: 'Risk 57%, threshold 26%: refused. Main factor: checking account.',
  },
  {
    name: 'Générateur-Contrefactuels',
    role: 'Searches for a way to approval',
    icon: Route,
    text: 'Plans which changes to try: first the loan terms, then the financial situation, never age, sex or nationality. Exhaustive search and DiCE propose candidates.',
    tool: 'generate_counterfactuals, permitted_moves',
    out: 'Attempt 3: repay over 12 months, bring the checking account above 200 DM.',
  },
  {
    name: 'Vérificateur-Équité',
    role: 'Audits every proposal',
    icon: Scale,
    text: 'Rejects anything unrealistic, unfair or fragile, and runs the flip test: the decision must not change when only a protected attribute does. A rejection sends the search back.',
    tool: 'plausibility (Gower kNN), flip_test, group_fairness',
    out: '3 candidates rejected as too far from real files. 1 path kept.',
  },
  {
    name: 'Arbitre et Rédacteur',
    role: 'Closes or escalates',
    icon: ScrollText,
    text: 'Closes the case or hands it to a person: borderline score, failed fairness test, no path found, or a near-identical past file decided the other way. Writes the PDF report and the letter.',
    tool: 'render_report, write_letter',
    out: 'Closed. Report AF-20261115 and letter in French issued.',
  },
]

function Nav({ solid }: { solid: boolean }) {
  return (
    <header
      className={`fixed inset-x-0 top-0 z-40 transition-all duration-300 ${
        solid ? 'border-b border-white/10 bg-night/80 backdrop-blur-xl' : 'border-b border-transparent'
      }`}
    >
      <nav className="mx-auto flex h-16 max-w-6xl items-center gap-8 px-6 text-[14px] text-white/70">
        <Link to="/" className="flex items-center gap-2.5 text-white">
          <Logo inverted />
          <span className="text-[15px] font-semibold tracking-tight">AgentForge</span>
        </Link>
        <a href="#how" className="hidden transition hover:text-white md:block">
          How it works
        </a>
        <a href="#evidence" className="hidden transition hover:text-white md:block">
          Evidence
        </a>
        <a href="#fairness" className="hidden transition hover:text-white md:block">
          Fairness
        </a>
        <Link
          to="/app"
          className="ml-auto inline-flex h-9 items-center gap-2 rounded-full bg-white px-4 font-medium text-night transition hover:bg-white/90"
        >
          Open the console <ArrowRight size={15} />
        </Link>
      </nav>
    </header>
  )
}

/** The hero visual: a case file whose risk falls under the threshold, then gets stamped. */
function CaseFile() {
  const [phase, setPhase] = useState(0)
  const [tilt, setTilt] = useState({ x: 0, y: 0 })
  const y = useScrollY()
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setPhase(4)
      return
    }
    const times = [700, 1700, 2900, 3800]
    const ids = times.map((t, i) => setTimeout(() => setPhase(i + 1), t))
    return () => ids.forEach(clearTimeout)
  }, [])

  const risk = phase >= 3 ? 22 : 57
  const shown = useCountUp(risk, true, 900)
  const approved = phase >= 3

  const layer = (depth: number): CSSProperties => ({
    transform: `translate3d(${tilt.x * depth * 14}px, ${tilt.y * depth * 10 - y * depth * 0.12}px, 0)`,
    transition: 'transform 0.25s ease-out',
  })

  return (
    <div
      ref={box}
      className="relative mx-auto h-[460px] w-full max-w-[520px] [perspective:1200px]"
      onMouseMove={(e) => {
        const r = box.current?.getBoundingClientRect()
        if (!r) return
        setTilt({ x: (e.clientX - r.left) / r.width - 0.5, y: (e.clientY - r.top) / r.height - 0.5 })
      }}
      onMouseLeave={() => setTilt({ x: 0, y: 0 })}
      aria-hidden="true"
    >
      {/* Back sheet: the letter */}
      <div style={layer(0.4)} className="absolute right-0 top-0 w-[78%]">
        <div className="rotate-[4deg] rounded-xl bg-[#f7f6f1] p-5 text-[11px] leading-relaxed text-[#3b4252] shadow-2xl">
          <p className="font-semibold text-[#1d2330]">Objet : votre demande de crédit</p>
          <p className="mt-2">Madame, Monsieur, votre demande de 3 104 DM sur 18 mois a été examinée.</p>
          <p className="mt-2">Piste 1 : rembourser sur 12 mois au lieu de 18 ; ramener votre compte courant à 200 DM ou plus.</p>
          <p className="mt-2 text-[#7a8291]">Vous pouvez demander le réexamen de votre dossier par un conseiller.</p>
        </div>
      </div>

      {/* Middle sheet: the factors */}
      <div style={layer(0.7)} className="absolute left-0 top-[70px] w-[66%]">
        <div className="-rotate-[3deg] rounded-xl border border-white/10 bg-[#131c31] p-4 shadow-2xl">
          <p className="text-[11px] font-medium text-white/50">What drives the score</p>
          {[
            ['Checking account', 0.9, true],
            ['Other instalment plans', 0.55, true],
            ['Savings', 0.4, true],
            ['Time in employment', 0.36, false],
          ].map(([label, w, up], i) => (
            <div key={String(label)} className="mt-2.5 flex items-center gap-2 text-[11px] text-white/70">
              <span className="w-32 truncate">{label}</span>
              <span className="relative h-1.5 flex-1">
                <span className="absolute inset-y-0 left-1/2 w-px bg-white/15" />
                <span
                  className={`absolute inset-y-0 rounded-full transition-all duration-700 ${up ? 'bg-[#ff6b5e]' : 'bg-[#3cc28f]'}`}
                  style={{
                    [up ? 'left' : 'right']: '50%',
                    width: phase >= 1 ? `${Number(w) * 48}%` : '0%',
                    transitionDelay: `${i * 90}ms`,
                  }}
                />
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Front card: the risk */}
      <div style={layer(1.1)} className="absolute bottom-0 right-[6%] w-[72%]">
        <div className="relative rounded-2xl border border-white/10 bg-white p-6 text-[#0e1626] shadow-[0_30px_80px_-20px_rgba(0,0,0,0.6)]">
          <div className="flex items-center justify-between text-[12px] text-[#637081]">
            <span>Applicant GC-0217</span>
            <span className="flex items-center gap-1.5">
              <span className={`h-1.5 w-1.5 rounded-full ${phase < 4 ? 'animate-pulse bg-[#2b4eff]' : 'bg-[#0f7b57]'}`} />
              {phase < 2 ? 'Scoring' : phase < 3 ? 'Searching attempt 3' : phase < 4 ? 'Auditing the path' : 'Audit complete'}
            </span>
          </div>
          <p className={`num mt-3 text-[64px] font-semibold leading-none tracking-tighter transition-colors duration-500 ${approved ? 'text-[#0f7b57]' : 'text-[#cf3a2e]'}`}>
            {Math.round(shown)}%
          </p>
          <p className="mt-1 text-[12.5px] text-[#637081]">Risk of default, threshold 26%</p>
          <div className="relative mt-4 h-2 rounded-full bg-[#e7e9e4]">
            <span className="absolute -top-1 h-4 w-0.5 rounded bg-[#0e1626]" style={{ left: '26%' }} />
            <span
              className={`absolute top-1/2 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white shadow transition-all duration-[900ms] ${
                approved ? 'bg-[#0f7b57]' : 'bg-[#cf3a2e]'
              }`}
              style={{ left: `${risk}%` }}
            />
          </div>
          <p className={`mt-4 text-[13px] transition-opacity duration-500 ${phase >= 2 ? 'opacity-100' : 'opacity-0'}`}>
            Repay over 12 months instead of 18, and bring the checking account above 200 DM.
          </p>
          {phase >= 4 && (
            <div
              className="stamp absolute -right-4 -top-6 rounded-[10px] border-[3px] border-[#0f7b57] bg-white/80 px-3 py-1 text-[#0f7b57]"
              style={{ boxShadow: 'inset 0 0 0 2px #fff, inset 0 0 0 3.5px #0f7b57' }}
            >
              <span className="block text-[18px] font-bold uppercase leading-none tracking-[0.12em]">Path verified</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/** Sticky scroll: one agent at a time while the section scrolls by. */
function HowItWorks() {
  const [ref, progress] = useScrollProgress<HTMLDivElement>()
  const active = Math.min(AGENTS.length - 1, Math.floor(progress * AGENTS.length * 0.999))
  const agent = AGENTS[active]
  const Icon = agent.icon

  return (
    <section id="how" ref={ref} className="relative" style={{ height: `${AGENTS.length * 70 + 60}vh` }}>
      <div className="sticky top-0 flex min-h-screen items-center py-20">
        <div className="mx-auto grid w-full max-w-6xl gap-12 px-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
          <div>
            <h2 className="text-[40px] font-semibold leading-[1.05] tracking-tight text-ink sm:text-[48px]">Five agents, one case file.</h2>
            <p className="mt-4 max-w-md text-[17px] leading-relaxed text-muted">
              Each agent has one job and its own tools. They hand the file to each other in a LangGraph state machine, and the auditor can send the
              search back up to three times.
            </p>
            <ol className="mt-10 space-y-1">
              {AGENTS.map((a, i) => (
                <li key={a.name} className="flex items-center gap-4">
                  <span
                    className={`num flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[13px] font-semibold transition-all duration-300 ${
                      i < active ? 'bg-ink text-canvas' : i === active ? 'bg-accent text-white shadow-[0_0_0_6px_var(--color-accent-wash)]' : 'bg-hairline text-muted'
                    }`}
                  >
                    {i < active ? <Check size={14} strokeWidth={3} /> : i + 1}
                  </span>
                  <span className={`py-2 text-[15px] transition-colors ${i === active ? 'font-semibold text-ink' : 'text-muted'}`}>{a.name}</span>
                </li>
              ))}
            </ol>
          </div>

          <div className="relative">
            <div className="mb-5 flex items-center" aria-hidden="true">
              {AGENTS.map((a, i) => {
                const A = a.icon
                return (
                  <div key={a.name} className="flex flex-1 items-center last:flex-none">
                    <span
                      className={`relative flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border transition-all duration-300 ${
                        i === active
                          ? 'scale-110 border-accent bg-accent text-white shadow-[0_10px_30px_-8px_var(--color-accent)]'
                          : i < active
                            ? 'border-ink bg-ink text-canvas'
                            : 'border-hairline bg-surface text-faint'
                      }`}
                    >
                      <A size={18} />
                    </span>
                    {i < AGENTS.length - 1 && (
                      <span className="mx-2 h-0.5 flex-1 rounded-full bg-hairline">
                        <span className="block h-0.5 rounded-full bg-ink transition-[width] duration-500" style={{ width: i < active ? '100%' : '0%' }} />
                      </span>
                    )}
                  </div>
                )
              })}
            </div>
            <div key={agent.name} className="settle card overflow-hidden">
              <div className="flex items-center gap-3 border-b border-hairline px-6 py-4">
                <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent-wash text-accent-ink">
                  <Icon size={19} />
                </span>
                <div>
                  <p className="font-semibold">{agent.name}</p>
                  <p className="text-[13px] text-muted">{agent.role}</p>
                </div>
                <span className="num ml-auto text-[13px] text-faint">
                  {active + 1} of {AGENTS.length}
                </span>
              </div>
              <div className="px-6 py-6">
                <p className="text-[17px] leading-relaxed text-soft">{agent.text}</p>
                <div className="mt-6 rounded-xl bg-canvas p-4 text-[13px]">
                  <p className="text-muted">Tools called</p>
                  <p className="mt-0.5 font-medium text-ink">{agent.tool}</p>
                  <p className="mt-3 text-muted">On applicant GC-0217</p>
                  <p className="mt-0.5 text-ink">{agent.out}</p>
                </div>
              </div>
              <div className="h-1 bg-hairline">
                <div className="h-1 bg-accent transition-[width] duration-200" style={{ width: `${progress * 100}%` }} />
              </div>
            </div>
            {active === 3 && (
              <p className="settle mt-4 flex items-center gap-2 text-[13.5px] text-negative">
                <span className="inline-block h-px w-6 bg-negative" /> A rejection sends the file back to the Générateur with the reason.
              </p>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}

function Bar({ value, tone, delay, visible }: { value: number; tone: 'accent' | 'muted' | 'negative'; delay: number; visible: boolean }) {
  const color = tone === 'accent' ? 'bg-accent' : tone === 'negative' ? 'bg-negative/80' : 'bg-ink/25'
  return (
    <span className="relative block h-2.5 flex-1 overflow-hidden rounded-full bg-hairline">
      <span
        className={`absolute inset-y-0 left-0 rounded-full ${color} transition-[width] duration-1000 ease-out`}
        style={{ width: visible ? `${value * 100}%` : '0%', transitionDelay: `${delay}ms` }}
      />
    </span>
  )
}

function Evidence() {
  const ref = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const io = new IntersectionObserver(([e]) => e.isIntersecting && setVisible(true), { threshold: 0.3 })
    io.observe(el)
    return () => io.disconnect()
  }, [])
  const headline = useCountUp(78, visible)

  return (
    <section id="evidence" className="mx-auto max-w-6xl px-6 py-28">
      <div className="grid gap-14 lg:grid-cols-[minmax(0,4fr)_minmax(0,7fr)]">
        <div className="reveal">
          <p className="num text-[96px] font-semibold leading-none tracking-tighter text-accent">{Math.round(headline)}%</p>
          <h2 className="mt-4 text-[32px] font-semibold leading-tight tracking-tight">of refused applicants leave with a way to approval that holds up.</h2>
          <p className="mt-4 text-[16px] leading-relaxed text-muted">
            Measured on the 99 refusals of a test set the model never saw. Sound means valid, actionable, realistic, robust and fair. Remove one agent and
            the figure halves, or wrong advice reaches the applicant.
          </p>
        </div>
        <div ref={ref} className="reveal card p-6 sm:p-8">
          <div className="mb-5 flex flex-wrap gap-x-6 gap-y-2 text-[12.5px] text-muted">
            <span className="flex items-center gap-2">
              <span className="h-2 w-4 rounded-full bg-accent" /> Refusals given a sound way to approval
            </span>
            <span className="flex items-center gap-2">
              <span className="h-2 w-4 rounded-full bg-negative/80" /> Refusals given unsound advice
            </span>
          </div>
          <ul className="space-y-6">
            {SYSTEMS.map((s, i) => (
              <li key={s.name}>
                <p className={`text-[14px] ${s.highlight ? 'font-semibold text-ink' : 'text-soft'}`}>{s.name}</p>
                <div className="mt-2 flex items-center gap-3">
                  <Bar value={s.sound} tone={s.highlight ? 'accent' : 'muted'} delay={i * 120} visible={visible} />
                  <span className={`num w-11 text-right text-[13px] font-semibold ${s.highlight ? 'text-accent-ink' : 'text-soft'}`}>{Math.round(s.sound * 100)}%</span>
                </div>
                <div className="mt-1.5 flex items-center gap-3">
                  <Bar value={s.unsound} tone="negative" delay={i * 120 + 200} visible={visible} />
                  <span className="num w-11 text-right text-[13px] text-negative">{Math.round(s.unsound * 100)}%</span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}

function Fairness() {
  const rows = [
    { label: 'Women vs men', full: 9, unaware: 1 },
    { label: 'Aged 18 to 25 vs the most approved age band', full: 18, unaware: 11 },
  ]
  return (
    <section id="fairness" className="border-y border-hairline bg-surface">
      <div className="mx-auto grid max-w-6xl gap-14 px-6 py-28 lg:grid-cols-2">
        <div className="reveal">
          <h2 className="text-[36px] font-semibold leading-tight tracking-tight">Bias is measured, not assumed away.</h2>
          <p className="mt-4 text-[16px] leading-relaxed text-muted">
            Every decision goes through a flip test: change only the sex, the age or the nationality and score again. Twenty-two test files depend on a
            protected attribute; the auditor caught all twenty-two and sent them to a person. Group gaps are measured with Fairlearn for the audited model
            and for a version trained without protected attributes.
          </p>
        </div>
        <div className="reveal space-y-8">
          {rows.map((r) => (
            <div key={r.label}>
              <p className="text-[14px] font-medium">{r.label}</p>
              <p className="text-[12.5px] text-muted">Gap in approval rate, percentage points</p>
              <div className="relative mt-5 h-10">
                <span className="absolute inset-x-0 top-1/2 h-px bg-hairline" />
                {[0, 5, 10, 15, 20].map((t) => (
                  <span key={t} className="num absolute -bottom-3 -translate-x-1/2 text-[11px] text-faint" style={{ left: `${(t / 20) * 100}%` }}>
                    {t}
                  </span>
                ))}
                <span className="absolute top-1/2 h-px bg-ink/30" style={{ left: `${(r.unaware / 20) * 100}%`, width: `${((r.full - r.unaware) / 20) * 100}%` }} />
                <span className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-surface bg-positive" style={{ left: `${(r.unaware / 20) * 100}%` }} />
                <span className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-surface bg-caution" style={{ left: `${(r.full / 20) * 100}%` }} />
              </div>
              <div className="mt-6 flex gap-5 text-[12.5px] text-muted">
                <span className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-caution" /> Audited model: {r.full} pts
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-positive" /> Without protected attributes: {r.unaware} pts
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function Documents() {
  const [ref, progress] = useScrollProgress<HTMLDivElement>()
  const shift = (progress - 0.5) * 60
  return (
    <section ref={ref} className="relative overflow-hidden py-28">
      <div className="mx-auto grid max-w-6xl items-center gap-14 px-6 lg:grid-cols-2">
        <div className="relative h-[420px]">
          <div
            className="absolute left-0 top-6 w-[72%] rotate-[-4deg] rounded-lg bg-white p-6 text-[12px] leading-relaxed text-[#2a3140] shadow-lift ring-1 ring-black/5"
            style={{ transform: `translateY(${shift * 0.6}px) rotate(-4deg)` }}
          >
            <p className="text-right text-[10.5px] text-[#7a8291]">Casablanca</p>
            <p className="mt-3 font-semibold">Objet : Refus de votre demande de crédit, dossier GC-0217</p>
            <p className="mt-3">Madame, Monsieur,</p>
            <p className="mt-2">Nous vous informons que votre demande de crédit d'un montant de 3 104 DM sur 18 mois a été refusée.</p>
            <p className="mt-2">Piste 1 : rembourser sur 12 mois au lieu de 18 ; solder vos autres crédits à tempérament. Risque estimé après mise en œuvre : 22 %.</p>
            <p className="mt-2">Vous pouvez demander le réexamen de votre dossier par un conseiller.</p>
          </div>
          <div
            className="absolute bottom-0 right-0 w-[62%] rounded-lg bg-white p-5 shadow-lift ring-1 ring-black/5"
            style={{ transform: `translateY(${-shift}px) rotate(3deg)` }}
          >
            <p className="text-[12px] font-semibold text-[#0e1626]">Audit report AF-20261115</p>
            <div className="mt-3 space-y-2">
              {[90, 70, 82, 55, 76, 40].map((w, i) => (
                <span key={i} className="block h-1.5 rounded-full bg-[#e5e8e2]" style={{ width: `${w}%` }} />
              ))}
            </div>
            <div className="mt-4 grid grid-cols-3 gap-2 text-center text-[10.5px] text-[#637081]">
              {[
                ['57%', 'risk'],
                ['3', 'attempts'],
                ['22%', 'after path'],
              ].map(([v, k]) => (
                <span key={k} className="rounded bg-[#f2f3ef] py-2">
                  <span className="num block text-[15px] font-semibold text-[#0e1626]">{v}</span>
                  {k}
                </span>
              ))}
            </div>
          </div>
        </div>
        <div className="reveal">
          <h2 className="text-[36px] font-semibold leading-tight tracking-tight">The case closes with paperwork a regulator can read.</h2>
          <p className="mt-4 text-[16px] leading-relaxed text-muted">
            A PDF report with every figure, tool call and rejection, a JSONL trace of the run, and a letter to the applicant in French that states the
            reasons, the verified path and the right to a human review. Every number in the text is checked against the tools before it is accepted.
          </p>
          <Link to="/app/new" className="mt-8 inline-flex h-11 items-center gap-2 rounded-full bg-ink px-6 text-[15px] font-medium text-canvas transition hover:opacity-90">
            Audit a file yourself <ArrowRight size={16} />
          </Link>
        </div>
      </div>
    </section>
  )
}

export function Landing() {
  const y = useScrollY()
  useReveal()
  useEffect(() => {
    const prev = document.documentElement.dataset.theme
    document.documentElement.dataset.theme = 'light'
    return () => {
      if (prev) document.documentElement.dataset.theme = prev
    }
  }, [])

  return (
    <div data-theme="light" className="bg-canvas text-ink">
      <Nav solid={y > 40} />

      <section className="relative overflow-hidden bg-night pb-24 pt-32 text-white sm:pt-40">
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.35]"
          style={{
            backgroundImage: 'linear-gradient(rgba(255,255,255,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.06) 1px, transparent 1px)',
            backgroundSize: '56px 56px',
            maskImage: 'radial-gradient(ellipse 70% 60% at 50% 30%, black, transparent)',
            transform: `translateY(${y * 0.25}px)`,
          }}
        />
        <div
          className="pointer-events-none absolute -top-40 left-1/2 h-[620px] w-[920px] -translate-x-1/2 rounded-full opacity-60 blur-[110px]"
          style={{ background: 'radial-gradient(closest-side, #2b4eff, rgba(43,78,255,0.15) 60%, transparent)', transform: `translate(-50%, ${y * 0.4}px)` }}
        />
        <div className="relative mx-auto grid max-w-6xl items-center gap-14 px-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div style={{ transform: `translateY(${y * -0.08}px)` }}>
            <p className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-[12.5px] text-white/70">
              <span className="h-1.5 w-1.5 rounded-full bg-[#3cc28f]" /> Agentic credit audit with counterfactual explanations
            </p>
            <h1 className="mt-6 text-[46px] font-semibold leading-[1.02] tracking-[-0.03em] sm:text-[64px]">
              Every refused loan gets a reason and a way back.
            </h1>
            <p className="mt-6 max-w-lg text-[18px] leading-relaxed text-white/65">
              Five AI agents audit a credit decision. They explain the score, search for the smallest realistic change that turns it into an approval,
              test it for bias, and write the letter. When they are unsure, a person decides.
            </p>
            <div className="mt-9 flex flex-wrap gap-3">
              <Link to="/app/new" className="inline-flex h-12 items-center gap-2 rounded-full bg-accent px-6 text-[15px] font-medium text-white shadow-[0_8px_30px_-6px_rgba(43,78,255,0.7)] transition hover:brightness-110">
                Run a live audit <ArrowRight size={16} />
              </Link>
              <a href="#how" className="inline-flex h-12 items-center rounded-full border border-white/20 px-6 text-[15px] font-medium text-white/85 transition hover:bg-white/5">
                See how it works
              </a>
            </div>
            <dl className="mt-14 grid max-w-lg grid-cols-3 gap-6 border-t border-white/10 pt-6">
              {[
                ['1,000', 'real loan files, German Credit'],
                ['0.806', 'test AUC, calibrated LightGBM'],
                ['104', 'automated tests'],
              ].map(([v, k]) => (
                <div key={k}>
                  <dt className="num text-[24px] font-semibold tracking-tight">{v}</dt>
                  <dd className="mt-1 text-[12.5px] leading-snug text-white/50">{k}</dd>
                </div>
              ))}
            </dl>
          </div>
          <CaseFile />
        </div>
      </section>

      <HowItWorks />
      <Evidence />
      <Fairness />
      <Documents />

      <section className="relative overflow-hidden bg-night text-white">
        <div
          className="pointer-events-none absolute -bottom-48 left-1/2 h-[480px] w-[820px] -translate-x-1/2 rounded-full opacity-50 blur-[110px]"
          style={{ background: 'radial-gradient(closest-side, #2b4eff, transparent)' }}
        />
        <div className="relative mx-auto max-w-6xl px-6 py-24 text-center">
          <h2 className="mx-auto max-w-2xl text-[40px] font-semibold leading-tight tracking-tight">Pick a real applicant and watch the five agents work.</h2>
          <p className="mx-auto mt-4 max-w-xl text-[16px] text-white/60">Six files from the held-out test set, one for each route an audit can take.</p>
          <Link to="/app/new" className="mt-9 inline-flex h-12 items-center gap-2 rounded-full bg-white px-7 text-[15px] font-medium text-night transition hover:bg-white/90">
            Open the console <ArrowRight size={16} />
          </Link>
        </div>
        <footer className="relative border-t border-white/10">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-6 text-[13px] text-white/45">
            <span className="flex items-center gap-2.5 text-white/70">
              <Logo inverted size={20} /> AgentForge
            </span>
            <span>Marouane Daouki and Imane Alouani, Master IA, Faculté des Sciences Ben M'Sik, Université Hassan II de Casablanca</span>
          </div>
        </footer>
      </section>
    </div>
  )
}
