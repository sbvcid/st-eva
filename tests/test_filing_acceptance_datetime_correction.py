"""Regression tests for the filing-acceptance evidence contract.

Every acceptance row keeps the EDGAR SGML header acceptance wall clock
(``acceptance_datetime_header_et``) with an explicit UTC offset, and the 16:00
ET usable-date cutoff is derived from that wall clock at load time -- never
from a UTC serialisation and never with a fixed four-hour offset.

The per-ticker shapes differ and are asserted as they are, not forced uniform:

* MU keeps, on every row, the header wall clock, the submissions-API original
  (``acceptance_datetime_submissions_api``, a UTC serialisation) and the
  ``acceptance_datetime_basis`` that names which value drove the record.
* AAPL keeps the header wall clock on every row and the API original where the
  header page carried one (43 of 48); it declares no basis field.
* MSFT keeps only the header wall clock (the accepted, verified shape).

These tests read the canonical data directly; they do not depend on any helper
script, because the canonical files themselves are the contract.
"""
import datetime
import json
import os
from pathlib import Path

import unittest

DATA = Path("data/historical_pe")
TICKERS = ("AAPL", "MSFT", "MU")
ALLOWED_BASIS = (
    "EDGAR_SGML_HEADER_ACCEPTANCE_DATETIME",
    "SUBMISSIONS_API_OFFSET_CORRECTION",
)


def _rows(ticker):
    return json.loads(
        (DATA / ticker / "filing_acceptance_evidence.json").read_text(encoding="utf-8")
    )


class TestAcceptanceContract(unittest.TestCase):
    def test_every_row_carries_a_header_wall_clock_with_an_explicit_offset(self):
        for ticker in TICKERS:
            rows = _rows(ticker)
            self.assertTrue(rows, f"{ticker}: no acceptance rows")
            for row in rows:
                header = row.get("acceptance_datetime_header_et")
                self.assertTrue(
                    header, f"{ticker} {row.get('accession')}: missing header ET"
                )
                parsed = datetime.datetime.fromisoformat(header)
                self.assertIsNotNone(
                    parsed.utcoffset(),
                    f"{ticker} {row['accession']}: header ET lost its offset",
                )

    def test_both_dst_offsets_are_present(self):
        # A file that assumed a fixed four-hour offset would only ever carry
        # -04:00 and would hide -05:00 (EST) entirely.
        seen = set()
        for ticker in TICKERS:
            for row in _rows(ticker):
                seen.add(row["acceptance_datetime_header_et"][-6:])
        self.assertIn("-04:00", seen)
        self.assertIn("-05:00", seen)

    def test_mu_keeps_the_api_original_and_basis_on_every_row(self):
        rows = _rows("MU")
        self.assertEqual(len(rows), 1003)
        for row in rows:
            self.assertTrue(
                row.get("acceptance_datetime_submissions_api"),
                f"MU {row['accession']}: API original dropped",
            )
            self.assertIn(row.get("acceptance_datetime_basis"), ALLOWED_BASIS)

    def test_mu_api_original_is_a_utc_serialisation_not_an_et_wall_clock(self):
        # The header wall clock and the API serialisation are genuinely two
        # different clocks; a file that copied one into the other fails here.
        mu = {r["accession"]: r for r in _rows("MU")}
        row = mu["0000723125-26-000018"]
        self.assertEqual(row["acceptance_datetime_header_et"], "2026-09-30T16:02:22-04:00")
        self.assertEqual(row["acceptance_datetime_submissions_api"], "2026-10-01T00:02:22.000Z")

    def test_aapl_keeps_the_api_original_where_the_header_carried_one(self):
        rows = _rows("AAPL")
        self.assertEqual(len(rows), 48)
        with_api = [r for r in rows if r.get("acceptance_datetime_submissions_api")]
        self.assertEqual(len(with_api), 43)
        for row in with_api:
            self.assertTrue(row["acceptance_datetime_submissions_api"].endswith("Z"))

    def test_msft_remains_header_only(self):
        rows = _rows("MSFT")
        self.assertEqual(len(rows), 47)
        for row in rows:
            self.assertNotIn("acceptance_datetime_submissions_api", row)

    def test_loader_does_not_read_a_backup_file(self):
        text = Path("historical_pe.py").read_text(encoding="utf-8", errors="ignore")
        self.assertNotIn(".bak", text.lower())

    def test_no_stray_corrected_file_sits_beside_the_canonical_one(self):
        # A second, non-canonical acceptance file beside the real one would let
        # two different shapes diverge; the canonical file is the only one.
        for ticker in TICKERS:
            stray = DATA / ticker / "filing_acceptance_evidence_corrected.json"
            self.assertFalse(os.path.exists(stray), f"{ticker}: stray {stray.name}")


if __name__ == "__main__":
    unittest.main()
