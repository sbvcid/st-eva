"""AAPL starting-EPS provenance closure tests.

The live AAPL analysis starts its growth bridge from a vendor-sourced trailing
EPS (8.72), not from a SEC filing fact. These tests pin how that value's actual
source -- the provider field and endpoint the acquisition observation recorded --
is carried into the scenario evidence, and that the missing direct SEC link and
the undeclared source period stay stated rather than being papered over.

Nothing here is inferred from a value's magnitude or from the existence of a
related filing: the provenance is read from the observation that produced the
value.
"""

import unittest

from data_contract import (
    UNIT_PER_SHARE,
    AvailabilityBasis,
    METRIC_TRAILING_EPS,
    Observation,
    SourceType,
)
from reverse_requirements import (
    ANCHOR_TTM,
    EpsAnchor,
    ReferenceMultiple,
    build_reverse_requirements_report,
    build_scenario_evidence,
)
from st_eva_runner import _vendor_source_reference


AAPL_QUOTE_SUMMARY_URL = "https://query2.finance.yahoo.com/v10/finance/quoteSummary/AAPL"
# The market-data provider the engine puts on the anchor composes the price
# provider and the fundamentals provider; it is NOT the EPS figure's own source.
MARKET_DATA_PROVIDER = "YahooFinance+YahooFinanceFundamentals"
# The provider of the trailing-EPS observation itself.
EPS_OBSERVATION_PROVIDER = "YahooFinanceFundamentals"


def _vendor_trailing_eps_observation(value=8.72):
    """The observation the live AAPL run actually produced for trailing EPS."""
    return Observation(
        observation_id="ev-current-eps-001",
        metric=METRIC_TRAILING_EPS,
        value=value,
        unit=UNIT_PER_SHARE,
        currency="USD",
        currency_basis="PER_SHARE",
        period_start=None,
        period_end=None,
        as_of=None,
        available_at=None,
        available_at_basis=AvailabilityBasis.UNDECLARED.value,
        provider="YahooFinanceFundamentals",
        source_type=SourceType.API_LIVE.value,
        source_url=AAPL_QUOTE_SUMMARY_URL,
        definition="Current/trailing EPS. Never synthesized.",
        methodology="Yahoo quoteSummary defaultKeyStatistics.trailingEps",
        retrieved_at="2026-10-13T00:00:00+00:00",
        raw={"module": "defaultKeyStatistics", "field": "trailingEps", "asOfDate": None},
    )


def _provider_anchor():
    return EpsAnchor(
        value=8.72,
        basis=ANCHOR_TTM,
        months_covered=12.0,
        period_label="trailing twelve months (assumed; source stated no period)",
        provider=MARKET_DATA_PROVIDER,
        currency="USD",
        period_undeclared_by_source=True,
        source_type=SourceType.API_LIVE.value,
        observation_id="ev-current-eps-001",
        sec_fact=None,
        sec_related_evidence={
            "accession": "0000320193-25-000079",
            "form": "10-K",
            "note": "Related SEC filing (cross-check); not verified as direct source of selected EPS value",
        },
        source_field="defaultKeyStatistics.trailingEps",
        source_url=AAPL_QUOTE_SUMMARY_URL,
        source_provider=EPS_OBSERVATION_PROVIDER,
    )


class TestVendorSourceReference(unittest.TestCase):
    def test_reads_the_provider_field_and_endpoint_from_the_observation(self):
        self.assertEqual(
            _vendor_source_reference(_vendor_trailing_eps_observation()),
            ("defaultKeyStatistics.trailingEps", AAPL_QUOTE_SUMMARY_URL),
        )

    def test_no_observation_yields_nothing(self):
        self.assertEqual(_vendor_source_reference(None), (None, None))

    def test_an_observation_without_provenance_yields_nothing(self):
        observation = _vendor_trailing_eps_observation()
        empty = Observation(
            **{
                **{f: getattr(observation, f) for f in observation.__dataclass_fields__},
                "source_url": None,
                "raw": {},
            }
        )
        self.assertEqual(_vendor_source_reference(empty), (None, None))


