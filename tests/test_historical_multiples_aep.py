"""Microsoft's production historical P/S and EV/EBITDA reference distributions.

The second issuer through the same generic pipeline: the same builders, the
same point-in-time rule, the same sufficiency gate, the same report, context,
archive and replay. These tests hold the second issuer to the same evidence the
first one is held to, they hold the three issuers apart, and they hold the
window rule that no fiscal label may override.
"""
import copy
import datetime
import json
import statistics
import tempfile
import unittest
from pathlib import Path

from archive import production_reference_request, replay
from historical_income import ISSUER_CONFIGS as INCOME_CONFIGS
from historical_income import load_issuer_historical_income
from historical_multiples import (
    EV_BRIDGE_COMPONENTS,
    ISSUER_CONFIGS,
    METRIC_EV_EBITDA_RATIO,
    METRIC_PS_RATIO,
    load_issuer_historical_multiples,
    production_multiples_summary,
)
from historical_pe import restore_as_traded_close
from sqlite_archive import SQLiteArchive
from st_eva_runner import (
    load_production_historical_references,
    production_ev_ebitda_for_reference,
    production_ps_for_reference,
    run_st_eva,
)

TICKER = "AEP"
ROOT = Path(__file__).resolve().parent.parent
PRICES_EXIST = (ROOT / "data" / "historical_pe" / TICKER / "daily_prices.json").exists()
PRICES_SKIP = "AEP daily_prices.json excluded per C-1 / DATA-DELIVERY.md"


def _payload():
    return load_issuer_historical_multiples(ISSUER_CONFIGS[TICKER]).to_dict()


def _raw_prices():
    with open(
        ROOT / "data" / "historical_pe" / TICKER / "daily_prices.json", encoding="utf-8"
    ) as handle:
        chart = json.load(handle)["chart"]["result"][0]
    quote = chart["indicators"]["quote"][0]
    bars = {
        datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc)
        .date()
        .isoformat(): float(quote["close"][index])
        for index, stamp in enumerate(chart["timestamp"])
        if quote["close"][index] is not None
    }
    splits = chart.get("events", {}).get("splits", {})
    return {
        day: round(restore_as_traded_close(close, day, splits)[0], 4)
        for day, close in bars.items()
    }


