from __future__ import annotations

"""
ST-EVA 2.3-A - provider-agnostic data contract.

This module is the only place where a sourced number is allowed to exist before
the deterministic engine sees it. It defines the layer chain required by
docs/ST-EVA-2.3-A-DATA-CONTRACT.md:

    Provider -> Observation -> Evidence -> Validation -> Derived

Rules enforced here:

    - An Observation is frozen. Validation labels a value, it never edits one.
    - The provider payload is kept in `raw`, so every derived figure can be
      recomputed from the observations that produced it.
    - Missing data is None / UNAVAILABLE. It is never guessed or filled.
    - Nothing in this module knows about any specific data provider. Provider
      field names belong in an adapter's `methodology`, never in a metric.
    - Nothing in this module performs valuation arithmetic and nothing here
      produces a score, a ranking, a probability, or a recommendation.

This module imports no other ST-EVA module. The dependency direction is
one-way: adapters and the engine depend on the contract, never the reverse.
"""

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from statistics import median as _median
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


UNAVAILABLE = "UNAVAILABLE"

# Kept here so the contract, the adapters, and the engine cannot drift apart on
# the observation count below which a band stops being a usable reference.
# This is the 2.2.3 value, unchanged.
MIN_BAND_OBSERVATIONS_FOR_REFERENCE = 20

# Freshness window used by the STALE status. A stale label is computed on
# observations in 2.3-A; it does not yet alter any CLI output.
DEFAULT_STALE_AFTER_DAYS = 7


def is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def safe_float(value: Any) -> Optional[float]:
    """A finite float, or None. Never coerces a missing or non-numeric value."""
    return float(value) if is_number(value) else None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Period-length bounds.
#
# A duration fact is discrete when it is a quarter or a year long, and two
# observations may only be differenced when they fall in the same bucket. Those
# are the same question, so the bounds live here rather than in the provider
# that filters and the document that compares: two copies of these numbers
# would eventually disagree, and a disagreement about what counts as a quarter
# is a disagreement about what a period means.
#
# The SEC's own frame definition uses 91 days +/- 30 for quarters and 365 days
# +/- 30 for years, widened here to keep a filer's 13-week and 52/53-week
# calendars on the discrete side.
QUARTER_MIN_DAYS = 60
QUARTER_MAX_DAYS = 130
YEAR_MIN_DAYS = 330
YEAR_MAX_DAYS = 400


def duration_days(start: Optional[str], end: Optional[str]) -> Optional[int]:
    """
    Whole days between two ISO dates, or None if either is unreadable.

    A pure date helper on the contract layer, because period length is a
    property of an observation rather than of the source that reported it. Both
    the providers and the document need it, and it belongs to neither.
    """
    start_date = parse_iso_date(start)
    end_date = parse_iso_date(end)
    if start_date is None or end_date is None:
        return None
    return (end_date - start_date).days


def parse_iso_date(value: Optional[str]) -> Optional[date]:
    """
    Parse an ISO-8601 date or date-time into a date.

    Returns None for anything unparseable rather than guessing, because a
    period boundary that cannot be read is not a period boundary.
    """
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        pass
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


class ValidationStatus(str, Enum):
    """
    Evidence states, not ratings.

    VERIFIED / CONSISTENT / DISCREPANT / METHODOLOGY_MISMATCH are declared so the
    vocabulary is complete and stable across versions. 2.3-A never produces
    them: doing so would require a second source, which is 2.3-B.
    """

    UNAVAILABLE = "UNAVAILABLE"
    UNVERIFIABLE = "UNVERIFIABLE"
    SINGLE_SOURCE = "SINGLE_SOURCE"
    INSUFFICIENT_OBSERVATIONS = "INSUFFICIENT_OBSERVATIONS"
    STALE = "STALE"
    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
    PERIOD_INVALID = "PERIOD_INVALID"
    PERIOD_MISMATCH = "PERIOD_MISMATCH"
    MISSING_METADATA = "MISSING_METADATA"
    DUPLICATE_OBSERVATION = "DUPLICATE_OBSERVATION"
    VALID = "VALID"
    VERIFIED = "VERIFIED"
    CONSISTENT = "CONSISTENT"
    DISCREPANT = "DISCREPANT"
    METHODOLOGY_MISMATCH = "METHODOLOGY_MISMATCH"
    # Two reliable sources disagree, or a derived quantity cannot be
    # reconciled with a reported one. Neither side is a winner: the conflict is
    # the finding, and collapsing it would destroy the evidence.
    CONFLICTING = "CONFLICTING"
    # The concept does not exist for this business. Added in 2.5 so that a
    # bank with no operating-income tag is distinguishable from a retrieval
    # that failed. A null cannot carry that distinction, and a database of
    # indistinguishable nulls is not queryable.
    NOT_APPLICABLE = "NOT_APPLICABLE"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


# Order used when escalating two statuses into one. A higher index is a
# stronger caveat, so escalation never hides a problem.
_STATUS_SEVERITY: Dict[ValidationStatus, int] = {
    ValidationStatus.VALID: 0,
    ValidationStatus.VERIFIED: 0,
    ValidationStatus.CONSISTENT: 1,
    ValidationStatus.UNVERIFIABLE: 2,
    ValidationStatus.SINGLE_SOURCE: 2,
    ValidationStatus.DUPLICATE_OBSERVATION: 3,
    ValidationStatus.STALE: 4,
    ValidationStatus.METHODOLOGY_MISMATCH: 5,
    ValidationStatus.PERIOD_INVALID: 5,
    ValidationStatus.MISSING_METADATA: 5,
    ValidationStatus.CURRENCY_MISMATCH: 5,
    ValidationStatus.INSUFFICIENT_OBSERVATIONS: 5,
    # A period mismatch and a methodology mismatch are both "these two cannot
    # be compared" verdicts. Neither is a claim that a figure is wrong, so they
    # sit at the same severity, below an outright disagreement.
    ValidationStatus.PERIOD_MISMATCH: 5,
    # A conflict is stronger than a period or methodology mismatch: two
    # comparable figures do disagree. It is not stronger than a discrepancy,
    # because a conflict carries no expectation that the sources are measuring
    # the same thing, which a discrepancy does.
    ValidationStatus.DISCREPANT: 6,
    ValidationStatus.CONFLICTING: 6,
    # Not applicable is not unavailable. A concept that does not exist for
    # this business is a statement, and it ranks with a positive finding
    # rather than with a missing one: the answer is that there is nothing to
    # report, not that we failed to find it.
    ValidationStatus.NOT_APPLICABLE: 6,
    ValidationStatus.UNAVAILABLE: 7,
}


def escalate_status(
    left: ValidationStatus,
    right: ValidationStatus,
) -> ValidationStatus:
    """Combine two statuses into the stronger caveat. Labels only, no values."""
    return max(
        (left, right),
        key=lambda status: _STATUS_SEVERITY.get(status, 0),
    )


class Unit(str, Enum):
    CURRENCY = "currency"
    PER_SHARE = "per_share"
    MULTIPLE = "multiple"
    RATIO = "ratio"
    COUNT = "count"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class SourceType(str, Enum):
    API_LIVE = "API_LIVE"
    REGRESSION_FIXTURE = "REGRESSION_FIXTURE"
    DETERMINISTIC_CALCULATION = "DETERMINISTIC_CALCULATION"
    USER_SUPPLIED = "USER_SUPPLIED"
    # A value taken from an official regulatory filing rather than a vendor.
    # It is a different kind of source, not a better one.
    REGULATORY_FILING = "REGULATORY_FILING"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class CurrencyBasis(str, Enum):
    REPORTED = "REPORTED"
    INSTRUMENT_DEFAULT = "INSTRUMENT_DEFAULT"
    UNDECLARED = "UNDECLARED"
    NOT_APPLICABLE = "NOT_APPLICABLE"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class AvailabilityBasis(str, Enum):
    REPORTED = "REPORTED"
    OBSERVATION_INSTANT = "OBSERVATION_INSTANT"
    UNDECLARED = "UNDECLARED"
    # SEC EDGAR: the instant EDGAR accepted and disseminated the submission.
    ACCEPTANCE_DATETIME = "ACCEPTANCE_DATETIME"
    # SEC EDGAR FILED AS OF DATE: a provable date whose time of day is not
    # published. Used when the accession is outside the submissions window.
    FILED_AS_OF_DATE = "FILED_AS_OF_DATE"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


