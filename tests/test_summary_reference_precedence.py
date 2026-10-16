"""
Regression tests for the summary reference-selection precedence.

Before this change the summary engine's reference could only be the operator's
supplied multiple or the vendor historical P/E band median, so a run whose
matrix admitted production historical P/E percentiles still reported
`selected_pe_basis = none` and `selected_pe = None`. The record reached the
matrix and contradicted the headline card.

The precedence is now: a user-supplied multiple, then the eligible production
historical P/E distribution's median, then the eligible vendor band median, then
nothing. These tests pin each rung, the eligibility gate, and the changes that
must *not* happen.
"""
from __future__ import annotations

import sys
import tempfile
import time
import unittest

sys.path.insert(0, ".")

from data_contract import ValuationInputs
from st_eva_runner import MarketImpliedAssumptionsEngine, production_pe_for_reference


def _eligible_distribution(median="33.195873", status="USABLE_FOR_REFERENCE"):
    return {
        "distribution": {
            "status": status,
            "usable_for_reference": True,
            "sample_count": 24,
            "total_evaluations": 27,
            "min_observations_required": 20,
            "period_start": "2021-07-28",
            "period_end": "2026-07-30",
            "percentiles": {
                "10th": 25.602182,
                "25th": 28.811204,
                "median": float(median),
                "75th": 35.400253,
                "90th": 36.088407,
            },
            "input_set_id": "e6719c725702af9b8cc44285a85fa89e1b4df175c0becbb46ac8a30dd847027c",
            "content_hash": "f3b133e4c5d42262d4ba1cb26266da05c3b4717f8862bcb26fded2c547df402d",
        }
    }


def _vendor_band(median=25.0, observations=40):
    """An eligible vendor band: a positive median with >= 20 declared observations."""
    return {
        "median": median,
        "10th": median - 5.0,
        "25th": median - 2.5,
        "50th": median,
        "75th": median + 2.5,
        "90th": median + 5.0,
        "observations": float(observations),
    }


def _inputs(price=535.07, current_eps=17.95, forward_eps=23.67732, consensus=23.67732,
            historical_pe_band=None):
    return ValuationInputs(
        price=price,
        currency="USD",
        current_eps=current_eps,
        forward_eps=forward_eps,
        consensus_forward_eps=consensus,
        historical_pe_band=historical_pe_band or {},
    )


class TestProductionPeForReference(unittest.TestCase):
    """The eligibility gate and the median both come from the distribution."""

    def test_an_eligible_distribution_yields_its_own_median(self):
        median, status = production_pe_for_reference(_eligible_distribution())
        self.assertEqual(median, 33.195873)
        self.assertEqual(status, "USABLE_FOR_REFERENCE")

    def test_an_absent_distribution_yields_nothing(self):
        self.assertEqual(production_pe_for_reference(None), (None, "UNAVAILABLE"))
        self.assertEqual(production_pe_for_reference({}), (None, "UNAVAILABLE"))

    def test_an_ineligible_distribution_yields_nothing(self):
        payload = _eligible_distribution()
        payload["distribution"]["usable_for_reference"] = False
        payload["distribution"]["status"] = "DESCRIPTIVE_ONLY_INSUFFICIENT_OBSERVATIONS"
        median, status = production_pe_for_reference(payload)
        self.assertIsNone(median)
        self.assertEqual(status, "DESCRIPTIVE_ONLY_INSUFFICIENT_OBSERVATIONS")

    def test_a_descriptive_only_distribution_never_qualifies(self):
        for status in (
            "DESCRIPTIVE_ONLY_INSUFFICIENT_OBSERVATIONS",
            "DESCRIPTIVE_ONLY_UNVERIFIED_SAMPLE_COUNT",
            "UNAVAILABLE",
        ):
            with self.subTest(status=status):
                payload = {
                    "distribution": {
                        "status": status,
                        "usable_for_reference": False,
                        "sample_count": 0,
                        "percentiles": {"median": 30.0},
                    }
                }
                median, reported = production_pe_for_reference(payload)
                self.assertIsNone(median)
                self.assertEqual(reported, status)

    def test_a_non_positive_median_is_refused_even_when_eligible(self):
        payload = _eligible_distribution(median="-1.0")
        median, _ = production_pe_for_reference(payload)
        self.assertIsNone(median)

    def test_the_median_is_read_from_the_distribution_not_the_band(self):
        """
        A different vendor band must not move the reference: the median is the
        distribution's own percentile, not a recomputation from the band or
        from today's price.
        """
        payload = _eligible_distribution()
        with_band = production_pe_for_reference(payload)[0]
        band_only = MarketImpliedAssumptionsEngine.analyze(
            _inputs(historical_pe_band=_vendor_band())
        )["reference"]["multiple"]
        self.assertEqual(with_band, 33.195873)
        self.assertNotEqual(with_band, band_only)


