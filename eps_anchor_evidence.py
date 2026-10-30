"""
Traceable EPS anchors for the reverse-requirements matrix.

The matrix needs one EPS figure to start its growth bridge from, and that figure
has to be able to say what it is. This module builds the *catalogue* of EPS
figures an issuer actually has evidence for, each carrying its own identity, and
nothing else: no valuation, no ratio, no forecast. It exists because the
existing starting anchor is a supplier field (`defaultKeyStatistics.trailingEps`)
whose payload declares no period, no accounting basis and no publication time,
so a reader cannot tell a twelve-month figure from a fiscal-year one.

Three kinds of anchor are distinguished, and the distinctions are the point:

- the **supplier** anchors, which carry the provider field and endpoint that
  recorded them and are marked `PROVIDER_REPORTED` with an undeclared basis;
- the **directly stated annual** anchor, one filed `us-gaap:EarningsPerShareDiluted`
  fact of a `10-K` fiscal year, marked `DIRECT_FILING` on a declared GAAP basis;
- the **derived twelve-month** anchor, the sum of four directly stated discrete
  quarters, marked `DERIVED_FROM_DIRECT_FILINGS` because the sum is this
  module's arithmetic and no issuer stated it.

An annual anchor never presents itself as a trailing figure and a derived sum
never presents itself as an issuer statement. Both keep their own period, their
own accession and form, and their own public availability date, and the derived
anchor keeps each of its four components so a reader can check the sum.

**Rules this module refuses to bend.**

1. *Point in time.* A fact published after the valuation date is not an input.
   The same 16:00 ET close discipline the historical P/E reference uses applies:
   a filing accepted before 16:00 ET on the valuation date is knowable that day,
   one accepted at or after it is not. A fact whose source declares only a
   filed *date*, with no time of day, is refused when that date is the valuation
   date itself, because nothing shows it preceded the close. A fact with no
   declared publication time at all is never an input.
2. *Enough evidence or nothing.* Four consecutive directly stated quarters, or no
   twelve-month anchor. Three quarters plus a gap is not a trailing figure and is
   not completed by arithmetic across the gap.
3. *Numerical agreement is not provenance.* A supplier figure that happens to
   equal a filed figure is still the supplier figure, and the two anchors stay
   separate entries. Only identity (accession, form, period, concept, unit)
   attaches a filing to an anchor.
4. *No reconciliation by adjustment.* When the four-quarter sum and the audited
   annual figure for the *same* window disagree, both numbers are kept and the
   basis difference is explained. Per-share amounts are not strictly additive
   across a changing share denominator, and nothing here invents a reconciling
   item.

Nothing in this module widens the archive valuation boundary in
`evidence_valuation_boundary.py`. That boundary admits `revenue` only and still
refuses `eps_diluted` by name; the starting-EPS anchor is a separate, separately
tested route, and widening the boundary to every SEC financial metric is out of
scope.
"""

from __future__ import annotations
import re

import datetime
import json
import math
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from data_contract import (
    QUARTER_MAX_DAYS,
    QUARTER_MIN_DAYS,
    YEAR_MAX_DAYS,
    YEAR_MIN_DAYS,
)
from reverse_requirements import (
    ANCHOR_FISCAL_YEAR,
    ANCHOR_FORWARD,
    ANCHOR_TTM,
    EpsAnchor,
)

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

# The stable identifier of each selectable anchor. The supplier ids keep the
# provider's own words so a reader can see which field the figure came from.
ANCHOR_SUPPLIER_TRAILING = "SUPPLIER_TRAILING_EPS"
ANCHOR_SUPPLIER_FORWARD = "SUPPLIER_FORWARD_EPS"
ANCHOR_SUPPLIER_CONSENSUS = "SUPPLIER_CONSENSUS_FORWARD_EPS"
ANCHOR_SEC_ANNUAL = "SEC_ANNUAL_DILUTED_EPS"
ANCHOR_SEC_TTM_FOUR_QUARTERS = "SEC_TTM_FOUR_QUARTERS"

ANCHOR_SEC_ANNUAL_CLASS_A = "SEC_ANNUAL_DILUTED_EPS_CLASS_A"
ANCHOR_SEC_ANNUAL_CLASS_B = "SEC_ANNUAL_DILUTED_EPS_CLASS_B"
ANCHOR_SEC_ANNUAL_CLASS_C = "SEC_ANNUAL_DILUTED_EPS_CLASS_C"

SEC_EPS_ANCHOR_IDS: Tuple[str, ...] = (
    ANCHOR_SUPPLIER_TRAILING,
    ANCHOR_SUPPLIER_FORWARD,
    ANCHOR_SUPPLIER_CONSENSUS,
    ANCHOR_SEC_ANNUAL,
    ANCHOR_SEC_ANNUAL_CLASS_A,
    ANCHOR_SEC_ANNUAL_CLASS_B,
    ANCHOR_SEC_ANNUAL_CLASS_C,
    ANCHOR_SEC_TTM_FOUR_QUARTERS,
)

# How the figure came to be. This is the field that stops an annual figure, a
# derived sum and a provider field from reading identically.
NATURE_PROVIDER_REPORTED = "PROVIDER_REPORTED"
NATURE_DIRECT_FILING = "DIRECT_FILING"
NATURE_DERIVED = "DERIVED_FROM_DIRECT_FILINGS"
NATURE_USER_SUPPLIED = "USER_SUPPLIED"

# The accounting basis, as declared by the source. The supplier fields declare
# none, which is recorded as such rather than read as GAAP.
GAAP_BASIS_UNDECLARED = "UNDECLARED"
GAAP_BASIS_DILUTED = "GAAP_DILUTED_EPS"

SEC_EPS_CONCEPT = "us-gaap:EarningsPerShareDiluted"
SEC_EPS_UNITS: Tuple[str, ...] = ("USD/shares", "USD-per-shares", "USD per share")
SEC_EPS_SOURCE_PROVIDER = "SecEdgar"

SHARE_CLASS_SCOPE_CLASS_A = "CLASS_A"
SHARE_CLASS_SCOPE_CLASS_B = "CLASS_B"
SHARE_CLASS_SCOPE_CLASS_C = "CLASS_C"
SHARE_CLASS_SCOPE_CONSOLIDATED = "CONSOLIDATED"
SHARE_CLASS_SCOPE_NOT_APPLICABLE = "NOT_APPLICABLE"
SHARE_CLASS_SCOPE_UNKNOWN = "UNKNOWN"
SHARE_CLASS_SCOPES = (
    SHARE_CLASS_SCOPE_CLASS_A,
    SHARE_CLASS_SCOPE_CLASS_B,
    SHARE_CLASS_SCOPE_CLASS_C,
    SHARE_CLASS_SCOPE_CONSOLIDATED,
    SHARE_CLASS_SCOPE_NOT_APPLICABLE,
    SHARE_CLASS_SCOPE_UNKNOWN,
)
# Availability bases, kept distinct because they answer different questions: an
# acceptance instant states when the filing entered the public record, a filed
# date only states the calendar day EDGAR stamped.
AVAILABILITY_ACCEPTANCE_DATETIME = "ACCEPTANCE_DATETIME"
AVAILABILITY_FILED_AS_OF_DATE = "FILED_AS_OF_DATE"
AVAILABILITY_UNDECLARED = "UNDECLARED"

KNOWABLE_ACCEPTANCE_BEFORE_CLOSE = "acceptance_before_1600ET_on_or_before_valuation_date"
KNOWABLE_ACCEPTANCE_EARLIER_DATE = "acceptance_on_an_earlier_date_than_valuation_date"
KNOWABLE_FILED_EARLIER_DATE = "filed_on_an_earlier_date_than_valuation_date"

# The point-in-time discipline. It is the historical P/E reference's own rule
# (`historical_pe.CUTOFF_ET`), restated here because this module must not depend
# on that engine's inputs, and applied to the same question: was the filing
# public before the closing print the valuation date is taken at?
CUTOFF_ET = datetime.time(16, 0)
ET = ZoneInfo("America/New_York")

# The gap a declared quarter boundary may leave between two consecutive
# quarters. Issuers that restate a boundary move it by a day or two; a larger
# jump means a quarter is missing and the window is not a twelve-month window.
MAX_CONTIGUITY_GAP_DAYS = 4

# The agreement allowed between a four-quarter sum and an audited annual figure
# over the *same* window before the two are reported as a basis difference. It is
# a reporting threshold, not a reconciliation allowance: above it both numbers
# are kept and neither is adjusted.
SUM_VS_ANNUAL_TOLERANCE = 0.005

# Averaged Gregorian month, so a declared span in days converts to a declared
# coverage in months without pretending to day-level precision.
DAYS_PER_MONTH = 365.2425 / 12.0

_PACKAGED_ROOT = os.path.join("data", "historical_pe")

# Refusal labels. Each names a specific missing or disqualifying fact, so a
# refused anchor can be told apart from another refused anchor.
REFUSAL_NO_DATASET = "NO_PACKAGED_SEC_EPS_DATASET"
REFUSAL_NO_ANNUAL_FACT = "NO_DIRECTLY_STATED_ANNUAL_EPS_FACT"
REFUSAL_ANNUAL_NOT_KNOWABLE = "ANNUAL_EPS_FACT_NOT_KNOWABLE_AT_VALUATION_DATE"
REFUSAL_INCOMPLETE_QUARTERS = "FOUR_CONSECUTIVE_DIRECT_QUARTERS_NOT_AVAILABLE"
REFUSAL_QUARTERS_NOT_KNOWABLE = "QUARTERLY_EPS_FACTS_NOT_KNOWABLE_AT_VALUATION_DATE"
REFUSAL_WINDOW_START_UNANCHORED = "TWELVE_MONTH_WINDOW_START_NOT_ANCHORED_BY_A_DECLARED_QUARTER"
REFUSAL_WINDOW_SPAN = "FOUR_QUARTERS_DO_NOT_SPAN_A_YEAR"
REFUSAL_NOT_POSITIVE = "EPS_NOT_POSITIVE"
REFUSAL_UNKNOWN_ANCHOR_ID = "UNKNOWN_EPS_ANCHOR_ID"
REFUSAL_SUPPLIER_NOT_OBSERVED = "SUPPLIER_EPS_NOT_OBSERVED_IN_THIS_RUN"

