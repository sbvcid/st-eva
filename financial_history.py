"""
Financial history assembled from sourced observations.

The point of this module is that a research reader can see how a number moved,
not just what it is today. It turns a set of period-scoped observations into
ordered series with growth rates and margins, where every row keeps the period
it covers, the unit and currency it is denominated in, the date the source
made it available, and the document it came from.

Three rules the arithmetic obeys:

1. **A growth rate is only computed between comparable periods.** Two figures
   are comparable when they cover the same kind of window (annual against
   annual, quarterly against quarterly) and end roughly a year apart. A
   quarterly figure is never differenced against an annual one, because the
   result would be a difference in measurement, not in performance.

2. **A margin is only computed inside one period.** Net income is divided by
   the revenue of the *same* period end. Dividing a trailing net income by an
   annual revenue would produce a number that looks like a margin and is not.

3. **Nothing is filled in.** A period with no observation is absent from the
   series rather than interpolated, carried forward or set to zero. The gap is
   visible, which is the useful information.

The module is pure: it takes observations and returns plain data. It performs
no I/O and makes no judgement about which periods matter most.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from data_contract import currencies_match, safe_float


HISTORY_FORMULA_VERSION = "financial-history/1.0"

# A window is annual if it covers most of a year and quarterly if it covers
# roughly a quarter. The bounds are deliberately loose because fiscal calendars
# do not align with calendar quarters.
_ANNUAL_MIN_DAYS = 330
_ANNUAL_MAX_DAYS = 400
_QUARTER_MIN_DAYS = 80
_QUARTER_MAX_DAYS = 100

# Two period ends further apart than this are not treated as a year-over-year
# pair. A filing calendar drift or a 53-week year should not silently produce a
# growth rate computed over the wrong span.
_YEAR_OVER_YEAR_MIN_DAYS = 350
_YEAR_OVER_YEAR_MAX_DAYS = 380

_WINDOW_ANNUAL = "ANNUAL"
_WINDOW_QUARTERLY = "QUARTERLY"
_WINDOW_INSTANT = "INSTANT"


class HistoryError(ValueError):
    """An input that makes a requested history figure undefined."""


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _span_days(observation: Any) -> Optional[int]:
    start = _parse_date(getattr(observation, "period_start", None))
    end = _parse_date(getattr(observation, "period_end", None))
    if start is None or end is None:
        return None
    return (end - start).days


def classify_window(observation: Any) -> str:
    """
    Whether a figure covers a year, a quarter, or is a point-in-time balance.

    Classified from the observation's own declared period rather than from its
    metric name, because the same metric can appear with both a duration and an
    instant form depending on the concept the issuer reported.
    """
    start_raw = getattr(observation, "period_start", None)
    end_raw = getattr(observation, "period_end", None)
    if not end_raw:
        return "MISSING_DATE"
    end = _parse_date(end_raw)
    if end is None:
        return "MISSING_DATE"
    if not start_raw:
        return _WINDOW_INSTANT
    start = _parse_date(start_raw)
    if start is None:
        return "MISSING_DATE"
    if start == end:
        return _WINDOW_INSTANT
    span = (end - start).days
    if span < 0:
        return "INVALID_PERIOD"
    if _ANNUAL_MIN_DAYS <= span <= _ANNUAL_MAX_DAYS:
        return _WINDOW_ANNUAL
    if _QUARTER_MIN_DAYS <= span <= _QUARTER_MAX_DAYS:
        return _WINDOW_QUARTERLY
    return "OTHER_%d_DAYS" % span


@dataclass(frozen=True)
class HistoryPoint:
    """One period of one metric, with the provenance a reader needs to trust it."""

    metric: str
    value: float
    unit: str
    currency: Optional[str]
    window: str
    period_start: Optional[str]
    period_end: Optional[str]
    as_of: Optional[str]
    available_at: Optional[str]
    available_at_basis: str
    provider: str
    source_type: str
    definition: str
    derivation: str = ""
    span_days: Optional[int] = None
    form: str = ""
    accession: str = ""
    alternate_derivations: Tuple[str, ...] = ()
    fiscal_year: Optional[int] = None
    fiscal_period: Optional[str] = None
    status: str = "UNVERIFIABLE"
    status_reasons: Tuple[str, ...] = ()

    def contract_view(self) -> Dict[str, Any]:
        return {
            "metric": self.metric,
            "value": self.value,
            "unit": self.unit,
            "currency": self.currency,
            "window": self.window,
            "period_type": (
                "INSTANT" if self.window == _WINDOW_INSTANT else "DURATION"
            ),
            "period_start": self.period_start,
            "period_end": self.period_end,
            "as_of": self.as_of,
            "available_at": self.available_at,
            "available_at_basis": self.available_at_basis,
            "provider": self.provider,
            "source_type": self.source_type,
            "definition": self.definition,
            "derivation": self.derivation,
            "alternate_derivations": list(self.alternate_derivations),
            "span_days": self.span_days,
            "form": self.form,
            "accession": self.accession,
            "fiscal_year": self.fiscal_year,
            "fiscal_period": self.fiscal_period,
            "status": self.status,
            "status_reasons": list(self.status_reasons),
            "formula_version": HISTORY_FORMULA_VERSION,
        }


@dataclass
class HistorySeries:
    """An ordered series for one metric, plus the reasons gaps exist."""

    metric: str
    window: str
    points: List[HistoryPoint] = field(default_factory=list)
    unavailable: List[Dict[str, Any]] = field(default_factory=list)

    def contract_view(self) -> Dict[str, Any]:
        return {
            "metric": self.metric,
            "window": self.window,
            "count": len(self.points),
            "points": [point.contract_view() for point in self.points],
            "unavailable": list(self.unavailable),
            "formula_version": HISTORY_FORMULA_VERSION,
        }


def _provenance(observation: Any, window: str) -> Tuple[str, str, str]:
    """Derivation kind, form and accession, read from the observation's own record."""
    raw = getattr(observation, "raw", None)
    derivation = ""
    form = ""
    accession = ""
    if isinstance(raw, dict):
        derivation = str(raw.get("derivation") or "")
        constituents = raw.get("constituents")
        if isinstance(constituents, list) and constituents:
            first = constituents[0]
            if isinstance(first, dict):
                form = str(first.get("form") or "")
                accession = str(first.get("accession") or "")
        if not form:
            form = str(raw.get("form") or "")
        if not accession:
            accession = str(raw.get("accession") or "")
        sec_fact = raw.get("sec_fact")
        if isinstance(sec_fact, dict):
            if not form:
                form = str(sec_fact.get("form") or "")
            if not accession:
                accession = str(sec_fact.get("accession") or "")
        if not derivation:
            basis = getattr(observation, "basis", None)
            if isinstance(basis, dict):
                derivation = str(basis.get("derivation") or "")
    if not form:
        basis = getattr(observation, "basis", None)
        if isinstance(basis, dict):
            form = str(basis.get("form") or "")
    return derivation, form, accession


