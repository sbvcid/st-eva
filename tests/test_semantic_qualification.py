"""The registry's standing on an element, and what it decides.

The historical income and multiples datasets reconstruct trailing revenue and
trailing EBITDA out of filed SEC facts. A reconstruction can be arithmetically
perfect, point-in-time correct, contiguous and long enough, and still be
built on an element the registry does not accept as this metric for this
filer. Decision 2.99 retired `us-gaap:Revenues` as a source of `revenue`
because it is broader than the target metric, and nothing in the
reconstruction pipeline would have noticed: the retired element's filed
values are complete, knowable and contiguous, so they would have produced a
perfectly computable price-to-sales distribution and, with enough of them, a
production reference.

These tests pin the gate that notices, the three production issuers' standing
under it, and the negative case that matters most: an element the registry
does not accept produces no production reference however many complete
observations it carries.
"""
import copy
import json
import shutil
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from historical_income import (
    ISSUER_CONFIGS as INCOME_ISSUER_CONFIGS,
    REASON_NO_QUALIFIED_DA_EVIDENCE,
    REASON_NO_QUALIFIED_REVENUE_ELEMENT,
)
from historical_multiples import (
    ISSUER_CONFIGS as MULTIPLES_ISSUER_CONFIGS,
    METRIC_EV_EBITDA_RATIO,
    METRIC_PS_RATIO,
    load_issuer_historical_multiples,
)
from semantic_qualification import (
    REASON_MAPPING_TYPE,
    REASON_NO_MAPPING,
    REASON_NO_SUCH_METRIC,
    REASON_QUALIFIED,
    REASON_SCOPE,
    qualify_element,
    registry,
)
from st_eva_runner import production_ps_for_reference

TICKERS = ("AAPL", "MSFT", "AEP")


def _income_payload(ticker: str) -> dict:
    from historical_income import load_issuer_historical_income

    return load_issuer_historical_income(
        INCOME_ISSUER_CONFIGS[ticker]
    ).to_dict()


def _multiples_payload(ticker: str) -> dict:
    return load_issuer_historical_multiples(
        MULTIPLES_ISSUER_CONFIGS[ticker]
    ).to_dict()


