"""
Data Transfer Objects (DTO) and API schemas for ST-EVA Web API.
Stable contracts decoupled from internal domain structures.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class JobProgressStage(str, Enum):
    PENDING = "pending"
    RESOLVING = "resolving"
    FETCHING_SEC = "fetching SEC"
    ADMISSION = "admission"
    VALUATION = "valuation"
    ARCHIVE_REPLAY = "archive/replay"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalyzeRequest(BaseModel):
    ticker: str = Field(..., description="Ticker symbol to analyze, e.g. AAPL, MSFT, 0700.HK")
    mode: str = Field("auto", description="Execution mode: auto, live, or regression")
    reference_multiple: Optional[float] = Field(None, description="Explicit valuation multiple")
    reference_multiples: Optional[List[float]] = Field(None, description="List of explicit valuation multiples")
    horizon_years: float = Field(1.0, description="Horizon years for EPS CAGR")
    reverse_horizons: Optional[List[float]] = Field(None, description="Scenario horizon years, e.g. [1.0, 2.0, 3.0, 5.0]")
    required_returns: Optional[List[float]] = Field(None, description="Scenario required returns, e.g. [0.08, 0.10, 0.12, 0.15]")
    prefer_eps_anchor: Optional[str] = Field(None, description="Preferred EPS anchor basis: trailing, forward, or consensus")
    user_eps: Optional[float] = Field(None, description="Explicit user-supplied starting EPS anchor")


class AnalyzeResponse(BaseModel):
    job_id: str
    ticker: str
    status: JobStatus


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"


class RefusalItem(BaseModel):
    ref: Optional[str] = None
    reason: str
    category: Optional[str] = None


class AdmissionSummary(BaseModel):
    total_admitted: int = 0
    total_refused: int = 0
    metrics_admitted: List[str] = Field(default_factory=list)
    refusals: List[RefusalItem] = Field(default_factory=list)


class ReplaySummary(BaseModel):
    attempted: bool = False
    outcome: Optional[str] = None
    reason: Optional[str] = None
    matched: bool = False
    reconstructed: bool = False
    observations_used: int = 0
    observations_considered: int = 0
    replay_fidelity: Optional[str] = None
    stored_document_hash: Optional[str] = None
    rebuilt_document_hash: Optional[str] = None


class ValuationSummary(BaseModel):
    analysis_type: Optional[str] = None
    current_price: Optional[float] = None
    currency: Optional[str] = None
    as_of: Optional[str] = None
    forward_eps_at_reference_multiple: Optional[float] = None
    eps_gap_vs_consensus: Optional[float] = None
    required_eps_cagr: Optional[float] = None
    selected_pe: Optional[float] = None
    observed_pe: Optional[float] = None
    observed_ps: Optional[float] = None
    observed_pfcf: Optional[float] = None
    observed_ev_ebitda: Optional[float] = None
    consensus_forward_eps: Optional[float] = None
    limitations: List[str] = Field(default_factory=list)


class ReferenceMultipleDTO(BaseModel):
    value: float
    source: str
    period_label: str = ""
    sample_size: Optional[int] = None
    sample_period: str = ""
    conditionality: Optional[str] = None


class EpsAnchorDTO(BaseModel):
    value: float
    basis: str
    months_covered: float
    period_label: str = ""
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    provider: str = ""
    currency: Optional[str] = None
    period_undeclared_by_source: bool = False


class EpsScenarioDTO(BaseModel):
    price: Optional[float] = None
    as_of: Optional[str] = None
    horizon_years: float
    required_return: float
    required_return_basis: str
    exit_multiple: ReferenceMultipleDTO
    required_exit_price: Optional[float] = None
    required_exit_price_basis: Optional[str] = None
    required_terminal_eps: Optional[float] = None
    start_eps: EpsAnchorDTO
    growth_years: Optional[float] = None
    required_eps_cagr: Optional[float] = None
    total_terminal_eps_growth: Optional[float] = None
    terminal_eps_vs_start_pct: Optional[float] = None
    terminal_pe_change_vs_current_pe: Optional[float] = None
    gap_vs_consensus_terminal_eps: Optional[float] = None
    comparison_notes: List[str] = Field(default_factory=list)
    flags: List[str] = Field(default_factory=list)
    formula_version: str = "reverse-requirements/1.1"
    dividend_per_share: Optional[float] = None
    dividend_convention: Optional[str] = None
    dividend_relief_exit_price: Optional[float] = None
    dividend_relief_terminal_eps: Optional[float] = None
    dividend_relief_cagr: Optional[float] = None


class ReverseRequirementsReportDTO(BaseModel):
    formula_version: str = "reverse-requirements/1.1"
    fingerprint: Optional[str] = None
    status: str = "COMPUTED"
    status_reason: Optional[str] = None
    matrix_size: int = 0
    reverse_requirements_matrix: List[EpsScenarioDTO] = Field(default_factory=list)
    reading_notes: List[str] = Field(default_factory=list)
    unavailable: List[Dict[str, Any]] = Field(default_factory=list)
    dividend_basis: Optional[Dict[str, Any]] = None
    total_return_scenarios: Optional[Dict[str, Any]] = None
    price_vs_total_return_comparison: Optional[List[Dict[str, Any]]] = None


class AnalysisResultDTO(BaseModel):
    ticker: str
    company_name: str
    status: str = "success"
    research_id: Optional[str] = None
    as_of: Optional[str] = None
    source_identifiers: List[str] = Field(default_factory=list)
    admission_summary: AdmissionSummary = Field(default_factory=AdmissionSummary)
    valuation_summary: ValuationSummary = Field(default_factory=ValuationSummary)
    replay_summary: ReplaySummary = Field(default_factory=ReplaySummary)
    refusal_reasons: List[str] = Field(default_factory=list)
    reverse_requirements: Optional[ReverseRequirementsReportDTO] = None
    raw_analysis: Optional[Dict[str, Any]] = None


class JobDetailResponse(BaseModel):
    job_id: str
    ticker: str
    status: JobStatus
    stage: JobProgressStage
    created_at: str
    updated_at: str
    error: Optional[str] = None
    result: Optional[AnalysisResultDTO] = None

