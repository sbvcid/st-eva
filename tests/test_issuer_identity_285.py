"""
2.85 -- adversarial tests for canonical issuer identity.

## What is being defended

The defect was that a filename decided who an issuer was, and twelve payloads are
named `<CIK>.json`. A test that only asserted `unique_issuers == 63` would pass
against a loader that happened to produce 63 for unrelated reasons -- for instance
one that deduplicated by path, or that skipped the anomalies entirely rather than
resolving them.

So the bulk of these tests drive `resolve_issuer` and `load_companyfacts_payloads`
with synthetic payloads covering the five cases that matter, and the corpus count
is asserted only as a measured result alongside them.

The five synthetic cases:

    normal filename + matching payload CIK
    nonstandard filename + valid payload CIK
    filename CIK that disagrees with the payload
    two payloads for one issuer
    payload with no usable CIK

The last two are the ones that would each reintroduce the defect: a fallback to
the filename would invent an issuer, and a non-merging loader would duplicate one.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import issuer_identity  # noqa: E402
import issuer_identity_audit_285 as audit  # noqa: E402
from candidate_discovery_repair_277 import held_payloads  # noqa: E402
from semantic_gap_census_275 import load_payloads  # noqa: E402

H = os.path.join(ROOT, "experiments", "003-llm-evidence-retrieval", "harness")
ARTEFACT = os.path.join(H, "285-issuer-identity-canonicalisation.json")
CENSUS_275 = os.path.join(H, "275-semantic-gap-census.json")
AUDIT_283 = os.path.join(H, "283-r-and-d-source-silent-filer-audit.json")

_RESULT = None


def result():
    global _RESULT
    if _RESULT is None:
        with io.open(ARTEFACT, encoding="utf-8") as handle:
            _RESULT = json.load(handle)
    return _RESULT


def setUpModule():
    if not os.path.exists(ARTEFACT):
        raise unittest.SkipTest("run issuer_identity_audit_285.py first")


class SyntheticPayloads(unittest.TestCase):
    """Five cases, written to disk so the loader is exercised end to end."""

    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp()
        self.cik_map = {"26172": "CMI", "1549084": "CHRN"}

    def write(self, filename, document):
        path = os.path.join(self.dir, filename)
        with io.open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(document) if document is not None else "not json")
        return path

    # 1. canonical ------------------------------------------------------------
    def test_normal_filename_with_a_matching_cik(self) -> None:
        path = self.write("CMI_companyfacts.json",
                          {"cik": 26172, "entityName": "Cummins"})
        record = issuer_identity.resolve_issuer(
            json.load(io.open(path, encoding="utf-8")), path, self.cik_map)
        self.assertEqual(record["identity_status"],
                         issuer_identity.CANONICAL_MATCH)
        self.assertEqual(record["canonical_issuer_cik"], "26172")
        self.assertEqual(record["resolved_ticker"], "CMI")
        self.assertEqual(record["key"], "CMI")
        self.assertEqual(record["resolved_from"], "cik_join")

    # 2. nonstandard filename -------------------------------------------------
    def test_nonstandard_filename_with_a_valid_cik(self) -> None:
        path = self.write("0000026172.json",
                          {"cik": 26172, "entityName": "Cummins"})
        record = issuer_identity.resolve_issuer(
            json.load(io.open(path, encoding="utf-8")), path, self.cik_map)
        self.assertEqual(record["identity_status"],
                         issuer_identity.NONCANONICAL_FILENAME)
        self.assertEqual(record["filename_derived_token"], "0000026172.JSON")
        self.assertEqual(record["canonical_issuer_cik"], "26172")
        self.assertEqual(record["key"], "CMI")
        self.assertFalse(record["filename_matches_expected_pattern"])

    # 3. filename disagreement ------------------------------------------------
    def test_filename_cik_that_disagrees_with_the_payload(self) -> None:
        path = self.write("0001549084.json",
                          {"cik": 26172, "entityName": "Cummins"})
        record = issuer_identity.resolve_issuer(
            json.load(io.open(path, encoding="utf-8")), path, self.cik_map)
        self.assertEqual(record["identity_status"],
                         issuer_identity.FILENAME_CIK_MISMATCH)
        self.assertFalse(record["filename_cik_equals_payload_cik"])
        # The payload's CIK wins; the filename does not create an issuer.
        self.assertEqual(record["canonical_issuer_cik"], "26172")
        self.assertEqual(record["key"], "CMI")

    # 4. two payloads, one issuer ---------------------------------------------
    def test_two_payloads_for_one_issuer_collapse(self) -> None:
        self.write("CMI_companyfacts.json",
                   {"cik": 26172, "entityName": "Cummins"})
        self.write("0000026172.json",
                   {"cik": 26172, "entityName": "Cummins"})
        mapping, records = issuer_identity.load_companyfacts_payloads(
            self.dir, self.cik_map)
        self.assertEqual(len(records), 2)
        self.assertEqual(len(mapping), 1)
        self.assertIn("CMI", mapping)
        self.assertNotIn("0000026172.JSON", mapping)

    # 5. missing or unusable CIK ---------------------------------------------
    def test_a_missing_payload_cik_does_not_fall_back_to_the_filename(self) -> None:
        path = self.write("ZZZZ_companyfacts.json",
                          {"entityName": "No CIK Here"})
        record = issuer_identity.resolve_issuer(
            json.load(io.open(path, encoding="utf-8")), path, self.cik_map)
        self.assertEqual(record["identity_status"],
                         issuer_identity.MISSING_PAYLOAD_CIK)
        self.assertIsNone(record["canonical_issuer_cik"])
        self.assertIsNone(record["resolved_ticker"])
        self.assertTrue(record["key"].startswith("UNRESOLVED:"))
        self.assertEqual(record["resolved_from"], "unresolved")

    def test_an_unusable_cik_is_unresolved_rather_than_guessed(self) -> None:
        path = self.write("CMI_companyfacts.json", {"cik": "not-a-number"})
        record = issuer_identity.resolve_issuer(
            json.load(io.open(path, encoding="utf-8")), path, self.cik_map)
        self.assertEqual(record["identity_status"],
                         issuer_identity.MISSING_PAYLOAD_CIK)

    def test_an_unknown_cik_is_reported_not_resolved_by_name(self) -> None:
        path = self.write("0009999999.json", {"cik": 9999999})
        record = issuer_identity.resolve_issuer(
            json.load(io.open(path, encoding="utf-8")), path, self.cik_map)
        self.assertIsNone(record["resolved_ticker"])
        self.assertEqual(record["resolved_from"], "cik_only")
        self.assertEqual(record["key"], "CIK:9999999")

    def test_an_unreadable_payload_does_not_hide_under_a_resolved_key(self) -> None:
        self.write("CMI_companyfacts.json", None)
        mapping, records = issuer_identity.load_companyfacts_payloads(
            self.dir, self.cik_map)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["identity_status"],
                         issuer_identity.MISSING_PAYLOAD_CIK)
        self.assertIn("CMI", mapping,
                      "an unreadable payload must not silently disappear")


class TestCanonicalIdentityComesFromThePayload(unittest.TestCase):
    """1."""

    def test_the_resolver_reads_the_document_not_the_name(self) -> None:
        source = io.open(os.path.join(ROOT, "issuer_identity.py"),
                         encoding="utf-8").read()
        self.assertIn('document or {}).get("cik")', source)

    def test_and_normalisation_strips_leading_zeros(self) -> None:
        self.assertEqual(issuer_identity.normalise_cik("0000026172"), "26172")
        self.assertEqual(issuer_identity.normalise_cik(26172), "26172")
        self.assertEqual(issuer_identity.normalise_cik("0"), "0")
        self.assertIsNone(issuer_identity.normalise_cik(""))
        self.assertIsNone(issuer_identity.normalise_cik("abc"))
        self.assertIsNone(issuer_identity.normalise_cik(None))

    def test_and_no_tracked_reader_derives_identity_from_a_filename(self) -> None:
        for module in sorted(audit.UPDATED_READERS):
            path = os.path.join(ROOT, module)
            if not os.path.exists(path):
                continue
            with io.open(path, encoding="utf-8") as f:
                body = f.read()
            self.assertIn("issuer_identity", body, module)
            self.assertNotIn('split("_")[0]', body, module)

    def test_and_the_only_remaining_uses_are_diagnostics(self) -> None:
        """
        `issuer_identity` exposes the filename token on purpose, as a
        diagnostic, and the 2.84 reconciliation quotes it when describing the
        defect. Nothing that *decides* an identity may still do it.
        """
        allowed = {"issuer_identity.py", "issuer_identity_audit_285.py",
                   "cohort_reconciliation_284.py"}
        offenders = []
        for name in sorted(os.listdir(ROOT)):
            if not name.endswith(".py") or name in allowed:
                continue
            with io.open(os.path.join(ROOT, name), encoding="utf-8",
                         errors="replace") as f:
                if 'split("_")[0]' in f.read():
                    offenders.append(name)
        self.assertEqual(offenders, [])


class TestFilenameIsDiagnosticOnly(unittest.TestCase):
    """2. 3. 4."""

    def test_the_filename_token_is_reported_as_a_diagnostic(self) -> None:
        self.assertEqual(issuer_identity.filename_token("0000026172.json"),
                         "0000026172.JSON")
        self.assertEqual(
            issuer_identity.filename_token("CMI_companyfacts.json"), "CMI")

    def test_and_expected_pattern_detection(self) -> None:
        self.assertTrue(
            issuer_identity.filename_matches_expected("CMI_companyfacts.json"))
        self.assertFalse(
            issuer_identity.filename_matches_expected("0000026172.json"))

    def test_and_a_mismatch_never_creates_a_second_issuer(self) -> None:
        self.write_payload = tempfile.mkdtemp()
        with io.open(os.path.join(self.write_payload, "CMI_companyfacts.json"),
                     "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps({"cik": 26172}))
        with io.open(os.path.join(self.write_payload, "0001549084.json"),
                     "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps({"cik": 26172}))
        mapping, records = issuer_identity.load_companyfacts_payloads(
            self.write_payload, {"26172": "CMI"})
        self.assertEqual(len(mapping), 1)
        self.assertEqual(len(records), 2)
        self.assertEqual(
            sorted(r["identity_status"] for r in records),
            [issuer_identity.CANONICAL_MATCH,
             issuer_identity.FILENAME_CIK_MISMATCH])


class TestAllPayloadsAreProcessed(unittest.TestCase):
    """6. 7."""

    def test_every_payload_file_yields_a_record(self) -> None:
        self.assertEqual(result()["counts"]["payload_files"], 89)
        self.assertEqual(len(issuer_identity.load_harness_payloads(
            H, None, issuer_identity.cik_ticker_index(H))[1]), 89)

    def test_and_the_canonical_count_is_computed_from_the_cik(self) -> None:
        counts = result()["counts"]
        self.assertEqual(counts["unique_canonical_issuers"], 63)
        self.assertEqual(
            counts["identity_status_counts"][issuer_identity.CANONICAL_MATCH]
            + counts["identity_status_counts"][
                issuer_identity.NONCANONICAL_FILENAME], 89)

    def test_and_no_issuer_is_unresolved_in_the_real_corpus(self) -> None:
        self.assertEqual(result()["counts"]["filers_unresolved"], 0)

    def test_and_every_key_is_a_ticker_not_a_filename_token(self) -> None:
        mapping, _records = issuer_identity.load_harness_payloads(
            H, None, issuer_identity.cik_ticker_index(H))
        for key in mapping:
            self.assertNotIn(".JSON", key, key)
            self.assertFalse(key.startswith(("CIK:", "UNRESOLVED:")), key)


class TestTheTwelveAnomaliesResolveToExistingIssuers(unittest.TestCase):
    """8."""

    EXPECTED = {"CCXIU", "CHRN", "CMI", "CONC", "KTCC", "LTRX", "MAIR",
                "NEON", "RBC", "SSYS", "STMEF", "TRSG"}

    def test_twelve_rows(self) -> None:
        self.assertEqual(len(result()["anomaly_table"]), 12)

    def test_and_they_are_the_documented_twelve(self) -> None:
        self.assertEqual({r["issuer"] for r in result()["anomaly_table"]},
                         self.EXPECTED)

    def test_and_each_resolves_to_an_existing_issuer(self) -> None:
        self.assertTrue(result()["anomalies_introduce_no_new_issuer"])
        for row in result()["anomaly_table"]:
            self.assertEqual(row["mismatch_type"],
                             issuer_identity.NONCANONICAL_FILENAME)
            self.assertTrue(row["payload_cik"])
            self.assertEqual(row["canonical_resolution"], row["issuer"])

    def test_and_the_filename_token_would_have_been_wrong(self) -> None:
        for row in result()["anomaly_table"]:
            self.assertTrue(row["filename_derived_token"].endswith(".JSON"))
            self.assertNotEqual(row["filename_derived_token"],
                                row["issuer"])

    def test_and_no_issuer_carries_two_keys(self) -> None:
        mapping, _records = issuer_identity.load_harness_payloads(
            H, None, issuer_identity.cik_ticker_index(H))
        self.assertEqual(len(mapping), 63)
        self.assertEqual(len(set(mapping)), 63)


class TestTheCohortIsUnchanged(unittest.TestCase):
    """9. 2.84's field finding is preserved."""

    def test_the_24_8_16_partition_holds(self) -> None:
        cohort = result()["cohort_regression"]
        self.assertEqual((cohort["total_assets"], cohort["attempted"],
                          cohort["collected"], cohort["source_silent"],
                          cohort["not_yet_collected_excluded"]),
                         (99, 24, 8, 16, 75))
        self.assertTrue(cohort["matches_2_75"])

    def test_and_the_collected_members_are_the_known_eight(self) -> None:
        self.assertEqual(result()["cohort_regression"]["collected_members"],
                         ["AAPL", "MSFT", "MU", "NEM", "NVDA", "RIO", "TECK",
                          "TSM"])

    def test_and_the_historical_artefact_is_not_edited(self) -> None:
        with io.open(CENSUS_275, encoding="utf-8") as handle:
            census = json.load(handle)
        self.assertEqual(
            census["corpus"]["filers_with_a_companyfacts_payload_on_disk"], 75,
            "2.75's figure is a record of what was measured then")
        self.assertEqual(result()["historical_artefacts_edited"], [])

    def test_and_the_readers_now_report_the_canonical_count(self) -> None:
        self.assertEqual(len(held_payloads()), 63)
        self.assertEqual(len(load_payloads()), 63)

    def test_and_that_is_a_change_of_one_not_of_the_cohort(self) -> None:
        self.assertNotEqual(len(load_payloads()), 75)
        self.assertEqual(result()["cohort_regression"]["attempted"], 24)


