export interface ResearchMetric {
  metric_id: string
  lane_id: string
  issuer_id: string
  instrument_id: string
  metric_label: string
  research_purpose: string
  research_use_label: string
  formula_expression: string
  formula_version: string
  formula_numerator: string
  formula_denominator: string
  numerator_kind: string
  numerator_label: string
  denominator_label: string
  status: string
  production_eligible: boolean
  candidate_metric: boolean
  sample_count: number
  total_evaluations: number
  refused_count: number
  period_start: string | null
  period_end: string | null
  mean: number | null
  std: number | null
  minimum: number | null
  maximum: number | null
  percentiles: Record<string, number | null>
  median: number | null
  sampling_cadence: string
  registry_standing: Record<string, Record<string, ResearchRegistryStanding>>
  production_refusal: Record<string, unknown>
  data_limitations: string[]
  basis_breaks: Record<string, string[]>
  prior_period_revisions: ResearchRevision[]
  input_set_id: string
  content_hash: string
  methodology: string
  logic_version: string
}

export interface ResearchRegistryStanding {
  role: string
  element: string
  registry_metric_id: string | null
  registry_decision: string
  reason_code: string | null
  qualified: boolean | null
  mapping_type: string | null
  relation_kind: string | null
  scope: string | null
  effective_from: string | null
  effective_to: string | null
  basis: string | null
}

export interface ResearchRevision {
  classification: string
  role: string
  period_start: string
  period_end: string
  detected_at_evaluation_date: string
  old_value: number
  old_accession: string
  old_usable_date: string
  old_element: string
  new_value: number
  new_accession: string
  new_usable_date: string
  new_element: string
  difference: number
  difference_ratio: number | null
  element_changed: boolean
  element_change_kind: string | null
  affected_observation_count: number
  note: string
}

export interface ResearchCatalogue {
  metrics: ResearchMetric[]
  research_use_notice: string
  user_assumption_label: string
  calculator_version: string
}

export interface ResearchObservation {
  evaluation_date: string
  status: string
  value: number | null
  reason_code: string | null
  reason_detail: string | null
  price: number | null
  shares_outstanding: number | null
  market_cap: number | null
  enterprise_value: number | null
  denominator: number | null
  basis_breaks: string[]
  content_hash: string
}

export interface ResearchMetricDetail {
  metric: ResearchMetric
  observations: ResearchObservation[]
}

export interface ResearchCalculation {
  metric_id: string
  lane_id: string
  issuer_id: string
  instrument_id: string
  status: string
  production_eligible: boolean
  research_use_label: string
  multiple: number
  multiple_source: string
  multiple_label: string
  multiple_observation_date: string | null
  multiple_observation_content_hash: string | null
  numerator: number
  numerator_source: string
  numerator_label: string
  numerator_kind: string
  numerator_date: string | null
  numerator_observation_content_hash: string | null
  implied_denominator: number
  implied_denominator_label: string
  formula_expression: string
  formula_version: string
  formula_operands: Record<string, unknown>
  lane_input_set_id: string
  lane_content_hash: string
  calculation_content_hash: string
  calculation_version: string
  methodology: string
  logic_version: string
  numerator_evidence: Record<string, any>
  multiple_evidence: Record<string, any>
  registry_standing: Record<string, Record<string, ResearchRegistryStanding>>
  basis_breaks: string[]
  prior_period_revisions: ResearchRevision[]
  production_refusal: Record<string, unknown>
  data_limitations: string[]
}

export interface ResearchRefusal {
  reason_code: string
  detail: string
  production_eligible: boolean
}
