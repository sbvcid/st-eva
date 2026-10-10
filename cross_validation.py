"""
ST-EVA 2.3-B - cross-source comparability policy.

Pure functions. No network, no clock, no filesystem. The policy is separated
from the adapters so that "can these two numbers be compared at all" is decided
by declared rules before any value is read, and so the rules can be tested
without touching a live API.

The governing principle, from docs/ST-EVA-2.3-B-SEC-VALIDATION.md:

    Validation is a third thing. It is not a modification of an Observation.

Nothing in this module merges, averages, blends, or selects a winning source.
The only things it produces are a `ValidationRecord` and a
`CrossValidationResult` that *reference* the observations on both sides.

There is deliberately no reconciliation helper here. If one is ever added, the
"no merge" guarantee in the spec and its test both become false.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from data_contract import (
    COMPARABLE_METRICS,
    CrossValidationResult,
    METRIC_ASSETS,
    METRIC_LONG_TERM_DEBT,
    METRIC_CASH,
    METRIC_EPS_DILUTED,
    METRIC_NET_INCOME,
    METRIC_REVENUE,
    METRIC_SHARES_OUTSTANDING,
    Observation,
    canonical_metric_id,
    Unit,
    ValidationRecord,
    ValidationStatus,
    is_comparable_observation,
    is_number,
    parse_iso_date,
)

# Company fiscal calendars do not align with calendar quarters. Apple's fiscal
# Q3 2026 ended 2026-06-27 while a vendor stamps its trailing figure
# 2026-06-30. A few days is ordinary noise; a quarter is a different period.
PERIOD_ALIGNMENT_WINDOW_DAYS = 7

# Independence of the two sources, per metric. A vendor that ingests a filing
# will agree with that filing by construction, and calling that corroboration
# would overstate what has been checked.
INDEPENDENCE_UNVERIFIED = "UNVERIFIED_INDEPENDENCE"
INDEPENDENCE_NONE = "NOT_INDEPENDENT"

_TOLERANCE_KIND = "RELATIVE_AND_ABSOLUTE_BOUND"


@dataclass(frozen=True)
class Tolerance:
    """
    The rule that decides agreement. Both bounds must hold.

    A difference passes only when it is small *relatively* and small
    *absolutely*. Either bound alone is wrong in a way that matters here:

    - Relative alone would accept a 0.5% gap on a 466 billion revenue figure.
      That is 2.3 billion dollars, which no reader would call agreement.
    - Absolute alone would accept any difference between two per-share
      figures, because every diluted EPS is under 100 and the only thing
      separating most of them is rounding.

    So the effective width is the tighter of the two. Each metric declares the
    pair that suits its magnitude: a revenue tolerance in the tens of millions,
    an EPS tolerance in the hundredths.
    """

    kind: str
    relative: float
    absolute: float

    def allowed(self, left: float, right: float) -> float:
        return min(
            self.relative * max(abs(left), abs(right)),
            self.absolute,
        )

    def allows(self, left: float, right: float) -> bool:
        return abs(left - right) <= self.allowed(left, right)

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "relative": self.relative,
            "absolute": self.absolute,
            "rule": "difference must satisfy both bounds",
        }


@dataclass(frozen=True)
class ComparabilitySpec:
    """The declared conditions under which a metric may be compared."""

    metric: str
    contract_unit: str
    # "duration" is a flow over a period; "instant" is a stock at a date.
    period_type: str
    # The measurement basis each side must claim: TTM, or a point-in-time value.
    measurement_basis: str
    tolerance: Tolerance
    independence: str
    independence_note: str
    # Whether the side is expected to be compared numerically at all. `assets`
    # is False because the vendor publishes no counterpart, and declaring that
    # up front is better than discovering it as a mystery null every run.
    yahoo_comparable: bool = True
    # Notes that are part of the verdict, not decoration.
    known_caveats: Tuple[str, ...] = ()


_MONETARY = Unit.CURRENCY.value
_PER_SHARE = Unit.PER_SHARE.value
_COUNT = Unit.COUNT.value

_VENDOR_AGGREGATE_NOTE = (
    "The vendor's trailing aggregate is not the same computation as the "
    "filing-side roll-forward, so agreement is meaningful; but the vendor's "
    "ingestion path is not disclosed, so independence is unverified."
)

_VENDOR_WINDOW_CAVEAT = (
    "The vendor does not publish the trailing window it used; the match rests "
    "on the as-of date, not on a declared period."
)

COMPARABILITY: Dict[str, ComparabilitySpec] = {
    METRIC_REVENUE: ComparabilitySpec(
        metric=METRIC_REVENUE,
        contract_unit=_MONETARY,
        period_type="duration",
        measurement_basis="TTM",
        tolerance=Tolerance(
            kind=_TOLERANCE_KIND,
            relative=0.005,
            absolute=50_000_000.0,
        ),
        independence=INDEPENDENCE_UNVERIFIED,
        independence_note=_VENDOR_AGGREGATE_NOTE,
        known_caveats=(_VENDOR_WINDOW_CAVEAT,),
    ),
    METRIC_NET_INCOME: ComparabilitySpec(
        metric=METRIC_NET_INCOME,
        contract_unit=_MONETARY,
        period_type="duration",
        measurement_basis="TTM",
        tolerance=Tolerance(
            kind=_TOLERANCE_KIND,
            relative=0.005,
            absolute=50_000_000.0,
        ),
        independence=INDEPENDENCE_UNVERIFIED,
        independence_note=_VENDOR_AGGREGATE_NOTE,
        known_caveats=(_VENDOR_WINDOW_CAVEAT,),
    ),
    METRIC_EPS_DILUTED: ComparabilitySpec(
        metric=METRIC_EPS_DILUTED,
        contract_unit=_PER_SHARE,
        period_type="duration",
        measurement_basis="TTM",
        tolerance=Tolerance(
            kind=_TOLERANCE_KIND,
            relative=0.01,
            absolute=0.01,
        ),
        independence=INDEPENDENCE_UNVERIFIED,
        independence_note="",
        known_caveats=(
            "Per-share amounts are not strictly additive: summing four "
            "quarterly diluted EPS figures only reproduces a trailing figure "
            "while the share denominator is constant.",
        ),
    ),
    METRIC_ASSETS: ComparabilitySpec(
        metric=METRIC_ASSETS,
        contract_unit=_MONETARY,
        period_type="instant",
        measurement_basis="INSTANT",
        tolerance=Tolerance(
            kind=_TOLERANCE_KIND,
            relative=0.005,
            absolute=50_000_000.0,
        ),
        independence=INDEPENDENCE_NONE,
        independence_note="",
        yahoo_comparable=False,
        known_caveats=(
            "The vendor publishes no total-assets counterpart; its "
            "fundamentals-timeseries request for total assets returns HTTP 404.",
        ),
    ),
    METRIC_CASH: ComparabilitySpec(
        metric=METRIC_CASH,
        contract_unit=_MONETARY,
        period_type="instant",
        measurement_basis="INSTANT",
        tolerance=Tolerance(
            kind=_TOLERANCE_KIND,
            relative=0.01,
            absolute=50_000_000.0,
        ),
        independence=INDEPENDENCE_UNVERIFIED,
        independence_note="",
        known_caveats=(
            "The vendor's totalCash includes short-term investments; the "
            "filing-side cash concept does not. The two are different "
            "quantities.",
        ),
    ),
    METRIC_LONG_TERM_DEBT: ComparabilitySpec(
        metric=METRIC_LONG_TERM_DEBT,
        contract_unit=_MONETARY,
        period_type="instant",
        measurement_basis="INSTANT",
        tolerance=Tolerance(
            kind=_TOLERANCE_KIND,
            relative=0.01,
            absolute=50_000_000.0,
        ),
        independence=INDEPENDENCE_UNVERIFIED,
        independence_note="",
        known_caveats=(
            "Long-term debt, per the 2.33 decision: the current and non-current "
            "portions of long-term debt, excluding short-term borrowings. The "
            "filing taxonomy publishes no single long-term-debt concept, so the "
            "figure is composed from the filer's current and non-current "
            "long-term concepts -- and that composition was verified rather "
            "than assumed: `LongTermDebtCurrent + LongTermDebtNoncurrent == "
            "us-gaap:LongTermDebt` holds in 451 periods across 25 filers, "
            "reproducible from the source documents. Filers still compose the "
            "current and non-current sides from different bases in some cases "
            "(capital leases on one side only), so a summed total is not always "
            "the filer's own. No vendor figure is expected for this metric: the "
            "Yahoo projection that once supplied one projected a *total* debt "
            "into a long-term-debt metric and was retired rather than caveated.",
        ),
    ),
    METRIC_SHARES_OUTSTANDING: ComparabilitySpec(
        metric=METRIC_SHARES_OUTSTANDING,
        contract_unit=_COUNT,
        period_type="instant",
        measurement_basis="INSTANT",
        tolerance=Tolerance(
            kind=_TOLERANCE_KIND,
            relative=0.001,
            absolute=10_000.0,
        ),
        independence=INDEPENDENCE_NONE,
        independence_note=(
            "The vendor's share count is taken from the same regulatory cover "
            "page the filing source reads, so agreement here is not "
            "independent corroboration. It confirms the plumbing, not the "
            "number."
        ),
        known_caveats=(
            "The vendor publishes no date for this count, so the two figures "
            "cannot be confirmed to be contemporaneous.",
            "A period-average diluted share count is a different concept from "
            "a cover-page count outstanding.",
        ),
    ),
}

# Metrics whose two sides are known to answer different questions, so a numeric
# verdict would be false. They are classified METHODOLOGY_MISMATCH rather than
# being compared and then excused.
#
# `shares_outstanding` is deliberately absent: both sides read the same cover
# page, so they are the same concept. Its problem is a missing date, not a
# different definition, and naming the wrong problem would be worse than
# naming none.
DEFINITION_DIVERGENT_METRICS = frozenset(
    {METRIC_CASH, METRIC_LONG_TERM_DEBT})

# Basis keys that, when they differ, mean the two figures are counting
# different things rather than disagreeing about the same thing. A listed
# instrument that is not the registered security, such as an American Depositary
# Share, is the case this exists for: a price quoted per ADS, a filing count of
# ordinary shares, and accounts denominated in the local currency are three
# different bases, and dividing one by another is arithmetic without meaning.
_BASIS_EXCLUSIONARY_KEYS = (
    "security_type",
    "shares_basis",
    "reporting_currency",
    "measurement_basis",
)

# A difference in a share count beyond this is a conflict rather than a
# rounding difference. It is a ratio, not an explanation: what the factor
# *means* is something only the issuer or the vendor can say, and ST-EVA does
# not say it.
SHARE_COUNT_CONFLICT_RATIO = 0.10

# Metrics whose two values are counts of a security, and where a large
# difference is therefore a question about what is being counted rather than
# about the number.
_SHARE_BASIS_METRICS = frozenset({METRIC_SHARES_OUTSTANDING})


def _undemonstrated_basis_result(
    metric: str,
    basis: Dict[str, Any],
    vendor: Observation,
    filing: Observation,
    ratio: float,
    references: Sequence[str],
    checked_at: str,
) -> CrossValidationResult:
    """
    Two counts that differ materially, where only one side declares its basis.

    The magnitude is reported because it is measurable. The cause is not,
    because a source that does not say what it is counting cannot be
    interpreted, and inferring a listing ratio from a number is exactly the kind
    of assumption this project exists not to make.
    """
    basis = dict(basis)
    basis["value_ratio"] = ratio
    basis["basis_differences"] = None
    basis["ratio_interpretation"] = (
        "NOT_EXPLAINED. The counts differ by a factor of "
        f"{ratio:.4f}, which is far more than a rounding difference. One "
        "source declares the security or share basis it counts and the other "
        "does not, so the two cannot be shown to be counting the same thing. "
        "ST-EVA does not infer what the factor represents."
    )
    return CrossValidationResult(
        metric=metric,
        status=ValidationStatus.METHODOLOGY_MISMATCH,
        validation=_record(
            ValidationStatus.METHODOLOGY_MISMATCH,
            metric,
            basis,
            [
                "the two counts differ by a factor of "
                f"{ratio:.4f} and one source does not declare its share basis"
            ],
            (
                f"{metric} could not be compared. The two sources report counts "
                f"differing by a factor of {ratio:.4f}, and one of them does "
                "not declare the security or share basis it is counting, so "
                "the two cannot be shown to be the same quantity. Both values "
                "are retained unchanged, no numeric verdict is issued, and no "
                "listing or share-class relationship is inferred."
            ),
            references,
            value_snapshot=(vendor.value, filing.value),
            checked_at=checked_at,
        ),
        left_observation_id=vendor.observation_id,
        right_observation_id=filing.observation_id,
    )


def _basis_of(observation: Observation) -> Dict[str, Any]:
    return observation.basis if isinstance(observation.basis, dict) else {}


def _declared_basis_value(basis: Dict[str, Any], key: str) -> Optional[str]:
    """
    A basis key a source actually declared.

    An explicit "UNDECLARED" is an absence, not a value. Comparing it against a
    stated value would manufacture a basis conflict out of missing information,
    and a conflict raised that often is a conflict nobody reads.
    """
    value = basis.get(key)
    if not value:
        return None
    text = str(value).strip()
    if not text or text.upper() in ("UNDECLARED", "UNKNOWN", "NONE"):
        return None
    return text


def _basis_conflict(
    left: Observation,
    right: Observation,
) -> Optional[Dict[str, Any]]:
    """
    Compare the declared bases of two figures of the same metric.

    Returns the differing keys, or None. Only keys a source actually declared
    are compared, for the same reason an undeclared currency does not make two
    figures conflict: absence is not a difference.
    """
    left_basis = _basis_of(left)
    right_basis = _basis_of(right)
    differences: Dict[str, Any] = {}
    for key in _BASIS_EXCLUSIONARY_KEYS:
        left_value = _declared_basis_value(left_basis, key)
        right_value = _declared_basis_value(right_basis, key)
        if left_value is None or right_value is None:
            continue
        if left_value.upper() != right_value.upper():
            differences[key] = {
                left.observation_id: left_value,
                right.observation_id: right_value,
            }
    return differences or None


def _value_ratio(left: Observation, right: Observation) -> Optional[float]:
    if not is_number(left.value) or not is_number(right.value):
        return None
    smaller = min(abs(float(left.value)), abs(float(right.value)))
    if smaller == 0:
        return None
    return max(abs(float(left.value)), abs(float(right.value))) / smaller


def _basis_mismatch_result(
    metric: str,
    basis: Dict[str, Any],
    differences: Dict[str, Any],
    vendor: Observation,
    filing: Observation,
    references: Sequence[str],
    checked_at: str,
) -> CrossValidationResult:
    """
    Two figures stated on different bases are a conflict, not a discrepancy.

    A discrepancy says "these measure the same thing and the numbers differ",
    which is a finding about the sources. A conflict says "these are not the
    same measurement", which is a finding about the comparison. Reporting the
    second as the first trains a reader to ignore the first.
    """
    ratio = _value_ratio(filing, vendor)
    basis = dict(basis)
    basis["value_ratio"] = ratio
    basis["basis_differences"] = differences
    basis["ratio_interpretation"] = (
        "NOT_EXPLAINED. The magnitude of the difference is reported because it "
        "is measurable. What the ratio represents - a listing ratio, a share "
        "class, a weighting, or two different dates - is not something ST-EVA "
        "can establish from the sources it holds, and is not asserted."
    )
    return CrossValidationResult(
        metric=metric,
        status=ValidationStatus.CONFLICTING,
        validation=_record(
            ValidationStatus.CONFLICTING,
            metric,
            basis,
            [
                "the two sources state different measurement bases: "
                + ", ".join(sorted(differences))
            ],
            (
                f"{metric} could not be compared because the two sources state "
                f"it on different bases ({', '.join(sorted(differences))}). "
                f"The values differ by a factor of "
                f"{ratio:.4f}." if ratio else
                f"{metric} could not be compared because the two sources state "
                f"it on different bases ({', '.join(sorted(differences))}). "
                "Both values are retained unchanged, neither is selected as "
                "correct, and no numeric verdict is issued."
            ),
            references,
            value_snapshot=(vendor.value, filing.value),
            checked_at=checked_at,
        ),
        left_observation_id=vendor.observation_id,
        right_observation_id=filing.observation_id,
    )


def spec_for(metric: str) -> Optional[ComparabilitySpec]:
    return COMPARABILITY.get(metric)


def _declared(observation: Observation, key: str) -> Optional[str]:
    raw = observation.raw if isinstance(observation.raw, dict) else {}
    value = raw.get(key)
    return str(value) if value else None


def _period_type(observation: Observation) -> str:
    """
    The declared period type of an observation.

    A source that does not publish its window still declares what kind of
    quantity it is. A vendor's trailing revenue is a flow over twelve months
    even though the window is not disclosed, so the declaration is consulted
    first and the shape is only a fallback. Inferring "instant" from a missing
    period_start would read a flow as a stock and refuse the comparison for the
    wrong reason.
    """
    declared = _declared(observation, "period_type")
    if declared:
        return declared
    if observation.period_start is None:
        return "instant"
    return "duration"


def _anchor(observation: Observation) -> Optional[str]:
    return observation.period_end or observation.as_of


def _days_between(left: str, right: str) -> Optional[int]:
    left_date = parse_iso_date(left)
    right_date = parse_iso_date(right)
    if left_date is None or right_date is None:
        return None
    return abs((left_date - right_date).days)


def _basis(observation: Observation) -> str:
    """The measurement basis an observation claims."""
    declared = _declared(observation, "vendor_basis")
    if declared:
        return declared
    raw = observation.raw if isinstance(observation.raw, dict) else {}
    if raw.get("derivation"):
        return "TRAILING_AGGREGATE"
    return "AS_OF"


def _record(
    status: ValidationStatus,
    metric: str,
    basis: Dict[str, Any],
    reasons: Sequence[str],
    explanation: str,
    references: Sequence[str],
    value_snapshot: Any = None,
    checked_at: str = "",
) -> ValidationRecord:
    return ValidationRecord(
        status=status,
        reasons=tuple(reasons),
        checked_at=checked_at,
        comparison_basis=basis,
        tolerance=(
            spec_for(metric).tolerance.contract_dict()
            if spec_for(metric) is not None
            else None
        ),
        explanation=explanation,
        references=tuple(references),
        value_snapshot=value_snapshot,
    )


def _methodology_mismatch(
    metric: str,
    basis: Dict[str, Any],
    reason: str,
    references: Sequence[str],
    checked_at: str,
    value_snapshot: Any = None,
) -> CrossValidationResult:
    """
    A "these cannot be compared" verdict.

    No difference is computed and neither value is judged. A difference between
    two figures that answer different questions is arithmetic noise, and
    reporting it as a discrepancy would train a reader to ignore the real ones.
    """
    return CrossValidationResult(
        metric=metric,
        status=ValidationStatus.METHODOLOGY_MISMATCH,
        validation=_record(
            ValidationStatus.METHODOLOGY_MISMATCH,
            metric,
            basis,
            [reason],
            (
                f"{metric} was not compared because the two sources define it "
                f"differently: {reason} No numeric verdict is issued, both "
                "values are retained unchanged, and neither source is treated "
                "as authoritative."
            ),
            references,
            value_snapshot=value_snapshot,
            checked_at=checked_at,
        ),
        left_observation_id=basis.get("vendor_observation"),
        right_observation_id=basis.get("filing_observation"),
    )


def _period_mismatch(
    metric: str,
    basis: Dict[str, Any],
    reason: str,
    explanation: str,
    references: Sequence[str],
    checked_at: str,
    value_snapshot: Any,
) -> CrossValidationResult:
    return CrossValidationResult(
        metric=metric,
        status=ValidationStatus.PERIOD_MISMATCH,
        validation=_record(
            ValidationStatus.PERIOD_MISMATCH,
            metric,
            basis,
            [reason],
            explanation,
            references,
            value_snapshot=value_snapshot,
            checked_at=checked_at,
        ),
        left_observation_id=basis.get("vendor_observation"),
        right_observation_id=basis.get("filing_observation"),
    )


def _unavailable(
    metric: str,
    basis: Dict[str, Any],
    reason: str,
    explanation: str,
    references: Sequence[str],
    checked_at: str,
    value_snapshot: Any = None,
) -> CrossValidationResult:
    return CrossValidationResult(
        metric=metric,
        status=ValidationStatus.UNAVAILABLE,
        validation=_record(
            ValidationStatus.UNAVAILABLE,
            metric,
            basis,
            [reason],
            explanation,
            references,
            value_snapshot=value_snapshot,
            checked_at=checked_at,
        ),
        left_observation_id=basis.get("vendor_observation"),
        right_observation_id=basis.get("filing_observation"),
    )


def cross_validate(
    metric: str,
    vendor: Optional[Observation],
    filing: Optional[Observation],
    checked_at: str = "",
) -> CrossValidationResult:
    """
    Compare one metric across two sources and return a verdict.

    Neither observation is read for anything except the comparison, and neither
    is altered. The result carries both IDs and the full arithmetic, so a human
    can adjudicate a disagreement without re-running anything.
    """
    spec = spec_for(metric)
    vendor_id = vendor.observation_id if vendor is not None else None
    filing_id = filing.observation_id if filing is not None else None
    references = [item for item in (vendor_id, filing_id) if item]

    basis: Dict[str, Any] = {
        "metric": metric,
        "vendor_observation": vendor_id,
        "filing_observation": filing_id,
        "period_window_days": PERIOD_ALIGNMENT_WINDOW_DAYS,
        "independence": (
            spec.independence if spec is not None else INDEPENDENCE_UNVERIFIED
        ),
    }
    if spec is not None:
        basis["required_unit"] = spec.contract_unit
        basis["required_period_type"] = spec.period_type
        basis["required_measurement_basis"] = spec.measurement_basis
        if spec.known_caveats:
            basis["known_caveats"] = list(spec.known_caveats)
        if spec.independence_note:
            basis["independence_note"] = spec.independence_note

    # C1 - both sides must exist and carry a value.
    if (
        vendor is None
        or filing is None
        or not vendor.is_available
        or not filing.is_available
    ):
        missing = []
        if vendor is None or not vendor.is_available:
            missing.append("vendor")
        if filing is None or not filing.is_available:
            missing.append("filing")
        return _unavailable(
            metric,
            basis,
            "; ".join(
                f"no usable value from the {side} side" for side in missing
            ),
            (
                f"{metric} could not be cross-checked: "
                f"{' and '.join(missing)} side unavailable. Neither side is "
                "treated as the correct answer."
            ),
            references,
            checked_at,
        )

    basis["vendor_value"] = vendor.value
    basis["filing_value"] = filing.value
    basis["vendor_unit"] = vendor.unit
    basis["filing_unit"] = filing.unit
    basis["vendor_currency"] = vendor.currency
    basis["filing_currency"] = filing.currency
    basis["vendor_as_of"] = vendor.as_of
    basis["filing_period_end"] = filing.period_end
    basis["vendor_period"] = (
        f"{vendor.period_start}..{vendor.period_end}"
        if vendor.period_start
        else None
    )
    basis["filing_period"] = (
        f"{filing.period_start}..{filing.period_end}"
        if filing.period_start
        else None
    )
    basis["vendor_available_at"] = vendor.available_at
    basis["filing_available_at"] = filing.available_at
    basis["vendor_basis_declared"] = _basis_of(vendor) or None
    basis["filing_basis_declared"] = _basis_of(filing) or None

    # Basis, before unit and before arithmetic. Two figures stated on different
    # bases are not comparable at any tolerance, so no amount of agreement would
    # make them comparable.
    differences = _basis_conflict(vendor, filing)
    if differences is not None:
        return _basis_mismatch_result(
            metric,
            basis,
            differences,
            vendor,
            filing,
            references,
            checked_at,
        )

    # A share count that differs by a large factor, where only one side says
    # what it is counting, is not a demonstrated basis conflict. It is a
    # comparability gap: the difference is measurable, the cause is not, and
    # calling it a conflict would over-claim what the sources establish.
    ratio = _value_ratio(filing, vendor)
    if (
        metric in _SHARE_BASIS_METRICS
        and ratio is not None
        and ratio > 1 + SHARE_COUNT_CONFLICT_RATIO
        and differences is None
    ):
        return _undemonstrated_basis_result(
            metric,
            basis,
            vendor,
            filing,
            ratio,
            references,
            checked_at,
        )

    # C2 - units must agree, and match what the contract declares.
    if spec is not None and vendor.unit != spec.contract_unit:
        return _methodology_mismatch(
            metric,
            basis,
            f"the vendor reports {metric} with unit '{vendor.unit}' where the "
            f"contract requires '{spec.contract_unit}'",
            references,
            checked_at,
        )
    if vendor.unit != filing.unit:
        return _methodology_mismatch(
            metric,
            basis,
            f"unit differs: vendor '{vendor.unit}' against filing "
            f"'{filing.unit}'",
            references,
            checked_at,
        )

    # C3 - currencies must agree. An unstated currency on a monetary metric is
    # a refusal, not an assumption.
    if (vendor.currency or None) != (filing.currency or None):
        return _methodology_mismatch(
            metric,
            basis,
            f"currency differs: vendor {vendor.currency!r} against filing "
            f"{filing.currency!r}",
            references,
            checked_at,
        )
    if (
        vendor.currency is None
        and spec is not None
        and spec.contract_unit == _MONETARY
    ):
        return _methodology_mismatch(
            metric,
            basis,
            "the vendor side does not state a currency, so a monetary "
            "comparison cannot proceed",
            references,
            checked_at,
        )

    # C4 - a flow may not be compared with a stock.
    vendor_type = _period_type(vendor)
    filing_type = _period_type(filing)
    basis["vendor_period_type"] = vendor_type
    basis["filing_period_type"] = filing_type
    if vendor_type != filing_type:
        return _methodology_mismatch(
            metric,
            basis,
            f"period type differs: vendor {vendor_type} against filing "
            f"{filing_type}. A flow over a period and a stock at an instant "
            "are different quantities.",
            references,
            checked_at,
        )

    # C6 - both sides must claim the same measurement basis. This is the check
    # that stops a trailing aggregate being compared with a single quarter.
    basis["vendor_basis"] = _basis(vendor)
    basis["filing_basis"] = _basis(filing)
    filing_is_ttm = (
        isinstance(filing.raw, dict) and bool(filing.raw.get("derivation"))
    )
    if spec is not None and spec.measurement_basis == "TTM":
        if not filing_is_ttm:
            return _methodology_mismatch(
                metric,
                basis,
                "the filing side is a single reported period, not a "
                "trailing-twelve-month aggregate, so it does not answer the "
                "same question as the vendor's trailing figure",
                references,
                checked_at,
            )
        if basis["vendor_basis"] != "TRAILING_AGGREGATE":
            return _methodology_mismatch(
                metric,
                basis,
                "the vendor side does not present as a trailing figure; it "
                f"declares {basis['vendor_basis']!r} instead",
                references,
                checked_at,
            )

    # A composed total is recorded in the basis whether or not it gates the
    # verdict. It is captured here, before the definition checks, so the reader
    # always learns how the filing-side figure was built even when the
    # comparison is refused for a stronger reason.
    # Canonicalised: the sealed 2.2.3 archive stores this metric under the
    # pre-2.33 name, and the branch must still recognise those rows.
    if canonical_metric_id(metric) == METRIC_LONG_TERM_DEBT:
        raw = filing.raw if isinstance(filing.raw, dict) else {}
        composition = raw.get("composition") or {}
        if composition:
            basis["filing_composition"] = composition.get("concepts")

    # Declared-definition divergence, checked before any arithmetic.
    if metric in DEFINITION_DIVERGENT_METRICS:
        return _methodology_mismatch(
            metric,
            basis,
            (
                f"the two sources measure different quantities for {metric}: "
                + "; ".join(spec.known_caveats if spec else ())
            ),
            references,
            checked_at,
            value_snapshot=(vendor.value, filing.value),
        )

    if spec is not None and not spec.yahoo_comparable:
        return _unavailable(
            metric,
            basis,
            f"{metric} has no vendor counterpart",
            (
                f"{metric} is reported by the filing source only. "
                + "; ".join(spec.known_caveats)
            ),
            references,
            checked_at,
            value_snapshot=(vendor.value, filing.value),
        )

    # C5 - period alignment, on the filing side's declared period when it has
    # one and on the as-of anchors otherwise.
    vendor_anchor = _anchor(vendor)
    filing_anchor = _anchor(filing)
    basis["period_basis"] = (
        "AS_OF_ONLY" if vendor.period_start is None else "DECLARED_PERIOD"
    )
    if vendor_anchor is None or filing_anchor is None:
        # A side with no date cannot be shown to refer to the same moment. That
        # is worth reporting even when the two values are identical, because
        # the reader otherwise has no way to tell an aligned agreement from an
        # unaligned coincidence.
        identical = float(vendor.value) == float(filing.value)
        return _period_mismatch(
            metric,
            basis,
            "one side states no period end and no as-of date, so the two "
            "figures cannot be attributed to the same moment",
            (
                f"{metric} could not be period-aligned: the vendor publishes "
                f"{vendor.value} with no date, while the filing source reports "
                f"{filing.value} as of {filing_anchor or 'no date'}. "
                + (
                    "The two values are identical, which is consistent with "
                    "the same underlying figure, but an undated value cannot "
                    "be confirmed to be contemporaneous, so the agreement is "
                    "reported and not validated."
                    if identical
                    else "The values differ as well as the dates, so no "
                    "agreement is claimed."
                )
            ),
            references,
            checked_at,
            (vendor.value, filing.value),
        )

    offset = _days_between(vendor_anchor, filing_anchor)
    basis["period_offset_days"] = offset
    if offset is None or offset > PERIOD_ALIGNMENT_WINDOW_DAYS:
        return _period_mismatch(
            metric,
            basis,
            f"period anchors differ by {offset} days, beyond the "
            f"{PERIOD_ALIGNMENT_WINDOW_DAYS}-day alignment window",
            (
                f"{metric} anchors are {offset} days apart (vendor as_of "
                f"{vendor_anchor}, filing period_end {filing_anchor}), outside "
                f"the {PERIOD_ALIGNMENT_WINDOW_DAYS}-day window. The two figures "
                "describe different windows, so no difference is computed and "
                "neither is judged."
            ),
            references,
            checked_at,
            (vendor.value, filing.value),
        )

    # Both sides are aligned, comparable, and fully described. Arithmetic.
    difference = float(vendor.value) - float(filing.value)
    scale = max(abs(float(vendor.value)), abs(float(filing.value)))
    relative = abs(difference) / scale if scale else 0.0
    basis["difference"] = difference
    basis["relative_difference"] = relative

    tolerance = spec.tolerance if spec is not None else None
    agrees = tolerance.allows(float(vendor.value), float(filing.value))
    independence_note = (
        f" {spec.independence_note}" if spec and spec.independence_note else ""
    )
    allowed = (
        tolerance.allowed(float(vendor.value), float(filing.value))
        if tolerance is not None
        else 0.0
    )
    tolerance_text = (
        f"{tolerance.relative * 100:.2f}% relative and "
        f"{tolerance.absolute:.10g} absolute"
        if tolerance is not None
        else "none"
    )

    if agrees:
        status = ValidationStatus.CONSISTENT
        explanation = (
            f"{metric} agrees across the two sources. The vendor reports "
            f"{vendor.value} and the filing source {filing.value}, a "
            f"difference of {relative * 100:.4f}%, within the declared "
            f"tolerance of {tolerance_text} (effective {allowed:.10g}). Both "
            f"values are retained unchanged.{independence_note}"
        )
    else:
        status = ValidationStatus.DISCREPANT
        explanation = (
            f"{metric} differs between the two sources. The vendor reports "
            f"{vendor.value} and the filing source {filing.value}, a "
            f"difference of {relative * 100:.4f}%, outside the declared "
            f"tolerance of {tolerance_text} (effective {allowed:.10g}). Both "
            "values are retained unchanged and neither source is preferred; a "
            "difference is not evidence that either is wrong."
            f"{independence_note}"
        )

    return CrossValidationResult(
        metric=metric,
        status=status,
        validation=_record(
            status,
            metric,
            basis,
            [
                "both sides are aligned on period, unit, currency, basis, and "
                "construction"
            ],
            explanation,
            references,
            value_snapshot=(vendor.value, filing.value),
            checked_at=checked_at,
        ),
        left_observation_id=vendor_id,
        right_observation_id=filing_id,
    )


def _select(
    observations: Sequence[Observation],
    anchor: Optional[str] = None,
) -> Optional[Observation]:
    """
    The observation a comparison should use on one side.

    When `anchor` is given, the trailing view closest to it wins. That is the
    point of a comparison: it aligns two accounts of the same window, so the
    filing side must be able to offer a window that ends when the vendor's
    figure ends, not only the newest one it happens to have. A vendor may be
    quoting a trailing figure that predates the filer's most recent annual
    report, and forcing the newest filing number against it would manufacture
    a period mismatch.

    Without an anchor, the trailing view wins if there is one, and otherwise
    the most recent observation: comparing against the oldest would be
    comparing against a period the reader did not ask about.
    """
    available = [
        observation for observation in observations if observation.is_available
    ]
    if not available:
        return None

    trailing = [
        observation
        for observation in available
        if isinstance(observation.raw, dict)
        and observation.raw.get("derivation")
    ]
    if anchor is not None and trailing:
        return min(
            trailing,
            key=lambda observation: _anchor_distance(observation, anchor),
        )
    if trailing:
        return max(trailing, key=lambda observation: observation.period_end or "")
    return max(
        available,
        key=lambda observation: (
            observation.period_end
            or observation.as_of
            or observation.available_at
            or ""
        ),
    )


def _anchor_distance(observation: Observation, anchor: str) -> int:
    observed = observation.period_end or observation.as_of
    days = _days_between(observed, anchor) if observed else None
    return days if days is not None else 10**6


def cross_validate_metric(
    metric: str,
    vendor_observations: Sequence[Observation],
    filing_observations: Sequence[Observation],
    checked_at: str = "",
) -> CrossValidationResult:
    """
    Cross-validate a metric from two observation collections.

    The filing side is aligned to the vendor's as-of date, so a trailing window
    is chosen to cover the same period rather than simply the newest one. When
    no such window exists the verdict is METHODOLOGY_MISMATCH or UNAVAILABLE
    rather than a false numeric agreement.
    """
    vendor = _select(vendor_observations)
    anchor = (vendor.as_of if vendor is not None else None) or None
    filing = _select(filing_observations, anchor=anchor)
    return cross_validate(
        metric,
        vendor,
        filing,
        checked_at=checked_at,
    )


def cross_validate_all(
    vendor_observations: Sequence[Observation],
    filing_observations: Sequence[Observation],
    metrics: Sequence[str] = COMPARABLE_METRICS,
    checked_at: str = "",
) -> Dict[str, CrossValidationResult]:
    """
    Cross-validate every requested metric, in the contract's metric order.

    A metric with nothing on either side is still reported, as UNAVAILABLE, so
    the output always accounts for all seven.
    """

    def by_metric(
        observations: Sequence[Observation],
    ) -> Dict[str, List[Observation]]:
        grouped: Dict[str, List[Observation]] = {}
        for observation in observations:
            if not is_comparable_observation(observation):
                continue
            grouped.setdefault(observation.metric, []).append(observation)
        return grouped

    vendor_index = by_metric(vendor_observations)
    filing_index = by_metric(filing_observations)

    results: Dict[str, CrossValidationResult] = {}
    for metric in metrics:
        results[metric] = cross_validate_metric(
            metric,
            vendor_index.get(metric, ()),
            filing_index.get(metric, ()),
            checked_at=checked_at,
        )
    return results
