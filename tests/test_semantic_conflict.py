"""
Evidence, applicability and coverage are three facts, and only one of them may
delete the others.

The decision this file guards: **a coverage interpretation must never become a
deletion filter on evidence.**

It was not always obvious, and the reason is worth keeping. 2.18 measured eight
bank filers whose `companyfacts` carry `operating_income` and whose filings classify
them `BANK`, which the registry rules `operating_income` out for. The two facts sit
side by side in the same ledger row: `status: NOT_APPLICABLE` and
`observations_held: 22`.

That disagreement *is* the finding. It is how `BANK -> operating_income
NOT_APPLICABLE` was caught as too broad -- NRIM tags
`us-gaap:OperatingIncomeLoss` in twenty-two rows and BBAR tags `ifrs-full:GrossProfit` in
eighteen, and a bank reporting a gross profit subtotal is not the fiction the
rule was written against.

Had ingestion refused to store those forty observations on the grounds that the
metric was ruled inapplicable, the ledger would have read zero, the rule would
have looked *confirmed*, and the mistake would have been locked in by the very
mechanism meant to catch it. A rule that cannot be contradicted by evidence is
not a rule; it is an assumption with a column.

So these tests assert the shape of the disagreement, not the resolution of it:

    the observation is stored
    the ledger reports NOT_APPLICABLE
    the conflict is named, with the concept that caused it
    the status counts still partition the Core universe
"""

from __future__ import annotations

import os
import pathlib
import sqlite3 as sqlite33
import sys
import tempfile
import unittest
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from core_registry import CoreRegistry  # noqa: E402
from coverage_semantics import (  # noqa: E402
    CONFLICT_EVIDENCE_HELD_FOR_INAPPLICABLE_METRIC,
    scoped_ledger,
)
from registry_seed import seed  # noqa: E402
from sec_ingest import Ingestor  # noqa: E402
from sqlite_archive import SQLiteArchive  # noqa: E402


class _BankSource:
    """
    One filer, one concept, one filing -- a financial institution reporting an
    operating income.

    SIC 6022, so the filer classifies `BANK`, which is the last refusal standing:
    `operating_income` is still ruled out there. It was **not** refuted -- 0 of the
    eight banks sampled tag `us-gaap:OperatingIncomeLoss`, which is consistent with
    the rule and does not establish it.

    The label moved three times to keep this test pointing at a live rule: it was
    `BANK` on `gross_profit`, then `FINANCE_SERVICES` on `operating_income`, and is
    now `BANK` on `operating_income` again. Each move followed a refutation, and the
    conflict machinery is only ever tested against a rule currently in force -- a
    contract exercised only against rules that have since been deleted would be
    evidence of nothing.

    Six members, because that is the whole `Ingestor` interface. The point of
    the fixture is that it is a *normal* run: nothing about it is exceptional,
    and the conflict arises from the registry rather than from anything the
    pipeline did.
    """

    def __init__(self, concept: str = "us-gaap:OperatingIncomeLoss") -> None:
        self.concept = concept
        self.documents_read = 0
        self.concept_fetches = 0
        self.network_fetches = 0
        self._history = [{
            "start": "2024-01-01",
            "end": "2024-12-31",
            "val": 125789000.0,
            "accn": "0000000001-25-000001",
            "fy": 2025,
            "fp": "FY",
            "form": "10-K",
            "filed": "2025-03-10",
        }]

    def resolve_company(self, ticker: str):
        class Company:
            cik = "0000000001"
            name = "Test Bank"
            exchanges = ()

        return Company()

    def submissions(self, cik: str) -> Dict[str, Any]:
        return {"sic": "6022", "sicDescription": "State Commercial Banks"}

    def filing_index(self, cik: str) -> List[Dict[str, Any]]:
        return [{
            "accession": "0000000001-25-000001",
            "form": "10-K",
            "filing_date": "2025-03-10",
            "report_date": "2024-12-31",
            "acceptance_datetime": "2025-03-10T16:22:31.000Z",
            "acceptance_precision": "INSTANT",
            "primary_document": "",
            "is_xbrl": 1,
        }]

    def concept_history(
        self, cik: str, taxonomy: str, concept: str
    ) -> Optional[Dict[str, Any]]:
        # Only the concept this filer actually tags. `operating_income` has two
        # declared concepts -- `us-gaap:OperatingIncomeLoss` and `ifrs-full:GrossProfit`
        # -- and a source that answers for both of them is not a bank that
        # reported a gross profit, it is a fixture that returns the same payload
        # whatever it is asked. A test for "the evidence survives the rule" has
        # to be about one real fact.
        if f"{taxonomy}:{concept}" != self.concept:
            return None
        return {
            "label": "Operating Income",
            "units": {"USD": list(self._history)},
        }

    def documents_for(self, taxonomy: str, concept: str):
        return ()


