"""
ST-EVA Historical P/E Engine — Production Pipeline.

Baseline: docs/ADR-HISTORICAL-PE-METHODOLOGY.md (Amendment 1, Decisions 10-14)
Contract: docs/methodology/CONTRACT-HISTORICAL-PE.md

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
  F-11: Reason codes are strictly in the closed ADR enumeration.
  F-12: XBRL_FACT_UNAVAILABLE is never an eligibility state.
  F-13: Determinism (identical input_set_id + logic_version -> identical content_hash).
  F-14: Source identity is complete (accession, form, url, content hash).
  F-15: Same accounting metric across classes (GAAP_DILUTED_EPS).
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

ET = ZoneInfo("America/New_York")
UTC = datetime.timezone.utc
CUTOFF_ET = datetime.time(16, 0)

METHODOLOGY = "docs/ADR-HISTORICAL-PE-METHODOLOGY.md"
METHODOLOGY_AMENDMENT = "Amendment 1 (2026-10-07), Decisions 10-14"
LOGIC_VERSION = "historical-pe/1.0.0"
FORMULA_VERSION = "historical-pe/1.0"

# Closed reason code enumeration per ADR and CONTRACT §D.2
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

# Statuses per CONTRACT §D.1
STATUS_AVAILABLE = "AVAILABLE"
STATUS_UNAVAILABLE = "UNAVAILABLE"
STATUS_REFUSED = "REFUSED"

# Distribution qualification statuses
STATUS_USABLE_FOR_REFERENCE = "USABLE_FOR_REFERENCE"
STATUS_INSUFFICIENT_OBSERVATIONS = "INSUFFICIENT_OBSERVATIONS"

# Evidence classes per CONTRACT §B.2
EVIDENCE_CLASS_FILED = "filed"
EVIDENCE_CLASS_FURNISHED = "furnished"
EVIDENCE_CLASS_COMPOSITE = "composite"

# Audit status per CONTRACT §B.2
AUDIT_STATUS_AUDITED = "audited"
AUDIT_STATUS_REVIEWED = "unaudited_reviewed"
AUDIT_STATUS_UNAUDITED = "unaudited"

# Metric IDs per CONTRACT §C.2
METRIC_TTM_GAAP_DILUTED_PE = "TTM_GAAP_DILUTED_PE"
METRIC_ANNUAL_GAAP_DILUTED_PE = "ANNUAL_GAAP_DILUTED_PE"
METRIC_CURRENT_PE = "CURRENT_PE"

# Calendar thresholds
QUARTER_MIN_DAYS = 80
QUARTER_MAX_DAYS = 100
YEAR_MIN_DAYS = 350
YEAR_MAX_DAYS = 380

# Sufficiency threshold per ADR Decision 9 & CONTRACT §K.2
MIN_OBSERVATIONS_FOR_REFERENCE = 20

# Excluded volatile fields for canonical content hash per CONTRACT §I.2
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
# Fiscal calendar derivation (Invariant F-3, CONTRACT §E.1)
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
    return min(months_after // 3, 3)


# ---------------------------------------------------------------------------
# Point-in-time usable date resolver (CONTRACT §E.3)
# ---------------------------------------------------------------------------

def resolve_usable_date(
    acceptance_et: datetime.datetime, trading_days: Sequence[str]
) -> Tuple[str, str]:
    """ADR Decision 3: 16:00 ET cutoff, then the next real trading day.

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
    """One quarter EPS evidence instance per CONTRACT §B.1."""

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
    """Price evidence instance per CONTRACT §B.3."""

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
    """One Historical P/E Observation instance per CONTRACT §C.1."""

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
    """Distribution statistics and reference eligibility gate per CONTRACT §C & §K."""

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
# Core Pipeline Resolver Sequence (CONTRACT §E)
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
            # Anchor on greatest fiscal-quarter position with known evidence
            anchor = ends_sorted[-1]
            anchor_year = fiscal_year_of(anchor, fye_month)
            anchor_number = quarter_number(anchor, fye_month)

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
                    if fiscal_year_of(end, fye_month) == pos_y and quarter_number(end, fye_month) == pos_q
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

        eps_state = {
            "status": STATUS_AVAILABLE if not missing_positions and ttm_components else STATUS_UNAVAILABLE,
            "window_anchor": {
                "fiscal_year": positions[-1][0],
                "fiscal_quarter": positions[-1][1],
            } if known_quarters else None,
            "quarter_denominator": round(sum(c["value"] for c in ttm_components), 6) if not missing_positions and ttm_components else None,
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

        # Build ANNUAL_GAAP_DILUTED_PE per CONTRACT §C.3
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

    # Current snapshot observation (CONTRACT §C.2, Invariant F-10)
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

        if known_quarters_cur:
            anchor_cur = max(known_quarters_cur.keys())
            pos_cur = []
            cy = fiscal_year_of(anchor_cur, fye_month)
            cq = quarter_number(anchor_cur, fye_month)
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
                    if fiscal_year_of(end, fye_month) == py and quarter_number(end, fye_month) == pq
                ]
                if m:
                    cur_components.append(known_quarters_cur[m[-1]].to_dict())
                else:
                    cur_missing.append({"fiscal_year": py, "fiscal_quarter": pq})

            if cur_missing:
                cur_ttm_reason = REASON_MISSING_Q4_EPS if any(p["fiscal_quarter"] == 4 for p in cur_missing) else REASON_INSUFFICIENT_QUARTERS
            else:
                total_eps_cur = sum(c["value"] for c in cur_components)
                if total_eps_cur > 0 and cur_p_val is not None:
                    cur_ttm_status = STATUS_AVAILABLE
                    cur_ttm_val = cur_p_val / total_eps_cur
                elif total_eps_cur <= 0:
                    cur_ttm_reason = REASON_NON_POSITIVE_EPS

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
            eps_state={"components": cur_components, "missing_quarters": cur_missing},
            price_state={"price_date": cur_day, "close": cur_p_val},
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

