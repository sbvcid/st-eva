"""
Production point-in-time historical P/FCF pipeline.

Builds a historical price-to-free-cash-flow reference distribution from filed
SEC cash-flow statements, the canonical daily price series, and cover-page
shares outstanding -- without the vendor P/FCF band, which lacks the market
cap and free cash flow history it would need.

Methodology (historical-pfcf/1.0):

  M-1:  Free cash flow per fiscal quarter = operating cash flow minus capital
        expenditure for that same discrete quarter. The SEC tags cash-flow
        payments and receipts as positive magnitudes, so capital expenditure
        is subtracted, never added.
  M-2:  10-Q cash-flow statements are cumulative year-to-date durations.
        Discrete quarters are deterministic differences of directly stated
        cumulative spans that share one fiscal-year start: Q1 from the stated
        quarter-length fact, Q2 = 6M - Q1, Q3 = 9M - 6M, Q4 = FY - 9M. A
        cumulative duration is never summed as if it were a single quarter.
  M-3:  A derived discrete quarter is knowable only when both constituent
        spans are knowable, and the value in force at an evaluation date is
        the latest usable version of each constituent span (R-PIT-SUPERSEDE).
        A filing's accounting period end is not its publication date: no fact
        is used before its filing's usable date under the 16:00 ET cutoff
        rule, identical to the historical P/E pipeline.
  M-4:  A TTM FCF window is four consecutive fiscal quarters and contains a
        Q4. The window anchors on the greatest fiscal-quarter position with
        knowable evidence and never rolls back; an incomplete window is
        refused, never backfilled, and annual facts never substitute for
        missing quarters.
  M-5:  P/FCF = (as-traded close on the evaluation date x latest knowable
        cover-page shares outstanding) / TTM FCF. Price, shares and cash
        flows are all USD as filed; the shares outstanding fact is the actual
        share count as of its stated cover date, never split-adjusted, which
        pairs with the as-traded close restored for the same share basis. A
        non-positive TTM FCF produces no multiple.
  M-6:  The evaluation dates are the periodic filing usable dates (10-Q,
        10-K, 8-K Item 2.02), the same cadence as the production historical
        P/E distribution -- not a continuous daily trading history.
  M-7:  The reference gate is the same >= 20 qualifying observations rule as
        the historical P/E distribution. A thinner sample stays descriptive.
  M-8:  Every observation carries the accessions, spans, usable dates, share
        fact and price evidence it was computed from, so each published
        multiple can be independently recomputed.

Known data limitation that the pipeline states rather than hides: the
operating-cash-flow concept does not carry AAPL's FY2016 Q1 span, so the
first evaluation date cannot anchor a complete FY2016 window and is reported
as refused. FY2016/FY2017 operating cash flows entered the concept only
through later comparatives, so those windows' knowability is conservative
(later than contemporaneous public knowledge, never earlier).
"""
from __future__ import annotations

import datetime
import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from fiscal_calendar import FiscalCalendar, build_fiscal_calendar
from historical_pe import (
    MIN_OBSERVATIONS_FOR_REFERENCE,
    QUARTER_MAX_DAYS,
    QUARTER_MIN_DAYS,
    STATUS_AVAILABLE,
    STATUS_INSUFFICIENT_OBSERVATIONS,
    STATUS_UNAVAILABLE,
    STATUS_USABLE_FOR_REFERENCE,
    UTC,
    canonical_json_hash,
    compute_distribution_percentiles,
    restore_as_traded_close,
    resolve_usable_date,
)

METHODOLOGY = "historical-pfcf/1.0"
LOGIC_VERSION = "historical-pfcf/1.1.0"
FORMULA_VERSION = "historical-pfcf/1.0"

# Metric identifier emitted by the historical P/FCF engine.
METRIC_TTM_MARKET_CAP_TO_FCF = "TTM_MARKET_CAP_TO_FCF"

# Reason codes. The closed set mirrors the historical P/E vocabulary where the
# conditions coincide, and names the P/FCF-specific refusals explicitly.
REASON_MISSING_PRICE = "REASON_MISSING_PRICE"
REASON_MISSING_SHARES = "REASON_MISSING_SHARES"
REASON_INSUFFICIENT_QUARTERS = "REASON_INSUFFICIENT_QUARTERS"
REASON_NON_POSITIVE_FCF = "REASON_NON_POSITIVE_FCF"
REASON_INSUFFICIENT_OBSERVATIONS = "REASON_INSUFFICIENT_OBSERVATIONS"

CLOSED_REASON_CODES = frozenset(
    {
        REASON_MISSING_PRICE,
        REASON_MISSING_SHARES,
        REASON_INSUFFICIENT_QUARTERS,
        REASON_NON_POSITIVE_FCF,
        REASON_INSUFFICIENT_OBSERVATIONS,
    }
)

# The SEC concept tags the pipeline reads, recorded so provenance names the
# exact tags rather than describing them in prose.
OCF_CONCEPT_TAG = "NetCashProvidedByUsedInOperatingActivities"
CAPEX_CONCEPT_TAG = "PaymentsToAcquirePropertyPlantAndEquipment"
SHARES_CONCEPT_TAG = "EntityCommonStockSharesOutstanding"
OCF_CONCEPT_SOURCE_URL = (
    "https://data.sec.gov/api/xbrl/companyconcept/{issuer_id}/us-gaap/"
    + OCF_CONCEPT_TAG
    + ".json"
)
CAPEX_CONCEPT_SOURCE_URL = (
    "https://data.sec.gov/api/xbrl/companyconcept/{issuer_id}/us-gaap/"
    + CAPEX_CONCEPT_TAG
    + ".json"
)
SHARES_CONCEPT_SOURCE_URL = (
    "https://data.sec.gov/api/xbrl/companyconcept/{issuer_id}/dei/"
    + SHARES_CONCEPT_TAG
    + ".json"
)


