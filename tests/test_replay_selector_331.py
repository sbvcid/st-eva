"""
3.31 Commit B -- the replay view must be filled by the point-in-time selector.

`ObservationSet.latest` returns the first match in whatever order the caller
supplied. Over an archive's `ORDER BY replay_eligible_from` that is the *oldest*
eligible row. The MU pilot archive holds 298 `revenue` rows across 298 distinct
`ingest|*` contract ids, and the per-`contract_id` collapse in `observations_for`
that makes `latest` safe for canonical `ev-*` ids does not fire for them, so
first-match and newest-match are different rows.

Every measurement here is on that real archive, or on a fixture shaped exactly
like it. No test asserts a synthetic number as if it were measured: the two
values 1,402,000,000 and 78,959,000,000 are read out of the archive at run
time and compared, so the test cannot pass against a corpus that no longer
contains the case.
"""

import shutil
import sqlite3
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
from st_eva_runner import market_data_from_observations

H = (
    Path(__file__).resolve().parent.parent
    / "experiments"
    / "003-llm-evidence-retrieval"
    / "harness"
)
MU_ARCHIVE = H / "pilot-mu.sqlite"
ASSET = "MU"
CUTOFF = "2026-06-30"

# The two figures 3.29 measured, kept here as the shape of the case rather than
# as the assertion: `test_the_real_archive_flips_from_oldest_to_newest` reads
# both out of the archive and fails if either has moved.
OLDEST_REVENUE = 1_402_000_000.0
LATEST_REVENUE = 78_959_000_000.0


def mu_sandbox(test: unittest.TestCase) -> Path:
    directory = tempfile.mkdtemp(prefix="steva331b_")
    test.addCleanup(shutil.rmtree, directory, ignore_errors=True)
    target = Path(directory) / "mu.sqlite"
    shutil.copyfile(MU_ARCHIVE, target)
    return target


def rows_for(path: Path, as_of: str):
    """`observations_for` over a copy, with the archive's own ordering intact."""
    connection = sqlite3.connect("file:" + str(path) + "?mode=ro", uri=True)
    try:
        connection.row_factory = sqlite3.Row
        columns = [description[0] for description in connection.execute(
            "SELECT * FROM observations LIMIT 0"
        ).description]
        wanted = [
            "contract_id", "metric", "value_json", "unit", "currency",
            "currency_basis", "period_start", "period_end", "as_of",
            "available_at", "available_at_basis", "provider", "source_type",
            "source_url", "definition", "methodology", "retrieved_at",
        ]
        rows = connection.execute(
            "SELECT contract_id, replay_eligible_from FROM observations"
            " WHERE replay_eligible_from IS NOT NULL AND replay_eligible_from <= ?"
            " ORDER BY replay_eligible_from, observation_id",
            (as_of,),
        ).fetchall()
        newest = {}
        for row in rows:
            newest[row["contract_id"]] = row["contract_id"]
        out = []
        for contract_id in newest.values():
            record = connection.execute(
                "SELECT * FROM observations WHERE contract_id = ? LIMIT 1",
                (contract_id,),
            ).fetchone()
            raw = json_loads(record["raw_json"])
            out.append(Observation(
                observation_id=str(record["contract_id"]),
                metric=str(record["metric"]),
                value=json_loads(record["value_json"]),
                unit=record["unit"],
                currency=record["currency"],
                currency_basis=record["currency_basis"],
                period_start=record["period_start"],
                period_end=record["period_end"],
                as_of=record["as_of"],
                available_at=record["available_at"],
                available_at_basis=record["available_at_basis"],
                provider=str(record["provider"]),
                source_type=str(record["source_type"]),
                source_url=record["source_url"],
                definition=record["definition"] or "",
                methodology=record["methodology"] or "",
                retrieved_at=str(record["retrieved_at"]),
                raw=raw,
            ))
        self_ = out
        return self_
    finally:
        connection.close()