def _fiscal_context(observation: Any) -> Tuple[Optional[int], Optional[str]]:
    raw = getattr(observation, "raw", None)
    fy = None
    fp = None
    if isinstance(raw, dict):
        fy = raw.get("fy")
        fp = raw.get("fp")
        sec_fact = raw.get("sec_fact")
        if isinstance(sec_fact, dict):
            if fy is None:
                fy = sec_fact.get("fy")
            if fp is None:
                fp = sec_fact.get("fp")
    if fy is not None:
        try:
            fy = int(fy)
        except (ValueError, TypeError):
            fy = None
    if fp is not None:
        fp = str(fp)
    return fy, fp


def _to_point(observation: Any, window: str) -> Optional[HistoryPoint]:
    value = safe_float(getattr(observation, "value", None))
    if value is None:
        return None
    derivation, form, accession = _provenance(observation, window)
    fy, fp = _fiscal_context(observation)
    status_val = getattr(observation, "status", None)
    status_str = status_val.value if hasattr(status_val, "value") else (str(status_val) if status_val is not None else "UNVERIFIABLE")
    reasons = tuple(str(r) for r in getattr(observation, "status_reasons", ()) or ())
    return HistoryPoint(
        metric=str(getattr(observation, "metric", "")),
        value=value,
        unit=str(getattr(observation, "unit", "")),
        currency=getattr(observation, "currency", None),
        window=window,
        period_start=getattr(observation, "period_start", None),
        period_end=getattr(observation, "period_end", None),
        as_of=getattr(observation, "as_of", None),
        available_at=getattr(observation, "available_at", None),
        available_at_basis=str(getattr(observation, "available_at_basis", "")),
        provider=str(getattr(observation, "provider", "")),
        source_type=str(getattr(observation, "source_type", "")),
        definition=str(getattr(observation, "definition", "")),
        derivation=derivation,
        span_days=_span_days(observation),
        form=form,
        accession=accession,
        fiscal_year=fy,
        fiscal_period=fp,
        status=status_str,
        status_reasons=reasons,
    )


