import unittest

from st_eva_runner import (
    CompanyResolver,
    MarketImpliedAssumptionsEngine,
    run_st_eva,
)
from fundamental_provider import FundamentalData, YahooFundamentalProvider



class TestMarketImpliedAssumptions(unittest.TestCase):
    def test_fundamental_provider_defaults_are_unavailable(self):
        data = FundamentalData()
        self.assertEqual(data.current_eps, "UNAVAILABLE")
        self.assertEqual(data.forward_eps, "UNAVAILABLE")
        self.assertEqual(data.consensus_forward_eps, "UNAVAILABLE")
        self.assertEqual(data.historical_pe_band, {})

    def test_consensus_extraction_never_uses_actual_eps(self):
        trend = {
            "trend": [
                {"period": "0q", "earningsEstimate": {"avg": 1.0}},
                {"period": "+1y", "earningsEstimate": {"avg": 4.0}},
            ]
        }
        self.assertEqual(
            YahooFundamentalProvider._extract_consensus_forward_eps(trend),
            4.0,
        )

    def test_msft_implied_eps(self):
        data = CompanyResolver.resolve("MSFT", mode="regression")
        self.assertIsNotNone(data)

        result = MarketImpliedAssumptionsEngine.analyze(
            data,
            reference_multiple=30.0,
        )

        self.assertAlmostEqual(
            result["implied_assumptions"][
                "forward_eps_at_reference_multiple"
            ],
            425.50 / 30.0,
            places=10,
        )

    def test_consensus_forward_pe(self):
        data = CompanyResolver.resolve("MSFT", mode="regression")
        result = MarketImpliedAssumptionsEngine.analyze(data)

        self.assertAlmostEqual(
            result["observed_valuation"]["consensus_forward_pe"],
            425.50 / 13.20,
            places=10,
        )

    def test_no_synthetic_growth(self):
        result = run_st_eva(
            "MSFT",
            mode="regression",
            save_snapshot=False,
        )

        self.assertIsNone(
            result["market_implied_assumptions"][
                "required_eps_cagr_from_current_eps"
            ]
        )

    def test_unknown_live_ticker(self):
        result = run_st_eva(
            "THIS_TICKER_SHOULD_NOT_EXIST_XYZ",
            mode="live",
            save_snapshot=False,
        )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
