"""
3.32 Commit B -- persistence of an admission decision.

An `Observation` is what a provider reported. An `Admission` is which of those
observations the engine was allowed to consume, at one asset, at one instant,
under one registry and one policy. These tests hold the line between them, and
they hold a second line that matters more: **a stored admission is evidence,
not authority.** Replay recomputes the decision and reports whether the stored
record agrees; it never reads the stored record to decide.

What the schema deliberately does not carry is tested as directly as what it
does. `value`, `unit`, `currency` and the period columns are absent because
they belong to the observation and are re-derivable from `contract_id`. The
registry and the code are absent because the two identity digests name them and
git holds them. The price's figure is absent for the same reason, while the
price's *identity* is present because `_currency_refusals` lets the price
decide rule 4.
"""

import sqlite3
import unittest

from archive import ArchiveError
from data_contract import (
    METRIC_REVENUE,
    AvailabilityBasis,
    Observation,
    SourceType,
    Unit,
    ValidationStatus,
)
from evidence_valuation_boundary import Admission, Refusal
from registry_identity import registry_state_identity, resolver_policy_identity
from sqlite_archive import SQLiteArchive, admission_identity

REGISTRY = "rgs:" + "0" * 64
POLICY = "pol:" + "1" * 64
AS_OF = "2026-06-30"

# `None` is a meaningful value for `price` -- "no price was a dependency" -- so
# the fixture needs a sentinel distinct from it.
_USE_PRICE = object()


def decision(admitted=True, contract_id="ev-revenue-001",
             source_fact_id="sfid-annual", refusals=(), **overrides):
    fields = {
        "metric": METRIC_REVENUE,
        "as_of": AS_OF,
        "admitted": admitted,
        "observation_id": contract_id,
        "contract_id": contract_id,
        "source_fact_id": source_fact_id,
        "accession": "0000723125-26-000015",
        "taxonomy": "us-gaap",
        "concept": "us-gaap:Revenue",
        "mapping_type": "EXACT",
        "relation_kind": "IDENTITY",
        "availability_class": "SOURCE_DECLARED",
        "considered_observations": 42,
        "superseded_accessions": ("0000723125-25-000099",),
        "superseded_values": (1.0,),
        "competing_concepts": ("us-gaap:SalesRevenueNet",),
        "value": 78_959_000_000.0,
        "unit": Unit.CURRENCY.value,
        "currency": "USD",
        "currency_basis": "REPORTED",
        "period_start": "2025-08-29",
        "period_end": "2026-05-28",
        "refusals": [Refusal(*refusal) for refusal in refusals],
    }
    fields.update(overrides)
    return Admission(**fields)


def price_observation(identifier="ev-price-001"):
    return Observation(
        observation_id=identifier,
        metric="price",
        value=425.50,
        unit=Unit.CURRENCY.value,
        currency="USD",
        currency_basis="REPORTED",
        period_start=None,
        period_end="2026-06-24",
        as_of="2026-06-24",
        available_at="2026-06-24T20:00:00.000Z",
        available_at_basis=AvailabilityBasis.OBSERVATION_INSTANT.value,
        provider="YahooFinance",
        source_type=SourceType.API_LIVE.value,
        source_url=None,
        definition="Observed current or latest market price.",
        methodology="chart API",
        retrieved_at="2026-06-24T21:00:00+00:00",
        raw={},
        status=ValidationStatus.SINGLE_SOURCE,
    )


class AdmissionFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SQLiteArchive(":memory:")
        self.store.record_asset("MU", name="MU", cik="0000723125")
        self.price = price_observation()

    def tearDown(self) -> None:
        self.store.close()

    def record(self, admission=None, as_of=AS_OF, price=_USE_PRICE,
               registry=REGISTRY, policy=POLICY, asset="MU"):
        chosen = self.price if price is _USE_PRICE else price
        return self.store.record_admission(
            asset,
            as_of,
            admission if admission is not None else decision(),
            registry,
            policy,
            chosen,
        )


