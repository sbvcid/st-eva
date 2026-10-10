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
import re
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
    METRIC_COMMERCIAL_PAPER,
    METRIC_LONG_TERM_DEBT,
    METRIC_MARKETABLE_SECURITIES_CURRENT,
    METRIC_DEFINITIONS,
    METRIC_EPS_DILUTED,
    METRIC_NET_INCOME,
    METRIC_REVENUE,
    METRIC_SHARES_OUTSTANDING,
    Observation,
    ObservationSet,
    PRECISION_INSTANT,
    SourceType,
    Unit,
    ValidationStatus,
    QUARTER_MAX_DAYS,
    QUARTER_MIN_DAYS,
    YEAR_MAX_DAYS,
    YEAR_MIN_DAYS,
    comparable_observation_id,
    duration_days,
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
"""The enumerated spellings only, kept for callers that name them literally.

**This is no longer the monetary test.** It used to be, which is how every
non-USD monetary fact ended up typed as a ratio with a NULL currency: 2.52
measured 51 of 51 non-USD facts losing their currency and 60 of 60 USD facts
keeping it, with no exception either way. The enumerated spellings below keep
their existing behaviour byte for byte; anything else is decided by
`monetary_currency_of`, which recognises an ISO 4217 code.

`xbrl_unit_to_contract_unit` above is likewise a seed, not the whole rule: an ISO
4217 code it does not list still resolves, through the same two helpers.
"""

# An ISO 4217 alphabetic currency code. XBRL types a monetary item by this
# reference, so a unit that is exactly three upper-case letters is a currency the
# source declared -- recording it is reporting what the filing said, not guessing
# a currency from a domicile, a listing or a ticker.
ISO_4217_CURRENCY_CODE = re.compile(r"^[A-Z]{3}$")


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
    METRIC_LONG_TERM_DEBT: (
        Concept("us-gaap", "LongTermDebtNoncurrent", role="addend"),
        Concept("us-gaap", "LongTermDebtCurrent", role="addend"),
    ),
    METRIC_SHARES_OUTSTANDING: (
        Concept("dei", "EntityCommonStockSharesOutstanding"),
    ),
    METRIC_MARKETABLE_SECURITIES_CURRENT: (
        Concept("us-gaap", "MarketableSecuritiesCurrent"),
    ),
    METRIC_COMMERCIAL_PAPER: (
        Concept("us-gaap", "CommercialPaper"),
    ),
}

# A duration metric needs a trailing-twelve-month view on the SEC side so it can
# be compared with a vendor trailing figure. An instant metric does not.
TTM_METRICS = (METRIC_REVENUE, METRIC_NET_INCOME, METRIC_EPS_DILUTED)

# Default metrics acquired by SECProvider.fetch: includes cross-source comparable
# metrics plus capital-structure balance-sheet components.
SEC_DEFAULT_METRICS: Tuple[str, ...] = tuple(
    list(COMPARABLE_METRICS)
    + [METRIC_MARKETABLE_SECURITIES_CURRENT, METRIC_COMMERCIAL_PAPER]
)


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
DOCUMENT_FILING = "SEC_FILING_DOCUMENT"

ARCHIVES_HOST = "https://www.sec.gov"
ARCHIVES_PATH = "/Archives/edgar/data/"
ARCHIVES_API_HOST = "https://data.sec.gov"


def _document_type_for(uri: str) -> str:
    if "/companyconcept/" in uri:
        return DOCUMENT_COMPANY_CONCEPT
    if "/submissions/" in uri:
        return DOCUMENT_SUBMISSIONS
    # A filing document served off the Archives path. Checked before the
    # fallback, so the three classifications above are unchanged and a ticker
    # map URL is still a ticker map.
    if ARCHIVES_PATH in uri:
        return DOCUMENT_FILING
    return DOCUMENT_TICKER_MAP


def content_hash_of(payload: bytes) -> str:
    """The identity of a document's bytes, always over the uncompressed form."""
    return "sha256:" + hashlib.sha256(payload).hexdigest()


# -- filing resources ------------------------------------------------------
#
# Four SEC resources, deliberately not one. The XBRL endpoints on `data.sec.gov`
# are already reachable; the three below live on `www.sec.gov` and supply
# something those endpoints cannot: which documents a filing contains, what the
# SEC calls each of them, and their bytes.
#
# The registration identity for the Archives host is declared here rather than
# written here. Registration is `store.record_source(...)` and belongs to the
# ingestor, which is Phase 2; a provider that persisted rows would be doing
# something this module is not allowed to do.
#
# `SEC_ARCHIVES_PROVIDER` repeats `sec_ingest.SEC_SOURCE` because `sec_ingest`
# imports this module and an import back would be a cycle. The repetition is
# pinned by a test that asserts the two constants are equal.
SEC_ARCHIVES_PROVIDER = "SecEdgar"
SEC_ARCHIVES_SOURCE_TYPE = SourceType.REGULATORY_FILING.value

