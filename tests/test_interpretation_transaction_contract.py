"""
The transaction contract of `add_interpretation`.

2.62's repair harness batches interpretation writes and relies on the method to
commit. During the 2.73 incident that assumption failed visibly: the writing
connection reported 28 rows while a fresh connection reported 0. Nothing warned,
because "written" and "persisted" are different questions and the method's return
value answers the first.

This file pins the contract down rather than changing it. The behaviour measured
here is the contract; whether it is the *intended* contract is a decision, and
these tests are what such a decision would be made against.

The distinction being tested:

    standalone call        the method owns its commit
    caller-owned batch      the caller owns the commit, and the method must not
                            commit out from under it
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from archive import InterpretationError  # noqa: E402
from core_registry import CoreRegistry  # noqa: E402
from evidence_model import source_fact_id  # noqa: E402
from registry_seed import seed  # noqa: E402
from sqlite_archive import SQLiteArchive  # noqa: E402

K1 = "2026-09-30T12:00:00+00:00"
K2 = "2026-10-02T00:00:00+00:00"
K3 = "2026-11-15T00:00:00+00:00"


class ContractCase(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "a.sqlite")
        store = SQLiteArchive(self.path)
        registry = CoreRegistry(store.connection)
        seed(registry)
        store.connection.commit()
        self._insert_facts(store, 3)
        store.close()

    def _insert_facts(self, store: SQLiteArchive, count: int) -> None:
        from archive import FilingRef
        from data_contract import Observation, utc_now
        for index in range(count):
            accession = f"acc{index}"
            fact_id = source_fact_id(
                source_id="SecEdgar", document_ref=accession,
                taxonomy="ifrs-full",
                concept="CurrentPortionOfLongtermBorrowings",
                period_start=None, period_end="2024-12-31")
            store.record_observation(
                "TSM",
                Observation(
                    observation_id=(
                        f"ingest|debt|ifrs-full:CurrentPortionOfLongterm"
                        f"Borrowings|{accession}|instant|2024-12-31|TWD"),
                    metric="debt", value=1000.0 + index, unit="currency",
                    currency="TWD", currency_basis="REPORTED",
                    period_start=None, period_end="2024-12-31",
                    as_of="2024-12-31", available_at="2025-04-22T06:30:00+00:00",
                    available_at_basis="ACCEPTANCE_DATETIME",
                    provider="SecEdgar", source_type="REGULATORY_FILING",
                    source_url=None, definition="debt",
                    methodology="as filed", retrieved_at=utc_now(),
                    raw={}, basis={}),
                accession=accession,
                filing=FilingRef(
                    accession=accession, form="20-F", taxonomy="ifrs-full",
                    fiscal_year=2024, fiscal_period="FY", statement=None,
                    instant=1, source_fact_id=fact_id,
                    source_concept=("ifrs-full:"
                                    "CurrentPortionOfLongtermBorrowings")),
                availability_class="SOURCE_DECLARED",
                first_archived_at="2026-09-30T00:00:00+00:00")
        store.connection.commit()

    def facts(self) -> list:
        connection = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        try:
            return [r[0] for r in connection.execute(
                "SELECT source_fact_id FROM observations"
                " WHERE source_fact_id IS NOT NULL ORDER BY source_fact_id")]
        finally:
            connection.close()

    def fresh_count(self) -> int:
        connection = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        try:
            return connection.execute(
                "SELECT COUNT(*) FROM interpretations").fetchone()[0]
        finally:
            connection.close()


class TestTransactionOwnership(ContractCase):
    def test_1_a_standalone_call_persists_after_return(self) -> None:
        store = SQLiteArchive(self.path)
        try:
            store.add_interpretation(self.facts()[0], K1, "currency", "TWD",
                                     "REPORTED")
            store.close()
            self.assertEqual(self.fresh_count(), 1)
        finally:
            store.close()

    def test_2_a_caller_owned_batch_needs_the_caller_to_commit(self) -> None:
        """The behaviour that cost 2.73 a day."""
        store = SQLiteArchive(self.path)
        try:
            facts = self.facts()
            store.connection.execute("BEGIN")
            store.add_interpretation(facts[0], K1, "currency", "TWD", "REPORTED")
            store.add_interpretation(facts[1], K1, "currency", "TWD", "REPORTED")
            store.add_interpretation(facts[2], K1, "currency", "TWD", "REPORTED")
            # The writing connection sees its own uncommitted work.
            self.assertEqual(store.interpretation_count(), 3)
            # A fresh connection does not.
            self.assertEqual(self.fresh_count(), 0)
            store.connection.commit()
        finally:
            store.close()
        self.assertEqual(self.fresh_count(), 3)

    def test_3_a_caller_rollback_removes_the_uncommitted_batch(self) -> None:
        store = SQLiteArchive(self.path)
        try:
            store.connection.execute("BEGIN")
            store.add_interpretation(self.facts()[0], K1, "currency", "TWD",
                                     "REPORTED")
            store.connection.rollback()
        finally:
            store.close()
        self.assertEqual(self.fresh_count(), 0)

    def test_4_a_fresh_connection_cannot_see_uncommitted_work(self) -> None:
        store = SQLiteArchive(self.path)
        try:
            store.connection.execute("BEGIN")
            store.add_interpretation(self.facts()[0], K1, "currency", "TWD",
                                     "REPORTED")
            self.assertEqual(self.fresh_count(), 0)
        finally:
            store.close()

    def test_5_a_repeated_insert_still_adds_no_row(self) -> None:
        store = SQLiteArchive(self.path)
        try:
            fact = self.facts()[0]
            first = store.add_interpretation(fact, K1, "currency", "TWD",
                                              "REPORTED")
            second = store.add_interpretation(fact, K1, "currency", "TWD",
                                              "REPORTED")
            store.connection.commit()
            self.assertTrue(first["created"])
            self.assertFalse(second["created"])
            self.assertEqual(store.interpretation_count(), 1)
        finally:
            store.close()
        self.assertEqual(self.fresh_count(), 1)

    def test_6_a_refusal_does_not_commit_a_caller_owned_transaction(self) -> None:
        """
        The exception path must leave the caller's transaction alone.

        The refusal has to be on the SAME fact: "one reading per instant" is
        scoped per source fact, so two different facts at one instant are both
        legitimate and would not raise.
        """
        store = SQLiteArchive(self.path)
        try:
            fact = self.facts()[0]
            store.connection.execute("BEGIN")
            store.add_interpretation(fact, K1, "currency", "TWD", "REPORTED")
            with self.assertRaises(InterpretationError):
                # Same fact, same instant, different reading.
                store.add_interpretation(fact, K1, "currency", "USD", "REPORTED")
            # The earlier row is still only in the caller's transaction.
            self.assertEqual(self.fresh_count(), 0)
            store.connection.rollback()
        finally:
            store.close()
        self.assertEqual(self.fresh_count(), 0)

    def test_ownership_is_decided_before_any_statement(self) -> None:
        """
        The fix, asserted structurally rather than by wording.

        The first version of this test asserted that the docstring contained the
        words "Commit only when this call opened nothing" -- which is how a
        comment can describe an intention the code does not implement, and how
        this defect survived a green suite. Pinning prose pins the past.

        What matters is that the ownership decision is captured before the
        INSERT, so it cannot be reading SQLite's state after the statement that
        opened the transaction.
        """
        import inspect

        source = inspect.getsource(SQLiteArchive.add_interpretation)
        ownership = source.index("started_transaction = not")
        insert = source.index("INSERT INTO interpretations")
        commit = source.index("if started_transaction:")
        self.assertLess(ownership, insert,
                        "ownership must be captured before the INSERT")
        self.assertLess(insert, commit,
                        "the commit decision must follow the INSERT it governs")
        # And the post-INSERT state must not be used to decide ownership.
        self.assertNotIn("if not self.connection.in_transaction:",
                         source)


class TestBatchCallersComply(unittest.TestCase):
    """
    The audit the prompt asks for: does every batching caller commit?

    A caller that relies on the method to commit is a latent data-loss bug of
    exactly the kind 2.73 hit.
    """

    CALLERS = [
        ("historical_non_usd_unit_repair_262.py", "apply_to_archive"),
        ("historical_non_usd_unit_repair_262.py", "main"),
    ]

    def test_every_batching_caller_commits_or_documents_the_ownership(self):
        import ast

        here = os.path.dirname(HERE)
        for filename, function in self.CALLERS:
            path = os.path.join(here, filename)
            if not os.path.exists(path):
                continue
            tree = ast.parse(open(path, encoding="utf-8").read())
            target = next(
                (n for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef) and n.name == function),
                None)
            self.assertIsNotNone(target, f"{filename}:{function} not found")
            calls_add = any(
                isinstance(n, ast.Attribute) and n.attr == "add_interpretation"
                for n in ast.walk(target))
            commits = any(
                (isinstance(n, ast.Attribute) and n.attr == "commit")
                or "commit()" in ast.dump(n)
                for n in ast.walk(target))
            if calls_add:
                self.assertTrue(
                    commits,
                    f"{filename}:{function} batches add_interpretation without "
                    "committing. The writing connection will see the rows and a "
                    "fresh one will not, which is silent data loss.")

    def test_the_only_production_caller_is_known(self) -> None:
        """No other module may batch interpretations without an audit."""
        import ast

        here = os.path.dirname(HERE)
        offenders = []
        for name in sorted(os.listdir(here)):
            if not name.endswith(".py") or name.startswith("test_"):
                continue
            try:
                tree = ast.parse(
                    open(os.path.join(here, name), encoding="utf-8").read())
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if (isinstance(node, ast.Attribute)
                        and node.attr == "add_interpretation"):
                    function = next(
                        (f for f in ast.walk(tree)
                         if isinstance(f, ast.FunctionDef)
                         and node in ast.walk(f)), None)
                    commits = function is not None and any(
                        (isinstance(n, ast.Attribute) and n.attr == "commit")
                        for n in ast.walk(function))
                    if not commits:
                        offenders.append((name, getattr(function, "name", "?")))
        self.assertEqual(offenders, [],
                         "these callers add interpretations without committing")


if __name__ == "__main__":
    unittest.main()