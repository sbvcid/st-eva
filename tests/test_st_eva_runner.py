import io
import unittest

from st_eva_runner import (
    CompanyResolver,
    MarketImpliedAssumptionsEngine,
    build_evidence,
    run_st_eva,
)
from fundamental_provider import FundamentalData, YahooFundamentalProvider
from llm_interpreter import build_interpretation_prompt
from report_formatter import (
    _display_width,
    normalize_ticker,
    render_report,
)



class TestReportFormatter(unittest.TestCase):
    def test_display_width_counts_cjk_as_two_columns(self):
        self.assertEqual(_display_width("abc"), 3)
        self.assertEqual(_display_width("隱含"), 4)
        self.assertEqual(_display_width("P/E"), 3)

    def test_normalize_ticker_resolves_known_aliases(self):
        self.assertEqual(normalize_ticker("apple"), "AAPL")
        self.assertEqual(normalize_ticker("騰訊"), "0700.HK")
        self.assertEqual(normalize_ticker("台積電"), "2330.TW")

    def test_normalize_ticker_does_not_invent_mappings(self):
        # Unknown input must pass through so it fails loudly.
        self.assertEqual(normalize_ticker("ZZZZ_NOT_REAL"), "ZZZZ_NOT_REAL")

    def test_report_renders_without_arithmetic(self):
        result = run_st_eva(
            "MSFT",
            mode="regression",
            reference_multiple=30.0,
            save_snapshot=False,
        )
        report = render_report(result)
        # The implied EPS from the engine must appear verbatim.
        self.assertIn("14.1833", report)
        self.assertIn("425.50", report)
        self.assertIn("user_supplied_multiple", report)
        self.assertIn("樣本數未驗證", report)

    def test_report_declares_no_reference_when_multiple_missing(self):
        result = run_st_eva(
            "MSFT", mode="regression", save_snapshot=False
        )
        result["reference"]["method"] = "none"
        result["reference"]["multiple"] = None
        result["market_implied_assumptions"]["forward_eps_at_reference_multiple"] = None
        report = render_report(result)
        self.assertIn("無參考倍數", report)
        self.assertIn("--reference-multiple", report)

    def test_report_distinguishes_unverified_sample_count(self):
        result = run_st_eva(
            "MSFT", mode="regression", save_snapshot=False
        )
        result["reference"]["historical_band_status"]["pe"] = (
            "DESCRIPTIVE_ONLY_UNVERIFIED_SAMPLE_COUNT"
        )
        report = render_report(result)
        self.assertIn("樣本數未驗證", report)
        self.assertIn("樣本數未宣告或無效", report)

    def test_report_flags_insufficient_observations(self):
        result = run_st_eva(
            "MSFT", mode="regression", save_snapshot=False
        )
        result["reference"]["historical_band_status"]["pe"] = (
            "DESCRIPTIVE_ONLY_INSUFFICIENT_OBSERVATIONS"
        )
        report = render_report(result)
        self.assertIn("觀測數不足未被採用為參考", report)

    def test_report_never_emits_target_price_or_stance(self):
        result = run_st_eva(
            "TENCENT", mode="regression", save_snapshot=False
        )
        report = render_report(result)
        for forbidden in ("目標價", "買進", "賣出", "目標價", "偏多", "觀望"):
            self.assertNotIn(forbidden, report)

    def test_report_handles_unicode_stream(self):
        result = run_st_eva(
            "TENCENT", mode="regression", save_snapshot=False
        )
        buffer = io.StringIO()
        from report_formatter import print_report
        print_report(result, stream=buffer)
        self.assertIn("0700.HK", buffer.getvalue())

    def test_report_is_deterministic(self):
        result = run_st_eva(
            "MSFT", mode="regression", save_snapshot=False
        )
        self.assertEqual(render_report(result), render_report(result))