# The precision a source declared for an availability value.
#
# This is not a fourth kind of basis. It is the question the basis cannot answer
# on its own: `FILED_AS_OF_DATE` says the source published a date rather than an
# instant, and that difference is what decides when a fact becomes replayable.
#
# It exists because 2.14 measured what happens when nobody asks. Two ingestion
# routes, both correct about which basis they meant, disagreed on 17,043 of
# 17,043 rows -- and the disagreement was entirely the *precision* of one field:
#
#     the SEC API path   filed date -> "2015-10-28T00:00:00+00:00"  and called
#                        it ACCEPTANCE_DATETIME, over-claiming a time of day
#                        the SEC does not publish
#     the bulk path      filed date -> "2015-10-28"                and was
#                        labelled UNDECLARED, so a declared date lost its
#                        declared-ness entirely
#
# A source that has only a date must be able to say so without the consumer
# guessing from the shape of a string, and a consumer that has a date must not
# promote it to an instant. The rule is one sentence: **ST-EVA does not raise
# date-precision information to an exact timestamp**, because a date proves that
# publication happened on a day and says nothing about when on that day, and an
# invented midnight is a claim about history that no filing supports.
PRECISION_INSTANT = "INSTANT"
PRECISION_DATE = "DATE"
PRECISION_NONE = "NONE"
PRECISIONS = (PRECISION_INSTANT, PRECISION_DATE, PRECISION_NONE)

# How far a declared date may trail the true dissemination instant.
#
# **A rule of a source, not a financial constant, and not inheritable.** It
# belongs to EDGAR because EDGAR's filed-as-of date and its acceptance instant
# are its own two fields and they do not always agree on the day: reconciling a
# bulk-built archive against the API-built one found 65 facts whose filed-as-of
# date was **one day earlier** than the acceptance instant -- MU, filed
# 2020-06-29, accepted 2020-06-30T16:12:44Z.
#
# So "the declared day is over" is not by itself a provable lower bound for this
# source, and an eligibility boundary that ignored this made 65 facts replayable
# before EDGAR published them. One day is the allowance because one day is the
# largest disagreement observed on this source. **A new adapter must measure its
# own and must not carry this value over**, because the same one-day shift is an
# artefact of how this publisher records two dates and another publisher may not
# have it at all.
#
# If a source ever needs two days, this is the single place to move, and the
# per-fact point-in-time check in `fullscope_bulk.py` reports the consequence
# rather than hiding it.
DECLARED_DATE_LAG_DAYS = 1


def start_of_day_after(value: Optional[str], days: int = 1) -> Optional[str]:
    """
    The first instant at which a declared date is provably elapsed.

    `days` shifts the boundary by whole days, and defaults to one. The
    point-in-time boundary for a `FILED_AS_OF_DATE` fact is
    `start_of_day_after(value, 1 + DECLARED_DATE_LAG_DAYS)`, because the
    declared date can trail the true dissemination instant by a day.

    The next day's start rather than the declared day's `23:59:59` because
    eligibility is a `<=` comparison and a day has no last instant at second
    resolution: naming `.999999` would invent a resolution the source never had.
    It also keeps the two point-in-time implementations in this repository
    agreeing. The in-memory path compares *dates*, so a whole-day shift is
    exactly what it can already express.

    None for anything unparseable, so a caller cannot fall back to a guess.
    """
    declared = parse_iso_date(value)
    if declared is None:
        return None
    return f"{(declared + timedelta(days=days)).isoformat()}T00:00:00+00:00"


def eligibility_for_declared_date(value: Optional[str]) -> Optional[str]:
    """
    When a fact known only by a declared date may be used in a replay.

    The whole of the rule in one function, because it is applied in two places
    that must not drift:

        an instant the source published   that instant
        a date the source published       after the declared day, plus the
                                          allowance for a declared date that
                                          trails the acceptance instant
        nothing declared                  never eligible

    A date is a claim about a day, not about a moment, and using the fact from
    that day's midnight would assert that EDGAR disseminated the filing at
    00:00. Measured across the two delivery routes, doing that made 6,508 of
    17,043 facts replayable from a moment before the filer published them.
    The evidence is not discarded: it becomes usable once its day is provably
    over.
    """
    return start_of_day_after(value, 1 + DECLARED_DATE_LAG_DAYS)


def end_of_declared_day(value: Optional[str]) -> Optional[str]:
    """
    The last instant a date covers, for reading a point-in-time *cutoff*.

    A bare date as a cutoff means the whole of that day, not its first moment.
    That is the ordinary reading of "as of 2026-03-05", and it is what the
    in-memory selector already does because it compares dates. The SQL selector
    compares strings, where a bare date sorts *before* every instant of that
    day, so it was silently reading "as of 2026-03-05" as midnight and would
    exclude a fact declared for that very day. The two implementations gave
    different answers to the same question.

    Only used for cutoffs. A *declared* value keeps its own precision: this is
    about what a caller is asking for, never about what a source said.
    """
    day = parse_iso_date(value)
    if day is None:
        return None
    return f"{day.isoformat()}T23:59:59.999999+00:00"


def point_in_time_cutoff(value: Optional[str]) -> Optional[str]:
    """
    The instant a point-in-time cutoff actually names.

    An ISO-8601 value carries a time only after a date-time separator, so that is
    what distinguishes an instant from a whole day. `datetime.fromisoformat`
    cannot make the distinction on its own -- it accepts a bare date as midnight
    -- and a cutoff silently read as midnight is how a fact becomes knowable
    before its day is over.

    None for anything unreadable, so a caller can refuse rather than answer with
    everything or with nothing and call it a result.
    """
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if "T" in text or " " in text:
        return text if parse_iso_date(text) is not None else None
    return end_of_declared_day(text)


# 2.2.3 evidence unit strings. A valuation band is a multiple, never a currency.
UNIT_MULTIPLE = Unit.MULTIPLE.value
UNIT_CURRENCY = Unit.CURRENCY.value
UNIT_PER_SHARE = Unit.PER_SHARE.value
UNIT_RATIO = Unit.RATIO.value

METRIC_PRICE = "price"
METRIC_PRICE_HISTORY = "price_history"
METRIC_VOLUME_HISTORY = "volume_history"
METRIC_TRAILING_EPS = "trailing_eps"
METRIC_FORWARD_EPS = "forward_eps"
METRIC_CONSENSUS_FORWARD_EPS = "consensus_forward_eps"
METRIC_PE_BAND = "pe_band"
METRIC_PFCF_BAND = "pfcf_band"
METRIC_PS_BAND = "ps_band"
METRIC_EV_EBITDA_BAND = "ev_ebitda_band"
METRIC_FREE_CASH_FLOW = "free_cash_flow"
METRIC_EBITDA = "ebitda"
METRIC_REVENUE = "revenue"
METRIC_NET_INCOME = "net_income"
METRIC_EPS_DILUTED = "eps_diluted"
METRIC_ASSETS = "assets"
METRIC_CASH = "cash"
# 2.33: `debt` is renamed `long_term_debt`.
#
# Core `debt` claimed total debt while its declared components summed, by value
# arithmetic, to `us-gaap:LongTermDebt`. Long-term debt is the decided semantic
# target; the name follows the components, which are what filers actually report.
# Short-term borrowings, total liabilities and lease-inclusive obligations are
# excluded unless a source concept says of itself that it is part of long-term debt.
#
# `METRIC_DEBT` is **retained as the legacy alias** rather than deleted. The
# sealed 2.2.3 archive holds 180 observations recorded under `metric = 'debt'`, and
# `observations.metric` is part of the contract id -- so those rows must keep
# resolving, and rewriting them would change `observation_id` and manufacture new
# historical Evidence out of a naming decision. `canonical_metric_id()` is what
# maps the old name onto the current one.
METRIC_LONG_TERM_DEBT = "long_term_debt"

