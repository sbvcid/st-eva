"""
2.85 -- production regression tests for canonical issuer identity.

## What is being defended

A filename used to decide who an issuer was, and twelve payloads in the corpus are
named `<CIK>.json`. `issuer_identity.py` is the single place that decides. This
file defends that rule and nothing else.

## Why these tests build their own payloads

Every case here writes a synthetic payload to a temporary directory and drives
`resolve_issuer` / `load_companyfacts_payloads` against it. A test that asserted
only a corpus count would pass against a loader that produced the count for
unrelated reasons -- for instance one that deduplicated by path, or that skipped
the anomalies instead of resolving them.

So the count-free contract is the contract, and the corpus measurements live on
the research side of the boundary. That split is deliberate and is what makes this
file runnable from a clean checkout: it imports one tracked module
(`issuer_identity`), reads no harness artefact, and needs no EDGAR payloads.

3.02 moved the corpus and artefact assertions out of this file. They are preserved
unchanged in the research-side companion, and this file is the part that is
genuinely production.

## What is not defended here

The measured corpus counts, the twelve-anomaly table, the 24/8/16 cohort
partition, and the 2.85 artefact's own self-description. Those are statements
about what was measured on a particular corpus on a particular date. Asserting
them from the production suite would make a production test depend on a research
artefact, and 3.02 measured what that costs: a clean checkout could not import
this file at all.
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import issuer_identity  # noqa: E402


class SyntheticPayloads(unittest.TestCase):
    """The five cases that matter, written to disk so the loader runs end to end."""

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
        """
        The payload's CIK wins. The filename does not create an issuer, which is
        the defect itself.
        """
        path = self.write("0001549084.json",
                          {"cik": 26172, "entityName": "Cummins"})
        record = issuer_identity.resolve_issuer(
            json.load(io.open(path, encoding="utf-8")), path, self.cik_map)
        self.assertEqual(record["identity_status"],
                         issuer_identity.FILENAME_CIK_MISMATCH)
        self.assertFalse(record["filename_cik_equals_payload_cik"])
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

    def test_the_resolver_reads_the_document_not_the_name(self) -> None:
        """
        Stated against the source rather than only through behaviour, because the
        behaviour tests all pass against a loader that happens to agree with the
        filename on the five synthetic cases. This asserts the decision is read
        from the payload's own `cik`.
        """
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

    def test_and_the_only_remaining_uses_are_diagnostics(self) -> None:
        """
        `issuer_identity` exposes the filename token on purpose, as a diagnostic,
        and the 2.84 reconciliation quotes it when describing the defect. Nothing
        that *decides* an identity may still do it.

        Stated by scanning what is present rather than by an allowlist of files
        that must exist, so the assertion holds in a checkout where the research
        artefacts are absent -- which is the whole point of 3.02.

        The companion assertion over the enumerated payload readers is NOT here.
        That list is derived by the 2.85 audit from a scan of research modules, so
        restating it by hand would assert a list nobody maintains; it is preserved
        unchanged in the research-side companion, which imports the audit's real
        `UPDATED_READERS`.
        """
        allowed = {"issuer_identity.py", "issuer_identity_audit_285.py",
                   "cohort_reconciliation_284.py"}
        offenders = []
        for name in sorted(os.listdir(ROOT)):
            if not name.endswith(".py") or name in allowed:
                continue
            with io.open(os.path.join(ROOT, name), encoding="utf-8",
                         errors="replace") as handle:
                if 'split("_")[0]' in handle.read():
                    offenders.append(name)
        self.assertEqual(offenders, [])


class TestFilenameIsDiagnosticOnly(unittest.TestCase):

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
        """
        The loader, not the resolver: two filenames and one CIK must produce one
        key and two records, so a mismatch is recorded rather than collapsed away.
        """
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


class TestIdentityResolutionIsNotScopedToAMetric(unittest.TestCase):
    """
    Issuer identity is a fact about who filed, not about what was measured.

    2.85 recorded that `sbc` was not opened by that round. Kept here as a
    production assertion rather than an artefact flag, because it is a property of
    the module and not of a particular run: a reader that decided identity would
    be deciding measurement scope as a side effect.
    """

    def test_the_module_does_not_name_a_metric(self) -> None:
        source = io.open(os.path.join(ROOT, "issuer_identity.py"),
                         encoding="utf-8").read()
        self.assertNotIn('"sbc"', source)
        self.assertNotIn("metric_concept_mapping", source)

    def test_it_takes_no_registry_dependency(self) -> None:
        """Issuer identity must be resolvable without seeding any registry."""
        source = io.open(os.path.join(ROOT, "issuer_identity.py"),
                         encoding="utf-8").read()
        self.assertNotIn("registry_seed", source)
        self.assertNotIn("CoreRegistry", source)


if __name__ == "__main__":
    unittest.main()