"""The filed historical P/S and EV/EBITDA distributions, and what keeps them
out.

The AAPL multiples dataset is the production source for the sales and
enterprise-value reference distributions. These tests pin the qualification it
has to pass and the conditions under which it refuses, because a multiple that
is not a point-in-time figure over a qualified sample must not become a
reference.
"""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from archive import (
    production_reference_count_divergence,
    production_reference_request,
    replay,
)
from historical_multiples import (
    EV_BRIDGE_COMPONENTS,
    ISSUER_CONFIGS,
    METRIC_EV_EBITDA_RATIO,
    METRIC_PS_RATIO,
    REASON_INCOMPLETE_EV_BRIDGE,
    REASON_INSUFFICIENT_OBSERVATIONS,
    HistoricalMultiplesConfig,
    compute_multiples_distribution,
    load_issuer_historical_multiples,
    production_multiples_summary,
)
from investment_context import compute_content_hash
from sqlite_archive import SQLiteArchive
from st_eva_runner import (
    load_production_historical_references,
    production_ev_ebitda_for_reference,
    production_ps_for_reference,
    run_st_eva,
)

TICKER = "AAPL"


def _payload():
    return load_issuer_historical_multiples(ISSUER_CONFIGS[TICKER]).to_dict()


class TheDataset(unittest.TestCase):
    """What the dataset holds, before anything is qualified from it."""

    @classmethod
    def setUpClass(cls):
        cls.payload = _payload()

    def test_the_dataset_names_the_concepts_it_read(self):
        tags = self.payload["concept_tags"]
        self.assertEqual(tags["cash"], "CashAndCashEquivalentsAtCarryingValue")
        self.assertEqual(tags["marketable_securities_current"], "MarketableSecuritiesCurrent")
        self.assertEqual(tags["commercial_paper"], "CommercialPaper")
        self.assertEqual(tags["long_term_debt_noncurrent"], "LongTermDebtNoncurrent")
        self.assertEqual(tags["long_term_debt_current"], "LongTermDebtCurrent")

    def test_both_distributions_are_reported(self):
        distributions = self.payload["distributions"]
        self.assertIn(METRIC_PS_RATIO, distributions)
        self.assertIn(METRIC_EV_EBITDA_RATIO, distributions)

    def test_every_observation_states_a_reason_for_every_refusal(self):
        for observation in self.payload["observations"]:
            if observation["ps_ratio"] is None:
                self.assertTrue(observation["ps_reason_code"], observation)
                self.assertTrue(observation["ps_reason_detail"], observation)
            if observation["ev_ebitda_ratio"] is None:
                self.assertTrue(observation["ev_reason_code"], observation)
                self.assertTrue(observation["ev_reason_detail"], observation)

    def test_every_multiple_recomputes_from_its_stated_operands(self):
        for observation in self.payload["observations"]:
            if observation["ps_ratio"] is not None:
                self.assertAlmostEqual(
                    observation["market_cap"] / observation["ttm_revenue"],
                    observation["ps_ratio"],
                    places=6,
                )
            if observation["ev_ebitda_ratio"] is not None:
                self.assertAlmostEqual(
                    observation["enterprise_value"] / observation["ttm_ebitda"],
                    observation["ev_ebitda_ratio"],
                    places=6,
                )

    def test_market_cap_recomputes_from_price_and_shares(self):
        for observation in self.payload["observations"]:
            if observation["ps_ratio"] is not None:
                self.assertAlmostEqual(
                    observation["price"] * observation["shares_outstanding"],
                    observation["market_cap"],
                    places=0,
                )

    def test_the_ev_bridge_sums_the_components_it_names(self):
        for observation in self.payload["observations"]:
            bridge = observation["ev_bridge"]
            if not bridge["complete"]:
                continue
            components = bridge["components"]
            total_debt = (
                components["long_term_debt_noncurrent"]["value"]
                + components["long_term_debt_current"]["value"]
                + components["commercial_paper"]["value"]
            )
            liquid_funds = (
                components["cash"]["value"]
                + components["marketable_securities_current"]["value"]
            )
            self.assertAlmostEqual(bridge["total_debt"], total_debt, places=4)
            self.assertAlmostEqual(bridge["liquid_funds"], liquid_funds, places=4)
            self.assertAlmostEqual(
                observation["enterprise_value"],
                observation["market_cap"] + total_debt - liquid_funds,
                places=2,
            )


