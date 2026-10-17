"""Issuer-declared fiscal period identity for SEC XBRL duration facts.

Why this module exists
----------------------

The historical P/E and P/FCF pipelines used to label every duration fact's
fiscal year and quarter with a month grid (`fiscal_year_of` / `quarter_number`
over a fiscal-year-end month). That grid cannot represent 52/53-week fiscal
calendars, whose quarter ends drift across month boundaries: Micron's June
quarter ends are fiscal Q3, its early-September fiscal year ends are fiscal
Q4, and Apple's 14-week first quarters push Q2 onto April 1 and Q3 onto
July 1 in some years. The grid misassigned 11 of MU's 38 quarter ends and 4
of AAPL's 42, produced collided fiscal positions and impossible TTM windows,
and blocked MU's FY2026 TTM entirely.

This module derives each period's fiscal identity from the issuer's own
declarations instead, in decreasing order of authority:

1. PRIMARY_FILING_FOCUS -- the 10-Q/10-K whose conformed period of report
   equals the fact's period end. Its XBRL `fy` (dei:FiscalYearFocus) and `fp`
   (dei:FiscalPeriodFocus) are the issuer's own label for that period; a 10-K
   period end is the fiscal year's fourth quarter.
2. PRIOR_YEAR_COMPARATIVE -- a 10-Q instance whose fact period end sits one
   fiscal year (364 or 371 days, within tolerance) before the filing's own
   period end is that filing's fiscal quarter one year earlier.
3. ANNUAL_SPAN_POSITION -- a quarter end contained in an issuer-declared
   annual span sits a whole number of quarters before that fiscal year's end;
   the offset picks the quarter (0 -> Q4, ~13 weeks -> Q3, ~26 -> Q2, ~39 -> Q1).

Rules are cross-checked where several apply; an end that cannot be identified
is returned as unresolved so callers can exclude it explicitly instead of
silently assigning a neighbouring quarter. The model never decides when
information became public: usable dates remain the filings' own acceptance-
derived dates, unchanged by identity.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

QUARTER_MIN_DAYS = 80
QUARTER_MAX_DAYS = 100
YEAR_MIN_DAYS = 350
YEAR_MAX_DAYS = 380

IDENTITY_PRIMARY = "PRIMARY_FILING_FOCUS"
IDENTITY_COMPARATIVE = "PRIOR_YEAR_COMPARATIVE"
IDENTITY_SPAN_POSITION = "ANNUAL_SPAN_POSITION"

_YEAR = 364.25


def _parse_date(value: str) -> datetime.date:
    return datetime.date.fromisoformat(value[:10])


def _years_back(delta_days: int) -> Optional[int]:
    """Whole fiscal years between two period ends, or None if not integral."""
    years = round(delta_days / _YEAR)
    if years < 0 or abs(delta_days - years * _YEAR) > 14:
        return None
    return years


@dataclass(frozen=True)
class FiscalPeriodIdentity:
    """One period end's issuer-declared fiscal year and quarter."""

    fiscal_year: int
    fiscal_quarter: int
    period_end: str
    identity_source: str
    primary_form: Optional[str] = None
    primary_accession: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fiscal_year": self.fiscal_year,
            "fiscal_quarter": self.fiscal_quarter,
            "period_end": self.period_end,
            "identity_source": self.identity_source,
            "primary_form": self.primary_form,
            "primary_accession": self.primary_accession,
        }


@dataclass
class FiscalCalendar:
    """Issuer-declared fiscal identities for one filer's reported periods."""

    quarter_identity: Dict[str, FiscalPeriodIdentity] = field(default_factory=dict)
    annual_fiscal_year: Dict[str, int] = field(default_factory=dict)
    unresolved: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)

    def fiscal_year_end(self, fiscal_year: int) -> Optional[str]:
        """The annual period end the issuer declared for a fiscal year."""
        for end, fy in self.annual_fiscal_year.items():
            if fy == fiscal_year:
                return end
        return None

    def identity_for(self, period_end: str) -> Optional[FiscalPeriodIdentity]:
        return self.quarter_identity.get(period_end)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quarter_identity": {
                end: identity.to_dict()
                for end, identity in sorted(self.quarter_identity.items())
            },
            "annual_fiscal_year": dict(sorted(self.annual_fiscal_year.items())),
            "unresolved": list(self.unresolved),
            "warnings": list(self.warnings),
        }


def _instance_key(instance: Dict[str, Any]) -> Tuple[str, str, str]:
    return (instance["start"], instance["end"], instance["accn"])


