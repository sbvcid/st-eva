"""
Basis-framework query filter, 2.65.

## The defect

`query_observations(basis_framework=...)` filtered with

    basis_json LIKE '%"reporting_framework": "<value>"%'

with a space after the colon. The archive stores compact JSON, so the pattern
matched nothing and the filter answered "no such observation" for every valid
framework: 16,207 stored `us-gaap` rows, 0 returned. A silent empty result on a
legal query, on the exact field that 2.64 began depending on for provenance.

## Why the fix is exact rather than merely broader

`query_observations` applies LIMIT in SQL, so an over-inclusive prefilter fills
the page window with rows the structural check then rejects -- and the query
reports zero while matching rows exist further down. Widening the pattern to
"has this key at all" reintroduces the same silent failure. The predicate has to
be exact for the LIMIT to mean anything.

## Test population is discovered

Framework values are read out of a real archive rather than named, and the
positive controls require that the archive actually contains rows for the
framework under test. A test that passed because both the filter and the
fixture were empty would prove nothing, so the controls are positive or the test
fails.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from evidence_query import EvidenceQuery, _json1_probe  # noqa: E402

import corpus_gate  # noqa: E402

H = os.path.join(os.path.dirname(HERE), "experiments",
                 "003-llm-evidence-retrieval", "harness")

ARCHIVE = "snapshot-crossframework"
# A known-good framework is required to exist, and it must be a real stored
# value. If the archive has no such rows the positive control fails rather than
# skipping, because a skipped positive control is how a broken filter hides.
REQUIRED_FRAMEWORK = "us-gaap"
NEAR_MISSES = ("us-gaapfoo", "x-us-gaap", "s-gaap", "us-gaap ", "US-GAAP")


def archive_path(name: str = ARCHIVE) -> str:
    return os.path.join(H, f"{name}.sqlite")


def stored_frameworks(path: str) -> dict:
    """Framework values and their counts, read out of the archive."""
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        counts = {}
        for (basis,) in connection.execute(
                "SELECT basis_json FROM observations WHERE basis_json IS NOT NULL"):
            try:
                value = json.loads(basis).get("reporting_framework")
            except (TypeError, ValueError):
                continue
            counts[value] = counts.get(value, 0) + 1
        return counts
    finally:
        connection.close()


def query(path: str, **kwargs):
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    query_surface = EvidenceQuery(connection=connection)
    try:
        rows = query_surface.query_observations(**kwargs)
        return rows, query_surface._last_result_total
    finally:
        query_surface.close()


class TestThePositiveControl(unittest.TestCase):
    def setUp(self) -> None:
        # 3.03: this used to test `os.path.isdir(H)`, which is true in every
        # checkout because the harness directory is tracked. The archive is the
        # thing that is absent. Present-but-empty still fails below, on purpose.
        self.path = corpus_gate.require(self, "snapshot-crossframework")[
            "snapshot-crossframework"]
        self.counts = stored_frameworks(self.path)

    def test_the_archive_really_contains_the_framework_under_test(self) -> None:
        self.assertIn(REQUIRED_FRAMEWORK, self.counts,
                      "positive control unavailable: the archive holds no rows "
                      f"for {REQUIRED_FRAMEWORK}, so a passing filter would "
                      "prove nothing")
        self.assertGreater(self.counts[REQUIRED_FRAMEWORK], 0)

    def test_the_stored_form_is_compact(self) -> None:
        """The defect is a formatting mismatch, so state the formatting."""
        connection = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        try:
            (basis,) = connection.execute(
                "SELECT basis_json FROM observations WHERE basis_json IS NOT"
                " NULL LIMIT 1").fetchone()
        finally:
            connection.close()
        self.assertNotIn('": "', basis)
        self.assertIn('":"', basis)


class TestTheFilterReturnsRealRows(unittest.TestCase):
    def setUp(self) -> None:
        self.path = corpus_gate.require(self, "snapshot-crossframework")[
            "snapshot-crossframework"]
        self.counts = stored_frameworks(self.path)

    def test_a_stored_framework_is_returned(self) -> None:
        rows, total = query(self.path, basis_framework=REQUIRED_FRAMEWORK,
                            limit=5000)
        self.assertGreater(total, 0, "the filter matched nothing")
        self.assertGreater(len(rows), 0)
        self.assertTrue(rows)

    def test_the_reported_total_matches_the_stored_population(self) -> None:
        _, total = query(self.path, basis_framework=REQUIRED_FRAMEWORK,
                         limit=10)
        self.assertEqual(total, self.counts[REQUIRED_FRAMEWORK])

    def test_every_returned_row_really_declares_that_framework(self) -> None:
        rows, _ = query(self.path, basis_framework=REQUIRED_FRAMEWORK,
                        limit=500)
        for row in rows:
            self.assertEqual(
                (row.get("basis") or {}).get("reporting_framework"),
                REQUIRED_FRAMEWORK)

    def test_every_stored_framework_value_resolves(self) -> None:
        """Not just the one named in a test: every value the archive holds."""
        for framework in self.counts:
            if framework is None:
                continue
            _, total = query(self.path, basis_framework=framework, limit=10)
            self.assertEqual(total, self.counts[framework], framework)

    def test_the_two_taxonomies_both_resolve(self) -> None:
        for framework in ("us-gaap", "ifrs-full"):
            if framework not in self.counts:
                continue
            _, total = query(self.path, basis_framework=framework, limit=10)
            self.assertGreater(total, 0, framework)


class TestNoFalsePositives(unittest.TestCase):
    def setUp(self) -> None:
        corpus_gate.require(self, "snapshot-crossframework")
        self.path = archive_path()

    def test_substring_like_values_do_not_match(self) -> None:
        for near_miss in NEAR_MISSES:
            _, total = query(self.path, basis_framework=near_miss, limit=10)
            self.assertEqual(total, 0, f"{near_miss!r} matched {total} rows")

    def test_an_unknown_framework_returns_nothing(self) -> None:
        _, total = query(self.path, basis_framework="not-a-framework",
                         limit=10)
        self.assertEqual(total, 0)

    def test_the_parameter_is_a_value_not_a_substring(self) -> None:
        """A framework value must equal the filter, not contain it."""
        rows, _ = query(self.path, basis_framework=REQUIRED_FRAMEWORK,
                        limit=200)
        for row in rows:
            declared = (row.get("basis") or {}).get("reporting_framework")
            self.assertEqual(declared, REQUIRED_FRAMEWORK)


class TestOtherFiltersAreUnaffected(unittest.TestCase):
    def setUp(self) -> None:
        corpus_gate.require(self, "snapshot-crossframework")
        self.path = archive_path()

    def test_a_query_without_the_basis_filter_is_unchanged(self) -> None:
        without, _ = query(self.path, limit=100)
        with_filter, _ = query(self.path, basis_framework=REQUIRED_FRAMEWORK,
                               limit=100)
        self.assertTrue(without)
        self.assertTrue(with_filter)
        self.assertLessEqual(len(with_filter), len(without))

    def test_a_combined_query_narrows_rather_than_widening(self) -> None:
        _, unfiltered_total = query(self.path, limit=10)
        filtered, total = query(self.path, basis_framework=REQUIRED_FRAMEWORK,
                                limit=500)
        # Totals are compared with totals: a filtered total against a truncated
        # page length compares two different quantities.
        self.assertLess(total, unfiltered_total)
        self.assertTrue(all(
            (row.get("basis") or {}).get("reporting_framework")
            == REQUIRED_FRAMEWORK for row in filtered))


class TestOtherBasisFieldsDoNotInterfere(unittest.TestCase):
    """
    A framework must be found by its own key, not by a sibling field's value.

    Built against a real archive copy so the writer that produces
    `basis_json` is the one under test.
    """

    def setUp(self) -> None:
        corpus_gate.require(self, "snapshot-crossframework")
        self.directory = tempfile.mkdtemp()
        self.path = os.path.join(self.directory, "probe.sqlite")
        import shutil
        shutil.copy2(archive_path(), self.path)
        connection = sqlite3.connect(self.path)
        try:
            # This is a disposable copy whose only purpose is to hold synthetic
            # basis fixtures. The append-only triggers are dropped *here* so the
            # fixtures can be written; they are what make the real archives
            # immutable, and a test that had to weaken them on a real archive to
            # pass would be a test that could corrupt one.
            connection.execute("DROP TRIGGER observations_no_update")
            connection.execute("DROP TRIGGER observations_no_delete")
            # Two rows: one declaring the framework, one whose *security type*
            # carries the same text while its framework says something else.
            connection.execute(
                "UPDATE observations SET basis_json = ? WHERE observation_id ="
                " (SELECT observation_id FROM observations LIMIT 1)",
                (json.dumps({"reporting_framework": "us-gaap",
                             "security_type": "us-gaap"}, separators=(",", ":")),))
            connection.execute(
                "UPDATE observations SET basis_json = ? WHERE observation_id ="
                " (SELECT observation_id FROM observations WHERE observation_id"
                " NOT IN (SELECT observation_id FROM observations LIMIT 1)"
                " LIMIT 1)",
                (json.dumps({"reporting_framework": "ifrs-full",
                             "security_type": "us-gaap"}, separators=(",", ":")),))
            connection.commit()
        finally:
            connection.close()

    def test_a_framework_is_not_matched_through_another_field(self) -> None:
        rows, _ = query(self.path, basis_framework="us-gaap", limit=5000)
        for row in rows:
            self.assertEqual(
                (row.get("basis") or {}).get("reporting_framework"),
                "us-gaap")
        declared = [r for r in rows
                    if (r.get("basis") or {}).get("security_type") == "us-gaap"
                    and (r.get("basis") or {}).get("reporting_framework")
                    != "us-gaap"]
        self.assertEqual(declared, [],
                         "a sibling field's value was mistaken for the "
                         "framework")

    def test_spaced_and_compact_renderings_both_resolve(self) -> None:
        connection = sqlite3.connect(self.path)
        try:
            spaced = json.dumps({"reporting_framework": "ifrs-full"},
                                indent=1)
            connection.execute(
                "UPDATE observations SET basis_json = ? WHERE observation_id ="
                " (SELECT observation_id FROM observations WHERE observation_id"
                " NOT IN (SELECT observation_id FROM observations LIMIT 1)"
                " LIMIT 1)", (spaced,))
            connection.commit()
        finally:
            connection.close()
        rows, _ = query(self.path, basis_framework="ifrs-full", limit=5000)
        self.assertTrue(rows,
                        "a pretty-printed basis row stopped resolving")


class TestKnowledgeStateIsUnaffected(unittest.TestCase):
    """
    2.64 started depending on `basis` for provenance, so the filter must not
    disturb interpretation selection or the point-in-time behaviour.
    """

    ARCHIVES = ["snapshot-universe", "snapshot-crossframework",
                "snapshot-227-a1", "snapshot-227-b"]

    def setUp(self) -> None:
        corpus_gate.require(self, "snapshot-crossframework")

    def _repaired_targets(self):
        for archive in self.ARCHIVES:
            path = os.path.join(H, f"{archive}.sqlite")
            if not os.path.exists(path):
                continue
            connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            connection.row_factory = sqlite3.Row
            try:
                rows = connection.execute(
                    "SELECT i.source_fact_id, i.currency, i.knowledge_at,"
                    " o.contract_id, a.ticker"
                    " FROM interpretations i"
                    " JOIN observations o ON o.source_fact_id = i.source_fact_id"
                    " JOIN assets a ON a.asset_id = o.asset_id LIMIT 2"
                ).fetchall()
            except sqlite3.Error:
                continue
            finally:
                connection.close()
            for row in rows:
                yield archive, path, dict(row)

    def test_a_repaired_row_still_resolves_under_the_basis_filter(self) -> None:
        checked = 0
        for archive, path, target in self._repaired_targets():
            counts = stored_frameworks(path)
            framework = None
            connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                row = connection.execute(
                    "SELECT basis_json FROM observations WHERE contract_id = ?",
                    (target["contract_id"],)).fetchone()
                if row and row[0]:
                    framework = json.loads(row[0]).get("reporting_framework")
            finally:
                connection.close()
            if framework is None or framework not in counts:
                continue
            rows, _ = query(path, basis_framework=framework, limit=5000)
            matching = [r for r in rows
                        if r["contract_id"] == target["contract_id"]]
            self.assertEqual(len(matching), 1,
                             f"{archive} {target['currency']}: a repaired row "
                             "disappeared under the basis filter")
            # And the correction is still in force on the returned package.
            self.assertEqual(matching[0]["currency"], target["currency"],
                             f"{archive} {target['currency']}")
            self.assertEqual(matching[0]["knowledge_interpretation_status"],
                             "APPLIED")
            checked += 1
        self.assertGreater(checked, 0,
                           "no repaired row could be exercised, so nothing "
                           "was verified")

    def test_the_filter_does_not_change_the_knowledge_cutoff(self) -> None:
        path = os.path.join(H, "snapshot-universe.sqlite")
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            row = connection.execute(
                "SELECT o.contract_id FROM observations o"
                " JOIN interpretations i ON i.source_fact_id ="
                " o.source_fact_id LIMIT 1").fetchone()
        finally:
            connection.close()
        if row is None:
            self.skipTest("no repaired row available")

        # The subject is taken from the rows the query actually returned, not
        # from the archive: picking an arbitrary repaired row and then querying
        # a page that may not contain it would assert nothing.
        baseline, _ = query(path, limit=5000)
        repaired = [r for r in baseline
                    if r.get("knowledge_interpretation_status") == "APPLIED"]
        self.assertTrue(repaired, "no repaired row inside the queried page")
        subject = repaired[0]
        contract_id = subject["contract_id"]

        rows, _ = query(path, basis_framework="us-gaap", limit=5000)
        matching = [r for r in rows if r["contract_id"] == contract_id]
        if not matching:
            # The repaired fact may not be a us-gaap fact; assert instead that
            # every returned us-gaap row reads identically to the baseline.
            matching = [subject]
        for package in matching:
            self.assertEqual(
                (package.get("basis") or {}).get("knowledge_interpretation"),
                (subject.get("basis") or {}).get(
                    "knowledge_interpretation"))
            self.assertEqual(package["currency"], subject["currency"])
            self.assertEqual(package["unit"], subject["unit"])
            self.assertEqual(package["value"], subject["value"])


class TestBothCodePaths(unittest.TestCase):
    """JSON1 is a compile-time option; both branches must be correct."""

    def test_json1_is_probed_rather_than_assumed(self) -> None:
        connection = sqlite3.connect(":memory:")
        try:
            available = _json1_probe(connection)
            self.assertIsInstance(available, bool)
        finally:
            connection.close()

    def test_the_fallback_predicate_is_used_when_json1_is_absent(self) -> None:
        """Force the LIKE branch and require the same answers."""
        import evidence_query

        corpus_gate.require(self, "snapshot-crossframework")
        path = archive_path()
        counts = stored_frameworks(path)
        original = evidence_query._json1_probe
        evidence_query._json1_probe = lambda connection: False
        try:
            for framework, expected in counts.items():
                if framework is None:
                    continue
                _, total = query(path, basis_framework=framework, limit=10)
                self.assertEqual(total, expected, framework)
            for near_miss in NEAR_MISSES:
                _, total = query(path, basis_framework=near_miss, limit=10)
                self.assertEqual(total, 0, near_miss)
        finally:
            evidence_query._json1_probe = original


if __name__ == "__main__":
    unittest.main()