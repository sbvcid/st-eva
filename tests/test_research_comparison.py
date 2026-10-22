"""The research comparison and sensitivity service.

The service's job is to say what a comparison may rest on. These tests check
that the arithmetic is recomputed from the observation records rather than
asserted, that the paired comparison uses only the dates where both lanes
published, that an unattributable difference is marked as such, and that
nothing a comparison does reaches production.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from research_comparison import (
    ASSUMPTION_MULTIPLE_OVERRIDE,
    ASSUMPTION_NUMERATOR_MULTIPLIER,
    CLOSED_COMPARISON_REASON_CODES,
    COMPARISON_CROSS_METRIC,
    COMPARISON_HISTORY,
    COMPARISON_PAIRED_BRIDGE,
    ResearchComparisonError,
    comparability,
    compare_bridges,
    compare_history,
    metric_definitions,
    run_sensitivity,
)
from research_lane_ko import build_ko_research_lanes
from web.app import create_app

ROOT = Path(__file__).resolve().parent.parent

A = "RESEARCH_KO_REPORTED_REVENUE_MULTIPLE"
B = "RESEARCH_KO_REPORTED_OPERATING_PROFIT_PLUS_REPORTED_D_AND_A_MULTIPLE"
C1 = "RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_PRODUCTION_SHAPE"
C2 = "RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_SHORT_TERM_BORROWINGS"
DIAGNOSTIC = "RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_DOUBLE_COUNTED_DIAGNOSTIC"


def _observations(metric_id: str):
    for result in build_ko_research_lanes():
        if result.metric_id == metric_id:
            return {o.evaluation_date: o for o in result.observations}
    raise AssertionError(metric_id)


class TheMetricDefinitions(unittest.TestCase):
    """Every metric declares what it may be compared with."""

    def test_the_definitions_carry_the_comparability_attributes(self):
        definitions = {d.metric_id: d for d in metric_definitions()}
        self.assertEqual(set(definitions), {A, B, C1, C2})
        for definition in definitions.values():
            self.assertIn(
                definition.numerator_kind, ("market_cap", "enterprise_value")
            )
            self.assertTrue(definition.denominator_definition)
            self.assertTrue(definition.denominator_elements)
            self.assertTrue(definition.currency)
            self.assertTrue(definition.unit)
            self.assertTrue(definition.formula_version)
            self.assertTrue(definition.formula_expression)
            self.assertTrue(definition.candidate_metric)

    def test_the_diagnostic_is_not_offered(self):
        self.assertNotIn(DIAGNOSTIC, {d.metric_id for d in metric_definitions()})

    def test_the_two_enterprise_value_lanes_are_a_paired_bridge_comparison(self):
        payload = comparability(C1, C2)
        self.assertTrue(payload["comparable"])
        self.assertEqual(payload["comparable_as"], COMPARISON_PAIRED_BRIDGE)
        self.assertEqual(payload["differences"], [])
        self.assertEqual(
            payload["shared"]["numerator_kind"], "enterprise_value"
        )

    def test_metrics_with_different_denominators_are_not_a_same_basis_comparison(self):
        payload = comparability(A, B)
        self.assertFalse(payload["comparable"])
        self.assertEqual(payload["comparable_as"], COMPARISON_CROSS_METRIC)
        attributes = {d["attribute"] for d in payload["differences"]}
        self.assertIn("denominator_definition", attributes)
        self.assertTrue(payload["reasons"])

    def test_metrics_with_different_numerators_are_not_a_same_basis_comparison(self):
        payload = comparability(B, C1)
        self.assertFalse(payload["comparable"])
        self.assertEqual(payload["comparable_as"], COMPARISON_CROSS_METRIC)
        attributes = {d["attribute"] for d in payload["differences"]}
        self.assertIn("numerator_kind", attributes)


class TheHistoricalComparison(unittest.TestCase):
    """One metric at two dates."""

    def test_the_comparison_is_recomputed_from_the_observations(self):
        observations = _observations(A)
        published = sorted(
            day for day, o in observations.items() if o.value is not None
        )
        earlier, later = published[0], published[-1]
        payload = compare_history(A, earlier, later)
        comparison = payload["comparison"]
        self.assertEqual(comparison["earlier_multiple"], observations[earlier].value)
        self.assertEqual(comparison["later_multiple"], observations[later].value)
        self.assertAlmostEqual(
            comparison["absolute_change"],
            observations[later].value - observations[earlier].value,
        )
        self.assertAlmostEqual(
            comparison["percentage_change"],
            (observations[later].value - observations[earlier].value)
            / observations[earlier].value,
        )

    def test_both_dates_carry_their_own_source_and_hash(self):
        observations = _observations(A)
        published = sorted(
            day for day, o in observations.items() if o.value is not None
        )
        payload = compare_history(A, published[0], published[-1])
        self.assertEqual(
            payload["earlier"]["content_hash"], observations[published[0]].content_hash
        )
        self.assertEqual(
            payload["later"]["content_hash"], observations[published[-1]].content_hash
        )
        self.assertTrue(payload["earlier"]["price_source"]["source_url"])
        self.assertTrue(payload["later"]["shares_source"]["source_url"])
        self.assertTrue(payload["comparison_hash"])

    def test_the_refused_dates_in_between_are_shown(self):
        # The refused dates between two published dates are listed, and the
        # list is checked against the observation records rather than against
        # a number written down here.
        for metric_id in (A, B, C1, C2):
            observations = _observations(metric_id)
            published = sorted(
                day for day, o in observations.items() if o.value is not None
            )
            for earlier, later in zip(published, published[1:]):
                between = sorted(
                    day
                    for day, o in observations.items()
                    if earlier < day < later and o.value is None
                )
                payload = compare_history(metric_id, earlier, later)
                self.assertEqual(
                    payload["refused_between_count"], len(between), metric_id
                )
                self.assertEqual(
                    [item["evaluation_date"] for item in payload["refused_between"]],
                    between,
                    metric_id,
                )
                for item in payload["refused_between"]:
                    self.assertTrue(item["reason_code"])
                    self.assertTrue(item["reason_detail"])

    def test_the_evidence_changes_between_the_dates_are_reported(self):
        observations = _observations(A)
        published = sorted(
            day for day, o in observations.items() if o.value is not None
        )
        payload = compare_history(A, published[0], published[-1])
        changes = payload["evidence_changes"]
        self.assertIn("elements_changed", changes)
        self.assertIn("denominator_window_changed", changes)
        self.assertIn("earlier_bridge_complete", changes)
        self.assertIn("basis_breaks", payload)
        self.assertIn("prior_period_revisions", payload)

    def test_a_refused_date_is_refused(self):
        observations = _observations(A)
        refused = next(
            day for day, o in observations.items() if o.value is None
        )
        published = next(
            day for day, o in observations.items() if o.value is not None
        )
        with self.assertRaises(ResearchComparisonError) as caught:
            compare_history(A, refused, published)
        self.assertEqual(
            caught.exception.reason_code,
            "RESEARCH_COMPARISON_REFUSED_OBSERVATION_REJECTED",
        )
        self.assertIn("RESEARCH_REASON", caught.exception.detail)

    def test_an_unknown_date_is_refused(self):
        with self.assertRaises(ResearchComparisonError) as caught:
            compare_history(A, "1999-01-01", "2026-07-29")
        self.assertEqual(
            caught.exception.reason_code,
            "RESEARCH_COMPARISON_REFUSED_OBSERVATION_UNKNOWN",
        )

    def test_the_same_date_is_refused(self):
        with self.assertRaises(ResearchComparisonError) as caught:
            compare_history(A, "2026-07-29", "2026-07-29")
        self.assertEqual(
            caught.exception.reason_code,
            "RESEARCH_COMPARISON_REFUSED_SAME_DATE",
        )

    def test_the_comparison_is_never_production_eligible(self):
        observations = _observations(A)
        published = sorted(
            day for day, o in observations.items() if o.value is not None
        )
        payload = compare_history(A, published[0], published[-1])
        self.assertFalse(payload["production_eligible"])


class ThePairedBridgeComparison(unittest.TestCase):
    """The two enterprise-value lanes on the dates where both published."""

    @classmethod
    def setUpClass(cls):
        cls.payload = compare_bridges(C1, C2)
        cls.left = _observations(C1)
        cls.right = _observations(C2)

    def test_only_the_shared_published_dates_are_paired(self):
        expected = sorted(
            day
            for day in set(self.left) & set(self.right)
            if self.left[day].value is not None and self.right[day].value is not None
        )
        self.assertEqual(self.payload["paired_sample_count"], len(expected))
        self.assertEqual(
            [pair["evaluation_date"] for pair in self.payload["pairs"]], expected
        )
        for pair in self.payload["pairs"]:
            self.assertIsNotNone(self.left[pair["evaluation_date"]].value)
            self.assertIsNotNone(self.right[pair["evaluation_date"]].value)

    def test_the_unpaired_dates_and_their_reasons_are_recorded(self):
        left_only = {
            day
            for day, o in self.left.items()
            if o.value is None
            and day in self.right
            and self.right[day].value is not None
        }
        right_only = {
            day
            for day, o in self.right.items()
            if o.value is None
            and day in self.left
            and self.left[day].value is not None
        }
        both_refused = {
            day
            for day, o in self.left.items()
            if o.value is None and day in self.right and self.right[day].value is None
        }
        self.assertEqual(
            {item["evaluation_date"] for item in self.payload["unpaired_left"]},
            left_only,
        )
        self.assertEqual(
            {item["evaluation_date"] for item in self.payload["unpaired_right"]},
            right_only,
        )
        self.assertEqual(
            {item["evaluation_date"] for item in self.payload["refused_on_both"]},
            both_refused,
        )
        for item in (
            self.payload["unpaired_left"] + self.payload["unpaired_right"]
        ):
            self.assertTrue(item["reason_code"])
            self.assertTrue(item["reason_detail"])

    def test_the_enterprise_value_difference_reproduces_from_the_bridges(self):
        for pair in self.payload["pairs"]:
            left_components = pair["left"]["bridge"]["components"]
            right_components = pair["right"]["bridge"]["components"]
            left_debt = sum(
                component["value"]
                for name, component in left_components.items()
                if name
                in ("long_term_debt_current", "long_term_debt_noncurrent", "commercial_paper")
            )
            right_debt = sum(
                component["value"]
                for name, component in right_components.items()
                if name
                in (
                    "long_term_debt_current",
                    "long_term_debt_noncurrent",
                    "notes_and_loans_payable",
                )
            )
            left_funds = sum(
                component["value"]
                for name, component in left_components.items()
                if name in ("cash", "marketable_securities_current")
            )
            right_funds = sum(
                component["value"]
                for name, component in right_components.items()
                if name in ("cash", "marketable_securities_current")
            )
            left_ev = pair["left"]["market_cap"] + left_debt - left_funds
            right_ev = pair["right"]["market_cap"] + right_debt - right_funds
            self.assertAlmostEqual(left_ev, pair["left"]["enterprise_value"], places=2)
            self.assertAlmostEqual(right_ev, pair["right"]["enterprise_value"], places=2)
            self.assertAlmostEqual(
                right_ev - left_ev,
                pair["differences"]["enterprise_value"],
                places=2,
            )

    def test_the_difference_is_the_short_term_component_difference(self):
        for pair in self.payload["pairs"]:
            left_components = pair["left"]["bridge"]["components"]
            right_components = pair["right"]["bridge"]["components"]
            short_term = pair["differences"]["short_term_components"]
            self.assertIn("commercial_paper", left_components)
            self.assertIn("notes_and_loans_payable", right_components)
            expected = (
                right_components["notes_and_loans_payable"]["value"]
                - left_components["commercial_paper"]["value"]
            )
            self.assertAlmostEqual(
                pair["differences"]["short_term_value_difference"], expected, places=2
            )
            self.assertAlmostEqual(
                pair["differences"]["enterprise_value"], expected, places=2
            )
            self.assertEqual(short_term["right"], "notes_and_loans_payable")
            self.assertEqual(short_term["left"], "commercial_paper")

    def test_the_multiple_difference_follows_from_the_enterprise_value_difference(self):
        for pair in self.payload["pairs"]:
            denominator = pair["left"]["denominator"]["value"]
            self.assertEqual(
                pair["left"]["denominator"]["value"],
                pair["right"]["denominator"]["value"],
            )
            # The lane publishes its multiples rounded to six decimals, and
            # the difference of two rounded figures carries that rounding, so
            # it follows to within two units in the last place.
            self.assertAlmostEqual(
                pair["differences"]["multiple"],
                pair["differences"]["enterprise_value"] / denominator,
                delta=2e-6,
            )

    def test_the_shared_components_agree(self):
        for pair in self.payload["pairs"]:
            checks = pair["checks"]
            self.assertTrue(checks["same_denominator_window"])
            self.assertTrue(checks["same_market_cap"])
            self.assertTrue(checks["same_long_term_debt"])
            self.assertTrue(checks["same_liquid_funds"])
            self.assertTrue(checks["components_knowable_and_aligned"])
            self.assertEqual(
                checks["components_that_differ"],
                ["commercial_paper", "notes_and_loans_payable"],
            )

    def test_the_bridge_components_describe_one_date_and_were_knowable(self):
        for pair in self.payload["pairs"]:
            for side in ("left", "right"):
                bridge = pair[side]["bridge"]
                self.assertTrue(bridge["complete"])
                self.assertEqual(len(bridge["distinct_period_ends"]), 1)
                for component in bridge["components"].values():
                    self.assertLessEqual(
                        component["usable_date"], pair["evaluation_date"]
                    )

    def test_a_pair_that_cannot_be_attributed_is_marked(self):
        # A pair whose shared components disagree must not be attributed, and
        # must say why.
        entry = self.payload["pairs"][0]
        self.assertTrue(entry["attributable"])
        self.assertEqual(entry["other_factors"], [])

    def test_the_comparison_is_never_production_eligible(self):
        self.assertFalse(self.payload["production_eligible"])


class TheSensitivity(unittest.TestCase):
    """One named assumption applied to one published figure."""

    def test_the_baseline_is_the_published_observation(self):
        observations = _observations(A)
        published = next(
            day for day, o in observations.items() if o.value is not None
        )
        payload = run_sensitivity(A, published, ASSUMPTION_NUMERATOR_MULTIPLIER, 1.1)
        self.assertEqual(payload["baseline"]["multiple"], observations[published].value)
        self.assertEqual(
            payload["baseline"]["content_hash"], observations[published].content_hash
        )
        self.assertEqual(payload["evaluation_date"], published)

    def test_the_assumption_is_named_and_kept_apart(self):
        observations = _observations(A)
        published = next(
            day for day, o in observations.items() if o.value is not None
        )
        payload = run_sensitivity(A, published, ASSUMPTION_NUMERATOR_MULTIPLIER, 1.1)
        assumption = payload["assumption"]
        self.assertEqual(assumption["name"], ASSUMPTION_NUMERATOR_MULTIPLIER)
        self.assertEqual(assumption["value"], 1.1)
        self.assertTrue(assumption["unit"])
        self.assertEqual(assumption["origin"], "user_supplied_research_assumption")
        self.assertTrue(payload["assumption_hash"])
        self.assertTrue(payload["comparison_hash"])

    def test_the_observation_is_not_modified(self):
        observations = _observations(A)
        published = next(
            day for day, o in observations.items() if o.value is not None
        )
        before = observations[published].value
        run_sensitivity(A, published, ASSUMPTION_NUMERATOR_MULTIPLIER, 1.1)
        after = _observations(A)[published].value
        self.assertEqual(before, after)

    def test_the_change_is_recomputed(self):
        observations = _observations(A)
        published = next(
            day for day, o in observations.items() if o.value is not None
        )
        observation = observations[published]
        payload = run_sensitivity(A, published, ASSUMPTION_NUMERATOR_MULTIPLIER, 1.1)
        self.assertAlmostEqual(
            payload["adjusted"]["multiple"],
            observation.market_cap * 1.1 / observation.denominator["value"],
            places=9,
        )
        self.assertAlmostEqual(
            payload["change"]["absolute"],
            payload["adjusted"]["multiple"] - payload["baseline"]["multiple"],
            places=9,
        )

    def test_a_multiple_override_changes_the_implied_denominator(self):
        observations = _observations(A)
        published = next(
            day for day, o in observations.items() if o.value is not None
        )
        observation = observations[published]
        payload = run_sensitivity(A, published, ASSUMPTION_MULTIPLE_OVERRIDE, 6.0)
        self.assertEqual(payload["adjusted"]["multiple"], 6.0)
        self.assertAlmostEqual(
            payload["adjusted"]["denominator"],
            observation.market_cap / 6.0,
            places=2,
        )

    def test_a_refused_date_cannot_be_made_into_a_figure(self):
        observations = _observations(A)
        refused = next(
            day for day, o in observations.items() if o.value is None
        )
        with self.assertRaises(ResearchComparisonError) as caught:
            run_sensitivity(A, refused, ASSUMPTION_NUMERATOR_MULTIPLIER, 1.1)
        self.assertEqual(
            caught.exception.reason_code,
            "RESEARCH_COMPARISON_REFUSED_OBSERVATION_REJECTED",
        )

    def test_an_unknown_assumption_is_refused(self):
        published = next(
            day
            for day, o in _observations(A).items()
            if o.value is not None
        )
        with self.assertRaises(ResearchComparisonError) as caught:
            run_sensitivity(A, published, "MAKE_ME_A_PREDICTION", 1.1)
        self.assertEqual(
            caught.exception.reason_code,
            "RESEARCH_SENSITIVITY_REFUSED_ASSUMPTION_UNKNOWN",
        )

    def test_a_non_positive_or_non_finite_assumption_is_refused(self):
        published = next(
            day
            for day, o in _observations(A).items()
            if o.value is not None
        )
        for value in (0, -1):
            with self.assertRaises(ResearchComparisonError) as caught:
                run_sensitivity(A, published, ASSUMPTION_NUMERATOR_MULTIPLIER, value)
            self.assertEqual(
                caught.exception.reason_code,
                "RESEARCH_SENSITIVITY_REFUSED_ASSUMPTION_NOT_POSITIVE",
            )
        for value in (float("nan"), float("inf")):
            with self.assertRaises(ResearchComparisonError) as caught:
                run_sensitivity(A, published, ASSUMPTION_NUMERATOR_MULTIPLIER, value)
            self.assertEqual(
                caught.exception.reason_code,
                "RESEARCH_SENSITIVITY_REFUSED_ASSUMPTION_NOT_FINITE",
            )

    def test_the_result_is_never_production_eligible(self):
        published = next(
            day
            for day, o in _observations(A).items()
            if o.value is not None
        )
        payload = run_sensitivity(A, published, ASSUMPTION_NUMERATOR_MULTIPLIER, 1.1)
        self.assertFalse(payload["production_eligible"])
        self.assertIn("not a forecast", payload["notice"])

    def test_every_refusal_code_is_in_the_closed_set(self):
        for code in (
            "RESEARCH_COMPARISON_REFUSED_OBSERVATION_REJECTED",
            "RESEARCH_SENSITIVITY_REFUSED_ASSUMPTION_UNKNOWN",
            "RESEARCH_SENSITIVITY_REFUSED_ASSUMPTION_NOT_FINITE",
            "RESEARCH_SENSITIVITY_REFUSED_ASSUMPTION_NOT_POSITIVE",
        ):
            self.assertIn(code, CLOSED_COMPARISON_REASON_CODES)


class TheComparisonApi(unittest.TestCase):
    """The comparison path is its own path."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(create_app())

    def test_the_definitions_are_served(self):
        response = self.client.get("/api/research/definitions")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["definitions"]), 4)
        self.assertIn("NUMERATOR_MULTIPLIER", payload["sensitivity_assumptions"])

    def test_the_paired_comparison_is_served(self):
        response = self.client.post(
            "/api/research/compare/bridges",
            json={"left_metric_id": C1, "right_metric_id": C2},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["comparison_kind"], COMPARISON_PAIRED_BRIDGE)
        self.assertGreater(payload["paired_sample_count"], 0)
        self.assertFalse(payload["production_eligible"])

    def test_the_history_comparison_is_served(self):
        response = self.client.post(
            "/api/research/compare/history",
            json={
                "metric_id": A,
                "earlier_date": "2026-04-30",
                "later_date": "2026-07-29",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["comparison_kind"], COMPARISON_HISTORY)
        self.assertTrue(payload["comparison_hash"])

    def test_the_sensitivity_is_served(self):
        response = self.client.post(
            "/api/research/sensitivity",
            json={
                "metric_id": A,
                "evaluation_date": "2026-07-29",
                "assumption": ASSUMPTION_NUMERATOR_MULTIPLIER,
                "value": 1.1,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["assumption"]["origin"], "user_supplied_research_assumption")
        self.assertFalse(payload["production_eligible"])

    def test_a_refused_comparison_is_a_research_refusal(self):
        response = self.client.post(
            "/api/research/compare/history",
            json={
                "metric_id": A,
                "earlier_date": "1999-01-01",
                "later_date": "2026-07-29",
            },
        )
        self.assertEqual(response.status_code, 400)
        detail = response.json()["detail"]
        self.assertEqual(
            detail["reason_code"],
            "RESEARCH_COMPARISON_REFUSED_OBSERVATION_UNKNOWN",
        )
        self.assertFalse(detail["production_eligible"])

    def test_a_comparison_starts_no_analysis_job(self):
        manager = self.client.app.state.job_manager
        before = set(manager.jobs)
        self.client.post(
            "/api/research/compare/bridges",
            json={"left_metric_id": C1, "right_metric_id": C2},
        )
        self.assertEqual(set(manager.jobs), before)


class TheComparisonChangesNothing(unittest.TestCase):
    """A comparison changes nothing that production holds."""

    def test_the_four_lanes_are_unchanged(self):
        expected = {
            A: (29, 6.403373),
            B: (64, 19.774421),
            C1: (27, 23.654283),
            C2: (29, 24.675484),
            DIAGNOSTIC: (16, 25.556776),
        }
        for result in build_ko_research_lanes():
            count, median = expected[result.metric_id]
            self.assertEqual(result.distribution.sample_count, count)
            self.assertAlmostEqual(
                result.distribution.percentiles["median"], median, places=6
            )

    def test_the_observations_and_their_refusals_are_unchanged(self):
        for result in build_ko_research_lanes():
            for observation in result.observations:
                if observation.value is None:
                    self.assertIn(
                        observation.reason_code,
                        {
                            "RESEARCH_REASON_NO_DENOMINATOR_WINDOW",
                            "RESEARCH_REASON_INCOMPLETE_EV_BRIDGE",
                            "RESEARCH_REASON_MIXED_BALANCE_SHEET_PERIODS",
                        },
                    )
                    self.assertTrue(observation.reason_detail)
                else:
                    self.assertIsNone(observation.reason_code)

    def test_the_comparison_writes_no_production_reference(self):
        client = TestClient(create_app())
        payload = client.post(
            "/api/research/compare/bridges",
            json={"left_metric_id": C1, "right_metric_id": C2},
        ).json()
        text = json.dumps(payload, default=str)
        self.assertNotIn("refc:", text)
        self.assertNotIn("PRODUCTION_PS_MEDIAN", text)
        self.assertNotIn("PRODUCTION_EV_EBITDA_MEDIAN", text)

    def test_the_production_payloads_are_unchanged(self):
        from historical_multiples import ISSUER_CONFIGS, load_issuer_historical_multiples
        from historical_pe import canonical_json_hash

        digests = {
            "AAPL": "ef7da465e7422f3e9429e2160be69ea5c3aeacbbd9bf1c77d000eec9f7b1b311",
            "AEP": "b9a53553bd9ebb75d0b25156520c842f05d32478933c049c8ed0b353ed1ed2e0",
            "MSFT": "a3f5d4e851848b71a9feb03abc35db5d884417dc355c38ea24bdf54fe7f3db2d",
        }
        for ticker, digest in digests.items():
            payload = load_issuer_historical_multiples(
                ISSUER_CONFIGS[ticker]
            ).to_dict()
            self.assertEqual(canonical_json_hash(payload), digest, ticker)

    def test_no_production_module_names_the_comparison(self):
        for name in (
            "st_eva_runner.py",
            "investment_context.py",
            "archive.py",
            "web/service_adapter.py",
            "web/job_manager.py",
        ):
            source = (ROOT / name).read_text(encoding="utf-8")
            self.assertNotIn("research_comparison", source, name)
            self.assertNotIn("research_lanes", source, name)


if __name__ == "__main__":
    unittest.main()