METRIC_DEBT = "debt"
"""Legacy id. Superseded by `long_term_debt`; kept so every observation archived
under the old name still resolves. Use `canonical_metric_id()` when reading a
metric id that came out of an archive."""

CROSS_CONTRACT_METRIC_ALIASES: Dict[str, str] = {
    METRIC_DEBT: METRIC_LONG_TERM_DEBT,
}


def canonical_metric_id(metric_id: str) -> str:
    """Map a stored metric id onto the id that currently carries its meaning."""
    return CROSS_CONTRACT_METRIC_ALIASES.get(metric_id, metric_id)
METRIC_SHARES_OUTSTANDING = "shares_outstanding"
METRIC_ENTERPRISE_VALUE = "enterprise_value"
METRIC_MARKET_CAP = "market_cap"
METRIC_PRICE_VOLUME_METRICS = "price_volume_metrics"
METRIC_MARKETABLE_SECURITIES_CURRENT = "marketable_securities_current"
METRIC_COMMERCIAL_PAPER = "commercial_paper"
METRIC_TOTAL_DEBT = "total_debt"

CONTRACT_METRICS: Tuple[str, ...] = (
    METRIC_PRICE,
    METRIC_PRICE_HISTORY,
    METRIC_VOLUME_HISTORY,
    METRIC_TRAILING_EPS,
    METRIC_FORWARD_EPS,
    METRIC_CONSENSUS_FORWARD_EPS,
    METRIC_PE_BAND,
    METRIC_PFCF_BAND,
    METRIC_PS_BAND,
    METRIC_EV_EBITDA_BAND,
    METRIC_FREE_CASH_FLOW,
    METRIC_EBITDA,
    METRIC_REVENUE,
    METRIC_ENTERPRISE_VALUE,
    METRIC_MARKET_CAP,
    METRIC_PRICE_VOLUME_METRICS,
    # 2.3-B cross-source metrics. Same concepts, judged by a second provider.
    METRIC_NET_INCOME,
    METRIC_EPS_DILUTED,
    METRIC_ASSETS,
    METRIC_CASH,
    METRIC_LONG_TERM_DEBT,
    METRIC_SHARES_OUTSTANDING,
    METRIC_MARKETABLE_SECURITIES_CURRENT,
    METRIC_COMMERCIAL_PAPER,
    METRIC_TOTAL_DEBT,
)

CONTRACT_UNITS: Tuple[str, ...] = tuple(unit.value for unit in Unit)

CONTRACT_SOURCE_TYPES: Tuple[str, ...] = tuple(
    source_type.value for source_type in SourceType
)

# Canonical observation IDs. Material inputs keep their 2.2.3 evidence IDs so
# the JSON evidence_ids array and the snapshot evidence block are unchanged.
CONTRACT_OBSERVATION_IDS: Dict[str, str] = {
    METRIC_PRICE: "ev-price-001",
    METRIC_TRAILING_EPS: "ev-current-eps-001",
    METRIC_FORWARD_EPS: "ev-forward-eps-001",
    METRIC_CONSENSUS_FORWARD_EPS: "ev-consensus-eps-001",
    METRIC_PE_BAND: "ev-pe-band-001",
    METRIC_PFCF_BAND: "ev-pfcf-band-001",
    METRIC_PS_BAND: "ev-ps-band-001",
    METRIC_EV_EBITDA_BAND: "ev-ev-ebitda-band-001",
    METRIC_FREE_CASH_FLOW: "ev-fcf-001",
    METRIC_EBITDA: "ev-ebitda-001",
    METRIC_REVENUE: "ev-revenue-001",
    METRIC_ENTERPRISE_VALUE: "ev-enterprise-value-001",
    METRIC_MARKET_CAP: "ev-market-cap-001",
    METRIC_PRICE_VOLUME_METRICS: "ev-metrics-001",
}

# Price and volume history are inputs to ev-metrics-001 but are not themselves
# material evidence, so they are not listed in evidence_ids.
OBSERVATION_ID_PRICE_HISTORY = "obs-price-history-001"
OBSERVATION_ID_VOLUME_HISTORY = "obs-volume-history-001"

# Material metrics supplied by an adapter, in the order the 2.2.3 evidence
# store registers them. The price/volume metrics are excluded: they are
# derived by the engine, not sourced.
MATERIAL_METRICS: Tuple[str, ...] = (
    METRIC_PRICE,
    METRIC_TRAILING_EPS,
    METRIC_FORWARD_EPS,
    METRIC_CONSENSUS_FORWARD_EPS,
    METRIC_PE_BAND,
    METRIC_PFCF_BAND,
    METRIC_PS_BAND,
    METRIC_EV_EBITDA_BAND,
    METRIC_FREE_CASH_FLOW,
    METRIC_EBITDA,
    METRIC_REVENUE,
    METRIC_ENTERPRISE_VALUE,
    METRIC_MARKET_CAP,
)

# Metrics the engine derives from other observations rather than sourcing.
DERIVED_METRICS: Tuple[str, ...] = (METRIC_PRICE_VOLUME_METRICS,)

# The order evidence is registered in, which is the 2.2.3 order.
EVIDENCE_METRICS: Tuple[str, ...] = MATERIAL_METRICS + DERIVED_METRICS

BAND_METRICS: Tuple[str, ...] = (
    METRIC_PE_BAND,
    METRIC_PFCF_BAND,
    METRIC_PS_BAND,
    METRIC_EV_EBITDA_BAND,
)

# Definitions of the material metrics, kept identical to the 2.2.3 evidence
# definitions so existing rows do not change wording.
METRIC_DEFINITIONS: Dict[str, str] = {
    METRIC_PRICE: "Observed current or latest market price.",
    METRIC_TRAILING_EPS: "Current/trailing EPS. Never synthesized.",
    METRIC_FORWARD_EPS: "Forward EPS. Used only when explicitly supplied.",
    METRIC_CONSENSUS_FORWARD_EPS: "Consensus forward EPS. Never synthesized.",
    METRIC_PE_BAND: "Historical P/E reference band.",
    METRIC_PFCF_BAND: "Historical P/FCF reference band.",
    METRIC_PS_BAND: "Historical P/S reference band.",
    METRIC_EV_EBITDA_BAND: "Historical EV/EBITDA reference band.",
    METRIC_FREE_CASH_FLOW: "Observed trailing free cash flow. Never synthesized.",
    METRIC_EBITDA: "Observed trailing EBITDA. Never synthesized.",
    METRIC_REVENUE: "Observed trailing revenue. Never synthesized.",
    METRIC_ENTERPRISE_VALUE: "Observed enterprise value. Never synthesized.",
    METRIC_MARKET_CAP: "Observed market capitalization. Never synthesized.",
    METRIC_PRICE_VOLUME_METRICS: (
        "Price and volume metrics calculated from observed history."
    ),
}

# Units of the material metrics. A band is a multiple, never a currency.
METRIC_UNITS: Dict[str, str] = {
    METRIC_PRICE: UNIT_CURRENCY,
    METRIC_PRICE_HISTORY: UNIT_CURRENCY,
    METRIC_VOLUME_HISTORY: Unit.COUNT.value,
    METRIC_TRAILING_EPS: UNIT_PER_SHARE,
    METRIC_FORWARD_EPS: UNIT_PER_SHARE,
    METRIC_CONSENSUS_FORWARD_EPS: UNIT_PER_SHARE,
    METRIC_PE_BAND: UNIT_MULTIPLE,
    METRIC_PFCF_BAND: UNIT_MULTIPLE,
    METRIC_PS_BAND: UNIT_MULTIPLE,
    METRIC_EV_EBITDA_BAND: UNIT_MULTIPLE,
    METRIC_FREE_CASH_FLOW: UNIT_CURRENCY,
    METRIC_EBITDA: UNIT_CURRENCY,
    METRIC_REVENUE: UNIT_CURRENCY,
    METRIC_ENTERPRISE_VALUE: UNIT_CURRENCY,
    METRIC_MARKET_CAP: UNIT_CURRENCY,
    METRIC_PRICE_VOLUME_METRICS: UNIT_RATIO,
    METRIC_NET_INCOME: UNIT_CURRENCY,
    METRIC_EPS_DILUTED: UNIT_PER_SHARE,
    METRIC_ASSETS: UNIT_CURRENCY,
    METRIC_CASH: UNIT_CURRENCY,
    METRIC_LONG_TERM_DEBT: UNIT_CURRENCY,
    METRIC_SHARES_OUTSTANDING: Unit.COUNT.value,
    METRIC_MARKETABLE_SECURITIES_CURRENT: UNIT_CURRENCY,
    METRIC_COMMERCIAL_PAPER: UNIT_CURRENCY,
    METRIC_TOTAL_DEBT: UNIT_CURRENCY,
}