def _provenance_richness(point: HistoryPoint) -> Tuple[int, int, int]:
    """How much a point can say about where it came from."""
    return (
        1 if point.derivation else 0,
        1 if point.form else 0,
        1 if point.accession else 0,
    )


def _deduplicate(points: Sequence[HistoryPoint]) -> List[HistoryPoint]:
    """
    Collapse observations that describe the same fact twice.

    A filing fact and the trailing-window aggregate derived from it can arrive
    as two observations of the same metric, window and period end. When they
    agree on the value they are one fact reached two ways, so the point with
    the richer provenance is kept and the other derivation is recorded on it.
    Keeping both would give a reader duplicate rows and duplicate margins.

    When the values disagree this is a genuine conflict between two sources, so
    both are kept and the conflict is reported. Silently preferring one would
    decide a question the module has no basis to decide.
    """
    kept: List[HistoryPoint] = []
    by_key: Dict[Tuple[Optional[str], float], HistoryPoint] = {}

    for point in points:
        key = (point.period_end, point.value)
        existing = by_key.get(key)
        if existing is None:
            kept.append(point)
            by_key[key] = point
            continue

        winner, loser = (
            (point, existing)
            if _provenance_richness(point) > _provenance_richness(existing)
            else (existing, point)
        )
        merged = tuple(
            sorted(
                set(winner.alternate_derivations)
                | ({loser.derivation} if loser.derivation else set())
                | ({loser.alternate_derivations} if loser.alternate_derivations else set())
                - ({winner.derivation} if winner.derivation else set())
            )
        )
        winner = _with_alternates(winner, merged)
        kept[kept.index(loser)] = winner
        by_key[key] = winner

    kept.sort(key=lambda p: (p.period_end or "", p.available_at or ""))
    return kept


def _with_alternates(point: HistoryPoint, alternates: Tuple[str, ...]) -> HistoryPoint:
    """A copy of the point carrying its alternate derivation paths."""
    from dataclasses import replace

    return replace(point, alternate_derivations=alternates)


def build_series(
    observations: Iterable[Any],
    metric: str,
    window: str,
) -> HistorySeries:
    """
    The ordered series for one metric and one window shape.

    Where two observations of the same period agree, they are one fact and the
    better-documented one is kept. Where they disagree, both are kept and the
    conflict is reported rather than resolved.
    """
    series = HistorySeries(metric=metric, window=window)
    raw_points: List[HistoryPoint] = []
    conflicts: List[Dict[str, Any]] = []

    for observation in observations:
        if str(getattr(observation, "metric", "")) != metric:
            continue
        if classify_window(observation) != window:
            continue
        point = _to_point(observation, window)
        if point is not None:
            raw_points.append(point)

    raw_points.sort(key=lambda p: (p.period_end or "", p.available_at or ""))

    seen_values: Dict[Optional[str], set] = {}
    for point in raw_points:
        seen_values.setdefault(point.period_end, set()).add(point.value)
    for period_end, values in sorted(seen_values.items(), key=lambda kv: kv[0] or ""):
        if len(values) > 1:
            conflicts.append(
                {
                    "item": "%s.%s@%s" % (metric, window.lower(), period_end),
                    "reason": (
                        "Two observations cover this period end with different values (%s). "
                        "Both are kept and no winner is selected, because choosing between "
                        "them is a judgement about which source is right."
                        % ", ".join("%.6g" % value for value in sorted(values))
                    ),
                    "reason_kind": "SOURCE_CONFLICT",
                    "blocks": [],
                }
            )

    series.points = _deduplicate(raw_points)
    series.unavailable.extend(conflicts)

    if not series.points:
        series.unavailable.append(
            {
                "item": "%s.%s" % (metric, window.lower()),
                "reason": (
                    "No %s observation covering a %s window was acquired for this run, "
                    "so the series is absent rather than empty-by-default."
                    % (metric, window.lower())
                ),
                "reason_kind": "MISSING",
                "blocks": ["financial_history"],
            }
        )
    return series


