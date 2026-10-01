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
from evidence_model import source_fact_id
from sec_provider import xbrl_unit_to_contract_unit

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
        self._pending_scope: List[Tuple[str, str, str, int, int, str]] = []

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
            self._count_fetches(report)
            report.transport = self._transport_stats()
            report.elapsed_seconds = round(time.monotonic() - started, 3)
            self._write_run(asset_id, report, "NO_CHANGE")
            return report

        self._record_scope(asset_id, metrics, attempted=True)
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
                if report.observations_stored == before:
                    report.classify(
                        OUTCOME_SOURCE_SILENT, metric,
                        "asked, and the source reported no figure for it",
                    )

        for entry in new_entries:
            self._record_filing(asset_id, entry, "")
        self._record_adoption(asset_id)
        self.connection.commit()
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
                (row[0], row[1], row[2], row[3], row[4], 0, row[5]),
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
    ) -> None:
        """
        Write down what this run was asked to collect.

        `ingestion_runs` says what a run did and nothing about what it was for,
        so "this metric has no observations" has been a sentence with three
        meanings that all read the same. This is the record that separates them,
        and it is written on every run including the ones that ask nothing --
        an unattempted metric is the single most useful thing a coverage figure
        can report, because it is the only status that is a to-do item.

        The status is decided by whether the registry has a concept to ask with,
        not by whether anything came back. A metric with no declaration is
        `NO_MAPPING` and one with a declaration the source did not answer is
        `SOURCE_SILENT`, and the two call for completely different work.
        """
        run_id = self._current_run_id
        if not run_id:
            return
        # Buffered rather than written here. A scope row names a run, and the run
        # row is written at the end of the run, so writing now would insert a
        # child before its parent. `_write_run` writes both in one transaction,
        # which also means a run can never exist without its scope or vice
        # versa.
        self._pending_scope = getattr(self, "_pending_scope", [])
        for metric in metrics:
            mapping_count = len(self.registry.mappings_for_metric(metric))
            if not attempted:
                status = "NOT_ATTEMPTED"
            elif mapping_count == 0:
                status = "NO_MAPPING"
            elif self._metric_observed(metric, asset_id):
                status = "INGESTED"
            else:
                status = "SOURCE_SILENT"
            self._pending_scope.append(
                (run_id, asset_id, metric, mapping_count, int(attempted), status)
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
        currency = unit if unit in ("USD",) else None
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
