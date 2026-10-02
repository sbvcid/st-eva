"""
2.39 -- the IFRS PPE acquisition concept promoted to Core `capex` as EXACT.

The semantic work is 2.35 (no label, no description in `companyfacts`),
2.36 (the presentation: cash-flow statement, investing activities, "Acquisitions
of property, plant and equipment") and 2.37 (the XBRL instance: one fact, one
value per period per unit, no `sign="-"`, so the second appearance is the same
fact seen as an asset-class breakdown rather than a second transaction).

What these tests pin is the *promotion*, not the semantics. The semantics live in
the mapping's own notes and in the report that argued them; a test cannot re-argue
them, and should not pretend to.

**Deliberately absent: any test asserting that numeric equality with another capex
concept proves equivalence.** It does not, it never did, and 2.38 measured why --
the equivalence here rests on the presentation and the instance, and a value
comparison would be supporting evidence at best. Equally, the absence of a
cross-framework comparator is not asserted as a negative: it is a check that could
not be run, and is recorded as such.

Item 10 is the one worth reading: the TSM case presents the same fact twice, and
the archive must not manufacture two observations out of one presentation being
rendered in two places.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import data_contract  # noqa: E402
from core_registry import CoreRegistry  # noqa: E402
from registry_seed import seed  # noqa: E402
from sec_ingest import Ingestor  # noqa: E402
from sqlite_archive import SQLiteArchive  # noqa: E402

IFRS = "ifrs-full"
PROMOTED = f"{IFRS}:PurchaseOfPropertyPlantAndEquipment" \
           f"ClassifiedAsInvestingActivities"
US_GAAP_EXACT = "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment"
US_GAAP_PARTIAL = "us-gaap:PaymentsToAcquireProductiveAssets"
REFUTED_NOT_MAPPED = ("ifrs-full:"
                      "AdditionsOtherThanThroughBusinessCombinationsPropertyPlant"
                      "AndEquipment")
STILL_UNDECIDED = "us-gaap:PaymentsForCapitalImprovements"

CAVEAT_FRAGMENT = (
    "TSM's non-cash transaction schedule presents the same XBRL fact and value "
    "under a non-cash heading"
)


def seeded() -> tuple:
    store = SQLiteArchive(os.path.join(tempfile.mkdtemp(), "a.sqlite"))
    registry = CoreRegistry(store.connection)
    seed(registry)
    return store, registry


class TestTheMappingExists(unittest.TestCase):
    """1, 2, 11: present, EXACT, and fails if pointed elsewhere or softened."""

    def setUp(self) -> None:
        self.store, self.registry = seeded()

    def tearDown(self) -> None:
        self.store.close()

    def test_the_ifrs_concept_resolves_to_capex(self):
        mapped = {
            m.concept_id: m.metric_id
            for m in self.registry.metrics()
            for m in self.registry.mappings_for_metric(m.metric_id)
        }
        self.assertEqual(mapped.get(PROMOTED), "capex")

    def test_the_mapping_type_is_exact_not_partial(self):
        mappings = {m.concept_id: m for m in
                    self.registry.mappings_for_metric("capex")}
        self.assertIn(PROMOTED, mappings)
        self.assertEqual(mappings[PROMOTED].mapping_type, "EXACT")

    def test_it_would_fail_if_mapped_to_the_wrong_metric(self):
        """11: the guard has to be a real assertion, not a smoke test."""
        for every in self.registry.metrics():
            for mapping in self.registry.mappings_for_metric(
                    every.metric_id):
                if mapping.concept_id == PROMOTED:
                    self.assertEqual(
                        mapping.metric_id, "capex",
                        "the IFRS PPE acquisition concept is mapped away from "
                        "capex",
                    )

    def test_it_would_fail_if_downgraded_to_partial(self):
        mappings = {m.concept_id: m.mapping_type
                    for m in self.registry.mappings_for_metric("capex")}
        self.assertNotEqual(
            mappings[PROMOTED], "PARTIAL",
            "EXACT is what 2.36-2.38 established from the presentation; a "
            "downgrade would silently merge it with the intangibles-bearing "
            "concept",
        )


class TestNothingElseMoved(unittest.TestCase):
    """3, 4: the promotion is one mapping, and the Core set is the same size."""

    def setUp(self) -> None:
        self.store, self.registry = seeded()

    def tearDown(self) -> None:
        self.store.close()

    def test_the_us_gaap_mappings_are_unchanged(self):
        mappings = {m.concept_id: m
                    for m in self.registry.mappings_for_metric("capex")}
        self.assertEqual(mappings[US_GAAP_EXACT].mapping_type, "EXACT")
        self.assertEqual(mappings[US_GAAP_EXACT].effective_from, "2013-09-28")
        self.assertEqual(mappings[US_GAAP_PARTIAL].mapping_type, "PARTIAL")
        self.assertEqual(mappings[US_GAAP_PARTIAL].effective_from,
                         "2007-09-29")
        self.assertEqual(mappings[US_GAAP_PARTIAL].effective_to, "2014-09-27")

    def test_the_core_metric_count_is_unchanged(self):
        active = [m.metric_id for m in self.registry.metrics()
                   if m.status == "ACTIVE"]
        self.assertEqual(len(active), 20)

    def test_the_refuted_concept_is_not_mapped(self):
        """C was refuted in 2.36 and stays unmapped."""
        mapped = {m.concept_id for every in self.registry.metrics()
                  for m in self.registry.mappings_for_metric(every.metric_id)}
        self.assertNotIn(REFUTED_NOT_MAPPED, mapped)

    def test_the_underdecided_concept_is_not_mapped(self):
        """A was narrowed but never decided, and undecided means unmapped."""
        mapped = {m.concept_id for every in self.registry.metrics()
                  for m in self.registry.mappings_for_metric(every.metric_id)}
        self.assertNotIn(STILL_UNDECIDED, mapped)

    def test_long_term_debt_is_untouched(self):
        mapped = {m.concept_id for every in self.registry.metrics()
                  for m in self.registry.mappings_for_metric(every.metric_id)}
        self.assertEqual(
            mapped & {"us-gaap:LongTermDebtCurrent",
                      "us-gaap:LongTermDebtNoncurrent"},
            {"us-gaap:LongTermDebtCurrent",
             "us-gaap:LongTermDebtNoncurrent"},
        )
        self.assertEqual(self.registry.resolve_metric("debt"),
                         "long_term_debt")


class TestTheCaveatIsPreserved(unittest.TestCase):
    """12: verbatim, and not turned into an ingestion rule."""

    def setUp(self) -> None:
        self.store, self.registry = seeded()

    def tearDown(self) -> None:
        self.store.close()

    def test_the_caveat_is_in_the_mapping_metadata(self):
        notes = next(m.notes for m in
                     self.registry.mappings_for_metric("capex")
                     if m.concept_id == PROMOTED)
        self.assertIn(CAVEAT_FRAGMENT, notes)

    def test_the_structural_limitation_is_recorded_with_its_incidence(self):
        notes = next(m.notes for m in
                     self.registry.mappings_for_metric("capex")
                     if m.concept_id == PROMOTED)
        self.assertIn("STRUCTURAL", notes)
        self.assertIn("0 of 104", notes)

    def test_the_caveat_is_not_an_ingestion_filter(self):
        """
        The caveat must stay a caveat.

        It says a presentation is unexplained. It does not say the fact should be
        dropped, and nothing in the mapping may turn it into a filter.
        """
        rows = self.store.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        ).fetchall()
        triggers = [r[0] for r in rows]
        self.assertFalse([t for t in triggers if "ifrs" in t.lower()],
                         "an IFRS-specific ingestion trigger would be the "
                         "caveat turned into a filter")
        notes = next(m.notes for m in
                     self.registry.mappings_for_metric("capex")
                     if m.concept_id == PROMOTED)
        self.assertNotIn("skip", notes.lower().replace("skipped", ""))


class TestOneFilingOneObservation(unittest.TestCase):
    """
    6, 7, 8, 9, 10.

    The TSM case: the same concept, the same period, the same value, presented
    twice in one filing. The archive must store one observation.
    """

    ACCESSION = "0001193125-25-083423"

    class _Source:
        """
        One IFRS filer reporting the promoted concept, and nothing else.

        The first version of this fixture also answered for
        `us-gaap:PaymentsToAcquirePropertyPlantAndEquipment` with the same
        payload, which is not the TSM case -- it is *two different concepts*
        carrying one value, and the archive quite correctly stored two rows,
        because they are two facts about the world. Answering for both made a
        correct behaviour look like a duplication bug.
        """

        def __init__(self, duplicate_same_value: bool = True):
            self.documents_read = 0
            self.concept_fetches = 0
            self.network_fetches = 0
            self.duplicate_same_value = duplicate_same_value
            self._facts = [
                {"start": "2024-01-01", "end": "2024-12-31",
                 "val": 956006.5, "accn": "0001193125-25-083423",
                 "fy": 2024, "fp": "FY", "form": "20-F", "filed": "2025-03-18"},
            ]
            if duplicate_same_value:
                # The same fact a second time: what the asset-class breakdown
                # looks like once dimensions are dropped.
                self._facts.append(dict(self._facts[0]))

        def resolve_company(self, ticker):
            class Company:
                cik = "0001046179"
                name = "Taiwan Semiconductor"
                exchanges = ()
            return Company()

        def submissions(self, cik):
            return {"sic": "3693", "sicDescription": "Semiconductors"}

        def filing_index(self, cik):
            return [{
                "accession": "0001193125-25-083423", "form": "20-F",
                "filing_date": "2025-03-18", "report_date": "2024-12-31",
                "acceptance_datetime": "2025-03-18T21:02:44.000Z",
                "acceptance_precision": "INSTANT",
                "primary_document": "", "is_xbrl": 1,
            }]

        def concept_history(self, cik, taxonomy, concept):
            if f"{taxonomy}:{concept}" != PROMOTED:
                return None
            return {"label": "Acquisitions of property, plant and equipment",
                    "units": {"USD": [dict(f) for f in self._facts]}}

        def documents_for(self, taxonomy, concept):
            return ()

    def _ingest(self, duplicate: bool = True):
        store, registry = seeded()
        report = Ingestor(store, self._Source(duplicate), registry).ingest(
            "TSMF", metrics=("capex",), forms=("20-F",))
        return store, report

    def test_a_filing_reporting_the_concept_resolves_to_capex(self):
        store, report = self._ingest(duplicate=False)
        try:
            self.assertEqual(report.observations_stored, 1)
            row = store.connection.execute(
                "SELECT metric, concept, value_json FROM observations"
            ).fetchall()
            self.assertEqual(len(row), 1)
            self.assertEqual(row[0]["metric"], "capex")
            self.assertEqual(row[0]["concept"], PROMOTED)
        finally:
            store.close()

    def test_dual_presentation_of_one_fact_yields_one_observation(self):
        """
        The case 2.37 described, and the one that would have been easy to get
        wrong.

        The same fact twice with the same value is one fact, and ST-EVA's
        observation identity is the content hash -- so the second copy is the same
        row, not a new one.
        """
        store, report = self._ingest(duplicate=True)
        try:
            self.assertEqual(report.observations_stored, 1)
            count = store.connection.execute(
                "SELECT COUNT(*) FROM observations").fetchone()[0]
            self.assertEqual(count, 1)
            distinct = store.connection.execute(
                "SELECT COUNT(DISTINCT observation_id) FROM observations"
            ).fetchone()[0]
            self.assertEqual(distinct, 1)
        finally:
            store.close()

    def test_source_fact_identity_is_unchanged_by_the_promotion(self):
        store, _ = self._ingest(duplicate=False)
        try:
            distinct = store.connection.execute(
                "SELECT COUNT(DISTINCT source_fact_id) FROM observations"
            ).fetchone()[0]
            total = store.connection.execute(
                "SELECT COUNT(*) FROM observations").fetchone()[0]
            self.assertEqual(total, distinct)
        finally:
            store.close()

    def test_the_observations_table_is_still_append_only(self):
        store, _ = self._ingest(duplicate=False)
        try:
            triggers = {
                r[0] for r in store.connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger'")}
            self.assertIn("observations_no_update", triggers)
            self.assertIn("observations_no_delete", triggers)
            with self.assertRaises(Exception):
                store.connection.execute(
                    "UPDATE observations SET metric = 'revenue'")
            with self.assertRaises(Exception):
                store.connection.execute("DELETE FROM observations")
        finally:
            store.close()


class TestContractParity(unittest.TestCase):
    """
    The focused registry / contract / mapping parity check.

    `capex` is **not** one of the 2.3-B cross-source metrics, so there is no
    `data_contract` entry for it and the parity to hold is registry-internal:
    the metric's own definition, the concepts it declares, and the metadata on the
    mapping must agree with one another. That is asserted here rather than assumed,
    because 2.33 exists because two contracts shared an id and drifted.
    """

    def setUp(self) -> None:
        self.store, self.registry = seeded()

    def tearDown(self) -> None:
        self.store.close()

    def test_capex_is_not_in_the_cross_source_contract(self):
        """
        Worth pinning, because it is *why* there is no second contract to drift.

        `long_term_debt` is in `data_contract` and in the Core registry, which is
        how 2.33's divergence happened. `capex` is Core-only, so this class of
        divergence cannot arise for it.
        """
        self.assertNotIn("capex", data_contract.CONTRACT_METRICS)
        self.assertNotIn("capex", data_contract.METRIC_UNITS)
        self.assertNotIn("capex", data_contract.METRIC_DEFINITIONS)

    def test_every_concept_mapped_to_capex_is_declared(self):
        declared = {row[0] for row in self.store.connection.execute(
            "SELECT concept_id FROM concept_registry")}
        mapped = {m.concept_id for m in
                  self.registry.mappings_for_metric("capex")}
        self.assertTrue(mapped)
        self.assertEqual(mapped - declared, set(),
                         "a mapping whose concept is not declared cannot be "
                         "resolved and would fail the foreign key on seed")

    def test_every_concept_mapped_to_capex_exists_in_concepts_taxonomy(self):
        rows = dict(self.store.connection.execute(
            "SELECT concept_id, taxonomy FROM concept_registry"))
        for mapping in self.registry.mappings_for_metric("capex"):
            self.assertEqual(
                rows[mapping.concept_id].split(":")[0],
                mapping.concept_id.split(":")[0],
            )

    def test_the_promoted_concept_is_declared_with_a_source_definition(self):
        row = self.store.connection.execute(
            "SELECT source_definition FROM concept_registry WHERE concept_id = ?",
            (PROMOTED,)).fetchone()
        self.assertIsNotNone(row)
        self.assertIn("cash outflow", row[0].lower())
        self.assertIn("property, plant and equipment", row[0].lower())

    def test_the_metric_declares_the_same_unit_family_it_is_mapped_with(self):
        """A mapping whose unit family disagrees with its metric is a latent fault."""
        self.assertEqual(self.registry.metric("capex").unit_family, "currency")
        self.assertEqual(self.registry.metric("capex").statement, "CASH_FLOW")
        self.assertEqual(self.registry.metric("capex").normal_period_type,
                         "DURATION")

    def test_the_metric_still_declares_exactly_three_capex_concepts(self):
        mapped = sorted(m.concept_id for m in
                        self.registry.mappings_for_metric("capex"))
        self.assertEqual(mapped, sorted(
            [PROMOTED, US_GAAP_EXACT, US_GAAP_PARTIAL]))


if __name__ == "__main__":
    unittest.main()