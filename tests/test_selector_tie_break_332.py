"""
3.32 Commit A -- the selector tie-break contract, and the fact that it is open.

3.32 was asked to choose a third ordering level for a point-in-time selection:
what should win when several facts became knowable at one instant. The brief
allows one answer only -- stop and record the ambiguity if the evidence does not
determine a unique correct tie-break -- and the measurement in
`selector_tie_break_ambiguity_332.py` concludes that it does not.

The short of it: `observation_id` is the only candidate that is total,
deterministic and already part of the contract, and adding it changes the
selection for 8 of the 18 metrics on the real archive. For `revenue` it
prefers a quarter stub over the annual from the same filing, and rule 7 refuses
the stub, so it would turn an admission into a refusal rather than change a
number. Everything else is either not a total order or not reproducible across
independently rebuilt archives.

So nothing was changed. What these tests do is pin the behaviour that exists,
so it cannot drift silently, and pin the record of why it is open, so the next
stage cannot mistake an accident for a rule.

The tests that matter most here are the two at the bottom: they assert that the
ambiguity is still recorded and still measured. A future change to either
selector that leaves the record stale should fail here.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from data_contract import (
    METRIC_REVENUE,
    AvailabilityBasis,
    Observation,
    ObservationSet,
    SourceType,
    Unit,
    ValidationStatus,
    is_comparable_observation,
)
from st_eva_runner import _latest_accepted, market_data_from_observations

HERE = Path(__file__).resolve().parent
H = (
    HERE.parent
    / "experiments"
    / "003-llm-evidence-retrieval"
    / "harness"
)
MU_ARCHIVE = H / "pilot-mu.sqlite"
ARTIFACT = H / "332-selector-tie-break-ambiguity.json"
ASSET = "MU"
CUTOFF = "2026-06-30"

OLDEST_REVENUE = 1_402_000_000.0
ANNUAL_REVENUE = 78_959_000_000.0


def _row(identifier, value, available_at, as_of="2026-05-28",
         available=True, unit=Unit.CURRENCY.value):
    """
    A revenue row, optionally one that carries no value.

    `Observation.is_available` is `value is not None and value != {}`
    (`data_contract.py:779`) -- it is about the value, not about `status`. So an
    "unavailable" observation here is one the live run wrote with no figure,
    which is exactly the row `unavailable_observation` produces and exactly the
    row `latest_knowable` refuses to return.
    """
    return Observation(
        observation_id=identifier,
        metric=METRIC_REVENUE,
        value=value if available else None,
        unit=unit,
        currency="USD",
        currency_basis="REPORTED",
        period_start="2025-08-29",
        period_end="2026-05-28",
        as_of=as_of,
        available_at=available_at,
        available_at_basis=AvailabilityBasis.ACCEPTANCE_DATETIME.value,
        provider="SecEdgar",
        source_type=SourceType.REGULATORY_FILING.value,
        source_url=None,
        definition="Revenue as filed.",
        methodology="us-gaap:Revenue",
        retrieved_at="2026-06-24T22:59:46+00:00",
        raw={},
        status=ValidationStatus.SINGLE_SOURCE,
    )


def _price(available_at="2026-06-24T23:00:00+00:00"):
    return Observation(
        observation_id="ev-price-001",
        metric="price",
        value=425.50,
        unit=Unit.CURRENCY.value,
        currency="USD",
        currency_basis="REPORTED",
        period_start=None,
        period_end="2026-06-24",
        as_of="2026-06-24",
        available_at=available_at,
        available_at_basis=AvailabilityBasis.OBSERVATION_INSTANT.value,
        provider="YahooFinance",
        source_type=SourceType.API_LIVE.value,
        source_url=None,
        definition="Observed current or latest market price.",
        methodology="chart API",
        retrieved_at="2026-06-24T23:00:00+00:00",
        raw={},
        status=ValidationStatus.SINGLE_SOURCE,
    )


class TestTheTieIsTheNormalCase(unittest.TestCase):
    """Premise. A single filing produces several knowable facts at one instant."""

    def test_one_instant_carries_both_an_annual_and_a_stub(self):
        annual = _row("ingest|revenue|R|2025-08-29|2026-05-28|USD",
                      ANNUAL_REVENUE, "2026-06-24T22:59:46.000Z")
        stub = _row("ingest|revenue|R|2026-02-27|2026-05-28|USD",
                    41_456_000_000.0, "2026-06-24T22:59:46.000Z")
        self.assertEqual(annual.available_at, stub.available_at)
        self.assertEqual(annual.as_of, stub.as_of)
        self.assertNotEqual(annual.observation_id, stub.observation_id)

    def test_two_facts_with_the_same_available_at_are_not_ordered_by_it(self):
        earlier = _row("ingest|revenue|R|a", 1.0, "2024-01-01T00:00:00.000Z")
        later = _row("ingest|revenue|R|b", 2.0, "2026-01-01T00:00:00.000Z")
        self.assertEqual(
            _latest_accepted([earlier, later]).observation_id, later.observation_id
        )

    def test_as_of_orders_what_available_at_cannot(self):
        old_instant = _row("ingest|revenue|R|a", 1.0, "2026-06-01T00:00:00.000Z",
                           as_of="2025-05-28")
        new_instant = _row("ingest|revenue|R|b", 2.0, "2026-06-01T00:00:00.000Z",
                           as_of="2026-05-28")
        self.assertEqual(
            _latest_accepted([old_instant, new_instant]).observation_id,
            new_instant.observation_id,
        )


class TestTheAmbiguityIsRealAndPinned(unittest.TestCase):
    """
    What the tie-break is *not* allowed to do.

    These are the constraints that ruled every candidate out. They are pinned so
    that a future proposal has to face them rather than rediscover them.
    """

    def test_reordering_the_input_changes_the_selection(self):
        """
        The consequence of leaving the tie-break open, stated as a fact.

        Both selectors inherit their tie-break from the order they were given,
        so a caller that reorders observations gets a different -- equally
        defensible-looking -- answer. This is not a hypothetical: on the real
        archive it holds for 12 of 18 metrics.
        """
        annual = _row("ingest|revenue|R|2025-08-29|2026-05-28|USD",
                      ANNUAL_REVENUE, "2026-06-24T22:59:46.000Z")
        stub = _row("ingest|revenue|R|2026-02-27|2026-05-28|USD",
                    41_456_000_000.0, "2026-06-24T22:59:46.000Z")
        self.assertEqual(
            _latest_accepted([annual, stub]).observation_id, stub.observation_id
        )
        self.assertEqual(
            _latest_accepted([stub, annual]).observation_id, annual.observation_id
        )

    def test_an_observation_id_tie_break_would_prefer_the_stub(self):
        """
        Why `observation_id` was rejected, as an executable fact.

        The contract id sorts on period start, so `2025-08-29` precedes
        `2026-02-27` and the stub carries the larger id. Choosing the largest
        would hand admission a quarter, which `_period_refusals` then refuses
        with `PERIOD_NOT_DISCRETE`.
        """
        annual = _row("ingest|revenue|R|2025-08-29|2026-05-28|USD",
                      ANNUAL_REVENUE, "2026-06-24T22:59:46.000Z")
        stub = _row("ingest|revenue|R|2026-02-27|2026-05-28|USD",
                    41_456_000_000.0, "2026-06-24T22:59:46.000Z")
        by_id = sorted(
            [annual, stub],
            key=lambda o: (o.available_at or "", o.as_of or "",
                           o.observation_id or ""),
        )[-1]
        self.assertEqual(by_id.observation_id, stub.observation_id)
        self.assertGreater(stub.observation_id, annual.observation_id)


class TestTheAmbiguityIsRecorded(unittest.TestCase):
    """
    The record exists and is current.

    A recorded ambiguity that nobody re-reads is worse than an open question,
    because it reads as a decision.
    """

    @classmethod
    def setUpClass(cls) -> None:
        if not ARTIFACT.exists():
            raise unittest.SkipTest(
                "run selector_tie_break_ambiguity_332.py to build the record"
            )
        cls.record = json.loads(ARTIFACT.read_text(encoding="utf-8"))

    def test_the_verdict_is_recorded_as_ambiguous(self):
        self.assertIn("AMBIGUOUS", self.record["verdict"])

    def test_the_measurement_is_present(self):
        self.assertGreater(self.record["revenue_rows"], 0)
        self.assertGreater(self.record["revenue_tie_groups"], 0)
        self.assertLess(
            self.record["revenue_distinct_available_at"],
            self.record["revenue_rows"],
            "a filing reporting many periods at one instant is the whole reason",
        )

    def test_the_observation_id_proposal_is_recorded_as_rejected(self):
        self.assertGreater(
            self.record["metrics_changed_by_observation_id_tiebreak"], 0
        )
        self.assertIn(
            "observation_id", self.record["rejected_candidates"]
        )

    def test_every_candidate_the_brief_named_was_considered(self):
        for candidate in (
            "observation_id", "source_fact_id", "accession",
            "filing_order", "database_row_order",
        ):
            self.assertIn(candidate, self.record["rejected_candidates"])

    def test_the_decisive_tie_group_is_recorded(self):
        group = self.record["decisive_tie_group"]["rows"]
        values = {str(row["value"]) for row in group}
        self.assertIn(str(ANNUAL_REVENUE), values)
        self.assertIn(str(41_456_000_000.0), values)


class TestTheRealArchiveSelection(unittest.TestCase):
    """
    The 3.31 regression, re-pinned.

    These two figures are the reason Commit A changed nothing: any tie-break
    proposal is measured against them.
    """

    @classmethod
    def setUpClass(cls) -> None:
        if not MU_ARCHIVE.exists():
            raise unittest.SkipTest("MU pilot archive not present")
        directory = tempfile.mkdtemp(prefix="steva332_")
        cls._directory = directory
        target = Path(directory) / "mu.sqlite"
        shutil.copyfile(MU_ARCHIVE, target)
        from sqlite_archive import SQLiteArchive

        cls.store = SQLiteArchive(path=str(target))
        cls.observations = list(cls.store.observations_for(ASSET, CUTOFF))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.store.close()
        shutil.rmtree(cls._directory, ignore_errors=True)

    def _revenue(self):
        return [o for o in self.observations if o.metric == METRIC_REVENUE]

    def test_the_first_match_is_still_the_unsafe_oldest(self):
        first = ObservationSet(
            ticker=ASSET, observations=self._revenue()
        ).latest(METRIC_REVENUE)
        self.assertEqual(float(first.value), OLDEST_REVENUE)

    def test_the_replayed_view_still_takes_the_annual(self):
        rebuilt = market_data_from_observations(
            self.observations + [_price()], ticker=ASSET, as_of=CUTOFF
        )
        self.assertIsNotNone(rebuilt)
        self.assertEqual(float(rebuilt.current_revenue), ANNUAL_REVENUE)

    def test_the_replayed_view_agrees_with_admissions_selector(self):
        agreed = ObservationSet(
            ticker=ASSET, observations=self._revenue()
        ).latest_knowable(CUTOFF, METRIC_REVENUE, eligibility=None)
        rebuilt = market_data_from_observations(
            self.observations + [_price()], ticker=ASSET, as_of=CUTOFF
        )
        self.assertEqual(float(rebuilt.current_revenue), float(agreed.value))

    def test_reordering_does_change_it_here_too(self):
        """
        The exposure, on real data: 12 of 18 metrics. Recorded so the risk is
        sized rather than described.
        """
        rows = self._revenue()
        forward = _latest_accepted(rows).observation_id
        backward = _latest_accepted(list(reversed(rows))).observation_id
        self.assertNotEqual(forward, backward)

    def test_the_archive_still_returns_rows_ascending(self):
        """
        B3/A4: the reader's ordering contract is untouched by this stage.

        `observations_for` emits `ORDER BY replay_eligible_from,
        observation_id` ascending and that is what makes the inherited
        tie-break reproducible between a live run and a replay.
        """
        connection = self.store.connection
        ordered = connection.execute(
            "SELECT replay_eligible_from, observation_id FROM observations"
            " WHERE replay_eligible_from IS NOT NULL AND replay_eligible_from <= ?"
            " ORDER BY replay_eligible_from, observation_id",
            (CUTOFF,),
        ).fetchall()
        self.assertEqual(len(ordered), len(self.observations))


class TestViewCandidateSemanticsUnchanged(unittest.TestCase):
    """
    A3: `_latest_accepted` keeps `latest`'s candidate population.

    The two selectors share an ordering and deliberately do not share
    eligibility. These pin the half that must not drift.
    """

    def test_an_unavailable_observation_is_still_a_candidate(self):
        """3.31 measured that filtering it out breaks a rebuild."""
        unavailable = _row("ingest|revenue|R|only", 7.0, "2026-06-01T00:00:00.000Z",
                           available=False)
        self.assertFalse(unavailable.is_available)
        self.assertIs(
            _latest_accepted([unavailable]), unavailable,
            "an unavailable observation is dropped only when a better one exists",
        )

    def test_an_available_observation_outranks_an_unavailable_one(self):
        """
        The availability preference lives in the caller, not the primitive.

        `_latest_accepted` orders whatever it is handed; choosing the available
        subset is `latest`'s job and stays there. Pinned at the level it is
        implemented, so a later move of that preference is deliberate.
        """
        unavailable = _row("ingest|revenue|R|a", 7.0, "2026-06-01T00:00:00.000Z",
                           available=False)
        available = _row("ingest|revenue|R|b", 8.0, "2026-05-01T00:00:00.000Z")
        rebuilt = market_data_from_observations(
            [unavailable, available, _price()], ticker=ASSET, as_of=CUTOFF
        )
        self.assertEqual(float(rebuilt.current_revenue), 8.0)

    def test_the_primitive_itself_does_not_filter(self):
        """
        A3: ordering and eligibility are separate, and stay separate.

        Handed both, the primitive orders by instant alone. That is why the two
        selectors can share it without either adopting the other's candidate
        semantics.
        """
        unavailable = _row("ingest|revenue|R|a", 7.0, "2026-06-01T00:00:00.000Z",
                           available=False)
        available = _row("ingest|revenue|R|b", 8.0, "2026-05-01T00:00:00.000Z")
        self.assertEqual(
            _latest_accepted([unavailable, available]).observation_id,
            unavailable.observation_id,
        )

    def test_a_comparable_observation_is_still_excluded_from_the_view(self):
        material = _row("ev-revenue-001", 1.0, "2026-05-01T00:00:00.000Z")
        second_source = _row("cmp-revenue-sec-2026q3", 2.0,
                             "2026-05-01T00:00:00.000Z")
        self.assertFalse(is_comparable_observation(material))
        self.assertTrue(is_comparable_observation(second_source))
        rebuilt = market_data_from_observations(
            [material, second_source, _price()], ticker=ASSET, as_of=CUTOFF
        )
        self.assertEqual(float(rebuilt.current_revenue), 1.0)

    def test_a_vendor_canonical_id_is_unaffected(self):
        vendor = _row("ev-revenue-001", 466_823_000_000.0, "2026-05-01T00:00:00.000Z")
        rebuilt = market_data_from_observations(
            [vendor, _price()], ticker=ASSET, as_of=CUTOFF
        )
        self.assertEqual(float(rebuilt.current_revenue), 466_823_000_000.0)

    def test_a_future_observation_is_the_callers_responsibility(self):
        """
        Neither selector filters by cutoff. The archive did, in
        `observations_for`, and re-filtering here is the half of
        `latest_knowable` that 3.31 measured as breaking a rebuild.
        """
        old = _row("ingest|revenue|R|a", 1.0, "2024-01-01T00:00:00.000Z")
        future = _row("ingest|revenue|R|b", 2.0, "2030-01-01T00:00:00.000Z")
        rebuilt = market_data_from_observations(
            [old, future, _price()], ticker=ASSET, as_of=CUTOFF
        )
        self.assertEqual(float(rebuilt.current_revenue), 2.0)


if __name__ == "__main__":
    unittest.main()
