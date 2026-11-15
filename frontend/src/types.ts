// Mirror of backend/app/schemas.py. Both files change together.

export type Decision = 'approved' | 'refused'
export type Value = string | number | boolean

export type LoanApplication = Record<string, Value> & { applicant_id: string }

export interface FeatureSpec {
  name: string
  label: string
  kind: 'numeric' | 'categorical' | 'boolean'
  group: string
  unit: string
  min: number | null
  max: number | null
  protected: boolean
  recourse: 'request' | 'situation' | 'fixed'
  options: { value: string; label: string }[]
}

export interface Schema {
  features: FeatureSpec[]
  threshold: number
  borderline_margin: number
  max_attempts: number
}

export interface Sample {
  tag: string
  title: string
  description: string
  application: LoanApplication
}

export interface Factor {
  feature: string
  label: string
  value: Value
  value_label: string
  contribution: number
}

export interface ScoreResult {
  default_probability: number
  threshold: number
  decision: Decision
  risk_band: 'low' | 'medium' | 'high'
  base_probability: number
  top_factors: Factor[]
  model_version: string
}

export interface FeatureChange {
  feature: string
  label: string
  from_value: Value
  to_value: Value
  from_label: string
  to_label: string
}

export interface Counterfactual {
  changes: FeatureChange[]
  new_probability: number
  valid: boolean
  actionable: boolean
  rejection_reason: string | null
  robust: boolean
  effort: 'immediate' | 'medium_term'
  cost: number
  source: 'exhaustive' | 'dice'
  statement: string
}

export interface SimilarCase {
  applicant_id: string
  distance: number
  defaulted: boolean
  credit_amount: number
  duration_months: number
}

export interface AnalystReport {
  warnings: string[]
  peer_default_rate: number | null
  peer_count: number
  peers: SimilarCase[]
  note: string
}

export interface ToolCall {
  name: string
  arguments: Record<string, unknown>
  result: string
  duration_ms: number
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

export type NodeId =
  | 'analyste_dossier'
  | 'modele_scoring'
  | 'generateur_contrefactuels'
  | 'verificateur_equite'
  | 'arbitre_redacteur'

export interface AgentEvent {
  run_id: string
  seq: number
  agent: string
  node: NodeId | 'system'
  status: 'completed' | 'rejected' | 'escalated' | 'finished' | 'error'
  message: string
  reasoning: string
  mode: 'llm' | 'rules'
  tool_calls: ToolCall[]
  payload: {
    analysis?: AnalystReport
    score?: ScoreResult
    explanation?: string
    counterfactuals?: Counterfactual[]
    fairness?: FairnessVerdict
    decision?: AuditDecision
  }
  ts: string
}

export interface Review {
  outcome: Decision
  reviewer: string
  comment: string
  at: string
}

export interface AuditSummary {
  run_id: string
  applicant_id: string
  started_at: string
  finished_at: string | null
  done: boolean
  decision: Decision | null
  default_probability: number | null
  escalated: boolean
  attempts: number
  paths: number
  review: Review | null
}

export interface AuditRecord extends AuditSummary {
  application: LoanApplication
  events: AgentEvent[]
  result: AuditDecision | null
}

export interface Health {
  status: string
  model: string
  variant: string
  threshold: number
  llm: { provider: string; model: string; enabled: boolean; calls: number; failures: number; last_error: string }
}

export interface PolicyMetrics {
  threshold: number
  rule: string
  auc: number
  refusal_rate: number
  expected_cost: number
  confusion: { bad_refused: number; bad_approved: number; good_refused: number; good_approved: number }
}

export interface ModelMeta {
  version: string
  variant: string
  threshold: number
  data: { train_rows: number; test_rows: number; default_rate: number }
  cv: { scheme: string; lightgbm_auc: number; baseline_logreg_auc: number; configs_tried: number }
  test: PolicyMetrics & { auc_ci95: [number, number]; ks: number; brier: number; cost_approve_all: number; cost_refuse_all: number }
  test_baseline_logreg: { auc: number; ks: number; brier: number }
  policies: Record<string, PolicyMetrics>
  monotone_increasing: string[]
}

export interface AuditStats {
  files: number
  refused: number
  approved: number
  escalated?: number
  no_path?: number
  solved_attempt_1?: number
  solved_attempt_2?: number
  solved_attempt_3?: number
  flip_test_failed?: number
  recourse_rate: number
  immediate_recourse_rate: number
  mean_paths: number
  flip_test_failure_rate: number
  ms_per_audit: number
}

export interface ModelCard {
  meta: ModelMeta
  comparison: ModelMeta | null
  summary: {
    roc: [number, number][]
    roc_baseline: [number, number][]
    calibration: { predicted: number; observed: number; count: number }[]
    histogram: { edges: number[]; repaid: number[]; defaulted: number[] }
    cost_curve: [number, number][]
    ks_curve: [number, number][]
    shap_importance: { feature: string; label: string; value: number }[]
    audit: Record<string, AuditStats>
  } | null
  labels: Record<string, string>
}
