"""
Live / Replay observation semantics.

A live run puts comparable (`cmp-`) SEC filing observations into the context as
evidence (cross-source, series). Replay used to drop every SecEdgar filing
observation that was not admitted, so the rebuilt context lacked evidence the
stored one carried and replay reported DIVERGED.

The semantics asserted here:

    material candidates (non-`cmp-` SEC rows) need admission to enter selection
    comparable `cmp-` SEC rows are evidence, kept in context with no admission

Admission itself must be unaffected.
"""

import tempfile
import unittest
from pathlib import Path

from archive import REPLAY_MATCH, replay
from core_registry import CoreRegistry
from data_contract import (
    METRIC_NET_INCOME,
    METRIC_PRICE,
    AvailabilityBasis,
    Observation,
    SourceType,
    Unit,
    ValidationStatus,
)
from evidence_valuation_boundary import V1_CROSSING_METRICS, admit
from registry_identity import registry_state_identity, resolver_policy_identity
from registry_seed import seed
from sqlite_archive import SQLiteArchive
from st_eva_runner import build_context_from_observations

ASSET = "MU"
AS_OF = "2026-06-30"
CMP_ID = "cmp-net_income-sec-fy2025-000072312525000028"
INGEST_ID = "ingest|net_income|NetIncomeLoss|0000723125-25-000028|2024-09-01|2025-08-28|currency"


def price() -> Observation:
    return Observation(
        observation_id="ev-price-001",
        metric=METRIC_PRICE,
        value=425.5,
        unit=Unit.CURRENCY.value,
        currency="USD",
        currency_basis="REPORTED",
        period_start=None,
        period_end=AS_OF,
        as_of=AS_OF,
        available_at="2026-06-30T20:00:00.000Z",
        available_at_basis=AvailabilityBasis.OBSERVATION_INSTANT.value,
        provider="YahooFinance",
        source_type=SourceType.API_LIVE.value,
        source_url=None,
        definition="Observed current market price.",
        methodology="chart API",
        retrieved_at="2026-06-30T21:00:00+00:00",
        raw={"regular_market_price": 425.5},
        status=ValidationStatus.SINGLE_SOURCE,
    )


def sec_net_income(observation_id: str) -> Observation:
    return Observation(
        observation_id=observation_id,
        metric=METRIC_NET_INCOME,
        value=8_539_000_000.0,
        unit=Unit.CURRENCY.value,
        currency="USD",
        currency_basis="REPORTED",
        period_start="2024-08-30",
        period_end="2025-08-28",
        as_of="2025-08-28",
        available_at="2025-10-03T21:02:11.000Z",
        available_at_basis=AvailabilityBasis.ACCEPTANCE_DATETIME.value,
        provider="SecEdgar",
        source_type=SourceType.REGULATORY_FILING.value,
        source_url=None,
        definition="net_income definition",
        methodology="us-gaap:NetIncomeLoss as filed in 10-K",
        retrieved_at="2026-06-30T21:00:00+00:00",
        raw={"sec_fact": {"taxonomy": "us-gaap", "tag": "NetIncomeLoss",
                          "accession": "0000723125-25-000028", "form": "10-K",
                          "fy": 2025, "fp": "FY"}},
        status=ValidationStatus.UNVERIFIABLE,
        status_reasons=("a single official source cannot cross-validate itself",),
        basis={"reporting_framework": "us-gaap", "source_declared": True},
    )


def replay_doc(observation_set, as_of, generated_at, asset_metadata=None):
    return build_context_from_observations(
        [observation_set.get(i) for i in observation_set.ids()],
        ticker=observation_set.ticker,
        as_of=as_of,
        generated_at=generated_at,
        asset_metadata=asset_metadata,
    )


class TestReplayEvidenceSymmetry(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.store = SQLiteArchive(path=str(Path(self._dir.name) / "a.sqlite"))
        seed(CoreRegistry(self.store.connection))
        self.store.record_asset(ASSET, name="Micron", exchange="NASDAQ", currency="USD")
        self.price = price()

    def tearDown(self):
        self.store.close()
        self._dir.cleanup()

    def _record(self, observation):
        self.store.record_observation(
            ASSET, observation,
            availability_class="SOURCE_DECLARED",
            first_archived_at="2026-06-30T21:00:00.000Z",
            replay_eligible_from=(
                "2026-06-30T20:00:00.000Z"
                if observation.observation_id == "ev-price-001"
                else "2025-10-03T21:02:11.000Z"
            ),
        )

    def _archive_live_run(self):
        """What a live run stores: context over every observation, plus admission."""
        rows = self.store.observations_for(ASSET, AS_OF)
        stored = build_context_from_observations(
            rows, ticker=ASSET, as_of=AS_OF,
            generated_at="2026-06-30T21:30:00+00:00",
            asset_metadata=self.store.asset_metadata(ASSET),
        )
        self.store.record_context(ASSET, stored, replay_fidelity="SOURCE_DECLARED")
        _, admissions = admit(
            self.store, ASSET, AS_OF, self.price, metrics=V1_CROSSING_METRICS
        )
        reg = registry_state_identity(self.store.connection)
        pol = resolver_policy_identity(self.store.connection)
        for adm in admissions:
            self.store.record_admission(ASSET, AS_OF, adm, reg, pol, self.price)
        return stored, admissions

    def test_unadmitted_sec_evidence_is_kept_and_replay_matches(self):
        self._record(self.price)
        self._record(sec_net_income(CMP_ID))
        stored, admissions = self._archive_live_run()

        # Precondition: the SEC row is evidence in the stored context and
        # nothing was admitted (revenue has no SEC fact here).
        self.assertIn(f"obs:{CMP_ID}", stored["provenance"]["refs"])
        self.assertFalse(any(a.admitted for a in admissions))

        result = replay(self.store, ASSET, AS_OF, replay_doc)

        self.assertEqual(result.outcome, REPLAY_MATCH, result.reason)
        self.assertEqual(result.document["context_id"], stored["context_id"])
        self.assertIn(f"obs:{CMP_ID}", result.document["provenance"]["refs"])

        # Admission is unaffected by keeping evidence.
        self.assertFalse(any(a.admitted for a in result.admissions))
        self.assertEqual(
            [(a.metric, a.admitted, a.contract_id) for a in result.admissions],
            [(a.metric, a.admitted, a.contract_id) for a in admissions],
        )

    def test_unadmitted_ingest_material_candidate_still_excluded(self):
        self._record(self.price)
        self._record(sec_net_income(INGEST_ID))
        result = replay(self.store, ASSET, AS_OF, replay_doc)
        self.assertTrue(result.reconstructed)
        self.assertNotIn(f"obs:{INGEST_ID}", result.document["provenance"]["refs"])
        self.assertFalse(any(a.admitted for a in result.admissions))


if __name__ == "__main__":
    unittest.main()