class TheQualification(unittest.TestCase):
    """What has to be true before a multiple may be used."""

    @classmethod
    def setUpClass(cls):
        cls.payload = _payload()

    def test_aapl_qualifies_on_both_distributions(self):
        for metric in (METRIC_PS_RATIO, METRIC_EV_EBITDA_RATIO):
            distribution = self.payload["distributions"][metric]
            self.assertEqual(distribution["status"], "USABLE_FOR_REFERENCE", metric)
            self.assertIs(distribution["usable_for_reference"], True, metric)
            self.assertGreaterEqual(
                distribution["sample_count"],
                distribution["min_observations_required"],
                metric,
            )

    def test_no_reference_is_fabricated_from_a_thinner_sample(self):
        distribution = compute_multiples_distribution(
            [],
            metric=METRIC_PS_RATIO,
            values=[(f"2026-01-{day:02d}", 1.0 + day * 0.01) for day in range(1, 20)],
        )
        self.assertEqual(distribution.status, "INSUFFICIENT_OBSERVATIONS")
        self.assertIs(distribution.usable_for_reference, False)
        self.assertEqual(distribution.reason_code, REASON_INSUFFICIENT_OBSERVATIONS)
        # The statistics are still reported, descriptively; what the gate
        # withholds is the reference eligibility, never the numbers.
        self.assertIsNotNone(distribution.percentiles.get("median"))
        self.assertIn("descriptive", distribution.reason_detail.lower())

    def test_the_gate_is_the_sample_count_not_the_evaluation_count(self):
        # 28 valid multiples over 36 evaluations qualify; 19 valid over the
        # same evaluation count would not. The gate counts what qualifies.
        ps = self.payload["distributions"][METRIC_PS_RATIO]
        self.assertEqual(ps["sample_count"], 28)
        self.assertEqual(ps["total_evaluations"], 36)

    def test_a_refused_denominator_is_never_repaired(self):
        # An evaluation the income dataset refused carries no denominator, so
        # this dataset produces no multiple for it and says which side
        # refused, rather than recomputing or backfilling one.
        for observation in self.payload["observations"]:
            if observation["ttm_revenue"] is None:
                self.assertIsNone(observation["ps_ratio"], observation)
                self.assertIn(
                    observation["ps_reason_code"],
                    (
                        "REASON_MISSING_REVENUE_WINDOW",
                        "REASON_SOURCE_CONCEPT_COVERAGE_GAP",
                    ),
                    observation,
                )
            if observation["ttm_ebitda"] is None:
                self.assertIsNone(observation["ev_ebitda_ratio"], observation)
                self.assertIn(
                    observation["ev_reason_code"],
                    (
                        "REASON_MISSING_EBITDA_WINDOW",
                        "REASON_SOURCE_CONCEPT_COVERAGE_GAP",
                    ),
                    observation,
                )


class ThePointInTimeRule(unittest.TestCase):
    """No fact is used before its filing's usable date."""

    @classmethod
    def setUpClass(cls):
        cls.payload = _payload()

    def test_every_bridge_component_is_knowable_at_its_evaluation_date(self):
        for observation in self.payload["observations"]:
            day = observation["evaluation_date"]
            for component, fact in observation["ev_bridge"]["components"].items():
                self.assertLessEqual(
                    fact["usable_date"],
                    day,
                    (day, component),
                )

    def test_the_share_count_is_knowable_at_its_evaluation_date(self):
        for observation in self.payload["observations"]:
            if observation["ps_ratio"] is None:
                continue
            self.assertLessEqual(
                observation["shares_as_of_date"],
                observation["evaluation_date"],
                observation["evaluation_date"],
            )

    def test_the_denominator_windows_travel_with_the_income_dataset(self):
        # The multiples dataset never recomputes a denominator: its windows
        # are the income dataset's own, and the lineage names that dataset's
        # identity, so the two cannot disagree about what a trailing figure is.
        for observation in self.payload["observations"]:
            lineage = observation["source_lineage"]
            self.assertTrue(lineage["income_observation_id"], observation)
            self.assertTrue(lineage["income_input_set_id"], observation)