SEC_ARCHIVES_SOURCE_REGISTRATION: Dict[str, Any] = {
    "provider": SEC_ARCHIVES_PROVIDER,
    "source_type": SEC_ARCHIVES_SOURCE_TYPE,
    "base_url": ARCHIVES_HOST,
    "notes": (
        "SEC EDGAR Archives: the documents inside one filing. The submissions "
        "index names a filing's primary document as a filename but does not "
        "enumerate the filing, so exhibits, the XBRL instance and the SGML "
        "header are only reachable from here. index.json reports a MIME type "
        "and is not the SEC <TYPE>; the two are separate vocabularies and this "
        "source never substitutes one for the other."
    ),
    # Unlike the XBRL endpoints, which arrive aggregated across dimension
    # members, a filing document is the filer's own bytes and keeps them. An
    # EX-101 instance carries every member a fact was reported with.
    "retains_dimensions": "NONE",
    "aggregation_note": (
        "Documents are stored byte-exact. Hashing is over the uncompressed "
        "response body, so the same declaration holds whether or not the "
        "transport compressed it."
    ),
}

# The SGML header's ACCEPTANCE-DATETIME is a label, not a policy. It is exposed
# so a caller can record which producer supplied an instant without this module
# choosing between two producers or ranking them.
ACCEPTANCE_SOURCE_SGML_HEADER = "SGML_HEADER_ACCEPTANCE_DATETIME"


class SecFilingParseError(ValueError):
    """
    A filing payload that is not the shape the SEC publishes.

    Distinct from a transport failure: a 404 means the filing is not there, a
    parse error means something answered and the answer was not a filing. The two
    are kept apart so a caller can tell "absent" from "corrupt", which are
    different answers and neither of which is a reason to invent documents.
    """


@dataclass(frozen=True)
class FetchedDocument:
    """
    One byte-exact response, before anything has parsed it.

    `content` is the uncompressed body exactly as served. `content_hash` is
    `content_hash_of(content)`, the same function every other capture path uses,
    so hashing here and hashing at persistence cannot disagree.

    Nothing in this object is re-encoded. A parser may decode `content` to read
    it, and what it returns is derived from those decoded bytes; the bytes
    themselves are never rebuilt from the parsed form.
    """

    uri: str
    canonical_uri: Optional[str]
    content: bytes
    content_hash: str
    media_type: Optional[str]
    http_status: int
    byte_size: int
    fetched_at: str


@dataclass(frozen=True)
class DirectoryEntry:
    """
    One entry of an EDGAR filing directory listing.

    There is no `sec_document_type` field and that is the point. `index.json`
    does not carry the SEC `<TYPE>`; its `type` is a MIME type such as `text.gif`
    or `compressed.gif`. An entry therefore states what the directory listing
    said and nothing more, and it cannot be used to name an exhibit.

    `source_ordinal` is this entry's 1-based position in `directory.item`, kept
    in EDGAR's own order. It is not comparable with the ordinal of the same
    document in the SGML `<DOCUMENT>` sequence: measured on two real filings,
    those two sequences agree at zero of seventeen and seven of seventy-nine
    positions respectively, so treating them as one sequence would pair every
    document with the wrong one.

    `byte_size` is `None` where EDGAR publishes an empty `size`, which it does
    for its own index artefacts. An absent size is not a zero-byte document.
    """

    source_ordinal: int
    filename: Optional[str]
    mime_type: Optional[str]
    byte_size: Optional[int]
    last_modified: Optional[str]


@dataclass(frozen=True)
class FilingDirectory:
    uri: str
    content_hash: str
    entries: Tuple[DirectoryEntry, ...]


@dataclass(frozen=True)
class SubmissionDocument:
    """
    One `<DOCUMENT>` block of a full submission.

    `sec_document_type` is the SEC `<TYPE>`: `8-K`, `EX-99.1`, `EX-99.2`,
    `EX-101.INS`, `GRAPHIC`, `XML`. `filename` and `description` are each
    independently absent or empty, because a filing legitimately omits them.

    `source_ordinal` is the block's 1-based position in the SGML sequence, and
    the same `<TYPE>` legitimately repeats -- one filing carried 62 blocks of
    `<TYPE>XML</TYPE>`, the SEC's own rendered report files. That is why neither
    the ordinal nor the type can serve as an identity, and why this object
    carries no assumption that a filename is unique.
    """

    source_ordinal: int
    sec_document_type: Optional[str]
    filename: Optional[str]
    description: Optional[str]