# Definitions of the 2.3-B cross-source metrics. Each states what the concept is
# and, where it matters, that the two sources do not necessarily measure the
# same thing under the same name.
METRIC_CROSS_SOURCE_DEFINITIONS: Dict[str, str] = {
    METRIC_NET_INCOME: (
        "Net income attributable to the parent. Never synthesized."
    ),
    METRIC_EPS_DILUTED: (
        "Diluted earnings per share. Never synthesized. Per-share amounts are "
        "not strictly additive across periods."
    ),
    METRIC_ASSETS: "Total assets at a balance sheet date. Never synthesized.",
    METRIC_CASH: (
        "Cash and cash equivalents at a balance sheet date. Never "
        "synthesized. Vendor 'total cash' may include short-term investments, "
        "which is a different concept."
    ),
    METRIC_LONG_TERM_DEBT: (
        "Long-term debt at a balance-sheet date, comprising the current and "
        "non-current portions of long-term debt. Excludes short-term "
        "borrowings, total liabilities and lease-inclusive debt obligations "
        "unless a source concept states that it is part of long-term debt. "
        "The current and non-current portions are two views of one quantity. "
        "Never synthesized. Renamed from `debt` in 2.33, when the components and "
        "the name were found to denote different quantities."
    ),
    METRIC_SHARES_OUTSTANDING: (
        "Shares outstanding at a stated date. Never synthesized. A period "
        "average diluted share count is a different concept."
    ),
    METRIC_MARKETABLE_SECURITIES_CURRENT: (
        "Current marketable securities at a balance-sheet date. Liquid "
        "investments with original or remaining maturities between 3 and 12 "
        "months (such as commercial paper, certificates of deposit, and short-term "
        "government obligations). Never synthesized."
    ),
    METRIC_COMMERCIAL_PAPER: (
        "Commercial paper liabilities at a balance-sheet date. Short-term "
        "unsecured promissory notes issued under commercial paper programs. "
        "A component of short-term borrowings; never double-counted with generic "
        "short-term borrowings. Never synthesized."
    ),
    METRIC_TOTAL_DEBT: (
        "Total debt obligations at a balance-sheet date, comprising long-term "
        "debt (current and non-current portions) plus commercial paper / short-term "
        "borrowings. Never synthesized."
    ),
}

METRIC_DEFINITIONS.update(METRIC_CROSS_SOURCE_DEFINITIONS)

# Capital-structure metrics supported for balance-sheet and enterprise-value reconstruction.
CAPITAL_STRUCTURE_METRICS: Tuple[str, ...] = (
    METRIC_ASSETS,
    METRIC_CASH,
    METRIC_MARKETABLE_SECURITIES_CURRENT,
    METRIC_COMMERCIAL_PAPER,
    METRIC_LONG_TERM_DEBT,
    METRIC_SHARES_OUTSTANDING,
)


def observation_id_for(metric: str) -> str:
    return CONTRACT_OBSERVATION_IDS.get(metric, f"obs-{metric}")


# ---------------------------------------------------------------------------
# Cross-source metrics (2.3-B)
#
# The seven metrics that a second source may independently corroborate. Each
# names a concept, not a value: the period, the unit, and the measurement basis
# are separate attributes of the observation.
# ---------------------------------------------------------------------------

COMPARABLE_METRICS: Tuple[str, ...] = (
    METRIC_REVENUE,
    METRIC_NET_INCOME,
    METRIC_EPS_DILUTED,
    METRIC_ASSETS,
    METRIC_CASH,
    METRIC_LONG_TERM_DEBT,
    METRIC_SHARES_OUTSTANDING,
)

# The seven metrics are 2.3-B additions. They get source-qualified IDs under a
# distinct `cmp-` prefix so they can never collide with the 2.2.3 material
# evidence IDs, and so `evidence_ids` and the CLI JSON cannot change because a
# second source was added.
SOURCE_YAHOO = "yahoo"
SOURCE_SEC = "sec"


def comparable_observation_id(
    metric: str,
    source: str,
    period: Optional[str] = None,
    accession: Optional[str] = None,
) -> str:
    """
    A source-qualified ID for a cross-source observation.

    2.3-A mapped one canonical ID per metric, which assumed a single source.
    2.3-B widens that to one ID per (metric, source, period) so that two
    sources reporting the same metric coexist instead of colliding.
    """
    parts = ["cmp", metric, source]
    if period:
        parts.append(str(period))
    if accession:
        parts.append(str(accession).replace("-", ""))
    return "-".join(parts)


def is_comparable_observation(observation: Observation) -> bool:
    """
    True for an observation that belongs to the 2.3-B cross-source set.

    The distinction is the ID prefix. The 2.2.3 material evidence shares metric
    names with the cross-source set, so filtering on the metric alone would pull
    the engine's own inputs into a comparison that is not about them.
    """
    return observation.observation_id.startswith("cmp-")


# The contract describes evidence states. It must never acquire the vocabulary
# of an investment verdict, because that is a different kind of claim and the
# engine is not entitled to make it. This list is checked by a test so a future
# field cannot quietly introduce one.
FORBIDDEN_VOCABULARY: Tuple[str, ...] = (
    "buy",
    "sell",
    "hold",
    "rating",
    "recommend",
    "score",
    "probabilit",
    "rank",
    "target_price",
    "price_target",
    "bull",
    "bear",
    "upside",
    "downside",
    "overvalued",
    "undervalued",
    "confidence",
)


def contract_vocabulary_is_safe() -> bool:
    """
    True when no contract identifier reads like an investment verdict.

    Checked across the metric names, units, source types, validation statuses,
    currency bases, and availability bases. It is a guard, not a style rule:
    the point is that a data contract cannot smuggle in a judgement.
    """
    vocabulary: List[str] = []
    vocabulary.extend(CONTRACT_METRICS)
    vocabulary.extend(CONTRACT_UNITS)
    vocabulary.extend(CONTRACT_SOURCE_TYPES)
    vocabulary.extend(status.value for status in ValidationStatus)
    vocabulary.extend(basis.value for basis in CurrencyBasis)
    vocabulary.extend(basis.value for basis in AvailabilityBasis)
    vocabulary.extend(
        definition.lower() for definition in METRIC_DEFINITIONS.values()
    )

    for term in vocabulary:
        lowered = term.lower()
        for forbidden in FORBIDDEN_VOCABULARY:
            if forbidden in lowered:
                return False
    return True


