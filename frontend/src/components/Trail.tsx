import type { AgentEvent } from '../types'

const DOT: Record<AgentEvent['status'], string> = {
  completed: 'bg-ink',
  finished: 'bg-ink',
  rejected: 'bg-negative',
  escalated: 'bg-caution',
  error: 'bg-negative',
}

function args(a: Record<string, unknown>): string {
  return Object.entries(a)
    .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : String(v)}`)
    .join('; ')
}

/** Every agent step with its tool calls: the audit trail of one file. */
export function Trail({ events, running }: { events: AgentEvent[]; running: boolean }) {
  if (events.length === 0)
    return <p className="text-sm text-muted">{running ? 'The first agent is reading the file.' : 'No step recorded.'}</p>
  const start = new Date(events[0].ts).getTime()
  return (
    <ol className="relative space-y-5 before:absolute before:bottom-2 before:left-[4.5px] before:top-2 before:w-px before:bg-hairline">
      {events.map((e) => (
        <li key={e.seq} className="settle relative pl-6">
          <span className={`absolute left-0 top-[7px] h-2.5 w-2.5 rounded-full ring-4 ring-surface ${DOT[e.status]}`} />
          <details>
            <summary className="rounded-md">
              <span className="flex items-baseline justify-between gap-3">
                <span className="font-medium">{e.agent}</span>
                <span className="num shrink-0 text-xs text-faint">
                  +{((new Date(e.ts).getTime() - start) / 1000).toFixed(1)} s
                </span>
              </span>
              <span className="mt-0.5 block text-sm text-muted">{e.message}</span>
              <span className="mt-1 block text-xs text-accent">
                {e.tool_calls.length > 0 ? `${e.tool_calls.length} tool call${e.tool_calls.length > 1 ? 's' : ''}, ` : ''}
                {e.mode === 'llm' ? 'language model' : 'rules'}
              </span>
            </summary>
            <div className="mt-3 space-y-3 rounded-xl bg-canvas p-3 text-sm">
              {e.reasoning && <p className="text-soft">{e.reasoning}</p>}
              {e.tool_calls.map((t, i) => (
                <div key={i}>
                  <p className="flex justify-between gap-2 font-medium">
                    <span className="break-all">{t.name}</span>
                    <span className="num shrink-0 font-normal text-faint">{t.duration_ms.toFixed(0)} ms</span>
                  </p>
                  {Object.keys(t.arguments).length > 0 && <p className="break-words text-muted">{args(t.arguments)}</p>}
                  {t.result && <p className="break-words text-soft">{t.result}</p>}
                </div>
              ))}
            </div>
          </details>
        </li>
      ))}
    </ol>
  )
}
