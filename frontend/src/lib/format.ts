import type { AgentEvent, NodeId } from '../types'

export const pct = (p: number, digits = 0) => `${(p * 100).toFixed(digits)}%`
export const dm = (n: number) => `${n.toLocaleString('en-US')} DM`

export function clock(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
}

export function dateTime(iso: string): string {
  return new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

export const NODES: { id: NodeId; name: string; role: string }[] = [
  { id: 'analyste_dossier', name: 'Analyste-Dossier', role: 'Checks the file' },
  { id: 'modele_scoring', name: 'Modèle-Scoring', role: 'Scores and explains' },
  { id: 'generateur_contrefactuels', name: 'Générateur-Contrefactuels', role: 'Searches for ways to approval' },
  { id: 'verificateur_equite', name: 'Vérificateur-Équité', role: 'Audits the result' },
  { id: 'arbitre_redacteur', name: 'Arbitre et Rédacteur', role: 'Closes or escalates' },
]

export type StepState = 'idle' | 'running' | 'done' | 'rejected' | 'escalated' | 'skipped'

export interface PipelineView {
  states: Record<NodeId, StepState>
  attempts: number
  rejections: number
  looping: boolean
  failed: boolean
}

/** Rebuilds the state of the five agents from the event stream alone. */
export function pipelineView(events: AgentEvent[], done: boolean, maxAttempts: number): PipelineView {
  const states = Object.fromEntries(NODES.map((n) => [n.id, 'idle'])) as Record<NodeId, StepState>
  let attempts = 0
  let rejections = 0
  let refused = false
  let next: NodeId | null = 'analyste_dossier'
  let looping = false
  let failed = false

  for (const e of events) {
    if (e.node === 'system') {
      failed = true
      next = null
      continue
    }
    looping = false
    states[e.node] = e.status === 'rejected' ? 'rejected' : e.status === 'escalated' ? 'escalated' : 'done'
    if (e.node === 'analyste_dossier') next = 'modele_scoring'
    else if (e.node === 'modele_scoring') {
      refused = e.payload.score?.decision === 'refused'
      next = refused ? 'generateur_contrefactuels' : 'verificateur_equite'
      if (!refused) states.generateur_contrefactuels = 'skipped'
    } else if (e.node === 'generateur_contrefactuels') {
      attempts += 1
      next = 'verificateur_equite'
    } else if (e.node === 'verificateur_equite') {
      const empty = (e.payload.counterfactuals ?? []).length === 0
      if (refused && empty) rejections += 1
      if (refused && empty && attempts < maxAttempts) {
        next = 'generateur_contrefactuels'
        looping = true
      } else next = 'arbitre_redacteur'
    } else next = null
  }
  if (!done && !failed && next) states[next] = 'running'
  return { states, attempts, rejections, looping, failed }
}
