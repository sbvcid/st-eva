"""
2.84 -- adversarial tests for the cohort reconciliation.

## What is being defended

The reconciliation's central claim is that there was never a membership
conflict: the raw `collection-*` directories and `load_collection()` contain the
same 99 asset keys, and the 40-versus-16 discrepancy is a *field* difference, not a
set difference. A claim like that is cheap to make and easy to fake, so the tests
assert the symmetry directly rather than trusting the reported status.

The second thing defended is the double-count. `held_payloads()` derives a filer
key from the filename, and twelve payloads are named `<CIK>.json`, so it returns
75 keys for 63 issuers -- which is where the census's "75 filers" came from. If
that double-count is not pinned, the next cohort statement built from payload keys
inherits it silently.

## No EDGAR traffic and no semantic work in the test path
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import cohort_reconciliation_284 as reconciliation  # noqa: E402
from semantic_gap_census_275 import load_collection  # noqa: E402

# 2.99 retired the invalid `us-gaap:Revenues -> revenue` PARTIAL mapping,
# which is the one production change an authorised round made. Every other
# production path stays protected, and the exemption is named here rather
# than hidden in a shared helper, so a reader of this file can see why
# registry_seed.py is treated differently and cannot widen silently.
AUTHORISED_PRODUCTION_PATHS = {"registry_seed.py"}


def changed_mine(git_status_output: str) -> set:
    """Tracked paths this test forbids, less the authorised one."""
    lines = [line for line in git_status_output.strip().splitlines()
             if line.strip()]
    return {line.split()[-1] for line in lines
            if line[:2].strip() in ("M", "R", "D", "A")} - \
        AUTHORISED_PRODUCTION_PATHS


H = os.path.join(ROOT, "experiments", "003-llm-evidence-retrieval", "harness")
ARTEFACT = os.path.join(H, "284-cohort-reconciliation.json")
AUDIT_283 = os.path.join(H, "283-r-and-d-source-silent-filer-audit.json")
CENSUS_275 = os.path.join(H, "275-semantic-gap-census.json")

_RESULT = None


def result():
    global _RESULT
    if _RESULT is None:
        with io.open(ARTEFACT, encoding="utf-8") as handle:
            _RESULT = json.load(handle)
    return _RESULT


def setUpModule():
    if not os.path.exists(ARTEFACT):
        raise unittest.SkipTest("run cohort_reconciliation_284.py first")


class TestEveryCompanyfactsFilerAppearsOnce(unittest.TestCase):
    """1."""

    def test_the_ledger_has_one_row_per_issuer(self) -> None:
        rows = result()["issuer_ledger"]
        keys = [(r["asset"], str(r["cik"] or "")) for r in rows]
        self.assertEqual(len(keys), len(set(keys)))

    def test_and_every_payload_issuer_is_in_the_ledger(self) -> None:
        payloads = reconciliation.payload_index(
            reconciliation.cik_to_ticker())
        ledger_ciks = {str(r["cik"]).strip().lstrip("0")
                       for r in result()["issuer_ledger"] if r["cik"]}
        for cik in payloads:
            self.assertIn(str(cik).strip().lstrip("0"), ledger_ciks,
                          cik)

    def test_and_every_coverage_asset_is_in_the_ledger(self) -> None:
        assets = {r["asset"] for r in result()["issuer_ledger"]}
        self.assertTrue(set(load_collection()) <= assets)

    def test_and_the_ledger_matches_the_artefact_count(self) -> None:
        self.assertEqual(len(result()["issuer_ledger"]),
                         result()["issuer_ledger_counts"][
                             "assets_with_a_coverage_record"])


class TestEveryRawAssetAppearsOnce(unittest.TestCase):
    """2. The 40-asset crosswalk must lose nobody."""

    def test_raw_and_loader_membership_are_identical(self) -> None:
        self.assertTrue(result()["membership_reconciled"])
        self.assertEqual(result()["memberships"]["in_raw_not_in_loader"], [])
        self.assertEqual(result()["memberships"]["in_loader_not_in_raw"], [])

    def test_and_it_is_recomputed_not_trusted(self) -> None:
        raw = set(reconciliation.raw_records())
        loader = set(load_collection())
        self.assertEqual(raw - loader, set())
        self.assertEqual(loader - raw, set())
        self.assertEqual(len(raw), 99)

    def test_and_every_raw_asset_is_in_the_crosswalk(self) -> None:
        crosswalk = set(result()["raw_40_reconciliation"][
            "silent_in_any_cohort"])
        self.assertTrue(crosswalk <= {r["asset"]
                                      for r in result()["issuer_ledger"]})

    def test_and_the_difference_is_the_stated_reason(self) -> None:
        raw40 = result()["raw_40_reconciliation"]
        expected = set(raw40["silent_in_any_cohort"]) - set(
            raw40["silent_in_canonical_cohort"])
        self.assertEqual(set(raw40["difference"]), expected)
        self.assertEqual(raw40["difference_explained_as"],
                         reconciliation.REASON_COHORT_ATTEMPTED_ELSEWHERE)


class TestTheTwentyFourAreIdentifiable(unittest.TestCase):
    """3."""

    def test_count(self) -> None:
        self.assertEqual(
            result()["issuer_ledger_counts"]["attempted_by_275"], 24)

    def test_and_each_has_a_canonical_record(self) -> None:
        for row in result()["issuer_ledger"]:
            if row["attempted_by_275"]:
                self.assertTrue(row["canonical_record_from"], row["asset"])
                self.assertIsNotNone(row["canonical_status"], row["asset"])


class TestTheAuditedSixteenAreASubset(unittest.TestCase):
    """4."""

    def test_subset(self) -> None:
        self.assertTrue(result()["audited_cohort"][
            "is_a_subset_of_the_attempted_cohort"])

    def test_and_the_membership_is_recomputed(self) -> None:
        attempted = {r["asset"] for r in result()["issuer_ledger"]
                     if r["attempted_by_275"]}
        with io.open(AUDIT_283, encoding="utf-8") as handle:
            audit = json.load(handle)
        self.assertEqual(set(audit["silent_filers"]) <= attempted, True)
        self.assertEqual(audit["silent_filers"],
                         result()["audited_cohort"][
                             "audited_source_silent_cohort"])


class TestCollectedPlusSilentEqualsAttempted(unittest.TestCase):
    """5."""

    def test_the_partition_sums(self) -> None:
        self.assertTrue(result()["attempted_partition"]["sums_to_attempted"])
        counts = result()["issuer_ledger_counts"]
        self.assertEqual(counts["collected_by_275"]
                         + counts["source_silent_by_275"],
                         counts["attempted_by_275"])

    def test_and_the_24_8_16_figures_are_reproduced(self) -> None:
        counts = result()["issuer_ledger_counts"]
        self.assertEqual((counts["attempted_by_275"],
                          counts["collected_by_275"],
                          counts["source_silent_by_275"]), (24, 8, 16))


class TestEveryDiscrepancyHasAReason(unittest.TestCase):
    """6."""

    def test_no_disagreement_is_unexplained(self) -> None:
        self.assertEqual(
            result()["issuer_ledger_counts"][
                "disagreements_without_a_reason"], 0)

    def test_and_each_disagreeing_row_names_its_reason(self) -> None:
        for row in result()["issuer_ledger"]:
            if row["cross_cohort_status_disagreement"]:
                self.assertTrue(row["disagreement_reasons"], row["asset"])

    def test_and_every_excluded_row_says_why(self) -> None:
        for row in result()["issuer_ledger"]:
            if not row["attempted_by_275"]:
                self.assertTrue(row["exclusion_reason"], row["asset"])

    def test_and_the_reason_vocabulary_is_the_declared_one(self) -> None:
        allowed = {
            reconciliation.REASON_COHORT_ATTEMPTED_ELSEWHERE,
            reconciliation.REASON_NOT_ATTEMPTED,
            reconciliation.REASON_UNIVERSE_COHORT_ONLY,
            reconciliation.REASON_NO_PAYLOAD,
            reconciliation.REASON_DUPLICATE_PAYLOAD,
            reconciliation.REASON_CANONICAL_RECORD,
            reconciliation.REASON_NO_COVERAGE_RECORD,
            reconciliation.REASON_FILENAME_CONVENTION_BROKEN,
            reconciliation.REASON_ATTEMPTED_ELSEWHERE_SILENT,
            reconciliation.REASON_ATTEMPTED_ELSEWHERE_OTHER + ":X",
            reconciliation.REASON_ATTEMPTED_ELSEWHERE_SILENT,
        }
        for row in result()["issuer_ledger"]:
            for reason in row["cohort_reason"]:
                self.assertIn(reason, allowed, row["asset"])
            for reason in row["disagreement_reasons"]:
                self.assertTrue(
                    reason in (reconciliation.REASON_ATTEMPTED_ELSEWHERE_SILENT,
                               reconciliation.REASON_ATTEMPTED_ELSEWHERE_OTHER)
                    or reason.startswith(
                        reconciliation.REASON_ATTEMPTED_ELSEWHERE_OTHER + ":"),
                    reason)


class TestNoCohortStateIsInferredFromAbsenceAlone(unittest.TestCase):
    """7."""

    def test_a_not_attempted_row_never_carries_a_semantic_state(self) -> None:
        for row in result()["issuer_ledger"]:
            if not row["attempted_by_275"]:
                self.assertIsNone(row["canonical_status"]
                                  if row["canonical_status"]
                                  != "NOT_YET_COLLECTED" else None)
                self.assertFalse(row["source_silent_by_275"], row["asset"])

    def test_and_an_unexamined_row_is_never_given_a_semantic_label(self) -> None:
        for row in result()["issuer_ledger"]:
            for forbidden in ("NO_SEPARATE_R_AND_D", "AGGREGATED_R_AND_D",
                              "not R&D", "presentation limitation"):
                self.assertNotIn(
                    forbidden, json.dumps(row.get("cohort_reason", [])))

    def test_and_the_unexamined_block_forbids_those_labels(self) -> None:
        remaining = result()["remaining_unexamined_source_silent"]
        self.assertEqual(sorted(remaining["must_not_be_called"]),
                         sorted(["not R&D", "no separate disclosure",
                                 "presentation limitation"]))
        self.assertGreater(remaining["count"], 0)


class TestAnIssuerOutsideTheCohortInheritsNothing(unittest.TestCase):
    """8."""

    def test_the_unexamined_set_is_disjoint_from_the_audited_set(self) -> None:
        remaining = set(result()["remaining_unexamined_source_silent"]["assets"])
        audited = set(result()["audited_cohort"]["audited_source_silent_cohort"])
        self.assertEqual(remaining & audited, set())
        self.assertEqual(len(remaining), 24)

    def test_and_every_unexamined_issuer_held_a_payload(self) -> None:
        remaining = result()["remaining_unexamined_source_silent"]
        self.assertEqual(remaining["with_payload_count"],
                         remaining["count"])

    def test_and_no_2_83_state_is_attached_to_them(self) -> None:
        audited_states = {}
        with io.open(AUDIT_283, encoding="utf-8") as handle:
            audit = json.load(handle)
        for filer in audit["filers"]:
            audited_states[filer["filer"]] = filer["final_state"]
        for asset in result()["remaining_unexamined_source_silent"]["assets"]:
            self.assertNotIn(asset, audited_states)


class TestTheSemanticResultsAreUnchanged(unittest.TestCase):
    """9."""

    def test_the_2_83_artefact_is_unmodified(self) -> None:
        with io.open(AUDIT_283, encoding="utf-8") as handle:
            audit = json.load(handle)
        self.assertEqual(audit["r_and_d_state"], "OPEN_MIXED_PRESENTATION")
        self.assertEqual(audit["state_counts"][
            "NO_SEPARATE_R_AND_D_DISCLOSURE"], 15)
        self.assertEqual(audit["state_counts"]["AGGREGATED_R_AND_D"], 1)
        self.assertEqual(audit["state_counts"]["ALTERNATE_R_AND_D_CONCEPT"], 0)

    def test_and_the_round_declares_it_recomputed_nothing(self) -> None:
        self.assertTrue(result()["audited_cohort"][
            "states_unchanged_by_this_round"])
        self.assertFalse(result()["semantic_validation_rerun"])
        self.assertEqual(result()["filings_fetched"], 0)

    def test_and_the_scoped_state_carries_its_scope(self) -> None:
        scoped = result()["scoped_r_and_d_state"]
        self.assertEqual(scoped["state"], "OPEN_MIXED_PRESENTATION")
        self.assertIn("16-filer", scoped["scope"])
        self.assertFalse(scoped["metric_closed"])
        self.assertFalse(scoped["generalizable_to_the_whole_corpus"])

    def test_and_the_allowed_and_forbidden_statements_are_recorded(self) -> None:
        scoped = result()["scoped_r_and_d_state"]
        self.assertIn("Among the 16", scoped["statement_allowed"])
        self.assertTrue(scoped["statement_not_allowed"])

    def test_and_the_census_filings_figure_is_corrected(self) -> None:
        """
        The double-count, and its correction.

        2.84 recorded that `held_payloads()` returned 75 keys for 63 issuers,
        which is where the census's "75 filers" came from. 2.85 fixed the loader,
        so the live figure is now 63 while 2.75's recorded artefact still says
        75. The two must still differ, or the historical figure stops being
        known-wrong and this test would be asserting something false.
        """
        finding = result()["issuer_identity_finding"]
        self.assertEqual(finding["unique_issuers_with_a_payload"], 63)
        self.assertEqual(
            finding["payload_files_breaking_the_convention"], 12)
        self.assertIn("counts twelve issuers twice", finding["consequence"])
        held = reconciliation.held_payloads()
        self.assertEqual(len(held), 63,
                         "2.85 canonicalises the loader, so 75 is no longer "
                         "what the corpus reports")
        with io.open(CENSUS_275, encoding="utf-8") as handle:
            census = json.load(handle)
        self.assertEqual(
            census["corpus"]["filers_with_a_companyfacts_payload_on_disk"], 75)
        self.assertNotEqual(
            len(held),
            census["corpus"]["filers_with_a_companyfacts_payload_on_disk"],
            "the record and the corrected live figure must differ, or the "
            "historical figure is no longer known to be wrong")

    def test_and_the_census_artefact_is_not_rewritten(self) -> None:
        with io.open(CENSUS_275, encoding="utf-8") as handle:
            census = json.load(handle)
        self.assertEqual(
            census["corpus"]["filers_with_a_companyfacts_payload_on_disk"], 75,
            "2.75's figure is historical and this round must not edit it")


class TestSbcRemainsUntouched(unittest.TestCase):
    """10."""

    def test_flag_and_absence(self) -> None:
        self.assertFalse(result()["sbc_inspected"])
        for row in result()["issuer_ledger"]:
            self.assertNotIn("sbc", (row["asset"] or "").lower())

    def test_and_the_module_never_names_sbc(self) -> None:
        source = io.open(os.path.join(ROOT,
                                      "cohort_reconciliation_284.py"),
                         encoding="utf-8").read()
        self.assertNotIn('"sbc"', source.replace('"sbc_inspected"', ""))


class TestNothingWasWritten(unittest.TestCase):
    """11."""

    def test_the_artefact_declares_itself_read_only(self) -> None:
        for field in ("registry_changed", "scope_set", "effective_from_set",
                      "migrated", "observations_changed",
                      "interpretations_changed", "schema_changed",
                      "supersession_changed", "semantic_validation_rerun"):
            self.assertFalse(result()[field], field)
        self.assertEqual(result()["mappings_added_or_promoted"], 0)

    def test_and_no_production_file_changed(self) -> None:
        changed = subprocess.run(
            ["git", "status", "--porcelain=v1", "--", "core_registry.py",
             "registry_seed.py", "archive"], capture_output=True, text=True,
            cwd=ROOT)
        self.assertEqual(changed_mine(changed.stdout), set(),
                             "tests/test_cohort_reconciliation_284.py")

    def test_and_no_period_was_invented(self) -> None:
        self.assertFalse(result()["temporal"]["fixed_dates_used"])
        self.assertIn("not temporal", result()["temporal"]["note"])


class TestDeterminismIsReal(unittest.TestCase):

    def test_the_loader_is_run_and_compared(self) -> None:
        self.assertEqual(result()["determinism"]["runs"], 2)
        self.assertTrue(result()["determinism"]["identical"])

    def test_and_the_state_follows_it(self) -> None:
        self.assertEqual(result()["status"], "COHORT_RECONCILED")
        self.assertNotIn("UNSTABLE", result()["status"])

    def test_and_it_is_recomputed_here_too(self) -> None:
        self.assertEqual(sorted(load_collection()),
                         sorted(load_collection()))


if __name__ == "__main__":
    unittest.main()