from __future__ import annotations

"""
ST-EVA 2.5.1 - incremental ingestion for one issuer.

    SEC submissions
        -> filing identity
        -> source document
        -> source fact
        -> concept registry
        -> metric mapping
        -> observation
        -> validation
        -> archive

Three properties this exists to hold, each with an acceptance test rather than
an intention.

    A second identical run changes nothing. Not one new filing, document,
    source fact, observation, or network request. Storage deduplicates on
    content hash already; the *fetch* diff is what this adds, because
    re-downloading a decade of filings on every run is correct for the store
    and indefensible for a source that asks callers to be considerate.

    A source fact has a stable identity that is not its value. Two filings
    reporting the same number are two facts, and two dimension members of one
    concept are two facts even when the aggregated endpoint shows them as one.

    A source concept is not a semantic metric. A vendor aggregate has no filing
    concept and says so with a null, rather than putting a metric name where a
    concept belongs.
"""

import json
import re
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from archive import FilingRef, StoredDocument
from core_registry import CoreRegistry
from data_contract import (
    AvailabilityBasis,
    Observation,
    PRECISION_DATE,
    PRECISION_INSTANT,
    PRECISION_NONE,
    PRECISIONS,
    SourceType,
    Unit,
    ValidationStatus,
    is_number,
    utc_now,
)
from evidence_model import canonical_json, source_fact_id
from sec_provenance import (
    document_fact_id,
    document_fact_identity,
    fiscal_calendar_declaration_id,
    filing_acceptance_id,
    filing_declaration_id,
    filing_document_declaration_id,
    filing_document_statement_id,
    filing_document_statement_identity,
    filing_item_declaration_id,
    filing_item_id,
    parse_items,
    project_held_filings,
)
from sec_provider import (
    DOCUMENT_FILING,
    extract_section18_statement,
    observation_currency_of,
    xbrl_unit_to_contract_unit,
)
from sec_xbrl_facts import XbrlParseError, parse_xbrl_document

SEC_SOURCE = "SecEdgar"
SEC_SOURCE_TYPE = SourceType.REGULATORY_FILING.value
SEC_CANONICAL = "https://data.sec.gov"

# The first slice ingests the concepts the registry has mapped for these
# metrics. It is a vertical slice, not coverage: a wider set is an ingestion
# change, never a schema change.
DEFAULT_METRICS = (
    "revenue",
    "net_income",
    "eps_diluted",
    "assets",
    "cash",
    "debt",
    "capex",
    "shares_outstanding",
)

DEFAULT_FORMS = ("10-K", "10-Q")

# How a source says what precision its availability value has.
#
# A filing index may carry `acceptance_precision` beside the value. Both
# producers in this repository set it: the SEC API index has EDGAR's
# `acceptanceDateTime`, which is an instant, and the bulk index is derived from
# each fact's `filed` date, which is not. The key exists so that a source with
# only a date can say so, rather than the consumer guessing from the shape of a
# string -- which is what it used to do, and 2.14 measured the result: two routes
# that were each right about which *basis* they meant still disagreed on
# 17,043 of 17,043 rows because neither of them said what the precision was.
#
# An index that carries a value without declaring its precision is read as an
# instant, because a source that puts a time in the field is asserting a time.
# The declaration is what lets a date-only source be honest without a guess.
DEFAULT_ACCEPTANCE_PRECISION = PRECISION_INSTANT

# SIC major groups, and the business model each one implies.
#
# Read from the filer's own submission rather than from a company list, so the
# classification is the issuer's and the rule is checkable by anyone with the
# same filing. Only groups that name a business model in the registry's closed
# vocabulary are mapped at all; everything else resolves to `None`, which means
# *no inapplicability ruling is made* and every declared metric stays
# applicable. That is the safe direction to be wrong in: an unclassified issuer
# gets asked about a metric that turns out not to exist, and is told so by the
# evidence layer, rather than silently having a metric removed from its coverage.
SIC_GROUPS: Tuple[Tuple[int, int, str], ...] = (
    (10, 14, "MINING"),
    (20, 39, "MANUFACTURING"),
    (70, 89, "SERVICES"),
    # SIC 60-67 was one bucket, which made a bank, an insurer, a credit union
    # and a finance company the same class. Split only as far as the rules need.
    #
    # 60 is depository institutions -- banks and savings banks -- and it is the
    # one group whose classification changes an applicability ruling: `gross_profit`
    # and `operating_income` are refused for BANK, and BANK had been unreachable
    # from any SIC code, so those two rules had never fired for the reason they
    # were written. 63 and 64 are insurance carriers and insurance agents and
    # brokers. 61 and 62 stay FINANCE_SERVICES on purpose: savings institutions
    # and credit unions are arguably either, and a wrong guess there is a
    # ruling removed from a real filer on the strength of a two-digit code. A
    # broad honest bucket beats a precise wrong one.
    #
    # **63-64 changes nothing yet, and that is the point of stating it.** No
    # seeded applicability rule names INSURANCE, so making it reachable adds a
    # label and not a ruling. It is worth doing because the classification then
    # matches the filer, and because the rules that would use it are then aimed
    # at a reachable class -- but it does not by itself test insurance
    # applicability, and claiming that it does would be a null result dressed as
    # a success. Writing those rules is a semantic decision, not a mapping fix.
    #
    # `REIT` (SIC 65) is deliberately **not** mapped. It is reachable only
    # through `DECLARED_BY_ISSUER`, `DERIVED_FROM_REPORTED_CONCEPTS` or
    # `MANUAL_CLASSIFICATION`, none of which the SEC ingestion path performs,
    # and inventing a SIC rule to make the vocabulary look covered is the wrong
    # direction: the question being asked is whether the classification has
    # enough resolution to explain missing evidence, and a rule added to raise
    # taxonomy coverage cannot answer it.
    (60, 60, "BANK"),
    (61, 62, "FINANCE_SERVICES"),
    (63, 64, "INSURANCE"),
)


def business_model_from_filer_classification(
    submissions: Dict[str, Any],
) -> Tuple[Optional[str], Optional[str]]:
    """
    The business model an issuer declares, and where the declaration is from.

    Returns `(business_model, source)`. `None` for the model when the
    classification does not name one in the closed vocabulary, and the source is
    the SIC code and description either way, because a reader who finds an
    issuer unclassified should be able to see what it actually said.
    """
    sic = submissions.get("sic")
    source = None
    if sic:
        description = submissions.get("sicDescription")
        source = f"SIC {sic} {description}".strip()
    if sic in (None, ""):
        return None, source
    try:
        major = int(sic) // 100
    except (TypeError, ValueError):
        return None, source
    for low, high, model in SIC_GROUPS:
        if low <= major <= high:
            return model, source
    return None, source


# Why a filing or an issuer produced no evidence, as a closed vocabulary.
#
# 2.11's acceptance criterion is **not** a success rate. A run over a hundred
# issuers that reports "94% collected" is worth less than one that reports what
# the other six percent was, because the first number cannot be acted on and the
# second can. So a failure is a *kind*, recorded with the thing it happened to,
# and the report is only considered complete when every failure has one.
#
# The kinds are drawn at the two places a run can fail, and they are different
# questions:
#
#   the *issuer* could not be worked on at all   ISSUER_UNRESOLVED
#   a *filing* could not be used                 FILING_UNSUPPORTED,
#                                                FILING_UNREADABLE
#   a *document* would not parse                 PARSER_FAILURE
#   the *registry* had nothing to ask            REGISTRY_UNRESOLVED
#   the *source* had nothing                     SOURCE_SILENT
#   the *business* rules it out                  NOT_APPLICABLE
#   it was never *attempted*                     NOT_ATTEMPTED
#
# `PARSER_FAILURE` and `FILING_UNSUPPORTED` are the two that did not exist before
# 2.11 and are the ones a success rate would have hidden. A filing whose form the
# pipeline does not handle and a filing whose document would not parse look
# identical in a count -- both produce nothing -- and they call for opposite
# responses: one is scope, the other is a bug.
OUTCOME_COLLECTED = "COLLECTED"
OUTCOME_SOURCE_SILENT = "SOURCE_SILENT"
OUTCOME_NOT_APPLICABLE = "NOT_APPLICABLE"
OUTCOME_NOT_ATTEMPTED = "NOT_ATTEMPTED"
OUTCOME_REGISTRY_UNRESOLVED = "REGISTRY_UNRESOLVED"
OUTCOME_PARSER_FAILURE = "PARSER_FAILURE"
OUTCOME_FILING_UNSUPPORTED = "FILING_UNSUPPORTED"
OUTCOME_FILING_UNREADABLE = "FILING_UNREADABLE"
OUTCOME_ISSUER_UNRESOLVED = "ISSUER_UNRESOLVED"
OUTCOME_PARTIAL = "PARTIAL"
INGESTION_OUTCOMES = (
    OUTCOME_COLLECTED,
    OUTCOME_SOURCE_SILENT,
    OUTCOME_NOT_APPLICABLE,
    OUTCOME_NOT_ATTEMPTED,
    OUTCOME_REGISTRY_UNRESOLVED,
    OUTCOME_PARSER_FAILURE,
    OUTCOME_FILING_UNSUPPORTED,
    OUTCOME_FILING_UNREADABLE,
    OUTCOME_ISSUER_UNRESOLVED,
    OUTCOME_PARTIAL,
)


@dataclass
class IngestionReport:
    """What one run did, counted rather than asserted."""

    asset: str
    cik: str
    run_id: str
    filings_seen: int = 0
    filings_already_held: int = 0
    filings_ingested: int = 0
    documents_stored: int = 0
    documents_reused: int = 0
    source_facts_stored: int = 0
    source_facts_skipped: int = 0
    observations_stored: int = 0
    observations_skipped: int = 0
    network_fetches: int = 0
    concept_fetches: int = 0
    concepts_unresolved: int = 0
    dimension_collisions: int = 0
    errors: List[str] = field(default_factory=list)
    # Every failure, with its kind and the thing it happened to. Empty is a
    # claim, and the claim is only meaningful because the kinds are closed: a run
    # with no entries has classified everything that did not happen.
    failures: List[Dict[str, str]] = field(default_factory=list)
    outcomes: Dict[str, int] = field(default_factory=dict)
    transport: Dict[str, Any] = field(default_factory=dict)
    elapsed_seconds: float = 0.0

    def classify(
        self,
        outcome: str,
        subject: str = "",
        detail: str = "",
    ) -> None:
        """
        Record one thing that did not become evidence, and why.

        `outcome` must be in the closed vocabulary. A free-text failure would
        put this back to being a log, and a log is what the acceptance criterion
        was written against.
        """
        if outcome not in INGESTION_OUTCOMES:
            raise ValueError(
                f"ingestion outcome {outcome!r} is not in "
                f"{list(INGESTION_OUTCOMES)}"
            )
        self.failures.append({
            "outcome": outcome,
            "subject": subject,
            "detail": detail[:400],
        })
        self.outcomes[outcome] = self.outcomes.get(outcome, 0) + 1

    @property
    def changed_anything(self) -> bool:
        return bool(
            self.filings_ingested
            or self.documents_stored
            or self.observations_stored
        )

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "asset": self.asset,
            "cik": self.cik,
            "run_id": self.run_id,
            "filings_seen": self.filings_seen,
            "filings_already_held": self.filings_already_held,
            "filings_ingested": self.filings_ingested,
            "documents_stored": self.documents_stored,
            "documents_reused": self.documents_reused,
            "source_facts_stored": self.source_facts_stored,
            "source_facts_skipped": self.source_facts_skipped,
            "observations_stored": self.observations_stored,
            "observations_skipped": self.observations_skipped,
            "network_fetches": self.network_fetches,
            "concept_fetches": self.concept_fetches,
            "concepts_unresolved": self.concepts_unresolved,
            "dimension_collisions": self.dimension_collisions,
            "errors": list(self.errors),
            # The classified absence, which is the thing a success rate would
            # have compressed away.
            "outcome": self.headline_outcome(),
            "outcomes": dict(self.outcomes),
            "failures": list(self.failures),
            "transport": dict(self.transport),
            "elapsed_seconds": self.elapsed_seconds,
        }

    @property
    def outcome(self) -> str:
        """
        The one word a reader takes away, chosen from the classified failures
        rather than from a success rate.

        A property rather than a method because `contract_dict` publishes it
        under that name, and a report whose attribute is spelled one way and
        reached another is a report people stop reading. It was exactly that
        mismatch, caught by a test.

        A run that stored something is `COLLECTED` even if some metrics came
        back empty, because the empty ones carry their own classifications and
        `PARTIAL` would imply a fault where there is none. A run that stored
        nothing reports the worst thing that happened to it, so a parser failure
        is never summarised as "no data".
        """
        return self.headline_outcome()

    def headline_outcome(self) -> str:
        if self.observations_stored:
            return OUTCOME_COLLECTED
        for outcome in (
            OUTCOME_PARSER_FAILURE,
            OUTCOME_FILING_UNREADABLE,
            OUTCOME_FILING_UNSUPPORTED,
            OUTCOME_ISSUER_UNRESOLVED,
            OUTCOME_REGISTRY_UNRESOLVED,
        ):
            if self.outcomes.get(outcome):
                return outcome
        if self.filings_ingested:
            return OUTCOME_SOURCE_SILENT
        return OUTCOME_NOT_ATTEMPTED


