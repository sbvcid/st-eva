"""The research calculation service.

A user chooses a research metric, states a multiple and a market value, and
the service computes what that pair implies about the underlying financial
denominator -- and shows the evidence the figure rests on.

Three properties hold throughout.

**The user chooses.** A research metric is never selected implicitly, and a
research result is never used as a valuation reference. The selectable
metrics are the candidate research metrics; the diagnostic lane is not one of
them and cannot be selected.

**The arithmetic is the lane's own.** A research multiple is a multiple of
its own lane: lane A and lane B divide a market capitalisation by their
denominator, lane C1 and lane C2 divide an enterprise value built from that
lane's own filed balance-sheet bridge by their denominator. A calculation
never mixes one lane's numerator with another lane's denominator or sample.

**A result is traceable.** Every figure the service returns carries the
formula and its version, the operands, the accessions, elements, periods,
units, knowability and source-file digests behind them, the registry's
standing on the elements read, the basis breaks and value revisions, and the
lane's input-set identity. A result can be followed back to the filing it
came from.

The service reads the committed research capture and computes. It writes
nothing, opens no Archive, produces no production reference, and reaches no
Investment Context. The isolation the lane already holds is asserted again
here, at the point a result is produced, rather than assumed to survive.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from research_issuers import (
    build_lane_results,
    candidate_lane_ids,
    config_for_lane,
    lane_configs,
)
from research_lane import (
    ResearchLaneResult,
    ResearchObservation,
    assert_research_isolation,
)

CALCULATOR_VERSION = "research-calculator/1.0"

# How a multiple was chosen.
MULTIPLE_HISTORY_MEDIAN = "HISTORY_MEDIAN"
MULTIPLE_OBSERVATION = "OBSERVATION"
MULTIPLE_USER_SUPPLIED = "USER_SUPPLIED"
MULTIPLE_SOURCES = (MULTIPLE_HISTORY_MEDIAN, MULTIPLE_OBSERVATION, MULTIPLE_USER_SUPPLIED)

# How the numerator was obtained.
NUMERATOR_OBSERVATION = "OBSERVATION"
NUMERATOR_USER_SUPPLIED = "USER_SUPPLIED"
NUMERATOR_SOURCES = (NUMERATOR_OBSERVATION, NUMERATOR_USER_SUPPLIED)

# The label every operator that came from the user rather than from the
# filed evidence carries.
USER_ASSUMPTION_LABEL = "user_supplied_research_assumption"

# The service's own refusal codes. They are separate from the lane's
# observation refusal codes: the lane refuses an observation, and the
# service refuses a calculation.
REFUSED_METRIC_UNAVAILABLE = "RESEARCH_CALCULATION_REFUSED_METRIC_UNAVAILABLE"
REFUSED_METRIC_NOT_SELECTABLE = "RESEARCH_CALCULATION_REFUSED_METRIC_NOT_SELECTABLE"
REFUSED_MULTIPLE_UNAVAILABLE = "RESEARCH_CALCULATION_REFUSED_MULTIPLE_UNAVAILABLE"
REFUSED_MULTIPLE_NOT_POSITIVE = "RESEARCH_CALCULATION_REFUSED_MULTIPLE_NOT_POSITIVE"
REFUSED_MULTIPLE_NOT_FINITE = "RESEARCH_CALCULATION_REFUSED_MULTIPLE_NOT_FINITE"
REFUSED_OBSERVATION_REJECTED = "RESEARCH_CALCULATION_REFUSED_OBSERVATION_REJECTED"
REFUSED_OBSERVATION_UNKNOWN = "RESEARCH_CALCULATION_REFUSED_OBSERVATION_UNKNOWN"
REFUSED_NUMERATOR_UNAVAILABLE = "RESEARCH_CALCULATION_REFUSED_NUMERATOR_UNAVAILABLE"
REFUSED_NUMERATOR_NOT_POSITIVE = "RESEARCH_CALCULATION_REFUSED_NUMERATOR_NOT_POSITIVE"
REFUSED_NUMERATOR_NOT_FINITE = "RESEARCH_CALCULATION_REFUSED_NUMERATOR_NOT_FINITE"
REFUSED_RESULT_NOT_FINITE = "RESEARCH_CALCULATION_REFUSED_RESULT_NOT_FINITE"
REFUSED_DATA_IDENTITY_MISMATCH = "RESEARCH_CALCULATION_REFUSED_DATA_IDENTITY_MISMATCH"
REFUSED_DENOMINATOR_UNAVAILABLE = "RESEARCH_CALCULATION_REFUSED_DENOMINATOR_UNAVAILABLE"

CLOSED_CALCULATION_REASON_CODES = frozenset(
    {
        REFUSED_METRIC_UNAVAILABLE,
        REFUSED_METRIC_NOT_SELECTABLE,
        REFUSED_MULTIPLE_UNAVAILABLE,
        REFUSED_MULTIPLE_NOT_POSITIVE,
        REFUSED_MULTIPLE_NOT_FINITE,
        REFUSED_OBSERVATION_REJECTED,
        REFUSED_OBSERVATION_UNKNOWN,
        REFUSED_NUMERATOR_UNAVAILABLE,
        REFUSED_NUMERATOR_NOT_POSITIVE,
        REFUSED_NUMERATOR_NOT_FINITE,
        REFUSED_RESULT_NOT_FINITE,
        REFUSED_DATA_IDENTITY_MISMATCH,
        REFUSED_DENOMINATOR_UNAVAILABLE,
    }
)

RESEARCH_USE_NOTICE = (
    "RESEARCH USE ONLY. A research calculation is computed from filed "
    "evidence that the production qualification regime does not admit. It is "
    "not a valuation reference, it is not a production reference chain "
    "input, and it must not be presented as one."
)


class ResearchCalculationError(Exception):
    """A calculation that cannot be made, with the reason it cannot be made."""

    def __init__(self, reason_code: str, detail: str) -> None:
        if reason_code not in CLOSED_CALCULATION_REASON_CODES:
            raise ValueError(
                f"reason_code {reason_code!r} is not in the closed calculation "
                "refusal set; an unknown code is an error, not a refusal"
            )
        super().__init__(detail)
        self.reason_code = reason_code
        self.detail = detail


# ---------------------------------------------------------------------------
# The catalogue
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResearchMetricSummary:
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
    #: The minimum sample the lane reports as a distribution rather than a
    #: descriptive summary. It is the lane's own research setting, carried
    #: here so a reader is told the threshold rather than left to assume one.
    #: It says how much evidence a description rests on; it says nothing about
    #: production eligibility, which is a separate field.
    min_observations_for_description: int
    #: Why the distribution is unavailable, when it is. A distribution that
    #: holds no valid observation says so here rather than being presented as
    #: an empty result.
    reason_code: Optional[str]
    reason_detail: Optional[str]
    period_start: Optional[str]
    period_end: Optional[str]
    mean: Optional[float]
    std: Optional[float]
    minimum: Optional[float]
    maximum: Optional[float]
    percentiles: Dict[str, Optional[float]]
    median: Optional[float]
    sampling_cadence: str
    registry_standing: Dict[str, Any]
    production_refusal: Dict[str, Any]
    data_limitations: List[str]
    basis_breaks: Dict[str, List[str]]
    prior_period_revisions: List[Dict[str, Any]]
    input_set_id: str
    content_hash: str
    methodology: str
    logic_version: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "lane_id": self.lane_id,
            "issuer_id": self.issuer_id,
            "instrument_id": self.instrument_id,
            "metric_label": self.metric_label,
            "research_purpose": self.research_purpose,
            "research_use_label": self.research_use_label,
            "formula_expression": self.formula_expression,
            "formula_version": self.formula_version,
            "formula_numerator": self.formula_numerator,
            "formula_denominator": self.formula_denominator,
            "numerator_kind": self.numerator_kind,
            "numerator_label": self.numerator_label,
            "denominator_label": self.denominator_label,
            "status": self.status,
            "production_eligible": self.production_eligible,
            "candidate_metric": self.candidate_metric,
            "sample_count": self.sample_count,
            "total_evaluations": self.total_evaluations,
            "refused_count": self.refused_count,
            "min_observations_for_description": self.min_observations_for_description,
            "reason_code": self.reason_code,
            "reason_detail": self.reason_detail,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "mean": self.mean,
            "std": self.std,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "percentiles": self.percentiles,
            "median": self.median,
            "sampling_cadence": self.sampling_cadence,
            "registry_standing": self.registry_standing,
            "production_refusal": self.production_refusal,
            "data_limitations": self.data_limitations,
            "basis_breaks": self.basis_breaks,
            "prior_period_revisions": self.prior_period_revisions,
            "input_set_id": self.input_set_id,
            "content_hash": self.content_hash,
            "methodology": self.methodology,
            "logic_version": self.logic_version,
        }


@dataclass(frozen=True)
class ResearchObservationSummary:
    """One evaluation date, with the value or the reason there is none."""

    evaluation_date: str
    status: str
    value: Optional[float]
    reason_code: Optional[str]
    reason_detail: Optional[str]
    price: Optional[float]
    shares_outstanding: Optional[float]
    market_cap: Optional[float]
    enterprise_value: Optional[float]
    denominator: Optional[float]
    basis_breaks: List[str]
    content_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evaluation_date": self.evaluation_date,
            "status": self.status,
            "value": self.value,
            "reason_code": self.reason_code,
            "reason_detail": self.reason_detail,
            "price": self.price,
            "shares_outstanding": self.shares_outstanding,
            "market_cap": self.market_cap,
            "enterprise_value": self.enterprise_value,
            "denominator": self.denominator,
            "basis_breaks": self.basis_breaks,
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True)
class ResearchCalculationRequest:
    """What the user asked for."""

    metric_id: str
    multiple_source: str = MULTIPLE_HISTORY_MEDIAN
    multiple: Optional[float] = None
    observation_date: Optional[str] = None
    numerator_source: str = NUMERATOR_OBSERVATION
    numerator_value: Optional[float] = None
    numerator_date: Optional[str] = None

    def __post_init__(self) -> None:
        if self.multiple_source not in MULTIPLE_SOURCES:
            raise ValueError(
                f"unknown multiple_source {self.multiple_source!r}; it must be "
                f"one of {MULTIPLE_SOURCES}"
            )
        if self.numerator_source not in NUMERATOR_SOURCES:
            raise ValueError(
                f"unknown numerator_source {self.numerator_source!r}; it must be "
                f"one of {NUMERATOR_SOURCES}"
            )


@dataclass(frozen=True)
class ResearchCalculationResult:
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
    multiple_observation_date: Optional[str]
    multiple_observation_content_hash: Optional[str]
    numerator: float
    numerator_source: str
    numerator_label: str
    numerator_kind: str
    numerator_date: Optional[str]
    numerator_observation_content_hash: Optional[str]
    implied_denominator: float
    implied_denominator_label: str
    formula_expression: str
    formula_version: str
    formula_operands: Dict[str, Any]
    lane_input_set_id: str
    lane_content_hash: str
    capture_identity: Dict[str, Any]
    calculation_content_hash: str
    calculation_version: str
    methodology: str
    logic_version: str
    numerator_evidence: Dict[str, Any] = field(default_factory=dict)
    multiple_evidence: Dict[str, Any] = field(default_factory=dict)
    registry_standing: Dict[str, Any] = field(default_factory=dict)
    basis_breaks: List[str] = field(default_factory=list)
    prior_period_revisions: List[Dict[str, Any]] = field(default_factory=list)
    production_refusal: Dict[str, Any] = field(default_factory=dict)
    data_limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "lane_id": self.lane_id,
            "issuer_id": self.issuer_id,
            "instrument_id": self.instrument_id,
            "status": self.status,
            "production_eligible": self.production_eligible,
            "research_use_label": self.research_use_label,
            "multiple": self.multiple,
            "multiple_source": self.multiple_source,
            "multiple_label": self.multiple_label,
            "multiple_observation_date": self.multiple_observation_date,
            "multiple_observation_content_hash": self.multiple_observation_content_hash,
            "numerator": self.numerator,
            "numerator_source": self.numerator_source,
            "numerator_label": self.numerator_label,
            "numerator_kind": self.numerator_kind,
            "numerator_date": self.numerator_date,
            "numerator_observation_content_hash": self.numerator_observation_content_hash,
            "implied_denominator": self.implied_denominator,
            "implied_denominator_label": self.implied_denominator_label,
            "formula_expression": self.formula_expression,
            "formula_version": self.formula_version,
            "formula_operands": self.formula_operands,
            "lane_input_set_id": self.lane_input_set_id,
            "lane_content_hash": self.lane_content_hash,
            "capture_identity": self.capture_identity,
            "calculation_content_hash": self.calculation_content_hash,
            "calculation_version": self.calculation_version,
            "methodology": self.methodology,
            "logic_version": self.logic_version,
            "numerator_evidence": self.numerator_evidence,
            "multiple_evidence": self.multiple_evidence,
            "registry_standing": self.registry_standing,
            "basis_breaks": self.basis_breaks,
            "prior_period_revisions": self.prior_period_revisions,
            "production_refusal": self.production_refusal,
            "data_limitations": self.data_limitations,
        }


# ---------------------------------------------------------------------------
# The lane results
# ---------------------------------------------------------------------------

_LANE_RESULTS: Optional[Dict[str, ResearchLaneResult]] = None


def _lane_results() -> Dict[str, ResearchLaneResult]:
    """The configured lanes, computed once and held for the lifetime.

    The lanes are a pure function of the committed captures and the
    configuration, so the results are the same every time; holding them
    keeps a user browsing the evidence explorer from recomputing the same
    windows on every request.
    """
    global _LANE_RESULTS
    if _LANE_RESULTS is None:
        _LANE_RESULTS = build_lane_results()
    return _LANE_RESULTS


def _reset_lane_cache() -> None:
    """Forget the held lane results, so the next call recomputes them."""
    global _LANE_RESULTS
    _LANE_RESULTS = None


def _capture_identity(capture_dir: Path) -> Dict[str, Any]:
    """
    The research data identity: what the capture is, by content.

    The capture's manifest pins each file's digest. If a file's bytes no
    longer match, the evidence the lanes would read is not the evidence the
    manifest names, and no calculation may be made from it.
    """
    import json

    manifest_path = capture_dir / "manifest.json"
    if not manifest_path.exists():
        raise ResearchCalculationError(
            REFUSED_DATA_IDENTITY_MISMATCH,
            f"The research capture has no manifest at {manifest_path}.",
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = manifest.get("files") or {}
    mismatches = []
    for name, entry in sorted(files.items()):
        path = capture_dir / name
        if not path.exists():
            mismatches.append(f"{name} is missing")
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry.get("sha256"):
            mismatches.append(f"{name} does not match its recorded SHA-256")
    if mismatches:
        raise ResearchCalculationError(
            REFUSED_DATA_IDENTITY_MISMATCH,
            "The research capture does not match its own manifest: "
            + "; ".join(mismatches)
            + ". No calculation is made from evidence the manifest does not name.",
        )
    return {
        "capture_dir": str(capture_dir),
        "captured_at": manifest.get("captured_at"),
        "issuer": manifest.get("issuer"),
        "capture_policy": manifest.get("capture_policy"),
        "files": {
            name: {"sha256": entry.get("sha256"), "role": entry.get("role")}
            for name, entry in sorted(files.items())
        },
    }


def _config_for(lane_id: str) -> Any:
    try:
        return config_for_lane(lane_id)
    except Exception as error:
        raise ResearchCalculationError(
            REFUSED_METRIC_UNAVAILABLE,
            f"No research lane named {lane_id!r} is configured.",
        ) from error


def _numerator_kind(lane_id: str) -> str:
    return _config_for(lane_id).numerator_kind


def _numerator_label(lane_id: str) -> str:
    kind = _numerator_kind(lane_id)
    if kind == "enterprise_value":
        return (
            "Enterprise value, built from this lane's own filed "
            "balance-sheet bridge: market capitalisation plus total debt "
            "less liquid funds."
        )
    return "Market capitalisation: the as-traded close on the evaluation date times the latest knowable cover-page share count."


def _numerator_short_label(lane_id: str) -> str:
    """The short name of the numerator a lane divides by."""
    if _numerator_kind(lane_id) == "enterprise_value":
        return "enterprise value"
    return "market capitalisation"


def _denominator_label(lane_id: str) -> str:
    config = _config_for(lane_id)
    return config.formula_denominator


def list_research_metrics() -> List[ResearchMetricSummary]:
    """
    The research metrics a user may choose.

    Only the candidate research metrics are listed. The diagnostic lane is
    not a metric and is not offered.
    """
    results = _lane_results()
    summaries: List[ResearchMetricSummary] = []
    for lane_id in candidate_lane_ids():
        result = results[lane_id]
        distribution = result.distribution
        config = _config_for(lane_id)
        summaries.append(
            ResearchMetricSummary(
                metric_id=result.metric_id,
                lane_id=result.lane_id,
                issuer_id=result.issuer_id,
                instrument_id=result.instrument_id,
                metric_label=distribution.metric_label,
                research_purpose=config.research_purpose,
                research_use_label=distribution.research_use_label,
                formula_expression=config.formula_expression,
                formula_version=config.formula_version,
                formula_numerator=config.formula_numerator,
                formula_denominator=config.formula_denominator,
                numerator_kind=config.numerator_kind,
                numerator_label=_numerator_label(lane_id),
                denominator_label=_denominator_label(lane_id),
                status=distribution.status,
                production_eligible=distribution.production_eligible,
                candidate_metric=distribution.candidate_metric,
                sample_count=distribution.sample_count,
                total_evaluations=distribution.total_evaluations,
                refused_count=len(distribution.excluded_observations),
                min_observations_for_description=(
                    distribution.min_observations_for_description
                ),
                reason_code=distribution.reason_code,
                reason_detail=distribution.reason_detail,
                period_start=distribution.period_start,
                period_end=distribution.period_end,
                mean=distribution.mean,
                std=distribution.std,
                minimum=distribution.min,
                maximum=distribution.max,
                percentiles=distribution.percentiles,
                median=distribution.percentiles.get("median"),
                sampling_cadence=distribution.sampling_cadence,
                registry_standing=distribution.registry_standing,
                production_refusal=distribution.production_refusal,
                data_limitations=distribution.data_limitations,
                basis_breaks=distribution.basis_breaks,
                prior_period_revisions=distribution.prior_period_revisions,
                input_set_id=result.input_set_id,
                content_hash=result.content_hash,
                methodology=distribution.methodology,
                logic_version=distribution.logic_version,
            )
        )
    return summaries


def _selected_result(metric_id: str) -> ResearchLaneResult:
    """
    The lane behind a metric id, when that metric is one a user may choose.

    The diagnostic lane is not selectable, and asking for it by name is a
    refusal rather than an empty result.
    """
    results = _lane_results()
    for lane_id in candidate_lane_ids():
        result = results[lane_id]
        if result.metric_id == metric_id or lane_id == metric_id:
            return result
    for result in results.values():
        if result.metric_id == metric_id:
            raise ResearchCalculationError(
                REFUSED_METRIC_NOT_SELECTABLE,
                f"{metric_id} is a research diagnostic, not a research metric. "
                "A diagnostic measures what a wrong construction would produce "
                "and is not offered for calculation.",
            )
    raise ResearchCalculationError(
        REFUSED_METRIC_UNAVAILABLE,
        f"No research metric named {metric_id!r} is available. The selectable "
        "research metrics are "
        + ", ".join(
            results[lane_id].metric_id for lane_id in candidate_lane_ids()
        )
        + ".",
    )


def list_observations(metric_id: str) -> List[ResearchObservationSummary]:
    """
    Every evaluation date of a metric, with its value or its refusal.

    The refused dates are part of the record. A reader who sees a median
    must be able to see the 38 dates the lane refused, and why.
    """
    result = _selected_result(metric_id)
    summaries: List[ResearchObservationSummary] = []
    for observation in result.observations:
        summaries.append(
            ResearchObservationSummary(
                evaluation_date=observation.evaluation_date,
                status=observation.status,
                value=observation.value,
                reason_code=observation.reason_code,
                reason_detail=observation.reason_detail,
                price=observation.price,
                shares_outstanding=observation.shares_outstanding,
                market_cap=observation.market_cap,
                enterprise_value=observation.enterprise_value,
                denominator=(
                    observation.denominator.get("value")
                    if observation.denominator
                    else None
                ),
                basis_breaks=list(observation.basis_breaks),
                content_hash=observation.content_hash,
            )
        )
    return summaries


def observation_evidence(metric_id: str, evaluation_date: str) -> Dict[str, Any]:
    """
    The full evidence of one evaluation date.

    The price, the share count, the market capitalisation or the enterprise
    value, the four denominator quarters with their accessions, elements,
    periods, units and knowability, the balance-sheet components with their
    source-file digests, the registry's standing, the basis breaks and the
    value revisions.
    """
    result = _selected_result(metric_id)
    for observation in result.observations:
        if observation.evaluation_date == evaluation_date:
            payload = observation.to_dict()
            payload["capture_identity"] = _capture_identity(
                _config_for(result.lane_id).capture_dir
            )
            return payload
    raise ResearchCalculationError(
        REFUSED_OBSERVATION_UNKNOWN,
        f"The metric has no evaluation dated {evaluation_date}.",
    )


# ---------------------------------------------------------------------------
# The calculation
# ---------------------------------------------------------------------------


def _observation_by_date(
    result: ResearchLaneResult, evaluation_date: str
) -> Optional[ResearchObservation]:
    for observation in result.observations:
        if observation.evaluation_date == evaluation_date:
            return observation
    return None


def _latest_valid_observation(
    result: ResearchLaneResult,
) -> Optional[ResearchObservation]:
    valid = [
        observation
        for observation in result.observations
        if observation.value is not None and observation.value > 0
    ]
    if not valid:
        return None
    return valid[-1]


def _numerator_of(observation: ResearchObservation, numerator_kind: str) -> Optional[float]:
    if numerator_kind == "enterprise_value":
        return observation.enterprise_value
    return observation.market_cap


def _numerator_evidence(
    observation: ResearchObservation, numerator_kind: str
) -> Dict[str, Any]:
    """The evidence behind a numerator taken from an observation."""
    evidence: Dict[str, Any] = {
        "evaluation_date": observation.evaluation_date,
        "price": observation.price,
        "price_currency": observation.price_currency,
        "price_accounting_basis": observation.price_accounting_basis,
        "price_split_restoration": observation.price_split_restoration,
        "shares_outstanding": observation.shares_outstanding,
        "shares_as_of_date": observation.shares_as_of_date,
        "shares_accession": observation.shares_accession,
        "shares_usable_date": observation.shares_usable_date,
        "market_cap": observation.market_cap,
        "enterprise_value": observation.enterprise_value,
        "numerator_kind": numerator_kind,
        "observation_content_hash": observation.content_hash,
        "point_in_time": observation.point_in_time,
    }
    if numerator_kind == "enterprise_value":
        evidence["bridge"] = observation.bridge
        evidence["total_debt"] = observation.total_debt
        evidence["liquid_funds"] = observation.liquid_funds
    evidence["denominator_quarters"] = [
        {
            "period_end": quarter.get("period_end"),
            "value": quarter.get("value"),
            "accessions": quarter.get("accessions"),
            "elements": quarter.get("elements"),
            "knowable_from": quarter.get("knowable_from"),
            "input_spans": quarter.get("input_spans"),
        }
        for quarter in (observation.denominator or {}).get("quarters", [])
    ]
    return evidence


def run_research_calculation(
    request: ResearchCalculationRequest,
) -> ResearchCalculationResult:
    """
    Compute one research reverse calculation, with its evidence.

    The user states a research metric, a multiple and a market value; the
    service computes the implied financial denominator and shows the
    evidence behind every operand.

    The metric is the user's to choose and is never assumed. The multiple
    and the numerator each say where they came from: a historical statistic,
    a named observation, or the user. A user-supplied operand is labelled as
    one and is kept apart from the observed facts.
    """
    # The isolation is asserted here, at the point a figure is produced, not
    # assumed to have survived from the lane.
    assert_research_isolation(
        [config.metric_id for config in lane_configs()]
    )

    result = _selected_result(request.metric_id)
    config = _config_for(result.lane_id)
    capture_identity = _capture_identity(config.capture_dir)
    distribution = result.distribution
    numerator_kind = config.numerator_kind

    # -- the multiple ---------------------------------------------------------
    multiple_evidence: Dict[str, Any] = {}
    multiple_observation_date: Optional[str] = None
    multiple_observation_hash: Optional[str] = None
    if request.multiple_source == MULTIPLE_HISTORY_MEDIAN:
        multiple = distribution.percentiles.get("median")
        if multiple is None:
            raise ResearchCalculationError(
                REFUSED_MULTIPLE_UNAVAILABLE,
                "This metric has no median: it holds no valid observation, so "
                "there is no historical statistic to apply.",
            )
        multiple_label = (
            f"The metric's own median over its {distribution.sample_count} valid "
            "observations, from "
            f"{distribution.period_start} to {distribution.period_end}."
        )
        multiple_evidence = {
            "source": MULTIPLE_HISTORY_MEDIAN,
            "statistic": "median",
            "sample_count": distribution.sample_count,
            "period_start": distribution.period_start,
            "period_end": distribution.period_end,
            "sampling_cadence": distribution.sampling_cadence,
        }
    elif request.multiple_source == MULTIPLE_OBSERVATION:
        if not request.observation_date:
            raise ResearchCalculationError(
                REFUSED_MULTIPLE_UNAVAILABLE,
                "A multiple taken from an observation needs the observation's "
                "evaluation date.",
            )
        observation = _observation_by_date(result, request.observation_date)
        if observation is None:
            raise ResearchCalculationError(
                REFUSED_OBSERVATION_UNKNOWN,
                f"The metric has no evaluation dated {request.observation_date}.",
            )
        if observation.value is None:
            raise ResearchCalculationError(
                REFUSED_OBSERVATION_REJECTED,
                f"The evaluation dated {request.observation_date} was refused "
                f"({observation.reason_code}): {observation.reason_detail}",
            )
        multiple = observation.value
        multiple_observation_date = observation.evaluation_date
        multiple_observation_hash = observation.content_hash
        multiple_label = (
            f"This metric's own value on {observation.evaluation_date}, the "
            "multiple the lane computed on that date from the filed facts."
        )
        multiple_evidence = {
            "source": MULTIPLE_OBSERVATION,
            "observation": observation.to_dict(),
        }
    else:
        multiple = request.multiple
        if multiple is None:
            raise ResearchCalculationError(
                REFUSED_MULTIPLE_UNAVAILABLE,
                "A user-supplied multiple needs a value.",
            )
        if not math.isfinite(multiple):
            raise ResearchCalculationError(
                REFUSED_MULTIPLE_NOT_FINITE,
                f"A multiple of {multiple!r} is not a finite number, so it "
                "cannot be applied to a market value. A multiple must be a "
                "finite number greater than zero.",
            )
        if multiple <= 0:
            raise ResearchCalculationError(
                REFUSED_MULTIPLE_NOT_POSITIVE,
                f"A multiple of {multiple} is not a usable multiple: it must be "
                "greater than zero.",
            )
        multiple_label = (
            "A multiple the user supplied. It is a research assumption, not an "
            "observed figure, and it is not part of the metric's sample."
        )
        multiple_evidence = {
            "source": MULTIPLE_USER_SUPPLIED,
            "label": USER_ASSUMPTION_LABEL,
            "value": multiple,
        }

    # -- the numerator --------------------------------------------------------
    numerator_evidence: Dict[str, Any] = {}
    numerator_date: Optional[str] = None
    numerator_observation_hash: Optional[str] = None
    if request.numerator_source == NUMERATOR_USER_SUPPLIED:
        if request.numerator_value is None:
            raise ResearchCalculationError(
                REFUSED_NUMERATOR_UNAVAILABLE,
                "A user-supplied market value needs a value.",
            )
        if not math.isfinite(request.numerator_value):
            raise ResearchCalculationError(
                REFUSED_NUMERATOR_NOT_FINITE,
                f"A market value of {request.numerator_value!r} is not a finite "
                "number, so it cannot be divided by a multiple. A market value "
                "must be a finite number greater than zero.",
            )
        if request.numerator_value <= 0:
            raise ResearchCalculationError(
                REFUSED_NUMERATOR_NOT_POSITIVE,
                f"A market value of {request.numerator_value} is not a usable "
                "market value: it must be greater than zero.",
            )
        numerator = float(request.numerator_value)
        numerator_label = (
            "A market value the user supplied. It is a research assumption, "
            "not an observed figure, and it is not part of the metric's sample."
        )
        numerator_evidence = {
            "source": NUMERATOR_USER_SUPPLIED,
            "label": USER_ASSUMPTION_LABEL,
            "value": numerator,
            "numerator_kind": numerator_kind,
        }
    else:
        if request.numerator_date:
            observation = _observation_by_date(result, request.numerator_date)
            if observation is None:
                raise ResearchCalculationError(
                    REFUSED_OBSERVATION_UNKNOWN,
                    f"The metric has no evaluation dated {request.numerator_date}.",
                )
            if observation.value is None:
                raise ResearchCalculationError(
                    REFUSED_OBSERVATION_REJECTED,
                    f"The evaluation dated {request.numerator_date} was refused "
                    f"({observation.reason_code}): {observation.reason_detail}",
                )
        else:
            observation = _latest_valid_observation(result)
            if observation is None:
                raise ResearchCalculationError(
                    REFUSED_NUMERATOR_UNAVAILABLE,
                    "This metric has no valid observation, so it has no market "
                    "value of its own to apply. A market value has to be "
                    "supplied by the user.",
                )
        value = _numerator_of(observation, numerator_kind)
        if value is None:
            if numerator_kind == "enterprise_value":
                raise ResearchCalculationError(
                    REFUSED_NUMERATOR_UNAVAILABLE,
                    f"The filed enterprise-value bridge is not complete on "
                    f"{observation.evaluation_date}, so this lane has no "
                    "enterprise value to apply on that date. The bridge is "
                    "never completed by omission or zero-fill.",
                )
            raise ResearchCalculationError(
                REFUSED_NUMERATOR_UNAVAILABLE,
                f"This lane has no market capitalisation on "
                f"{observation.evaluation_date}.",
            )
        numerator = float(value)
        numerator_date = observation.evaluation_date
        numerator_observation_hash = observation.content_hash
        numerator_label = (
            f"This lane's own {_numerator_short_label(result.lane_id)} on "
            f"{observation.evaluation_date}, built from the filed facts in this "
            "lane's own capture."
        )
        numerator_evidence = _numerator_evidence(observation, numerator_kind)

    # -- the figure ------------------------------------------------------------
    implied_denominator = numerator / multiple
    if not math.isfinite(implied_denominator):
        # Finite operands can still overflow: a very large market value over a
        # very small multiple is not a figure, and a figure that is not finite
        # is never published as a result.
        raise ResearchCalculationError(
            REFUSED_RESULT_NOT_FINITE,
            "The implied denominator is not a finite number: dividing the "
            f"market value {numerator} by the multiple {multiple} does not "
            "produce a figure. No result is produced from it.",
        )
    formula_operands = {
        "numerator": numerator,
        "numerator_source": request.numerator_source,
        "numerator_kind": numerator_kind,
        "multiple": multiple,
        "multiple_source": request.multiple_source,
        "implied_denominator": implied_denominator,
        "derivation": (
            f"{numerator_kind} / multiple = implied denominator, the reverse of "
            "the lane's own formula"
        ),
    }

    calculation_hash = hashlib.sha256(
        (
            "|".join(
                [
                    request.metric_id,
                    str(request.multiple_source),
                    str(request.multiple),
                    str(request.observation_date),
                    str(request.numerator_source),
                    str(request.numerator_value),
                    str(request.numerator_date),
                    result.input_set_id,
                    config.formula_version,
                    CALCULATOR_VERSION,
                ]
            )
            + "|"
            + repr(sorted(formula_operands.items()))
        ).encode("utf-8")
    ).hexdigest()

    return ResearchCalculationResult(
        metric_id=result.metric_id,
        lane_id=result.lane_id,
        issuer_id=result.issuer_id,
        instrument_id=result.instrument_id,
        status="AVAILABLE",
        production_eligible=distribution.production_eligible,
        research_use_label=distribution.research_use_label,
        multiple=float(multiple),
        multiple_source=request.multiple_source,
        multiple_label=multiple_label,
        multiple_observation_date=multiple_observation_date,
        multiple_observation_content_hash=multiple_observation_hash,
        numerator=numerator,
        numerator_source=request.numerator_source,
        numerator_label=numerator_label,
        numerator_kind=numerator_kind,
        numerator_date=numerator_date,
        numerator_observation_content_hash=numerator_observation_hash,
        implied_denominator=implied_denominator,
        implied_denominator_label=_denominator_label(result.lane_id),
        formula_expression=config.formula_expression,
        formula_version=config.formula_version,
        formula_operands=formula_operands,
        lane_input_set_id=result.input_set_id,
        lane_content_hash=result.content_hash,
        capture_identity=capture_identity,
        calculation_content_hash=calculation_hash,
        calculation_version=CALCULATOR_VERSION,
        methodology=result.methodology,
        logic_version=result.logic_version,
        numerator_evidence=numerator_evidence,
        multiple_evidence=multiple_evidence,
        registry_standing=distribution.registry_standing,
        basis_breaks=sorted(distribution.basis_breaks),
        prior_period_revisions=distribution.prior_period_revisions,
        production_refusal=distribution.production_refusal,
        data_limitations=distribution.data_limitations,
    )
