"""R6.1: replay must reconcile a run against its own snapshot.

When one asset carries several archived contexts that share an `as_of` -- for
example two runs with different supplied reference multiples -- selecting a
stored snapshot by `as_of` alone (`context_at`, which returns the earliest) can
compare a run's rebuild against an unrelated context. That produced a *false
MATCH* (a reference-conditioned run matching an older reference-free snapshot)
and a *false DIVERGED* (a reference-free run failing against an older
reference-conditioned one).

`replay()` now accepts the snapshot identity it is reconciling, and the web
adapter passes the context each run just archived. These tests pin the intended
target and prove honest outcomes in both directions, using temporary archives
and no SEC acquisition.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from archive import (
    REPLAY_DIVERGED,
    REPLAY_INSUFFICIENT,
    REPLAY_MATCH,
    REPLAY_NO_SNAPSHOT,
    replay,
)
from st_eva_runner import (
    MarketData,
    UNAVAILABLE,
    _apply_observations_to_view,
    price_observations,
    run_st_eva,
)
from web.service_adapter import AnalysisServiceAdapter, default_replay_doc_builder

PRICE = 336.64


def _live_market_data(ticker: str) -> MarketData:
    data = MarketData(
        ticker=ticker,
        company_name="Live Acquired Co",
        exchange="NMS",
        currency="USD",
        price=PRICE,
        price_date="2026-10-09",
        price_source="Yahoo Finance chart API",
        price_source_url="https://query1.finance.yahoo.com/v8/finance/chart/",
        current_eps=8.72,
        forward_eps=9.41,
        consensus_forward_eps=9.8805,
        next_event=UNAVAILABLE,
        next_event_status="Unconfirmed",
        historical_pe_band={"percentile_5": 28.0, "median": 35.65, "observations": 8},
        current_fcf=110.4e9,
        current_ebitda=145.9e9,
        current_revenue=402.7e9,
        current_enterprise_value=3.9e12,
        current_market_cap=3.8e12,
        price_history=[
            (f"2026-10-{day:02d}", 330.0 + 2.0 * index)
            for index, day in enumerate(range(1, 10), start=1)
        ],
        volume_history=[float(40_000_000 + 1_000_000 * index) for index in range(9)],
        source_type="API_LIVE",
        provider="YahooFinance+YahooFinanceFundamentals",
    )
    return _apply_observations_to_view(data, price_observations(data))


class _StubProvider:
    def fetch(self, _ticker: str) -> MarketData:
        return _live_market_data(_ticker)


_SEC_PATCH = {
    "observations": [],
    "documents": [],
    "cik": None,
    "entity_name": None,
    "cross_validation": {},
    "acquired": False,
}


class _SnapshotIdentityBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="r61-")
        self.archives_dir = Path(self._tmp.name)
        self.adapter = AnalysisServiceAdapter(archives_dir=str(self.archives_dir))
        self.addCleanup(self._tmp.cleanup)

    def _archive_context(self, archive, ticker, reference_multiple=None):
        context_file = self.archives_dir / f"{ticker}.context.json"
        with patch("st_eva_runner.YahooFinanceProvider", return_value=_StubProvider()), patch(
            "st_eva_runner._acquire_sec_evidence", return_value=dict(_SEC_PATCH)
        ):
            core = run_st_eva(
                ticker=ticker,
                mode="live",
                reference_multiple=reference_multiple,
                reverse_horizons=[3.0],
                required_returns=[0.10],
                save_snapshot=False,
                context_path=str(context_file),
                archive=archive,
                include_historical_pe=False,
            )
        # The web path identifies the snapshot by the context artifact the run
        # wrote, so the test reads it the same way rather than from the result
        # dict, which must stay unchanged for the CLI-output contract.
        context_id = None
        if context_file.exists():
            context_id = json.loads(
                context_file.read_text(encoding="utf-8")
            ).get("context_id")
        return {"archived_context_id": context_id, "as_of": core["as_of"]}

    def _adapter_dto(self, ticker, reference_multiple=None):
        with patch("st_eva_runner.YahooFinanceProvider", return_value=_StubProvider()), patch(
            "st_eva_runner._acquire_sec_evidence", return_value=dict(_SEC_PATCH)
        ):
            return self.adapter.run_analysis_pipeline(
                ticker=ticker,
                mode="live",
                reference_multiple=reference_multiple,
                reverse_horizons=[3.0],
                required_returns=[0.10],
            )

    def _snapshots(self, archive, ticker):
        return [
            dict(row)
            for row in archive.connection.execute(
                "SELECT c.context_id, c.as_of, c.document_json FROM context_snapshots c"
                " JOIN assets a ON a.asset_id = c.asset_id WHERE a.ticker = ?"
                " ORDER BY c.archived_at",
                (ticker,),
            ).fetchall()
        ]


class TestReplayTargetsTheNamedSnapshot(_SnapshotIdentityBase):
    """A stored context is reconciled by identity, not by as_of alone."""

    def test_two_contexts_sharing_as_of_are_distinct_and_selectable(self):
        archive = self.adapter.get_archive("SEQ")
        self.addCleanup(archive.close)
        c_free = self._archive_context(archive, "SEQ", None)["archived_context_id"]
        c_ref = self._archive_context(archive, "SEQ", 32.0)["archived_context_id"]
        watermark = archive.archival_watermark("SEQ")

        self.assertIsNotNone(c_free)
        self.assertIsNotNone(c_ref)
        self.assertNotEqual(c_free, c_ref)

        snapshots = self._snapshots(archive, "SEQ")
        self.assertEqual(len(snapshots), 2)
        # They genuinely share an as_of, which is what makes by-as_of selection
        # ambiguous.
        self.assertEqual(snapshots[0]["as_of"], snapshots[1]["as_of"])

        # context_by_id selects the exact snapshot for each identity.
        self.assertEqual(archive.context_by_id("SEQ", c_free)["context_id"], c_free)
        self.assertEqual(archive.context_by_id("SEQ", c_ref)["context_id"], c_ref)

        # The reference-free run reconciles against itself (MATCH); the
        # reference-conditioned run reconciles against itself (DIVERGED, because
        # its conditioning reference is not archived knowledge).
        by_free = replay(
            archive, "SEQ", watermark, default_replay_doc_builder, context_id=c_free
        )
        by_ref = replay(
            archive, "SEQ", watermark, default_replay_doc_builder, context_id=c_ref
        )
        self.assertEqual(by_free.outcome, REPLAY_MATCH, by_free.reason)
        self.assertEqual(by_ref.outcome, REPLAY_DIVERGED, by_ref.reason)

    def test_a_reference_conditioned_run_no_longer_false_matches(self):
        # The dangerous case is fixed: the OLD as_of selection matches the
        # earliest (reference-free) snapshot, but the named snapshot does not.
        archive = self.adapter.get_archive("SEQC")
        self.addCleanup(archive.close)
        c_free = self._archive_context(archive, "SEQC", None)["archived_context_id"]
        c_ref = self._archive_context(archive, "SEQC", 32.0)["archived_context_id"]
        watermark = archive.archival_watermark("SEQC")

        arbitrary = replay(archive, "SEQC", watermark, default_replay_doc_builder)
        named = replay(
            archive, "SEQC", watermark, default_replay_doc_builder, context_id=c_ref
        )
        # The reference-free snapshot is the earliest, so as_of selection
        # (documenting the old behaviour) reports MATCH ...
        self.assertEqual(arbitrary.outcome, REPLAY_MATCH)
        # ... while reconciling against its own snapshot is honestly DIVERGED.
        self.assertEqual(named.outcome, REPLAY_DIVERGED, named.reason)
        self.assertNotEqual(c_free, c_ref)

    def test_an_unknown_snapshot_identity_is_absent_not_substituted(self):
        archive = self.adapter.get_archive("SEQU")
        self.addCleanup(archive.close)
        self._archive_context(archive, "SEQU", None)
        watermark = archive.archival_watermark("SEQU")
        result = replay(
            archive,
            "SEQU",
            watermark,
            default_replay_doc_builder,
            context_id="ctx_does_not_exist",
        )
        self.assertEqual(result.outcome, REPLAY_NO_SNAPSHOT)
        # A snapshot for one asset id is not returned for a different asset.
        self.assertIsNone(archive.context_by_id("SEQU", "ctx_does_not_exist"))

    def test_the_default_as_of_selection_is_unchanged(self):
        # Without a named identity replay still resolves the earliest snapshot,
        # so existing callers and strict point-in-time behaviour are preserved.
        archive = self.adapter.get_archive("SEQD")
        self.addCleanup(archive.close)
        self._archive_context(archive, "SEQD", None)
        watermark = archive.archival_watermark("SEQD")
        result = replay(archive, "SEQD", watermark, default_replay_doc_builder)
        self.assertEqual(result.outcome, REPLAY_MATCH, result.reason)


class TestWebPathReconcilesAgainstItsOwnRun(_SnapshotIdentityBase):
    """The service adapter reports each submission's own replay result."""

    def test_reference_conditioned_after_reference_free(self):
        # Submission 1 reference-free -> MATCH; submission 2 reference-32 ->
        # DIVERGED against its own snapshot (never the older reference-free one).
        dto1 = self._adapter_dto("WAC", None)
        dto2 = self._adapter_dto("WAC", 32.0)
        self.assertEqual(dto1.replay_summary.outcome, REPLAY_MATCH, dto1.replay_summary.reason)
        self.assertEqual(dto2.replay_summary.outcome, REPLAY_DIVERGED, dto2.replay_summary.reason)

    def test_reference_free_after_reference_conditioned(self):
        # Submission 1 reference-32 -> DIVERGED; submission 2 reference-free ->
        # MATCH against its own snapshot (never the older reference-conditioned
        # one, which would report a false DIVERGED).
        dto1 = self._adapter_dto("WAB", 32.0)
        dto2 = self._adapter_dto("WAB", None)
        self.assertEqual(dto1.replay_summary.outcome, REPLAY_DIVERGED, dto1.replay_summary.reason)
        self.assertEqual(dto2.replay_summary.outcome, REPLAY_MATCH, dto2.replay_summary.reason)


