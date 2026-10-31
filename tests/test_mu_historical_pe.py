"""MU historical P/E: Q4 furnished evidence, PIT discipline, and the
window-continuity guard.

These tests pin the production behavior that this round added for MU:

* the six fiscal Q4 GAAP diluted EPS facts are directly stated in 8-K
  Item 2.02 EX-99.1 exhibits, load through the canonical evidence gate, and
  carry furnished provenance distinct from filed evidence;
* GAAP values stay isolated from the non-GAAP figures the releases quote;
* a filled fiscal-position window whose period ends are not consecutive
  calendar quarters is refused (52/53-week filers can hit this through the
  month-grid quarter mapping), so a skipped quarter can never masquerade as
  a TTM sum;
* usable dates follow the 16:00 ET rule against real MU trading days, and
  the acceptance file's corrected ET timestamps preserve the original
  submissions-API values for audit;
* point-in-time supersede, the missing-period reasons, and the reference
  gate all hold on the real MU dataset.

Network is never touched.
"""

from __future__ import annotations

import datetime
import json
import unittest
from pathlib import Path

from historical_pe import (
    EVIDENCE_CLASS_FILED,
    EVIDENCE_CLASS_FURNISHED,
    ISSUER_CONFIGS,
    METRIC_TTM_GAAP_DILUTED_PE,
    QuarterEpsEvidence,
    REASON_INSUFFICIENT_QUARTERS,
    REASON_MISSING_Q4_EPS,
    REASON_NON_POSITIVE_EPS,
    STATUS_AVAILABLE,
    STATUS_USABLE_FOR_REFERENCE,
    build_historical_pe,
    load_issuer_historical_pe,
    resolve_usable_date,
    HistoricalPriceEvidence,
)
from zoneinfo import ZoneInfo

DATA = Path("data/historical_pe/MU")
PRICES_EXIST = (DATA / "daily_prices.json").exists()
PRICES_SKIP = "MU daily_prices.json excluded per C-1 / DATA-DELIVERY.md"

# The 43 evidence-relevant accessions whose acceptance times were verified
# against the filings' own SGML headers (10-Q/10-K filings that carry the
# quarter/annual facts, plus the six fiscal Q4 earnings 8-Ks). The rebuild
# stores each value in the acceptance file; this table is the tracked ground
# truth the corrected rows must reproduce.
SGML_VERIFIED = {
    "0000723125-17-000131": "2017-10-26T12:51:41-04:00",
    "0000723125-17-000166": "2017-12-20T14:56:35-05:00",
    "0000723125-18-000036": "2018-03-23T14:52:31-04:00",
    "0000723125-18-000065": "2018-06-22T11:39:04-04:00",
    "0000723125-18-000092": "2018-10-15T14:40:51-04:00",
    "0000723125-18-000156": "2018-12-19T10:49:25-05:00",
    "0000723125-19-000014": "2019-03-21T15:11:06-04:00",
    "0000723125-19-000035": "2019-06-26T16:00:55-04:00",
    "0000723125-19-000094": "2019-10-17T14:44:04-04:00",
    "0000723125-19-000174": "2019-12-20T12:21:53-05:00",
    "0000723125-20-000034": "2020-03-26T13:52:52-04:00",
    "0000723125-20-000067": "2020-06-30T12:12:44-04:00",
    "0000723125-20-000082": "2020-10-19T14:36:42-04:00",
    "0000723125-21-000012": "2021-01-08T12:49:12-05:00",
    "0000723125-21-000032": "2021-04-01T13:49:08-04:00",
    "0000723125-21-000052": "2021-07-01T14:04:20-04:00",
    "0000723125-21-000060": "2021-09-28T16:01:35-04:00",
    "0000723125-21-000065": "2021-10-08T13:23:24-04:00",
    "0000723125-22-000004": "2022-01-06T15:27:43-05:00",
    "0000723125-22-000016": "2022-03-30T15:47:32-04:00",
    "0000723125-22-000036": "2022-06-30T17:47:52-04:00",
    "0000723125-22-000044": "2022-09-29T16:00:31-04:00",
    "0000723125-22-000048": "2022-10-07T14:57:09-04:00",
    "0000723125-22-000072": "2022-12-22T12:38:24-05:00",
    "0000723125-23-000022": "2023-03-29T16:48:21-04:00",
    "0000723125-23-000041": "2023-06-29T15:34:20-04:00",
    "0000723125-23-000051": "2023-09-27T16:00:28-04:00",
    "0000723125-23-000054": "2023-10-06T16:01:37-04:00",
    "0000723125-23-000077": "2023-12-21T13:05:34-05:00",
    "0000723125-24-000007": "2024-03-21T13:17:48-04:00",
    "0000723125-24-000019": "2024-06-27T13:19:29-04:00",
    "0000723125-24-000023": "2024-09-25T16:00:27-04:00",
    "0000723125-24-000027": "2024-10-04T16:12:50-04:00",
    "0000723125-24-000047": "2024-12-18T18:52:13-05:00",
    "0000723125-25-000009": "2025-03-20T19:20:23-04:00",
    "0000723125-25-000021": "2025-06-25T18:50:42-04:00",
    "0000723125-25-000024": "2025-09-23T16:02:28-04:00",
    "0000723125-25-000028": "2025-10-03T14:42:25-04:00",
    "0000723125-25-000046": "2025-12-17T18:47:44-05:00",
    "0000723125-26-000006": "2026-03-18T19:00:06-04:00",
    "0000723125-26-000015": "2026-06-24T18:59:46-04:00",
    "0000723125-26-000018": "2026-09-30T16:02:22-04:00",
    "0000723125-26-000023": "2026-10-09T08:21:00-04:00",
}