# ---------------------------------------------------------------------------
# Evidence schemas
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DurationSpanEvidence:
    """
    One version of one cumulative duration, as one filing stated it.

    `start`/`end` are the accounting period the fact covers; `usable_date` is
    when the fact became knowable under the 16:00 ET cutoff rule. A value the
    SEC serves for the same span from several filings keeps every version:
    which one is in force at an evaluation date is a point-in-time decision
    the pipeline makes per date, never a load-time deduplication.

    The same shape serves a cash-flow statement and an income statement: the
    rule that makes a discrete quarter out of a cumulative duration is the
    rule, not the statement it came from.
    """

    evidence_id: str
    issuer_id: str
    concept_tag: str
    role: str  # "operating_cash_flow" | "capital_expenditure" | "revenue" | ...
    start: str
    end: str
    duration_days: int
    value: float  # positive magnitude, USD
    accession: str
    form: str
    acceptance_datetime: str
    usable_date: str
    usable_date_rule: str
    filed_date: str
    source_url: str
    content_sha256: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ShareCountEvidence:
    """One cover-page shares outstanding fact, with its own knowability."""

    evidence_id: str
    issuer_id: str
    shares: float  # actual count as of the stated date, never split-adjusted
    as_of_date: str  # the cover date the count is stated as of
    accession: str
    form: str
    usable_date: str
    usable_date_rule: str
    source_url: str
    content_sha256: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HistoricalPfcfObservation:
    """One dated historical P/FCF evaluation with full recomputation inputs."""

    observation_id: str
    issuer_id: str
    instrument_id: str
    evaluation_date: str
    status: str
    reason_code: Optional[str] = None
    reason_detail: Optional[str] = None
    value: Optional[float] = None  # the P/FCF multiple
    price: Optional[float] = None
    price_currency: str = "USD"
    price_accounting_basis: str = "as_traded"
    shares_outstanding: Optional[float] = None
    shares_as_of_date: Optional[str] = None
    shares_accession: Optional[str] = None
    market_cap: Optional[float] = None
    ttm_free_cash_flow: Optional[float] = None
    ttm_free_cash_flow_currency: str = "USD"
    ttm_window: Optional[Dict[str, Any]] = None
    formula: Dict[str, Any] = field(default_factory=dict)
    metric_id: str = METRIC_TTM_MARKET_CAP_TO_FCF
    methodology: str = METHODOLOGY
    logic_version: str = LOGIC_VERSION
    input_set_id: str = ""
    content_hash: str = ""
    role: Optional[str] = None

    def __post_init__(self) -> None:
        if self.reason_code is not None and self.reason_code not in CLOSED_REASON_CODES:
            raise ValueError(
                f"Invariant M-11 violation: reason_code {self.reason_code!r} not in closed set"
            )
        if not self.content_hash:
            self.content_hash = self.compute_content_hash()

    def compute_content_hash(self) -> str:
        data = asdict(self)
        data.pop("content_hash", None)
        return canonical_json_hash(data)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HistoricalPfcfDistribution:
    """Distribution statistics and the reference eligibility gate."""

    metric_id: str = METRIC_TTM_MARKET_CAP_TO_FCF
    status: str = STATUS_UNAVAILABLE
    usable_for_reference: bool = False
    sample_count: int = 0
    total_evaluations: int = 0
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    min_observations_required: int = MIN_OBSERVATIONS_FOR_REFERENCE
    mean: Optional[float] = None
    std: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    percentiles: Dict[str, Optional[float]] = field(default_factory=dict)
    reason_code: Optional[str] = None
    reason_detail: Optional[str] = None
    excluded_observations: List[Dict[str, Any]] = field(default_factory=list)
    observations: List[Dict[str, Any]] = field(default_factory=list)
    sampling_cadence: str = "PERIODIC_FILING_USABLE_DATES"
    evaluation_schedule_description: str = (
        "Evaluated on periodic SEC filing and earnings release usable dates (10-Q, 10-K, "
        "8-K Item 2.02); not a continuous daily trading history."
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HistoricalPfcfResult:
    """Overall package returned by the historical P/FCF pipeline."""

    issuer_id: str
    instrument_id: str
    input_set_id: str
    distribution: HistoricalPfcfDistribution
    observations: List[HistoricalPfcfObservation]
    current_snapshot: Optional[HistoricalPfcfObservation] = None
    content_hash: str = ""
    summary_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issuer_id": self.issuer_id,
            "instrument_id": self.instrument_id,
            "input_set_id": self.input_set_id,
            "content_hash": self.content_hash,
            "distribution": self.distribution.to_dict(),
            "observations": [obs.to_dict() for obs in self.observations],
            "current_snapshot": self.current_snapshot.to_dict() if self.current_snapshot else None,
            "summary_notes": list(self.summary_notes),
        }


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def _parse_date(value: Any) -> Optional[datetime.date]:
    if not value:
        return None
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def in_force_version(
    versions: Sequence[DurationSpanEvidence], day: str
) -> Optional[DurationSpanEvidence]:
    """
    The version of one span that is in force at `day` (R-PIT-SUPERSEDE).

    Versions are ordered by usable date; the latest one knowable at the
    evaluation date wins. A restatement therefore takes over on its own
    usable date and never earlier, and the value visible before the first
    version is absence, not zero.
    """
    in_force = None
    for version in versions:
        if version.usable_date <= day:
            in_force = version
        else:
            break
    return in_force


