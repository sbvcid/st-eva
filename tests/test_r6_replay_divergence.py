"""R6: diagnose and correct the live-AAPL point-in-time replay DIVERGENCE.

The R3 live AAPL acceptance recorded `replay_summary.outcome = DIVERGED`. This
module demonstrates the exact cause with a deterministic, offline reproduction
(a live-shaped `API_LIVE` acquisition in a temporary archive directory), then
proves the correction and that genuine divergences are still reported.

Two separable causes are separated here:

1. A replay *cutoff* mismatch (the demonstrated defect). The web path replayed
   at the data date, which is before the archival watermark for the
   archive-first-seen vendor fundamentals, so `observations_for` dropped those
   observations and a faithful rebuild was reported DIVERGED. Replaying at the
   archival watermark rebuilds from the *same* eligible observation set and
   MATCHes.

2. A genuine, *unresolved* input difference that is preserved, not hidden. The
   live context was conditioned on a user-supplied reference multiple -- a
   runtime assumption, not an archived observation. The replay rebuilds from
   observations only, so the reference-conditional figures cannot be
   reconstructed and a reference-conditioned context still reports DIVERGED.

Nothing here touches the persistent databases; every run uses a temporary
archive directory and the SEC layer is left empty so the test never needs the
network.
"""

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
from data_contract import (
    AvailabilityBasis,
    METRIC_PRICE,
    Observation,
    SourceType,
    Unit,
    ValidationStatus,
)
from st_eva_runner import (
    MarketData,
    UNAVAILABLE,
    _apply_observations_to_view,
    price_observations,
    run_st_eva,
)
from web.service_adapter import AnalysisServiceAdapter, default_replay_doc_builder

LIVE_PRICE = 336.64
LIVE_TRAILING_EPS = 8.72
LIVE_FORWARD_EPS = 9.41


def _price_observation(price: float = 400.0, as_of: str = "2026-09-20") -> Observation:
    """A single source-dated price observation, with no context archived."""
    return Observation(
        observation_id="ev-price-nosnap-001",
        metric=METRIC_PRICE,
        value=price,
        unit=Unit.CURRENCY.value,
        currency="USD",
        currency_basis="REPORTED",
        period_start=None,
        period_end=as_of,
        as_of=as_of,
        available_at=f"{as_of}T20:00:00.000Z",
        available_at_basis=AvailabilityBasis.OBSERVATION_INSTANT.value,
        provider="RegressionFixture",
        source_type=SourceType.REGRESSION_FIXTURE.value,
        source_url=None,
        definition="Observed current or latest market price.",
        methodology="test helper",
        retrieved_at="2026-09-28T12:00:00+00:00",
        raw={"regular_market_price": price},
        status=ValidationStatus.SINGLE_SOURCE,
    )


def _live_market_data(ticker: str) -> MarketData:
    data = MarketData(
        ticker=ticker,
        company_name="Live Acquired Co",
        exchange="NMS",
        currency="USD",
        price=LIVE_PRICE,
        price_date="2026-10-09",
        price_source="Yahoo Finance chart API",
        price_source_url="https://query1.finance.yahoo.com/v8/finance/chart/",
        current_eps=LIVE_TRAILING_EPS,
        forward_eps=LIVE_FORWARD_EPS,
        consensus_forward_eps=LIVE_FORWARD_EPS * 1.05,
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


class _ReplayDiagnosisBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="r6-replay-")
        self.archives_dir = Path(self._tmp.name)
        self.adapter = AnalysisServiceAdapter(archives_dir=str(self.archives_dir))
        self.ticker = "LIVECO"
        self.addCleanup(self._tmp.cleanup)

    def _acquire(self, reference_multiple=None):
        """Archive a live-shaped acquisition into a fresh temporary archive."""
        archive = self.adapter.get_archive(self.ticker)
        self.addCleanup(archive.close)
        context_file = self.archives_dir / f"{self.ticker}.context.json"
        with patch("st_eva_runner.YahooFinanceProvider", return_value=_StubProvider()), patch(
            "st_eva_runner._acquire_sec_evidence",
            return_value={
                "observations": [],
                "documents": [],
                "cik": None,
                "entity_name": None,
                "cross_validation": {},
                "acquired": False,
            },
        ):
            core = run_st_eva(
                ticker=self.ticker,
                mode="live",
                reference_multiple=reference_multiple,
                reverse_horizons=[3.0],
                required_returns=[0.10],
                save_snapshot=False,
                context_path=str(context_file),
                archive=archive,
                include_historical_pe=False,
            )
        return archive, core

    def _adapter_dto(self, reference_multiple=None, ticker=None):
        with patch("st_eva_runner.YahooFinanceProvider", return_value=_StubProvider()), patch(
            "st_eva_runner._acquire_sec_evidence",
            return_value={
                "observations": [],
                "documents": [],
                "cik": None,
                "entity_name": None,
                "cross_validation": {},
                "acquired": False,
            },
        ):
            return self.adapter.run_analysis_pipeline(
                ticker=ticker or self.ticker,
                mode="live",
                reference_multiple=reference_multiple,
                reverse_horizons=[3.0],
                required_returns=[0.10],
            )


