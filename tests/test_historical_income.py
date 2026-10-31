"""The filed trailing revenue and EBITDA, and the refusals that keep them out.

The AAPL income-statement dataset is the production source for the trailing
revenue and trailing EBITDA the sales and enterprise-value multiples are
computed from. These tests pin the qualification it has to pass and the
conditions under which it refuses, because a figure that is not a filed
trailing figure must not become a denominator.
"""
import copy
import unittest
from pathlib import Path

PRICES_EXIST = Path("data/historical_pe/AAPL/daily_prices.json").exists()
PRICES_SKIP = "AAPL daily_prices.json excluded per C-1 / DATA-DELIVERY.md"

from historical_income import (
    ISSUER_CONFIGS,
    METRIC_TTM_EBITDA,
    METRIC_TTM_REVENUE,
    load_issuer_historical_income,
)
from sec_derived_inputs import (
    qualified_ttm_ebitda,
    qualified_ttm_revenue,
)

TICKER = "AAPL"
CUT = "2026-10-20"


def _payload():
    return load_issuer_historical_income(ISSUER_CONFIGS[TICKER]).to_dict()


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class TheDataset(unittest.TestCase):
    """What the dataset holds, before anything is qualified from it."""

    @classmethod
    def setUpClass(cls):
        cls.payload = _payload()

    def test_the_dataset_names_the_concepts_it_read(self):
        tags = self.payload["concept_tags"]
        self.assertEqual(
            tags["revenue"], "RevenueFromContractWithCustomerExcludingAssessedTax"
        )
        self.assertEqual(tags["operating_income"], "OperatingIncomeLoss")
        self.assertEqual(
            tags["depreciation_and_amortization"],
            "DepreciationDepletionAndAmortization",
        )

    def test_every_evaluation_carries_a_window_or_a_reason(self):
        for observation in self.payload["observations"]:
            self.assertIn(
                observation["status"], ("AVAILABLE", "UNAVAILABLE"), observation
            )
            if observation["status"] == "AVAILABLE":
                self.assertIsNotNone(observation["ttm_revenue"])
                self.assertIsNotNone(observation["ttm_ebitda"])
            else:
                self.assertTrue(observation["reason_code"])
                self.assertTrue(observation["reason_detail"])

    def test_the_current_window_is_four_consecutive_quarters(self):
        snapshot = self.payload["current_snapshot"]
        for key in ("ttm_revenue", "ttm_ebitda"):
            quarters = snapshot[key]["quarters"]
            self.assertEqual(len(quarters), 4, key)
            positions = [
                (quarter["fiscal_year"], quarter["fiscal_quarter"])
                for quarter in quarters
            ]
            for index in range(1, 4):
                year, number = positions[index - 1]
                expected = (year, number + 1) if number < 4 else (year + 1, 1)
                self.assertEqual(positions[index], expected, key)

    def test_every_quarter_carries_its_filing(self):
        snapshot = self.payload["current_snapshot"]
        for quarter in snapshot["ttm_revenue"]["quarters"]:
            self.assertTrue(quarter["inputs"])
            for span in quarter["inputs"]:
                self.assertTrue(span["accession"])
                self.assertTrue(span["form"])
                self.assertTrue(span["usable_date"])
                self.assertTrue(span["source_url"])

    def test_a_derived_quarter_says_it_is_derived(self):
        snapshot = self.payload["current_snapshot"]
        derived = [
            quarter
            for quarter in snapshot["ttm_revenue"]["quarters"]
            if len(quarter["inputs"]) > 1
        ]
        self.assertTrue(derived, "the fourth quarter is a difference of two spans")
        for quarter in derived:
            self.assertIn("cumulative difference", quarter["derivation"])


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class TheQualification(unittest.TestCase):
    """What has to be true before a trailing figure may be used."""

    @classmethod
    def setUpClass(cls):
        cls.payload = _payload()

    def _latest_record(self, payload=None, window_key="ttm_revenue"):
        """The most recent evaluation that carries the named window."""
        records = (payload or self.payload)["observations"]
        for record in reversed(records):
            if record.get(window_key):
                return record
        raise AssertionError("the dataset carries no window")

    def _every_window(self, payload, window_key="ttm_revenue"):
        """Every evaluation's window, so a refusal has nowhere to fall back to."""
        for record in payload["observations"]:
            window = record.get(window_key)
            if window:
                yield window

    def test_aapl_qualifies_on_both_figures(self):
        revenue = qualified_ttm_revenue(self.payload, CUT, TICKER)
        ebitda = qualified_ttm_ebitda(self.payload, CUT, TICKER)
        self.assertIsNotNone(revenue)
        self.assertIsNotNone(ebitda)
        self.assertEqual(revenue["source"], "SEC_DERIVED")
        self.assertEqual(revenue["basis"], "TTM")
        self.assertEqual(revenue["currency"], "USD")
        self.assertEqual(len(revenue["components"]), 4)
        self.assertEqual(len(ebitda["components"]), 4)
        for component in ebitda["components"]:
            self.assertIsNotNone(component["operating_income"])
            self.assertIsNotNone(component["depreciation_and_amortization"])
            self.assertAlmostEqual(
                component["ebitda"],
                component["operating_income"]
                + component["depreciation_and_amortization"],
            )

    def test_the_trailing_figure_is_the_sum_of_the_quarters(self):
        revenue = qualified_ttm_revenue(self.payload, CUT, TICKER)
        self.assertAlmostEqual(
            revenue["value"],
            sum(component["value"] for component in revenue["components"]),
        )
        ebitda = qualified_ttm_ebitda(self.payload, CUT, TICKER)
        self.assertAlmostEqual(
            ebitda["value"],
            sum(component["value"] for component in ebitda["components"]),
        )

    def test_a_cut_before_any_window_is_knowable_refuses(self):
        self.assertIsNone(
            qualified_ttm_revenue(self.payload, "2018-01-01", TICKER)
        )
        self.assertIsNone(
            qualified_ttm_ebitda(self.payload, "2018-01-01", TICKER)
        )

    def test_an_earlier_cut_uses_the_window_that_was_knowable_then(self):
        # The FY2026 second-quarter filing was accepted on 2026-05-01, so a
        # cut on that day knows the window that ends in March, not the one that
        # ends in June.
        revenue = qualified_ttm_revenue(self.payload, "2026-05-01", TICKER)
        self.assertIsNotNone(revenue)
        self.assertEqual(revenue["components"][-1]["period_end"], "2026-03-28")

    def test_a_window_missing_a_quarter_refuses(self):
        payload = copy.deepcopy(self.payload)
        for window in self._every_window(payload):
            window["quarters"] = window["quarters"][:3]
        self.assertIsNone(qualified_ttm_revenue(payload, CUT, TICKER))

    def test_a_window_whose_quarters_are_not_consecutive_refuses(self):
        payload = copy.deepcopy(self.payload)
        for window in self._every_window(payload):
            window["quarters"][1]["fiscal_year"] = 2030
        self.assertIsNone(qualified_ttm_revenue(payload, CUT, TICKER))

    def test_a_window_in_two_currencies_refuses(self):
        payload = copy.deepcopy(self.payload)
        for window in self._every_window(payload):
            window["quarters"][2]["currency"] = "EUR"
        self.assertIsNone(qualified_ttm_revenue(payload, CUT, TICKER))

    def test_a_window_not_yet_knowable_refuses(self):
        payload = copy.deepcopy(self.payload)
        for window in self._every_window(payload):
            window["quarters"][0]["knowable_from"] = "2027-01-01"
        self.assertIsNone(qualified_ttm_revenue(payload, CUT, TICKER))

    def test_a_quarter_without_its_sources_refuses(self):
        payload = copy.deepcopy(self.payload)
        for window in self._every_window(payload):
            window["quarters"][1]["inputs"] = []
        self.assertIsNone(qualified_ttm_revenue(payload, CUT, TICKER))

    def test_an_ebitda_quarter_without_its_depreciation_refuses(self):
        payload = copy.deepcopy(self.payload)
        for window in self._every_window(payload, "ttm_ebitda"):
            window["quarters"][1]["depreciation_inputs"] = []
        self.assertIsNone(qualified_ttm_ebitda(payload, CUT, TICKER))

    def test_a_concept_the_registry_does_not_map_to_the_metric_refuses(self):
        payload = copy.deepcopy(self.payload)
        payload["concept_tags"]["revenue"] = "Revenues"
        self.assertIsNone(qualified_ttm_revenue(payload, CUT, TICKER))

    def test_a_mapping_scoped_to_another_issuer_refuses(self):
        # The depreciation element is Apple's own presentation, so the
        # registry maps it for Apple alone. For another issuer the same
        # element is not this metric.
        self.assertIsNone(qualified_ttm_ebitda(self.payload, CUT, "MU"))
        self.assertIsNone(qualified_ttm_ebitda(self.payload, CUT, "MSFT"))

    def test_no_ticker_means_no_qualification(self):
        self.assertIsNone(qualified_ttm_revenue(self.payload, CUT, ""))
        self.assertIsNone(qualified_ttm_ebitda(self.payload, CUT, ""))

    def test_an_issuer_without_a_dataset_qualifies_nothing(self):
        self.assertIsNone(qualified_ttm_revenue(None, CUT, TICKER))
        self.assertIsNone(qualified_ttm_ebitda(None, CUT, TICKER))


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class TheMetricNames(unittest.TestCase):
    """The dataset says which figures it produces."""

    def test_the_metric_names(self):
        self.assertEqual(METRIC_TTM_REVENUE, "TTM_REVENUE")
        self.assertEqual(METRIC_TTM_EBITDA, "TTM_EBITDA")


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class TheDocumentHoldsTheWindows(unittest.TestCase):
    """The context holds the windows, and recomputes the figures from them.

    The document is built with the parity check on: the registry recomputes
    each trailing figure from the quarters the document holds, and a
    disagreement with the engine raises rather than producing a document. So
    a document that exists is itself the proof that the two agree.
    """

    @classmethod
    def setUpClass(cls):
        import json
        import tempfile
        from pathlib import Path

        from st_eva_runner import run_st_eva

        cls._tmp = tempfile.TemporaryDirectory(prefix="income-context-")
        context_path = Path(cls._tmp.name) / "context.json"
        cls.core = run_st_eva(
            ticker=TICKER,
            mode="regression",
            include_historical_pe=True,
            include_historical_pfcf=True,
            include_historical_income=True,
            context_path=str(context_path),
            save_snapshot=False,
        )
        cls.document = json.loads(context_path.read_text(encoding="utf-8"))

    def test_the_document_carries_both_windows(self):
        observed = self.document["observed"]
        self.assertIn("ttm_revenue_window", observed)
        self.assertIn("ttm_ebitda_window", observed)

    def test_the_trailing_figures_are_derivations_over_those_windows(self):
        derived = self.document["derived"]
        for name in ("ttm_revenue", "ttm_ebitda"):
            self.assertIn(name, derived)
            figure = derived[name]["figure"]
            self.assertEqual(figure["provenance_kind"], "DERIVED")
            self.assertIsNotNone(figure["value"])
            self.assertTrue(derived[name]["derivation_ref"])

    def test_the_trailing_figure_is_the_sum_of_the_window_it_holds(self):
        observed = self.document["observed"]
        derived = self.document["derived"]
        for name, figure_name in (
            ("ttm_revenue_window", "ttm_revenue"),
            ("ttm_ebitda_window", "ttm_ebitda"),
        ):
            entry = observed[name]
            observation = entry[0] if isinstance(entry, list) else entry
            samples = observation["figure"]["value"]["samples"]
            self.assertEqual(len(samples), 4, name)
            self.assertAlmostEqual(
                derived[figure_name]["figure"]["value"], sum(samples), places=3
            )

    def test_the_sales_multiple_is_divided_by_the_trailing_revenue(self):
        provenance = self.core["input_provenance"]
        revenue = provenance["current_revenue"]
        self.assertEqual(revenue["source"], "SEC_DERIVED")
        self.assertEqual(revenue["basis"], "TTM")
        self.assertTrue(revenue["used_by_engine"])
        self.assertEqual(revenue["currency"], "USD")
        self.assertEqual(len(revenue["components"]), 4)
        for component in revenue["components"]:
            self.assertTrue(component["accession"])
            self.assertTrue(component["period_end"])

    def test_the_enterprise_value_multiple_is_divided_by_the_trailing_ebitda(self):
        provenance = self.core["input_provenance"]
        ebitda = provenance["current_ebitda"]
        self.assertEqual(ebitda["source"], "SEC_DERIVED")
        self.assertEqual(ebitda["basis"], "TTM")
        self.assertTrue(ebitda["used_by_engine"])
        self.assertEqual(len(ebitda["components"]), 4)
        for component in ebitda["components"]:
            self.assertIsNotNone(component["operating_income"])
            self.assertIsNotNone(component["depreciation_and_amortization"])
            self.assertAlmostEqual(
                component["value"],
                component["operating_income"]
                + component["depreciation_and_amortization"],
            )

    def test_the_windows_name_their_filings(self):
        for name in ("ttm_revenue_window", "ttm_ebitda_window"):
            entry = self.document["observed"][name]
            observation = entry[0] if isinstance(entry, list) else entry
            payload = observation["figure"]["value"]
            self.assertEqual(len(payload["samples"]), 4, name)
            quarters = payload["quarters"]
            self.assertEqual(len(quarters), 4, name)
            for quarter in quarters:
                self.assertTrue(quarter["formula"], name)
                self.assertTrue(quarter["knowable_from"], name)
                self.assertTrue(quarter["accessions"], name)


if __name__ == "__main__":
    unittest.main()
