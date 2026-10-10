"""
Tests for the audit corrections.

Two results were already being computed and then dropped:

- the cross-source verdicts, which the filing pass produces on the financial
  history path and which nothing carried into the result;
- the implied net margin's counterpart, the margin the filings actually report,
  which sat in another section as an unrelated series.

Both are pinned here so they cannot silently disappear again.
"""
from __future__ import annotations

import sys
import unittest

sys.path.insert(0, ".")

from cross_validation import ComparabilitySpec, Tolerance, spec_for
from research_dossier import build_dossier, render_dossier
from reverse_requirements import (
    EpsAnchor,
    ANCHOR_TTM,
    ReferenceMultiple,
    build_reverse_requirements_report,
    valuation_method_scenarios,
)
from st_eva_runner import _serialise_cross_validation, run_st_eva


def _anchor(value: float = 4.0) -> EpsAnchor:
    return EpsAnchor(
        value=value, basis=ANCHOR_TTM, months_covered=12.0,
        period_label="TTM to 2026-09-30", provider="fixture", currency="USD",
    )


class TestCrossSourceVerdictSerialisation(unittest.TestCase):
    def test_absent_verdicts_are_reported_as_not_performed(self):
        block = _serialise_cross_validation(None)
        self.assertFalse(block["performed"])
        self.assertIn("No second source", block["reason"])

    def test_empty_verdicts_are_not_performed(self):
        self.assertFalse(_serialise_cross_validation({})["performed"])

    def test_a_verdict_is_flattened_with_its_ids_and_values(self):
        class _Record:
            def contract_dict(self):
                return {
                    "status": "CONSISTENT",
                    "reasons": ["both sides aligned"],
                    "checked_at": "",
                    "comparison_basis": {
                        "vendor_observation": "v1",
                        "filing_observation": "f1",
                        "vendor_value": 100.0,
                        "filing_value": 100.0,
                        "period_offset_days": 3,
                        "independence": "UNVERIFIED_INDEPENDENCE",
                    },
                    "explanation": "agrees",
                    "references": ["v1", "f1"],
                }

        class _Verdict:
            validation = _Record()
            status = "CONSISTENT"

        block = _serialise_cross_validation({"revenue": _Verdict()})
        self.assertTrue(block["performed"])
        verdict = block["verdicts"]["revenue"]
        self.assertEqual(verdict["status"], "CONSISTENT")
        self.assertEqual(verdict["vendor_observation"], "v1")
        self.assertEqual(verdict["filing_value"], 100.0)
        self.assertEqual(block["counts"], {"CONSISTENT": 1})
        self.assertIn("1 of 1", block["summary"])

    def test_a_metric_without_a_contract_dict_still_reports_a_status(self):
        class _Verdict:
            validation = None
            status = "UNAVAILABLE"

        block = _serialise_cross_validation({"assets": _Verdict()})
        self.assertEqual(block["verdicts"]["assets"]["status"], "UNAVAILABLE")


class TestComparabilitySpecCaveatsAreTuples(unittest.TestCase):
    """
    A bare string in `known_caveats` iterates into single characters.

    That produced an 841-element list of one-letter caveats in the cross-source
    output for long-term debt, which is unreadable and wrong.
    """

    def test_every_spec_declares_its_caveats_as_a_sequence_of_strings(self):
        for metric in (
            "revenue", "net_income", "eps_diluted",
            "assets", "cash", "long_term_debt", "shares_outstanding",
        ):
            spec = spec_for(metric)
            self.assertIsNotNone(spec, metric)
            caveats = spec.known_caveats
            self.assertNotIsInstance(
                caveats, str,
                "%s declares its caveats as a bare string, so list() splits it into "
                "single characters" % metric,
            )
            self.assertGreater(len(list(caveats)), 0, metric)
            for caveat in caveats:
                self.assertGreater(len(caveat), 1, metric)

    def test_the_debt_caveat_is_one_readable_sentence(self):
        caveats = list(spec_for("long_term_debt").known_caveats)
        self.assertEqual(len(caveats), 1)
        self.assertTrue(caveats[0].startswith("Long-term debt"))