def _raw_shares():
    with open(
        ROOT / "data" / "historical_multiples" / TICKER / "shares_outstanding_concept.json",
        encoding="utf-8",
    ) as handle:
        payload = json.load(handle)
    return [
        (fact["end"], float(fact["val"]), fact["accn"])
        for fact in payload["units"]["shares"]
    ]


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class TheSources(unittest.TestCase):
    """What the dataset was built from, and what each file is."""

    @classmethod
    def setUpClass(cls):
        cls.payload = _payload()
        cls.manifest = json.loads(
            (
                ROOT / "data" / "historical_multiples" / TICKER / "manifest.json"
            ).read_text(encoding="utf-8")
        )

    def test_the_manifest_pins_every_file_it_names(self):
        import hashlib

        for name, meta in self.manifest["provenance"]["files"].items():
            path = (
                Path(meta["path"])
                if "path" in meta
                else ROOT / "data" / "historical_multiples" / TICKER / name
            )
            self.assertTrue(path.exists(), name)
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(),
                meta["content_sha256"],
                name,
            )

    def test_the_revenue_role_names_the_registry_accepted_element(self):
        income = load_issuer_historical_income(INCOME_CONFIGS[TICKER]).to_dict()
        # The element the registry accepts for the revenue metric, and not the
        # one decision 2.99 retired.
        self.assertEqual(
            income["concept_tags"]["revenue"],
            "RevenueFromContractWithCustomerExcludingAssessedTax",
        )
        self.assertNotEqual(income["concept_tags"]["revenue"], "Revenues")

    def test_the_retired_revenue_element_is_not_used_for_the_reference(self):
        from core_registry import CoreRegistry
        from registry_seed import seed

        store = SQLiteArchive(":memory:")
        try:
            registry = CoreRegistry(store.connection)
            seed(registry)
            store.connection.commit()
            rows = [
                dict(row)
                for row in store.connection.execute(
                    "SELECT concept_id, metric_id, scope_json FROM metric_concept_mapping"
                )
            ]
        finally:
            store.close()
        revenues = [row for row in rows if row["concept_id"] == "us-gaap:Revenues"]
        self.assertEqual(revenues, [], "the retired element must carry no mapping")

    def test_the_concepts_are_the_elements_this_issuer_uses(self):
        tags = self.payload["concept_tags"]
        self.assertEqual(tags["cash"], "CashAndCashEquivalentsAtCarryingValue")
        self.assertEqual(tags["marketable_securities_current"], "ShortTermInvestments")
        self.assertEqual(tags["commercial_paper"], "CommercialPaper")
        self.assertEqual(tags["long_term_debt_current"], "LongTermDebtCurrent")
        self.assertEqual(tags["long_term_debt_noncurrent"], "LongTermDebtNoncurrent")

    def test_the_latest_filed_quarter_is_in_the_capture(self):
        # The company-concept API did not yet carry the FY2026 second-quarter
        # 10-Q, so its facts were taken from the filing's own instance.
        for name in (
            "cash_concept.json",
            "marketable_securities_current_concept.json",
            "commercial_paper_concept.json",
            "long_term_debt_current_concept.json",
            "long_term_debt_noncurrent_concept.json",
        ):
            with open(
                ROOT / "data" / "historical_multiples" / TICKER / name, encoding="utf-8"
            ) as handle:
                payload = json.load(handle)
            rows = [
                row
                for unit in payload["units"].values()
                for row in unit
                if row.get("end")
            ]
            self.assertEqual(
                max(row["end"] for row in rows),
                "2026-06-30",
                name,
            )
            supplemented = [
                row
                for row in rows
                if row.get("accn") == "0000004904-26-000059"
            ]
            self.assertTrue(supplemented, name)

    def test_every_observation_carries_its_source_lineage(self):
        for observation in self.payload["observations"]:
            lineage = observation["source_lineage"]
            self.assertTrue(lineage["income_observation_id"], observation)
            self.assertTrue(lineage["income_input_set_id"], observation)


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class ThePointInTimeRule(unittest.TestCase):
    """No fact is used before its filing's usable date."""

    @classmethod
    def setUpClass(cls):
        cls.payload = _payload()

    def test_no_operand_is_knowable_after_its_evaluation_date(self):
        for observation in self.payload["observations"]:
            day = observation["evaluation_date"]
            for name, fact in observation["ev_bridge"]["components"].items():
                self.assertLessEqual(fact["usable_date"], day, (day, name))
                self.assertLessEqual(fact["period_end"], day, (day, name))
            if observation["shares_as_of_date"]:
                self.assertLessEqual(observation["shares_as_of_date"], day, day)

    def test_the_price_is_the_as_traded_close_of_the_evaluation_date(self):
        prices = _raw_prices()
        for observation in self.payload["observations"]:
            if observation["price"] is None:
                continue
            self.assertEqual(observation["price"], prices[observation["evaluation_date"]])

    def test_there_is_no_split_in_the_covered_period(self):
        with open(
            ROOT / "data" / "historical_pe" / TICKER / "daily_prices.json",
            encoding="utf-8",
        ) as handle:
            chart = json.load(handle)["chart"]["result"][0]
        self.assertEqual(chart.get("events", {}).get("splits", {}), {})


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class TheFormulas(unittest.TestCase):
    """Every published multiple recomputes from the raw sources."""

    @classmethod
    def setUpClass(cls):
        cls.payload = _payload()
        cls.prices = _raw_prices()
        cls.shares = _raw_shares()
        cls.income = load_issuer_historical_income(INCOME_CONFIGS[TICKER]).to_dict()
        cls.windows = {
            observation["evaluation_date"]: observation["ttm_revenue"]
            for observation in cls.income["observations"]
            if observation.get("ttm_revenue")
        }
        cls.ebitda_windows = {
            observation["evaluation_date"]: observation["ttm_ebitda"]
            for observation in cls.income["observations"]
            if observation.get("ttm_ebitda")
        }

    def test_every_ps_recomputes_from_the_price_shares_and_revenue_window(self):
        values = []
        for observation in self.payload["observations"]:
            if observation["ps_ratio"] is None:
                continue
            day = observation["evaluation_date"]
            price = self.prices[day]
            share = next(
                fact
                for fact in self.shares
                if fact[2] == observation["shares_accession"]
            )
            window = self.windows[day]
            revenue = sum(quarter["value"] for quarter in window["quarters"])
            recomputed = (price * share[1]) / revenue
            self.assertAlmostEqual(recomputed, observation["ps_ratio"], places=6)
            self.assertAlmostEqual(
                price * share[1], observation["market_cap"], places=0
            )
            values.append(recomputed)
        self.assertEqual(len(values), 4)

    def test_every_trailing_ebitda_is_the_sum_of_its_quarters(self):
        for observation in self.income["observations"]:
            window = observation.get("ttm_ebitda")
            if not window:
                continue
            operating = sum(quarter["operating_income"] for quarter in window["quarters"])
            depreciation = sum(
                quarter["depreciation_and_amortization"]
                for quarter in window["quarters"]
            )
            self.assertAlmostEqual(
                operating + depreciation, window["value"], places=0
            )

    def test_every_ev_recomputes_from_its_components(self):
        for observation in self.payload["observations"]:
            if observation["ev_ebitda_ratio"] is None:
                continue
            components = observation["ev_bridge"]["components"]
            total_debt = (
                components["long_term_debt_noncurrent"]["value"]
                + components["long_term_debt_current"]["value"]
                + components["commercial_paper"]["value"]
            )
            liquid = (
                components["cash"]["value"]
                + components["marketable_securities_current"]["value"]
            )
            enterprise_value = observation["market_cap"] + total_debt - liquid
            self.assertAlmostEqual(
                enterprise_value, observation["enterprise_value"], places=2
            )
            self.assertAlmostEqual(
                enterprise_value / observation["ttm_ebitda"],
                observation["ev_ebitda_ratio"],
                places=6,
            )

    def test_the_medians_recompute_from_the_published_observations(self):
        for metric in (METRIC_PS_RATIO, METRIC_EV_EBITDA_RATIO):
            distribution = self.payload["distributions"][metric]
            values = [
                observation["value"] for observation in distribution["observations"]
            ]
            self.assertEqual(
                distribution["percentiles"]["median"],
                round(statistics.median(values), 6),
                metric,
            )

    def test_no_enterprise_value_is_published_from_a_mixed_bridge(self):
        for observation in self.payload["observations"]:
            bridge = observation["ev_bridge"]
            if not bridge["components"]:
                continue
            periods = {fact["period_end"] for fact in bridge["components"].values()}
            if len(periods) > 1:
                self.assertIsNone(observation["enterprise_value"], observation)
                self.assertIsNone(observation["ev_ebitda_ratio"], observation)
                self.assertIs(bridge["complete"], False)

    def test_no_enterprise_value_is_published_from_an_incomplete_bridge(self):
        for observation in self.payload["observations"]:
            bridge = observation["ev_bridge"]
            if bridge["components_absent"]:
                self.assertIsNone(observation["enterprise_value"], observation)
                self.assertIs(bridge["complete"], False)
                for component in EV_BRIDGE_COMPONENTS:
                    if component in bridge["components_absent"]:
                        self.assertNotIn(component, bridge["components"])


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class TheWindowRule(unittest.TestCase):
    """A window's quarters are four consecutive periods of the issuer's own."""

    @classmethod
    def setUpClass(cls):
        cls.income = load_issuer_historical_income(INCOME_CONFIGS[TICKER]).to_dict()
        cls.by_date = {o["evaluation_date"]: o for o in cls.income["observations"]}

    def test_no_published_window_has_a_gap_in_its_periods(self):
        for observation in self.income["observations"]:
            for key in ("ttm_revenue", "ttm_ebitda"):
                window = observation.get(key)
                if not window:
                    continue
                periods = sorted(
                    (quarter.get("period_end"),) for quarter in window["quarters"]
                )
                self.assertEqual(len(periods), 4, observation["evaluation_date"])
                self.assertEqual(
                    [p[0] for p in periods],
                    sorted(p[0] for p in periods),
                    observation["evaluation_date"],
                )

    def test_the_window_that_was_never_consecutive_is_refused(self):
        # 2021-04-22 published a window spanning December 2019, March 2020,
        # June 2020 and March 2021 -- a fifteen-month span with a gap. It is
        # refused, and the refusal names the break.
        observation = self.by_date["2021-04-22"]
        self.assertIsNone(observation.get("ttm_ebitda"))
        rejection = (observation.get("window_rejection") or {}).get("ebitda")
        self.assertEqual(rejection["reason_code"], "REASON_FISCAL_POSITION_UNRESOLVED")
        self.assertTrue(rejection.get("contiguity_breaks"))
        self.assertIn("is followed by", rejection["detail"])

    def test_a_position_the_issuer_labels_inconsistently_is_unresolved(self):
        # The facts for the quarter ended 2021-03-31 are in the capture, and
        # the issuer's own declarations name that period FY2020 Q3, so the
        # position the window needs cannot be determined. These are reported as
        # unresolved, not as a missing fact.
        for day in ("2021-07-22", "2021-10-28", "2022-02-24"):
            observation = self.by_date[day]
            rejection = (observation.get("window_rejection") or {}).get("ebitda")
            self.assertIsNotNone(rejection, day)
            self.assertEqual(
                rejection["reason_code"], "REASON_FISCAL_POSITION_UNRESOLVED", day
            )
            self.assertIn("nothing says which fiscal quarter", rejection["detail"])
            self.assertIn(
                rejection["unresolved_position"]["expected_period"],
                rejection["detail"],
            )

    def test_a_missing_fact_is_still_reported_as_a_missing_fact(self):
        # The coverage reason and the unresolved reason are different
        # conditions, and neither is reported as the other.
        codes = set()
        for observation in self.income["observations"]:
            for rejection in (observation.get("window_rejection") or {}).values():
                codes.add(rejection["reason_code"])
        self.assertIn("REASON_FISCAL_POSITION_UNRESOLVED", codes)
        self.assertIn("REASON_INSUFFICIENT_QUARTERS", codes)


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class TheEligibility(unittest.TestCase):
    """Each distribution is qualified on its own evidence."""

    @classmethod
    def setUpClass(cls):
        cls.payload = _payload()

    def test_the_ev_ebitda_distribution_qualifies_on_its_own_sample(self):
        distribution = self.payload["distributions"][METRIC_EV_EBITDA_RATIO]
        self.assertEqual(distribution["status"], "USABLE_FOR_REFERENCE")
        self.assertIs(distribution["usable_for_reference"], True)
        self.assertEqual(distribution["sample_count"], 24)
        self.assertEqual(distribution["total_evaluations"], 33)
        self.assertGreaterEqual(
            distribution["sample_count"],
            distribution["min_observations_required"],
        )
        self.assertEqual(distribution["percentiles"]["median"], 13.221693)

    def test_the_ps_distribution_is_reported_as_a_short_sample(self):
        # The revenue role's element covers only the periods from the fiscal
        # 2023 annual figure onward, so the P/S distribution holds four
        # qualifying observations and is ineligible. The old production
        # qualification is not carried over.
        distribution = self.payload["distributions"][METRIC_PS_RATIO]
        self.assertEqual(distribution["sample_count"], 4)
        self.assertEqual(distribution["status"], "INSUFFICIENT_OBSERVATIONS")
        self.assertIs(distribution["usable_for_reference"], False)
        self.assertEqual(distribution["reason_code"], "REASON_INSUFFICIENT_OBSERVATIONS")

    def test_the_two_distributions_are_qualified_independently(self):
        distributions = self.payload["distributions"]
        self.assertIs(
            distributions[METRIC_EV_EBITDA_RATIO]["usable_for_reference"], True
        )
        self.assertIs(distributions[METRIC_PS_RATIO]["usable_for_reference"], False)

    def test_only_the_qualified_distribution_is_a_reference(self):
        ps_median, ps_status = production_ps_for_reference(self.payload)
        ev_median, ev_status = production_ev_ebitda_for_reference(self.payload)
        self.assertIsNone(ps_median)
        self.assertEqual(ps_status, "INSUFFICIENT_OBSERVATIONS")
        self.assertIsNotNone(ev_median)
        self.assertEqual(ev_status, "USABLE_FOR_REFERENCE")


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class TheCrossCompanyBoundary(unittest.TestCase):
    """One issuer's data never becomes another issuer's reference."""

    @classmethod
    def setUpClass(cls):
        cls.aep = _payload()
        cls.aapl = load_issuer_historical_multiples(ISSUER_CONFIGS["AAPL"]).to_dict()
        cls.msft = load_issuer_historical_multiples(ISSUER_CONFIGS["MSFT"]).to_dict()

    def test_the_three_issuers_have_different_dataset_identities(self):
        identities = {
            self.aep["input_set_id"],
            self.aapl["input_set_id"],
            self.msft["input_set_id"],
        }
        self.assertEqual(len(identities), 3)

    def test_the_first_issuers_distribution_is_unchanged(self):
        ps = self.aapl["distributions"][METRIC_PS_RATIO]
        self.assertEqual(ps["sample_count"], 28)
        self.assertEqual(ps["percentiles"]["median"], 7.257709)
        ev = self.aapl["distributions"][METRIC_EV_EBITDA_RATIO]
        self.assertEqual(ev["sample_count"], 27)
        self.assertEqual(ev["percentiles"]["median"], 22.326)

    def test_the_second_issuers_distribution_is_unchanged(self):
        ps = self.msft["distributions"][METRIC_PS_RATIO]
        self.assertEqual(ps["sample_count"], 23)
        self.assertEqual(ps["percentiles"]["median"], 11.783822)
        ev = self.msft["distributions"][METRIC_EV_EBITDA_RATIO]
        self.assertEqual(ev["sample_count"], 0)
        self.assertEqual(ev["status"], "UNAVAILABLE")

    def test_the_first_issuers_identities_are_unchanged(self):
        income = load_issuer_historical_income(INCOME_CONFIGS["AAPL"]).to_dict()
        self.assertEqual(
            income["input_set_id"],
            "401a14e73b53e6b1434be23b2c27c4ea6a0a10db0025b23cbf3740419c58e4b4",
        )
        self.assertEqual(
            income["content_hash"],
            "568d33fac2c202a2ac601657a6a5ebffdaa9057d0aec5bd2f0b600bec3f1f30b",
        )
        self.assertEqual(
            self.aapl["input_set_id"],
            "77402a13b164324323ab08341cfca35408b489232a4066f0a9e61b479c78a540",
        )
        self.assertEqual(
            self.aapl["content_hash"],
            "321e8b165bfc7ef30e4c178934a122e5bc2f41fd639ab7ad0767d0ce595b59b0",
        )

    def test_each_issuer_reads_its_own_price_series(self):
        symbols = set()
        for ticker in ("AAPL", "MSFT", "AEP"):
            with open(
                ROOT / "data" / "historical_pe" / ticker / "daily_prices.json",
                encoding="utf-8",
            ) as handle:
                chart = json.load(handle)["chart"]["result"][0]
            symbols.add(chart["meta"]["symbol"])
        self.assertEqual(len(symbols), 3)

    def test_no_issuers_median_is_offered_for_another(self):
        _, _, apple = load_production_historical_references(
            "AAPL", include_historical_multiples=True
        )
        _, _, microsoft = load_production_historical_references(
            "MSFT", include_historical_multiples=True
        )
        _, _, electric = load_production_historical_references(
            "AEP", include_historical_multiples=True
        )
        self.assertEqual(production_ps_for_reference(apple)[0], 7.257709)
        self.assertEqual(production_ps_for_reference(microsoft)[0], 11.783822)
        self.assertIsNone(production_ps_for_reference(electric)[0])
        self.assertEqual(production_ev_ebitda_for_reference(electric)[0], 13.221693)


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class TheProductWiring(unittest.TestCase):
    """The qualified reference reaches the report, the context and the archive."""

    def test_the_run_selects_the_production_ev_ebitda_median(self):
        result = run_st_eva(
            TICKER,
            mode="regression",
            include_historical_multiples=True,
            save_snapshot=False,
            reverse_horizons=[3],
            required_returns=[0.1],
        )
        reference = result["reference"]
        self.assertEqual(
            reference["ev_ebitda_method"], "production_historical_ev_ebitda_median"
        )
        self.assertEqual(reference["ev_ebitda_multiple"], 13.221693)
        self.assertEqual(
            reference["production_historical_ev_ebitda_sample_count"], 24
        )
        self.assertEqual(
            reference["production_historical_ev_ebitda_status"], "USABLE_FOR_REFERENCE"
        )

    def test_the_unqualified_ps_reference_is_not_selected(self):
        result = run_st_eva(
            TICKER,
            mode="regression",
            include_historical_multiples=True,
            save_snapshot=False,
            reverse_horizons=[3],
            required_returns=[0.1],
        )
        reference = result["reference"]
        self.assertIsNone(reference["ps_multiple"])
        self.assertEqual(
            reference["production_historical_ps_status"], "INSUFFICIENT_OBSERVATIONS"
        )

    def test_a_user_multiple_still_wins(self):
        result = run_st_eva(
            TICKER,
            mode="regression",
            include_historical_multiples=True,
            ps_multiple=3.0,
            ev_ebitda_multiple=11.0,
            save_snapshot=False,
            reverse_horizons=[3],
            required_returns=[0.1],
        )
        reference = result["reference"]
        self.assertEqual(reference["ev_ebitda_method"], "user_supplied_multiple")
        self.assertEqual(reference["ev_ebitda_multiple"], 11.0)
        method = result["reverse_requirements"]["valuation_methods"]["methods"][
            "enterprise_value_multiple"
        ]["reference_multiple"]
        self.assertEqual(method["source"], "user_supplied")
        self.assertIs(method["is_user_assumption"], True)

    def test_the_pfcf_method_still_reads_no_production_reference(self):
        result = run_st_eva(
            TICKER,
            mode="regression",
            include_historical_multiples=True,
            save_snapshot=False,
            reverse_horizons=[3],
            required_returns=[0.1],
        )
        methods = result["reverse_requirements"]["valuation_methods"]["methods"]
        self.assertIsNone(methods["cash_flow_multiple"]["reference_multiple"])

    def test_the_compact_summary_agrees_with_the_payload(self):
        payload = _payload()
        summary = production_multiples_summary(payload)
        for metric in (METRIC_PS_RATIO, METRIC_EV_EBITDA_RATIO):
            self.assertEqual(
                summary["distributions"][metric]["sample_count"],
                payload["distributions"][metric]["sample_count"],
            )
        self.assertEqual(summary["input_set_id"], payload["input_set_id"])


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class TheArchiveAndReplay(unittest.TestCase):
    """The archive keeps the counts, and the replay reproduces the document."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.archive_path = str(Path(cls.tmp.name) / "aep.sqlite")
        cls.context_path = str(Path(cls.tmp.name) / "ctx.json")
        store = SQLiteArchive(cls.archive_path)
        try:
            run_st_eva(
                TICKER,
                mode="regression",
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

    def test_the_archived_document_saves_the_count(self):
        refs = self.document["provenance"]["refs"]
        self.assertEqual(
            refs["refc:ev_ebitda_reference"]["source_observation_count"], 24
        )
        self.assertEqual(
            refs["refc:ev_ebitda_reference"]["basis"], "PRODUCTION_EV_EBITDA_MEDIAN"
        )

    def test_the_replay_request_carries_the_count(self):
        request = production_reference_request(self.document)
        self.assertEqual(request["multiples_ev_ebitda"], 24)

    def test_the_replay_reproduces_the_document(self):
        store = SQLiteArchive(self.archive_path)
        try:
            from web.service_adapter import default_replay_doc_builder

            result = replay(store, TICKER, "2026-12-31", default_replay_doc_builder)
        finally:
            store.close()
        self.assertEqual(result.outcome, "MATCH")
        refs = result.document["provenance"]["refs"]
        self.assertEqual(
            refs["refc:ev_ebitda_reference"]["source_observation_count"], 24
        )
        self.assertEqual(refs["refc:ev_ebitda_reference"]["multiple"], 13.221693)

    def test_an_archive_without_a_count_is_not_given_one(self):
        legacy = copy.deepcopy(self.document)
        legacy["provenance"]["refs"]["refc:ev_ebitda_reference"][
            "source_observation_count"
        ] = None
        request = production_reference_request(legacy)
        self.assertIsNone(request["multiples_ev_ebitda"])


if __name__ == "__main__":
    unittest.main()