# The six fiscal Q4 earnings 8-Ks and their directly stated GAAP diluted EPS.
EXPECTED_Q4 = {
    "0000723125-21-000060": ("2021-09-02", 2.39),
    "0000723125-22-000044": ("2022-09-01", 1.35),
    "0000723125-23-000051": ("2023-08-31", -1.31),
    "0000723125-24-000023": ("2024-08-29", 0.79),
    "0000723125-25-000024": ("2025-08-28", 2.83),
    "0000723125-26-000018": ("2026-09-03", 32.87),
}

# Non-GAAP diluted EPS the same releases quote next to the GAAP figures;
# recorded in the study, excluded from evidence.
NON_GAAP_QUOTED = {
    "0000723125-21-000060": 2.42,
    "0000723125-22-000044": 1.45,
    "0000723125-23-000051": -1.07,
    "0000723125-24-000023": 1.18,
    "0000723125-25-000024": 3.03,
    "0000723125-26-000018": 33.42,
}


def _load_mu():
    return load_issuer_historical_pe(ISSUER_CONFIGS["MU"])


def _canonical_q4_records():
    payload = json.loads((DATA / "q4_evidence_records.json").read_text(encoding="utf-8"))
    return payload["records"]


class TestMuQ4EvidenceRecords(unittest.TestCase):
    """The canonical Q4 evidence file: direct, furnished, traceable."""

    def test_canonical_records_are_exactly_the_six_fiscal_q4s(self):
        records = _canonical_q4_records()
        self.assertEqual(len(records), 6)
        by_accession = {r["accession"]: r for r in records}
        self.assertEqual(set(by_accession), set(EXPECTED_Q4))
        for accession, (period_end, diluted_eps) in EXPECTED_Q4.items():
            record = by_accession[accession]
            self.assertEqual(record["quarter_period_end"], period_end)
            self.assertEqual(record["diluted_eps"], diluted_eps)
            self.assertEqual(record["fiscal_quarter"], 4)
            self.assertEqual(record["form"], "8-K")
            self.assertEqual(record["sec_item"], "Item 2.02")
            self.assertEqual(record["source_type"], "SEC_8K_ITEM_2_02_EX_99_1")
            self.assertTrue(record["meets_st_eva_q4_evidence"])
            self.assertTrue(record["stated_directly"])
            self.assertEqual(record["evidence_class"], EVIDENCE_CLASS_FURNISHED)
            self.assertEqual(record["audit_status"], "unaudited")
            self.assertEqual(record["currency"], "USD")

    def test_records_carry_complete_source_identity(self):
        for record in _canonical_q4_records():
            self.assertTrue(record["accession"])
            self.assertTrue(record["source_url"].startswith("https://www.sec.gov/Archives/"))
            self.assertTrue(record["document_identifier"].endswith(".htm"))
            self.assertRegex(record["content_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(
                record["acceptance_datetime"],
                r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}-0[45]:00$",
            )
            self.assertTrue(record["usable_date"] >= record["quarter_period_end"])

    def test_gaap_values_stay_isolated_from_quoted_non_gaap_and_annual(self):
        # The non-GAAP figure each release quotes beside the GAAP figure and
        # the exhibit's own twelve-month figure must never equal the evidence
        # value. The annual comparison reads the tracked XBRL concept file.
        concept = json.loads(
            (DATA / "eps_diluted_concept.json").read_text(encoding="utf-8")
        )
        annual = {}
        for fact in concept["units"]["USD/shares"]:
            if not fact.get("start"):
                continue
            span = (
                datetime.date.fromisoformat(fact["end"])
                - datetime.date.fromisoformat(fact["start"])
            ).days
            if 350 <= span <= 380 and fact["form"] == "10-K":
                annual[fact["end"]] = float(fact["val"])
        for record in _canonical_q4_records():
            self.assertNotEqual(
                record["diluted_eps"],
                NON_GAAP_QUOTED[record["accession"]],
                "the evidence value must be the GAAP column, not the quoted "
                "non-GAAP figure",
            )
            annual_value = annual.get(record["quarter_period_end"])
            self.assertIsNotNone(
                annual_value,
                f"no 10-K annual fact for {record['quarter_period_end']}",
            )
            self.assertNotEqual(
                record["diluted_eps"],
                annual_value,
                "a quarter value equal to the annual fact would mean the "
                "twelve-month figure was read as the quarter",
            )


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class TestMuLoaderAdoptsFurnishedQ4(unittest.TestCase):
    """The production loader adopts the furnished Q4 records and keeps classes."""

    @classmethod
    def setUpClass(cls):
        cls.result = _load_mu()

    def test_all_six_furnished_records_enter_the_evidence_stream(self):
        # With issuer-declared fiscal identity the FY2026 Q4 furnished fact
        # fills its true (2026, Q4) position, so every one of the six
        # furnished records now completes real TTM windows, and the current
        # snapshot is itself the FY2026 window.
        furnished = [
            c
            for o in self.result.observations
            for c in o.eps_state.get("components", [])
            if c["evidence_class"] == EVIDENCE_CLASS_FURNISHED
        ]
        adopted_accessions = {c["accession"] for c in furnished}
        self.assertEqual(adopted_accessions, set(EXPECTED_Q4))
        snapshot_accessions = {
            c["accession"] for c in self.result.current_snapshot.eps_state["components"]
        }
        self.assertIn("0000723125-26-000018", snapshot_accessions)

    def test_furnished_components_keep_their_class_and_provenance(self):
        seen = set()
        observations = list(self.result.observations) + [self.result.current_snapshot]
        for o in observations:
            for c in o.eps_state.get("components", []):
                if c["evidence_class"] == EVIDENCE_CLASS_FURNISHED:
                    key = c["accession"]
                    if key in seen:
                        continue
                    seen.add(key)
                    self.assertEqual(c["form"], "8-K")
                    self.assertEqual(c["sec_item"], "Item 2.02")
                    self.assertEqual(c["audit_status"], "unaudited")
                    self.assertTrue(c["item_2_02_furnished_not_filed"])
                    self.assertIn("furnished not filed", c["legal_status_note"])
                    self.assertEqual(c["period_declaration"], "STATEMENT_COLUMN_LABEL")
                    self.assertTrue(c["stated_directly"])
        self.assertEqual(seen, set(EXPECTED_Q4))

    def test_no_component_is_laundered_between_classes(self):
        for o in self.result.observations:
            summary = o.eps_state["component_summary"]
            for c in o.eps_state.get("components", []):
                if c["form"] == "8-K":
                    self.assertEqual(c["evidence_class"], EVIDENCE_CLASS_FURNISHED)
                elif c["form"] in ("10-Q", "10-K"):
                    self.assertEqual(c["evidence_class"], EVIDENCE_CLASS_FILED)
            if summary["mixed_class_window"]:
                classes = {c["evidence_class"] for c in o.eps_state["components"]}
                self.assertEqual(classes, {EVIDENCE_CLASS_FILED, EVIDENCE_CLASS_FURNISHED})


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class TestMuUsableDates(unittest.TestCase):
    """The 16:00 ET rule against real MU trading days."""

    def test_every_q4_record_usable_the_next_trading_day(self):
        # Every Q4 release was accepted between 16:00:27 and 16:02:28 ET, so
        # each usable date is the next MU trading day, not the acceptance day.
        prices = json.loads((DATA / "daily_prices.json").read_text(encoding="utf-8"))
        result = prices["chart"]["result"][0]
        quote = result["indicators"]["quote"][0]
        trading_days = sorted(
            datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc).date().isoformat()
            for stamp, close in zip(result["timestamp"], quote["close"])
            if close is not None
        )
        trading_set = set(trading_days)
        for record in _canonical_q4_records():
            accepted_at = datetime.datetime.fromisoformat(record["acceptance_datetime"])
            self.assertGreaterEqual(accepted_at.time().isoformat(), "16:00:00")
            usable, rule = resolve_usable_date(accepted_at, trading_days)
            self.assertEqual(usable, record["usable_date"])
            self.assertEqual(rule, "acceptance_at_or_after_1600ET_next_trading_day")
            self.assertNotEqual(usable, accepted_at.date().isoformat())
            self.assertIn(usable, trading_set)

    def test_acceptance_file_keeps_true_et_plus_the_api_original(self):
        rows = json.loads(
            (DATA / "filing_acceptance_evidence.json").read_text(encoding="utf-8")
        )
        by_accession = {r["accession"]: r for r in rows}
        # The FY2026 Q4 8-K: SGML header says 2026-09-30 16:02:22 ET; the
        # submissions API serialized 2026-10-01T00:02:22Z (true UTC plus the
        # Eastern offset). The corrected value is the acceptance wall clock.
        row = by_accession["0000723125-26-000018"]
        self.assertEqual(row["acceptance_datetime_header_et"], "2026-09-30T16:02:22-04:00")
        self.assertEqual(
            row["acceptance_datetime_submissions_api"], "2026-10-01T00:02:22.000Z"
        )
        self.assertEqual(
            row["acceptance_datetime_basis"], "EDGAR_SGML_HEADER_ACCEPTANCE_DATETIME"
        )
        # The 10-K that trails it: accepted 08:21 ET on filing day, same-day usable.
        row = by_accession["0000723125-26-000023"]
        self.assertEqual(row["acceptance_datetime_header_et"], "2026-10-09T08:21:00-04:00")

    def test_every_acceptance_row_carries_an_explicit_offset(self):
        rows = json.loads(
            (DATA / "filing_acceptance_evidence.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(rows), 1003)
        for row in rows:
            parsed = datetime.datetime.fromisoformat(row["acceptance_datetime_header_et"])
            self.assertIsNotNone(
                parsed.utcoffset(),
                f"row {row['accession']} lost its explicit timezone",
            )
            self.assertTrue(row["acceptance_datetime_submissions_api"])
            self.assertIn(
                row["acceptance_datetime_basis"],
                (
                    "EDGAR_SGML_HEADER_ACCEPTANCE_DATETIME",
                    "SUBMISSIONS_API_OFFSET_CORRECTION",
                ),
            )

    def test_offset_correction_reproduces_the_sgml_verified_values(self):
        rows = json.loads(
            (DATA / "filing_acceptance_evidence.json").read_text(encoding="utf-8")
        )
        by_accession = {r["accession"]: r for r in rows}
        self.assertEqual(len(SGML_VERIFIED), 43)
        for accession, true_et in SGML_VERIFIED.items():
            self.assertEqual(by_accession[accession]["acceptance_datetime_header_et"], true_et)
            self.assertEqual(
                by_accession[accession]["acceptance_datetime_basis"],
                "EDGAR_SGML_HEADER_ACCEPTANCE_DATETIME",
            )

    def test_frozen_exhibit_identity_is_recorded_in_the_canonical_records(self):
        # The exhibits live in the git-ignored research/ tree; the tracked
        # provenance is the digest, the URL and the file name, which the
        # study's verify stage re-checks against the stored bytes.
        for record in _canonical_q4_records():
            self.assertNotIn("research", record["source_url"])
            self.assertTrue(record["source_url"].endswith(record["document_identifier"]))
            self.assertEqual(len(record["content_sha256"]), 64)


class TestWindowContinuityGuard(unittest.TestCase):
    """A position-filled window over non-adjacent quarter ends is not a TTM."""

    def _evidence(self, ends_values, usable_date, fye_month=8):
        quarters = []
        for end, value in ends_values:
            end_d = datetime.date.fromisoformat(end)
            months_after = (end_d.month - fye_month) % 12
            fq = 4 if months_after == 0 else (months_after - 1) // 3 + 1
            quarters.append(
                QuarterEpsEvidence(
                    evidence_id=f"ev-{end}",
                    issuer_id="CIK0000723125",
                    evidence_class=EVIDENCE_CLASS_FILED,
                    form="10-Q",
                    accession=f"accn-{end}",
                    period_end=end,
                    fiscal_year=end_d.year + (1 if end_d.month > fye_month else 0),
                    fiscal_quarter=fq,
                    value=value,
                    audit_status="unaudited_reviewed",
                    acceptance_datetime="2024-01-01T12:00:00-05:00",
                    usable_date=usable_date,
                    usable_date_rule="acceptance_before_1600ET_same_day",
                    period_start=None,
                    duration_days=None,
                    period_declaration="STATEMENT_COLUMN_LABEL",
                    stated_directly=True,
                )
            )
        return quarters

    def _prices(self, days):
        return {
            day: HistoricalPriceEvidence(
                price_evidence_id=f"price-{day}",
                issuer_id="CIK0000723125",
                instrument_id="MU",
                price_date=day,
                close=100.0,
            )
            for day in days
        }

    def test_window_with_a_skipped_quarter_is_refused(self):
        # Four formula positions fill, but the chosen ends jump 182 days over
        # the actual June quarter: not a TTM window, no value.
        quarters = self._evidence(
            [
                ("2022-12-01", -0.18),
                ("2023-03-02", -2.12),
                ("2023-08-31", -1.31),
                ("2023-11-30", -1.12),
            ],
            usable_date="2024-01-02",
        )
        prices = self._prices(["2024-01-02"])
        result = build_historical_pe(
            issuer_id="CIK0000723125",
            instrument_id="MU",
            quarter_evidence=quarters,
            annual_evidence=[],
            prices=prices,
            fye_month=8,
            trading_days=["2024-01-02"],
            evaluation_dates=["2024-01-02"],
        )
        obs = result.observations[0]
        self.assertEqual(obs.status, "UNAVAILABLE")
        self.assertEqual(obs.reason_code, REASON_INSUFFICIENT_QUARTERS)
        self.assertIn("not consecutive", obs.reason_detail)
        self.assertIn("182", obs.reason_detail)
        self.assertEqual(obs.eps_state["components"], [])
        self.assertIsNone(obs.value)

    def test_contiguous_window_stays_available(self):
        quarters = self._evidence(
            [
                ("2023-11-30", -1.12),
                ("2024-02-29", 0.71),
                ("2024-05-30", 0.30),
                ("2024-08-29", 0.79),
            ],
            usable_date="2024-09-26",
        )
        prices = self._prices(["2024-09-26"])
        result = build_historical_pe(
            issuer_id="CIK0000723125",
            instrument_id="MU",
            quarter_evidence=quarters,
            annual_evidence=[],
            prices=prices,
            fye_month=8,
            trading_days=["2024-09-26"],
            evaluation_dates=["2024-09-26"],
        )
        obs = result.observations[0]
        self.assertEqual(obs.status, STATUS_AVAILABLE)
        self.assertIsNone(obs.reason_code)
        # Sum 0.68; close 100 -> 147.058824
        self.assertAlmostEqual(obs.value, 100.0 / 0.68, places=6)

    @unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
    def test_real_mu_fy2023_era_windows_are_true_fiscal_quarters_excluded_as_losses(self):
        # The fiscal-year 2023 loss era assembles honestly under issuer-
        # declared identity: each window holds the four issuer-declared
        # fiscal quarters in sequence (no 182-day skip, no fabricated sum)
        # and is refused as non-positive. The continuity guard never fires
        # on this data; it stays as a structural safety net.
        result = _load_mu()
        guard_refusals = [
            o.evaluation_date
            for o in result.observations
            if o.reason_detail and "not consecutive" in o.reason_detail
        ]
        self.assertEqual(guard_refusals, [])
        era = [
            o
            for o in result.observations
            if "2023-09-28" <= o.evaluation_date <= "2024-09-25"
            and o.evaluation_date < "2024-09-26"
        ]
        self.assertTrue(era)
        true_fy2023 = ("2022-09-01", "2022-12-01", "2023-03-02", "2023-06-01", "2023-08-31")
        true_fy2024 = ("2023-11-30", "2024-02-29", "2024-05-30", "2024-08-29")
        for o in era:
            ends = sorted(c["period_end"] for c in o.eps_state["components"])
            self.assertTrue(
                set(ends) <= set(true_fy2023) | set(true_fy2024),
                f"window {ends} is not built from issuer-declared fiscal quarters",
            )
            gaps = [
                (
                    datetime.date.fromisoformat(b) - datetime.date.fromisoformat(a)
                ).days
                for a, b in zip(ends, ends[1:])
            ]
            for gap in gaps:
                self.assertLessEqual(gap, 100)
            self.assertEqual(o.status, "UNAVAILABLE")
            self.assertIsNone(o.value)
            self.assertEqual(o.reason_code, REASON_NON_POSITIVE_EPS)

    @unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
    def test_real_mu_valid_windows_are_consecutive_calendar_quarters(self):
        result = _load_mu()
        valid = [
            o
            for o in result.observations
            if o.status == STATUS_AVAILABLE and o.metric_id == METRIC_TTM_GAAP_DILUTED_PE
        ]
        self.assertTrue(valid)
        seen = set()
        for o in valid:
            ends = sorted(c["period_end"] for c in o.eps_state["components"])
            key = tuple(ends)
            if key in seen:
                continue
            seen.add(key)
            gaps = [
                (
                    datetime.date.fromisoformat(b) - datetime.date.fromisoformat(a)
                ).days
                for a, b in zip(ends, ends[1:])
            ]
            for gap in gaps:
                self.assertGreaterEqual(gap, 80)
                self.assertLessEqual(gap, 100)


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class TestMuDistributionState(unittest.TestCase):
    """The reference gate and the observation set on the real MU dataset."""

    @classmethod
    def setUpClass(cls):
        cls.result = _load_mu()

    def test_distribution_is_usable_for_reference_at_the_20_gate(self):
        dist = self.result.distribution
        self.assertEqual(dist.status, STATUS_USABLE_FOR_REFERENCE)
        self.assertTrue(dist.usable_for_reference)
        self.assertGreaterEqual(dist.sample_count, 20)
        self.assertEqual(dist.min_observations_required, 20)
        # Issuer-declared identity extends the valid series in both
        # directions: the FY2016/FY2017 windows assemble correctly from
        # 2017-10-26, and the FY2026 window carries the series to the last
        # frozen trading day.
        self.assertEqual(dist.period_start, "2017-10-26")
        self.assertEqual(dist.period_end, "2026-10-16")

    def test_the_median_is_pinned_against_an_independent_recomputation(self):
        values = sorted(
            o.value
            for o in self.result.observations
            if o.status == STATUS_AVAILABLE and o.value is not None
        )
        n = len(values)
        self.assertGreater(n, 0)
        median = (
            values[n // 2]
            if n % 2
            else (values[n // 2 - 1] + values[n // 2]) / 2
        )
        self.assertAlmostEqual(
            self.result.distribution.percentiles["median"], median, places=6
        )

    def test_current_snapshot_verifies_the_fy2026_ttm(self):
        # Issuer-declared identity places the furnished FQ4-26 in its true
        # (2026, Q4) position, so the latest-date snapshot now assembles the
        # real FY2026 window: three filed 10-Q facts plus the furnished
        # release figure, anchored at fiscal 2026's fourth quarter.
        snapshot = self.result.current_snapshot
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.status, STATUS_AVAILABLE)
        self.assertIsNone(snapshot.reason_code)
        eps_state = snapshot.eps_state
        self.assertEqual(
            eps_state["window_anchor"], {"fiscal_year": 2026, "fiscal_quarter": 4}
        )
        components = eps_state["components"]
        self.assertEqual(
            [(c["period_end"], c["value"]) for c in components],
            [
                ("2025-11-27", 4.60),
                ("2026-02-26", 12.07),
                ("2026-05-28", 24.67),
                ("2026-09-03", 32.87),
            ],
        )
        self.assertEqual(components[3]["evidence_class"], EVIDENCE_CLASS_FURNISHED)
        self.assertEqual(
            {c["fiscal_quarter"] for c in components}, {1, 2, 3, 4}
        )
        self.assertEqual({c["fiscal_year"] for c in components}, {2026})

        # The denominator is marked as a derived sum of the four directly
        # stated quarterly figures (74.21), and the issuer's audited annual
        # figure in force at the same date (74.33) is carried beside it: the
        # per-share non-additivity gap stays visible, never reconciled away.
        denominator = eps_state["quarter_denominator"]
        self.assertEqual(denominator, 74.21)
        derivation = eps_state["quarter_denominator_derivation"]
        self.assertTrue(derivation["derived_not_issuer_declared"])
        self.assertEqual(
            derivation["method"], "SUM_OF_FOUR_DIRECTLY_STATED_QUARTERLY_EPS"
        )
        annual = derivation["annual_eps_in_force_at_evaluation_date"]
        self.assertEqual(annual["value"], 74.33)
        self.assertEqual(annual["fiscal_year"], 2026)
        self.assertEqual(annual["accession"], "0000723125-26-000023")
        # The multiple itself: price on the last trading day divided by the
        # derived TTM EPS sum.
        self.assertAlmostEqual(
            snapshot.value, snapshot.price_state["close"] / 74.21, places=6
        )

    def test_restated_quarter_supersedes_only_from_its_own_usable_date(self):
        # The 2025-02-27 quarter appears twice in XBRL: original 10-Q
        # (0000723125-25-000009, usable 2025-03-21) and the FY2026 10-Q
        # comparative (0000723125-26-000006, usable 2026-03-19), both valued
        # 1.41. Every observation must carry exactly the latest version whose
        # usable date it has reached -- never an unreleased restatement, and
        # never the original once the restatement is in force.
        from collections import defaultdict

        concept = json.loads(
            (DATA / "eps_diluted_concept.json").read_text(encoding="utf-8")
        )
        versions = defaultdict(list)
        for fact in concept["units"]["USD/shares"]:
            if fact.get("end") == "2025-02-27" and fact.get("start"):
                span = (
                    datetime.date.fromisoformat(fact["end"])
                    - datetime.date.fromisoformat(fact["start"])
                ).days
                if 80 <= span <= 100:
                    versions[fact["accn"]].append(fact)
        self.assertEqual(
            set(versions),
            {"0000723125-25-000009", "0000723125-26-000006"},
        )

        carrying = [
            (o.evaluation_date, c["accession"])
            for o in self.result.observations
            if o.status == STATUS_AVAILABLE
            for c in o.eps_state["components"]
            if c["period_end"] == "2025-02-27"
        ]
        self.assertTrue(carrying)
        for evaluation_date, accession in carrying:
            self.assertIn(accession, versions)
            if accession == "0000723125-26-000006":
                self.assertGreaterEqual(evaluation_date, "2026-03-19")
            else:
                self.assertLess(evaluation_date, "2026-03-19")

    def test_two_runs_replay_identically(self):
        again = _load_mu()
        self.assertEqual(self.result.content_hash, again.content_hash)
        self.assertEqual(self.result.input_set_id, again.input_set_id)

    def test_annual_observations_never_substitute_for_ttm(self):
        for obs in self.result.annual_observations:
            self.assertFalse(obs.eps_state["substituted_for_ttm"])


class TestQuarterEpsEvidenceContract(unittest.TestCase):
    """The evidence object refuses anything but directly stated GAAP diluted."""

    def _valid(self, **overrides):
        base = dict(
            evidence_id="ev-x",
            issuer_id="CIK0000723125",
            evidence_class=EVIDENCE_CLASS_FURNISHED,
            form="8-K",
            accession="accn",
            period_end="2026-09-03",
            fiscal_year=2027,
            fiscal_quarter=4,
            value=32.87,
            audit_status="unaudited",
            acceptance_datetime="2026-09-30T16:02:22-04:00",
            usable_date="2026-10-01",
            usable_date_rule="acceptance_at_or_after_1600ET_next_trading_day",
            stated_directly=True,
        )
        base.update(overrides)
        return QuarterEpsEvidence(**base)

    def test_a_non_gaap_metric_is_rejected(self):
        with self.assertRaises(ValueError):
            self._valid(metric="NON_GAAP_DILUTED_EPS")

    def test_derived_evidence_is_rejected(self):
        with self.assertRaises(ValueError):
            self._valid(stated_directly=False)

    def test_an_unknown_evidence_class_is_rejected(self):
        with self.assertRaises(ValueError):
            self._valid(evidence_class="filed-furnished")

    def test_filed_and_furnished_coexist_as_distinct_classes(self):
        filed = self._valid(evidence_class=EVIDENCE_CLASS_FILED, form="10-K")
        furnished = self._valid()
        self.assertEqual(filed.evidence_class, EVIDENCE_CLASS_FILED)
        self.assertEqual(furnished.evidence_class, EVIDENCE_CLASS_FURNISHED)
        self.assertNotEqual(filed.to_dict(), furnished.to_dict())


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class TestMuHistoricalPfcfFiscalIdentity(unittest.TestCase):
    """The P/FCF pipeline shares the fiscal identity model: MU's drifted
    quarter ends must land in their true fiscal positions there too, and the
    FY2026 window must complete from the cumulative-span derivations."""

    @classmethod
    def setUpClass(cls):
        from historical_pfcf import ISSUER_CONFIGS as PFCF_CONFIGS
        from historical_pfcf import load_issuer_historical_pfcf

        cls.result = load_issuer_historical_pfcf(PFCF_CONFIGS["MU"])

    def test_current_snapshot_anchors_on_true_fy2026_q4(self):
        snapshot = self.result.current_snapshot
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.status, "AVAILABLE")
        anchor = snapshot.ttm_window["anchor"]
        self.assertEqual(
            anchor,
            {"fiscal_year": 2026, "fiscal_quarter": 4, "period_end": "2026-09-03"},
        )
        positions = snapshot.ttm_window["positions"]
        self.assertEqual(
            positions,
            [
                {"fiscal_year": 2026, "fiscal_quarter": q}
                for q in (1, 2, 3, 4)
            ],
        )

    def test_derived_fy2026_quarters_carry_their_true_fiscal_labels(self):
        # MU states cumulative cash flows: Q2 and Q3 are derived by
        # differencing the 6M/9M spans, and their period ends (2026-02-26,
        # 2026-05-28) are month-grid traps the old code got wrong.
        window = self.result.current_snapshot.ttm_window
        by_end = {q["period_end"]: q for q in window["quarters"]}
        self.assertEqual(by_end["2025-11-27"]["fiscal_quarter"], 1)
        self.assertEqual(by_end["2026-02-26"]["fiscal_quarter"], 2)
        self.assertEqual(by_end["2026-05-28"]["fiscal_quarter"], 3)
        self.assertEqual(by_end["2026-09-03"]["fiscal_quarter"], 4)
        self.assertTrue(
            all(q["identity_source"] for q in window["quarters"]),
            "each discrete quarter should carry its identity provenance",
        )

    def test_no_valid_window_skips_a_calendar_quarter(self):
        # Quarter ends inside every valid P/FCF window must be consecutive
        # quarters in calendar time (~13 weeks apart); a 182-day gap would
        # mean a skipped real quarter presented as a TTM sum.
        for obs in self.result.distribution.observations:
            ends = sorted(
                datetime.date.fromisoformat(q["period_end"])
                for q in obs["ttm_window"]["quarters"]
            )
            gaps = [(b - a).days for a, b in zip(ends, ends[1:])]
            for gap in gaps:
                self.assertGreaterEqual(gap, 80)
                self.assertLessEqual(gap, 100)


if __name__ == "__main__":
    unittest.main()
