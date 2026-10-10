"""
Tests for capital structure and balance-sheet reconciliation.

Covers:
- Point-in-time balance sheet observations (assets, cash, debt, shares)
- Reconstructed market capitalization from price and dated share count
- Reconstructed enterprise value (partial bridge) with explicitly declared components
- Side-by-side reconciliation of observed vs reconstructed values with dates and definitions
- Distinction between cover-page point-in-time shares and EPS weighted-average diluted shares
- Currency mismatch handling and explicit unavailable items
"""
from __future__ import annotations

import unittest

from capital_structure import (
    CAPITAL_FORMULA_VERSION,
    EV_BRIDGE_COMPONENTS,
    build_capital_structure,
)
from data_contract import Observation, ValidationStatus


def make_instant(
    metric: str,
    value: float,
    effective_date: str,
    *,
    unit: str = "currency",
    currency: str = "USD",
    provider: str = "SecEdgar",
    form: str = "10-Q",
    accession: str = "0000320193-26-000100",
    available_at: str = "2026-07-31T14:01:02Z",
    available_at_basis: str = "ACCEPTANCE_DATETIME",
) -> Observation:
    return Observation(
        observation_id=f"obs-{metric}-{effective_date}",
        metric=metric,
        value=value,
        unit=unit,
        currency=currency,
        currency_basis="REPORTED",
        period_start=None,
        period_end=effective_date,
        as_of=effective_date,
        available_at=available_at,
        available_at_basis=available_at_basis,
        provider=provider,
        source_type="REGULATORY_FILING",
        source_url=None,
        definition=f"Observed {metric}",
        methodology="SEC XBRL",
        retrieved_at="2026-10-10T00:00:00Z",
        raw={"form": form, "accession": accession, "fy": 2026, "fp": "Q3"},
        status=ValidationStatus.UNVERIFIABLE,
    )


