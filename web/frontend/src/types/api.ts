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
  // The metric names behind `total_refused` (deduplicated), so the refused
  // count can be reconciled with a list even when `refusals` also carries
  // context-availability entries that are not admission rows.
  metrics_refused?: string[]
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
  // Structured observation-level diff: which observations the replay considered
  // and their availability class. Used to explain a DIVERGED outcome with
  // concrete per-observation detail rather than only a generic reason string.
  availability_classes?: Array<{ observation_id: string; class: string }> | null
  // Field-level differences between the stored context and the rebuilt
  // context. Each entry has `field` (dotted path), `stored` (old value),
  // and `rebuilt` (new value). Volatile fields (timestamps, hashes,
  // refc:* reference timestamps) are excluded.
  field_diffs?: Array<{ field: string; stored: unknown; rebuilt: unknown }> | null
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
  // 'production_historical_pe_median', 'historical_pe_median', or 'none'.
  // 'production_historical_pe_median' is the median of the eligible
  // point-in-time historical P/E distribution -- the same reference the
  // matrix's eligible exit multiples are drawn from, so a computed matrix
  // and this summary cannot disagree about whether a reference exists.
  // `summary_horizon_years` is the horizon the summary CAGR is annualised
  // over (default 1.0 on the web path).
  selected_pe_basis?: string | null
  // The cash-flow reference and the figure it inverts into, carried with the
  // same basis discipline as the P/E reference: the basis names where the
  // number came from, and an absent reference stays absent rather than being
  // filled from the P/E or from a band.
  selected_pfcf?: number | null
  selected_pfcf_basis?: string | null
  implied_fcf_at_reference_multiple?: number | null
  // The observed market capitalisation the cash-flow figure was inverted from
  // (`implied_fcf_at_reference_multiple == market_cap / selected_pfcf`), in
  // `currency`. A total, never a per-share figure; carried so the headline can
  // be recomputed from the response and the export.
  market_cap?: number | null
  // Operands each non-earnings method inverts from, so the implied figure can
  // be recomputed straight from the response:
  //   implied_revenue == market_cap / P/S
  //   implied_fcf     == market_cap / P/FCF
  //   implied_ebitda  == enterprise_value / EV/EBITDA
  // Totals in `currency`, never per-share figures; absent when not observed.
  enterprise_value?: number | null
  revenue?: number | null
  ebitda?: number | null
  fcf?: number | null
  summary_horizon_years?: number | null
  observed_pe?: number | null
  observed_ps?: number | null
  observed_pfcf?: number | null
  observed_ev_ebitda?: number | null
  consensus_forward_eps?: number | null
  /** The vendor's own consensus period label, kept verbatim (e.g. "+1y"). */
  consensus_forward_eps_period?: string | null
  /**
   * The fiscal-period end the source declared for that consensus estimate.
   * Null whenever the source declared none; never inferred from the label.
   */
  consensus_forward_eps_period_end?: string | null
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

export interface ValuationMethodResultDTO {
  // One valuation method's single-point reverse result (revenue / P/S,
  // cash flow / P/FCF, enterprise value / EV/EBITDA). It carries no
  // holding period, required return or EPS CAGR -- it is a different
  // question from the EPS matrix scenario.
  status?: 'COMPUTED' | 'NOT_COMPUTED' | string
  // The reference multiple in force for this method. For revenue /
  // cash_flow / enterprise_value this is ReferenceMultiple-shaped;
  // implied_net_margin carries a pe/revenue pair instead, so the type is
  // deliberately permissive and implied_net_margin is not rendered.
  reference_multiple?: ReferenceMultipleDTO | Record<string, any> | null
  implied?: number | null
  observed?: number | null
  unit?: string | null
  gap_implied_vs_observed?: number | null
  notes?: string[]
  reason_kind?: string | null
  reason_detail?: string | null
}

export interface ValuationMethodsDTO {
  methods?: Record<string, ValuationMethodResultDTO> | null
  unavailable?: Array<Record<string, any>> | null
  reading_notes?: string[]
}

export interface ProvenanceEntryDTO {
  // Where one observed fundamental came from and on what basis, so the reader
  // can tell a filed figure from a provider's and a trailing figure from a
  // year's or quarter's, and check the implied figure against it.
  // `value` is either the observed number or the engine's named-absence
  // sentinel (e.g. "UNAVAILABLE"), never coerced to zero.
  value?: number | string | null
  source?: string | null
  basis?: string | null
  currency?: string | null
  derivation?: string | null
  usable_from?: string | null
  period_start?: string | null
  period_end?: string | null
  used_by_engine?: boolean | null
  note?: string | null
  provider_figure?: Record<string, any> | null
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
  acceptance_datetime?: string | null
  available_at?: string | null
  available_at_basis?: string | null
  evidence_class?: string | null
  gaap_basis?: string | null
  source_url?: string | null
}