@dataclass(frozen=True)
class SubmissionHeader:
    """
    The SGML header a filing carries about itself.

    Every field is a raw declaration. `None` means the header did not mention
    the field; `""` means it mentioned it and left it empty. Those are different
    answers and neither is collapsed into the other.

    `acceptance_datetime` is the header's own `ACCEPTANCE-DATETIME` element,
    which EDGAR publishes as an Eastern Time wall clock. It is not
    `filed_as_of_date`, which is the calendar day the filing was accepted for
    dissemination, and the two are not interchangeable: the filings index serves
    the same instant as a UTC timestamp, and recovering the wall clock from that
    requires the Eastern Time offset, which no resource here supplies.

    `item_information` holds the header's item *titles* verbatim and
    `item_information_count` how many the header listed. The submissions index
    carries item *codes* for the same filing. They are complementary rather than
    conflicting, and this object never merges them: pairing a code with a title
    would be an inference from list order, and this module makes inferences
    about nothing.

    `fiscal_year_end` is kept as the raw four-character form EDGAR publishes.
    It is a date anchor, not a month: one filer's 2013 filings declared `0929`
    and its 2026 filings declared `0926`, so reducing either to a month integer
    would lose the drift.
    """

    accession_number: Optional[str] = None
    conformed_submission_type: Optional[str] = None
    conformed_period_of_report: Optional[str] = None
    item_information: Tuple[str, ...] = ()
    item_information_count: int = 0
    filed_as_of_date: Optional[str] = None
    acceptance_datetime: Optional[str] = None
    acceptance_source: Optional[str] = None
    public_document_count: Optional[int] = None
    fiscal_year_end: Optional[str] = None

    @property
    def has_acceptance_datetime(self) -> bool:
        """Whether the header declared an instant at all."""
        return self.acceptance_datetime is not None


@dataclass(frozen=True)
class FullSubmission:
    """One parsed full submission: its header and its documents, in EDGAR's order."""

    uri: str
    content_hash: str
    header: SubmissionHeader
    documents: Tuple[SubmissionDocument, ...]


@dataclass(frozen=True)
class Section18Statement:
    """
    One Section 18 "not deemed filed" statement, read from captured bytes.

    `quote_locator` is a `"<start>:<end>"` span of **byte** offsets into the
    captured payload, and `quote_text` is exactly
    `payload[start:end].decode("utf-8")` -- not a cleaned, de-tagged or
    whitespace-normalised rendering of it. Two reasons, both about being able to
    check the work rather than trust it:

        * a reader can slice the stored bytes and see the quotation, so the
          locator is verifiable rather than descriptive;
        * the raw span is what the document actually says. Stripping tags or
          collapsing whitespace would mean the locator no longer addresses the
          quoted bytes, and the quote could no longer be located again.

    The measured real filing bears this out: the sentence is wrapped in a
    `<span style=...>` and uses HTML entities (`&#8220;filed&#8221;`), so a
    text-level search for `"filed"` finds nothing and a tag-stripped quote would
    not correspond to any contiguous byte range.

    `applies_to_filing_item_code` is the first `Item N.NN` the *document* names.
    In the measured filing it is at byte 29858 while the statement is at 30586 --
    the item is named in the document's own heading, not inside the sentence --
    so this is a document-level fact rather than part of the quotation.
    """

    quote_text: str
    quote_locator: str
    applies_to_filing_item_code: Optional[str]

    def quote_from(self, payload: bytes) -> Optional[str]:
        """Re-read the quotation out of the bytes the locator addresses."""
        start, end = (int(part) for part in self.quote_locator.split(":"))
        return payload[start:end].decode("utf-8")


# `shall not be deemed` is the phrase the statute's non-filing statement turns on,
# and `Section 18` is what makes it that statement rather than any other
# "not deemed" language. Both must be present in the same sentence: either alone
# is not sufficient, and requiring both keeps the test from firing on an
# unrelated use of either phrase.
_SECTION_18_MARKER = b"shall not be deemed"
_SECTION_18_CITATION = b"section 18"
# How far after the marker the citation may sit and still be the same sentence.
# The measured sentence places it 56 bytes on.
_SECTION_18_WINDOW = 400
# "Item" and its number are often separated by a non-breaking space, which the
# measured filing writes as `&#160;`, so a plain `\s+` misses it.
_ITEM_SEPARATOR = rb"(?:\s|&#\d+;|&\w+;)+"
_ITEM_CODE = re.compile(
    rb"item" + _ITEM_SEPARATOR + rb"(\d+\.\d{2})", re.IGNORECASE
)