class TheEvBridge(unittest.TestCase):
    """A complete filed bridge is required, and a partial one is refused."""

    @classmethod
    def setUpClass(cls):
        cls.payload = _payload()

    def test_a_complete_bridge_names_every_component(self):
        for observation in self.payload["observations"]:
            bridge = observation["ev_bridge"]
            if bridge["complete"]:
                self.assertEqual(
                    sorted(bridge["components"]),
                    sorted(EV_BRIDGE_COMPONENTS),
                    observation["evaluation_date"],
                )
                self.assertEqual(bridge["components_absent"], [])

    def test_a_missing_component_refuses_ev_ebitda_and_not_ps(self):
        # With one balance-sheet concept emptied, no evaluation has a complete
        # bridge: EV/EBITDA is refused with the explicit reason on every date,
        # while P/S -- which never needed the bridge -- still computes.
        with tempfile.TemporaryDirectory() as temp_dir:
            copied = Path(temp_dir) / "AAPL"
            shutil.copytree(ISSUER_CONFIGS[TICKER].data_dir, copied)
            emptied = json.loads(
                (copied / "commercial_paper_concept.json").read_text(encoding="utf-8")
            )
            emptied["units"] = {}
            (copied / "commercial_paper_concept.json").write_text(
                json.dumps(emptied), encoding="utf-8"
            )
            config = HistoricalMultiplesConfig(
                ticker=TICKER,
                issuer_id=ISSUER_CONFIGS[TICKER].issuer_id,
                entity_name=ISSUER_CONFIGS[TICKER].entity_name,
                fye_month=ISSUER_CONFIGS[TICKER].fye_month,
                data_dir=copied,
                prices_path=ISSUER_CONFIGS[TICKER].prices_path,
                acceptance_path=ISSUER_CONFIGS[TICKER].acceptance_path,
                shares_path=ISSUER_CONFIGS[TICKER].shares_path,
                income_config=ISSUER_CONFIGS[TICKER].income_config,
                balance_sheet_concepts=dict(
                    ISSUER_CONFIGS[TICKER].balance_sheet_concepts
                ),
            )
            payload = load_issuer_historical_multiples(config).to_dict()

        ev = payload["distributions"][METRIC_EV_EBITDA_RATIO]
        self.assertEqual(ev["sample_count"], 0)
        self.assertIs(ev["usable_for_reference"], False)
        ps = payload["distributions"][METRIC_PS_RATIO]
        self.assertEqual(ps["status"], "USABLE_FOR_REFERENCE")
        for observation in payload["observations"]:
            if observation["ps_ratio"] is not None:
                self.assertFalse(observation["ev_bridge"]["complete"])
                self.assertIn(
                    "commercial_paper", observation["ev_bridge"]["components_absent"]
                )
                self.assertEqual(
                    observation["ev_reason_code"], REASON_INCOMPLETE_EV_BRIDGE
                )
                self.assertIsNone(observation["ev_ebitda_ratio"])