class TheGate(unittest.TestCase):
    """What the registry says about an element, and why."""

    def test_the_accepted_revenue_element_is_qualified(self):
        qualification = qualify_element(
            metric_id="revenue",
            taxonomy="us-gaap",
            element="RevenueFromContractWithCustomerExcludingAssessedTax",
            ticker="AAPL",
        )
        self.assertTrue(qualification.qualified)
        self.assertEqual(qualification.reason_code, REASON_QUALIFIED)
        self.assertEqual(qualification.mapping_type, "EXACT")
        self.assertEqual(qualification.relation_kind, "IDENTITY")

    def test_a_retired_element_is_not_qualified_for_the_metric(self):
        # `us-gaap:Revenues` is the element decision 2.99 retired: the
        # registry holds it as a concept and maps it to nothing, so it is not
        # the revenue metric for any filer.
        qualification = qualify_element(
            metric_id="revenue",
            taxonomy="us-gaap",
            element="Revenues",
            ticker="AEP",
        )
        self.assertFalse(qualification.qualified)
        self.assertEqual(qualification.reason_code, REASON_NO_MAPPING)

    def test_an_element_the_registry_maps_only_partially_is_not_qualified(self):
        # `us-gaap:SalesRevenueNet` is a characterisation of how the filer
        # reported revenue, not a claim that the element is revenue.
        qualification = qualify_element(
            metric_id="revenue",
            taxonomy="us-gaap",
            element="SalesRevenueNet",
            ticker="AAPL",
        )
        self.assertFalse(qualification.qualified)
        self.assertEqual(qualification.reason_code, REASON_MAPPING_TYPE)

    def test_an_element_scoped_to_another_issuer_is_not_qualified(self):
        # The registry mapped this element to the depreciation-and-
        # amortization metric for AAPL alone, and to no other filer.
        qualification = qualify_element(
            metric_id="depreciation_and_amortization",
            taxonomy="us-gaap",
            element="DepreciationDepletionAndAmortization",
            ticker="MSFT",
        )
        self.assertFalse(qualification.qualified)
        self.assertEqual(qualification.reason_code, REASON_SCOPE)
        self.assertTrue(
            qualify_element(
                metric_id="depreciation_and_amortization",
                taxonomy="us-gaap",
                element="DepreciationDepletionAndAmortization",
                ticker="AAPL",
            ).qualified
        )

    def test_a_company_custom_element_is_not_qualified_by_being_filed(self):
        # The issuer reports it and the reconstruction holds it as evidence.
        # The registry has no mapping for it, so it is not the metric.
        qualification = qualify_element(
            metric_id="depreciation_and_amortization",
            taxonomy="msft",
            element="DepreciationAmortizationAndOther",
            ticker="MSFT",
        )
        self.assertFalse(qualification.qualified)
        self.assertEqual(qualification.reason_code, REASON_NO_MAPPING)

    def test_a_metric_the_registry_does_not_declare_is_not_a_refusal(self):
        # The registry has no standing to rule on a metric it does not model.
        # That is a different condition from a decision against the element,
        # and the filed-bridge specification governs the component instead.
        qualification = qualify_element(
            metric_id="marketable_securities_current",
            taxonomy="us-gaap",
            element="ShortTermInvestments",
            ticker="MSFT",
        )
        self.assertFalse(qualification.qualified)
        self.assertEqual(qualification.reason_code, REASON_NO_SUCH_METRIC)
        self.assertFalse(qualification.registry_metric_exists)

    def test_the_gate_agrees_with_the_registrys_own_resolver(self):
        # The gate must not hold a second opinion. For every mapping the
        # registry records, and for each production filer, the gate's answer
        # is the resolver's answer: the concept resolves to that metric, as an
        # exact claim, for that filer, or it does not.
        from core_registry import MAPPING_EXACT, ConceptResolution
        from registry_seed import MAPPINGS

        reg = registry()
        for mapping in MAPPINGS:
            taxonomy, _, element = mapping.concept_id.partition(":")
            for ticker in TICKERS:
                resolution = reg.resolve_source_concept(
                    mapping.concept_id, as_of=None, asset_id=ticker
                )
                expected = (
                    resolution.status == ConceptResolution.RESOLVED
                    and resolution.destination_metric == mapping.metric_id
                    and resolution.mapping_type == MAPPING_EXACT
                )
                qualification = qualify_element(
                    metric_id=mapping.metric_id,
                    taxonomy=taxonomy,
                    element=element,
                    ticker=ticker,
                )
                self.assertEqual(
                    qualification.qualified,
                    expected,
                    f"{mapping.concept_id} -> {mapping.metric_id} for {ticker}",
                )


