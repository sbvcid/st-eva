"""
Source-conditional supersession: `debt` -> `long_term_debt`.

## What changed and why it was invisible

2.33 recorded `debt -> long_term_debt` and made `mappings_for_metric` follow the
chain. That is correct for a metric-level question and wrong for an
observation-level one. A metric declares concepts; an observation carries one.
Following the chain made every one of the 8,193 historical `debt` rows look as
though it carried all four concepts the successor declares -- including the two
IFRS concepts whose destination 2.47 and 2.48 had not established.

The reason nobody saw it is the reason it matters: **the concept set does not
change when the chain is followed.** `resolve_metric('debt')` returns
`long_term_debt`, and `long_term_debt` declares exactly the four concepts `debt`
declared before the rename. Coverage counts, mapping counts and mapping types all
stay identical, so every existing invariant still passed while the semantics
were wrong.

So these tests are mostly about what a single observation is *not* given.

## The rule under test

    stored metric + source concept  ->  the mapping declared for that concept

and nothing else. No source concept is insufficient context, reported as such.
A concept with no declared mapping is unresolved, which is not refutation. The
stored metric is never rewritten.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from core_registry import CoreRegistry, ObservationMapping  # noqa: E402
from evidence_query import EvidenceQuery  # noqa: E402
from registry_seed import seed  # noqa: E402
from sec_ingest import Ingestor  # noqa: E402
from sqlite_archive import SQLiteArchive  # noqa: E402

LEGACY = "debt"
SUCCESSOR = "long_term_debt"

US_GAAP_CURRENT = "us-gaap:LongTermDebtCurrent"
US_GAAP_NONCURRENT = "us-gaap:LongTermDebtNoncurrent"
US_GAAP_CURRENT_METRIC = "long_term_debt_current"
US_GAAP_NONCURRENT_METRIC = "long_term_debt_noncurrent"
IFRS_NONCURRENT = "ifrs-full:LongtermBorrowings"
IFRS_CURRENT = "ifrs-full:CurrentPortionOfLongtermBorrowings"

# Every concept the successor declares. An observation resolving under the old
# blanket behaviour would be handed all of these.
SUCCESSOR_CONCEPTS = {
    US_GAAP_CURRENT, US_GAAP_NONCURRENT, IFRS_NONCURRENT, IFRS_CURRENT,
}

# Named by 2.49 as excluded from long-term debt, and named by 2.30 as present in
# the corpus. A concept outside the successor's set is the sharpest test of
# whether the blanket answer is being returned.
OUTSIDE_THE_SUCCESSOR_SET = "us-gaap:ShortTermBorrowings"


class _Source:
    """One filing, one concept, filed under the legacy metric name."""

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
        if f"{taxonomy}:{concept}" != US_GAAP_CURRENT:
            return None
        return {"label": "Long-term Debt, Current Maturities", "units": {
            "USD": [{"start": None, "end": "2024-12-31", "val": 5000.0,
                     "accn": "0000000001-25-000001", "fy": 2024,
                     "fp": "FY", "form": "10-K", "filed": "2025-03-10"}]}}

    def documents_for(self, taxonomy, concept):
        return ()


def seeded():
    directory = tempfile.mkdtemp()
    store = SQLiteArchive(os.path.join(directory, "a.sqlite"))
    registry = CoreRegistry(store.connection)
    seed(registry)
    return store, registry


class TestTheSupersessionStillHolds(unittest.TestCase):
    """Requirement 1: the rename is untouched. This is resolution, not migration."""

    def setUp(self) -> None:
        self.store, self.registry = seeded()

    def tearDown(self) -> None:
        self.store.close()

    def test_the_legacy_name_still_resolves_to_the_successor(self):
        self.assertEqual(self.registry.resolve_metric(LEGACY), SUCCESSOR)

    def test_the_relationship_is_still_recorded(self):
        record = self.registry.supersession_of(LEGACY)
        self.assertIsNotNone(record)
        self.assertEqual(record["successor_id"], SUCCESSOR)

    def test_the_change_did_not_make_the_two_metrics_unrelated(self):
        """
        They still supersede. What changed is which mappings are handed over.

        Revised in 2.67: the destination is no longer necessarily the successor.
        A concept that a component metric declares itself resolves to that
        component, and the supersession is still recorded underneath it.
        """
        self.assertEqual(
            self.registry.resolve_metric(LEGACY), SUCCESSOR)
        self.assertIsNotNone(self.registry.supersession_of(LEGACY))
        self.assertEqual(
            self.registry.mappings_for_observation(
                LEGACY, US_GAAP_CURRENT).resolved_metric_id,
            US_GAAP_CURRENT_METRIC)

    def test_the_core_metric_count_did_not_change(self):
        active = [m.metric_id for m in self.registry.metrics()
                  if m.status == "ACTIVE"]
        self.assertEqual(len(active), 20)

    def test_no_mapping_was_added_or_promoted(self):
        """The four concepts and their types are exactly what 2.33 declared."""
        declared = {(m.concept_id, m.mapping_type)
                    for m in self.registry.mappings_for_metric(SUCCESSOR)}
        self.assertEqual(declared,
                         {(c, "PARTIAL") for c in SUCCESSOR_CONCEPTS})


class TestResolutionIsConditionedOnTheSourceConcept(unittest.TestCase):
    """Requirements 2, 3, and the negative tests."""

    def setUp(self) -> None:
        self.store, self.registry = seeded()

    def tearDown(self) -> None:
        self.store.close()

    def test_the_resolver_accepts_a_source_concept(self):
        result = self.registry.mappings_for_observation(
            LEGACY, US_GAAP_NONCURRENT)
        self.assertEqual(result.source_concept, US_GAAP_NONCURRENT)
        self.assertTrue(result.is_resolved)

    def test_an_observation_gets_only_its_own_mapping(self):
        """
        The substantive change.

        Under the blanket path this observation would be handed all four
        successor concepts. Revised in 2.67: an IFRS concept has no authorised
        destination at all, so it is handed none. What remains true, and is the
        property worth keeping, is that it is never handed the successor's set.
        """
        result = self.registry.mappings_for_observation(
            LEGACY, US_GAAP_CURRENT)
        self.assertEqual(len(result.mappings), 1)
        self.assertEqual(result.mappings[0].concept_id, US_GAAP_CURRENT)

    def test_the_returned_set_is_not_the_successor_set(self):
        """
        Negative test, stated so a future edit cannot quietly pass.

        Asserted as a strict subset and as non-equality, because a superset
        containing the right mapping plus the other three would still fail the
        first test while looking correct to a reader skimming the payload.
        """
        for concept in SUCCESSOR_CONCEPTS:
            returned = {
                m.concept_id for m in
                self.registry.mappings_for_observation(LEGACY, concept).mappings
            }
            self.assertLess(returned, SUCCESSOR_CONCEPTS,
                            f"{concept} received the whole successor set")
            self.assertNotEqual(returned, SUCCESSOR_CONCEPTS, concept)
            # Exactly the observation's own concept, or nothing at all -- never a
            # sibling, and never an unauthorised destination.
            self.assertIn(returned, ({concept}, set()), concept)

    def test_an_unmapped_concept_receives_no_successor_mapping(self):
        result = self.registry.mappings_for_observation(
            LEGACY, OUTSIDE_THE_SUCCESSOR_SET)
        self.assertFalse(result.is_resolved)
        self.assertEqual(result.mappings, ())
        self.assertEqual(result.status,
                         ObservationMapping.UNRESOLVED_NO_APPLICABLE_MAPPING)

    def test_an_unmapped_concept_does_not_fall_back_to_all_successor_mappings(self):
        result = self.registry.mappings_for_observation(
            LEGACY, OUTSIDE_THE_SUCCESSOR_SET)
        self.assertEqual(result.mapping_types, ())
        self.assertNotIn(US_GAAP_CURRENT, {m.concept_id
                                           for m in result.mappings})

    def test_unresolved_is_not_refuted(self):
        """The reason has to say what it does and does not mean."""
        result = self.registry.mappings_for_observation(
            LEGACY, OUTSIDE_THE_SUCCESSOR_SET)
        self.assertIn("unresolved, not refuted", result.reason)

    def test_a_missing_source_concept_cannot_produce_a_positive_resolution(self):
        result = self.registry.mappings_for_observation(LEGACY, None)
        self.assertFalse(result.is_resolved)
        self.assertEqual(result.mappings, ())
        self.assertEqual(result.status,
                         ObservationMapping.UNRESOLVED_NO_SOURCE_CONCEPT)

    def test_a_missing_source_concept_does_not_fall_back_to_the_successor_set(self):
        result = self.registry.mappings_for_observation(LEGACY, None)
        self.assertEqual(
            {m.concept_id for m in result.mappings} & SUCCESSOR_CONCEPTS,
            set())

    def test_an_empty_source_string_is_also_insufficient_context(self):
        result = self.registry.mappings_for_observation(LEGACY, "")
        self.assertFalse(result.is_resolved)
        self.assertEqual(result.status,
                         ObservationMapping.UNRESOLVED_NO_SOURCE_CONCEPT)

    def test_resolution_is_deterministic(self):
        """Requirement 11. Twice, byte-identical."""
        for concept in sorted(SUCCESSOR_CONCEPTS) + [OUTSIDE_THE_SUCCESSOR_SET]:
            first = self.registry.mappings_for_observation(
                LEGACY, concept).contract_dict()
            second = self.registry.mappings_for_observation(
                LEGACY, concept).contract_dict()
            self.assertEqual(
                json.dumps(first, sort_keys=True),
                json.dumps(second, sort_keys=True),
                concept)

    def test_a_resolved_status_without_a_mapping_is_not_a_resolution(self):
        """
        The vacuous-truth guard, tested directly rather than trusted.

        `status` and `mappings` are separate fields, so a caller could one day
        set the status without a mapping behind it. `is_resolved` requires both,
        so an empty mapping set can never read as resolved.
        """
        empty = ObservationMapping(
            stored_metric_id=LEGACY,
            resolved_metric_id=SUCCESSOR,
            source_concept=US_GAAP_CURRENT,
            mappings=(),
            status=ObservationMapping.RESOLVED,
        )
        self.assertFalse(empty.is_resolved)
        self.assertFalse(bool(empty.mapping_types))

    def test_an_empty_candidate_set_does_not_produce_a_verdict(self):
        """
        No `all([...])` anywhere in the resolution path.

        Every concept that is not declared must come back unresolved, not
        vacuously approved, so this walks the whole successor set and asserts
        the two halves are exact and disjoint.
        """
        resolved = {
            concept for concept in SUCCESSOR_CONCEPTS | {OUTSIDE_THE_SUCCESSOR_SET}
            if self.registry.mappings_for_observation(
                LEGACY, concept).is_resolved
        }
        # Revised in 2.67: only the concepts a component metric declares itself
        # resolve. The two IFRS concepts are characterisation without an
        # authorised destination, so they are absent -- and the anti-vacuous
        # property this test exists for is unchanged: the two halves are exact
        # and disjoint.
        self.assertEqual(resolved, {US_GAAP_CURRENT, US_GAAP_NONCURRENT})
        self.assertEqual(resolved & {OUTSIDE_THE_SUCCESSOR_SET}, set())
        self.assertEqual(resolved & {IFRS_NONCURRENT, IFRS_CURRENT}, set())


class TestTheFourCriticalCases(unittest.TestCase):
    """Requirements 4, 5, 6, 7 -- one class at a time."""

    def setUp(self) -> None:
        self.store, self.registry = seeded()

    def tearDown(self) -> None:
        self.store.close()

    def _resolve(self, concept):
        return self.registry.mappings_for_observation(LEGACY, concept)

    def test_case_1_us_gaap_current_keeps_its_component_identity(self):
        """
        Revised in 2.67.

        2.50 recorded this as resolving to the successor with a PARTIAL
        component mapping. 2.66 measured that as a collapse onto the total, and
        2.67 restores the component: the metric that declares this concept
        itself wins outright over anything inherited through the supersession.
        """
        result = self._resolve(US_GAAP_CURRENT)
        self.assertTrue(result.is_resolved)
        self.assertEqual(result.stored_metric_id, LEGACY)
        self.assertEqual(result.resolved_metric_id, US_GAAP_CURRENT_METRIC)
        self.assertEqual(result.mapping_types, ("EXACT",))
        self.assertEqual(result.mappings[0].metric_id, US_GAAP_CURRENT_METRIC)

    def test_case_2_us_gaap_non_current_keeps_its_component_identity(self):
        result = self._resolve(US_GAAP_NONCURRENT)
        self.assertTrue(result.is_resolved)
        self.assertEqual(result.stored_metric_id, LEGACY)
        self.assertEqual(result.resolved_metric_id,
                         US_GAAP_NONCURRENT_METRIC)
        self.assertEqual(result.mapping_types, ("EXACT",))

    def test_case_3_ifrs_non_current_is_not_resolved(self):
        """
        2.47 returned SUPPORTED_PARTIAL: the accounting object matches the
        non-current component, but the realised breadth is filer-dependent, so
        provider-agnostic equivalence to `LongTermDebtNoncurrent` was not
        established.

        Revised in 2.67 from "resolved as PARTIAL" to **unresolved**. 2.66
        measured why: an inherited PARTIAL proposition is a characterisation,
        not a decision, and treating it as a destination exposed all 417
        unauthorised IFRS rows as total long-term debt -- 2.45's
        BLOCKED_SUPERSESSION, still live. Unresolved is not refuted.
        """
        result = self._resolve(IFRS_NONCURRENT)
        self.assertFalse(result.is_resolved)
        self.assertEqual(result.mappings, ())
        self.assertEqual(result.stored_metric_id, LEGACY)
        self.assertEqual(result.status,
                         ObservationMapping.UNRESOLVED_NO_APPLICABLE_MAPPING)
        self.assertIn("unresolved, not refuted", result.reason.lower())
        # Name and concept are separate questions. The metric *name* `debt` was
        # superseded regardless; the *concept* has no authorised destination.
        # Reporting the successor here while refusing to resolve is what keeps
        # the two apart.
        self.assertEqual(result.resolved_metric_id, SUCCESSOR)

    def test_case_4_ifrs_current_is_not_promoted_by_the_sibling_or_the_parent(self):
        """
        2.48 characterised the object and asserted mapping readiness
        `NOT_ASSERTED`. It must not gain a semantic mapping merely because a
        sibling sits on the same metric or because a supersession exists.
        """
        result = self._resolve(IFRS_CURRENT)
        # Revised in 2.67: unresolved, not "handed a sibling's mapping".
        self.assertFalse(result.is_resolved)
        self.assertEqual(result.mappings, ())
        self.assertEqual(result.stored_metric_id, LEGACY)
        self.assertEqual(result.status,
                         ObservationMapping.UNRESOLVED_NO_APPLICABLE_MAPPING)

    def test_the_two_ifrs_classes_do_not_see_each_other(self):
        """
        Revised in 2.67. Neither resolves, so neither can see the other -- the
        separation is now total rather than a matter of not picking a sibling.
        """
        self.assertEqual(
            self._resolve(IFRS_NONCURRENT).mappings, ())
        self.assertEqual(
            self._resolve(IFRS_CURRENT).mappings, ())

    def test_us_gaap_mappings_are_unchanged_from_what_the_registry_declares(self):
        """
        Requirement 7: nothing about the registry moved.

        Revised in 2.67 to compare against the declaring metric rather than the
        successor, because the destination is now the component metric. The
        assertion is unchanged in substance: the mapping returned is exactly the
        one the registry declares.
        """
        for concept, metric_id in ((US_GAAP_CURRENT, US_GAAP_CURRENT_METRIC),
                                   (US_GAAP_NONCURRENT,
                                    US_GAAP_NONCURRENT_METRIC)):
            declared = next(
                m for m in self.registry.mappings_for_metric(metric_id)
                if m.concept_id == concept)
            resolved = self._resolve(concept).mappings[0]
            self.assertEqual(resolved, declared, concept)


class TestExistingCallersAreNotSilentlyBroadened(unittest.TestCase):
    """Requirement 12."""

    def setUp(self) -> None:
        self.store, self.registry = seeded()

    def tearDown(self) -> None:
        self.store.close()

    def test_the_metric_level_query_still_returns_the_full_declared_set(self):
        """A ledger, a gate or an ingestion plan wants the declaration."""
        declared = {m.concept_id
                    for m in self.registry.mappings_for_metric(LEGACY)}
        self.assertEqual(declared, SUCCESSOR_CONCEPTS)

    def test_the_metric_level_query_is_unchanged_by_this_change(self):
        declared = {(m.concept_id, m.mapping_type, m.effective_from,
                     m.effective_to)
                    for m in self.registry.mappings_for_metric(LEGACY)}
        self.assertEqual(
            declared,
            {(m.concept_id, m.mapping_type, m.effective_from, m.effective_to)
             for m in self.registry.mappings_for_metric(SUCCESSOR)})

    def test_a_metric_with_no_supersession_resolves_its_own_concepts(self):
        result = self.registry.mappings_for_observation(
            "capex", "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment")
        self.assertTrue(result.is_resolved)
        self.assertFalse(result.is_superseded)
        self.assertEqual(result.stored_metric_id, "capex")
        self.assertEqual(result.resolved_metric_id, "capex")

    def test_a_metric_with_no_supersession_still_filters_by_concept(self):
        """The condition is about the concept, not about being superseded."""
        result = self.registry.mappings_for_observation(
            "capex", OUTSIDE_THE_SUCCESSOR_SET)
        self.assertFalse(result.is_resolved)
        self.assertEqual(result.mappings, ())


class TestSupersessionMetadataIsOptional(unittest.TestCase):
    """
    The regression 2.50 introduced and had to fix.

    An archive that predates the supersession table -- a read-only consumer, or a
    fixture that builds its schema directly -- has a perfectly good `debt`
    metric. Asking for its supersession must not raise, for the same reason
    `resolve_metric` does not.
    """

    def test_an_archive_without_the_table_still_resolves(self):
        """
        The guard, exercised rather than skipped.

        A fresh archive creates the table, so the only honest way to test the
        absence is to remove it -- which is what an archive predating 2.33
        looks like to the code.
        """
        store, registry = seeded()
        try:
            registry.connection.execute("DROP TABLE metric_supersession")
            self.assertFalse(registry._has_table("metric_supersession"))
            self.assertIsNone(registry.supersession_of(LEGACY))
            # `debt` still resolves; there is just nothing superseding it, so it
            # stands as itself and can inherit nothing.
            self.assertEqual(registry.resolve_metric(LEGACY), LEGACY)
            # Revised in 2.67. Without the supersession table the legacy metric
            # stands as itself, but this concept is claimed by a *component*
            # metric directly and that declaration never depended on any
            # supersession -- so it resolves to the component either way. The
            # property under test is that nothing crashes and nothing is
            # inherited from a chain that does not exist.
            result = registry.mappings_for_observation(
                LEGACY, US_GAAP_CURRENT)
            self.assertTrue(result.is_resolved)
            self.assertFalse(result.is_superseded)
            self.assertEqual(result.resolved_metric_id,
                             US_GAAP_CURRENT_METRIC)
            self.assertEqual(result.status, ObservationMapping.RESOLVED)
            self.assertIsNone(result.supersession)
        finally:
            store.close()


class TestHistoricalObservationsAreUntouched(unittest.TestCase):
    """
    Requirements 8, 9, 10.

    Resolution adds meaning. It must not touch a row, change an identity, or
    create an observation -- and `observations.metric` is part of the contract
    id, so a rewrite would manufacture new historical evidence out of a naming
    decision.
    """

    def _filed(self):
        store, registry = seeded()
        Ingestor(store, _Source(), registry).ingest(
            "TESTBK", metrics=(LEGACY,), forms=("10-K",))
        return store, registry

    def test_the_observation_is_still_stored_under_the_legacy_name(self):
        store, _ = self._filed()
        try:
            metrics = {row[0] for row in store.connection.execute(
                "SELECT DISTINCT metric FROM observations")}
            self.assertEqual(metrics, {LEGACY})
        finally:
            store.close()

    def test_nothing_was_appended_under_the_successor_or_its_components(self):
        store, _ = self._filed()
        try:
            metrics = {row[0] for row in store.connection.execute(
                "SELECT DISTINCT metric FROM observations")}
            for forbidden in (SUCCESSOR, "long_term_debt_current",
                              "long_term_debt_noncurrent"):
                self.assertNotIn(forbidden, metrics)
            self.assertEqual(
                store.connection.execute(
                    "SELECT COUNT(*) FROM observations").fetchone()[0], 1)
        finally:
            store.close()

    def test_observation_identity_is_unchanged_by_resolving(self):
        store, registry = self._filed()
        try:
            before = store.connection.execute(
                "SELECT observation_id, contract_id, metric, concept,"
                " value_json FROM observations").fetchall()
            self.assertEqual(len(before), 1)
            registry.mappings_for_observation(
                before[0]["metric"], before[0]["concept"])
            after = store.connection.execute(
                "SELECT observation_id, contract_id, metric, concept,"
                " value_json FROM observations").fetchall()
            self.assertEqual([tuple(r) for r in before],
                             [tuple(r) for r in after])
        finally:
            store.close()

    def test_resolution_writes_nothing_to_the_registry(self):
        store, registry = self._filed()
        try:
            before = store.connection.execute(
                "SELECT COUNT(*) FROM metric_concept_mapping").fetchone()[0]
            for concept in SUCCESSOR_CONCEPTS:
                registry.mappings_for_observation(LEGACY, concept)
            after = store.connection.execute(
                "SELECT COUNT(*) FROM metric_concept_mapping").fetchone()[0]
            self.assertEqual(before, after)
        finally:
            store.close()


class TestTheQuerySurfaceReportsStoredAndResolvedSeparately(unittest.TestCase):
    """
    The caller update.

    `_semantic_for` resolved observation -> concept -> metric and ignored the
    stored metric entirely, so a legacy row could not show that it was carrying a
    superseded identity. Stored and resolved are now both reported, and the
    identity is reported rather than rewritten.
    """

    def _filed(self):
        store, registry = seeded()
        Ingestor(store, _Source(), registry).ingest(
            "TESTBK", metrics=(LEGACY,), forms=("10-K",))
        query = EvidenceQuery(connection=store.connection)
        contract_id = store.connection.execute(
            "SELECT contract_id FROM observations WHERE metric = ?",
            (LEGACY,)).fetchone()[0]
        return store, registry, query.get_observation(contract_id)

    def test_a_legacy_observation_keeps_its_stored_identity_in_the_payload(self):
        store, _, row = self._filed()
        try:
            semantic = row["semantic"]
            self.assertEqual(semantic["stored_metric"], LEGACY)
            # Revised in 2.67: the destination is the component the source
            # concept declares, not the successor total.
            self.assertEqual(semantic["resolved_metric"],
                             US_GAAP_CURRENT_METRIC)
            self.assertTrue(semantic["metric_superseded"])
            # The figure itself is still filed under the legacy name.
            self.assertEqual(row["metric"], LEGACY)
        finally:
            store.close()

    def test_the_inherited_mapping_is_conditioned_on_the_observation(self):
        store, _, row = self._filed()
        try:
            inherited = row["semantic"]["inherited_mapping"]
            self.assertTrue(inherited["resolved"])
            self.assertEqual(inherited["source_concept"], US_GAAP_CURRENT)
            self.assertEqual(
                [m["concept_id"] for m in inherited["mappings"]],
                [US_GAAP_CURRENT])
        finally:
            store.close()

    def test_the_payload_states_the_stored_metric_is_not_rewritten(self):
        store, _, row = self._filed()
        try:
            self.assertEqual(row["semantic"]["stored_metric"], row["metric"])
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()