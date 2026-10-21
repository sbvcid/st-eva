"""
The research API: a separate path for research calculation and evidence.

This router is mounted at ``/api/research`` and is independent of the
production analysis path. It starts no analysis job, it writes no Archive,
it produces no production reference, and it reaches no Investment Context.
Every figure it returns is a research figure, and every one of them carries
the reason it is not a production reference.

The refusal codes are the service's own. A research metric that cannot be
selected, a multiple that does not exist, an observation the lane refused
and a capture that does not match its own manifest are different
conditions, and each says which one it is.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from research_calculator import (
    CALCULATOR_VERSION,
    MULTIPLE_HISTORY_MEDIAN,
    NUMERATOR_OBSERVATION,
    USER_ASSUMPTION_LABEL,
    ResearchCalculationError,
    ResearchCalculationRequest,
    list_observations,
    list_research_metrics,
    observation_evidence,
    run_research_calculation,
)

research_router = APIRouter(prefix="/api/research", tags=["research"])


class ResearchMetricDTO(BaseModel):
    """One selectable research metric, as the user sees it."""

    metric_id: str
    lane_id: str
    issuer_id: str
    instrument_id: str
    metric_label: str
    research_purpose: str
    research_use_label: str
    formula_expression: str
    formula_version: str
    formula_numerator: str
    formula_denominator: str
    numerator_kind: str
    numerator_label: str
    denominator_label: str
    status: str
    production_eligible: bool
    candidate_metric: bool
    sample_count: int
    total_evaluations: int
    refused_count: int
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    mean: Optional[float] = None
    std: Optional[float] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    percentiles: Dict[str, Optional[float]] = Field(default_factory=dict)
    median: Optional[float] = None
    sampling_cadence: str
    registry_standing: Dict[str, Any] = Field(default_factory=dict)
    production_refusal: Dict[str, Any] = Field(default_factory=dict)
    data_limitations: List[str] = Field(default_factory=list)
    basis_breaks: Dict[str, List[str]] = Field(default_factory=dict)
    prior_period_revisions: List[Dict[str, Any]] = Field(default_factory=list)
    input_set_id: str
    content_hash: str
    methodology: str
    logic_version: str


class ResearchMetricCatalogueDTO(BaseModel):
    """The research metrics a user may choose, and the notice that governs them."""

    metrics: List[ResearchMetricDTO]
    research_use_notice: str
    user_assumption_label: str
    calculator_version: str


class ResearchObservationDTO(BaseModel):
    """One evaluation date, with its value or the reason there is none."""

    evaluation_date: str
    status: str
    value: Optional[float] = None
    reason_code: Optional[str] = None
    reason_detail: Optional[str] = None
    price: Optional[float] = None
    shares_outstanding: Optional[float] = None
    market_cap: Optional[float] = None
    enterprise_value: Optional[float] = None
    denominator: Optional[float] = None
    basis_breaks: List[str] = Field(default_factory=list)
    content_hash: str


class ResearchMetricDetailDTO(BaseModel):
    """A metric and every evaluation date behind it."""

    metric: ResearchMetricDTO
    observations: List[ResearchObservationDTO]


class ResearchObservationEvidenceDTO(BaseModel):
    """The full evidence of one evaluation date."""

    evaluation_date: str
    metric_id: str
    content_hash: str
    evidence: Dict[str, Any]


class ResearchCalculationRequestDTO(BaseModel):
    """What the user asked for."""

    metric_id: str = Field(
        ..., description="The research metric the user chose. There is no default."
    )
    multiple_source: str = Field(
        MULTIPLE_HISTORY_MEDIAN,
        description=(
            "HISTORY_MEDIAN, OBSERVATION or USER_SUPPLIED. The metric's own "
            "median, one of its own observations, or a multiple the user "
            "supplied."
        ),
    )
    multiple: Optional[float] = Field(
        None, description="The multiple, when the user supplied it."
    )
    observation_date: Optional[str] = Field(
        None, description="The evaluation date, when the multiple is one observation."
    )
    numerator_source: str = Field(
        NUMERATOR_OBSERVATION,
        description=(
            "OBSERVATION or USER_SUPPLIED. The lane's own market value, or one "
            "the user supplied."
        ),
    )
    numerator_value: Optional[float] = Field(
        None, description="The market value, when the user supplied it."
    )
    numerator_date: Optional[str] = Field(
        None,
        description=(
            "The evaluation date the market value is taken from. The latest "
            "valid observation is used when this is absent."
        ),
    )


class ResearchCalculationDTO(BaseModel):
    """The figure, and everything behind it."""

    metric_id: str
    lane_id: str
    issuer_id: str
    instrument_id: str
    status: str
    production_eligible: bool
    research_use_label: str
    multiple: float
    multiple_source: str
    multiple_label: str
    multiple_observation_date: Optional[str] = None
    multiple_observation_content_hash: Optional[str] = None
    numerator: float
    numerator_source: str
    numerator_label: str
    numerator_kind: str
    numerator_date: Optional[str] = None
    numerator_observation_content_hash: Optional[str] = None
    implied_denominator: float
    implied_denominator_label: str
    formula_expression: str
    formula_version: str
    formula_operands: Dict[str, Any] = Field(default_factory=dict)
    lane_input_set_id: str
    lane_content_hash: str
    capture_identity: Dict[str, Any] = Field(default_factory=dict)
    calculation_content_hash: str
    calculation_version: str
    methodology: str
    logic_version: str
    numerator_evidence: Dict[str, Any] = Field(default_factory=dict)
    multiple_evidence: Dict[str, Any] = Field(default_factory=dict)
    registry_standing: Dict[str, Any] = Field(default_factory=dict)
    basis_breaks: List[str] = Field(default_factory=list)
    prior_period_revisions: List[Dict[str, Any]] = Field(default_factory=list)
    production_refusal: Dict[str, Any] = Field(default_factory=dict)
    data_limitations: List[str] = Field(default_factory=list)


class ResearchRefusalDTO(BaseModel):
    """A calculation that could not be made, and why."""

    reason_code: str
    detail: str
    production_eligible: bool = False


def _refusal(exc: ResearchCalculationError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "reason_code": exc.reason_code,
            "detail": exc.detail,
            "production_eligible": False,
        },
    )


@research_router.get(
    "/metrics", response_model=ResearchMetricCatalogueDTO
)
def get_research_metrics() -> ResearchMetricCatalogueDTO:
    """
    The research metrics a user may choose.

    The diagnostic lane is not among them and cannot be selected.
    """
    from research_calculator import RESEARCH_USE_NOTICE

    return ResearchMetricCatalogueDTO(
        metrics=[
            ResearchMetricDTO(**summary.to_dict())
            for summary in list_research_metrics()
        ],
        research_use_notice=RESEARCH_USE_NOTICE,
        user_assumption_label=USER_ASSUMPTION_LABEL,
        calculator_version=CALCULATOR_VERSION,
    )


@research_router.get(
    "/metrics/{metric_id}", response_model=ResearchMetricDetailDTO
)
def get_research_metric(metric_id: str) -> ResearchMetricDetailDTO:
    """
    A research metric and every evaluation date behind it.

    The refused dates are in the list with their reasons. A reader who sees
    a median can see the dates the lane refused, not only the result.
    """
    try:
        summaries = list_research_metrics()
        summary = next(
            (item for item in summaries if item.metric_id == metric_id), None
        )
        if summary is None:
            raise ResearchCalculationError(
                "RESEARCH_CALCULATION_REFUSED_METRIC_UNAVAILABLE",
                f"No research metric named {metric_id!r} is available.",
            )
        observations = list_observations(metric_id)
    except ResearchCalculationError as exc:
        raise _refusal(exc) from exc
    return ResearchMetricDetailDTO(
        metric=ResearchMetricDTO(**summary.to_dict()),
        observations=[
            ResearchObservationDTO(**observation.to_dict())
            for observation in observations
        ],
    )


@research_router.get(
    "/metrics/{metric_id}/observations/{evaluation_date}",
    response_model=ResearchObservationEvidenceDTO,
)
def get_research_observation_evidence(
    metric_id: str, evaluation_date: str
) -> ResearchObservationEvidenceDTO:
    """
    The full evidence of one evaluation date: the operands, the four
    denominator quarters, the balance-sheet components, the accessions, the
    elements, the periods, the units, the knowability and the digests.
    """
    try:
        evidence = observation_evidence(metric_id, evaluation_date)
    except ResearchCalculationError as exc:
        raise _refusal(exc) from exc
    return ResearchObservationEvidenceDTO(
        evaluation_date=evaluation_date,
        metric_id=metric_id,
        content_hash=evidence.get("content_hash", ""),
        evidence=evidence,
    )


@research_router.post("/calculate", response_model=ResearchCalculationDTO)
def calculate_research(request: ResearchCalculationRequestDTO) -> ResearchCalculationDTO:
    """
    Compute one research reverse calculation, with its evidence.

    The metric is the user's to choose and is never assumed. A user-supplied
    multiple or market value is labelled as a research assumption and is
    kept apart from the observed facts.
    """
    try:
        result = run_research_calculation(
            ResearchCalculationRequest(
                metric_id=request.metric_id,
                multiple_source=request.multiple_source,
                multiple=request.multiple,
                observation_date=request.observation_date,
                numerator_source=request.numerator_source,
                numerator_value=request.numerator_value,
                numerator_date=request.numerator_date,
            )
        )
    except ResearchCalculationError as exc:
        raise _refusal(exc) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "reason_code": "RESEARCH_CALCULATION_REFUSED_INVALID_REQUEST",
                "detail": str(exc),
                "production_eligible": False,
            },
        ) from exc
    return ResearchCalculationDTO(**result.to_dict())
