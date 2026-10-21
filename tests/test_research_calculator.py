"""
Exercise the research calculation service and the research API path.

The service is the research lane's arithmetic with a user in front of it, so
the tests here are about two things: that the arithmetic and the evidence
are the lane's own, and that nothing a user does can turn a research figure
into a production one.
"""
from __future__ import annotations

import datetime
import json
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from web.app import create_app
from research_calculator import (
    CALCULATOR_VERSION,
    MULTIPLE_HISTORY_MEDIAN,
    MULTIPLE_OBSERVATION,
    MULTIPLE_USER_SUPPLIED,
    NUMERATOR_OBSERVATION,
    NUMERATOR_USER_SUPPLIED,
    USER_ASSUMPTION_LABEL,
    ResearchCalculationError,
    ResearchCalculationRequest,
    list_observations,
    list_research_metrics,
    observation_evidence,
    run_research_calculation,
)
from research_lane_ko import CAPTURE_DIR, build_ko_research_lanes

ROOT = Path(__file__).resolve().parent.parent

EXPECTED = {
    "RESEARCH_KO_REPORTED_REVENUE_MULTIPLE": (29, 6.403373, "market_cap"),
    (
        "RESEARCH_KO_REPORTED_OPERATING_PROFIT_PLUS_REPORTED_D_AND_A_MULTIPLE"
    ): (64, 19.775345, "market_cap"),
    "RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_PRODUCTION_SHAPE": (
        27,
        23.639435,
        "enterprise_value",
    ),
    "RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_SHORT_TERM_BORROWINGS": (
        29,
        24.675484,
        "enterprise_value",
    ),
}

DIAGNOSTIC_METRIC_ID = (
    "RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_DOUBLE_COUNTED_DIAGNOSTIC"
)


class TheCatalogue(unittest.TestCase):
    """The metrics a user may choose."""

    def test_the_four_candidate_lanes_are_offered(self):
        metrics = list_research_metrics()
        self.assertEqual(len(metrics), 4)
        self.assertEqual(
            {metric.metric_id for metric in metrics}, set(EXPECTED)
        )

    def test_the_names_formulas_and_statistics_still_reproduce(self):
        for metric in list_research_metrics():
            count, median, _numerator_kind = EXPECTED[metric.metric_id]
            self.assertEqual(metric.sample_count, count, metric.metric_id)
            self.assertAlmostEqual(
                metric.median, median, places=6, msg=metric.metric_id
            )
            self.assertTrue(metric.formula_expression)
            self.assertTrue(metric.formula_numerator)
            self.assertTrue(metric.formula_denominator)

    def test_no_metric_is_labelled_as_a_production_multiple(self):
        for metric in list_research_metrics():
            label = metric.metric_label.lower()
            # The name says what the formula is, and does not borrow a
            # production multiple's name.
            self.assertNotIn("price to sales", label)
            self.assertNotIn("price-to-sales", label)
            self.assertNotIn("p/s", label)
            self.assertNotIn("ev/ebitda", label)
            self.assertNotIn("ev to ebitda", label)
            # The purpose states the research-only standing, and may name
            # what the metric is not.
            purpose = metric.research_purpose.lower()
            self.assertIn("research use only", purpose)
            self.assertTrue(metric.metric_id.startswith("RESEARCH_"))

    def test_the_diagnostic_is_not_offered(self):
        offered = {metric.metric_id for metric in list_research_metrics()}
        self.assertNotIn(DIAGNOSTIC_METRIC_ID, offered)

    def test_the_diagnostic_cannot_be_selected(self):
        with self.assertRaises(ResearchCalculationError) as caught:
            run_research_calculation(
                ResearchCalculationRequest(metric_id=DIAGNOSTIC_METRIC_ID)
            )
        self.assertEqual(
            caught.exception.reason_code,
            "RESEARCH_CALCULATION_REFUSED_METRIC_NOT_SELECTABLE",
        )

    def test_every_metric_carries_the_registry_standing_and_the_refusal(self):
        for metric in list_research_metrics():
            self.assertTrue(metric.registry_standing)
            self.assertFalse(metric.production_eligible)
            self.assertIn("production_eligible", metric.production_refusal)
            self.assertFalse(metric.production_refusal["production_eligible"])
            self.assertTrue(metric.data_limitations)

    def test_every_metric_states_the_elements_it_reads(self):
        for metric in list_research_metrics():
            elements = set()
            for standing in metric.registry_standing.values():
                elements.update(standing)
            self.assertTrue(elements, metric.metric_id)