class TestDefectIsTheCutoffNotSerialization(_ReplayDiagnosisBase):
    """The data-date cutoff -- not volatile serialization -- was the defect."""

    def test_data_date_replay_diverges_but_watermark_replay_matches(self):
        archive, core = self._acquire(reference_multiple=None)
        as_of = core["as_of"]
        watermark = archive.archival_watermark(self.ticker)

        # The archive-first-seen fundamentals become eligible strictly after the
        # data date, so the watermark is later than the data date.
        self.assertIsNotNone(watermark)
        self.assertGreater(watermark, as_of)

        # DEFECT reproduced: replaying at the data date drops the just-archived
        # vendor fundamentals, so a faithful rebuild is wrongly DIVERGED.
        at_data_date = replay(archive, self.ticker, as_of, default_replay_doc_builder)
        self.assertEqual(at_data_date.outcome, REPLAY_DIVERGED)

        # CORRECTION: replaying at the archival watermark (the knowledge instant
        # the archive holds) rebuilds from the same eligible observation set.
        at_watermark = replay(archive, self.ticker, watermark, default_replay_doc_builder)
        self.assertEqual(at_watermark.outcome, REPLAY_MATCH, at_watermark.reason)

        stored = archive.context_at(self.ticker, as_of)
        self.assertEqual(at_watermark.document["context_id"], stored["context_id"])

        # The data-date rebuild genuinely used fewer observations -- the
        # difference is eligibility, not a transformed hash.
        self.assertLess(
            at_data_date.observations_used, at_watermark.observations_used
        )
        self.assertEqual(
            at_watermark.observations_used, at_watermark.observations_considered
        )


class TestSemanticEqualityMatches(_ReplayDiagnosisBase):
    """A stored context rebuilt from the same eligible observations MATCHes."""

    def test_web_replay_of_a_reference_free_live_context_matches(self):
        dto = self._adapter_dto(reference_multiple=None)
        rs = dto.replay_summary
        self.assertTrue(rs.attempted)
        self.assertEqual(rs.outcome, REPLAY_MATCH, rs.reason)
        self.assertTrue(rs.matched)
        self.assertTrue(rs.reconstructed)
        # Archive-first-seen vendor data replays OBSERVATIONAL, honestly.
        self.assertEqual(rs.replay_fidelity, "OBSERVATIONAL")
        # Every eligible observation was used; nothing was dropped or padded.
        self.assertGreater(rs.observations_used, 0)


class TestRealInputDifferenceStillDiverges(_ReplayDiagnosisBase):
    """A materially different input still reports DIVERGED, never a forced match."""

    def test_a_conditioning_reference_is_a_real_difference(self):
        reference_free = self._adapter_dto(reference_multiple=None, ticker="LIVEA")
        self.assertEqual(reference_free.replay_summary.outcome, REPLAY_MATCH)

        conditioned = self._adapter_dto(reference_multiple=24.0, ticker="LIVEB")
        self.assertEqual(conditioned.replay_summary.outcome, REPLAY_DIVERGED)
        self.assertFalse(conditioned.replay_summary.matched)

    def test_the_divergence_is_the_reference_conditioned_figure_not_noise(self):
        archive, core = self._acquire(reference_multiple=24.0)
        as_of = core["as_of"]
        watermark = archive.archival_watermark(self.ticker)

        stored = archive.context_at(self.ticker, as_of)
        result = replay(archive, self.ticker, watermark, default_replay_doc_builder)
        self.assertEqual(result.outcome, REPLAY_DIVERGED)
        rebuilt = result.document

        # The stored context carries the reference-conditioned figure; the
        # observation-only rebuild cannot reconstruct it, because the reference
        # multiple is not archived knowledge. That is the honest difference.
        stored_implied = (
            stored.get("market_implied", {})
            .get("figures", {})
            .get("implied_forward_eps", {})
            .get("figure", {})
            .get("value")
        )
        self.assertAlmostEqual(stored_implied, LIVE_PRICE / 24.0, places=9)
        rebuilt_implied = (
            rebuilt.get("market_implied", {})
            .get("figures", {})
            .get("implied_forward_eps", {})
            .get("figure", {})
            .get("value")
        )
        self.assertIsNone(rebuilt_implied)