class TestOtherStatesStillHold(_SnapshotIdentityBase):
    """Named snapping does not alter INSUFFICIENT / NO_SNAPSHOT semantics."""

    def test_earlier_cutoff_still_excludes_later_observations(self):
        archive = self.adapter.get_archive("WAE")
        self.addCleanup(archive.close)
        core = self._archive_context(archive, "WAE", None)
        cid = core["archived_context_id"]
        # A cutoff before the vendor fundamentals (and the price) became
        # eligible leaves nothing replayable -- nothing is substituted.
        early = replay(
            archive, "WAE", "2026-10-01", default_replay_doc_builder, context_id=cid
        )
        self.assertEqual(early.outcome, REPLAY_INSUFFICIENT)
        self.assertIn("nothing was substituted", early.reason.lower())

    def test_observations_without_a_snapshot_still_report_no_snapshot(self):
        archive = self.adapter.get_archive("WAN")
        self.addCleanup(archive.close)
        # No context archived for this asset; observations exist but the named
        # snapshot does not.
        from data_contract import (
            AvailabilityBasis,
            METRIC_PRICE,
            Observation,
            SourceType,
            Unit,
            ValidationStatus,
        )

        archive.record_observation(
            "WAN",
            Observation(
                observation_id="ev-price-wan-001",
                metric=METRIC_PRICE,
                value=400.0,
                unit=Unit.CURRENCY.value,
                currency="USD",
                currency_basis="REPORTED",
                period_start=None,
                period_end="2026-09-20",
                as_of="2026-09-20",
                available_at="2026-09-20T20:00:00.000Z",
                available_at_basis=AvailabilityBasis.OBSERVATION_INSTANT.value,
                provider="RegressionFixture",
                source_type=SourceType.REGRESSION_FIXTURE.value,
                source_url=None,
                definition="Observed current or latest market price.",
                methodology="test helper",
                retrieved_at="2026-09-28T12:00:00+00:00",
                raw={"regular_market_price": 400.0},
                status=ValidationStatus.SINGLE_SOURCE,
            ),
        )
        archive.connection.commit()
        result = replay(
            archive, "WAN", "2999-12-31", default_replay_doc_builder, context_id="ctx_absent"
        )
        self.assertEqual(result.outcome, REPLAY_NO_SNAPSHOT)


class TestNoPersistentDatabaseChanges(_SnapshotIdentityBase):
    """This task never writes the project's persistent archives."""

    def test_runs_use_only_temporary_archives(self):
        # The adapter under test is pointed at a temporary archives directory,
        # so writing a snapshot here cannot touch the persistent archives.
        archive = self.adapter.get_archive("PERSISTGUARD")
        archive.connection.commit()
        archive.close()
        guard = Path("data/archives/PERSISTGUARD.sqlite")
        self.assertFalse(guard.exists(), "no persistent archive file may be created")


if __name__ == "__main__":
    unittest.main()