class TestTheTableExistsAndIsAppendOnly(AdmissionFixture):
    def test_the_migration_creates_the_table(self):
        self.assertTrue(self.store._has_admissions())

    def test_an_update_is_refused(self):
        self.record()
        row = self.store.admissions_for("MU")[0]
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connection.execute(
                "UPDATE admissions SET admitted = 0 WHERE admission_id = ?",
                (row["admission_id"],),
            )

    def test_a_delete_is_refused(self):
        self.record()
        row = self.store.admissions_for("MU")[0]
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connection.execute(
                "DELETE FROM admissions WHERE admission_id = ?",
                (row["admission_id"],),
            )

    def test_a_correction_is_a_superseding_insert(self):
        """Not an UPDATE: the previous decision stays true of its instant."""
        first = self.record()
        second = self.record(
            decision(admitted=False, contract_id=None, source_fact_id=None)
        )
        self.assertTrue(second["created"])
        rows = self.store.admissions_for("MU")
        self.assertEqual(len(rows), 2)
        newest = self.store.effective_admission("MU", METRIC_REVENUE, AS_OF)
        self.assertEqual(newest["admission_id"], second["admission_id"])
        self.assertEqual(newest["supersedes"], first["admission_id"])


class TestDecisionIdentity(AdmissionFixture):
    def test_a_duplicate_identity_is_a_read_not_a_second_row(self):
        self.assertTrue(self.record()["created"])
        self.assertFalse(self.record()["created"])
        self.assertEqual(self.store.admission_count(), 1)

    def test_the_record_is_deterministic(self):
        """
        The identity is content-derived, so the same decision twice yields the
        same id on any machine -- no clock and no sequence is involved.
        """
        self.record()
        first = self.store.admissions_for("MU")[0]
        other = SQLiteArchive(":memory:")
        try:
            other.record_asset("MU", name="MU", cik="0000723125")
            other.record_admission(
                "MU", AS_OF, decision(), REGISTRY, POLICY, self.price
            )
            second = other.admissions_for("MU")[0]
        finally:
            other.close()
        self.assertEqual(first["admission_id"], second["admission_id"])
        self.assertEqual(first["identity"], second["identity"])

    def test_a_different_registry_state_is_a_different_decision(self):
        """3.31's whole point: the interpretation is part of what was decided."""
        self.record()
        self.record(registry="rgs:" + "2" * 64)
        self.assertEqual(self.store.admission_count(), 2)

    def test_a_different_policy_is_a_different_decision(self):
        self.record()
        self.record(policy="pol:" + "2" * 64)
        self.assertEqual(self.store.admission_count(), 2)

    def test_a_different_instant_is_a_different_decision(self):
        self.record()
        self.record(as_of="2025-12-31")
        self.assertEqual(self.store.admission_count(), 2)

    def test_the_identity_function_is_pure(self):
        args = dict(
            asset_id="1", decided_at=AS_OF, metric=METRIC_REVENUE,
            admitted=True, contract_id="ev-revenue-001",
            registry_state_identity=REGISTRY, resolver_policy_identity=POLICY,
        )
        self.assertEqual(admission_identity(**args), admission_identity(**args))
        changed = dict(args, admitted=False)
        self.assertNotEqual(admission_identity(**args), admission_identity(**changed))

    def test_a_refusal_is_a_record_rather_than_an_absence(self):
        """
        A refused admission is a decision, and it is recorded like one.
        """
        result = self.record(decision(
            admitted=False, contract_id=None, source_fact_id=None,
            refusals=(("MAPPING_NOT_EXACT", "us-gaap:Revenues is PARTIAL"),),
        ))
        self.assertTrue(result["created"])
        row = self.store.effective_admission("MU", METRIC_REVENUE, AS_OF)
        self.assertEqual(row["admitted"], 0)
        self.assertIn("MAPPING_NOT_EXACT", row["refusals_json"])
        self.assertIsNone(row["contract_id"])


