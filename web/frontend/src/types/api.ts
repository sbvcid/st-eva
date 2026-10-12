/**
 * Typed API interfaces corresponding to ST-EVA Web API schemas.
 */

export type JobStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED'

export type JobProgressStage =
  | 'pending'
  | 'resolving'
  | 'fetching SEC'
  | 'admission'
  | 'valuation'
  | 'archive/replay'
  | 'completed'
  | 'failed'

export interface RefusalItem {
  ref?: string | null
  reason: string
  category?: string | null
}

export interface AdmissionSummary {
  total_admitted: number
  total_refused: number
  metrics_admitted: string[]
  refusals: RefusalItem[]
}

export interface ReplaySummary {
  attempted: boolean
  outcome?: 'MATCH' | 'DIVERGED' | 'INSUFFICIENT' | 'NO_SNAPSHOT' | string | null
  reason?: string | null
  matched: boolean
  reconstructed: boolean
  observations_used: number
  observations_considered: number
  replay_fidelity?: string | null
  stored_document_hash?: string | null
  rebuilt_document_hash?: string | null
}

export interface ValuationSummary {
  analysis_type?: string | null
  current_price?: number | null
  currency?: string | null
  as_of?: string | null
  forward_eps_at_reference_multiple?: number | null
  eps_gap_vs_consensus?: number | null
  required_eps_cagr?: number | null
  selected_pe?: number | null
  // Basis of the summary headline metrics, so they are not mistaken for a
  // reverse-requirements matrix row. `selected_pe_basis` is the summary
  // engine's own reference method: 'user_supplied_multiple',
  // 'historical_pe_median', or 'none'. `summary_horizon_years` is the horizon
  // the summary CAGR is annualised over (default 1.0 on the web path).
  selected_pe_basis?: string | null
  summary_horizon_years?: number | null
  observed_pe?: number | null
  observed_ps?: number | null
  observed_pfcf?: number | null
  observed_ev_ebitda?: number | null
  consensus_forward_eps?: number | null
  limitations: string[]
}

export interface ReferenceMultipleDTO {
  value: number
  source: string
  period_label?: string
  sample_size?: number | null
  sample_period?: string
  conditionality?: string | null
  is_user_assumption?: boolean
  eligibility_state?: string | null
  usable_for_reference?: boolean | null
}

export interface SecFactDTO {
  accession?: string | null
  form?: string | null
  filed_date?: string | null
  concept?: string | null
  unit?: string | null
  period_start?: string | null
  period_end?: string | null
  document_url?: string | null
}

export interface RelatedSecEvidenceDTO extends SecFactDTO {
  note?: string | null
}

export interface EpsAnchorDTO {
  value: number
  basis: string
  months_covered: number
  period_label?: string
  period_start?: string | null
  period_end?: string | null
  provider?: string
  currency?: string | null
  period_undeclared_by_source?: boolean
  source_type?: string | null
  observation_id?: string | null
  is_user_assumption?: boolean
  sec_fact?: SecFactDTO | null
}

export interface MarketPriceEvidenceDTO {
  value: number
  currency?: string | null
  as_of?: string | null
  provider: string
  source_type: string
  observation_id?: string | null
  is_user_assumption: boolean
}

export interface EpsAnchorEvidenceDTO {
  value: number
  basis: string
  months_covered: number
  period_label?: string
  period_start?: string | null
  period_end?: string | null
  provider?: string
  currency?: string | null
  period_undeclared_by_source?: boolean
  source_type?: string | null
  observation_id?: string | null
  is_user_assumption?: boolean
  sec_fact?: SecFactDTO | null
}

export interface ExitMultipleEvidenceDTO {
  value: number
  source: string
  period_label?: string
  sample_size?: number | null
  sample_period?: string
  conditionality?: string | null
  is_user_assumption: boolean
  eligibility_state: string
  usable_for_reference: boolean
}

export interface CalculationStepDTO {
  step_number: number
  step_id: string
  name: string
  formula_expression: string
  operands: Record<string, any>
  output_value?: number | null
  output_unit?: string
  reproducible: boolean
  status: string
  status_reason?: string | null
}