class TheIdentity(unittest.TestCase):
    """One dataset identity, read the same by every consumer."""

    @classmethod
    def setUpClass(cls):
        cls.payload = _payload()

    def test_reloading_is_deterministic(self):
        again = _payload()
        self.assertEqual(self.payload["input_set_id"], again["input_set_id"])
        self.assertEqual(self.payload["content_hash"], again["content_hash"])

    def test_the_identity_digests_every_result_affecting_input(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            copied = Path(temp_dir) / "AAPL"
            shutil.copytree(ISSUER_CONFIGS[TICKER].data_dir, copied)
            changed = json.loads(
                (copied / "cash_concept.json").read_text(encoding="utf-8")
            )
            # One changed fact value changes the file's bytes, so the
            # dataset identity changes with it.
            changed["units"]["USD"][0]["val"] = (
                changed["units"]["USD"][0]["val"] + 1
            )
            (copied / "cash_concept.json").write_text(
                json.dumps(changed), encoding="utf-8"
            )
            config = HistoricalMultiplesConfig(
                ticker=TICKER,
                issuer_id=ISSUER_CONFIGS[TICKER].issuer_id,
                entity_name=ISSUER_CONFIGS[TICKER].entity_name,
                fye_month=ISSUER_CONFIGS[TICKER].fye_month,
                data_dir=copied,
                prices_path=ISSUER_CONFIGS[TICKER].prices_path,
                acceptance_path=ISSUER_CONFIGS[TICKER].acceptance_path,
                shares_path=ISSUER_CONFIGS[TICKER].shares_path,
                income_config=ISSUER_CONFIGS[TICKER].income_config,
                balance_sheet_concepts=dict(
                    ISSUER_CONFIGS[TICKER].balance_sheet_concepts
                ),
            )
            payload = load_issuer_historical_multiples(config).to_dict()
        self.assertNotEqual(payload["input_set_id"], self.payload["input_set_id"])


class TheReverseRequirementsBlock(unittest.TestCase):
    """The qualified references reach the report's valuation methods."""

    def _report(self, **kwargs):
        from st_eva_runner import run_st_eva

        return run_st_eva(
            TICKER,
            mode="regression",
            include_historical_pe=True,
            include_historical_multiples=True,
            save_snapshot=False,
            reverse_horizons=[3],
            required_returns=[0.1],
            **kwargs,
        )["reverse_requirements"]

    def test_the_sales_and_enterprise_value_methods_use_the_production_medians(self):
        methods = self._report()["valuation_methods"]["methods"]
        revenue = methods["revenue_multiple"]["reference_multiple"]
        enterprise = methods["enterprise_value_multiple"]["reference_multiple"]
        self.assertEqual(revenue["source"], "production_historical_ps_median")
        self.assertEqual(enterprise["source"], "production_historical_ev_ebitda_median")
        for multiple in (revenue, enterprise):
            self.assertEqual(
                multiple["eligibility_state"], "ELIGIBLE_PRODUCTION_DISTRIBUTION"
            )
            self.assertIs(multiple["is_user_assumption"], False)
            self.assertTrue(multiple["usable_for_reference"])

    def test_a_user_multiple_still_wins_in_the_report(self):
        methods = self._report(
            ps_multiple=3.0, ev_ebitda_multiple=11.0
        )["valuation_methods"]["methods"]
        revenue = methods["revenue_multiple"]["reference_multiple"]
        enterprise = methods["enterprise_value_multiple"]["reference_multiple"]
        self.assertEqual(revenue["value"], 3.0)
        self.assertEqual(revenue["source"], "user_supplied")
        self.assertIs(revenue["is_user_assumption"], True)
        self.assertEqual(enterprise["value"], 11.0)
        self.assertEqual(enterprise["source"], "user_supplied")
        self.assertIs(enterprise["is_user_assumption"], True)

    def test_an_ineligible_distribution_leaves_the_method_unavailable(self):
        # The report refuses the method with the distribution's own reason
        # rather than filling it from the vendor band or another method.
        from reverse_requirements import (
            reference_multiple_from_production_distribution,
        )

        ineligible = {
            "status": "INSUFFICIENT_OBSERVATIONS",
            "usable_for_reference": False,
            "sample_count": 3,
            "percentiles": {"median": 7.0},
        }
        multiple, refusal = reference_multiple_from_production_distribution(
            ineligible,
            source="production_historical_ps_median",
            metric_label="P/S",
        )
        self.assertIsNone(multiple)
        self.assertEqual(refusal["reason_kind"], "INSUFFICIENT_OBSERVATIONS")
        self.assertIn("valuation_methods", refusal["blocks"])

    def test_a_distribution_that_declares_no_count_is_refused(self):
        from reverse_requirements import (
            reference_multiple_from_production_distribution,
        )

        undeclared = {
            "status": "USABLE_FOR_REFERENCE",
            "usable_for_reference": True,
            "percentiles": {"median": 7.0},
        }
        multiple, refusal = reference_multiple_from_production_distribution(
            undeclared,
            source="production_historical_ps_median",
            metric_label="P/S",
        )
        self.assertIsNone(multiple)
        self.assertEqual(refusal["reason_kind"], "OBSERVATION_COUNT_UNVERIFIED")

    def test_a_distribution_that_declares_itself_ineligible_is_refused(self):
        from reverse_requirements import (
            reference_multiple_from_production_distribution,
        )

        # Enough observations but an eligibility status that says otherwise:
        # the declared status decides, so a large count cannot promote a
        # distribution the gate refused.
        declared_ineligible = {
            "status": "INELIGIBLE_STATUS",
            "usable_for_reference": False,
            "sample_count": 40,
            "percentiles": {"median": 7.0},
        }
        multiple, refusal = reference_multiple_from_production_distribution(
            declared_ineligible,
            source="production_historical_ev_ebitda_median",
            metric_label="EV/EBITDA",
        )
        self.assertIsNone(multiple)
        self.assertEqual(refusal["reason_kind"], "INELIGIBLE_STATUS")


class TheSummaryReference(unittest.TestCase):
    """How a qualified distribution reaches the engine's references."""

    @classmethod
    def setUpClass(cls):
        pe, pfcf, multiples = load_production_historical_references(
            TICKER,
            include_historical_pe=True,
            include_historical_pfcf=True,
            include_historical_multiples=True,
        )
        cls.pe = pe
        cls.multiples = multiples

    def test_the_loader_returns_the_same_payload_the_module_builds(self):
        self.assertEqual(
            self.multiples["input_set_id"], _payload()["input_set_id"]
        )

    def test_eligible_distributions_are_the_references(self):
        ps_median, ps_status = production_ps_for_reference(self.multiples)
        ev_median, ev_status = production_ev_ebitda_for_reference(self.multiples)
        self.assertEqual(ps_status, "USABLE_FOR_REFERENCE")
        self.assertEqual(ev_status, "USABLE_FOR_REFERENCE")
        self.assertEqual(
            ps_median,
            self.multiples["distributions"][METRIC_PS_RATIO]["percentiles"]["median"],
        )
        self.assertEqual(
            ev_median,
            self.multiples["distributions"][METRIC_EV_EBITDA_RATIO]["percentiles"][
                "median"
            ],
        )

    def test_an_ineligible_distribution_stays_descriptive(self):
        ineligible = copy.deepcopy(self.multiples)
        for distribution in ineligible["distributions"].values():
            distribution["usable_for_reference"] = False
            distribution["status"] = "INSUFFICIENT_OBSERVATIONS"
        ps_median, ps_status = production_ps_for_reference(ineligible)
        self.assertIsNone(ps_median)
        self.assertEqual(ps_status, "INSUFFICIENT_OBSERVATIONS")

    def test_an_absent_payload_reports_no_reference(self):
        ps_median, ps_status = production_ps_for_reference(None)
        self.assertIsNone(ps_median)
        self.assertEqual(ps_status, "UNAVAILABLE")

    def test_the_report_carries_the_multiples_summary(self):
        from st_eva_runner import run_st_eva

        result = run_st_eva(
            TICKER,
            mode="regression",
            include_historical_multiples=True,
            save_snapshot=False,
            reverse_horizons=[3],
            required_returns=[0.1],
        )
        reference = result["reference"]
        self.assertEqual(reference["ps_method"], "production_historical_ps_median")
        self.assertEqual(
            reference["ev_ebitda_method"],
            "production_historical_ev_ebitda_median",
        )
        self.assertEqual(
            reference["production_historical_ps_sample_count"],
            self.multiples["distributions"][METRIC_PS_RATIO]["sample_count"],
        )
        self.assertEqual(
            reference["production_historical_ev_ebitda_sample_count"],
            self.multiples["distributions"][METRIC_EV_EBITDA_RATIO]["sample_count"],
        )
        summary = result["reverse_requirements"][
            "production_historical_multiples_summary"
        ]
        self.assertEqual(
            summary["input_set_id"], self.multiples["input_set_id"]
        )
        for metric in (METRIC_PS_RATIO, METRIC_EV_EBITDA_RATIO):
            stated = summary["distributions"][metric]
            actual = self.multiples["distributions"][metric]
            self.assertEqual(stated["sample_count"], actual["sample_count"])
            self.assertEqual(stated["status"], actual["status"])

    def test_a_user_multiple_still_wins_over_the_production_median(self):
        from st_eva_runner import run_st_eva

        result = run_st_eva(
            TICKER,
            mode="regression",
            include_historical_multiples=True,
            save_snapshot=False,
            ps_multiple=3.0,
            ev_ebitda_multiple=11.0,
            reverse_horizons=[3],
            required_returns=[0.1],
        )
        reference = result["reference"]
        self.assertEqual(reference["ps_method"], "user_supplied_multiple")
        self.assertEqual(reference["ps_multiple"], 3.0)
        self.assertEqual(reference["ev_ebitda_method"], "user_supplied_multiple")
        self.assertEqual(reference["ev_ebitda_multiple"], 11.0)

    def test_an_unestablished_ticker_states_its_unavailability(self):
        _, _, multiples = load_production_historical_references(
            "TSM", include_historical_multiples=True
        )
        for metric in (METRIC_PS_RATIO, METRIC_EV_EBITDA_RATIO):
            distribution = multiples["distributions"][metric]
            self.assertEqual(distribution["status"], "UNAVAILABLE")
            self.assertIs(distribution["usable_for_reference"], False)
            self.assertIn("not yet established", distribution["reason_detail"])
        ps_median, _ = production_ps_for_reference(multiples)
        self.assertIsNone(ps_median)


class TheReplayIdentity(unittest.TestCase):
    """Live and replay read the same dataset identity."""

    def test_the_rebuild_uses_the_same_loader_and_the_same_payload(self):
        # The replay's document builder loads the production references with
        # the same loader a live run uses, so a rebuild cannot select a
        # reference the run did not use. The dataset identity is what both
        # reads digest.
        _, _, live = load_production_historical_references(
            TICKER, include_historical_multiples=True
        )
        _, _, rebuild = load_production_historical_references(
            TICKER, include_historical_multiples=True
        )
        self.assertEqual(live["input_set_id"], rebuild["input_set_id"])
        self.assertEqual(live["content_hash"], rebuild["content_hash"])

    def test_the_archive_names_the_multiples_references_it_can_reproduce(self):
        from archive import production_reference_request

        stored = {
            "ps_reference": {
                "basis": "PRODUCTION_PS_MEDIAN",
                "source_observation_count": 28,
            },
            "ev_ebitda_reference": {
                "basis": "PRODUCTION_EV_EBITDA_MEDIAN",
                "source_observation_count": 29,
            },
        }
        request = production_reference_request(stored)
        self.assertEqual(request["multiples_ps"], 28)
        self.assertEqual(request["multiples_ev_ebitda"], 29)

    def test_the_context_records_a_production_median_as_production(self):
        from investment_context import REFERENCE_SOURCES

        for basis in ("PRODUCTION_PS_MEDIAN", "PRODUCTION_EV_EBITDA_MEDIAN"):
            entry = REFERENCE_SOURCES[basis]
            self.assertIs(entry["observed"], True, basis)
            self.assertEqual(entry["source_statistic"], "median", basis)


class TheCompactSummary(unittest.TestCase):
    """The API-facing summary states the same facts the payload does."""

    @classmethod
    def setUpClass(cls):
        cls.payload = _payload()
        cls.summary = production_multiples_summary(cls.payload)

    def test_the_summary_names_the_dataset_identity(self):
        self.assertEqual(self.summary["input_set_id"], self.payload["input_set_id"])
        self.assertEqual(self.summary["content_hash"], self.payload["content_hash"])

    def test_each_distribution_summary_agrees_with_its_payload(self):
        for metric in (METRIC_PS_RATIO, METRIC_EV_EBITDA_RATIO):
            stated = self.summary["distributions"][metric]
            actual = self.payload["distributions"][metric]
            self.assertEqual(stated["sample_count"], actual["sample_count"])
            self.assertEqual(stated["status"], actual["status"])
            self.assertEqual(
                stated["usable_for_reference"], actual["usable_for_reference"]
            )
            self.assertEqual(stated["percentiles"], actual["percentiles"])
            self.assertEqual(
                stated["excluded_observation_count"],
                len(actual["excluded_observations"]),
            )

    def test_an_absent_payload_summarizes_to_none(self):
        self.assertIsNone(production_multiples_summary(None))


class TheBridgeDateRule(unittest.TestCase):
    """Every filed balance-sheet component must describe one balance sheet."""

    @classmethod
    def setUpClass(cls):
        cls.payload = _payload()

    def test_a_published_enterprise_value_uses_one_balance_sheet_date(self):
        published = 0
        for observation in self.payload["observations"]:
            bridge = observation["ev_bridge"]
            if observation["ev_ebitda_ratio"] is None:
                continue
            published += 1
            alignment = bridge["period_alignment"]
            self.assertTrue(alignment["required"], observation["evaluation_date"])
            self.assertIs(alignment["single_balance_sheet_date"], True)
            self.assertIs(alignment["all_components_present"], True)
            self.assertEqual(len(alignment["distinct_period_ends"]), 1)
            self.assertIsNotNone(alignment["balance_sheet_date"])
            for component, fact in bridge["components"].items():
                self.assertEqual(
                    fact["period_end"],
                    alignment["balance_sheet_date"],
                    (observation["evaluation_date"], component),
                )
        self.assertGreater(published, 0)

    def test_a_mixed_period_bridge_publishes_no_enterprise_value(self):
        mixed = [
            observation
            for observation in self.payload["observations"]
            if observation["ev_reason_code"] == "REASON_MIXED_BALANCE_SHEET_PERIODS"
        ]
        self.assertTrue(mixed, "the mixed-period dates must be refused, not published")
        for observation in mixed:
            self.assertIsNone(observation["ev_ebitda_ratio"], observation)
            self.assertIsNone(observation["enterprise_value"], observation)
            self.assertIs(observation["ev_bridge"]["complete"], False)
            alignment = observation["ev_bridge"]["period_alignment"]
            self.assertIs(alignment["single_balance_sheet_date"], False)
            self.assertGreater(len(alignment["distinct_period_ends"]), 1)
            # The refusal names the periods, so a reader can see which
            # component was stale.
            for period_end in alignment["distinct_period_ends"]:
                self.assertIn(period_end, observation["ev_reason_detail"])

    def test_the_stale_component_is_never_zero_filled(self):
        for observation in self.payload["observations"]:
            if observation["ev_reason_code"] != "REASON_MIXED_BALANCE_SHEET_PERIODS":
                continue
            components = observation["ev_bridge"]["components"]
            self.assertTrue(components, observation)
            for fact in components.values():
                self.assertNotEqual(fact["value"], 0.0, observation)

    def test_the_sample_excludes_the_mixed_period_dates(self):
        distribution = self.payload["distributions"][METRIC_EV_EBITDA_RATIO]
        self.assertEqual(distribution["sample_count"], 27)
        self.assertEqual(distribution["total_evaluations"], 36)
        self.assertEqual(len(distribution["excluded_observations"]), 9)

    def test_the_median_is_recomputed_from_the_surviving_observations(self):
        distribution = self.payload["distributions"][METRIC_EV_EBITDA_RATIO]
        values = sorted(
            observation["value"] for observation in distribution["observations"]
        )
        self.assertEqual(len(values), 27)
        self.assertEqual(distribution["percentiles"]["median"], values[13])

    def test_the_ps_distribution_is_unchanged_by_the_bridge_rule(self):
        distribution = self.payload["distributions"][METRIC_PS_RATIO]
        self.assertEqual(distribution["sample_count"], 28)
        self.assertEqual(distribution["percentiles"]["median"], 7.257709)

    def test_the_policy_is_recorded_on_every_bridge(self):
        for observation in self.payload["observations"]:
            alignment = observation["ev_bridge"]["period_alignment"]
            self.assertIn("same balance-sheet date", alignment["policy"])


class TheRefusalReasons(unittest.TestCase):
    """A refusal says which cause it is, and says it from the evidence."""

    @classmethod
    def setUpClass(cls):
        cls.payload = _payload()

    def test_every_rejection_uses_a_code_from_the_closed_set(self):
        from historical_multiples import CLOSED_REASON_CODES

        codes = set()
        for observation in self.payload["observations"]:
            for code in (
                observation["ps_reason_code"],
                observation["ev_reason_code"],
            ):
                if code:
                    codes.add(code)
                    self.assertIn(code, CLOSED_REASON_CODES)
        self.assertIn("REASON_SOURCE_CONCEPT_COVERAGE_GAP", codes)

    def test_the_ps_rejections_tell_a_coverage_gap_from_a_timing_refusal(self):
        reasons = {
            observation["evaluation_date"]: observation["ps_reason_code"]
            for observation in self.payload["observations"]
            if observation["ps_ratio"] is None
        }
        self.assertEqual(len(reasons), 8)
        coverage = sorted(
            day for day, code in reasons.items()
            if code == "REASON_SOURCE_CONCEPT_COVERAGE_GAP"
        )
        timing = sorted(
            day for day, code in reasons.items()
            if code == "REASON_MISSING_REVENUE_WINDOW"
        )
        # The capture carries no revenue from any filing knowable before
        # 2019-01-31, so the five earliest evaluations are a gap in the
        # source; the three later ones are positions the capture carries from
        # a filing that was not yet public.
        self.assertEqual(
            coverage,
            ["2018-01-02", "2018-02-02", "2018-05-03", "2018-08-02", "2018-11-05"],
        )
        self.assertEqual(timing, ["2019-01-31", "2019-05-02", "2019-08-01"])

    def test_a_coverage_gap_says_it_is_a_property_of_the_capture(self):
        for observation in self.payload["observations"]:
            if observation["ps_reason_code"] != "REASON_SOURCE_CONCEPT_COVERAGE_GAP":
                continue
            detail = observation["ps_reason_detail"]
            self.assertIn("capture", detail)
            self.assertIn("not a statement about what the issuer had reported", detail)

    def test_a_timing_refusal_names_the_positions_and_when_they_arrived(self):
        refusals = [
            observation
            for observation in self.payload["observations"]
            if observation["ps_reason_code"] == "REASON_MISSING_REVENUE_WINDOW"
        ]
        self.assertTrue(refusals)
        for observation in refusals:
            detail = observation["ps_reason_detail"]
            self.assertIn("first knowable from", detail)
            self.assertIn("refused rather than backfilled", detail)

    def test_the_upstream_free_cash_flow_wording_is_not_propagated(self):
        # The shared window helper's prose names the quantity it was written
        # for. This dataset writes its own reason, and the wrong wording must
        # not reach the sales reference.
        for observation in self.payload["observations"]:
            for detail in (
                observation["ps_reason_detail"],
                observation["ev_reason_detail"],
            ):
                if detail:
                    self.assertNotIn("free cash flow", detail.lower())


class TheArchiveCountChain(unittest.TestCase):
    """The reference's own observation count survives the archive round trip."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.archive_path = str(Path(cls.tmp.name) / "audit.sqlite")
        cls.context_path = str(Path(cls.tmp.name) / "ctx.json")
        store = SQLiteArchive(cls.archive_path)
        try:
            run_st_eva(
                TICKER,
                mode="regression",
                include_historical_pe=True,
                include_historical_multiples=True,
                save_snapshot=False,
                context_path=cls.context_path,
                archive=store,
            )
        finally:
            store.close()
        cls.document = json.loads(Path(cls.context_path).read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_archived_document_saves_the_sample_counts(self):
        refs = self.document["provenance"]["refs"]
        self.assertEqual(
            refs["refc:ps_reference"]["source_observation_count"],
            _payload()["distributions"][METRIC_PS_RATIO]["sample_count"],
        )
        self.assertEqual(
            refs["refc:ev_ebitda_reference"]["source_observation_count"],
            _payload()["distributions"][METRIC_EV_EBITDA_RATIO]["sample_count"],
        )

    def test_the_eligibility_carries_the_same_count(self):
        refs = self.document["provenance"]["refs"]
        for name in ("ps_reference", "ev_ebitda_reference"):
            entry = refs[f"refc:{name}"]
            self.assertEqual(
                entry["eligibility_observation_count"],
                entry["source_observation_count"],
                name,
            )

    def test_the_replay_request_carries_both_counts(self):
        request = production_reference_request(self.document)
        self.assertEqual(
            request["multiples_ps"],
            _payload()["distributions"][METRIC_PS_RATIO]["sample_count"],
        )
        self.assertEqual(
            request["multiples_ev_ebitda"],
            _payload()["distributions"][METRIC_EV_EBITDA_RATIO]["sample_count"],
        )

    def test_an_archive_without_the_count_is_not_given_one(self):
        # An archive written before the count was preserved records no count.
        # The rebuild's number is not evidence against an unknown, so the
        # count is not filled in for it.
        legacy = copy.deepcopy(self.document)
        for name in ("ps_reference", "ev_ebitda_reference"):
            legacy["provenance"]["refs"][f"refc:{name}"][
                "source_observation_count"
            ] = None
        request = production_reference_request(legacy)
        self.assertIsNone(request["multiples_ps"])
        self.assertIsNone(request["multiples_ev_ebitda"])
        self.assertEqual(production_reference_count_divergence(legacy, self.document), [])

    def test_a_count_difference_is_found(self):
        changed = copy.deepcopy(self.document)
        changed["provenance"]["refs"]["refc:ps_reference"][
            "source_observation_count"
        ] = 26
        differences = production_reference_count_divergence(changed, self.document)
        self.assertEqual(len(differences), 1)
        self.assertEqual(differences[0]["source"], "multiples_ps")
        self.assertEqual(differences[0]["archived_observation_count"], 26)
        self.assertEqual(
            differences[0]["rebuilt_observation_count"],
            _payload()["distributions"][METRIC_PS_RATIO]["sample_count"],
        )

    def test_a_replay_over_a_changed_count_diverges_and_says_why(self):
        # The dataset behind the reference has changed since the run was
        # archived: the rebuild reads a distribution holding a different number
        # of observations. The median is left alone, so nothing but the count
        # tells the two apart, and the replay must diverge and name the
        # difference rather than report a match.
        from unittest import mock

        import web.service_adapter as service_adapter

        real_loader = service_adapter.load_production_historical_references

        def loader_with_a_changed_count(*args, **kwargs):
            pe, pfcf, multiples = real_loader(*args, **kwargs)
            if multiples:
                multiples = copy.deepcopy(multiples)
                multiples["distributions"]["P_S_RATIO_REFERENCE"][
                    "sample_count"
                ] = 26
            return pe, pfcf, multiples

        store = SQLiteArchive(self.archive_path)
        try:
            from web.service_adapter import default_replay_doc_builder

            with mock.patch.object(
                service_adapter,
                "load_production_historical_references",
                loader_with_a_changed_count,
            ):
                result = replay(
                    store, TICKER, "2026-12-31", default_replay_doc_builder
                )
        finally:
            store.close()
        self.assertEqual(result.outcome, "DIVERGED")
        self.assertIn("different number of observations", result.reason)
        self.assertIn("multiples_ps", result.reason)

    def test_a_replay_over_an_unchanged_archive_matches(self):
        store = SQLiteArchive(self.archive_path)
        try:
            from web.service_adapter import default_replay_doc_builder

            result = replay(store, TICKER, "2026-12-31", default_replay_doc_builder)
        finally:
            store.close()
        self.assertEqual(result.outcome, "MATCH")


class TheDatasetAvailability(unittest.TestCase):
    """An absent dataset, a thin dataset and a qualified dataset are three
    different conditions, and each is reported as the condition it is."""

    def test_a_ticker_without_the_dataset_reports_that_the_dataset_is_absent(self):
        for ticker in ("MSFT", "TSM"):
            _, _, multiples = load_production_historical_references(
                ticker, include_historical_multiples=True
            )
            for distribution in multiples["distributions"].values():
                self.assertEqual(distribution["status"], "UNAVAILABLE")
                self.assertIs(distribution["usable_for_reference"], False)
                self.assertEqual(
                    distribution["reason_code"], "REASON_DATASET_NOT_ESTABLISHED"
                )
                self.assertIn("not yet established", distribution["reason_detail"])

    def test_an_absent_dataset_contributes_no_reference(self):
        _, _, multiples = load_production_historical_references(
            "MSFT", include_historical_multiples=True
        )
        median, status = production_ps_for_reference(multiples)
        self.assertIsNone(median)
        self.assertEqual(status, "UNAVAILABLE")

    def test_a_thin_dataset_reports_insufficient_observations(self):
        distribution = compute_multiples_distribution(
            [],
            metric=METRIC_PS_RATIO,
            values=[(f"2026-01-{day:02d}", 1.0 + day * 0.01) for day in range(1, 12)],
        )
        self.assertEqual(distribution.status, "INSUFFICIENT_OBSERVATIONS")
        self.assertEqual(distribution.reason_code, "REASON_INSUFFICIENT_OBSERVATIONS")

    def test_a_qualified_dataset_is_eligible(self):
        distribution = _payload()["distributions"][METRIC_PS_RATIO]
        self.assertEqual(distribution["status"], "USABLE_FOR_REFERENCE")
        self.assertIs(distribution["usable_for_reference"], True)
        self.assertIsNone(distribution["reason_code"])

    def test_the_three_conditions_use_three_different_codes(self):
        from historical_multiples import (
            REASON_DATASET_NOT_ESTABLISHED,
            REASON_INSUFFICIENT_OBSERVATIONS,
        )

        self.assertNotEqual(
            REASON_DATASET_NOT_ESTABLISHED, REASON_INSUFFICIENT_OBSERVATIONS
        )


if __name__ == "__main__":
    unittest.main()
