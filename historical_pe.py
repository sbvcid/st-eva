"""
ST-EVA Historical P/E Engine — Production Pipeline.

This module implements the point-in-time (PIT) Historical P/E pipeline. It pairs
historical prices with contemporaneous EPS evidence without lookahead bias, enforces
strict fiscal calendar windows (four consecutive fiscal quarters with a Q4, directly
stated, strictly prohibiting FY - YTD synthesis), distinguishes filed and furnished
evidence classes, computes distribution statistics, and applies the reference
sufficiency gate (>= 20 valid observations required for reference distribution status).

Invariants enforced:
  F-1:  Evidence is never synthesised (no FY - YTD).
  F-2:  A TTM window is four consecutive fiscal quarters and contains a Q4.
  F-3:  Fiscal identity never depends on the existence of a 10-K.
  F-4:  Annual never fills TTM.
  F-5:  Evidence class is never laundered.
  F-6:  Price and EPS accounting bases agree.
  F-7:  Point-in-time monotonicity (usable_date <= evaluation_date).
  F-8:  Restatements are point-in-time (R-PIT-SUPERSEDE).
  F-9:  GAAP is never mixed with non-GAAP.
  F-10: CURRENT_PE is excluded from every window and distribution.
  F-11: Reason codes use the explicit enumeration declared by this module.
  F-12: XBRL_FACT_UNAVAILABLE is never an eligibility state.
  F-13: Determinism (identical input_set_id + logic_version -> identical content_hash).
  F-14: Source identity is complete (accession, form, url, content hash).
  F-15: Same accounting metric across classes (GAAP_DILUTED_EPS).
  F-16: Fiscal identity of a period is the issuer's own declaration (dei
        focus fields of the declaring filing, the earnings release's quarter
        label, or the issuer's annual span) -- never a month grid, which
        cannot represent 52/53-week calendars; a period with no issuer
        declaration is excluded, never assigned to a neighbouring quarter.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple
from zoneinfo import ZoneInfo

from fiscal_calendar import (
    IDENTITY_COMPARATIVE,
    IDENTITY_PRIMARY,
    IDENTITY_SPAN_POSITION,
    build_fiscal_calendar,
)

ET = ZoneInfo("America/New_York")
UTC = datetime.timezone.utc
CUTOFF_ET = datetime.time(16, 0)

METHODOLOGY = "historical-pe/1.0"
METHODOLOGY_AMENDMENT = "Amendment 1 (2026-10-07), Decisions 10-14"
LOGIC_VERSION = "historical-pe/1.1.0"
FORMULA_VERSION = "historical-pe/1.0"

# Explicit reason-code enumeration included in each result.
REASON_MISSING_PRICE = "REASON_MISSING_PRICE"
REASON_MISSING_Q4_EPS = "REASON_MISSING_Q4_EPS"
REASON_INSUFFICIENT_QUARTERS = "REASON_INSUFFICIENT_QUARTERS"
REASON_NON_POSITIVE_EPS = "REASON_NON_POSITIVE_EPS"
REASON_CORPORATE_ACTION_UNRESOLVED = "REASON_CORPORATE_ACTION_UNRESOLVED"
REASON_INSUFFICIENT_OBSERVATIONS = "REASON_INSUFFICIENT_OBSERVATIONS"
REASON_INSUFFICIENT_TIME_SPAN = "REASON_INSUFFICIENT_TIME_SPAN"

CLOSED_REASON_CODES = frozenset({
    REASON_MISSING_PRICE,
    REASON_MISSING_Q4_EPS,
    REASON_INSUFFICIENT_QUARTERS,
    REASON_NON_POSITIVE_EPS,
    REASON_CORPORATE_ACTION_UNRESOLVED,
    REASON_INSUFFICIENT_OBSERVATIONS,
    REASON_INSUFFICIENT_TIME_SPAN,
})

# Status vocabulary emitted by the historical P/E engine
STATUS_AVAILABLE = "AVAILABLE"
STATUS_UNAVAILABLE = "UNAVAILABLE"
STATUS_REFUSED = "REFUSED"

# Distribution qualification statuses
STATUS_USABLE_FOR_REFERENCE = "USABLE_FOR_REFERENCE"
STATUS_INSUFFICIENT_OBSERVATIONS = "INSUFFICIENT_OBSERVATIONS"

# Evidence classes carried by source records
EVIDENCE_CLASS_FILED = "filed"
EVIDENCE_CLASS_FURNISHED = "furnished"
EVIDENCE_CLASS_COMPOSITE = "composite"

# Audit-status vocabulary carried by source records
AUDIT_STATUS_AUDITED = "audited"
AUDIT_STATUS_REVIEWED = "unaudited_reviewed"
AUDIT_STATUS_UNAUDITED = "unaudited"

# Metric identifiers emitted by the historical P/E engine
METRIC_TTM_GAAP_DILUTED_PE = "TTM_GAAP_DILUTED_PE"
METRIC_ANNUAL_GAAP_DILUTED_PE = "ANNUAL_GAAP_DILUTED_PE"
METRIC_CURRENT_PE = "CURRENT_PE"

# Calendar thresholds
QUARTER_MIN_DAYS = 80
QUARTER_MAX_DAYS = 100
YEAR_MIN_DAYS = 350
YEAR_MAX_DAYS = 380

# Minimum sample size before a distribution can serve as a reference
MIN_OBSERVATIONS_FOR_REFERENCE = 20

# Volatile fields excluded from the canonical content hash
EXCLUDED_HASH_FIELDS = frozenset({
    "retrieved_at",
    "wall_clock_timestamp",
    "run_id",
    "host_identifier",
})


def _parse_date(value: str | datetime.date | None) -> datetime.date | None:
    if not value:
        return None
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _clean_for_hash(obj: Any) -> Any:
    """Strip volatile excluded fields recursively before hashing."""
    if isinstance(obj, dict):
        return {
            k: _clean_for_hash(v)
            for k, v in sorted(obj.items())
            if k not in EXCLUDED_HASH_FIELDS
        }
    if isinstance(obj, (list, tuple)):
        return [_clean_for_hash(item) for item in obj]
    return obj


def canonical_json_hash(payload: Any) -> str:
    """Compute deterministic SHA256 of canonical JSON form."""
    cleaned = _clean_for_hash(payload)
    serialized = json.dumps(cleaned, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Fiscal calendar derivation from reported period ends
# ---------------------------------------------------------------------------

def fiscal_year_of(period_end: datetime.date, fye_month: int) -> int:
    """The fiscal year a quarter belongs to.

    Derived from the quarter's own period end and the declared fiscal year end
    month. Deliberately not derived from filed 10-K period ends.
    """
    return period_end.year + (1 if period_end.month > fye_month else 0)


def quarter_number(period_end: datetime.date, fye_month: int) -> int:
    """Fiscal quarter number (1, 2, 3, or 4)."""
    months_after = (period_end.month - fye_month) % 12
    if months_after == 0:
        return 4
    return (months_after - 1) // 3 + 1


def _window_ends_consecutive(window_ends: Sequence[datetime.date]) -> bool:
    """Whether the window's period ends are consecutive quarters in calendar
    time: each adjacent pair of quarter ends spans one quarter (13 or 14
    weeks), the same span QUARTER_MIN_DAYS..QUARTER_MAX_DAYS admits."""
    for earlier, later in zip(window_ends, window_ends[1:]):
        gap = (later - earlier).days
        if gap < QUARTER_MIN_DAYS or gap > QUARTER_MAX_DAYS:
            return False
    return True


# ---------------------------------------------------------------------------
# Point-in-time usable-date resolver
# ---------------------------------------------------------------------------

def resolve_usable_date(
    acceptance_et: datetime.datetime, trading_days: Sequence[str]
) -> Tuple[str, str]:
    """Resolve the date a filing becomes usable under the 16:00 ET cutoff.

    Returns (usable_date_str, rule_label).
    """
    if acceptance_et.tzinfo is None:
        raise ValueError("acceptance_datetime must carry explicit timezone information")

    # Ensure timestamp is evaluated in America/New_York
    acceptance_in_et = acceptance_et.astimezone(ET)
    before_close = acceptance_in_et.time() < CUTOFF_ET

    candidate = (
        acceptance_in_et.date()
        if before_close
        else acceptance_in_et.date() + datetime.timedelta(days=1)
    )
    rule = (
        "acceptance_before_1600ET_same_day"
        if before_close
        else "acceptance_at_or_after_1600ET_next_trading_day"
    )
    candidate_iso = candidate.isoformat()

    for day in trading_days:
        if day >= candidate_iso:
            return day, rule

    return candidate_iso, rule + "_before_price_series"


# ---------------------------------------------------------------------------
# Input Schemas: QuarterEpsEvidence & HistoricalPriceEvidence
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class QuarterEpsEvidence:
    """One quarter EPS evidence instance with source and availability metadata."""

    evidence_id: str
    issuer_id: str
    evidence_class: str  # "filed" | "furnished"
    form: str            # "10-Q" | "10-K" | "8-K"
    accession: str
    period_end: str
    fiscal_year: int
    fiscal_quarter: int
    value: float
    audit_status: str    # "audited" | "unaudited_reviewed" | "unaudited"
    acceptance_datetime: str
    usable_date: str
    usable_date_rule: str
    metric: str = "GAAP_DILUTED_EPS"
    sec_item: Optional[str] = None
    source_document: Optional[str] = None
    source_url: Optional[str] = None
    acceptance_source: str = "EDGAR_SGML_HEADER_ACCEPTANCE_DATETIME"
    acceptance_precision: str = "INSTANT"
    legal_status_note: Optional[str] = None
    period_declaration: str = "XBRL_FACT_PERIOD"
    period_start: Optional[str] = None
    duration_days: Optional[int] = None
    fiscal_position_source: str = "DERIVED_FROM_ISSUER_FY_END"
    unit: str = "per_share"
    currency: str = "USD"
    stated_directly: bool = True
    derivation: str = "directly tagged quarter-length XBRL fact"
    content_sha256: Optional[str] = None
    retrieved_from: Optional[str] = None
    core_observation_ref: Optional[str] = None
    item_2_02_furnished_not_filed: Optional[bool] = None

    def __post_init__(self) -> None:
        if self.metric != "GAAP_DILUTED_EPS":
            raise ValueError(f"metric must be GAAP_DILUTED_EPS, got {self.metric!r}")
        if self.evidence_class not in (EVIDENCE_CLASS_FILED, EVIDENCE_CLASS_FURNISHED):
            raise ValueError(f"invalid evidence_class: {self.evidence_class!r}")
        if not self.stated_directly:
            raise ValueError("Invariant F-1 violation: evidence must be stated directly (no FY-YTD)")
        if self.fiscal_quarter not in (1, 2, 3, 4):
            raise ValueError(f"fiscal_quarter must be 1..4, got {self.fiscal_quarter}")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HistoricalPriceEvidence:
    """Price evidence for a specific trading date."""

    price_evidence_id: str
    issuer_id: str
    instrument_id: str
    price_date: str
    close: float
    currency: str = "USD"
    unit: str = "currency"
    price_source: str = "Yahoo Finance chart API v8 close"
    price_source_url: Optional[str] = None
    vendor_adjustment_note: Optional[str] = None
    corporate_action_provenance: Tuple[Dict[str, Any], ...] = ()
    accounting_basis: str = "as_traded"
    content_sha256: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        res["corporate_action_provenance"] = list(self.corporate_action_provenance)
        return res


# ---------------------------------------------------------------------------
# Output Schemas: HistoricalPeObservation & Distribution
# ---------------------------------------------------------------------------

@dataclass
class HistoricalPeObservation:
    """One computed historical P/E observation."""

    observation_id: str
    issuer_id: str
    instrument_id: str
    metric_id: str
    evaluation_date: str
    evaluation_date_is_trading_day: bool
    status: str
    reason_code: Optional[str]
    reason_detail: Optional[str]
    value: Optional[float]
    unit: str
    currency: Optional[str]
    eps_state: Dict[str, Any]
    price_state: Dict[str, Any]
    pe_state: Dict[str, Any]
    source_lineage: Dict[str, Any]
    methodology: str = METHODOLOGY
    methodology_amendment: str = METHODOLOGY_AMENDMENT
    logic_version: str = LOGIC_VERSION
    input_set_id: str = ""
    content_hash: str = ""
    replay_identity: Dict[str, Any] = field(default_factory=dict)
    role: Optional[str] = None

    def __post_init__(self) -> None:
        if self.reason_code is not None and self.reason_code not in CLOSED_REASON_CODES:
            raise ValueError(f"Invariant F-11 violation: reason_code {self.reason_code!r} not in closed set")
        if not self.content_hash:
            self.content_hash = self.compute_content_hash()

    def compute_content_hash(self) -> str:
        data = asdict(self)
        data.pop("content_hash", None)
        return canonical_json_hash(data)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HistoricalPeDistribution:
    """Distribution statistics and reference eligibility gate."""

    metric_id: str = METRIC_TTM_GAAP_DILUTED_PE
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
        "Evaluated on periodic SEC filing and earnings release usable dates (10-Q, 10-K, 8-K Item 2.02); "
        "not a continuous daily trading history."
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HistoricalPeResult:
    """Overall package returned by historical P/E pipeline."""

    issuer_id: str
    instrument_id: str
    input_set_id: str
    distribution: HistoricalPeDistribution
    observations: List[HistoricalPeObservation]
    annual_observations: List[HistoricalPeObservation]
    current_snapshot: Optional[HistoricalPeObservation] = None
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
            "annual_observations": [obs.to_dict() for obs in self.annual_observations],
            "current_snapshot": self.current_snapshot.to_dict() if self.current_snapshot else None,
            "summary_notes": list(self.summary_notes),
        }


def production_distribution_summary(
    payload: Optional[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    The compact state of a production historical P/E payload.

    The full payload carries one record per evaluation date with its quarter
    evidence, which is far more than a report or API response needs to state a
    reference distribution's identity and eligibility. This returns only that
    statement: the metric, the source identity, the sample and qualifying
    counts, the sample period, the as-of rule the evaluation dates follow, the
    percentiles, the current P/E snapshot, the input-set identity, and the
    reason when the distribution is unavailable or under-qualified. It changes
    nothing about eligibility: the same gate that decides the scenarios decides
    what this summary reports.
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
        "percentiles": {key: value for key, value in percentiles.items() if value is not None},
        "current_pe": snapshot.get("value"),
        "current_pe_as_of": snapshot.get("evaluation_date"),
        "sampling_cadence": distribution.get("sampling_cadence"),
        "evaluation_schedule_description": distribution.get("evaluation_schedule_description"),
        "excluded_observation_count": len(excluded),
        "input_set_id": payload.get("input_set_id"),
        "content_hash": payload.get("content_hash"),
        "reason_code": distribution.get("reason_code"),
        "reason_detail": distribution.get("reason_detail"),
    }


# ---------------------------------------------------------------------------
# Distribution Statistics Helper
# ---------------------------------------------------------------------------

def compute_distribution_percentiles(values: Sequence[float]) -> Dict[str, float]:
    """Compute 10th, 25th, median (50th), 75th, 90th percentiles using linear interpolation."""
    if not values:
        return {}
    sorted_vals = sorted(values)
    n = len(sorted_vals)

    def _percentile(p: float) -> float:
        if n == 1:
            return sorted_vals[0]
        # Linear interpolation between nearest ranks
        k = (n - 1) * (p / 100.0)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_vals[int(k)]
        d0 = sorted_vals[int(f)] * (c - k)
        d1 = sorted_vals[int(c)] * (k - f)
        return d0 + d1

    return {
        "10th": round(_percentile(10.0), 6),
        "25th": round(_percentile(25.0), 6),
        "median": round(_percentile(50.0), 6),
        "75th": round(_percentile(75.0), 6),
        "90th": round(_percentile(90.0), 6),
    }


def compute_historical_pe_distribution(
    observations: Sequence[HistoricalPeObservation],
    min_observations: int = MIN_OBSERVATIONS_FOR_REFERENCE,
) -> HistoricalPeDistribution:
    """Build the production historical P/E distribution and apply sufficiency gate."""
    ttm_obs = [o for o in observations if o.metric_id == METRIC_TTM_GAAP_DILUTED_PE and o.role != "current_snapshot"]

    valid_obs = [o for o in ttm_obs if o.status == STATUS_AVAILABLE and o.value is not None and o.value > 0]
    excluded = [
        {
            "evaluation_date": o.evaluation_date,
            "status": o.status,
            "reason_code": o.reason_code,
            "reason_detail": o.reason_detail,
        }
        for o in ttm_obs
        if o.status != STATUS_AVAILABLE
    ]

    sample_count = len(valid_obs)
    total_evals = len(ttm_obs)

    if sample_count == 0:
        return HistoricalPeDistribution(
            metric_id=METRIC_TTM_GAAP_DILUTED_PE,
            status=STATUS_UNAVAILABLE,
            usable_for_reference=False,
            sample_count=0,
            total_evaluations=total_evals,
            min_observations_required=min_observations,
            reason_code=REASON_INSUFFICIENT_OBSERVATIONS,
            reason_detail="Zero valid point-in-time TTM observations could be constructed.",
            excluded_observations=excluded,
        )

    values = [o.value for o in valid_obs if o.value is not None]
    period_start = min(o.evaluation_date for o in valid_obs)
    period_end = max(o.evaluation_date for o in valid_obs)

    mean_val = round(sum(values) / sample_count, 6)
    variance = sum((x - mean_val) ** 2 for x in values) / (sample_count - 1) if sample_count > 1 else 0.0
    std_val = round(math.sqrt(variance), 6) if sample_count > 1 else 0.0
    min_val = round(min(values), 6)
    max_val = round(max(values), 6)
    percentiles = compute_distribution_percentiles(values)

    # Reference sufficiency gate: strict >= 20 threshold
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
            f"required to establish an authoritative reference distribution. Descriptive statistics "
            f"(median {percentiles.get('median')}) are reported for review but are ineligible as "
            f"scenario exit multiples."
        )

    return HistoricalPeDistribution(
        metric_id=METRIC_TTM_GAAP_DILUTED_PE,
        status=status,
        usable_for_reference=usable_for_reference,
        sample_count=sample_count,
        total_evaluations=total_evals,
        period_start=period_start,
        period_end=period_end,
        min_observations_required=min_observations,
        mean=mean_val,
        std=std_val,
        min=min_val,
        max=max_val,
        percentiles=percentiles,
        reason_code=reason_code,
        reason_detail=reason_detail,
        excluded_observations=excluded,
        observations=[o.to_dict() for o in valid_obs],
    )


# ---------------------------------------------------------------------------
# Core pipeline: resolve admissible inputs and compute dated observations
# ---------------------------------------------------------------------------

def build_historical_pe(
    *,
    issuer_id: str,
    instrument_id: str,
    quarter_evidence: Sequence[QuarterEpsEvidence],
    annual_evidence: Sequence[QuarterEpsEvidence],
    prices: Mapping[str, HistoricalPriceEvidence],
    fye_month: int,
    trading_days: Sequence[str],
    evaluation_dates: Optional[Sequence[str]] = None,
    current_price_evidence: Optional[HistoricalPriceEvidence] = None,
    min_observations: int = MIN_OBSERVATIONS_FOR_REFERENCE,
    input_set_id: str = "",
) -> HistoricalPeResult:
    """Executes the normative resolver sequence E.0 through E.8."""
    # Organize evidence by period_end
    quarterly_by_end: Dict[datetime.date, List[QuarterEpsEvidence]] = {}
    for ev in quarter_evidence:
        end_d = _parse_date(ev.period_end)
        if end_d:
            quarterly_by_end.setdefault(end_d, []).append(ev)

    for versions in quarterly_by_end.values():
        versions.sort(key=lambda item: (item.usable_date, item.acceptance_datetime, item.accession))

    annual_by_end: Dict[datetime.date, List[QuarterEpsEvidence]] = {}
    for ev in annual_evidence:
        end_d = _parse_date(ev.period_end)
        if end_d:
            annual_by_end.setdefault(end_d, []).append(ev)

    for versions in annual_by_end.values():
        versions.sort(key=lambda item: (item.usable_date, item.acceptance_datetime, item.accession))

    # Determine evaluation dates if not explicitly provided
    if evaluation_dates is None:
        eval_set: Set[str] = set()
        for ev_list in quarterly_by_end.values():
            for ev in ev_list:
                eval_set.add(ev.usable_date)
        for ev_list in annual_by_end.values():
            for ev in ev_list:
                eval_set.add(ev.usable_date)
        eval_dates = sorted(eval_set)
    else:
        eval_dates = sorted(evaluation_dates)

    observations: List[HistoricalPeObservation] = []
    annual_observations: List[HistoricalPeObservation] = []

    for day in eval_dates:
        price_ev = prices.get(day)
        price_val = price_ev.close if price_ev else None

        # Point-in-time quarter evidence known at date day: R-PIT-SUPERSEDE
        known_quarters: Dict[datetime.date, QuarterEpsEvidence] = {}
        for p_end, versions in quarterly_by_end.items():
            usable = [v for v in versions if v.usable_date <= day]
            if usable:
                # Latest usable_date, tie broken by acceptance_datetime and accession
                known_quarters[p_end] = usable[-1]

        ends_sorted = sorted(known_quarters.keys())

        ttm_status = STATUS_UNAVAILABLE
        ttm_reason = None
        ttm_reason_detail = None
        ttm_value = None
        ttm_components: List[Dict[str, Any]] = []
        missing_positions: List[Dict[str, Any]] = []

        if not known_quarters:
            ttm_reason = REASON_INSUFFICIENT_QUARTERS
            ttm_reason_detail = f"No quarter EPS evidence is knowable at evaluation date {day}."
        else:
            # Anchor on greatest fiscal-quarter position with known evidence.
            # Fiscal positions come from the evidence's issuer-declared
            # identity (dei:FiscalYearFocus / dei:FiscalPeriodFocus of the
            # declaring filing, the earnings release's own quarter label, or
            # the issuer's annual span), never from a month grid: 52/53-week
            # filers' quarter ends drift across month boundaries and a month
            # grid assigns them to the wrong fiscal quarter.
            anchor = ends_sorted[-1]
            anchor_evidence = known_quarters[anchor]
            anchor_year = anchor_evidence.fiscal_year
            anchor_number = anchor_evidence.fiscal_quarter

            positions: List[Tuple[int, int]] = []
            cur_y = anchor_year
            cur_q = anchor_number
            for _ in range(4):
                positions.append((cur_y, cur_q))
                cur_q -= 1
                if cur_q == 0:
                    cur_q = 4
                    cur_y -= 1
            positions.reverse()  # Ascending fiscal order

            window_ends: List[datetime.date] = []
            for pos_y, pos_q in positions:
                matches = [
                    end for end in ends_sorted
                    if known_quarters[end].fiscal_year == pos_y
                    and known_quarters[end].fiscal_quarter == pos_q
                ]
                if matches:
                    window_ends.append(matches[-1])
                else:
                    missing_positions.append({
                        "fiscal_year": pos_y,
                        "fiscal_quarter": pos_q,
                        "candidate_evidence_classes_enumerated": [EVIDENCE_CLASS_FILED, EVIDENCE_CLASS_FURNISHED],
                    })

            if missing_positions:
                if any(p["fiscal_quarter"] == 4 for p in missing_positions):
                    ttm_reason = REASON_MISSING_Q4_EPS
                    ttm_reason_detail = (
                        "The four-quarter fiscal window contains an unfilled fiscal Q4 position after enumerating "
                        "both filed and furnished evidence classes."
                    )
                else:
                    ttm_reason = REASON_INSUFFICIENT_QUARTERS
                    ttm_reason_detail = (
                        f"The four-quarter fiscal window is missing positions: {missing_positions}."
                    )
            elif not _window_ends_consecutive(window_ends):
                # Invariant F-2 at calendar level: the fiscal-position grid can
                # fill all four positions with period ends that are not
                # consecutive quarters for a 52/53-week filer whose quarter ends
                # drift across month boundaries (e.g. MU's June quarter ends).
                # Such a filled window is not a TTM window and is refused.
                gaps = [
                    (window_ends[i + 1] - window_ends[i]).days
                    for i in range(len(window_ends) - 1)
                ]
                ttm_reason = REASON_INSUFFICIENT_QUARTERS
                ttm_reason_detail = (
                    "The fiscal-position window is filled but its period ends are not consecutive "
                    f"calendar quarters (gap days {gaps} between sorted ends {window_ends}); "
                    "a month-grid fiscal mapping cannot represent this issuer's quarter sequence."
                )
            else:
                # All 4 positions filled!
                for end in window_ends:
                    ev = known_quarters[end]
                    # Verify Invariant F-7: PIT monotonicity
                    if ev.usable_date > day:
                        raise ValueError(f"Invariant F-7 violation: evidence usable_date {ev.usable_date} > {day}")
                    ttm_components.append(ev.to_dict())

                eps_sum = sum(c["value"] for c in ttm_components)

                # Check price and EPS conditions
                if price_val is None:
                    ttm_reason = REASON_MISSING_PRICE
                    ttm_reason_detail = f"No historical price evidence is observed for trading day {day}."
                elif eps_sum <= 0:
                    ttm_reason = REASON_NON_POSITIVE_EPS
                    ttm_reason_detail = f"Sum of four quarterly EPS is non-positive ({eps_sum:.4f})."
                elif price_ev and price_ev.accounting_basis != "as_traded":
                    ttm_reason = REASON_CORPORATE_ACTION_UNRESOLVED
                    ttm_reason_detail = f"Price accounting basis {price_ev.accounting_basis} unaligned with as-filed EPS."
                else:
                    ttm_status = STATUS_AVAILABLE
                    ttm_value = price_val / eps_sum

        classes_present = sorted({c["evidence_class"] for c in ttm_components})
        forms_present = sorted({c["form"] for c in ttm_components})
        audit_statuses = sorted({c["audit_status"] for c in ttm_components})

        ttm_denominator = round(sum(c["value"] for c in ttm_components), 6) if not missing_positions and ttm_components else None
        denominator_derivation = None
        if ttm_denominator is not None:
            # The TTM denominator is a derived sum of four directly stated
            # quarterly figures, never an issuer-declared annual figure.
            # Per-share amounts are not strictly additive across quarters with
            # differing share counts, so the sum can differ from the issuer's
            # audited annual EPS; the annual figure in force at this date is
            # carried beside it so the gap stays visible instead of being
            # reconciled away.
            annual_in_force = None
            for annual_end in sorted(annual_by_end):
                versions = [v for v in annual_by_end[annual_end] if v.usable_date <= day]
                if versions:
                    annual_ev = versions[-1]
                    annual_in_force = {
                        "value": annual_ev.value,
                        "period_end": annual_ev.period_end,
                        "fiscal_year": annual_ev.fiscal_year,
                        "accession": annual_ev.accession,
                    }
            denominator_derivation = {
                "method": "SUM_OF_FOUR_DIRECTLY_STATED_QUARTERLY_EPS",
                "derived_not_issuer_declared": True,
                "annual_eps_in_force_at_evaluation_date": annual_in_force,
                "note": (
                    "The TTM denominator sums four issuer-declared fiscal "
                    "quarters' directly stated GAAP diluted EPS. It is a "
                    "derived TTM indicator, not an issuer-declared figure; "
                    "per-share amounts are not strictly additive across "
                    "quarters with differing share counts, so it can differ "
                    "from the audited annual EPS recorded beside it."
                ),
            }

        eps_state = {
            "status": STATUS_AVAILABLE if not missing_positions and ttm_components else STATUS_UNAVAILABLE,
            "window_anchor": {
                "fiscal_year": positions[-1][0],
                "fiscal_quarter": positions[-1][1],
            } if known_quarters else None,
            "quarter_denominator": ttm_denominator,
            "quarter_denominator_derivation": denominator_derivation,
            "quarters_required": 4,
            "quarters_present": len(ttm_components),
            "missing_quarters": missing_positions,
            "components": ttm_components,
            "component_summary": {
                "evidence_classes_present": classes_present,
                "forms_present": forms_present,
                "audit_statuses_present": audit_statuses,
                "mixed_class_window": len(classes_present) > 1,
                "fy_minus_ytd_used": False,
            },
        }

        price_state = {
            "status": STATUS_AVAILABLE if price_val is not None else STATUS_UNAVAILABLE,
            "price_date": day,
            "close": price_val,
            "currency": price_ev.currency if price_ev else "USD",
            "accounting_basis": price_ev.accounting_basis if price_ev else "as_traded",
            "price_evidence_id": price_ev.price_evidence_id if price_ev else None,
            "corporate_action_provenance": list(price_ev.corporate_action_provenance) if price_ev else [],
            "basis_alignment": "aligned" if price_ev and price_ev.accounting_basis == "as_traded" else "unaligned",
            "source": {
                "provider": price_ev.price_source if price_ev else None,
                "url": price_ev.price_source_url if price_ev else None,
                "content_sha256": price_ev.content_sha256 if price_ev else None,
                "vendor_adjustment_note": price_ev.vendor_adjustment_note if price_ev else None,
            },
        }

        pe_state = {
            "status": ttm_status,
            "numerator_source": "price_state.close",
            "denominator_source": "eps_state.quarter_denominator",
            "formula": "close / quarter_denominator",
        }

        source_lineage = {
            "evidence_ids": [c["evidence_id"] for c in ttm_components],
            "price_evidence_ids": [price_ev.price_evidence_id] if price_ev else [],
            "refusals": [],
        }

        obs = HistoricalPeObservation(
            observation_id=f"histpe-{METRIC_TTM_GAAP_DILUTED_PE}-{instrument_id}-{day}",
            issuer_id=issuer_id,
            instrument_id=instrument_id,
            metric_id=METRIC_TTM_GAAP_DILUTED_PE,
            evaluation_date=day,
            evaluation_date_is_trading_day=True,
            status=ttm_status,
            reason_code=ttm_reason,
            reason_detail=ttm_reason_detail,
            value=round(ttm_value, 6) if ttm_value is not None else None,
            unit="multiple",
            currency=None,
            eps_state=eps_state,
            price_state=price_state,
            pe_state=pe_state,
            source_lineage=source_lineage,
            methodology=METHODOLOGY,
            methodology_amendment=METHODOLOGY_AMENDMENT,
            logic_version=LOGIC_VERSION,
            input_set_id=input_set_id,
            replay_identity={
                "input_set_id": input_set_id,
                "logic_version": LOGIC_VERSION,
                "deterministic": True,
            },
        )
        observations.append(obs)

        # Build annual GAAP diluted P/E from directly reported annual EPS
        annual_candidates: List[Tuple[datetime.date, QuarterEpsEvidence]] = []
        for p_end, a_versions in annual_by_end.items():
            usable_a = [v for v in a_versions if v.usable_date <= day and v.audit_status == AUDIT_STATUS_AUDITED and v.evidence_class == EVIDENCE_CLASS_FILED]
            if usable_a:
                annual_candidates.append((p_end, usable_a[-1]))

        ann_status = STATUS_UNAVAILABLE
        ann_reason = None
        ann_value = None
        ann_component = None

        if not annual_candidates:
            ann_reason = REASON_INSUFFICIENT_QUARTERS
        else:
            cand_end, cand_ev = max(annual_candidates, key=lambda pair: pair[0])
            ann_component = cand_ev.to_dict()
            if price_val is None:
                ann_reason = REASON_MISSING_PRICE
            elif cand_ev.value <= 0:
                ann_reason = REASON_NON_POSITIVE_EPS
            else:
                ann_status = STATUS_AVAILABLE
                ann_value = price_val / cand_ev.value

        ann_obs = HistoricalPeObservation(
            observation_id=f"histpe-{METRIC_ANNUAL_GAAP_DILUTED_PE}-{instrument_id}-{day}",
            issuer_id=issuer_id,
            instrument_id=instrument_id,
            metric_id=METRIC_ANNUAL_GAAP_DILUTED_PE,
            evaluation_date=day,
            evaluation_date_is_trading_day=True,
            status=ann_status,
            reason_code=ann_reason,
            reason_detail=None,
            value=round(ann_value, 6) if ann_value is not None else None,
            unit="multiple",
            currency=None,
            eps_state={
                "status": ann_status,
                "component": ann_component,
                "substituted_for_ttm": False,  # Invariant F-4
            },
            price_state=price_state,
            pe_state={
                "status": ann_status,
                "numerator_source": "price_state.close",
                "denominator_source": "eps_state.component.value",
                "formula": "close / annual_audited_eps",
            },
            source_lineage={
                "evidence_ids": [ann_component["evidence_id"]] if ann_component else [],
                "price_evidence_ids": [price_ev.price_evidence_id] if price_ev else [],
                "refusals": [],
            },
            methodology=METHODOLOGY,
            methodology_amendment=METHODOLOGY_AMENDMENT,
            logic_version=LOGIC_VERSION,
            input_set_id=input_set_id,
            replay_identity={
                "input_set_id": input_set_id,
                "logic_version": LOGIC_VERSION,
                "deterministic": True,
            },
        )
        annual_observations.append(ann_obs)

    # Current snapshot observation, kept distinct from the dated history series
    current_snapshot = None
    if current_price_evidence and trading_days:
        cur_day = trading_days[-1]
        cur_p_val = current_price_evidence.close

        known_quarters_cur: Dict[datetime.date, QuarterEpsEvidence] = {}
        for p_end, versions in quarterly_by_end.items():
            usable = [v for v in versions if v.usable_date <= cur_day]
            if usable:
                known_quarters_cur[p_end] = usable[-1]

        cur_missing = []
        cur_components = []
        cur_ttm_status = STATUS_UNAVAILABLE
        cur_ttm_val = None
        cur_ttm_reason = None
        cur_denominator = None
        cur_denominator_derivation = None

        if known_quarters_cur:
            # Fiscal positions from the anchor evidence's issuer-declared
            # identity, as in the dated loop; the month grid cannot represent
            # 52/53-week calendars.
            anchor_cur = max(known_quarters_cur.keys())
            anchor_cur_evidence = known_quarters_cur[anchor_cur]
            pos_cur = []
            cy = anchor_cur_evidence.fiscal_year
            cq = anchor_cur_evidence.fiscal_quarter
            for _ in range(4):
                pos_cur.append((cy, cq))
                cq -= 1
                if cq == 0:
                    cq = 4
                    cy -= 1
            pos_cur.reverse()

            for py, pq in pos_cur:
                m = [
                    end for end in sorted(known_quarters_cur.keys())
                    if known_quarters_cur[end].fiscal_year == py
                    and known_quarters_cur[end].fiscal_quarter == pq
                ]
                if m:
                    cur_components.append(known_quarters_cur[m[-1]].to_dict())
                else:
                    cur_missing.append({"fiscal_year": py, "fiscal_quarter": pq})

            if cur_missing:
                cur_ttm_reason = REASON_MISSING_Q4_EPS if any(p["fiscal_quarter"] == 4 for p in cur_missing) else REASON_INSUFFICIENT_QUARTERS
            elif not _window_ends_consecutive(
                sorted(
                    datetime.date.fromisoformat(c["period_end"])
                    for c in cur_components
                )
            ):
                # Invariant F-2 at calendar level, as in the dated loop: a
                # position-filled window over non-adjacent quarter ends is not
                # a TTM window.
                cur_ttm_reason = REASON_INSUFFICIENT_QUARTERS
            else:
                total_eps_cur = sum(c["value"] for c in cur_components)
                if total_eps_cur > 0 and cur_p_val is not None:
                    cur_ttm_status = STATUS_AVAILABLE
                    cur_ttm_val = cur_p_val / total_eps_cur
                elif total_eps_cur <= 0:
                    cur_ttm_reason = REASON_NON_POSITIVE_EPS

            if not cur_missing and cur_components:
                # Same derivation marking as the dated loop: the TTM
                # denominator is a derived sum, never an issuer-declared
                # annual figure; the audited annual in force is carried
                # beside it so any per-share non-additivity stays visible.
                cur_denominator = round(sum(c["value"] for c in cur_components), 6)
                cur_annual_versions = [
                    v
                    for versions in annual_by_end.values()
                    for v in versions
                    if v.usable_date <= cur_day
                ]
                cur_annual_in_force = None
                if cur_annual_versions:
                    annual_ev = max(cur_annual_versions, key=lambda v: v.period_end)
                    cur_annual_in_force = {
                        "value": annual_ev.value,
                        "period_end": annual_ev.period_end,
                        "fiscal_year": annual_ev.fiscal_year,
                        "accession": annual_ev.accession,
                    }
                cur_denominator_derivation = {
                    "method": "SUM_OF_FOUR_DIRECTLY_STATED_QUARTERLY_EPS",
                    "derived_not_issuer_declared": True,
                    "annual_eps_in_force_at_evaluation_date": cur_annual_in_force,
                    "note": (
                        "The TTM denominator sums four issuer-declared fiscal "
                        "quarters' directly stated GAAP diluted EPS. It is a "
                        "derived TTM indicator, not an issuer-declared figure; "
                        "per-share amounts are not strictly additive across "
                        "quarters with differing share counts, so it can differ "
                        "from the audited annual EPS recorded beside it."
                    ),
                }

        current_snapshot = HistoricalPeObservation(
            observation_id=f"histpe-{METRIC_CURRENT_PE}-{instrument_id}-{cur_day}",
            issuer_id=issuer_id,
            instrument_id=instrument_id,
            metric_id=METRIC_CURRENT_PE,
            evaluation_date=cur_day,
            evaluation_date_is_trading_day=True,
            status=cur_ttm_status,
            reason_code=cur_ttm_reason,
            reason_detail=None,
            value=round(cur_ttm_val, 6) if cur_ttm_val is not None else None,
            unit="multiple",
            currency=None,
            eps_state={
                "components": cur_components,
                "missing_quarters": cur_missing,
                "window_anchor": {
                    "fiscal_year": pos_cur[-1][0],
                    "fiscal_quarter": pos_cur[-1][1],
                } if known_quarters_cur else None,
                "quarter_denominator": cur_denominator,
                "quarter_denominator_derivation": cur_denominator_derivation,
            },
            price_state={
                "price_date": cur_day,
                "close": cur_p_val,
                "currency": current_price_evidence.currency,
                "accounting_basis": current_price_evidence.accounting_basis,
                "price_evidence_id": current_price_evidence.price_evidence_id,
                "corporate_action_provenance": list(current_price_evidence.corporate_action_provenance),
                "source": {
                    "provider": current_price_evidence.price_source,
                    "url": current_price_evidence.price_source_url,
                    "content_sha256": current_price_evidence.content_sha256,
                    "vendor_adjustment_note": current_price_evidence.vendor_adjustment_note,
                },
            },
            pe_state={"status": cur_ttm_status},
            source_lineage={"evidence_ids": [c["evidence_id"] for c in cur_components]},
            methodology=METHODOLOGY,
            methodology_amendment=METHODOLOGY_AMENDMENT,
            logic_version=LOGIC_VERSION,
            input_set_id=input_set_id,
            role="current_snapshot",  # Invariant F-10
            replay_identity={"input_set_id": input_set_id, "logic_version": LOGIC_VERSION, "deterministic": True},
        )

    # Compute distribution statistics over historical observations
    dist = compute_historical_pe_distribution(observations, min_observations=min_observations)

    # Compute package content hash
    package_dict = {
        "issuer_id": issuer_id,
        "instrument_id": instrument_id,
        "input_set_id": input_set_id,
        "distribution": dist.to_dict(),
        "observations": [o.to_dict() for o in observations],
        "annual_observations": [o.to_dict() for o in annual_observations],
    }
    content_hash = canonical_json_hash(package_dict)

    return HistoricalPeResult(
        issuer_id=issuer_id,
        instrument_id=instrument_id,
        input_set_id=input_set_id,
        distribution=dist,
        observations=observations,
        annual_observations=annual_observations,
        current_snapshot=current_snapshot,
        content_hash=content_hash,
    )


# ---------------------------------------------------------------------------
# AAPL POC Raw Fixture Loader (Verified Byte-Identical to Amendment 1)
# ---------------------------------------------------------------------------

@dataclass
class IssuerHistoricalPeConfig:
    """Configuration for loading Historical P/E dataset for an issuer."""
    ticker: str
    issuer_id: str
    fye_month: int
    data_dir: Path
    canonical_path: Optional[Path] = None


# Known issuer configurations
ISSUER_CONFIGS = {
    "AAPL": IssuerHistoricalPeConfig(
        ticker="AAPL",
        issuer_id="CIK0000320193",
        fye_month=9,
        data_dir=Path("data/historical_pe/AAPL"),
        canonical_path=Path("research/experiments/aapl-historical-pe-poc"),
    ),
    "MSFT": IssuerHistoricalPeConfig(
        ticker="MSFT",
        issuer_id="CIK0000789019",
        fye_month=6,
        data_dir=Path("data/historical_pe/MSFT"),
        canonical_path=None,
    ),
    "MU": IssuerHistoricalPeConfig(
        ticker="MU",
        issuer_id="CIK0000723125",
        fye_month=8,
        data_dir=Path("data/historical_pe/MU"),
        canonical_path=None,
    ),
    "SOFI": IssuerHistoricalPeConfig(
        ticker="SOFI",
        issuer_id="CIK0001818874",
        fye_month=12,
        data_dir=Path("data/historical_pe/SOFI"),
        canonical_path=None,
    ),
}



def _load_msft_filing_acceptance(base_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Load MSFT filing acceptance dates from SGML headers.
    
    MSFT POC uses header files in raw/headers/ to extract acceptance datetime
    instead of a pre-computed filing_acceptance_evidence.json file.
    
    Returns: dict keyed by accession number with acceptance_datetime_header_et, form, period_end
    """
    raw_dir = base_dir / "raw"
    headers_dir = raw_dir / "headers"
    submissions_path = raw_dir / "submissions.json"
    
    if not headers_dir.exists() or not submissions_path.exists():
        raise FileNotFoundError(f"MSFT headers or submissions not found at {raw_dir}")
    
    submissions = json.loads(submissions_path.read_text(encoding="utf-8"))
    recent = submissions["filings"]["recent"]
    
    # Map accession to filing metadata from submissions
    by_accession = {}
    for accn, form, period_end, items in zip(
        recent.get("accessionNumber", []),
        recent.get("form", []),
        recent.get("reportDate", []),
        recent.get("items", []),
    ):
        by_accession[accn] = {
            "form": form,
            "period_end": period_end,
            "items": items or "",
        }
    
    filings_index: Dict[str, Dict[str, Any]] = {}
    
    # Extract acceptance datetime from each header file
    for header_file in sorted(headers_dir.glob("*.txt")):
        accession = header_file.stem
        if accession not in by_accession:
            continue
        
        try:
            header_text = header_file.read_text(encoding="utf-8", errors="replace")
            # Search for ACCEPTANCE-DATETIME in SGML format
            match = re.search(r"ACCEPTANCE-DATETIME&gt;(\d{14})", header_text)
            if not match:
                continue
            
            acceptance_str = match.group(1)
            # Parse YYYYMMDDHHMMSS to ISO format with ET timezone
            acceptance_dt = datetime.datetime.strptime(acceptance_str, "%Y%m%d%H%M%S").replace(tzinfo=ET)
            
            filings_index[accession] = {
                "form": by_accession[accession]["form"],
                "acceptance_datetime": acceptance_dt.isoformat(),
                "acceptance_datetime_header_et": acceptance_dt.isoformat(),
                "period_end": by_accession[accession]["period_end"],
            }
        except Exception:
            # Skip files we can't parse
            continue
    
    if not filings_index:
        raise ValueError(f"Could not extract any filing acceptance dates from {headers_dir}")
    
    return filings_index


