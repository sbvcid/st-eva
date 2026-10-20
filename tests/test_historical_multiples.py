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
from st_eva_runner import (
    load_production_historical_references,
    production_ev_ebitda_for_reference,
    production_ps_for_reference,
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
                self.assertEqual(
                    observation["ps_reason_code"], "REASON_MISSING_REVENUE_WINDOW"
                )
            if observation["ttm_ebitda"] is None:
                self.assertIsNone(observation["ev_ebitda_ratio"], observation)
                self.assertEqual(
                    observation["ev_reason_code"], "REASON_MISSING_EBITDA_WINDOW"
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


if __name__ == "__main__":
    unittest.main()
