"""
SEC ingestion: reprocessing saved evidence without new filings.

These assertions exercise the backfill route: after a mapping is added or
changed, saved SEC concept documents already held in the archive must be able
to (re)produce the standard observations, with no network request, no duplicate
rows on repeat, and every gap reported explicitly. The formal SQLite database
is never touched -- every test uses an isolated in-memory store.
"""

from __future__ import annotations

import json
import unittest
from typing import Any, Dict, List, Optional, Tuple

from archive import StoredDocument
from core_registry import CoreRegistry, ConceptMapping, MAPPING_EXACT
from registry_seed import seed
from sec_ingest import DEFAULT_METRICS, SEC_SOURCE, Ingestor
from sqlite_archive import SQLiteArchive

TICKER = "AAPL"
CIK = "0000320193"
ACCESSION = "0000320193-26-000018"
EPS_PAYLOAD = {
    "cik": CIK, "taxonomy": "us-gaap", "tag": "EarningsPerShareDiluted",
    "label": "Diluted EPS",
    "units": {"USD/shares": [{
        "start": "2026-01-01", "end": "2026-03-28", "val": 1.65,
        "accn": ACCESSION, "fy": 2026, "fp": "Q2", "form": "10-Q",
        "filed": "2026-07-30",
    }]},
}
EPS_URI = (
    f"https://data.sec.gov/api/xbrl/companyconcept/CIK{CIK}"
    f"/us-gaap/EarningsPerShareDiluted.json"
)


class _NoFetchProvider:
    """A provider that fails loudly if any concept/fetching endpoint is
    reached. `submissions` is allowed because `ingest()` reads it for the
    issuer business model, but it returns nothing that triggers a fetch."""

    def __init__(self) -> None:
        self.calls: List[str] = []

    def resolve_company(self, ticker: str) -> Any:
        company = type("Company", (), {})()
        company.cik = CIK
        company.name = "Apple Inc."
        return company

    def submissions(self, cik: str) -> Dict[str, Any]:
        return {"sic": "3571", "sicDescription": "Electronic Computers"}

    def filing_index(self, cik: str) -> List[Dict[str, Any]]:
        # No new filings: ingest() must return NO_CHANGE without touching the
        # concept endpoint.
        return []

    def concept_history(self, cik: str, taxonomy: str,
                        concept: str) -> Optional[Dict[str, Any]]:
        self.calls.append("concept_history")
        raise AssertionError("concept_history must not be called")

    def documents_for(self, taxonomy: str, concept: str) -> Tuple[Any, ...]:
        self.calls.append("documents_for")
        return ()

    def transport_stats(self) -> Dict[str, Any]:
        return {}

    @property
    def network_fetches(self) -> int:
        return 0

    @property
    def concept_fetches(self) -> int:
        return 0


