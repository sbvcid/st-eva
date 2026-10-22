"""The research issuer configuration, the unit policy and the second case.

A research lane is described by a configuration, and the configuration is
the only place an issuer's elements, roles, formulas and units are written
down. These tests check that the configuration is validated, that a lane
refuses inputs it cannot state the units of, and that the migration left the
KO case's results, identities and isolation exactly as they were.
"""
from __future__ import annotations

import dataclasses
import json
import unittest
from pathlib import Path

from historical_multiples import ISSUER_CONFIGS, load_issuer_historical_multiples
from research_calculator import ResearchCalculationRequest, run_research_calculation
from research_comparison import compare_bridges
from research_issuers import (
    CONFIG_PATH,
    IssuerConfigurationError,
    all_lane_ids,
    build_lane_results,
    candidate_lane_ids,
    config_for_lane,
    lane_configs,
    load_issuer_settings,
    settings_for_ticker,
)
from research_lane import (
    BRIDGE_GROUP_LONG_TERM,
    BRIDGE_GROUP_SHORT_TERM,
    FORMULA_DENOMINATOR,
    FORMULA_SHARES,
    ResearchLaneConfig,
    ResearchRole,
    ResearchUnitPolicy,
    load_research_lane,
)

ROOT = Path(__file__).resolve().parent.parent
C1 = "RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_PRODUCTION_SHAPE"
C2 = "RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_SHORT_TERM_BORROWINGS"
A = "RESEARCH_KO_REPORTED_REVENUE_MULTIPLE"
B = "RESEARCH_KO_REPORTED_OPERATING_PROFIT_PLUS_REPORTED_D_AND_A_MULTIPLE"
DIAGNOSTIC = "RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_DOUBLE_COUNTED_DIAGNOSTIC"


class TheConfiguration(unittest.TestCase):
    """The configuration is loaded, validated and the only source."""

    def test_the_configuration_is_the_only_source(self):
        self.assertTrue(CONFIG_PATH.exists())
        document = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        self.assertEqual(document["schema_version"], 1)
        self.assertEqual(
            [issuer["ticker"] for issuer in document["issuers"]],
            ["KO", "AAPL", "MSFT"],
        )

    def test_the_element_table_is_written_down_once(self):
        document = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        for issuer in document["issuers"]:
            capture = issuer["capture"]["elements"]
            for role in issuer["roles"]:
                # A role names the capture role it reads; the elements
                # themselves live in the capture's table and nowhere else.
                self.assertIn(role["capture_role"], capture)
                self.assertNotIn("elements", role)

    def test_the_roles_read_the_elements_the_capture_holds(self):
        for settings in load_issuer_settings():
            for role in settings.roles:
                element = settings.capture["elements"][role.capture_role]
                self.assertEqual(role.taxonomy, element["taxonomy"])
                self.assertEqual(list(role.elements), element["elements"])

    def test_the_lanes_name_roles_the_issuer_declares(self):
        for settings in load_issuer_settings():
            names = {role.name for role in settings.roles}
            for lane in settings.lanes:
                for role in lane.denominator_roles:
                    self.assertIn(role, names)
                for role in lane.roles:
                    if role.formula_role == "BRIDGE_COMPONENT":
                        self.assertIn(role.name, names)

    def test_a_duplicate_lane_id_is_refused(self):
        document = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        document["issuers"][1]["lanes"][0]["lane_id"] = document["issuers"][0][
            "lanes"
        ][0]["lane_id"]
        with self.assertRaises(IssuerConfigurationError) as caught:
            self._load(document)
        self.assertIn("declared twice", str(caught.exception))

    def test_a_duplicate_research_metric_id_is_refused(self):
        document = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        document["issuers"][1]["lanes"][0]["metric_id"] = document["issuers"][0][
            "lanes"
        ][0]["metric_id"]
        with self.assertRaises(IssuerConfigurationError) as caught:
            self._load(document)
        self.assertIn("declared twice", str(caught.exception))

    def test_a_research_metric_id_that_takes_a_production_name_is_refused(self):
        document = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        document["issuers"][0]["lanes"][0]["metric_id"] = "PRODUCTION_PS_MEDIAN"
        with self.assertRaises(IssuerConfigurationError) as caught:
            self._load(document)
        self.assertIn("collide", str(caught.exception).lower())

    def test_a_role_that_reads_a_capture_role_the_capture_lacks_is_refused(self):
        document = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        document["issuers"][0]["roles"][0]["capture_role"] = "no_such_role"
        with self.assertRaises(IssuerConfigurationError) as caught:
            self._load(document)
        self.assertIn("no such role", str(caught.exception))

    def test_a_lane_that_names_an_unknown_role_is_refused(self):
        document = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        document["issuers"][0]["lanes"][0]["denominator_roles"] = ["no_such_role"]
        with self.assertRaises(IssuerConfigurationError) as caught:
            self._load(document)
        self.assertIn("no_such_role", str(caught.exception))

    def test_an_unknown_formula_role_is_refused(self):
        document = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        document["issuers"][0]["roles"][0]["formula_role"] = "NOT_A_ROLE"
        with self.assertRaises(IssuerConfigurationError) as caught:
            self._load(document)
        self.assertIn("unknown formula role", str(caught.exception))

    def test_a_missing_configuration_is_refused(self):
        with self.assertRaises(IssuerConfigurationError) as caught:
            load_issuer_settings(Path("/nonexistent/research_issuers.json"))
        self.assertIn("missing", str(caught.exception))

    def test_an_issuer_that_is_not_configured_is_refused(self):
        with self.assertRaises(IssuerConfigurationError) as caught:
            settings_for_ticker("NOPE")
        self.assertIn("no research issuer", str(caught.exception))

    def _load(self, document):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "research_issuers.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            return load_issuer_settings(path)


