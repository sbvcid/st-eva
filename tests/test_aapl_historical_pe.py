"""AAPL canonical historical P/E dataset tests.

These mirror the MSFT canonical tests and assert that the promoted AAPL Q4
evidence dataset (FY2021-FY2025) is self-contained in version-controlled data:
the tracked canonical directory alone supports schema, cross-file acceptance
consistency, and the production loader. The git-ignored research/ tree is never
required at test runtime.
"""
import builtins
import datetime
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from historical_pe import (
    ISSUER_CONFIGS,
    STATUS_USABLE_FOR_REFERENCE,
    EVIDENCE_CLASS_FURNISHED,
    IssuerHistoricalPeConfig,
    canonical_json_hash,
    load_aapl_historical_pe,
    load_issuer_historical_pe,
    resolve_usable_date,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_DIR = REPO_ROOT / "data" / "historical_pe" / "AAPL"

SOURCE_TYPE = "SEC_8K_ITEM_2_02_EX_99_1"

# The five Q4 Item 2.02 EX-99.1 records the production loader adopts.
EXPECTED_Q4_ACCESSIONS = {
    "0000320193-21-000104": ("2021-09-25", 1.24, "2021-10-29"),
    "0000320193-22-000107": ("2022-09-24", 1.29, "2022-10-28"),
    "0000320193-23-000104": ("2023-09-30", 1.46, "2023-11-03"),
    "0000320193-24-000120": ("2024-09-28", 0.97, "2024-11-01"),
    "0000320193-25-000077": ("2025-09-27", 1.85, "2025-10-31"),
}


def _load_json(name):
    return json.loads((CANONICAL_DIR / name).read_text(encoding="utf-8"))


def _adopted_records():
    q4 = _load_json("q4_evidence_records.json")
    return [
        r for r in q4["records"]
        if r.get("source_type") == SOURCE_TYPE and r.get("meets_st_eva_q4_evidence")
    ]


def _trading_days():
    payload = _load_json("daily_prices.json")["chart"]["result"][0]
    return [
        datetime.datetime.fromtimestamp(t, datetime.timezone.utc).date().isoformat()
        for t in payload["timestamp"]
    ]


class TestAaplCanonicalDatasetIsSelfContained(unittest.TestCase):
    def test_aapl_config_points_at_tracked_canonical_dir(self):
        config = ISSUER_CONFIGS["AAPL"]
        self.assertEqual(config.issuer_id, "CIK0000320193")
        self.assertEqual(config.fye_month, 9)
        resolved = (REPO_ROOT / config.data_dir).resolve()
        self.assertEqual(resolved, CANONICAL_DIR.resolve())
        self.assertNotIn("research", resolved.parts)

    def test_canonical_inputs_are_present(self):
        for name in (
            "daily_prices.json",
            "eps_diluted_concept.json",
            "filing_acceptance_evidence.json",
            "q4_evidence_records.json",
            "manifest.json",
        ):
            self.assertTrue((CANONICAL_DIR / name).is_file(), f"missing canonical input: {name}")

    def test_production_load_succeeds_without_research_dir(self):
        """The production path must not touch the git-ignored research/ tree."""
        research_root = REPO_ROOT / "research"

        real_exists, real_is_dir, real_open = Path.exists, Path.is_dir, builtins.open
        real_os_open = os.open

        def _under_research(path) -> bool:
            return str(path).replace("\\", "/").startswith(
                str(research_root).replace("\\", "/")
            )

        def _blocked_exists(self):
            if _under_research(self):
                raise AssertionError(f"production path touched research/: {self}")
            return real_exists(self)

        def _blocked_is_dir(self):
            if _under_research(self):
                raise AssertionError(f"production path touched research/: {self}")
            return real_is_dir(self)

        def _blocked_open(file, *a, **kw):
            if _under_research(getattr(file, "__str__", lambda: file)()):
                raise AssertionError(f"production path opened research/ file: {file}")
            return real_open(file, *a, **kw)

        os.open = _blocked_open
        Path.exists = _blocked_exists
        Path.is_dir = _blocked_is_dir
        builtins.open = _blocked_open
        try:
            result = load_aapl_historical_pe(enable_furnished=True)
        finally:
            Path.exists = real_exists
            Path.is_dir = real_is_dir
            builtins.open = real_open
            os.open = real_os_open

        self.assertEqual(result.distribution.status, STATUS_USABLE_FOR_REFERENCE)
        self.assertEqual(len(result.observations), 36)
        self.assertEqual(result.distribution.sample_count, 28)


class TestAaplQ4EvidenceSchema(unittest.TestCase):
    def test_loader_adopts_exactly_the_five_expected_q4_records(self):
        adopted = _adopted_records()
        self.assertEqual(len(adopted), 5, "expected exactly 5 adopted Q4 records")
        self.assertEqual({r["accession"] for r in adopted}, set(EXPECTED_Q4_ACCESSIONS))

    def test_canonical_q4_file_contains_only_the_five_adopted_records(self):
        """Canonical boundary matches MSFT: only evidence-gate-passing records."""
        q4 = _load_json("q4_evidence_records.json")
        self.assertEqual(len(q4["records"]), 5,
                         "production canonical must contain only the 5 adopted records")
        for r in q4["records"]:
            with self.subTest(accession=r.get("accession")):
                self.assertEqual(r.get("source_type"), SOURCE_TYPE)
                self.assertTrue(r.get("meets_st_eva_q4_evidence"))

    def test_each_adopted_record_matches_expected_identity(self):
        adopted = {r["accession"]: r for r in _adopted_records()}
        for accn, (period_end, eps, _usable) in EXPECTED_Q4_ACCESSIONS.items():
            with self.subTest(accession=accn):
                r = adopted[accn]
                self.assertEqual(r.get("source_type"), SOURCE_TYPE)
                self.assertEqual(r.get("form"), "8-K")
                self.assertEqual(r.get("fiscal_quarter"), 4)
                self.assertEqual(r.get("quarter_period_end"), period_end)
                self.assertEqual(r.get("diluted_eps"), eps)
                self.assertTrue(r.get("meets_st_eva_q4_evidence"))
                self.assertTrue(r.get("pit_usable_date"))
                self.assertTrue(r.get("item_2_02_furnished_not_filed"))
                self.assertTrue(r.get("document_identifier"), "missing EX-99.1 exhibit identity")
                self.assertIn(accn.replace("-", ""), (r.get("source_url") or ""))

    def test_no_duplicate_or_mismatched_adopted_records(self):
        adopted = _adopted_records()
        keys = [(r["fiscal_year"], r["fiscal_quarter"], r["quarter_period_end"]) for r in adopted]
        self.assertEqual(len(keys), len(set(keys)), "duplicate fiscal quarter keys among adopted records")
        self.assertEqual(len({r["accession"] for r in adopted}), len(adopted))
        years = sorted(r["fiscal_year"] for r in adopted)
        self.assertEqual(years, [2021, 2022, 2023, 2024, 2025])

    def test_loader_uses_exactly_the_five_furnished_q4_components(self):
        result = load_aapl_historical_pe(enable_furnished=True)
        furnished = {}
        for obs in result.observations:
            for comp in obs.eps_state.get("components") or []:
                if str(comp.get("evidence_id", "")).startswith("ev-furn-"):
                    furnished[comp["accession"]] = comp
        self.assertEqual(set(furnished), set(EXPECTED_Q4_ACCESSIONS))
        for accn, comp in furnished.items():
            with self.subTest(accession=accn):
                self.assertEqual(comp.get("form"), "8-K")
                self.assertEqual(comp.get("evidence_class"), EVIDENCE_CLASS_FURNISHED)
                self.assertEqual(comp.get("usable_date"), EXPECTED_Q4_ACCESSIONS[accn][2])
                self.assertTrue(comp.get("source_document"), "source_document is None (document_identifier schema mismatch)")
                self.assertTrue(comp.get("source_url"))
                self.assertTrue(comp.get("content_sha256"))


class TestAaplAcceptanceEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = _load_json("filing_acceptance_evidence.json")
        cls.by_accession = {r["accession"]: r for r in cls.rows}
        cls.q4 = {r["accession"]: r for r in _adopted_records()}
        cls.trading_days = _trading_days()

    def test_existing_10k_10q_evidence_preserved(self):
        tenk_tenq = [r for r in self.rows if r["form"] in ("10-K", "10-Q")]
        self.assertGreaterEqual(len(tenk_tenq), 43, "existing 10-K/10-Q acceptance evidence was deleted")
        for r in self.rows:
            for key in ("accession", "form", "period_end", "acceptance_datetime_header_et"):
                self.assertIn(key, r, f"acceptance row {r.get('accession')} missing {key}")

    def test_five_8k_item_2_02_rows_present_in_tracked_acceptance(self):
        for accn in EXPECTED_Q4_ACCESSIONS:
            with self.subTest(accession=accn):
                row = self.by_accession.get(accn)
                self.assertIsNotNone(row, f"{accn} missing from tracked acceptance evidence")
                self.assertEqual(row["form"], "8-K")
                self.assertTrue(row.get("sec_items", "").startswith("2.02"))
                self.assertEqual(row.get("acceptance_datetime_header_raw"),
                                 row["acceptance_datetime_header_et"].replace("-", "").replace(":", "").replace("T", "")[:14])

    def test_acceptance_matches_q4_records_and_time_rule(self):
        """Acceptance evidence must independently confirm each Q4 record's datetime and usable date.

        The check is not the boolean meets_st_eva_q4_evidence flag: it re-derives
        the usable date from the tracked acceptance datetime with the repo's own
        16:00 ET rule and compares it to the record.
        """
        for accn, rec in self.q4.items():
            with self.subTest(accession=accn):
                row = self.by_accession[accn]
                self.assertEqual(row["acceptance_datetime_header_et"], rec["acceptance_datetime"])
                usable, rule = resolve_usable_date(
                    datetime.datetime.fromisoformat(row["acceptance_datetime_header_et"]),
                    self.trading_days,
                )
                self.assertEqual(usable, rec["pit_usable_date"])
                self.assertEqual(usable, EXPECTED_Q4_ACCESSIONS[accn][2])

    def test_post_cutoff_acceptance_rolls_to_next_trading_day(self):
        cutoff = datetime.time(16, 0)
        for accn in EXPECTED_Q4_ACCESSIONS:
            with self.subTest(accession=accn):
                acc_dt = datetime.datetime.fromisoformat(self.by_accession[accn]["acceptance_datetime_header_et"])
                self.assertGreaterEqual((acc_dt.hour, acc_dt.minute), (cutoff.hour, cutoff.minute))
                usable, _rule = resolve_usable_date(acc_dt, self.trading_days)
                self.assertGreater(usable, acc_dt.date().isoformat(),
                                   "post-16:00 ET acceptance must not be usable the same day")


class TestAaplProductionMetadataAndManifest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.q4 = _load_json("q4_evidence_records.json")
        cls.manifest = _load_json("manifest.json")

    def test_q4_metadata_declares_production_role(self):
        meta = self.q4.get("metadata")
        self.assertIsInstance(meta, dict, "q4_evidence_records.json missing metadata block")
        self.assertEqual(meta.get("canonical_role"), "production")
        self.assertEqual(meta.get("total_q4_records"), 5)
        self.assertEqual(len(self.q4["records"]), 5, "canonical record set must equal total_q4_records")
        self.assertEqual(meta.get("evidence_class"), "furnished")
        self.assertEqual(meta.get("form_type"), "8-K")
        self.assertEqual(meta.get("sec_item"), "Item 2.02")
        self.assertNotIn("not_production", self.q4, "stale not_production marker still present")
        self.assertIn("document_identifier", meta.get("schema_notes", ""), "schema note must warn about document_identifier")

    def test_rejected_candidates_have_a_documented_retention_location(self):
        """The 15 non-adopted candidates are not in canonical but must be retained.

        The canonical metadata records the distinct source-study candidate count and
        the retention path, and the tracked research manifest indexes that file, so
        the rejection records are not silently dropped.
        """
        meta = self.q4["metadata"]
        self.assertEqual(meta.get("source_study_candidate_records"), 20)
        retained_at = meta.get("rejected_records_retained_at")
        self.assertEqual(retained_at, "research/experiments/aapl-historical-pe-poc/q4_study/out/q4_evidence_records.json")
        self.assertEqual(meta.get("source_file"), retained_at)

        manifest_path = REPO_ROOT / "research" / "RESEARCH-ARCHIVE-MANIFEST.json"
        self.assertTrue(manifest_path.is_file(), "tracked research archive manifest missing")
        archived = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        rel = "aapl-historical-pe-poc/q4_study/out/q4_evidence_records.json"
        entry = next((f for f in archived["files"] if f["path"] == rel), None)
        self.assertIsNotNone(entry, "candidate/refusal records are not indexed in the tracked research manifest")
        self.assertEqual(entry["source_sha256"].lower(), entry["archived_sha256"].lower())

    def test_q4_content_hash_is_valid(self):
        self.assertEqual(
            self.q4["content_hash"],
            canonical_json_hash({k: v for k, v in self.q4.items() if k != "content_hash"}),
        )

    def test_manifest_role_and_hashes_match_canonical_files(self):
        self.assertEqual(self.manifest.get("role"), "production")
        files = self.manifest["provenance"]["files"]
        for name in ("daily_prices.json", "eps_diluted_concept.json",
                     "filing_acceptance_evidence.json", "q4_evidence_records.json"):
            with self.subTest(file=name):
                actual = hashlib.sha256((CANONICAL_DIR / name).read_bytes()).hexdigest()
                self.assertEqual(files[name]["content_sha256"], actual)

    def test_production_loader_is_reproducible_and_changes_with_inputs(self):
        base = load_aapl_historical_pe(enable_furnished=True)
        again = load_aapl_historical_pe(enable_furnished=True)
        self.assertEqual(base.input_set_id, again.input_set_id)
        self.assertEqual(base.content_hash, again.content_hash)

        tmp = Path(tempfile.mkdtemp(prefix="aapl_q4_"))
        try:
            work = tmp / "AAPL"
            shutil.copytree(CANONICAL_DIR, work)
            target = work / "q4_evidence_records.json"
            payload = json.loads(target.read_text(encoding="utf-8"))
            payload["records"][0]["diluted_eps"] = 12.34
            target.write_text(json.dumps(payload, indent=2), encoding="utf-8")

            cfg = IssuerHistoricalPeConfig(
                ticker="AAPL", issuer_id="CIK0000320193", fye_month=9,
                data_dir=work, canonical_path=None,
            )
            mutated = load_issuer_historical_pe(cfg, enable_furnished=True)
            self.assertNotEqual(base.input_set_id, mutated.input_set_id)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
