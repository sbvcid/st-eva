"""R2.1 regression tests: strict EPS source binding.

The defect these tests pin down: `_resolve_sec_eps_fact` attached SEC filing
metadata to a selected EPS anchor on the strength of numerical equality alone --
the first historical SEC EPS observation that carried an accession, or a recent
annual filing -- so a vendor-provided forward or consensus figure, or any value
that merely equalled a historical filing figure, displayed a 10-K as its direct
source. A source must describe where a value actually came from, not a document
concerning the same metric or company.

The corrected rule: a filing fact is named as the source of a selected EPS value
only when the acquisition data structures establish that the exact fact supplied
that value (observation identity, concept, unit, period, accession, form/filed),
with the value used only as a confirming check on the record identity already
identified. When that linkage does not exist, the direct SEC source stays absent
and the limitation is stated explicitly.

These tests fail against the defective resolution and pass against the corrected
one. They never touch the network and never touch a persistent database.
"""
from __future__ import annotations

import sys
import unittest

sys.path.insert(0, ".")

from data_contract import (
    AvailabilityBasis,
    CurrencyBasis,
    METRIC_TRAILING_EPS,
    ObservationSet,
    SourceType,
    Unit,
    build_observation,
)
from reverse_requirements import (
    ANCHOR_FORWARD,
    ANCHOR_TTM,
    ANCHOR_USER,
    EpsAnchor,
    FORMULA_VERSION,
    ReferenceMultiple,
    build_scenario_evidence,
    build_start_anchor,
)
from st_eva_runner import (
    REGRESSION_TEST_FIXTURES,
    CompanyResolver,
    UNAVAILABLE,
    _build_reverse_requirements,
    _resolve_sec_eps_fact,
    _sec_observation_supplying_anchor,
    run_st_eva,
)

SEC_ACCESSION = "0001564590-19-027952"


def _sec_filing_observation(
    value: float = 5.06,
    metric: str = METRIC_TRAILING_EPS,
    observation_id: str = "sec-trailing_eps-2018-07-01..2019-06-30-0001564590-19-027952",
) -> object:
    """An acquisition observation that carries a filing fact, as SEC ingest mints one."""
    return build_observation(
        metric=metric,
        value=value,
        unit=Unit.PER_SHARE.value,
        provider="SecEdgar",
        source_type=SourceType.REGULATORY_FILING.value,
        definition="Diluted earnings per share as reported in a filing",
        methodology=(
            f"SEC XBRL us-gaap:EarningsPerShareDiluted as reported in 10-K accession {SEC_ACCESSION}"
        ),
        retrieved_at="2026-10-11T00:00:00+00:00",
        currency="USD",
        currency_basis=CurrencyBasis.REPORTED.value,
        period_start="2018-07-01",
        period_end="2019-06-30",
        as_of="2019-06-30",
        available_at="2019-07-25",
        available_at_basis=AvailabilityBasis.FILED_AS_OF_DATE.value,
        source_url=(
            "https://data.sec.gov/api/xbrl/companyconcept/"
            "CIK0000787569/us-gaap/EarningsPerShareDiluted.json"
        ),
        observation_id=observation_id,
        raw={
            "sec_fact": {"taxonomy": "us-gaap", "tag": "EarningsPerShareDiluted"},
            "accession": SEC_ACCESSION,
            "form": "10-K",
            "filed": "2019-07-25",
            "reported_currency_unit": "USD/shares",
            "source_document": (
                "https://www.sec.gov/Archives/edgar/data/789019/000156459019027952/"
            ),
        },
    )


def _vendor_observation(
    value: float = 5.06,
    metric: str = METRIC_TRAILING_EPS,
    observation_id: str = "ev-trailing-eps-001",
) -> object:
    """The same number as reported by a vendor: a value match, never a source match."""
    return build_observation(
        metric=metric,
        value=value,
        unit=Unit.PER_SHARE.value,
        provider="YahooFinance",
        source_type=SourceType.API_LIVE.value,
        definition="Trailing earnings per share",
        methodology="Yahoo quoteSummary defaultKeyStatistics.trailingEps",
        retrieved_at="2026-10-11T00:00:00+00:00",
        currency="USD",
        currency_basis=CurrencyBasis.INSTRUMENT_DEFAULT.value,
        period_start="2018-07-01",
        period_end="2019-06-30",
        as_of="2019-06-30",
        observation_id=observation_id,
        raw={"trailingEps": value},
    )