def discrete_quarters_for_role(
    *,
    spans_in_force: Mapping[Tuple[str, str], DurationSpanEvidence],
    role: str,
) -> Dict[datetime.date, Dict[str, Any]]:
    """
    Discrete fiscal quarters of one concept, as knowable at the evaluation date.

    A span end is a quarter boundary when the difference to the immediately
    preceding cumulative span with the same fiscal-year start is itself a
    quarter-length duration (M-2). The quarter-length case is a directly
    stated Q1. Both constituents must be in force at the evaluation date, so
    a derived quarter can never be knowable before its own inputs (M-3).

    The rule is the rule whichever statement the duration came from, so it
    lives here rather than inside the cash-flow reconstruction: an income
    statement's cumulative spans are differenced by the same rule.
    """
    own = {
        (span[1], span[2]): version
        for span, version in spans_in_force.items()
        if version.role == role
    }
    quarters: Dict[datetime.date, Dict[str, Any]] = {}
    for (start, end), version in own.items():
        start_d, end_d = _parse_date(start), _parse_date(end)
        if start_d is None or end_d is None:
            continue
        span_days = version.duration_days
        if QUARTER_MIN_DAYS <= span_days <= QUARTER_MAX_DAYS:
            quarters[end_d] = {
                "value": version.value,
                "knowable_from": version.usable_date,
                "derivation": "directly stated quarter-length cumulative fact",
                "inputs": [version.to_dict()],
            }
            continue
        predecessors = [
            (s2, e2)
            for (s2, e2) in own
            if s2 == start and e2 < end
        ]
        if not predecessors:
            continue
        prior_span = max(predecessors, key=lambda se: _parse_date(se[1]))
        prior = own[prior_span]
        quarter_days = (
            _parse_date(end) - _parse_date(prior_span[1])
        ).days
        if not (QUARTER_MIN_DAYS <= quarter_days <= QUARTER_MAX_DAYS):
            # The span end is not a quarter boundary this derivation can
            # use; the value stays absent rather than being approximated.
            continue
        quarters[end_d] = {
            "value": version.value - prior.value,
            "knowable_from": max(version.usable_date, prior.usable_date),
            "derivation": (
                f"cumulative difference: {end} minus {prior_span[1]} "
                f"({quarter_days} days)"
            ),
            "inputs": [version.to_dict(), prior.to_dict()],
        }
    return quarters


def derive_discrete_quarters_at(
    *,
    spans_in_force: Mapping[Tuple[str, str], DurationSpanEvidence],
    ocf_role: str,
    capex_role: str,
    fiscal_calendar: "FiscalCalendar",
    evaluation_date: str,
    issuer_id: str,
) -> Dict[datetime.date, Dict[str, Any]]:
    """
    Discrete fiscal quarters of one concept's cash flows, as knowable at the
    evaluation date.

    A span end is a quarter boundary when the difference to the immediately
    preceding cumulative span with the same fiscal-year start is itself a
    quarter-length duration (M-2). The quarter-length case is a directly
    stated Q1. Both constituents must be in force at the evaluation date, so
    a derived quarter can never be knowable before its own inputs (M-3).

    Each discrete quarter's fiscal year and quarter come from the issuer's
    own declarations (the fiscal calendar built from the filings' XBRL focus
    fields and annual spans), never from a month grid: 52/53-week filers'
    quarter ends drift across month boundaries. A span end with no issuer
    declaration is left out, never assigned to a neighbouring quarter.
    """
    ocf_quarters = discrete_quarters_for_role(
        spans_in_force=spans_in_force, role=ocf_role
    )
    capex_quarters = discrete_quarters_for_role(
        spans_in_force=spans_in_force, role=capex_role
    )

    combined: Dict[datetime.date, Dict[str, Any]] = {}
    for end_d in sorted(set(ocf_quarters) | set(capex_quarters)):
        ocf = ocf_quarters.get(end_d)
        capex = capex_quarters.get(end_d)
        if ocf is None or capex is None:
            # One concept states the quarter and the other does not: the
            # quarter's free cash flow is absent, not zero (M-1).
            continue
        identity = fiscal_calendar.identity_for(end_d.isoformat())
        if identity is None:
            # No issuer declaration identifies this period's fiscal year and
            # quarter; the quarter is left out rather than mislabelled.
            continue
        combined[end_d] = {
            "fiscal_year": identity.fiscal_year,
            "fiscal_quarter": identity.fiscal_quarter,
            "identity_source": identity.identity_source,
            "period_end": end_d.isoformat(),
            "operating_cash_flow": ocf["value"],
            "capital_expenditure": capex["value"],
            "free_cash_flow": ocf["value"] - capex["value"],
            "knowable_from": max(ocf["knowable_from"], capex["knowable_from"]),
            "currency": "USD",
            "formula": "operating cash flow - capital expenditure",
            "operating_cash_flow_derivation": ocf["derivation"],
            "capital_expenditure_derivation": capex["derivation"],
            "operating_cash_flow_inputs": ocf["inputs"],
            "capital_expenditure_inputs": capex["inputs"],
        }
    return combined