SELECTION_RULE = (
    "The starting EPS anchor is one entry of the issuer's EPS anchor catalogue. "
    "Each entry names its value, the period it covers, the source that recorded "
    "it, its accounting basis as declared by that source, when it became public, "
    "and whether it is provider-reported, directly filed or derived. An anchor "
    "named explicitly is used only if it is available; an unavailable one is "
    "refused with its reason and is never replaced by a different figure."
)


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EpsFactRecord:
    """
    One directly stated diluted-EPS fact, whatever filing stated it.

    Every field is read from the filing's own payload. `period_start` is None
    when the source states only the period end (an Item 2.02 exhibit names the
    quarter it closes and no start date), and stays None rather than being
    inferred from the value or from a sibling fact.
    """

    period_start: Optional[str]
    period_end: str
    value: float
    form: str
    accession: str
    filed: Optional[str]
    acceptance_datetime: Optional[str]
    available_at: Optional[str]
    available_at_basis: str
    # "filed" for a periodic report the issuer files, "furnished" for an Item 2.02
    # earnings release the issuer furnishes. The distinction is carried because
    # a furnished quarter is unaudited and the audited annual is not.
    evidence_class: str
    fiscal_year: Optional[Any] = None
    fiscal_period: Optional[str] = None
    fiscal_quarter: Optional[Any] = None
    source_url: Optional[str] = None
    # Raw EPS fact identity (Phase 2). These preserve the source fact without
    # overwriting the normalized Observation.
    concept_qname: str = SEC_EPS_CONCEPT
    context_ref: Optional[str] = None
    dimensions: Tuple[Dict[str, Any], ...] = ()
    unit: str = "USD/shares"
    decimals: Optional[str] = None
    raw_value: Optional[float] = None
    normalized_value: Optional[float] = None
    source_kind: str = "SEC"
    assurance_status: str = "UNDECLARED"
    derived_status: str = "DIRECT"
    derivation_description: str = ""
    share_class_scope: str = SHARE_CLASS_SCOPE_UNKNOWN

    def __post_init__(self) -> None:
        if self.raw_value is None:
            object.__setattr__(self, "raw_value", self.value)
        if self.normalized_value is None:
            object.__setattr__(self, "normalized_value", self.value)
        if not self.derivation_description:
            object.__setattr__(self, "derivation_description", "")

    @property
    def derivation(self) -> str:
        return self.derivation_description

    @property
    def span_days(self) -> Optional[int]:
        return _span_days(self.period_start, self.period_end)

    def is_annual(self) -> bool:
        span = self.span_days
        return span is not None and YEAR_MIN_DAYS <= span <= YEAR_MAX_DAYS

    def is_discrete_quarter(self) -> bool:
        span = self.span_days
        return span is not None and QUARTER_MIN_DAYS <= span <= QUARTER_MAX_DAYS

    def component_view(self) -> Dict[str, Any]:
        """The component's identity, as the audit surface and export show it."""
        return {
            "period_start": self.period_start,
            "period_end": self.period_end,
            "value": self.value,
            "form": self.form,
            "accession": self.accession,
            "filed_date": self.filed,
            "acceptance_datetime": self.acceptance_datetime,
            "available_at": self.available_at,
            "available_at_basis": self.available_at_basis,
            "evidence_class": self.evidence_class,
            "fiscal_year": self.fiscal_year,
            "fiscal_period": self.fiscal_period,
            "fiscal_quarter": self.fiscal_quarter,
            "concept_qname": self.concept_qname,
            "context_ref": self.context_ref,
            "dimensions": [dict(item) for item in self.dimensions],
            "unit": self.unit,
            "decimals": self.decimals,
            "raw_value": self.raw_value,
            "normalized_value": self.normalized_value,
            "source_kind": self.source_kind,
            "assurance_status": self.assurance_status,
            "derived_status": self.derived_status,
            "derivation_description": self.derivation_description,
            "share_class_scope": self.share_class_scope,
            "concept": SEC_EPS_CONCEPT,
            "gaap_basis": GAAP_BASIS_DILUTED,
            "source_url": self.source_url,
        }


@dataclass(frozen=True)
class EpsAnchorCandidate:
    """
    One selectable EPS anchor, with the identity a reader needs to judge it.

    An unavailable entry is retained rather than dropped, carrying the reason it
    could not be offered. That is what lets a caller answer "why is there no
    twelve-month filing anchor for this issuer" instead of showing nothing.
    """

    anchor_id: str
    available: bool
    basis: str = ""
    value: Optional[float] = None
    months_covered: float = 0.0
    nature: str = ""
    gaap_basis: str = GAAP_BASIS_UNDECLARED
    source_label: str = ""
    source_provider: str = ""
    source_url: Optional[str] = None
    source_field: Optional[str] = None
    period_label: str = ""
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    period_undeclared_by_source: bool = False
    available_at: Optional[str] = None
    available_at_basis: str = AVAILABILITY_UNDECLARED
    # The single filing that stated a directly reported anchor. Absent for a
    # derived anchor, whose evidence is the component list instead.
    sec_fact: Optional[Dict[str, Any]] = None
    # The four directly stated quarters a derived anchor sums, in period order.
    sec_components: Tuple[Dict[str, Any], ...] = ()
    derivation: str = ""
    # The audited annual figure beside a derived window over the same period, or
    # the statement that the two windows are not the same and were not compared.
    annual_comparison: Optional[Dict[str, Any]] = None
    # The run observation whose value a supplier anchor reports, when the run
    # recorded one. A filing anchor's identity is the accession instead.
    observation_id: Optional[str] = None
    refusal_code: str = ""
    refusal_reason: str = ""
    share_class_scope: str = SHARE_CLASS_SCOPE_UNKNOWN

    def contract_view(self) -> Dict[str, Any]:
        return {
            "anchor_id": self.anchor_id,
            "available": self.available,
            "basis": self.basis,
            "value": self.value,
            "months_covered": self.months_covered,
            "nature": self.nature,
            "gaap_basis": self.gaap_basis,
            "source_label": self.source_label,
            "source_provider": self.source_provider,
            "source_url": self.source_url,
            "source_field": self.source_field,
            "period_label": self.period_label,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "period_undeclared_by_source": self.period_undeclared_by_source,
            "available_at": self.available_at,
            "available_at_basis": self.available_at_basis,
            "sec_fact": self.sec_fact,
            "sec_components": [dict(item) for item in self.sec_components],
            "derivation": self.derivation,
            "annual_comparison": self.annual_comparison,
            "observation_id": self.observation_id,
            "refusal_code": self.refusal_code,
            "refusal_reason": self.refusal_reason,
            "share_class_scope": self.share_class_scope,
        }


@dataclass(frozen=True)
class EpsAnchorCandidateSet:
    """The whole catalogue for one issuer at one valuation date."""

    ticker: str
    valuation_date: str
    currency: Optional[str]
    candidates: Tuple[EpsAnchorCandidate, ...]
    evidence_inputs: Dict[str, Any] = field(default_factory=dict)

    def available_ids(self) -> Tuple[str, ...]:
        return tuple(c.anchor_id for c in self.candidates if c.available)

    def get(self, anchor_id: str) -> Optional[EpsAnchorCandidate]:
        for candidate in self.candidates:
            if candidate.anchor_id == anchor_id:
                return candidate
        return None

    def contract_view(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "valuation_date": self.valuation_date,
            "currency": self.currency,
            "selection_rule": SELECTION_RULE,
            "candidates": [c.contract_view() for c in self.candidates],
            "available_anchor_ids": list(self.available_ids()),
            "evidence_inputs": dict(self.evidence_inputs),
        }


# ---------------------------------------------------------------------------
# Small readers
# ---------------------------------------------------------------------------

