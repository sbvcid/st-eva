"""
2.99 -- regression coverage for the retirement of the invalid legacy mapping.

    us-gaap:Revenues -> revenue, PARTIAL, 2016-09-24 .. 2018-09-29, scope null

2.98R established from the taxonomy documentation linkbase that `us-gaap:Revenues` is
BROADER_THAN_TARGET relative to `revenue`. `IDENTITY + PARTIAL` denotes a restricted
subset, so the seeded mapping described the relationship in the wrong direction. It
was retired rather than re-typed.

These tests pin the retirement and, more importantly, pin the three ways it could
quietly come back: as an `EXACT` mapping, with an invented scope, or by attaching a
destination that was never audited. They also pin that nothing else moved.
"""

from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core_registry import CoreRegistry  # noqa: E402
from registry_seed import seed  # noqa: E402
from sqlite_archive import SQLiteArchive  # noqa: E402

RETIRED = "us-gaap:Revenues"
DESTINATION = "revenue"

# Mappings that must be exactly as seeded, because 2.99 was not allowed to touch
# them. `SalesRevenueNet` is the other legacy revenue PARTIAL; the contract-revenue
# line is the destination's own EXACT source.
UNCHANGED_PRESENT = {
    "us-gaap:SalesRevenueNet": (DESTINATION, "PARTIAL"),
    "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax":
        (DESTINATION, "EXACT"),
}
# 2.99 retired the `Revenues` mapping and nothing else, and 2.100 then promoted
# `us-gaap:RestrictedStockExpense` to `sbc` as a measured PARTIAL on 2.95's
# cross-filer evidence -- a different decision, taken in a different round, on
# its own evidence.
#
# So the live invariant is not a list of concepts that stayed absent, which would
# need invented ids to express. It is that `sbc` has exactly two sources, both
# named, and that the promoted one is pinned to the mapping 2.100 declared rather
# than permitted to be anything. A third SBC source fails here.
SBC_EXACT_SOURCE = "us-gaap:ShareBasedCompensation"
PROMOTED_AFTER_299 = ("us-gaap:RestrictedStockExpense",)


class RegistryUnderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.store = SQLiteArchive(":memory:")
        cls.registry = CoreRegistry(cls.store.connection)
        seed(cls.registry)
        cls.store.connection.commit()
        cls.mappings: dict = {}
        for row in cls.registry.connection.execute(
                "SELECT metric_id, concept_id, mapping_type, relation_kind,"
                " effective_from, effective_to, scope_json FROM"
                " metric_concept_mapping"):
            cls.mappings.setdefault(row["concept_id"], []).append(dict(row))
        cls.concepts = {r["concept_id"] for r in
                        cls.registry.connection.execute(
                            "SELECT concept_id FROM concept_registry")}

    @classmethod
    def tearDownClass(cls) -> None:
        cls.store.close()


class TestTheInvalidMappingIsNotActive(RegistryUnderTest):

    def test_it_has_no_mapping_to_revenue(self) -> None:
        self.assertNotIn(RETIRED, self.mappings)

    def test_and_it_cannot_silently_become_exact(self) -> None:
        for mapping in self.mappings.get(RETIRED, []):
            self.assertNotEqual(mapping["mapping_type"], "EXACT")

    def test_and_no_scope_was_invented_to_rescue_it(self) -> None:
        for mapping in self.mappings.get(RETIRED, []):
            self.assertIsNone(mapping["scope_json"])

    def test_and_no_unaudited_destination_was_attached(self) -> None:
        for mapping in self.mappings.get(RETIRED, []):
            self.assertIn(mapping["metric_id"],
                          {DESTINATION, "sbc"},
                          "no destination other than revenue was ever audited "
                          "for this concept")

    def test_and_it_does_not_resolve_to_revenue(self) -> None:
        resolution = self.registry.resolve_source_concept(RETIRED)
        self.assertIsNone(resolution.destination_metric)
        self.assertNotEqual(resolution.destination_metric, DESTINATION)
        self.assertFalse(resolution.is_resolved)

    def test_but_the_concept_stays_registered(self) -> None:
        """
        Retirement removes a mapping, not a finding. The concept must remain in
        `concept_registry` so the evidence stays auditable through the registry
        itself and not only through a report.
        """
        self.assertIn(RETIRED, self.concepts)


class TestNothingElseMoved(RegistryUnderTest):

    def test_the_other_legacy_revenue_partial_is_untouched(self) -> None:
        for concept, (metric, mapping_type) in UNCHANGED_PRESENT.items():
            self.assertTrue(
                any(m["metric_id"] == metric
                    and m["mapping_type"] == mapping_type
                    for m in self.mappings.get(concept, [])),
                "%s must still be %s -> %s" % (concept, mapping_type, metric))

    def test_and_the_salesrevenuenet_window_is_unchanged(self) -> None:
        mapping = next(m for m in self.mappings["us-gaap:SalesRevenueNet"]
                       if m["metric_id"] == DESTINATION)
        self.assertEqual(mapping["effective_from"], "2007-09-29")
        self.assertEqual(mapping["effective_to"], "2018-06-30")

    def test_and_the_only_sbc_mappings_are_the_two_promoted_ones(self) -> None:
        """
        2.99's scope was the retirement. Since then 2.100 promoted exactly one
        concept to `sbc`, and it is pinned here to the declaration that made it
        -- IDENTITY, PARTIAL, the evidence-derived window, a measured scope.

        Stated as an exact set of the live `sbc` sources rather than as a list of
        concepts that must stay absent, because the second form needs invented
        ids to say anything and an invented id is rejected by the foreign key.
        """
        sources = self.registry.effective_metric_sources("sbc")
        self.assertEqual({s["concept"] for s in sources},
                         {SBC_EXACT_SOURCE} | set(PROMOTED_AFTER_299))
        self.assertEqual(len(sources), 2, sources)

    def test_and_the_later_promotion_is_the_one_that_was_declared(self) -> None:
        """
        Permitting the mapping would let it drift. It is still PARTIAL, still
        IDENTITY, still open-ended from the date 2.96 derived.
        """
        for concept in PROMOTED_AFTER_299:
            rows = self.mappings[concept]
            self.assertEqual(len(rows), 1, concept)
            mapping = rows[0]
            self.assertEqual(mapping["metric_id"], "sbc")
            self.assertEqual(mapping["mapping_type"], "PARTIAL")
            self.assertEqual(mapping["relation_kind"], "IDENTITY")
            self.assertEqual(mapping["effective_from"], "2008-12-31")
            self.assertIsNone(mapping["effective_to"])
            self.assertTrue(mapping["scope_json"],
                            "2.74 requires a measured PARTIAL to carry one")

    def test_and_the_registry_still_seeds(self) -> None:
        """
        A retirement that broke seeding would be a larger change than the one
        authorised, so the seed is asserted to build cleanly here.
        """
        store = SQLiteArchive(":memory:")
        try:
            registry = CoreRegistry(store.connection)
            seed(registry)
            store.connection.commit()
            total = registry.connection.execute(
                "SELECT count(*) FROM metric_concept_mapping").fetchone()[0]
            self.assertGreater(total, 0)
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()