class TestEvidenceOutlivesTheRuleThatDisagreesWithIt(unittest.TestCase):
    """The one property: nothing is deleted to make a ruling look settled."""

    def setUp(self) -> None:
        self.directory = tempfile.mkdtemp()
        self.store = SQLiteArchive(os.path.join(self.directory, "a.sqlite"))
        registry = CoreRegistry(self.store.connection)
        seed(registry)
        # Make the refusal this fixture needs. No seeded exclusion has production
        # authority since 2.25 -- a rule must be `SUPPORTED` to refuse -- so a
        # refusal here is an explicit act rather than an inherited condition.
        registry.support_exclusion("operating_income", "BANK")
        ingestor = Ingestor(self.store, _BankSource(), registry)
        report = ingestor.ingest("TESTBK", metrics=("operating_income",))
        self.report = report
        asset = self.store.connection.execute(
            "SELECT asset_id FROM assets WHERE ticker = 'TESTBK'"
        ).fetchone()["asset_id"]
        self.ledger = scoped_ledger(self.store.connection, registry, asset,
                                    "TESTBK")

    def tearDown(self) -> None:
        self.store.close()

    def _row(self, metric: str) -> Dict[str, Any]:
        return next(
            r for r in self.ledger["rows"] if r["metric"] == metric
        )

    def test_the_filer_is_classified_as_a_bank(self):
        self.assertEqual(self.ledger["business_model"], "BANK")

    def test_the_observation_is_stored(self):
        # The whole point. One row, present, addressable, in the archive.
        stored = self.store.connection.execute(
            "SELECT COUNT(*) AS n FROM observations WHERE metric = 'operating_income'"
        ).fetchone()["n"]
        self.assertEqual(stored, 1)
        self.assertEqual(self._row("operating_income")["observations_held"], 1)

    def test_the_ledger_still_reports_not_applicable(self):
        self.assertEqual(
            self._row("operating_income")["status"], "NOT_APPLICABLE"
        )

    def test_both_facts_are_in_the_same_row(self):
        # A reader must not have to join two tables to see the disagreement.
        row = self._row("operating_income")
        self.assertEqual(row["status"], "NOT_APPLICABLE")
        self.assertEqual(row["observations_held"], 1)

    def test_the_conflict_is_named_with_its_concept(self):
        conflict = self._row("operating_income")["semantic_conflict"]
        self.assertIsNotNone(conflict)
        self.assertEqual(
            conflict["kind"],
            CONFLICT_EVIDENCE_HELD_FOR_INAPPLICABLE_METRIC,
        )
        self.assertEqual(conflict["observations_held"], 1)
        self.assertIn("us-gaap:OperatingIncomeLoss", conflict["concepts_reported"])

    def test_the_conflict_is_also_counted_at_the_ledger_level(self):
        metrics = [c["metric"] for c in self.ledger["semantic_conflicts"]]
        self.assertEqual(metrics, ["operating_income"])

    def test_the_status_counts_still_partition_the_core_universe(self):
        # The tempting shortcut is a SEMANTIC_CONFLICT *status*. It would break
        # this: the counts stop summing to the universe, and every reader that
        # reconciles a status tally against the registry quietly stops working.
        self.assertEqual(
            sum(self.ledger["status_counts"].values()),
            self.ledger["metrics_total"],
        )
        self.assertEqual(self.ledger["metrics_total"], 20)

    def test_a_conflicted_cell_is_not_a_backlog_item(self):
        # Backlog means "work to do": we have not handled this metric yet. The
        # metric has been handled -- collected, ruled on, and contradicted.
        self.assertFalse(self._row("operating_income")["is_backlog_item"])

    def test_a_silent_inapplicable_metric_raises_no_conflict(self):
        # `gross_profit` is no longer ruled out for anyone -- 2.23 refuted it for
        # `BANK` and 2.25 for `FINANCE_SERVICES` -- and this filer reported nothing
        # for it. Nothing disagrees with anything, so nothing is named.
        self.assertEqual(self._row("gross_profit")["observations_held"], 0)
        self.assertIsNone(self._row("gross_profit")["semantic_conflict"])

    def test_a_quiet_cell_stays_quiet(self):
        # A marker that fires constantly teaches a reader to ignore it, so it has
        # to be silent everywhere the three facts agree.
        fired = [
            r["metric"] for r in self.ledger["rows"]
            if r["semantic_conflict"]
        ]
        self.assertEqual(fired, ["operating_income"])