class TestImpliedNetMarginIsCompared(unittest.TestCase):
    def _methods(self, **overrides):
        base = dict(
            price=100.0, shares=10.0, market_cap=1000.0, enterprise_value=1200.0,
            free_cash_flow=50.0, ebitda=100.0, revenue=400.0, trailing_eps=4.0,
            multiples={
                "pe": ReferenceMultiple(value=20.0, source="user"),
                "revenue": ReferenceMultiple(value=2.5, source="user"),
            },
        )
        base.update(overrides)
        return valuation_method_scenarios(**base)["methods"]

    def test_implied_margin_is_set_beside_the_observed_one(self):
        margin = self._methods(
            observed_net_margin=0.25, observed_net_margin_period="2026-06-27"
        )["implied_net_margin"]
        self.assertEqual(margin["status"], "COMPUTED")
        self.assertAlmostEqual(margin["implied"], 0.125, places=12)
        self.assertAlmostEqual(margin["observed"], 0.25, places=12)
        self.assertAlmostEqual(margin["gap_implied_vs_observed"], -0.125, places=12)
        self.assertEqual(margin["observed_margin_period"], "2026-06-27")

    def test_without_an_observed_margin_the_field_stays_empty(self):
        margin = self._methods()["implied_net_margin"]
        self.assertIsNone(margin["observed"])
        self.assertIsNone(margin["gap_implied_vs_observed"])

    def test_a_zero_observed_margin_still_yields_a_meaningful_gap(self):
        # Unlike a level gap, which divides by the observed figure, a margin
        # gap is a plain difference of two ratios. Differencing against zero is
        # well defined and is what a reader expects here.
        margin = self._methods(observed_net_margin=0.0)["implied_net_margin"]
        self.assertAlmostEqual(margin["gap_implied_vs_observed"], 0.125, places=12)

    def test_the_report_carries_the_observed_margin_through(self):
        report = build_reverse_requirements_report(
            price=100.0, ticker="T", currency="USD", as_of="2026-09-30",
            price_source="f", horizons_years=[1.0], required_returns=[0.10],
            exit_multiples=[ReferenceMultiple(value=20.0, source="user")],
            start_anchor=_anchor(), market_cap=1000.0, revenue=400.0,
            valuation_multiples={
                "pe": ReferenceMultiple(value=20.0, source="user"),
                "revenue": ReferenceMultiple(value=2.5, source="user"),
            },
            observed_net_margin=0.25,
            observed_net_margin_period="2026-06-27",
        )
        margin = report["valuation_methods"]["methods"]["implied_net_margin"]
        self.assertEqual(margin["observed"], 0.25)
        self.assertEqual(margin["gap_implied_vs_observed"], -0.125)


class TestDossierShowsCrossSourceAndMarginContext(unittest.TestCase):
    def test_dossier_renders_a_cross_source_section(self):
        result = run_st_eva(
            "MSFT", mode="regression", save_snapshot=False, render_dossier_report=True
        )
        text = result["dossier_report_text"]
        self.assertIn("跨來源比對", text)

    def test_dossier_states_when_no_second_source_was_consulted(self):
        result = run_st_eva(
            "MSFT", mode="regression", save_snapshot=False, render_dossier_report=True
        )
        block = result["research_dossier"]["sections"]["market_and_company"][
            "cross_source_validation"
        ]
        # The regression path consults no second source, so the block must say
        # so rather than implying verification happened.
        self.assertIn("performed", block)

    def test_dossier_carries_the_net_margin_context_block(self):
        result = run_st_eva(
            "MSFT", mode="regression", save_snapshot=False, render_dossier_report=True
        )
        section = result["research_dossier"]["sections"]["comparison_to_observations"]
        self.assertIn("net_margin_context", section)
        self.assertIn("observed_series", section["net_margin_context"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