def json_loads(value):
    import json

    if value is None:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def price(available_at: str = "2026-06-30T20:00:00.000Z") -> Observation:
    return Observation(
        observation_id="ev-price-001",
        metric="price",
        value=425.50,
        unit=Unit.CURRENCY.value,
        currency="USD",
        currency_basis="REPORTED",
        period_start=None,
        period_end="2026-06-30",
        as_of="2026-06-30",
        available_at=available_at,
        available_at_basis=AvailabilityBasis.OBSERVATION_INSTANT.value,
        provider="RegressionFixture",
        source_type=SourceType.REGRESSION_FIXTURE.value,
        source_url=None,
        definition="Observed current or latest market price.",
        methodology="static regression fixture",
        retrieved_at="2026-06-30T21:00:00+00:00",
        raw={"regular_market_price": 425.50},
        status=ValidationStatus.SINGLE_SOURCE,
    )


class TestTheHazardIsReal(unittest.TestCase):
    """The premise. Without these the fix below would prove nothing."""

    def test_the_real_archive_flips_from_oldest_to_newest(self):
        if not MU_ARCHIVE.exists():
            self.skipTest("MU pilot archive not present")
        observations = rows_for(mu_sandbox(self), CUTOFF)
        revenue = [o for o in observations if o.metric == METRIC_REVENUE]
        self.assertGreater(
            len(revenue), 1,
            "the archive must hold competing revenue rows or the case is void",
        )

        unsafe = ObservationSet(ticker=ASSET, observations=revenue).latest(
            METRIC_REVENUE
        )
        correct = ObservationSet(ticker=ASSET, observations=revenue).latest_knowable(
            CUTOFF, METRIC_REVENUE, eligibility=None
        )
        self.assertIsNotNone(unsafe)
        self.assertIsNotNone(correct)
        self.assertNotEqual(
            unsafe.observation_id, correct.observation_id,
            "first-match and newest must differ, or there is no hazard",
        )
        self.assertEqual(float(unsafe.value), OLDEST_REVENUE)
        self.assertEqual(float(correct.value), LATEST_REVENUE)
        self.assertGreater(float(correct.value), float(unsafe.value))

    def test_every_revenue_row_is_an_ingest_id_not_a_canonical_one(self):
        """
        Why the per-`contract_id` collapse does not protect these rows.

        `observations_for` keeps one row per `contract_id`, which is what makes
        first-match safe for a canonical `ev-<metric>-001`. SEC ingest mints an
        id per *fact*, so every row survives the collapse and `[0]` is free to
        be the oldest.
        """
        if not MU_ARCHIVE.exists():
            self.skipTest("MU pilot archive not present")
        observations = rows_for(mu_sandbox(self), CUTOFF)
        revenue = [o for o in observations if o.metric == METRIC_REVENUE]
        self.assertTrue(
            all(o.observation_id.startswith("ingest|") for o in revenue)
        )
        self.assertEqual(
            len(revenue), len({o.observation_id for o in revenue}),
            "these ids are distinct, so the collapse cannot reduce them",
        )
        self.assertFalse(any(is_comparable_observation(o) for o in revenue))


