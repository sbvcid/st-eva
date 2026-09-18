import unittest

from st_eva_runner import (
    CompanyResolver,
    MarketImpliedAssumptionsEngine,
    run_st_eva,
)
from fundamental_provider import FundamentalData, YahooFundamentalProvider
from llm_interpreter import build_interpretation_prompt



class TestMarketImpliedAssumptions(unittest.TestCase):
    def test_fundamental_provider_defaults_are_unavailable(self):
        data = FundamentalData()
        self.assertEqual(data.current_eps, "UNAVAILABLE")
        self.assertEqual(data.forward_eps, "UNAVAILABLE")
        self.assertEqual(data.consensus_forward_eps, "UNAVAILABLE")
        self.assertEqual(data.historical_pe_band, {})

    def test_consensus_extraction_prefers_forward_year_estimate(self):
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


    def test_historical_pe_percentile_uses_full_band(self):
        data = CompanyResolver.resolve("MSFT", mode="regression")
        data.historical_pe_band = {
            "10th": 10.0,
            "25th": 15.0,
            "median": 20.0,
            "75th": 30.0,
            "90th": 40.0,
        }
        result = MarketImpliedAssumptionsEngine.analyze(
            data,
            reference_multiple=20.0,
        )
        self.assertAlmostEqual(
            result["observed_valuation"]["approx_historical_pe_percentile"],
            50.0,
            places=10,
        )

    def test_multi_method_reverse_valuation(self):
        data = CompanyResolver.resolve("MSFT", mode="regression")
        data.current_fcf = 10.0
        data.current_ebitda = 20.0
        data.current_revenue = 50.0
        data.current_market_cap = 1000.0
        data.current_enterprise_value = 1100.0
        data.historical_ps_band = {
            "10th": 3.0, "25th": 4.0, "median": 5.0,
            "75th": 6.0, "90th": 7.0, "observations": 5,
        }
        data.historical_ev_ebitda_band = {
            "10th": 10.0, "25th": 12.0, "median": 15.0,
            "75th": 18.0, "90th": 20.0, "observations": 5,
        }
        result = MarketImpliedAssumptionsEngine.analyze(data, pfcf_multiple=25.0)
        self.assertAlmostEqual(result["observed_valuation"]["current_pfcf"], 100.0)
        self.assertAlmostEqual(result["observed_valuation"]["current_ev_ebitda"], 55.0)
        self.assertAlmostEqual(result["observed_valuation"]["current_ps"], 20.0)
        self.assertAlmostEqual(result["implied_assumptions"]["fcf_at_reference_multiple"], 40.0)
        self.assertAlmostEqual(result["implied_assumptions"]["ebitda_at_reference_multiple"], 1100.0 / 15.0)
        self.assertAlmostEqual(result["implied_assumptions"]["revenue_at_reference_multiple"], 200.0)

    def test_llm_interpreter_is_non_arithmetic_adapter(self):
        prompt = build_interpretation_prompt({
            "market_implied_assumptions": {
                "forward_eps_at_reference_multiple": 10.0,
                "required_eps_cagr_from_current_eps": 0.12,
            },
            "missing_data": ["current_fcf"],
        })
        self.assertIn("Do not calculate or modify financial numbers", prompt)
        self.assertIn("10.0", prompt)
        self.assertIn("current_fcf", prompt)

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
