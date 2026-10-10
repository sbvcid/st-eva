"""MSFT Historical P/E loader integration tests."""
import unittest
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

    def test_msft_with_furnished_q4_evidence_qualifies(self):
        """MSFT with furnished Q4 evidence reaches 24 qualifying observations."""
        config = ISSUER_CONFIGS["MSFT"]
        result = load_issuer_historical_pe(config, enable_furnished=True)
        
        # With furnished 8-K Item 2.02 Q4 evidence, MSFT qualifies
        self.assertEqual(result.distribution.status, STATUS_USABLE_FOR_REFERENCE)
        self.assertTrue(result.distribution.usable_for_reference)
        self.assertEqual(result.distribution.sample_count, 24)
        self.assertGreaterEqual(result.distribution.sample_count, 20)

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


if __name__ == "__main__":
    unittest.main()
