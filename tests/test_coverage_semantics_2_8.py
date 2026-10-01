"""
2.8: coverage semantics — what a coverage figure cannot say on its own.

"How much" is answered by a count. "Why" is not, and without the why the number
cannot be acted on: "3.0% of this filer's concepts" and "3.0% of the concepts
ST-EVA promised" are different sentences with the same number in them.

The tests here pin the distinctions rather than the implementation, and the
distinction that matters most is the one the phase was written to make:
`NOT_YET_COLLECTED` is not `DELIBERATELY_DECLINED`, and neither is `UNMAPPED`.
All three read as "no observations" in a flat list, and all three call for
completely different work.
"""

import contextlib
import sqlite3
import sys
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core_registry import (  # noqa: E402
    REASON_COMPONENT_OF,
    REASON_NOT_A_METRIC,
    CoreRegistry,
    DeclinedConcept,
    RegistryError,
    concept_id_for,
)
from coverage_semantics import (  # noqa: E402
    BACKLOG_STATUS,
    COLLECTED,
    DELIBERATELY_DECLINED,
    MAPPED_NO_CURRENT_OBSERVATION,
    NOT_APPLICABLE_STATUS,
    NOT_YET_COLLECTED,
    SCOPED,
    SOURCE_SILENT,
    UNDETERMINED,
    UNMAPPED,
    scoped_ledger,
)
from evidence_query import EvidenceQuery  # noqa: E402
from registry_seed import seed  # noqa: E402
from sqlite_archive import SQLiteArchive  # noqa: E402

IFRS_FULL = "ifrs-full"
AAPL = "AAPL"


def _now():
    return datetime.now(timezone.utc).isoformat()


