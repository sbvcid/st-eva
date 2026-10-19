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
    # The metric names behind `total_refused`, deduplicated in archival order,
    # so the refused count is reconcilable with a list the interface can show
    # without reading the mixed `refusals` feed (which also carries context
    # unavailability entries that are not admission rows).
    metrics_refused: List[str] = Field(default_factory=list)
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
    # Structured observation-level diff: which observations the replay considered
    # and their availability class. Used to explain a DIVERGED outcome with
    # concrete per-observation detail rather than only a generic reason string.
    availability_classes: List[Dict[str, Any]] = Field(default_factory=list)
    # Field-level differences between the stored context and the rebuilt
    # context. Each entry is {"field": dotted_path, "stored": old_value,
    # "rebuilt": new_value}. Empty when no stored context exists, when the
    # contexts match, or when every difference is confined to volatile fields.
    field_diffs: List[Dict[str, Any]] = Field(default_factory=list)


class ValuationSummary(BaseModel):
    analysis_type: Optional[str] = None
    current_price: Optional[float] = None
    currency: Optional[str] = None
    as_of: Optional[str] = None
    forward_eps_at_reference_multiple: Optional[float] = None
    eps_gap_vs_consensus: Optional[float] = None
    required_eps_cagr: Optional[float] = None
    selected_pe: Optional[float] = None
    # Basis of the summary headline metrics, so a reader cannot mistake them for
    # a reverse-requirements matrix row. The summary CAGR is a single-point,
    # flat-multiple inversion (today's price vs the price-implied EPS at the
    # selected multiple, annualised over one horizon); it encodes no required
    # return, no exit multiple and no dividends, unlike a matrix scenario.
    selected_pe_basis: Optional[str] = None
    # The cash-flow reference and the figure it inverts into, carried with the
    # same basis discipline as the P/E reference: the basis names where the
    # number came from, and an absent reference stays absent rather than being
    # filled from the P/E or from a band.
    selected_pfcf: Optional[float] = None
    selected_pfcf_basis: Optional[str] = None
    implied_fcf_at_reference_multiple: Optional[float] = None
    # The market capitalisation the implied cash-flow figure was inverted from
    # (`implied_fcf_at_reference_multiple == market_cap / selected_pfcf`). It is
    # the run's own observed market cap -- a total in `currency`, never a
    # per-share figure -- carried so the headline number can be recomputed from
    # the response and the export instead of taken on trust.
    market_cap: Optional[float] = None
    summary_horizon_years: Optional[float] = None
    observed_pe: Optional[float] = None
    observed_ps: Optional[float] = None
    observed_pfcf: Optional[float] = None
    observed_ev_ebitda: Optional[float] = None
    consensus_forward_eps: Optional[float] = None
    consensus_forward_eps_period: Optional[str] = None
    consensus_forward_eps_period_end: Optional[str] = None
    limitations: List[str] = Field(default_factory=list)


class ConsensusReferenceDTO(BaseModel):
    """The consensus EPS the matrix's gap column is differenced against.

    Carries the source's own facts: the vendor period label verbatim, the
    fiscal-period end date the same source declared, and the rule a consumer
    needs to check a gap against. `period_end` is None whenever the source
    declared none -- it is never derived from `source_period_label`, so a
    `+1y` label cannot be read as a date.

    No verdict lives here. Whether a given row's terminal EPS covers the same
    period depends on that row's horizon, so the verdict is on each scenario as
    a flag and a reason.
    """

    eps: Optional[float] = None
    provider: str = ""
    basis: str = ""
    months_covered: Optional[float] = None
    source_period_label: Optional[str] = None
    period_end: Optional[str] = None
    period_end_declared_by_source: bool = False
    target_period_end: Optional[str] = None
    comparison_tolerance_days: Optional[int] = None
    comparable_horizon_years: Optional[float] = None


class ReferenceMultipleDTO(BaseModel):
    value: float
    source: str
    period_label: str = ""
    sample_size: Optional[int] = None
    sample_period: str = ""
    conditionality: Optional[str] = None
    is_user_assumption: bool = False
    eligibility_state: Optional[str] = None
    usable_for_reference: Optional[bool] = None


