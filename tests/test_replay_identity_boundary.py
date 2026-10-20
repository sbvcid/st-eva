"""Boundary tests for the replay identity contract.

These pin the behaviour the R6/R6.1 replay fixes depend on, at the boundary
where a replay can go wrong in the two ways that matter:

* a faithful rebuild that differs from the run it rebuilds, because the run
  and the rebuild resolve the same figure's currency differently; and
* a rebuild that is *more* informed than the run, so a run that refused a
  figure comes back as if it had computed it.

The second is the dangerous one: it turns a replay into a silent improvement
on the record. A figure the run refused must stay refused in the rebuild, and
a figure the run computed must come back computed.

They also pin that the data-date cutoff and the archival watermark are
distinguished by the availability rules rather than by swapping one for the
other, and that a genuinely different input is still reported as different.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from archive import REPLAY_DIVERGED, REPLAY_MATCH, replay
from data_contract import (
    AvailabilityBasis,
    CurrencyBasis,
    METRIC_REVENUE,
    SourceType,
    Unit,
    build_observation,
    effective_currency,
)
from st_eva_runner import (
    MarketData,
    UNAVAILABLE,
    _apply_observations_to_view,
    material_observations,
    price_observations,
    run_st_eva,
)
from web.service_adapter import AnalysisServiceAdapter, default_replay_doc_builder

PRICE = 336.64
SEC_PATCH = {
    "observations": [],
    "documents": [],
    "cik": None,
    "entity_name": None,
    "cross_validation": {},
    "acquired": False,
}


def _revenue_observation(value, currency):
    """A provider-stated revenue, in the currency the provider stated."""
    return build_observation(
        metric=METRIC_REVENUE,
        observation_id="ev-revenue-stub-001",
        value=value,
        unit=Unit.CURRENCY.value,
        provider="StubProvider",
        source_type=SourceType.API_LIVE.value,
        definition="Reported revenue.",
        methodology="stub source field",
        retrieved_at="2026-10-09T21:00:00+00:00",
        currency=currency,
        currency_basis=CurrencyBasis.REPORTED.value,
        period_start="2026-04-01",
        period_end="2026-09-30",
        as_of="2026-09-30",
        available_at="2026-10-09T21:00:00+00:00",
        available_at_basis=AvailabilityBasis.OBSERVATION_INSTANT.value,
        source_url="https://example.invalid/revenue",
        raw={"totalRevenue": value},
    )


def _live_market_data(ticker, revenue=402.7e9, revenue_currency=None):
    """A live-shaped acquisition.

    `revenue_currency` states the revenue's currency in a provider
    observation, the way a provider that reports in another currency does.
    Without it the revenue is a bare attribute of the instrument's currency.
    """
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
        current_revenue=revenue,
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
    observations = list(price_observations(data))
    if revenue_currency is not None:
        observations.append(_revenue_observation(revenue, revenue_currency))
    return _apply_observations_to_view(data, observations)


class _StubProvider:
    def __init__(self, revenue=402.7e9, revenue_currency=None):
        self._revenue = revenue
        self._revenue_currency = revenue_currency

    def fetch(self, ticker):
        return _live_market_data(
            ticker, revenue=self._revenue, revenue_currency=self._revenue_currency
        )


class _ReplayBoundaryBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="replay-boundary-")
        self.archives_dir = Path(self._tmp.name)
        self.adapter = AnalysisServiceAdapter(archives_dir=str(self.archives_dir))
        self.addCleanup(self._tmp.cleanup)

    def _acquire(self, ticker, provider, reference_multiple=None):
        archive = self.adapter.get_archive(ticker)
        self.addCleanup(archive.close)
        context_file = self.archives_dir / f"{ticker}.context.json"
        with patch("st_eva_runner.YahooFinanceProvider", return_value=provider), patch(
            "st_eva_runner._acquire_sec_evidence", return_value=dict(SEC_PATCH)
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
        return archive, core, context_file

    def _context_id(self, context_file):
        if not context_file.exists():
            return None
        return json.loads(context_file.read_text(encoding="utf-8")).get("context_id")


class TestTheArchiveAndTheEngineAgreeOnACurrency(_ReplayBoundaryBase):
    """One rule decides a figure's currency, wherever it is asked for."""

    def test_the_minted_observation_and_the_projection_resolve_the_same_currency(self):
        """The archive's rule and the engine's rule are the same rule."""
        view = _live_market_data("CUR")
        minted = material_observations(view)[METRIC_REVENUE]
        from data_contract import ValuationInputs

        resolved = ValuationInputs.from_legacy_view(view).current_revenue_currency
        self.assertEqual(minted.currency, resolved)

    def test_a_figure_with_no_observation_carries_the_instruments_currency(self):
        currency, basis = effective_currency(None, "USD")
        self.assertEqual(currency, "USD")
        self.assertEqual(basis, CurrencyBasis.REPORTED.value)

    def test_a_stated_currency_wins_over_the_instruments_currency(self):
        source = _revenue_observation(1.0, "JPY")
        currency, _basis = effective_currency(source, "USD")
        self.assertEqual(currency, "JPY")

    def test_no_currency_anywhere_leaves_it_undeclared(self):
        currency, basis = effective_currency(None, None)
        self.assertIsNone(currency)
        self.assertEqual(basis, CurrencyBasis.UNDECLARED.value)


