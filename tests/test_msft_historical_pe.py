"""MSFT Historical P/E loader integration tests."""
import unittest
from historical_pe import (
    ISSUER_CONFIGS,
    load_issuer_historical_pe,
    STATUS_INSUFFICIENT_OBSERVATIONS,
)


class TestMsftHistoricalPeIntegration(unittest.TestCase):
    """Verify MSFT can be loaded through the generic pipeline."""

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
        
        # MSFT POC loads through the pipeline and reports UNAVAILABLE status
        # (pending data format alignment for TTM qualifying observations)
        self.assertIn(result.distribution.status, ("UNAVAILABLE", STATUS_INSUFFICIENT_OBSERVATIONS))
        self.assertFalse(result.distribution.usable_for_reference)

    def test_msft_observations_are_valid(self):
        """MSFT observations structure is valid even if unavailable."""
        config = ISSUER_CONFIGS["MSFT"]
        result = load_issuer_historical_pe(config, enable_furnished=False)
        
        # All observations (27) exist structurally
        self.assertEqual(len(result.observations), 27)
        
        # All have correct IDs
        for obs in result.observations:
            self.assertEqual(obs.issuer_id, "CIK0000789019")
            self.assertEqual(obs.instrument_id, "MSFT")

    def test_msft_runner_integration(self):
        """MSFT returns UNAVAILABLE status through the runner."""
        from st_eva_runner import run_st_eva
        
        result = run_st_eva("MSFT", horizon=3, mode="regression", include_historical_pe=True)
        self.assertIsNotNone(result)
        hist_pe = result.get("production_historical_pe", {})
        dist = hist_pe.get("distribution", {})
        self.assertEqual(dist.get("status"), "UNAVAILABLE")
        self.assertFalse(dist.get("usable_for_reference", False))


if __name__ == "__main__":
    unittest.main()