class SecFactDTO(BaseModel):
    accession: Optional[str] = None
    form: Optional[str] = None
    filed_date: Optional[str] = None
    concept: Optional[str] = "us-gaap:EarningsPerShareDiluted"
    unit: Optional[str] = "USD/shares"
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    document_url: Optional[str] = None
    # When the filing entered the public record, and on what basis that instant
    # is declared. Present for an EPS anchor adopted from the catalogue; None
    # for the related-evidence cross-check, which declares a filed date only.
    acceptance_datetime: Optional[str] = None
    available_at: Optional[str] = None
    available_at_basis: Optional[str] = None
    evidence_class: Optional[str] = None
    gaap_basis: Optional[str] = None
    source_url: Optional[str] = None


class RelatedSecEvidenceDTO(BaseModel):
    """Filing evidence related to the selected EPS, never its direct source.

    Presented for cross-check only: no input-to-fact linkage is claimed, and a
    consumer must not read this as the provenance of the selected value.
    """

    accession: Optional[str] = None
    form: Optional[str] = None
    filed_date: Optional[str] = None
    concept: Optional[str] = "us-gaap:EarningsPerShareDiluted"
    unit: Optional[str] = "USD/shares"
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    document_url: Optional[str] = None
    note: Optional[str] = None


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
    source_type: Optional[str] = ""
    observation_id: Optional[str] = None
    is_user_assumption: bool = False
    sec_fact: Optional[SecFactDTO] = None
    # The EPS anchor catalogue entry this anchor was adopted from, with the
    # nature that distinguishes a provider-reported figure from a directly
    # stated filing fact and from a derived sum, when it became public, and
    # the directly stated quarterly components a derived sum was built from.
    # All absent for the legacy vendor anchors.
    anchor_id: Optional[str] = None
    anchor_nature: Optional[str] = None
    anchor_gaap_basis: Optional[str] = None
    available_at: Optional[str] = None
    available_at_basis: Optional[str] = None
    sec_components: Optional[List[Dict[str, Any]]] = None
    annual_comparison: Optional[Dict[str, Any]] = None


class MarketPriceEvidenceDTO(BaseModel):
    value: float
    currency: Optional[str] = None
    as_of: Optional[str] = None
    provider: str = ""
    source_type: str = ""
    observation_id: Optional[str] = None
    is_user_assumption: bool = False


class EpsAnchorEvidenceDTO(BaseModel):
    value: float
    basis: str
    months_covered: float
    period_label: str = ""
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    provider: str = ""
    currency: Optional[str] = None
    period_undeclared_by_source: bool = False
    source_type: Optional[str] = ""
    observation_id: Optional[str] = None
    is_user_assumption: bool = False
    sec_fact: Optional[SecFactDTO] = None
    anchor_id: Optional[str] = None
    anchor_nature: Optional[str] = None
    anchor_gaap_basis: Optional[str] = None
    available_at: Optional[str] = None
    available_at_basis: Optional[str] = None
    sec_components: Optional[List[Dict[str, Any]]] = None
    annual_comparison: Optional[Dict[str, Any]] = None


class ExitMultipleEvidenceDTO(BaseModel):
    value: float
    source: str
    period_label: str = ""
    sample_size: Optional[int] = None
    sample_period: str = ""
    conditionality: Optional[str] = None
    is_user_assumption: bool = False
    eligibility_state: str = "USABLE_FOR_REFERENCE"
    usable_for_reference: bool = True


class CalculationStepDTO(BaseModel):
    step_number: int
    step_id: str
    name: str
    formula_expression: str
    operands: Dict[str, Any] = Field(default_factory=dict)
    output_value: Optional[float] = None
    output_unit: str = ""
    reproducible: bool = True
    status: str = "COMPUTED"
    status_reason: Optional[str] = None