def _resolve_annual_spans(
    annual_spans: Dict[str, List[Dict[str, Any]]],
    filings_index: Mapping[str, Mapping[str, Any]],
    warnings: List[Dict[str, Any]],
) -> Tuple[Dict[str, int], Dict[str, int]]:
    """Fiscal year per annual span end, from 10-K declarations.

    A primary instance (the 10-K whose period of report is the span end)
    declares its own fiscal year; a comparative instance in a later 10-K
    declares a prior fiscal year at a whole-year distance.
    """
    resolved: Dict[str, int] = {}
    candidates: Dict[str, List[Tuple[int, str, str]]] = {}
    for span_end, instances in annual_spans.items():
        for instance in instances:
            meta = filings_index.get(instance["accn"])
            if meta is None or instance["form"] != "10-K":
                continue
            fy = instance.get("fy")
            if not isinstance(fy, int):
                continue
            if meta["period_end"] == span_end:
                candidates.setdefault(span_end, []).append((fy, "primary", instance["accn"]))
                continue
            delta = (_parse_date(meta["period_end"]) - _parse_date(span_end)).days
            years = _years_back(delta)
            if years is not None and years >= 1:
                candidates.setdefault(span_end, []).append((fy - years, "comparative", instance["accn"]))

    for span_end, found in candidates.items():
        primary_found = [item for item in found if item[1] == "primary"]
        primary_values = {fy for fy, _, _ in primary_found}
        if len(primary_values) > 1:
            warnings.append(
                {
                    "annual_period_end": span_end,
                    "reason": "annual primary instances declare different fiscal years",
                    "candidates": [
                        {"fiscal_year": fy, "basis": basis, "accession": accn}
                        for fy, basis, accn in found
                    ],
                }
            )
            continue
        if primary_found:
            resolved[span_end] = sorted(primary_values)[0]
            continue
        comparative_values = {fy for fy, _, _ in found}
        if len(comparative_values) > 1:
            warnings.append(
                {
                    "annual_period_end": span_end,
                    "reason": "annual comparative instances declare different fiscal years",
                    "candidates": [
                        {"fiscal_year": fy, "basis": basis, "accession": accn}
                        for fy, basis, accn in found
                    ],
                }
            )
            continue
        if comparative_values:
            resolved[span_end] = sorted(comparative_values)[0]
    return resolved, {span_end: min((_parse_date(i["start"]) for i in spans), default=None) for span_end, spans in annual_spans.items()}


def _quarter_from_offset(offset_days: int) -> Optional[int]:
    """Quarter position from the distance to the fiscal year end."""
    if offset_days <= 45:
        return 4
    if offset_days <= 136:
        return 3
    if offset_days <= 227:
        return 2
    if offset_days <= 320:
        return 1
    return None