class LedgerFixture(unittest.TestCase):
    def setUp(self):
        self.store = SQLiteArchive(":memory:")
        self.registry = CoreRegistry(self.store.connection)
        seed(self.registry)
        self.connection = self.store.connection
        self.asset_id = self.store.record_asset(AAPL, cik="1", name="X")
        self.query = EvidenceQuery(connection=self.store.connection)

    def tearDown(self):
        self.store.close()

    @contextlib.contextmanager
    def writable(self):
        self.connection.execute("PRAGMA query_only = OFF")
        try:
            yield
        finally:
            self.connection.execute("PRAGMA query_only = ON")

    def support_operating_income_for_banks(self):
        """
        Make the one refusal these tests need, explicitly.

        2.25 gave a rule production authority only at `SUPPORTED`, and no seeded
        exclusion is -- so a refusal here is a decision somebody made, which is
        the whole point of the change. `operating_income x BANK` is the standing
        `TESTABLE` proposition; promoting it here is what a real support decision
        would look like.
        """
        with self.writable():
            self.registry.support_exclusion("operating_income", "BANK")

    def classify(self, model="BANK"):
        """
        `BANK`, because that is the class these tests promote a refusal for.

        2.23 refuted `gross_profit` for `BANK` and 2.25 refuted both remaining
        exclusions for `FINANCE_SERVICES`, so `operating_income` under this label
        is what still exercises a refusal. The statuses under test are unchanged.
        """
        self.support_operating_income_for_banks()
        with self.writable():
            self.registry.set_issuer_business_model(
                self.asset_id, model, basis="DECLARED_BY_ISSUER",
                source="SIC 6199 Finance Services",
            )

    def add_observation(self, metric="revenue"):
        observation_id = "obs_" + uuid.uuid4().hex
        with self.writable():
            self.connection.execute(
                "INSERT OR IGNORE INTO observation_lineage (lineage_id,"
                " asset_id, metric, concept, period_start, period_end,"
                " created_at, note) VALUES ('l1', ?, ?, 'us-gaap:Revenues',"
                " '2023-01-01', '2023-12-31', ?, 'test')",
                (self.asset_id, metric, _now()),
            )
            self.connection.execute(
                "INSERT INTO observations (observation_id, contract_id,"
                " asset_id, lineage_id, metric, provider, source_type,"
                " source_url, concept, value_json, unit, currency,"
                " currency_basis, period_start, period_end, as_of, available_at,"
                " available_at_basis, availability_class, retrieved_at,"
                " first_archived_at, replay_eligible_from, definition,"
                " methodology, status, status_reasons_json, inputs_json,"
                " observation_count, raw_json, content_hash, basis_json, taxonomy,"
                " accession, form, fiscal_year, fiscal_period, statement,"
                " instant, source_fact_id, source_concept_ref)"
                " VALUES (?, 'c1', ?, 'l1', ?, 'SecEdgar', 'REGULATORY_FILING',"
                " NULL, 'us-gaap:Revenues', '1.0', 'currency', 'USD', 'REPORTED',"
                " '2023-01-01', '2023-12-31', '2023-12-31', '2024-02-01',"
                " 'ACCEPTANCE_DATETIME', 'FILING_ACCEPTED', '2024-02-01',"
                " '2024-02-02', '2024-02-01', 'd', 'm', 'UNVERIFIABLE', '[]',"
                " '[]', NULL, '{}', 'h2', '{}', 'us-gaap',"
                " '0000320193-24-000001', '10-K', 2023, 'FY', 'INCOME', 0,"
                " 'sfid_x', NULL)",
                (observation_id, self.asset_id, metric),
            )
            self.connection.commit()
        return observation_id

    def add_adoption(self, concept_id):
        with self.writable():
            self.connection.execute(
                "INSERT OR REPLACE INTO issuer_concept_adoption (asset_id,"
                " concept_id, first_used, last_used, fact_count, filing_count,"
                " basis) VALUES (?, ?, '2020-01-01', '2024-01-01', 4, 2,"
                " 'OBSERVED_ADOPTION')",
                (self.asset_id, concept_id),
            )

    def add_scope_run(self, metric, status):
        with self.writable():
            run_id = "run_" + uuid.uuid4().hex[:12]
            self.connection.execute(
                "INSERT INTO ingestion_runs (run_id, asset_id, source_id,"
                " started_at, finished_at, filings_seen, filings_already_held,"
                " filings_ingested, documents_stored, documents_reused,"
                " source_facts_stored, source_facts_skipped, observations_stored,"
                " observations_skipped, network_fetches, concepts_unresolved,"
                " status, error) VALUES (?, ?, 'SecEdgar', ?, ?, 0, 0, 0, 0, 0,"
                " 0, 0, 0, 0, 0, 0, 'OK', NULL)",
                (run_id, self.asset_id, _now(), _now()),
            )
            self.connection.execute(
                "INSERT INTO ingestion_scope (run_id, asset_id, metric_id,"
                " mapping_count, attempted, observations_stored, status)"
                " VALUES (?, ?, ?, 1, 1, 0, ?)",
                (run_id, self.asset_id, metric, status),
            )
            self.connection.commit()

    def decline(self, concept_id, metric, reason_code=REASON_COMPONENT_OF):
        with self.writable():
            self.registry.decline_concept_mapping(
                concept_id, metric, reason_code,
                "considered and rejected, with the reason stated",
                framework_basis=IFRS_FULL,
            )

    def ledger(self, inventory=None):
        return scoped_ledger(
            self.connection, self.registry, self.asset_id, AAPL,
            source_inventory=inventory,
        )

    def status_of(self, ledger, metric):
        return next(
            r["status"] for r in ledger["rows"] if r["metric"] == metric
        )