def growth_against_prior_year(points: Sequence[HistoryPoint]) -> List[Dict[str, Any]]:
    """
    Year-over-year growth for each point that has a comparable predecessor.

    A point with no comparable predecessor gets an entry with a null rate and a
    stated reason, so the reader can tell "no growth rate was computable" from
    "the growth rate was zero".
    """
    rows: List[Dict[str, Any]] = []
    for index, point in enumerate(points):
        if point.window == _WINDOW_INSTANT:
            rows.append(
                {
                    "period_end": point.period_end,
                    "value": point.value,
                    "prior_period_end": None,
                    "prior_value": None,
                    "growth": None,
                    "comparable": False,
                    "reason": (
                        "This is a point-in-time balance observed at an effective date. "
                        "It has no duration to compound over, so no growth rate is "
                        "computed for it."
                    ),
                }
            )
            continue

        end = _parse_date(point.period_end)
        prior_candidates = []
        if end is not None:
            for earlier in points[:index]:
                if earlier.window != point.window or earlier.window == _WINDOW_INSTANT:
                    continue
                earlier_end = _parse_date(earlier.period_end)
                if earlier_end is None:
                    continue
                gap = (end - earlier_end).days
                if _YEAR_OVER_YEAR_MIN_DAYS <= gap <= _YEAR_OVER_YEAR_MAX_DAYS:
                    prior_candidates.append((earlier, gap))

        if not prior_candidates:
            rows.append(
                {
                    "period_end": point.period_end,
                    "value": point.value,
                    "prior_period_end": None,
                    "prior_value": None,
                    "growth": None,
                    "comparable": False,
                    "reason": (
                        "No observation of this metric covering a comparable window about a "
                        "year earlier was acquired, so no year-over-year rate is computed."
                    ),
                }
            )
            continue

        # The predecessor closest to a year apart is the correct comparison.
        prior, gap = min(prior_candidates, key=lambda item: abs(item[1] - 365))

        if prior.value == 0:
            rows.append(
                {
                    "period_end": point.period_end,
                    "value": point.value,
                    "prior_period_end": prior.period_end,
                    "prior_value": prior.value,
                    "growth": None,
                    "comparable": False,
                    "reason": (
                        "The prior-year figure is zero, so a growth rate against it has no "
                        "meaning. The ratio is not reported as a large number."
                    ),
                }
            )
            continue

        rate = point.value / prior.value - 1.0
        note = ""
        if abs(gap - 365) > 5:
            note = (
                "The comparable period ends %d days rather than 365 days before this one, "
                "which is common with 52/53-week retail calendars. The rate is over the "
                "declared span, not over a normalised year." % gap
            )
        rows.append(
            {
                "period_end": point.period_end,
                "value": point.value,
                "prior_period_end": prior.period_end,
                "prior_value": prior.value,
                "growth": rate,
                "comparable": True,
                "reason": note,
                "period_gap_days": gap,
            }
        )
    return rows


