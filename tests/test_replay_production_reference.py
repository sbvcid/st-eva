"""A replay reproduces the reference the archived run selected.

The live web path runs with the production historical P/E and P/FCF
distributions in force, so its documents condition their implied figures on a
reference that came from the committed production datasets. A rebuild that
selected no reference produced a document that differed from the archived one
in every figure conditional on that reference -- a divergence that reported a
difference in the *reference*, not in the data.

These tests pin the cases apart:

  1. a run that used the production distributions replays as a match, and the
     rebuild's reference is the distribution's own median;
  2. a run that asked for no production reference still replays as a match --
     the rebuild invents no reference the run did not have;
  3. a run conditioned on an operator's own multiple still diverges, because
     that multiple is an assumption rather than archived knowledge, and the
     rebuild must not quietly substitute the production median for it;
  4. a run that built its distribution without the furnished evidence replays
     as a match too, because the archived document records how many
     observations stood behind its reference, and that count says which load
     of the dataset the run used.

Nothing here touches the persistent archives: every run uses a temporary
archive directory, the SEC layer is left empty and the provider is stubbed, so
the tests never need the network. The production distributions themselves are
read from the committed datasets, which is what the live path reads.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from archive import REPLAY_DIVERGED, REPLAY_MATCH, replay
from st_eva_runner import (
    MarketData,
    UNAVAILABLE,
    _apply_observations_to_view,
    price_observations,
    run_st_eva,
)
from web.service_adapter import AnalysisServiceAdapter, default_replay_doc_builder

PRICES_EXIST = (Path("data/historical_pe/AAPL/daily_prices.json")).exists()
PRICES_SKIP = "AAPL daily_prices.json excluded per C-1 / DATA-DELIVERY.md"

# The ticker under test has an established production historical P/E and P/FCF
# distribution, so a run that asks for them gets a qualified reference.
TICKER = "AAPL"

# This issuer's distribution is eligible both with and without the furnished
# evidence, and the two medians differ.
NEGATIVE_PATH_TICKER = "MU"

LIVE_PRICE = 336.64
LIVE_TRAILING_EPS = 8.72
LIVE_FORWARD_EPS = 9.41


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


def _no_sec_evidence():
    return {
        "observations": [],
        "documents": [],
        "cik": None,
        "entity_name": None,
        "cross_validation": {},
        "acquired": False,
    }


class _ReplayFixture(unittest.TestCase):
    """A live-shaped acquisition in a temporary archive, and its replay."""

    ticker = TICKER

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="replay-production-ref-")
        self.archives_dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.adapter = AnalysisServiceAdapter(archives_dir=str(self.archives_dir))

    def _acquire(self, **kwargs):
        """Archive a live-shaped acquisition into a fresh temporary archive."""
        archive = self.adapter.get_archive(self.ticker)
        self.addCleanup(archive.close)
        context_file = self.archives_dir / f"{self.ticker}.context.json"
        with patch("st_eva_runner.YahooFinanceProvider", return_value=_StubProvider()), patch(
            "st_eva_runner._acquire_sec_evidence",
            return_value=_no_sec_evidence(),
        ):
            core = run_st_eva(
                ticker=self.ticker,
                mode="live",
                reverse_horizons=[3.0],
                required_returns=[0.10],
                save_snapshot=False,
                context_path=str(context_file),
                archive=archive,
                **kwargs,
            )
        return archive, core

    def _stored(self, archive, core):
        return archive.context_at(self.ticker, core["as_of"])

    def _replay(self, archive, core, context_id=None):
        watermark = archive.archival_watermark(self.ticker)
        return replay(
            archive,
            self.ticker,
            watermark,
            default_replay_doc_builder,
            context_id=context_id,
        )


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class ProductionReferenceReplay(_ReplayFixture):
    """The rebuild reproduces the reference the archived run selected."""

    def test_a_production_reference_run_replays_as_a_match(self):
        archive, core = self._acquire(
            include_historical_pe=True,
            include_historical_pfcf=True,
        )
        stored = self._stored(archive, core)
        self.assertEqual(
            stored["valuation_reference"]["basis"],
            "PRODUCTION_PE_MEDIAN",
        )

        result = self._replay(archive, core)
        self.assertEqual(result.outcome, REPLAY_MATCH, result.reason)
        self.assertEqual(result.field_diffs, ())

    def test_the_rebuilt_reference_is_the_production_median(self):
        archive, core = self._acquire(include_historical_pe=True)
        stored = self._stored(archive, core)

        rebuilt = self._replay(archive, core).document
        reference = rebuilt["valuation_reference"]
        self.assertEqual(reference["basis"], "PRODUCTION_PE_MEDIAN")
        self.assertEqual(reference["multiple"], stored["valuation_reference"]["multiple"])
        self.assertEqual(
            reference["source_observation_count"],
            stored["valuation_reference"]["source_observation_count"],
        )
        # The reference the run used, not a vendor band statistic and not a
        # number the rebuild made up.
        self.assertNotEqual(
            reference["multiple"],
            35.65,
        )

    def test_a_reference_free_run_replays_as_a_match(self):
        archive, core = self._acquire(include_historical_pe=False)
        stored = self._stored(archive, core)
        self.assertEqual(stored["valuation_reference"]["basis"], "NONE")

        result = self._replay(archive, core)
        self.assertEqual(result.outcome, REPLAY_MATCH, result.reason)
        # The rebuild selected no production reference either: the run had
        # none, and the archive does not get to add one.
        rebuilt = result.document
        self.assertEqual(rebuilt["valuation_reference"]["basis"], "NONE")
        self.assertIsNone(rebuilt["valuation_reference"]["multiple"])

    def test_an_operator_multiple_is_not_replaced_by_the_production_median(self):
        archive, core = self._acquire(
            include_historical_pe=True,
            reference_multiple=24.0,
        )
        stored = self._stored(archive, core)
        self.assertEqual(stored["valuation_reference"]["basis"], "USER_SUPPLIED")

        result = self._replay(archive, core)
        self.assertEqual(result.outcome, REPLAY_DIVERGED)
        rebuilt = result.document
        # The rebuild holds no reference at all: the operator's multiple is an
        # assumption, not archived knowledge, and substituting the production
        # median for it would report a match that is not one.
        self.assertIsNone(rebuilt["valuation_reference"]["multiple"])
        self.assertIsNone(
            rebuilt.get("derived", {})
            .get("implied_forward_eps", {})
            .get("figure", {})
            .get("value")
        )


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class NegativePathReplay(_ReplayFixture):
    """The rebuild reads the load of the dataset the run used.

    A distribution built with the furnished evidence and one built without it
    are different distributions: different observations, and a different
    median. The archived document records how many observations stood behind
    its reference, and that count is what tells the two apart.
    """

    ticker = NEGATIVE_PATH_TICKER

    def test_a_run_without_the_furnished_evidence_replays_as_a_match(self):
        archive, core = self._acquire(
            include_historical_pe=True,
            enable_furnished_pe=False,
        )
        stored = self._stored(archive, core)
        reference = stored["valuation_reference"]
        self.assertEqual(reference["basis"], "PRODUCTION_PE_MEDIAN")
        self.assertIsNotNone(reference["source_observation_count"])

        result = self._replay(archive, core)
        self.assertEqual(result.outcome, REPLAY_MATCH, result.reason)
        self.assertEqual(result.field_diffs, ())
        self.assertEqual(
            result.document["valuation_reference"]["multiple"],
            reference["multiple"],
        )


if __name__ == "__main__":
    unittest.main()
