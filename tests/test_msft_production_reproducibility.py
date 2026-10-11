"""MSFT production-path reproducibility tests.

These tests assert that the production runner reproduces the verified POC
expectations from the *tracked canonical dataset only*. The git-ignored
research/ POC tree must never be required at test runtime.
"""
import builtins
import json
import os
import unittest
from pathlib import Path

from historical_pe import (
    ISSUER_CONFIGS,
    STATUS_USABLE_FOR_REFERENCE,
    EVIDENCE_CLASS_FURNISHED,
    load_issuer_historical_pe,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "msft_historical_pe_expected.json"
CANONICAL_DIR = REPO_ROOT / "data" / "historical_pe" / "MSFT"

EXPECTED_Q4_ACCESSIONS = {
    "0001193125-21-225746",
    "0001193125-22-202034",
    "0000950170-23-034400",
    "0000950170-24-087835",
    "0000950170-25-100226",
    "0001193125-26-323632",
}


def _load_fixture():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


class TestCanonicalDatasetIsSelfContained(unittest.TestCase):
    """The production input set must not depend on the git-ignored research tree."""

    def test_msft_config_points_at_tracked_canonical_dir(self):
        config = ISSUER_CONFIGS["MSFT"]
        self.assertEqual(config.issuer_id, "CIK0000789019")
        self.assertEqual(config.fye_month, 6)
        resolved = (REPO_ROOT / config.data_dir).resolve()
        self.assertEqual(resolved, CANONICAL_DIR.resolve())
        self.assertNotIn("research", resolved.parts)

    def test_canonical_inputs_are_tracked_and_present(self):
        for name in (
            "daily_prices.json",
            "eps_diluted_concept.json",
            "filing_acceptance_evidence.json",
            "q4_evidence_records.json",
            "manifest.json",
        ):
            self.assertTrue((CANONICAL_DIR / name).is_file(), f"missing canonical input: {name}")

    def test_production_load_succeeds_without_research_dir(self):
        """Load the production path while every research/ access raises.

        This proves a clean checkout reproduces the result without the POC tree.
        On a clean checkout research/ is absent, so the guard additionally asserts
        the loader never touches it.
        """
        research_root = REPO_ROOT / "research"
        research_present = research_root.exists()

        real_exists, real_is_dir, real_open = (
            Path.exists, Path.is_dir, builtins.open
        )
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
            result = load_issuer_historical_pe(ISSUER_CONFIGS["MSFT"], enable_furnished=True)
        finally:
            Path.exists = real_exists
            Path.is_dir = real_is_dir
            builtins.open = real_open
            os.open = real_os_open

        self.assertEqual(result.distribution.status, STATUS_USABLE_FOR_REFERENCE)
        self.assertEqual(result.distribution.sample_count, 24)
        self.assertEqual(len(result.observations), 27)


class TestMsftMatchesPocRegressionFixture(unittest.TestCase):
    """Compare production output against the committed POC-derived fixture."""

    @classmethod
    def setUpClass(cls):
        cls.fixture = _load_fixture()
        cls.result = load_issuer_historical_pe(ISSUER_CONFIGS["MSFT"], enable_furnished=True)
        cls.by_date = {o.evaluation_date: o for o in cls.result.observations}

    def test_evaluation_date_count_matches_fixture(self):
        self.assertEqual(len(self.by_date), self.fixture["expected"]["evaluation_date_count"])

    def test_evaluation_dates_match_fixture_exactly(self):
        expected = [o["evaluation_date"] for o in self.fixture["observations"]]
        self.assertEqual(sorted(self.by_date), sorted(expected))

    def test_availability_statuses_match_fixture(self):
        for exp in self.fixture["observations"]:
            with self.subTest(date=exp["evaluation_date"]):
                self.assertEqual(self.by_date[exp["evaluation_date"]].status, exp["status"])

    def test_available_count_matches_fixture(self):
        self.assertEqual(self.result.distribution.sample_count, self.fixture["expected"]["available_count"])
        self.assertGreaterEqual(self.result.distribution.sample_count, 20)

    def test_per_date_pe_matches_fixture_within_tolerance(self):
        tol = self.fixture["tolerance"]["pe_abs"]
        compared = 0
        for exp in self.fixture["observations"]:
            with self.subTest(date=exp["evaluation_date"]):
                got = self.by_date[exp["evaluation_date"]].value
                if exp["pe"] is None:
                    self.assertIsNone(got)
                    continue
                self.assertIsNotNone(got)
                self.assertAlmostEqual(got, exp["pe"], delta=tol)
                compared += 1
        self.assertEqual(compared, self.fixture["expected"]["available_count"])

    def test_distribution_matches_fixture_within_tolerance(self):
        tol = self.fixture["tolerance"]["distribution_abs"]
        dist = self.result.distribution
        exp = self.fixture["expected"]["distribution"]
        self.assertAlmostEqual(dist.mean, exp["mean"], delta=tol)
        self.assertAlmostEqual(dist.std, exp["std"], delta=tol)
        self.assertAlmostEqual(dist.min, exp["min"], delta=tol)
        self.assertAlmostEqual(dist.max, exp["max"], delta=tol)

    def test_point_in_time_usable_dates_respect_16_et_cutoff(self):
        """Every EPS component is usable no earlier than its filing acceptance."""
        import datetime

        cutoff = datetime.time(16, 0)
        checked = 0
        for date, obs in self.by_date.items():
            for comp in obs.eps_state.get("components") or []:
                acc = comp.get("acceptance_datetime")
                if not acc:
                    continue
                acc_dt = datetime.datetime.fromisoformat(acc)
                usable = comp.get("usable_date")
                self.assertIsNotNone(usable, f"{date}: component missing usable_date")
                # Acceptance at/after 16:00 ET must not be usable the same day.
                local = acc_dt.timetz()
                after_cutoff = (local.hour, local.minute) >= (cutoff.hour, cutoff.minute)
                if after_cutoff:
                    self.assertGreater(
                        usable, acc_dt.date().isoformat(),
                        f"{date}: post-cutoff filing usable same day",
                    )
                else:
                    self.assertGreaterEqual(usable, acc_dt.date().isoformat())
                checked += 1
        self.assertGreater(checked, 0)

    def test_furnished_q4_components_carry_non_empty_source_identifier(self):
        """Regression: source_document silently became None via a schema mismatch."""
        seen = {}
        for obs in self.by_date.values():
            for comp in obs.eps_state.get("components") or []:
                if str(comp.get("evidence_id", "")).startswith("ev-furn-"):
                    seen[comp["evidence_id"]] = comp
        self.assertEqual(len(seen), len(EXPECTED_Q4_ACCESSIONS))
        for evidence_id, comp in sorted(seen.items()):
            with self.subTest(evidence_id=evidence_id):
                self.assertEqual(comp.get("evidence_class"), EVIDENCE_CLASS_FURNISHED)
                self.assertTrue(
                    comp.get("source_document"),
                    f"{evidence_id}: source_document is None (document_identifier schema mismatch)",
                )
                self.assertTrue(comp.get("source_url"))
                self.assertTrue(comp.get("content_sha256"))
                self.assertEqual(comp.get("form"), "8-K")
                self.assertIn(comp.get("accession"), EXPECTED_Q4_ACCESSIONS)
                self.assertTrue(str(evidence_id).startswith("ev-furn-"))
                self.assertIn(comp["accession"], evidence_id)

    def test_ttm_components_match_fixture_evidence_and_values(self):
        """Component identities match the POC per date.

        Provenance semantics differ by evidence class and are asserted accordingly:
        furnished 8-K components carry the per-exhibit document hash from the Q4
        evidence file, while filed XBRL components carry the digest of the canonical
        EPS concept file (the loader has no per-filing document hash).
        """
        import hashlib

        eps_digest = hashlib.sha256(
            (CANONICAL_DIR / "eps_diluted_concept.json").read_bytes()
        ).hexdigest()

        checked = 0
        furnished_dates = 0
        for exp in self.fixture["observations"]:
            obs = self.by_date[exp["evaluation_date"]]
            got = {
                c["accession"]: c
                for c in (obs.eps_state.get("components") or [])
                if c.get("accession")
            }
            want = {c["accession"]: c for c in exp["components"]}
            with self.subTest(date=exp["evaluation_date"]):
                self.assertEqual(set(got), set(want))
                for accn, w in want.items():
                    self.assertEqual(got[accn].get("form"), w["form"])
                    self.assertEqual(got[accn].get("evidence_class"), w["evidence_class"])
                    self.assertTrue(got[accn].get("value") is not None)
                    if w["evidence_class"] == EVIDENCE_CLASS_FURNISHED:
                        self.assertEqual(got[accn].get("content_sha256"), w["content_sha256"])
                        self.assertEqual(got[accn].get("source_document"), w["source_document"])
                    else:
                        self.assertEqual(got[accn].get("content_sha256"), eps_digest)
                if any(c["evidence_class"] == EVIDENCE_CLASS_FURNISHED for c in want.values()):
                    furnished_dates += 1
            checked += 1
        self.assertEqual(checked, self.fixture["expected"]["evaluation_date_count"])
        self.assertGreater(furnished_dates, 0)


class TestMsftInputSetIdDeterminism(unittest.TestCase):
    """input_set_id must be stable for identical inputs and move for real changes."""

    def test_input_set_id_is_stable_across_runs(self):
        a = load_issuer_historical_pe(ISSUER_CONFIGS["MSFT"], enable_furnished=True)
        b = load_issuer_historical_pe(ISSUER_CONFIGS["MSFT"], enable_furnished=True)
        self.assertEqual(a.input_set_id, b.input_set_id)
        self.assertEqual(a.content_hash, b.content_hash)

    def test_input_set_id_changes_when_q4_evidence_changes(self):
        import hashlib
        import shutil
        import tempfile

        base = load_issuer_historical_pe(ISSUER_CONFIGS["MSFT"], enable_furnished=True)

        tmp = Path(tempfile.mkdtemp(prefix="msft_q4_"))
        try:
            work = tmp / "MSFT"
            shutil.copytree(CANONICAL_DIR, work)
            target = work / "q4_evidence_records.json"
            payload = json.loads(target.read_text(encoding="utf-8"))
            payload["records"][0]["diluted_eps"] = 12.34
            target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

            from historical_pe import IssuerHistoricalPeConfig

            cfg = IssuerHistoricalPeConfig(
                ticker="MSFT",
                issuer_id="CIK0000789019",
                fye_month=6,
                data_dir=work,
                canonical_path=None,
            )
            mutated = load_issuer_historical_pe(cfg, enable_furnished=True)
            self.assertNotEqual(base.input_set_id, mutated.input_set_id)
            self.assertNotEqual(base.content_hash, mutated.content_hash)
            self.assertNotEqual(
                hashlib.sha256(target.read_bytes()).hexdigest(),
                hashlib.sha256((CANONICAL_DIR / "q4_evidence_records.json").read_bytes()).hexdigest(),
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_input_set_id_changes_when_price_input_changes(self):
        import shutil
        import tempfile

        base = load_issuer_historical_pe(ISSUER_CONFIGS["MSFT"], enable_furnished=True)

        tmp = Path(tempfile.mkdtemp(prefix="msft_px_"))
        try:
            work = tmp / "MSFT"
            shutil.copytree(CANONICAL_DIR, work)
            target = work / "daily_prices.json"
            payload = json.loads(target.read_text(encoding="utf-8"))
            payload["chart"]["result"][0]["indicators"]["quote"][0]["close"][5] = 999.0
            target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

            from historical_pe import IssuerHistoricalPeConfig

            cfg = IssuerHistoricalPeConfig(
                ticker="MSFT",
                issuer_id="CIK0000789019",
                fye_month=6,
                data_dir=work,
                canonical_path=None,
            )
            mutated = load_issuer_historical_pe(cfg, enable_furnished=True)
            self.assertNotEqual(base.input_set_id, mutated.input_set_id)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestAaplRegressionBaseline(unittest.TestCase):
    """The MSFT change must not disturb the AAPL baseline."""

    @classmethod
    def setUpClass(cls):
        from historical_pe import load_aapl_historical_pe

        cls.result = load_aapl_historical_pe(enable_furnished=True)

    def test_aapl_retains_31_observations(self):
        self.assertEqual(self.result.distribution.sample_count, 31)
        self.assertEqual(len(self.result.observations), 31)
        self.assertEqual(self.result.distribution.status, STATUS_USABLE_FOR_REFERENCE)
        self.assertTrue(self.result.distribution.usable_for_reference)

    def test_aapl_excluded_count_is_zero(self):
        self.assertEqual(len(self.result.distribution.excluded_observations), 0)


if __name__ == "__main__":
    unittest.main()