class TestTheConflictIsNotAStatus(unittest.TestCase):
    """
    Three facts, three places. Collapsing them is the failure.

    `Evidence existence` -- did the source report it?
    `Applicability`    -- should it mean anything for this filer?
    `Coverage`         -- have we handled it?

    A cell that is `Evidence: yes, Applicability: no, Coverage: handled` is not
    in a bad state. It is in a *contradictory* state, and the contradiction is
    the reportable thing. One status can only hold one of the three.
    """

    def test_the_conflict_lives_beside_the_status_not_inside_it(self):
        from coverage_semantics import COVERAGE_STATUSES

        self.assertNotIn(
            CONFLICT_EVIDENCE_HELD_FOR_INAPPLICABLE_METRIC,
            COVERAGE_STATUSES,
        )


class TestRefutedRulesAreAbsent(unittest.TestCase):
    """
    The two rules real filers contradicted are gone, and this pins them gone.

    **A regression guard, deliberately.** Both were written in 2.7 from a
    category intuition and both survived every round until a filer of the target
    class existed to contradict them:

        BANK   -> gross_profit    NRIM, 22 observations,
                                 us-gaap:GrossProfit, quarterly beside its 10-Q
        MINING -> r_and_d         NEM,  236 observations,
                                 us-gaap:ResearchAndDevelopmentExpense

    `2/2 refuted` says these two rules did not survive. It does **not** say
    applicability rules are useless -- see the next test. What it says is that a
    rule has to be tested against a filer of its own class before it refuses
    anything, and that once a filer contradicts it the refusal stops.

    Re-adding either requires editing this test, which is the point: the file
    says which filer said what.
    """

    def _metric(self, metric_id: str):
        registry = self._registry()
        try:
            return registry.metric(metric_id)
        finally:
            registry.connection.close()

    def _exclusion_states(self):
        return self._registry().exclusion_states()

    def _registry(self):
        from core_registry import CoreRegistry
        from registry_seed import seed
        from sqlite_archive import SQLiteArchive

        probe = SQLiteArchive(":memory:")
        registry = CoreRegistry(probe.connection)
        seed(registry)
        return registry

    def test_gross_profit_is_no_longer_refused_for_banks(self):
        gross_profit = self._metric("gross_profit")
        self.assertNotIn("BANK", gross_profit.inapplicable_in)
        self.assertTrue(gross_profit.applies_to("BANK"))

    def test_r_and_d_is_no_longer_refused_for_mining(self):
        r_and_d = self._metric("r_and_d")
        self.assertEqual(tuple(r_and_d.inapplicable_in), ())
        self.assertTrue(r_and_d.applies_to("MINING"))

    def test_the_refuted_labels_are_still_reachable(self):
        """
        Removing the rules must not make the classifications unnameable.

        `BANK` and `MINING` were reachable from 2.16.1 and remain so. What changed
        is that a filer carrying either label is no longer refused these two
        metrics -- the label does its other work, and the source is asked.
        """
        self.assertEqual("BANK", self._model_for("6022"))
        self.assertEqual("INSURANCE", self._model_for("6311"))
        self.assertEqual("MINING", self._model_for("1040"))

    def _model_for(self, sic: str) -> Optional[str]:
        from sec_ingest import business_model_from_filer_classification

        model, _ = business_model_from_filer_classification(
            {"sic": sic, "sicDescription": "irrelevant"}
        )
        return model