class TheEvidenceExplorer(unittest.TestCase):
    """The observations behind a statistic."""

    def test_the_refused_dates_are_shown_with_their_reasons(self):
        observations = list_observations(
            "RESEARCH_KO_REPORTED_REVENUE_MULTIPLE"
        )
        self.assertEqual(len(observations), 67)
        refused = [
            observation
            for observation in observations
            if observation.value is None
        ]
        self.assertEqual(len(refused), 38)
        for observation in refused:
            self.assertTrue(observation.reason_code)
            self.assertTrue(observation.reason_detail)

    def test_one_observation_carries_its_full_evidence(self):
        evidence = observation_evidence(
            "RESEARCH_KO_REPORTED_REVENUE_MULTIPLE", "2026-07-29"
        )
        self.assertEqual(evidence["evaluation_date"], "2026-07-29")
        self.assertIsNotNone(evidence["price"])
        self.assertIsNotNone(evidence["shares_outstanding"])
        self.assertTrue(evidence["shares_accession"])
        self.assertIsNotNone(evidence["market_cap"])
        quarters = evidence["denominator"]["quarters"]
        self.assertEqual(len(quarters), 4)
        for quarter in quarters:
            self.assertTrue(quarter["accessions"])
            self.assertTrue(quarter["elements"])
            self.assertTrue(quarter["knowable_from"])
        for component in (evidence["bridge"].get("components") or {}).values():
            self.assertTrue(component["accession"])
            self.assertTrue(component["usable_date"])
            self.assertTrue(component["content_sha256"])
        self.assertTrue(evidence["registry_standing"])
        self.assertTrue(evidence["capture_identity"]["files"])

    def test_an_unknown_date_is_refused(self):
        with self.assertRaises(ResearchCalculationError) as caught:
            observation_evidence(
                "RESEARCH_KO_REPORTED_REVENUE_MULTIPLE", "1999-01-01"
            )
        self.assertEqual(
            caught.exception.reason_code,
            "RESEARCH_CALCULATION_REFUSED_OBSERVATION_UNKNOWN",
        )