class TestScenarioEvidenceCarriesVendorProvenance(unittest.TestCase):
    def _evidence(self, anchor):
        return build_scenario_evidence(
            price=342.22,
            currency="USD",
            as_of="2026-10-13",
            price_evidence={"value": 342.22, "provider": "YahooFinance+YahooFinanceFundamentals",
                            "source_type": "API_LIVE", "as_of": "2026-10-13"},
            start_anchor=anchor,
            exit_multiple=ReferenceMultiple(value=20.0, source="user_supplied"),
            horizon_years=1.0,
            required_return=0.10,
            required_return_basis="PRICE_RETURN_ONLY",
        )

    def test_provider_sourced_eps_names_its_field_and_endpoint(self):
        ev = self._evidence(_provider_anchor())
        joined = " | ".join(ev["sourced_facts"])
        self.assertIn("defaultKeyStatistics.trailingEps", joined)
        self.assertIn(AAPL_QUOTE_SUMMARY_URL, joined)
        self.assertIn("source declared no period date", joined)
        self.assertIn("YahooFinanceFundamentals", joined)

    def test_eps_provider_is_the_observation_provider_not_the_market_composite(self):
        """The EPS figure's direct source is its own observation's provider.

        The anchor's market-data provider composes the price and fundamentals
        providers; it must not be shown as the EPS source.
        """
        ev = self._evidence(_provider_anchor())
        eps_facts = [f for f in ev["sourced_facts"] if f.startswith("Starting EPS")]
        self.assertTrue(eps_facts)
        for fact in eps_facts:
            self.assertIn(EPS_OBSERVATION_PROVIDER, fact)
            self.assertNotIn(MARKET_DATA_PROVIDER, fact)
        # The baseline line labels and names the EPS provider explicitly.
        self.assertTrue(any(
            fact.startswith("Starting EPS:") and f"EPS provider: {EPS_OBSERVATION_PROVIDER}" in fact
            for fact in eps_facts
        ))

    def test_eps_provider_falls_back_to_the_anchor_when_the_observation_has_none(self):
        anchor = _provider_anchor()
        anchor = EpsAnchor(**{
            **anchor.contract_view(),
            "source_field": "defaultKeyStatistics.trailingEps",
            "source_url": AAPL_QUOTE_SUMMARY_URL,
            "source_provider": None,
        })
        ev = self._evidence(anchor)
        # No observation provider: the anchor's provider stands, unchanged label.
        self.assertTrue(any(
            f"provider: {MARKET_DATA_PROVIDER}" in fact for fact in ev["sourced_facts"]
        ))

    def test_the_direct_sec_absence_and_undeclared_period_are_retained(self):
        ev = self._evidence(_provider_anchor())
        self.assertIn("Starting EPS period coverage was not declared by source", ev["missing_or_unvalidated"])
        self.assertTrue(any(
            "Direct SEC source of selected EPS not established" in item
            for item in ev["missing_or_unvalidated"]
        ))
        # The related filing is still presented as cross-check only, not as source.
        self.assertIsNotNone(ev["related_sec_evidence"])
        self.assertIsNone(ev["eps_evidence"]["sec_fact"])

    def test_the_eps_evidence_contract_keys_are_unchanged(self):
        ev = self._evidence(_provider_anchor())
        self.assertEqual(
            set(ev["eps_evidence"].keys()),
            {
                "value", "basis", "months_covered", "period_label", "period_start",
                "period_end", "provider", "currency", "period_undeclared_by_source",
                "source_type", "observation_id", "is_user_assumption",
                "sec_fact", "sec_related_evidence",
            },
        )

    def test_a_sec_linked_anchor_is_not_relabelled_as_provider_sourced(self):
        linked = EpsAnchor(
            value=8.72, basis=ANCHOR_TTM, months_covered=12.0,
            provider="SecEdgar", currency="USD",
            source_type="REGULATORY_FILING", observation_id="ev-sec-eps-001",
            sec_fact={"accession": "0000320193-25-000079", "form": "10-K", "period_end": "2025-09-27"},
            source_field="defaultKeyStatistics.trailingEps",
            source_url=AAPL_QUOTE_SUMMARY_URL,
            source_provider="SecEdgar",
        )
        ev = self._evidence(linked)
        self.assertFalse(any(f.startswith("Starting EPS source:") for f in ev["sourced_facts"]))
        self.assertTrue(any("accession 0000320193-25-000079" in f for f in ev["sourced_facts"]))
        self.assertTrue(any("EPS provider: SecEdgar" in f for f in ev["sourced_facts"]))


class TestVendorProvenanceIsNotPartOfTheMatrixContract(unittest.TestCase):
    def _report(self, field, url, provider=None):
        anchor = _provider_anchor()
        anchor = EpsAnchor(**{
            **anchor.contract_view(),
            "source_field": field,
            "source_url": url,
            "source_provider": provider,
        })
        return build_reverse_requirements_report(
            price=342.22, ticker="AAPL", currency="USD", as_of="2026-10-13",
            price_source="fixture",
            horizons_years=[1.0], required_returns=[0.10],
            exit_multiples=[ReferenceMultiple(value=20.0, source="user_supplied")],
            start_anchor=anchor,
        )

    def test_provenance_does_not_change_the_fingerprint_or_start_eps_block(self):
        with_prov = self._report("defaultKeyStatistics.trailingEps", AAPL_QUOTE_SUMMARY_URL, EPS_OBSERVATION_PROVIDER)
        without = self._report(None, None, None)
        self.assertEqual(with_prov["fingerprint"], without["fingerprint"])
        self.assertEqual(
            with_prov["reverse_requirements_matrix"][0]["start_eps"],
            without["reverse_requirements_matrix"][0]["start_eps"],
        )

    def test_the_matrix_row_evidence_carries_the_provenance(self):
        report = self._report("defaultKeyStatistics.trailingEps", AAPL_QUOTE_SUMMARY_URL)
        row = report["reverse_requirements_matrix"][0]
        joined = " | ".join(row["evidence"]["sourced_facts"])
        self.assertIn("defaultKeyStatistics.trailingEps", joined)
        self.assertIn(AAPL_QUOTE_SUMMARY_URL, joined)


if __name__ == "__main__":
    unittest.main()