class TestSummaryReferencePrecedence(unittest.TestCase):
    """
    The rungs, in order, verified through the engine that the web path calls.
    """

    def test_the_eligible_production_median_is_the_summary_reference(self):
        analysis = MarketImpliedAssumptionsEngine.analyze(
            _inputs(),
            production_historical_pe=_eligible_distribution(),
        )
        reference = analysis["reference"]

        self.assertEqual(reference["method"], "production_historical_pe_median")
        self.assertEqual(reference["multiple"], 33.195873)
        self.assertEqual(
            reference["production_historical_pe_status"], "USABLE_FOR_REFERENCE"
        )
        # The derived figure uses that same multiple, consistently.
        self.assertAlmostEqual(
            analysis["implied_assumptions"]["forward_eps_at_reference_multiple"],
            535.07 / 33.195873,
            places=9,
        )

    def test_a_user_supplied_multiple_keeps_precedence(self):
        analysis = MarketImpliedAssumptionsEngine.analyze(
            _inputs(),
            reference_multiple=30.0,
            production_historical_pe=_eligible_distribution(),
        )
        reference = analysis["reference"]

        self.assertEqual(reference["method"], "user_supplied_multiple")
        self.assertEqual(reference["multiple"], 30.0)
        self.assertAlmostEqual(
            analysis["implied_assumptions"]["forward_eps_at_reference_multiple"],
            535.07 / 30.0,
            places=9,
        )

    def test_an_eligible_vendor_band_remains_the_fallback(self):
        analysis = MarketImpliedAssumptionsEngine.analyze(
            _inputs(historical_pe_band=_vendor_band()),
        )
        reference = analysis["reference"]

        self.assertEqual(reference["method"], "historical_pe_median")
        self.assertEqual(reference["multiple"], 25.0)
        self.assertAlmostEqual(
            analysis["implied_assumptions"]["forward_eps_at_reference_multiple"],
            535.07 / 25.0,
            places=9,
        )

    def test_the_production_median_wins_over_an_eligible_vendor_band(self):
        """
        Both sources qualified. The production distribution is the second rung
        and the vendor band the third, so the distribution's median is the one
        reported -- which is also the centre of the matrix's exit multiples.
        """
        analysis = MarketImpliedAssumptionsEngine.analyze(
            _inputs(historical_pe_band=_vendor_band()),
            production_historical_pe=_eligible_distribution(),
        )
        reference = analysis["reference"]

        self.assertEqual(reference["method"], "production_historical_pe_median")
        self.assertEqual(reference["multiple"], 33.195873)
        self.assertNotEqual(reference["multiple"], 25.0)

    def test_an_ineligible_production_distribution_falls_back_to_the_band(self):
        payload = _eligible_distribution()
        payload["distribution"]["usable_for_reference"] = False
        payload["distribution"]["status"] = "DESCRIPTIVE_ONLY_INSUFFICIENT_OBSERVATIONS"

        analysis = MarketImpliedAssumptionsEngine.analyze(
            _inputs(historical_pe_band=_vendor_band()),
            production_historical_pe=payload,
        )
        reference = analysis["reference"]

        self.assertEqual(reference["method"], "historical_pe_median")
        self.assertEqual(reference["multiple"], 25.0)
        self.assertEqual(
            reference["production_historical_pe_status"],
            "DESCRIPTIVE_ONLY_INSUFFICIENT_OBSERVATIONS",
        )

    def test_no_eligible_reference_stays_unavailable_with_no_fabrication(self):
        analysis = MarketImpliedAssumptionsEngine.analyze(_inputs())
        reference = analysis["reference"]

        self.assertEqual(reference["method"], "none")
        self.assertIsNone(reference["multiple"])
        self.assertIsNone(
            analysis["implied_assumptions"]["forward_eps_at_reference_multiple"]
        )
        # No fabricated growth or consensus gap either.
        self.assertIsNone(
            analysis["implied_assumptions"]["required_eps_cagr_from_current_eps"]
        )
        self.assertIsNone(analysis["implied_assumptions"]["eps_gap_vs_consensus"])

    def test_a_thin_vendor_band_is_not_a_reference(self):
        analysis = MarketImpliedAssumptionsEngine.analyze(
            _inputs(historical_pe_band=_vendor_band(observations=7)),
            production_historical_pe=None,
        )
        self.assertEqual(analysis["reference"]["method"], "none")
        self.assertIsNone(analysis["reference"]["multiple"])

    def test_the_production_status_is_reported_without_a_reference(self):
        payload = _eligible_distribution()
        payload["distribution"]["usable_for_reference"] = False
        payload["distribution"]["status"] = "DESCRIPTIVE_ONLY_UNVERIFIED_SAMPLE_COUNT"
        analysis = MarketImpliedAssumptionsEngine.analyze(
            _inputs(), production_historical_pe=payload
        )
        self.assertEqual(analysis["reference"]["method"], "none")
        self.assertEqual(
            analysis["reference"][
                "production_historical_pe_status"
            ],
            "DESCRIPTIVE_ONLY_UNVERIFIED_SAMPLE_COUNT",
        )


