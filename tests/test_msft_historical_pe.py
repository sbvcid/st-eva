"""MSFT Historical P/E loader integration tests."""
import unittest
import json
from pathlib import Path
from historical_pe import (
    ISSUER_CONFIGS,
    load_issuer_historical_pe,
    STATUS_USABLE_FOR_REFERENCE,
    STATUS_INSUFFICIENT_OBSERVATIONS,
    EVIDENCE_CLASS_FURNISHED,
)


class TestMsftHistoricalPeIntegration(unittest.TestCase):
    """Verify MSFT can be loaded through the generic pipeline with furnished Q4 evidence."""

    def test_msft_configured(self):
        """MSFT is registered in ISSUER_CONFIGS."""
        self.assertIn("MSFT", ISSUER_CONFIGS)
        config = ISSUER_CONFIGS["MSFT"]
        self.assertEqual(config.ticker, "MSFT")
        self.assertEqual(config.issuer_id, "CIK0000789019")
        self.assertEqual(config.fye_month, 6)

    def test_msft_loads_through_generic_pipeline(self):
        """MSFT can be loaded using the generic load_issuer_historical_pe."""
        config = ISSUER_CONFIGS["MSFT"]
        result = load_issuer_historical_pe(config, enable_furnished=False)
        
        # Without furnished Q4 evidence, MSFT reports UNAVAILABLE
        self.assertIn(result.distribution.status, ("UNAVAILABLE", STATUS_INSUFFICIENT_OBSERVATIONS))
        self.assertFalse(result.distribution.usable_for_reference)

    def test_msft_observations_are_valid(self):
        """MSFT observations structure is valid even if unavailable without furnished."""
        config = ISSUER_CONFIGS["MSFT"]
        result = load_issuer_historical_pe(config, enable_furnished=False)
        
        # All observations (27) exist structurally
        self.assertEqual(len(result.observations), 27)
        
        # All have correct IDs
        for obs in result.observations:
            self.assertEqual(obs.issuer_id, "CIK0000789019")
            self.assertEqual(obs.instrument_id, "MSFT")

    def test_msft_q4_evidence_file_contains_six_records(self):
        """Q4 evidence JSON file contains 6 furnished records with correct schema."""
        q4_path = Path("data/historical_pe/MSFT/q4_evidence_records.json")
        self.assertTrue(q4_path.exists(), f"Q4 evidence file not found at {q4_path}")
        
        q4_data = json.loads(q4_path.read_text())
        records = q4_data.get("records", [])
        self.assertEqual(len(records), 6, "Expected 6 furnished Q4 records")
        
        # Verify schema of each record
        for i, rec in enumerate(records):
            self.assertEqual(rec.get("source_type"), "SEC_8K_ITEM_2_02_EX_99_1", 
                           f"Record {i}: wrong source_type")
            self.assertTrue(rec.get("meets_st_eva_q4_evidence"), 
                          f"Record {i}: meets_st_eva_q4_evidence not true")
            self.assertEqual(rec.get("fiscal_quarter"), 4, f"Record {i}: not Q4")
            self.assertIn("accession", rec, f"Record {i}: missing accession")
            self.assertIn("diluted_eps", rec, f"Record {i}: missing diluted_eps")
            self.assertIn("quarter_period_end", rec, f"Record {i}: missing quarter_period_end")
            self.assertIn("usable_date", rec, f"Record {i}: missing usable_date")
            self.assertIn("document_identifier", rec, f"Record {i}: missing document_identifier")

    def test_msft_q4_evidence_actually_loaded_in_observations(self):
        """Six Q4 furnished records are actually loaded into quarterly evidence."""
        config = ISSUER_CONFIGS["MSFT"]
        result = load_issuer_historical_pe(config, enable_furnished=True)
        
        # Count Q4 furnished EPS evidence across all observations
        q4_furnished_by_accession = {}
        for obs in result.observations:
            for comp in obs.eps_state.get("components", []):
                if comp.get("form") == "8-K" and comp.get("evidence_class") == EVIDENCE_CLASS_FURNISHED:
                    accession = comp.get("accession")
                    if accession:
                        q4_furnished_by_accession[accession] = comp
        
        # Verify we have all 6 unique Q4 accessions
        expected_accessions = {
            "0001193125-21-225746",
            "0001193125-22-202034", 
            "0000950170-23-034400",
            "0000950170-24-087835",
            "0000950170-25-100226",
            "0001193125-26-323632"
        }
        self.assertEqual(set(q4_furnished_by_accession.keys()), expected_accessions,
                        "Not all 6 Q4 furnished records were loaded")
        
        # Verify EPS values match
        expected_eps = {
            "0001193125-21-225746": 2.17,
            "0001193125-22-202034": 2.23,
            "0000950170-23-034400": 2.69,
            "0000950170-24-087835": 2.95,
            "0000950170-25-100226": 3.65,
            "0001193125-26-323632": 4.81
        }
        for accession, expected_eps_val in expected_eps.items():
            actual_eps = q4_furnished_by_accession[accession].get("value")
            self.assertEqual(actual_eps, expected_eps_val,
                           f"Q4 EPS mismatch for {accession}: {actual_eps} != {expected_eps_val}")

    def test_msft_ttm_components_include_q4_furnished_evidence_ids(self):
        """TTM components contain Q4 furnished evidence IDs matching accessions."""
        config = ISSUER_CONFIGS["MSFT"]
        result = load_issuer_historical_pe(config, enable_furnished=True)
        
        # Find at least one observation with 4 components including furnished Q4
        found_with_q4 = False
        for obs in result.observations:
            if obs.eps_state.get("status") == "AVAILABLE":
                components = obs.eps_state.get("components", [])
                if len(components) == 4:
                    # Check for Q4 furnished component
                    q4_comps = [c for c in components if "furn" in c.get("evidence_id", "")]
                    if q4_comps:
                        found_with_q4 = True
                        q4_comp = q4_comps[0]
                        # Verify evidence ID structure: ev-furn-{accession}-{period}
                        self.assertIn("ev-furn-", q4_comp.get("evidence_id", ""))
                        # Verify accession is present
                        self.assertIn(q4_comp.get("accession"), expected_accessions)
                        break
        
        self.assertTrue(found_with_q4, "No observation with Q4 furnished component found")

    def test_msft_with_furnished_q4_evidence_qualifies(self):
        """MSFT with furnished Q4 evidence reaches 24 qualifying observations."""
        config = ISSUER_CONFIGS["MSFT"]
        result = load_issuer_historical_pe(config, enable_furnished=True)
        
        # With furnished 8-K Item 2.02 Q4 evidence, MSFT qualifies
        self.assertEqual(result.distribution.status, STATUS_USABLE_FOR_REFERENCE)
        self.assertTrue(result.distribution.usable_for_reference)
        self.assertEqual(result.distribution.sample_count, 24)
        self.assertGreaterEqual(result.distribution.sample_count, 20)

    def test_msft_reconciles_with_poc_eval_dates(self):
        """Production observations match POC evaluation dates."""
        config = ISSUER_CONFIGS["MSFT"]
        result = load_issuer_historical_pe(config, enable_furnished=True)
        
        # POC has 27 evaluation dates
        prod_eval_dates = sorted({obs.evaluation_date for obs in result.observations})
        self.assertEqual(len(prod_eval_dates), 27, "Expected 27 evaluation dates")

    def test_msft_reconciles_with_poc_pe_values(self):
        """Production TTM P/E distribution statistics match POC."""
        config = ISSUER_CONFIGS["MSFT"]
        result = load_issuer_historical_pe(config, enable_furnished=True)
        
        dist = result.distribution
        
        # POC computed: mean=32.127051, std=4.278044, min=24.272619, max=39.112903
        self.assertAlmostEqual(dist.mean, 32.127051, places=4)
        self.assertAlmostEqual(dist.std, 4.278044, places=4)
        self.assertAlmostEqual(dist.min, 24.272619, places=4)
        self.assertAlmostEqual(dist.max, 39.112903, places=4)

    def test_msft_furnished_evidence_includes_q4_records(self):
        """MSFT observations include furnished Q4 evidence from 8-K exhibits."""
        config = ISSUER_CONFIGS["MSFT"]
        result = load_issuer_historical_pe(config, enable_furnished=True)
        
        # Verify furnished evidence class is present in observations
        classes = set()
        q4_evidence_count = 0
        for obs in result.observations:
            for comp in obs.eps_state.get("components", []):
                classes.add(comp.get("evidence_class"))
                if "furn" in comp.get("evidence_id", ""):
                    q4_evidence_count += 1
        
        # Should have both filed and furnished evidence classes
        self.assertIn(EVIDENCE_CLASS_FURNISHED, classes)
        # Should have Q4 furnished evidence
        self.assertGreater(q4_evidence_count, 0)

    def test_msft_runner_integration(self):
        """MSFT returns USABLE_FOR_REFERENCE status through the runner."""
        from st_eva_runner import run_st_eva
        
        result = run_st_eva("MSFT", horizon=3, mode="regression", include_historical_pe=True)
        self.assertIsNotNone(result)
        hist_pe = result.get("production_historical_pe", {})
        dist = hist_pe.get("distribution", {})
        # With furnished Q4 evidence integrated, MSFT is now USABLE_FOR_REFERENCE
        self.assertEqual(dist.get("status"), "USABLE_FOR_REFERENCE")
        self.assertTrue(dist.get("usable_for_reference", False))
        self.assertEqual(dist.get("sample_count"), 24)


# Expected accessions for use in tests
expected_accessions = {
    "0001193125-21-225746",
    "0001193125-22-202034", 
    "0000950170-23-034400",
    "0000950170-24-087835",
    "0000950170-25-100226",
    "0001193125-26-323632"
}


if __name__ == "__main__":
    unittest.main()