class TestCoverageRecordsAndPayloadsRemainDistinct(unittest.TestCase):
    """10."""

    def test_coverage_without_payload_is_counted_separately(self) -> None:
        distinct = result()["coverage_and_payloads_remain_distinct"]
        self.assertEqual(distinct["coverage_records_without_a_payload_count"],
                         36)
        self.assertIn("payload-unavailable", distinct["statement"])

    def test_and_no_payload_has_no_coverage_record(self) -> None:
        distinct = result()["coverage_and_payloads_remain_distinct"]
        self.assertEqual(distinct["payloads_without_a_coverage_record"], [])

    def test_and_the_two_populations_are_not_merged(self) -> None:
        counts = result()["counts"]
        self.assertEqual(counts["unique_canonical_issuers"], 63)
        self.assertEqual(
            result()["cohort_regression"]["total_assets"], 99)


class TestNoSemanticOrRegistryChange(unittest.TestCase):
    """11. 12. 13. 14."""

    def test_no_semantic_classification_changed(self) -> None:
        with io.open(AUDIT_283, encoding="utf-8") as handle:
            audit = json.load(handle)
        self.assertEqual(audit["state_counts"][
            "NO_SEPARATE_R_AND_D_DISCLOSURE"], 15)
        self.assertEqual(audit["state_counts"]["AGGREGATED_R_AND_D"], 1)
        self.assertEqual(audit["r_and_d_state"], "OPEN_MIXED_PRESENTATION")
        self.assertFalse(result()["semantic_research_performed"])

    def test_and_no_registry_change(self) -> None:
        for field in ("registry_changed", "scope_set", "effective_from_set",
                      "migrated", "observations_changed",
                      "interpretations_changed", "supersession_changed"):
            self.assertFalse(result()[field], field)
        self.assertEqual(result()["mappings_added_or_promoted"], 0)

    def test_and_no_sbc_access(self) -> None:
        self.assertFalse(result()["sbc_accessed"])
        source = io.open(os.path.join(ROOT, "issuer_identity.py"),
                         encoding="utf-8").read()
        self.assertNotIn('"sbc"', source)

    def test_and_no_period_is_asserted(self) -> None:
        self.assertFalse(result()["temporal"]["fixed_dates_used"])

    def test_and_production_files_are_the_only_tracked_changes(self) -> None:
        changed = subprocess.run(
            ["git", "status", "--porcelain=v1"], capture_output=True, text=True,
            cwd=ROOT).stdout
        modified = [line for line in changed.splitlines()
                    if line[:2].strip() in ("M", "A", "R", "D")]
        self.assertTrue(modified, "the fix must be a tracked production change")
        for line in modified:
            path = line.split()[-1]
            self.assertNotIn("snapshot.sqlite", path)
            self.assertNotIn("harness", path)


if __name__ == "__main__":
    unittest.main()