class TestReprocessExisting(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SQLiteArchive(":memory:")
        self.registry = CoreRegistry(self.store.connection)
        seed(self.registry)
        self.provider = _NoFetchProvider()
        self.store.record_asset(TICKER, cik=CIK, name="Apple Inc.")
        self.asset_id = self.store.asset_id_for_cik(CIK)
        self.ingestor = Ingestor(self.store, self.provider, self.registry)

    def _seed_eps_document(self) -> None:
        """Record one saved concept document, exactly as a prior ingest run
        would have stored it, with no network."""
        body = json.dumps(EPS_PAYLOAD).encode("utf-8")
        document = StoredDocument(
            content_hash="sha256:" + EPS_URI,
            uri=EPS_URI,
            canonical_uri=EPS_URI,
            http_status=200,
            media_type="application/json",
            byte_size=len(body),
            fetched_at="2026-08-01T00:00:00Z",
            first_seen_at="2026-08-01T00:00:00Z",
            provider="SecEdgar",
            document_type="SEC_COMPANY_CONCEPT",
            payload=body,
        )
        self.store.record_source_document(document)

    def _observations(self) -> int:
        return self.store.connection.execute(
            "SELECT COUNT(*) FROM observations WHERE asset_id = ?",
            (self.asset_id,),
        ).fetchone()[0]

    def test_reprocess_creates_observations_from_saved_document(self):
        # The concept payload was saved by a previous run; no new filing exists
        # now, so a plain ingest would return NO_CHANGE and store nothing.
        self._seed_eps_document()
        before = self._observations()
        report = self.ingestor.reprocess_existing(
            TICKER, metrics=["eps_diluted"], forms=["10-Q"],
        )
        self.assertEqual(self.provider.calls, [], "no network request may be made")
        self.assertEqual(report.network_fetches, 0)
        self.assertEqual(report.concept_fetches, 0)
        self.assertEqual(report.filings_ingested, 0)
        self.assertEqual(report.headline_outcome(), "COLLECTED")
        self.assertEqual(report.observations_stored, 1)
        self.assertEqual(self._observations(), before + 1)

    def test_reprocess_is_deterministic_and_never_duplicates(self):
        self._seed_eps_document()
        first = self.ingestor.reprocess_existing(
            TICKER, metrics=["eps_diluted"], forms=["10-Q"],
        )
        second = self.ingestor.reprocess_existing(
            TICKER, metrics=["eps_diluted"], forms=["10-Q"],
        )
        self.assertEqual(first.observations_stored, 1)
        self.assertEqual(second.observations_stored, 0)
        self.assertEqual(second.source_facts_skipped, 1)
        self.assertEqual(second.observations_skipped, 1)
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self._observations(), 1)

    def test_ingest_no_change_is_distinct_from_reprocess(self):
        self._seed_eps_document()
        ingest_report = self.ingestor.ingest(
            TICKER, metrics=["eps_diluted"], forms=["10-Q"],
        )
        self.assertEqual(ingest_report.headline_outcome(), "NOT_ATTEMPTED")
        self.assertEqual(ingest_report.filings_ingested, 0)
        self.assertEqual(ingest_report.observations_stored, 0)

        reprocess_report = self.ingestor.reprocess_existing(
            TICKER, metrics=["eps_diluted"], forms=["10-Q"],
        )
        self.assertEqual(reprocess_report.headline_outcome(), "COLLECTED")
        self.assertEqual(reprocess_report.filings_ingested, 0)
        self.assertEqual(reprocess_report.observations_stored, 1)
        self.assertEqual(ingest_report.headline_outcome() !=
                         reprocess_report.headline_outcome(), True)

    def test_ingest_reprocess_flag_delegates(self):
        self._seed_eps_document()
        report = self.ingestor.ingest(
            TICKER, metrics=["eps_diluted"], forms=["10-Q"], reprocess=True,
        )
        self.assertEqual(report.headline_outcome(), "COLLECTED")
        self.assertEqual(report.observations_stored, 1)
        self.assertEqual(self.provider.calls, [])

    def test_unknown_ticker_reports_unresolved(self):
        report = self.ingestor.reprocess_existing(
            "NOPE", metrics=["eps_diluted"], forms=["10-Q"],
        )
        self.assertEqual(report.headline_outcome(), "ISSUER_UNRESOLVED")
        self.assertEqual(report.observations_stored, 0)

    def test_metric_without_mapping_is_reported(self):
        self._seed_eps_document()
        report = self.ingestor.reprocess_existing(
            TICKER, metrics=["does_not_exist"], forms=["10-Q"],
        )
        self.assertEqual(report.concepts_unresolved, 1)
        self.assertEqual(report.observations_stored, 0)
        self.assertEqual(report.errors, [])

    def test_missing_saved_document_is_reported(self):
        # A mapping exists but no concept document was ever saved for it, so
        # reprocessing must not fabricate a fetch.
        report = self.ingestor.reprocess_existing(
            TICKER, metrics=["eps_diluted"], forms=["10-Q"],
        )
        self.assertEqual(report.concepts_unresolved, 1)
        self.assertEqual(report.observations_stored, 0)
        self.assertEqual(report.errors, [])
        self.assertEqual(self.provider.calls, [])

    def test_reprocess_touches_only_this_asset(self):
        self._seed_eps_document()
        report = self.ingestor.reprocess_existing(
            TICKER, metrics=["eps_diluted"], forms=["10-Q"],
        )
        self.assertEqual(report.cik, CIK)
        self.assertEqual(report.asset, TICKER)
        self.assertEqual(report.source_facts_stored, 1)


if __name__ == "__main__":
    unittest.main()