def _reference_multiple() -> ReferenceMultiple:
    return ReferenceMultiple(
        value=25.0,
        source="historical_pe_band_median",
        sample_size=30,
        period_label="10-yr",
        is_user_assumption=False,
        eligibility_state="ELIGIBLE_HISTORICAL_BAND",
        usable_for_reference=True,
    )


def _reverse_package(
    current_eps,
    observations,
    sec_observations=None,
    prefer: str = "trailing",
) -> dict:
    """Run the reverse-requirements stage over one constructed acquisition."""
    data = CompanyResolver._from_fixture(REGRESSION_TEST_FIXTURES["MSFT"])
    data.current_eps = current_eps
    data.forward_eps = UNAVAILABLE
    data.consensus_forward_eps = UNAVAILABLE
    data.observations = ObservationSet(ticker="MSFT", observations=list(observations))
    analysis = {"observed_valuation": {}, "fundamental_snapshot": {}}
    return _build_reverse_requirements(
        data,
        analysis,
        horizons_years=(3.0,),
        required_returns=(0.10,),
        reference_multiple=25.0,
        reference_multiples=None,
        pfcf_multiple=None,
        ev_ebitda_multiple=None,
        ps_multiple=None,
        include_risk_free_rates=False,
        include_dcf=False,
        beta=None,
        equity_risk_premium=None,
        risk_free_tenor="10_YEAR",
        sec_observations=list(sec_observations or []),
        cross_validation=None,
        production_historical_pe=None,
        prefer_eps_anchor=prefer,
        user_eps=None,
    )


def _first_scenario(package: dict) -> dict:
    matrix = package["reverse_requirements_matrix"]
    assert matrix, "the package produced no scenario rows"
    return matrix[0]


class TestVendorAnchorDoesNotInheritSecFiling(unittest.TestCase):
    """A vendor value keeps its vendor identity; a filing is not its source."""

    def test_forward_vendor_eps_does_not_inherit_historical_sec_10k(self):
        # Defective behaviour returned the latest historical filing fact for the
        # ticker regardless of what the value was; the corrected resolver refuses.
        self.assertIsNone(
            _resolve_sec_eps_fact(13.20),
            "a vendor forward EPS must not inherit a historical SEC 10-K",
        )
        self.assertIsNone(
            _resolve_sec_eps_fact(17.95),
            "even the most recent annual figure is not the source of a vendor value",
        )

    def test_regression_forward_anchor_carries_no_sec_fact(self):
        # The fixture band declares no sample count, so a reference-free run
        # has no eligible exit multiple; the anchor-evidence assertions run on
        # a matrix computed from an explicitly supplied multiple.
        result = run_st_eva(
            "MSFT",
            mode="regression",
            reference_multiple=25.0,
            save_snapshot=False,
        )
        scenario = _first_scenario(result["reverse_requirements"])
        evidence = scenario["evidence"]
        self.assertIsNone(
            evidence["eps_evidence"]["sec_fact"],
            "the fixture forward EPS is vendor/fixture data, not an SEC filing",
        )
        self.assertFalse(evidence["eps_evidence"]["is_user_assumption"])
        # The value itself stays visible with its declared provider.
        self.assertEqual(evidence["eps_evidence"]["value"], 13.20)
        self.assertEqual(evidence["eps_evidence"]["provider"], "RegressionFixture")
        for item in evidence["sourced_facts"]:
            if "Starting EPS" in item:
                self.assertNotIn("SEC", item)

    def test_consensus_forward_eps_does_not_inherit_sec_filing_metadata(self):
        # A consensus figure equal to a historical filing figure (MSFT FY2024
        # diluted EPS is 11.80) still has no SEC source.
        self.assertIsNone(
            _resolve_sec_eps_fact(11.80),
            "a consensus value must not inherit SEC filing metadata",
        )
        result = run_st_eva(
            "MSFT",
            mode="regression",
            reference_multiple=25.0,
            save_snapshot=False,
            prefer_eps_anchor="consensus",
        )
        scenario = _first_scenario(result["reverse_requirements"])
        evidence = scenario["evidence"]
        self.assertIsNone(evidence["eps_evidence"]["sec_fact"])
        for item in evidence["sourced_facts"]:
            if "Starting EPS" in item:
                self.assertNotIn("accession", item)

    def test_value_equal_sec_observation_does_not_attach_without_linkage(self):
        # The run holds an SEC record with exactly the anchor's value, but the
        # engine's input did not come from it: availability is not provenance.
        observation = _sec_filing_observation()
        data = CompanyResolver._from_fixture(REGRESSION_TEST_FIXTURES["MSFT"])
        anchor, _ = build_start_anchor(
            trailing_eps=5.06,
            forward_eps=None,
            consensus_eps=None,
            currency="USD",
            provider="YahooFinance",
            prefer="trailing",
        )
        self.assertIsNone(_sec_observation_supplying_anchor(data, anchor, [observation]))
        self.assertIsNone(
            _resolve_sec_eps_fact(5.06, source_observation=None),
            "an unlinked SEC record is never the source of a value",
        )


