"""The research comparison and sensitivity service.

A comparison is an argument about two numbers, and the service's job is to
say what the argument may and may not rest on. It therefore answers three
questions before it shows anything:

* **Are the two metrics the same kind of thing?** Two metrics may be shown
  side by side, but a difference between them is only a statement about
  something when their definitions agree: the same numerator, the same
  denominator, the same currency, the same formula version. Where they do
  not agree, the comparison is labelled as a difference between two different
  formulas, and no single attribution is offered.

* **Are the two observations of the same thing?** A comparison across two
  evaluation dates of one lane is only a comparison if both dates published a
  figure. The dates in between that did not are shown, with their reasons,
  so that a reader never mistakes a sparse series for a continuous one.

* **Is the difference attributable?** For the two enterprise-value lanes,
  which differ in one bridge component, the difference is attributed only
  where the shared components, the denominator window and the knowability of
  every component agree. Where they do not, the pair is marked as affected
  by other factors rather than quietly concluded from.

The service never edits an observation. A sensitivity is a separate record
that names the assumption it makes, and it cannot be used to get around a
point-in-time refusal, a fiscal window that does not exist, or an
enterprise-value bridge that is not complete: a sensitivity may only be
computed on a date the lane itself published.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

from research_lane import ResearchLaneResult, ResearchObservation
from research_lane_ko import CANDIDATE_LANE_IDS, build_ko_research_lanes

COMPARISON_VERSION = "research-comparison/1.0"

# The kinds of comparison the service offers.
COMPARISON_HISTORY = "SAME_LANE_HISTORY"
COMPARISON_PAIRED_BRIDGE = "PAIRED_BRIDGE"
COMPARISON_CROSS_METRIC = "CROSS_METRIC"

# The service's own refusal codes, separate from the lane's observation
# refusals and the calculation's.
REFUSED_METRIC_UNAVAILABLE = "RESEARCH_COMPARISON_REFUSED_METRIC_UNAVAILABLE"
REFUSED_OBSERVATION_UNKNOWN = "RESEARCH_COMPARISON_REFUSED_OBSERVATION_UNKNOWN"
REFUSED_OBSERVATION_REJECTED = "RESEARCH_COMPARISON_REFUSED_OBSERVATION_REJECTED"
REFUSED_SAME_DATE = "RESEARCH_COMPARISON_REFUSED_SAME_DATE"
REFUSED_DATE_ORDER = "RESEARCH_COMPARISON_REFUSED_DATE_ORDER"
REFUSED_NOT_COMPARABLE = "RESEARCH_COMPARISON_REFUSED_NOT_COMPARABLE"
REFUSED_NO_PAIRED_DATES = "RESEARCH_COMPARISON_REFUSED_NO_PAIRED_DATES"
REFUSED_ASSUMPTION_UNKNOWN = "RESEARCH_SENSITIVITY_REFUSED_ASSUMPTION_UNKNOWN"
REFUSED_ASSUMPTION_NOT_POSITIVE = (
    "RESEARCH_SENSITIVITY_REFUSED_ASSUMPTION_NOT_POSITIVE"
)
REFUSED_ASSUMPTION_NOT_FINITE = "RESEARCH_SENSITIVITY_REFUSED_ASSUMPTION_NOT_FINITE"

CLOSED_COMPARISON_REASON_CODES = frozenset(
    {
        REFUSED_METRIC_UNAVAILABLE,
        REFUSED_OBSERVATION_UNKNOWN,
        REFUSED_OBSERVATION_REJECTED,
        REFUSED_SAME_DATE,
        REFUSED_DATE_ORDER,
        REFUSED_NOT_COMPARABLE,
        REFUSED_NO_PAIRED_DATES,
        REFUSED_ASSUMPTION_UNKNOWN,
        REFUSED_ASSUMPTION_NOT_POSITIVE,
        REFUSED_ASSUMPTION_NOT_FINITE,
    }
)

# The named sensitivity assumptions. The set is closed: a sensitivity names
# the assumption it makes, so that what was assumed can be told apart from
# what was observed.
ASSUMPTION_NUMERATOR_MULTIPLIER = "NUMERATOR_MULTIPLIER"
ASSUMPTION_MULTIPLE_OVERRIDE = "MULTIPLE_OVERRIDE"
SENSITIVITY_ASSUMPTIONS = {
    ASSUMPTION_NUMERATOR_MULTIPLIER: {
        "label": "The market value (or enterprise value) is multiplied by a factor",
        "unit": "factor",
        "applies_to": "numerator",
    },
    ASSUMPTION_MULTIPLE_OVERRIDE: {
        "label": "The research multiple is replaced with a supplied one",
        "unit": "multiple",
        "applies_to": "multiple",
    },
}


class ResearchComparisonError(Exception):
    """A comparison that cannot be made, with the reason it cannot be made."""

    def __init__(self, reason_code: str, detail: str) -> None:
        if reason_code not in CLOSED_COMPARISON_REASON_CODES:
            raise ValueError(
                f"reason_code {reason_code!r} is not in the closed comparison "
                "refusal set; an unknown code is an error, not a refusal"
            )
        super().__init__(detail)
        self.reason_code = reason_code
        self.detail = detail


# ---------------------------------------------------------------------------
# The metric definitions the comparisons are made against
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MetricDefinition:
    """The comparability attributes of one research metric."""

    metric_id: str
    lane_id: str
    metric_label: str
    numerator_kind: str
    numerator_description: str
    denominator_definition: str
    denominator_elements: Tuple[str, ...]
    currency: str
    unit: str
    formula_version: str
    formula_expression: str
    bridge_components: Tuple[str, ...]
    candidate_metric: bool
    sample_count: int
    total_evaluations: int
    period_start: Optional[str]
    period_end: Optional[str]
    registry_standing: Dict[str, Any]
    basis_breaks: Dict[str, List[str]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "lane_id": self.lane_id,
            "metric_label": self.metric_label,
            "numerator_kind": self.numerator_kind,
            "numerator_description": self.numerator_description,
            "denominator_definition": self.denominator_definition,
            "denominator_elements": list(self.denominator_elements),
            "currency": self.currency,
            "unit": self.unit,
            "formula_version": self.formula_version,
            "formula_expression": self.formula_expression,
            "bridge_components": list(self.bridge_components),
            "candidate_metric": self.candidate_metric,
            "sample_count": self.sample_count,
            "total_evaluations": self.total_evaluations,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "registry_standing": self.registry_standing,
            "basis_breaks": self.basis_breaks,
        }


_LANE_RESULTS: Optional[Dict[str, ResearchLaneResult]] = None


def _lane_results() -> Dict[str, ResearchLaneResult]:
    global _LANE_RESULTS
    if _LANE_RESULTS is None:
        _LANE_RESULTS = {result.lane_id: result for result in build_ko_research_lanes()}
    return _LANE_RESULTS


def _reset_lane_cache() -> None:
    global _LANE_RESULTS
    _LANE_RESULTS = None


def _definition_for(lane_id: str) -> MetricDefinition:
    result = _lane_results()[lane_id]
    distribution = result.distribution
    observation = next(
        (obs for obs in result.observations if obs.value is not None), None
    )
    denominator_elements: Tuple[str, ...] = ()
    bridge_components: Tuple[str, ...] = ()
    currency = "USD"
    unit = "USD"
    numerator_kind = "market_cap"
    numerator_description = "Market capitalisation"
    if observation is not None:
        denominator = observation.denominator or {}
        currency = denominator.get("currency") or currency
        unit = denominator.get("unit") or unit
        elements = sorted(
            {
                element
                for quarter in denominator.get("quarters", [])
                for element in quarter.get("elements", [])
            }
        )
        denominator_elements = tuple(elements)
        components = observation.bridge.get("components") or {}
        bridge_components = tuple(sorted(components))
        if observation.enterprise_value is not None:
            numerator_kind = "enterprise_value"
            numerator_description = (
                "Enterprise value, from this lane's own filed balance-sheet "
                "bridge"
            )
    return MetricDefinition(
        metric_id=result.metric_id,
        lane_id=result.lane_id,
        metric_label=distribution.metric_label,
        numerator_kind=numerator_kind,
        numerator_description=numerator_description,
        denominator_definition=distribution.formula.get("denominator", ""),
        denominator_elements=denominator_elements,
        currency=currency,
        unit=unit,
        formula_version=distribution.formula.get("formula_version", ""),
        formula_expression=distribution.formula.get("expression", ""),
        bridge_components=bridge_components,
        candidate_metric=distribution.candidate_metric,
        sample_count=distribution.sample_count,
        total_evaluations=distribution.total_evaluations,
        period_start=distribution.period_start,
        period_end=distribution.period_end,
        registry_standing=distribution.registry_standing,
        basis_breaks=distribution.basis_breaks,
    )


def metric_definitions() -> List[MetricDefinition]:
    """The comparability attributes of every selectable research metric."""
    return [_definition_for(lane_id) for lane_id in CANDIDATE_LANE_IDS]


def _definition_by_metric(metric_id: str) -> MetricDefinition:
    for definition in metric_definitions():
        if definition.metric_id == metric_id or definition.lane_id == metric_id:
            return definition
    raise ResearchComparisonError(
        REFUSED_METRIC_UNAVAILABLE,
        f"No research metric named {metric_id!r} is available.",
    )


def comparability(left_metric_id: str, right_metric_id: str) -> Dict[str, Any]:
    """
    Whether two research metrics may be compared, and on what basis.

    The answer separates the attributes that agree from those that do not,
    and names what kind of comparison the pair supports. Two metrics that
    do not share a definition may still be shown side by side, but the
    comparison is then a difference between two different formulas, and it
    carries no single attribution.
    """
    left = _definition_by_metric(left_metric_id)
    right = _definition_by_metric(right_metric_id)

    shared: Dict[str, Any] = {}
    differences: List[Dict[str, Any]] = []
    for attribute in (
        "numerator_kind",
        "denominator_definition",
        "denominator_elements",
        "currency",
        "formula_version",
    ):
        left_value = getattr(left, attribute)
        right_value = getattr(right, attribute)
        if left_value == right_value:
            shared[attribute] = left_value
        else:
            differences.append(
                {
                    "attribute": attribute,
                    "left": left_value,
                    "right": right_value,
                }
            )

    same_formula = (
        not differences and left.formula_expression == right.formula_expression
    )
    if same_formula:
        comparable_as = COMPARISON_HISTORY
        comparable = True
        reasons = [
            "The two metrics are the same formula, so a difference between "
            "their figures is a difference between their dates."
        ]
    elif not differences:
        # The same numerator and denominator, but a different bridge: the two
        # enterprise-value lanes.
        comparable_as = COMPARISON_PAIRED_BRIDGE
        comparable = True
        reasons = [
            "The two metrics share their numerator kind, their denominator, "
            "their currency and their formula version, and differ only in the "
            "short-term component of the bridge. They may be compared on a "
            "shared date, and the difference is attributable to that component "
            "only where every other component and the denominator window agree."
        ]
    else:
        comparable_as = COMPARISON_CROSS_METRIC
        comparable = False
        reasons = [
            "The two metrics are not the same formula: "
            + "; ".join(
                f"the {difference['attribute']} differs" for difference in differences
            )
            + ". They may be shown side by side, but the difference between "
            "their figures is a difference between two different formulas and "
            "is not attributed to any one factor."
        ]
    return {
        "left": left.to_dict(),
        "right": right.to_dict(),
        "same_formula": same_formula,
        "comparable": comparable,
        "comparable_as": comparable_as,
        "shared": shared,
        "differences": differences,
        "reasons": reasons,
    }


# ---------------------------------------------------------------------------
# Helpers over the observations
# ---------------------------------------------------------------------------


def _result_for(metric_id: str) -> ResearchLaneResult:
    definition = _definition_by_metric(metric_id)
    return _lane_results()[definition.lane_id]


def _observation(result: ResearchLaneResult, evaluation_date: str) -> ResearchObservation:
    for observation in result.observations:
        if observation.evaluation_date == evaluation_date:
            return observation
    raise ResearchComparisonError(
        REFUSED_OBSERVATION_UNKNOWN,
        f"The metric has no evaluation dated {evaluation_date}.",
    )


def _published(
    result: ResearchLaneResult, evaluation_date: str
) -> ResearchObservation:
    observation = _observation(result, evaluation_date)
    if observation.value is None:
        raise ResearchComparisonError(
            REFUSED_OBSERVATION_REJECTED,
            f"The evaluation dated {evaluation_date} was refused "
            f"({observation.reason_code}): {observation.reason_detail}",
        )
    return observation


def _observation_evidence(observation: ResearchObservation) -> Dict[str, Any]:
    """The trace of one observation, for the comparison to show."""
    return {
        "evaluation_date": observation.evaluation_date,
        "value": observation.value,
        "price": observation.price,
        "price_currency": observation.price_currency,
        "price_source": observation.price_source,
        "shares_outstanding": observation.shares_outstanding,
        "shares_accession": observation.shares_accession,
        "shares_usable_date": observation.shares_usable_date,
        "shares_source": observation.shares_source,
        "market_cap": observation.market_cap,
        "enterprise_value": observation.enterprise_value,
        "total_debt": observation.total_debt,
        "liquid_funds": observation.liquid_funds,
        "denominator": observation.denominator,
        "bridge": observation.bridge,
        "formula": observation.formula,
        "registry_standing": observation.registry_standing,
        "basis_breaks": observation.basis_breaks,
        "prior_period_revisions": observation.prior_period_revisions,
        "point_in_time": observation.point_in_time,
        "content_hash": observation.content_hash,
        "input_set_id": observation.input_set_id,
        "formula_version": observation.formula_version,
    }


def _bridge_summary(observation: ResearchObservation) -> Dict[str, Any]:
    bridge = observation.bridge or {}
    components = bridge.get("components") or {}
    return {
        "complete": bool(bridge.get("complete")),
        "balance_sheet_date": bridge.get("balance_sheet_date"),
        "distinct_period_ends": bridge.get("distinct_period_ends") or [],
        "components_absent": bridge.get("components_absent") or [],
        "components": {
            name: {
                "element": component.get("element"),
                "value": component.get("value"),
                "period_end": component.get("period_end"),
                "accession": component.get("accession"),
                "filed": component.get("filed"),
                "usable_date": component.get("usable_date"),
                "currency": component.get("currency"),
                "source_file": component.get("source_file"),
                "source_sha256": component.get("content_sha256"),
                "source_url": component.get("source_url"),
            }
            for name, component in components.items()
        },
    }


def _denominator_summary(observation: ResearchObservation) -> Dict[str, Any]:
    denominator = observation.denominator or {}
    return {
        "value": denominator.get("value"),
        "unit": denominator.get("unit"),
        "currency": denominator.get("currency"),
        "anchor": denominator.get("anchor"),
        "positions": denominator.get("positions") or [],
        "quarters": [
            {
                "period_end": quarter.get("period_end"),
                "value": quarter.get("value"),
                "unit": quarter.get("unit"),
                "accessions": quarter.get("accessions") or [],
                "elements": quarter.get("elements") or [],
                "knowable_from": quarter.get("knowable_from"),
            }
            for quarter in denominator.get("quarters", [])
        ],
    }


def _denominator_signature(observation: ResearchObservation) -> Tuple:
    """The identity of a denominator window: its periods, values and filings."""
    denominator = observation.denominator or {}
    return tuple(
        (
            quarter.get("period_end"),
            quarter.get("value"),
            tuple(quarter.get("accessions") or []),
        )
        for quarter in denominator.get("quarters", [])
    )


def _content_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


# ---------------------------------------------------------------------------
# The historical comparison
# ---------------------------------------------------------------------------


def compare_history(
    metric_id: str, earlier_date: str, later_date: str
) -> Dict[str, Any]:
    """
    One research metric at two evaluation dates.

    Both dates must have published a figure. The dates in between that did
    not are shown with their reasons, so that the two figures are not read as
    a continuous series.
    """
    if earlier_date == later_date:
        raise ResearchComparisonError(
            REFUSED_SAME_DATE,
            "A comparison needs two different evaluation dates.",
        )
    if earlier_date > later_date:
        raise ResearchComparisonError(
            REFUSED_DATE_ORDER,
            "The earlier date must come before the later date.",
        )
    result = _result_for(metric_id)
    earlier = _published(result, earlier_date)
    later = _published(result, later_date)

    between = [
        {
            "evaluation_date": observation.evaluation_date,
            "reason_code": observation.reason_code,
            "reason_detail": observation.reason_detail,
        }
        for observation in result.observations
        if earlier_date < observation.evaluation_date < later_date
        and observation.value is None
    ]

    earlier_value = earlier.value
    later_value = later.value
    absolute_change = later_value - earlier_value
    percentage_change = (
        absolute_change / earlier_value if earlier_value else None
    )

    earlier_evidence = _observation_evidence(earlier)
    later_evidence = _observation_evidence(later)

    # What changed in the evidence itself between the two dates.
    earlier_bridge = earlier_evidence["bridge"]
    later_bridge = later_evidence["bridge"]
    earlier_components = {
        name: component.get("element")
        for name, component in (earlier_bridge.get("components") or {}).items()
    }
    later_components = {
        name: component.get("element")
        for name, component in (later_bridge.get("components") or {}).items()
    }
    element_changes = sorted(
        name
        for name in set(earlier_components) | set(later_components)
        if earlier_components.get(name) != later_components.get(name)
    )
    coverage_changes = {
        "earlier_bridge_complete": earlier_bridge.get("complete"),
        "later_bridge_complete": later_bridge.get("complete"),
        "earlier_bridge_date": earlier_bridge.get("balance_sheet_date"),
        "later_bridge_date": later_bridge.get("balance_sheet_date"),
        "elements_changed": element_changes,
        "denominator_window_changed": (
            _denominator_signature(earlier) != _denominator_signature(later)
        ),
    }

    payload = {
        "comparison_kind": COMPARISON_HISTORY,
        "comparison_version": COMPARISON_VERSION,
        "metric_id": result.metric_id,
        "lane_id": result.lane_id,
        "earlier": earlier_evidence,
        "later": later_evidence,
        "comparison": {
            "earlier_multiple": earlier_value,
            "later_multiple": later_value,
            "absolute_change": absolute_change,
            "percentage_change": percentage_change,
            "earlier_numerator": earlier_evidence.get("market_cap")
            if earlier_evidence.get("enterprise_value") is None
            else earlier_evidence.get("enterprise_value"),
            "later_numerator": later_evidence.get("market_cap")
            if later_evidence.get("enterprise_value") is None
            else later_evidence.get("enterprise_value"),
            "earlier_denominator": (earlier_evidence.get("denominator") or {}).get(
                "value"
            ),
            "later_denominator": (later_evidence.get("denominator") or {}).get("value"),
        },
        "evidence_changes": coverage_changes,
        "basis_breaks": {
            "earlier": earlier_evidence.get("basis_breaks") or [],
            "later": later_evidence.get("basis_breaks") or [],
        },
        "prior_period_revisions": {
            "earlier": earlier_evidence.get("prior_period_revisions") or [],
            "later": later_evidence.get("prior_period_revisions") or [],
        },
        "refused_between": between,
        "refused_between_count": len(between),
        "production_eligible": False,
    }
    payload["comparison_hash"] = _content_hash(payload)
    return payload


# ---------------------------------------------------------------------------
# The paired bridge comparison
# ---------------------------------------------------------------------------


def compare_bridges(
    left_metric_id: str, right_metric_id: str
) -> Dict[str, Any]:
    """
    Two enterprise-value lanes on the dates where both published.

    Only the intersection counts. For each shared date the service checks
    that every component of both bridges describes one balance-sheet date and
    was knowable at that date, that the denominator window is the same
    version in both lanes, and that the components other than the short-term
    one agree. Where they do, the difference is attributed to the short-term
    component; where they do not, the pair is marked as affected by other
    factors.
    """
    left_definition = _definition_by_metric(left_metric_id)
    right_definition = _definition_by_metric(right_metric_id)
    left_result = _result_for(left_metric_id)
    right_result = _result_for(right_metric_id)

    left_observations = {
        observation.evaluation_date: observation
        for observation in left_result.observations
    }
    right_observations = {
        observation.evaluation_date: observation
        for observation in right_result.observations
    }

    shared_dates = sorted(set(left_observations) & set(right_observations))
    paired: List[Dict[str, Any]] = []
    left_only: List[Dict[str, Any]] = []
    right_only: List[Dict[str, Any]] = []
    neither: List[Dict[str, Any]] = []

    for evaluation_date in shared_dates:
        left_observation = left_observations[evaluation_date]
        right_observation = right_observations[evaluation_date]
        if (
            left_observation.value is None
            and right_observation.value is None
        ):
            neither.append(
                {
                    "evaluation_date": evaluation_date,
                    "left_reason_code": left_observation.reason_code,
                    "right_reason_code": right_observation.reason_code,
                }
            )
            continue
        if left_observation.value is None:
            left_only.append(
                {
                    "evaluation_date": evaluation_date,
                    "reason_code": left_observation.reason_code,
                    "reason_detail": left_observation.reason_detail,
                    "side": "left",
                }
            )
            continue
        if right_observation.value is None:
            right_only.append(
                {
                    "evaluation_date": evaluation_date,
                    "reason_code": right_observation.reason_code,
                    "reason_detail": right_observation.reason_detail,
                    "side": "right",
                }
            )
            continue
        paired.append(
            _pair_entry(
                left_observation,
                right_observation,
                left_definition,
                right_definition,
            )
        )

    attributable = [entry for entry in paired if entry["attributable"]]
    summary = {
        "comparison_kind": COMPARISON_PAIRED_BRIDGE,
        "comparison_version": COMPARISON_VERSION,
        "left": left_definition.to_dict(),
        "right": right_definition.to_dict(),
        "paired_sample_count": len(paired),
        "attributable_sample_count": len(attributable),
        "shared_date_count": len(shared_dates),
        "unpaired_left": left_only,
        "unpaired_right": right_only,
        "refused_on_both": neither,
        "pairs": paired,
        "compatibility": comparability(left_metric_id, right_metric_id),
        "production_eligible": False,
    }
    summary["comparison_hash"] = _content_hash(summary)
    return summary


def _long_term_debt(components: Mapping[str, Any]) -> Optional[float]:
    """The long-term debt of a bridge, taken component by component."""
    values = [
        component.get("value")
        for name, component in components.items()
        if name in ("long_term_debt_current", "long_term_debt_noncurrent")
    ]
    if not values or any(value is None for value in values):
        return None
    return sum(values)


def _liquid_funds(components: Mapping[str, Any]) -> Optional[float]:
    """The liquid funds of a bridge, taken component by component."""
    values = [
        component.get("value")
        for name, component in components.items()
        if name in ("cash", "marketable_securities_current")
    ]
    if not values or any(value is None for value in values):
        return None
    return sum(values)


def _pair_entry(
    left: ResearchObservation,
    right: ResearchObservation,
    left_definition: MetricDefinition,
    right_definition: MetricDefinition,
) -> Dict[str, Any]:
    """One paired date, with the difference and what it can be attributed to."""
    left_bridge = _bridge_summary(left)
    right_bridge = _bridge_summary(right)
    left_components = left_bridge["components"]
    right_components = right_bridge["components"]

    shared_names = sorted(set(left_components) & set(right_components))
    differing_names = sorted(
        name
        for name in set(left_components) | set(right_components)
        if left_components.get(name, {}).get("value")
        != right_components.get(name, {}).get("value")
    )

    # The denominator window, and whether the two lanes read the same one.
    same_denominator = _denominator_signature(left) == _denominator_signature(right)
    same_market_cap = left.market_cap == right.market_cap
    # The long-term debt is compared component by component: a lane's
    # `total_debt` aggregate includes its short-term component, so the
    # aggregate would differ by exactly the difference under test.
    same_long_term_debt = _long_term_debt(left_components) == _long_term_debt(
        right_components
    )
    same_liquid_funds = _liquid_funds(left_components) == _liquid_funds(
        right_components
    )

    # Every component of both bridges: one balance-sheet date, knowable.
    knowable = True
    for observation, bridge in ((left, left_bridge), (right, right_bridge)):
        if not bridge["complete"]:
            knowable = False
        if len(bridge["distinct_period_ends"]) != 1:
            knowable = False
        for component in bridge["components"].values():
            if component["usable_date"] > observation.evaluation_date:
                knowable = False

    ev_difference = None
    if left.enterprise_value is not None and right.enterprise_value is not None:
        ev_difference = right.enterprise_value - left.enterprise_value
    multiple_difference = right.value - left.value

    # The short-term components, and what their difference is.
    short_term_difference = None
    short_term_names: Dict[str, Any] = {}
    for name, component in right_components.items():
        if name in left_components:
            continue
        if name in ("commercial_paper", "notes_and_loans_payable"):
            counterpart = "commercial_paper" if name == "notes_and_loans_payable" else "notes_and_loans_payable"
            left_value = left_components.get(counterpart, {}).get("value")
            if left_value is not None:
                short_term_difference = component["value"] - left_value
                short_term_names = {
                    "right": name,
                    "left": counterpart,
                    "right_value": component["value"],
                    "left_value": left_value,
                    "right_element": component.get("element"),
                    "left_element": left_components.get(counterpart, {}).get("element"),
                    "right_period_end": component.get("period_end"),
                    "left_period_end": left_components.get(counterpart, {}).get(
                        "period_end"
                    ),
                }

    factors: List[str] = []
    if not knowable:
        factors.append(
            "A bridge component is not knowable at this date, or the bridge's "
            "components do not describe one balance-sheet date."
        )
    if not same_denominator:
        factors.append(
            "The two lanes read different denominator windows, so the "
            "difference is not a bridge difference."
        )
    if not same_market_cap:
        factors.append("The two lanes read different market capitalisations.")
    if not same_long_term_debt:
        factors.append("The two lanes read different long-term debt.")
    if not same_liquid_funds:
        factors.append("The two lanes read different liquid funds.")
    if not short_term_names:
        factors.append(
            "The two lanes do not differ in a short-term borrowings component, "
            "so there is no short-term difference to attribute."
        )
    if short_term_names and short_term_names.get("right_period_end") != (
        short_term_names.get("left_period_end")
    ):
        factors.append(
            "The two short-term components are measured at different balance-"
            "sheet dates."
        )

    attributable = not factors
    if attributable and ev_difference is not None:
        if abs(ev_difference - float(short_term_difference)) > 0.5:
            factors.append(
                "The enterprise-value difference is not the difference of the "
                "two short-term components."
            )
            attributable = False

    return {
        "evaluation_date": left.evaluation_date,
        "left": {
            "metric_id": left.metric_id,
            "value": left.value,
            "market_cap": left.market_cap,
            "enterprise_value": left.enterprise_value,
            "denominator": _denominator_summary(left),
            "bridge": left_bridge,
            "content_hash": left.content_hash,
            "input_set_id": left.input_set_id,
        },
        "right": {
            "metric_id": right.metric_id,
            "value": right.value,
            "market_cap": right.market_cap,
            "enterprise_value": right.enterprise_value,
            "denominator": _denominator_summary(right),
            "bridge": right_bridge,
            "content_hash": right.content_hash,
            "input_set_id": right.input_set_id,
        },
        "differences": {
            "enterprise_value": ev_difference,
            "multiple": multiple_difference,
            "short_term_components": short_term_names,
            "short_term_value_difference": short_term_difference,
        },
        "checks": {
            "same_denominator_window": same_denominator,
            "same_market_cap": same_market_cap,
            "same_long_term_debt": same_long_term_debt,
            "same_liquid_funds": same_liquid_funds,
            "components_knowable_and_aligned": knowable,
            "shared_components": shared_names,
            "components_that_differ": differing_names,
        },
        "attributable": attributable,
        "other_factors": factors,
        "basis_breaks": {
            "left": list(left.basis_breaks),
            "right": list(right.basis_breaks),
        },
        "prior_period_revisions": {
            "left": list(left.prior_period_revisions),
            "right": list(right.prior_period_revisions),
        },
    }


# ---------------------------------------------------------------------------
# The sensitivity analysis
# ---------------------------------------------------------------------------


def run_sensitivity(
    metric_id: str,
    evaluation_date: str,
    assumption: str,
    value: float,
) -> Dict[str, Any]:
    """
    How one named research figure changes when one named input is changed.

    The observation is not modified. The sensitivity is a separate record
    that names the assumption it makes, and it may only be computed on a date
    the lane itself published: a date the lane refused cannot be made into a
    figure by an assumption.
    """
    if assumption not in SENSITIVITY_ASSUMPTIONS:
        raise ResearchComparisonError(
            REFUSED_ASSUMPTION_UNKNOWN,
            f"{assumption!r} is not a named sensitivity assumption. The named "
            "assumptions are "
            + ", ".join(sorted(SENSITIVITY_ASSUMPTIONS))
            + ".",
        )
    if not math.isfinite(value):
        raise ResearchComparisonError(
            REFUSED_ASSUMPTION_NOT_FINITE,
            "The assumption is not a finite number, so it cannot be applied.",
        )
    if value <= 0:
        raise ResearchComparisonError(
            REFUSED_ASSUMPTION_NOT_POSITIVE,
            "The assumption must be greater than zero.",
        )
    result = _result_for(metric_id)
    observation = _published(result, evaluation_date)

    baseline_multiple = observation.value
    baseline_numerator = (
        observation.enterprise_value
        if observation.enterprise_value is not None
        else observation.market_cap
    )
    if baseline_numerator is None:
        raise ResearchComparisonError(
            REFUSED_OBSERVATION_REJECTED,
            "The observation carries no market value to adjust.",
        )
    denominator = (observation.denominator or {}).get("value")

    if assumption == ASSUMPTION_NUMERATOR_MULTIPLIER:
        adjusted_numerator = baseline_numerator * value
        adjusted_multiple = (
            adjusted_numerator / denominator if denominator else None
        )
        adjusted_denominator = denominator
        formula = (
            "(market value x the factor) / the denominator = the adjusted "
            "multiple"
        )
    else:
        adjusted_multiple = value
        adjusted_numerator = baseline_numerator
        adjusted_denominator = (
            baseline_numerator / value if value else None
        )
        formula = (
            "the market value / the supplied multiple = the adjusted implied "
            "denominator"
        )

    absolute_change = (
        adjusted_multiple - baseline_multiple
        if adjusted_multiple is not None
        else None
    )
    percentage_change = (
        absolute_change / baseline_multiple if baseline_multiple else None
    )

    assumption_record = {
        "name": assumption,
        "label": SENSITIVITY_ASSUMPTIONS[assumption]["label"],
        "unit": SENSITIVITY_ASSUMPTIONS[assumption]["unit"],
        "applies_to": SENSITIVITY_ASSUMPTIONS[assumption]["applies_to"],
        "value": value,
        "origin": "user_supplied_research_assumption",
    }

    payload = {
        "comparison_kind": "SENSITIVITY",
        "comparison_version": COMPARISON_VERSION,
        "metric_id": result.metric_id,
        "lane_id": result.lane_id,
        "evaluation_date": evaluation_date,
        "assumption": assumption_record,
        "baseline": {
            "multiple": baseline_multiple,
            "numerator": baseline_numerator,
            "denominator": denominator,
            "content_hash": observation.content_hash,
            "input_set_id": observation.input_set_id,
        },
        "adjusted": {
            "multiple": adjusted_multiple,
            "numerator": adjusted_numerator,
            "denominator": adjusted_denominator,
        },
        "change": {
            "absolute": absolute_change,
            "percentage": percentage_change,
        },
        "formula": formula,
        "observation": _observation_evidence(observation),
        "notice": (
            "A sensitivity is a what-if on one named input. It is not a "
            "forecast, a target price or a fair value, and it does not change "
            "the observation it is computed on."
        ),
        "production_eligible": False,
    }
    payload["assumption_hash"] = _content_hash(assumption_record)
    payload["comparison_hash"] = _content_hash(payload)
    return payload