def margin_for_periods(
    numerator_points: Sequence[HistoryPoint],
    denominator_points: Sequence[HistoryPoint],
    label: str,
) -> List[Dict[str, Any]]:
    """
    A margin series computed only inside one single shared period.

    Both series must cover the same window shape and end on the same date. That
    matters twice over:

    * A period present in only one series is reported as not computable with
      the reason, because padding one series to match the other would
      fabricate a margin out of two unrelated periods.
    * A numerator or denominator that is a point-in-time balance is refused
      outright. Dividing a balance at a date by an amount over a window would
      produce a number with no unit of its own, and it would still look like a
      margin on the page.
    """
    denominator_window = denominator_points[0].window if denominator_points else ""
    by_end: Dict[str, HistoryPoint] = {}
    for point in denominator_points:
        if point.period_end:
            by_end.setdefault(point.period_end, point)

    rows: List[Dict[str, Any]] = []
    for point in numerator_points:
        instant_reason = _instant_margin_reason(point.window, denominator_window)
        if instant_reason:
            rows.append(
                {
                    "label": label,
                    "period_end": point.period_end,
                    "window": point.window,
                    "numerator": point.value,
                    "denominator": None,
                    "margin": None,
                    "comparable": False,
                    "reason": instant_reason,
                }
            )
            continue

        denominator = by_end.get(point.period_end or "")
        if denominator is None:
            rows.append(
                {
                    "label": label,
                    "period_end": point.period_end,
                    "window": point.window,
                    "numerator": point.value,
                    "denominator": None,
                    "margin": None,
                    "comparable": False,
                    "reason": (
                        "The matching %s period was not acquired for this period end, so no "
                        "margin is computed. Filling it from a neighbouring period would "
                        "combine two different periods." % label
                    ),
                }
            )
            continue

        denom_instant_reason = _instant_margin_reason(point.window, denominator.window)
        if denom_instant_reason:
            rows.append(
                {
                    "label": label,
                    "period_end": point.period_end,
                    "window": point.window,
                    "numerator": point.value,
                    "denominator": denominator.value,
                    "margin": None,
                    "comparable": False,
                    "reason": denom_instant_reason,
                }
            )
            continue

        if point.window != denominator.window:
            rows.append(
                {
                    "label": label,
                    "period_end": point.period_end,
                    "window": point.window,
                    "numerator": point.value,
                    "denominator": denominator.value,
                    "margin": None,
                    "comparable": False,
                    "reason": (
                        "The numerator covers a %s window while the denominator covers a %s "
                        "window. A margin requires matching period windows."
                        % (point.window.lower(), denominator.window.lower())
                    ),
                }
            )
            continue

        if denominator.value == 0:
            rows.append(
                {
                    "label": label,
                    "period_end": point.period_end,
                    "window": point.window,
                    "numerator": point.value,
                    "denominator": denominator.value,
                    "margin": None,
                    "comparable": False,
                    "reason": "The denominator is zero, so the ratio is undefined.",
                }
            )
            continue

        rows.append(
            {
                "label": label,
                "period_end": point.period_end,
                "window": point.window,
                "numerator": point.value,
                "denominator": denominator.value,
                "margin": point.value / denominator.value,
                "comparable": True,
                "reason": "",
                "currency_match": _currency_note(point.currency, denominator.currency),
            }
        )
    return rows


def _instant_margin_reason(numerator_window: str, denominator_window: str) -> str:
    """
    Why a margin cannot be formed from these two windows, if it cannot.

    A duration over a duration is the ordinary case. A duration over an instant,
    or an instant over a duration, is not: one side is an amount over a window
    and the other is a balance at a date, and their quotient has no meaning as
    a margin. An instant over an instant is refused too, because while the
    quotient is arithmetically fine it is a ratio of two stocks, not a margin
    on activity.
    """
    instant_sides = [
        name
        for name, window in (("numerator", numerator_window), ("denominator", denominator_window))
        if window == _WINDOW_INSTANT
    ]
    if not instant_sides:
        return ""
    return (
        "A margin combines an amount over a period. The %s %s a point-in-time "
        "balance observed at an effective date, so this ratio would have no "
        "meaning as a margin and is not computed."
        % (
            " and ".join(instant_sides),
            "is" if len(instant_sides) == 1 else "are",
        )
    )


def _currency_note(left: Optional[str], right: Optional[str]) -> str:
    if left and right and not currencies_match(left, right):
        return (
            "CURRENCY_MISMATCH: the two figures are denominated in %s and %s. The ratio is "
            "shown but is not a meaningful margin." % (left, right)
        )
    return ""