@dataclass(frozen=True)
class Observation:
    """
    One metric, one value, one provenance record.

    Frozen on purpose: a validation pass has no way to write to it, which is
    how the "validation must not overwrite a raw observation" rule is enforced
    structurally rather than by convention.
    """

    observation_id: str
    metric: str
    value: Any
    unit: str
    currency: Optional[str]
    currency_basis: str
    period_start: Optional[str]
    period_end: Optional[str]
    as_of: Optional[str]
    available_at: Optional[str]
    available_at_basis: str
    provider: str
    source_type: str
    source_url: Optional[str]
    definition: str
    methodology: str
    retrieved_at: str
    raw: Any = None
    observation_count: Optional[int] = None
    status: ValidationStatus = ValidationStatus.UNVERIFIABLE
    status_reasons: Tuple[str, ...] = ()
    inputs: Tuple[str, ...] = ()
    # The security, share, price and earnings basis a value is stated on.
    #
    # A listed security can be quoted per ADS while a filing counts ordinary
    # shares and the accounts are denominated in the local currency. A
    # consumer that cannot see that will divide a price by the wrong count.
    #
    # An adapter declares only what its source states. Every other key is
    # absent rather than guessed, so "unknown" is a value a consumer can read
    # and a missing key is not.
    basis: Optional[Dict[str, Any]] = None

    @property
    def is_available(self) -> bool:
        return self.value is not None and self.value != {}

    def declared_basis(self, key: str) -> Optional[str]:
        """A basis key, or None when the source did not state it."""
        if not self.basis:
            return None
        value = self.basis.get(key)
        return str(value) if value else None

    @property
    def is_band(self) -> bool:
        return self.metric in BAND_METRICS

    def missing_reason(self) -> str:
        """Canonical reason string for an unavailable observation."""
        return f"{self.metric} was requested but not provided by {self.provider}"

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "metric": self.metric,
            "value": self.value,
            "unit": self.unit,
            "currency": self.currency,
            "currency_basis": self.currency_basis,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "as_of": self.as_of,
            "available_at": self.available_at,
            "available_at_basis": self.available_at_basis,
            "provider": self.provider,
            "source_type": self.source_type,
            "source_url": self.source_url,
            "definition": self.definition,
            "methodology": self.methodology,
            "retrieved_at": self.retrieved_at,
            "observation_count": self.observation_count,
            "status": self.status.value,
            "status_reasons": list(self.status_reasons),
            "inputs": list(self.inputs),
            "raw_preserved": self.raw is not None,
            "basis": dict(self.basis) if self.basis else None,
        }


@dataclass(frozen=True)
class ValidationRecord:
    """
    The outcome of inspecting one or more observations.

    It labels values. It never carries one, and it never writes one.

    The `comparison_basis`, `tolerance`, `explanation` and `references` fields
    exist for cross-source validation: a comparison is an annotation on a pair
    of observations, so the rule that produced the verdict has to travel with
    the verdict. They are optional, so a single-source record is unchanged.
    """

    status: ValidationStatus
    reasons: Tuple[str, ...] = ()
    checked_at: str = ""
    comparison_basis: Optional[Dict[str, Any]] = None
    tolerance: Optional[Dict[str, Any]] = None
    explanation: str = ""
    references: Tuple[str, ...] = ()
    # The value as it stood when validated. A copy for auditing, never a
    # replacement: if an observation's value ever differs from this snapshot,
    # the mutation is detectable.
    value_snapshot: Any = None

    @property
    def is_comparison(self) -> bool:
        return self.comparison_basis is not None

    def contract_dict(self) -> Dict[str, Any]:
        record: Dict[str, Any] = {
            "status": self.status.value,
            "reasons": list(self.reasons),
            "checked_at": self.checked_at,
        }
        if self.is_comparison:
            record["comparison_basis"] = self.comparison_basis
            record["tolerance"] = self.tolerance
            record["explanation"] = self.explanation
            record["references"] = list(self.references)
        return record


@dataclass(frozen=True)
class LegacyEvidenceRow:
    """
    The 2.2.3 evidence row, preserved verbatim.

    The 2.2.3 row stamped the instrument currency onto every row, including
    the valuation bands, and reported the price date as the `as_of` of every
    input. Those simplifications are kept here so that existing snapshots and
    existing evidence assertions do not change. They are a presentation
    projection and are not the contract view: `Evidence.contract_dict()`
    serializes the observation, which is where the real per-metric
    provenance lives.
    """

    provider: str
    source: str
    source_url: Optional[str]
    as_of: Optional[str]
    unit: str
    currency: Optional[str]
    quality: str
    traceability: str


@dataclass(frozen=True)
class Evidence:
    """
    Engine-facing identity for a material input.

    Evidence references the observation instead of copying a value, so the raw
    observation survives by construction.
    """

    evidence_id: str
    observation: Observation
    validation: ValidationRecord
    legacy: LegacyEvidenceRow

    @property
    def value(self) -> Any:
        return self.observation.value

    @property
    def unit(self) -> str:
        return self.legacy.unit

    @property
    def currency(self) -> Optional[str]:
        return self.legacy.currency

    @property
    def as_of(self) -> Optional[str]:
        return self.legacy.as_of

    @property
    def provider(self) -> str:
        return self.legacy.provider

    @property
    def source(self) -> str:
        return self.legacy.source

    @property
    def source_url(self) -> Optional[str]:
        return self.legacy.source_url

    @property
    def quality(self) -> str:
        return self.legacy.quality

    @property
    def traceability(self) -> str:
        return self.legacy.traceability

    @property
    def definition(self) -> str:
        return self.observation.definition

    @property
    def source_type(self) -> str:
        return self.observation.source_type

    @property
    def status(self) -> ValidationStatus:
        return escalate_status(
            self.observation.status,
            self.validation.status,
        )

    @property
    def is_available(self) -> bool:
        return self.observation.is_available

    def as_dict(self) -> Dict[str, Any]:
        """The 2.2.3 evidence row, field for field and in the same order."""
        return {
            "evidence_id": self.evidence_id,
            "value": self.value if self.is_available else UNAVAILABLE,
            "provider": self.legacy.provider,
            "source": self.legacy.source,
            "source_url": self.legacy.source_url,
            "as_of": self.legacy.as_of,
            "unit": self.legacy.unit,
            "currency": self.legacy.currency,
            "definition": self.observation.definition,
            "source_type": self.observation.source_type,
            "quality": self.legacy.quality,
            "traceability": self.legacy.traceability,
        }

    def contract_dict(self) -> Dict[str, Any]:
        record = self.observation.contract_dict()
        record["evidence_id"] = self.evidence_id
        record["evidence_status"] = self.status.value
        record["validation"] = self.validation.contract_dict()
        record["quality"] = self.legacy.quality
        record["traceability"] = self.legacy.traceability
        return record


class EvidenceStore:
    """
    Ordered collection of evidence.

    A duplicate evidence_id is a defect and is refused. A duplicate metric from
    two providers is not a defect and is not collapsed: two sources reporting
    the same metric is exactly the evidence 2.3-B needs, so it is preserved.
    """

    def __init__(self) -> None:
        self._items: Dict[str, Evidence] = {}

    def add(self, evidence: Evidence) -> None:
        if evidence.evidence_id in self._items:
            raise ValueError(
                f"Duplicate Evidence ID: {evidence.evidence_id}"
            )
        self._items[evidence.evidence_id] = evidence

    def get(self, evidence_id: str) -> Optional[Evidence]:
        return self._items.get(evidence_id)

    def ids(self) -> List[str]:
        return list(self._items.keys())

    def as_dict(self) -> Dict[str, Any]:
        return {
            evidence_id: evidence.as_dict()
            for evidence_id, evidence in self._items.items()
        }

    def contract_dict(self) -> Dict[str, Any]:
        return {
            evidence_id: evidence.contract_dict()
            for evidence_id, evidence in self._items.items()
        }

    def statuses(self) -> Dict[str, str]:
        return {
            evidence_id: evidence.status.value
            for evidence_id, evidence in self._items.items()
        }

    def unavailable_ids(self) -> List[str]:
        return [
            evidence_id
            for evidence_id, evidence in self._items.items()
            if not evidence.is_available
        ]