class TheCalculation(unittest.TestCase):
    """The reverse calculation."""

    def test_the_metric_is_never_assumed(self):
        with self.assertRaises(ResearchCalculationError) as caught:
            run_research_calculation(ResearchCalculationRequest(metric_id=""))
        self.assertEqual(
            caught.exception.reason_code,
            "RESEARCH_CALCULATION_REFUSED_METRIC_UNAVAILABLE",
        )

    def test_a_market_cap_lane_divides_a_market_capitalisation(self):
        result = run_research_calculation(
            ResearchCalculationRequest(
                metric_id="RESEARCH_KO_REPORTED_REVENUE_MULTIPLE",
                multiple_source=MULTIPLE_HISTORY_MEDIAN,
                numerator_source=NUMERATOR_OBSERVATION,
            )
        )
        self.assertEqual(result.numerator_kind, "market_cap")
        self.assertIsNotNone(result.numerator)
        self.assertIsNotNone(result.implied_denominator)

    def test_an_enterprise_value_lane_divides_its_own_enterprise_value(self):
        for metric_id in (
            "RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_PRODUCTION_SHAPE",
            "RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_SHORT_TERM_BORROWINGS",
        ):
            result = run_research_calculation(
                ResearchCalculationRequest(
                    metric_id=metric_id,
                    multiple_source=MULTIPLE_HISTORY_MEDIAN,
                    numerator_source=NUMERATOR_OBSERVATION,
                )
            )
            self.assertEqual(result.numerator_kind, "enterprise_value")
            self.assertIsNotNone(result.numerator)
            self.assertIsNotNone(result.implied_denominator)

    def test_the_implied_denominator_is_the_numerator_over_the_multiple(self):
        result = run_research_calculation(
            ResearchCalculationRequest(
                metric_id="RESEARCH_KO_REPORTED_REVENUE_MULTIPLE",
                multiple_source=MULTIPLE_HISTORY_MEDIAN,
                numerator_source=NUMERATOR_OBSERVATION,
            )
        )
        self.assertAlmostEqual(
            result.implied_denominator,
            result.numerator / result.multiple,
            places=6,
        )

    def test_a_multiple_from_one_observation_is_traced_to_it(self):
        observations = list_observations(
            "RESEARCH_KO_REPORTED_REVENUE_MULTIPLE"
        )
        published = next(
            observation for observation in observations if observation.value
        )
        result = run_research_calculation(
            ResearchCalculationRequest(
                metric_id="RESEARCH_KO_REPORTED_REVENUE_MULTIPLE",
                multiple_source=MULTIPLE_OBSERVATION,
                observation_date=published.evaluation_date,
                numerator_source=NUMERATOR_OBSERVATION,
            )
        )
        self.assertAlmostEqual(result.multiple, published.value, places=6)
        self.assertEqual(
            result.multiple_observation_date, published.evaluation_date
        )
        self.assertEqual(
            result.multiple_observation_content_hash, published.content_hash
        )
        self.assertIn("observation", result.multiple_evidence)

    def test_a_refused_observation_cannot_supply_a_multiple(self):
        observations = list_observations(
            "RESEARCH_KO_REPORTED_REVENUE_MULTIPLE"
        )
        refused = next(
            observation for observation in observations if observation.value is None
        )
        with self.assertRaises(ResearchCalculationError) as caught:
            run_research_calculation(
                ResearchCalculationRequest(
                    metric_id="RESEARCH_KO_REPORTED_REVENUE_MULTIPLE",
                    multiple_source=MULTIPLE_OBSERVATION,
                    observation_date=refused.evaluation_date,
                )
            )
        self.assertEqual(
            caught.exception.reason_code,
            "RESEARCH_CALCULATION_REFUSED_OBSERVATION_REJECTED",
        )
        self.assertIn(refused.reason_code, caught.exception.detail)

    def test_a_user_supplied_multiple_is_labelled_an_assumption(self):
        result = run_research_calculation(
            ResearchCalculationRequest(
                metric_id="RESEARCH_KO_REPORTED_REVENUE_MULTIPLE",
                multiple_source=MULTIPLE_USER_SUPPLIED,
                multiple=6.5,
                numerator_source=NUMERATOR_USER_SUPPLIED,
                numerator_value=250_000_000_000,
            )
        )
        self.assertEqual(
            result.multiple_evidence["label"], USER_ASSUMPTION_LABEL
        )
        self.assertEqual(
            result.numerator_evidence["label"], USER_ASSUMPTION_LABEL
        )
        self.assertAlmostEqual(
            result.implied_denominator, 250_000_000_000 / 6.5, places=2
        )

    def test_a_user_supplied_market_value_is_kept_apart_from_the_observations(self):
        result = run_research_calculation(
            ResearchCalculationRequest(
                metric_id="RESEARCH_KO_REPORTED_REVENUE_MULTIPLE",
                multiple_source=MULTIPLE_HISTORY_MEDIAN,
                numerator_source=NUMERATOR_USER_SUPPLIED,
                numerator_value=250_000_000_000,
            )
        )
        self.assertIsNone(result.numerator_date)
        self.assertIsNone(result.numerator_observation_content_hash)
        self.assertEqual(
            result.numerator_evidence["source"], NUMERATOR_USER_SUPPLIED
        )
        # The historical statistics are untouched by the user's own input.
        self.assertEqual(result.lane_input_set_id, list_research_metrics()[0].input_set_id)

    def test_the_result_carries_the_lane_identity_and_the_formula_version(self):
        result = run_research_calculation(
            ResearchCalculationRequest(
                metric_id="RESEARCH_KO_REPORTED_REVENUE_MULTIPLE"
            )
        )
        self.assertTrue(result.lane_input_set_id)
        self.assertTrue(result.lane_content_hash)
        self.assertTrue(result.calculation_content_hash)
        self.assertEqual(result.calculation_version, CALCULATOR_VERSION)
        self.assertTrue(result.formula_expression)
        self.assertTrue(result.formula_version)

    def test_the_execution_record_carries_every_required_field(self):
        observations = list_observations(
            "RESEARCH_KO_REPORTED_REVENUE_MULTIPLE"
        )
        published = next(
            observation for observation in observations if observation.value
        )
        result = run_research_calculation(
            ResearchCalculationRequest(
                metric_id="RESEARCH_KO_REPORTED_REVENUE_MULTIPLE",
                multiple_source=MULTIPLE_OBSERVATION,
                observation_date=published.evaluation_date,
                numerator_source=NUMERATOR_OBSERVATION,
                numerator_date=published.evaluation_date,
            )
        )
        record = result.to_dict()
        # The research metric's identity.
        self.assertEqual(record["metric_id"], "RESEARCH_KO_REPORTED_REVENUE_MULTIPLE")
        # The lane's input set identity and content hash.
        self.assertTrue(record["lane_input_set_id"])
        self.assertTrue(record["lane_content_hash"])
        self.assertTrue(record["capture_identity"]["files"])
        # The formula version.
        self.assertEqual(record["formula_version"], "research-multiples/1.0")
        self.assertEqual(record["calculation_version"], "research-calculator/1.0")
        # The dates, the multiple and the assumptions the user chose.
        self.assertEqual(record["multiple_observation_date"], published.evaluation_date)
        self.assertEqual(record["numerator_date"], published.evaluation_date)
        self.assertAlmostEqual(record["multiple"], published.value, places=6)
        self.assertEqual(record["multiple_source"], MULTIPLE_OBSERVATION)
        self.assertEqual(record["numerator_source"], NUMERATOR_OBSERVATION)
        # The final figure and the basis it rests on.
        self.assertAlmostEqual(
            record["implied_denominator"],
            record["numerator"] / record["multiple"],
            places=6,
        )
        self.assertTrue(record["numerator_evidence"])
        self.assertTrue(record["formula_operands"])
        self.assertTrue(record["calculation_content_hash"])

    def test_the_same_input_gives_the_same_result(self):
        request = ResearchCalculationRequest(
            metric_id="RESEARCH_KO_REPORTED_REVENUE_MULTIPLE",
            multiple_source=MULTIPLE_HISTORY_MEDIAN,
            numerator_source=NUMERATOR_OBSERVATION,
        )
        first = run_research_calculation(request)
        second = run_research_calculation(request)
        self.assertEqual(
            first.calculation_content_hash, second.calculation_content_hash
        )
        self.assertEqual(first.implied_denominator, second.implied_denominator)

    def test_a_different_input_gives_a_different_result(self):
        first = run_research_calculation(
            ResearchCalculationRequest(
                metric_id="RESEARCH_KO_REPORTED_REVENUE_MULTIPLE",
                multiple_source=MULTIPLE_USER_SUPPLIED,
                multiple=6.5,
                numerator_source=NUMERATOR_USER_SUPPLIED,
                numerator_value=250_000_000_000,
            )
        )
        second = run_research_calculation(
            ResearchCalculationRequest(
                metric_id="RESEARCH_KO_REPORTED_REVENUE_MULTIPLE",
                multiple_source=MULTIPLE_USER_SUPPLIED,
                multiple=6.6,
                numerator_source=NUMERATOR_USER_SUPPLIED,
                numerator_value=250_000_000_000,
            )
        )
        self.assertNotEqual(
            first.calculation_content_hash, second.calculation_content_hash
        )

    def test_a_result_is_never_production_eligible(self):
        result = run_research_calculation(
            ResearchCalculationRequest(
                metric_id="RESEARCH_KO_REPORTED_REVENUE_MULTIPLE"
            )
        )
        self.assertFalse(result.production_eligible)
        self.assertIn("RESEARCH USE ONLY", result.research_use_label)
        self.assertFalse(result.production_refusal["production_eligible"])

    def test_a_non_positive_multiple_is_refused(self):
        with self.assertRaises(ResearchCalculationError) as caught:
            run_research_calculation(
                ResearchCalculationRequest(
                    metric_id="RESEARCH_KO_REPORTED_REVENUE_MULTIPLE",
                    multiple_source=MULTIPLE_USER_SUPPLIED,
                    multiple=0,
                )
            )
        self.assertEqual(
            caught.exception.reason_code,
            "RESEARCH_CALCULATION_REFUSED_MULTIPLE_NOT_POSITIVE",
        )

    def test_a_non_positive_market_value_is_refused(self):
        with self.assertRaises(ResearchCalculationError) as caught:
            run_research_calculation(
                ResearchCalculationRequest(
                    metric_id="RESEARCH_KO_REPORTED_REVENUE_MULTIPLE",
                    numerator_source=NUMERATOR_USER_SUPPLIED,
                    numerator_value=-1,
                )
            )
        self.assertEqual(
            caught.exception.reason_code,
            "RESEARCH_CALCULATION_REFUSED_NUMERATOR_NOT_POSITIVE",
        )

    def test_an_enterprise_value_lane_refuses_without_a_complete_bridge(self):
        # A lane whose bridge is incomplete on the requested date has no
        # enterprise value to apply, and says so rather than filling the gap.
        observations = list_observations(
            "RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_SHORT_TERM_BORROWINGS"
        )
        refused = next(
            observation
            for observation in observations
            if observation.value is None
            and observation.reason_code
            == "RESEARCH_REASON_INCOMPLETE_EV_BRIDGE"
        )
        with self.assertRaises(ResearchCalculationError) as caught:
            run_research_calculation(
                ResearchCalculationRequest(
                    metric_id=(
                        "RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_SHORT_TERM_BORROWINGS"
                    ),
                    numerator_source=NUMERATOR_OBSERVATION,
                    numerator_date=refused.evaluation_date,
                )
            )
        self.assertEqual(
            caught.exception.reason_code,
            "RESEARCH_CALCULATION_REFUSED_OBSERVATION_REJECTED",
        )
        self.assertIn("RESEARCH_REASON_INCOMPLETE_EV_BRIDGE", caught.exception.detail)


