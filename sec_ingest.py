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

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from archive import FilingRef, StoredDocument
from core_registry import CoreRegistry
from data_contract import (
    AvailabilityBasis,
    Observation,
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
        }


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
        cik = self._known_cik(ticker)
        if cik is None:
            company = self.provider.resolve_company(ticker)
            if company is None:
                raise ValueError(
                    f"{ticker} is not in the SEC company map; no CIK could "
                    "be resolved and no filing was inferred."
                )
            cik = company.cik
            name = company.name
        else:
            name = ticker.upper()

        asset_id = self.store.record_asset(ticker.upper(), cik=cik, name=name)
        report = IngestionReport(
            asset=ticker.upper(), cik=cik, run_id="run_" + uuid.uuid4().hex[:16]
        )

        index = self.provider.filing_index(cik)
        wanted = set(forms)
        relevant = [
            entry
            for entry in index
            if entry.get("form") in wanted
            and entry.get("is_xbrl") in (1, "1", True)
        ]
        report.filings_seen = len(relevant)
        acceptance = {
            entry["accession"]: entry.get("acceptance_datetime")
            for entry in index
        }

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
            self._count_fetches(report)
            self._write_run(asset_id, report, "NO_CHANGE")
            return report

        for metric in metrics:
            try:
                self._ingest_metric(
                    cik, ticker.upper(), metric, acceptance, report
                )
            except Exception as error:  # noqa: BLE001
                report.errors.append(f"{metric}: {type(error).__name__}: {error}")

        for entry in new_entries:
            self._record_filing(asset_id, entry, "")
        self.connection.commit()
        self._count_fetches(report)
        self._write_run(
            asset_id, report, "OK" if not report.errors else "PARTIAL"
        )
        return report

    def _count_fetches(self, report: IngestionReport) -> None:
        report.network_fetches = self.provider.network_fetches
        report.concept_fetches = self.provider.concept_fetches

    def _write_run(self, asset_id: str, report: IngestionReport, status: str) -> None:
        self.connection.execute(
            "INSERT INTO ingestion_runs (run_id, asset_id, source_id,"
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
        self.connection.commit()

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

    def _store_facts(
        self,
        cik: str,
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

        seen_periods: Dict[Tuple[str, str, str], float] = {}
        stored = 0

        for unit, entries in (payload.get("units") or {}).items():
            for entry in entries:
                if not is_number(entry.get("val")) or not entry.get("end"):
                    continue
                period_start = entry.get("start")
                period_end = str(entry["end"])
                accession = str(entry.get("accn") or "")

                # The submissions index only carries recent filings, so an older
                # accession has no acceptance timestamp there. The fact's own
                # `filed` date is the coarser provable answer, and it is the
                # same date the SEC published, so it is used with its own
                # basis rather than dropped.
                available_at = acceptance.get(accession)
                if not available_at and entry.get("filed"):
                    available_at = f"{entry['filed']}T00:00:00+00:00"

                # An aggregated endpoint hides dimension members, so two facts
                # can arrive looking identical. A differing value for the same
                # concept, period and unit is the signature of that, and it is
                # counted rather than silently overwritten.
                collision_key = (str(period_start or ""), period_end, unit)
                previous = seen_periods.get(collision_key)
                if previous is not None and previous != float(entry["val"]):
                    report.dimension_collisions += 1
                seen_periods[collision_key] = float(entry["val"])

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
        accession: str,
    ) -> Observation:
        contract_unit = xbrl_unit_to_contract_unit(unit) or Unit.RATIO.value
        currency = unit if unit in ("USD",) else None
        available_basis = (
            AvailabilityBasis.ACCEPTANCE_DATETIME.value
            if available_at and "T" in str(available_at)
            else AvailabilityBasis.UNDECLARED.value
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
                    "label": payload.get("label"),
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