def build_financial_history(
    observations: Iterable[Any],
    *,
    revenue_metric: str = "revenue",
    earnings_metric: str = "net_income",
    eps_metric: str = "eps_diluted",
    windows: Sequence[str] = (_WINDOW_ANNUAL, _WINDOW_QUARTERLY),
    instant_metrics: Sequence[str] = (),
    instant_window: str = _WINDOW_INSTANT,
) -> Dict[str, Any]:
    """
    The full history block: series, growth rates and margins.

    Duration metrics and point-in-time metrics are kept in separate series.
    A balance is a value at an effective date, not an amount over a window, so
    mixing the two would let a margin divide an instant balance by a duration
    and call the result a margin. Instant metrics therefore get their own
    series, take no growth rate, and never enter a margin.

    Everything that could not be computed is listed in `unavailable` with the
    reason, so the block is readable as a statement about coverage rather than
    as a set of numbers with silent holes.
    """
    observations = list(observations)
    unavailable: List[Dict[str, Any]] = []

    series_block: Dict[str, Any] = {}
    for metric in (revenue_metric, earnings_metric, eps_metric):
        for window in windows:
            series = build_series(observations, metric, window)
            series_block["%s.%s" % (metric, window.lower())] = series
            unavailable.extend(series.unavailable)

    for metric in instant_metrics or ():
        series = build_series(observations, metric, instant_window)
        series_block["%s.%s" % (metric, instant_window.lower())] = series
        unavailable.extend(series.unavailable)

    growth_block: Dict[str, Any] = {}
    for key, series in series_block.items():
        if not series.points:
            continue
        if series.window == _WINDOW_INSTANT:
            # A point-in-time balance has no window to compound over. Comparing
            # it to a prior instant is a change in a balance, which is a
            # different question from a growth rate and is not reported as one.
            growth_block[key] = [
                {
                    "period_end": point.period_end,
                    "value": point.value,
                    "prior_period_end": None,
                    "prior_value": None,
                    "growth": None,
                    "comparable": False,
                    "reason": (
                        "This is a point-in-time balance observed at an effective date. "
                        "It has no duration to compound over, so no growth rate is "
                        "computed for it."
                    ),
                }
                for point in series.points
            ]
            continue
        growth_block[key] = growth_against_prior_year(series.points)

    margin_block: Dict[str, Any] = {}
    for window in windows:
        revenue_series = series_block.get("%s.%s" % (revenue_metric, window.lower()))
        earnings_series = series_block.get("%s.%s" % (earnings_metric, window.lower()))
        if revenue_series is None or earnings_series is None:
            continue
        if not revenue_series.points:
            unavailable.append(
                {
                    "item": "net_margin.%s" % window.lower(),
                    "reason": (
                        "A net margin needs revenue and net income for the same period. "
                        "No %s revenue series was acquired, so no margin is computed."
                        % window.lower()
                    ),
                    "reason_kind": "MISSING",
                    "blocks": ["net_margin"],
                }
            )
            continue
        rows = margin_for_periods(
            earnings_series.points, revenue_series.points, "net_margin"
        )
        margin_block["net_margin.%s" % window.lower()] = rows
        if not any(row["comparable"] for row in rows):
            unavailable.append(
                {
                    "item": "net_margin.%s" % window.lower(),
                    "reason": (
                        "Revenue and net income were acquired for %s periods but not for the "
                        "same period ends, so no margin is computable."
                        % window.lower()
                    ),
                    "reason_kind": "PERIOD_MISMATCH",
                    "blocks": ["net_margin"],
                }
            )

    return {
        "formula_version": HISTORY_FORMULA_VERSION,
        "series": {key: series.contract_view() for key, series in series_block.items()},
        "growth": growth_block,
        "margins": margin_block,
        "unavailable": unavailable,
        "reading_notes": [
            "Growth is year-over-year within one window shape. A quarterly figure is never "
            "differenced against an annual one.",
            "A margin is computed only where numerator and denominator cover the same "
            "period end; a missing counterpart produces a stated reason, not a padded number.",
            "A period with no observation is absent from the series rather than interpolated.",
            "Each point keeps its own availability date, so a reader can tell when a figure "
            "became knowable rather than only when it covered.",
        ],
    }
