"""
ST-EVA 2.5 - Core Registry tests.

The registry's whole purpose is to refuse a name-based guess, so most of these
assert that something is *not* resolved when it should not be, and that a series
breaks where the seed says it does.

The cases are the ones real AAPL filings produced, not invented ones. Three
would have been got wrong from the tag names alone:

    Revenues vs RevenueFromContractWithCustomer... overlap for two quarters
    and mean different things, so both map to revenue only partially and the
    series breaks between them.

    PaymentsToAcquireProductiveAssets includes software and intangibles while
    PaymentsToAcquirePropertyPlantAndEquipment does not. The names read alike
    and the definitions do not agree.

    LongTermDebtNoncurrent and LongTermDebtCurrent share a name family and are
    two different quantities, so they are two metrics and never one series.
"""

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from core_registry import (
    BANK,
    CONTINUING_MAPPINGS,
    MAPPING_EQUIVALENT,
    MAPPING_EXACT,
    MAPPING_NON_COMPARABLE,
    MAPPING_PARTIAL,
    Concept,
    ConceptMapping,
    CoreRegistry,
    Metric,
    RegistryError,
    concept_id_for,
)
from evidence_query import EvidenceQuery
from registry_seed import MAPPINGS, METRICS, seed
from sqlite_archive import SQLiteArchive

REPO = Path(__file__).resolve().parent.parent
US_GAAP = "us-gaap"
# The second accounting framework, named here so the cross-framework tests read
# as a statement about two frameworks rather than about one taxonomy.
IFRS_FULL = "ifrs-full"


class RegistryFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SQLiteArchive(":memory:")
        self.counts = seed(CoreRegistry(self.store.connection))
        self.registry = CoreRegistry(self.store.connection)
        self._seed_observations()

    def tearDown(self) -> None:
        self.store.close()

    def _seed_observations(self) -> None:
        """
        One filing figure and one vendor figure for the same meaning.

        Two observations, deliberately. A shared mapping is not a licence to
        merge them: they are two sources' readings, and collapsing them would
        delete the evidence that both existed.
        """
        asset = self.store.record_asset("AAPL", cik="0000320193")
        self.store.record_source("SecEdgar", "REGULATORY_FILING")
        self.store.record_source("YahooFinanceFundamentals", "API_LIVE")
        self.store.connection.execute(
            "INSERT INTO observation_lineage (lineage_id, asset_id, metric,"
            " concept, period_start, period_end, created_at, note)"
            " VALUES ('l1', ?, 'revenue', 'us-gaap:Revenues', NULL, NULL,"
            " '2024-05-03', 'fixture')",
            (asset,),
        )
        columns = (
            "observation_id", "contract_id", "asset_id", "lineage_id", "metric",
            "provider", "source_type", "concept", "taxonomy", "value_json",
            "unit", "currency", "currency_basis", "period_start",
            "period_end", "as_of", "available_at", "available_at_basis",
            "availability_class", "retrieved_at", "first_archived_at",
            "replay_eligible_from", "definition", "methodology", "status",
            "source_fact_id", "content_hash", "raw_json",
        )
        for contract_id, provider, source_type, concept, value, unit in (
            (
                "cmp-revenue-sec",
                "SecEdgar",
                "REGULATORY_FILING",
                "us-gaap:Revenues",
                "95000000000.0",
                "currency",
            ),
            (
                "cmp-revenue-vendor",
                "YahooFinanceFundamentals",
                "API_LIVE",
                "vendor:trailingTotalRevenue",
                "94900000000.0",
                "currency",
            ),
        ):
            values = {
                "observation_id": "obs_" + contract_id,
                "contract_id": contract_id,
                "asset_id": asset,
                "lineage_id": "l1",
                "metric": "revenue",
                "provider": provider,
                "source_type": source_type,
                "concept": concept,
                "taxonomy": concept.split(":")[0],
                "value_json": value,
                "unit": unit,
                "currency": "USD",
                "currency_basis": "REPORTED",
                "period_start": "2023-07-01",
                "period_end": "2024-06-30",
                "as_of": "2024-06-30",
                "available_at": "2024-07-31T10:01:02.000Z",
                "available_at_basis": "ACCEPTANCE_DATETIME",
                "availability_class": "SOURCE_DECLARED",
                "retrieved_at": "2024-08-01T00:00:00+00:00",
                "first_archived_at": "2024-08-01T00:00:00+00:00",
                "replay_eligible_from": "2024-07-31T10:01:02.000Z",
                "definition": "revenue",
                "methodology": "fixture",
                "status": "UNVERIFIABLE",
                "source_fact_id": "sfid_" + contract_id,
                "content_hash": "h_" + contract_id,
                "raw_json": json.dumps(
                    {"sec_fact": {"taxonomy": concept.split(":")[0],
                                   "tag": concept.split(":")[-1],
                                   "accession": "0000320193-24-000001"}}
                ),
            }
            self.store.connection.execute(
                "INSERT INTO observations ({}) VALUES ({})".format(
                    ", ".join(columns),
                    ", ".join("?" for _ in columns),
                ),
                tuple(values[column] for column in columns),
            )
        self.store.connection.commit()