export interface EpsAnchorComponentDTO {
  period_start?: string | null
  period_end?: string | null
  value?: number | null
  form?: string | null
  accession?: string | null
  filed_date?: string | null
  acceptance_datetime?: string | null
  available_at?: string | null
  available_at_basis?: string | null
  evidence_class?: string | null
  fiscal_year?: number | string | null
  fiscal_period?: string | null
  fiscal_quarter?: number | string | null
  concept?: string | null
  gaap_basis?: string | null
  source_url?: string | null
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
  anchor_id?: string | null
  anchor_nature?: string | null
  anchor_gaap_basis?: string | null
  available_at?: string | null
  available_at_basis?: string | null
  sec_components?: EpsAnchorComponentDTO[] | null
  annual_comparison?: Record<string, any> | null
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
  anchor_id?: string | null
  anchor_nature?: string | null
  anchor_gaap_basis?: string | null
  available_at?: string | null
  available_at_basis?: string | null
  sec_components?: EpsAnchorComponentDTO[] | null
  annual_comparison?: Record<string, any> | null
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

export interface ProductionHistoricalPfcfDTO {
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
  current_pfcf?: number | null
  current_pfcf_as_of?: string | null
  sampling_cadence?: string | null
  evaluation_schedule_description?: string | null
  excluded_observation_count?: number | null
  input_set_id?: string | null
  content_hash?: string | null
  reason_code?: string | null
  reason_detail?: string | null
}

export interface ProductionHistoricalMultiplesDistributionDTO {
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

/**
 * The consensus EPS the matrix gap column is differenced against.
 *
 * `source_period_label` is the vendor's own label ("+1y"), kept verbatim.
 * `period_end` is the calendar date the same source declared for that
 * estimate, and is null whenever the source declared none. It is never
 * derived from the label, so a "+1y" row cannot be read as a date.
 *
 * No verdict lives here: whether a row's terminal EPS covers the same period
 * depends on that row's horizon, so the verdict is on each scenario.
 */
export interface ConsensusReferenceDTO {
  eps?: number | null
  provider?: string
  basis?: string
  months_covered?: number | null
  source_period_label?: string | null
  period_end?: string | null
  period_end_declared_by_source?: boolean
  target_period_end?: string | null
  comparison_tolerance_days?: number | null
  comparable_horizon_years?: number | null
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
  production_historical_pfcf_summary?: ProductionHistoricalPfcfDTO | null
  production_historical_multiples_summary?: Record<string, any> | null
  // Each production distribution for P/S, P/FCF and EV/EBITDA that the
  # report computed from its own committed dataset. Keyed by metric key so
  # the browser can present each reference's status, sample count and
  // refusal reason without depending on the valuation_methods results.
  # Present when the distribution was established, absent otherwise -- never
  # fabricated or inferred from anything else.
  production_historical_multiples_distributions?: Record<string, ProductionHistoricalMultiplesDistributionDTO> | null
  consensus_reference?: ConsensusReferenceDTO
  eps_anchor_catalogue?: Record<string, any> | null
  eps_anchor_selection?: Record<string, any> | null
  // The per-method reverse results (revenue / P/S, cash flow / P/FCF,
  // enterprise value / EV/EBITDA): single-point references implied by
  // each method's own reference multiple, never ranked against each other
  // and never substituted for a per-scenario EPS matrix row.
  valuation_methods?: ValuationMethodsDTO | null
  // Where each observed fundamental the multiples are computed from came from
  // and on what basis (filed TTM window vs provider's undeclared trailing
  // figure), keyed by metric, so the implied and observed figures can be
  // checked against like-for-like facts.
  input_provenance?: Record<string, ProvenanceEntryDTO> | null
}

export interface FamilyCoverageDTO {
  // One reference family's coverage state for one issuer, read from the
  // family's own production distribution and its own qualification gate:
  // USABLE_FOR_REFERENCE when qualified, INSUFFICIENT_OBSERVATIONS for a thin
  // sample, UNAVAILABLE for a missing dataset. An ineligible state never
  // renders as a zero multiple.
  status: string
  usable_for_reference: boolean
  sample_count: number
  min_observations_required?: number | null
  reason_detail?: string | null
}

export interface IssuerCoverageDTO {
  ticker: string
  pe: FamilyCoverageDTO
  ps: FamilyCoverageDTO
  pfcf: FamilyCoverageDTO
  ev_ebitda: FamilyCoverageDTO
}

export interface CoverageResponseDTO {
  // First-use coverage derived from the committed production datasets the
  // engine itself loads, so the homepage cannot drift from what an analysis
  // would actually use.
  issuers: Record<string, IssuerCoverageDTO>
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
  production_historical_pfcf?: ProductionHistoricalPfcfDTO | null
  production_historical_multiples?: Record<string, any> | null
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
  ps_multiple?: number | null
  ev_ebitda_multiple?: number | null
  pfcf_multiple?: number | null
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