def ttm_window_at(
    *,
    quarters: Mapping[datetime.date, Dict[str, Any]],
    day: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
    """
    The four-quarter fiscal window knowable at `day` (M-4).

    Anchors on the greatest fiscal-quarter position with knowable evidence
    and walks back four consecutive positions. The anchor's fiscal year and
    quarter are the issuer-declared identity carried by the quarter itself;
    the window must contain a Q4 by construction of the anchor walk; a
    missing position refuses the window. There is no rollback to an earlier
    anchor and no synthesis.

    The walk is over fiscal positions, not over the quarters' own contents,
    so it serves a window of free cash flow and a window of revenue alike.
    """
    known = {
        end: quarter for end, quarter in quarters.items() if quarter["knowable_from"] <= day
    }
    if not known:
        return None, REASON_INSUFFICIENT_QUARTERS, (
            f"No discrete quarter free cash flow is knowable at evaluation date {day}."
        )
    anchor = max(known)
    anchor_year = known[anchor]["fiscal_year"]
    anchor_number = known[anchor]["fiscal_quarter"]

    positions: List[Tuple[int, int]] = []
    year, number = anchor_year, anchor_number
    for _ in range(4):
        positions.append((year, number))
        number -= 1
        if number == 0:
            number, year = 4, year - 1
    positions.reverse()

    window_quarters: List[Dict[str, Any]] = []
    missing: List[Dict[str, Any]] = []
    for pos_year, pos_number in positions:
        matches = [
            end
            for end in known
            if known[end]["fiscal_year"] == pos_year
            and known[end]["fiscal_quarter"] == pos_number
        ]
        if matches:
            window_quarters.append(known[max(matches)])
        else:
            missing.append({"fiscal_year": pos_year, "fiscal_quarter": pos_number})

    if missing:
        return None, REASON_INSUFFICIENT_QUARTERS, (
            f"The four-quarter fiscal window ending at FY{anchor_year} Q{anchor_number} "
            f"is missing positions: {missing}."
        )

    return {
        "anchor": {
            "fiscal_year": anchor_year,
            "fiscal_quarter": anchor_number,
            "period_end": anchor.isoformat(),
        },
        "positions": [
            {"fiscal_year": year_, "fiscal_quarter": number_}
            for year_, number_ in positions
        ],
        "quarters": window_quarters,
    }, None, None


def ttm_fcf_window_at(
    *,
    quarters: Mapping[datetime.date, Dict[str, Any]],
    day: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
    """
    The TTM FCF window knowable at `day` (M-4).

    Anchors on the greatest fiscal-quarter position with knowable evidence
    and walks back four consecutive positions. The anchor's fiscal year and
    quarter are the issuer-declared identity carried by the quarter itself;
    the window must contain a Q4 by construction of the anchor walk; a
    missing position refuses the window. There is no rollback to an earlier
    anchor and no synthesis.
    """
    window, reason, detail = ttm_window_at(quarters=quarters, day=day)
    if window is None:
        return None, reason, detail
    total = sum(quarter["free_cash_flow"] for quarter in window["quarters"])
    return {
        **window,
        "total_free_cash_flow": total,
    }, None, None


def build_historical_pfcf(
    *,
    issuer_id: str,
    instrument_id: str,
    cash_flow_spans: Sequence[DurationSpanEvidence],
    share_counts: Sequence[ShareCountEvidence],
    prices: Mapping[str, Dict[str, Any]],
    fiscal_calendar: "FiscalCalendar",
    evaluation_dates: Sequence[str],
    current_price_day: Optional[str] = None,
    min_observations: int = MIN_OBSERVATIONS_FOR_REFERENCE,
    input_set_id: str = "",
) -> HistoricalPfcfResult:
    """
    Execute the historical P/FCF resolver over the given evidence.

    `prices` maps each trading day to {"close", "currency"} plus optional
    accounting-basis metadata; `evaluation_dates` are the usable dates the
    distribution is sampled on (M-6). Every refusal carries a closed-set
    reason code and a detail naming what was missing (M-8). Fiscal positions
    come from `fiscal_calendar`, the issuer-declared identity model; the
    month grid cannot represent 52/53-week fiscal calendars.
    """
    # Span identity is (role, start, end): operating cash flow and capital
    # expenditure state the same cumulative periods, and a version of one
    # concept must never stand in for the other.
    spans_by_key: Dict[Tuple[str, str, str], List[DurationSpanEvidence]] = {}
    for span in cash_flow_spans:
        spans_by_key.setdefault((span.role, span.start, span.end), []).append(span)
    for versions in spans_by_key.values():
        versions.sort(
            key=lambda item: (item.usable_date, item.acceptance_datetime, item.accession)
        )

    share_versions = sorted(
        share_counts, key=lambda item: (item.usable_date, item.as_of_date, item.accession)
    )

    def shares_at(day: str) -> Tuple[Optional[ShareCountEvidence], Optional[str]]:
        in_force = None
        for version in share_versions:
            if version.usable_date <= day:
                in_force = version
            else:
                break
        if in_force is None:
            return None, (
                f"No cover-page shares outstanding fact is knowable at evaluation date {day}."
            )
        return in_force, None

    observations: List[HistoricalPfcfObservation] = []

    def evaluate(day: str, role: Optional[str]) -> HistoricalPfcfObservation:
        spans_in_force = {
            key: in_force_version(versions, day)
            for key, versions in spans_by_key.items()
        }
        spans_in_force = {
            key: version for key, version in spans_in_force.items() if version is not None
        }
        quarters = derive_discrete_quarters_at(
            spans_in_force=spans_in_force,
            ocf_role="operating_cash_flow",
            capex_role="capital_expenditure",
            fiscal_calendar=fiscal_calendar,
            evaluation_date=day,
            issuer_id=issuer_id,
        )
        window, window_reason, window_detail = ttm_fcf_window_at(
            quarters=quarters, day=day
        )

        price = prices.get(day)
        share, share_detail = shares_at(day)

        status = STATUS_UNAVAILABLE
        reason_code: Optional[str] = window_reason
        reason_detail: Optional[str] = window_detail
        value: Optional[float] = None
        market_cap: Optional[float] = None
        ttm_fcf: Optional[float] = window.get("total_free_cash_flow") if window else None

        if window_reason is None and price is None:
            reason_code = REASON_MISSING_PRICE
            reason_detail = f"No historical price evidence is observed for trading day {day}."
        elif window_reason is None and share is None:
            reason_code = REASON_MISSING_SHARES
            reason_detail = share_detail
        elif window_reason is None and ttm_fcf is not None and ttm_fcf <= 0:
            reason_code = REASON_NON_POSITIVE_FCF
            reason_detail = (
                f"TTM free cash flow is non-positive ({ttm_fcf:,.0f} USD); a negative or "
                "zero denominator produces no P/FCF multiple."
            )
        elif window_reason is None:
            market_cap = price["close"] * share.shares
            value = market_cap / ttm_fcf
            status = STATUS_AVAILABLE
            reason_code = None
            reason_detail = None

        window_payload = None
        if window is not None:
            window_payload = {
                "anchor": window["anchor"],
                "positions": window["positions"],
                "total_free_cash_flow": window["total_free_cash_flow"],
                "quarters": [
                    {
                        "period_end": quarter["period_end"],
                        "fiscal_year": quarter["fiscal_year"],
                        "fiscal_quarter": quarter["fiscal_quarter"],
                        "identity_source": quarter.get("identity_source"),
                        "operating_cash_flow": quarter["operating_cash_flow"],
                        "capital_expenditure": quarter["capital_expenditure"],
                        "free_cash_flow": quarter["free_cash_flow"],
                        "currency": quarter["currency"],
                        "formula": quarter["formula"],
                        "knowable_from": quarter["knowable_from"],
                        "operating_cash_flow_derivation": quarter[
                            "operating_cash_flow_derivation"
                        ],
                        "capital_expenditure_derivation": quarter[
                            "capital_expenditure_derivation"
                        ],
                        "operating_cash_flow_inputs": [
                            item["accession"] for item in quarter["operating_cash_flow_inputs"]
                        ],
                        "capital_expenditure_inputs": [
                            item["accession"] for item in quarter["capital_expenditure_inputs"]
                        ],
                    }
                    for quarter in window["quarters"]
                ],
            }

        observation = HistoricalPfcfObservation(
            observation_id=f"histpfcf-{METRIC_TTM_MARKET_CAP_TO_FCF}-{instrument_id}-{day}",
            issuer_id=issuer_id,
            instrument_id=instrument_id,
            evaluation_date=day,
            status=status,
            reason_code=reason_code,
            reason_detail=reason_detail,
            value=round(value, 6) if value is not None else None,
            price=price["close"] if price else None,
            price_currency=price["currency"] if price else "USD",
            price_accounting_basis=price.get("accounting_basis", "as_traded") if price else "as_traded",
            shares_outstanding=share.shares if share else None,
            shares_as_of_date=share.as_of_date if share else None,
            shares_accession=share.accession if share else None,
            market_cap=round(market_cap, 2) if market_cap is not None else None,
            ttm_free_cash_flow=ttm_fcf,
            ttm_window=window_payload,
            formula={
                "expression": "(close x shares outstanding) / TTM free cash flow",
                "formula_version": FORMULA_VERSION,
                "numerator": "as-traded close on the evaluation date times the latest "
                "knowable cover-page shares outstanding",
                "denominator": "sum of four consecutive fiscal quarters' (operating cash "
                "flow - capital expenditure), each knowable at the evaluation date",
                "market_cap_currency": price["currency"] if price else "USD",
                "cash_flow_currency": "USD",
            },
            input_set_id=input_set_id,
            role=role,
        )
        return observation

    for day in sorted(evaluation_dates):
        observations.append(evaluate(day, role=None))

    current_snapshot: Optional[HistoricalPfcfObservation] = None
    if current_price_day:
        current_snapshot = evaluate(current_price_day, role="current_snapshot")

    distribution = compute_historical_pfcf_distribution(
        observations, min_observations=min_observations
    )

    package_dict = {
        "issuer_id": issuer_id,
        "instrument_id": instrument_id,
        "input_set_id": input_set_id,
        "distribution": distribution.to_dict(),
        "observations": [obs.to_dict() for obs in observations],
    }
    content_hash = canonical_json_hash(package_dict)

    return HistoricalPfcfResult(
        issuer_id=issuer_id,
        instrument_id=instrument_id,
        input_set_id=input_set_id,
        distribution=distribution,
        observations=observations,
        current_snapshot=current_snapshot,
        content_hash=content_hash,
    )


def compute_historical_pfcf_distribution(
    observations: Sequence[HistoricalPfcfObservation],
    min_observations: int = MIN_OBSERVATIONS_FOR_REFERENCE,
) -> HistoricalPfcfDistribution:
    """Build the distribution and apply the same sufficiency gate as P/E (M-7)."""
    ttm_obs = [
        obs
        for obs in observations
        if obs.metric_id == METRIC_TTM_MARKET_CAP_TO_FCF and obs.role != "current_snapshot"
    ]
    valid_obs = [
        obs
        for obs in ttm_obs
        if obs.status == STATUS_AVAILABLE and obs.value is not None and obs.value > 0
    ]
    excluded = [
        {
            "evaluation_date": obs.evaluation_date,
            "status": obs.status,
            "reason_code": obs.reason_code,
            "reason_detail": obs.reason_detail,
        }
        for obs in ttm_obs
        if obs.status != STATUS_AVAILABLE
    ]

    sample_count = len(valid_obs)
    total_evals = len(ttm_obs)

    if sample_count == 0:
        return HistoricalPfcfDistribution(
            metric_id=METRIC_TTM_MARKET_CAP_TO_FCF,
            status=STATUS_UNAVAILABLE,
            usable_for_reference=False,
            sample_count=0,
            total_evaluations=total_evals,
            min_observations_required=min_observations,
            reason_code=REASON_INSUFFICIENT_OBSERVATIONS,
            reason_detail="Zero valid point-in-time TTM P/FCF observations could be constructed.",
            excluded_observations=excluded,
        )

    values = [obs.value for obs in valid_obs if obs.value is not None]
    period_start = min(obs.evaluation_date for obs in valid_obs)
    period_end = max(obs.evaluation_date for obs in valid_obs)

    mean_val = round(sum(values) / sample_count, 6)
    variance = (
        sum((x - mean_val) ** 2 for x in values) / (sample_count - 1)
        if sample_count > 1
        else 0.0
    )
    std_val = round(math.sqrt(variance), 6) if sample_count > 1 else 0.0
    percentiles = compute_distribution_percentiles(values)

    if sample_count >= min_observations:
        status = STATUS_USABLE_FOR_REFERENCE
        usable_for_reference = True
        reason_code = None
        reason_detail = None
    else:
        status = STATUS_INSUFFICIENT_OBSERVATIONS
        usable_for_reference = False
        reason_code = REASON_INSUFFICIENT_OBSERVATIONS
        reason_detail = (
            f"The sample holds {sample_count} valid observations, below the {min_observations} "
            f"required to establish an authoritative reference distribution. Descriptive "
            f"statistics (median {percentiles.get('median')}) are reported for review but are "
            f"ineligible as scenario exit multiples."
        )

    return HistoricalPfcfDistribution(
        metric_id=METRIC_TTM_MARKET_CAP_TO_FCF,
        status=status,
        usable_for_reference=usable_for_reference,
        sample_count=sample_count,
        total_evaluations=total_evals,
        period_start=period_start,
        period_end=period_end,
        min_observations_required=min_observations,
        mean=mean_val,
        std=std_val,
        min=round(min(values), 6),
        max=round(max(values), 6),
        percentiles=percentiles,
        reason_code=reason_code,
        reason_detail=reason_detail,
        excluded_observations=excluded,
        observations=[obs.to_dict() for obs in valid_obs],
    )


# ---------------------------------------------------------------------------
# Dataset loader
# ---------------------------------------------------------------------------

@dataclass
class HistoricalPfcfConfig:
    """Configuration for loading a historical P/FCF dataset for an issuer."""

    ticker: str
    issuer_id: str
    fye_month: int
    data_dir: Path
    # The canonical price and acceptance evidence this dataset reuses by path,
    # so the two datasets cannot drift apart.
    prices_path: Path
    acceptance_path: Path


ISSUER_CONFIGS: Dict[str, HistoricalPfcfConfig] = {
    "AAPL": HistoricalPfcfConfig(
        ticker="AAPL",
        issuer_id="CIK0000320193",
        fye_month=9,
        data_dir=Path("data/historical_pfcf/AAPL"),
        prices_path=Path("data/historical_pe/AAPL/daily_prices.json"),
        acceptance_path=Path("data/historical_pe/AAPL/filing_acceptance_evidence.json"),
    ),
    "MSFT": HistoricalPfcfConfig(
        ticker="MSFT",
        issuer_id="CIK0000789019",
        fye_month=6,
        data_dir=Path("data/historical_pfcf/MSFT"),
        prices_path=Path("data/historical_pe/MSFT/daily_prices.json"),
        acceptance_path=Path("data/historical_pe/MSFT/filing_acceptance_evidence.json"),
    ),
    "MU": HistoricalPfcfConfig(
        ticker="MU",
        issuer_id="CIK0000723125",
        fye_month=8,
        data_dir=Path("data/historical_pfcf/MU"),
        prices_path=Path("data/historical_pe/MU/daily_prices.json"),
        acceptance_path=Path("data/historical_pe/MU/filing_acceptance_evidence.json"),
    ),
}

def concept_spans_from_payload(
    *,
    payload: Mapping[str, Any],
    unit: str,
    role: str,
    concept_tag: str,
    issuer_id: str,
    filings_index: Mapping[str, Dict[str, Any]],
    content_sha256: str,
    source_url: Optional[str] = None,
) -> List[DurationSpanEvidence]:
    """
    Duration facts of one concept, each carrying its own filing's knowability.

    A fact whose accession is not in the acceptance index has no knowability
    evidence in this dataset and is skipped, never guessed. Duration facts
    outside the quarter/year calendar bounds are still kept: the discrete
    derivation decides span by span whether an end is a quarter boundary.

    `source_url` names the endpoint the payload came from. It defaults to the
    cash-flow concept URL, which is right for the cash-flow reconstruction and
    wrong for anything else, so a caller that reads a different concept says
    which one.
    """
    spans: List[DurationSpanEvidence] = []
    if source_url is None:
        source_url = (
            OCF_CONCEPT_SOURCE_URL if role == "operating_cash_flow" else CAPEX_CONCEPT_SOURCE_URL
        ).format(issuer_id=issuer_id)
    for fact in payload.get("units", {}).get(unit, []):
        start = fact.get("start")
        end = fact.get("end")
        if not start or not end:
            continue
        accession = fact.get("accn")
        filing_meta = filings_index.get(accession)
        if filing_meta is None:
            continue
        start_d, end_d = _parse_date(start), _parse_date(end)
        spans.append(
            DurationSpanEvidence(
                evidence_id=f"span-{role}-{accession}-{start}-{end}",
                issuer_id=issuer_id,
                concept_tag=concept_tag,
                role=role,
                start=start,
                end=end,
                duration_days=(end_d - start_d).days,
                value=float(fact["val"]),
                accession=accession,
                form=filing_meta["form"],
                acceptance_datetime=filing_meta["acceptance_datetime"],
                usable_date=filing_meta["usable_date"],
                usable_date_rule=filing_meta["usable_date_rule"],
                filed_date=str(fact.get("filed") or ""),
                source_url=source_url,
                content_sha256=content_sha256,
            )
        )
    return spans


def _share_counts_from_payload(
    *,
    payload: Mapping[str, Any],
    unit: str,
    issuer_id: str,
    filings_index: Mapping[str, Dict[str, Any]],
    content_sha256: str,
) -> List[ShareCountEvidence]:
    counts: List[ShareCountEvidence] = []
    for fact in payload.get("units", {}).get(unit, []):
        accession = fact.get("accn")
        filing_meta = filings_index.get(accession)
        if filing_meta is None:
            continue
        counts.append(
            ShareCountEvidence(
                evidence_id=f"shares-{accession}-{fact.get('end')}",
                issuer_id=issuer_id,
                shares=float(fact["val"]),
                as_of_date=str(fact.get("end") or ""),
                accession=accession,
                form=filing_meta["form"],
                usable_date=filing_meta["usable_date"],
                usable_date_rule=filing_meta["usable_date_rule"],
                source_url=SHARES_CONCEPT_SOURCE_URL.format(issuer_id=issuer_id),
                content_sha256=content_sha256,
            )
        )
    return counts


def load_issuer_historical_pfcf(
    config: HistoricalPfcfConfig,
    min_observations: int = MIN_OBSERVATIONS_FOR_REFERENCE,
) -> HistoricalPfcfResult:
    """
    Load a promoted historical P/FCF dataset and execute the pipeline.

    The price series and the acceptance index are the canonical historical
    P/E dataset's files, read by path: one price series serves both
    reconstructions, so a reference multiple built here is on the same
    trading-day basis as the P/E distribution it sits beside.
    """
    prices_path = config.prices_path
    acceptance_path = config.acceptance_path
    ocf_path = config.data_dir / "net_cash_operating_concept.json"
    capex_path = config.data_dir / "capex_concept.json"
    shares_path = config.data_dir / "shares_outstanding_concept.json"
    for path in (prices_path, acceptance_path, ocf_path, capex_path, shares_path):
        if not path.exists():
            raise FileNotFoundError(f"Missing required file: {path}")

    # -- prices: the canonical chart payload, restored to as-traded closes --
    price_payload = json.loads(prices_path.read_bytes().decode("utf-8"))["chart"]["result"][0]
    _meta = price_payload.get("meta", {})
    _granularity = _meta.get("dataGranularity")
    if _granularity != "1d":
        raise ValueError(
            f"Price data granularity must be '1d', got '{_granularity}'; "
            f"quarterly or monthly aggregates cannot serve as daily prices"
        )
    quote = price_payload["indicators"]["quote"][0]
    bars = {
        datetime.datetime.fromtimestamp(stamp, UTC).date().isoformat(): float(
            quote["close"][idx]
        )
        for idx, stamp in enumerate(price_payload["timestamp"])
        if quote["close"][idx] is not None
    }
    trading_days = sorted(bars.keys())
    splits = price_payload.get("events", {}).get("splits", {})

    prices_map: Dict[str, Dict[str, Any]] = {}
    for day, close in bars.items():
        restored_close, _, _ = restore_as_traded_close(close, day, splits)
        prices_map[day] = {
            "close": round(restored_close, 4),
            "currency": "USD",
            "accounting_basis": "as_traded",
        }
    current_price_day = trading_days[-1] if trading_days else None

    # -- acceptance index, identical rule to the historical P/E loader --
    acceptance_evidence = json.loads(acceptance_path.read_text(encoding="utf-8"))
    filings_index: Dict[str, Dict[str, Any]] = {}
    for row in acceptance_evidence:
        acceptance_dt = datetime.datetime.fromisoformat(
            row["acceptance_datetime_header_et"]
        )
        usable_d, usable_r = resolve_usable_date(acceptance_dt, trading_days)
        filings_index[row["accession"]] = {
            "form": row["form"],
            "acceptance_datetime": acceptance_dt.isoformat(),
            "usable_date": usable_d,
            "usable_date_rule": usable_r,
            "period_end": row["period_end"],
        }

    # -- concepts --
    ocf_sha = _sha256_of(ocf_path)
    capex_sha = _sha256_of(capex_path)
    shares_sha = _sha256_of(shares_path)
    ocf_payload = json.loads(ocf_path.read_text(encoding="utf-8"))
    capex_payload = json.loads(capex_path.read_text(encoding="utf-8"))
    shares_payload = json.loads(shares_path.read_text(encoding="utf-8"))

    # Fiscal identities from the issuer's own declarations. The cumulative
    # cash-flow spans' period ends are quarter ends (3M/6M/9M cumulative and
    # fiscal-year spans each end where a fiscal quarter ends); the primary
    # filings of those spans declare their fiscal year and quarter. The
    # month grid cannot represent 52/53-week calendars and is no longer used.
    fiscal_calendar = build_fiscal_calendar(
        [ocf_payload, capex_payload], filings_index, units=("USD",)
    )

    cash_flow_spans = concept_spans_from_payload(
        payload=ocf_payload,
        unit="USD",
        role="operating_cash_flow",
        concept_tag=OCF_CONCEPT_TAG,
        issuer_id=config.issuer_id,
        filings_index=filings_index,
        content_sha256=ocf_sha,
    ) + concept_spans_from_payload(
        payload=capex_payload,
        unit="USD",
        role="capital_expenditure",
        concept_tag=CAPEX_CONCEPT_TAG,
        issuer_id=config.issuer_id,
        filings_index=filings_index,
        content_sha256=capex_sha,
    )
    share_counts = _share_counts_from_payload(
        payload=shares_payload,
        unit="shares",
        issuer_id=config.issuer_id,
        filings_index=filings_index,
        content_sha256=shares_sha,
    )

    # Digest every result-affecting input, so input_set_id changes when any
    # of them changes -- the same rule the historical P/E loader applies.
    input_manifest = {
        "issuer_config": {
            "ticker": config.ticker,
            "issuer_id": config.issuer_id,
            "fye_month": config.fye_month,
        },
        "prices": _sha256_of(prices_path),
        "acceptances": _sha256_of(acceptance_path),
        "operating_cash_flow_concept": ocf_sha,
        "capital_expenditure_concept": capex_sha,
        "shares_outstanding_concept": shares_sha,
        "min_observations": min_observations,
    }
    input_set_id = canonical_json_hash(input_manifest)

    # The same evaluation cadence as the historical P/E distribution: the
    # usable dates of the indexed filings. Facts outside the index never
    # introduce an evaluation date of their own.
    evaluation_dates = sorted({filing["usable_date"] for filing in filings_index.values()})

    result = build_historical_pfcf(
        issuer_id=config.issuer_id,
        instrument_id=config.ticker,
        cash_flow_spans=cash_flow_spans,
        share_counts=share_counts,
        prices=prices_map,
        fiscal_calendar=fiscal_calendar,
        evaluation_dates=evaluation_dates,
        current_price_day=current_price_day,
        min_observations=min_observations,
        input_set_id=input_set_id,
    )
    # Only span ends that actually carry indexed facts can be lost to an
    # unresolved identity; report those precisely, never payload-wide noise.
    # Cumulative (6M/9M) span ends are quarter-end candidates too, so an
    # unresolved identity on a cumulative period is reported rather than
    # silently ignored.
    indexed_quarter_ends = {span.end for span in cash_flow_spans if span.duration_days is not None}
    lost_ends = sorted(
        end for end in indexed_quarter_ends if end not in fiscal_calendar.quarter_identity
    )
    if lost_ends:
        result.summary_notes.append(
            f"{len(lost_ends)} quarter periods carry cash-flow facts but no issuer "
            "declaration identifying their fiscal year and quarter and are excluded "
            f"from the discrete-quarter stream rather than mislabelled: {lost_ends}."
        )
    if fiscal_calendar.unresolved:
        result.summary_notes.append(
            f"{len(fiscal_calendar.unresolved)} fiscal periods remain unresolved by "
            f"issuer declaration and are excluded rather than assigned: "
            f"{[item['period_end'] for item in fiscal_calendar.unresolved]}."
        )
    if fiscal_calendar.warnings:
        result.summary_notes.append(
            f"{len(fiscal_calendar.warnings)} fiscal identity conflicts were recorded "
            f"and not silently resolved: {fiscal_calendar.warnings}."
        )
    return result


def load_aapl_historical_pfcf(
    min_observations: int = MIN_OBSERVATIONS_FOR_REFERENCE,
) -> HistoricalPfcfResult:
    """Load the AAPL promoted dataset and execute the production pipeline."""
    return load_issuer_historical_pfcf(ISSUER_CONFIGS["AAPL"], min_observations=min_observations)


def production_pfcf_summary(payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    The compact state of a production historical P/FCF payload.

    The full payload carries one record per evaluation date with its window
    components; this returns only what a summary needs to state the
    distribution's identity and eligibility. It changes nothing about
    eligibility: the same gate that decides usability decides what this
    summary reports.
    """
    if not payload:
        return None
    distribution = payload.get("distribution") or {}
    snapshot = payload.get("current_snapshot") or {}
    percentiles = distribution.get("percentiles") or {}
    excluded = distribution.get("excluded_observations") or []
    return {
        "issuer_id": payload.get("issuer_id"),
        "instrument_id": payload.get("instrument_id"),
        "metric_id": distribution.get("metric_id"),
        "status": distribution.get("status"),
        "usable_for_reference": bool(distribution.get("usable_for_reference")),
        "sample_count": distribution.get("sample_count"),
        "total_evaluations": distribution.get("total_evaluations"),
        "min_observations_required": distribution.get("min_observations_required"),
        "period_start": distribution.get("period_start"),
        "period_end": distribution.get("period_end"),
        "mean": distribution.get("mean"),
        "std": distribution.get("std"),
        "min": distribution.get("min"),
        "max": distribution.get("max"),
        "percentiles": {
            key: value for key, value in percentiles.items() if value is not None
        },
        "current_pfcf": snapshot.get("value"),
        "current_pfcf_as_of": snapshot.get("evaluation_date"),
        "sampling_cadence": distribution.get("sampling_cadence"),
        "evaluation_schedule_description": distribution.get(
            "evaluation_schedule_description"
        ),
        "excluded_observation_count": len(excluded),
        "input_set_id": payload.get("input_set_id"),
        "content_hash": payload.get("content_hash"),
        "reason_code": distribution.get("reason_code"),
        "reason_detail": distribution.get("reason_detail"),
    }
