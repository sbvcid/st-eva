from __future__ import annotations

"""
ST-EVA 2.3-B - SEC EDGAR provider.

Acquires XBRL facts from the SEC's own data APIs and emits them as
provider-agnostic observations. It never computes a valuation ratio, never
selects a reference, and never merges two sources into one number.

The SEC is a second source, not a better one. Nothing here overrides Yahoo, and
nothing here changes what the engine calculates. The purpose is to make a
comparison possible and to record why a comparison may not be.

Three dates are kept strictly apart, because collapsing them is how a filing
gets misdated:

    CONFORMED PERIOD OF REPORT  -> period_end / as_of  (what the filing reports)
    FILED AS OF DATE            -> fallback for available_at
    ACCEPTANCE-DATETIME         -> available_at        (when it became public)

Design points that are load-bearing:

    - A 10-Q reports a fact twice for the same end date: year-to-date and the
      discrete quarter. Only the discrete entry is accepted. A YTD figure
      compared against a trailing-twelve-month figure is a category error, not
      a discrepancy.
    - The same (concept, period) can be reported by several filings with
      different values, because filings get restated. Every filing produces its
      own observation. Collapsing them would silently pick a winner.
    - A concept that 404s is unavailable, not an error.
"""

import gzip
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

from data_contract import (
    AvailabilityBasis,
    COMPARABLE_METRICS,
    CurrencyBasis,
    METRIC_ASSETS,
    METRIC_CASH,
    METRIC_DEBT,
    METRIC_DEFINITIONS,
    METRIC_EPS_DILUTED,
    METRIC_NET_INCOME,
    METRIC_REVENUE,
    METRIC_SHARES_OUTSTANDING,
    Observation,
    ObservationSet,
    SourceType,
    Unit,
    ValidationStatus,
    comparable_observation_id,
    is_number,
    parse_iso_date,
    utc_now,
)

PROVIDER_NAME = "SecEdgar"

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
CONCEPT_URL = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/{taxonomy}/{tag}.json"
TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"

# The SEC caps automated access at 10 requests per second, counted per IP, and
# requires a contactable User-Agent. The provider self-limits well below the
# ceiling instead of relying on the server's throttle.
SEC_MAX_REQUESTS_PER_SECOND = 10
SAFE_REQUEST_INTERVAL_SECONDS = 1.0 / 4.0

DEFAULT_USER_AGENT = (
    "ST-EVA/2.3 (research; contact st-eva@example.com)"
)

# A duration fact is discrete when it is a quarter or a year long. The SEC's own
# frame definition uses 91 days +/- 30 for quarters and 365 days +/- 30 for
# years, so the bounds are widened slightly to keep a filer's 13-week and 52/53
# week calendars on the discrete side.
QUARTER_MIN_DAYS = 60
QUARTER_MAX_DAYS = 130
YEAR_MIN_DAYS = 330
YEAR_MAX_DAYS = 400

# The number of discrete quarters summed to build a trailing-twelve-month view
# on the SEC side, because Yahoo reports a trailing figure and the SEC does not.
TTM_QUARTER_COUNT = 4

# Fiscal calendars and cumulative periods never line up exactly, so a trailing
# window is accepted as ending on its anchor within this many days. The SEC's
# own frame definition uses the same 30-day tolerance for quarters.
ROLL_FORWARD_TOLERANCE_DAYS = 10

# XBRL unit -> contract unit. The SEC documents numerator/denominator units as
# "USD-per-shares", but the live API returns "USD/shares"; both are accepted and
# whatever was actually returned is preserved in the raw payload.
XBRL_UNIT_TO_CONTRACT_UNIT: Dict[str, str] = {
    "USD": Unit.CURRENCY.value,
    "USD/shares": Unit.PER_SHARE.value,
    "USD-per-shares": Unit.PER_SHARE.value,
    "shares": Unit.COUNT.value,
    "pure": Unit.RATIO.value,
}

MONETARY_XBRL_UNITS = ("USD", "USD/shares", "USD-per-shares")


class Concept:
    """One XBRL concept the provider knows how to ask for."""

    def __init__(self, taxonomy: str, tag: str, role: str = "primary") -> None:
        self.taxonomy = taxonomy
        self.tag = tag
        # "primary" is the concept on its own. "addend" is one component of a
        # composed metric such as debt, and its value is only meaningful when
        # the composition is declared.
        self.role = role


# Concepts are tried in order; the first that returns facts wins. Concept
# choice is recorded in the observation's methodology, because a company that
# switched concept (ASC 606 adoption moved revenue from us-gaap:Revenues to
# us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax) is not reporting
# the same thing across the transition.
SEC_CONCEPTS: Dict[str, Tuple[Concept, ...]] = {
    METRIC_REVENUE: (
        Concept(
            "us-gaap",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
        ),
        Concept("us-gaap", "Revenues"),
        Concept("us-gaap", "SalesRevenueNet"),
    ),
    METRIC_NET_INCOME: (
        Concept("us-gaap", "NetIncomeLoss"),
        Concept("us-gaap", "ProfitLoss"),
    ),
    METRIC_EPS_DILUTED: (
        Concept("us-gaap", "EarningsPerShareDiluted"),
    ),
    METRIC_ASSETS: (
        Concept("us-gaap", "Assets"),
    ),
    METRIC_CASH: (
        Concept("us-gaap", "CashAndCashEquivalentsAtCarryingValue"),
        Concept(
            "us-gaap",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        ),
    ),
    METRIC_DEBT: (
        Concept("us-gaap", "LongTermDebtNoncurrent", role="addend"),
        Concept("us-gaap", "LongTermDebtCurrent", role="addend"),
    ),
    METRIC_SHARES_OUTSTANDING: (
        Concept("dei", "EntityCommonStockSharesOutstanding"),
    ),
}

# A duration metric needs a trailing-twelve-month view on the SEC side so it can
# be compared with a vendor trailing figure. An instant metric does not.
TTM_METRICS = (METRIC_REVENUE, METRIC_NET_INCOME, METRIC_EPS_DILUTED)


@dataclass(frozen=True)
class SecCompany:
    """The issuer a set of observations belongs to."""

    ticker: str
    cik: str
    name: str
    exchanges: Tuple[str, ...] = ()

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "cik": self.cik,
            "name": self.name,
            "exchanges": list(self.exchanges),
        }