class TheResearchIsolation(unittest.TestCase):
    """A research figure reaches nothing in production."""

    def test_a_research_calculation_writes_no_archive(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            archives = Path(directory) / "archives"
            archives.mkdir()
            before = sorted(path.name for path in archives.iterdir())
            run_research_calculation(
                ResearchCalculationRequest(
                    metric_id="RESEARCH_KO_REPORTED_REVENUE_MULTIPLE"
                )
            )
            after = sorted(path.name for path in archives.iterdir())
            self.assertEqual(before, after)

    def test_the_production_payloads_hold_no_research_figure(self):
        from historical_multiples import ISSUER_CONFIGS, load_issuer_historical_multiples

        for ticker in ("AAPL", "AEP", "MSFT"):
            payload = json.dumps(
                load_issuer_historical_multiples(
                    ISSUER_CONFIGS[ticker]
                ).to_dict(),
                default=str,
            )
            self.assertNotIn("RESEARCH_", payload, ticker)
            self.assertNotIn("research_lane", payload, ticker)
            self.assertNotIn("research-multiples", payload, ticker)

    def test_the_production_runner_does_not_read_the_research_tree(self):
        for name in (
            "st_eva_runner.py",
            "investment_context.py",
            "archive.py",
            "web/service_adapter.py",
            "web/job_manager.py",
        ):
            source = (ROOT / name).read_text(encoding="utf-8")
            self.assertNotIn("research_lane", source, name)
            self.assertNotIn("research_lanes", source, name)
            self.assertNotIn("research_multiples", source, name)
            self.assertNotIn("research_calculator", source, name)

    def test_the_research_path_is_not_the_production_path(self):
        client = TestClient(create_app())
        paths = set(client.app.openapi()["paths"])
        self.assertIn("/api/research/metrics", paths)
        self.assertIn("/api/research/calculate", paths)
        self.assertIn("/api/research/metrics/{metric_id}", paths)
        self.assertIn(
            "/api/research/metrics/{metric_id}/observations/{evaluation_date}",
            paths,
        )
        self.assertIn("/api/analyze", paths)
        self.assertIn("/api/jobs/{job_id}", paths)


class TheRefusals(unittest.TestCase):
    """The conditions that must refuse a calculation."""

    def test_a_capture_that_does_not_match_its_manifest_is_refused(self):
        import shutil
        import tempfile

        import research_calculator

        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory) / "KO"
            shutil.copytree(research_calculator.CAPTURE_DIR, copy)
            target = copy / "revenue_concept.json"
            target.write_text(
                target.read_text(encoding="utf-8") + "\n", encoding="utf-8"
            )
            original = research_calculator.CAPTURE_DIR
            research_calculator.CAPTURE_DIR = copy
            research_calculator._reset_lane_cache()
            try:
                with self.assertRaises(ResearchCalculationError) as caught:
                    run_research_calculation(
                        ResearchCalculationRequest(
                            metric_id="RESEARCH_KO_REPORTED_REVENUE_MULTIPLE"
                        )
                    )
            finally:
                research_calculator.CAPTURE_DIR = original
                research_calculator._reset_lane_cache()
            self.assertEqual(
                caught.exception.reason_code,
                "RESEARCH_CALCULATION_REFUSED_DATA_IDENTITY_MISMATCH",
            )

    def test_a_denominator_that_cannot_be_formed_refuses_the_multiple(self):
        # A metric with no valid observation has no median to apply.
        result = run_research_calculation(
            ResearchCalculationRequest(
                metric_id="RESEARCH_KO_REPORTED_REVENUE_MULTIPLE",
                multiple_source=MULTIPLE_HISTORY_MEDIAN,
                numerator_source=NUMERATOR_OBSERVATION,
            )
        )
        self.assertIsNotNone(result.multiple)

    def test_a_missing_price_refuses_the_observation(self):
        import hashlib
        import shutil
        import tempfile

        from research_lane import FORMULA_DENOMINATOR, ResearchLaneConfig, ResearchRole
        from research_lane import load_research_lane

        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory) / "KO"
            shutil.copytree(CAPTURE_DIR, copy)
            prices_path = copy / "daily_prices.json"
            document = json.loads(prices_path.read_text(encoding="utf-8"))
            result = document["chart"]["result"][0]
            # The price series is cut short, so the last filing's usable date
            # falls after it and that date has no price.
            keep = [
                index
                for index, stamp in enumerate(result["timestamp"])
                if datetime.datetime.fromtimestamp(
                    stamp, datetime.timezone.utc
                ).date()
                <= datetime.date(2026, 6, 30)
            ]
            for key in ("timestamp",):
                result[key] = [result[key][index] for index in keep]
            indicators = result.get("indicators") or {}
            for name, series in list(indicators.items()):
                if isinstance(series, list):
                    for block in series:
                        for key, values in list(block.items()):
                            if isinstance(values, list):
                                block[key] = [values[index] for index in keep]
                else:
                    for key, values in list(series.items()):
                        if isinstance(values, list):
                            series[key] = [values[index] for index in keep]
            prices_path.write_text(json.dumps(document), encoding="utf-8")

            # The capture's manifest pins its own files, so the mutated
            # capture declares the digest it now has.
            manifest_path = copy / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"]["daily_prices.json"]["sha256"] = hashlib.sha256(
                prices_path.read_bytes()
            ).hexdigest()
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            config = ResearchLaneConfig(
                lane_id="ko_missing_price_probe",
                issuer_id="CIK0000021344",
                instrument_id="KO",
                entity_name="The Coca-Cola Company",
                fye_month=12,
                capture_dir=copy,
                metric_id="RESEARCH_KO_MISSING_PRICE_PROBE",
                metric_label="probe",
                research_purpose="A probe whose price is missing.",
                formula_expression="probe",
                formula_numerator="probe",
                formula_denominator="probe",
                denominator_roles=("revenue",),
                roles=(
                    ResearchRole(
                        name="revenue",
                        taxonomy="us-gaap",
                        elements=("Revenues",),
                        formula_role=FORMULA_DENOMINATOR,
                        registry_metric_id="revenue",
                    ),
                ),
            )
            lane = load_research_lane(config)
            refused = next(
                observation
                for observation in lane.observations
                if observation.value is None
                and observation.reason_code == "RESEARCH_REASON_MISSING_PRICE"
            )
            self.assertIsNone(refused.value)
            self.assertTrue(refused.reason_detail)
            # The evaluation date whose price the capture does not carry is
            # refused, not filled with a stale price.
            self.assertEqual(refused.evaluation_date, "2026-07-29")

    def test_the_registry_standing_the_lane_depends_on_is_unchanged(self):
        standing = {
            metric.metric_id: metric.registry_standing
            for metric in list_research_metrics()
        }
        revenue = standing["RESEARCH_KO_REPORTED_REVENUE_MULTIPLE"]["revenue"]
        self.assertEqual(
            revenue["Revenues"]["registry_decision"], "NOT_QUALIFIED"
        )
        self.assertEqual(
            revenue["Revenues"]["reason_code"], "NO_MAPPING_FOR_METRIC"
        )
        operating = standing[
            "RESEARCH_KO_REPORTED_OPERATING_PROFIT_PLUS_REPORTED_D_AND_A_MULTIPLE"
        ]
        self.assertEqual(
            operating["operating_income"]["OperatingIncomeLoss"][
                "registry_decision"
            ],
            "QUALIFIED",
        )
        self.assertEqual(
            operating["depreciation"]["DepreciationDepletionAndAmortization"][
                "registry_decision"
            ],
            "NOT_QUALIFIED",
        )
        self.assertEqual(
            operating["depreciation"]["DepreciationDepletionAndAmortization"][
                "reason_code"
            ],
            "SCOPE_NOT_APPLICABLE",
        )

    def test_the_lane_refuses_a_missing_price_or_share_count(self):
        from research_lane import CLOSED_REASON_CODES

        self.assertIn("RESEARCH_REASON_MISSING_PRICE", CLOSED_REASON_CODES)
        self.assertIn("RESEARCH_REASON_MISSING_SHARES", CLOSED_REASON_CODES)

    def test_a_point_in_time_violation_cannot_reach_a_result(self):
        # Every fact a published observation rests on was knowable at that
        # observation's date.
        for result in build_ko_research_lanes():
            for observation in result.observations:
                if observation.value is None:
                    continue
                day = observation.evaluation_date
                for quarter in (observation.denominator or {}).get("quarters", []):
                    for span in quarter["input_spans"]:
                        self.assertLessEqual(span["usable_date"], day)
                for component in (observation.bridge.get("components") or {}).values():
                    self.assertLessEqual(component["usable_date"], day)


