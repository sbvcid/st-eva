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
    horizon_years: float = Field(1.0, description="Horizon years for EPS CAGR")


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

