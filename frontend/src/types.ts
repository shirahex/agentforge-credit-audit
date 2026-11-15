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

export interface Plausibility {
  score: number
  knn_distance: number
  limit: number
  applicant_distance: number
  plausible: boolean
  neighbours_repaid: number
  k: number
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
  plausibility: Plausibility | null
}

export interface PastAudit {
  run_id: string
  applicant_id: string
  similarity: number
  decision: Decision
  final_outcome: Decision
  default_probability: number
  escalated: boolean
  reviewed: boolean
  attempts: number
  paths: number
  best_path: string
  closed_at: string
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
  precedents: PastAudit[]
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
  verdict: string
  notes: string[]
  group_context: GroupContext[]
  candidates_checked: number
  candidates_kept: number
}

export interface GroupContext {
  attribute: string
  label: string
  group: string
  approval_rate: number
  best_group: string
  best_approval_rate: number
  gap: number
  comparable: boolean
  disadvantaged: boolean
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
  report_id: string | null
  letter: string
  letter_status: 'draft' | 'final'
  review: Review | null
  final_outcome: Decision | null
  precedents: PastAudit[]
  precedent_conflict: string | null
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
  status: 'running' | 'awaiting_review' | 'finished' | 'error'
  done: boolean
  decision: Decision | null
  final_outcome: Decision | null
  report_id: string | null
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
  store: { audits: number; cases: number; awaiting_review: number }
}

export interface GroupStats {
  n: number
  selection_rate: number
  true_positive_rate: number
  false_positive_rate: number
  small_sample: boolean
}

export interface AttributeFairness {
  label: string
  groups: Record<string, GroupStats>
  demographic_parity_difference: number
  demographic_parity_ratio: number
  equalized_odds_difference: number
  least_approved: string
  most_approved: string
  ci95: { demographic_parity_difference: [number, number]; equalized_odds_difference: [number, number] } | null
  reliable_gap: number | null
  alert: boolean
  four_fifths_ok: boolean
}

export interface FairnessReport {
  variant: string
  model_version: string
  threshold: number
  files: number
  approval_rate: number
  attributes: Record<string, AttributeFairness>
}

export interface FairnessComparison {
  full: FairnessReport
  unaware: FairnessReport
  tolerance: number
  min_group: number
  reading: string[]
  definitions: Record<string, string>
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
  fairness: FairnessComparison | null
}