class TestMarketImpliedAssumptions(unittest.TestCase):
    def test_thin_historical_band_is_not_used_as_reference(self):
        # A band with too few observations must not become the reference
        # multiple, and must not produce a percentile reading.
        data = CompanyResolver.resolve("MSFT", mode="regression")
        data.historical_pe_band = {
            "10th": 10.0,
            "25th": 15.0,
            "median": 20.0,
            "75th": 30.0,
            "90th": 40.0,
            "observations": 8,
        }
        result = MarketImpliedAssumptionsEngine.analyze(data)
        self.assertIsNone(result["reference"]["multiple"])
        self.assertEqual(result["reference"]["method"], "none")
        self.assertIsNone(
            result["observed_valuation"]["approx_historical_pe_percentile"]
        )
        self.assertEqual(
            result["reference"]["historical_band_status"]["pe"],
            "DESCRIPTIVE_ONLY_INSUFFICIENT_OBSERVATIONS",
        )
        self.assertIsNone(
            result["implied_assumptions"]["forward_eps_at_reference_multiple"]
        )

    def test_undeclared_historical_band_sample_count_is_not_used_as_reference(self):
        data = CompanyResolver.resolve("MSFT", mode="regression")
        data.historical_pe_band = {
            "10th": 10.0,
            "25th": 15.0,
            "median": 20.0,
            "75th": 30.0,
            "90th": 40.0,
        }
        result = MarketImpliedAssumptionsEngine.analyze(data)
        self.assertIsNone(result["reference"]["multiple"])
        self.assertEqual(result["reference"]["method"], "none")
        self.assertEqual(
            result["reference"]["historical_band_status"]["pe"],
            "DESCRIPTIVE_ONLY_UNVERIFIED_SAMPLE_COUNT",
        )
        self.assertIsNone(
            result["observed_valuation"]["approx_historical_pe_percentile"]
        )

    def test_adequate_historical_band_is_used_as_reference(self):
        data = CompanyResolver.resolve("MSFT", mode="regression")
        data.historical_pe_band = {
            "10th": 10.0,
            "25th": 15.0,
            "median": 20.0,
            "75th": 30.0,
            "90th": 40.0,
            "observations": 120,
        }
        result = MarketImpliedAssumptionsEngine.analyze(data)
        self.assertEqual(result["reference"]["method"], "historical_pe_median")
        self.assertEqual(result["reference"]["multiple"], 20.0)
        self.assertEqual(
            result["reference"]["historical_band_status"]["pe"],
            "USABLE_FOR_REFERENCE",
        )

    def test_user_supplied_multiple_overrides_thin_band(self):
        data = CompanyResolver.resolve("MSFT", mode="regression")
        data.historical_pe_band = {
            "10th": 10.0, "25th": 15.0, "median": 20.0,
            "75th": 30.0, "90th": 40.0, "observations": 5,
        }
        result = MarketImpliedAssumptionsEngine.analyze(
            data, reference_multiple=30.0
        )
        self.assertEqual(result["reference"]["multiple"], 30.0)
        self.assertEqual(result["reference"]["method"], "user_supplied_multiple")
        self.assertAlmostEqual(
            result["implied_assumptions"]["forward_eps_at_reference_multiple"],
            425.50 / 30.0,
            places=10,
        )

    def test_fundamental_provider_survives_timeseries_failure(self):
        # Regression: pfcf_band was unbound when the valuation timeseries
        # request failed, which crashed the whole acquisition.
        class FailingProvider(YahooFundamentalProvider):
            def _bootstrap_crumb(self):
                return "fake_crumb"

            def _quote_summary(self, ticker, crumb):
                return {"quoteSummary": {"result": []}}

            def _timeseries(self, ticker, types, years=5):
                raise Exception("timeseries unavailable")

        data = FailingProvider().fetch("AAPL")
        self.assertEqual(data.historical_pfcf_band, {})
        self.assertEqual(data.historical_pe_band, {})
        self.assertTrue(data.errors)

    def test_all_band_evidence_uses_multiple_unit(self):
        data = CompanyResolver.resolve("MSFT", mode="regression")
        data.historical_pe_band = {
            "10th": 22.0, "25th": 26.0, "median": 30.0,
            "75th": 34.0, "90th": 38.0, "observations": 4,
        }
        data.historical_ps_band = {"10th": 3.0, "median": 5.0, "observations": 2}
        data.historical_pfcf_band = {"10th": 12.0, "median": 20.0, "observations": 2}
        data.historical_ev_ebitda_band = {
            "10th": 8.0, "median": 14.0, "observations": 2,
        }
        data.current_fcf = 10.0
        metrics = {
            "observations": 2, "return_1d": None, "return_5d": None,
            "return_20d": None, "return_60d": None,
            "realized_volatility_annualized": None,
            "average_volume": 1.0, "latest_volume_vs_average": None,
        }
        store = build_evidence(data, metrics).as_dict()
        for evidence_id in (
            "ev-pe-band-001", "ev-pfcf-band-001",
            "ev-ps-band-001", "ev-ev-ebitda-band-001",
        ):
            self.assertEqual(store[evidence_id]["unit"], "multiple")
        self.assertEqual(store["ev-fcf-001"]["unit"], "USD")

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
            (4.0, "+1y", None),
        )

    def test_consensus_extraction_preserves_the_declared_period_end(self):
        # The third element is the fiscal-period end the same source row
        # declared. It is the only period boundary the source states, so it is
        # carried verbatim and never derived from the "+1y" label.
        trend = {
            "trend": [
                {"period": "0q", "earningsEstimate": {"avg": 1.0}},
                {
                    "period": "+1y",
                    "earningsEstimate": {"avg": 23.67732},
                    "endDate": "2028-06-30",
                },
            ]
        }
        self.assertEqual(
            YahooFundamentalProvider._extract_consensus_forward_eps(trend),
            (23.67732, "+1y", "2028-06-30"),
        )

    def test_consensus_extraction_keeps_the_winning_row_s_declared_end(self):
        # The declared end travels with the row that wins the existing
        # priority, not with the row that happens to declare a date.
        trend = {
            "trend": [
                {
                    "period": "0y",
                    "earningsEstimate": {"avg": 2.0},
                    "endDate": "2027-06-30",
                },
                {
                    "period": "+1y",
                    "earningsEstimate": {"avg": 4.0},
                    "endDate": "2028-06-30",
                },
            ]
        }
        self.assertEqual(
            YahooFundamentalProvider._extract_consensus_forward_eps(trend),
            (4.0, "+1y", "2028-06-30"),
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
            (4.0, "+1y", None),
        )

    def test_consensus_extraction_leaves_an_unreadable_end_undeclared(self):
        # A date the source cannot state as a calendar date is not a date to
        # repair from the label; the end simply stays undeclared.
        for bad in ("not-a-date", "   ", None, 20280630):
            with self.subTest(endDate=bad):
                trend = {
                    "trend": [
                        {
                            "period": "+1y",
                            "earningsEstimate": {"avg": 4.0},
                            "endDate": bad,
                        }
                    ]
                }
                self.assertEqual(
                    YahooFundamentalProvider._extract_consensus_forward_eps(
                        trend
                    ),
                    (4.0, "+1y", None),
                )


    def test_historical_pe_percentile_uses_full_band(self):
        data = CompanyResolver.resolve("MSFT", mode="regression")
        data.historical_pe_band = {
            "10th": 10.0,
            "25th": 15.0,
            "median": 20.0,
            "75th": 30.0,
            "90th": 40.0,
            "observations": 120,
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
            "75th": 6.0, "90th": 7.0, "observations": 120,
        }
        data.historical_ev_ebitda_band = {
            "10th": 10.0, "25th": 12.0, "median": 15.0,
            "75th": 18.0, "90th": 20.0, "observations": 120,
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
        val_mc, curr_mc, as_of_mc = YahooFundamentalProvider._latest_value(results_a, "trailingMarketCap")
        val_rev, curr_rev, as_of_rev = YahooFundamentalProvider._latest_value(results_a, "trailingTotalRevenue")
        self.assertEqual(curr_mc, curr_rev)

        # B. different-currency Market Cap / Revenue (USD vs TWD)
        results_b = [
            {"trailingMarketCap": [{"asOfDate": "2026-01-01", "currencyCode": "USD", "reportedValue": {"raw": 1000.0}}]},
            {"trailingTotalRevenue": [{"asOfDate": "2026-01-01", "currencyCode": "TWD", "reportedValue": {"raw": 3000.0}}]}
        ]
        mc_val, mc_curr, mc_as_of = YahooFundamentalProvider._latest_value(results_b, "trailingMarketCap")
        rev_val, rev_curr, rev_as_of = YahooFundamentalProvider._latest_value(results_b, "trailingTotalRevenue")
        self.assertNotEqual(mc_curr, rev_curr)

        # C. same-currency EV / EBITDA
        results_c = [
            {"trailingEnterpriseValue": [{"asOfDate": "2026-01-01", "currencyCode": "USD", "reportedValue": {"raw": 1100.0}}]},
            {"trailingEBITDA": [{"asOfDate": "2026-01-01", "currencyCode": "USD", "reportedValue": {"raw": 100.0}}]}
        ]
        ev_val, ev_curr, ev_as_of = YahooFundamentalProvider._latest_value(results_c, "trailingEnterpriseValue")
        eb_val, eb_curr, eb_as_of = YahooFundamentalProvider._latest_value(results_c, "trailingEBITDA")
        self.assertEqual(ev_curr, eb_curr)

        # D. different-currency EV / EBITDA
        results_d = [
            {"trailingEnterpriseValue": [{"asOfDate": "2026-01-01", "currencyCode": "USD", "reportedValue": {"raw": 1100.0}}]},
            {"trailingEBITDA": [{"asOfDate": "2026-01-01", "currencyCode": "TWD", "reportedValue": {"raw": 3000.0}}]}
        ]
        ev_val, ev_curr, ev_as_of = YahooFundamentalProvider._latest_value(results_d, "trailingEnterpriseValue")
        eb_val, eb_curr, eb_as_of = YahooFundamentalProvider._latest_value(results_d, "trailingEBITDA")
        self.assertNotEqual(ev_curr, eb_curr)

        # E. different-currency FCF
        results_e = [
            {"trailingMarketCap": [{"asOfDate": "2026-01-01", "currencyCode": "USD", "reportedValue": {"raw": 1000.0}}]},
            {"trailingFreeCashFlow": [{"asOfDate": "2026-01-01", "currencyCode": "TWD", "reportedValue": {"raw": 50.0}}]}
        ]
        mc_val, mc_curr, mc_as_of = YahooFundamentalProvider._latest_value(results_e, "trailingMarketCap")
        fcf_val, fcf_curr, fcf_as_of = YahooFundamentalProvider._latest_value(results_e, "trailingFreeCashFlow")
        self.assertNotEqual(mc_curr, fcf_curr)

        # F. missing currency metadata
        results_f = [
            {"trailingMarketCap": [{"asOfDate": "2026-01-01", "reportedValue": {"raw": 1000.0}}]},
            {"trailingTotalRevenue": [{"asOfDate": "2026-01-01", "currencyCode": "USD", "reportedValue": {"raw": 100.0}}]}
        ]
        mc_val, mc_curr, mc_as_of = YahooFundamentalProvider._latest_value(results_f, "trailingMarketCap")
        rev_val, rev_curr, rev_as_of = YahooFundamentalProvider._latest_value(results_f, "trailingTotalRevenue")
        self.assertIsNone(mc_curr)
        self.assertIsNotNone(rev_curr)

        # G. TSM regression case simulation
        tsm_market_cap = 2000000000000.0
        tsm_mc_curr = "USD"
        tsm_fcf = 1000000000000.0
        tsm_fcf_curr = "TWD"
        fcf_final = tsm_fcf if (tsm_mc_curr and tsm_fcf_curr and tsm_mc_curr == tsm_fcf_curr) else None
        self.assertIsNone(fcf_final)


    def test_fundamental_provider_collects_errors(self):
        class FailingProvider(YahooFundamentalProvider):
            def _bootstrap_crumb(self):
                return "fake_crumb"
            def _quote_summary(self, ticker, crumb):
                raise Exception("Network failure")

        provider = FailingProvider()
        data = provider.fetch("MSFT")
        self.assertTrue(len(data.errors) > 0)
        self.assertTrue(any("Network failure" in e for e in data.errors))
        self.assertEqual(data.current_eps, "UNAVAILABLE")



if __name__ == "__main__":
    unittest.main()


class TestMUFGFxRate(unittest.TestCase):
    """Isolated tests for MUFG FX rate conversion (fx_rates.py)."""

    def test_mufg_fx_rate_is_sourced_not_illustrative(self):
        from fx_rates import MUFG_FX_RATE_USD_PER_JPY
        self.assertIsNotNone(MUFG_FX_RATE_USD_PER_JPY)
        self.assertEqual(MUFG_FX_RATE_USD_PER_JPY.provider, "Federal Reserve Board H.10")
        self.assertEqual(MUFG_FX_RATE_USD_PER_JPY.quote_direction, "USD per JPY")
        # Rate must be ~0.006316 (1/158.34), not the old illustrative 0.0067.
        self.assertAlmostEqual(MUFG_FX_RATE_USD_PER_JPY.rate_usd_per_jpy, 0.006316, places=6)
        # The old 0.0067 implied ~149 JPY/USD; actual H.10 rate is ~158 JPY/USD.
        self.assertNotEqual(MUFG_FX_RATE_USD_PER_JPY.rate_usd_per_jpy, 0.0067)
        self.assertIn("158.3400", MUFG_FX_RATE_USD_PER_JPY.original_amounts["note"])
        self.assertNotIn("illustrative", MUFG_FX_RATE_USD_PER_JPY.original_amounts["note"].lower())

    def test_convert_jpy_to_usd_uses_corrected_rate(self):
        from fx_rates import MUFG_FX_RATE_USD_PER_JPY, convert_jpy_to_usd
        jpy = 1583400000000.0  # ¥1.5834T
        usd = convert_jpy_to_usd(jpy, MUFG_FX_RATE_USD_PER_JPY)
        # ¥1.5834T × 0.006316 USD/JPY = $10,000,754,400
        self.assertAlmostEqual(usd, 10000754400.0, places=0)

    def test_convert_usd_to_jpy_uses_corrected_rate(self):
        from fx_rates import MUFG_FX_RATE_USD_PER_JPY, convert_usd_to_jpy
        usd = 10000000000.0  # $10B
        jpy = convert_usd_to_jpy(usd, MUFG_FX_RATE_USD_PER_JPY)
        # $10B / 0.006316 USD/JPY ≈ ¥1.5833T
        self.assertAlmostEqual(jpy, 1583280557314.756, places=0)


class TestMUFGAdrRatio(unittest.TestCase):
    """Isolated tests for MUFG ADR ratio (adr_ratio.py)."""

    def test_mufg_adr_ratio_is_one_to_one_per_nyse(self):
        from adr_ratio import MUFG_ADR_RATIO
        self.assertIsNotNone(MUFG_ADR_RATIO)
        self.assertEqual(MUFG_ADR_RATIO.provider, "NYSE")
        self.assertEqual(MUFG_ADR_RATIO.exchange, "NYSE")
        # NYSE listing: "EACH REP 1 ORD SHS" → 1 ADR = 1 ordinary share.
        self.assertEqual(MUFG_ADR_RATIO.underlying_shares_per_adr, 1.0)
        # The old incorrect 2.0 shares/ADR must not be used.
        self.assertNotEqual(MUFG_ADR_RATIO.underlying_shares_per_adr, 2.0)
        self.assertIn("EACH REP 1 ORD SHS", MUFG_ADR_RATIO.original_amounts["note"])
        self.assertNotIn("÷ 2", MUFG_ADR_RATIO.original_amounts["note"])

    def test_adr_price_to_underlying_usd_uses_one_to_one(self):
        from adr_ratio import MUFG_ADR_RATIO, adr_price_to_underlying_usd
        # $21.88 ADR price ÷ 1.0 = $21.88 underlying share price (USD)
        underlying = adr_price_to_underlying_usd(21.88, MUFG_ADR_RATIO)
        self.assertAlmostEqual(underlying, 21.88, places=4)

    def test_underlying_usd_to_jpy_uses_corrected_fx(self):
        from adr_ratio import MUFG_ADR_RATIO, underlying_usd_to_jpy
        from fx_rates import MUFG_FX_RATE_USD_PER_JPY
        # $21.88 / 0.006316 USD/JPY ≈ ¥3,464
        jpy = underlying_usd_to_jpy(21.88, MUFG_FX_RATE_USD_PER_JPY)
        self.assertAlmostEqual(jpy, 3464.22, places=0)


class TestMUFGFxRateAnalysisDate(unittest.TestCase):
    """Isolated tests for MUFG analysis-date FX rate (fx_rates.py)."""

    def test_mufg_fx_rate_analysis_date_is_ecb_derived(self):
        from fx_rates import MUFG_FX_RATE_ANALYSIS_DATE_USD_PER_JPY
        self.assertIsNotNone(MUFG_FX_RATE_ANALYSIS_DATE_USD_PER_JPY)
        self.assertEqual(MUFG_FX_RATE_ANALYSIS_DATE_USD_PER_JPY.provider, "European Central Bank (ECB)")
        self.assertEqual(MUFG_FX_RATE_ANALYSIS_DATE_USD_PER_JPY.as_of, "2026-10-16")
        self.assertEqual(MUFG_FX_RATE_ANALYSIS_DATE_USD_PER_JPY.quote_direction, "USD per JPY")
        # ECB-derived rate: 1 EUR = 1.1253 USD, 1 EUR = 177.82 JPY
        # => USD/JPY = 1.1253 / 177.82 = 0.0063283095...
        expected_rate = 1.1253 / 177.82
        self.assertAlmostEqual(
            MUFG_FX_RATE_ANALYSIS_DATE_USD_PER_JPY.rate_usd_per_jpy,
            expected_rate,
            places=10,
        )
        # Distinct from fiscal-period H.10 rate (0.006316)
        from fx_rates import MUFG_FX_RATE_USD_PER_JPY
        self.assertNotEqual(
            MUFG_FX_RATE_ANALYSIS_DATE_USD_PER_JPY.rate_usd_per_jpy,
            MUFG_FX_RATE_USD_PER_JPY.rate_usd_per_jpy,
        )
        self.assertIn("1.1253", MUFG_FX_RATE_ANALYSIS_DATE_USD_PER_JPY.original_amounts["note"])
        self.assertIn("177.82", MUFG_FX_RATE_ANALYSIS_DATE_USD_PER_JPY.original_amounts["note"])
        self.assertIn("2026-10-16", MUFG_FX_RATE_ANALYSIS_DATE_USD_PER_JPY.original_amounts["note"])

    def test_analysis_date_rate_not_disguised_as_fiscal_period(self):
        from fx_rates import (
            MUFG_FX_RATE_ANALYSIS_DATE_USD_PER_JPY,
            MUFG_FX_RATE_USD_PER_JPY,
        )
        # The analysis-date rate (2026-10-16) must not have the fiscal-period
        # H.10 date (2026-10-09) or provider.
        self.assertNotEqual(
            MUFG_FX_RATE_ANALYSIS_DATE_USD_PER_JPY.as_of, "2026-10-09"
        )
        self.assertNotEqual(
            MUFG_FX_RATE_ANALYSIS_DATE_USD_PER_JPY.provider,
            "Federal Reserve Board H.10",
        )
        # The fiscal-period rate must not have the analysis-date date.
        self.assertNotEqual(
            MUFG_FX_RATE_USD_PER_JPY.as_of, "2026-10-16"
        )
        self.assertNotEqual(
            MUFG_FX_RATE_USD_PER_JPY.provider,
            "European Central Bank (ECB)",
        )


class TestMUFGAdrRatio(unittest.TestCase):
    """Isolated tests for MUFG ADR ratio (adr_ratio.py)."""

    def test_mufg_adr_ratio_is_one_to_one_per_nyse(self):
        from adr_ratio import MUFG_ADR_RATIO
        self.assertIsNotNone(MUFG_ADR_RATIO)
        self.assertEqual(MUFG_ADR_RATIO.provider, "NYSE")
        self.assertEqual(MUFG_ADR_RATIO.exchange, "NYSE")
        # NYSE listing: "EACH REP 1 ORD SHS" → 1 ADR = 1 ordinary share.
        self.assertEqual(MUFG_ADR_RATIO.underlying_shares_per_adr, 1.0)
        # The old incorrect 2.0 shares/ADR must not be used.
        self.assertNotEqual(MUFG_ADR_RATIO.underlying_shares_per_adr, 2.0)
        self.assertIn("EACH REP 1 ORD SHS", MUFG_ADR_RATIO.original_amounts["note"])
        self.assertNotIn("÷ 2", MUFG_ADR_RATIO.original_amounts["note"])

    def test_adr_price_to_underlying_usd_uses_one_to_one(self):
        from adr_ratio import MUFG_ADR_RATIO, adr_price_to_underlying_usd
        # $21.88 ADR price ÷ 1.0 = $21.88 underlying share price (USD)
        underlying = adr_price_to_underlying_usd(21.88, MUFG_ADR_RATIO)
        self.assertAlmostEqual(underlying, 21.88, places=4)

    def test_underlying_usd_to_jpy_uses_corrected_fx(self):
        from adr_ratio import MUFG_ADR_RATIO, underlying_usd_to_jpy
        from fx_rates import MUFG_FX_RATE_USD_PER_JPY
        # $21.88 / 0.006316 USD/JPY ≈ ¥3,464
        jpy = underlying_usd_to_jpy(21.88, MUFG_FX_RATE_USD_PER_JPY)
        self.assertAlmostEqual(jpy, 3464.22, places=0)


class TestMUFGCrossCurrencyAnalysis(unittest.TestCase):
    """End-to-end MUFG cross-currency analysis with two FX scopes."""

    def test_mufg_cross_currency_two_fx_scopes(self):
        result = run_st_eva(
            ticker="MUFG",
            mode="auto",
            fx_rate_usd_per_jpy=0.006316,
            fx_analysis_date_usd_per_jpy=1.1253 / 177.82,
            adr_underlying_shares_per_adr=1.0,
            save_snapshot=False,
        )
        self.assertIsNotNone(result)
        cc = result["cross_currency"]
        self.assertTrue(cc["applicable"])

        # Historical reference FX rate (Fed H.10, 2026-10-09) - reference only.
        self.assertIsNotNone(cc["fx_rate_fiscal_period"])
        fp = cc["fx_rate_fiscal_period"]
        self.assertAlmostEqual(fp["rate_usd_per_jpy"], 0.006316, places=6)
        self.assertEqual(fp["as_of"], "2026-10-09")
        self.assertEqual(fp["provider"], "operator-supplied")
        self.assertEqual(fp["scope"], "reference_only")
        self.assertNotIn("analysis_date", fp["note"].lower())

        # Analysis-date FX rate (ECB, 2026-10-16) - used for conversions.
        self.assertIsNotNone(cc["fx_rate_analysis_date"])
        ad = cc["fx_rate_analysis_date"]
        expected_rate = 1.1253 / 177.82
        self.assertAlmostEqual(ad["rate_usd_per_jpy"], expected_rate, places=10)
        self.assertEqual(ad["as_of"], "2026-10-16")
        self.assertEqual(ad["provider"], "European Central Bank (ECB)")
        self.assertEqual(ad["scope"], "analysis_date")
        self.assertIn("1.1253", ad["note"])
        self.assertIn("177.82", ad["note"])

        # ADR ratio must be 1.0 per NYSE listing.
        self.assertIsNotNone(cc["adr_ratio"])
        self.assertEqual(cc["adr_ratio"]["underlying_shares_per_adr"], 1.0)
        self.assertEqual(cc["adr_ratio"]["provider"], "operator-supplied")

        # Revenue conversion uses analysis-date rate.
        self.assertIsNotNone(cc["revenue_conversion"])
        rev = cc["revenue_conversion"]
        self.assertAlmostEqual(rev["fx_rate_used"], expected_rate, places=10)
        self.assertEqual(rev["fx_scope"], "analysis_date")
        self.assertEqual(rev["fx_as_of"], "2026-10-16")
        self.assertIsNotNone(rev["ps_ratio_usd_converted"])
        # The raw JPY/USD P/S 0.03x must NOT be reported as valid.
        self.assertNotAlmostEqual(rev["ps_ratio_usd_converted"], 0.03, places=2)

        # EPS conversion uses analysis-date rate.
        self.assertIsNotNone(cc["eps_conversion"])
        eps = cc["eps_conversion"]
        self.assertAlmostEqual(eps["fx_rate_used"], expected_rate, places=10)
        self.assertEqual(eps["fx_scope"], "analysis_date")
        self.assertEqual(eps["fx_as_of"], "2026-10-16")
        self.assertEqual(eps["adr_ratio_used"], 1.0)
        # With 1:1 ADR, EPS per share == EPS per ADR.
        self.assertAlmostEqual(
            eps["eps_usd_per_share_converted"],
            eps["eps_usd_per_adr_converted"],
            places=4,
        )

        # Derived EPS labelled annual, not TTM.
        self.assertIsNotNone(cc["ttm_eps"])
        self.assertIn("not true TTM", cc["ttm_eps"]["basis"])

        # Corporate targets shown separately from EPS, not converted to growth rate.
        self.assertIsNotNone(cc["corporate_target_comparison"])
        tgt = cc["corporate_target_comparison"]
        self.assertAlmostEqual(tgt["fx_rate_used"], expected_rate, places=10)
        self.assertEqual(tgt["fx_scope"], "analysis_date")
        self.assertIsNotNone(tgt["net_income_fy2025_actual_usd"])
        self.assertIsNotNone(tgt["net_income_target_fy2026_usd"])
        self.assertIn("NOT converted to an EPS growth rate", tgt["note"])

    def test_mufg_fiscal_period_rate_not_used_for_conversions(self):
        """When both rates are provided, conversions use the analysis-date
        rate, not the fiscal-period rate."""
        result = run_st_eva(
            ticker="MUFG",
            mode="auto",
            fx_rate_usd_per_jpy=0.006316,
            fx_analysis_date_usd_per_jpy=1.1253 / 177.82,
            adr_underlying_shares_per_adr=1.0,
            save_snapshot=False,
        )
        self.assertIsNotNone(result)
        cc = result["cross_currency"]
        # Both rates present in output.
        self.assertIsNotNone(cc["fx_rate_fiscal_period"])
        self.assertIsNotNone(cc["fx_rate_analysis_date"])
        # Conversions use analysis-date rate (0.0063283095), not historical reference (0.006316).
        self.assertAlmostEqual(
            cc["revenue_conversion"]["fx_rate_used"],
            1.1253 / 177.82,
            places=10,
        )
        self.assertNotAlmostEqual(
            cc["revenue_conversion"]["fx_rate_used"],
            0.006316,
            places=6,
        )

    def test_mufg_fallback_to_reference_only_when_no_analysis_date(self):
        """When only historical reference rate is provided, conversions use it."""
        result = run_st_eva(
            ticker="MUFG",
            mode="auto",
            fx_rate_usd_per_jpy=0.006316,
            adr_underlying_shares_per_adr=1.0,
            save_snapshot=False,
        )
        self.assertIsNotNone(result)
        cc = result["cross_currency"]
        self.assertIsNotNone(cc["fx_rate_fiscal_period"])
        self.assertIsNone(cc["fx_rate_analysis_date"])
        # Conversions fall back to historical reference rate.
        self.assertAlmostEqual(
            cc["revenue_conversion"]["fx_rate_used"],
            0.006316,
            places=6,
        )
        self.assertEqual(cc["revenue_conversion"]["fx_scope"], "reference_only")

    def test_mufg_historical_pe_insufficient_observations(self):
        """Historical P/E band has 8 observations (< 20) → UNAVAILABLE."""
        result = run_st_eva(
            ticker="MUFG",
            mode="auto",
            fx_rate_usd_per_jpy=0.006316,
            fx_analysis_date_usd_per_jpy=1.1253 / 177.82,
            adr_underlying_shares_per_adr=1.0,
            include_historical_pe=True,
            save_snapshot=False,
        )
        self.assertIsNotNone(result)
        ref = result["reference"]
        self.assertEqual(ref["production_historical_pe_status"], "UNAVAILABLE")
        self.assertEqual(ref["min_observations_for_reference"], 20)

    def test_mufg_reverse_requirements_not_computed_without_user_multiple(self):
        """No user-supplied exit multiple → reverse requirements NOT_COMPUTED."""
        result = run_st_eva(
            ticker="MUFG",
            mode="auto",
            fx_rate_usd_per_jpy=0.006316,
            fx_analysis_date_usd_per_jpy=1.1253 / 177.82,
            adr_underlying_shares_per_adr=1.0,
            save_snapshot=False,
        )
        self.assertIsNotNone(result)
        rr = result["reverse_requirements"]
        self.assertEqual(rr["status"], "NOT_COMPUTED")


class TestMUFGRegressionDatesAndPrecision(unittest.TestCase):
    """Regression tests for FX date, quote direction, precision, and ADR ratio."""

    def test_analysis_date_is_2026_10_16_not_2026_10_09(self):
        from fx_rates import MUFG_FX_RATE_ANALYSIS_DATE_USD_PER_JPY
        self.assertEqual(MUFG_FX_RATE_ANALYSIS_DATE_USD_PER_JPY.as_of, "2026-10-16")

    def test_fiscal_period_date_is_2026_10_09(self):
        from fx_rates import MUFG_FX_RATE_USD_PER_JPY
        self.assertEqual(MUFG_FX_RATE_USD_PER_JPY.as_of, "2026-10-09")

    def test_quote_direction_is_usd_per_jpy(self):
        from fx_rates import MUFG_FX_RATE_ANALYSIS_DATE_USD_PER_JPY, MUFG_FX_RATE_USD_PER_JPY
        self.assertEqual(
            MUFG_FX_RATE_ANALYSIS_DATE_USD_PER_JPY.quote_direction, "USD per JPY"
        )
        self.assertEqual(MUFG_FX_RATE_USD_PER_JPY.quote_direction, "USD per JPY")

    def test_ecb_rate_carries_unrounded_value(self):
        from fx_rates import MUFG_FX_RATE_ANALYSIS_DATE_USD_PER_JPY
        # Rate computed as 1.1253 / 177.82, not rounded to 4 decimal places.
        expected = 1.1253 / 177.82
        self.assertAlmostEqual(
            MUFG_FX_RATE_ANALYSIS_DATE_USD_PER_JPY.rate_usd_per_jpy,
            expected,
            places=12,
        )
        # Rounded display value (0.0063) must not equal the unrounded input.
        self.assertNotEqual(
            round(MUFG_FX_RATE_ANALYSIS_DATE_USD_PER_JPY.rate_usd_per_jpy, 4),
            MUFG_FX_RATE_ANALYSIS_DATE_USD_PER_JPY.rate_usd_per_jpy,
        )

    def test_adr_ratio_is_one_to_one_not_two_to_one(self):
        from adr_ratio import MUFG_ADR_RATIO
        self.assertEqual(MUFG_ADR_RATIO.underlying_shares_per_adr, 1.0)
        self.assertNotEqual(MUFG_ADR_RATIO.underlying_shares_per_adr, 2.0)


class TestMUFGCrossCurrencyPsRejection(unittest.TestCase):
    """Regression tests: cross-currency P/S must be refused, not computed."""

    def test_mufg_cross_currency_ps_is_none_not_0_03x(self):
        """MUFG market cap (USD) / revenue (JPY) must NOT produce 0.03x P/S."""
        from fx_rates import mufg_fx_rate_analysis_date
        from adr_ratio import mufg_adr_ratio

        fx = mufg_fx_rate_analysis_date()
        adr = mufg_adr_ratio()

        result = run_st_eva(
            ticker="MUFG",
            mode="auto",
            fx_rate_usd_per_jpy=0.006316,
            fx_analysis_date_usd_per_jpy=fx.rate_usd_per_jpy,
            adr_underlying_shares_per_adr=adr.underlying_shares_per_adr,
            save_snapshot=False,
        )
        self.assertIsNotNone(result)
        obs = result["observed_valuation"]
        # Mixed-currency P/S must be refused, not computed.
        self.assertIsNone(obs["current_ps"])
        # The cross-currency section must still carry the converted figure.
        cc = result["cross_currency"]
        self.assertIsNotNone(cc["revenue_conversion"])
        self.assertAlmostEqual(
            cc["revenue_conversion"]["ps_ratio_usd_converted"], 5.20, places=1
        )

    def test_mufg_cross_currency_ps_limitation(self):
        """When P/S is refused due to currency mismatch, a limitation is added."""
        from fx_rates import mufg_fx_rate_analysis_date
        from adr_ratio import mufg_adr_ratio

        fx = mufg_fx_rate_analysis_date()
        adr = mufg_adr_ratio()

        result = run_st_eva(
            ticker="MUFG",
            mode="auto",
            fx_rate_usd_per_jpy=0.006316,
            fx_analysis_date_usd_per_jpy=fx.rate_usd_per_jpy,
            adr_underlying_shares_per_adr=adr.underlying_shares_per_adr,
            save_snapshot=False,
        )
        self.assertIsNotNone(result)
        limitations = result.get("limitations", [])
        ps_limitations = [
            l for l in limitations if "P/S not reported" in l
        ]
        self.assertEqual(len(ps_limitations), 1)
        self.assertIn("currency", ps_limitations[0].lower())


if __name__ == "__main__":
    unittest.main()
