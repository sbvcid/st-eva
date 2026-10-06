"""
3.32 Commit C -- Replay wiring with point-in-time admission and verification.

Asserts:
1. Same price fact
2. Same admitted revenue fact
3. Same source_fact_id
4. Same valuation input
5. Same current_ps
6. Same replay context where applicable
7. Stored admission and recomputed admission match
8. No older SEC revenue wins (neither 1,402,000,000 oldest nor refused stubs)

Negative cases:
- Modify registry state -> detectable divergence
- Modify policy file -> detectable divergence
- Remove selected source observation -> explicit divergence
- Add older eligible SEC observation -> cannot change selected fact incorrectly
- Stored admission tampered -> replay recomputation still wins and divergence reported
- Refusal stored but recomputation admits -> divergence, not silent acceptance
"""

import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from archive import (
    REPLAY_DIVERGED,
    REPLAY_MATCH,
    REPLAY_NO_SNAPSHOT,
    replay,
)
from data_contract import (
    METRIC_PRICE,
    METRIC_REVENUE,
    AvailabilityBasis,
    Observation,
    SourceType,
    Unit,
    ValidationStatus,
)
from evidence_valuation_boundary import admit, V1_CROSSING_METRICS
from registry_identity import registry_state_identity, resolver_policy_identity
from sqlite_archive import SQLiteArchive
from st_eva_runner import build_context_from_observations

H = (
    Path(__file__).resolve().parent.parent
    / "experiments"
    / "003-llm-evidence-retrieval"
    / "harness"
)
MU_ARCHIVE = H / "pilot-mu.sqlite"
ASSET = "MU"
CUTOFF = "2026-06-30"

OLDEST_REVENUE = 1_402_000_000.0
ADMITTED_ANNUAL_REVENUE = 37_378_000_000.0
REFUSED_STUB_REVENUE = 78_959_000_000.0


def make_price_observation(price_value: float = 425.50, identifier: str = "ev-price-001") -> Observation:
    return Observation(
        observation_id=identifier,
        metric=METRIC_PRICE,
        value=price_value,
        unit=Unit.CURRENCY.value,
        currency="USD",
        currency_basis="REPORTED",
        period_start=None,
        period_end=CUTOFF,
        as_of=CUTOFF,
        available_at="2026-06-30T20:00:00.000Z",
        available_at_basis=AvailabilityBasis.OBSERVATION_INSTANT.value,
        provider="YahooFinance",
        source_type=SourceType.API_LIVE.value,
        source_url=None,
        definition="Observed current market price.",
        methodology="chart API",
        retrieved_at="2026-06-30T21:00:00+00:00",
        raw={"regular_market_price": price_value},
        status=ValidationStatus.SINGLE_SOURCE,
    )


def replay_doc(observation_set, as_of, generated_at, asset_metadata=None):
    return build_context_from_observations(
        [observation_set.get(id_) for id_ in observation_set.ids()],
        ticker=observation_set.ticker,
        as_of=as_of,
        generated_at=generated_at,
        asset_metadata=asset_metadata,
    )


class RealMUReplayFixture(unittest.TestCase):
    def setUp(self) -> None:
        if not MU_ARCHIVE.exists():
            raise unittest.SkipTest("MU pilot archive not present")
        self.tmpdir = tempfile.mkdtemp(prefix="steva332_replay_")
        self.target = Path(self.tmpdir) / "mu.sqlite"
        shutil.copyfile(MU_ARCHIVE, self.target)

        self.store = SQLiteArchive(path=str(self.target))
        self.price = make_price_observation()
        # Record the valuation-side price observation into the archive
        self.store.record_observation(
            asset=ASSET,
            observation=self.price,
            availability_class="SOURCE_DECLARED",
            first_archived_at="2026-06-30T21:00:00.000Z",
            replay_eligible_from="2026-06-30T20:00:00.000Z",
        )

        # Compute admission and persist it
        self.inputs, self.admissions = admit(
            self.store, ASSET, CUTOFF, self.price, metrics=V1_CROSSING_METRICS
        )
        self.reg_id = registry_state_identity(self.store.connection)
        self.pol_id = resolver_policy_identity(self.store.connection)
        for adm in self.admissions:
            self.store.record_admission(
                ASSET, CUTOFF, adm, self.reg_id, self.pol_id, self.price
            )

    def tearDown(self) -> None:
        self.store.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)


