"""Microsoft's production historical P/S and EV/EBITDA reference distributions.

The second issuer through the same generic pipeline: the same builders, the
same point-in-time rule, the same sufficiency gate, the same report, context,
archive and replay. What differs is the evidence, and these tests hold the
difference to the evidence rather than to a rule relaxed to reach a number.
"""
import copy
import datetime
import json
import shutil
import statistics
import tempfile
import unittest
from pathlib import Path

from historical_income import ISSUER_CONFIGS as INCOME_CONFIGS
from historical_income import load_issuer_historical_income
from historical_multiples import (
    EV_BRIDGE_COMPONENTS,
    ISSUER_CONFIGS,
    METRIC_EV_EBITDA_RATIO,
    METRIC_PS_RATIO,
    REASON_INSUFFICIENT_OBSERVATIONS,
    REASON_MIXED_BALANCE_SHEET_PERIODS,
    REASON_MISSING_EBITDA_WINDOW,
    REASON_MISSING_REVENUE_WINDOW,
    REASON_NO_QUALIFIED_DA_EVIDENCE,
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

TICKER = "MSFT"
ROOT = Path(__file__).resolve().parent.parent

PRICES_EXIST = (ROOT / "data" / "historical_pe" / "MSFT" / "daily_prices.json").exists()
PRICES_SKIP = "MSFT daily_prices.json excluded per C-1 / DATA-DELIVERY.md"


def _payload():
    return load_issuer_historical_multiples(ISSUER_CONFIGS[TICKER]).to_dict()


def _raw_prices():
    """The as-traded closes, read straight from the source file."""
    with open(
        ROOT / "data" / "historical_pe" / TICKER / "daily_prices.json",
        encoding="utf-8",
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
    """The cover-page share counts, read straight from the source file."""
    with open(
        ROOT / "data" / "historical_pfcf" / TICKER / "shares_outstanding_concept.json",
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

    def test_every_source_is_an_sec_companyconcept_url_or_a_named_reuse(self):
        for name, meta in self.manifest["provenance"]["files"].items():
            if "path" in meta:
                self.assertTrue(meta["path"].startswith("data/"), name)
            else:
                self.assertIn("data.sec.gov/api/xbrl/companyconcept", meta["source"])

    def test_the_concepts_are_the_elements_microsoft_uses(self):
        tags = self.payload["concept_tags"]
        self.assertEqual(tags["cash"], "CashAndCashEquivalentsAtCarryingValue")
        # Microsoft reports current marketable securities as short-term
        # investments and does not use the element Apple uses.
        self.assertEqual(tags["marketable_securities_current"], "ShortTermInvestments")
        self.assertEqual(tags["commercial_paper"], "CommercialPaper")
        self.assertEqual(tags["long_term_debt_current"], "LongTermDebtCurrent")
        self.assertEqual(tags["long_term_debt_noncurrent"], "LongTermDebtNoncurrent")

    def test_the_issuer_is_microsoft_on_its_june_fiscal_year(self):
        self.assertEqual(self.payload["issuer_id"], "CIK0000789019")
        self.assertEqual(self.manifest["provenance"]["issuer_facts"]["fye_month"], 6)
        self.assertEqual(self.manifest["entity_name"], "Microsoft Corporation")

    def test_every_observation_carries_its_source_lineage(self):
        for observation in self.payload["observations"]:
            lineage = observation["source_lineage"]
            self.assertTrue(lineage["income_observation_id"], observation)
            self.assertTrue(lineage["income_input_set_id"], observation)
            if observation["ps_ratio"] is not None:
                self.assertTrue(lineage["revenue_window_accessions"], observation)
                self.assertTrue(lineage["shares_accessions"], observation)


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

    def test_microsoft_has_had_no_split_since_the_price_series_begins(self):
        # The as-traded close and the cover-page share count pair directly,
        # because there is no split to adjust either side of the pair.
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
        self.assertEqual(len(values), 23)

    def test_the_median_recomputes_from_the_published_observations(self):
        distribution = self.payload["distributions"][METRIC_PS_RATIO]
        values = [
            observation["value"] for observation in distribution["observations"]
        ]
        self.assertEqual(
            distribution["percentiles"]["median"], round(statistics.median(values), 6)
        )
        self.assertEqual(distribution["sample_count"], len(values))

    def test_every_rejection_states_a_reason_from_the_closed_set(self):
        from historical_multiples import CLOSED_REASON_CODES

        for observation in self.payload["observations"]:
            for code in (
                observation["ps_reason_code"],
                observation["ev_reason_code"],
            ):
                if code:
                    self.assertIn(code, CLOSED_REASON_CODES)

    def test_a_refused_window_is_never_backfilled(self):
        for observation in self.payload["observations"]:
            if observation["ps_ratio"] is None:
                # The market cap may still be there -- it is a fact about the
                # price and the share count -- but no multiple is derived from
                # a window that does not exist.
                self.assertIsNone(observation["ps_ratio"], observation)
                self.assertIn(
                    observation["ps_reason_code"],
                    (
                        REASON_MISSING_REVENUE_WINDOW,
                        "REASON_SOURCE_CONCEPT_COVERAGE_GAP",
                    ),
                )
                self.assertIsNone(observation["ps_formula"].get("value"), observation)

    def test_no_enterprise_value_is_published_from_a_mixed_bridge(self):
        for observation in self.payload["observations"]:
            bridge = observation["ev_bridge"]
            if not bridge["components"]:
                continue
            periods = {fact["period_end"] for fact in bridge["components"].values()}
            if len(periods) > 1:
                # A bridge that mixes two balance sheets publishes no
                # enterprise value. The reason the date carries is the
                # denominator, which does not exist at all for Microsoft, so
                # the bridge is never the binding cause -- but the bridge's
                # own state is still recorded and still refuses.
                self.assertIsNone(observation["enterprise_value"], observation)
                self.assertIsNone(observation["ev_ebitda_ratio"], observation)
                self.assertIs(bridge["complete"], False)
                self.assertEqual(
                    observation["ev_reason_code"], REASON_NO_QUALIFIED_DA_EVIDENCE
                )
                self.assertGreater(len(bridge["period_alignment"]["distinct_period_ends"]), 1)

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
class TheEligibility(unittest.TestCase):
    """Each distribution is qualified on its own evidence."""

    @classmethod
    def setUpClass(cls):
        cls.payload = _payload()

    def test_the_ps_distribution_qualifies_on_its_own_sample(self):
        distribution = self.payload["distributions"][METRIC_PS_RATIO]
        self.assertEqual(distribution["sample_count"], 23)
        self.assertEqual(distribution["total_evaluations"], 27)
        self.assertEqual(distribution["status"], "USABLE_FOR_REFERENCE")
        self.assertIs(distribution["usable_for_reference"], True)
        self.assertGreaterEqual(
            distribution["sample_count"], distribution["min_observations_required"]
        )
        self.assertEqual(distribution["percentiles"]["median"], 11.783822)

    def test_the_ev_ebitda_distribution_does_not_qualify_and_says_why(self):
        distribution = self.payload["distributions"][METRIC_EV_EBITDA_RATIO]
        self.assertEqual(distribution["sample_count"], 0)
        self.assertEqual(distribution["status"], "UNAVAILABLE")
        self.assertIs(distribution["usable_for_reference"], False)
        # The reason names the cause: the denominator does not exist, because
        # no element qualifies for the depreciation-and-amortization role. The
        # distribution's own code says so. A shortage of observations would
        # send a reader looking for more of the very evidence that cannot
        # exist: the registry does not accept this issuer's depreciation
        # element as the metric, so no count of quarters would help.
        self.assertEqual(distribution["reason_code"], REASON_NO_QUALIFIED_DA_EVIDENCE)
        self.assertNotEqual(
            distribution["reason_code"], REASON_INSUFFICIENT_OBSERVATIONS
        )
        detail = distribution["reason_detail"]
        self.assertIn(REASON_NO_QUALIFIED_DA_EVIDENCE, detail)
        self.assertNotIn(REASON_MISSING_EBITDA_WINDOW, detail)

    def test_one_qualifying_distribution_does_not_qualify_the_other(self):
        distributions = self.payload["distributions"]
        self.assertIs(distributions[METRIC_PS_RATIO]["usable_for_reference"], True)
        self.assertIs(distributions[METRIC_EV_EBITDA_RATIO]["usable_for_reference"], False)

    def test_the_usable_distribution_and_the_unusable_one_report_differently(self):
        _, ps_status = production_ps_for_reference(self.payload)
        ev_median, ev_status = production_ev_ebitda_for_reference(self.payload)
        self.assertEqual(ps_status, "USABLE_FOR_REFERENCE")
        self.assertIsNone(ev_median)
        self.assertEqual(ev_status, "UNAVAILABLE")

    def test_the_thin_sample_would_not_qualify_at_any_threshold_it_cannot_meet(self):
        # The gate is the rule, and the rule is not met here: the sample is
        # zero, so no threshold below one would be a threshold the data meets.
        distribution = self.payload["distributions"][METRIC_EV_EBITDA_RATIO]
        self.assertEqual(distribution["sample_count"], 0)
        self.assertGreater(distribution["min_observations_required"], 0)


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class TheCrossCompanyBoundary(unittest.TestCase):
    """One issuer's data never becomes another issuer's reference."""

    @classmethod
    def setUpClass(cls):
        cls.msft = _payload()
        cls.aapl = load_issuer_historical_multiples(ISSUER_CONFIGS["AAPL"]).to_dict()

    def test_the_two_issuers_have_different_dataset_identities(self):
        self.assertNotEqual(
            self.msft["input_set_id"], self.aapl["input_set_id"]
        )
        self.assertNotEqual(self.msft["content_hash"], self.aapl["content_hash"])

    def test_aapls_distribution_is_unchanged_by_the_microsoft_data(self):
        distribution = self.aapl["distributions"][METRIC_PS_RATIO]
        self.assertEqual(distribution["sample_count"], 28)
        self.assertEqual(distribution["percentiles"]["median"], 7.257709)
        ev = self.aapl["distributions"][METRIC_EV_EBITDA_RATIO]
        self.assertEqual(ev["sample_count"], 27)
        self.assertEqual(ev["percentiles"]["median"], 22.326)

    def test_each_issuers_observations_name_only_its_own_filings(self):
        for payload, issuer in ((self.msft, "CIK0000789019"), (self.aapl, "CIK0000320193")):
            self.assertEqual(payload["issuer_id"], issuer)
            for observation in payload["observations"]:
                for accession in (
                    observation["source_lineage"]["revenue_window_accessions"]
                    + observation["source_lineage"]["balance_sheet_accessions"]
                    + observation["source_lineage"]["shares_accessions"]
                ):
                    self.assertTrue(accession, observation)

    def test_the_two_issuers_read_different_price_and_share_series(self):
        with open(
            ROOT / "data" / "historical_pe" / TICKER / "daily_prices.json",
            encoding="utf-8",
        ) as handle:
            msft_prices = json.load(handle)
        with open(
            ROOT / "data" / "historical_pe" / "AAPL" / "daily_prices.json",
            encoding="utf-8",
        ) as handle:
            aapl_prices = json.load(handle)
        self.assertNotEqual(
            msft_prices["chart"]["result"][0]["meta"]["symbol"],
            aapl_prices["chart"]["result"][0]["meta"]["symbol"],
        )

    def test_no_microsoft_multiple_is_offered_for_apple(self):
        _, _, apple = load_production_historical_references(
            "AAPL", include_historical_multiples=True
        )
        median, _ = production_ps_for_reference(apple)
        self.assertEqual(median, 7.257709)


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class TheDepreciationRole(unittest.TestCase):
    """Pure depreciation is not depreciation and amortization.

    Microsoft reports depreciation alone on us-gaap:Depreciation and its
    cash-flow line on a company-specific element the registry does not accept.
    The role is therefore empty, and these tests hold it empty.
    """

    @classmethod
    def setUpClass(cls):
        cls.income = load_issuer_historical_income(INCOME_CONFIGS[TICKER]).to_dict()
        cls.manifest = json.loads(
            (
                ROOT / "data" / "historical_income" / TICKER / "manifest.json"
            ).read_text(encoding="utf-8")
        )

    def test_the_role_is_empty(self):
        self.assertIsNone(self.income["concept_tags"]["depreciation_and_amortization"])
        self.assertIsNone(INCOME_CONFIGS[TICKER].depreciation_concept)

    def test_no_observation_carries_a_trailing_ebitda(self):
        for observation in self.income["observations"]:
            self.assertIsNone(observation["ttm_ebitda"], observation)

    def test_no_window_is_published_for_the_ebitda_role(self):
        for observation in self.income["observations"]:
            rejection = (observation.get("window_rejection") or {}).get("ebitda")
            if rejection is None:
                continue
            self.assertEqual(
                rejection["reason_code"], "REASON_NO_QUALIFIED_DA_EVIDENCE", observation
            )
            self.assertEqual(rejection["positions_missing"], [])
            self.assertIn("depreciation", rejection["detail"].lower())

    def test_the_pure_depreciation_evidence_is_kept_and_named(self):
        import hashlib

        path = (
            ROOT
            / "data"
            / "historical_income"
            / TICKER
            / "depreciation_expense_concept.json"
        )
        self.assertTrue(path.exists())
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
        self.assertEqual(payload["tag"], "Depreciation")
        files = self.manifest["provenance"]["files"]
        self.assertIn("depreciation_expense_concept.json", files)
        entry = files["depreciation_expense_concept.json"]
        self.assertEqual(entry["role"], "evidence_only")
        self.assertIn("DEPRECIATION ALONE", entry["definition"])
        self.assertEqual(
            hashlib.sha256(path.read_bytes()).hexdigest(), entry["content_sha256"]
        )

    def test_the_manifest_states_which_elements_fill_the_role_and_which_do_not(self):
        role = self.manifest["provenance"]["depreciation_and_amortization_role"]
        self.assertIs(role["filled"], False)
        self.assertIsNone(role["element"])
        self.assertIn(
            "msft:DepreciationAmortizationAndOther",
            role["rejected_element"]["element"],
        )
        self.assertIn("bundles 'other' items", role["rejected_element"]["why"])
        # The two note elements are not added together to stand in for the
        # cash-flow line, and the manifest says so.
        self.assertIn("39,000,000,000", role["not_a_substitute"])

    def test_the_pure_depreciation_never_reaches_an_ebitda_figure(self):
        payload = _payload()
        for observation in payload["observations"]:
            self.assertIsNone(observation["ttm_ebitda"], observation)
            self.assertIsNone(observation["ev_ebitda_ratio"], observation)
        self.assertEqual(
            payload["distributions"][METRIC_EV_EBITDA_RATIO]["sample_count"], 0
        )

    def test_the_core_registry_does_not_map_the_element_either(self):
        # The provider's current EBITDA stays the provider's figure, because
        # no element is mapped to the metric for this issuer.
        from sec_derived_inputs import _concept_is_exact_for

        self.assertFalse(
            _concept_is_exact_for(
                "depreciation_and_amortization", "Depreciation", TICKER
            )
        )
        self.assertFalse(
            _concept_is_exact_for(
                "depreciation_and_amortization",
                "DepreciationAmortizationAndOther",
                TICKER,
            )
        )

    def test_the_dataset_is_not_a_substitute_for_the_providers_current_figure(self):
        # The income dataset holds no D&A element, so the valuation chain
        # cannot read a filed EBITDA out of it; the provider's figure stands,
        # and the two are different paths.
        self.assertIsNone(
            (self.income["concept_tags"] or {}).get("depreciation_and_amortization")
        )


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class TheProductWiring(unittest.TestCase):
    """The reference reaches the report, the context and the archive."""

    def test_the_run_selects_the_production_ps_median(self):
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
        self.assertEqual(reference["ps_multiple"], 11.783822)
        self.assertEqual(reference["production_historical_ps_sample_count"], 23)
        self.assertEqual(reference["production_historical_ps_status"], "USABLE_FOR_REFERENCE")

    def test_the_ev_ebitda_reference_is_unavailable_and_never_borrowed(self):
        result = run_st_eva(
            TICKER,
            mode="regression",
            include_historical_multiples=True,
            save_snapshot=False,
            reverse_horizons=[3],
            required_returns=[0.1],
        )
        reference = result["reference"]
        self.assertEqual(reference["ev_ebitda_method"], "none")
        self.assertIsNone(reference["ev_ebitda_multiple"])
        self.assertEqual(
            reference["production_historical_ev_ebitda_status"], "UNAVAILABLE"
        )
        methods = result["reverse_requirements"]["valuation_methods"]["methods"]
        self.assertIsNone(methods["enterprise_value_multiple"]["reference_multiple"])

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
        self.assertEqual(summary["distributions"][METRIC_PS_RATIO]["sample_count"], 23)
        self.assertEqual(
            summary["distributions"][METRIC_EV_EBITDA_RATIO]["sample_count"], 0
        )
        self.assertEqual(
            summary["input_set_id"], result["production_historical_multiples"]["input_set_id"]
        )

    def test_a_user_multiple_still_wins_over_the_production_median(self):
        result = run_st_eva(
            TICKER,
            mode="regression",
            include_historical_multiples=True,
            ps_multiple=3.0,
            save_snapshot=False,
            reverse_horizons=[3],
            required_returns=[0.1],
        )
        reference = result["reference"]
        self.assertEqual(reference["ps_method"], "user_supplied_multiple")
        self.assertEqual(reference["ps_multiple"], 3.0)
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
        unavailable = [
            entry
            for entry in result["reverse_requirements"]["unavailable"]
            if entry.get("item") == "valuation_method.cash_flow"
        ]
        self.assertTrue(unavailable)

    def test_the_compact_summary_agrees_with_the_payload(self):
        payload = _payload()
        summary = production_multiples_summary(payload)
        for metric in (METRIC_PS_RATIO, METRIC_EV_EBITDA_RATIO):
            self.assertEqual(
                summary["distributions"][metric]["sample_count"],
                payload["distributions"][metric]["sample_count"],
            )
            self.assertEqual(
                summary["distributions"][metric]["status"],
                payload["distributions"][metric]["status"],
            )
        self.assertEqual(summary["input_set_id"], payload["input_set_id"])


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class TheArchiveAndReplay(unittest.TestCase):
    """The archive keeps Microsoft's counts, and the replay reproduces them."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.archive_path = str(Path(cls.tmp.name) / "msft.sqlite")
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

    def test_the_archived_document_saves_the_sample_count(self):
        refs = self.document["provenance"]["refs"]
        self.assertEqual(
            refs["refc:ps_reference"]["source_observation_count"], 23
        )
        self.assertEqual(
            refs["refc:ps_reference"]["basis"], "PRODUCTION_PS_MEDIAN"
        )
        self.assertEqual(
            refs["refc:ps_reference"]["multiple"], 11.783822
        )

    def test_the_enterprise_value_reference_is_recorded_as_unavailable(self):
        refs = self.document["provenance"]["refs"]
        entry = refs.get("refc:ev_ebitda_reference")
        if entry is not None:
            self.assertIsNone(entry.get("multiple"))
            self.assertIs(entry.get("eligible_as_reference"), False)

    def test_the_replay_request_carries_the_count(self):
        from archive import production_reference_request

        request = production_reference_request(self.document)
        self.assertEqual(request["multiples_ps"], 23)
        # The enterprise-value reference is unavailable, so it is not a
        # production reference the replay has to reproduce, and the request
        # does not name it. Nothing is invented to fill the gap.
        self.assertNotIn("multiples_ev_ebitda", request)

    def test_the_replay_reproduces_the_document(self):
        from archive import replay

        store = SQLiteArchive(self.archive_path)
        try:
            from web.service_adapter import default_replay_doc_builder

            result = replay(store, TICKER, "2026-12-31", default_replay_doc_builder)
        finally:
            store.close()
        self.assertEqual(result.outcome, "MATCH")
        refs = result.document["provenance"]["refs"]
        self.assertEqual(refs["refc:ps_reference"]["source_observation_count"], 23)
        self.assertEqual(refs["refc:ps_reference"]["multiple"], 11.783822)

    def test_a_changed_count_does_not_reproduce_the_archive(self):
        from archive import production_reference_count_divergence

        changed = copy.deepcopy(self.document)
        changed["provenance"]["refs"]["refc:ps_reference"][
            "source_observation_count"
        ] = 22
        differences = production_reference_count_divergence(changed, self.document)
        self.assertEqual(len(differences), 1)
        self.assertEqual(differences[0]["source"], "multiples_ps")
        self.assertEqual(differences[0]["archived_observation_count"], 22)
        self.assertEqual(differences[0]["rebuilt_observation_count"], 23)

    def test_an_archive_without_a_count_is_not_given_one(self):
        from archive import production_reference_request

        legacy = copy.deepcopy(self.document)
        legacy["provenance"]["refs"]["refc:ps_reference"][
            "source_observation_count"
        ] = None
        request = production_reference_request(legacy)
        self.assertIsNone(request["multiples_ps"])


if __name__ == "__main__":
    unittest.main()