class TheSecondCase(unittest.TestCase):
    """AAPL is configured, its capture is committed, and its lanes compute."""

    def test_the_issuer_is_configured(self):
        settings = settings_for_ticker("AAPL")
        self.assertEqual(settings.issuer_id, "CIK0000320193")
        self.assertEqual(settings.entity_name, "Apple Inc.")
        self.assertEqual(settings.fiscal_year_end, "09-26")
        self.assertEqual(settings.fye_month, 9)
        self.assertTrue(settings.capture_dir.exists())

    def test_its_calendar_splits_and_semantics_are_expressible(self):
        settings = settings_for_ticker("AAPL")
        elements = settings.capture["elements"]
        # The revenue element's chronology, and the registry's standing on it.
        self.assertEqual(
            elements["revenue"]["elements"],
            [
                "Revenues",
                "RevenueFromContractWithCustomerExcludingAssessedTax",
            ],
        )
        # The depreciation element's chronology.
        self.assertEqual(
            elements["depreciation"]["elements"],
            [
                "DepreciationAndAmortization",
                "DepreciationDepletionAndAmortization",
            ],
        )
        # The two splits in the price series's range, and the acceptances
        # after 16:00 ET, are facts about the filer, not about the lane.
        note = next(
            role.note
            for role in settings.roles
            if role.name == "shares_outstanding"
        )
        self.assertIn("7:1", note)
        self.assertIn("4:1", note)

    def test_its_lanes_are_offered(self):
        settings = settings_for_ticker("AAPL")
        self.assertTrue(settings.lanes)
        for lane in settings.lanes:
            self.assertIn(lane.lane_id, candidate_lane_ids())
            self.assertIn(lane.lane_id, all_lane_ids())

    def test_the_end_to_end_verification_is_established(self):
        """
        AAPL's capture is committed, so its lanes compute.

        The figures are the lane's own. Nothing here is a production
        reference, and no production figure may be read out of them.
        """
        results = build_lane_results(issuer_ids=["AAPL"])
        self.assertEqual(
            sorted(results),
            [
                "aapl_filed_ev_bridge_multiple_production_shape",
                "aapl_reported_operating_profit_plus_reported_d_and_a_multiple",
                "aapl_reported_revenue_multiple",
            ],
        )
        for result in results.values():
            self.assertEqual(
                result.distribution.status, "RESEARCH_DISTRIBUTION", result.lane_id
            )
            self.assertTrue(result.input_set_id)
            self.assertTrue(result.content_hash)
            self.assertFalse(result.distribution.production_eligible)