class TestTheUniverseIsScoped(LedgerFixture):
    """
    Coverage is measured against what ST-EVA promised, not against the source.

    The refusal is the design. A headline "3.0% of this filer's 334 concepts"
    invites someone to raise it, and the cheapest way to raise it is to collect
    concepts nobody asked for -- the exact opposite of the product's premise.
    """

    def test_the_universe_is_named(self):
        self.assertEqual(self.ledger()["universe"], SCOPED)

    def test_every_active_metric_gets_a_row(self):
        ledger = self.ledger()
        self.assertEqual(
            len(ledger["rows"]), ledger["metrics_total"]
        )
        self.assertIn("revenue", [r["metric"] for r in ledger["rows"]])

    def test_the_source_count_is_reported_but_is_not_the_denominator(self):
        """
        The source figure is available and is not the score.

        Losing it would lose a real number -- what the filer actually reports --
        so it is reported. Denominating on it would make the score reward
        collecting the wrong things.
        """
        ledger = self.ledger(inventory=["us-gaap:A", "us-gaap:B"])
        self.assertTrue(ledger["source_inventory_known"])
        self.assertEqual(ledger["source_inventory_size"], 2)
        self.assertEqual(ledger["universe"], SCOPED)
        self.assertIn("Not the filer's full concept count",
                      ledger["universe_note"])

    def test_an_absent_inventory_is_declared_absent_not_guessed(self):
        """
        2.7 established that a registry-driven archive cannot see a concept it
        never asked for. A ledger that assumed it could would report the same
        confident zero the ingest loop already reports.
        """
        ledger = self.ledger()
        self.assertFalse(ledger["source_inventory_known"])
        self.assertIsNone(ledger["source_inventory_size"])