def build_fiscal_calendar(
    concept_payloads: Sequence[Mapping[str, Any]],
    filings_index: Mapping[str, Mapping[str, Any]],
    units: Optional[Sequence[str]] = None,
) -> FiscalCalendar:
    """Derive issuer-declared fiscal identities from XBRL duration facts.

    `concept_payloads` are SEC companyconcept-style payloads; every duration
    fact (with start and end) contributes a span instance. `filings_index`
    maps accession to at least {"period_end", "form"}. Spans whose accession
    is absent from the index carry no usable declaration and are ignored.
    """
    quarter_spans: Dict[str, List[Dict[str, Any]]] = {}
    annual_spans: Dict[str, List[Dict[str, Any]]] = {}
    seen: set = set()
    for payload in concept_payloads:
        for unit, facts in (payload.get("units") or {}).items():
            if units is not None and unit not in units:
                continue
            for fact in facts:
                start, end = fact.get("start"), fact.get("end")
                if not start or not end:
                    continue
                key = _instance_key(fact)
                if key in seen:
                    continue
                seen.add(key)
                span_days = (_parse_date(end) - _parse_date(start)).days
                instance = dict(fact)
                if YEAR_MIN_DAYS <= span_days <= YEAR_MAX_DAYS:
                    annual_spans.setdefault(end, []).append(instance)
                # Every duration span end is a quarter-end candidate: a 3M
                # span ends where Q1/Q2/Q3 ends, a 6M/9M cumulative span ends
                # where Q2/Q3 ends, and a fiscal-year span ends where Q4
                # ends. Identity is a property of the period end, not of the
                # span length, and cumulative-only filers (whose discrete Q2
                # and Q3 are derived by differencing 6M/9M spans) need their
                # quarter ends identified from the cumulative spans' ends.
                quarter_spans.setdefault(end, []).append(instance)

    calendar = FiscalCalendar()
    annual_fy, annual_starts = _resolve_annual_spans(
        annual_spans, filings_index, calendar.warnings
    )
    calendar.annual_fiscal_year = annual_fy
    ordered_annual = sorted(
        (
            (span_end, annual_starts.get(span_end), span_end)
            for span_end, fy in annual_fy.items()
        ),
        key=lambda item: item[1] or _parse_date(item[2]),
    )

    def annual_containment(end: str) -> Optional[Tuple[int, int, str]]:
        """(fiscal_year, quarter, source) for a quarter end inside an annual span."""
        end_d = _parse_date(end)
        for span_end, span_start, _ in ordered_annual:
            span_end_d = _parse_date(span_end)
            if end_d > span_end_d:
                continue
            if span_start is not None and end_d < span_start:
                continue
            offset = (span_end_d - end_d).days
            quarter = _quarter_from_offset(offset)
            if quarter is not None:
                fy = annual_fy[span_end]
                return fy, quarter, IDENTITY_SPAN_POSITION
        return None

    for end in sorted(quarter_spans):
        instances = quarter_spans[end]
        primary_candidates: List[Tuple[int, int, str, str, str]] = []
        comparative_candidates: List[Tuple[int, int, str, str]] = []
        for instance in instances:
            meta = filings_index.get(instance["accn"])
            if meta is None:
                continue
            form = instance["form"]
            fy = instance.get("fy")
            fp = (instance.get("fp") or "").upper()
            if form in ("10-Q", "10-K") and meta["period_end"] == end:
                if form == "10-K":
                    primary_candidates.append((fy, 4, form, instance["accn"], instance.get("filed") or ""))
                elif fp in ("Q1", "Q2", "Q3", "Q4"):
                    primary_candidates.append(
                        (fy, int(fp[1]), form, instance["accn"], instance.get("filed") or "")
                    )
            elif form == "10-Q" and isinstance(fy, int) and fp in ("Q1", "Q2", "Q3", "Q4"):
                delta = (_parse_date(meta["period_end"]) - _parse_date(end)).days
                years = _years_back(delta)
                if years is not None and years == 1:
                    comparative_candidates.append(
                        (fy - years, int(fp[1]), instance["accn"], instance.get("filed") or "")
                    )

        identity: Optional[FiscalPeriodIdentity] = None
        if primary_candidates:
            values = {(fy, q) for fy, q, _, _, _ in primary_candidates}
            if len(values) > 1:
                calendar.warnings.append(
                    {
                        "period_end": end,
                        "reason": "primary instances declare different fiscal periods",
                        "candidates": [
                            {"fiscal_year": fy, "fiscal_quarter": q, "form": form, "accession": accn}
                            for fy, q, form, accn, _ in primary_candidates
                        ],
                    }
                )
                calendar.unresolved.append(
                    {
                        "period_end": end,
                        "reason": "primary instances declare different fiscal periods",
                        "candidates": [
                            {"fiscal_year": fy, "fiscal_quarter": q, "basis": IDENTITY_PRIMARY, "accession": accn}
                            for fy, q, _, accn, _ in primary_candidates
                        ],
                    }
                )
                continue
            fy, q, form, accession, _ = sorted(
                primary_candidates, key=lambda item: (item[2] != "10-Q", item[4], item[3])
            )[0]
            identity = FiscalPeriodIdentity(
                fiscal_year=fy,
                fiscal_quarter=q,
                period_end=end,
                identity_source=IDENTITY_PRIMARY,
                primary_form=form,
                primary_accession=accession,
            )
        else:
            derived: List[Tuple[int, int, str, str]] = [
                (fy, q, IDENTITY_COMPARATIVE, accn) for fy, q, accn, _ in comparative_candidates
            ]
            containment = annual_containment(end)
            if containment is not None:
                derived.append((containment[0], containment[1], IDENTITY_SPAN_POSITION, None))
            values = {(fy, q) for fy, q, _, _ in derived}
            if not derived:
                calendar.unresolved.append(
                    {
                        "period_end": end,
                        "reason": "no issuer declaration identifies this period",
                        "forms": sorted({i["form"] for i in instances}),
                    }
                )
                continue
            if len(values) > 1:
                calendar.unresolved.append(
                    {
                        "period_end": end,
                        "reason": "issuer declarations disagree on this period's identity",
                        "candidates": [
                            {"fiscal_year": fy, "fiscal_quarter": q, "basis": basis}
                            for fy, q, basis, _ in derived
                        ],
                    }
                )
                continue
            fy, q, basis, accession = derived[0]
            identity = FiscalPeriodIdentity(
                fiscal_year=fy,
                fiscal_quarter=q,
                period_end=end,
                identity_source=basis,
                primary_form="10-Q",
                primary_accession=accession,
            )
        calendar.quarter_identity[end] = identity

    return calendar


def build_fiscal_calendar_from_identities(
    quarter_identities: Mapping[str, Tuple[int, int]],
    annual_fiscal_year: Optional[Mapping[str, int]] = None,
) -> FiscalCalendar:
    """A calendar from caller-supplied declarations (synthetic fixtures)."""
    calendar = FiscalCalendar()
    for end, (fy, q) in quarter_identities.items():
        calendar.quarter_identity[end] = FiscalPeriodIdentity(
            fiscal_year=fy,
            fiscal_quarter=q,
            period_end=end,
            identity_source=IDENTITY_PRIMARY,
        )
    calendar.annual_fiscal_year = dict(annual_fiscal_year or {})
    return calendar