class TheThirdCase(unittest.TestCase):
    """MSFT is configured, its capture is committed, and its lanes compute."""

    def test_the_issuer_is_configured(self):
        settings = settings_for_ticker("MSFT")
        self.assertEqual(settings.issuer_id, "CIK0000789019")
        self.assertEqual(settings.entity_name, "Microsoft Corporation")
        self.assertEqual(settings.fiscal_year_end, "06-30")
        self.assertEqual(settings.fye_month, 6)
        self.assertTrue(settings.capture_dir.exists())

    def test_its_calendar_and_elements_are_expressible(self):
        settings = settings_for_ticker("MSFT")
        elements = settings.capture["elements"]
        # MSFT files its revenue on us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax,
        # which the registry accepts as an exact identity mapping.
        self.assertEqual(
            elements["revenue"]["elements"],
            ["RevenueFromContractWithCustomerExcludingAssessedTax"],
        )
        self.assertEqual(
            elements["operating_income"]["elements"],
            ["OperatingIncomeLoss"],
        )
        # MSFT files no depreciation-and-amortization total; the depreciation role
        # names us-gaap:DepreciationDepletionAndAmortization, which is not filed.
        self.assertEqual(
            elements["depreciation"]["elements"],
            ["DepreciationDepletionAndAmortization"],
        )
        # MSFT's fiscal year ends 30 June.
        self.assertEqual(settings.fye_month, 6)

    def test_its_lanes_are_offered(self):
        settings = settings_for_ticker("MSFT")
        self.assertTrue(settings.lanes)
        for lane in settings.lanes:
            self.assertIn(lane.lane_id, candidate_lane_ids())
            self.assertIn(lane.lane_id, all_lane_ids())

    def test_the_end_to_end_verification_is_established(self):
        """
        MSFT's capture is committed, so its lanes compute.

        The revenue lane computes; the operating-profit-plus-depreciation lane
        refuses because MSFT files no depreciation-and-amortization total.
        """
        results = build_lane_results(issuer_ids=["MSFT"])
        self.assertEqual(
            sorted(results),
            [
                "msft_filed_ev_bridge_multiple_over_revenue",
                "msft_reported_operating_profit_plus_reported_d_and_a_multiple",
                "msft_reported_revenue_multiple",
            ],
        )
        revenue = results["msft_reported_revenue_multiple"]
        da = results["msft_reported_operating_profit_plus_reported_d_and_a_multiple"]
        self.assertEqual(revenue.distribution.status, "RESEARCH_DISTRIBUTION")
        self.assertEqual(revenue.distribution.sample_count, 33)
        self.assertEqual(da.distribution.status, "RESEARCH_UNAVAILABLE")
        self.assertEqual(da.distribution.reason_code, "RESEARCH_REASON_ELEMENT_UNAVAILABLE")
        self.assertTrue(revenue.input_set_id)
        self.assertTrue(revenue.content_hash)
        self.assertFalse(revenue.distribution.production_eligible)


class TheThirdCaseAgainstProduction(unittest.TestCase):
    """
    MSFT's research revenue lane and the production P/S reference read the
    same filed facts.

    The research lane reaches further back than the production dataset, so
    the two datasets do not evaluate the same dates. Where both publish, the
    figures must agree, and where only the research lane publishes, the
    difference must be the reach of the two datasets over the same filed
    facts and not a disagreement about arithmetic.
    """

    REVENUE_LANE = "msft_reported_revenue_multiple"

    @classmethod
    def setUpClass(cls):
        cls.production = {
            observation["evaluation_date"]: observation
            for observation in load_issuer_historical_multiples(
                ISSUER_CONFIGS["MSFT"]
            ).to_dict()["observations"]
        }
        cls.results = build_lane_results(issuer_ids=["MSFT"])

    def test_the_revenue_lane_matches_production_wherever_both_publish(self):
        lane = self.results[self.REVENUE_LANE]
        shared = 0
        for observation in lane.observations:
            other = self.production.get(observation.evaluation_date)
            if other is None or observation.value is None:
                continue
            if other.get("ps_ratio") is None:
                continue
            shared += 1
            self.assertEqual(
                observation.price, other["price"], observation.evaluation_date
            )
            self.assertEqual(
                observation.shares_outstanding,
                other["shares_outstanding"],
                observation.evaluation_date,
            )
            self.assertAlmostEqual(
                observation.value,
                other["ps_ratio"],
                places=6,
                msg=observation.evaluation_date,
            )
        self.assertEqual(shared, 21)

    def test_the_dates_only_the_research_lane_reaches_are_named(self):
        """
        On three of the dates both datasets evaluate, only the research lane
        publishes. Production refuses the window under its own rule and
        refuses rather than backfill a quarter from a later filing; the
        research capture reads each quarter from the annual filing that
        stated it, which was public before the evaluation date. The dates
        are named rather than reconciled away.
        """
        lane = self.results[self.REVENUE_LANE]
        research_only = []
        for observation in lane.observations:
            other = self.production.get(observation.evaluation_date)
            if other is None or observation.value is None:
                continue
            if other.get("ps_ratio") is None:
                research_only.append(observation)
        self.assertEqual(
            [observation.evaluation_date for observation in research_only],
            ["2020-10-28", "2021-01-27", "2021-04-28"],
        )
        for observation in research_only:
            other = self.production[observation.evaluation_date]
            self.assertIsNone(other["ps_ratio"])
            self.assertEqual(
                other["ps_reason_code"], "REASON_MISSING_REVENUE_WINDOW"
            )

    def test_the_first_research_only_window_is_pit_clean_and_crosses_the_june_boundary(
        self,
    ):
        """
        The 2020-10-28 window is four consecutive quarters of MSFT's June
        cycle -- Q2, Q3 and Q4 of FY2020 plus Q1 of FY2021 -- and every
        quarter was public before the evaluation date: the three FY2020
        quarters from the FY2020 10-K, accepted after the close of
        2020-07-30 and so usable from 2020-07-31, and Q1 FY2021 from the
        10-Q accepted after the close of 2020-10-27, usable 2020-10-28.
        """
        lane = self.results[self.REVENUE_LANE]
        observation = next(
            item
            for item in lane.observations
            if item.evaluation_date == "2020-10-28"
        )
        quarters = observation.denominator["quarters"]
        self.assertEqual(
            [quarter["period_end"] for quarter in quarters],
            ["2019-12-31", "2020-03-31", "2020-06-30", "2020-09-30"],
        )
        self.assertEqual(
            [(quarter["fiscal_year"], quarter["fiscal_quarter"]) for quarter in quarters],
            [(2020, 2), (2020, 3), (2020, 4), (2021, 1)],
        )
        for quarter in quarters:
            self.assertLessEqual(
                quarter["knowable_from"], observation.evaluation_date
            )
        self.assertEqual(quarters[0]["knowable_from"], "2020-07-31")
        self.assertEqual(quarters[1]["knowable_from"], "2020-07-31")
        self.assertEqual(quarters[2]["knowable_from"], "2020-07-31")
        self.assertEqual(quarters[3]["knowable_from"], "2020-10-28")


