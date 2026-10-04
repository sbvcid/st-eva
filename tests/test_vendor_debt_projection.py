"""
The Yahoo `totalDebt` projection is retired, and may not come back.

2.33 renamed Core `debt` to `long_term_debt` and adopted long-term debt as the
semantic target. That decision left one inconsistency: `fundamental_provider` was
still projecting Yahoo's `financialData.totalDebt` into the metric.

Those are different quantities.

    Yahoo financialData.totalDebt   the vendor's total debt, short-term included
    Core long_term_debt             long-term debt, short-term borrowings excluded
                                    by its own definition

Projecting one into the other is not a mismatch that a `methodology` caveat can
absorb. It puts a different quantity in the same metric under the same name, and
every Core consumer reads it as long-term debt. This is the same shape as the
2.29 candidate searches that each admitted a category the metric was not about.

So the projection is gone, and `long_term_debt` is simply **unavailable from this
source** — which is what "the source does not report it" looks like from the
provider side.

**What the provider actually acquires decides this, not what it could acquire.**
It requests `defaultKeyStatistics,earningsTrend,financialData` and no
balance-sheet module, so it holds no field whose semantics it has verified as
long-term debt. Assuming one existed because a name suggested it is exactly the
inference 2.29 rejected four times.

**Retiring it cost no history.** Every `debt` observation in every archive on
disk, the sealed 2.2.3 snapshot included, is provider `SecEdgar`. The projection
had never written one, so there is no legacy figure to preserve and no
compatibility shim to build.
"""

from __future__ import annotations

import glob
import os
import sqlite3
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import corpus_gate  # noqa: E402

H = os.path.join(REPO, "experiments", "003-llm-evidence-retrieval", "harness")

VENDOR_TOTAL_DEBT_FIELD = "totalDebt"
DECIDED = "long_term_debt"


class TestTheYahooProjectionIsRetired(unittest.TestCase):
    """No path from `financialData.totalDebt` into `long_term_debt`."""

    def test_the_provider_does_not_reference_total_debt_as_a_value(self):
        """
        The field no longer appears as a *value* anywhere in the provider.

        Asserted on the parsed source rather than on a loop, because a line-based
        check on a loop was what the previous version did and it matched a
        different loop entirely. A string literal equal to the field name is the
        only thing that could reintroduce the projection, and comments -- including
        the one explaining this retirement -- are not literals.
        """
        import ast

        source = open(
            os.path.join(REPO, "fundamental_provider.py"),
            encoding="utf-8").read()
        tree = ast.parse(source)
        literals = [
            node.lineno for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and node.value == VENDOR_TOTAL_DEBT_FIELD
        ]
        self.assertEqual(
            literals, [],
            f"fundamental_provider still names {VENDOR_TOTAL_DEBT_FIELD} as a "
            f"value at lines {literals}")

    def test_no_source_file_projects_total_debt_onto_the_decided_metric(self):
        """
        A repository-wide scan, so a projection added elsewhere is caught.

        Parsed rather than grepped. A line scan flags the comment that explains
        the retirement -- it names both the field and the metric -- and a test that
        fails on the documentation of the thing it forbids is a test that gets
        deleted. Walking the AST for string constants is immune to comments and
        docstrings by construction.
        """
        import ast

        offenders = []
        for path in glob.glob(os.path.join(REPO, "*.py")):
            if os.path.basename(path) == os.path.basename(__file__):
                continue
            try:
                tree = ast.parse(open(path, encoding="utf-8").read())
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant):
                    continue
                if node.value != VENDOR_TOTAL_DEBT_FIELD:
                    continue
                # A string literal naming the field. Is the metric it is being
                # projected onto the decided one?
                segment = ast.get_source_segment(
                    open(path, encoding="utf-8").read(), node) or ""
                parent_line = node.lineno
                source_lines = open(
                    path, encoding="utf-8").read().split("\n")
                window = "\n".join(
                    source_lines[max(0, parent_line - 4):parent_line])
                if DECIDED in segment or "LONG_TERM_DEBT" in window:
                    offenders.append(
                        f"{os.path.basename(path)}:{node.lineno}")
        self.assertEqual(offenders, [],
                         f"totalDebt projected onto {DECIDED} at {offenders}")

    def test_the_metric_still_has_a_contract_definition(self):
        import data_contract

        self.assertIn(DECIDED, data_contract.METRIC_CROSS_SOURCE_DEFINITIONS)
        self.assertNotIn(
            "total debt",
            data_contract.METRIC_CROSS_SOURCE_DEFINITIONS[DECIDED].lower())