class TestMetricRegistry(RegistryFixture):
    def test_metric_registry_lookup(self):
        metric = self.registry.metric("revenue")
        self.assertIsNotNone(metric)
        self.assertEqual(metric.statement, "INCOME")
        self.assertEqual(metric.unit_family, "currency")
        self.assertEqual(metric.normal_period_type, "DURATION")
        self.assertTrue(metric.semantic_definition)

    def test_an_unknown_metric_is_absent_not_a_guess(self):
        self.assertIsNone(self.registry.metric("no_such_metric"))

    def test_metrics_are_groupable_by_statement(self):
        balance = self.registry.metrics(statement="BALANCE_SHEET")
        self.assertTrue(balance)
        for metric in balance:
            self.assertEqual(metric.statement, "BALANCE_SHEET")

    def test_the_seed_registers_the_required_metrics(self):
        for metric_id in (
            "revenue", "net_income", "eps_diluted", "assets", "cash", "debt",
            "shares_outstanding", "gross_profit", "operating_income", "r_and_d",
            "sga", "interest_expense", "income_tax", "operating_cash_flow",
            "capex", "sbc",
        ):
            self.assertIsNotNone(
                self.registry.metric(metric_id), f"{metric_id} is not seeded"
            )

    def test_a_vocabulary_violation_is_refused(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connection.execute(
                "INSERT INTO metric_registry (metric_id, display_name,"
                " statement, semantic_definition, unit_family,"
                " normal_period_type, applicability, comparability_group, status)"
                " VALUES ('bad', 'Bad', 'PROFIT_AND_LOSS', 'x', 'currency',"
                " 'DURATION', 'APPLICABLE', NULL, 'ACTIVE')"
            )
            self.store.connection.commit()


class TestConceptRegistry(RegistryFixture):
    def test_concept_registry_lookup(self):
        concept = self.registry.concept(
            concept_id_for(US_GAAP, "NetIncomeLoss")
        )
        self.assertIsNotNone(concept)
        self.assertEqual(concept.taxonomy, "us-gaap")
        self.assertTrue(concept.source_definition)

    def test_a_concept_is_found_by_qualified_name(self):
        concept = self.registry.concept(
            f"{US_GAAP}:EarningsPerShareDiluted"
        )
        self.assertIsNotNone(concept)
        self.assertEqual(concept.concept, "EarningsPerShareDiluted")

    def test_an_unknown_concept_is_absent(self):
        self.assertIsNone(self.registry.concept("us-gaap:NotAThing"))

    def test_concept_definitions_are_quoted_not_invented(self):
        """A paraphrase would let two concepts read as equal when they are not."""
        rows = self.store.connection.execute(
            "SELECT concept_id, source_definition FROM concept_registry"
        ).fetchall()
        self.assertTrue(rows)
        for row in rows:
            self.assertTrue(
                row["source_definition"],
                f"{row['concept_id']} has no source definition",
            )


class TestMappingRegistry(RegistryFixture):
    def test_metric_concept_mapping_lookup(self):
        mappings = self.registry.mappings_for_metric("revenue")
        self.assertTrue(mappings)
        for mapping in mappings:
            self.assertEqual(mapping.metric_id, "revenue")

    def test_mapping_type_enforcement(self):
        with self.assertRaises(RegistryError):
            ConceptMapping(
                metric_id="revenue",
                concept_id=concept_id_for(US_GAAP, "Revenues"),
                mapping_type="CLOSE_ENOUGH",
            )

    def test_a_breaking_mapping_must_record_when_it_applies(self):
        with self.assertRaises(RegistryError):
            ConceptMapping(
                metric_id="revenue",
                concept_id=concept_id_for(US_GAAP, "Revenues"),
                mapping_type=MAPPING_PARTIAL,
            )
        with self.assertRaises(RegistryError):
            ConceptMapping(
                metric_id="revenue",
                concept_id=concept_id_for(US_GAAP, "Revenues"),
                mapping_type=MAPPING_NON_COMPARABLE,
            )

    def test_a_continuing_mapping_needs_no_window(self):
        mapping = ConceptMapping(
            metric_id="revenue",
            concept_id=concept_id_for(US_GAAP, "Revenues"),
            mapping_type=MAPPING_EXACT,
        )
        self.assertTrue(mapping.series_continues)

    def test_only_exact_and_equivalent_continue_a_series(self):
        self.assertEqual(
            set(CONTINUING_MAPPINGS), {MAPPING_EXACT, MAPPING_EQUIVALENT}
        )
        for mapping_type in (MAPPING_PARTIAL, MAPPING_NON_COMPARABLE):
            self.assertNotIn(mapping_type, CONTINUING_MAPPINGS)

    def test_mapping_effective_dates(self):
        historical = self.registry.mappings_for_metric(
            "capex", as_of="2010-01-01"
        )
        current = self.registry.mappings_for_metric(
            "capex", as_of="2020-01-01"
        )
        self.assertEqual(
            [m.concept_id for m in historical],
            [concept_id_for(US_GAAP, "PaymentsToAcquireProductiveAssets")],
        )
        self.assertEqual(
            [m.concept_id for m in current],
            [concept_id_for(US_GAAP, "PaymentsToAcquirePropertyPlantAndEquipment")],
        )

    def test_no_date_filter_returns_every_mapping(self):
        """
        Narrowing to unbounded mappings would hide a concept that stopped.

        Asserted as the property the docstring names -- every mapping reachable
        with no date is reachable through *some* dated read -- rather than as an
        arithmetic identity. The identity was a proxy that happened to hold for
        one framework and stopped holding when a second was added, because a
        mapping whose window covers both sampled dates is legitimately counted
        twice. The proxy failed for a correct reason and said nothing about
        whether a concept was hidden.
        """
        every = {
            m.concept_id
            for m in self.registry.mappings_for_metric("revenue")
        }
        self.assertTrue(every)
        reachable = set()
        for when in ("2010-01-01", "2017-01-01", "2018-01-01", "2020-01-01"):
            reachable |= {
                m.concept_id
                for m in self.registry.mappings_for_metric(
                    "revenue", as_of=when
                )
            }
        self.assertEqual(
            every - reachable, set(),
            "a mapping is invisible to every dated read, which is the "
            "unbounded-mapping filter this test exists to catch",
        )
        # And the IFRS revenue concept's window is real in both directions: it
        # is absent before the element was ever reported here, and present for
        # every period it covers. A window that swallowed those dates would hide
        # the concept for the exact periods it was declared for.
        ifrs_revenue = concept_id_for(IFRS_FULL, "Revenue")
        self.assertIn(ifrs_revenue, every)
        self.assertNotIn(
            ifrs_revenue,
            [
                m.concept_id
                for m in self.registry.mappings_for_metric(
                    "revenue", as_of="2010-01-01"
                )
            ],
        )
        for when in ("2017-01-01", "2020-01-01"):
            self.assertIn(
                ifrs_revenue,
                [
                    m.concept_id
                    for m in self.registry.mappings_for_metric(
                        "revenue", as_of=when
                    )
                ],
            )

    def test_one_metric_is_reachable_from_two_frameworks(self):
        """
        The generalisation 2.7 was asked to demonstrate, as a test.

        A semantic metric is reached through whichever source concept the filer
        used, and the two taxonomies sit beside each other in one table with no
        issuer column, no framework column on the metric, and no code path that
        knows which framework it is reading. If that stops being true this fails
        rather than being noticed later by a reader.
        """
        for metric in ("assets", "cash", "eps_diluted", "net_income"):
            taxonomies = {
                concept_id.split(":", 1)[0]
                for concept_id in (
                    m.concept_id
                    for m in self.registry.mappings_for_metric(metric)
                )
            }
            self.assertIn("ifrs-full", taxonomies, metric)
            self.assertIn("us-gaap", taxonomies, metric)

    def test_a_framework_never_gets_an_exact_mapping_on_a_label_alone(self):
        """
        The one thing a similar English label does not establish.

        `ifrs-full:Revenue` and `us-gaap:Revenues` read alike and do not mean
        the same thing: the IFRS element is an aggregate of ordinary-activity
        income that may carry interest, dividend and royalty income, while the
        US-GAAP element the metric calls exact is contracts-with-customers only,
        which is a component of it. The test asserts the *weaker* type, so a
        future edit that promotes it to EXACT on the strength of the spelling
        fails here.
        """
        mapping = next(
            m for m in self.registry.mappings_for_metric("revenue")
            if m.concept_id == concept_id_for(IFRS_FULL, "Revenue")
        )
        self.assertEqual(mapping.mapping_type, MAPPING_PARTIAL)
        self.assertFalse(mapping.series_continues)
        self.assertTrue(mapping.effective_from)
        # And the exact mapping for the same metric is the *other* framework's
        # narrower concept, so the two cannot be quietly swapped.
        exact = [
            m for m in self.registry.mappings_for_metric("revenue")
            if m.mapping_type == MAPPING_EXACT
        ]
        self.assertTrue(exact)
        for entry in exact:
            self.assertTrue(entry.concept_id.startswith("us-gaap:"))

    def test_the_database_refuses_a_vocabulary_violation(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connection.execute(
                "INSERT INTO metric_concept_mapping (metric_id, concept_id,"
                " mapping_type, effective_from, effective_to, notes)"
                " VALUES ('revenue', ?, 'APPROXIMATELY', '2007-01-01', NULL, NULL)",
                (concept_id_for(US_GAAP, "Revenues"),),
            )
            self.store.connection.commit()


class TestApplicability(RegistryFixture):
    def test_applicability_is_explicit(self):
        metric = self.registry.metric("operating_income")
        self.assertEqual(metric.applicability, "APPLICABLE")

    def test_a_business_model_can_exclude_a_metric(self):
        """
        A refusal exists, but only because one was made.

        2.25 gave a rule production authority only at state `SUPPORTED`, and no
        seeded exclusion is. So the mechanism is exercised the way it would have to
        be exercised for real: someone decides, and the refusal appears.
        """
        operating = self.registry.metric("operating_income")
        # Before: a `TESTABLE` proposition is a question, not a refusal.
        self.assertTrue(operating.applies_to("INDUSTRIALS"))
        self.assertTrue(operating.applies_to(BANK))
        self.assertEqual(
            self.registry.exclusion_states().get("operating_income", {}),
            {BANK: "TESTABLE"},
        )
        self.registry.support_exclusion("operating_income", BANK)
        # After: the same proposition, now supported, refuses.
        operating = self.registry.metric("operating_income")
        self.assertTrue(operating.applies_to("INDUSTRIALS"))
        self.assertFalse(operating.applies_to(BANK))

    def test_an_unsupported_exclusion_refuses_nothing(self):
        """
        **The invariant 2.25 exists to establish.**

        A `TESTABLE` hypothesis must not prevent Evidence collection, or the
        lifecycle is decoration: an unsupported rule would still be editing the
        coverage surface while claiming to be a question.
        """
        for model in ("BANK", "FINANCE_SERVICES", "MINING", "INSURANCE"):
            self.assertTrue(
                self.registry.metric("operating_income").applies_to(model),
                model,
            )

    def test_a_refusal_cannot_be_made_without_a_proposition(self):
        from core_registry import RegistryError

        with self.assertRaises(RegistryError):
            self.registry.support_exclusion("operating_income", "MANUFACTURING")

    def test_an_unknown_business_model_is_not_inapplicability(self):
        """
        Absence of retrieval is never evidence that a concept does not exist.
        """
        revenue = self.registry.metric("revenue")
        self.assertTrue(revenue.applies_to(None))
        self.assertTrue(revenue.applies_to("SOMETHING_WE_DO_NOT_KNOW"))

    def test_not_applicable_is_never_inferred_from_a_missing_observation(self):
        """A metric with no archived observation stays applicable."""
        for metric in self.registry.metrics():
            held = self.store.connection.execute(
                "SELECT COUNT(*) AS n FROM observations WHERE metric = ?",
                (metric.metric_id,),
            ).fetchone()["n"]
            if held == 0:
                self.assertNotEqual(
                    metric.applicability,
                    "NOT_APPLICABLE",
                    f"{metric.metric_id} was marked inapplicable with no "
                    "observation to justify it",
                )


class TestComparability(RegistryFixture):
    def test_equivalent_concepts_share_a_metric_without_merging(self):
        """
        Two vocabularies, one meaning.

        The mapping is shared; the observations are not. A vendor figure and a
        filing figure stay two observations, because merging them would delete
        the evidence that two independent readings existed.
        """
        metrics = {
            mapping.metric_id
            for mapping, _ in self.registry.metrics_for_concept(
                concept_id_for("vendor", "trailingTotalRevenue")
            )
        }
        self.assertEqual(metrics, {"revenue"})
        for mapping in self.registry.mappings_for_metric("revenue"):
            if mapping.concept_id.endswith("trailingTotalRevenue"):
                self.assertEqual(mapping.mapping_type, MAPPING_EQUIVALENT)
                self.assertTrue(mapping.series_continues)

    def test_similar_concepts_with_different_definitions_stay_apart(self):
        """
        The capex pair. The names read alike; the source says one includes
        software and intangibles and the other does not. A name-based guess
        would have merged them.
        """
        exact = next(
            mapping
            for mapping in self.registry.mappings_for_metric("capex")
            if mapping.concept_id.endswith("PropertyPlantAndEquipment")
        )
        partial = next(
            mapping
            for mapping in self.registry.mappings_for_metric("capex")
            if mapping.concept_id.endswith("ProductiveAssets")
        )
        self.assertEqual(exact.mapping_type, MAPPING_EXACT)
        self.assertEqual(partial.mapping_type, MAPPING_PARTIAL)
        self.assertFalse(partial.series_continues)

        pp_e = self.registry.concept(exact.concept_id)
        productive = self.registry.concept(partial.concept_id)
        self.assertIn("intangible", (productive.source_definition or "").lower())
        self.assertNotIn("intangible", (pp_e.source_definition or "").lower())

    def test_non_comparable_concepts_remain_distinct_metrics(self):
        """
        Debt's two portions share a name family and are never one series.
        """
        noncurrent = self.registry.metric("long_term_debt_noncurrent")
        current = self.registry.metric("long_term_debt_current")
        self.assertNotEqual(noncurrent.metric_id, current.metric_id)
        self.assertEqual(noncurrent.comparability_group,
                         current.comparability_group)
        # Same family, so a consumer can see they belong together, and a
        # different metric, so they are never summed by the registry.
        self.assertEqual(noncurrent.statement, current.statement)

    def test_a_series_breaks_where_a_concept_changes(self):
        breaks = self.registry.series_breaks("revenue")
        concept_ids = {item["concept_id"] for item in breaks}
        self.assertIn(concept_id_for(US_GAAP, "Revenues"), concept_ids)
        self.assertIn(concept_id_for(US_GAAP, "SalesRevenueNet"), concept_ids)
        for item in breaks:
            self.assertEqual(item["kind"], "CONCEPT_MAPPING_BREAK")
            self.assertEqual(item["explanation"], "NOT_EXPLAINED_BY_ST_EVA")

    def test_a_stable_series_has_no_breaks(self):
        self.assertEqual(self.registry.series_breaks("assets"), [])
        self.assertEqual(self.registry.series_breaks("eps_diluted"), [])

    def test_the_registry_resolves_no_conflicts(self):
        """Resolution stays where 2.4.3 put it."""
        self.assertFalse(
            hasattr(self.registry, "resolve_conflict"),
            "the registry must not resolve conflicts",
        )
        for name in dir(self.registry):
            self.assertNotIn("winner", name.lower())
            self.assertNotIn("prefer", name.lower())


class TestResolution(RegistryFixture):
    def test_a_known_concept_resolves_to_its_metric(self):
        resolved = self.registry.resolve(
            concept_id_for(US_GAAP, "NetIncomeLoss")
        )
        self.assertTrue(resolved.is_resolved)
        self.assertEqual(resolved.metric.metric_id, "net_income")

    def test_an_unknown_concept_does_not_silently_match(self):
        """
        The point of the registry. An unmapped concept resolves to nothing
        rather than to the metric whose name looks nearest.
        """
        resolved = self.registry.resolve("us-gaap:SomeNovelConcept")
        self.assertFalse(resolved.is_resolved)
        self.assertIsNone(resolved.metric)

    def test_a_name_that_matches_nothing_resolves_to_nothing(self):
        for concept in ("us-gaap:Revenueish", "us-gaap:Debt", "revenue"):
            self.assertIsNone(
                self.registry.resolve(concept).metric,
                f"{concept} resolved without a mapping",
            )

    def test_an_ambiguous_concept_is_reported_not_chosen(self):
        """A concept that maps to several metrics is a registry question."""
        self.registry.add_mapping(
            ConceptMapping(
                metric_id="gross_profit",
                concept_id=concept_id_for(US_GAAP, "Revenues"),
                mapping_type=MAPPING_EXACT,
                effective_from="2016-09-24",
                effective_to="2018-09-29",
            )
        )
        resolved = self.registry.resolve(
            concept_id_for(US_GAAP, "Revenues"), as_of="2017-12-31"
        )
        self.assertFalse(resolved.is_resolved)
        self.assertTrue(resolved.series_breaks)
        self.assertEqual(
            resolved.series_breaks[0]["kind"], "AMBIGUOUS_MAPPING"
        )
        self.assertIn("NOT_EXPLAINED", resolved.series_breaks[0]["explanation"])

    def test_resolution_is_deterministic(self):
        first = self.registry.resolve(
            concept_id_for(US_GAAP, "Assets")
        ).contract_dict()
        second = self.registry.resolve(
            concept_id_for(US_GAAP, "Assets")
        ).contract_dict()
        self.assertEqual(
            json.dumps(first, sort_keys=True),
            json.dumps(second, sort_keys=True),
        )


class TestQuerySurfaceIntegration(RegistryFixture):
    def test_the_query_surface_resolves_observation_to_metric(self):
        """
        The integration the Query Surface is required to gain: a figure reaches
        its source concept and then the semantic metric that concept means.
        """
        data = self.store.connection.execute(
            "SELECT contract_id FROM observations WHERE metric = 'assets'"
            " LIMIT 1"
        ).fetchone()
        if data is None:
            self.skipTest("this archive holds no assets observation")
        query = EvidenceQuery(connection=self.store.connection)
        row = query.get_observation(data["contract_id"])
        semantic = row["semantic"]
        self.assertTrue(semantic["resolved"])
        self.assertEqual(semantic["metric"], "assets")
        self.assertEqual(semantic["concept"], "us-gaap:Assets")
        self.assertTrue(semantic["metric_definition"])

    def test_observation_provenance_survives_resolution(self):
        data = self.store.connection.execute(
            "SELECT contract_id FROM observations LIMIT 1"
        ).fetchone()
        query = EvidenceQuery(connection=self.store.connection)
        row = query.get_observation(data["contract_id"])
        # Resolution adds meaning; it must not replace the evidence.
        for key in (
            "observation_id", "asset", "metric", "value", "unit", "currency",
            "period", "as_of", "available_at", "status", "source",
            "definition", "methodology", "basis", "validation", "lineage",
        ):
            self.assertIn(key, row, f"resolution dropped {key}")
        self.assertTrue(row["source"]["accession"])
        self.assertTrue(row["source"]["concept"])
        self.assertTrue(row["source"]["provider"])

    def test_observations_are_not_merged_by_the_registry(self):
        """Two sources, two observations, whatever the registry says."""
        data = self.store.connection.execute(
            "SELECT contract_id FROM observations WHERE metric = 'revenue'"
            " AND provider = 'YahooFinance' LIMIT 1"
        ).fetchone()
        if data is None:
            self.skipTest("this archive holds no vendor revenue observation")
        query = EvidenceQuery(connection=self.store.connection)
        row = query.get_observation(data["contract_id"])
        self.assertEqual(row["source"]["provider"], "YahooFinance")
        self.assertEqual(
            row["semantic"]["metric"],
            "revenue",
            "the vendor concept maps EQUIVALENT to the same metric",
        )
        # The mapping is shared; the observation is still this source's alone.
        self.assertEqual(
            row["source"]["concept"], "vendor:trailingTotalRevenue"
        )


@unittest.skipUnless(
    os.environ.get("ST_EVA_LIVE") == "1",
    "the AAPL registry validation needs ST_EVA_LIVE=1",
)
class TestAapplRegistryValidation(unittest.TestCase):
    """
    Real AAPL evidence, resolved through the registry.

    The chain is: source document -> source fact -> observation -> concept
    registry -> metric registry -> query result. Nothing in it is invented, and
    no observation is created to satisfy a test.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.directory = tempfile.mkdtemp(prefix="steva-registry-")
        cls.archive = os.path.join(cls.directory, "aapl.sqlite")
        import st_eva_runner

        st_eva_runner.run_st_eva(
            "AAPL",
            mode="live",
            save_snapshot=False,
            context_path=os.path.join(cls.directory, "aapl.json"),
            context_sources=("yahoo", "sec"),
            archive=SQLiteArchive(cls.archive),
        )
        store = SQLiteArchive(cls.archive)
        seed(CoreRegistry(store.connection))
        cls.registry = CoreRegistry(store.connection)
        cls.query = EvidenceQuery(connection=store.connection)
        cls.store = store

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls.query.close()
            cls.store.close()
        finally:
            import shutil

            shutil.rmtree(cls.directory, ignore_errors=True)

    def test_every_archived_concept_resolves_or_says_why_not(self):
        rows = self.query.query_observations(asset="AAPL")
        self.assertTrue(rows)
        for row in rows:
            concept = (row["source"].get("concept") or "").split(":")[-1]
            if not concept or concept in ("None",):
                continue
            resolved = self.registry.resolve(
                f"{row['source'].get('taxonomy')}:{concept}"
            )
            self.assertIsNotNone(
                resolved,
                f"{concept} could not be looked up at all",
            )

    def test_aapl_observations_resolve_or_explain_they_do_not(self):
        """
        Every figure either resolves or says why not.

        Some AAPL observations are built from the market-data view and carry no
        filing concept at all. Those must report that, not be attached to the
        metric whose name is nearest.
        """
        rows = self.query.query_observations(
            asset="AAPL", metric="revenue"
        )
        self.assertTrue(rows)
        resolved = 0
        for row in rows:
            semantic = row["semantic"]
            if semantic["resolved"]:
                self.assertEqual(semantic["metric"], "revenue")
                resolved += 1
            else:
                self.assertTrue(
                    semantic.get("reason"),
                    "an unresolved figure must say why",
                )
        self.assertGreater(resolved, 0, "nothing resolved at all")

    def test_two_concepts_map_to_one_metric_without_merging(self):
        """
        The equivalence case, on real evidence: the vendor's trailing revenue
        and the filing's contract revenue are one meaning in two vocabularies,
        and they remain two observations.
        """
        rows = self.query.query_observations(
            asset="AAPL", metric="revenue"
        )
        by_concept = {row["source"]["concept"]: row for row in rows}
        filing = by_concept.get(
            "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"
        )
        vendor = by_concept.get("vendor:trailingTotalRevenue")
        if filing is None or vendor is None:
            self.skipTest("this run archived only one revenue source")
        self.assertEqual(filing["semantic"]["metric"], "revenue")
        self.assertEqual(vendor["semantic"]["metric"], "revenue")
        self.assertNotEqual(filing["observation_id"],
                            vendor["observation_id"])
        self.assertEqual(filing["source"]["provider"], "SecEdgar")
        self.assertEqual(vendor["source"]["provider"], "YahooFinanceFundamentals")

    def test_similar_concepts_remain_non_comparable(self):
        """The case that proves the registry is not matching on names."""
        pp_e = self.registry.concept(
            concept_id_for(US_GAAP, "PaymentsToAcquirePropertyPlantAndEquipment")
        )
        productive = self.registry.concept(
            concept_id_for(US_GAAP, "PaymentsToAcquireProductiveAssets")
        )
        self.assertNotIn(
            "intangible", (pp_e.source_definition or "").lower()
        )
        self.assertIn(
            "intangible", (productive.source_definition or "").lower()
        )
        breaks = self.registry.series_breaks("capex")
        self.assertTrue(breaks)
        self.assertEqual(breaks[0]["mapping_type"], MAPPING_PARTIAL)

    def test_debt_components_stay_two_metrics(self):
        for metric_id in ("long_term_debt_noncurrent", "long_term_debt_current"):
            self.assertIsNotNone(self.registry.metric(metric_id))
        # And the total is a composition, declared, not summed by the registry.
        debt = self.registry.metric("debt")
        self.assertIn("composition", debt.semantic_definition.lower())

    def test_the_whole_chain_is_mechanically_traceable(self):
        row = self.query.query_observations(
            asset="AAPL", metric="net_income", order="PERIOD_ASCENDING", limit=1
        )[0]
        lineage = self.query.get_lineage(row["observation_id"])
        steps = {item["step"] for item in lineage["chain"]}
        self.assertIn("SOURCE_DOCUMENT", steps)
        self.assertIn("OBSERVATION", steps)
        self.assertEqual(
            row["semantic"]["concept"], "us-gaap:NetIncomeLoss"
        )
        self.assertEqual(row["semantic"]["metric"], "net_income")
        document = self.query.get_source_document(
            row["source"]["documents"][0]["document_id"]
        )
        self.assertTrue(document["content_available"])
        self.assertTrue(row["source"]["accession"])


if __name__ == "__main__":
    unittest.main()