class TestTheProductionPathUsesThePointInTimeSelector(unittest.TestCase):
    """
    B4: the production path must reach the correct figure, and must reach it by
    selection rather than by a side effect of ordering.
    """

    def _rebuilt(self, as_of):
        observations = rows_for(mu_sandbox(self), as_of)
        return market_data_from_observations(
            observations + [price()], ticker=ASSET, as_of=as_of
        )

    def test_the_replayed_view_carries_the_fact_admission_would_select(self):
        if not MU_ARCHIVE.exists():
            self.skipTest("MU pilot archive not present")
        rebuilt = self._rebuilt(CUTOFF)
        self.assertIsNotNone(rebuilt, "the view needs a price observation")
        self.assertEqual(
            float(rebuilt.current_revenue), LATEST_REVENUE,
            "the replayed engine input is the newest knowable revenue fact",
        )

    def test_the_selection_is_the_newest_accepted_instant(self):
        """
        What the contract guarantees is the newest *accepted* instant, and the
        production path reaches it.

        Deliberately not asserted as value-equality across a reordering. On this
        archive 298 revenue rows share only 65 distinct `available_at` values --
        one filing reports an annual, three quarters and year-to-date figures,
        and they all become knowable at the same acceptance instant -- so the
        selection is almost always a tie on `available_at`, and the contract's
        selector breaks that tie with `as_of` and then with the order it was
        given. Reordering the input can therefore move the value.

        That is a property of `latest_knowable`, which this commit does not
        touch because rules 9 and 10 of admission depend on it. It is recorded
        here so it is not rediscovered as a replay divergence later.
        """
        if not MU_ARCHIVE.exists():
            self.skipTest("MU pilot archive not present")
        observations = rows_for(mu_sandbox(self), CUTOFF)
        rebuilt = market_data_from_observations(
            observations + [price()], ticker=ASSET, as_of=CUTOFF
        )
        self.assertIsNotNone(rebuilt)
        newest = ObservationSet(ticker=ASSET, observations=observations)
        expected = newest.latest_knowable(CUTOFF, METRIC_REVENUE, eligibility=None)
        self.assertEqual(
            float(rebuilt.current_revenue), float(expected.value),
            "the production path must use the contract's selector verbatim",
        )
        self.assertEqual(
            expected.available_at,
            max(o.available_at or "" for o in observations
                if o.metric == METRIC_REVENUE),
        )

    def test_the_tie_breaker_is_input_order_and_is_known(self):
        """
        Pins the boundary rather than asserting a fix.

        Two candidates accepted at the same instant are separated by input
        order, because `latest_knowable` sorts on `(available_at, as_of)` and
        Python's sort is stable. This is why the archive's own
        `ORDER BY replay_eligible_from, observation_id` is load-bearing: it is
        what makes the tie-break reproducible between a live run and a replay.
        Changing it is not this commit's business, and this test is here so a
        future change to the selector is a deliberate one.
        """
        early = _row("ingest|revenue|A", 100.0, "2020-04-30")
        late = _row("ingest|revenue|B", 200.0, "2020-04-30")
        observation_set = ObservationSet(ticker=ASSET, observations=[early, late])
        self.assertEqual(
            observation_set.latest_knowable(
                CUTOFF, METRIC_REVENUE, eligibility=None
            ).observation_id,
            late.observation_id,
        )
        reversed_set = ObservationSet(ticker=ASSET, observations=[late, early])
        self.assertEqual(
            reversed_set.latest_knowable(
                CUTOFF, METRIC_REVENUE, eligibility=None
            ).observation_id,
            early.observation_id,
        )


class TestPointInTimeBehaviour(unittest.TestCase):
    """
    The B4 cases, on a fixture shaped like the archive.

    `market_data_from_observations` does not filter by cutoff -- the archive
    already did, via `observations_for(asset, as_of)`, and re-filtering here is
    the half of `latest_knowable` that breaks a rebuild. So these tests supply
    the rows the archive *would* have returned, which is what the real call path
    does. `test_the_cutoff_is_applied_by_the_archive_not_here` pins that
    division rather than leaving it as an assumption.
    """

    def setUp(self) -> None:
        self.rows = [
            _row("ingest|revenue|A|2020-01-01|2020-03-31|USD", 100.0,
                 "2020-04-30"),
            _row("ingest|revenue|B|2021-01-01|2021-03-31|USD", 200.0,
                 "2021-04-30"),
            _row("ingest|revenue|C|2022-01-01|2022-03-31|USD", 300.0,
                 "2022-04-30"),
        ]

    def _eligible(self, as_of: str) -> list:
        """The rows the archive returns at `as_of`."""
        return [
            row for row in self.rows
            if (row.available_at or "") <= f"{as_of}T23:59:59.999Z"
        ]

    def _revenue(self, as_of: str):
        rebuilt = market_data_from_observations(
            self._eligible(as_of) + [price(f"{as_of}T20:00:00.000Z")],
            ticker=ASSET, as_of=as_of,
        )
        return None if rebuilt is None else float(rebuilt.current_revenue)

    def test_a_future_observation_is_excluded(self):
        self.assertEqual(self._revenue("2021-06-30"), 200.0)

    def test_a_stale_but_knowable_observation_still_counts(self):
        """Aware-but-old is knowable; only unawareness excludes."""
        self.assertEqual(self._revenue("2024-06-30"), 300.0)

    def test_the_latest_accepted_wins_when_several_are_knowable(self):
        self.assertEqual(self._revenue("2023-06-30"), 300.0)

    def test_the_oldest_is_never_chosen_when_a_newer_one_exists(self):
        """
        The defect itself, in miniature.

        All three rows are eligible, so the archive would return all three in
        ascending order. The first of them is 100.0; the answer must not be it.
        """
        rebuilt = market_data_from_observations(
            self.rows + [price()], ticker=ASSET, as_of=CUTOFF
        )
        self.assertIsNotNone(rebuilt)
        self.assertEqual(float(rebuilt.current_revenue), 300.0)
        self.assertNotEqual(float(rebuilt.current_revenue), 100.0)

    def test_the_cutoff_is_applied_by_the_archive_not_here(self):
        """
        Passing ineligible rows is a caller error, and this documents it.

        Without the archive's own filter the newest row wins regardless of the
        cutoff. That is deliberate: re-filtering here would drop undated and
        unavailable rows, which are exactly the rows a rebuild must be able to
        read back.
        """
        rebuilt = market_data_from_observations(
            self.rows + [price()], ticker=ASSET, as_of="2021-06-30"
        )
        self.assertEqual(float(rebuilt.current_revenue), 300.0)

    def test_no_observation_yet_known_leaves_the_field_unavailable(self):
        rebuilt = market_data_from_observations(
            self._eligible("2019-06-30") + [price("2019-06-30T20:00:00.000Z")],
            ticker=ASSET, as_of="2019-06-30",
        )
        self.assertIsNotNone(rebuilt)
        self.assertNotIsInstance(rebuilt.current_revenue, float)

    def test_multiple_contract_ids_are_the_normal_case_not_an_edge_case(self):
        rebuilt = market_data_from_observations(
            self.rows + [price()], ticker=ASSET, as_of=CUTOFF
        )
        self.assertEqual(float(rebuilt.current_revenue), 300.0)
        self.assertGreater(len(self.rows), 1)