class TestARebuildReproducesItsRun(_ReplayBoundaryBase):
    """A faithful rebuild reports the same verdict the run recorded."""

    def test_a_provider_reported_ratio_is_reproduced_by_its_replay(self):
        archive, core, context_file = self._acquire("REPRO", _StubProvider())
        stored = archive.context_at("REPRO", core["as_of"])
        stored_ps = (
            stored.get("derived", {}).get("current_ps", {}).get("figure", {}).get("value")
        )
        self.assertIsNotNone(
            stored_ps, "the live run must have computed the ratio it had the data for"
        )

        watermark = archive.archival_watermark("REPRO")
        result = replay(
            archive,
            "REPRO",
            watermark,
            default_replay_doc_builder,
            context_id=self._context_id(context_file),
        )
        self.assertEqual(result.outcome, REPLAY_MATCH, result.reason)

    def test_a_run_that_refused_a_cross_currency_ratio_still_refuses_it(self):
        """A rebuild must not be more informed than the run it rebuilds."""
        archive, core, context_file = self._acquire(
            "XCUR", _StubProvider(revenue=402.7e9, revenue_currency="JPY")
        )
        stored = archive.context_at("XCUR", core["as_of"])
        stored_ps = (
            stored.get("derived", {}).get("current_ps", {}).get("figure", {}).get("value")
        )
        self.assertIsNone(
            stored_ps,
            "a JPY revenue against a USD market cap must not produce a ratio",
        )

        watermark = archive.archival_watermark("XCUR")
        result = replay(
            archive,
            "XCUR",
            watermark,
            default_replay_doc_builder,
            context_id=self._context_id(context_file),
        )
        self.assertEqual(result.outcome, REPLAY_MATCH, result.reason)
        rebuilt_ps = (
            result.document.get("derived", {})
            .get("current_ps", {})
            .get("figure", {})
            .get("value")
        )
        self.assertIsNone(rebuilt_ps, "the rebuild must refuse the ratio as well")


class TestTheCutoffIsTheAvailabilityRule(_ReplayBoundaryBase):
    """The data date and the watermark are different knowledge instants."""

    def test_the_data_date_sees_fewer_observations_than_the_watermark(self):
        archive, core, _ = self._acquire("CUT", _StubProvider())
        as_of = core["as_of"]
        watermark = archive.archival_watermark("CUT")
        self.assertGreater(watermark, as_of)
        self.assertLess(
            len(archive.observations_for("CUT", as_of)),
            len(archive.observations_for("CUT", watermark)),
        )

    def test_the_data_date_rebuild_is_not_the_watermark_rebuild(self):
        """The cutoff is not swapped: an earlier cutoff sees less evidence."""
        archive, core, context_file = self._acquire("CUT2", _StubProvider())
        as_of = core["as_of"]
        watermark = archive.archival_watermark("CUT2")
        early = replay(archive, "CUT2", as_of, default_replay_doc_builder)
        late = replay(
            archive,
            "CUT2",
            watermark,
            default_replay_doc_builder,
            context_id=self._context_id(context_file),
        )
        self.assertLess(early.observations_used, late.observations_used)
        self.assertEqual(late.observations_used, late.observations_considered)
        self.assertEqual(late.outcome, REPLAY_MATCH, late.reason)


class TestAGenuineDifferenceIsStillADifference(_ReplayBoundaryBase):
    """Nothing here is allowed to report a false match."""

    def test_a_reference_conditioned_run_still_diverges_from_its_own_snapshot(self):
        archive, core, context_file = self._acquire(
            "REF", _StubProvider(), reference_multiple=24.0
        )
        watermark = archive.archival_watermark("REF")
        result = replay(
            archive,
            "REF",
            watermark,
            default_replay_doc_builder,
            context_id=self._context_id(context_file),
        )
        self.assertEqual(result.outcome, REPLAY_DIVERGED, result.reason)
        self.assertFalse(result.matched)

    def test_two_runs_that_differ_report_their_difference(self):
        """A different input is a real difference, not a canonicalisation slip."""
        free = self._acquire("TWOA", _StubProvider(revenue=402.7e9))
        conditioned = self._acquire("TWOB", _StubProvider(revenue=402.7e9),
                                    reference_multiple=24.0)
        for archive, _core, context_file in (free, conditioned):
            watermark = archive.archival_watermark(
                "TWOA" if archive is free[0] else "TWOB"
            )
            result = replay(
                archive,
                "TWOA" if archive is free[0] else "TWOB",
                watermark,
                default_replay_doc_builder,
                context_id=self._context_id(context_file),
            )
            expected = REPLAY_MATCH if archive is free[0] else REPLAY_DIVERGED
            self.assertEqual(result.outcome, expected, result.reason)


class TestTheDifferenceReportMatchesTheIdentity(_ReplayBoundaryBase):
    """A reader is never shown a difference the identity ignores."""

    def test_a_volatile_field_is_not_reported_as_a_difference(self):
        archive, core, context_file = self._acquire("VOL", _StubProvider())
        watermark = archive.archival_watermark("VOL")
        result = replay(
            archive,
            "VOL",
            watermark,
            default_replay_doc_builder,
            context_id=self._context_id(context_file),
        )
        self.assertEqual(result.outcome, REPLAY_MATCH, result.reason)
        reported = {d["field"].rsplit(".", 1)[-1] for d in result.field_diffs}
        for volatile in ("selected_at", "generated_at", "retrieved_at", "checked_at"):
            self.assertNotIn(volatile, reported)


if __name__ == "__main__":
    unittest.main()
