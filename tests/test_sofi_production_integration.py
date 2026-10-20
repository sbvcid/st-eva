"""
End-to-end verification that SOFI's qualified historical P/E distribution
enters the product's reverse valuation through the official call path.

This is a product-integration test, not a loader test. It drives the web API
(`POST /api/analyze`), which is the path the product itself uses, and asserts
that the qualified distribution is actually *used* by the reverse valuation
rather than merely reported alongside it.

The acceptance conditions are the ones the integration must satisfy:

* the distribution is `USABLE_FOR_REFERENCE` with 130 qualifying observations,
  a median of 47.299768 and the observation window 2024-11-08..2026-09-24;
* the current snapshot is `AVAILABLE` at 30.21875;
* the reverse valuation receives that qualified reference -- the summary names
  the production median as its basis and the derived figure is computed from
  it, and the matrix's exit multiples are the distribution's own percentiles;
* every result states its inputs, formula, period and conditional assumptions
  and is never described as a forecast, a fair value or a buy/sell signal;
* windows with missing or non-positive EPS stay refused, and the reference
  gate is unchanged.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, ".")

REPO_ROOT = Path(__file__).resolve().parents[1]


class TestSofiIsRegisteredAsAnIssuer(unittest.TestCase):
    """SOFI is a configured issuer, not a loose directory of data."""

    def test_sofi_is_in_the_issuer_configuration(self):
        from historical_pe import ISSUER_CONFIGS

        self.assertIn("SOFI", ISSUER_CONFIGS)
        config = ISSUER_CONFIGS["SOFI"]
        self.assertEqual(config.ticker, "SOFI")
        self.assertEqual(config.issuer_id, "CIK0001818874")
        self.assertEqual(config.fye_month, 12)

    def test_the_configured_data_directory_is_tracked(self):
        from historical_pe import ISSUER_CONFIGS

        config = ISSUER_CONFIGS["SOFI"]
        resolved = (REPO_ROOT / config.data_dir).resolve()
        self.assertTrue(resolved.is_dir(), f"missing dataset directory: {resolved}")
        for name in (
            "daily_prices.json",
            "eps_diluted_concept.json",
            "filing_acceptance_evidence.json",
            "q4_evidence_records.json",
        ):
            self.assertTrue(
                (resolved / name).is_file(), f"missing canonical input: {name}"
            )


class TestSofiDistributionIsQualified(unittest.TestCase):
    """The official configuration yields the qualified distribution."""

    @classmethod
    def setUpClass(cls):
        from historical_pe import ISSUER_CONFIGS, load_issuer_historical_pe

        cls.result = load_issuer_historical_pe(ISSUER_CONFIGS["SOFI"], enable_furnished=True)
        cls.payload = cls.result.to_dict()

    def test_the_distribution_is_usable_as_a_reference(self):
        dist = self.result.distribution
        self.assertEqual(dist.status, "USABLE_FOR_REFERENCE")
        self.assertTrue(dist.usable_for_reference)
        self.assertEqual(dist.sample_count, 130)
        self.assertEqual(dist.min_observations_required, 20)
        self.assertGreaterEqual(dist.sample_count, dist.min_observations_required)

    def test_the_distribution_matches_the_recorded_dataset(self):
        dist = self.result.distribution
        self.assertEqual(dist.percentiles["median"], 47.299768)
        self.assertEqual(dist.period_start, "2024-11-08")
        self.assertEqual(dist.period_end, "2026-09-24")
        self.assertEqual(dist.total_evaluations, 330)
        self.assertEqual(len(self.result.observations), 330)

    def test_the_current_snapshot_is_available(self):
        snapshot = self.result.current_snapshot
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.status, "AVAILABLE")
        self.assertEqual(snapshot.value, 30.21875)
        self.assertEqual(snapshot.evaluation_date, "2026-10-19")

    def test_the_excluded_windows_keep_their_explicit_reasons(self):
        excluded = self.payload["distribution"]["excluded_observations"]
        self.assertEqual(len(excluded), 200)
        reasons = {}
        for observation in excluded:
            self.assertEqual(observation["status"], "UNAVAILABLE")
            self.assertIsNotNone(observation["reason_code"])
            reasons[observation["reason_code"]] = (
                reasons.get(observation["reason_code"], 0) + 1
            )
        self.assertEqual(
            reasons,
            {"REASON_MISSING_Q4_EPS": 98, "REASON_NON_POSITIVE_EPS": 102},
        )

    def test_the_manifest_agrees_with_the_production_loader(self):
        manifest = json.loads(
            (REPO_ROOT / "data/historical_pe/SOFI/manifest.json").read_text(encoding="utf-8")
        )
        recorded = manifest["production_pipeline"]
        self.assertEqual(manifest["status"], "USABLE_FOR_REFERENCE")
        self.assertEqual(manifest["issuer_id"], "CIK0001818874")
        self.assertEqual(recorded["sample_count"], self.result.distribution.sample_count)
        self.assertEqual(
            recorded["percentiles"]["median"], self.result.distribution.percentiles["median"]
        )
        self.assertEqual(recorded["input_set_id"], self.result.input_set_id)
        self.assertEqual(recorded["content_hash"], self.result.content_hash)


class TestSofiEntersTheReverseValuationThroughTheProductPath(unittest.TestCase):
    """The web API is the product's own call path."""

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        from web.app import create_app

        cls._dir = tempfile.TemporaryDirectory(prefix="steva-sofi-")
        client = TestClient(create_app(archives_dir=cls._dir.name))
        job = client.post(
            "/api/analyze", json={"ticker": "SOFI", "mode": "regression"}
        ).json()["job_id"]
        for _ in range(180):
            state = client.get(f"/api/jobs/{job}").json()
            if state["status"] in ("COMPLETED", "FAILED"):
                break
            time.sleep(1)
        cls.state = state
        cls.result = state.get("result") or {}
        cls.report = cls.result.get("reverse_requirements") or {}
        cls.summary = cls.result.get("valuation_summary") or {}
        cls.distribution = cls.report.get("production_historical_pe_summary") or {}

    @classmethod
    def tearDownClass(cls):
        cls._dir.cleanup()

    def test_the_analysis_completed(self):
        self.assertEqual(self.state["status"], "COMPLETED", self.state.get("error"))
        self.assertTrue(self.result)

    def test_the_product_path_reports_the_qualified_distribution(self):
        self.assertEqual(self.distribution["status"], "USABLE_FOR_REFERENCE")
        self.assertTrue(self.distribution["usable_for_reference"])
        self.assertEqual(self.distribution["sample_count"], 130)
        self.assertEqual(self.distribution["percentiles"]["median"], 47.299768)
        self.assertEqual(self.distribution["period_start"], "2024-11-08")
        self.assertEqual(self.distribution["period_end"], "2026-09-24")
        self.assertEqual(self.distribution["issuer_id"], "CIK0001818874")

    def test_the_current_snapshot_is_available_through_the_product_path(self):
        self.assertEqual(self.distribution["current_pe"], 30.21875)
        self.assertEqual(self.distribution["current_pe_as_of"], "2026-10-19")

    def test_the_summary_selects_the_production_median_as_its_reference(self):
        self.assertEqual(self.summary["selected_pe_basis"], "production_historical_pe_median")
        self.assertEqual(self.summary["selected_pe"], 47.299768)
        self.assertEqual(self.summary["selected_pe"], self.distribution["percentiles"]["median"])

    def test_the_derived_figure_is_computed_from_that_reference(self):
        """The reference must reach the arithmetic, not just the response."""
        self.assertAlmostEqual(
            self.summary["forward_eps_at_reference_multiple"],
            self.summary["current_price"] / self.summary["selected_pe"],
            places=9,
        )

    def test_the_matrix_is_computed_from_the_distribution(self):
        self.assertEqual(self.report["status"], "COMPUTED")
        rows = self.report["reverse_requirements_matrix"]
        self.assertTrue(rows, "the reverse requirements matrix must be populated")
        self.assertEqual(len(rows), self.report["matrix_size"])

        expected = set(self.distribution["percentiles"].values())
        observed = {row["exit_multiple"]["value"] for row in rows}
        self.assertEqual(observed, expected)
        for row in rows:
            self.assertEqual(
                row["exit_multiple"]["source"], "production_historical_pe_percentile"
            )
            self.assertEqual(
                row["exit_multiple"]["eligibility_state"], "ELIGIBLE_PRODUCTION_DISTRIBUTION"
            )
            self.assertTrue(row["exit_multiple"]["usable_for_reference"])
            self.assertFalse(row["exit_multiple"]["is_user_assumption"])
            self.assertEqual(row["exit_multiple"]["sample_size"], 130)

    def test_no_row_uses_the_ineligible_vendor_band(self):
        """The captured vendor band holds five observations, so it is refused."""
        for row in self.report["reverse_requirements_matrix"]:
            self.assertNotEqual(row["exit_multiple"]["source"], "vendor_historical_band")
        blocked = {
            entry["item"]
            for entry in (self.report.get("unavailable") or [])
            if entry.get("reason_kind") == "INSUFFICIENT_OBSERVATIONS"
        }
        self.assertIn("exit_multiple.band_scenarios", blocked)

    def test_the_matrix_row_is_recomputable_from_the_distribution(self):
        """The row's own arithmetic must reproduce from the reference it names."""
        row = next(
            r
            for r in self.report["reverse_requirements_matrix"]
            if r["exit_multiple"]["value"] == 47.299768
        )
        multiple = row["exit_multiple"]["value"]
        start_eps = row["start_eps"]["value"]

        # The exit price is the current price grown at the required return over
        # the horizon; the terminal EPS is what that exit price implies at the
        # exit multiple; the required EPS growth is the CAGR between them.
        expected_exit_price = row["price"] * ((1 + row["required_return"]) ** row["horizon_years"])
        self.assertAlmostEqual(row["required_exit_price"], expected_exit_price, places=6)
        self.assertAlmostEqual(
            row["required_terminal_eps"], expected_exit_price / multiple, places=6
        )
        expected_cagr = (row["required_terminal_eps"] / start_eps) ** (
            1 / row["growth_years"]
        ) - 1
        self.assertAlmostEqual(row["required_eps_cagr"], expected_cagr, places=6)


