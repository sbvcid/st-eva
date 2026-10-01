"""
The `debt` -> `long_term_debt` rename, and what it was not allowed to break.

2.33's product decision: Core `debt` denotes **long-term debt** and is renamed
accordingly. `total_debt` is a future semantic candidate and is deliberately not
created.

The implementation problem was not the rename. The **sealed 2.2.3 archive holds
180 observations recorded under `metric = 'debt'`**, and `observations.metric` is
part of the contract id -- so rewriting those rows would change `observation_id`
and manufacture new historical Evidence out of a naming decision. So the rename is
a semantic migration recorded alongside the old name:

    observation.metric = 'debt'      -- unchanged, forever
    metric_supersession              -- debt -> long_term_debt
    metric_registry                  -- 'debt' DEPRECATED, 'long_term_debt' ACTIVE

What changes is the question *what does this metric denote*, and it is answered by
following the supersession chain rather than by editing rows that are supposed to
be immutable.

Two contracts contain this metric -- the Core registry and the cross-source
contract in `data_contract.py` -- and they shared an id without anything
constraining them to mean the same thing. That is what drifted in the first place,
so the parity is now tested rather than assumed.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import data_contract  # noqa: E402
from core_registry import CoreRegistry  # noqa: E402
from coverage_semantics import scoped_ledger  # noqa: E402
from registry_seed import seed  # noqa: E402
from sec_ingest import Ingestor  # noqa: E402
from sqlite_archive import SQLiteArchive  # noqa: E402

LEGACY = "debt"
DECIDED = "long_term_debt"
# The concepts the decided target declares. Nothing outside this set may join it
# without a source concept saying of itself that it is part of long-term debt.
DECIDED_CONCEPTS = {
    "us-gaap:LongTermDebtCurrent",
    "us-gaap:LongTermDebtNoncurrent",
    "ifrs-full:CurrentPortionOfLongtermBorrowings",
    "ifrs-full:LongtermBorrowings",
}
EXCLUDED = {
    "us-gaap:ShortTermBorrowings",
    "us-gaap:DebtAndCapitalLeaseObligations",
    "us-gaap:LongTermDebtAndCapitalLeaseObligations",
    "us-gaap:OperatingLeaseLiabilityCurrent",
    "us-gaap:FinanceLeaseLiabilityCurrent",
}


def seeded() -> tuple:
    directory = tempfile.mkdtemp()
    store = SQLiteArchive(os.path.join(directory, "a.sqlite"))
    registry = CoreRegistry(store.connection)
    seed(registry)
    return store, registry


class TestTheDecisionIsRecorded(unittest.TestCase):
    """The rename happened, and the record says why."""

    def setUp(self) -> None:
        self.store, self.registry = seeded()

    def tearDown(self) -> None:
        self.store.close()

    def test_the_successor_is_active_and_the_predecessor_is_not(self):
        self.assertEqual(self.registry.metric(DECIDED).status, "ACTIVE")
        self.assertEqual(self.registry.metric(LEGACY).status, "DEPRECATED")

    def test_the_core_set_did_not_expand(self):
        """One metric leaves, one arrives. Renaming is not adding."""
        active = [m.metric_id for m in self.registry.metrics()
                  if m.status == "ACTIVE"]
        self.assertEqual(len(active), 20)
        self.assertNotIn(LEGACY, active)
        self.assertIn(DECIDED, active)

    def test_the_predecessor_row_is_retained_with_its_observations_resolvable(self):
        """
        Retained, not deleted.

        The row has to exist for historical observations to resolve at all, and
        `resolve_metric` is what carries the old name to the decided meaning.
        """
        self.assertIsNotNone(self.registry.metric(LEGACY))
        self.assertEqual(self.registry.resolve_metric(LEGACY), DECIDED)
        self.assertEqual(self.registry.resolve_metric(DECIDED), DECIDED)

    def test_the_supersession_record_names_the_evidence_it_rests_on(self):
        record = self.registry.supersession_of(LEGACY)
        self.assertIsNotNone(record)
        self.assertEqual(record["successor_id"], DECIDED)
        self.assertTrue(record["reason"])
        self.assertIn("231-debt-composition.json", record["evidence"] or "")
        self.assertIsNone(self.registry.supersession_of(DECIDED))

    def test_the_supersession_table_is_append_only(self):
        with self.assertRaises(Exception):
            self.store.connection.execute(
                "UPDATE metric_supersession SET successor_id = 'revenue'"
                " WHERE predecessor_id = ?", (LEGACY,))
        with self.assertRaises(Exception):
            self.store.connection.execute(
                "DELETE FROM metric_supersession WHERE predecessor_id = ?",
                (LEGACY,))


class TestTheMappingIsWhatTheDecisionSays(unittest.TestCase):
    """The components are the target; nothing else joined."""

    def setUp(self) -> None:
        self.store, self.registry = seeded()

    def tearDown(self) -> None:
        self.store.close()

    def test_exactly_the_four_current_and_non_current_concepts_are_mapped(self):
        mapped = {m.concept_id
                  for m in self.registry.mappings_for_metric(DECIDED)}
        self.assertEqual(mapped, DECIDED_CONCEPTS)

    def test_no_short_term_borrowing_and_no_lease_concept_joined(self):
        """
        The exclusions, stated in the decision, enforced in the registry.

        `total_debt` was not created and no concept was added to stand in for it.
        A filer's short-term borrowings are not long-term debt, and a
        lease-inclusive total is not either, so adding either would have quietly
        re-imported the quantity the rename excluded.
        """
        mapped = {m.concept_id
                  for m in self.registry.mappings_for_metric(DECIDED)}
        self.assertEqual(mapped & EXCLUDED, set())

    def test_short_term_borrowings_is_not_mapped_to_anything(self):
        """
        The specific thing the decision named.

        2.29 found `ShortTermBorrowings` in 11 of 75 filers and 2.31 showed it
        participates in no debt arithmetic. It is the obvious candidate for a
        broadened `debt`, and it must not be one.
        """
        target = data_contract.canonical_metric_id("us-gaap:ShortTermBorrowings")
        self.assertEqual(target, "us-gaap:ShortTermBorrowings")
        for metric in self.registry.metrics():
            mapped = {m.concept_id for m in
                      self.registry.mappings_for_metric(metric.metric_id)}
            self.assertNotIn("us-gaap:ShortTermBorrowings", mapped,
                             f"mapped to {metric.metric_id}")

    def test_both_taxonomies_reach_the_same_target(self):
        by_taxonomy = {}
        for mapping in self.registry.mappings_for_metric(DECIDED):
            by_taxonomy.setdefault(mapping.concept_id.split(":")[0], set()).add(
                mapping.mapping_type)
        self.assertEqual(set(by_taxonomy), {"us-gaap", "ifrs-full"})
        for types in by_taxonomy.values():
            self.assertEqual(types, {"PARTIAL"})

    def test_total_debt_does_not_exist(self):
        self.assertIsNone(self.registry.metric("total_debt"))
        self.assertIsNone(self.registry.supersession_of(DECIDED))
        active = {m.metric_id for m in self.registry.metrics()
                  if m.status == "ACTIVE"}
        self.assertNotIn("total_debt", active)


class TestTheDefinitionIsNoLongerCircular(unittest.TestCase):
    """
    A circular definition cannot be tested against anything, which is why the
    rename was necessary and not merely tidy.
    """

    def setUp(self) -> None:
        self.store, self.registry = seeded()

    def tearDown(self) -> None:
        self.store.close()

    def test_the_decided_definition_names_a_quantity(self):
        definition = self.registry.metric(DECIDED).semantic_definition.lower()
        self.assertIn("long-term debt", definition)
        self.assertIn("current and non-current", definition)
        # The old phrasing defined the metric by reference to itself.
        self.assertNotIn("under this metric definition", definition)

    def test_the_decided_definition_states_what_is_excluded(self):
        definition = self.registry.metric(DECIDED).semantic_definition.lower()
        for excluded in ("short-term borrowings", "total liabilities",
                         "lease-inclusive"):
            self.assertIn(excluded, definition)

    def test_the_predecessor_definition_records_the_withdrawal(self):
        definition = self.registry.metric(LEGACY).semantic_definition.lower()
        self.assertIn("superseded", definition)
        self.assertIn("withdrawn", definition)


class TestBothContractsStateTheSameTarget(unittest.TestCase):
    """
    The parity that was never tested, and that is how the drift happened.

    `debt` existed in two contracts -- the Core registry and the cross-source
    contract -- sharing an id with nothing constraining them to mean the same
    thing. Both said "total debt" while the registry's components summed to
    long-term debt. `total_debt` is now unestablished, and the target is
    long-term debt, so both contracts must say so and a test must keep them
    saying it.
    """

    def setUp(self) -> None:
        self.store, self.registry = seeded()

    def tearDown(self) -> None:
        self.store.close()

    def test_both_contracts_use_the_same_metric_id(self):
        self.assertIn(DECIDED, data_contract.CONTRACT_METRICS)
        self.assertNotIn(LEGACY, data_contract.CONTRACT_METRICS)

    def test_unit_family_agrees(self):
        self.assertEqual(data_contract.METRIC_UNITS[DECIDED], "currency")
        self.assertEqual(self.registry.metric(DECIDED).unit_family, "currency")

    def test_period_type_agrees(self):
        self.assertEqual(
            self.registry.metric(DECIDED).normal_period_type, "INSTANT")

    def test_both_definitions_exclude_the_same_things(self):
        registry_text = self.registry.metric(
            DECIDED).semantic_definition.lower()
        contract_text = data_contract.METRIC_CROSS_SOURCE_DEFINITIONS[
            DECIDED].lower()
        for excluded in ("short-term borrowings", "total liabilities",
                         "lease-inclusive"):
            self.assertIn(excluded, registry_text)
            self.assertIn(excluded, contract_text)

    def test_the_cross_source_definition_does_not_claim_total_debt(self):
        self.assertNotIn(
            "total debt",
            data_contract.METRIC_CROSS_SOURCE_DEFINITIONS[DECIDED].lower())

    def test_the_legacy_alias_still_resolves(self):
        self.assertEqual(
            data_contract.canonical_metric_id(LEGACY), DECIDED)
        self.assertEqual(
            data_contract.canonical_metric_id(DECIDED), DECIDED)
        self.assertEqual(
            data_contract.canonical_metric_id("revenue"), "revenue")


class TestHistoricalEvidenceIsUntouched(unittest.TestCase):
    """
    The hard rule, checked rather than asserted in a report.

    An observation filed before the rename keeps the metric it was filed under, and
    still resolves to the same mappings, so nothing about the archive changes and
    no new historical Evidence is created.
    """

    class _Source:
        """One filing, one concept, one metric -- filed under the legacy name."""

        # The ingestor reads these three counters off the provider; the fake
        # source is otherwise complete.
        documents_read = 0
        concept_fetches = 0
        network_fetches = 0

        def resolve_company(self, ticker):
            class Company:
                cik = "0000000001"
                name = "Test"
                exchanges = ()
            return Company()

        def submissions(self, cik):
            return {"sic": "6035", "sicDescription": "Savings Institution"}

        def filing_index(self, cik):
            return [{
                "accession": "0000000001-25-000001", "form": "10-K",
                "filing_date": "2025-03-10", "report_date": "2024-12-31",
                "acceptance_datetime": "2025-03-10T16:00:00.000Z",
                "acceptance_precision": "INSTANT",
                "primary_document": "", "is_xbrl": 1,
            }]

        def concept_history(self, cik, taxonomy, concept):
            if f"{taxonomy}:{concept}" != "us-gaap:LongTermDebtCurrent":
                return None
            return {"label": "Long-term Debt, Current Maturities", "units": {
                "USD": [{"start": None, "end": "2024-12-31", "val": 5000.0,
                         "accn": "0000000001-25-000001", "fy": 2024,
                         "fp": "FY", "form": "10-K", "filed": "2025-03-10"}]}}

        def documents_for(self, taxonomy, concept):
            return ()

    def _filed(self):
        store, registry = seeded()
        Ingestor(store, self._Source(), registry).ingest(
            "TESTBK", metrics=(LEGACY,), forms=("10-K",))
        return store, registry

    def test_the_observation_is_stored_under_the_name_it_was_filed_with(self):
        store, _ = self._filed()
        try:
            metrics = {row[0] for row in store.connection.execute(
                "SELECT DISTINCT metric FROM observations")}
            self.assertEqual(metrics, {LEGACY})
        finally:
            store.close()

    def test_the_observation_count_and_identity_do_not_change(self):
        store, _ = self._filed()
        try:
            count = store.connection.execute(
                "SELECT COUNT(*) FROM observations").fetchone()[0]
            distinct = store.connection.execute(
                "SELECT COUNT(DISTINCT source_fact_id) FROM observations"
            ).fetchone()[0]
            self.assertEqual(count, 1)
            self.assertEqual(distinct, 1)
        finally:
            store.close()

    def test_the_stored_observation_reaches_the_new_mappings(self):
        """
        The point of the supersession chain.

        Stored under `debt`, resolved to `long_term_debt`, and read through the
        concepts the successor declares -- so a historical row is not left
        stranded with no mapping the moment a metric is renamed.
        """
        store, registry = self._filed()
        try:
            asset = store.connection.execute(
                "SELECT asset_id FROM assets WHERE ticker = 'TESTBK'"
            ).fetchone()["asset_id"]
            ledger = scoped_ledger(store.connection, registry, asset, "TESTBK")
            row = next(r for r in ledger["rows"] if r["metric"] == LEGACY)
            self.assertEqual(row["observations_held"], 1)
            self.assertEqual(
                {m.concept_id for m in registry.mappings_for_metric(LEGACY)},
                DECIDED_CONCEPTS)
        finally:
            store.close()

    def test_a_renamed_metric_is_still_reported_on_the_coverage_surface(self):
        """
        Not dropped from the ledger.

        The active universe no longer lists `debt`, so an archive holding only
        legacy-named rows would silently lose them from the coverage surface --
        a regression caused entirely by a rename. The ledger therefore reports
        the active universe *plus* every metric the archive actually holds.
        """
        store, registry = self._filed()
        try:
            asset = store.connection.execute(
                "SELECT asset_id FROM assets WHERE ticker = 'TESTBK'"
            ).fetchone()["asset_id"]
            ledger = scoped_ledger(store.connection, registry, asset, "TESTBK")
            self.assertIn(LEGACY, {r["metric"] for r in ledger["rows"]})
            self.assertIn(DECIDED, {r["metric"] for r in ledger["rows"]})
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()