def _safe_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def _iso_date(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.date.fromisoformat(value.strip()).isoformat()
    except ValueError:
        return None


def _iso_instant(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.isoformat()


def _parse_aware(value: Any) -> Optional[datetime.datetime]:
    instant = _iso_instant(value)
    if instant is None:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(instant)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _span_days(start: Optional[str], end: Optional[str]) -> Optional[int]:
    """The days a declared period covers, or None when a boundary is undeclared."""
    start_date = _iso_date(start)
    end_date = _iso_date(end)
    if not start_date or not end_date:
        return None
    try:
        return (datetime.date.fromisoformat(end_date) - datetime.date.fromisoformat(start_date)).days
    except ValueError:
        return None


def _document_url(cik: Optional[str], accession: Optional[str]) -> Optional[str]:
    if not cik or not accession:
        return None
    digits = "".join(ch for ch in str(cik) if ch.isdigit()).lstrip("0") or "0"
    return (
        f"https://www.sec.gov/Archives/edgar/data/{digits}/"
        f"{str(accession).replace('-', '')}/{accession}-index.htm"
    )


# ---------------------------------------------------------------------------
# Point in time
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Knowability:
    """Whether a publication instant was public before the valuation date's close."""

    knowable: bool
    rule: str
    detail: str


def resolve_knowability(
    *,
    available_at: Optional[str],
    available_at_basis: str,
    valuation_date: Optional[str],
) -> Knowability:
    """
    Was this fact public before the valuation date's closing print?

    The 16:00 ET cutoff is the historical P/E reference's own rule: an EDGAR
    acceptance stamped at or after 16:00 ET entered the record after the close,
    so a valuation taken at that close could not have used it. A source that
    declares only a calendar date carries no time of day, and nothing shows such
    a filing preceded the close, so a fact filed *on* the valuation date is
    refused rather than admitted. A fact with no declared publication time is
    never knowable at any date.
    """
    as_of = _iso_date(valuation_date)
    if not available_at or not as_of:
        return Knowability(
            False,
            "no_publication_time_declared",
            (
                "The source declared no acceptance time or filed date for this "
                "fact, so it cannot be shown to have been public on the "
                f"valuation date {as_of or valuation_date}."
            ),
        )

    moment = _parse_aware(available_at)
    if moment is not None:
        local = moment.astimezone(ET)
        published = local.date().isoformat()
        if published < as_of:
            return Knowability(
                True,
                KNOWABLE_ACCEPTANCE_EARLIER_DATE,
                f"Accepted {published} (ET), before the {as_of} valuation date.",
            )
        if published > as_of:
            return Knowability(
                False,
                "acceptance_after_valuation_date",
                (
                    f"Accepted {published} (ET), after the {as_of} valuation "
                    "date, so it was not available as an input at that date."
                ),
            )
        if local.time() < CUTOFF_ET:
            return Knowability(
                True,
                KNOWABLE_ACCEPTANCE_BEFORE_CLOSE,
                (
                    f"Accepted {local.strftime('%H:%M')} ET on the valuation "
                    f"date {as_of}, before the 16:00 ET close."
                ),
            )
        return Knowability(
            False,
            "acceptance_at_or_after_1600ET_on_valuation_date",
            (
                f"Accepted {local.strftime('%H:%M')} ET on the valuation date "
                f"{as_of}, at or after the 16:00 ET close, so it was not "
                "available to a valuation taken at that close."
            ),
        )

    filed = _iso_date(available_at)
    if filed is None:
        return Knowability(
            False,
            "unreadable_publication_date",
            f"The declared publication date {available_at!r} could not be read.",
        )
    if filed < as_of:
        return Knowability(
            True,
            KNOWABLE_FILED_EARLIER_DATE,
            f"Filed {filed}, before the {as_of} valuation date.",
        )
    return Knowability(
        False,
        "filed_on_valuation_date_without_declared_time",
        (
            f"Filed {filed}, the valuation date itself, with no declared time of "
            "day. Nothing shows the filing preceded the 16:00 ET close, so it is "
            "refused rather than admitted."
        ),
    )


def _availability_from(
    acceptance_datetime: Optional[str],
    filed: Optional[str],
) -> Tuple[Optional[str], str]:
    """The publication instant a source declares, preferring the acceptance stamp."""
    moment = _parse_aware(acceptance_datetime)
    if moment is not None:
        return moment.isoformat(), AVAILABILITY_ACCEPTANCE_DATETIME
    filed_date = _iso_date(filed)
    if filed_date:
        return f"{filed_date}T00:00:00+00:00", AVAILABILITY_FILED_AS_OF_DATE
    return None, AVAILABILITY_UNDECLARED


# ---------------------------------------------------------------------------
# SEC fact sources
# ---------------------------------------------------------------------------

def share_class_scope_from_dimensions(dimensions: Any) -> str:
    """Derive a share-class scope from raw XBRL dimensions only.

    No dimension means an entity-level fact. A recognised class-of-stock
    dimension maps to its class. Anything unrecognised is kept as UNKNOWN; it is
    never promoted to CONSOLIDATED and never inferred from a ticker.
    """
    items = dimensions or ()
    has_dimensions = False
    for item in items:
        if not isinstance(item, dict):
            continue
        has_dimensions = True
        axis = str(item.get("axis") or item.get("dimension") or "")
        axis_local = axis.rsplit(":", 1)[-1] if ":" in axis else axis
        if "ClassOfStock" not in axis_local and "classofstock" not in axis_local.lower():
            continue
        member = item.get("member")
        typed = item.get("typed")
        text = str(member if member is not None else typed or "")
        haystack = (text + " " + axis_local).lower()
        # Remove separators so "Class A", "ClassA", "CommonClassAMember" match.
        compact = "".join(ch for ch in haystack if ch.isalnum())
        if "classa" in compact:
            return SHARE_CLASS_SCOPE_CLASS_A
        if "classb" in compact:
            return SHARE_CLASS_SCOPE_CLASS_B
        if "classc" in compact:
            return SHARE_CLASS_SCOPE_CLASS_C
        return SHARE_CLASS_SCOPE_UNKNOWN
    if not has_dimensions:
        return SHARE_CLASS_SCOPE_CONSOLIDATED
    return SHARE_CLASS_SCOPE_UNKNOWN


# Aliases for callers that name the same operation differently.
classify_share_class_scope = share_class_scope_from_dimensions
share_class_scope_of = share_class_scope_from_dimensions
derive_share_class_scope = share_class_scope_from_dimensions
normalize_share_class_scope = share_class_scope_from_dimensions


def _records_from_companyconcept(
    payload: Dict[str, Any],
) -> List[EpsFactRecord]:
    """
    Directly stated `EarningsPerShareDiluted` facts from a SEC companyconcept slice.

    A `companyconcept` payload is a `companyfacts` slice, so it carries each
    fact's own form, fiscal period, period, accession and filed date. Cumulative
    spans are kept here and filtered later by span, because whether a span is a
    quarter or a year is a question about its dates, not about its form.
    """
    units = payload.get("units") or {}
    raw_facts = units.get("USD/shares")
    if raw_facts is None:
        for unit in SEC_EPS_UNITS:
            if units.get(unit):
                raw_facts = units[unit]
                break
    if not isinstance(raw_facts, list):
        return []
    cik = payload.get("cik")

    records: List[EpsFactRecord] = []
    for item in raw_facts:
        if not isinstance(item, dict):
            continue
        value = _safe_float(item.get("val"))
        period_end = _iso_date(item.get("end"))
        accession = item.get("accn") or item.get("accession")
        if value is None or not period_end or not accession:
            continue
        filed = _iso_date(item.get("filed"))
        available_at, basis = _availability_from(None, filed)
        unit = str(item.get("unit") or "UNKNOWN")
        records.append(
            EpsFactRecord(
                period_start=_iso_date(item.get("start")),
                period_end=period_end,
                value=value,
                form=str(item.get("form") or ""),
                accession=str(accession),
                filed=filed,
                acceptance_datetime=None,
                available_at=available_at,
                available_at_basis=basis,
                # A periodic report is filed. A company's own inline XBRL is the
                # filed statement even where the period is a comparative.
                evidence_class="filed",
                fiscal_year=item.get("fy"),
                fiscal_period=str(item.get("fp") or "") or None,
                source_url=_document_url(cik, accession),
                concept_qname=SEC_EPS_CONCEPT,
                context_ref=None,
                dimensions=(),
                unit=unit,
                decimals=item.get("decimals"),
                raw_value=value,
                normalized_value=value,
                source_kind="SEC_COMPANYCONCEPT",
                assurance_status="UNKNOWN",
                derived_status="DIRECT",
                derivation_description="",
                share_class_scope=SHARE_CLASS_SCOPE_CONSOLIDATED,
            )
        )
    return records


def _records_from_furnished_quarters(
    payload: Dict[str, Any],
) -> Tuple[List[EpsFactRecord], List[Dict[str, Any]]]:
    """
    Fiscal fourth-quarter facts an issuer *furnished* in an Item 2.02 exhibit.

    A periodic report does not state its own fourth quarter as a discrete period,
    so a directly stated fourth quarter exists only where the issuer furnished
    one. These are real filed-period numbers with their own accession and
    acceptance time, but they are unaudited, which is why the anchor that sums
    them says so. A record that declined the ST-EVA evidence test, or whose
    figure was produced by subtracting a year-to-date from a fiscal year, is not
    read at all: those refusals belong to the study that made them and are
    returned here only so the caller can state them.
    """
    records: List[EpsFactRecord] = []
    declined: List[Dict[str, Any]] = []
    for item in payload.get("records") or []:
        if not isinstance(item, dict):
            continue
        accession = str(item.get("accession") or "")
        period_end = _iso_date(item.get("quarter_period_end") or item.get("period_end"))
        value = _safe_float(item.get("diluted_eps"))
        label = f"{accession or 'unknown accession'} {item.get('form') or ''} {period_end or ''}".strip()

        if not item.get("meets_st_eva_q4_evidence"):
            declined.append({"record": label, "reason": str(item.get("refusal_reason") or "does not meet the Q4 evidence test")})
            continue
        if item.get("fy_minus_ytd_used"):
            declined.append({"record": label, "reason": "derived by subtracting a year-to-date figure"})
            continue
        if not (accession and period_end and value is not None):
            declined.append({"record": label, "reason": "accession, quarter period end or diluted EPS is missing"})
            continue
        # A quarter figure is only read from an exhibit that states it directly.
        # The two packaging shapes record that differently: one flags
        # `stated_directly`, the other states the headline and the statement
        # column agree. Neither flag present means the extraction did not say
        # how the figure was read, which is not the same as saying it was read
        # directly.
        stated_directly = item.get("stated_directly")
        headline = _safe_float(item.get("diluted_eps_headline_statement"))
        headline_agrees = headline is not None and abs(headline - value) <= SUM_VS_ANNUAL_TOLERANCE
        if stated_directly is not True and not headline_agrees:
            declined.append({
                "record": label,
                "reason": "the exhibit does not state that the quarterly figure was read directly",
            })
            continue

        acceptance = item.get("acceptance_datetime")
        available_at, basis = _availability_from(acceptance, None)
        records.append(
            EpsFactRecord(
                period_start=_iso_date(item.get("quarter_period_start")),
                period_end=period_end,
                value=value,
                form=str(item.get("form") or "8-K"),
                accession=accession,
                filed=_iso_date(item.get("usable_date") or item.get("pit_usable_date")),
                acceptance_datetime=_iso_instant(acceptance),
                available_at=available_at,
                available_at_basis=basis,
                evidence_class="furnished",
                fiscal_year=item.get("fiscal_year"),
                fiscal_period=str(item.get("sec_item") or "") or None,
                fiscal_quarter=item.get("fiscal_quarter"),
                source_url=item.get("source_url"),
                concept_qname=SEC_EPS_CONCEPT,
                context_ref=None,
                dimensions=(),
                unit="UNKNOWN",
                decimals=None,
                raw_value=value,
                normalized_value=value,
                source_kind="FURNISHED_EXHIBIT",
                assurance_status="UNAUDITED",
                derived_status="DIRECT",
                derivation_description="",
                share_class_scope=SHARE_CLASS_SCOPE_CONSOLIDATED,
            )
        )
    return records, declined


def _records_from_run_observations(observations: Optional[Sequence[Any]]) -> List[EpsFactRecord]:
    """
    Directly stated diluted-EPS facts from this run's own filing acquisition.

    Read from each observation's declared identity, never from its value, and
    only for facts the filer stated itself: an observation the acquisition
    derived (a summed or rolled-forward window) carries a `derivation` in its
    raw payload and is not a filing statement. A run's acquisition is preferred
    over the packaged dataset wherever both hold the same fact, because it is
    the fresher and identically identified copy.
    """
    records: List[EpsFactRecord] = []
    for observation in observations or ():
        metric = str(getattr(observation, "metric", "") or "")
        raw = getattr(observation, "raw", None)
        raw = raw if isinstance(raw, dict) else {}
        fact = raw.get("sec_fact") if isinstance(raw.get("sec_fact"), dict) else {}
        tag = str(fact.get("tag") or "")
        concept_is_diluted_eps = (
            metric in ("eps_diluted", "METRIC_EPS_DILUTED", "EarningsPerShareDiluted")
            or tag == "EarningsPerShareDiluted"
        )
        if not concept_is_diluted_eps or raw.get("derivation"):
            continue
        accession = raw.get("accession") or raw.get("accn") or fact.get("accession")
        form = raw.get("form") or fact.get("form")
        filed = _iso_date(raw.get("filed") or fact.get("filed"))
        period_end = _iso_date(getattr(observation, "period_end", None) or fact.get("end"))
        period_start = _iso_date(getattr(observation, "period_start", None) or fact.get("start"))
        value = _safe_float(getattr(observation, "value", None))
        tag = fact.get("tag")
        concept_qname = fact.get("concept_qname") or (f"us-gaap:{tag}" if tag else SEC_EPS_CONCEPT)
        unit = str(fact.get("unit") or raw.get("reported_currency_unit") or "")
        if not unit or unit not in SEC_EPS_UNITS:
            continue
        if not (accession and form and period_end and value is not None):
            continue
        available_at = getattr(observation, "available_at", None)
        basis = str(getattr(observation, "available_at_basis", "") or AVAILABILITY_UNDECLARED)
        if not available_at:
            available_at, basis = _availability_from(raw.get("acceptance_datetime"), filed)
        dimensions_raw = fact.get("dimensions") or raw.get("dimensions") or ()
        if not isinstance(dimensions_raw, (list, tuple)):
            dimensions_raw = ()
        dimensions = tuple(dimensions_raw)
        scope = share_class_scope_from_dimensions(dimensions)
        form_upper = str(form).upper()
        assurance = "UNKNOWN"
        records.append(
            EpsFactRecord(
                period_start=period_start,
                period_end=period_end,
                value=value,
                form=str(form),
                accession=str(accession),
                filed=filed,
                acceptance_datetime=_iso_instant(raw.get("acceptance_datetime")),
                available_at=str(available_at),
                available_at_basis=basis,
                evidence_class="filed",
                fiscal_year=fact.get("fy"),
                fiscal_period=str(fact.get("fp") or "") or None,
                source_url=getattr(observation, "source_url", None),
                concept_qname=concept_qname,
                context_ref=fact.get("context_ref") or raw.get("context_ref"),
                dimensions=dimensions,
                unit=unit,
                decimals=fact.get("decimals") or raw.get("decimals"),
                raw_value=value,
                normalized_value=value,
                source_kind="SEC_COMPANYCONCEPT",
                assurance_status=assurance,
                derived_status="DIRECT",
                derivation_description="",
                share_class_scope=scope,
            )
        )
    return records


def _load_packaged_records(
    ticker: str, root: str = _PACKAGED_ROOT
) -> Tuple[List[EpsFactRecord], List[Dict[str, Any]], Dict[str, Any]]:
    """The tracked SEC datasets for one ticker, read without any network call."""
    inputs: Dict[str, Any] = {}
    records: List[EpsFactRecord] = []
    declined: List[Dict[str, Any]] = []
    directory = os.path.join(root, ticker)

    concept_path = os.path.join(directory, "eps_diluted_concept.json")
    if os.path.exists(concept_path):
        inputs["companyconcept"] = concept_path
        try:
            with open(concept_path, "r", encoding="utf-8") as handle:
                records.extend(_records_from_companyconcept(json.load(handle)))
        except (OSError, ValueError):
            inputs["companyconcept_readable"] = False

    q4_path = os.path.join(directory, "q4_evidence_records.json")
    if os.path.exists(q4_path):
        inputs["furnished_quarter_evidence"] = q4_path
        try:
            with open(q4_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            furnished, q4_declined = _records_from_furnished_quarters(payload)
            records.extend(furnished)
            declined.extend(q4_declined)
            if q4_declined:
                inputs["declined_furnished_quarter_records"] = q4_declined
        except (OSError, ValueError):
            inputs["furnished_quarter_evidence_readable"] = False

    return records, declined, inputs


# ---------------------------------------------------------------------------
# Window assembly
# ---------------------------------------------------------------------------

def _anchor_record_known(
    record: EpsFactRecord,
    *,
    valuation_date: Optional[str],
    extra: Optional[Dict[str, Any]] = None,
) -> Optional[Knowability]:
    return resolve_knowability(
        available_at=record.available_at,
        available_at_basis=record.available_at_basis,
        valuation_date=valuation_date,
    )


def _dedupe_by_period_end(records: Sequence[EpsFactRecord]) -> List[EpsFactRecord]:
    """
    One record per period end, preferring the filed periodic report.

    Where an issuer both filed a discrete quarter and furnished the same quarter
    in an earnings release, the periodic report is the filed statement and the
    furnished release corroborates it. The choice is recorded on the record that
    wins so the alternative stays visible rather than being discarded silently.
    """
    chosen: Dict[str, EpsFactRecord] = {}
    for record in records:
        existing = chosen.get(record.period_end)
        if existing is None:
            chosen[record.period_end] = record
            continue
        if existing.evidence_class == "filed" and record.evidence_class != "filed":
            continue
        if existing.evidence_class != "filed" and record.evidence_class == "filed":
            chosen[record.period_end] = record
            continue
        # Same class: the later filing of the same period is the current
        # statement of it, and the accession breaks a tie deterministically.
        if (record.filed or "", record.accession) > (existing.filed or "", existing.accession):
            chosen[record.period_end] = record
    return [chosen[key] for key in sorted(chosen)]


def eps_fact_records_from_xbrl_document(
    document: Any,
    *,
    accession: str,
    form: str = "10-K",
    filed: Optional[str] = None,
    acceptance_datetime: Optional[str] = None,
    cik: Optional[str] = None,
    concept_qname: str = SEC_EPS_CONCEPT,
    source_kind: str = "FILED_XBRL",
    assurance_status: str = "UNKNOWN",
    source_url: Optional[str] = None,
    fiscal_year: Optional[Any] = None,
    fiscal_period: Optional[str] = None,
    expected_cik: Optional[str] = None,
    issuer_cik: Optional[str] = None,
    target_cik: Optional[str] = None,
    rejections: Optional[List[Dict[str, Any]]] = None,
) -> List[EpsFactRecord]:
    """Convert a parsed XBRL document's dimensional EPS facts to EpsFactRecord."""
    records: List[EpsFactRecord] = []
    try:
        contexts = getattr(document, "contexts", {}) or {}
        units = getattr(document, "units", {}) or {}
        facts = getattr(document, "facts", ()) or ()
    except Exception:
        return records
    target = expected_cik or issuer_cik or target_cik or cik
    normalized_target = None
    if target is None:
        target_error = "MISSING_TARGET_CIK"
    else:
        digits = "".join(ch for ch in str(target) if ch.isdigit())
        if len(digits) != 10:
            target_error = "INVALID_TARGET_CIK"
        else:
            normalized_target = digits.zfill(10)
            target_error = None

    def _reject(code: str, detail: str, context_ref: Optional[str] = None) -> None:
        if isinstance(rejections, list):
            rejections.append({"reason_code": code, "detail": detail, "context_ref": context_ref, "accession": accession})

    # Fail closed if no valid target CIK.
    if target_error is not None:
        _reject(target_error, "a valid 10-digit target CIK is required", None)
        return records

    # Validate accession format and CIK part.
    accession_value = str(accession or "").strip()
    accession_ok = True
    if not accession_value or accession_value.lower() in ("none", "null"):
        accession_ok = False
        _reject("ACCESSION_MISSING", "accession is required", None)
    else:
        acc_match = re.match(r"^(\d{10})-(\d{2})-(\d{6})$", accession_value)
        if not acc_match:
            accession_ok = False
            _reject("ACCESSION_INVALID", f"accession {accession_value!r} does not match SEC format", None)
        else:
            acc_cik = acc_match.group(1)
            if acc_cik != normalized_target:
                accession_ok = False
                _reject("ACCESSION_CIK_MISMATCH", f"accession CIK {acc_cik} != target {normalized_target}", None)

    # Validate form (no implicit 10-K default).
    form_value = str(form or "").strip()
    supported_forms = {"10-K", "10-K/A", "10-Q", "10-Q/A"}
    if not form_value:
        _reject("FORM_MISSING", "form is required", None)
        form_ok = False
    elif form_value not in supported_forms:
        _reject("FORM_UNSUPPORTED", f"form {form_value!r} is not supported", None)
        form_ok = False
    else:
        form_ok = True

    # Validate fiscal year.
    fiscal_year_ok = True
    try:
        fy_int = int(fiscal_year)
    except (TypeError, ValueError):
        fy_int = None
        fiscal_year_ok = False
        _reject("FISCAL_YEAR_MISSING", "fiscal_year must be a valid integer", None)

    # Validate fiscal period and compatibility with form.
    fiscal_period_value = str(fiscal_period).strip() if fiscal_period is not None else ""
    fiscal_period_ok = True
    if not fiscal_period_value:
        fiscal_period_ok = False
        _reject("FISCAL_PERIOD_MISSING", "fiscal_period is required", None)
    elif form_value == "10-K" and fiscal_period_value != "FY":
        fiscal_period_ok = False
        _reject("FISCAL_PERIOD_INCOMPATIBLE", f"fiscal_period {fiscal_period_value} incompatible with form 10-K", None)
    elif form_value == "10-Q" and fiscal_period_value not in ("Q1", "Q2", "Q3"):
        fiscal_period_ok = False
        _reject("FISCAL_PERIOD_INCOMPATIBLE", f"fiscal_period {fiscal_period_value} incompatible with form 10-Q", None)

    # Point-in-time availability: values must be parseable, not merely present.
    pit_ok = False
    filed_ok = False
    acceptance_ok = False
    if filed is not None:
        try:
            _iso_date(filed)
            # _iso_date returns None on failure
            if _iso_date(filed) is not None:
                filed_ok = True
        except Exception:
            filed_ok = False
    if acceptance_datetime is not None:
        try:
            if _iso_instant(acceptance_datetime) is not None:
                acceptance_ok = True
        except Exception:
            acceptance_ok = False
    if filed_ok or acceptance_ok:
        pit_ok = True
    else:
        if filed is None and acceptance_datetime is None:
            _reject("POINT_IN_TIME_MISSING", "filed or acceptance_datetime is required", None)
        else:
            _reject("POINT_IN_TIME_UNPARSEABLE", "filed/acceptance_datetime could not be parsed", None)

    # If core metadata invalid, do not promote any fact.
    if not (accession_ok and form_ok and fiscal_year_ok and fiscal_period_ok and pit_ok):
        return records

    for fact in facts:
        tag = str(getattr(fact, "tag", "") or "")
        taxonomy = str(getattr(fact, "taxonomy", "") or "")
        if tag != "EarningsPerShareDiluted":
            continue
        # Strict US-GAAP namespace validation.
        tax_lower = taxonomy.lower()
        if not (tax_lower.startswith("http://fasb.org/us-gaap/") or tax_lower.startswith("https://fasb.org/us-gaap/")):
            _reject("TAXONOMY_NOT_US_GAAP", f"taxonomy {taxonomy!r} is not a US-GAAP namespace", getattr(fact, "context_ref", None))
            continue
        # concept_qname consistency check (do not trust caller's value for identity).
        concept_local = str(concept_qname).rsplit(":", 1)[-1]
        if concept_local and concept_local != tag:
            _reject("CONCEPT_QNAME_MISMATCH", f"concept_qname {concept_qname!r} != {tag}", getattr(fact, "context_ref", None))
            continue
        context_ref = getattr(fact, "context_ref", None)
        if not context_ref or context_ref not in contexts:
            _reject("CONTEXT_UNRESOLVED", f"context {context_ref} unresolved", context_ref)
            continue
        ctx = contexts[context_ref]
        entity_scheme = getattr(ctx, "entity_scheme", None)
        if str(entity_scheme or "").strip() != "http://www.sec.gov/CIK":
            _reject("ENTITY_SCHEME_INVALID", f"context {context_ref} scheme {entity_scheme!r} is not the SEC CIK scheme", context_ref)
            continue
        entity_identifier = getattr(ctx, "entity_identifier", None)
        entity_text = str(entity_identifier or "").strip()
        if not re.fullmatch(r"\d{10}", entity_text):
            _reject("ENTITY_IDENTIFIER_INVALID", f"context {context_ref} identifier {entity_identifier!r} is not a 10-digit CIK", context_ref)
            continue
        if entity_text != normalized_target:
            _reject("ISSUER_IDENTITY_MISMATCH", f"context {context_ref} entity {entity_text} != target {normalized_target}", context_ref)
            continue
        # Accession CIK consistency with context issuer.
        # Accession CIK is validated against the target above.

        period_start = getattr(ctx, "period_start", None)
        period_end = getattr(ctx, "period_end", None)
        if not period_end:
            _reject("PERIOD_MISSING", f"context {context_ref} has no period end", context_ref)
            continue
        value = _safe_float(getattr(fact, "resolved_value", None))
        if value is None:
            _reject("VALUE_NOT_NUMERIC", f"fact {context_ref} value not numeric", context_ref)
            continue
        dimensions = getattr(ctx, "dimensions", ()) or ()
        if not isinstance(dimensions, (list, tuple)):
            dimensions = ()
        dimensions = tuple(dimensions)
        scope = share_class_scope_from_dimensions(dimensions)
        decimals = getattr(fact, "decimals", None)
        # Resolve unit spelling.
        unit_ref = getattr(fact, "unit_ref", None)
        unit_str = "UNKNOWN"
        try:
            unit_obj = units.get(unit_ref) if isinstance(units, dict) else None
            if unit_obj is not None:
                spelling = None
                try:
                    from sec_xbrl_facts import unit_spelling
                    spelling = unit_spelling(unit_obj)
                except Exception:
                    spelling = None
                if spelling:
                    unit_str = spelling
                elif getattr(unit_obj, "measures", None):
                    unit_str = "/".join(str(m) for m in unit_obj.measures)
        except Exception:
            unit_str = str(unit_ref or "UNKNOWN")
        if unit_str not in SEC_EPS_UNITS:
            _reject("UNIT_NOT_PER_SHARE", f"unit {unit_str!r} is not a per-share unit", context_ref)
            continue
        try:
            from sec_provider import xbrl_unit_to_contract_unit
            if xbrl_unit_to_contract_unit(unit_str) != "per_share":
                _reject("UNIT_NOT_PER_SHARE", f"unit {unit_str!r} is not per_share", context_ref)
                continue
        except Exception:
            pass

        available_at, basis = _availability_from(acceptance_datetime, filed)
        records.append(
            EpsFactRecord(
                period_start=_iso_date(period_start),
                period_end=_iso_date(period_end) or str(period_end),
                value=value,
                form=form_value,
                accession=accession_value,
                filed=_iso_date(filed),
                acceptance_datetime=_iso_instant(acceptance_datetime),
                available_at=available_at,
                available_at_basis=basis,
                evidence_class="filed",
                fiscal_year=fiscal_year if fiscal_year is not None else fy_int,
                fiscal_period=fiscal_period_value,
                source_url=source_url or (_document_url(cik, accession_value) if cik else None),
                concept_qname=SEC_EPS_CONCEPT,
                context_ref=context_ref,
                dimensions=dimensions,
                unit=unit_str,
                decimals=decimals,
                raw_value=value,
                normalized_value=value,
                source_kind="FILED_XBRL",
                assurance_status=assurance_status,
                derived_status="DIRECT",
                derivation_description="",
                share_class_scope=scope,
            )
        )

    return records

    # Validate accession format and CIK part.
    accession_value = str(accession or "").strip()
    accession_ok = True
    if not accession_value or accession_value.lower() in ("none", "null"):
        accession_ok = False
        _reject("ACCESSION_MISSING", "accession is required", None)
    else:
        acc_match = re.match(r"^(\d{10})-(\d{2})-(\d{6})$", accession_value)
        if not acc_match:
            accession_ok = False
            _reject("ACCESSION_INVALID", f"accession {accession_value!r} does not match SEC format", None)
        else:
            acc_cik = acc_match.group(1)
            if acc_cik != normalized_target:
                accession_ok = False
                _reject("ACCESSION_CIK_MISMATCH", f"accession CIK {acc_cik} != target {normalized_target}", None)

    # Validate form (no implicit 10-K default).
    form_value = str(form or "").strip()
    supported_forms = {"10-K", "10-K/A", "10-Q", "10-Q/A"}
    if not form_value:
        _reject("FORM_MISSING", "form is required", None)
        form_ok = False
    elif form_value not in supported_forms:
        _reject("FORM_UNSUPPORTED", f"form {form_value!r} is not supported", None)
        form_ok = False
    else:
        form_ok = True

    # Validate fiscal year.
    fiscal_year_ok = True
    try:
        fy_int = int(fiscal_year)
    except (TypeError, ValueError):
        fy_int = None
        fiscal_year_ok = False
        _reject("FISCAL_YEAR_MISSING", "fiscal_year must be a valid integer", None)

    # Validate fiscal period and compatibility with form.
    fiscal_period_value = str(fiscal_period).strip() if fiscal_period is not None else ""
    fiscal_period_ok = True
    if not fiscal_period_value:
        fiscal_period_ok = False
        _reject("FISCAL_PERIOD_MISSING", "fiscal_period is required", None)
    elif form_value == "10-K" and fiscal_period_value != "FY":
        fiscal_period_ok = False
        _reject("FISCAL_PERIOD_INCOMPATIBLE", f"fiscal_period {fiscal_period_value} incompatible with form 10-K", None)
    elif form_value == "10-Q" and fiscal_period_value not in ("Q1", "Q2", "Q3"):
        fiscal_period_ok = False
        _reject("FISCAL_PERIOD_INCOMPATIBLE", f"fiscal_period {fiscal_period_value} incompatible with form 10-Q", None)

    # Point-in-time availability: values must be parseable, not merely present.
    pit_ok = False
    filed_ok = False
    acceptance_ok = False
    if filed is not None:
        try:
            _iso_date(filed)
            # _iso_date returns None on failure
            if _iso_date(filed) is not None:
                filed_ok = True
        except Exception:
            filed_ok = False
    if acceptance_datetime is not None:
        try:
            if _iso_instant(acceptance_datetime) is not None:
                acceptance_ok = True
        except Exception:
            acceptance_ok = False
    if filed_ok or acceptance_ok:
        pit_ok = True
    else:
        if filed is None and acceptance_datetime is None:
            _reject("POINT_IN_TIME_MISSING", "filed or acceptance_datetime is required", None)
        else:
            _reject("POINT_IN_TIME_UNPARSEABLE", "filed/acceptance_datetime could not be parsed", None)

    # If core metadata invalid, do not promote any fact.
    if not (accession_ok and form_ok and fiscal_year_ok and fiscal_period_ok and pit_ok):
        return records

    for fact in facts:
        tag = str(getattr(fact, "tag", "") or "")
        taxonomy = str(getattr(fact, "taxonomy", "") or "")
        if tag != "EarningsPerShareDiluted":
            continue
        # Strict US-GAAP namespace validation.
        tax_lower = taxonomy.lower()
        if not (tax_lower.startswith("http://fasb.org/us-gaap/") or tax_lower.startswith("https://fasb.org/us-gaap/")):
            _reject("TAXONOMY_NOT_US_GAAP", f"taxonomy {taxonomy!r} is not a US-GAAP namespace", getattr(fact, "context_ref", None))
            continue
        # concept_qname consistency check (do not trust caller's value for identity).
        concept_local = str(concept_qname).rsplit(":", 1)[-1]
        if concept_local and concept_local != tag:
            _reject("CONCEPT_QNAME_MISMATCH", f"concept_qname {concept_qname!r} != {tag}", getattr(fact, "context_ref", None))
            continue
        context_ref = getattr(fact, "context_ref", None)
        if not context_ref or context_ref not in contexts:
            _reject("CONTEXT_UNRESOLVED", f"context {context_ref} unresolved", context_ref)
            continue
        ctx = contexts[context_ref]
        entity_scheme = getattr(ctx, "entity_scheme", None)
        if str(entity_scheme or "").strip() != "http://www.sec.gov/CIK":
            _reject("ENTITY_SCHEME_INVALID", f"context {context_ref} scheme {entity_scheme!r} is not the SEC CIK scheme", context_ref)
            continue
        entity_identifier = getattr(ctx, "entity_identifier", None)
        entity_text = str(entity_identifier or "").strip()
        if not re.fullmatch(r"\d{10}", entity_text):
            _reject("ENTITY_IDENTIFIER_INVALID", f"context {context_ref} identifier {entity_identifier!r} is not a 10-digit CIK", context_ref)
            continue
        if entity_text != normalized_target:
            _reject("ISSUER_IDENTITY_MISMATCH", f"context {context_ref} entity {entity_text} != target {normalized_target}", context_ref)
            continue
        # Accession CIK consistency with context issuer.
        # Accession CIK is validated against the target above.

        period_start = getattr(ctx, "period_start", None)
        period_end = getattr(ctx, "period_end", None)
        if not period_end:
            _reject("PERIOD_MISSING", f"context {context_ref} has no period end", context_ref)
            continue
        value = _safe_float(getattr(fact, "resolved_value", None))
        if value is None:
            _reject("VALUE_NOT_NUMERIC", f"fact {context_ref} value not numeric", context_ref)
            continue
        dimensions = getattr(ctx, "dimensions", ()) or ()
        if not isinstance(dimensions, (list, tuple)):
            dimensions = ()
        dimensions = tuple(dimensions)
        scope = share_class_scope_from_dimensions(dimensions)
        decimals = getattr(fact, "decimals", None)
        # Resolve unit spelling.
        unit_ref = getattr(fact, "unit_ref", None)
        unit_str = "UNKNOWN"
        try:
            unit_obj = units.get(unit_ref) if isinstance(units, dict) else None
            if unit_obj is not None:
                spelling = None
                try:
                    from sec_xbrl_facts import unit_spelling
                    spelling = unit_spelling(unit_obj)
                except Exception:
                    spelling = None
                if spelling:
                    unit_str = spelling
                elif getattr(unit_obj, "measures", None):
                    unit_str = "/".join(str(m) for m in unit_obj.measures)
        except Exception:
            unit_str = str(unit_ref or "UNKNOWN")
        if unit_str not in SEC_EPS_UNITS:
            _reject("UNIT_NOT_PER_SHARE", f"unit {unit_str!r} is not a per-share unit", context_ref)
            continue
        try:
            from sec_provider import xbrl_unit_to_contract_unit
            if xbrl_unit_to_contract_unit(unit_str) != "per_share":
                _reject("UNIT_NOT_PER_SHARE", f"unit {unit_str!r} is not per_share", context_ref)
                continue
        except Exception:
            pass

        available_at, basis = _availability_from(acceptance_datetime, filed)
        records.append(
            EpsFactRecord(
                period_start=_iso_date(period_start),
                period_end=_iso_date(period_end) or str(period_end),
                value=value,
                form=form_value,
                accession=accession_value,
                filed=_iso_date(filed),
                acceptance_datetime=_iso_instant(acceptance_datetime),
                available_at=available_at,
                available_at_basis=basis,
                evidence_class="filed",
                fiscal_year=fiscal_year if fiscal_year is not None else fy_int,
                fiscal_period=fiscal_period_value,
                source_url=source_url or (_document_url(cik, accession_value) if cik else None),
                concept_qname=SEC_EPS_CONCEPT,
                context_ref=context_ref,
                dimensions=dimensions,
                unit=unit_str,
                decimals=decimals,
                raw_value=value,
                normalized_value=value,
                source_kind="FILED_XBRL",
                assurance_status=assurance_status,
                derived_status="DIRECT",
                derivation_description="",
                share_class_scope=scope,
            )
        )

    return records


# Aliases for varied caller names.
records_from_xbrl_document = eps_fact_records_from_xbrl_document
extract_eps_facts_from_document = eps_fact_records_from_xbrl_document
extract_dimensional_eps = eps_fact_records_from_xbrl_document
parse_eps_facts_from_document = eps_fact_records_from_xbrl_document
extract_eps_dimensional_facts = eps_fact_records_from_xbrl_document


def _annual_candidate(
    records: Sequence[EpsFactRecord],
    *,
    valuation_date: Optional[str],
    scope: Optional[str] = None,
) -> Tuple[Optional[EpsFactRecord], Knowability, List[EpsFactRecord]]:
    """
    The latest annual fact that was public at the valuation date.

    Among facts covering the same fiscal year the latest filing wins, because at
    the valuation date that is the statement of the period a reader could see;
    where a prior-year comparative is re-presented in a later 10-K it covers an
    earlier period end and therefore never outranks the current year.
    """
    annuals = [
        record
        for record in records
        if record.is_annual()
        and record.form in ("10-K", "10-K/A")
        and str(record.fiscal_period or "") == "FY"
    ]
    if scope is not None:
        annuals = [r for r in annuals if r.share_class_scope == scope]
    if not annuals:
        return None, Knowability(False, "no_annual_fact", "No directly stated annual diluted-EPS fact was read."), []

    knowable = [
        (record, _anchor_record_known(record, valuation_date=valuation_date))
        for record in annuals
    ]
    eligible = [pair for pair in knowable if pair[1].knowable]
    if not eligible:
        blocked = knowable[0][1]
        return None, blocked, annuals
    best = max(eligible, key=lambda pair: (pair[0].period_end, pair[0].filed or "", pair[0].accession))
    return best[0], best[1], annuals


def _quarter_window(
    records: Sequence[EpsFactRecord],
    *,
    valuation_date: Optional[str],
) -> Tuple[Optional[Tuple[List[EpsFactRecord], str, str]], Dict[str, Any]]:
    """
    The latest four consecutive directly stated quarters, and its window.

    Returns the window's four components, its start and its end, or a refusal
    describing precisely which condition failed. The window start is anchored by
    a declared quarter boundary: a window whose opening date can only be guessed
    is not offered, because a twelve-month claim needs a stated start.
    """
    # A directly stated quarterly figure normally declares both boundaries, but a
    # fiscal fourth quarter furnished in an Item 2.02 exhibit states only the
    # period it closes. Such a record cannot be span-tested on its own, so it
    # enters the pool as an end boundary and the boundaries around it are what
    # verify it.
    quarters = _dedupe_by_period_end(
        [
            record
            for record in records
            if record.is_discrete_quarter() or record.period_start is None
        ]
    )
    if not quarters:
        return None, {
            "refusal_code": REFUSAL_INCOMPLETE_QUARTERS,
            "refusal_reason": (
                "No directly stated quarterly diluted-EPS fact was read for this "
                "issuer, so a twelve-month window cannot be assembled."
            ),
        }

    usable = [
        record
        for record in quarters
        if _anchor_record_known(record, valuation_date=valuation_date).knowable
    ]
    if not usable:
        return None, {
            "refusal_code": REFUSAL_QUARTERS_NOT_KNOWABLE,
            "refusal_reason": (
                "Quarterly diluted-EPS facts exist for this issuer but none was "
                "public before the valuation date's close, so none may be used."
            ),
        }

    def _chain_is_contiguous(window: Sequence[EpsFactRecord]) -> bool:
        """
        Whether consecutive components share a boundary, or adjoin one quarter apart.

        A component that declares its start fixes the boundary against the
        previous component's declared end. A component that states only its end
        can only be checked from the other side: either the next component's
        declared start follows it immediately, or, when it closes the window,
        its end falls one quarter after the previous component's end. Anything
        else means a quarter is unaccounted for.
        """
        for position in range(len(window) - 1):
            previous, following = window[position], window[position + 1]
            if following.period_start is not None:
                gap = _span_days(previous.period_end, following.period_start)
                if gap is None or gap < 1 or gap > MAX_CONTIGUITY_GAP_DAYS:
                    return False
                continue
            if position != len(window) - 2:
                # A component that states only its end cannot separate two
                # components that both follow it, so it may only close the window.
                return False
            quarter_later = _span_days(previous.period_end, following.period_end)
            if quarter_later is None or not (QUARTER_MIN_DAYS <= quarter_later <= QUARTER_MAX_DAYS):
                return False
        return True

    # Walk back from the latest quarter end until four consecutive quarters line
    # up. A window is accepted only when the whole chain is contiguous and spans
    # a year; a partial chain is never completed across a missing quarter.
    for index in range(len(usable) - 1, 2, -1):
        window = usable[index - 3: index + 1]
        if not _chain_is_contiguous(window):
            continue

        window_end = window[-1].period_end
        if window[0].period_start is not None:
            window_start = window[0].period_start
        else:
            # The earliest component states only its period end, so the window's
            # opening boundary is anchored on the declared quarter immediately
            # before it. That quarter must be knowable and must be one quarter
            # long; otherwise there is no stated date to open the window on and
            # none is invented.
            opening_end = window[0].period_end
            anchor = None
            for record in reversed(usable):
                if record.period_end >= opening_end:
                    continue
                gap = _span_days(record.period_end, opening_end)
                if gap is not None and QUARTER_MIN_DAYS <= gap <= QUARTER_MAX_DAYS:
                    anchor = record
                    break
            if anchor is None:
                continue
            window_start = (
                datetime.date.fromisoformat(anchor.period_end) + datetime.timedelta(days=1)
            ).isoformat()

        span = _span_days(window_start, window_end)
        if span is None or not (YEAR_MIN_DAYS <= span <= YEAR_MAX_DAYS):
            continue
        return (window, window_start, window_end), {}

    return None, {
        "refusal_code": REFUSAL_WINDOW_SPAN,
        "refusal_reason": (
            "The directly stated quarterly facts public at this valuation date do "
            "not form four consecutive quarters spanning a year, so no twelve-month "
            "window is offered. A missing quarter is not filled by arithmetic across "
            "the gap."
        ),
    }


def _sum_window(window: Sequence[EpsFactRecord]) -> Optional[float]:
    """
    The four quarters' sum, added in period order.

    Rounded to the precision a per-share amount is stated at, so that summing
    four two-decimal figures does not present a float artefact as a stated
    value. The rounding removes representation error only; it never merges or
    reconciles the figures being added.
    """
    total = 0.0
    for record in window:
        total += record.value
    result = _safe_float(total)
    return None if result is None else round(result, 6)


def _latest_instant(records: Sequence[EpsFactRecord]) -> Tuple[Optional[str], str]:
    """
    When the whole set became public, and on what basis.

    A window is knowable only once its last component was, so the set's
    availability is the latest acceptance instant among its components. Instants
    are compared as parsed timestamps rather than as text, because the tracked
    datasets mix a bare filed date with a full acceptance instant and those
    strings do not sort in chronological order.
    """
    stamped: List[Tuple[datetime.datetime, EpsFactRecord]] = []
    for record in records:
        moment = _parse_aware(record.available_at)
        if moment is not None:
            stamped.append((moment, record))
    if stamped:
        latest = max(stamped, key=lambda pair: pair[0])[1]
        return latest.available_at, latest.available_at_basis
    dated = [record for record in records if record.available_at]
    if not dated:
        return None, AVAILABILITY_UNDECLARED
    latest = max(dated, key=lambda record: _iso_date(record.available_at) or "")
    return latest.available_at, latest.available_at_basis


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------

def _supplier_candidate(
    *,
    anchor_id: str,
    value: Optional[float],
    basis: str,
    months_covered: float,
    period_label: str,
    provider: str,
    source_field: Optional[str],
    source_url: Optional[str],
    source_observation_type: Optional[str],
    source_retrieved_at: Optional[str],
    observation_id: Optional[str] = None,
    currency: Optional[str],
) -> EpsAnchorCandidate:
    """
    A supplier EPS field, as far as its own payload allows it to be described.

    The supplier declares no accounting basis and, for the trailing figure,
    usually no period, so both are recorded as undeclared instead of being read
    as a verified trailing twelve-month GAAP figure. The figure remains usable;
    what it is not stated rather than assumed.
    """
    numeric = _safe_float(value)
    if numeric is None or numeric <= 0:
        return EpsAnchorCandidate(
            anchor_id=anchor_id,
            available=False,
            basis=basis,
            nature=NATURE_PROVIDER_REPORTED,
            source_label=source_field or "supplier EPS field",
            source_provider=provider,
            observation_id=observation_id,
            refusal_code=REFUSAL_SUPPLIER_NOT_OBSERVED,
            refusal_reason=(
                f"This run observed no positive {anchor_id.lower()} value from the "
                "supplier, so the anchor is not offered."
            ),
            share_class_scope=SHARE_CLASS_SCOPE_UNKNOWN,
        )
    return EpsAnchorCandidate(
        anchor_id=anchor_id,
        available=True,
        basis=basis,
        value=numeric,
        months_covered=months_covered,
        nature=NATURE_PROVIDER_REPORTED,
        gaap_basis=GAAP_BASIS_UNDECLARED,
        source_label=source_field or anchor_id,
        source_provider=provider,
        source_url=source_url,
        source_field=source_field,
        observation_id=observation_id,
        period_label=period_label,
        period_undeclared_by_source=True,
        available_at=_iso_instant(source_retrieved_at),
        available_at_basis=(
            "OBSERVATION_RETRIEVED_AT" if _iso_instant(source_retrieved_at) else AVAILABILITY_UNDECLARED
        ),
        derivation=(
            "Read directly from the supplier field the run acquired. The supplier "
            "declares no accounting basis for this figure, so none is asserted."
        ),
        share_class_scope=SHARE_CLASS_SCOPE_UNKNOWN,
    )


def build_eps_anchor_candidates(
    *,
    ticker: str,
    valuation_date: Optional[str],
    currency: Optional[str] = None,
    trailing_eps: Optional[float] = None,
    forward_eps: Optional[float] = None,
    consensus_eps: Optional[float] = None,
    trailing_period_label: str = "",
    forward_period_label: str = "",
    provider: str = "",
    trailing_source_field: Optional[str] = None,
    trailing_source_url: Optional[str] = None,
    trailing_observation_type: Optional[str] = None,
    trailing_retrieved_at: Optional[str] = None,
    trailing_observation_id: Optional[str] = None,
    forward_source_field: Optional[str] = None,
    forward_source_url: Optional[str] = None,
    forward_observation_type: Optional[str] = None,
    forward_retrieved_at: Optional[str] = None,
    forward_observation_id: Optional[str] = None,
    consensus_source_field: Optional[str] = None,
    consensus_source_url: Optional[str] = None,
    consensus_observation_type: Optional[str] = None,
    consensus_retrieved_at: Optional[str] = None,
    consensus_observation_id: Optional[str] = None,
    run_observations: Optional[Sequence[Any]] = None,
    records: Optional[Sequence[EpsFactRecord]] = None,
    xbrl_records: Optional[Sequence[EpsFactRecord]] = None,
    dimensional_records: Optional[Sequence[EpsFactRecord]] = None,
    xbrl_documents: Optional[Sequence[Any]] = None,
    raw_xbrl_documents: Optional[Sequence[Any]] = None,
    accession: Optional[str] = None,
    form: str = "10-K",
    filed: Optional[str] = None,
    fiscal_year: Optional[Any] = None,
    fiscal_period: Optional[str] = None,
    assurance_status: str = "UNKNOWN",
    packaged_root: Optional[str] = None,
    **kwargs: Any,
) -> EpsAnchorCandidateSet:
    """
    The EPS anchor catalogue for one issuer at one valuation date.

    Supplier figures come from what this run observed. Issuer figures come from
    this run's own filing acquisition where it has any and from the tracked SEC
    datasets otherwise; neither is fetched, so building the catalogue adds no
    network acquisition. Every entry is either available with its full identity,
    or unavailable with the specific condition that failed.
    """
    root = packaged_root if packaged_root is not None else _PACKAGED_ROOT
    packaged, _declined, inputs = _load_packaged_records(ticker, root)
    run_records = _records_from_run_observations(run_observations)
    if run_records:
        inputs["run_acquisition_facts"] = len(run_records)

    # Collect dimensional XBRL records supplied by callers (Phase 2.1).
    xbrl_fact_records: List[EpsFactRecord] = []
    for collection in (records, xbrl_records, dimensional_records):
        if collection:
            for item in collection:
                if isinstance(item, EpsFactRecord):
                    xbrl_fact_records.append(item)
    for collection in (xbrl_documents, raw_xbrl_documents):
        if collection:
            for item in collection:
                try:
                    converted = eps_fact_records_from_xbrl_document(
                        item,
                        accession=accession or "",
                        form=form,
                        filed=filed,
                        fiscal_year=fiscal_year,
                        fiscal_period=fiscal_period,
                        assurance_status=assurance_status,
                        source_url=None,
                    )
                    xbrl_fact_records.extend(converted)
                except Exception:
                    continue
    # kwargs may carry additional record collections.
    for key, value in (kwargs or {}).items():
        if isinstance(value, (list, tuple)):
            for item in value:
                if isinstance(item, EpsFactRecord):
                    xbrl_fact_records.append(item)
                elif hasattr(item, "contexts") and hasattr(item, "facts"):
                    try:
                        converted = eps_fact_records_from_xbrl_document(
                            item,
                            accession=accession or "",
                            form=form,
                            filed=filed,
                            fiscal_year=fiscal_year,
                            fiscal_period=fiscal_period,
                            assurance_status=assurance_status,
                        )
                        xbrl_fact_records.extend(converted)
                    except Exception:
                        continue
    if xbrl_fact_records:
        inputs["xbrl_dimensional_facts"] = len(xbrl_fact_records)
    records = run_records + xbrl_fact_records + list(packaged)

    candidates: List[EpsAnchorCandidate] = [
        _supplier_candidate(
            anchor_id=ANCHOR_SUPPLIER_TRAILING,
            value=trailing_eps,
            basis=ANCHOR_TTM,
            months_covered=12.0,
            period_label=trailing_period_label
            or "trailing twelve months (assumed; the supplier declared no period)",
            provider=provider,
            source_field=trailing_source_field,
            source_url=trailing_source_url,
            source_observation_type=trailing_observation_type,
            source_retrieved_at=trailing_retrieved_at,
            observation_id=trailing_observation_id,
            currency=currency,
        ),
        _supplier_candidate(
            anchor_id=ANCHOR_SUPPLIER_FORWARD,
            value=forward_eps,
            basis=ANCHOR_FORWARD,
            months_covered=12.0,
            period_label=forward_period_label
            or "forward twelve months (assumed; the supplier declared no period)",
            provider=provider,
            source_field=forward_source_field,
            source_url=forward_source_url,
            source_observation_type=forward_observation_type,
            source_retrieved_at=forward_retrieved_at,
            observation_id=forward_observation_id,
            currency=currency,
        ),
        _supplier_candidate(
            anchor_id=ANCHOR_SUPPLIER_CONSENSUS,
            value=consensus_eps,
            basis=ANCHOR_FORWARD,
            months_covered=12.0,
            period_label="consensus forward EPS (the supplier declared no period)",
            provider=provider,
            source_field=consensus_source_field,
            source_url=consensus_source_url,
            source_observation_type=consensus_observation_type,
            source_retrieved_at=consensus_retrieved_at,
            observation_id=consensus_observation_id,
            currency=currency,
        ),
    ]

    if not records:
        candidates.append(
            EpsAnchorCandidate(
                anchor_id=ANCHOR_SEC_ANNUAL,
                available=False,
                nature=NATURE_DIRECT_FILING,
                refusal_code=REFUSAL_NO_DATASET,
                refusal_reason=(
                    f"No SEC diluted-EPS evidence is available for {ticker}: this run "
                    "acquired no filing fact and no tracked SEC dataset holds one. Run "
                    "with --context to acquire the issuer's filing evidence."
                ),
            )
        )
        candidates.append(
            EpsAnchorCandidate(
                anchor_id=ANCHOR_SEC_TTM_FOUR_QUARTERS,
                available=False,
                nature=NATURE_DERIVED,
                refusal_code=REFUSAL_NO_DATASET,
                refusal_reason=(
                    f"No SEC quarterly diluted-EPS evidence is available for {ticker}, so "
                    "no derived twelve-month window is offered."
                ),
            )
        )
        return EpsAnchorCandidateSet(
            ticker=ticker,
            valuation_date=str(valuation_date or ""),
            currency=currency,
            candidates=tuple(candidates),
            evidence_inputs=inputs,
        )

    annual_record, annual_knowability, annuals = _annual_candidate(
        records, valuation_date=valuation_date, scope=SHARE_CLASS_SCOPE_CONSOLIDATED
    )
    if annual_record is None:
        code = (
            REFUSAL_NO_ANNUAL_FACT
            if not annuals
            else REFUSAL_ANNUAL_NOT_KNOWABLE
        )
        reason = (
            annual_knowability.detail
            if annuals
            else (
                "The issuer's SEC evidence holds no directly stated annual "
                "us-gaap:EarningsPerShareDiluted fact of a 10-K fiscal year."
            )
        )
        candidates.append(
            EpsAnchorCandidate(
                anchor_id=ANCHOR_SEC_ANNUAL,
                available=False,
                nature=NATURE_DIRECT_FILING,
                refusal_code=code,
                refusal_reason=reason,
                share_class_scope=SHARE_CLASS_SCOPE_CONSOLIDATED,
            )
        )
    else:
        span = annual_record.span_days or 0
        candidates.append(
            EpsAnchorCandidate(
                anchor_id=ANCHOR_SEC_ANNUAL,
                available=True,
                basis=ANCHOR_FISCAL_YEAR,
                value=annual_record.value,
                months_covered=round(span / DAYS_PER_MONTH, 3),
                nature=NATURE_DIRECT_FILING,
                gaap_basis=GAAP_BASIS_DILUTED,
                source_label=(
                    f"SEC {annual_record.form} {SEC_EPS_CONCEPT}"
                    f" (accession {annual_record.accession})"
                ),
                source_provider=SEC_EPS_SOURCE_PROVIDER,
                source_url=annual_record.source_url,
                period_label=(
                    f"fiscal year {annual_record.fiscal_year}"
                    f"{f' {annual_record.fiscal_period}' if annual_record.fiscal_period else ''}, "
                    f"as filed ({annual_record.period_start} to {annual_record.period_end})"
                ),
                period_start=annual_record.period_start,
                period_end=annual_record.period_end,
                period_undeclared_by_source=False,
                available_at=annual_record.available_at,
                available_at_basis=annual_record.available_at_basis,
                sec_fact=annual_record.component_view(),
                derivation=(
                    "A directly stated figure. The issuer reported this diluted "
                    "earnings-per-share amount for the fiscal year it names. It is "
                    "an annual period, not a trailing twelve-month window, and it is "
                    "never relabelled as one."
                ),
                share_class_scope=SHARE_CLASS_SCOPE_CONSOLIDATED,
            )
        )

    # Per-share-class annual anchors (Phase 2): each scope gets its own entry.
    for scope, anchor_id in (
        (SHARE_CLASS_SCOPE_CLASS_A, "SEC_ANNUAL_DILUTED_EPS_CLASS_A"),
        (SHARE_CLASS_SCOPE_CLASS_B, "SEC_ANNUAL_DILUTED_EPS_CLASS_B"),
        (SHARE_CLASS_SCOPE_CLASS_C, "SEC_ANNUAL_DILUTED_EPS_CLASS_C"),
    ):
        scope_records = [r for r in records if r.share_class_scope == scope]
        if not scope_records:
            continue
        scope_record, scope_knowability, scope_annuals = _annual_candidate(
            scope_records, valuation_date=valuation_date, scope=scope
        )
        if scope_record is None:
            code = (
                REFUSAL_NO_ANNUAL_FACT if not scope_annuals else REFUSAL_ANNUAL_NOT_KNOWABLE
            )
            reason = (
                scope_knowability.detail
                if scope_annuals
                else f"No directly stated annual diluted-EPS fact for scope {scope}."
            )
            candidates.append(
                EpsAnchorCandidate(
                    anchor_id=anchor_id,
                    available=False,
                    nature=NATURE_DIRECT_FILING,
                    refusal_code=code,
                    refusal_reason=reason,
                    share_class_scope=scope,
                )
            )
            continue
        span = scope_record.span_days or 0
        candidates.append(
            EpsAnchorCandidate(
                anchor_id=anchor_id,
                available=True,
                basis=ANCHOR_FISCAL_YEAR,
                value=scope_record.value,
                months_covered=round(span / DAYS_PER_MONTH, 3),
                nature=NATURE_DIRECT_FILING,
                gaap_basis=GAAP_BASIS_DILUTED,
                source_label=(
                    f"SEC {scope_record.form} {SEC_EPS_CONCEPT}"
                    f" (accession {scope_record.accession})"
                ),
                source_provider=SEC_EPS_SOURCE_PROVIDER,
                source_url=scope_record.source_url,
                period_label=(
                    f"fiscal year {scope_record.fiscal_year}"
                    f"{f' {scope_record.fiscal_period}' if scope_record.fiscal_period else ''}, "
                    f"as filed ({scope_record.period_start} to {scope_record.period_end})"
                ),
                period_start=scope_record.period_start,
                period_end=scope_record.period_end,
                period_undeclared_by_source=False,
                available_at=scope_record.available_at,
                available_at_basis=scope_record.available_at_basis,
                sec_fact=scope_record.component_view(),
                derivation=(
                    "A directly stated figure for share-class scope "
                    f"{scope}. The issuer reported this diluted earnings-per-share "
                    "amount for the fiscal year it names."
                ),
                share_class_scope=scope,
            )
        )

    # Derived TTM uses only consolidated (entity-level) facts.
    consolidated_records = [r for r in records if r.share_class_scope == SHARE_CLASS_SCOPE_CONSOLIDATED]
    window_result, window_refusal = _quarter_window(consolidated_records, valuation_date=valuation_date)
    if window_result is None:
        candidates.append(
            EpsAnchorCandidate(
                anchor_id=ANCHOR_SEC_TTM_FOUR_QUARTERS,
                available=False,
                nature=NATURE_DERIVED,
                refusal_code=window_refusal.get("refusal_code", REFUSAL_INCOMPLETE_QUARTERS),
                refusal_reason=window_refusal.get("refusal_reason", ""),
            )
        )
    else:
        window, window_start, window_end = window_result
        total = _sum_window(window)
        if total is None or total <= 0:
            candidates.append(
                EpsAnchorCandidate(
                    anchor_id=ANCHOR_SEC_TTM_FOUR_QUARTERS,
                    available=False,
                    basis=ANCHOR_TTM,
                    nature=NATURE_DERIVED,
                period_start=window_start,
                period_end=window_end,
                refusal_code=REFUSAL_NOT_POSITIVE,
                refusal_reason=(
                    "The four directly stated quarterly diluted-EPS facts sum to a "
                    f"value that is not positive ({total}). A growth rate from it has "
                    "no meaning, so the twelve-month anchor is not offered."
                ),
                share_class_scope=SHARE_CLASS_SCOPE_CONSOLIDATED,
            ),
        )
        else:
            span = _span_days(window_start, window_end) or 0
            classes = sorted({record.evidence_class for record in window})
            available_at, available_at_basis = _latest_instant(window)
            opening = (
                "The window opens on the day after the declared end of the quarter "
                "that precedes its earliest component, because a fiscal fourth "
                "quarter furnished in an earnings release states the period it "
                "closes and not the period it opens."
                if window[0].period_start is None
                else "Every component states both of its period boundaries."
            )
            candidates.append(
                EpsAnchorCandidate(
                    anchor_id=ANCHOR_SEC_TTM_FOUR_QUARTERS,
                    available=True,
                    basis=ANCHOR_TTM,
                    value=total,
                    months_covered=round(span / DAYS_PER_MONTH, 3),
                    nature=NATURE_DERIVED,
                    gaap_basis=GAAP_BASIS_DILUTED,
                    source_label=(
                        "Sum of four directly stated quarterly diluted-EPS facts"
                        + (f" ({', '.join(classes)} evidence)" if len(classes) > 1 else f" ({classes[0]} evidence)")
                    ),
                    source_provider=SEC_EPS_SOURCE_PROVIDER,
                    period_label=(
                        f"four consecutive quarters, {window_start} to {window_end} "
                        f"(summed, not stated by the issuer)"
                    ),
                    period_start=window_start,
                    period_end=window_end,
                    period_undeclared_by_source=False,
                    available_at=available_at,
                    available_at_basis=available_at_basis,
                    sec_components=tuple(record.component_view() for record in window),
                    derivation=(
                        "Sum of four directly stated discrete quarterly "
                        "us-gaap:EarningsPerShareDiluted facts. The sum is this "
                        "engine's arithmetic: no issuer stated a twelve-month figure "
                        "for this window. Per-share amounts are not strictly additive "
                        "when the share denominator changes, which is why the audited "
                        "annual figure is kept beside it rather than reconciled into "
                        f"it. {opening}"
                    ),
                    annual_comparison=_annual_comparison(
                        annual_record, window_start, window_end, total
                    ),
                    share_class_scope=SHARE_CLASS_SCOPE_CONSOLIDATED,
                )
            )

    return EpsAnchorCandidateSet(
        ticker=ticker,
        valuation_date=str(valuation_date or ""),
        currency=currency,
        candidates=tuple(candidates),
        evidence_inputs=inputs,
    )


def _annual_comparison(
    annual: Optional[EpsFactRecord],
    window_start: str,
    window_end: str,
    derived_total: float,
) -> Dict[str, Any]:
    """
    The audited annual figure beside a derived window, or why it is not comparable.

    A four-quarter sum and an audited annual figure cover the same window but
    are not the same measurement: the sum adds four separately rounded per-share
    amounts, each divided by that quarter's own weighted-average share count.
    When the two windows are the same and the figures differ, both are reported
    and the difference is explained. When the windows differ, the two are not
    compared at all, because comparing figures that cover different periods says
    nothing about either.
    """
    if annual is None:
        return {
            "comparable": False,
            "reason": (
                "No directly stated annual diluted-EPS fact is public at this "
                "valuation date, so the summed window has no audited annual figure "
                "to sit beside."
            ),
        }
    same_window = annual.period_start == window_start and annual.period_end == window_end
    if not same_window:
        return {
            "comparable": False,
            "annual_period_start": annual.period_start,
            "annual_period_end": annual.period_end,
            "annual_value": annual.value,
            "annual_accession": annual.accession,
            "reason": (
                f"The latest annual figure covers {annual.period_start or 'an undeclared start'} "
                f"to {annual.period_end}, which is not the same window as the summed "
                f"{window_start} to {window_end}. The two are different periods and are "
                "not compared."
            ),
        }
    difference = abs(annual.value - derived_total)
    agrees = difference <= SUM_VS_ANNUAL_TOLERANCE
    return {
        "comparable": True,
        "annual_period_start": annual.period_start,
        "annual_period_end": annual.period_end,
        "annual_value": annual.value,
        "annual_accession": annual.accession,
        "annual_form": annual.form,
        "annual_filed_date": annual.filed,
        "annual_evidence_class": annual.evidence_class,
        "derived_value": derived_total,
        "difference": round(annual.value - derived_total, 6),
        "agrees": agrees,
        "tolerance": SUM_VS_ANNUAL_TOLERANCE,
        "reason": (
            "The audited annual figure and the four-quarter sum cover the same "
            f"window and agree within {SUM_VS_ANNUAL_TOLERANCE:g}. Both are kept; "
            "neither replaces the other."
            if agrees
            else (
                "The audited annual figure and the four-quarter sum cover the same "
                f"window but differ by {abs(annual.value - derived_total):.4g} per share. "
                "Both are kept as stated and neither is adjusted: per-share amounts "
                "are not strictly additive across quarters with different weighted-average "
                "share counts, so the difference is a basis difference rather than an "
                "error to be reconciled. The matrix uses the figure the selected anchor "
                "names, and this note records that the other exists."
            )
        ),
    }


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AnchorSelection:
    """What was asked for, what was found, and what was refused."""

    requested: Optional[str]
    candidate: Optional[EpsAnchorCandidate]
    refused: List[Dict[str, Any]] = field(default_factory=list)
    mode: str = "EXPLICIT"
    rule: str = SELECTION_RULE

    def contract_view(self) -> Dict[str, Any]:
        return {
            "requested": self.requested,
            "mode": self.mode,
            "rule": self.rule,
            "selected_anchor_id": self.candidate.anchor_id if self.candidate else None,
            "refused": [dict(item) for item in self.refused],
        }


def is_explicit_anchor_id(requested: Optional[str]) -> bool:
    """Whether a request names a catalogue anchor rather than a legacy preference."""
    return bool(requested) and str(requested) in SEC_EPS_ANCHOR_IDS


# The preference words the pre-catalogue path answered. A request spelled as
# one of these is a legacy preference, not a catalogue anchor, and keeps the
# behaviour it always had; anything else that is not a catalogue identifier is
# refused rather than reinterpreted.
LEGACY_ANCHOR_PREFERENCES: Tuple[str, ...] = ("trailing", "forward", "consensus")


def is_legacy_anchor_preference(requested: Optional[str]) -> bool:
    """Whether a request is the legacy preference word it has always been."""
    return bool(requested) and str(requested).strip().lower() in LEGACY_ANCHOR_PREFERENCES


def unknown_anchor_request_refusal(requested: str) -> Dict[str, Any]:
    """
    The refusal for a request that names no catalogue anchor.

    A named request is never silently reinterpreted as a legacy preference:
    the caller receives this refusal and no starting anchor at all, because
    substituting a figure the caller did not name is the one outcome a reader
    cannot detect.
    """
    return {
        "item": f"eps_anchor_candidate.{requested}",
        "reason": (
            f"{requested!r} is not an EPS anchor in the catalogue. Available "
            f"identifiers: {', '.join(SEC_EPS_ANCHOR_IDS)}. No other figure is "
            "substituted for it."
        ),
        "reason_kind": REFUSAL_UNKNOWN_ANCHOR_ID,
        "blocks": ["start_anchor"],
    }


def select_anchor(
    candidate_set: EpsAnchorCandidateSet,
    requested: Optional[str],
) -> AnchorSelection:
    """
    The anchor an explicit request names, or a refusal.

    An explicit request is never satisfied by a different figure. If the named
    anchor is unavailable the result carries no candidate and states the reason
    the named one could not be offered, because a substituted number is the one
    outcome a reader cannot detect.
    """
    if not requested:
        return AnchorSelection(
            requested=None,
            candidate=None,
            refused=[],
            mode="NOT_REQUESTED",
        )

    name = str(requested)
    if name not in SEC_EPS_ANCHOR_IDS:
        return AnchorSelection(
            requested=name,
            candidate=None,
            refused=[
                {
                    "item": f"eps_anchor_candidate.{name}",
                    "reason": (
                        f"{name!r} is not an EPS anchor in the catalogue. Available "
                        f"identifiers: {', '.join(SEC_EPS_ANCHOR_IDS)}."
                    ),
                    "reason_kind": REFUSAL_UNKNOWN_ANCHOR_ID,
                    "blocks": ["start_anchor"],
                }
            ],
        )

    candidate = candidate_set.get(name)
    if candidate is not None and candidate.available:
        return AnchorSelection(requested=name, candidate=candidate, refused=[])
    if candidate is None:
        reason = "This issuer's catalogue holds no entry under that identifier."
        code = REFUSAL_UNKNOWN_ANCHOR_ID
    else:
        reason = candidate.refusal_reason
        code = candidate.refusal_code
    return AnchorSelection(
        requested=name,
        candidate=None,
        refused=[
            {
                "item": f"eps_anchor_candidate.{name}",
                "reason": (
                    f"The EPS anchor {name} was requested and is not available: {reason} "
                    "No other figure is substituted for it."
                ),
                "reason_kind": code or REFUSAL_SUPPLIER_NOT_OBSERVED,
                "blocks": ["start_anchor"],
            }
        ],
    )


def candidate_to_eps_anchor(
    candidate: EpsAnchorCandidate,
    *,
    currency: Optional[str] = None,
) -> EpsAnchor:
    """
    The matrix's starting anchor for one adopted catalogue entry.

    The conversion carries the entry's whole identity across: what the figure
    is, the period it covers, the source that recorded it, its accounting
    basis, when it became public, and its directly stated or derived nature.
    The run-level `source_type` is left empty for the caller to set from its
    own execution context, because the catalogue describes the figure's source
    and the run describes how this execution obtained it.
    """
    if not candidate.available or candidate.value is None:
        raise ValueError(
            f"cannot build a starting anchor from the unavailable entry {candidate.anchor_id}"
        )
    return EpsAnchor(
        value=candidate.value,
        basis=candidate.basis,
        months_covered=candidate.months_covered,
        period_label=candidate.period_label,
        period_start=candidate.period_start,
        period_end=candidate.period_end,
        provider=candidate.source_provider or candidate.source_label,
        currency=currency,
        period_undeclared_by_source=candidate.period_undeclared_by_source,
        source_type="",
        observation_id=candidate.observation_id,
        is_user_assumption=False,
        sec_fact=dict(candidate.sec_fact) if candidate.sec_fact else None,
        sec_related_evidence=None,
        source_field=candidate.source_field,
        source_url=candidate.source_url,
        source_provider=candidate.source_provider,
        anchor_id=candidate.anchor_id,
        anchor_nature=candidate.nature,
        anchor_gaap_basis=candidate.gaap_basis,
        anchor_available_at=candidate.available_at,
        anchor_available_at_basis=candidate.available_at_basis,
        sec_components=tuple(dict(item) for item in candidate.sec_components),
        anchor_derivation=candidate.derivation,
        annual_comparison=(
            dict(candidate.annual_comparison) if candidate.annual_comparison else None
        ),
    )