class TestTheStatusesAreDistinct(LedgerFixture):
    """
    The phase's whole content: five ways of holding nothing, kept apart.
    """

    def test_collected(self):
        self.add_observation("revenue")
        self.assertEqual(
            self.status_of(self.ledger(), "revenue"), COLLECTED
        )

    def test_mapped_no_current_observation(self):
        """
        The concept was observed being reported, and nothing is held now.

        Distinct from "never asked" because the evidence is different in kind: we
        know this filer used the concept, so the absence is about the mapping
        window or deduplication rather than about the backlog.
        """
        self.add_adoption(concept_id_for("us-gaap", "Assets"))
        self.add_scope_run("assets", "SOURCE_SILENT")
        self.assertEqual(
            self.status_of(self.ledger(), "assets"),
            MAPPED_NO_CURRENT_OBSERVATION,
        )

    def test_source_silent(self):
        """
        Asked, and the source had nothing.
        """
        # `long_term_debt`, not `debt`: 2.33 renamed the metric and `debt` is no
        # longer in the active universe, so asking the ledger about it now
        # measures the rename rather than the status. The status under test is
        # unchanged.
        self.add_scope_run("long_term_debt", "SOURCE_SILENT")
        self.assertEqual(
            self.status_of(self.ledger(), "long_term_debt"), SOURCE_SILENT
        )

    def test_not_yet_collected_is_the_only_backlog_item(self):
        """
        A to-do list built from the other four statuses would be a list of work
        somebody already did or decided against.
        """
        self.add_observation("revenue")
        self.classify()
        self.decline(concept_id_for(IFRS_FULL, "LoansAndAdvancesToCustomers"),
                     "cash")
        self.add_scope_run("long_term_debt", "SOURCE_SILENT")
        ledger = self.ledger()
        self.assertEqual(
            self.status_of(ledger, "long_term_debt"), SOURCE_SILENT
        )
        backlog = {r["metric"] for r in ledger["rows"] if r["is_backlog_item"]}
        self.assertNotIn("long_term_debt", backlog)
        self.assertNotIn("revenue", backlog)
        self.assertNotIn("cash", backlog)
        self.assertIn("r_and_d", backlog)
        self.assertEqual(BACKLOG_STATUS, NOT_YET_COLLECTED)

    def test_deliberately_declined(self):
        """
        A metric whose only candidate concepts were rejected.

        Not hypothetical: the seed declines both IFRS candidates for
        `shares_outstanding` -- authorised shares and a currency amount -- and a
        financial institution that reports no share count lands here. It is a
        real status with a real use, and it must not read as a backlog item.
        """
        seeded = self.registry.declines_for_metric("shares_outstanding")
        self.assertTrue(seeded)
        ledger = self.ledger()
        self.assertEqual(
            self.status_of(ledger, "shares_outstanding"),
            DELIBERATELY_DECLINED,
        )
        row = next(
            r for r in ledger["rows"] if r["metric"] == "shares_outstanding"
        )
        self.assertEqual(len(row["declined"]), len(seeded))
        self.assertEqual(
            sorted({d["reason_code"] for d in row["declined"]}),
            ["IDENTITY_MISMATCH", "NOT_A_METRIC"],
        )
        self.assertNotIn("shares_outstanding", ledger["backlog_items"])

    def test_not_applicable_outranks_everything(self):
        """
        A decision about the company, not about collection.
        """
        self.classify()
        ledger = self.ledger()
        self.assertEqual(
            self.status_of(ledger, "operating_income"), NOT_APPLICABLE_STATUS
        )
        # One refusal, not two. `gross_profit` was refused for this class until
        # 2.25 refuted it against three of the seven SIC 61-62 filers, so it is
        # now applicable here and the ledger's applicable count rises to match.
        self.assertEqual(ledger["metrics_applicable"],
                         ledger["metrics_total"] - 1)

    def test_a_decline_coexists_with_a_collection_through_another_concept(self):
        """
        The mistake the first version made, and the reason the status ordering
        matters.

        A decline is a fact about a *concept*. A metric can be collected through
        one concept while another is declined against it, and a reader is
        entitled to both: AAPL's revenue is collected through US-GAAP concepts
        while four IFRS revenue elements are declined, and those are framework
        judgements rather than per-issuer ones. Making the two compete let the
        collection hide every decline on the row.
        """
        self.add_observation("revenue")
        seeded = self.registry.declines_for_metric("revenue")
        self.assertTrue(seeded)
        row = next(
            r for r in self.ledger()["rows"] if r["metric"] == "revenue"
        )
        self.assertEqual(row["status"], COLLECTED)
        self.assertEqual(len(row["declined"]), len(seeded))
        self.assertIn(
            REASON_COMPONENT_OF,
            {d["reason_code"] for d in row["declined"]},
        )

    def test_every_status_is_in_the_closed_vocabulary(self):
        self.add_observation("revenue")
        self.classify()
        self.decline(concept_id_for(IFRS_FULL, "IssuedCapital"),
                     "shares_outstanding", reason_code=REASON_NOT_A_METRIC)
        self.add_scope_run("debt", "SOURCE_SILENT")
        ledger = self.ledger()
        for row in ledger["rows"]:
            self.assertIn(row["status"], ledger["status_counts"])
        self.assertEqual(
            sum(ledger["status_counts"].values()), ledger["metrics_total"]
        )

    def test_every_row_says_why(self):
        """
        A status with no derivation is an assertion, and a coverage figure a
        reader cannot audit is a coverage figure they have to take on trust.
        """
        self.add_observation("revenue")
        self.classify()
        for row in self.ledger()["rows"]:
            self.assertTrue(row["why"].strip(), row["metric"])