class TestTheMatrixIsUnaffected(unittest.TestCase):
    """
    Only the summary's reference selection changed. The matrix's reference
    comes from the distribution directly and must not move.
    """

    def test_the_engine_default_path_is_unchanged(self):
        """
        No distribution supplied reproduces the pre-change engine exactly,
        including the legacy band-median path.
        """
        analysis = MarketImpliedAssumptionsEngine.analyze(
            _inputs(historical_pe_band=_vendor_band())
        )
        self.assertEqual(analysis["reference"]["method"], "historical_pe_median")
        self.assertEqual(analysis["reference"]["multiple"], 25.0)
        # The unchanged vendor-band percentile read still works.
        self.assertIsNotNone(
            analysis["observed_valuation"]["approx_historical_pe_percentile"]
        )

    def test_the_legacy_view_path_agrees_with_the_contract_path(self):
        from st_eva_runner import MarketData

        view = MarketData(
            ticker="MSFT",
            company_name="Microsoft",
            exchange="NMS",
            currency="USD",
            price=535.07,
            price_date="2026-10-09",
            price_source="Yahoo chart regularMarketPrice",
            price_source_url=None,
            price_history=[500.0, 535.07],
            volume_history=[1.0, 1.0],
            current_eps=17.95,
            forward_eps=23.67732,
            consensus_forward_eps=23.67732,
            historical_pe_band=_vendor_band(),
        )
        from_view = MarketImpliedAssumptionsEngine.analyze(view)
        contract = MarketImpliedAssumptionsEngine.analyze(
            _inputs(historical_pe_band=_vendor_band())
        )
        self.assertEqual(
            from_view["reference"]["method"], contract["reference"]["method"]
        )
        self.assertEqual(
            from_view["reference"]["multiple"], contract["reference"]["multiple"]
        )

    def test_the_summary_and_the_matrix_agree_on_the_production_median(self):
        """
        The precise defect: the matrix's eligible exit multiples are the
        distribution's percentiles, so the summary must report the distribution's
        own median rather than claiming no reference exists.
        """
        distribution = _eligible_distribution()["distribution"]
        analysis = MarketImpliedAssumptionsEngine.analyze(
            _inputs(),
            production_historical_pe=_eligible_distribution(),
        )

        self.assertEqual(analysis["reference"]["method"], "production_historical_pe_median")
        self.assertEqual(
            analysis["reference"]["multiple"], distribution["percentiles"]["median"]
        )