class TestTheDecisionIsUnchangedByThisFix(unittest.TestCase):
    """A projection fix must not have moved the target."""

    def test_short_term_borrowings_is_still_unmapped(self):
        from core_registry import CoreRegistry
        from registry_seed import seed
        from sqlite_archive import SQLiteArchive
        import tempfile

        store = SQLiteArchive(os.path.join(tempfile.mkdtemp(), "a.sqlite"))
        try:
            registry = CoreRegistry(store.connection)
            seed(registry)
            for metric in registry.metrics():
                mapped = {m.concept_id for m in
                          registry.mappings_for_metric(metric.metric_id)}
                self.assertNotIn("us-gaap:ShortTermBorrowings", mapped)
            self.assertIsNone(registry.metric("total_debt"))
        finally:
            store.close()

    def test_the_core_metric_count_is_unchanged(self):
        from core_registry import CoreRegistry
        from registry_seed import seed
        from sqlite_archive import SQLiteArchive
        import tempfile

        store = SQLiteArchive(os.path.join(tempfile.mkdtemp(), "a.sqlite"))
        try:
            registry = CoreRegistry(store.connection)
            seed(registry)
            active = [m.metric_id for m in registry.metrics()
                      if m.status == "ACTIVE"]
            self.assertEqual(len(active), 20)
        finally:
            store.close()


class TestNoHistoryWasAffected(unittest.TestCase):
    """
    The projection had never written an observation, so retiring it changed no
    archive. Checked rather than argued, because that is the claim.
    """

    def test_every_stored_debt_observation_is_from_a_filing_source(self):
        # 3.03: this globs whatever archives exist rather than naming one, so it
        # is gated on "any corpus", not on a specific file. The `total > 0`
        # assertion below stays and is the point: with a corpus present but no
        # debt rows, it must fail rather than pass vacuously. Only the absence of
        # every archive is an environment fact this test defers on.
        corpus_gate.require_any(
            self, "snapshot-universe", "snapshot-crossframework",
            "snapshot-227-a1", "snapshot-227-b", "snapshot")
        checked, total = 0, 0
        for path in sorted(glob.glob(os.path.join(H, "*.sqlite"))):
            try:
                connection = sqlite3.connect(
                    f"file:{path}?mode=ro", uri=True)
                connection.row_factory = sqlite3.Row
                columns = [r[1] for r in connection.execute(
                    "PRAGMA table_info(observations)")]
                if "metric" not in columns:
                    connection.close()
                    continue
                rows = connection.execute(
                    "SELECT DISTINCT provider FROM observations"
                    " WHERE metric = 'debt'").fetchall()
                count = connection.execute(
                    "SELECT COUNT(*) FROM observations"
                    " WHERE metric = 'debt'").fetchone()[0]
                connection.close()
                checked += 1
                total += count
                for row in rows:
                    self.assertEqual(
                        row["provider"], "SecEdgar",
                        f"{os.path.basename(path)} has a non-filing "
                        f"debt observation")
            except sqlite3.Error:
                continue
        self.assertGreater(total, 0,
                           "no debt observations found to check; the claim "
                           "that none came from Yahoo would be vacuous")

    def test_the_sealed_snapshot_is_untouched(self):
        import hashlib

        path = os.path.join(H, "snapshot.sqlite")
        if not os.path.exists(path):
            self.skipTest("sealed snapshot not present")
        digest = hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]
        self.assertEqual(digest, "ce603a5588cef067")


if __name__ == "__main__":
    unittest.main()