class ObservationSet:
    """
    A provider-agnostic collection of observations for one instrument.

    Membership is by observation_id. Two observations may carry the same metric
    as long as they have distinct identities; both are kept.
    """

    def __init__(
        self,
        ticker: str = "",
        observations: Optional[Sequence[Observation]] = None,
    ) -> None:
        self.ticker = ticker
        self._items: Dict[str, Observation] = {}
        for observation in observations or ():
            self.add(observation)

    def add(self, observation: Observation) -> None:
        if observation.observation_id in self._items:
            raise ValueError(
                "Duplicate observation ID: "
                f"{observation.observation_id}"
            )
        self._items[observation.observation_id] = observation

    def extend(self, observations: Iterable[Observation]) -> None:
        for observation in observations:
            self.add(observation)

    def get(self, observation_id: str) -> Optional[Observation]:
        return self._items.get(observation_id)

    def ids(self) -> List[str]:
        return list(self._items.keys())

    def for_metric(self, metric: str) -> List[Observation]:
        return [
            observation
            for observation in self._items.values()
            if observation.metric == metric
        ]

    def latest(self, metric: str) -> Optional[Observation]:
        """First available observation for a metric, or the first if none are."""
        matches = self.for_metric(metric)
        if not matches:
            return None
        for observation in matches:
            if observation.is_available:
                return observation
        return matches[0]

    def value_for(self, metric: str, default: Any = None) -> Any:
        observation = self.latest(metric)
        if observation is None or not observation.is_available:
            return default
        return observation.value

    def providers(self) -> List[str]:
        seen: List[str] = []
        for observation in self._items.values():
            if observation.provider not in seen:
                seen.append(observation.provider)
        return seen

    def is_empty(self) -> bool:
        return not self._items

    def knowable_at(
        self,
        cutoff: str,
        metric: Optional[str] = None,
        eligibility: Optional[Dict[str, str]] = None,
    ) -> List[Observation]:
        """
        Observations that were public at or before a cutoff instant.

        This is the point-in-time selector. It is a pure function with no
        network access and no hidden clock: given the same set and the same
        cutoff it always returns the same answer.

        An observation whose `available_at` is undeclared is excluded, because
        a value whose knowable time is unknown cannot be asserted to have been
        available at any particular moment. Excluding it is the safe direction;
        including it would silently make undated data look contemporaneous.

        `eligibility` is the 2.4 archive's escape hatch, used only for
        observations that carry no `available_at`. It maps `observation_id` to
        the instant an *archive* first held the fact, which is a weaker and
        different kind of knowledge than a source-declared publication time.
        It is consulted only when `available_at` is absent, and an id missing
        from the mapping is still excluded, so omitting it entirely reproduces
        this method's original behaviour exactly.

        **A declared date is not an instant.** This path compares dates, so a
        `FILED_AS_OF_DATE` observation is knowable from after its declared day
        -- plus the allowance for a declared date that trails the acceptance
        instant -- which is exactly what `eligibility_for_declared_date` derives.
        Both point-in-time implementations in this repository therefore answer
        the same question the same way; leaving this one alone would give a
        repository two answers to "when was this knowable", which is the failure
        2.14 measured across two delivery routes.
        """
        cutoff_value = parse_iso_date(cutoff)
        if cutoff_value is None:
            return []
        known: List[Observation] = []
        for observation in self._items.values():
            if metric is not None and observation.metric != metric:
                continue
            declared = parse_iso_date(observation.available_at)
            if (
                declared is not None
                and observation.available_at_basis
                == AvailabilityBasis.FILED_AS_OF_DATE.value
            ):
                declared = declared + timedelta(
                    days=1 + DECLARED_DATE_LAG_DAYS
                )
            if declared is None and eligibility:
                declared = parse_iso_date(
                    eligibility.get(observation.observation_id)
                )
            if declared is None or declared > cutoff_value:
                continue
            known.append(observation)
        return known

    def latest_knowable(
        self,
        cutoff: str,
        metric: str,
        eligibility: Optional[Dict[str, str]] = None,
    ) -> Optional[Observation]:
        """
        The most recently accepted observation for a metric at a cutoff.

        This is how a restatement is handled without choosing a winner: the
        newest filing that had been accepted by the cutoff is the value a
        reader at that moment would have seen. A later restatement does not
        rewrite it, it adds another observation with a later `available_at`.
        """
        candidates = [
            observation
            for observation in self.knowable_at(
                cutoff, metric=metric, eligibility=eligibility
            )
            if observation.is_available
        ]
        if not candidates:
            return None
        candidates.sort(
            key=lambda observation: (
                observation.available_at
                or (eligibility or {}).get(observation.observation_id)
                or "",
                observation.as_of or "",
            )
        )
        return candidates[-1]

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "observation_count": len(self._items),
            "providers": self.providers(),
            "observations": [
                observation.contract_dict()
                for observation in self._items.values()
            ],
        }


@dataclass(frozen=True)
class CrossValidationResult:
    """
    The verdict on one metric across two sources.

    This is the third thing. It references the observations on both sides and
    replaces neither. There is no merged value, no averaged value, and no
    winning source anywhere in this type, deliberately: a comparison that picks
    a side is not a validation.
    """

    metric: str
    status: ValidationStatus
    validation: ValidationRecord
    left_observation_id: Optional[str] = None
    right_observation_id: Optional[str] = None
    right_observation_ids: Tuple[str, ...] = ()

    @property
    def comparable(self) -> bool:
        """True only when a numeric verdict was actually reached."""
        return self.status in (
            ValidationStatus.CONSISTENT,
            ValidationStatus.DISCREPANT,
        )

    @property
    def is_disagreement(self) -> bool:
        return self.status is ValidationStatus.DISCREPANT

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "metric": self.metric,
            "status": self.status.value,
            "comparable": self.comparable,
            "left_observation_id": self.left_observation_id,
            "right_observation_id": self.right_observation_id,
            "right_observation_ids": list(self.right_observation_ids),
            "validation": self.validation.contract_dict(),
        }


@dataclass(frozen=True)
class DerivedValue:
    """
    A deterministic function of identified observations.

    `inputs` names the observations that were consumed and `method` names the
    formula, so any derived figure can be traced and recomputed.
    """

    name: str
    value: Any
    unit: str
    currency: Optional[str]
    method: str
    inputs: Tuple[str, ...] = ()
    deterministic: bool = True

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "currency": self.currency,
            "method": self.method,
            "inputs": list(self.inputs),
            "deterministic": self.deterministic,
        }


# ---------------------------------------------------------------------------
# Observation construction helpers
# ---------------------------------------------------------------------------


def unavailable_observation(
    metric: str,
    provider: str,
    source_type: str,
    definition: str,
    methodology: str,
    retrieved_at: str,
    unit: str,
    currency: Optional[str] = None,
    currency_basis: str = CurrencyBasis.NOT_APPLICABLE.value,
    source_url: Optional[str] = None,
) -> Observation:
    """
    An observation for a metric that was requested and not returned.

    The value stays None. It is never zero, never the median of something
    else, and never carried over from a related metric.
    """
    return Observation(
        observation_id=observation_id_for(metric),
        metric=metric,
        value=None,
        unit=unit,
        currency=currency,
        currency_basis=currency_basis,
        period_start=None,
        period_end=None,
        as_of=None,
        available_at=None,
        available_at_basis=AvailabilityBasis.UNDECLARED.value,
        provider=provider,
        source_type=source_type,
        source_url=source_url,
        definition=definition,
        methodology=methodology,
        retrieved_at=retrieved_at,
        raw=None,
        observation_count=None,
        status=ValidationStatus.UNAVAILABLE,
        status_reasons=(f"{metric} was requested but not provided by {provider}",),
    )