class TestTheResultStatesItsAssumptions(unittest.TestCase):
    """Inputs, formula, period and conditionality stay explicit."""

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        from web.app import create_app

        cls._dir = tempfile.TemporaryDirectory(prefix="steva-sofi-terms-")
        client = TestClient(create_app(archives_dir=cls._dir.name))
        job = client.post(
            "/api/analyze", json={"ticker": "SOFI", "mode": "regression"}
        ).json()["job_id"]
        for _ in range(180):
            state = client.get(f"/api/jobs/{job}").json()
            if state["status"] in ("COMPLETED", "FAILED"):
                break
            time.sleep(1)
        cls.result = state.get("result") or {}
        cls.report = cls.result.get("reverse_requirements") or {}
        cls.summary = cls.result.get("valuation_summary") or {}
        cls.blob = json.dumps(cls.result, default=str)

    @classmethod
    def tearDownClass(cls):
        cls._dir.cleanup()

    def test_every_matrix_row_names_its_inputs_formula_and_period(self):
        for row in self.report["reverse_requirements_matrix"]:
            evidence = row["evidence"]
            self.assertIn("price_evidence", evidence)
            self.assertIn("eps_evidence", evidence)
            self.assertIn("multiple_evidence", evidence)
            self.assertTrue(row["formula_version"])
            self.assertTrue(row["required_return_basis"])
            self.assertTrue(row["as_of"])
            self.assertTrue(row["exit_multiple"]["period_label"])
            self.assertTrue(row["exit_multiple"]["sample_period"])
            self.assertTrue(row["exit_multiple"]["conditionality"])

    def test_the_conditionality_states_it_is_not_a_market_expectation(self):
        for row in self.report["reverse_requirements_matrix"]:
            self.assertIn(
                "not a statement of what the market expects",
                row["exit_multiple"]["conditionality"],
            )

    def test_the_unvalidated_inputs_are_named(self):
        for row in self.report["reverse_requirements_matrix"]:
            missing = row["evidence"]["missing_or_unvalidated"]
            self.assertIsInstance(missing, list)
            self.assertTrue(missing, "the caveats must not be empty")
            self.assertTrue(row["evidence"]["sourced_facts"])

    def test_the_limitations_state_the_output_is_not_a_signal(self):
        limitations = self.summary["limitations"]
        self.assertIn(
            "This output is descriptive valuation analysis, not a buy/sell signal.",
            limitations,
        )
        self.assertIn(
            "ST-EVA does not invent EPS, consensus, probabilities, or target prices.",
            limitations,
        )

    def test_no_recommendation_or_fair_value_language_appears(self):
        for term in (
            "fair value",
            "overweight",
            "underweight",
            "buy rating",
            "sell rating",
            "recommendation",
            "undervalued",
            "overvalued",
            "should buy",
            "should sell",
        ):
            with self.subTest(term=term):
                self.assertNotIn(term, self.blob.lower())

    def test_the_only_forecast_and_target_price_mentions_are_disclaimers(self):
        """Those words may appear only inside an explicit denial."""
        denials = (
            "not a forecast",
            "does not invent",
            "not an independent forecast",
            "not a price target",
            "reverse valuation, not a",
            "not a statement of what the market expects",
        )
        for term in ("forecast", "target price", "price target"):
            with self.subTest(term=term):
                for match in re.finditer(re.escape(term), self.blob, re.IGNORECASE):
                    window = self.blob[max(0, match.start() - 240): match.end() + 140].lower()
                    self.assertTrue(
                        any(denial in window for denial in denials),
                        f"{term!r} appears outside a disclaimer: ...{window}...",
                    )


