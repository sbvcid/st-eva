"""R2.1 regression tests: strict EPS provenance binding (source identity, not existence)."""
import unittest
import json
from pathlib import Path

# Ensure project root on import path
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reverse_requirements import (
    EpsAnchor, ANCHOR_USER, ANCHOR_FORWARD, ANCHOR_TTM,
    build_scenario_evidence, build_start_anchor, ReferenceMultiple,
)
from st_eva_runner import _resolve_sec_eps_fact, _find_related_sec_evidence


class TestR21StrictProvenanceBinding(unittest.TestCase):
    """Defective behavior: _resolve_sec_eps_fact returned first observation/concept record regardless of value/identity; caller attached sec_fact to any non-user anchor. Corrected: identity-first, value-only-as-confirming-check, caller attaches only on exact link; related evidence separate."""

    # --- 1. Vendor forward EPS must not inherit historical SEC 10-K ---
    def test_forward_vendor_eps_no_direct_sec_inheritance(self):
        """A vendor-provided forward value must not receive a historical 10-K as direct sec_fact merely because the concept file exists."""
        # Use an unrelated value that does not match any concept entry for the ticker
        result = _resolve_sec_eps_fact("AAPL", sec_observations=None, target_value=99.99)
        self.assertIsNone(result, "Unrelated vendor value must not inherit first available SEC record")

    # --- 2. Consensus forward EPS must not inherit SEC filing metadata ---
    def test_consensus_forward_eps_no_sec_metadata(self):
        result = _resolve_sec_eps_fact("MSFT", sec_observations=None, target_value=123.456)
        self.assertIsNone(result)

    # --- 3. Same-ticker historical record must not attach by first-available ---
    def test_first_available_record_not_attached_unrelated(self):
        """Even when a concept file exists for the ticker, an unrelated anchor value must not receive the first record."""
        result = _resolve_sec_eps_fact("MSFT", sec_observations=None, target_value=999.99)
        self.assertIsNone(result)

    # --- 4. Exact linkage establishes direct filing reference ---
    def test_exact_linkage_gets_filing_reference(self):
        """When target_value exactly matches a concept-file entry with full identity, the specific filing is returned."""
        # Pick a real entry from AAPL concept to prove linkage works
        concept_path = Path("data/historical_pe/AAPL/eps_diluted_concept.json")
        self.assertTrue(concept_path.exists(), "AAPL concept file required for positive link test")
        with open(concept_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        units = (data.get("units") or {}).get("USD/shares") or []
        self.assertGreaterEqual(len(units), 1, "Need at least one concept entry")
        entry = units[0]
        val = entry.get("val")
        self.assertIsNotNone(val)
        result = _resolve_sec_eps_fact("AAPL", sec_observations=None, target_value=float(val))
        self.assertIsNotNone(result, "Exact value match with identity must yield filing fact")
        self.assertIn("accession", result)
        self.assertIn("form", result)
        self.assertIn("filed_date", result)
        # Verify it refers to the specific entry (accession present and non-empty)
        self.assertTrue(result.get("accession"))

    # --- 5. User-supplied EPS has no SEC source attribution ---
    def test_user_supplied_eps_no_sec_attribution(self):
        anchor = EpsAnchor(
            value=7.42,
            basis=ANCHOR_USER,
            months_covered=12.0,
            provider="user",
            source_type="USER_SUPPLIED",
            is_user_assumption=True,
            sec_fact=None,
            sec_related_evidence=None,
        )
        self.assertIsNone(anchor.sec_fact)
        self.assertTrue(anchor.is_user_assumption)
        exit_mult = ReferenceMultiple(
            value=25.0, source="historical_pe_band_median",
            sample_size=30, period_label="10-yr",
            is_user_assumption=False, eligibility_state="ELIGIBLE_HISTORICAL_BAND",
            usable_for_reference=True,
        )
        exit_mult = ReferenceMultiple(
            value=25.0, source="historical_pe_band_median",
            sample_size=30, period_label="10-yr",
            is_user_assumption=False, eligibility_state="ELIGIBLE_HISTORICAL_BAND",
            usable_for_reference=True,
        )
        evidence = build_scenario_evidence(
            price=150.0,
            currency="USD",
            as_of="2026-10-11",
            price_evidence={},
            start_anchor=anchor,
            exit_multiple=exit_mult,
            horizon_years=3.0,
            required_return=0.10,
            required_return_basis="market",
        )
        # Evidence must not invent SEC source for user assumption
        eps_ev = evidence.get("eps_evidence", {})
        self.assertTrue(eps_ev.get("is_user_assumption"))
        self.assertIsNone(eps_ev.get("sec_fact"))
        # User assumption must appear in user_assumptions
        self.assertTrue(any("user-supplied" in s for s in evidence.get("user_assumptions", [])))
        # Must NOT appear in sourced_facts with SEC note
        for item in evidence.get("sourced_facts", []):
            if "Starting EPS" in item:
                self.assertNotIn("SEC ", item, "User EPS must not carry SEC filing note")

    # --- 6. Unverified provenance shown explicitly; value not hidden, source not invented ---
    def test_unverified_provenance_explicit_without_invention(self):
        # Build a vendor-derived anchor with no direct sec_fact but with related evidence present
        anchor = EpsAnchor(
            value=5.55,
            basis=ANCHOR_FORWARD,
            months_covered=12.0,
            provider="refinitiv",
            source_type="OBSERVED",
            is_user_assumption=False,
            sec_fact=None,
            sec_related_evidence=_find_related_sec_evidence("AAPL"),
        )
        exit_mult = ReferenceMultiple(
            value=25.0, source="historical_pe_band_median",
            sample_size=30, period_label="10-yr",
            is_user_assumption=False, eligibility_state="ELIGIBLE_HISTORICAL_BAND",
            usable_for_reference=True,
        )
        # If related exists but direct does not, limitation must be recorded
        evidence = build_scenario_evidence(
            price=150.0,
            currency="USD",
            as_of="2026-10-11",
            price_evidence={},
            start_anchor=anchor,
            exit_multiple=exit_mult,
            horizon_years=3.0,
            required_return=0.10,
            required_return_basis="market",
        )
        eps_ev = evidence.get("eps_evidence", {})
        self.assertIsNone(eps_ev.get("sec_fact"))
        # The EPS value must still be visible (not hidden)
        self.assertEqual(eps_ev.get("value"), 5.55)
        # Related evidence should be present when file exists
        if anchor.sec_related_evidence:
            self.assertIsNotNone(evidence.get("related_sec_evidence"))
        # Limitations must state the unverified provenance explicitly
        missing = evidence.get("missing_or_unvalidated", [])
        limitation_text = "Direct SEC source of selected EPS not established"
        self.assertTrue(
            any(limitation_text in m for m in missing),
            f"Expected explicit unverified provenance message; got {missing}"
        )
        # Sourced facts must NOT claim SEC source
        for item in evidence.get("sourced_facts", []):
            if "Starting EPS" in item:
                self.assertNotIn("accession", item, "Unverified source must not invent accession")

    # --- 7. Deterministic traces and DTO error behavior intact ---
    def test_epsilon_anchor_contract_preserved(self):
        # Valid anchor passes
        a = EpsAnchor(value=3.5, basis=ANCHOR_TTM, months_covered=12.0, provider="test")
        self.assertEqual(a.value, 3.5)
        # Non-finite rejected
        with self.assertRaises(Exception):
            EpsAnchor(value=float('nan'), basis=ANCHOR_TTM, months_covered=12.0, provider="test")
        # Non-positive coverage rejected
        with self.assertRaises(Exception):
            EpsAnchor(value=3.5, basis=ANCHOR_TTM, months_covered=0.0, provider="test")

    def test_build_start_anchor_selects_correct_basis(self):
        # Trailing preferred by default
        anchor, unavailable = build_start_anchor(
            trailing_eps=2.0, forward_eps=2.5, consensus_eps=3.0,
            currency="USD", prefer="trailing",
        )
        self.assertIsNotNone(anchor)
        self.assertEqual(anchor.basis, ANCHOR_TTM)
        # Forward preferred
        anchor_f, _ = build_start_anchor(
            trailing_eps=2.0, forward_eps=2.5, consensus_eps=3.0,
            currency="USD", prefer="forward",
        )
        self.assertEqual(anchor_f.basis, ANCHOR_FORWARD)


if __name__ == "__main__":
    unittest.main(verbosity=2)