@dataclass(frozen=True)
class SECDocument:
    """
    One fetched SEC document, exactly as it was served.

    Kept so an observation can be traced to the specific version of a document
    that produced it, years later. SEC data is updated as filings are
    disseminated and a filing can be corrected after acceptance, so a URL is
    not a stable reference and the bytes are.
    """

    content_hash: str
    uri: str
    payload: bytes
    media_type: str
    byte_size: int
    http_status: int
    fetched_at: str
    provider: str
    document_type: str

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "content_hash": self.content_hash,
            "uri": self.uri,
            "media_type": self.media_type,
            "byte_size": self.byte_size,
            "http_status": self.http_status,
            "fetched_at": self.fetched_at,
            "provider": self.provider,
            "document_type": self.document_type,
        }


DOCUMENT_COMPANY_CONCEPT = "SEC_COMPANY_CONCEPT"
DOCUMENT_SUBMISSIONS = "SEC_SUBMISSIONS"
DOCUMENT_TICKER_MAP = "SEC_TICKER_MAP"


def _document_type_for(uri: str) -> str:
    if "/companyconcept/" in uri:
        return DOCUMENT_COMPANY_CONCEPT
    if "/submissions/" in uri:
        return DOCUMENT_SUBMISSIONS
    return DOCUMENT_TICKER_MAP


def content_hash_of(payload: bytes) -> str:
    """The identity of a document's bytes, always over the uncompressed form."""
    return "sha256:" + hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class SecFact:
    """One XBRL fact, before it becomes an observation."""

    metric: str
    concept: Concept
    taxonomy: str
    tag: str
    label: str
    description: str
    unit: str
    value: float
    start: Optional[str]
    end: str
    accession: str
    form: str
    fiscal_year: Optional[int]
    fiscal_period: Optional[str]
    frame: Optional[str]
    filed: Optional[str]
    role: str = "primary"
    # The documents this fact was read out of. The concept document carries the
    # fact; the submissions document carries the acceptance timestamp that makes
    # it knowable, so both are part of the fact's provenance.
    document_hashes: Tuple[str, ...] = ()

    @property
    def is_instant(self) -> bool:
        return self.start is None

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "metric": self.metric,
            "taxonomy": self.taxonomy,
            "tag": self.tag,
            "label": self.label,
            "unit": self.unit,
            "value": self.value,
            "start": self.start,
            "end": self.end,
            "accession": self.accession,
            "form": self.form,
            "fy": self.fiscal_year,
            "fp": self.fiscal_period,
            "frame": self.frame,
            "filed": self.filed,
            "role": self.role,
            "document_hashes": list(self.document_hashes),
        }


@dataclass(frozen=True)
class SecAcquisition:
    """Everything the SEC provider produced for one issuer."""

    company: Optional[SecCompany] = None
    observations: Tuple[Observation, ...] = ()
    facts: Tuple[SecFact, ...] = ()
    errors: Tuple[str, ...] = ()
    # Facts dropped because they were not discrete, and facts whose concept was
    # simply not reported. Counted rather than silently discarded: a run that
    # rejects 40 of 44 facts is telling the reader something.
    rejected_not_discrete: int = 0
    rejected_duplicate: int = 0
    unavailable_concepts: Tuple[str, ...] = ()
    retrieved_at: str = ""
    # Every document fetched during this run, exactly as served. Returned so
    # the archive can capture the evidence rather than a URL.
    documents: Tuple[SECDocument, ...] = ()

    def observation_set(self) -> ObservationSet:
        return ObservationSet(
            ticker=self.company.ticker if self.company else "",
            observations=self.observations,
        )

    def metrics_found(self) -> Tuple[str, ...]:
        found: List[str] = []
        for observation in self.observations:
            if observation.metric not in found:
                found.append(observation.metric)
        return tuple(found)


def normalize_cik(value: Any) -> str:
    """CIKs are zero-padded to ten digits in every SEC URL."""
    digits = "".join(character for character in str(value) if character.isdigit())
    return digits.zfill(10)


def xbrl_unit_to_contract_unit(unit: str) -> Optional[str]:
    return XBRL_UNIT_TO_CONTRACT_UNIT.get(unit)


def duration_days(start: str, end: str) -> Optional[int]:
    start_date = parse_iso_date(start)
    end_date = parse_iso_date(end)
    if start_date is None or end_date is None:
        return None
    return (end_date - start_date).days


def _basis_for(fact: SecFact) -> Dict[str, Any]:
    """
    What the XBRL element itself states about the basis of a fact.

    Only source-stated facts appear here. The DEI cover-page element is a count
    of the registered security's shares, which is a different quantity from a
    count of the listed instrument when the two differ, and that difference has
    to be visible rather than assumed away.
    """
    basis: Dict[str, Any] = {
        "reporting_currency": (
            fact.unit if fact.unit in MONETARY_XBRL_UNITS else "UNDECLARED"
        ),
        "source_declared": True,
        "taxonomy": fact.taxonomy,
        "concept": fact.tag,
    }
    if fact.taxonomy == "dei" and fact.tag == (
        "EntityCommonStockSharesOutstanding"
    ):
        # The cover page counts shares of the registrant, before any adjustment
        # for the listed instrument. Stating it is what lets a consumer see
        # that a vendor's listed-instrument count is a different quantity.
        basis["shares_basis"] = "FILING_COVER_PAGE_REGISTERED_SECURITY"
        basis["security_type"] = "REGISTERED_SECURITY"
        basis["excludes_listing_adjustment"] = True
    elif fact.unit == "shares":
        basis["shares_basis"] = "UNDECLARED"
    else:
        basis["security_type"] = "UNDECLARED"
    return basis


def is_discrete_period(fact: SecFact) -> bool:
    """
    True when a duration fact covers a quarter or a year, not a year-to-date stub.

    This is the single most important filter in the provider. Without it, a
    nine-month year-to-date figure is compared against a trailing-twelve-month
    figure and the two sources are reported as disagreeing when they never
    answered the same question.
    """
    if fact.is_instant:
        return True
    days = duration_days(fact.start or "", fact.end)
    if days is None:
        return False
    return (
        QUARTER_MIN_DAYS <= days <= QUARTER_MAX_DAYS
        or YEAR_MIN_DAYS <= days <= YEAR_MAX_DAYS
    )


def is_quarter(fact: SecFact) -> bool:
    if fact.is_instant:
        return False
    days = duration_days(fact.start or "", fact.end)
    return days is not None and QUARTER_MIN_DAYS <= days <= QUARTER_MAX_DAYS


def is_annual(fact: SecFact) -> bool:
    if fact.is_instant:
        return False
    days = duration_days(fact.start or "", fact.end)
    return days is not None and YEAR_MIN_DAYS <= days <= YEAR_MAX_DAYS