class TestNoSubstitutionAtAnEarlierCutoff(_ReplayDiagnosisBase):
    """A newer observation never silently fills an earlier point in time."""

    def test_a_late_first_seen_fundamental_is_excluded_not_substituted(self):
        archive, core = self._acquire(reference_multiple=None)
        watermark = archive.archival_watermark(self.ticker)

        at_watermark = archive.observations_for(self.ticker, watermark)
        at_early = archive.observations_for(self.ticker, "2026-10-10")

        # The vendor fundamentals are archive-first-seen after 2026-10-09, so an
        # earlier cutoff sees strictly fewer observations.
        self.assertLess(len(at_early), len(at_watermark))

        # The excluded observations are genuinely dropped, not replaced with a
        # newer stand-in: the early rebuild reports less available evidence and
        # explicit unavailable states, never a populated figure.
        rebuilt_early = replay(
            archive, self.ticker, "2026-10-10", default_replay_doc_builder
        ).document
        early_observed = rebuilt_early.get("observed", {})
        stored = archive.context_at(self.ticker, core["as_of"])
        stored_coverage = stored.get("data_quality", {}).get("evidence_coverage", {})
        early_coverage = rebuilt_early.get("data_quality", {}).get("evidence_coverage", {})
        self.assertGreater(
            early_coverage.get("unavailable", 0),
            stored_coverage.get("unavailable", 0),
        )
        # A material vendor figure present in the stored context is unavailable
        # in the early rebuild -- excluded, not invented.
        self.assertIn("trailing_eps", stored.get("observed", {}))
        trailing = early_observed.get("trailing_eps")
        if isinstance(trailing, list) and trailing:
            figure = trailing[0].get("figure", {})
            self.assertEqual(figure.get("provenance_kind"), "UNAVAILABLE")


class TestInsufficientAndNoSnapshotPreserved(_ReplayDiagnosisBase):
    """Missing snapshots and empty archives keep meaningful states and reasons."""

    def test_empty_archive_is_insufficient_and_says_nothing_was_substituted(self):
        archive = self.adapter.get_archive("EMPTY")
        self.addCleanup(archive.close)
        result = replay(archive, "EMPTY", "2026-10-09", default_replay_doc_builder)
        self.assertEqual(result.outcome, REPLAY_INSUFFICIENT)
        self.assertIsNone(result.document)
        self.assertIn("nothing was substituted", result.reason.lower())

    def test_archived_observations_without_a_context_report_no_snapshot(self):
        # Snapshots are immutable (append-only by trigger), so build an archive
        # that holds observations but no context rather than deleting one.
        archive = self.adapter.get_archive("NOSNAP")
        self.addCleanup(archive.close)
        archive.record_observation("NOSNAP", _price_observation())
        archive.connection.commit()
        result = replay(archive, "NOSNAP", "2999-12-31", default_replay_doc_builder)
        self.assertEqual(result.outcome, REPLAY_NO_SNAPSHOT)
        # The reconstruction is still offered -- reported, not hidden.
        self.assertIsNotNone(result.document)
        self.assertIn("no context was archived", result.reason.lower())


class TestCanonicalizationIsDeterministic(_ReplayDiagnosisBase):
    """The semantic identity is deterministic; the full evidence is retained."""

    def test_repeat_replay_is_stable_and_volatile_fields_are_kept_out_of_identity(self):
        archive, core = self._acquire(reference_multiple=None)
        watermark = archive.archival_watermark(self.ticker)

        first = replay(archive, self.ticker, watermark, default_replay_doc_builder)
        second = replay(archive, self.ticker, watermark, default_replay_doc_builder)
        self.assertEqual(first.outcome, REPLAY_MATCH)
        # Deterministic: the same eligible inputs always rebuild the same id.
        self.assertEqual(
            first.document["context_id"], second.document["context_id"]
        )
        # The full documents still carry when-we-asked fields (generated_at); the
        # document hashes therefore differ, while the semantic context_id --
        # which strips volatile fields -- matches the stored snapshot.
        self.assertNotEqual(
            first.rebuilt_document_hash, first.stored_document_hash
        )
        stored = archive.context_at(self.ticker, core["as_of"])
        self.assertIn("generated_at", stored)
        self.assertIn("generated_at", first.document)


if __name__ == "__main__":
    unittest.main()