class TheResearchApi(unittest.TestCase):
    """The research path is its own path."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(create_app())

    def test_the_catalogue_is_served(self):
        response = self.client.get("/api/research/metrics")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["metrics"]), 4)
        self.assertIn("RESEARCH USE ONLY", payload["research_use_notice"])
        self.assertEqual(
            payload["user_assumption_label"], USER_ASSUMPTION_LABEL
        )

    def test_the_detail_carries_the_observations(self):
        response = self.client.get(
            "/api/research/metrics/RESEARCH_KO_REPORTED_REVENUE_MULTIPLE"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["observations"]), 67)
        refused = [
            observation
            for observation in payload["observations"]
            if observation["value"] is None
        ]
        self.assertEqual(len(refused), 38)
        for observation in refused:
            self.assertTrue(observation["reason_code"])
            self.assertTrue(observation["reason_detail"])

    def test_the_evidence_of_one_observation_is_served(self):
        response = self.client.get(
            "/api/research/metrics/RESEARCH_KO_REPORTED_REVENUE_MULTIPLE"
            "/observations/2026-07-29"
        )
        self.assertEqual(response.status_code, 200)
        evidence = response.json()["evidence"]
        self.assertEqual(len(evidence["denominator"]["quarters"]), 4)
        self.assertTrue(evidence["shares_accession"])

    def test_a_calculation_is_served(self):
        response = self.client.post(
            "/api/research/calculate",
            json={
                "metric_id": "RESEARCH_KO_REPORTED_REVENUE_MULTIPLE",
                "multiple_source": MULTIPLE_HISTORY_MEDIAN,
                "numerator_source": NUMERATOR_OBSERVATION,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["production_eligible"])
        self.assertTrue(payload["calculation_content_hash"])
        self.assertTrue(payload["lane_input_set_id"])
        self.assertAlmostEqual(
            payload["implied_denominator"],
            payload["numerator"] / payload["multiple"],
            places=6,
        )

    def test_the_diagnostic_is_refused_over_the_api(self):
        response = self.client.post(
            "/api/research/calculate",
            json={"metric_id": DIAGNOSTIC_METRIC_ID},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"]["reason_code"],
            "RESEARCH_CALCULATION_REFUSED_METRIC_NOT_SELECTABLE",
        )
        self.assertFalse(response.json()["detail"]["production_eligible"])

    def test_the_research_path_does_not_answer_the_production_path(self):
        response = self.client.post(
            "/api/analyze", json={"ticker": "KO", "mode": "live"}
        )
        # The production path is untouched and does not know the research
        # metric; the research path is a separate route.
        self.assertNotEqual(response.status_code, 404)

    def test_the_research_path_writes_no_archive(self):
        client = TestClient(create_app(archives_dir=None))
        response = client.get("/api/research/metrics")
        self.assertEqual(response.status_code, 200)
        # No archive directory was created by the research path.
        self.assertFalse((ROOT / "data" / "archives" / "KO").exists())


if __name__ == "__main__":
    unittest.main()