def _resolve_issuer_paths(
    issuer_config: IssuerHistoricalPeConfig,
) -> Tuple[Path, Path, Path, Optional[Path]]:
    """Resolve data file paths for an issuer.
    
    Returns: (prices_path, concept_path, acceptance_path, q4_records_path)
    Raises FileNotFoundError if required files not found.
    """
    base_dir = issuer_config.data_dir
    
    # Check canonical production layout (AAPL)
    if (base_dir / "daily_prices.json").exists():
        prices_path = base_dir / "daily_prices.json"
        concept_path = base_dir / "eps_diluted_concept.json"
        acceptance_path = base_dir / "filing_acceptance_evidence.json"
        q4_records_path = base_dir / "q4_evidence_records.json" if (base_dir / "q4_evidence_records.json").exists() else None
    # Check AAPL POC research layout
    elif (base_dir / "raw" / "daily_prices.json").exists() and (base_dir / "raw" / "eps_diluted_concept.json").exists():
        raw_dir = base_dir / "raw"
        q4_out_dir = base_dir / "q4_study" / "out"
        prices_path = raw_dir / "daily_prices.json"
        concept_path = raw_dir / "eps_diluted_concept.json"
        acceptance_path = raw_dir / "filing_acceptance_evidence.json"
        q4_records_path = q4_out_dir / "q4_evidence_records.json" if (q4_out_dir / "q4_evidence_records.json").exists() else None
    # Check MSFT POC layout (uses eps_diluted.json instead of eps_diluted_concept.json)
    elif (base_dir / "raw" / "prices.json").exists() and (base_dir / "raw" / "eps_diluted.json").exists():
        raw_dir = base_dir / "raw"
        prices_path = raw_dir / "prices.json"
        concept_path = raw_dir / "eps_diluted.json"
        # MSFT uses headers directory for acceptance dates
        acceptance_path = raw_dir / "headers"  # Marker path; actual loading uses headers
        # MSFT furnished Q4 evidence from 8-K Item 2.02 exhibits
        q4_records_path = (base_dir / "q4_evidence_records.json") if (base_dir / "q4_evidence_records.json").exists() else None
    else:
        raise FileNotFoundError(
            f"Could not find Historical P/E data for {issuer_config.ticker} at {base_dir} "
            f"(checked canonical and POC layouts)"
        )
    
    # Verify required files exist
    for path in [prices_path, concept_path, acceptance_path]:
        if not path.exists():
            raise FileNotFoundError(f"Missing required file: {path}")
    
    return prices_path, concept_path, acceptance_path, q4_records_path