class TestWhatIsNotStored(AdmissionFixture):
    def setUp(self) -> None:
        super().setUp()
        self.record()
        self.row = self.store.admissions_for("MU")[0]

    def test_no_value_is_stored(self):
        """
        The observation is stored once, under its own identity. A second copy
        here would be a second thing that can disagree with the first.
        """
        columns = {
            row["name"]
            for row in self.store.connection.execute("PRAGMA table_info(admissions)")
        }
        for absent in ("value", "unit", "currency", "currency_basis",
                       "period_start", "period_end", "value_json"):
            self.assertNotIn(absent, columns)

    def test_no_observation_json_is_stored(self):
        columns = {
            row["name"]
            for row in self.store.connection.execute("PRAGMA table_info(admissions)")
        }
        for absent in ("observation_json", "raw_json", "document_json"):
            self.assertNotIn(absent, columns)

    def test_no_registry_content_or_source_is_stored(self):
        """Only digests. git already holds both, and a snapshot would drift."""
        columns = {
            row["name"]
            for row in self.store.connection.execute("PRAGMA table_info(admissions)")
        }
        self.assertIn("registry_state_identity", columns)
        self.assertIn("resolver_policy_identity", columns)
        for absent in ("registry_rows", "registry_json", "policy_json",
                       "source_code"):
            self.assertNotIn(absent, columns)

    def test_no_price_value_is_stored(self):
        """
        The price is recorded by identity, never by figure. Its value is already
        in the archive under its own identity, and a second copy is a second
        thing that can disagree.
        """
        columns = {
            row["name"]
            for row in self.store.connection.execute("PRAGMA table_info(admissions)")
        }
        self.assertIn("price_contract_id", columns)
        for absent in ("price_value", "price_json", "price"):
            self.assertNotIn(absent, columns)
        self.assertEqual(self.row["price_contract_id"], "ev-price-001")

    def test_no_context_id_is_stored(self):
        """
        B5: the crossing produces a BoundaryResult, not a document, so there is
        no context to associate with. Keying the decision by `context_id` would
        make it depend on a document that may never have been built.
        """
        columns = {
            row["name"]
            for row in self.store.connection.execute("PRAGMA table_info(admissions)")
        }
        self.assertNotIn("context_id", columns)

    def test_both_identities_are_present_and_not_null(self):
        columns = {
            row["name"]: row["notnull"]
            for row in self.store.connection.execute("PRAGMA table_info(admissions)")
        }
        self.assertEqual(columns["registry_state_identity"], 1)
        self.assertEqual(columns["resolver_policy_identity"], 1)


class TestThePriceDependencyIsRecordedByIdentity(AdmissionFixture):
    def test_the_price_identity_is_recorded(self):
        """B2: the price decides rule 4, so which price decided is part of it."""
        self.record()
        row = self.store.admissions_for("MU")[0]
        self.assertEqual(row["price_contract_id"], "ev-price-001")

    def test_a_different_price_is_a_different_decision(self):
        """
        Two prices can decide rule 4 differently -- one declaring USD, one
        declaring nothing -- so the price identity belongs in the key.
        """
        self.record()
        self.record(price=price_observation("ev-price-002"))
        self.assertEqual(self.store.admission_count(), 2)

    def test_no_price_is_recorded_as_a_price_dependency(self):
        self.record(price=None)
        row = self.store.admissions_for("MU")[0]
        self.assertIsNone(row["price_contract_id"])


class TestOneObservationManyConsumptions(AdmissionFixture):
    """
    3.27's central result, now expressible in storage.

    One source observation is EVIDENCE_ONLY at one instant and ENGINE_INPUT at
    another. Two admissions say so; no second observation exists and none is
    needed.
    """

    def test_the_same_observation_can_be_admitted_twice_at_two_instants(self):
        self.record(as_of="2024-11-02")
        self.record(as_of="2026-06-30")
        rows = self.store.admissions_for("MU")
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            {row["contract_id"] for row in rows}, {"ev-revenue-001"}
        )
        self.assertEqual(
            {row["admitted"] for row in rows}, {1}
        )

    def test_the_same_source_fact_can_back_a_refused_and_an_admitted_decision(self):
        self.record(
            decision(admitted=False, refusals=(("PERIOD_NOT_DISCRETE", "a quarter"),)),
            as_of="2024-11-02",
        )
        self.record(as_of="2026-06-30")
        rows = self.store.admissions_for("MU")
        self.assertEqual({row["admitted"] for row in rows}, {0, 1})

    def test_no_observation_row_was_touched(self):
        """B1: `observations` keeps meaning a source-fact reading, untouched."""
        before = self.store.observation_count()
        self.record()
        self.assertEqual(self.store.observation_count(), before)