def _sentence_span_around(payload: bytes, marker_start: int) -> Optional[Tuple[int, int]]:
    """
    The sentence containing a marker, as a byte span, without the HTML around it.

    Scans backwards to the end of the preceding tag or newline so the span opens
    on the sentence's first character, and forwards to the full stop that ends
    it. Both directions stop at markup rather than crossing it, so a span never
    contains a partial tag.
    """
    start = marker_start
    while start > 0 and payload[start - 1:start] not in (b">", b"\n"):
        start -= 1
    end = marker_start
    limit = min(len(payload), marker_start + _SECTION_18_WINDOW)
    while end < limit:
        if payload[end:end + 1] == b".":
            following = payload[end + 1:end + 2]
            if following in (b"", b" ", b"\n", b"\t", b"<"):
                return start, end + 1
        end += 1
    return None


def extract_section18_statement(payload: bytes) -> Optional[Section18Statement]:
    """
    Locate a Section 18 non-filing statement in one document's captured bytes.

    Deterministic and a pure function of the bytes: the same capture always
    yields the same span, so re-extraction is idempotent, and a differing result
    from the same bytes is a contradiction the archive rejects rather than
    absorbs. There is no language model and no judgement of legal meaning here --
    the rule is two literal phrases and a citation, and a document that does not
    contain both yields `None`.

    `None` is the ordinary answer for most documents in a filing. Returning
    nothing is not a failure and must not become a fabricated statement.
    """
    lowered = payload.lower()
    citation_at = lowered.find(_SECTION_18_CITATION)
    offset = 0
    while True:
        marker_at = lowered.find(_SECTION_18_MARKER, offset)
        if marker_at < 0:
            return None
        offset = marker_at + 1
        # Both phrases must belong to the same sentence.
        window_end = min(len(payload), marker_at + _SECTION_18_WINDOW)
        if citation_at < 0 or not (
            marker_at < citation_at < window_end
        ):
            continue
        span = _sentence_span_around(payload, marker_at)
        if span is None:
            continue
        start, end = span
        item = _ITEM_CODE.search(payload)
        return Section18Statement(
            quote_text=payload[start:end].decode("utf-8", errors="replace"),
            quote_locator=f"{start}:{end}",
            applies_to_filing_item_code=(
                item.group(1).decode("ascii") if item else None
            ),
        )


def filing_directory_url(cik: str, accession: str) -> str:
    """The `index.json` that lists one filing's directory."""
    return (
        f"{ARCHIVES_HOST}{ARCHIVES_PATH}{int(cik)}"
        f"/{accession.replace('-', '')}/index.json"
    )


def full_submission_url(cik: str, accession: str) -> str:
    """The `.txt` carrying one filing's SGML header and every document inline."""
    return (
        f"{ARCHIVES_HOST}{ARCHIVES_PATH}{int(cik)}"
        f"/{accession.replace('-', '')}/{accession}.txt"
    )


def filing_document_url(cik: str, accession: str, filename: str) -> str:
    """One document inside a filing, by the filename its manifest declared."""
    return (
        f"{ARCHIVES_HOST}{ARCHIVES_PATH}{int(cik)}"
        f"/{accession.replace('-', '')}/{filename}"
    )


def _optional_text(value: Any) -> Optional[str]:
    """A JSON string, or `None` for an absent or non-string value.

    An empty string survives as an empty string. `index.json` publishes an empty
    `size` for its own index artefacts and an empty `name` would be a real
    defect rather than a missing value; neither is silently promoted to a value
    the resource did not give.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    return value


def _optional_size(value: Any) -> Optional[int]:
    """`index.json` publishes `size` as a *string*, and empty for index artefacts."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_filing_directory(payload: bytes, uri: str) -> FilingDirectory:
    """
    Parse an EDGAR filing directory listing, in EDGAR's own order.

    Deterministic: the same bytes always yield the same entries in the same
    sequence, and nothing is sorted, deduplicated or inferred. The three EDGAR
    index artefacts every filing carries (`-index.html`, `-index-headers.html`
    and the `.txt`) are returned like any other entry, because whether a
    directory entry is a filed document or an artefact EDGAR generated is a
    question about the SGML manifest, and answering it here would mean guessing
    from a filename.
    """
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SecFilingParseError(
            f"filing directory at {uri} is not JSON: {error}"
        ) from error
    if not isinstance(document, dict):
        raise SecFilingParseError(
            f"filing directory at {uri} is not a JSON object"
        )
    directory = document.get("directory")
    if not isinstance(directory, dict):
        raise SecFilingParseError(
            f"filing directory at {uri} has no `directory` object"
        )
    items = directory.get("item")
    if not isinstance(items, list):
        raise SecFilingParseError(
            f"filing directory at {uri} has no `directory.item` list"
        )
    entries: List[DirectoryEntry] = []
    for position, item in enumerate(items):
        if not isinstance(item, dict):
            raise SecFilingParseError(
                f"filing directory at {uri} entry {position + 1} is not an object"
            )
        entries.append(DirectoryEntry(
            source_ordinal=position + 1,
            filename=_optional_text(item.get("name")),
            mime_type=_optional_text(item.get("type")),
            byte_size=_optional_size(item.get("size")),
            last_modified=_optional_text(item.get("last-modified")),
        ))
    return FilingDirectory(
        uri=uri, content_hash=content_hash_of(payload), entries=tuple(entries),
    )