def _sha256_of(path: Path) -> str:
    """Content digest of an input file, for input_set_id provenance."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _acceptance_input_digest(acceptance_path: Path) -> str:
    """Digest the filing acceptance input actually used.

    The canonical layout reads a single pre-computed JSON file, but the legacy POC
    layout derives acceptance from a directory of SGML headers plus submissions.json.
    Hash the exact inputs consumed so input_set_id tracks whichever was used.
    """
    if acceptance_path.name == "headers" and acceptance_path.is_dir():
        raw_dir = acceptance_path.parent
        parts = []
        for header_file in sorted(acceptance_path.glob("*.txt")):
            parts.append(f"{header_file.name}:{_sha256_of(header_file)}")
        submissions = raw_dir / "submissions.json"
        if submissions.exists():
            parts.append(f"submissions.json:{_sha256_of(submissions)}")
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return _sha256_of(acceptance_path)


def restore_as_traded_close(
    close: float,
    price_date: str,
    splits: Mapping[str, Mapping[str, Any]],
) -> Tuple[float, Tuple[Dict[str, Any], ...], Optional[str]]:
    """Restore a provider's split-adjusted close to the share basis traded on price_date.

    Yahoo's historical close series reflects later split events. A historical
    date must therefore be multiplied by every split whose ex-date is after
    that date, not just the earliest split in the response.
    """
    events: List[Dict[str, Any]] = []
    for stamp, entry in splits.items():
        ex_date = datetime.datetime.fromtimestamp(int(stamp), UTC).date().isoformat()
        numerator = float(entry["numerator"])
        denominator = float(entry["denominator"])
        if not math.isfinite(numerator) or not math.isfinite(denominator) or numerator <= 0 or denominator <= 0:
            raise ValueError(f"Invalid split ratio for {ex_date}: {numerator}:{denominator}")
        ratio = numerator / denominator
        ratio_label = entry.get("splitRatio") or f"{numerator:g}:{denominator:g}"
        events.append({
            "ex_date": ex_date,
            "ratio": ratio,
            "ratio_label": str(ratio_label),
        })

    applicable = sorted(
        (event for event in events if event["ex_date"] > price_date),
        key=lambda event: event["ex_date"],
    )
    factor = math.prod(event["ratio"] for event in applicable)
    restored_close = close * factor
    provenance = tuple({
        "ex_date": event["ex_date"],
        "split_ratio": event["ratio_label"],
        "vendor_adjusted_close": close,
        "restored_as_traded_close": restored_close,
        "cumulative_restoration_factor": factor,
    } for event in applicable)

    note = None
    if applicable:
        split_dates = ", ".join(
            f"{event['ex_date']} ({event['ratio_label']})" for event in applicable
        )
        note = (
            f"Yahoo chart close multiplied by cumulative split factor {factor:g} "
            f"to restore as-traded units using later splits: {split_dates}."
        )
    return restored_close, provenance, note


def load_issuer_historical_pe(
    issuer_config: IssuerHistoricalPeConfig,
    enable_furnished: bool = True,
    min_observations: int = MIN_OBSERVATIONS_FOR_REFERENCE,
) -> HistoricalPeResult:
    """Load Historical P/E dataset for an issuer using generic pipeline.
    
    Args:
        issuer_config: IssuerHistoricalPeConfig with ticker, CIK, FYE month, data paths
        enable_furnished: Enable Form 8-K Item 2.02 furnished evidence
        min_observations: Minimum observations required for reference distribution
    
    Returns:
        HistoricalPeResult with observations, distribution, and status
    
    Raises:
        FileNotFoundError: If required data files not found
    """
    prices_path, concept_path, acceptance_path, q4_records_path = _resolve_issuer_paths(issuer_config)
    
    # Load and process prices. The digest identifies the exact tracked chart payload
    # from which each dated price observation is derived.
    price_payload_bytes = prices_path.read_bytes()
    price_payload_hash = hashlib.sha256(price_payload_bytes).hexdigest()
    price_payload = json.loads(price_payload_bytes.decode("utf-8"))["chart"]["result"][0]
    quote = price_payload["indicators"]["quote"][0]
    bars = {
        datetime.datetime.fromtimestamp(stamp, UTC).date().isoformat(): float(quote["close"][idx])
        for idx, stamp in enumerate(price_payload["timestamp"])
        if quote["close"][idx] is not None
    }
    trading_days = sorted(bars.keys())
    
    # Restore each historical close from provider-adjusted units to the share
    # basis actually traded on that date, accounting for every later split.
    splits = price_payload.get("events", {}).get("splits", {})
    
    prices_map: Dict[str, HistoricalPriceEvidence] = {}
    for day, close in bars.items():
        restored_close, provenance, adjustment_note = restore_as_traded_close(
            close, day, splits
        )
        prices_map[day] = HistoricalPriceEvidence(
            price_evidence_id=f"price-{issuer_config.ticker}-{day}",
            issuer_id=issuer_config.issuer_id,
            instrument_id=issuer_config.ticker,
            price_date=day,
            close=round(restored_close, 4),
            currency="USD",
            price_source_url=f"https://query1.finance.yahoo.com/v8/finance/chart/{issuer_config.ticker}",
            vendor_adjustment_note=adjustment_note,
            corporate_action_provenance=provenance,
            accounting_basis="as_traded",
            content_sha256=price_payload_hash,
        )
    
    # Filing acceptance evidence
    # MSFT uses header files; others use pre-computed JSON
    if acceptance_path.name == "headers" and acceptance_path.is_dir():
        # MSFT: load from headers directory
        filings_index = _load_msft_filing_acceptance(issuer_config.data_dir)
    else:
        # AAPL and others: load from pre-computed acceptance JSON
        acceptance_evidence = json.loads(acceptance_path.read_text(encoding="utf-8"))
        filings_index: Dict[str, Dict[str, Any]] = {}
        for row in acceptance_evidence:
            acceptance_dt = datetime.datetime.fromisoformat(row["acceptance_datetime_header_et"])
            usable_d, usable_r = resolve_usable_date(acceptance_dt, trading_days)
            filings_index[row["accession"]] = {
                "form": row["form"],
                "acceptance_datetime": acceptance_dt.isoformat(),
                "usable_date": usable_d,
                "usable_date_rule": usable_r,
                "period_end": row["period_end"],
            }
    
    # Apply usable-date rules to filings_index entries (for MSFT which doesn't have them pre-computed)
    for accession in filings_index:
        if "usable_date" not in filings_index[accession]:
            acceptance_dt = datetime.datetime.fromisoformat(filings_index[accession]["acceptance_datetime"])
            usable_d, usable_r = resolve_usable_date(acceptance_dt, trading_days)
            filings_index[accession]["usable_date"] = usable_d
            filings_index[accession]["usable_date_rule"] = usable_r
    
    concept_sha = hashlib.sha256(concept_path.read_bytes()).hexdigest()
    
    # Quarterly and annual evidence from filed XBRL facts. Fiscal identity is
    # issuer-declared: the 10-Q/10-K whose conformed period of report equals
    # the fact's period end declares the period's fiscal year and quarter in
    # its own XBRL focus fields; comparative and annual-span rules fill the
    # rest. The month grid is no longer consulted for identity -- it cannot
    # represent 52/53-week calendars whose quarter ends drift across months.
    concept_payload = json.loads(concept_path.read_text(encoding="utf-8"))
    fiscal_calendar = build_fiscal_calendar([concept_payload], filings_index)
    identity_notes: List[str] = []
    all_period_ends_with_indexed_fact: Set[str] = set()
    annual_span_ends_with_indexed_fact: Set[str] = set()
    for fact in concept_payload["units"]["USD/shares"]:
        if not fact.get("start") or fact["accn"] not in filings_index:
            continue
        span = (
            datetime.date.fromisoformat(fact["end"])
            - datetime.date.fromisoformat(fact["start"])
        ).days
        all_period_ends_with_indexed_fact.add(fact["end"])
        if YEAR_MIN_DAYS <= span <= YEAR_MAX_DAYS and fact["form"] == "10-K":
            annual_span_ends_with_indexed_fact.add(fact["end"])
    lost_quarter_ends = sorted(
        end
        for end in all_period_ends_with_indexed_fact
        if end not in fiscal_calendar.quarter_identity
    )
    lost_annual_ends = sorted(
        end
        for end in annual_span_ends_with_indexed_fact
        if end not in fiscal_calendar.annual_fiscal_year
    )
    if lost_quarter_ends:
        identity_notes.append(
            f"{len(lost_quarter_ends)} quarter periods carry facts but no issuer "
            "declaration identifying their fiscal year and quarter and are excluded "
            "from the quarterly evidence stream rather than assigned to a "
            f"neighbouring quarter: {lost_quarter_ends}."
        )
    if lost_annual_ends:
        identity_notes.append(
            f"{len(lost_annual_ends)} annual periods carry 10-K facts but no "
            "issuer declaration resolving their fiscal year and are excluded: "
            f"{lost_annual_ends}."
        )
    if fiscal_calendar.unresolved:
        identity_notes.append(
            f"{len(fiscal_calendar.unresolved)} fiscal periods remain unresolved by "
            f"issuer declaration and are excluded rather than assigned: "
            f"{[item['period_end'] for item in fiscal_calendar.unresolved]}."
        )
    if fiscal_calendar.warnings:
        identity_notes.append(
            f"{len(fiscal_calendar.warnings)} fiscal identity conflicts were recorded "
            f"and not silently resolved: {fiscal_calendar.warnings}."
        )
    quarter_evidence: List[QuarterEpsEvidence] = []
    annual_evidence: List[QuarterEpsEvidence] = []
    
    for fact in concept_payload["units"]["USD/shares"]:
        if not fact.get("start"):
            continue
        start_d = datetime.date.fromisoformat(fact["start"])
        end_d = datetime.date.fromisoformat(fact["end"])
        span = (end_d - start_d).days
        accn = fact["accn"]
        if accn not in filings_index:
            continue
        filing_meta = filings_index[accn]
        form = filing_meta["form"]
        
        if QUARTER_MIN_DAYS <= span <= QUARTER_MAX_DAYS:
            identity = fiscal_calendar.quarter_identity.get(end_d.isoformat())
            if identity is None:
                # No issuer declaration identifies this period; excluding it is
                # the honest refusal (never a neighbouring-quarter assignment).
                continue
            fy = identity.fiscal_year
            fq = identity.fiscal_quarter
            q_ev = QuarterEpsEvidence(
                evidence_id=f"ev-filed-{accn}-{end_d.isoformat()}",
                issuer_id=issuer_config.issuer_id,
                evidence_class=EVIDENCE_CLASS_FILED,
                form=form,
                accession=accn,
                period_end=end_d.isoformat(),
                period_start=start_d.isoformat(),
                duration_days=span,
                fiscal_year=fy,
                fiscal_quarter=fq,
                value=float(fact["val"]),
                audit_status=AUDIT_STATUS_AUDITED if form == "10-K" else AUDIT_STATUS_REVIEWED,
                acceptance_datetime=filing_meta["acceptance_datetime"],
                usable_date=filing_meta["usable_date"],
                usable_date_rule=filing_meta["usable_date_rule"],
                source_url=f"https://data.sec.gov/api/xbrl/companyconcept/{issuer_config.issuer_id}/us-gaap/EarningsPerShareDiluted.json",
                content_sha256=concept_sha,
                stated_directly=True,
                derivation="directly tagged quarter-length XBRL fact",
                fiscal_position_source=identity.identity_source,
            )
            quarter_evidence.append(q_ev)
        
        elif YEAR_MIN_DAYS <= span <= YEAR_MAX_DAYS and form == "10-K":
            fy = fiscal_calendar.annual_fiscal_year.get(end_d.isoformat())
            if fy is None:
                # Covered by the lost_annual_ends note; skip without guessing.
                continue
            a_ev = QuarterEpsEvidence(
                evidence_id=f"ev-annual-{accn}-{end_d.isoformat()}",
                issuer_id=issuer_config.issuer_id,
                evidence_class=EVIDENCE_CLASS_FILED,
                form=form,
                accession=accn,
                period_end=end_d.isoformat(),
                period_start=start_d.isoformat(),
                duration_days=span,
                fiscal_year=fy,
                fiscal_quarter=4,
                value=float(fact["val"]),
                audit_status=AUDIT_STATUS_AUDITED,
                acceptance_datetime=filing_meta["acceptance_datetime"],
                usable_date=filing_meta["usable_date"],
                usable_date_rule=filing_meta["usable_date_rule"],
                source_url=f"https://data.sec.gov/api/xbrl/companyconcept/{issuer_config.issuer_id}/us-gaap/EarningsPerShareDiluted.json",
                content_sha256=concept_sha,
                stated_directly=True,
                derivation="directly tagged annual XBRL fact",
                fiscal_position_source=IDENTITY_PRIMARY,
            )
            annual_evidence.append(a_ev)
    
    # Furnished Q4 evidence from Form 8-K Item 2.02 EX-99.1
    if enable_furnished and q4_records_path and q4_records_path.exists():
        q4_study = json.loads(q4_records_path.read_text(encoding="utf-8"))
        for rec in q4_study["records"]:
            if rec.get("source_type") != "SEC_8K_ITEM_2_02_EX_99_1" or not rec.get("meets_st_eva_q4_evidence"):
                continue
            period_end_d = datetime.date.fromisoformat(rec["quarter_period_end"])
            acceptance_dt = datetime.datetime.fromisoformat(rec["acceptance_datetime"])
            usable_d, usable_r = resolve_usable_date(acceptance_dt, trading_days)
            # The release itself declares the fiscal year of the quarter it
            # reports ("fourth quarter of fiscal N, which ended <date>"). The
            # issuer's declared annual span for that fiscal year, when already
            # on file, must end on the same date; a disagreement refuses the
            # record instead of silently relabelling either side.
            fy = rec.get("fiscal_year")
            fq = 4
            if not isinstance(fy, int):
                identity_notes.append(
                    f"Furnished Q4 record {rec.get('accession')} is refused: it "
                    "declares no fiscal year for its quarter."
                )
                continue
            declared_year_end = fiscal_calendar.fiscal_year_end(fy)
            if declared_year_end is not None and declared_year_end != rec["quarter_period_end"]:
                identity_notes.append(
                    f"Furnished Q4 record {rec.get('accession')} is refused: its "
                    f"period end {rec['quarter_period_end']} disagrees with the "
                    f"issuer's declared fiscal {fy} annual period end {declared_year_end}."
                )
                continue
            
            furn_ev = QuarterEpsEvidence(
                evidence_id=f"ev-furn-{rec['accession']}-{period_end_d.isoformat()}",
                issuer_id=issuer_config.issuer_id,
                evidence_class=EVIDENCE_CLASS_FURNISHED,
                form="8-K",
                sec_item="Item 2.02",
                accession=rec["accession"],
                period_end=period_end_d.isoformat(),
                period_start=None,
                duration_days=None,
                period_declaration="STATEMENT_COLUMN_LABEL",
                fiscal_year=fy,
                fiscal_quarter=fq,
                value=float(rec["diluted_eps"]),
                audit_status=AUDIT_STATUS_UNAUDITED,
                acceptance_datetime=acceptance_dt.isoformat(),
                usable_date=usable_d,
                usable_date_rule=usable_r,
                source_document=rec.get("document_identifier"),
                source_url=rec.get("source_url"),
                legal_status_note="Form 8-K Item 2.02 furnished not filed for §18 purposes",
                content_sha256=rec.get("content_sha256"),
                stated_directly=True,
                derivation="directly stated in exhibit Three Months Ended column",
                fiscal_position_source="ISSUER_DECLARED_EARNINGS_RELEASE",
                item_2_02_furnished_not_filed=True,
            )
            quarter_evidence.append(furn_ev)
    
    # Compute digest of Q4 records if loaded
    q4_records_hash = None
    if enable_furnished and q4_records_path and q4_records_path.exists():
        q4_records_hash = hashlib.sha256(q4_records_path.read_bytes()).hexdigest()
    
    # Digest every result-affecting input so input_set_id changes deterministically
    # when any of them changes, not just when the furnished Q4 file changes.
    # Paths alone are insufficient: the canonical layout keeps a stable directory,
    # so an edited price or acceptance file would otherwise be indistinguishable.
    input_manifest = {
        "issuer_config": {
            "ticker": issuer_config.ticker,
            "issuer_id": issuer_config.issuer_id,
            "fye_month": issuer_config.fye_month,
        },
        "prices": _sha256_of(prices_path),
        "concepts": _sha256_of(concept_path),
        "acceptances": _acceptance_input_digest(acceptance_path),
        "enable_furnished": enable_furnished,
        "min_observations": min_observations,
    }
    if q4_records_hash:
        input_manifest["q4_records"] = q4_records_hash

    input_set_id = canonical_json_hash(input_manifest)
    
    # Use every evaluation date supported by the loaded evidence. Do not
    # retain a fixed end date from the completed AAPL proof-of-concept dataset:
    # new qualifying evidence should extend the production series naturally.
    evaluation_dates = sorted({
        filing["usable_date"] for filing in filings_index.values()
    } | {
        ev.usable_date for ev in quarter_evidence
    })
    
    current_price = prices_map.get(trading_days[-1])
    
    result = build_historical_pe(
        issuer_id=issuer_config.issuer_id,
        instrument_id=issuer_config.ticker,
        quarter_evidence=quarter_evidence,
        annual_evidence=annual_evidence,
        prices=prices_map,
        fye_month=issuer_config.fye_month,
        trading_days=trading_days,
        evaluation_dates=evaluation_dates,
        current_price_evidence=current_price,
        min_observations=min_observations,
        input_set_id=input_set_id,
    )
    if identity_notes:
        result.summary_notes.extend(identity_notes)
    return result


def load_aapl_historical_pe(
    base_dir: Optional[Path] = None,
    enable_furnished: bool = True,
    min_observations: int = MIN_OBSERVATIONS_FOR_REFERENCE,
) -> HistoricalPeResult:
    """Load AAPL frozen dataset and execute production historical P/E pipeline.
    
    Maintained for backward compatibility. Delegates to load_issuer_historical_pe.
    """
    config = ISSUER_CONFIGS["AAPL"]
    if base_dir:
        config = IssuerHistoricalPeConfig(
            ticker="AAPL",
            issuer_id=config.issuer_id,
            fye_month=config.fye_month,
            data_dir=base_dir,
            canonical_path=None,
        )
    elif (config.data_dir / "daily_prices.json").exists():
        # Use canonical data directory
        pass
    elif config.canonical_path and config.canonical_path.exists():
        # Fall back to research POC
        config = IssuerHistoricalPeConfig(
            ticker="AAPL",
            issuer_id=config.issuer_id,
            fye_month=config.fye_month,
            data_dir=config.canonical_path,
            canonical_path=None,
        )
    
    return load_issuer_historical_pe(config, enable_furnished, min_observations)