class TestFilingFactRequiresExactLinkage(unittest.TestCase):
    """The filing fact may be named only when the exact fact supplied the value."""

    def test_sec_derived_anchor_receives_its_filing_reference(self):
        observation = _sec_filing_observation()
        fact = _resolve_sec_eps_fact(5.06, source_observation=observation)
        self.assertIsNotNone(fact)
        self.assertEqual(fact["accession"], SEC_ACCESSION)
        self.assertEqual(fact["form"], "10-K")
        self.assertEqual(fact["filed_date"], "2019-07-25")
        self.assertEqual(fact["concept"], "us-gaap:EarningsPerShareDiluted")
        self.assertEqual(fact["unit"], "USD/shares")
        self.assertEqual(fact["period_start"], "2018-07-01")
        self.assertEqual(fact["period_end"], "2019-06-30")
        self.assertEqual(
            fact["document_url"],
            "https://www.sec.gov/Archives/edgar/data/789019/000156459019027952/"
            "0001564590-19-027952-index.htm",
        )

    def test_vendor_observation_with_same_value_is_not_the_filing(self):
        vendor = _vendor_observation()
        self.assertIsNone(
            _resolve_sec_eps_fact(5.06, source_observation=vendor),
            "a vendor observation with the same value is not a filing source",
        )

    def test_linked_record_must_carry_the_selected_value(self):
        observation = _sec_filing_observation()
        self.assertIsNone(
            _resolve_sec_eps_fact(99.99, source_observation=observation),
            "the identified record does not carry the selected value",
        )

    def test_linked_record_must_name_the_diluted_eps_concept(self):
        other_concept = build_observation(
            metric="revenue",
            value=5.06,
            unit=Unit.PER_SHARE.value,
            provider="SecEdgar",
            source_type=SourceType.REGULATORY_FILING.value,
            definition="Revenue as reported",
            methodology="SEC XBRL us-gaap:Revenues",
            retrieved_at="2026-10-11T00:00:00+00:00",
            currency="USD",
            observation_id="sec-revenue-x",
            raw={
                "sec_fact": {"taxonomy": "us-gaap", "tag": "Revenues"},
                "accession": SEC_ACCESSION,
                "form": "10-K",
                "filed": "2019-07-25",
                "reported_currency_unit": "USD/shares",
            },
        )
        self.assertIsNone(
            _resolve_sec_eps_fact(5.06, source_observation=other_concept),
            "a filing figure of another concept is a different fact",
        )

    def test_matrix_names_the_filing_only_for_the_linked_anchor(self):
        observation = _sec_filing_observation()
        package = _reverse_package(5.06, [observation], [observation])
        evidence = _first_scenario(package)["evidence"]
        fact = evidence["eps_evidence"]["sec_fact"]
        self.assertIsNotNone(fact)
        self.assertEqual(fact["accession"], SEC_ACCESSION)
        self.assertNotIn(
            "Direct SEC source of selected EPS not established",
            evidence["missing_or_unvalidated"],
        )
        sec_notes = [item for item in evidence["sourced_facts"] if "Starting EPS" in item]
        self.assertTrue(sec_notes)
        self.assertIn(f"SEC 10-K accession {SEC_ACCESSION}", sec_notes[0])

    def test_matrix_leaves_sec_source_absent_when_input_came_from_vendor(self):
        # The run acquired the filing fact, and the vendor holds the same value,
        # but the engine read the vendor figure: no SEC source may be named.
        sec_acquisition = _sec_filing_observation(metric="eps_diluted")
        vendor = _vendor_observation()
        package = _reverse_package(5.06, [vendor], [sec_acquisition])
        evidence = _first_scenario(package)["evidence"]
        self.assertIsNone(evidence["eps_evidence"]["sec_fact"])
        for item in evidence["sourced_facts"]:
            if "Starting EPS" in item:
                self.assertNotIn("accession", item)
        self.assertTrue(
            any(
                "Direct SEC source of selected EPS not established" in item
                for item in evidence["missing_or_unvalidated"]
            ),
            evidence["missing_or_unvalidated"],
        )

    def test_user_supplied_eps_gets_no_sec_attribution(self):
        # The value the run acquired from SEC is available, yet a user-supplied
        # EPS is still the user's, and no filing fact may be named for it.
        sec_acquisition = _sec_filing_observation()
        data = CompanyResolver._from_fixture(REGRESSION_TEST_FIXTURES["MSFT"])
        user_anchor = EpsAnchor(
            value=7.42,
            basis=ANCHOR_USER,
            months_covered=12.0,
            provider="user",
            source_type="USER_SUPPLIED",
            is_user_assumption=True,
            sec_fact=None,
            sec_related_evidence=None,
        )
        self.assertIsNone(
            _sec_observation_supplying_anchor(data, user_anchor, [sec_acquisition])
        )
        # The runner never links a user anchor to any observation, and the
        # anchor declares itself user-supplied with no filing attribution.
        self.assertIsNone(getattr(user_anchor, "sec_fact", None))
        evidence = build_scenario_evidence(
            price=150.0,
            currency="USD",
            as_of="2026-10-11",
            price_evidence={},
            start_anchor=user_anchor,
            exit_multiple=_reference_multiple(),
            horizon_years=3.0,
            required_return=0.10,
            required_return_basis="market",
        )
        self.assertTrue(evidence["eps_evidence"]["is_user_assumption"])
        self.assertIsNone(evidence["eps_evidence"]["sec_fact"])
        self.assertIsNone(evidence["related_sec_evidence"])
        self.assertTrue(
            any("user-supplied" in item for item in evidence["user_assumptions"])
        )
        for item in evidence["sourced_facts"]:
            if "Starting EPS" in item:
                self.assertNotIn("SEC", item)

    def test_user_supplied_run_carries_no_sec_source(self):
        result = run_st_eva(
            "MSFT",
            mode="regression",
            save_snapshot=False,
            user_eps=25.0,
            reference_multiple=27.5,
        )
        scenarios = [
            row
            for row in result["reverse_requirements"]["reverse_requirements_matrix"]
            if row["exit_multiple"]["value"] == 27.5
        ]
        self.assertTrue(scenarios)
        evidence = scenarios[0]["evidence"]
        self.assertTrue(evidence["eps_evidence"]["is_user_assumption"])
        self.assertEqual(evidence["eps_evidence"]["source_type"], "USER_SUPPLIED")
        self.assertIsNone(evidence["eps_evidence"]["sec_fact"])