class TestCapitalStructureReconstruction(unittest.TestCase):
    def setUp(self):
        self.observations = [
            make_instant("assets", 383_000_000_000.0, "2026-06-27"),
            make_instant("cash", 40_000_000_000.0, "2026-06-27"),
            make_instant("long_term_debt", 80_000_000_000.0, "2026-06-27"),
            make_instant(
                "shares_outstanding",
                15_000_000_000.0,
                "2026-07-17",
                unit="count",
                currency=None,
            ),
        ]

    def test_full_reconstruction_with_mismatched_dates(self):
        cap = build_capital_structure(
            self.observations,
            price=300.0,
            price_date="2026-10-09",
            currency="USD",
            observed_market_cap=4_600_000_000_000.0,
            observed_enterprise_value=4_640_000_000_000.0,
        )
        self.assertEqual(cap["formula_version"], CAPITAL_FORMULA_VERSION)
        self.assertEqual(cap["status"], "COMPUTED")

        # Market Cap reconstruction: 300 * 15B = 4.5T
        recon_cap = cap["reconstructed_market_cap"]
        self.assertEqual(recon_cap["status"], "COMPUTED")
        self.assertEqual(recon_cap["value"], 4_500_000_000_000.0)
        self.assertIn("not from the same date", recon_cap["date_alignment"])
        self.assertIn("cover-page", recon_cap["notes"][1])

        # Enterprise Value reconstruction: 4.5T + 80B - 40B = 4.54T
        recon_ev = cap["reconstructed_enterprise_value"]
        self.assertEqual(recon_ev["status"], "PARTIAL")
        self.assertEqual(recon_ev["value"], 4_540_000_000_000.0)
        self.assertFalse(recon_ev["definition_is_complete"])
        self.assertIn("long_term_debt", recon_ev["components_present"])
        self.assertIn("cash", recon_ev["components_present"])
        self.assertIn("total_debt", recon_ev["components_absent"])
        self.assertIn("short_term_borrowings", recon_ev["components_absent"])

        # Side-by-side reconciliation
        recon_rows = {r["metric"]: r for r in cap["observed_vs_reconstructed"]}
        mcap_row = recon_rows["market_cap"]
        self.assertEqual(mcap_row["observed"], 4_600_000_000_000.0)
        self.assertEqual(mcap_row["reconstructed"], 4_500_000_000_000.0)
        self.assertAlmostEqual(mcap_row["difference"], -100_000_000_000.0)
        self.assertAlmostEqual(mcap_row["relative_difference"], -100_000_000_000.0 / 4_600_000_000_000.0)
        self.assertEqual(mcap_row["observed_date"], "2026-10-09")
        self.assertEqual(mcap_row["reconstructed_dates"]["shares_date"], "2026-07-17")

        ev_row = recon_rows["enterprise_value"]
        self.assertEqual(ev_row["observed"], 4_640_000_000_000.0)
        self.assertEqual(ev_row["reconstructed"], 4_540_000_000_000.0)
        self.assertEqual(ev_row["reconstructed_status"], "PARTIAL")

    def test_missing_shares_outstanding_prevents_market_cap_and_ev(self):
        obs_no_shares = [
            o for o in self.observations if o.metric != "shares_outstanding"
        ]
        cap = build_capital_structure(
            obs_no_shares,
            price=300.0,
            price_date="2026-10-09",
            currency="USD",
        )
        self.assertEqual(cap["reconstructed_market_cap"]["status"], "NOT_COMPUTED")
        self.assertIsNone(cap["reconstructed_market_cap"]["value"])
        self.assertEqual(cap["reconstructed_enterprise_value"]["status"], "NOT_COMPUTED")
        self.assertIsNone(cap["reconstructed_enterprise_value"]["value"])
        missing_items = {u["item"] for u in cap["unavailable"]}
        self.assertIn("capital_structure.shares_outstanding", missing_items)

    def test_currency_mismatch_blocks_reconstruction(self):
        obs_eur = [
            make_instant("cash", 40_000_000_000.0, "2026-06-27", currency="EUR"),
            make_instant("long_term_debt", 80_000_000_000.0, "2026-06-27", currency="USD"),
            make_instant("shares_outstanding", 15_000_000_000.0, "2026-07-17", unit="count", currency=None),
        ]
        cap = build_capital_structure(
            obs_eur,
            price=300.0,
            price_date="2026-10-09",
            currency="USD",
        )
        self.assertEqual(cap["reconstructed_market_cap"]["status"], "NOT_COMPUTED")
        reasons = [u["reason_kind"] for u in cap["unavailable"]]
        self.assertIn("CURRENCY_MISMATCH", reasons)

    def test_cross_source_verdicts_are_carried_into_observation_views(self):
        cross_source = {
            "performed": True,
            "verdicts": {
                "cash": {
                    "status": "METHODOLOGY_MISMATCH",
                    "reasons": ["Vendor cash includes short term investments"],
                    "explanation": "Different accounting scopes",
                },
                "shares_outstanding": {
                    "status": "PERIOD_MISMATCH",
                    "reasons": ["Vendor publishes no date"],
                    "explanation": "Cannot confirm contemporaneous",
                },
            },
        }
        cap = build_capital_structure(
            self.observations,
            price=300.0,
            price_date="2026-10-09",
            currency="USD",
            cross_source=cross_source,
        )
        cash_latest = cap["observations"]["cash"]["latest"]
        self.assertEqual(cash_latest["validation_status"], "METHODOLOGY_MISMATCH")
        self.assertIn("Vendor cash includes short term investments", cash_latest["caveats"])
        self.assertEqual(cash_latest["comparability_caveat"], "Different accounting scopes")

        shares_latest = cap["observations"]["shares_outstanding"]["latest"]
        self.assertEqual(shares_latest["validation_status"], "PERIOD_MISMATCH")
        self.assertIn("Vendor publishes no date", shares_latest["caveats"])

    def test_empty_observations_gives_not_acquired_status(self):
        cap = build_capital_structure([])
        self.assertEqual(cap["status"], "NOT_ACQUIRED")
        self.assertEqual(cap["reconstructed_market_cap"]["status"], "NOT_COMPUTED")


if __name__ == "__main__":
    unittest.main(verbosity=2)

