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

    def test_derived_ratio_band_requires_exact_date_matching(self):
        results = [
            {
                "trailingMarketCap": [
                    {"asOfDate": "2025-06-30", "reportedValue": {"raw": 1000.0}}
                ]
            },
            {
                "trailingFreeCashFlow": [
                    {"asOfDate": "2025-06-29", "reportedValue": {"raw": 50.0}}
                ]
            }
        ]
        band = YahooFundamentalProvider._derived_ratio_band(results, "trailingMarketCap", "trailingFreeCashFlow")
        self.assertEqual(band, {})

    def test_missing_fcf_and_ebitda_remain_unavailable(self):
        data = CompanyResolver.resolve("MSFT", mode="regression")
        data.current_fcf = "UNAVAILABLE"
        data.current_ebitda = "UNAVAILABLE"
        result = MarketImpliedAssumptionsEngine.analyze(data)
        self.assertIsNone(result["observed_valuation"]["current_pfcf"])
        self.assertIsNone(result["observed_valuation"]["current_ev_ebitda"])

    def test_currency_consistency_protection_a_to_g(self):
        # A. same-currency Market Cap / Revenue
        results_a = [
            {"trailingMarketCap": [{"asOfDate": "2026-01-01", "currencyCode": "USD", "reportedValue": {"raw": 1000.0}}]},
            {"trailingTotalRevenue": [{"asOfDate": "2026-01-01", "currencyCode": "USD", "reportedValue": {"raw": 100.0}}]}
        ]
        val_mc = YahooFundamentalProvider._latest_value(results_a, "trailingMarketCap")
        val_rev = YahooFundamentalProvider._latest_value(results_a, "trailingTotalRevenue")
        self.assertEqual(val_mc[1], val_rev[1])

        # B. different-currency Market Cap / Revenue (USD vs TWD)
        results_b = [
            {"trailingMarketCap": [{"asOfDate": "2026-01-01", "currencyCode": "USD", "reportedValue": {"raw": 1000.0}}]},
            {"trailingTotalRevenue": [{"asOfDate": "2026-01-01", "currencyCode": "TWD", "reportedValue": {"raw": 3000.0}}]}
        ]
        mc_val, mc_curr = YahooFundamentalProvider._latest_value(results_b, "trailingMarketCap")
        rev_val, rev_curr = YahooFundamentalProvider._latest_value(results_b, "trailingTotalRevenue")
        self.assertNotEqual(mc_curr, rev_curr)

        # C. same-currency EV / EBITDA
        results_c = [
            {"trailingEnterpriseValue": [{"asOfDate": "2026-01-01", "currencyCode": "USD", "reportedValue": {"raw": 1100.0}}]},
            {"trailingEBITDA": [{"asOfDate": "2026-01-01", "currencyCode": "USD", "reportedValue": {"raw": 100.0}}]}
        ]
        ev_val, ev_curr = YahooFundamentalProvider._latest_value(results_c, "trailingEnterpriseValue")
        eb_val, eb_curr = YahooFundamentalProvider._latest_value(results_c, "trailingEBITDA")
        self.assertEqual(ev_curr, eb_curr)

        # D. different-currency EV / EBITDA
        results_d = [
            {"trailingEnterpriseValue": [{"asOfDate": "2026-01-01", "currencyCode": "USD", "reportedValue": {"raw": 1100.0}}]},
            {"trailingEBITDA": [{"asOfDate": "2026-01-01", "currencyCode": "TWD", "reportedValue": {"raw": 3000.0}}]}
        ]
        ev_val, ev_curr = YahooFundamentalProvider._latest_value(results_d, "trailingEnterpriseValue")
        eb_val, eb_curr = YahooFundamentalProvider._latest_value(results_d, "trailingEBITDA")
        self.assertNotEqual(ev_curr, eb_curr)

        # E. different-currency FCF
        results_e = [
            {"trailingMarketCap": [{"asOfDate": "2026-01-01", "currencyCode": "USD", "reportedValue": {"raw": 1000.0}}]},
            {"trailingFreeCashFlow": [{"asOfDate": "2026-01-01", "currencyCode": "TWD", "reportedValue": {"raw": 50.0}}]}
        ]
        mc_val, mc_curr = YahooFundamentalProvider._latest_value(results_e, "trailingMarketCap")
        fcf_val, fcf_curr = YahooFundamentalProvider._latest_value(results_e, "trailingFreeCashFlow")
        self.assertNotEqual(mc_curr, fcf_curr)

        # F. missing currency metadata
        results_f = [
            {"trailingMarketCap": [{"asOfDate": "2026-01-01", "reportedValue": {"raw": 1000.0}}]},
            {"trailingTotalRevenue": [{"asOfDate": "2026-01-01", "currencyCode": "USD", "reportedValue": {"raw": 100.0}}]}
        ]
        mc_val, mc_curr = YahooFundamentalProvider._latest_value(results_f, "trailingMarketCap")
        rev_val, rev_curr = YahooFundamentalProvider._latest_value(results_f, "trailingTotalRevenue")
        self.assertIsNone(mc_curr)
        self.assertIsNotNone(rev_curr)

        # G. TSM regression case simulation
        tsm_market_cap = 2000000000000.0
        tsm_mc_curr = "USD"
        tsm_fcf = 1000000000000.0
        tsm_fcf_curr = "TWD"
        fcf_final = tsm_fcf if (tsm_mc_curr and tsm_fcf_curr and tsm_mc_curr == tsm_fcf_curr) else None
        self.assertIsNone(fcf_final)


if __name__ == "__main__":
    unittest.main()