def is_instant(fact: SecFact) -> bool:
    return fact.is_instant


def is_cumulative(fact: SecFact) -> bool:
    """
    True for a year-to-date or otherwise cumulative duration fact.

    A cumulative fact is not a quarter, so it is never comparable with a
    trailing figure on its own. It is not useless either: it is the standard
    ingredient of a trailing roll-forward, which is where it is used, and only
    there.
    """
    if fact.is_instant:
        return False
    if is_quarter(fact) or is_annual(fact):
        return False
    return duration_days(fact.start or "", fact.end) is not None


def period_label(end: str, days: Optional[int]) -> str:
    """A short, stable label for a reported period."""
    if days is None:
        return end
    if YEAR_MIN_DAYS <= days <= YEAR_MAX_DAYS:
        return f"fy{end[:4]}"
    if QUARTER_MIN_DAYS <= days <= QUARTER_MAX_DAYS:
        return f"q-{end}"
    return end


def _ends_at_or_before(candidate: str, anchor: str, tolerance_days: int) -> bool:
    candidate_date = parse_iso_date(candidate)
    anchor_date = parse_iso_date(anchor)
    if candidate_date is None or anchor_date is None:
        return False
    return abs((candidate_date - anchor_date).days) <= tolerance_days


def _quarter_view(
    facts: Sequence[SecFact],
    anchor: Optional[str],
    count: int,
    tolerance_days: int,
) -> Optional[Dict[str, Any]]:
    """
    Four contiguous quarters, ending at `anchor` when one is given.

    The anchor is the window's end, not an upper bound. A trailing view that
    ends a quarter before the requested anchor would misalign a comparison, so
    it is refused rather than returned.
    """
    quarters = [fact for fact in facts if is_quarter(fact)]
    by_end: Dict[str, SecFact] = {}
    for fact in quarters:
        by_end[fact.end] = fact
    ends = sorted(by_end, reverse=True)
    if anchor is not None:
        anchor_date = parse_iso_date(anchor)
        if anchor_date is None:
            return None
        # The window is the four quarters *ending at* the anchor, which are the
        # newest three plus the anchor itself. Filtering to quarters that end
        # exactly at the anchor would leave one quarter, so the cut is applied
        # and then the newest surviving quarter is required to be the anchor.
        ends = [
            end
            for end in ends
            if (parse_iso_date(end) - anchor_date).days <= tolerance_days
        ]
        if not ends or not _ends_at_or_before(
            ends[0], anchor, tolerance_days
        ):
            return None
    ordered = [by_end[end] for end in ends[:count]]
    if len(ordered) < count:
        return None

    ordered.sort(key=lambda fact: fact.start or "")
    first_start = parse_iso_date(ordered[0].start or "")
    last_end = parse_iso_date(ordered[-1].end)
    if first_start is None or last_end is None:
        return None

    # Contiguity: the quarters must abut. A filer's own comparative
    # restatement of an earlier quarter can leave a hole, and a retail
    # filer's fiscal Q3 is frequently only reported inside the annual
    # context. A hole here is a refusal, not a rounding error.
    for earlier, later in zip(ordered, ordered[1:]):
        earlier_end = parse_iso_date(earlier.end)
        later_start = parse_iso_date(later.start or "")
        if earlier_end is None or later_start is None:
            return None
        if later_start != earlier_end and (
            later_start - earlier_end
        ).days > 10:
            return None

    span_days = (last_end - first_start).days
    if not 300 <= span_days <= 400:
        return None

    return {
        "construction": "SUM_OF_DISCRETE_QUARTERS",
        "value": sum(fact.value for fact in ordered),
        "start": ordered[0].start,
        "end": ordered[-1].end,
        "constituents": list(ordered),
        "span_days": span_days,
    }


def _annual_view(
    facts: Sequence[SecFact],
    anchor: Optional[str],
    tolerance_days: int,
) -> Optional[Dict[str, Any]]:
    """
    A filed annual period, used as the trailing view.

    An annual period *is* twelve months of the same quantity, so when a fiscal
    year has just closed it is a fresher trailing figure than any sum of
    quarters, which necessarily ends a quarter earlier. Declaring it as a
    trailing view is more honest than reporting a stale window.
    """
    annuals = [fact for fact in facts if is_annual(fact)]
    if anchor is not None:
        annuals = [
            fact
            for fact in annuals
            if _ends_at_or_before(fact.end, anchor, tolerance_days)
        ]
    if not annuals:
        return None
    annual = max(annuals, key=lambda fact: fact.end)
    span = duration_days(annual.start or "", annual.end)
    if span is None or not 330 <= span <= 400:
        return None
    return {
        "construction": "ANNUAL_FACT_AS_TRAILING_WINDOW",
        "value": annual.value,
        "start": annual.start,
        "end": annual.end,
        "constituents": [annual],
        "span_days": span,
    }


def _roll_forward_view(
    facts: Sequence[SecFact],
    anchor: Optional[str],
    tolerance_days: int,
) -> Optional[Dict[str, Any]]:
    """
    TTM = prior fiscal year - prior-year cumulative + current cumulative

    This is the construction the trailing figure actually comes from, and it
    is the only one available for a filer whose discrete quarters do not form a
    contiguous window. Apple is exactly that case: its fiscal Q3 is reported
    inside the annual context rather than as a discrete quarter, so the four
    most recent quarters have a hole in them and summing them would silently
    omit a quarter of revenue.
    """
    annuals = [fact for fact in facts if is_annual(fact)]
    all_cumulatives = [fact for fact in facts if is_cumulative(fact)]
    if not annuals or not all_cumulatives:
        return None

    # The anchor selects the cumulative period being rolled to. The prior-year
    # period necessarily ends before it, so the anchor cut is applied to the
    # current period only and the full set stays available for the search.
    if anchor is not None:
        candidates = [
            fact
            for fact in all_cumulatives
            if _ends_at_or_before(fact.end, anchor, tolerance_days)
        ]
    else:
        candidates = all_cumulatives
    if not candidates:
        return None

    current = max(candidates, key=lambda fact: fact.end)
    current_end = parse_iso_date(current.end)
    if current_end is None:
        return None

    current_start = parse_iso_date(current.start or "")
    if current_start is None:
        return None

    # The annual that the cumulative period rolls forward from: the one whose
    # end coincides with the start of that cumulative period.
    prior_annuals = [
        fact
        for fact in annuals
        if abs(
            (parse_iso_date(fact.end) - current_start).days
        )
        <= tolerance_days
    ]
    if not prior_annuals:
        return None
    annual = max(prior_annuals, key=lambda fact: fact.end)

    # The prior-year cumulative period: the same span, one year earlier.
    target = current_end.toordinal() - 365
    prior_candidates = [
        fact
        for fact in all_cumulatives
        if fact.end != current.end
        and parse_iso_date(fact.end) is not None
        and abs(
            (parse_iso_date(fact.end).toordinal() - target)
        )
        <= tolerance_days
    ]
    if not prior_candidates:
        return None
    prior = min(
        prior_candidates,
        key=lambda fact: abs(
            (parse_iso_date(fact.end).toordinal() - target)
        ),
    )
    prior_end = parse_iso_date(prior.end)
    if prior_end is None:
        return None

    # The rolled window is the stretch the arithmetic actually covers: the
    # day after the prior cumulative period ended, through today.
    start = date(prior_end.year, prior_end.month, prior_end.day) + timedelta(
        days=1
    )
    span_days = (current_end - start).days
    if not 300 <= span_days <= 400:
        return None

    current_days = duration_days(current.start or "", current.end) or 0
    prior_days = duration_days(prior.start or "", prior.end) or 0
    if abs(current_days - prior_days) > tolerance_days:
        # A cumulative period that changed length between years is not a
        # like-for-like subtraction.
        return None

    return {
        "construction": "ANNUAL_ROLL_FORWARD",
        "value": annual.value - prior.value + current.value,
        "start": start.isoformat(),
        "end": current.end,
        "constituents": [annual, prior, current],
        "span_days": span_days,
    }