class TestUnresolvedProvenanceIsExplicit(unittest.TestCase):
    """The limitation is stated without hiding the value or inventing a source."""

    def test_limitation_is_stated_and_value_is_kept(self):
        from st_eva_runner import _find_related_sec_evidence

        anchor = EpsAnchor(
            value=13.20,
            basis=ANCHOR_FORWARD,
            months_covered=12.0,
            provider="RegressionFixture",
            source_type="REGRESSION_FIXTURE",
            is_user_assumption=False,
            sec_fact=None,
            sec_related_evidence=_find_related_sec_evidence("MSFT"),
        )
        evidence = build_scenario_evidence(
            price=425.50,
            currency="USD",
            as_of="2026-09-18",
            price_evidence={},
            start_anchor=anchor,
            exit_multiple=_reference_multiple(),
            horizon_years=3.0,
            required_return=0.10,
            required_return_basis="PRICE_RETURN_ONLY",
        )
        # The value is still shown, from its declared provider.
        self.assertEqual(evidence["eps_evidence"]["value"], 13.20)
        self.assertIsNone(evidence["eps_evidence"]["sec_fact"])
        # The limitation names the unverified provenance explicitly.
        self.assertTrue(
            any(
                "Direct SEC source of selected EPS not established" in item
                for item in evidence["missing_or_unvalidated"]
            )
        )
        # Related evidence is present and labelled as cross-check, never as source.
        related = evidence["related_sec_evidence"]
        self.assertIsNotNone(related)
        self.assertTrue(related.get("accession"))
        self.assertIn("cross-check", related.get("note", ""))
        for item in evidence["sourced_facts"]:
            if "Starting EPS" in item:
                self.assertNotIn("accession", item)

    def test_api_contract_keeps_related_evidence_apart_from_direct_source(self):
        from web.schemas import RelatedSecEvidenceDTO, ScenarioEvidenceDTO

        package = _reverse_package(
            5.06,
            [_vendor_observation()],
            [_sec_filing_observation(metric="eps_diluted")],
        )
        evidence = ScenarioEvidenceDTO.model_validate(
            _first_scenario(package)["evidence"]
        )
        self.assertIsNone(evidence.eps_evidence.sec_fact)
        self.assertIsNotNone(evidence.related_sec_evidence)
        self.assertIsInstance(evidence.related_sec_evidence, RelatedSecEvidenceDTO)
        self.assertTrue(
            any(
                "Direct SEC source of selected EPS not established" in item
                for item in evidence.missing_or_unvalidated
            )
        )

    def test_ticker_without_filing_data_reports_absent_provenance(self):
        evidence = build_scenario_evidence(
            price=150.0,
            currency="USD",
            as_of="2026-10-11",
            price_evidence={},
            start_anchor=EpsAnchor(
                value=5.55,
                basis=ANCHOR_FORWARD,
                months_covered=12.0,
                provider="refinitiv",
                source_type="OBSERVED",
                is_user_assumption=False,
                sec_fact=None,
                sec_related_evidence=None,
            ),
            exit_multiple=_reference_multiple(),
            horizon_years=3.0,
            required_return=0.10,
            required_return_basis="PRICE_RETURN_ONLY",
        )
        self.assertIsNone(evidence["related_sec_evidence"])
        self.assertEqual(evidence["eps_evidence"]["value"], 5.55)
        self.assertTrue(
            any(
                "Direct SEC source of selected EPS not established" in item
                for item in evidence["missing_or_unvalidated"]
            )
        )