class ScenarioEvidenceDTO(BaseModel):
    price_evidence: MarketPriceEvidenceDTO
    eps_evidence: EpsAnchorEvidenceDTO
    multiple_evidence: ExitMultipleEvidenceDTO
    user_assumptions: List[str] = Field(default_factory=list)
    sourced_facts: List[str] = Field(default_factory=list)
    missing_or_unvalidated: List[str] = Field(default_factory=list)
    related_sec_evidence: Optional[RelatedSecEvidenceDTO] = None


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
    evidence: Optional[ScenarioEvidenceDTO] = None
    calculation_steps: List[CalculationStepDTO] = Field(default_factory=list)


class ProductionHistoricalPeSummaryDTO(BaseModel):
    """State of the production point-in-time historical P/E reference distribution.

    Reported separately from the vendor P/E band: a distribution qualifies for
    reference scenarios only through this dataset's own eligibility gate, and an
    ineligible or missing distribution is stated as such rather than being
    replaced by a band or a user multiple.
    """

    issuer_id: Optional[str] = None
    instrument_id: Optional[str] = None
    metric_id: Optional[str] = None
    status: Optional[str] = None
    usable_for_reference: Optional[bool] = None
    sample_count: Optional[int] = None
    total_evaluations: Optional[int] = None
    min_observations_required: Optional[int] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    mean: Optional[float] = None
    std: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    percentiles: Optional[Dict[str, float]] = None
    current_pe: Optional[float] = None
    current_pe_as_of: Optional[str] = None
    sampling_cadence: Optional[str] = None
    evaluation_schedule_description: Optional[str] = None
    excluded_observation_count: Optional[int] = None
    input_set_id: Optional[str] = None
    content_hash: Optional[str] = None
    reason_code: Optional[str] = None
    reason_detail: Optional[str] = None


class ProductionHistoricalPfcfSummaryDTO(BaseModel):
    """State of the production point-in-time historical P/FCF reference distribution.

    The cash-flow counterpart of the P/E summary, with the same discipline: the
    distribution qualifies only through its own eligibility gate, it is reported
    separately from the vendor P/FCF band (which carries no usable history), and
    an ineligible or unsupported distribution is stated as such rather than
    being filled from anything else.
    """

    issuer_id: Optional[str] = None
    instrument_id: Optional[str] = None
    metric_id: Optional[str] = None
    status: Optional[str] = None
    usable_for_reference: Optional[bool] = None
    sample_count: Optional[int] = None
    total_evaluations: Optional[int] = None
    min_observations_required: Optional[int] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    mean: Optional[float] = None
    std: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    percentiles: Optional[Dict[str, float]] = None
    current_pfcf: Optional[float] = None
    current_pfcf_as_of: Optional[str] = None
    sampling_cadence: Optional[str] = None
    evaluation_schedule_description: Optional[str] = None
    excluded_observation_count: Optional[int] = None
    input_set_id: Optional[str] = None
    content_hash: Optional[str] = None
    reason_code: Optional[str] = None
    reason_detail: Optional[str] = None


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
    # The compact statement of the production distribution that the report
    # carries. The full dataset is not part of the API contract; its eligibility
    # state, identity and provenance are.
    production_historical_pe_summary: Optional[ProductionHistoricalPeSummaryDTO] = None
    # The cash-flow counterpart, carried with the same separation from the
    # vendor band. Absent when the reconstruction is not established for the
    # ticker, which the summary itself states.
    production_historical_pfcf_summary: Optional[ProductionHistoricalPfcfSummaryDTO] = None
    # The consensus the gap column is differenced against, with the period the
    # source declared for it. An eligible gap can be checked against these
    # facts, and a missing gap is explained by them rather than read as a zero.
    consensus_reference: ConsensusReferenceDTO = ConsensusReferenceDTO()
    # The EPS anchor catalogue and the selection record, present when the run
    # asked for a named catalogue anchor: every entry the issuer has evidence
    # for, and which one the matrix actually started from, or the specific
    # reason the named one was refused.
    eps_anchor_catalogue: Optional[Dict[str, Any]] = None
    eps_anchor_selection: Optional[Dict[str, Any]] = None


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
    production_historical_pe: Optional[ProductionHistoricalPeSummaryDTO] = None
    production_historical_pfcf: Optional[ProductionHistoricalPfcfSummaryDTO] = None
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