class SECProvider:
    """
    Acquires SEC XBRL facts as provider-agnostic observations.

    Never synthesizes: a concept the issuer does not report is unavailable, not
    estimated. Never merges: every filing that reported a fact keeps its own
    observation.
    """

    name = PROVIDER_NAME
    source_type = SourceType.REGULATORY_FILING.value

    def __init__(
        self,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: int = 15,
        request_interval: float = SAFE_REQUEST_INTERVAL_SECONDS,
        max_periods: int = 8,
        max_annuals: int = 2,
    ) -> None:
        self.user_agent = user_agent
        self.timeout = timeout
        self.request_interval = request_interval
        self.max_periods = max_periods
        self.max_annuals = max_annuals
        self._last_request_at = 0.0
        self._ticker_map: Optional[Dict[str, Dict[str, Any]]] = None
        self._submission_cache: Dict[str, Dict[str, Any]] = {}
        self._documents: List[SECDocument] = []
        self._document_hashes: set = set()
        self._concept_cache: Dict[str, Tuple[Optional[Dict[str, Any]], Tuple[str, ...]]] = {}
        self._submissions_hashes: Dict[str, Optional[str]] = {}

    # -- transport ---------------------------------------------------------

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.request_interval:
            time.sleep(self.request_interval - elapsed)
        self._last_request_at = time.monotonic()

    def _get(
        self,
        url: str,
        allow_missing: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch a JSON document, honouring the SEC fair-access policy.

        The exact bytes served are retained alongside the parsed result. SEC
        data changes as filings are disseminated and a filing can be corrected
        after acceptance, so a URL is not a stable reference to what a fact was
        read from; the bytes are.

        A 404 is an answer, not a failure: the issuer does not report that
        concept. `allow_missing` returns None for it instead of raising.
        """
        self._throttle()
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read()
                encoding = response.headers.get("Content-Encoding", "")
                if encoding == "gzip":
                    body = gzip.decompress(body)
                status = response.getcode()
                media_type = (
                    response.headers.get("Content-Type") or "application/json"
                )
            self._record_document(url, body, status, media_type)
            return json.loads(body.decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code == 404 and allow_missing:
                return None
            raise
        except json.JSONDecodeError as error:
            raise ValueError(
                f"SEC returned a non-JSON document for {url}: {error}"
            ) from error

    def _record_document(
        self,
        uri: str,
        payload: bytes,
        status: int,
        media_type: str,
    ) -> str:
        """Retain one fetched document, deduplicated by the hash of its bytes."""
        content_hash = content_hash_of(payload)
        if content_hash in self._document_hashes:
            return content_hash
        self._document_hashes.add(content_hash)
        self._documents.append(
            SECDocument(
                content_hash=content_hash,
                uri=uri,
                payload=payload,
                media_type=media_type,
                byte_size=len(payload),
                http_status=status,
                fetched_at=utc_now(),
                provider=self.name,
                document_type=_document_type_for(uri),
            )
        )
        return content_hash

    def document_hashes(self) -> Tuple[str, ...]:
        return tuple(
            document.content_hash for document in self._documents
        )

    # -- company resolution ------------------------------------------------

    def ticker_map(self) -> Dict[str, Dict[str, Any]]:
        """
        ticker -> {cik, name, exchanges}, from the SEC's own mapping file.

        An unknown ticker is absent from this map. It is never guessed from a
        company name, because guessing a CIK would attach another issuer's
        filings to a ticker and every comparison after that would be false.
        """
        if self._ticker_map is not None:
            return self._ticker_map

        payload = self._get(TICKER_MAP_URL) or {}
        mapping: Dict[str, Dict[str, Any]] = {}
        for entry in payload.values():
            if not isinstance(entry, dict):
                continue
            ticker = str(entry.get("ticker", "")).upper()
            if not ticker:
                continue
            mapping[ticker] = {
                "cik": normalize_cik(entry.get("cik_str", "")),
                "name": str(entry.get("title", "")),
            }
        self._ticker_map = mapping
        return mapping

    def resolve_company(self, ticker: str) -> Optional[SecCompany]:
        """Resolve a ticker to an issuer, or None when the SEC does not list it."""
        entry = self.ticker_map().get(ticker.upper().strip())
        if entry is None:
            return None

        exchanges: List[str] = []
        try:
            submissions = self.submissions(entry["cik"])
            exchanges = [
                str(value)
                for value in (submissions.get("exchanges") or [])
                if value
            ]
        except Exception:
            # Exchange metadata is nice to have. Its absence must not turn a
            # resolvable company into an unresolvable one.
            exchanges = []

        return SecCompany(
            ticker=ticker.upper().strip(),
            cik=entry["cik"],
            name=entry["name"],
            exchanges=tuple(exchanges),
        )

    def submissions(self, cik: str) -> Dict[str, Any]:
        cik = normalize_cik(cik)
        if cik not in self._submission_cache:
            url = SUBMISSIONS_URL.format(cik=cik)
            self._submission_cache[cik] = self._get(url) or {}
        return self._submission_cache[cik]

    def acceptance_index(self, cik: str) -> Dict[str, Dict[str, str]]:
        """
        accession -> filing dates, from the submissions history.

        This is where `available_at` comes from. The XBRL concept API only
        exposes the filed date; EDGAR's acceptance timestamp is the instant the
        submission actually became public, and it is published separately in
        the submissions history.

        The submissions API exposes roughly the most recent thousand filings in
        `filings.recent`, with older ones in separate archive files. An
        accession outside that window is simply absent here, and the caller
        falls back to the filed date rather than to the retrieval time.
        """
        submissions = self.submissions(cik)
        recent = ((submissions.get("filings") or {}).get("recent")) or {}
        accessions = recent.get("accessionNumber") or []
        index: Dict[str, Dict[str, str]] = {}
        for position, accession in enumerate(accessions):
            def column(name: str) -> Optional[str]:
                values = recent.get(name) or []
                if position < len(values):
                    return values[position]
                return None

            index[str(accession)] = {
                "acceptance_datetime": column("acceptanceDateTime"),
                "filing_date": column("filingDate"),
                "report_date": column("reportDate"),
                "form": column("form"),
            }
        return index

    def company_concept(
        self,
        cik: str,
        taxonomy: str,
        tag: str,
    ) -> Optional[Dict[str, Any]]:
        """Fetch one concept. None means the issuer does not report it."""
        url = CONCEPT_URL.format(
            cik=normalize_cik(cik),
            taxonomy=taxonomy,
            tag=tag,
        )
        return self._get(url, allow_missing=True)

    # -- fact extraction ---------------------------------------------------

    def _facts_for_concept(
        self,
        metric: str,
        concept: Concept,
        payload: Dict[str, Any],
        document_hashes: Sequence[str] = (),
        submissions_hash: Optional[str] = None,
    ) -> List[SecFact]:
        facts: List[SecFact] = []
        units = payload.get("units") or {}
        # A fact is read from the concept document; the instant it became
        # knowable comes from the submissions document. Both belong in the
        # fact's provenance, because replay needs both.
        sources = tuple(document_hashes)
        if submissions_hash and submissions_hash not in sources:
            sources = sources + (submissions_hash,)
        for unit, entries in units.items():
            if xbrl_unit_to_contract_unit(unit) is None:
                # An unmapped unit is not coerced. A company that reports the
                # same concept in an unrecognised measure keeps its value out
                # of the comparable set rather than having its unit guessed.
                continue
            for entry in entries:
                value = entry.get("val")
                end = entry.get("end")
                if not is_number(value) or not end:
                    continue
                start = entry.get("start")
                facts.append(
                    SecFact(
                        metric=metric,
                        concept=concept,
                        taxonomy=str(payload.get("taxonomy") or concept.taxonomy),
                        tag=str(payload.get("tag") or concept.tag),
                        label=str(payload.get("label") or ""),
                        description=str(payload.get("description") or ""),
                        unit=unit,
                        value=float(value),
                start=str(start) if start else None,
                end=str(end),
                accession=str(entry.get("accn") or ""),
                form=str(entry.get("form") or ""),
                fiscal_year=entry.get("fy"),
                fiscal_period=entry.get("fp"),
                frame=entry.get("frame"),
                        filed=entry.get("filed"),
                        role=concept.role,
                        document_hashes=sources,
                    )
                )
        return facts

    def _instant_fact(
        self,
        metric: str,
        concept: Concept,
        entries: Sequence[Dict[str, Any]],
        end: str,
        document_hashes: Sequence[str] = (),
        submissions_hash: Optional[str] = None,
    ) -> Optional[SecFact]:
        """
        One instant fact from the entries a concept reported for one date.

        Composed metrics such as debt are built from several concepts, and a
        filer may not report all of them for every date. When a component is
        absent the date is skipped rather than treated as zero: a missing
        long-term-debt concept does not mean the company has no long-term debt.
        """
        for entry in entries:
            if str(entry.get("end")) != end:
                continue
            value = entry.get("val")
            if not is_number(value):
                continue
            return SecFact(
                metric=metric,
                concept=concept,
                taxonomy=str(entry.get("taxonomy") or concept.taxonomy),
                tag=concept.tag,
                label="",
                description="",
                unit="USD",
                value=float(value),
                start=None,
                end=end,
                accession=str(entry.get("accn") or ""),
                form=str(entry.get("form") or ""),
                fiscal_year=entry.get("fy"),
                fiscal_period=entry.get("fp"),
                frame=entry.get("frame"),
                filed=entry.get("filed"),
                role=concept.role,
                document_hashes=(
                    tuple(document_hashes)
                    + ((submissions_hash,) if submissions_hash else ())
                ),
            )
        return None

    def _composed_instant_facts(
        self,
        metric: str,
        concepts: Sequence[Concept],
        payloads: Dict[str, Dict[str, Any]],
        hashes: Optional[Dict[str, Sequence[str]]] = None,
        submissions_hash: Optional[str] = None,
    ) -> Tuple[List[Tuple[SecFact, Tuple[SecFact, ...]]], List[str]]:
        """
        Compose a metric whose parts the SEC does not publish as one total.

        Every observation records the exact composition that produced it, because
        filers compose debt differently and a composed total is only comparable
        to another total with the same declared composition.

        Returns a list of (composed fact, constituent facts) pairs.
        """
        hashes = hashes or {}
        addends = [concept for concept in concepts if concept.role == "addend"]
        if not addends:
            return [], []

        per_concept: List[Tuple[Concept, List[Dict[str, Any]]]] = []
        for concept in addends:
            payload = payloads.get(concept.tag) or {}
            units = payload.get("units") or {}
            entries: List[Dict[str, Any]] = []
            for unit_values in units.values():
                entries.extend(
                    entry for entry in unit_values if is_number(entry.get("val"))
                )
            per_concept.append((concept, entries))

        end_dates = sorted(
            {
                str(entry.get("end"))
                for _, entries in per_concept
                for entry in entries
                if entry.get("end")
            },
            reverse=True,
        )

        composed: List[Tuple[SecFact, Tuple[SecFact, ...]]] = []
        for end in end_dates:
            parts: List[SecFact] = []
            for concept, entries in per_concept:
                fact = self._instant_fact(
                    metric, concept, entries, end,
                    tuple(hashes.get(concept.tag) or ()),
                    submissions_hash,
                )
                if fact is not None:
                    parts.append(fact)
            if len(parts) != len(per_concept):
                # A component is missing for this date. Skip the date rather
                # than treating the absent component as zero.
                continue
            representative = parts[0]
            total = SecFact(
                metric=metric,
                concept=representative.concept,
                taxonomy=representative.taxonomy,
                tag=representative.tag,
                label="",
                description="",
                unit="USD",
                value=sum(part.value for part in parts),
                start=None,
                end=end,
                accession=representative.accession,
                form=representative.form,
                fiscal_year=representative.fiscal_year,
                fiscal_period=representative.fiscal_period,
                frame=representative.frame,
                filed=representative.filed,
                role="composed",
            )
            composed.append((total, tuple(parts)))

        return composed, [
            f"{concept.taxonomy}:{concept.tag}" for concept in addends
        ]

    def _facts_for_metric(
        self,
        cik: str,
        metric: str,
    ) -> Tuple[List[Tuple[SecFact, Tuple[SecFact, ...]]], Optional[str], Optional[List[str]]]:
        """
        Facts for one metric, using the first concept set that has any.

        Returns (facts, reason unavailable, composition). Each fact is paired
        with its constituents, which is empty for a single-concept metric. The
        composition lists the concepts that were summed, and is None when the
        metric is a single concept.
        """
        attempted: List[str] = []
        concepts = SEC_CONCEPTS[metric]
        is_composition = any(concept.role == "addend" for concept in concepts)
        submissions_hash = self._submissions_document_hash(cik)

        if is_composition:
            payloads: Dict[str, Dict[str, Any]] = {}
            hashes: Dict[str, Sequence[str]] = {}
            for part in concepts:
                attempted.append(f"{part.taxonomy}:{part.tag}")
                captured = self._concept_payload(cik, part)
                payloads[part.tag] = captured[0] or {}
                hashes[part.tag] = captured[1]
            composed, composition = self._composed_instant_facts(
                metric, concepts, payloads, hashes, submissions_hash
            )
            if composed:
                return composed, None, composition
            return [], (
                f"{metric} is not reported under any composition of: "
                f"{', '.join(attempted)}"
            ), composition

        for concept in concepts:
            attempted.append(f"{concept.taxonomy}:{concept.tag}")
            payload, hashes = self._concept_payload(cik, concept)
            if not payload:
                continue
            facts = self._facts_for_concept(
                metric, concept, payload, hashes, submissions_hash
            )
            if facts:
                return [(fact, ()) for fact in facts], None, None
        return [], (
            f"{metric} is not reported under any of: {', '.join(attempted)}"
        ), None

    def _concept_payload(
        self,
        cik: str,
        concept: Concept,
    ) -> Tuple[Optional[Dict[str, Any]], Tuple[str, ...]]:
        """
        One concept document, fetched at most once per provider instance.

        The returned hashes are the documents the payload was read from, and
        are empty for a 404 because nothing was read.
        """
        key = f"{cik}|{concept.taxonomy}|{concept.tag}"
        if key not in self._concept_cache:
            before = len(self._documents)
            payload = self.company_concept(
                cik, concept.taxonomy, concept.tag
            )
            self._concept_cache[key] = (
                payload,
                tuple(
                    document.content_hash
                    for document in self._documents[before:]
                ),
            )
        return self._concept_cache[key]

    def _submissions_document_hash(self, cik: str) -> Optional[str]:
        """
        The submissions document for an issuer, which carries the acceptance
        timestamps that make the facts knowable.
        """
        if cik in self._submissions_hashes:
            return self._submissions_hashes[cik]
        try:
            self.submissions(cik)
        except Exception:
            self._submissions_hashes[cik] = None
            return None
        documents = [
            document
            for document in self._documents
            if document.document_type == DOCUMENT_SUBMISSIONS
        ]
        found = documents[-1].content_hash if documents else None
        self._submissions_hashes[cik] = found
        return found

    def _dedupe_facts(self, facts: Sequence[SecFact]) -> Tuple[List[SecFact], int]:
        """
        Drop a fact that a later filing repeated unchanged.

        A quarter is reported by the 10-Q that first disclosed it and again as a
        comparative inside the following 10-K. That is one fact reported twice,
        not two facts. Keyed on everything except the filing, so a genuine
        restatement survives: same period, different value, kept.
        """
        seen = set()
        kept: List[SecFact] = []
        duplicates = 0
        for fact in facts:
            key = (fact.metric, fact.tag, fact.start, fact.end, fact.value)
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            kept.append(fact)
        return kept, duplicates

    def _discrete_facts(
        self,
        facts: Sequence[SecFact],
    ) -> Tuple[List[SecFact], int]:
        discrete: List[SecFact] = []
        rejected = 0
        for fact in facts:
            if is_discrete_period(fact):
                discrete.append(fact)
            else:
                rejected += 1
        discrete.sort(key=lambda fact: (fact.end, fact.accession))
        return discrete, rejected

    def ttm_from_quarters(
        self,
        facts: Sequence[SecFact],
        anchor: Optional[str] = None,
        count: int = TTM_QUARTER_COUNT,
    ) -> Optional[Dict[str, Any]]:
        """Four contiguous quarters, ending at `anchor` when one is given."""
        return _quarter_view(facts, anchor, count, ROLL_FORWARD_TOLERANCE_DAYS)

    def ttm_from_annual(
        self,
        facts: Sequence[SecFact],
        anchor: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """A filed annual period, treated as the trailing view."""
        return _annual_view(facts, anchor, ROLL_FORWARD_TOLERANCE_DAYS)

    def ttm_by_roll_forward(
        self,
        facts: Sequence[SecFact],
        anchor: Optional[str] = None,
        tolerance_days: int = ROLL_FORWARD_TOLERANCE_DAYS,
    ) -> Optional[Dict[str, Any]]:
        """Prior fiscal year minus prior-year cumulative plus current cumulative."""
        return _roll_forward_view(facts, anchor, tolerance_days)

    def build_ttm(
        self,
        facts: Sequence[SecFact],
        anchor: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        The trailing-twelve-month view ending at or before `anchor`.

        Three constructions are tried, most direct first: a filed annual period
        is already twelve months; four contiguous quarters are next; the
        roll-forward is the fallback for a filer whose quarters have a hole.
        Each is preferred over giving up, because a declared construction
        teaches exactly how the two sides were made comparable.
        """
        return (
            self.ttm_from_annual(facts, anchor)
            or self.ttm_from_quarters(facts, anchor)
            or self.ttm_by_roll_forward(facts, anchor)
        )

    def trailing_anchors(
        self,
        facts: Sequence[SecFact],
        limit: int = 4,
    ) -> List[str]:
        """
        Period ends for which a trailing view could be built.

        A comparison is an alignment, not a contest to find the newest number
        on each side. A vendor may be quoting a trailing figure that predates
        the filer's most recent annual report, and the right filing-side window
        is the one covering the same period, not the newest one available.
        """
        ends: List[str] = []
        for fact in facts:
            if is_quarter(fact) or is_annual(fact):
                ends.append(fact.end)
        ordered = sorted(set(ends), reverse=True)
        return ordered[:limit]

    # -- observations ------------------------------------------------------

    def _availability(
        self,
        acceptance: Dict[str, Dict[str, str]],
        fact: SecFact,
    ) -> Tuple[Optional[str], str, bool]:
        """
        The instant a fact became public, and whether that instant is precise.

        Returns (available_at, basis, time_of_day_known). The acceptance
        datetime is preferred because it is the moment EDGAR disseminated the
        submission. The filed date is a provable date whose time of day the SEC
        does not publish, so it is used second and flagged. The retrieval time
        is never used: it is when this process asked, not when the data
        existed.
        """
        record = acceptance.get(fact.accession) or {}
        accepted = record.get("acceptance_datetime")
        if accepted:
            return accepted, AvailabilityBasis.ACCEPTANCE_DATETIME.value, True

        filed = fact.filed or record.get("filing_date")
        if filed:
            return (
                f"{filed}T00:00:00+00:00",
                AvailabilityBasis.FILED_AS_OF_DATE.value,
                False,
            )

        return None, AvailabilityBasis.UNDECLARED.value, False

    def _observation(
        self,
        fact: SecFact,
        company: SecCompany,
        acceptance: Dict[str, Dict[str, str]],
        retrieved_at: str,
        period: Optional[str] = None,
        composition: Optional[List[str]] = None,
        parts: Sequence[SecFact] = (),
    ) -> Observation:
        """Build a contract observation for one fact."""
        contract_unit = xbrl_unit_to_contract_unit(fact.unit) or Unit.RATIO.value
        currency = "USD" if fact.unit in MONETARY_XBRL_UNITS else None
        currency_basis = (
            CurrencyBasis.REPORTED.value
            if currency
            else CurrencyBasis.NOT_APPLICABLE.value
        )
        available_at, available_basis, time_known = self._availability(
            acceptance,
            fact,
        )
        days = duration_days(fact.start or "", fact.end) if fact.start else None
        label = period or period_label(fact.end, days)
        accession_record = acceptance.get(fact.accession) or {}

        raw: Dict[str, Any] = {
            "sec_fact": fact.contract_dict(),
            # The documents this fact was read out of. An observation traced to
            # a URL is not traced to anything: SEC data changes as filings are
            # disseminated and a filing can be corrected after acceptance.
            "source_document_hashes": list(fact.document_hashes),
            "concept_label": fact.label,
            "concept_description": fact.description,
            "accession": fact.accession,
            "form": fact.form,
            "filed": fact.filed,
            "reported_currency_unit": fact.unit,
            # The three SEC dates, kept apart. Collapsing them is how a July
            # filing ends up looking like a June fact.
            "acceptance_datetime": accession_record.get("acceptance_datetime"),
            "filing_date": accession_record.get("filing_date"),
            "report_date": accession_record.get("report_date"),
            "time_of_day_known": time_known,
            "source_document": (
                "https://www.sec.gov/Archives/edgar/data/"
                f"{int(company.cik)}/{fact.accession.replace('-', '')}/"
                if fact.accession
                else None
            ),
        }
        if composition:
            # A composed total is only comparable to another total with the same
            # declared composition, so the composition is the methodology, not
            # a footnote. Naming only the first concept would be a lie about
            # where the number came from.
            methodology = (
                "sum of SEC XBRL "
                + " + ".join(composition)
                + f" as reported in {fact.form} accession {fact.accession}"
            )
        else:
            methodology = (
                f"SEC XBRL {fact.taxonomy}:{fact.tag} as reported in "
                f"{fact.form} accession {fact.accession}"
            )

        if parts:
            raw["composition"] = {
                "concepts": list(composition or ()),
                "parts": [part.contract_dict() for part in parts],
            }

        return Observation(
            observation_id=comparable_observation_id(
                fact.metric,
                "sec",
                period=label,
                accession=fact.accession,
            ),
            metric=fact.metric,
            value=fact.value,
            unit=contract_unit,
            currency=currency,
            currency_basis=currency_basis,
            period_start=fact.start,
            period_end=fact.end,
            as_of=fact.end,
            available_at=available_at,
            available_at_basis=available_basis,
            provider=self.name,
            source_type=self.source_type,
            source_url=CONCEPT_URL.format(
                cik=company.cik,
                taxonomy=fact.taxonomy,
                tag=fact.tag,
            ),
            definition=METRIC_DEFINITIONS[fact.metric],
            methodology=methodology,
            retrieved_at=retrieved_at,
            raw=raw,
            observation_count=None,
            status=ValidationStatus.UNVERIFIABLE,
            status_reasons=(
                "a single official source cannot cross-validate itself",
            ),
            # A directly-sourced observation has no derived inputs; only a
            # constructed one, such as a trailing window, does.
            inputs=(),
            basis=_basis_for(fact),
        )

    def _ttm_observation(
        self,
        metric: str,
        ttm: Dict[str, Any],
        quarterly_observations: Sequence[Observation],
        company: SecCompany,
        acceptance: Dict[str, Dict[str, str]],
        retrieved_at: str,
    ) -> Observation:
        """
        The trailing-twelve-month view on the SEC side.

        Yahoo reports a trailing figure and the SEC reports discrete periods, so
        without this the two sides would be answering different questions and
        the comparison would be a category error. The sum is declared, its
        constituents are preserved, and it is recomputable.
        """
        quarters: List[SecFact] = ttm["constituents"]
        latest = max(quarters, key=lambda fact: fact.end)
        inputs = tuple(
            observation.observation_id for observation in quarterly_observations
        )
        accessions = ", ".join(sorted({fact.accession for fact in quarters}))
        if ttm["construction"] == "SUM_OF_DISCRETE_QUARTERS":
            method = (
                f"sum of {len(quarters)} discrete SEC quarters "
                f"({accessions})"
            )
        else:
            method = (
                "prior fiscal year minus prior-year cumulative plus current "
                f"cumulative ({accessions})"
            )
        if metric == METRIC_EPS_DILUTED:
            method += (
                "; per-share amounts are not strictly additive when the "
                "denominator changes, so this is an approximation"
            )

        # The TTM inherits the availability of its latest input: that is the
        # first moment the whole window could be assembled.
        available_at, available_basis, time_known = self._availability(
            acceptance,
            latest,
        )
        unit = xbrl_unit_to_contract_unit(latest.unit) or Unit.RATIO.value
        currency = "USD" if latest.unit in MONETARY_XBRL_UNITS else None

        return Observation(
            observation_id=comparable_observation_id(
                metric,
                "sec",
                # The anchor end is part of the identity: one filing can supply
                # several trailing windows, and collapsing them would hide a
                # period from the comparison.
                period=f"ttm-to-{ttm['end']}",
                accession=latest.accession,
            ),
            metric=metric,
            value=ttm["value"],
            unit=unit,
            currency=currency,
            currency_basis=(
                CurrencyBasis.REPORTED.value
                if currency
                else CurrencyBasis.NOT_APPLICABLE.value
            ),
            period_start=ttm["start"],
            period_end=ttm["end"],
            as_of=ttm["end"],
            available_at=available_at,
            available_at_basis=available_basis,
            provider=self.name,
            source_type=self.source_type,
            source_url=CONCEPT_URL.format(
                cik=company.cik,
                taxonomy=latest.taxonomy,
                tag=latest.tag,
            ),
            definition=METRIC_DEFINITIONS[metric],
            methodology=method,
            retrieved_at=retrieved_at,
            raw={
                "derivation": ttm["construction"],
                "span_days": ttm["span_days"],
                "constituents": [fact.contract_dict() for fact in quarters],
                "time_of_day_known": time_known,
                "additive": metric != METRIC_EPS_DILUTED,
            },
            observation_count=len(quarters),
            status=ValidationStatus.UNVERIFIABLE,
            status_reasons=(
                "a single official source cannot cross-validate itself",
            ),
            inputs=inputs,
            basis={
                "measurement_basis": "TRAILING_AGGREGATE",
                "reporting_currency": currency or "UNDECLARED",
                "derivation": ttm["construction"],
                "source_declared": True,
            },
        )

    # -- public API --------------------------------------------------------

    def fetch(
        self,
        ticker: str,
        metrics: Sequence[str] = COMPARABLE_METRICS,
    ) -> SecAcquisition:
        """
        Acquire SEC observations for a ticker.

        Returns an acquisition result rather than raising on an unknown ticker:
        an issuer the SEC does not list is unavailable data, not an exception.
        """
        retrieved_at = utc_now()
        company = self.resolve_company(ticker)
        if company is None:
            return SecAcquisition(
                company=None,
                errors=(
                    f"{ticker} is not listed in the SEC company ticker map; "
                    "no CIK could be resolved and no observation was inferred.",
                ),
                retrieved_at=retrieved_at,
            )

        acceptance = self.acceptance_index(company.cik)
        observations: List[Observation] = []
        all_facts: List[SecFact] = []
        errors: List[str] = []
        unavailable: List[str] = []
        rejected_not_discrete = 0
        rejected_duplicate = 0

        for metric in metrics:
            if metric not in SEC_CONCEPTS:
                continue
            try:
                paired, reason, composition = self._facts_for_metric(
                    company.cik,
                    metric,
                )
            except Exception as error:  # noqa: BLE001
                errors.append(
                    f"{metric}: SEC concept request failed: {error}"
                )
                continue

            if not paired:
                if reason:
                    unavailable.append(reason)
                continue

            facts = [fact for fact, _ in paired]
            all_facts.extend(facts)
            deduped, duplicates = self._dedupe_facts(facts)
            rejected_duplicate += duplicates
            discrete, rejected = self._discrete_facts(deduped)
            rejected_not_discrete += rejected

            if not discrete:
                unavailable.append(
                    f"{metric} reported no discrete quarterly or annual period"
                )
                continue

            # Quarters and annuals are truncated separately. Truncating a mixed
            # list by date would let annual filings crowd out the quarters, and
            # the trailing-twelve-month window is built from quarters.
            quarters = [fact for fact in discrete if is_quarter(fact)]
            annuals = [fact for fact in discrete if is_annual(fact)]
            instants = [fact for fact in discrete if is_instant(fact)]
            selected = (
                quarters[-self.max_periods :]
                + annuals[-self.max_annuals :]
                + instants[-self.max_periods :]
            )
            selected.sort(key=lambda fact: (fact.end, fact.accession))

            parts_by_value = {
                (fact.end, round(fact.value, 6)): parts
                for fact, parts in paired
            }

            metric_observations: List[Observation] = []
            for fact in selected:
                parts = parts_by_value.get(
                    (fact.end, round(fact.value, 6)),
                    (),
                )
                try:
                    observation = self._observation(
                        fact,
                        company,
                        acceptance,
                        retrieved_at,
                        composition=composition,
                        parts=parts,
                    )
                except Exception as error:  # noqa: BLE001
                    errors.append(
                        f"{metric} {fact.tag} {fact.end}: {error}"
                    )
                    continue
                observations.append(observation)
                metric_observations.append(observation)

            if metric in TTM_METRICS:
                # One trailing view per anchor a counterparty might be
                # quoting. Alignment picks the window that covers the same
                # period, so the filing side must be able to offer more than
                # its newest number.
                for anchor in self.trailing_anchors(deduped):
                    ttm = self.build_ttm(deduped, anchor=anchor)
                    if ttm is None:
                        continue
                    observations.append(
                        self._ttm_observation(
                            metric,
                            ttm,
                            metric_observations,
                            company,
                            acceptance,
                            retrieved_at,
                        )
                    )
                if not any(
                    isinstance(observation.raw, dict)
                    and observation.raw.get("derivation")
                    for observation in metric_observations
                ) and not any(
                    isinstance(observation.raw, dict)
                    and observation.raw.get("derivation")
                    for observation in observations
                    if observation.metric == metric
                ):
                    unavailable.append(
                        f"{metric} could not form any trailing-twelve-month "
                        f"window from {TTM_QUARTER_COUNT} discrete quarters "
                        "or an annual roll-forward"
                    )

        return SecAcquisition(
            company=company,
            observations=tuple(observations),
            facts=tuple(all_facts),
            errors=tuple(errors),
            rejected_not_discrete=rejected_not_discrete,
            rejected_duplicate=rejected_duplicate,
            unavailable_concepts=tuple(unavailable),
            retrieved_at=retrieved_at,
            documents=tuple(self._documents),
        )