class TestCalculationContractRemainsIntact(unittest.TestCase):
    """R2's deterministic traces and DTO error behaviour are unchanged."""

    def test_formula_version_and_fingerprint_are_unchanged(self):
        first = run_st_eva("MSFT", mode="regression", save_snapshot=False)
        second = run_st_eva("MSFT", mode="regression", save_snapshot=False)
        for result in (first, second):
            package = result["reverse_requirements"]
            self.assertEqual(package["formula_version"], FORMULA_VERSION)
            self.assertEqual(len(package["fingerprint"]), 64)
        self.assertEqual(
            first["reverse_requirements"]["fingerprint"],
            second["reverse_requirements"]["fingerprint"],
        )

    def test_calculation_steps_reproduce_within_tolerance(self):
        result = run_st_eva(
            "MSFT",
            mode="regression",
            save_snapshot=False,
            reverse_horizons=(2.0, 3.0),
            required_returns=(0.10, 0.12),
            reference_multiple=25.0,
        )
        for scenario in result["reverse_requirements"]["reverse_requirements_matrix"]:
            steps = scenario["calculation_steps"]
            self.assertEqual(len(steps), 4)
            for step in steps:
                self.assertTrue(step["reproducible"])

    def test_eps_anchor_contract_is_enforced(self):
        anchor = EpsAnchor(
            value=3.5, basis=ANCHOR_TTM, months_covered=12.0, provider="test"
        )
        self.assertEqual(anchor.value, 3.5)
        self.assertIn("sec_related_evidence", anchor.contract_view())
        with self.assertRaises(Exception):
            EpsAnchor(
                value=float("nan"),
                basis=ANCHOR_TTM,
                months_covered=12.0,
                provider="test",
            )
        with self.assertRaises(Exception):
            EpsAnchor(
                value=3.5, basis=ANCHOR_TTM, months_covered=0.0, provider="test"
            )

    def test_build_start_anchor_preference_order_is_unchanged(self):
        anchor, _ = build_start_anchor(
            trailing_eps=2.0,
            forward_eps=2.5,
            consensus_eps=3.0,
            currency="USD",
            prefer="trailing",
        )
        self.assertEqual(anchor.basis, ANCHOR_TTM)
        anchor_f, _ = build_start_anchor(
            trailing_eps=2.0,
            forward_eps=2.5,
            consensus_eps=3.0,
            currency="USD",
            prefer="forward",
        )
        self.assertEqual(anchor_f.basis, ANCHOR_FORWARD)

    def test_dto_validation_still_fails_loudly(self):
        from pydantic import ValidationError

        from web.schemas import RelatedSecEvidenceDTO, ScenarioEvidenceDTO
        from web.schemas import ReverseRequirementsReportDTO

        # A value that cannot satisfy the declared type still fails loudly.
        with self.assertRaises(ValidationError):
            ReverseRequirementsReportDTO.model_validate(
                {
                    "formula_version": "reverse-requirements/1.1",
                    "matrix_size": "INVALID_NOT_AN_INT",
                }
            )
        # The contract still accepts related evidence kept apart from the
        # (absent) direct source.
        evidence = ScenarioEvidenceDTO.model_validate(
            {
                "price_evidence": {
                    "value": 100.0,
                    "currency": "USD",
                    "provider": "RegressionFixture",
                    "source_type": "REGRESSION_FIXTURE",
                    "observation_id": "ev-price-001",
                    "is_user_assumption": False,
                },
                "eps_evidence": {
                    "value": 4.0,
                    "basis": "TRAILING_TWELVE_MONTHS",
                    "months_covered": 12.0,
                    "period_label": "FY2026",
                    "provider": "RegressionFixture",
                    "currency": "USD",
                    "period_undeclared_by_source": False,
                    "source_type": "REGRESSION_FIXTURE",
                    "observation_id": "ev-current-eps-001",
                    "is_user_assumption": False,
                    "sec_fact": None,
                },
                "multiple_evidence": {
                    "value": 25.0,
                    "source": "user_supplied",
                    "is_user_assumption": True,
                    "eligibility_state": "USER_SPECIFIED",
                    "usable_for_reference": False,
                },
                "user_assumptions": [
                    "Holding Horizon: 3 years",
                    "Required Return Hurdle: 10% (PRICE_RETURN_ONLY)",
                ],
                "sourced_facts": ["Starting EPS: 4 USD (TRAILING_TWELVE_MONTHS, provider: RegressionFixture)"],
                "missing_or_unvalidated": ["Direct SEC source of selected EPS not established"],
                "related_sec_evidence": {
                    "accession": "0001193125-26-323660",
                    "form": "10-K",
                    "filed_date": "2026-07-30",
                    "concept": "us-gaap:EarningsPerShareDiluted",
                    "unit": "USD/shares",
                    "period_start": "2025-07-01",
                    "period_end": "2026-06-30",
                    "document_url": None,
                    "note": "Related SEC filing (cross-check); not verified as direct source of selected EPS value",
                },
            }
        )
        self.assertIsNone(evidence.eps_evidence.sec_fact)
        self.assertIsInstance(evidence.related_sec_evidence, RelatedSecEvidenceDTO)
        self.assertIn("cross-check", evidence.related_sec_evidence.note)


if __name__ == "__main__":
    unittest.main(verbosity=2)