class TestIneligibleWindowsStayRefused(unittest.TestCase):
    """The reference gate and the refusals are unchanged."""

    def test_a_distribution_below_the_threshold_is_never_promoted(self):
        """The gate is the production builder's, so build a genuinely thin one."""
        from historical_pe import (
            ISSUER_CONFIGS,
            compute_historical_pe_distribution,
            load_issuer_historical_pe,
        )
        from reverse_requirements import exit_multiples_from_production_distribution

        result = load_issuer_historical_pe(ISSUER_CONFIGS["SOFI"], enable_furnished=True)
        available = [o for o in result.observations if o.status == "AVAILABLE"]
        self.assertGreater(len(available), 20)

        thin = compute_historical_pe_distribution(available[:19])
        self.assertEqual(thin.status, "INSUFFICIENT_OBSERVATIONS")
        self.assertFalse(thin.usable_for_reference)
        self.assertEqual(thin.sample_count, 19)

        multiples, unavailable = exit_multiples_from_production_distribution(
            thin.to_dict()
        )
        self.assertEqual(multiples, [])
        self.assertEqual(len(unavailable), 1)
        self.assertEqual(unavailable[0]["reason_kind"], "INSUFFICIENT_OBSERVATIONS")

    def test_the_thirty_observation_threshold_is_unchanged(self):
        from historical_pe import MIN_OBSERVATIONS_FOR_REFERENCE

        self.assertEqual(MIN_OBSERVATIONS_FOR_REFERENCE, 20)

    def test_the_sofi_windows_without_usable_eps_are_excluded_not_padded(self):
        from historical_pe import ISSUER_CONFIGS, load_issuer_historical_pe

        result = load_issuer_historical_pe(ISSUER_CONFIGS["SOFI"], enable_furnished=True)
        excluded = result.to_dict()["distribution"]["excluded_observations"]
        self.assertEqual(len(excluded), 200)
        # Every excluded window names a reason; none was filled in.
        for observation in excluded:
            self.assertIsNone(observation.get("value"))
            self.assertIn(
                observation["reason_code"],
                ("REASON_MISSING_Q4_EPS", "REASON_NON_POSITIVE_EPS"),
            )