def build_observation(
    metric: str,
    value: Any,
    unit: str,
    provider: str,
    source_type: str,
    definition: str,
    methodology: str,
    retrieved_at: str,
    currency: Optional[str] = None,
    currency_basis: Optional[str] = None,
    period_start: Optional[str] = None,
    period_end: Optional[str] = None,
    as_of: Optional[str] = None,
    available_at: Optional[str] = None,
    available_at_basis: Optional[str] = None,
    source_url: Optional[str] = None,
    raw: Any = None,
    observation_count: Optional[int] = None,
    status: Optional[ValidationStatus] = None,
    status_reasons: Tuple[str, ...] = (),
    inputs: Tuple[str, ...] = (),
    basis: Optional[Dict[str, Any]] = None,
    observation_id: Optional[str] = None,
) -> Observation:
    """
    Construct an observation, defaulting the optional provenance explicitly.

    Defaults are chosen to be visible rather than convenient: an undisclosed
    publication date is UNDECLARED, and a dimensionless value carries no
    currency.
    """
    if value is None:
        return unavailable_observation(
            metric=metric,
            provider=provider,
            source_type=source_type,
            definition=definition,
            methodology=methodology,
            retrieved_at=retrieved_at,
            unit=unit,
            currency=currency,
            currency_basis=currency_basis or CurrencyBasis.NOT_APPLICABLE.value,
            source_url=source_url,
        )

    if unit == Unit.MULTIPLE.value:
        resolved_currency = None
        resolved_currency_basis = CurrencyBasis.NOT_APPLICABLE.value
    else:
        resolved_currency = currency
        resolved_currency_basis = currency_basis or (
            CurrencyBasis.REPORTED.value
            if currency
            else CurrencyBasis.NOT_APPLICABLE.value
        )

    if available_at_basis is None:
        if available_at:
            resolved_availability = (
                AvailabilityBasis.OBSERVATION_INSTANT.value
                if available_at == as_of
                else AvailabilityBasis.REPORTED.value
            )
        else:
            resolved_availability = AvailabilityBasis.UNDECLARED.value
    else:
        resolved_availability = available_at_basis

    if status is None:
        resolved_status = (
            ValidationStatus.UNVERIFIABLE
            if source_type == SourceType.API_LIVE.value
            else ValidationStatus.SINGLE_SOURCE
        )
    else:
        resolved_status = status

    return Observation(
        observation_id=observation_id or observation_id_for(metric),
        metric=metric,
        value=value,
        unit=unit,
        currency=resolved_currency,
        currency_basis=resolved_currency_basis,
        period_start=period_start,
        period_end=period_end,
        as_of=as_of,
        available_at=available_at,
        available_at_basis=resolved_availability,
        provider=provider,
        source_type=source_type,
        source_url=source_url,
        definition=definition,
        methodology=methodology,
        retrieved_at=retrieved_at,
        raw=raw,
        observation_count=observation_count,
        status=resolved_status,
        status_reasons=status_reasons,
        inputs=inputs,
        basis=basis,
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_observation(
    observation: Observation,
    now: Optional[str] = None,
    stale_after_days: int = DEFAULT_STALE_AFTER_DAYS,
) -> ValidationRecord:
    """
    Inspect an observation and return a status. Never edits the observation.

    `now` is a parameter rather than a clock read so the result is
    reproducible in a test and in an audit.
    """
    reasons: List[str] = []
    status = ValidationStatus.VALID

    def escalate(candidate: ValidationStatus, reason: str) -> None:
        nonlocal status
        status = escalate_status(status, candidate)
        reasons.append(reason)

    for name, value in (
        ("observation_id", observation.observation_id),
        ("metric", observation.metric),
        ("unit", observation.unit),
        ("provider", observation.provider),
        ("source_type", observation.source_type),
        ("definition", observation.definition),
        ("methodology", observation.methodology),
        ("retrieved_at", observation.retrieved_at),
    ):
        if not value:
            escalate(
                ValidationStatus.MISSING_METADATA,
                f"{name} is required and absent.",
            )

    if observation.unit not in CONTRACT_UNITS:
        escalate(
            ValidationStatus.MISSING_METADATA,
            f"unit {observation.unit!r} is not a contract unit.",
        )
    if observation.metric not in CONTRACT_METRICS:
        escalate(
            ValidationStatus.MISSING_METADATA,
            f"metric {observation.metric!r} is not a contract metric.",
        )
    if observation.source_type not in CONTRACT_SOURCE_TYPES:
        escalate(
            ValidationStatus.MISSING_METADATA,
            f"source_type {observation.source_type!r} is not a contract source type.",
        )
    if observation.currency_basis not in tuple(
        basis.value for basis in CurrencyBasis
    ):
        escalate(
            ValidationStatus.MISSING_METADATA,
            f"currency_basis {observation.currency_basis!r} is unknown.",
        )
    if observation.available_at_basis not in tuple(
        basis.value for basis in AvailabilityBasis
    ):
        escalate(
            ValidationStatus.MISSING_METADATA,
            f"available_at_basis {observation.available_at_basis!r} is unknown.",
        )

    period_start = parse_iso_date(observation.period_start)
    period_end = parse_iso_date(observation.period_end)
    if observation.period_start and period_start is None:
        escalate(
            ValidationStatus.PERIOD_INVALID,
            f"period_start {observation.period_start!r} is not an ISO-8601 date.",
        )
    if observation.period_end and period_end is None:
        escalate(
            ValidationStatus.PERIOD_INVALID,
            f"period_end {observation.period_end!r} is not an ISO-8601 date.",
        )
    if period_start and period_end and period_start > period_end:
        escalate(
            ValidationStatus.PERIOD_INVALID,
            "period_start is later than period_end.",
        )

    as_of = parse_iso_date(observation.as_of)
    if observation.as_of and as_of is None:
        escalate(
            ValidationStatus.PERIOD_INVALID,
            f"as_of {observation.as_of!r} is not an ISO-8601 date.",
        )

    available_at = parse_iso_date(observation.available_at)
    if observation.available_at and available_at is None:
        escalate(
            ValidationStatus.PERIOD_INVALID,
            f"available_at {observation.available_at!r} is not an ISO-8601 date.",
        )
    if available_at and as_of and available_at < as_of:
        escalate(
            ValidationStatus.PERIOD_INVALID,
            "available_at precedes as_of; the value claims to have been "
            "knowable before the period it describes.",
        )
    if observation.available_at_basis == AvailabilityBasis.UNDECLARED.value and observation.available_at:
        escalate(
            ValidationStatus.MISSING_METADATA,
            "available_at is set while the basis is UNDECLARED.",
        )

    if observation.is_band:
        if not observation.is_available:
            escalate(
                ValidationStatus.UNAVAILABLE,
                observation.missing_reason(),
            )
        else:
            count = observation.observation_count
            if count is None and isinstance(observation.value, dict):
                count = observation.value.get("observations")
            if count is not None and int(count) < MIN_BAND_OBSERVATIONS_FOR_REFERENCE:
                escalate(
                    ValidationStatus.INSUFFICIENT_OBSERVATIONS,
                    f"{observation.metric} carries {int(count)} observations, "
                    f"below the {MIN_BAND_OBSERVATIONS_FOR_REFERENCE} required "
                    "for a reference.",
                )

    if not observation.is_available and status is ValidationStatus.VALID:
        escalate(
            ValidationStatus.UNAVAILABLE,
            observation.missing_reason(),
        )

    if (
        now
        and observation.is_available
        and observation.source_type == SourceType.API_LIVE.value
    ):
        now_date = parse_iso_date(now)
        if now_date and available_at:
            # Only a declared availability date can be stale. When the provider
            # hides it, freshness is undetermined, and saying STALE would
            # punish the source for being honest about what it does not
            # disclose. The UNDECLARED basis is the visible signal instead.
            #
            # Freshness is a live-data question. A regression fixture is a
            # fixed point in time and declares itself as one, so it is never
            # stale; a fixture that has gone out of date is a test-data
            # problem, not a data-quality finding about the market.
            age_days = (now_date - available_at).days
            if age_days > stale_after_days:
                escalate(
                    ValidationStatus.STALE,
                    f"available {age_days} days ago, past the "
                    f"{stale_after_days}-day freshness window.",
                )

    return ValidationRecord(
        status=status,
        reasons=tuple(reasons),
        checked_at=now or observation.retrieved_at,
    )


def currencies_match(left: Optional[str], right: Optional[str]) -> bool:
    """
    Two amounts may only be combined when their currencies are stated and equal.

    An unstated currency is a refusal, not a match. This preserves the 2.2.3
    currency-consistency protection at the contract layer.
    """
    if not left or not right:
        return False
    return str(left).upper() == str(right).upper()


def units_match(left: Optional[str], right: Optional[str]) -> bool:
    if not left or not right:
        return False
    return str(left).lower() == str(right).lower()


def figure_units_compatible(
    left: Optional[Observation],
    right: Optional[Observation],
) -> bool:
    """
    Whether two figures may be combined in one derived value.

    Two axes, and they are not the same axis:

        *unit* says what kind of quantity this is - money, a per-share amount,
        a multiple. Both figures being "currency" says nothing about which
        currency.

        *currency* says which money. A US dollar amount and a New Taiwan dollar
        amount are both `currency` and are not the same quantity, and dividing
        one by the other yields a number with no economic meaning that is
        indistinguishable from a real ratio.

    A figure that states no currency does not constrain the other side: it is
    unknown rather than different, and a derivation that needs a stated
    currency must refuse it explicitly rather than proceed.
    """
    if left is None or right is None:
        return False
    if not units_match(left.unit, right.unit):
        return False
    if left.currency and right.currency:
        return currencies_match(left.currency, right.currency)
    return True


# ---------------------------------------------------------------------------
# Deterministic recomputation
# ---------------------------------------------------------------------------


def percentile(values: Sequence[float], fraction: float) -> Optional[float]:
    """Linear interpolation at position (n - 1) * p over sorted values."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def distribution_from_samples(samples: Sequence[float]) -> Dict[str, Any]:
    """
    The band statistics for a sample, in the 2.2.3 form and method.

    An empty sample yields an empty band. It never yields zeros.
    """
    values = [float(sample) for sample in samples if is_number(sample)]
    if not values:
        return {}
    return {
        "10th": percentile(values, 0.10),
        "25th": percentile(values, 0.25),
        "median": _median(values),
        "75th": percentile(values, 0.75),
        "90th": percentile(values, 0.90),
        "observations": len(values),
    }


def recompute_distribution(observation: Observation) -> Dict[str, Any]:
    """
    Rebuild a band observation from the samples preserved in its raw payload.

    Returns an empty band when the samples are not preserved, which makes the
    gap visible instead of silently trusting a stored summary.
    """
    raw = observation.raw if isinstance(observation.raw, dict) else {}
    samples = raw.get("samples")
    if not isinstance(samples, (list, tuple)) or not samples:
        return {}
    return distribution_from_samples(samples)


def compute_price_volume_metrics(
    prices: Sequence[Any],
    volumes: Sequence[Any],
) -> Dict[str, Any]:
    """
    Price and volume statistics. Pure, and the only price-series arithmetic in
    the engine, so the derived metrics can be recomputed from raw series.
    """
    observed = [float(x) for x in prices if is_number(x) and float(x) > 0]
    traded = [float(x) for x in volumes if is_number(x) and float(x) >= 0]

    result: Dict[str, Any] = {
        "return_1d": None,
        "return_5d": None,
        "return_20d": None,
        "return_60d": None,
        "realized_volatility_annualized": None,
        "average_volume": None,
        "latest_volume_vs_average": None,
        "observations": len(observed),
    }

    if len(observed) >= 2:
        result["return_1d"] = observed[-1] / observed[-2] - 1.0
    if len(observed) >= 6:
        result["return_5d"] = observed[-1] / observed[-6] - 1.0
    if len(observed) >= 21:
        result["return_20d"] = observed[-1] / observed[-21] - 1.0
    if len(observed) >= 61:
        result["return_60d"] = observed[-1] / observed[-61] - 1.0

    if len(observed) >= 3:
        log_returns = [
            math.log(observed[i] / observed[i - 1])
            for i in range(1, len(observed))
            if observed[i - 1] > 0
        ]
        if len(log_returns) >= 2:
            mean = sum(log_returns) / len(log_returns)
            variance = sum(
                (x - mean) ** 2 for x in log_returns
            ) / (len(log_returns) - 1)
            result["realized_volatility_annualized"] = math.sqrt(
                max(variance, 0.0) * 252.0
            )

    if traded:
        average = sum(traded) / len(traded)
        result["average_volume"] = average
        if average > 0:
            result["latest_volume_vs_average"] = traded[-1] / average - 1.0

    return result


def recompute_price_volume_metrics(observation: Observation) -> Dict[str, Any]:
    """
    Rebuild the price/volume metrics from the preserved raw series.

    Returns an empty mapping when the series are absent, so a derived figure
    without its inputs is recognisable as such.
    """
    raw = observation.raw if isinstance(observation.raw, dict) else {}
    prices = raw.get("prices")
    volumes = raw.get("volumes")
    if not isinstance(prices, (list, tuple)) or not prices:
        return {}
    if not isinstance(volumes, (list, tuple)):
        volumes = []
    return compute_price_volume_metrics(prices, volumes)


# ---------------------------------------------------------------------------
# Engine boundary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValuationInputs:
    """
    The provider-agnostic input surface of the deterministic engine.

    It names metrics and values. It carries no provider field names, no
    endpoints, and no wire structures, which is what keeps the engine from
    depending on any single provider's shape.
    """

    price: float
    currency: Optional[str] = None
    current_eps: Any = UNAVAILABLE
    forward_eps: Any = UNAVAILABLE
    consensus_forward_eps: Any = UNAVAILABLE
    current_fcf: Any = UNAVAILABLE
    current_ebitda: Any = UNAVAILABLE
    current_revenue: Any = UNAVAILABLE
    current_enterprise_value: Any = UNAVAILABLE
    current_market_cap: Any = UNAVAILABLE
    historical_pe_band: Dict[str, Any] = field(default_factory=dict)
    historical_ps_band: Dict[str, Any] = field(default_factory=dict)
    historical_pfcf_band: Dict[str, Any] = field(default_factory=dict)
    historical_ev_ebitda_band: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def _band(observations: ObservationSet, metric: str) -> Dict[str, Any]:
        value = observations.value_for(metric, default={})
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _scalar(observations: ObservationSet, metric: str) -> Any:
        return observations.value_for(metric, default=UNAVAILABLE)

    @classmethod
    def from_observations(
        cls,
        observations: ObservationSet,
        price: Optional[float] = None,
        currency: Optional[str] = None,
    ) -> "ValuationInputs":
        """
        Build engine inputs from observations only.

        Anything the observation set does not carry stays UNAVAILABLE, so an
        absent observation and a present-but-null observation behave the same:
        the engine sees nothing and produces null.
        """
        if price is None:
            observed_price = observations.value_for(METRIC_PRICE, default=None)
            price = (
                float(observed_price)
                if is_number(observed_price)
                else 0.0
            )
        return cls(
            price=price,
            currency=currency,
            current_eps=cls._scalar(observations, METRIC_TRAILING_EPS),
            forward_eps=cls._scalar(observations, METRIC_FORWARD_EPS),
            consensus_forward_eps=cls._scalar(
                observations, METRIC_CONSENSUS_FORWARD_EPS
            ),
            current_fcf=cls._scalar(observations, METRIC_FREE_CASH_FLOW),
            current_ebitda=cls._scalar(observations, METRIC_EBITDA),
            current_revenue=cls._scalar(observations, METRIC_REVENUE),
            current_enterprise_value=cls._scalar(
                observations, METRIC_ENTERPRISE_VALUE
            ),
            current_market_cap=cls._scalar(observations, METRIC_MARKET_CAP),
            historical_pe_band=cls._band(observations, METRIC_PE_BAND),
            historical_ps_band=cls._band(observations, METRIC_PS_BAND),
            historical_pfcf_band=cls._band(observations, METRIC_PFCF_BAND),
            historical_ev_ebitda_band=cls._band(
                observations, METRIC_EV_EBITDA_BAND
            ),
        )

    @classmethod
    def from_legacy_view(cls, view: Any) -> "ValuationInputs":
        """
        Compatibility shim over the 2.2.3 MarketData attribute surface.

        It reads attributes by name and imports nothing, so the contract stays
        free of any dependency on the engine module. Existing callers that
        build or mutate MarketData keep working unchanged.
        """

        def band(name: str) -> Dict[str, Any]:
            value = getattr(view, name, None)
            return value if isinstance(value, dict) else {}

        return cls(
            price=getattr(view, "price", 0.0),
            currency=getattr(view, "currency", None),
            current_eps=getattr(view, "current_eps", UNAVAILABLE),
            forward_eps=getattr(view, "forward_eps", UNAVAILABLE),
            consensus_forward_eps=getattr(
                view, "consensus_forward_eps", UNAVAILABLE
            ),
            current_fcf=getattr(view, "current_fcf", UNAVAILABLE),
            current_ebitda=getattr(view, "current_ebitda", UNAVAILABLE),
            current_revenue=getattr(view, "current_revenue", UNAVAILABLE),
            current_enterprise_value=getattr(
                view, "current_enterprise_value", UNAVAILABLE
            ),
            current_market_cap=getattr(view, "current_market_cap", UNAVAILABLE),
            historical_pe_band=band("historical_pe_band"),
            historical_ps_band=band("historical_ps_band"),
            historical_pfcf_band=band("historical_pfcf_band"),
            historical_ev_ebitda_band=band("historical_ev_ebitda_band"),
        )