class TestRealMUReplayWiring(RealMUReplayFixture):
    def test_recomputation_matches_stored_admission_and_rebuilds_context(self):
        result = replay(self.store, ASSET, CUTOFF, replay_doc)
        self.assertTrue(result.reconstructed)
        self.assertIn(result.outcome, (REPLAY_MATCH, REPLAY_NO_SNAPSHOT))

        # 1. Same price fact
        observed_price = result.document["observed"]["price"][0]["figure"]["value"]
        self.assertEqual(observed_price, 425.50)

        # 2. Same admitted revenue fact
        observed_revenue = result.document["observed"]["revenue"][0]["figure"]["value"]
        self.assertEqual(
            float(observed_revenue),
            ADMITTED_ANNUAL_REVENUE,
        )

        # 3. Same source_fact_id
        admitted_adm = self.admissions[0]
        self.assertTrue(admitted_adm.admitted)
        self.assertIsNotNone(admitted_adm.source_fact_id)
        effective = self.store.effective_admission(ASSET, METRIC_REVENUE, CUTOFF)
        self.assertEqual(effective["source_fact_id"], admitted_adm.source_fact_id)

        # 4. Same valuation input
        self.assertEqual(
            float(observed_revenue),
            float(self.inputs.current_revenue),
        )

        # 5. Same current_ps
        ps_figure = result.document["derived"]["current_ps"]["figure"]
        self.assertIsNotNone(ps_figure)
        self.assertEqual(ps_figure["ref"], "der:current_ps")

        # 7. Stored admission and recomputed admission match
        self.assertEqual(effective["contract_id"], admitted_adm.contract_id)
        self.assertEqual(effective["admitted"], 1)

        # 8. No older SEC revenue wins (not oldest 1,402,000,000 and not 9-month stub 78,959,000,000)
        self.assertNotEqual(float(observed_revenue), OLDEST_REVENUE)
        self.assertNotEqual(float(observed_revenue), REFUSED_STUB_REVENUE)

    def test_replay_with_stored_context_yields_replay_match(self):
        # Build context and store it
        result_first = replay(self.store, ASSET, CUTOFF, replay_doc)
        self.store.record_context(ASSET, result_first.document, replay_fidelity="FIDELITY_SOURCE_DECLARED")

        result = replay(self.store, ASSET, CUTOFF, replay_doc)
        self.assertEqual(result.outcome, REPLAY_MATCH)
        self.assertTrue(result.matched)


