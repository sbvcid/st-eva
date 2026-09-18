import unittest

from st_eva_runner import (
    CompanyResolver,
    MarketImpliedAssumptionsEngine,
    run_st_eva,
)


class TestMarketImpliedAssumptions(unittest.TestCase):
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