class TheProductionIssuers(unittest.TestCase):
    """The three production issuers' standing under the gate."""

    def test_aapl_reads_elements_the_registry_accepts(self):
        roles = (
            _income_payload("AAPL")["semantic_qualification"]["roles"]
        )
        for name in ("revenue", "operating_income", "depreciation_and_amortization"):
            self.assertTrue(roles[name]["qualified"], name)
            self.assertEqual(roles[name]["reason_code"], REASON_QUALIFIED, name)

    def test_aapl_prices_and_enterprise_value_are_unchanged(self):
        payload = _multiples_payload("AAPL")
        sales = payload["distributions"][METRIC_PS_RATIO]
        enterprise = payload["distributions"][METRIC_EV_EBITDA_RATIO]
        self.assertEqual(sales["sample_count"], 28)
        self.assertEqual(sales["percentiles"]["median"], 7.257709)
        self.assertTrue(sales["usable_for_reference"])
        self.assertEqual(enterprise["sample_count"], 27)
        self.assertEqual(enterprise["percentiles"]["median"], 22.326)
        self.assertTrue(enterprise["usable_for_reference"])

    def test_msft_reads_an_accepted_revenue_element(self):
        roles = _income_payload("MSFT")["semantic_qualification"]["roles"]
        self.assertTrue(roles["revenue"]["qualified"])
        self.assertEqual(roles["revenue"]["reason_code"], REASON_QUALIFIED)

    def test_msft_has_no_qualified_depreciation_element_and_no_ebitda(self):
        payload = _income_payload("MSFT")
        roles = payload["semantic_qualification"]["roles"]
        self.assertFalse(roles["depreciation_and_amortization"]["qualified"])
        self.assertEqual(roles["depreciation_and_amortization"]["element"], "")
        # The element MSFT does report about depreciation is held as
        # evidence, and the registry's standing on it is recorded. It is not
        # a role and it contributes to no figure.
        evidence = roles["depreciation_evidence"]
        self.assertFalse(evidence["qualified"])
        self.assertEqual(evidence["reason_code"], REASON_NO_MAPPING)
        for observation in payload["observations"]:
            self.assertIsNone(observation["ttm_ebitda"])
            # The EBITDA refusal is stated in its own right, whatever the
            # revenue window did at that date.
            rejection = observation["window_rejection"]["ebitda"]
            self.assertEqual(
                rejection["reason_code"], REASON_NO_QUALIFIED_DA_EVIDENCE
            )

    def test_msft_prices_and_enterprise_value_are_unchanged(self):
        payload = _multiples_payload("MSFT")
        sales = payload["distributions"][METRIC_PS_RATIO]
        enterprise = payload["distributions"][METRIC_EV_EBITDA_RATIO]
        self.assertEqual(sales["sample_count"], 23)
        self.assertEqual(sales["percentiles"]["median"], 11.783822)
        self.assertTrue(sales["usable_for_reference"])
        self.assertEqual(enterprise["sample_count"], 0)
        self.assertEqual(enterprise["status"], "UNAVAILABLE")
        self.assertFalse(enterprise["usable_for_reference"])
        # The absence is a semantic refusal, not a shortage: no count of
        # quarters would produce the denominator the registry says does not
        # exist.
        self.assertEqual(enterprise["reason_code"], REASON_NO_QUALIFIED_DA_EVIDENCE)

    def test_aeps_retired_revenue_element_is_not_the_revenue_role(self):
        roles = _income_payload("AEP")["semantic_qualification"]["roles"]
        self.assertTrue(roles["revenue"]["qualified"])
        self.assertEqual(
            roles["revenue"]["concept_id"],
            "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        )
        # The element decision 2.99 retired is not the role, and would not
        # qualify if it were.
        self.assertFalse(
            qualify_element(
                metric_id="revenue",
                taxonomy="us-gaap",
                element="Revenues",
                ticker="AEP",
            ).qualified
        )

    def test_aeps_sales_distribution_is_judged_on_its_window_count(self):
        payload = _multiples_payload("AEP")
        sales = payload["distributions"][METRIC_PS_RATIO]
        self.assertEqual(sales["sample_count"], 4)
        self.assertEqual(sales["status"], "INSUFFICIENT_OBSERVATIONS")
        self.assertFalse(sales["usable_for_reference"])
        # The element is the registry's revenue element; the sample is what
        # the window produced, and four observations do not meet the
        # threshold.
        roles = payload["semantic_qualification"]["denominators"]
        self.assertTrue(roles["revenue"]["qualified"])

    def test_aeps_enterprise_value_is_unchanged(self):
        payload = _multiples_payload("AEP")
        enterprise = payload["distributions"][METRIC_EV_EBITDA_RATIO]
        self.assertEqual(enterprise["sample_count"], 24)
        self.assertEqual(enterprise["percentiles"]["median"], 13.221693)
        self.assertTrue(enterprise["usable_for_reference"])
        roles = payload["semantic_qualification"]["denominators"]["ebitda"]
        self.assertTrue(roles["qualified"])
        self.assertTrue(roles["roles"]["operating_income"]["qualified"])
        self.assertTrue(
            roles["roles"]["depreciation_and_amortization"]["qualified"]
        )

    def test_the_filed_bridge_components_the_registry_cannot_rule_on_are_named(self):
        # Two of the five filed bridge components have no registry metric.
        # The registry has no standing to rule on them, the filed-bridge
        # specification governs them, and the dataset says so rather than
        # inventing a metric.
        components = _multiples_payload("AAPL")["semantic_qualification"][
            "ev_bridge_components"
        ]
        self.assertTrue(components["cash"]["qualified"])
        self.assertTrue(components["long_term_debt_noncurrent"]["qualified"])
        self.assertTrue(components["long_term_debt_current"]["qualified"])
        for component in ("marketable_securities_current", "commercial_paper"):
            self.assertIsNone(components[component]["qualified"], component)
            self.assertFalse(
                components[component]["registry_metric_exists"], component
            )
            self.assertEqual(
                components[component]["reason_code"], REASON_NO_SUCH_METRIC
            )


class TheNegativeCase(unittest.TestCase):
    """An element the registry does not accept produces no reference."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.data_dir = Path(cls.tmp.name) / "AAPL"
        shutil.copytree(
            Path("data/historical_income/AAPL"), cls.data_dir
        )
        # The capture is AAPL's own: the same filed values, the same
        # filings, the same knowability. Only the element's identity changes,
        # to the one decision 2.99 retired. The file declares the element it
        # holds, so the fixture does not claim to be something it is not.
        revenue_path = cls.data_dir / "revenue_concept.json"
        payload = json.loads(revenue_path.read_text(encoding="utf-8"))
        payload["tag"] = "us-gaap:Revenues"
        payload["label"] = "Revenues"
        revenue_path.write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
        cls.income_config = replace(
            INCOME_ISSUER_CONFIGS["AAPL"],
            data_dir=cls.data_dir,
            revenue_concept="Revenues",
        )
        cls.multiples_config = replace(
            MULTIPLES_ISSUER_CONFIGS["AAPL"], income_config=cls.income_config
        )

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_capture_holds_more_than_twenty_complete_observations(self):
        # The control: the same capture under the element the registry
        # accepts produces more than the twenty observations a reference
        # needs. The data was never the problem.
        control = load_issuer_historical_multiples(
            MULTIPLES_ISSUER_CONFIGS["AAPL"]
        ).to_dict()
        sales = control["distributions"][METRIC_PS_RATIO]
        self.assertGreater(sales["sample_count"], 20)
        self.assertTrue(sales["usable_for_reference"])

    def test_the_retired_element_produces_no_revenue_window(self):
        payload = load_issuer_historical_multiples(
            self.multiples_config
        ).to_dict()
        for observation in payload["observations"]:
            self.assertIsNone(observation["ttm_revenue"])
            self.assertEqual(
                observation["ps_reason_code"], REASON_NO_QUALIFIED_REVENUE_ELEMENT
            )
        # The refusal names the registry's decision, not a shortage of
        # quarters, and it says which element and which metric.
        detail = payload["observations"][0]["ps_reason_detail"]
        self.assertIn("Revenues", detail)
        self.assertIn("revenue", detail)

    def test_the_sales_distribution_is_unavailable_for_the_semantic_reason(self):
        payload = load_issuer_historical_multiples(
            self.multiples_config
        ).to_dict()
        sales = payload["distributions"][METRIC_PS_RATIO]
        self.assertEqual(sales["status"], "UNAVAILABLE")
        self.assertFalse(sales["usable_for_reference"])
        self.assertEqual(sales["reason_code"], REASON_NO_QUALIFIED_REVENUE_ELEMENT)
        # Not a thin sample: the distribution says the denominator does not
        # exist rather than that there were too few observations of it.
        self.assertNotEqual(sales["sample_count"], 4)
        self.assertEqual(sales["sample_count"], 0)

    def test_the_reference_chain_refuses_the_rejected_distribution(self):
        payload = load_issuer_historical_multiples(
            self.multiples_config
        ).to_dict()
        median, status = production_ps_for_reference(payload)
        self.assertIsNone(median)
        self.assertEqual(status, "UNAVAILABLE")

    def test_the_enterprise_value_multiple_is_unaffected(self):
        # The rejection is the revenue role's alone. The enterprise-value
        # denominator is read from other elements, and it still qualifies:
        # the gate judges each role on its own element.
        payload = load_issuer_historical_multiples(
            self.multiples_config
        ).to_dict()
        enterprise = payload["distributions"][METRIC_EV_EBITDA_RATIO]
        self.assertEqual(enterprise["sample_count"], 27)
        self.assertTrue(enterprise["usable_for_reference"])


class TheArchiveKeepsTheBasis(unittest.TestCase):
    """The archive holds the standing, and the replay checks it."""

    @classmethod
    def setUpClass(cls):
        from sqlite_archive import SQLiteArchive
        from st_eva_runner import run_st_eva

        cls.tmp = tempfile.TemporaryDirectory()
        cls.archive_path = str(Path(cls.tmp.name) / "aapl.sqlite")
        cls.context_path = str(Path(cls.tmp.name) / "ctx.json")
        store = SQLiteArchive(cls.archive_path)
        try:
            run_st_eva(
                "AAPL",
                mode="regression",
                include_historical_multiples=True,
                save_snapshot=False,
                context_path=cls.context_path,
                archive=store,
            )
        finally:
            store.close()
        cls.document = json.loads(
            Path(cls.context_path).read_text(encoding="utf-8")
        )

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_archived_document_keeps_the_standing_under_which_it_was_built(self):
        from archive import production_reference_qualification_divergence

        refs = self.document["provenance"]["refs"]
        entry = refs["refc:ev_ebitda_reference"]
        basis = entry["eligibility_semantic_qualification"]
        self.assertTrue(basis)
        denominator = basis["denominator"]
        self.assertTrue(denominator["qualified"])
        self.assertEqual(
            denominator["roles"]["operating_income"]["concept_id"],
            "us-gaap:OperatingIncomeLoss",
        )
        self.assertTrue(
            denominator["roles"]["depreciation_and_amortization"]["qualified"]
        )
        # A document that keeps its own basis does not diverge from itself.
        self.assertEqual(
            production_reference_qualification_divergence(
                self.document, self.document
            ),
            [],
        )

    def test_a_changed_standing_is_reported_as_a_divergence(self):
        from archive import production_reference_qualification_divergence

        stored = copy.deepcopy(self.document)
        rebuilt = copy.deepcopy(self.document)
        stored["provenance"]["refs"]["refc:ev_ebitda_reference"][
            "eligibility_semantic_qualification"
        ]["denominator"]["roles"]["operating_income"]["qualified"] = False
        differences = production_reference_qualification_divergence(stored, rebuilt)
        self.assertEqual(len(differences), 1)
        self.assertEqual(differences[0]["reference"], "ev_ebitda_reference")
        self.assertEqual(differences[0]["source"], "multiples_ev_ebitda")

    def test_an_archive_without_a_basis_is_not_given_one(self):
        from archive import production_reference_qualification_divergence

        legacy = copy.deepcopy(self.document)
        legacy["provenance"]["refs"]["refc:ev_ebitda_reference"][
            "eligibility_semantic_qualification"
        ] = None
        # The side that does not record the basis does not know it, and the
        # other side's basis is not evidence against an unknown.
        self.assertEqual(
            production_reference_qualification_divergence(legacy, self.document), []
        )
        self.assertEqual(
            production_reference_qualification_divergence(self.document, legacy), []
        )

    def test_the_replay_reproduces_the_document(self):
        from archive import replay
        from sqlite_archive import SQLiteArchive
        from web.service_adapter import default_replay_doc_builder

        store = SQLiteArchive(self.archive_path)
        try:
            result = replay(store, "AAPL", "2026-12-31", default_replay_doc_builder)
        finally:
            store.close()
        self.assertEqual(result.outcome, "MATCH")
        basis = result.document["provenance"]["refs"][
            "refc:ev_ebitda_reference"
        ]["eligibility_semantic_qualification"]
        self.assertTrue(basis["denominator"]["qualified"])


if __name__ == "__main__":
    unittest.main()