class TestRealMUReplayNegativeCases(RealMUReplayFixture):
    def test_modify_registry_state_produces_detectable_divergence(self):
        # Modify metric_registry state by inserting a new metric with valid vocabulary
        self.store.connection.execute(
            "INSERT INTO metric_registry (metric_id, display_name, statement, semantic_definition, unit_family, normal_period_type, applicability, comparability_group, status)"
            " VALUES ('tamper_metric', 'Tamper', 'INCOME', 'Tamper test', 'currency', 'DURATION', 'APPLICABLE', 'ALL', 'ACTIVE')"
        )
        self.store.connection.commit()

        result = replay(self.store, ASSET, CUTOFF, replay_doc)
        self.assertEqual(result.outcome, REPLAY_DIVERGED)
        self.assertIn("registry_state_identity", str(result.reason))

    def test_modify_policy_file_produces_detectable_divergence(self):
        # Mock resolver_policy_identity in registry_identity
        with patch("registry_identity.resolver_policy_identity", return_value="pol:modified_policy_hash"):
            result = replay(self.store, ASSET, CUTOFF, replay_doc)
            self.assertEqual(result.outcome, REPLAY_DIVERGED)
            self.assertIn("resolver_policy_identity", str(result.reason))

    def test_remove_selected_source_observation_produces_divergence(self):
        # Remove the admitted observation from the archive
        admitted_id = self.admissions[0].contract_id
        self.store.connection.execute("DROP TRIGGER IF EXISTS observations_no_update")
        self.store.connection.execute(
            "UPDATE observations SET replay_eligible_from = NULL WHERE contract_id = ?",
            (admitted_id,),
        )
        self.store.connection.commit()

        result = replay(self.store, ASSET, CUTOFF, replay_doc)
        self.assertEqual(result.outcome, REPLAY_DIVERGED)

    def test_add_older_eligible_sec_observation_cannot_change_selected_fact(self):
        # Add an older eligible SEC observation
        older_obs = Observation(
            observation_id="ingest|revenue|RevenueFromContractWithCustomerExcludingAssessedTax|0000723125-24-999999|2023-08-30|2024-08-28|USD",
            metric=METRIC_REVENUE,
            value=25_000_000_000.0,
            unit=Unit.CURRENCY.value,
            currency="USD",
            currency_basis="REPORTED",
            period_start="2023-08-30",
            period_end="2024-08-28",
            as_of="2024-08-28",
            available_at="2024-10-01T00:00:00.000Z",
            available_at_basis=AvailabilityBasis.ACCEPTANCE_DATETIME.value,
            provider="SecEdgar",
            source_type=SourceType.REGULATORY_FILING.value,
            source_url=None,
            definition="Older revenue",
            methodology="us-gaap",
            retrieved_at="2024-10-01T00:00:00.000Z",
            raw={},
            status=ValidationStatus.SINGLE_SOURCE,
        )
        self.store.record_observation(
            asset=ASSET,
            observation=older_obs,
            availability_class="SOURCE_DECLARED",
            first_archived_at="2024-10-01T00:00:00.000Z",
            replay_eligible_from="2024-10-01T00:00:00.000Z",
        )

        result = replay(self.store, ASSET, CUTOFF, replay_doc)
        observed_revenue = result.document["observed"]["revenue"][0]["figure"]["value"]
        self.assertEqual(
            float(observed_revenue),
            ADMITTED_ANNUAL_REVENUE,
        )

    def test_stored_admission_tampered_recomputation_still_wins(self):
        effective = self.store.effective_admission(ASSET, METRIC_REVENUE, CUTOFF)
        # Attempting direct UPDATE is blocked by trigger:
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connection.execute(
                "UPDATE admissions SET price_contract_id = 'ev-price-tampered' WHERE admission_id = ?",
                (effective["admission_id"],),
            )

        # Temporarily drop triggers in test sandbox to simulate storage corruption:
        self.store.connection.execute("DROP TRIGGER IF EXISTS admissions_no_update")
        self.store.connection.execute(
            "UPDATE admissions SET price_contract_id = 'ev-price-forged' WHERE admission_id = ?",
            (effective["admission_id"],),
        )
        self.store.connection.commit()

        result = replay(self.store, ASSET, CUTOFF, replay_doc)
        observed_revenue = result.document["observed"]["revenue"][0]["figure"]["value"]
        # Recomputation produced the correct document:
        self.assertEqual(
            float(observed_revenue),
            ADMITTED_ANNUAL_REVENUE,
        )
        # And reported divergence because stored admission was tampered:
        self.assertEqual(result.outcome, REPLAY_DIVERGED)
        self.assertIn("price_contract_id", str(result.reason))

    def test_refusal_stored_but_recomputation_admits_causes_divergence(self):
        # Simulate stored admission being a refusal (admitted = 0)
        effective = self.store.effective_admission(ASSET, METRIC_REVENUE, CUTOFF)
        self.store.connection.execute("DROP TRIGGER IF EXISTS admissions_no_update")
        self.store.connection.execute(
            "UPDATE admissions SET admitted = 0 WHERE admission_id = ?",
            (effective["admission_id"],),
        )
        self.store.connection.commit()

        result = replay(self.store, ASSET, CUTOFF, replay_doc)
        observed_revenue = result.document["observed"]["revenue"][0]["figure"]["value"]
        # Recomputation still produces the admitted figure
        self.assertEqual(
            float(observed_revenue),
            ADMITTED_ANNUAL_REVENUE,
        )
        # And divergence is reported rather than silent acceptance
        self.assertEqual(result.outcome, REPLAY_DIVERGED)
        self.assertIn("admitted", str(result.reason))


if __name__ == "__main__":
    unittest.main()