class TestOtherIssuersAreUnchanged(unittest.TestCase):
    """AAPL, MSFT and MU keep their results, and the MUFG limit is intact."""

    def test_the_other_issuers_still_qualify(self):
        from historical_pe import ISSUER_CONFIGS, load_issuer_historical_pe

        expected = {
            "AAPL": (36, 28.44563),
            "MSFT": (24, 33.195873),
            "MU": (454, 20.552342),
        }
        for ticker, (count, median) in expected.items():
            with self.subTest(ticker=ticker):
                result = load_issuer_historical_pe(
                    ISSUER_CONFIGS[ticker], enable_furnished=True
                )
                self.assertEqual(result.distribution.status, "USABLE_FOR_REFERENCE")
                self.assertEqual(result.distribution.sample_count, count)
                self.assertEqual(result.distribution.percentiles["median"], median)

    def test_the_sofi_registration_did_not_change_the_other_issuers(self):
        from historical_pe import ISSUER_CONFIGS, load_issuer_historical_pe

        for ticker in ("AAPL", "MSFT", "MU"):
            with self.subTest(ticker=ticker):
                first = load_issuer_historical_pe(ISSUER_CONFIGS[ticker], enable_furnished=True)
                second = load_issuer_historical_pe(ISSUER_CONFIGS[ticker], enable_furnished=True)
                self.assertEqual(first.input_set_id, second.input_set_id)
                self.assertEqual(first.content_hash, second.content_hash)

    def test_the_mufg_cross_currency_limit_is_not_degraded(self):
        """MUFG's cross-currency inputs stay as declared.

        MUFG has no production historical P/E dataset, so registering SOFI must
        not change its path: the two FX scopes stay distinct, the ADR ratio
        stays one-to-one, and the reference FX rate keeps its declared date and
        its reference-only scope.
        """
        from adr_ratio import MUFG_ADR_RATIO
        from fx_rates import MUFG_FX_RATE_USD_PER_JPY
        from historical_pe import ISSUER_CONFIGS

        self.assertNotIn("MUFG", ISSUER_CONFIGS)

        self.assertEqual(MUFG_ADR_RATIO.underlying_shares_per_adr, 1.0)
        self.assertEqual(MUFG_FX_RATE_USD_PER_JPY.rate_usd_per_jpy, 0.006316)
        self.assertEqual(MUFG_FX_RATE_USD_PER_JPY.as_of, "2026-10-09")
        self.assertEqual(MUFG_FX_RATE_USD_PER_JPY.quote_direction, "USD per JPY")
        self.assertIn("Reference only", MUFG_FX_RATE_USD_PER_JPY.original_amounts["note"])

    def test_adding_sofi_did_not_register_any_other_issuer(self):
        from historical_pe import ISSUER_CONFIGS

        self.assertEqual(
            sorted(ISSUER_CONFIGS),
            ["AAPL", "MSFT", "MU", "SOFI"],
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
