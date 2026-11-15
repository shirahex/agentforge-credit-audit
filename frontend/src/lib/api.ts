import type { AgentEvent, LoanApplication } from '../types'

export async function fetchSamples(): Promise<LoanApplication[]> {
  const res = await fetch('/api/samples')
  if (!res.ok) throw new Error(`samples: HTTP ${res.status}`)
  return res.json()
}

export async function startAudit(application: LoanApplication): Promise<string> {
  const res = await fetch('/api/audits', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(application),
  })
  if (!res.ok) throw new Error(`audit: HTTP ${res.status}`)
  return (await res.json()).run_id
}

/** Subscribes to the audit trail. Returns a function that closes the stream. */
export function streamEvents(
  runId: string,
  onEvent: (event: AgentEvent) => void,
  onEnd: () => void,
): () => void {
  const source = new EventSource(`/api/audits/${runId}/events`)
  source.onmessage = (msg) => onEvent(JSON.parse(msg.data))
  const finish = () => {
    source.close()
    onEnd()
  }
  source.addEventListener('end', finish)
  source.onerror = finish
  return () => source.close()
}
