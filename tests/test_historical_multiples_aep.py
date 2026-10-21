"""American Electric Power's production historical P/S and EV/EBITDA reference
distributions.

The second issuer with a qualified enterprise-value reference, through the
same generic pipeline: the same builders, the same point-in-time rule, the
same sufficiency gate, the same report, context, archive and replay. These
tests hold the second issuer to the same evidence the first one is held to,
and they hold the three issuers apart.
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

    def test_the_concepts_are_the_elements_this_issuer_uses(self):
        tags = self.payload["concept_tags"]
        self.assertEqual(tags["cash"], "CashAndCashEquivalentsAtCarryingValue")
        # This issuer reports current marketable securities as short-term
        # investments, and does not use the element the first issuer uses.
        self.assertEqual(tags["marketable_securities_current"], "ShortTermInvestments")
        self.assertEqual(tags["commercial_paper"], "CommercialPaper")
        self.assertEqual(tags["long_term_debt_current"], "LongTermDebtCurrent")
        self.assertEqual(tags["long_term_debt_noncurrent"], "LongTermDebtNoncurrent")

    def test_the_depreciation_role_is_the_filers_own_line(self):
        income = load_issuer_historical_income(INCOME_CONFIGS[TICKER]).to_dict()
        # The cash-flow line "Depreciation and Amortization", on a
        # utility-sector element; the amortization of nuclear fuel is a
        # separate line, so this one is depreciation and amortization and
        # nothing else.
        self.assertEqual(
            income["concept_tags"]["depreciation_and_amortization"],
            "UtilitiesOperatingExpenseDepreciationAndAmortization",
        )

    def test_the_core_registry_accepts_this_issuers_depreciation_element(self):
        from sec_derived_inputs import _concept_is_exact_for

        self.assertTrue(
            _concept_is_exact_for(
                "depreciation_and_amortization",
                "UtilitiesOperatingExpenseDepreciationAndAmortization",
                TICKER,
            )
        )
        self.assertTrue(
            _concept_is_exact_for("operating_income", "OperatingIncomeLoss", TICKER)
        )

    def test_the_retired_revenue_mapping_stays_retired(self):
        # This issuer's revenue line is carried on us-gaap:Revenues, and the
        # registry retired that element as a mapping to the revenue metric
        # (2.99) because the element's own definition is broader than the
        # metric. The decision is honoured here: the historical dataset reads
        # the filer's own line, and the registry still declines the element,
        # so this issuer's current figures in the valuation chain stay the
        # provider's. No scope was invented to rescue it.
        from core_registry import CoreRegistry
        from registry_seed import seed
        from sqlite_archive import SQLiteArchive

        store = SQLiteArchive(":memory:")
        try:
            registry = CoreRegistry(store.connection)
            seed(registry)
            store.connection.commit()
            rows = [
                dict(row)
                for row in store.connection.execute(
                    "SELECT metric_id, concept_id, scope_json FROM"
                    " metric_concept_mapping"
                )
            ]
        finally:
            store.close()
        revenues_rows = [
            row
            for row in rows
            if row["concept_id"] == "us-gaap:Revenues"
        ]
        self.assertEqual(revenues_rows, [])
        from sec_derived_inputs import _concept_is_exact_for

        self.assertFalse(_concept_is_exact_for("revenue", "Revenues", TICKER))

    def test_the_registry_keeps_the_other_issuers_decisions(self):
        from sec_derived_inputs import _concept_is_exact_for

        # The first issuer's element stays mapped for that issuer alone, and
        # the second issuer's refusal stands.
        self.assertTrue(
            _concept_is_exact_for(
                "depreciation_and_amortization",
                "DepreciationDepletionAndAmortization",
                "AAPL",
            )
        )
        self.assertFalse(
            _concept_is_exact_for(
                "depreciation_and_amortization",
                "DepreciationDepletionAndAmortization",
                "AEP",
            )
        )
        self.assertFalse(
            _concept_is_exact_for("depreciation_and_amortization", "Depreciation", "MSFT")
        )
        self.assertFalse(
            _concept_is_exact_for(
                "depreciation_and_amortization", "DepreciationAmortizationAndOther", "MSFT"
            )
        )

    def test_every_observation_carries_its_source_lineage(self):
        for observation in self.payload["observations"]:
            lineage = observation["source_lineage"]
            self.assertTrue(lineage["income_observation_id"], observation)
            self.assertTrue(lineage["income_input_set_id"], observation)


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

    def test_the_market_cap_is_continuous_across_the_sample(self):
        caps = sorted(
            (o["evaluation_date"], o["market_cap"])
            for o in self.payload["observations"]
            if o["market_cap"] is not None
        )
        for (day, cap), (previous_day, previous_cap) in zip(caps, caps[1:]):
            ratio = cap / previous_cap
            self.assertGreater(ratio, 0.6, (previous_day, day, ratio))
            self.assertLess(ratio, 1.7, (previous_day, day, ratio))


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
        self.assertEqual(len(values), 29)

    def test_every_ebitda_window_is_the_sum_of_its_quarters(self):
        for observation in self.payload["observations"]:
            if observation["ttm_ebitda"] is None:
                continue
            day = observation["evaluation_date"]
            window = self.ebitda_windows[day]
            operating = sum(quarter["operating_income"] for quarter in window["quarters"])
            depreciation = sum(
                quarter["depreciation_and_amortization"]
                for quarter in window["quarters"]
            )
            self.assertAlmostEqual(
                operating + depreciation, window["value"], places=0
            )
            self.assertEqual(window["value"], observation["ttm_ebitda"])

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


class TheEligibility(unittest.TestCase):
    """Each distribution is qualified on its own evidence."""

    @classmethod
    def setUpClass(cls):
        cls.payload = _payload()

    def test_both_distributions_qualify_on_their_own_samples(self):
        for metric in (METRIC_PS_RATIO, METRIC_EV_EBITDA_RATIO):
            distribution = self.payload["distributions"][metric]
            self.assertEqual(distribution["status"], "USABLE_FOR_REFERENCE", metric)
            self.assertIs(distribution["usable_for_reference"], True, metric)
            self.assertGreaterEqual(
                distribution["sample_count"],
                distribution["min_observations_required"],
                metric,
            )

    def test_the_measured_counts_and_medians(self):
        ps = self.payload["distributions"][METRIC_PS_RATIO]
        self.assertEqual(ps["sample_count"], 29)
        self.assertEqual(ps["total_evaluations"], 33)
        self.assertEqual(ps["percentiles"]["median"], 2.728945)
        ev = self.payload["distributions"][METRIC_EV_EBITDA_RATIO]
        self.assertEqual(ev["sample_count"], 25)
        self.assertEqual(ev["total_evaluations"], 33)
        self.assertEqual(ev["percentiles"]["median"], 13.224119)

    def test_the_rejections_state_their_cause(self):
        reasons = {
            observation["evaluation_date"]: observation["ev_reason_code"]
            for observation in self.payload["observations"]
            if observation["ev_ebitda_ratio"] is None
        }
        self.assertEqual(len(reasons), 8)
        for code in reasons.values():
            self.assertIn(
                code,
                (
                    "REASON_MISSING_EBITDA_WINDOW",
                    "REASON_SOURCE_CONCEPT_COVERAGE_GAP",
                ),
            )

    def test_the_references_are_the_distributions_own_medians(self):
        ps_median, ps_status = production_ps_for_reference(self.payload)
        ev_median, ev_status = production_ev_ebitda_for_reference(self.payload)
        self.assertEqual(ps_status, "USABLE_FOR_REFERENCE")
        self.assertEqual(ev_status, "USABLE_FOR_REFERENCE")
        self.assertEqual(
            ps_median, self.payload["distributions"][METRIC_PS_RATIO]["percentiles"]["median"]
        )
        self.assertEqual(
            ev_median,
            self.payload["distributions"][METRIC_EV_EBITDA_RATIO]["percentiles"]["median"],
        )


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
        apple_median, _ = production_ps_for_reference(apple)
        microsoft_median, _ = production_ps_for_reference(microsoft)
        self.assertEqual(apple_median, 7.257709)
        self.assertEqual(microsoft_median, 11.783822)
        self.assertNotEqual(apple_median, 2.728945)


class TheProductWiring(unittest.TestCase):
    """The qualified references reach the report, the context and the archive."""

    def test_the_run_selects_both_production_medians(self):
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
        self.assertEqual(reference["ps_multiple"], 2.728945)
        self.assertEqual(reference["production_historical_ps_sample_count"], 29)
        self.assertEqual(
            reference["ev_ebitda_method"], "production_historical_ev_ebitda_median"
        )
        self.assertEqual(reference["ev_ebitda_multiple"], 13.224119)
        self.assertEqual(
            reference["production_historical_ev_ebitda_sample_count"], 25
        )

    def test_the_report_carries_the_multiples_summary(self):
        result = run_st_eva(
            TICKER,
            mode="regression",
            include_historical_multiples=True,
            save_snapshot=False,
            reverse_horizons=[3],
            required_returns=[0.1],
        )
        summary = result["reverse_requirements"][
            "production_historical_multiples_summary"
        ]
        self.assertEqual(summary["distributions"][METRIC_PS_RATIO]["sample_count"], 29)
        self.assertEqual(
            summary["distributions"][METRIC_EV_EBITDA_RATIO]["sample_count"], 25
        )
        self.assertEqual(
            summary["input_set_id"],
            result["production_historical_multiples"]["input_set_id"],
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
        self.assertEqual(reference["ps_method"], "user_supplied_multiple")
        self.assertEqual(reference["ev_ebitda_method"], "user_supplied_multiple")
        method = result["reverse_requirements"]["valuation_methods"]["methods"][
            "revenue_multiple"
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


class TheArchiveAndReplay(unittest.TestCase):
    """The archive keeps this issuer's counts, and the replay reproduces them."""

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

    def test_the_archived_document_saves_both_counts(self):
        refs = self.document["provenance"]["refs"]
        self.assertEqual(refs["refc:ps_reference"]["source_observation_count"], 29)
        self.assertEqual(refs["refc:ps_reference"]["basis"], "PRODUCTION_PS_MEDIAN")
        self.assertEqual(
            refs["refc:ev_ebitda_reference"]["source_observation_count"], 25
        )
        self.assertEqual(
            refs["refc:ev_ebitda_reference"]["basis"], "PRODUCTION_EV_EBITDA_MEDIAN"
        )

    def test_the_replay_request_carries_both_counts(self):
        request = production_reference_request(self.document)
        self.assertEqual(request["multiples_ps"], 29)
        self.assertEqual(request["multiples_ev_ebitda"], 25)

    def test_the_replay_reproduces_the_document(self):
        store = SQLiteArchive(self.archive_path)
        try:
            from web.service_adapter import default_replay_doc_builder

            result = replay(store, TICKER, "2026-12-31", default_replay_doc_builder)
        finally:
            store.close()
        self.assertEqual(result.outcome, "MATCH")
        refs = result.document["provenance"]["refs"]
        self.assertEqual(refs["refc:ps_reference"]["source_observation_count"], 29)
        self.assertEqual(
            refs["refc:ev_ebitda_reference"]["source_observation_count"], 25
        )

    def test_an_archive_without_a_count_is_not_given_one(self):
        legacy = copy.deepcopy(self.document)
        legacy["provenance"]["refs"]["refc:ps_reference"][
            "source_observation_count"
        ] = None
        request = production_reference_request(legacy)
        self.assertIsNone(request["multiples_ps"])


if __name__ == "__main__":
    unittest.main()