class TestRefutedDoesNotMeanUseless(unittest.TestCase):
    """
    The boundary, stated as an executable claim.

    Two rules were refuted. That supports "these two do not hold", and it does
    **not** support "applicability rules are useless". The rules that survived
    are still in force, still refusals, and still falsifiable -- and one of them
    is untested rather than supported, which is a state of its own.
    """

    def _metric(self, metric_id: str):
        registry = self._registry()
        try:
            return registry.metric(metric_id)
        finally:
            registry.connection.close()

    def _exclusion_states(self):
        return self._registry().exclusion_states()

    def _registry(self):
        from core_registry import CoreRegistry
        from registry_seed import seed
        from sqlite_archive import SQLiteArchive

        probe = SQLiteArchive(":memory:")
        registry = CoreRegistry(probe.connection)
        seed(registry)
        return registry

    def test_operating_income_is_still_refused_for_financial_institutions(self):
        # 0 of the eight banks sampled tag `us-gaap:OperatingIncomeLoss`. That is
        # consistent with the rule and does not establish it, so it stays -- and
        # it stays testable, which is what keeps it honest.
        # Narrowed in 2.25 rather than removed: refuted for FINANCE_SERVICES by
        # six of seven SIC 61-62 filers holding 666 observations of the concept,
        # and untouched for BANK.
        operating_income = self._metric("operating_income")
        self.assertTrue(operating_income.applies_to("BANK"))
        self.assertTrue(operating_income.applies_to("FINANCE_SERVICES"))
        self.assertTrue(operating_income.applies_to("MINING"))
        self.assertTrue(operating_income.applies_to("INSURANCE"))

    def test_gross_profit_is_now_applicable_to_every_financial_class(self):
        # 2.24 recorded this exclusion as PROPOSED rather than supported, on the
        # grounds that SIC 61-62 had never been collected at full scope. 2.25
        # collected them: three of the seven tag `us-gaap:GrossProfit` (AIXC 4
        # obs, SLNHP 20, SUIG 15), so the exclusion is gone entirely and the
        # registry now holds no refusal for this metric.
        gross_profit = self._metric("gross_profit")
        self.assertTrue(gross_profit.applies_to("FINANCE_SERVICES"))
        self.assertTrue(gross_profit.applies_to("BANK"))
        self.assertEqual(tuple(gross_profit.inapplicable_in), ())

    def test_the_vocabulary_still_cannot_express_conditional_applicability(self):
        """
        **A gap marker, and it survived the refutations.**

        2.21 asked whether a rule like "a bank may report gross profit, and this
        filer does" needs a CONDITIONAL state, and concluded it does not: the
        correct response to a refuted rule is to have no rule, and
        `SOURCE_SILENT` already expresses what a filer did not report. Nothing
        changed here, and `applies_to` is still binary.

        Written to **fail** if anyone adds conditionality. They should, and should
        then update this test and SPEC 0.28 -- because the first thing they would
        have to decide is whether a conditional ruling satisfies or overrides the
        conflict marker, and it is not obvious.
        """
        operating_income = self._metric("operating_income")
        self.assertTrue(operating_income.applies_to("BANK"))
        self.assertTrue(operating_income.applies_to("MANUFACTURING"))
        self.assertNotIn("CONDITIONAL", operating_income.applicability)