export interface ProductionHistoricalPeDTO {
  issuer_id?: string | null
  instrument_id?: string | null
  metric_id?: string | null
  status?: string | null
  usable_for_reference?: boolean | null
  sample_count?: number | null
  total_evaluations?: number | null
  min_observations_required?: number | null
  period_start?: string | null
  period_end?: string | null
  mean?: number | null
  std?: number | null
  min?: number | null
  max?: number | null
  percentiles?: Record<string, number> | null
  current_pe?: number | null
  current_pe_as_of?: string | null
  sampling_cadence?: string | null
  evaluation_schedule_description?: string | null
  excluded_observation_count?: number | null
  input_set_id?: string | null
  content_hash?: string | null
  reason_code?: string | null
  reason_detail?: string | null
}

export interface ScenarioEvidenceDTO {
  price_evidence: MarketPriceEvidenceDTO
  eps_evidence: EpsAnchorEvidenceDTO
  multiple_evidence: ExitMultipleEvidenceDTO
  user_assumptions: string[]
  sourced_facts: string[]
  missing_or_unvalidated: string[]
  related_sec_evidence?: RelatedSecEvidenceDTO | null
}

export interface EpsScenarioDTO {
  price?: number | null
  as_of?: string | null
  horizon_years: number
  required_return: number
  required_return_basis: string
  exit_multiple: ReferenceMultipleDTO
  required_exit_price?: number | null
  required_exit_price_basis?: string | null
  required_terminal_eps?: number | null
  start_eps: EpsAnchorDTO
  growth_years?: number | null
  required_eps_cagr?: number | null
  total_terminal_eps_growth?: number | null
  terminal_eps_vs_start_pct?: number | null
  terminal_pe_change_vs_current_pe?: number | null
  gap_vs_consensus_terminal_eps?: number | null
  comparison_notes: string[]
  flags: string[]
  formula_version: string
  dividend_per_share?: number | null
  dividend_convention?: string | null
  dividend_relief_exit_price?: number | null
  dividend_relief_terminal_eps?: number | null
  dividend_relief_cagr?: number | null
  evidence?: ScenarioEvidenceDTO | null
  calculation_steps?: CalculationStepDTO[]
}

export interface ReverseRequirementsReportDTO {
  formula_version: string
  fingerprint?: string | null
  status: 'COMPUTED' | 'NOT_COMPUTED' | string
  status_reason?: string | null
  matrix_size: number
  reverse_requirements_matrix: EpsScenarioDTO[]
  reading_notes?: string[]
  unavailable?: Array<Record<string, any>>
  dividend_basis?: Record<string, any> | null
  total_return_scenarios?: Record<string, any> | null
  price_vs_total_return_comparison?: Array<Record<string, any>> | null
  production_historical_pe_summary?: ProductionHistoricalPeDTO | null
}

export interface AnalysisResultDTO {
  ticker: string
  company_name: string
  status: string
  research_id?: string | null
  as_of?: string | null
  source_identifiers: string[]
  admission_summary: AdmissionSummary
  valuation_summary: ValuationSummary
  replay_summary: ReplaySummary
  refusal_reasons: string[]
  reverse_requirements?: ReverseRequirementsReportDTO | null
  production_historical_pe?: ProductionHistoricalPeDTO | null
  raw_analysis?: Record<string, any> | null
}

export interface AnalyzeRequest {
  ticker: string
  mode?: string
  reference_multiple?: number | null
  reference_multiples?: number[] | null
  horizon_years?: number
  reverse_horizons?: number[] | null
  required_returns?: number[] | null
  prefer_eps_anchor?: string | null
  user_eps?: number | null
}

export interface AnalyzeResponse {
  job_id: string
  ticker: string
  status: JobStatus
}

export interface JobDetailResponse {
  job_id: string
  ticker: string
  status: JobStatus
  stage: JobProgressStage
  created_at: string
  updated_at: string
  error?: string | null
  result?: AnalysisResultDTO | null
}

export interface HealthResponse {
  status: string
  version: string
}

