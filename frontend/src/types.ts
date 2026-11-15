// Mirror of backend/app/schemas.py. Both files change together.

export type Decision = 'approved' | 'refused'

export interface LoanApplication {
  applicant_id: string
  duration_months: number
  credit_amount: number
  age: number
  sex: 'male' | 'female'
  purpose: string
  housing: 'own' | 'rent' | 'free'
  employment_years: number
  savings: 'none' | 'low' | 'medium' | 'high'
  checking_status: 'none' | 'negative' | 'low' | 'high'
  foreign_worker: boolean
}

export interface FeatureChange {
  feature: string
  from_value: string | number | boolean
  to_value: string | number | boolean
}

export interface Counterfactual {
  changes: FeatureChange[]
  new_probability: number
  valid: boolean
  actionable: boolean
  rejection_reason: string | null
}

export interface FairnessVerdict {
  passed: boolean
  reasons: string[]
  metrics: Record<string, number>
  flip_test_passed: boolean
}

export interface AuditDecision {
  applicant_id: string
  decision: Decision
  default_probability: number
  escalated: boolean
  escalation_reason: string | null
  summary: string
  counterfactuals: Counterfactual[]
  fairness: FairnessVerdict | null
  attempts: number
  report_path: string | null
}

export interface AgentEvent {
  run_id: string
  seq: number
  agent: string
  status: 'completed' | 'rejected' | 'escalated' | 'finished' | 'error'
  message: string
  payload: { decision?: AuditDecision } & Record<string, unknown>
  ts: string
}