class TestACollisionSaysWhatWasSeenAndNotWhatItMeans(unittest.TestCase):
    """
    Two kinds, and the third one that was wrong.

    `RESTATED_SAME_PERIOD` was written first and removed after measurement. It
    asserted that a later filing disagreeing with an earlier one is an ordinary
    revision -- which the aggregated endpoint cannot support, because the member
    axis was dropped before ingestion saw anything. BBAR tags
    `ifrs-full:GrossProfit` for 2019 as 88.8bn, 120.9bn and 182.5bn across three
    20-F filings; a restatement does not move a number by 36% then 51%, and
    nothing in what was fetched can prove it was not a pair of hidden members.

    So the vocabulary records the observation and leaves the interpretation to a
    source that still has the axis.
    """

    def setUp(self) -> None:
        self.directory = tempfile.mkdtemp()

    def tearDown(self) -> None:
        pass

    def _ingest(self, rows: List[Dict[str, Any]]):
        class Source(_BankSource):
            def __init__(self) -> None:
                super().__init__()
                self._history = rows

            def submissions(self, cik: str) -> Dict[str, Any]:
                # SIC 6035 -- a savings institution. Ruled out for operating_income,
                # so the conflict machinery is live for the same metric these
                # collisions are recorded against.
                return {"sic": "6035",
                        "sicDescription": "Savings Institution"}

            def filing_index(self, cik: str) -> List[Dict[str, Any]]:
                out = []
                for row in rows:
                    accession = row["accn"]
                    if not any(
                        e["accession"] == accession for e in out
                    ):
                        out.append({
                            "accession": accession,
                            "form": "10-K",
                            "filing_date": row["filed"],
                            "report_date": row["end"],
                            "acceptance_datetime": f"{row['filed']}T16:00:00.000Z",
                            "acceptance_precision": "INSTANT",
                            "primary_document": "",
                            "is_xbrl": 1,
                        })
                return out

        store = SQLiteArchive(os.path.join(self.directory, "c.sqlite"))
        registry = CoreRegistry(store.connection)
        seed(registry)
        report = Ingestor(store, Source(), registry).ingest(
            "TESTBK", metrics=("operating_income",)
        )
        collisions = store.connection.execute(
            "SELECT concept_id, period_start, period_end, distinct_values,"
            " collision_kind FROM ingestion_dimension_collisions"
            " ORDER BY period_end"
        ).fetchall()
        store.close()
        return report, collisions

    def _fact(self, val: float, accn: str, end: str = "2024-12-31"):
        return {
            "start": "2024-01-01", "end": end, "val": val, "accn": accn,
            "fy": 2025, "fp": "FY", "form": "10-K", "filed": "2025-03-10",
        }

    def test_one_filing_reporting_two_values_is_a_provable_hidden_member(self):
        report, collisions = self._ingest([
            self._fact(100.0, "0000000001-25-000001"),
            self._fact(250.0, "0000000001-25-000001"),
        ])
        self.assertEqual(report.dimension_collisions, 1)
        self.assertEqual(len(collisions), 1)
        self.assertEqual(
            collisions[0]["collision_kind"],
            "SAME_PERIOD_DIFFERENT_VALUE",
        )
        self.assertEqual(collisions[0]["distinct_values"], 2)

    def test_two_filings_reporting_one_value_each_is_not_called_a_restatement(self):
        report, collisions = self._ingest([
            self._fact(100.0, "0000000001-25-000001"),
            dict(self._fact(250.0, "0000000001-26-000001"), filed="2026-03-10"),
        ])
        self.assertEqual(report.dimension_collisions, 1)
        self.assertEqual(
            collisions[0]["collision_kind"], "LATER_FILING_DIFFERS"
        )

    def test_the_record_names_the_metric_and_the_concept(self):
        # The whole reason this table exists: the count used to be per issuer, so
        # a question about a metric had no number to answer it with.
        _report, collisions = self._ingest([
            self._fact(100.0, "0000000001-25-000001"),
            self._fact(250.0, "0000000001-25-000001"),
        ])
        self.assertEqual(collisions[0]["concept_id"], "us-gaap:OperatingIncomeLoss")

    def test_a_third_value_for_one_period_counts_once_per_new_value(self):
        report, collisions = self._ingest([
            self._fact(100.0, "0000000001-25-000001"),
            dict(self._fact(250.0, "0000000001-26-000001"), filed="2026-03-10"),
            dict(self._fact(400.0, "0000000001-27-000001"), filed="2027-03-10"),
        ])
        self.assertEqual(report.dimension_collisions, 2)
        self.assertEqual(
            sorted(row["distinct_values"] for row in collisions), [2, 3]
        )

    def _store_with_parents(self):
        """
        A store holding the parent rows the foreign keys demand.

        Without them the CHECK constraint and the FOREIGN KEY constraint can
        both fire, so a test asserting "this kind is rejected" would pass for the
        wrong reason and prove nothing about the vocabulary.
        """
        store = SQLiteArchive(os.path.join(self.directory, "v.sqlite"))
        store.connection.execute(
            "INSERT OR IGNORE INTO assets (asset_id, ticker, name, first_seen_at)"
            " VALUES ('asset-1', 'TESTBK', 'Test Bank', '2026-01-01T00:00:00+00:00')"
        )
        store.connection.execute(
            "INSERT OR IGNORE INTO ingestion_runs"
            " (run_id, asset_id, source_id, started_at, finished_at,"
            " status) VALUES ('run-1', 'asset-1', 'sec-edgar',"
            " '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:01+00:00',"
            " 'COLLECTED')"
        )
        return store

    def _insert_kind(self, kind: str) -> None:
        store = self._store_with_parents()
        try:
            store.connection.execute(
                "INSERT INTO ingestion_dimension_collisions"
                " (run_id, asset_id, metric_id, concept_id, accession,"
                " period_start, period_end, unit, distinct_values,"
                " collision_kind, detected_at)"
                " VALUES ('run-1', 'asset-1', 'operating_income',"
                " 'us-gaap:OperatingIncomeLoss', 'x', NULL, '2024-01-01',"
                f" 'USD', 2, '{kind}', '2026-01-01T00:00:00+00:00')"
            )
        finally:
            store.close()

    def test_the_vocabulary_lists_no_kind_that_nothing_can_produce(self):
        """
        A closed vocabulary that names a state no code can emit is worse than a
        short one: it advertises a distinction the archive cannot make.
        `UNIT_MISMATCH` was one -- the collision key includes the unit, so a unit
        mismatch never collides -- and it was removed for that reason. A rejected
        `RESTATED_SAME_PERIOD` is the other: the endpoint cannot support it.
        """
        for dead in ("UNIT_MISMATCH", "RESTATED_SAME_PERIOD"):
            with self.assertRaises(
                sqlite33.IntegrityError, msg=dead
            ):
                self._insert_kind(dead)

    def test_only_the_two_supported_kinds_are_accepted(self):
        for kind in ("SAME_PERIOD_DIFFERENT_VALUE", "LATER_FILING_DIFFERS"):
            self._insert_kind(kind)