class TestTheDeclineRecordIsClosed(LedgerFixture):
    def test_a_decline_must_state_a_reason(self):
        with self.assertRaises(RegistryError):
            self.registry.decline_concept_mapping(
                concept_id_for(IFRS_FULL, "Revenue"), "revenue",
                REASON_COMPONENT_OF, "   ",
            )

    def test_a_decline_must_be_qualified(self):
        with self.assertRaises(RegistryError):
            DeclinedConcept(
                concept_id="Revenue", considered_for_metric="revenue",
                reason_code=REASON_COMPONENT_OF, reason="why",
            )

    def test_a_decline_reason_is_from_the_closed_vocabulary(self):
        with self.assertRaises(RegistryError):
            DeclinedConcept(
                concept_id=concept_id_for(IFRS_FULL, "Revenue"),
                considered_for_metric="revenue",
                reason_code="FEELS_WRONG", reason="why",
            )
        with self.assertRaises(sqlite3.IntegrityError):
            with self.writable():
                self.connection.execute(
                    "INSERT INTO declined_concept_mappings (concept_id,"
                    " considered_for_metric, reason_code, reason,"
                    " framework_basis, recorded_at)"
                    " VALUES ('ifrs-full:X', 'revenue', 'FEELS_WRONG', 'why',"
                    " NULL, NULL)"
                )

    def test_declines_are_read_back_for_the_metric(self):
        before = len(self.registry.declines_for_metric("revenue"))
        self.decline(concept_id_for(IFRS_FULL, "RevenueFromRoyalties"),
                     "revenue")
        after = self.registry.declines_for_metric("revenue")
        self.assertEqual(len(after), before + 1)
        self.assertIn(
            concept_id_for(IFRS_FULL, "RevenueFromRoyalties"),
            [d["concept_id"] for d in after],
        )
        # And they are stable in order, because a coverage report is read by a
        # language model and a reordering would look like a change in what
        # ST-EVA holds.
        self.assertEqual(
            [d["concept_id"] for d in self.registry.declines_for_metric("revenue")],
            sorted(
                d["concept_id"]
                for d in self.registry.declines_for_metric("revenue")
            ),
        )

    def test_the_seed_declines_are_records_and_not_just_notes(self):
        """
        2.7's nine IFRS decisions were prose in a seed file. They are records
        now, and this fails if they ever go back to being notes.
        """
        declines = self.registry.all_declines()
        self.assertGreaterEqual(len(declines), 9)
        for decline in declines:
            self.assertIn(":", decline["concept_id"])
            self.assertTrue(decline["reason"].strip())
            self.assertTrue(decline["reason_code"].strip())

    def test_the_interesting_decline_is_the_component_case(self):
        """
        The one worth having recorded at all: an IFRS element that is a *part* of
        the revenue line, reported at the same value as the line itself.
        """
        decline = next(
            d for d in self.registry.all_declines()
            if d["concept_id"].endswith("RevenueFromContractsWithCustomers")
        )
        self.assertEqual(decline["considered_for_metric"], "revenue")
        self.assertEqual(decline["reason_code"], REASON_COMPONENT_OF)
        self.assertEqual(decline["framework_basis"], IFRS_FULL)