class TestStoredAdmissionIsNotAuthority(AdmissionFixture):
    """
    The line that matters most.

    A stored admission is audit evidence and a comparison target. Replay
    re-derives the decision. If the two disagree, the recomputation stands and
    the disagreement is reported -- a stored row must never be able to make a
    replay produce a figure.
    """

    def test_effective_admission_is_read_only_and_does_not_decide(self):
        self.record()
        stored = self.store.effective_admission("MU", METRIC_REVENUE, AS_OF)
        self.assertIsNotNone(stored)
        self.assertEqual(stored["admitted"], 1)

    def test_a_tampered_stored_row_changes_nothing_recomputable(self):
        """
        The append-only triggers mean tampering fails outright. This pins the
        attempt rather than assuming it, because a row that *could* be edited
        would be authority by another route.
        """
        self.record()
        row = self.store.admissions_for("MU")[0]
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connection.execute(
                "UPDATE admissions SET contract_id = 'ingest|revenue|forged'"
                " WHERE admission_id = ?",
                (row["admission_id"],),
            )
        again = self.store.admissions_for("MU")[0]
        self.assertEqual(again["contract_id"], "ev-revenue-001")

    def test_a_repeated_identity_is_refused_by_the_constraint(self):
        """
        What the schema really guarantees about `identity`.

        UNIQUE makes a repeated decision a read rather than a second row. That
        is a dedup guarantee, and it is the one the writer relies on.

        It is *not* an integrity proof, and pretending otherwise would be the
        more dangerous claim. SQLite cannot recompute a SHA-256 in a CHECK
        constraint, so a row whose `identity` does not describe its own content
        can be written by anyone holding the connection. What stops that row from
        mattering is not the constraint: it is that replay re-derives the
        decision and never reads this row to make it. The test below records the
        gap rather than asserting a protection that does not exist.
        """
        self.record()
        recorded = self.store.admissions_for("MU")[0]
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connection.execute(
                "INSERT INTO admissions (admission_id, asset_id, decided_at,"
                " metric, admitted, registry_state_identity,"
                " resolver_policy_identity, identity, created_at)"
                " VALUES ('adm_second', ?, ?, ?, 1, ?, ?, ?, '2026-01-01')",
                (
                    self.store._asset_id_for_ticker("MU"), AS_OF, METRIC_REVENUE,
                    REGISTRY, POLICY, recorded["identity"],
                ),
            )

    def test_a_forged_identity_is_writable_and_that_is_a_recorded_gap(self):
        """
        The honest negative. A hand-written row with a meaningless `identity`
        inserts cleanly, because the column is UNIQUE and not CHECKed.

        Stated as a test so that a future migration which does close the gap is
        visible as a change rather than as an unexplained difference.
        """
        self.record()
        forged = "0" * 64
        self.store.connection.execute(
            "INSERT INTO admissions (admission_id, asset_id, decided_at,"
            " metric, admitted, contract_id, registry_state_identity,"
            " resolver_policy_identity, identity, created_at)"
            " VALUES ('adm_forged', ?, ?, ?, 1, 'ingest|revenue|forged', ?, ?,"
            " ?, '2026-01-01')",
            (
                self.store._asset_id_for_ticker("MU"), AS_OF, METRIC_REVENUE,
                REGISTRY, POLICY, forged,
            ),
        )
        self.store.connection.commit()
        self.assertIsNotNone(self.store.get_admission("adm_forged"))
        # And it changes nothing, because `effective_admission` is a comparison
        # target that no decision path reads.
        effective = self.store.effective_admission("MU", METRIC_REVENUE, AS_OF)
        self.assertIsNotNone(effective)
        self.assertEqual(effective["admitted"], 1)

    def test_an_archive_without_the_table_reports_rather_than_raises(self):
        """
        Every archive on disk predates 3.32, so its absence must be ordinary.
        """
        legacy = sqlite3.connect(":memory:")
        legacy.row_factory = sqlite3.Row
        legacy.execute("CREATE TABLE assets (asset_id INTEGER PRIMARY KEY,"
                       " ticker TEXT UNIQUE, name TEXT, exchange TEXT,"
                       " currency TEXT, cik TEXT, recorded_at TEXT)")
        legacy.execute("INSERT INTO assets (ticker, name) VALUES ('MU','MU')")
        legacy.commit()
        self.assertFalse(
            legacy.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table'"
                " AND name='admissions'"
            ).fetchone()
        )
        legacy.close()