class TestUnaffectedPaths(unittest.TestCase):
    """B5: vendor, price and comparable behaviour must not move."""

    def test_a_canonical_vendor_id_is_unaffected_by_the_cutoff(self):
        canonical = _row("ev-revenue-001", 466_823_000_000.0, "2026-06-30")
        rebuilt = market_data_from_observations(
            [canonical, price()], ticker=ASSET, as_of=CUTOFF
        )
        self.assertIsNotNone(rebuilt)
        self.assertEqual(float(rebuilt.current_revenue), 466_823_000_000.0)

    def test_a_comparable_observation_still_cannot_reach_the_view(self):
        canonical = _row("ev-revenue-001", 100.0, "2026-06-30")
        second_source = _row("cmp-revenue-sec-2026q3", 999.0, "2026-06-30")
        rebuilt = market_data_from_observations(
            [canonical, second_source, price()], ticker=ASSET, as_of=CUTOFF
        )
        self.assertIsNotNone(rebuilt)
        self.assertEqual(float(rebuilt.current_revenue), 100.0)

    def test_without_a_cutoff_the_first_match_read_is_kept(self):
        """
        The live paths have no cutoff and keep their existing behaviour, because
        canonical ids leave one row per metric there. This pins that choice so a
        later change to it is deliberate.
        """
        first = _row("ingest|revenue|A", 100.0, "2020-04-30")
        second = _row("ingest|revenue|B", 200.0, "2021-04-30")
        rebuilt = market_data_from_observations(
            [first, second, price()], ticker=ASSET
        )
        self.assertIsNotNone(rebuilt)
        self.assertEqual(float(rebuilt.current_revenue), 100.0)

    def test_a_view_without_a_price_is_still_refused(self):
        rebuilt = market_data_from_observations(
            self.__class__._row_only(), ticker=ASSET, as_of=CUTOFF
        )
        self.assertIsNone(rebuilt)

    @staticmethod
    def _row_only():
        return [_row("ingest|revenue|A", 100.0, "2020-04-30")]


def _row(observation_id, value, available_at):
    return Observation(
        observation_id=observation_id,
        metric=METRIC_REVENUE,
        value=value,
        unit=Unit.CURRENCY.value,
        currency="USD",
        currency_basis="REPORTED",
        period_start="2020-01-01",
        period_end="2020-03-31",
        as_of="2020-03-31",
        available_at=available_at,
        available_at_basis=AvailabilityBasis.ACCEPTANCE_DATETIME.value,
        provider="SecEdgar",
        source_type=SourceType.REGULATORY_FILING.value,
        source_url=None,
        definition="Revenue as filed.",
        methodology="us-gaap:Revenue",
        retrieved_at="2026-06-30T21:00:00+00:00",
        raw={},
        status=ValidationStatus.UNVERIFIABLE,
    )


if __name__ == "__main__":
    unittest.main()