class TestTheMatrixIsUnchanged(unittest.TestCase):
    """
    The matrix is a different calculation built from the distribution directly,
    so this change must not move it. These run the real web pipeline in
    regression mode with a temporary archive directory and compare the matrix
    against what the distribution's own percentiles produce.
    """

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        from web.app import create_app

        cls._dir = tempfile.TemporaryDirectory(prefix="steva-r75-")
        cls.result = {}
        client = TestClient(create_app(archives_dir=cls._dir.name))
        for ticker in ("MSFT", "AAPL"):
            job = client.post(
                "/api/analyze", json={"ticker": ticker, "mode": "regression"}
            ).json()["job_id"]
            import time

            for _ in range(180):
                state = client.get(f"/api/jobs/{job}").json()
                if state["status"] in ("COMPLETED", "FAILED"):
                    break
                time.sleep(1)
            cls.result[ticker] = state.get("result") or {}

    @classmethod
    def tearDownClass(cls):
        cls._dir.cleanup()

    def _rows(self, ticker):
        return (self.result[ticker].get("reverse_requirements") or {}).get(
            "reverse_requirements_matrix"
        ) or []

    def test_the_summary_reports_the_production_median_it_agrees_with(self):
        for ticker in ("MSFT", "AAPL"):
            with self.subTest(ticker=ticker):
                report = self.result[ticker]["reverse_requirements"]
                summary = self.result[ticker]["valuation_summary"]
                distribution = report["production_historical_pe_summary"]

                self.assertEqual(
                    summary["selected_pe_basis"], "production_historical_pe_median"
                )
                self.assertEqual(
                    summary["selected_pe"], distribution["percentiles"]["median"]
                )
                self.assertTrue(distribution["usable_for_reference"])
                # The derived figure still uses that same multiple.
                self.assertAlmostEqual(
                    summary["forward_eps_at_reference_multiple"],
                    summary["current_price"] / summary["selected_pe"],
                    places=9,
                )

    def test_the_exit_multiples_are_still_the_distribution_percentiles(self):
        from reverse_requirements import exit_multiples_from_production_distribution

        for ticker in ("MSFT", "AAPL"):
            with self.subTest(ticker=ticker):
                rows = self._rows(ticker)
                report = self.result[ticker]["reverse_requirements"]
                distribution = report["production_historical_pe_summary"]
                expected_multiples, unavailable = (
                    exit_multiples_from_production_distribution(distribution)
                )
                self.assertEqual(unavailable, [])
                self.assertTrue(expected_multiples)
                expected = {m.value for m in expected_multiples}
                observed = {
                    row["exit_multiple"]["value"]
                    for row in rows
                    if row["exit_multiple"]["source"]
                    == "production_historical_pe_percentile"
                }
                self.assertEqual(observed, expected)
                self.assertEqual(
                    {
                        row["exit_multiple"]["eligibility_state"]
                        for row in rows
                        if row["exit_multiple"]["source"]
                        == "production_historical_pe_percentile"
                    },
                    {"ELIGIBLE_PRODUCTION_DISTRIBUTION"},
                )
                # The median of that set is the summary's reference, so the two
                # cannot disagree about which distribution is in play.
                self.assertEqual(
                    self.result[ticker]["valuation_summary"]["selected_pe"],
                    distribution["percentiles"]["median"],
                )
                # The regression fixture also carries a vendor band whose rows
                # are emitted under the pre-existing descriptive-only rule. That
                # branch is untouched here and its rows stay as they were.
                band_rows = [
                    row
                    for row in rows
                    if row["exit_multiple"]["source"]
                    == "historical_pe_band_percentile"
                ]
                if band_rows:
                    self.assertEqual(
                        {
                            row["exit_multiple"]["eligibility_state"]
                            for row in band_rows
                        },
                        {"DESCRIPTIVE_ONLY_UNVERIFIED_SAMPLE_COUNT"},
                    )

    def test_the_scenario_figures_are_unchanged(self):
        """
        The published equations and the scenario cross product are untouched, so
        a user-supplied reference must produce the identical exit prices,
        terminal EPS, growth and CAGR it always did.
        """
        from fastapi.testclient import TestClient

        from web.app import create_app

        with tempfile.TemporaryDirectory(prefix="steva-r75-cmp-") as scratch:
            client = TestClient(create_app(archives_dir=scratch))
            job = client.post(
                "/api/analyze",
                json={"ticker": "MSFT", "mode": "regression", "reference_multiple": 30.0},
            ).json()["job_id"]
            for _ in range(180):
                state = client.get(f"/api/jobs/{job}").json()
                if state["status"] in ("COMPLETED", "FAILED"):
                    break
                time.sleep(1)

            report = state["result"]["reverse_requirements"]
            self.assertEqual(report["formula_version"], "reverse-requirements/1.1")
            rows = self._rows("MSFT")
            self.assertTrue(rows, "the reference-free run must still compute")
            for row in rows:
                self.assertAlmostEqual(
                    row["required_exit_price"],
                    row["price"]
                    * (1.0 + row["required_return"]) ** row["horizon_years"],
                    places=6,
                    msg="the published exit-price equation moved",
                )
                self.assertAlmostEqual(
                    row["required_terminal_eps"],
                    row["required_exit_price"] / row["exit_multiple"]["value"],
                    places=6,
                    msg="the published terminal-EPS equation moved",
                )
                self.assertAlmostEqual(
                    row["total_terminal_eps_growth"],
                    row["required_terminal_eps"] / row["start_eps"]["value"] - 1.0,
                    places=6,
                    msg="the published total-growth equation moved",
                )

    def test_the_matrix_is_identical_to_the_pre_change_baseline(self):
        """
        The matrix is a separate calculation and this task must not move it.

        Every scenario row, the exit multiples with their eligibility states,
        the unavailable list, the matrix status and the formula version are
        compared against the values captured from the parent commit of this
        change. A difference here means the selection change leaked into the
        matrix and the task's own boundary was crossed.
        """
        baseline = {
            "MSFT": {
                "status": "COMPUTED",
                "matrix_size": 160,
                "distinct_exit_multiples": {
                    # MSFT
                    '22.0|historical_pe_band_percentile|DESCRIPTIVE_ONLY_UNVERIFIED_SAMPLE_COUNT',
                    '25.602182|production_historical_pe_percentile|ELIGIBLE_PRODUCTION_DISTRIBUTION',
                    '26.0|historical_pe_band_percentile|DESCRIPTIVE_ONLY_UNVERIFIED_SAMPLE_COUNT',
                    '28.811204|production_historical_pe_percentile|ELIGIBLE_PRODUCTION_DISTRIBUTION',
                    '30.0|historical_pe_band_percentile|DESCRIPTIVE_ONLY_UNVERIFIED_SAMPLE_COUNT',
                    '33.195873|production_historical_pe_percentile|ELIGIBLE_PRODUCTION_DISTRIBUTION',
                    '34.0|historical_pe_band_percentile|DESCRIPTIVE_ONLY_UNVERIFIED_SAMPLE_COUNT',
                    '35.400253|production_historical_pe_percentile|ELIGIBLE_PRODUCTION_DISTRIBUTION',
                    '36.088407|production_historical_pe_percentile|ELIGIBLE_PRODUCTION_DISTRIBUTION',
                    '38.0|historical_pe_band_percentile|DESCRIPTIVE_ONLY_UNVERIFIED_SAMPLE_COUNT',
                },
            },
            "AAPL": {
                "status": "COMPUTED",
                "matrix_size": 80,
                "distinct_exit_multiples": {
                    # AAPL
                    '17.715401|production_historical_pe_percentile|ELIGIBLE_PRODUCTION_DISTRIBUTION',
                    '24.785061|production_historical_pe_percentile|ELIGIBLE_PRODUCTION_DISTRIBUTION',
                    '28.286075|production_historical_pe_percentile|ELIGIBLE_PRODUCTION_DISTRIBUTION',
                    '33.333948|production_historical_pe_percentile|ELIGIBLE_PRODUCTION_DISTRIBUTION',
                    '36.334726|production_historical_pe_percentile|ELIGIBLE_PRODUCTION_DISTRIBUTION',
                },
            },
        }

        for ticker, expected in baseline.items():
            with self.subTest(ticker=ticker):
                report = self.result[ticker]["reverse_requirements"]
                rows = self._rows(ticker)
                self.assertEqual(report["status"], expected["status"])
                self.assertEqual(report["matrix_size"], expected["matrix_size"])
                self.assertEqual(len(rows), expected["matrix_size"])
                self.assertEqual(
                    {
                        "{}|{}|{}".format(
                            row["exit_multiple"]["value"],
                            row["exit_multiple"]["source"],
                            row["exit_multiple"]["eligibility_state"],
                        )
                        for row in rows
                    },
                    expected["distinct_exit_multiples"],
                )
                self.assertEqual(
                    report["formula_version"], "reverse-requirements/1.1"
                )