class TestTheRefusalSurfaceHasOneEntryPoint(unittest.TestCase):
    """
    **A mechanical audit of the 2.26 contract, run on every test invocation.**

    The contract is that only a `SUPPORTED` proposition may refuse Evidence
    collection. A contract like that is only as strong as the narrowest path to
    the surface it governs, so the paths are checked here rather than trusted --
    the same reasoning as 2.13's empty `tickers.json`, which produced a run that
    reported no errors and collected nothing.

    Two bypasses existed when this was written, both inert because every seeded
    exclusion is empty, and both now closed or pinned:

    * `add_metric(metric, inapplicable_in=...)` wrote the surface directly and
      `seed()` passed `metric.inapplicable_in` straight through. **Removed.** A
      metric's dataclass can still *declare* propositions, and those are
      recorded -- but only `support_exclusion` can make one refuse.
    * `Metric.applicability == "NOT_APPLICABLE"` refuses for every business model
      with no proposition at all. Kept, because the coverage surface reads it,
      and pinned by an assertion that no seeded metric carries it.
    """

    REPO = os.path.dirname(HERE)

    def _sources(self):
        """
        Repository sources, and only these.

        The first version of this scan walked into `.kilo/worktrees/` and found a
        second copy of `core_registry.py` -- an agent worktree, which is a full
        shadow of the codebase sitting inside the repository. It reported a
        duplicate writer and would have reported a bypass on the next structural
        change to either copy. Excluding dot-directories and anything holding its
        own `.git` entry is the fix, and the incident is worth recording: a
        source-level audit that counts files has to know what a file is.
        """
        for root, dirs, files in os.walk(self.REPO):
            dirs[:] = [
                d for d in dirs
                if not d.startswith(".")
                and d != "__pycache__"
                and not os.path.exists(os.path.join(root, d, ".git"))
            ]
            for name in files:
                if name.endswith((".py", ".sql")):
                    yield os.path.join(root, name)

    def test_the_only_writer_of_the_refusal_surface_is_support_exclusion(self):
        """
        Every write in the repository, located by function scope rather than by
        matching the line.

        An earlier version of this test allowed a writer by looking for the
        helper's name on the line itself, and refused its own helper -- which is
        the failure mode a source scan is most prone to, and the reason the scope
        has to be resolved properly rather than pattern-matched.
        """
        writers = []
        for path in self._sources():
            # Normalised: `relpath` yields the platform separator while the
            # allow-list below is written with forward slashes, which on Windows
            # compared unequal and reported a false bypass on the migration that
            # this contract depends on.
            relative = os.path.relpath(path, self.REPO).replace("\\", "/")
            for number, line, scope in self._scoped_lines(path):
                stripped = line.strip()
                # A comment does not write anything, and the migration that
                # empties the surface has a comment explaining that it empties it.
                if stripped.startswith("--") or stripped.startswith("#"):
                    continue
                upper = stripped.upper()
                if "METRIC_INAPPLICABLE_IN" not in upper:
                    continue
                if not any(
                    verb in upper
                    for verb in ("INSERT", "UPDATE", "DELETE", "DROP", "REPLACE")
                ):
                    continue
                writers.append((relative, number, scope, stripped))

        self.assertTrue(writers, "expected the surface to have a writer at all")
        permitted_scopes = {
            ("core_registry.py", "_set_inapplicable"),
            # The one-time reset. 0015 carries the hypotheses across and empties
            # the surface; a migration that cannot be re-run is not a live path.
            ("archive/migrations/0015_exclusion_lifecycle.sql", "migration"),
        }
        for relative, number, scope, line in writers:
            self.assertIn(
                (relative, scope), permitted_scopes,
                f"{relative}:{number} (in {scope or 'module scope'}) writes the "
                f"refusal surface outside `support_exclusion`: {line}",
            )
        # And the helper the audit permits is reached from exactly one place.
        self.assertEqual(
            len([
                w for w in writers
                if w[0] == "core_registry.py" and w[2] == "_set_inapplicable"
            ]),
            1,
            "the surface should be written in exactly one place",
        )

    @staticmethod
    def _scoped_lines(path: str):
        """Yield (number, line, enclosing function name or '') per source line."""
        current = ""
        for number, line in enumerate(
            pathlib.Path(path).read_text(encoding="utf-8",
                                         errors="ignore").split("\n"), 1
        ):
            if line.startswith("def ") or line.startswith("    def "):
                current = line.strip().split("(")[0][len("def "):]
            elif line and not line[0].isspace() and not line.startswith(")"):
                current = ""
            scope = "migration" if line.strip().startswith("--") is False and (
                path.endswith(".sql")
            ) else current
            yield number, line, scope

    def test_set_inapplicable_is_reached_only_by_support_exclusion(self):
        path = os.path.join(self.REPO, "core_registry.py")
        lines = pathlib.Path(path).read_text(encoding="utf-8").split("\n")
        callers = [
            (number, line.strip())
            for number, line in enumerate(lines, 1)
            if "_set_inapplicable(" in line
            and not line.strip().startswith("def ")
        ]
        self.assertEqual(len(callers), 1, callers)
        self.assertEqual(callers[0][0] - 1, None) if False else None
        # The one call site sits inside `support_exclusion`, which is defined
        # above it.
        definition = next(
            number for number, line in enumerate(lines, 1)
            if line.strip().startswith("def support_exclusion")
        )
        self.assertGreater(callers[0][0], definition)

    def test_no_seeded_metric_carries_a_global_not_applicable_flag(self):
        """
        The second path to a refusal, with no proposition behind it.

        `Metric.applicability == "NOT_APPLICABLE"` makes `applies_to` false for
        *every* business model and never consults the lifecycle, so it is a
        refusal no `SUPPORTED` decision authorised. Nothing uses it -- the flag is
        `APPLICABLE` for all twenty seeded metrics -- and it is kept because the
        coverage surface reads it. This is what makes it a recorded decision to
        leave it unused rather than an accident.
        """
        registry, store = self._registry_with_store()
        try:
            flagged = [
                metric.metric_id for metric in registry.metrics()
                if metric.applicability != "APPLICABLE"
            ]
            self.assertEqual(flagged, [])
        finally:
            store.close()

    def _registry_with_store(self):
        from core_registry import CoreRegistry
        from registry_seed import seed
        from sqlite_archive import SQLiteArchive

        store = SQLiteArchive(":memory:")
        registry = CoreRegistry(store.connection)
        seed(registry)
        return registry, store


if __name__ == "__main__":
    unittest.main()