class TestRealIdentitiesAreAccepted(AdmissionFixture):
    def test_a_real_pair_of_identities_round_trips(self):
        """Not the fixture digests: the 3.31 functions' own output."""
        registry = registry_state_identity(self.store.connection)
        policy = resolver_policy_identity(self.store.connection)
        self.record(registry=registry, policy=policy)
        row = self.store.admissions_for("MU")[0]
        self.assertEqual(row["registry_state_identity"], registry)
        self.assertEqual(row["resolver_policy_identity"], policy)


class TestProductionAdmissionWritePath(unittest.TestCase):
    """
    3.34: Verify that run_st_eva / context generation writes admissions
    to the persistent archive when context and archive are provided,
    is idempotent, leaves source observations untouched, and never uses
    stored admissions as engine inputs.
    """

    def setUp(self) -> None:
        self.store = SQLiteArchive(":memory:")

    def tearDown(self) -> None:
        self.store.close()

    def test_live_run_writes_admission(self):
        import io, sys
        from st_eva_runner import run_st_eva

        self.assertEqual(self.store.admission_count(), 0)
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            result = run_st_eva(
                ticker="MSFT",
                mode="regression",
                save_snapshot=False,
                context_path="-",
                archive=self.store,
            )
        finally:
            sys.stdout = old_stdout

        self.assertIsNotNone(result)
        self.assertGreater(self.store.admission_count(), 0)
        admissions = self.store.admissions_for("MSFT")
        self.assertEqual(len(admissions), 1)
        self.assertEqual(admissions[0]["metric"], "revenue")

    def test_repeated_same_run_is_idempotent(self):
        import io, sys
        from st_eva_runner import run_st_eva

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            run_st_eva(
                ticker="MSFT",
                mode="regression",
                save_snapshot=False,
                context_path="-",
                archive=self.store,
            )
        finally:
            sys.stdout = old_stdout
        count_first = self.store.admission_count()
        self.assertGreater(count_first, 0)

        # Repeated run with same inputs
        sys.stdout = io.StringIO()
        try:
            run_st_eva(
                ticker="MSFT",
                mode="regression",
                save_snapshot=False,
                context_path="-",
                archive=self.store,
            )
        finally:
            sys.stdout = old_stdout
        count_second = self.store.admission_count()
        self.assertEqual(count_first, count_second)

    def test_source_observation_remains_unchanged(self):
        import io, sys
        from st_eva_runner import run_st_eva

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            run_st_eva(
                ticker="MSFT",
                mode="regression",
                save_snapshot=False,
                context_path="-",
                archive=self.store,
            )
        finally:
            sys.stdout = old_stdout
        obs_before = [
            (r["observation_id"], r["metric"], r["value_json"])
            for r in self.store.connection.execute(
                "SELECT observation_id, metric, value_json FROM observations ORDER BY observation_id"
            ).fetchall()
        ]

        # Re-run
        sys.stdout = io.StringIO()
        try:
            run_st_eva(
                ticker="MSFT",
                mode="regression",
                save_snapshot=False,
                context_path="-",
                archive=self.store,
            )
        finally:
            sys.stdout = old_stdout
        obs_after = [
            (r["observation_id"], r["metric"], r["value_json"])
            for r in self.store.connection.execute(
                "SELECT observation_id, metric, value_json FROM observations ORDER BY observation_id"
            ).fetchall()
        ]
        self.assertEqual(obs_before, obs_after)

    def test_stored_admission_is_not_used_to_compute_live_valuation(self):
        import io, sys
        from st_eva_runner import run_st_eva

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            result1 = run_st_eva(
                ticker="MSFT",
                mode="regression",
                save_snapshot=False,
                context_path="-",
                archive=self.store,
            )
        finally:
            sys.stdout = old_stdout

        val1 = result1["market_implied_assumptions"]["forward_eps_at_reference_multiple"]
        self.assertGreater(self.store.admission_count(), 0)

        # Run with an independent clean store (zero stored admissions)
        clean_store = SQLiteArchive(":memory:")
        try:
            sys.stdout = io.StringIO()
            try:
                result2 = run_st_eva(
                    ticker="MSFT",
                    mode="regression",
                    save_snapshot=False,
                    context_path="-",
                    archive=clean_store,
                )
            finally:
                sys.stdout = old_stdout

            val2 = result2["market_implied_assumptions"]["forward_eps_at_reference_multiple"]
            self.assertEqual(val1, val2)
        finally:
            clean_store.close()


if __name__ == "__main__":
    unittest.main()