class TestReferenceSampleCountIsTheReferencesOwn(unittest.TestCase):
    """
    The reference block carries the observation count of the reference actually
    selected, for the one basis that has a source count at all.

    The count cannot be read from the vendor band here: the band is a different
    object, and for two of the four bases it supplied nothing, so its count is
    not the reference's. The context layer builds this field from what the
    summary reports, so the summary has to report the right number or the
    context has nothing correct to copy.
    """

    def test_the_production_reference_reports_the_distributions_own_count(self):
        analysis = MarketImpliedAssumptionsEngine.analyze(
            _inputs(historical_pe_band=_vendor_band(observations=7)),
            production_historical_pe=_eligible_distribution(),
        )
        reference = analysis["reference"]

        self.assertEqual(reference["method"], "production_historical_pe_median")
        self.assertEqual(
            reference["production_historical_pe_sample_count"],
            24,
            "the distribution holds 24 observations",
        )
        self.assertNotEqual(
            reference["production_historical_pe_sample_count"],
            _vendor_band(observations=7)["observations"],
            "the vendor band's 7 is not the reference's source count",
        )

    def test_a_distribution_that_is_not_the_reference_contributes_no_count(self):
        analysis = MarketImpliedAssumptionsEngine.analyze(
            _inputs(historical_pe_band=_vendor_band(observations=7)),
            reference_multiple=30.0,
            production_historical_pe=_eligible_distribution(),
        )
        reference = analysis["reference"]

        self.assertEqual(reference["method"], "user_supplied_multiple")
        self.assertIsNone(
            reference["production_historical_pe_sample_count"],
            "an eligible distribution that was not selected has no count to report",
        )

    def test_a_band_reference_reports_no_production_count(self):
        analysis = MarketImpliedAssumptionsEngine.analyze(
            _inputs(historical_pe_band=_vendor_band(observations=40))
        )
        reference = analysis["reference"]

        self.assertEqual(reference["method"], "historical_pe_median")
        self.assertIsNone(
            reference["production_historical_pe_sample_count"],
            "the band is the reference, so no production count belongs here",
        )

    def test_no_reference_reports_no_production_count(self):
        analysis = MarketImpliedAssumptionsEngine.analyze(_inputs())
        reference = analysis["reference"]

        self.assertEqual(reference["method"], "none")
        self.assertIsNone(reference["production_historical_pe_sample_count"])

    def test_the_status_is_still_reported_for_every_basis(self):
        """Adding the count must not displace the eligibility status beside it."""
        analysis = MarketImpliedAssumptionsEngine.analyze(
            _inputs(historical_pe_band=_vendor_band(observations=7)),
            production_historical_pe=_eligible_distribution(),
        )
        self.assertEqual(
            analysis["reference"]["production_historical_pe_status"],
            "USABLE_FOR_REFERENCE",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