class Ingestor:
    """Accumulates one issuer's filed evidence, incrementally."""

    def __init__(
        self,
        store: Any,
        provider: Any,
        registry: CoreRegistry,
    ) -> None:
        self.store = store
        self.provider = provider
        self.registry = registry
        self.connection = store.connection
        # The run this ingest is writing, and the scope rows waiting on it.
        # A scope row names a run, and the run row is written last, so the scope
        # is buffered and written alongside it.
        self._current_run_id: Optional[str] = None
        # (run_id, asset_id, metric_id, mapping_count, attempted,
        #  observations_stored, status) -- the row as `ingestion_scope` stores it.
        self._pending_scope: List[
            Tuple[str, str, str, int, int, int, str]] = []
        # Provenance failures, buffered for the run report rather than raised.
        #
        # Provenance is strictly additive and no observation depends on it, so a
        # provenance write that fails must not turn a run that stored facts into a
        # run that stored none. It must also not vanish: a silent skip would make
        # the archive look as though a filing declared nothing when in fact the
        # declaration was never written. So the failure is collected here and
        # flushed into `report.errors` at the end of `ingest`.
        self._provenance_errors: List[str] = []

    # -- filing identity -------------------------------------------------

    def held_accessions(self, asset_id: str) -> set:
        return {
            row["accession"]
            for row in self.connection.execute(
                "SELECT accession FROM held_filings WHERE asset_id = ?",
                (asset_id,),
            )
        }

    def _known_cik(self, ticker: str) -> Optional[str]:
        """
        The CIK this archive already holds, without asking anyone.

        The ticker map is a global document that is fetched once and never
        changes in a way that matters here, and re-fetching it on every run to
        learn something already stored is one request too many.
        """
        row = self.connection.execute(
            "SELECT cik FROM assets WHERE ticker = ? AND cik IS NOT NULL",
            (ticker.upper(),),
        ).fetchone()
        return row["cik"] if row else None

    def _record_filing(
        self,
        asset_id: str,
        entry: Dict[str, Any],
        document_id: str,
    ) -> None:
        self.connection.execute(
            "INSERT OR IGNORE INTO held_filings (asset_id, accession, form,"
            " filed_at, period_end, report_date, primary_document, document_id,"
            " first_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                asset_id,
                entry["accession"],
                entry.get("form"),
                entry.get("filing_date"),
                entry.get("report_date"),
                entry.get("report_date"),
                entry.get("primary_document"),
                document_id,
                utc_now(),
            ),
        )

    # -- the run ---------------------------------------------------------

    def ingest(
        self,
        ticker: str,
        metrics: Sequence[str] = DEFAULT_METRICS,
        forms: Sequence[str] = DEFAULT_FORMS,
    ) -> IngestionReport:
        """
        Ingest every filing this issuer has accepted that the archive lacks.

        The index is re-read every run, because it is the only way to learn
        whether anything changed. A concept document is fetched only when a new
        filing has been accepted, so a run that finds nothing new downloads
        nothing.
        """
        started = time.monotonic()
        report: IngestionReport
        cik = self._known_cik(ticker)
        if cik is None:
            company = self.provider.resolve_company(ticker)
            if company is None:
                # A ticker the SEC does not list is a fact about the universe,
                # not an error to raise. At 2.11's population a raise would end
                # the run on the first bad name and leave every later issuer
                # unclassified -- the failure would be total and the report
                # would say nothing about which issuer caused it.
                report = IngestionReport(
                    asset=ticker.upper(), cik="", run_id="",
                )
                report.classify(
                    OUTCOME_ISSUER_UNRESOLVED, ticker.upper(),
                    "the SEC company map does not list this ticker",
                )
                report.elapsed_seconds = round(
                    time.monotonic() - started, 3
                )
                return report
            cik = company.cik
            name = company.name
        else:
            name = ticker.upper()

        # An issuer we already hold under a *different ticker* is the same
        # company, not a conflict. The EDGAR map lists every share class as its
        # own ticker -- a preferred and its common share one CIK between them --
        # so a caller working from tickers will hand us the same issuer twice, and
        # the right answer is to use the asset that exists rather than to refuse.
        # The UNIQUE constraint on `assets.cik` is the archive's opinion on the
        # question and it is the right one: two rows for one CIK would put the
        # same filing under two names and make every later comparison ambiguous.
        asset_id = self.store.asset_id_for_cik(cik) if hasattr(
            self.store, "asset_id_for_cik"
        ) else None
        if asset_id is None:
            asset_id = self.store.record_asset(
                ticker.upper(), cik=cik, name=name
            )

        # The issuer's declared business model, recorded before anything is
        # fetched, so the applicability surface is reachable from the first
        # observation rather than needing a second pass. It is a fact about the
        # filer taken from the filer's own submission, and it is what lets
        # `NOT_APPLICABLE` be derived rather than asserted per issuer.
        #
        # A provider that cannot supply the classification is not an error. The
        # classification is worth having and is not worth failing an ingestion
        # over: without it the registry simply makes no inapplicability ruling
        # for that issuer, which is the same position as any unclassified issuer
        # and the safe direction to be wrong in.
        declared, declared_source = (
            business_model_from_filer_classification(
                self.provider.submissions(cik)
            )
            if hasattr(self.provider, "submissions") else (None, None)
        )
        if declared is not None:
            self.registry.set_issuer_business_model(
                asset_id,
                declared,
                basis="DECLARED_BY_ISSUER",
                source=declared_source,
            )

        report = IngestionReport(
            asset=ticker.upper(), cik=cik, run_id="run_" + uuid.uuid4().hex[:16]
        )
        # The run this ingest writes, for the scope rows buffered against it.
        self._current_run_id = report.run_id

        index = self.provider.filing_index(cik)
        wanted = set(forms)
        relevant = [
            entry
            for entry in index
            if entry.get("form") in wanted
            and entry.get("is_xbrl") in (1, "1", True)
        ]
        report.filings_seen = len(relevant)
        # Accession to (value, precision), and the precision is the index's own
        # declaration rather than something recovered from the value. A bulk
        # index derived from each fact's `filed` date declares a date; the SEC
        # submissions index declares EDGAR's acceptance instant. Reading the
        # declaration is what makes the two routes agree.
        acceptance: Dict[str, Optional[Tuple[str, str]]] = {}
        for entry in index:
            value = entry.get("acceptance_datetime")
            if not value:
                acceptance[entry["accession"]] = None
                continue
            precision = str(
                entry.get("acceptance_precision")
                or DEFAULT_ACCEPTANCE_PRECISION
            )
            if precision not in PRECISIONS:
                raise ValueError(
                    f"filing index declares precision {precision!r} for "
                    f"{entry['accession']}, which is not a declared precision"
                )
            acceptance[entry["accession"]] = (str(value), precision)

        held = self.held_accessions(asset_id)
        report.filings_already_held = len(
            [entry for entry in relevant if entry["accession"] in held]
        )
        new_entries = [
            entry for entry in relevant if entry["accession"] not in held
        ]
        report.filings_ingested = len(new_entries)

        # Filing-level provenance, recorded before any fact is stored. The order
        # is the foreign keys: a filing exists before anything references it.
        #
        # It runs on every run and not only when something is new, because a
        # filing the index listed is still worth asserting today: the index is
        # re-read each run precisely so that a changed declaration is noticed, and
        # a changed declaration becomes a second row rather than an amendment.
        #
        # Failures are buffered rather than raised. Provenance is additive and no
        # observation depends on it, so a write that fails here must not turn a run
        # that stored facts into a run that stored none.
        self._provenance_errors = []
        submission = self._submission_recent(cik)
        try:
            self._acquire_filing_provenance(asset_id, index, submission)
        except Exception as error:  # noqa: BLE001
            self._record_provenance_failure("filing_metadata", error)
        try:
            self._acquire_fiscal_calendar(asset_id, submission)
        except Exception as error:  # noqa: BLE001
            self._record_provenance_failure("fiscal_calendar", error)
        # B1 and B2: the two manifests, fetched and written separately so that
        # one being unreadable does not discard the other.
        try:
            self._acquire_filing_manifests(asset_id, cik, index)
        except Exception as error:  # noqa: BLE001
            self._record_provenance_failure("filing_manifests", error)
        # The bytes themselves, for the documents two independent manifests agree
        # this filing contains. `new_entries` is the evidence for capture kind: an
        # accession already in `held_filings` when this run began was not first
        # discovered here.
        try:
            self._acquire_document_bytes(
                asset_id, cik, index,
                frozenset(entry["accession"] for entry in new_entries),
            )
        except Exception as error:  # noqa: BLE001
            self._record_provenance_failure("document_bytes", error)
        # Statements are read from bytes this run already captured, so this
        # follows the capture phase and fetches nothing.
        try:
            for entry in index:
                accession = str(entry.get("accession") or "")
                if accession:
                    self._acquire_document_statements(asset_id, accession)
        except Exception as error:  # noqa: BLE001
            self._record_provenance_failure("document_statements", error)
        # XBRL facts are read from bytes this run already captured, so this
        # follows the capture phase and fetches nothing. It reads every captured
        # document of the filing, not just the primary one, because a fact may be
        # asserted in an `EX-101.INS` and nowhere else.
        try:
            for entry in index:
                accession = str(entry.get("accession") or "")
                if accession:
                    self._acquire_document_fact_occurrences(asset_id, accession)
        except Exception as error:  # noqa: BLE001
            self._record_provenance_failure("document_fact_occurrences", error)

        if not new_entries:
            # Nothing new was accepted, so no concept endpoint can have
            # changed for a filing we already hold. Fetching them again would
            # re-download a decade of filings to learn nothing.
            #
            # The scope is still recorded, and recorded as `NOT_ATTEMPTED`. A run
            # that asked nothing must not read as a run that looked and found
            # silence, because those are the same sentence to every count that
            # reads `ingestion_runs` -- and they are opposite facts.
            self._record_scope(asset_id, metrics, attempted=False)
            for metric in metrics:
                report.classify(
                    OUTCOME_NOT_ATTEMPTED, metric,
                    "the run found no new filings, so it asked nothing",
                )
            report.errors.extend(self._provenance_errors)
            self._count_fetches(report)
            report.transport = self._transport_stats()
            report.elapsed_seconds = round(time.monotonic() - started, 3)
            self._write_run(asset_id, report, "NO_CHANGE")
            return report

        # The scope is recorded after the metrics are ingested, not before. It used
        # to be written here, which meant the status could only describe what the
        # archive already held -- so a first run labelled every mapped metric
        # `SOURCE_SILENT` before it had asked anything. The per-metric count this
        # run wrote is what the row now reports.
        stored_by_metric: Dict[str, int] = {}
        for metric in metrics:
            # Which of these two it is changes what happens next, and a success
            # rate cannot tell them apart: one is a bug in our reading and one
            # is a fact about the filer. The exception text names the class.
            before = report.observations_stored
            try:
                self._ingest_metric(
                    cik, ticker.upper(), metric, acceptance, report,
                    asset_id=asset_id,
                )
            except Exception as error:  # noqa: BLE001
                report.errors.append(f"{metric}: {type(error).__name__}: {error}")
                report.classify(
                    self._classify_metric_error(error), metric,
                    f"{type(error).__name__}: {error}",
                )
            else:
                stored_by_metric[metric] = report.observations_stored - before
                if report.observations_stored == before:
                    report.classify(
                        OUTCOME_SOURCE_SILENT, metric,
                        "asked, and the source reported no figure for it",
                    )

        self._record_scope(asset_id, metrics, attempted=True,
                           stored=stored_by_metric)

        for entry in new_entries:
            self._record_filing(asset_id, entry, "")
        self._record_adoption(asset_id)
        self.connection.commit()
        report.errors.extend(self._provenance_errors)
        self._count_fetches(report)
        report.transport = self._transport_stats()
        report.elapsed_seconds = round(time.monotonic() - started, 3)
        self._write_run(
            asset_id, report, "OK" if not report.errors else "PARTIAL"
        )
        return report

    def collection_chain(self, ticker: str) -> Dict[str, Any]:
        """
        The whole collection chain for one filer, per metric.

        Written after every run so that "can collection coverage be maintained"
        is answerable from a sequence of runs rather than from one measurement.
        The four concept and fact counts move between runs for different reasons
        -- a mapping is a decision, adoption is evidence about the filer,
        observations are what is in hand -- and collapsing them into a percentage
        is what makes a coverage figure impossible to act on.
        """
        from coverage_semantics import collection_chain

        asset_id = self.store.record_asset(
            ticker.upper(), cik=self.provider.resolve_company(ticker).cik
        )
        return collection_chain(
            self.connection, self.registry, asset_id, ticker.upper()
        )

    def coverage(self, ticker: str) -> Dict[str, Any]:
        """
        How much of this filer's history the archive holds, stated honestly.

        Evidence coverage and filing-ledger coverage are different things and the
        difference is not small. The company-concept endpoint reaches back to
        2006; the submissions index that populates the ledger carries roughly the
        last year to 1,000 filings. So a large share of the facts held have an
        accession the ledger has never seen.

        Nothing is missing from the archive — the facts are there and they trace
        to a real accession. What is missing is the *incremental* view of that
        history. The ledger answers "what is new since the last run", and beyond
        the index window it cannot answer it, because it does not know those
        filings exist. Stating the two numbers side by side is the honest form;
        a single "coverage" figure would be an interpretation.
        """
        asset_id = self.store.record_asset(ticker.upper())
        held = self.connection.execute(
            "SELECT COUNT(*) AS n FROM observations WHERE asset_id = ?",
            (asset_id,),
        ).fetchone()["n"]
        with_accession = self.connection.execute(
            "SELECT COUNT(*) AS n FROM observations"
            " WHERE asset_id = ? AND accession IS NOT NULL",
            (asset_id,),
        ).fetchone()["n"]
        unledgered = self.connection.execute(
            "SELECT COUNT(*) AS n FROM observations o"
            " WHERE o.asset_id = ? AND o.accession IS NOT NULL"
            " AND NOT EXISTS (SELECT 1 FROM held_filings h"
            " WHERE h.accession = o.accession AND h.asset_id = o.asset_id)",
            (asset_id,),
        ).fetchone()["n"]
        ledgers = self.connection.execute(
            "SELECT MIN(filed_at) AS earliest, MAX(filed_at) AS latest,"
            " COUNT(*) AS n FROM held_filings WHERE asset_id = ?",
            (asset_id,),
        ).fetchone()
        fact_span = self.connection.execute(
            "SELECT MIN(period_end) AS earliest, MAX(period_end) AS latest"
            " FROM observations WHERE asset_id = ? AND period_end IS NOT NULL",
            (asset_id,),
        ).fetchone()
        return {
            "asset": ticker.upper(),
            "evidence": {
                "observations": held,
                "with_accession": with_accession,
                "earliest_period": fact_span["earliest"],
                "latest_period": fact_span["latest"],
            },
            "filing_ledger": {
                "filings": ledgers["n"] or 0,
                "earliest_filing": ledgers["earliest"],
                "latest_filing": ledgers["latest"],
            },
            "observations_outside_the_ledger": unledgered,
            "ledger_covers_all_evidence": unledgered == 0,
            "note": (
                "The submissions index carries only recent filings, so the "
                "ledger is a recent-filing view. Facts older than the index are "
                "held and traceable but are not in the incremental diff, which "
                "means 'what changed' is answerable only inside the index "
                "window. Closing this needs SEC's historical submission files or "
                "the EDGAR full-index, not a wider company-concept call."
            ),
        }

    def _record_adoption(self, asset_id: str) -> None:
        """
        Derive what this filer was observed doing with each concept.

        Read back out of the stored facts rather than carried alongside the run,
        so adoption is a property of the evidence and not of one execution. Two
        runs that stored the same facts agree; a run that stored fewer does not
        shrink the record.

        This is what separates "the concept means revenue" from "MSFT reported
        it as revenue from 2007". The former is the mapping; the latter is this
        row, and only the second one is specific to a filer.
        """
        rows = self.connection.execute(
            "SELECT source_concept_ref AS concept_id,"
            " MIN(period_end) AS first_used, MAX(period_end) AS last_used,"
            " COUNT(*) AS fact_count, COUNT(DISTINCT accession) AS filing_count"
            " FROM observations WHERE asset_id = ?"
            " AND source_concept_ref IS NOT NULL GROUP BY source_concept_ref",
            (asset_id,),
        ).fetchall()
        for row in rows:
            self.registry.record_adoption(
                asset_id=asset_id,
                concept_id=row["concept_id"],
                first_used=row["first_used"],
                last_used=row["last_used"],
                fact_count=row["fact_count"],
                filing_count=row["filing_count"],
            )

    def _count_fetches(self, report: IngestionReport) -> None:
        report.network_fetches = self.provider.network_fetches
        report.concept_fetches = self.provider.concept_fetches

    def _write_run(self, asset_id: str, report: IngestionReport, status: str) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO ingestion_runs (run_id, asset_id, source_id,"
            " started_at, finished_at, filings_seen, filings_already_held,"
            " filings_ingested, documents_stored, documents_reused,"
            " source_facts_stored, source_facts_skipped, observations_stored,"
            " observations_skipped, network_fetches, concepts_unresolved,"
            " status, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,"
            " ?, ?, ?, ?, ?)",
            (
                report.run_id,
                asset_id,
                SEC_SOURCE,
                utc_now(),
                utc_now(),
                report.filings_seen,
                report.filings_already_held,
                report.filings_ingested,
                report.documents_stored,
                report.documents_reused,
                report.source_facts_stored,
                report.source_facts_skipped,
                report.observations_stored,
                report.observations_skipped,
                report.network_fetches,
                report.concepts_unresolved,
                status,
                "; ".join(report.errors) or None,
            ),
        )
        # The run exists now, so the scope can name it. Written in the same
        # transaction as the run so the two cannot come apart.
        for row in self._pending_scope:
            if row[0] != report.run_id:
                continue
            self.connection.execute(
                "INSERT OR REPLACE INTO ingestion_scope (run_id, asset_id,"
                " metric_id, mapping_count, attempted, observations_stored,"
                " status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (row[0], row[1], row[2], row[3], row[4], row[5], row[6]),
            )
        self._pending_scope = [
            row for row in self._pending_scope if row[0] != report.run_id
        ]
        # The collisions, in the same transaction as the run they belong to.
        # A collision is a statement about a metric, so filing it per issuer
        # would put the number somewhere nobody asking the question looks:
        # 2.21 could report 404 collisions across eight banks and still be unable
        # to say whether any of them belonged to gross profit.
        seen_collisions = set()
        for row in getattr(self, "_pending_collisions", []):
            if row[0] != report.run_id:
                continue
            key = row[1:8]
            if key in seen_collisions:
                continue
            seen_collisions.add(key)
            self.connection.execute(
                "INSERT OR REPLACE INTO ingestion_dimension_collisions"
                " (run_id, asset_id, metric_id, concept_id, accession,"
                " period_start, period_end, unit, distinct_values,"
                " collision_kind, detected_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (*row, utc_now()),
            )
        self._pending_collisions = [
            row for row in getattr(self, "_pending_collisions", [])
            if row[0] != report.run_id
        ]
        self.connection.commit()

    def _availability_for(
        self,
        fact: Dict[str, Any],
        acceptance: Dict[str, Optional[Tuple[str, str]]],
    ) -> Tuple[Optional[str], str, str]:
        """
        When this fact became public, on what basis, and at what precision.

        Three answers rather than one, because they are three different claims
        and the archive has to be able to make all three:

            value      what the source published, at the precision it
                       published it
            basis      which of the contract's declared bases that is
            precision  whether a consumer may treat the value as an instant

        The order is the SEC's own: the acceptance datetime is preferred,
        because it is the moment EDGAR disseminated the submission; the filed
        date is second, because it is a provable date whose time of day the SEC
        does not publish. The retrieval time is never used. It is when this
        process asked, not when the data existed.

        **The filed date is kept as a date.** It used to be rendered as
        `T00:00:00+00:00`, which asserted that EDGAR disseminated the filing at
        midnight, and the archive then made the fact replayable from that
        midnight. 2.14 measured the consequence across the two delivery routes:
        6,508 of 17,043 facts were replayable from a moment before the filer
        published them. A date is a claim about a day; an invented time of day is
        a claim about history that no filing supports.
        """
        accession = str(fact.get("accn") or "")
        declared = acceptance.get(accession)
        if declared is not None:
            value, precision = declared
            if value:
                if precision == PRECISION_DATE:
                    return (
                        value,
                        AvailabilityBasis.FILED_AS_OF_DATE.value,
                        PRECISION_DATE,
                    )
                return (
                    value,
                    AvailabilityBasis.ACCEPTANCE_DATETIME.value,
                    PRECISION_INSTANT,
                )
        filed = str(fact.get("filed") or "").strip()
        if filed:
            return (
                filed,
                AvailabilityBasis.FILED_AS_OF_DATE.value,
                PRECISION_DATE,
            )
        return None, AvailabilityBasis.UNDECLARED.value, PRECISION_NONE

    def _concept_plan(
        self,
        metric: str,
    ) -> List[Tuple[str, str, Any]]:
        """
        Every concept the registry maps to this metric, most faithful first.

        Taken from the registry, never from a name. A metric with no mapping
        is skipped and counted as unresolved rather than guessed at.
        """
        plan: List[Tuple[str, str, Any]] = []
        for mapping in self.registry.mappings_for_metric(metric):
            concept = self.registry.concept(mapping.concept_id)
            if concept is None:
                continue
            plan.append((concept.taxonomy, concept.concept, mapping))
        return plan

    def _ingest_metric(
        self,
        company_cik: str,
        ticker: str,
        metric: str,
        acceptance: Dict[str, Optional[str]],
        report: IngestionReport,
        asset_id: str = "",
    ) -> None:
        """
        Ingest every concept the registry maps to this metric, not just the
        first one that answers.

        Stopping at the first would store the current tag and drop the history
        that preceded it, which is exactly the loss the registry's windows exist
        to prevent: a filer that switched concepts has two real facts per period
        boundary, and keeping only the newer one silently rewrites the past. The
        series break is already recorded against the metric, so storing both is
        what makes the break observable in data rather than only in metadata.
        """
        plan = self._concept_plan(metric)
        if not plan:
            report.concepts_unresolved += 1
            return

        stored_any = 0
        for taxonomy, concept, mapping in plan:
            payload = self.provider.concept_history(
                company_cik, taxonomy, concept
            )
            if not payload:
                continue
            document_id = self._store_document(
                company_cik, taxonomy, concept, payload, report
            )
            stored_any += self._store_facts(
                company_cik,
                asset_id,
                ticker,
                metric,
                taxonomy,
                concept,
                mapping,
                payload,
                document_id,
                acceptance,
                report,
            )

        if not stored_any:
            report.concepts_unresolved += 1

    def _transport_stats(self) -> Dict[str, Any]:
        """What this issuer cost, when the provider can say."""
        stats = getattr(self.provider, "transport_stats", None)
        return dict(stats()) if callable(stats) else {}

    @staticmethod
    def _classify_metric_error(error: Exception) -> str:
        """
        Which kind of failure an exception was, from what the pipeline knows
        about its own stages.

        Keyed on the exception *type* rather than its text, because the text is
        whatever the network or the parser happened to say and the type is ours.
        """
        if isinstance(error, (ValueError, json.JSONDecodeError)):
            return OUTCOME_PARSER_FAILURE
        if isinstance(error, UnicodeDecodeError):
            return OUTCOME_FILING_UNREADABLE
        if isinstance(error, urllib.error.HTTPError):
            if error.code == 404:
                return OUTCOME_SOURCE_SILENT
            if error.code in (403, 429, 500, 502, 503, 504):
                return OUTCOME_FILING_UNREADABLE
        if isinstance(error, urllib.error.URLError):
            return OUTCOME_FILING_UNREADABLE
        return OUTCOME_FILING_UNREADABLE

    def _record_scope(
        self,
        asset_id: str,
        metrics: Sequence[str],
        attempted: bool,
        stored: Optional[Dict[str, int]] = None,
    ) -> None:
        """
        Write down what this run was asked to collect.

        `ingestion_runs` says what a run did and nothing about what it was for,
        so "this metric has no observations" has been a sentence with three
        meanings that all read the same. This is the record that separates them,
        and it is written on every run including the ones that ask nothing --
        an unattempted metric is the single most useful thing a coverage figure
        can report, because it is the only status that is a to-do item.

        The status is decided by what this run did for the metric, plus what the
        archive already holds. A metric with no declaration is `NO_MAPPING`; one
        with a declaration that stored nothing here and holds nothing is
        `SOURCE_SILENT`; one that stored something here, or already held
        something, is `INGESTED`. The two call for completely different work.

        This used to be decided before the metrics were ingested, from
        `_metric_observed` alone, which could only see the past. On a first run
        that made every mapped metric `SOURCE_SILENT` -- 18 of 20 falsely, on the
        MU pilot -- because the rows it was going to ask about did not exist yet.
        `stored` is the per-metric count this run actually wrote, and it is
        already computed by the ingest loop to classify silence; passing it in
        is what lets the status describe this run instead of the archive's
        memory.

        `observations_stored` is the count THIS RUN stored for the metric. It is
        deliberately not a lifetime total, not the archive's holding, and not an
        attempt count: the row's grain is (run_id, metric_id), so every column in
        it describes one run's encounter with one metric. The lifetime question is
        already answered elsewhere, from `observations` directly, which is what
        `scoped_ledger` does.
        """
        run_id = self._current_run_id
        if not run_id:
            return
        stored = stored or {}
        # Buffered rather than written here. A scope row names a run, and the run
        # row is written at the end of the run, so writing now would insert a
        # child before its parent. `_write_run` writes both in one transaction,
        # which also means a run can never exist without its scope or vice
        # versa.
        self._pending_scope = getattr(self, "_pending_scope", [])
        for metric in metrics:
            mapping_count = len(self.registry.mappings_for_metric(metric))
            stored_here = int(stored.get(metric, 0))
            if not attempted:
                status = "NOT_ATTEMPTED"
            elif mapping_count == 0:
                status = "NO_MAPPING"
            elif stored_here or self._metric_observed(metric, asset_id):
                status = "INGESTED"
            else:
                status = "SOURCE_SILENT"
            self._pending_scope.append(
                (run_id, asset_id, metric, mapping_count, int(attempted),
                 stored_here, status)
            )

    def _metric_observed(self, metric: str, asset_id: str) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM observations WHERE asset_id = ? AND metric = ?"
            " LIMIT 1", (asset_id, metric),
        ).fetchone()
        return row is not None

    def _ensure_sec_source(self) -> None:
        """
        Register what SEC EDGAR is, once per archive.

        The evidence path had no `sources` row at all: documents carried a
        `provider` string and nothing described what that provider *is* or what
        shape its facts arrive in. So a question like "does this endpoint keep the
        dimensional axis" had nowhere to be answered, and the only way to express
        it was as a per-metric exception -- which is a property of the accident
        rather than of the data.

        Declared once, here, because it is true of the endpoint and not of any
        filer or metric:

            AGGREGATE   both EDGAR XBRL endpoints drop the member axis, so two
                        facts differing only by dimension arrive looking like one.
                        `companyconcept` is per-concept over the same flattened
                        view, so reading concept-by-concept does not recover it.

        That is a limitation of the source and not a defect in the archive, and
        saying so at the source is what lets the per-event collision records be
        read as *evidence* of this rather than as a list of metrics that are odd.
        """
        if getattr(self, "_sec_source_registered", False):
            return
        self.store.record_source(
            SEC_SOURCE,
            SourceType.REGULATORY_FILING.value,
            base_url=SEC_CANONICAL,
            notes=(
                "SEC EDGAR XBRL company facts and company concept. Every fact "
                "carries one accession, period and unit; the dimensional axis is "
                "not returned. Two facts differing only by member therefore "
                "arrive looking identical, which is what "
                "`ingestion_dimension_collisions` records."
            ),
            retains_dimensions="AGGREGATE",
            aggregation_note=(
                "Facts are aggregated across dimension members. A period with "
                "two or more distinct values for one concept is therefore "
                "ambiguous by construction, and which member each value belongs "
                "to is not determinable from this source."
            ),
        )
        self._sec_source_registered = True

    def _store_document(
        self,
        cik: str,
        taxonomy: str,
        concept: str,
        payload: Dict[str, Any],
        report: IngestionReport,
    ) -> str:
        """
        Capture the bytes that were parsed.

        Taken from the transport's own capture of this fetch, so what is stored
        is what the parser read and not a second read that might differ.
        """
        documents = self.provider.documents_for(taxonomy, concept)
        if not documents:
            return ""
        self._ensure_sec_source()
        document = documents[-1]
        uri = (
            f"{SEC_CANONICAL}/api/xbrl/companyconcept/CIK{cik}"
            f"/{taxonomy}/{concept}.json"
        )
        before = self.store.document_count()
        document_id = self.store.record_source_document(
            StoredDocument(
                content_hash=document.content_hash,
                uri=uri,
                canonical_uri=uri,
                http_status=document.http_status,
                media_type=document.media_type,
                byte_size=document.byte_size,
                fetched_at=document.fetched_at,
                first_seen_at=document.fetched_at,
                payload=document.payload,
                provider=document.provider,
                document_type=document.document_type,
            )
        )
        if self.store.document_count() > before:
            report.documents_stored += 1
        else:
            report.documents_reused += 1
        return document_id

    def _ensure_filing_identity(
        self,
        asset_id: str,
        accession: str,
        entry: Dict[str, Any],
    ) -> None:
        """
        Make sure every accession a fact came from has a filing row.

        `held_filings` is written from the submissions index, and that index is
        bounded: EDGAR publishes roughly the most recent thousand filings per
        filer. The XBRL *concept* endpoint reaches much further back, so an
        issuer's company facts legitimately contain accessions the index never
        mentions. Those facts were stored, and no filing row was written for
        them, and the consequence was that the provenance chain stopped one link
        short for every one of them:

            observation -> source_fact_id -> document -> accession -> ???

        2.7 asked for that chain to resolve to a filing and to found that it did
        not, for 29 of 86 accessions. It is not new with this round -- the sealed
        2.6 archive has the same gap for 30 of 74 -- and nothing about it is
        specific to a framework or an issuer. It is a gap in writing down an
        identity that was sitting in the fact the whole time.

        `form` and `filed` come from the fact's own record, so the row is
        recorded from evidence rather than guessed. The filing's *document* is
        left empty when the fact did not name one, because inventing a document
        reference would be worse than an honest null, and the document link for
        these facts already resolves through `observation_sources`.
        """
        if not accession:
            return
        exists = self.connection.execute(
            "SELECT 1 FROM held_filings WHERE asset_id = ? AND accession = ?",
            (asset_id, accession),
        ).fetchone()
        if exists is not None:
            return
        # Provenance for the accessions the submissions index never lists. This
        # runs before the ledger insert and is independent of it, so a fact from
        # outside the index still gets filing identity even though `held_filings`
        # keeps no row for it. Guarded for the same reason the rest of provenance
        # is: this sits inside the per-fact loop, and raising here would turn a
        # provenance problem into a lost metric.
        try:
            self._record_fact_filing_provenance(asset_id, accession, entry)
        except Exception as provenance_error:  # noqa: BLE001
            self._record_provenance_failure(
                f"fact_filing:{accession}", provenance_error
            )
        form = str(entry.get("form") or "").strip() or None
        filed = str(entry.get("filed") or "").strip() or None
        report_date = str(entry.get("fy") or "")
        self.connection.execute(
            "INSERT OR IGNORE INTO held_filings (asset_id, accession, form,"
            " filed_at, period_end, report_date, primary_document, document_id,"
            " first_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                asset_id,
                accession,
                form,
                filed,
                None,
                report_date or None,
                None,
                "",
                utc_now(),
            ),
        )

    # -- provenance: filing metadata (0020) --------------------------------
    #
    # Acquisition A. Everything here is an *assertion by a source*, written to a
    # relation whose identity is a digest of that assertion, so a repeated run is
    # a no-op and a changed assertion becomes a second row rather than an
    # amendment. No writer here touches an Observation, and no observation
    # depends on anything written here.
    #
    # Two producers are represented and one deliberately is not. The submissions
    # index and an individual fact are both sources; the SGML header is a third,
    # and this phase does not read it, so `SGML_SUBMISSION_HEADER` is absent here
    # rather than asserted from something else. Inventing a declaration nobody
    # made is the failure this whole layer exists to prevent.

    SUBMISSIONS_INDEX = "SUBMISSIONS_API_FILING_INDEX"
    SUBMISSIONS_ITEMS = "SUBMISSIONS_API_ITEMS"
    SUBMISSIONS_ACCEPTANCE = "SUBMISSIONS_API_ACCEPTANCE_DATETIME"
    SUBMISSIONS_FISCAL_YEAR_END = "SUBMISSIONS_API_FISCAL_YEAR_END"
    FACT_RECORD = "FACT_RECORD"

    def _record_provenance_failure(self, where: str, error: BaseException) -> None:
        """
        Note a provenance failure without ending the run.

        The archive already says this about the business-model classification
        (`:486`) for the same reason: a value this run could not write is not
        worth losing a decade of facts over. It is not worth losing silently
        either, so it is buffered and reported rather than swallowed.
        """
        self._provenance_errors.append(
            f"provenance:{where}: {type(error).__name__}: {error}"
        )

    def _submission_recent(self, cik: str) -> Dict[str, Any]:
        """
        The submissions payload's `filings.recent` columns, read once.

        `filing_index()` is a flattened view of exactly seven columns. Two things
        this phase needs are not among them: `items`, which names the sections a
        filing declares, and the issuer-level `fiscalYearEnd`, which names when
        the filer's year ends. Both live in the payload `ingest()` has already
        fetched, so reading them costs no request. A provider without
        `submissions`, or one that fails, yields nothing rather than a guess.
        """
        absent = {"recent": {}, "fiscalYearEnd": None}
        if not hasattr(self.provider, "submissions"):
            return absent
        try:
            payload = self.provider.submissions(cik) or {}
        except Exception as error:  # noqa: BLE001
            self._record_provenance_failure("submissions", error)
            return absent
        filings = payload.get("filings") or {}
        return {
            "recent": filings.get("recent") or {},
            "fiscalYearEnd": payload.get("fiscalYearEnd"),
        }

    @staticmethod
    def _recent_column(recent: Dict[str, Any], name: str,
                       accession: str) -> Optional[str]:
        """One value of a `filings.recent` column, addressed by accession.

        `filings.recent` is a column-major structure, so the accession's position
        in one array is its position in all of them. A shorter column means the
        payload is truncated and the value is simply not available -- which is an
        absence, not a zero.
        """
        values = recent.get(name) or []
        accessions = recent.get("accessionNumber") or []
        try:
            position = accessions.index(accession)
        except ValueError:
            return None
        if position >= len(values):
            return None
        value = values[position]
        return None if value is None else str(value)

    def _acquire_filing_provenance(
        self,
        asset_id: str,
        index: List[Dict[str, Any]],
        submission: Dict[str, Any],
    ) -> None:
        """
        Record what the submissions index says about the filings it lists.

        Order follows the foreign keys: the filing exists before anything
        references it, an item declaration exists before its items, and the
        acceptance declaration comes last. Every write is idempotent, so this
        method is safe to call on every run.
        """
        recent = submission["recent"]

        # Whatever earlier runs put in the ingestion ledger, projected onto the
        # relations that can say so properly. This runs before the index below so
        # that an archive created before 0020 gains filing identity at all.
        try:
            project_held_filings(self.store)
        except Exception as error:  # noqa: BLE001
            self._record_provenance_failure("held_filings_projection", error)

        for entry in index:
            accession = str(entry.get("accession") or "")
            if not accession:
                continue
            try:
                self._acquire_one_filing(
                    asset_id, accession, entry, recent, submission
                )
            except Exception as error:  # noqa: BLE001
                self._record_provenance_failure(f"filing:{accession}", error)

    def _acquire_one_filing(
        self,
        asset_id: str,
        accession: str,
        entry: Dict[str, Any],
        recent: Dict[str, Any],
        submission: Dict[str, Any],
    ) -> None:
        """One filing, from the submissions index."""
        self.store.record_filing(asset_id, accession, utc_now())

        # What the index declares about the filing. `report_date` here is EDGAR's
        # own reportDate column, which is a filing attribute; it is NOT
        # `held_filings.report_date`, which this same archive fills with an XBRL
        # fiscal year. The two are unrelated values that share a name.
        self.store.record_filing_declaration(
            filing_declaration_id(
                asset_id, accession, self.SUBMISSIONS_INDEX,
                form=entry.get("form") or None,
                filing_date=entry.get("filing_date") or None,
                report_date=entry.get("report_date") or None,
                primary_document=entry.get("primary_document") or None,
                is_xbrl=1 if entry.get("is_xbrl") in (1, "1", True) else 0,
            ),
            asset_id, accession, self.SUBMISSIONS_INDEX, utc_now(),
            "FIRST_HAND",
            form=entry.get("form") or None,
            filing_date=entry.get("filing_date") or None,
            report_date=entry.get("report_date") or None,
            primary_document=entry.get("primary_document") or None,
            is_xbrl=1 if entry.get("is_xbrl") in (1, "1", True) else 0,
        )

        self._acquire_filing_items(asset_id, accession, recent)

        # Acceptance, only when the index declared an *instant*.
        #
        # A `PRECISION_DATE` value here is not a weaker EDGAR acceptance; on the
        # bootstrap path it is a fact's own `filed` date (`sec_bulk
        # ._derived_filing_index`), which is a different claim about a different
        # object and already lives on the observation as `FILED_AS_OF_DATE`.
        # Recording it here would turn a filed-date fallback into filing-level
        # provenance, so the declared precision is what decides, and a date is
        # simply not recorded.
        if str(entry.get("acceptance_precision") or "") == PRECISION_INSTANT:
            # `raw` is what the resource served and `value` is what it declared;
            # they differ when the resource served an empty string, and both are
            # kept so the negative observation stays auditable. `None` means the
            # producer declared nothing; `raw_value = ''` means it was asked and
            # answered with nothing.
            raw = str(entry.get("acceptance_datetime") or "")
            value = raw or None
            precision = PRECISION_INSTANT if value else "NONE"
            self.store.record_filing_acceptance(
                filing_acceptance_id(
                    asset_id, accession, self.SUBMISSIONS_ACCEPTANCE,
                    value, precision, raw,
                ),
                asset_id, accession, self.SUBMISSIONS_ACCEPTANCE, precision,
                utc_now(), "FIRST_HAND",
                acceptance_datetime=value, raw_value=raw,
            )

    def _acquire_filing_items(
        self,
        asset_id: str,
        accession: str,
        recent: Dict[str, Any],
    ) -> None:
        """
        Record the sections a filing declares, from `filings.recent.items`.

        The raw string is stored unsplit and the items are parsed from it, so a
        changed parse cannot silently discard an item and a reader can always see
        what the source actually wrote. A filing that declares no item produces no
        declaration at all -- EDGAR writes an empty string rather than omitting the
        column, and an empty string is an absence, not a declaration of nothing.
        """
        raw = self._recent_column(recent, "items", accession)
        if not raw or not raw.strip():
            return
        declaration = self.store.record_filing_item_declaration(
            filing_item_declaration_id(
                asset_id, accession, self.SUBMISSIONS_ITEMS, raw
            ),
            asset_id, accession, self.SUBMISSIONS_ITEMS, raw, utc_now(),
            "FIRST_HAND",
            declared_item_count=len(parse_items(raw)),
        )
        for ordinal, code in parse_items(raw):
            self.store.record_filing_item(
                filing_item_id(declaration, ordinal, code), declaration, ordinal,
                code, utc_now(),
            )

    def _acquire_fiscal_calendar(self, asset_id: str, submission: Dict[str, Any]
                                 ) -> None:
        """
        Record the issuer's declared fiscal year end.

        The raw four-character form, never a month and never a fiscal year. The
        value is a date anchor, not a month: one filer declared `0929` in a 2013
        filing and `0926` in a 2026 one, so reducing either to a month integer
        would lose the drift. Which declaration applies to which fiscal year is
        Contract section K.4 and it stays open, which is why this records a
        declaration and nothing else.
        """
        raw = submission.get("fiscalYearEnd")
        if not raw or not re.fullmatch(r"\d{4}", str(raw)):
            return
        self.store.record_fiscal_calendar_declaration(
            fiscal_calendar_declaration_id(
                asset_id, str(raw), self.SUBMISSIONS_FISCAL_YEAR_END
            ),
            asset_id, str(raw), self.SUBMISSIONS_FISCAL_YEAR_END, utc_now(),
            "FIRST_HAND",
        )

    def _record_fact_filing_provenance(
        self,
        asset_id: str,
        accession: str,
        entry: Dict[str, Any],
    ) -> None:
        """
        Record what an individual fact says about the filing it came from.

        Needed for the accessions the submissions index never lists: that index is
        bounded to roughly the most recent thousand filings per filer while the
        XBRL concept endpoint reaches much further back, so a fact can name an
        accession no index will ever mention. For those, the fact is the only
        source that has spoken about the filing at all.

        Only `form` and `filed` are taken. The fact's `end` is the period the fact
        *covers*, which is not a filing attribute, so `report_date` stays unset:
        this archive's `held_filings.report_date` stores an XBRL fiscal year for
        exactly this column, and nothing here is allowed to repeat that.
        """
        form = str(entry.get("form") or "").strip() or None
        filed = str(entry.get("filed") or "").strip() or None
        if not form and not filed:
            return
        self.store.record_filing(asset_id, accession, utc_now())
        self.store.record_filing_declaration(
            filing_declaration_id(
                asset_id, accession, self.FACT_RECORD, form=form,
                filing_date=filed,
            ),
            asset_id, accession, self.FACT_RECORD, utc_now(), "FIRST_HAND",
            form=form, filing_date=filed,
        )

    # -- provenance: filing manifests (0020, Phase 2B) -----------------
    #
    # Two acquisitions, kept apart on purpose.
    #
    #   B1  the filing's directory listing, which is the only resource that
    #       enumerates a filing's files and the only one whose filenames are a
    #       filesystem identity within that filing
    #   B2  the full submission, which is the only resource that names the SEC
    #       `<TYPE>` of each document and carries the filing's SGML header
    #
    # They are separate requests, separate parses and separate write phases, and
    # they commit independently. A filing whose submission is unreadable still
    # has its directory and its documents; a filing whose directory is unreadable
    # still has its header. Merging them into one operation would mean a single
    # 404 throws away whichever answer did arrive.
    #
    # **No document bytes are fetched here.** An individual document is not
    # requested, its content is not read, and `filing_document_captures` and
    # `filing_document_statements` stay empty. A filename from either manifest is
    # a declaration that such a document exists, not a copy of it.

    MANIFEST_DIRECTORY = "EDGAR_FILING_DIRECTORY_INDEX_JSON"
    MANIFEST_SUBMISSION = "EDGAR_FULL_SUBMISSION_TEXT"
    SGML_FILING_DECLARATION = "SGML_SUBMISSION_HEADER"
    SGML_ITEMS = "SGML_ITEM_INFORMATION"
    SGML_ACCEPTANCE = "SGML_HEADER_ACCEPTANCE_DATETIME"
    SGML_FISCAL_YEAR_END = "SGML_HEADER_FISCAL_YEAR_END"

    def _acquire_filing_manifests(
        self,
        asset_id: str,
        cik: str,
        index: List[Dict[str, Any]],
    ) -> None:
        """Run B1 and B2 for every accession the index listed."""
        for entry in index:
            accession = str(entry.get("accession") or "")
            if not accession:
                continue
            # B1 and B2 are independent, so a failure in one is not allowed to
            # stop the other. Each writes only after its own fetch has parsed.
            for unit, acquire in (
                ("directory", self._acquire_filing_directory),
                ("submission", self._acquire_full_submission),
            ):
                try:
                    acquire(asset_id, cik, accession)
                except Exception as error:  # noqa: BLE001
                    self._record_provenance_failure(f"{unit}:{accession}",
                                                     error)

    def _acquire_filing_directory(
        self,
        asset_id: str,
        cik: str,
        accession: str,
    ) -> None:
        """
        B1: read one filing's directory listing and record what it declares.

        Every entry becomes a declaration in EDGAR's own order. `sec_document_type`
        is left unset, because `index.json` does not publish one -- its `type` is
        a MIME type such as `text.gif`, and this is the place where confusing the
        two would let a MIME string be read as an exhibit name.

        Filing identities are minted here and only here, and only for a filename
        the listing declared exactly once. A filename declared twice leaves both
        declarations standing and mints nothing: an unresolved document is a
        truthful state, and one identity row standing for two would be a merge
        that nothing in the data supports.
        """
        if not hasattr(self.provider, "filing_directory"):
            return
        directory = self.provider.filing_directory(cik, accession)
        if directory is None:
            return
        self.store.record_filing(asset_id, accession, utc_now())
        declared_at = utc_now()
        for entry in directory.entries:
            self.store.record_filing_document_declaration(
                filing_document_declaration_id(
                    asset_id, accession, self.MANIFEST_DIRECTORY,
                    entry.source_ordinal, entry.filename,
                    mime_type=entry.mime_type, byte_size=entry.byte_size,
                ),
                asset_id, accession, self.MANIFEST_DIRECTORY,
                entry.source_ordinal, declared_at, "FIRST_HAND",
                filename=entry.filename, mime_type=entry.mime_type,
                byte_size=entry.byte_size, last_modified=entry.last_modified,
            )
        self._mint_filing_documents(
            asset_id, accession, directory.entries, declared_at
        )

    def _mint_filing_documents(
        self,
        asset_id: str,
        accession: str,
        entries: Any,
        declared_at: str,
    ) -> None:
        """
        Mint one identity per filename the directory listing declared once.

        A filename appearing more than once is counted before anything is
        written, and the count is what decides: the database trigger refuses an
        ambiguous identity too, but a refusal there would abort the whole
        declaration phase, whereas here the duplicate is skipped, reported, and
        every other document in the filing is still recorded.
        """
        names = [entry.filename for entry in entries if entry.filename]
        for name in sorted(set(names)):
            if names.count(name) > 1:
                self._record_provenance_failure(
                    f"duplicate_filename:{accession}:{name}",
                    ValueError(
                        "the directory listing declared this filename more"
                        " than once, so no document identity was minted; the"
                        " declarations are kept and the document is unresolved"
                    ),
                )
                continue
            self.store.record_filing_document(
                asset_id, accession, name, declared_at
            )

    def _acquire_full_submission(
        self,
        asset_id: str,
        cik: str,
        accession: str,
    ) -> None:
        """
        B2: read one filing's full submission and record its header and documents.

        The header's declarations and the document sequence are written from one
        response, so they are consistent with each other. Neither mints a filing
        document identity and neither captures bytes.
        """
        if not hasattr(self.provider, "full_submission"):
            return
        submission = self.provider.full_submission(cik, accession)
        if submission is None:
            return
        self.store.record_filing(asset_id, accession, utc_now())
        declared_at = utc_now()
        self._record_sgml_documents(asset_id, accession, submission, declared_at)
        self._record_sgml_header(asset_id, cik, accession, submission.header,
                                 declared_at)

    def _record_sgml_documents(
        self,
        asset_id: str,
        accession: str,
        submission: Any,
        declared_at: str,
    ) -> None:
        """
        One declaration per `<DOCUMENT>` block, in the submission's own order.

        The same `<TYPE>XML</TYPE>` repeats -- one filing carried 62 of them --
        so neither the type nor the position can be an identity, and a block with
        no `<FILENAME>` is recorded with the filename absent rather than skipped.
        Nothing here creates a document identity: this sequence says what the
        filing declared, and identity is minted from the directory listing.
        """
        for document in submission.documents:
            self.store.record_filing_document_declaration(
                filing_document_declaration_id(
                    asset_id, accession, self.MANIFEST_SUBMISSION,
                    document.source_ordinal, document.filename,
                    sec_document_type=document.sec_document_type,
                    description=document.description,
                ),
                asset_id, accession, self.MANIFEST_SUBMISSION,
                document.source_ordinal, declared_at, "FIRST_HAND",
                filename=document.filename,
                sec_document_type=document.sec_document_type,
                description=document.description,
            )

    def _record_sgml_header(
        self,
        asset_id: str,
        cik: str,
        accession: str,
        header: Any,
        declared_at: str,
    ) -> None:
        """
        The header's own assertions, each under its own producer.

        `form` and `conformed_period_of_report` are the header's declarations and
        belong to `SGML_SUBMISSION_HEADER`; they do not amend what the submissions
        index said, because two sources disagreeing is a fact worth keeping and
        silently preferring one is not.

        `FILED AS OF DATE` is deliberately absent here. It is the day the filing
        was accepted for dissemination, which is a filing attribute, and it is not
        an acceptance *instant*: only `ACCEPTANCE-DATETIME` is, and that is the
        only header field that reaches `filing_acceptances`.

        The item titles are recorded as one declaration and no per-item rows are
        written. `filing_items.item_code` is NOT NULL, and the SGML header names
        its items rather than coding them -- storing a title in a column named
        `code` would be the MIME-versus-SEC-type confusion one layer up. The
        declaration keeps the titles verbatim, so nothing is lost and the join can
        be completed once the schema question is decided.
        """
        self.store.record_filing_declaration(
            filing_declaration_id(
                asset_id, accession, self.SGML_FILING_DECLARATION,
                form=header.conformed_submission_type,
                filing_date=header.filed_as_of_date,
                report_date=header.conformed_period_of_report,
                conformed_period_of_report=header.conformed_period_of_report,
                public_document_count=header.public_document_count,
            ),
            asset_id, accession, self.SGML_FILING_DECLARATION, declared_at,
            "FIRST_HAND",
            form=header.conformed_submission_type,
            filing_date=header.filed_as_of_date,
            report_date=header.conformed_period_of_report,
            conformed_period_of_report=header.conformed_period_of_report,
            public_document_count=header.public_document_count,
        )

        if header.acceptance_datetime:
            self.store.record_filing_acceptance(
                filing_acceptance_id(
                    asset_id, accession, self.SGML_ACCEPTANCE,
                    header.acceptance_datetime, "INSTANT",
                    header.acceptance_datetime,
                ),
                asset_id, accession, self.SGML_ACCEPTANCE, "INSTANT",
                declared_at, "FIRST_HAND",
                acceptance_datetime=header.acceptance_datetime,
                raw_value=header.acceptance_datetime,
            )

        if header.item_information:
            raw = "\n".join(header.item_information)
            self.store.record_filing_item_declaration(
                filing_item_declaration_id(
                    asset_id, accession, self.SGML_ITEMS, raw
                ),
                asset_id, accession, self.SGML_ITEMS, raw, declared_at,
                "FIRST_HAND", declared_item_count=header.item_information_count,
            )

        fiscal = header.fiscal_year_end
        if fiscal and re.fullmatch(r"\d{4}", fiscal):
            self.store.record_fiscal_calendar_declaration(
                fiscal_calendar_declaration_id(
                    asset_id, fiscal, self.SGML_FISCAL_YEAR_END, accession
                ),
                asset_id, fiscal, self.SGML_FISCAL_YEAR_END, declared_at,
                "FIRST_HAND", declaring_accession=accession,
            )

    # -- provenance: document bytes (0020, Phase 3A) --------------------
    #
    # The chain, in the only order that is honest:
    #
    #     filing_documents            identity: this filename is a document of
    #                                 this filing
    #       -> filing_document_captures   a specific byte sequence was captured
    #            for it, at a specific time, under a stated capture kind
    #              -> source_documents    the bytes themselves, content-addressed
    #
    # Nothing in this chain is inferred from an accession. A capture row exists
    # only because a fetch returned bytes and those bytes were hashed.

    DOCUMENT_ACQUISITION_CLASS = "SEC_FILING_DOCUMENT"

    def _acquire_document_bytes(
        self,
        asset_id: str,
        cik: str,
        index: List[Dict[str, Any]],
        first_seen: frozenset,
    ) -> None:
        """
        Fetch the bytes of every eligible document of every listed filing.

        `first_seen` is the set of accessions this run saw for the first time --
        those already in `held_filings` when the run began. It is the only
        evidence available for whether a capture is first-hand, and it is why
        `capture_kind` is derived from it rather than asserted: a run that
        already held a filing did not first discover it, so bytes it fetches now
        are a later acquisition and are labelled as one.
        """
        if not hasattr(self.provider, "filing_document"):
            return
        for entry in index:
            accession = str(entry.get("accession") or "")
            if not accession:
                continue
            try:
                self._acquire_documents_for_filing(
                    asset_id, cik, accession,
                    "FIRST_HAND" if accession in first_seen
                    else "LATER_ACQUISITION",
                )
            except Exception as error:  # noqa: BLE001
                self._record_provenance_failure(f"document_bytes:{accession}",
                                                 error)

    def _eligible_document_filenames(
        self,
        asset_id: str,
        accession: str,
    ) -> List[str]:
        """
        Filenames both manifests agree this filing contains.

        Two independent resources are required, and that is the whole rule. The
        directory listing enumerates the filing's files; the submission's
        `<DOCUMENT>` sequence says which of them EDGAR publishes as documents.
        A filename only one of them names is not corroborated, and the measured
        difference is exactly EDGAR's own transmission products -- the two index
        pages and the full submission text. An accession, or a listing entry, is
        never sufficient on its own.
        """
        corroborated = {
            row["filename"] for row in self.connection.execute(
                "SELECT filename FROM filing_document_declarations"
                " WHERE asset_id = ? AND accession = ? AND manifest_source = ?"
                " AND filename IS NOT NULL",
                (asset_id, accession, self.MANIFEST_SUBMISSION),
            )
        }
        if not corroborated:
            # No submission was read for this filing, so nothing is corroborated
            # and nothing is eligible. Absence of one manifest is not permission
            # to fetch on the word of the other.
            return []
        declared = [
            row["filename"] for row in self.connection.execute(
                "SELECT filename FROM filing_documents"
                " WHERE asset_id = ? AND accession = ? ORDER BY filename",
                (asset_id, accession),
            )
        ]
        return [name for name in declared if name in corroborated]

    def _document_needs_refetch(self, asset_id: str, accession: str,
                                filename: str) -> bool:
        """
        Whether this document's bytes are not already held.

        A capture row for a filename means its bytes are stored, and a filed
        document does not change under its own accession -- a changed document
        arrives as an amendment under a new accession, which is a different
        filing entirely. So re-fetching every document of every held filing on
        every run would spend the whole request budget re-reading immutable
        bytes. A document is re-fetched only when its directory declaration has
        moved on, which is the one case where the archive has reason to look
        again.
        """
        captured = self.connection.execute(
            "SELECT MAX(captured_at) AS captured_at FROM"
            " filing_document_captures"
            " WHERE asset_id = ? AND accession = ? AND filename = ?",
            (asset_id, accession, filename),
        ).fetchone()
        if captured is None or captured["captured_at"] is None:
            return True
        latest = self.connection.execute(
            "SELECT declaration_id, captured_at FROM"
            " filing_document_declarations"
            " WHERE asset_id = ? AND accession = ? AND filename = ?"
            " AND manifest_source = ?"
            " ORDER BY captured_at DESC, declaration_id DESC LIMIT 1",
            (asset_id, accession, filename, self.MANIFEST_DIRECTORY),
        ).fetchone()
        if latest is None:
            return True
        return latest["captured_at"] > captured["captured_at"]

    def _acquire_documents_for_filing(
        self,
        asset_id: str,
        cik: str,
        accession: str,
        capture_kind: str,
    ) -> int:
        """
        Fetch and store every eligible document of one filing.

        One document failing does not stop the others. The listing is walked in a
        stable order and each fetch is isolated, because a single document the
        server will not serve would otherwise strand every document after it,
        and a filing's capture state would depend on alphabetical order.
        """
        stored = 0
        for filename in self._eligible_document_filenames(asset_id, accession):
            try:
                captured = self._acquire_one_document(
                    asset_id, cik, accession, filename, capture_kind
                )
            except Exception as error:  # noqa: BLE001
                self._record_provenance_failure(
                    f"document:{accession}:{filename}", error
                )
                continue
            if captured:
                stored += 1
        return stored

    def _acquire_one_document(
        self,
        asset_id: str,
        cik: str,
        accession: str,
        filename: str,
        capture_kind: str,
    ) -> bool:
        """Fetch one document and link the bytes it returned. True if newly stored."""
        if not self._document_needs_refetch(asset_id, accession, filename):
            return False
        fetched = self.provider.filing_document(cik, accession, filename)
        if fetched is None:
            # A document the directory listed and the submission named, that the
            # server will not serve. Its declarations stand; it simply has no
            # bytes, and the absence of a capture row says so.
            return False
        document_id = self.store.record_source_document(StoredDocument(
            content_hash=fetched.content_hash,
            uri=fetched.uri,
            canonical_uri=fetched.canonical_uri,
            http_status=fetched.http_status,
            media_type=fetched.media_type,
            byte_size=fetched.byte_size,
            fetched_at=fetched.fetched_at,
            first_seen_at=fetched.fetched_at,
            payload=fetched.content,
            provider=SEC_SOURCE,
            document_type=DOCUMENT_FILING,
        ))
        return self.store.record_filing_document_capture(
            asset_id, accession, filename, document_id,
            self.DOCUMENT_ACQUISITION_CLASS, fetched.fetched_at, capture_kind,
        )

    # -- provenance: document statements (0020, Phase 3B) -------------
    #
    # The whole chain, and the order it can only be built in:
    #
    #     filing_documents            the document is part of the filing
    #       -> filing_document_captures   a specific byte sequence was captured
    #            -> source_documents       the bytes, content-addressed
    #              -> filing_document_statements  a quotation read out of them
    #
    # A statement is the last link and the only one that can be manufactured from
    # nothing. Every other link is a fact about a fetch. So a statement exists
    # only when the bytes it quotes were actually captured, and it names the
    # capture it was read from -- `filing_document_statements` has a composite
    # foreign key onto `filing_document_captures`, so a statement cannot float
    # free of the bytes behind it even if a caller tries.

    STATEMENT_SECTION_18 = "SECTION_18_NOT_DEEMED_FILED"
    STATEMENT_METHOD_VERBATIM = "DECLARED_VERBATIM_QUOTE"

    def _acquire_document_statements(
        self,
        asset_id: str,
        accession: str,
    ) -> int:
        """
        Read Section 18 statements out of the bytes this archive already holds.

        Only the filing's **primary document** is read, and which document that
        is comes from the submission manifest rather than from a filename
        pattern: the first `<DOCUMENT>` the filing declares. That is where the
        language was empirically observed, and it is why an exhibit is never
        substituted here -- an EX-99.1 carries the results, not the statement
        about their status, and this phase refuses to go looking for the second
        in the first.

        Nothing is fetched. A document with no capture has no bytes and
        therefore yields no statement; the absence is the record.
        """
        primary = self._primary_document_filename(asset_id, accession)
        if primary is None:
            return 0
        captures = [
            dict(row) for row in self.connection.execute(
                "SELECT document_id, captured_at, capture_kind FROM"
                " filing_document_captures WHERE asset_id = ? AND accession = ?"
                " AND filename = ? ORDER BY captured_at, document_id",
                (asset_id, accession, primary),
            )
        ]
        stored = 0
        for capture in captures:
            try:
                stored += self._record_statement_from_capture(
                    asset_id, accession, primary, capture
                )
            except Exception as error:  # noqa: BLE001
                self._record_provenance_failure(
                    f"statement:{accession}:{primary}:"
                    f"{capture['document_id']}",
                    error,
                )
        return stored

    def _acquire_document_fact_occurrences(
        self,
        asset_id: str,
        accession: str,
    ) -> int:
        """
        Read XBRL facts out of the bytes this archive already holds.

        Unlike the statement pass above, this reads **every** captured document
        of the filing rather than only the primary one. A fact is asserted
        wherever it is asserted: a legacy `EX-101.INS` may be the only document
        carrying diluted EPS while the `EX-99.1` carries none, and the primary
        HTML of an 8-K may carry nothing at all.

        It also reads *each* document independently and writes an occurrence per
        document that holds the fact. When the same fact appears in both a filed
        primary document and an EDGAR-generated `_htm.xml`, two occurrences are
        the truth: current evidence cannot decide which of them is authoritative
        (invariant 19), and this phase refuses to decide it. Nothing here writes
        an `observation_filing_documents` row, so no exact-source assertion is
        implied by the existence of occurrences.

        Nothing is fetched. A document with no capture has no bytes and
        therefore yields no occurrence; the absence is the record.
        """
        captures = self.connection.execute(
            "SELECT filename, document_id, captured_at, capture_kind FROM"
            " filing_document_captures WHERE asset_id = ? AND accession = ?"
            " ORDER BY filename, captured_at, document_id",
            (asset_id, accession),
        ).fetchall()
        stored = 0
        for capture in captures:
            try:
                stored += self._record_fact_occurrences_from_capture(
                    asset_id, accession, dict(capture)
                )
            except Exception as error:  # noqa: BLE001
                self._record_provenance_failure(
                    f"fact_occurrence:{accession}:{capture['filename']}:"
                    f"{capture['document_id']}",
                    error,
                )
        return stored

    def _record_fact_occurrences_from_capture(
        self,
        asset_id: str,
        accession: str,
        capture: Dict[str, Any],
    ) -> int:
        """Parse one capture's bytes and persist the facts they actually assert."""
        document_id = capture["document_id"]
        row = self.connection.execute(
            "SELECT content_hash FROM source_documents WHERE document_id = ?",
            (document_id,),
        ).fetchone()
        if row is None:
            return 0
        payload = self.store.content_for(row["content_hash"])
        if payload is None:
            # Captured as a reference rather than as content: the capture row
            # stands and there are simply no bytes to read.
            return 0

        parsed = parse_xbrl_document(payload)
        for rejection in parsed.rejections:
            # Run-level only (ADR Amendment 0 §3 item 7): an absent occurrence
            # and a never-attempted read must be distinguishable, and this is
            # where that distinction is recorded. Nothing is written to any
            # table for a rejection, and nothing is inferred in its place.
            self._record_provenance_failure(
                f"fact_rejection:{accession}:{capture['filename']}:"
                f"{document_id}:{rejection.taxonomy}:{rejection.tag}:"
                f"{rejection.context_ref or '-'}:{rejection.reason}",
                XbrlParseError(rejection.reason),
            )

        stored = 0
        for fact in parsed.facts:
            occurrence_id = document_fact_id(
                SEC_SOURCE, asset_id, accession, document_id,
                fact.taxonomy, fact.tag, fact.context_ref, fact.unit_ref,
            )
            self.store.record_filing_document_fact_occurrence(
                document_fact_id=occurrence_id,
                document_fact_identity=document_fact_identity(
                    SEC_SOURCE, asset_id, accession, document_id,
                    fact.taxonomy, fact.tag, fact.context_ref, fact.unit_ref,
                ),
                asset_id=asset_id,
                accession=accession,
                filename=capture["filename"],
                document_id=document_id,
                provider=SEC_SOURCE,
                taxonomy=fact.taxonomy,
                tag=fact.tag,
                context_ref=fact.context_ref,
                unit_ref=fact.unit_ref,
                entity_identifier=parsed.contexts[
                    fact.context_ref].entity_identifier,
                entity_scheme=parsed.contexts[
                    fact.context_ref].entity_scheme,
                period_kind=parsed.contexts[fact.context_ref].period_kind,
                period_start=parsed.contexts[fact.context_ref].period_start,
                period_end=parsed.contexts[fact.context_ref].period_end,
                dimensions_json=parsed.dimensions_json(fact.context_ref),
                unit_measures_json=parsed.unit_measures_json(fact.unit_ref),
                value_text=fact.value_text,
                resolved_value=fact.resolved_value,
                sign=fact.sign,
                scale=fact.scale,
                format_=fact.format_,
                decimals=fact.decimals,
                language=fact.language,
                locators_json=parsed.locators_json(fact),
                context_locator_json=parsed.context_locator_json(
                    fact.context_ref),
                unit_locator_json=parsed.unit_locator_json(fact.unit_ref),
                captured_at=capture["captured_at"],
                capture_kind=capture["capture_kind"],
            )
            stored += 1
        return stored

    def _primary_document_filename(
        self,
        asset_id: str,
        accession: str,
    ) -> Optional[str]:
        """
        The filing's own first document, as its submission declares it.

        The SGML manifest's first `<DOCUMENT>` is the primary document; this is
        the submission's statement about its own contents, not a guess from a
        name. A filing whose submission was never read has no such declaration
        and nothing is attempted.
        """
        row = self.connection.execute(
            "SELECT filename FROM filing_document_declarations"
            " WHERE asset_id = ? AND accession = ? AND manifest_source = ?"
            " AND source_ordinal = 1 AND filename IS NOT NULL"
            " ORDER BY declaration_id LIMIT 1",
            (asset_id, accession, self.MANIFEST_SUBMISSION),
        ).fetchone()
        return None if row is None else row["filename"]

    def _record_statement_from_capture(
        self,
        asset_id: str,
        accession: str,
        filename: str,
        capture: Dict[str, Any],
    ) -> int:
        """Extract from one capture's bytes and persist what was actually found."""
        content_hash = self.connection.execute(
            "SELECT content_hash FROM source_documents WHERE document_id = ?",
            (capture["document_id"],),
        ).fetchone()
        if content_hash is None:
            return 0
        payload = self.store.content_for(content_hash["content_hash"])
        if payload is None:
            # Captured as a reference rather than as content. The capture row
            # stands; there are simply no bytes to quote, and a statement is not
            # written from the existence of a fetch.
            return 0
        statement = extract_section18_statement(payload)
        if statement is None:
            return 0
        statement_id = filing_document_statement_id(
            asset_id, accession, filename, capture["document_id"],
            self.STATEMENT_SECTION_18, statement.quote_locator,
        )
        existing = self.connection.execute(
            "SELECT quote_text, extraction_method FROM"
            " filing_document_statements WHERE statement_id = ?",
            (statement_id,),
        ).fetchone()
        if existing is not None and (
            existing["quote_text"] == statement.quote_text
            and existing["extraction_method"] == self.STATEMENT_METHOD_VERBATIM
        ):
            return 0
        self.store.record_filing_document_statement(
            statement_id,
            filing_document_statement_identity(
                asset_id, accession, filename, capture["document_id"],
                self.STATEMENT_SECTION_18, statement.quote_locator,
            ),
            asset_id, accession, filename, capture["document_id"],
            self.STATEMENT_SECTION_18, statement.quote_locator,
            statement.quote_text, self.STATEMENT_METHOD_VERBATIM,
            utc_now(), capture["capture_kind"],
            # The document this statement governs is not derivable from the bytes
            # alone, and is deliberately left unstated rather than inferred --
            # see the Constitution's invariant 19.
            applies_to_document_type=None,
            applies_to_filing_item_code=statement.applies_to_filing_item_code,
        )
        return 1

    def _store_facts(
        self,
        cik: str,
        asset_id: str,
        ticker: str,
        metric: str,
        taxonomy: str,
        concept: str,
        mapping: Any,
        payload: Dict[str, Any],
        document_id: str,
        acceptance: Dict[str, Optional[str]],
        report: IngestionReport,
    ) -> int:
        """
        Append every fact of this concept, deduplicating per source document.

        The identity is the fact's position in the filing, not its value. Two
        filings reporting the same number are two facts, and a fact reported by
        two adapters is one.
        """
        document_hash = ""
        if document_id:
            row = self.connection.execute(
                "SELECT content_hash FROM source_documents WHERE document_id = ?",
                (document_id,),
            ).fetchone()
            document_hash = row["content_hash"] if row else ""

        seen_periods: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        stored = 0

        for unit, entries in (payload.get("units") or {}).items():
            for entry in entries:
                if not is_number(entry.get("val")) or not entry.get("end"):
                    continue
                period_start = entry.get("start")
                period_end = str(entry["end"])
                accession = str(entry.get("accn") or "")
                if asset_id:
                    self._ensure_filing_identity(asset_id, accession, entry)

                # The submissions index only carries recent filings, so an older
                # accession has no acceptance timestamp there. `_availability_for`
                # then falls back to the fact's own `filed` date -- at the
                # precision the fact declares, which is a date, not an instant.
                available_at, available_basis, available_precision = (
                    self._availability_for(entry, acceptance)
                )

                # An aggregated endpoint hides dimension members, so two facts
                # can arrive looking identical. A differing value for the same
                # concept, period and unit is the signature of that.
                #
                # Counted, and now *persisted with the metric, the concept, the
                # filing and the period attached* -- 2.21. The count used to be
                # per run and per issuer, which is useless at the moment it
                # matters: deciding whether a bank reports a gross profit is a
                # question about a metric, and the number that would answer it
                # was filed a level above the question. It is also recorded per
                # distinct value rather than per event, so six members of one
                # period count as one row with `distinct_values = 6` rather than
                # as five rows that look like five separate ambiguities.
                #
                # Restatements are told apart from hidden members, because the
                # two call for opposite responses and look identical otherwise:
                # the same member restated across two accessions is ordinary, and
                # a filer revising last year's figure is not a fact whose
                # meaning is in doubt.
                collision_key = (str(period_start or ""), period_end, unit)
                values: Dict[str, Dict[str, Any]] = seen_periods.setdefault(
                    collision_key,
                    {"by_accession": {}, "all": set()},
                )
                by_accession: Dict[str, set] = values["by_accession"]
                distinct: set = values["all"]
                fact_value = float(entry["val"])
                filing = accession or ""
                by_accession.setdefault(filing, set()).add(fact_value)
                if distinct and fact_value not in distinct:
                    report.dimension_collisions += 1
                    # Which of two things this is, decided by what the evidence
                    # supports rather than by what would be reassuring. If one
                    # filing reported two values for one period, a member was
                    # hidden and that is provable from this source. If each filing
                    # reported one and they disagree, all that can be said is
                    # that a later filing reports something different.
                    #
                    # It was tempting to call the second case a restatement --
                    # ordinary, comparable, not an ambiguity. Measurement refused
                    # it: BBAR tags GrossProfit for 2019 as 88.8bn, 120.9bn and
                    # 182.5bn across three 20-F filings, and a restatement does
                    # not move a number by 36% then 51%. But the aggregated
                    # endpoint dropped the member axis before ingestion saw
                    # anything, so nothing here can tell a revision from two
                    # members. The kind therefore says what was seen.
                    member_hidden = any(
                        len(seen) > 1 for seen in by_accession.values()
                    )
                    self._record_dimension_collision(
                        asset_id=asset_id,
                        metric=metric,
                        concept=f"{taxonomy}:{concept}",
                        accession=accession,
                        period_start=str(period_start or ""),
                        period_end=period_end,
                        unit=unit,
                        distinct_values=len(distinct) + 1,
                        kind=(
                            "SAME_PERIOD_DIFFERENT_VALUE"
                            if member_hidden
                            else "LATER_FILING_DIFFERS"
                        ),
                    )
                distinct.add(fact_value)

                fact_id = source_fact_id(
                    source_id=SEC_SOURCE,
                    # The accession, not the document hash. The fact's document
                    # is the filing that contains it, and a filing's identity is
                    # its accession. The companyconcept endpoint is a rolling
                    # view over every filing that ever reported this concept, so
                    # its content hash changes the moment anything new is filed
                    # — anchoring identity to it would give the same historical
                    # fact a new id on the next run and re-append it.
                    document_ref=accession or document_hash,
                    taxonomy=taxonomy,
                    concept=concept,
                    period_start=period_start,
                    period_end=period_end,
                    context=accession,
                )
                if self._fact_held(fact_id):
                    report.source_facts_skipped += 1
                    report.observations_skipped += 1
                    continue

                observation = self._observation(
                    metric,
                    taxonomy,
                    concept,
                    mapping,
                    payload,
                    entry,
                    unit,
                    period_start,
                    period_end,
                    available_at,
                    available_basis,
                    available_precision,
                    accession,
                )
                self.store.record_observation(
                    # The ticker, not the asset_id. `record_observation`
                    # registers whatever it is handed, so passing the id here
                    # would silently create a second asset named after the id
                    # and file the evidence under it, where a query by ticker
                    # can never find it.
                    asset=ticker,
                    observation=observation,
                    availability_class="SOURCE_DECLARED",
                    document_hashes=[document_hash] if document_hash else [],
                    filing=self._filing(
                        fact_id,
                        taxonomy,
                        concept,
                        accession,
                        entry,
                        period_start,
                    ),
                )
                report.source_facts_stored += 1
                report.observations_stored += 1
                stored += 1

        return stored

    def _record_dimension_collision(
        self,
        asset_id: str,
        metric: str,
        concept: str,
        accession: str,
        period_start: str,
        period_end: str,
        unit: str,
        distinct_values: int,
        kind: str,
    ) -> None:
        """
        Buffer one dimension collision, at the grain a decision needs.

        Buffered rather than written, for the same reason the scope rows are: the
        row names a run and the run row is written at the end of the run, so
        writing here would insert a child before its parent. `_write_run` writes
        both in one transaction, which means a run cannot exist without its
        collisions and cannot have collisions without the run.

        Keyed on the collision rather than the run so a rerun over the same
        window replaces the row instead of accumulating a second identical one,
        while a rerun over a *wider* window adds rows -- which is the honest
        direction, because more filings means more chances to find a member that
        the first window had not reached.
        """
        if not self._current_run_id or not asset_id:
            return
        self._pending_collisions = getattr(
            self, "_pending_collisions", []
        )
        self._pending_collisions.append((
            self._current_run_id,
            asset_id,
            metric,
            concept,
            accession or None,
            period_start or None,
            period_end or None,
            unit or None,
            int(distinct_values),
            kind,
        ))

    def _fact_held(self, fact_id: str) -> bool:
        return (
            self.connection.execute(
                "SELECT 1 FROM observations WHERE source_fact_id = ?",
                (fact_id,),
            ).fetchone()
            is not None
        )

    def _observation(
        self,
        metric: str,
        taxonomy: str,
        concept: str,
        mapping: Any,
        payload: Dict[str, Any],
        entry: Dict[str, Any],
        unit: str,
        period_start: Optional[str],
        period_end: str,
        available_at: Optional[str],
        available_basis: str,
        available_precision: str,
        accession: str,
    ) -> Observation:
        contract_unit = xbrl_unit_to_contract_unit(unit) or Unit.RATIO.value
        # The source-declared currency, not a hardcoded `USD`. This line and the
        # `or Unit.RATIO.value` fallback above are the two halves of the defect
        # 2.52 measured: an unmapped unit took the fallback and lost its
        # currency, so a TWD or CAD or JPY fact was recorded as a ratio with no
        # currency and could not satisfy a currency-family metric.
        currency = observation_currency_of(unit)
        # The basis arrives as a declaration rather than being recovered from the
        # shape of the value. It used to be decided by asking whether the string
        # contained a `T`, which meant a filed-date fallback wearing a midnight
        # was recorded as an acceptance instant, and a bare date was recorded as
        # undeclared -- so the two delivery routes produced different
        # availability semantics for identical evidence.
        if available_at and available_basis not in AvailabilityBasis:
            raise ValueError(
                f"availability basis {available_basis!r} is not declared"
            )
        if available_at and available_precision not in PRECISIONS:
            raise ValueError(
                f"availability precision {available_precision!r} is not declared"
            )
        return Observation(
            observation_id=(
                f"ingest|{metric}|{concept}|{accession}"
                f"|{period_start or 'instant'}|{period_end}|{unit}"
            ),
            metric=metric,
            value=float(entry["val"]),
            unit=contract_unit,
            currency=currency,
            currency_basis="REPORTED" if currency else "NOT_APPLICABLE",
            period_start=period_start,
            period_end=period_end,
            as_of=period_end,
            available_at=available_at,
            available_at_basis=available_basis,
            provider=SEC_SOURCE,
            source_type=SEC_SOURCE_TYPE,
            source_url=None,
            definition=payload.get("description") or metric,
            methodology=(
                f"{taxonomy}:{concept} as filed in {entry.get('form')} "
                f"accession {accession}; registry mapping "
                f"{mapping.mapping_type}"
            ),
            retrieved_at=utc_now(),
            raw={
                "sec_fact": {
                    "taxonomy": taxonomy,
                    "tag": concept,
                    "accession": accession,
                    "form": entry.get("form"),
                    "fy": entry.get("fy"),
                    "fp": entry.get("fp"),
                    "frame": entry.get("frame"),
                    "filed": entry.get("filed"),
                    "label": payload.get("label"),
                },
                # What the source declared about *when*, kept next to the value
                # so a consumer can read the precision without re-deriving it
                # from the shape of a string -- which is the mistake 2.14
                # measured across the two delivery routes.
                "availability": {
                    "declared_value": available_at,
                    "declared_basis": available_basis,
                    "declared_precision": available_precision,
                },
                "mapping_type": mapping.mapping_type,
                "mapping_effective_from": mapping.effective_from,
                "mapping_effective_to": mapping.effective_to,
            },
            observation_count=None,
            status=ValidationStatus.UNVERIFIABLE,
            status_reasons=(
                "a single official source cannot cross-validate itself",
            ),
            basis={
                "reporting_framework": taxonomy,
                "security_type": "REGISTERED_SECURITY",
                "mapping_fidelity": mapping.mapping_type,
                "source_declared": True,
            },
        )

    def _filing(
        self,
        fact_id: str,
        taxonomy: str,
        concept: str,
        accession: str,
        fact: Dict[str, Any],
        period_start: Optional[str],
    ) -> FilingRef:
        """
        The filing identity that travels with the row.

        `source_concept` is qualified as `taxonomy:concept`. A vendor or
        view-derived observation legitimately has no filing concept, and says so
        with a null rather than borrowing a metric name; nothing here fabricates
        one. The legacy `concept` column is left to the archive, which already
        derives it from the preserved payload, because rewriting it would change
        what existing archives hold.
        """
        return FilingRef(
            accession=accession or None,
            form=fact.get("form"),
            taxonomy=taxonomy,
            fiscal_year=fact.get("fy"),
            fiscal_period=fact.get("fp"),
            statement=fact.get("statement"),
            instant=1 if period_start is None else 0,
            source_fact_id=fact_id,
            source_concept=f"{taxonomy}:{concept}",
        )
