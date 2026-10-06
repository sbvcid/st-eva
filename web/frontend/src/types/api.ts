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
  observed_pe?: number | null
  observed_ps?: number | null
  observed_pfcf?: number | null
  observed_ev_ebitda?: number | null
  consensus_forward_eps?: number | null
  limitations: string[]
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
  raw_analysis?: Record<string, any> | null
}

export interface AnalyzeRequest {
  ticker: string
  mode?: string
  reference_multiple?: number | null
  horizon_years?: number
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