class TheUnitPolicy(unittest.TestCase):
    """A lane refuses inputs it cannot state the units of."""

    def setUp(self):
        self.config = config_for_lane("ko_reported_revenue_multiple")

    def _lane(self, **overrides):
        return dataclasses.replace(self.config, **overrides)

    def test_the_policy_states_the_units_the_capture_uses(self):
        policy = self.config.unit_policy
        self.assertEqual(policy.filing_unit, "USD")
        self.assertEqual(policy.filing_currency, "USD")
        self.assertEqual(policy.price_currency, "USD")
        self.assertEqual(policy.share_unit, "shares")
        self.assertEqual(policy.scale, 1)
        self.assertTrue(policy.scale_basis)

    def test_the_policy_is_recorded_on_the_distribution(self):
        result = load_research_lane(self.config)
        policy = result.distribution.unit_policy
        self.assertEqual(policy["filing_unit"], "USD")
        self.assertEqual(policy["observed_price_currency"], "USD")
        self.assertEqual(policy["observed_share_unit"], "shares")
        self.assertEqual(policy["role_units"]["revenue"], "USD")

    def test_a_denominator_in_another_unit_is_refused(self):
        lane = load_research_lane(
            self._lane(
                unit_policy=dataclasses.replace(
                    self.config.unit_policy, filing_unit="EUR"
                )
            )
        )
        self.assertEqual(lane.distribution.status, "RESEARCH_UNAVAILABLE")
        self.assertEqual(
            lane.distribution.reason_code, "RESEARCH_REASON_UNIT_CONFLICT"
        )
        self.assertEqual(lane.observations, [])

    def test_a_price_in_another_currency_is_refused(self):
        lane = load_research_lane(
            self._lane(
                unit_policy=dataclasses.replace(
                    self.config.unit_policy, price_currency="EUR"
                )
            )
        )
        self.assertEqual(
            lane.distribution.reason_code, "RESEARCH_REASON_CURRENCY_MISMATCH"
        )

    def test_a_denominator_and_a_price_in_different_currencies_are_refused(self):
        lane = load_research_lane(
            self._lane(
                unit_policy=dataclasses.replace(
                    self.config.unit_policy, filing_currency="EUR"
                )
            )
        )
        self.assertEqual(
            lane.distribution.reason_code, "RESEARCH_REASON_CURRENCY_MISMATCH"
        )
        self.assertIn("conversion rule", lane.distribution.reason_detail)

    def test_a_declared_conversion_rule_lets_the_currencies_differ(self):
        lane = load_research_lane(
            self._lane(
                unit_policy=dataclasses.replace(
                    self.config.unit_policy,
                    filing_currency="EUR",
                    fx_rule="the issuer's reported rate on the evaluation date",
                )
            )
        )
        self.assertNotEqual(
            lane.distribution.reason_code, "RESEARCH_REASON_CURRENCY_MISMATCH"
        )
        self.assertTrue(lane.observations)

    def test_a_lane_with_no_share_count_is_refused(self):
        lane = load_research_lane(
            self._lane(
                roles=tuple(
                    role
                    for role in self.config.roles
                    if role.formula_role != FORMULA_SHARES
                )
            )
        )
        self.assertEqual(
            lane.distribution.reason_code, "RESEARCH_REASON_UNIT_UNKNOWN"
        )
        self.assertEqual(lane.observations, [])

    def test_a_scale_that_is_not_positive_is_refused(self):
        with self.assertRaises(ValueError):
            ResearchUnitPolicy(
                filing_unit="USD",
                filing_currency="USD",
                price_currency="USD",
                share_unit="shares",
                scale=0,
            )

    def test_a_policy_that_names_no_unit_is_refused(self):
        with self.assertRaises(ValueError):
            ResearchUnitPolicy(
                filing_unit="",
                filing_currency="USD",
                price_currency="USD",
                share_unit="shares",
            )


