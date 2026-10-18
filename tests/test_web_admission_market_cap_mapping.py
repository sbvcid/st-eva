"""Offline regression tests for the web DTO's admission and market-cap mapping.

The adapter maps the archive's per-metric admission rows into the DTO's
admitted/refused metric lists, and carries the observed market capitalisation
that the implied cash-flow figure was inverted from. Both are presentation
contracts the interface and the export reconcile against, so they are pinned
here without touching the network: `run_st_eva` and `replay` are stubbed and the
archive is a small fake.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from web import service_adapter
from web.service_adapter import AnalysisServiceAdapter


class _FakeArchive:
    def __init__(self, rows):
        self._rows = rows

    def admissions_for(self, ticker):
        return list(self._rows)

    def archival_watermark(self, ticker):
        return "2026-10-18T00:00:00+00:00"

    def close(self):
        return None


CORE_RESULT = {
    "ticker": "MU",
    "as_of": "2026-10-16",
    "market_snapshot": {"price": 878.84, "currency": "USD", "provider": "YahooFinance"},
    "observed_valuation": {"current_pfcf": 46.2545},
    "market_implied_assumptions": {
        "fcf_at_reference_multiple": 17878087201.56143,
    },
    "reference": {
        "pfcf_multiple": 67.712721,
        "pfcf_method": "production_historical_pfcf_median",
    },
    "fundamental_snapshot": {"current_market_cap": 1210573930693.0},
    "data_quality": {},
}

ADMISSION_ROWS = [
    {"metric": "operating_cash_flow", "admitted": 0, "refusals_json": "[]", "contract_id": None},
    {"metric": "capex", "admitted": 0, "refusals_json": "[]", "contract_id": None},
    {"metric": "revenue", "admitted": 1, "refusals_json": "[]", "contract_id": "cmp-1"},
    {"metric": "revenue", "admitted": 1, "refusals_json": "[]", "contract_id": "cmp-2"},
    {"metric": "operating_income", "admitted": 0, "refusals_json": "[]", "contract_id": None},
    {"metric": "depreciation_and_amortization", "admitted": 0, "refusals_json": "[]", "contract_id": None},
]


class TestAdmissionAndMarketCapMapping(unittest.TestCase):
    def _run(self, rows=None):
        adapter = AnalysisServiceAdapter(archives_dir=tempfile.mkdtemp(prefix="st-eva-adm-test-"))
        fake = _FakeArchive(rows if rows is not None else ADMISSION_ROWS)
        with patch.object(service_adapter, "run_st_eva", return_value=dict(CORE_RESULT)), patch.object(
            service_adapter, "replay"
        ) as replay_mock, patch.object(adapter, "get_archive", return_value=fake):
            replay_mock.return_value = type(
                "R",
                (),
                {
                    "outcome": "DIVERGED",
                    "reason": "stub",
                    "matched": False,
                    "reconstructed": True,
                    "observations_used": 1,
                    "observations_considered": 1,
                    "replay_fidelity": "OBSERVATIONAL",
                    "stored_document_hash": "a",
                    "rebuilt_document_hash": "b",
                },
            )()
            return adapter.run_analysis_pipeline("MU")

    def test_counts_are_rows_and_lists_are_unique_metric_names(self):
        dto = self._run()
        adm = dto.admission_summary
        # Counts stay row-based (two admitted revenue rows), lists are unique
        # names in archival order.
        self.assertEqual(adm.total_admitted, 2)
        self.assertEqual(adm.total_refused, 4)
        self.assertEqual(adm.metrics_admitted, ["revenue"])
        self.assertEqual(
            adm.metrics_refused,
            [
                "operating_cash_flow",
                "capex",
                "operating_income",
                "depreciation_and_amortization",
            ],
        )
        # The refused count is reconcilable with the refused list.
        self.assertEqual(len(adm.metrics_refused), adm.total_refused)

    def test_market_cap_operand_travels_with_the_implied_cash_flow(self):
        dto = self._run()
        vs = dto.valuation_summary
        self.assertAlmostEqual(vs.market_cap, 1210573930693.0, places=6)
        self.assertAlmostEqual(vs.selected_pfcf, 67.712721, places=6)
        # The figure is recomputable from the response's own operands.
        self.assertAlmostEqual(
            vs.implied_fcf_at_reference_multiple,
            vs.market_cap / vs.selected_pfcf,
            places=4,
        )

    def test_absence_is_reported_as_absence(self):
        dto = self._run(rows=[])
        adm = dto.admission_summary
        self.assertEqual(adm.total_admitted, 0)
        self.assertEqual(adm.metrics_refused, [])


if __name__ == "__main__":
    unittest.main()