_HEADER_LINE = re.compile(r"^([A-Z][A-Z0-9 \-]*?):[ \t]*(.*)$")


def parse_sgml_header(text: str) -> SubmissionHeader:
    """
    Parse the SGML header, keeping every declaration raw.

    Header lines are `KEY:<whitespace>value`, and several keys repeat --
    `ITEM INFORMATION` once per item, `FORMER COMPANY` once per former name. A
    repeated scalar is taken as the first occurrence rather than silently
    concatenated, because a concatenation would invent a value EDGAR never
    wrote.

    `ACCEPTANCE-DATETIME` is not one of these: EDGAR publishes it as an XML
    element inside the header rather than as a `KEY: value` line, so it is read
    in its own `<ACCEPTANCE-DATETIME>` form.
    """
    accession: Optional[str] = None
    form: Optional[str] = None
    period: Optional[str] = None
    filed: Optional[str] = None
    acceptance: Optional[str] = None
    document_count: Optional[int] = None
    fiscal_year_end: Optional[str] = None
    items: List[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        match = _HEADER_LINE.match(stripped)
        if match is None:
            continue
        key, value = match.group(1).strip(), match.group(2).strip()
        if key == "ACCESSION NUMBER" and accession is None:
            accession = value
        elif key == "CONFORMED SUBMISSION TYPE" and form is None:
            form = value
        elif key == "CONFORMED PERIOD OF REPORT" and period is None:
            period = value
        elif key == "FILED AS OF DATE" and filed is None:
            filed = value
        elif key == "PUBLIC DOCUMENT COUNT" and document_count is None:
            document_count = int(value) if value.isdigit() else None
        elif key == "FISCAL YEAR END" and fiscal_year_end is None:
            fiscal_year_end = value
        elif key == "ITEM INFORMATION":
            items.append(value)

    # Verified against a real submission: EDGAR writes
    # `<ACCEPTANCE-DATETIME>20260730163028` as an *unclosed* element with nothing
    # after it on the line, and no `</ACCEPTANCE-DATETIME>` anywhere in the file.
    # Two mistakes are available here and both are silent. Requiring a closing tag
    # yields None for every real filing; capturing with `[^<]*` instead swallows
    # the whole remaining header, because the next `<` is the end of the SGML
    # header block and everything up to it is captured as the timestamp. So the
    # value is bounded to its line and then cut at any tag.
    element = re.search(r"<ACCEPTANCE-DATETIME>([^\r\n]*)", text)
    if element is not None:
        acceptance = element.group(1).split("<", 1)[0].strip() or None

    return SubmissionHeader(
        accession_number=accession,
        conformed_submission_type=form,
        conformed_period_of_report=period,
        item_information=tuple(items),
        item_information_count=len(items),
        filed_as_of_date=filed,
        acceptance_datetime=acceptance,
        acceptance_source=(
            ACCEPTANCE_SOURCE_SGML_HEADER if acceptance is not None else None
        ),
        public_document_count=document_count,
        fiscal_year_end=fiscal_year_end,
    )


_SGML_DOCUMENT = re.compile(r"<DOCUMENT>(.*?)</DOCUMENT>", re.S)
# Verified against a real submission: `<TYPE>8-K`, `<FILENAME>aapl-20260730.htm`
# and `<DESCRIPTION>FORM 8-K` are likewise *unclosed* elements whose value runs
# to the end of the line. So the capture is bounded to its line and then cut at
# any tag, exactly as ACCEPTANCE-DATETIME is. A pattern requiring
# `</TYPE>` returns None for every real filing.
_SGML_FIELD = r"<{tag}>([^\r\n]*)"


def parse_full_submission(payload: bytes, uri: str) -> FullSubmission:
    """
    Parse a full submission into its header and its document sequence.

    A submission is recognised by its `<SEC-DOCUMENT>` marker. Without that
    marker the payload is not a filing and this raises rather than returning an
    empty document list, because "this is not a filing" and "this filing declares
    no documents" are different answers and only one of them is an absence.

    A `<DOCUMENT>` opened and never closed is also an error. Counting the openers
    against the matched blocks catches it, which a non-greedy match alone would
    not: an unclosed block would simply be absent from the results and the
    sequence would silently shift, pairing every later document with the wrong
    ordinal.

    The document bodies are decoded with replacement rather than strict decoding
    so that one odd byte in a multi-megabyte filing does not discard every
    declaration in it. The decoded text is only ever read; `content_hash` covers
    the bytes, and the bytes are what a capture stores.
    """
    text = payload.decode("utf-8", errors="replace")
    if "<SEC-DOCUMENT>" not in text:
        raise SecFilingParseError(
            f"full submission at {uri} carries no <SEC-DOCUMENT> marker"
        )
    header_text = text.split("<DOCUMENT>")[0]
    header = parse_sgml_header(header_text)

    opened = text.count("<DOCUMENT>")
    blocks = _SGML_DOCUMENT.findall(text)
    if len(blocks) != opened:
        raise SecFilingParseError(
            f"full submission at {uri} declares {opened} documents but "
            f"{len(blocks)} closed correctly"
        )

    documents: List[SubmissionDocument] = []
    for position, block in enumerate(blocks):
        fields = {}
        for tag in ("TYPE", "FILENAME", "DESCRIPTION"):
            found = re.search(_SGML_FIELD.format(tag=tag), block)
            value = found.group(1).split("<", 1)[0] if found else None
            fields[tag] = value.strip() if value else None
        documents.append(SubmissionDocument(
            source_ordinal=position + 1,
            sec_document_type=fields["TYPE"] or None,
            filename=fields["FILENAME"] or None,
            description=fields["DESCRIPTION"] or None,
        ))
    return FullSubmission(
        uri=uri,
        content_hash=content_hash_of(payload),
        header=header,
        documents=tuple(documents),
    )


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


def monetary_currency_of(unit: str) -> Optional[str]:
    """
    The currency code this unit is denominated in, or None if it is not monetary.

    Two rules, and only two.

    The enumerated spellings keep the behaviour they always had, byte for byte,
    so no already-recorded USD value moves. Everything else is decided by
    whether the unit is an ISO 4217 code -- optionally followed by a `/shares`
    divisor, which names the code it is per-share of.

    Before 2.52 this decision was `unit in ("USD",)`, and a TWD or CAD or JPY
    fact was stored as a ratio with no currency at all, which is how 278 IFRS
    and 20 US-GAAP observations ended up unable to satisfy a currency-family
    metric.
    """
    explicit = XBRL_UNIT_TO_CONTRACT_UNIT.get(unit)
    if explicit == Unit.CURRENCY.value:
        return unit
    if explicit == Unit.PER_SHARE.value:
        return "USD"
    if explicit is not None:
        return None
    if ISO_4217_CURRENCY_CODE.match(unit or ""):
        return unit
    base, slash, divisor = (unit or "").partition("/shares")
    if slash and not divisor and ISO_4217_CURRENCY_CODE.match(base):
        return base
    return None


def observation_currency_of(unit: str) -> Optional[str]:
    """
    The currency for a contract observation's `currency` column.

    A per-share fact keeps its currency in the basis rather than here, because
    the observation's unit is already `per_share` and the currency column states
    what the observation is *measured in*.
    """
    if xbrl_unit_to_contract_unit(unit) != Unit.CURRENCY.value:
        return None
    return monetary_currency_of(unit)


def xbrl_unit_to_contract_unit(unit: str) -> Optional[str]:
    """
    The contract unit this XBRL unit is recorded under, or None if unrecognised.

    The enumerated spellings are answered from the table. An ISO 4217 code the
    table does not list is a currency and resolves to `currency`, and a code
    followed by `/shares` resolves to `per_share`. Anything else returns None so
    that the caller refuses it rather than coercing it.
    """
    explicit = XBRL_UNIT_TO_CONTRACT_UNIT.get(unit)
    if explicit is not None:
        return explicit
    if ISO_4217_CURRENCY_CODE.match(unit or ""):
        return Unit.CURRENCY.value
    base, slash, divisor = (unit or "").partition("/shares")
    if slash and not divisor and ISO_4217_CURRENCY_CODE.match(base):
        return Unit.PER_SHARE.value
    return None


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
            fact.unit if fact.unit in MONETARY_XBRL_UNITS
            else monetary_currency_of(fact.unit) or "UNDECLARED"
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
        # Every network request this provider instance made. The 2.5.1
        # incremental-ingestion acceptance test asserts on this count, so it has
        # to be the transport's own tally rather than an inference from what
        # happened to be stored.
        self._fetch_log: List[str] = []
        # Transport accounting, for the scale question. See `_get`.
        self.requests_made = 0
        self.bytes_downloaded = 0

    @property
    def network_fetches(self) -> int:
        """How many requests this provider actually made."""
        return len(self._fetch_log)

    @property
    def concept_fetches(self) -> int:
        """
        Requests for concept documents, as opposed to indexes.

        The index has to be re-read on every run, because it is the only way
        to learn whether anything changed. A concept document is only fetched
        when a new filing has been accepted, and a run that finds nothing new
        must fetch none of them.
        """
        return sum(
            1 for url in self._fetch_log if "/companyconcept/" in url
        )

    @property
    def fetch_log(self) -> Tuple[str, ...]:
        return tuple(self._fetch_log)

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

        Every call is counted and every body measured, in `transport_stats()`.
        They are here because the question "is ten thousand companies actually
        feasible" is a question about **requests and bytes per company**, and a
        harness that cannot answer it has to guess. Counting a request costs
        nothing and guessing the order of magnitude later costs a redesign.
        """
        self._throttle()
        self._fetch_log.append(url)
        self.requests_made += 1
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
                self.bytes_downloaded += len(body)
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

    def _fetch_bytes(
        self,
        url: str,
        allow_missing: bool = False,
    ) -> Optional[FetchedDocument]:
        """
        Fetch a document and return its bytes, whatever they are.

        A sibling of `_get`, not an extension of it. `_get` is JSON-only and
        asserts so: it raises `ValueError` on a body that will not parse as JSON,
        because every caller of `_get` wanted a JSON endpoint. A filing document
        is HTML or a full submission, so making `_get` accept it would mean
        weakening an invariant three existing call sites depend on. The two
        methods share `_throttle`, the user agent, gzip handling, the fetch log
        and `_record_document`, so there is still only one SEC rate limiter and
        one byte ledger.

        What comes back is the uncompressed body exactly as served, and its hash
        is `content_hash_of(body)` -- the same function every other capture path
        hashes with, so a document hashed here and hashed again at persistence
        cannot disagree. Nothing is decoded, re-encoded or normalised. A parser
        that later reads these bytes derives from them; it does not replace them.

        `allow_missing` keeps `_get`'s meaning exactly: a 404 is an answer and
        returns `None`, and any other HTTP status raises as before. An empty body
        is *not* a failure -- a zero-byte response is a fact about a resource, and
        whether that resource is the thing we wanted is the parser's judgement to
        make, not this method's.
        """
        self._throttle()
        self._fetch_log.append(url)
        self.requests_made += 1
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                # Not `application/json`: this method exists for the documents
                # that are not JSON, and asking for JSON would make the response
                # reflect our header rather than the resource.
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read()
                self.bytes_downloaded += len(body)
                encoding = response.headers.get("Content-Encoding", "")
                if encoding == "gzip":
                    body = gzip.decompress(body)
                status = response.getcode()
                media_type = response.headers.get("Content-Type")
        except urllib.error.HTTPError as error:
            if error.code == 404 and allow_missing:
                return None
            raise
        self._record_document(url, body, status, media_type)
        return FetchedDocument(
            uri=url,
            canonical_uri=url,
            content=body,
            content_hash=content_hash_of(body),
            media_type=media_type,
            http_status=status,
            byte_size=len(body),
            fetched_at=utc_now(),
        )

    def filing_directory(
        self,
        cik: str,
        accession: str,
        allow_missing: bool = False,
    ) -> Optional[FilingDirectory]:
        """
        Read one filing's directory listing.

        Returns the manifest in EDGAR's own order, with no entry sorted away and
        none dropped -- including the index artefacts EDGAR generates, which is
        what lets a caller tell a filed document from a generated one by
        comparing against the SGML manifest rather than by guessing from a name.
        """
        url = filing_directory_url(cik, accession)
        fetched = self._fetch_bytes(url, allow_missing=allow_missing)
        if fetched is None:
            return None
        return parse_filing_directory(fetched.content, fetched.uri)

    def full_submission(
        self,
        cik: str,
        accession: str,
        allow_missing: bool = False,
    ) -> Optional[FullSubmission]:
        """
        Read one filing's full submission: its SGML header and its documents.

        The header and the document sequence come from one response and are
        therefore consistent with each other, which is why they are returned
        together rather than as two separately-fetched things.
        """
        url = full_submission_url(cik, accession)
        fetched = self._fetch_bytes(url, allow_missing=allow_missing)
        if fetched is None:
            return None
        return parse_full_submission(fetched.content, fetched.uri)

    def filing_document(
        self,
        cik: str,
        accession: str,
        filename: str,
        allow_missing: bool = False,
    ) -> Optional[FetchedDocument]:
        """
        Fetch one document's bytes, byte-exact.

        No parsing happens here and none is offered. The caller already knows the
        filename from a manifest and is entitled to the bytes; what those bytes
        *mean* -- which exhibit they are, whether they are furnished, which
        concept they report -- is derived downstream from what the manifests and
        the header declared, never from the filename or the SEC `<TYPE>` alone.
        """
        url = filing_document_url(cik, accession, filename)
        return self._fetch_bytes(url, allow_missing=allow_missing)

    def transport_stats(self) -> Dict[str, Any]:
        """
        What this provider cost, and what it brought back.

        Four numbers and the two ratios that decide whether a population is
        reachable: requests and bytes per company, and bytes per filing. The
        ratios are the point -- a raw byte total says nothing without a
        denominator, and the question at scale is never "how much data" but "how
        much per company and whether that is a linear or a super-linear cost".
        """
        unique_bytes = sum(
            document.byte_size or 0 for document in self._documents
        )
        return {
            "requests_made": self.requests_made,
            "bytes_downloaded": self.bytes_downloaded,
            "documents_retained": len(self._documents),
            "unique_document_bytes": unique_bytes,
            # The two byte figures above are *different units* and must not be
            # divided into each other: `bytes_downloaded` is what came off the
            # wire, gzipped, and `unique_document_bytes` is the decompressed
            # payload we keep. The first version of this method reported their
            # ratio as a deduplication ratio, which is a category error and
            # produced the confidently meaningless 0.157.
            #
            # A real deduplication figure needs *served* bytes on both sides, so
            # it is not reported here rather than reported wrongly. What is
            # meaningful and is reported: requests per unique document, which
            # says how many times a document had to be asked for to keep it once.
            "requests_per_unique_document": (
                round(self.requests_made / len(self._documents), 2)
                if self._documents else None
            ),
        }

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

    def document_hashes(self) -> Tuple[str, ...]:
        return tuple(document.content_hash for document in self._documents)

    def documents_for(
        self,
        taxonomy: str,
        concept: str,
    ) -> Tuple[SECDocument, ...]:
        """
        Captured documents for one concept, in fetch order.

        The ingestion path stores what the parser actually read rather than
        reading the endpoint a second time, because a second read is a second
        version and the point is to keep the one the fact came from.
        """
        return tuple(
            document
            for document in self._documents
            if document.uri.endswith(f"/{taxonomy}/{concept}.json")
        )

    def filing_index(self, cik: str) -> List[Dict[str, Any]]:
        """
        The submissions index: one entry per filing, as EDGAR publishes it.

        A filing's identity is its accession number, and this is where they
        come from. The 2.5.1 ingestion diffs this against the filings the
        archive holds, so a run with nothing new accepted fetches no documents
        at all. An amendment arrives under a new accession, which is exactly why
        the accession is the thing that diffs: a restatement is a new filing,
        not a change to an old one.
        """
        recent = (self.submissions(cik).get("filings") or {}).get("recent") or {}
        accessions = recent.get("accessionNumber") or []
        entries: List[Dict[str, Any]] = []
        for position, accession in enumerate(accessions):
            def column(name: str) -> Optional[str]:
                values = recent.get(name) or []
                if position < len(values):
                    return values[position]
                return None

            entries.append(
                {
                    "accession": str(accession),
                    "form": column("form"),
                    "filing_date": column("filingDate"),
                    "report_date": column("reportDate"),
                    "acceptance_datetime": column("acceptanceDateTime"),
                    # EDGAR publishes the acceptance instant, so this index
                    # declares an instant. The declaration is what lets a
                    # source with only a date say so without the consumer
                    # inferring the precision from the shape of a string.
                    "acceptance_precision": PRECISION_INSTANT,
                    "primary_document": column("primaryDocument"),
                    "is_xbrl": column("isXBRL"),
                }
            )
        return entries

    def concept_history(
        self,
        cik: str,
        taxonomy: str,
        concept: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Every fact a source has published for one concept, across all history.

        The ingestion path uses this rather than `fetch`, because an archive
        needs the whole series and `fetch` deliberately keeps only a recent
        window. Returns None when the concept is not reported at all, which is
        an answer rather than a failure.
        """
        return self.company_concept(cik, taxonomy, concept)

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
        currency = (
            monetary_currency_of(fact.unit)
            if contract_unit in (Unit.CURRENCY.value, Unit.PER_SHARE.value)
            else None
        )
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
        currency = (
            monetary_currency_of(latest.unit)
            if unit in (Unit.CURRENCY.value, Unit.PER_SHARE.value)
            else None
        )

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
        metrics: Sequence[str] = SEC_DEFAULT_METRICS,
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