class TheBridgeGroups(unittest.TestCase):
    """The comparison reads the groups, not the component names."""

    def test_ko_declares_its_groups(self):
        config = config_for_lane("ko_filed_ev_bridge_multiple_production_shape")
        groups = {role.name: role.bridge_group for role in config.roles}
        self.assertEqual(groups["cash"], "LIQUID")
        self.assertEqual(groups["marketable_securities_current"], "LIQUID")
        self.assertEqual(groups["commercial_paper"], "SHORT_TERM")
        self.assertEqual(groups["long_term_debt_current"], BRIDGE_GROUP_LONG_TERM)
        self.assertEqual(groups["long_term_debt_noncurrent"], BRIDGE_GROUP_LONG_TERM)

    def test_the_paired_differences_still_recompute(self):
        payload = compare_bridges(C1, C2)
        self.assertEqual(payload["paired_sample_count"], 16)
        self.assertEqual(payload["attributable_sample_count"], 16)
        for pair in payload["pairs"]:
            self.assertTrue(pair["attributable"])
            self.assertAlmostEqual(
                pair["differences"]["enterprise_value"],
                pair["differences"]["short_term_value_difference"],
                places=2,
            )


class TheMigration(unittest.TestCase):
    """The migration left the KO case as it was."""

    def test_the_lanes_still_produce_their_figures(self):
        expected = {
            "ko_reported_revenue_multiple": (29, 6.403373),
            "ko_reported_operating_denominator_multiple": (64, 19.774421),
            "ko_filed_ev_bridge_multiple_production_shape": (27, 23.654283),
            "ko_filed_ev_bridge_multiple_short_term_borrowings": (29, 24.675484),
        }
        results = build_lane_results(issuer_ids=["KO"])
        for lane_id, (count, median) in expected.items():
            distribution = results[lane_id].distribution
            self.assertEqual(distribution.sample_count, count, lane_id)
            self.assertAlmostEqual(
                distribution.percentiles["median"], median, places=6, msg=lane_id
            )

    def test_the_identity_contract_still_holds(self):
        results = build_lane_results(issuer_ids=["KO"])
        for result in results.values():
            self.assertTrue(result.input_set_id)
            self.assertTrue(result.content_hash)
            for observation in result.observations:
                self.assertTrue(observation.content_hash)
                self.assertEqual(observation.input_set_id, result.input_set_id)

    def test_the_capture_is_unchanged_and_its_digests_verify(self):
        import hashlib

        manifest = json.loads(
            (
                ROOT / "data" / "research_multiples" / "KO" / "manifest.json"
            ).read_text(encoding="utf-8")
        )
        for name, entry in manifest["files"].items():
            path = ROOT / "data" / "research_multiples" / "KO" / name
            self.assertTrue(path.exists(), name)
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(),
                entry["sha256"],
                name,
            )

    def test_the_diagnostic_is_not_selectable(self):
        self.assertNotIn(DIAGNOSTIC, candidate_lane_ids())
        with self.assertRaises(Exception):
            run_research_calculation(
                ResearchCalculationRequest(metric_id=DIAGNOSTIC)
            )


if __name__ == "__main__":
    unittest.main()