class TestTheScopeRecordIsWritten(LedgerFixture):
    def test_a_run_records_what_it_was_asked_for(self):
        with self.writable():
            self.connection.execute(
                "INSERT INTO ingestion_runs (run_id, asset_id, source_id,"
                " started_at, finished_at, filings_seen, filings_already_held,"
                " filings_ingested, documents_stored, documents_reused,"
                " source_facts_stored, source_facts_skipped, observations_stored,"
                " observations_skipped, network_fetches, concepts_unresolved,"
                " status, error) VALUES ('r1', ?, 'SecEdgar', ?, ?, 0, 0, 0,"
                " 0, 0, 0, 0, 0, 0, 0, 0, 'OK', NULL)",
                (self.asset_id, _now(), _now()),
            )
            self.connection.execute(
                "INSERT INTO ingestion_scope (run_id, asset_id, metric_id,"
                " mapping_count, attempted, observations_stored, status)"
                " VALUES ('r1', ?, 'revenue', 2, 1, 0, 'INGESTED')",
                (self.asset_id,),
            )
        self.assertEqual(
            self.connection.execute(
                "SELECT status FROM ingestion_scope WHERE metric_id = 'revenue'"
            ).fetchone()[0],
            "INGESTED",
        )

    def test_the_scope_vocabulary_is_closed(self):
        """
        "No answer" must be distinguishable from "an answer we have not parsed
        yet", and a run that asked nothing must not read as one that looked.
        """
        with self.writable():
            self.connection.execute(
                "INSERT INTO ingestion_runs (run_id, asset_id, source_id,"
                " started_at, finished_at, filings_seen, filings_already_held,"
                " filings_ingested, documents_stored, documents_reused,"
                " source_facts_stored, source_facts_skipped, observations_stored,"
                " observations_skipped, network_fetches, concepts_unresolved,"
                " status, error) VALUES ('r2', ?, 'SecEdgar', ?, ?, 0, 0, 0,"
                " 0, 0, 0, 0, 0, 0, 0, 0, 'OK', NULL)",
                (self.asset_id, _now(), _now()),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            with self.writable():
                self.connection.execute(
                    "INSERT INTO ingestion_scope (run_id, asset_id, metric_id,"
                    " mapping_count, attempted, observations_stored, status)"
                    " VALUES ('r2', ?, 'revenue', 1, 1, 0, 'MAYBE')",
                    (self.asset_id,),
                )

    def test_a_run_that_asked_nothing_is_recorded_as_unasked(self):
        """
        The specific regression: a run that returned early because nothing was
        new has asked nothing, and must not silence the evidence that an earlier
        run did look.
        """
        with self.writable():
            self.connection.execute(
                "INSERT INTO ingestion_runs (run_id, asset_id, source_id,"
                " started_at, finished_at, filings_seen, filings_already_held,"
                " filings_ingested, documents_stored, documents_reused,"
                " source_facts_stored, source_facts_skipped, observations_stored,"
                " observations_skipped, network_fetches, concepts_unresolved,"
                " status, error) VALUES ('r3', ?, 'SecEdgar', ?, ?, 0, 0, 0,"
                " 0, 0, 0, 0, 0, 0, 0, 0, 'NO_CHANGE', NULL)",
                (self.asset_id, _now(), _now()),
            )
            self.connection.execute(
                "INSERT INTO ingestion_scope (run_id, asset_id, metric_id,"
                " mapping_count, attempted, observations_stored, status)"
                " VALUES ('r3', ?, 'revenue', 1, 0, 0, 'NOT_ATTEMPTED')",
                (self.asset_id,),
            )
        row = self.connection.execute(
            "SELECT status, attempted FROM ingestion_scope WHERE run_id = 'r3'"
        ).fetchone()
        self.assertEqual(row[0], "NOT_ATTEMPTED")
        self.assertEqual(row[1], 0)


class TestTheLedgerIsReachable(LedgerFixture):
    def test_it_is_on_the_query_surface(self):
        """
        Readable the way everything else is, because that is how a consumer
        would ask. A coverage figure nothing can query is a coverage figure only
        its author can see.
        """
        self.add_observation("revenue")
        self.classify()
        ledger = self.query.coverage_ledger(AAPL)
        self.assertEqual(ledger["asset"], AAPL)
        self.assertEqual(self.status_of(ledger, "revenue"), COLLECTED)
        self.assertEqual(
            self.status_of(ledger, "operating_income"), NOT_APPLICABLE_STATUS
        )

    def test_it_works_on_an_archive_predating_the_migration(self):
        """
        The sealed archive has neither table, and must keep answering.

        It answers `UNDETERMINED` rather than claiming the metrics were never
        asked for. An archive that cannot record what ingestion looked for
        cannot tell "not asked" from "asked and nothing came back", and the
        second is what it plainly has for any metric it did not keep.
        """
        self.add_observation("revenue")
        with self.writable():
            self.connection.execute("DROP TABLE declined_concept_mappings")
            self.connection.execute("DROP TABLE ingestion_scope")
        ledger = self.query.coverage_ledger(AAPL)
        self.assertFalse(ledger["scope_known"])
        # A positive fact is still a positive fact.
        self.assertEqual(
            self.status_of(ledger, "revenue"), COLLECTED
        )
        # And nothing is invented for the rest.
        self.assertEqual(
            self.status_of(ledger, "r_and_d"), UNDETERMINED
        )
        self.assertEqual(ledger["backlog_items"], [])
        for row in ledger["rows"]:
            if row["status"] == UNDETERMINED:
                self.assertIn("predates", row["why"])


if __name__ == "__main__":
    unittest.main()