def load_aapl_historical_pe(
    base_dir: Optional[Path] = None,
    enable_furnished: bool = True,
    min_observations: int = MIN_OBSERVATIONS_FOR_REFERENCE,
) -> HistoricalPeResult:
    """Load AAPL frozen dataset and execute production historical P/E pipeline."""
    if base_dir is None:
        base_dir = Path("research/experiments/aapl-historical-pe-poc")

    raw_dir = base_dir / "raw"
    q4_out_dir = base_dir / "q4_study" / "out"

    prices_path = raw_dir / "daily_prices.json"
    concept_path = raw_dir / "eps_diluted_concept.json"
    acceptance_path = raw_dir / "filing_acceptance_evidence.json"
    q4_records_path = q4_out_dir / "q4_evidence_records.json"

    price_payload = json.loads(prices_path.read_text(encoding="utf-8"))["chart"]["result"][0]
    quote = price_payload["indicators"]["quote"][0]
    bars = {
        datetime.datetime.fromtimestamp(stamp, UTC).date().isoformat(): float(quote["close"][idx])
        for idx, stamp in enumerate(price_payload["timestamp"])
        if quote["close"][idx] is not None
    }
    trading_days = sorted(bars.keys())

    split_stamp = min(price_payload["events"]["splits"].keys())
    split_entry = price_payload["events"]["splits"][split_stamp]
    split_ex_date = datetime.datetime.fromtimestamp(int(split_stamp), UTC).date().isoformat()
    split_ratio = float(split_entry["numerator"]) / float(split_entry["denominator"])

    # Build price evidence with as-traded close restoration
    prices_map: Dict[str, HistoricalPriceEvidence] = {}
    for day, close in bars.items():
        restored_close = close
        provenance = []
        if split_ex_date > day:
            restored_close = close * split_ratio
            provenance.append({
                "ex_date": split_ex_date,
                "split_ratio": split_entry["splitRatio"],
                "vendor_adjusted_close": close,
                "restored_as_traded_close": restored_close,
            })
        prices_map[day] = HistoricalPriceEvidence(
            price_evidence_id=f"price-AAPL-{day}",
            issuer_id="CIK0000320193",
            instrument_id="AAPL",
            price_date=day,
            close=round(restored_close, 4),
            currency="USD",
            accounting_basis="as_traded",
            corporate_action_provenance=tuple(provenance),
        )

    # AAPL Fiscal Year End month is 9 (September)
    fye_month = 9

    # Filing acceptance evidence
    acceptance_evidence = json.loads(acceptance_path.read_text(encoding="utf-8"))
    concept_sha = hashlib.sha256(concept_path.read_bytes()).hexdigest()

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

    # Quarterly and annual evidence from filed XBRL facts
    concept_payload = json.loads(concept_path.read_text(encoding="utf-8"))
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
            fy = fiscal_year_of(end_d, fye_month)
            fq = quarter_number(end_d, fye_month)
            q_ev = QuarterEpsEvidence(
                evidence_id=f"ev-filed-{accn}-{end_d.isoformat()}",
                issuer_id="CIK0000320193",
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
                source_url="https://data.sec.gov/api/xbrl/companyconcept/CIK0000320193/us-gaap/EarningsPerShareDiluted.json",
                content_sha256=concept_sha,
                stated_directly=True,
                derivation="directly tagged quarter-length XBRL fact",
            )
            quarter_evidence.append(q_ev)

        elif YEAR_MIN_DAYS <= span <= YEAR_MAX_DAYS and form == "10-K":
            fy = fiscal_year_of(end_d, fye_month)
            a_ev = QuarterEpsEvidence(
                evidence_id=f"ev-annual-{accn}-{end_d.isoformat()}",
                issuer_id="CIK0000320193",
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
                source_url="https://data.sec.gov/api/xbrl/companyconcept/CIK0000320193/us-gaap/EarningsPerShareDiluted.json",
                content_sha256=concept_sha,
                stated_directly=True,
                derivation="directly tagged annual XBRL fact",
            )
            annual_evidence.append(a_ev)

    # Furnished Q4 evidence from Form 8-K Item 2.02 EX-99.1
    if enable_furnished and q4_records_path.exists():
        q4_study = json.loads(q4_records_path.read_text(encoding="utf-8"))
        for rec in q4_study["records"]:
            if rec.get("source_type") != "SEC_8K_ITEM_2_02_EX_99_1" or not rec.get("meets_st_eva_q4_evidence"):
                continue
            period_end_d = datetime.date.fromisoformat(rec["quarter_period_end"])
            acceptance_dt = datetime.datetime.fromisoformat(rec["acceptance_datetime"])
            usable_d, usable_r = resolve_usable_date(acceptance_dt, trading_days)
            fy = fiscal_year_of(period_end_d, fye_month)
            fq = 4

            furn_ev = QuarterEpsEvidence(
                evidence_id=f"ev-furn-{rec['accession']}-{period_end_d.isoformat()}",
                issuer_id="CIK0000320193",
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
                item_2_02_furnished_not_filed=True,
            )
            quarter_evidence.append(furn_ev)

    input_manifest = {
        "prices": str(prices_path),
        "concepts": str(concept_path),
        "acceptances": str(acceptance_path),
        "enable_furnished": enable_furnished,
    }
    input_set_id = canonical_json_hash(input_manifest)

    # Use evaluation dates from 2019-01-30 to 2026-10-06 matching POC and CONTRACT §E.4
    poc_eval_dates = sorted({
        filing["usable_date"] for filing in filings_index.values()
        if "2019-01-30" <= filing["usable_date"] <= "2026-10-06"
    } | {
        ev.usable_date for ev in quarter_evidence
        if "2019-01-30" <= ev.usable_date <= "2026-10-06"
    })

    current_price = prices_map.get(trading_days[-1])

    return build_historical_pe(
        issuer_id="CIK0000320193",
        instrument_id="AAPL",
        quarter_evidence=quarter_evidence,
        annual_evidence=annual_evidence,
        prices=prices_map,
        fye_month=fye_month,
        trading_days=trading_days,
        evaluation_dates=poc_eval_dates,
        current_price_evidence=current_price,
        min_observations=min_observations,
        input_set_id=input_set_id,
    )
