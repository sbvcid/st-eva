"""
3.19: the V1 crossing from archived SEC evidence into reverse valuation.

These tests run without a network, without a live collection, and without any
corpus. They build a temporary `SQLiteArchive`, seed the real registry into it, and
record filing-sourced revenue the way `Ingestor._observation` does -- one
`FilingRef` per filing, one row per accession, `basis.mapping_fidelity` on the
observation. The concepts and windows used are the registry's own, so a mapping
this test relies on is a mapping the project actually holds.

`IntegrationTests` is the class that matters most. It runs the admitted revenue
into `MarketImpliedAssumptionsEngine` and pins what does *not* change: no implied
figure becomes SEC-derived. `revenue_at_reference_multiple` is `market_cap /
selected_ps` and reads no revenue at all, so a filing-sourced revenue is invisible
to it. A test that asserted otherwise would be asserting a financial claim the
engine does not make.
"""

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from archive import (
    ARCHIVE_FIRST_SEEN,
    SOURCE_DECLARED,
    UNDECLARED,
    FilingRef,
)
from core_registry import CoreRegistry
from data_contract import (
    METRIC_PRICE,
    METRIC_REVENUE,
    UNAVAILABLE,
    AvailabilityBasis,
    Observation,
    SourceType,
    Unit,
    ValidationStatus,
)
from evidence_valuation_boundary import (
    AVAILABILITY_UNDECLARED,
    CONCEPT_AMBIGUOUS,
    CURRENCY_MISMATCH,
    CURRENCY_UNDECLARED,
    MAPPING_NOT_EXACT,
    METRIC_NOT_IN_V1_SCOPE,
    NOT_KNOWABLE_AT_AS_OF,
    PERIOD_NOT_DISCRETE,
    AMBIGUITY_RAISED,
    REFUSAL_LABELS,
    UNAVAILABLE,
    UNIT_NOT_MONETARY,
    V1_CROSSING_METRICS,
    ValuationAdmissionError,
    admit,
    build_valuation_inputs,
)
from registry_seed import seed
from sqlite_archive import SQLiteArchive
from st_eva_runner import MarketImpliedAssumptionsEngine

TICKER = "MU"

ACCEPTED = AvailabilityBasis.ACCEPTANCE_DATETIME.value
FILED_DATE = AvailabilityBasis.FILED_AS_OF_DATE.value

# The registry's own two revenue concepts, with the windows it really holds.
# `RevenueFromContractWithCustomerExcludingAssessedTax` is EXACT from 2017-09-30;
# `SalesRevenueNet` is PARTIAL over 2007-09-29..2018-06-30. MU reports both, so
# 2017-08-27..2017-11-26 is genuinely contested and 2015-10-17..2016-01-16 is
# reachable only through the PARTIAL claim. Neither window is invented here.
EXACT_CONCEPT = "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"
PARTIAL_CONCEPT = "us-gaap:SalesRevenueNet"
EPS_CONCEPT = "us-gaap:EarningsPerShareDiluted"

# MU's Q3 FY2026 shape, so the durations are the ones the pilot measured.
QUARTER = ("2026-02-27", "2026-05-28")
ANNUAL = ("2024-08-31", "2025-08-30")
YTD = ("2025-08-29", "2026-05-28")
PARTIAL_ONLY_QUARTER = ("2015-10-17", "2016-01-16")
CONTESTED_QUARTER = ("2017-08-27", "2017-11-26")

QUARTER_VALUE = 41_456_000_000
YTD_VALUE = 78_959_000_000
RESTATED_VALUE = 40_900_000_000
MARKET_CAP = 1_900_000_000_000
PRICE = 425.50


def filing_observation(
    metric: str,
    concept: str,
    value,
    period,
    available_at: str,
    available_at_basis: str,
    *,
    accession: str,
    unit: str = Unit.CURRENCY.value,
    currency: str = "USD",
    fidelity: str = "EXACT",
    form: str = "10-Q",
    fiscal_year: int = 2026,
    fiscal_period: str = "Q3",
    retrieved_at: str = "2026-09-29T12:00:00+00:00",
    instant: bool = False,
) -> Observation:
    """
    One SEC fact, shaped the way `Ingestor._observation` shapes it.

    The observation id carries the accession, which is what makes two filings of
    one period two facts rather than a collision: `observation_content_hash`
    includes it, and `sec_ingest.py:1452` builds the id the same way.
    """
    start, end = period
    taxonomy, _, tag = concept.rpartition(":")
    return Observation(
        observation_id=f"ingest|{metric}|{tag}|{accession}|{start}|{end}|{unit}",
        metric=metric,
        value=value,
        unit=unit,
        currency=currency,
        currency_basis="REPORTED" if currency else "NOT_APPLICABLE",
        period_start=None if instant else start,
        period_end=end,
        as_of=end,
        available_at=available_at,
        available_at_basis=available_at_basis,
        provider="SecEdgar",
        source_type=SourceType.REGULATORY_FILING.value,
        source_url=None,
        definition=f"{metric} definition",
        methodology=f"{taxonomy}:{tag} as filed in {form} accession {accession}",
        retrieved_at=retrieved_at,
        raw={
            "sec_fact": {
                "taxonomy": taxonomy,
                "tag": tag,
                "accession": accession,
                "form": form,
                "fy": fiscal_year,
                "fp": fiscal_period,
            },
            "mapping_type": fidelity,
        },
        status=ValidationStatus.UNVERIFIABLE,
        status_reasons=(
            "a single official source cannot cross-validate itself",
        ),
        basis={
            "reporting_framework": taxonomy,
            "security_type": "REGISTERED_SECURITY",
            "mapping_fidelity": fidelity,
            "source_declared": True,
        },
    )


def price_observation(currency: str = "USD") -> Observation:
    """The valuation-side price, which V1 never derives and never supplies."""
    return Observation(
        observation_id="ev-price-001",
        metric=METRIC_PRICE,
        value=PRICE,
        unit=Unit.CURRENCY.value,
        currency=currency,
        currency_basis="REPORTED" if currency else "NOT_APPLICABLE",
        period_start=None,
        period_end="2026-09-28",
        as_of="2026-09-28",
        available_at="2026-09-28T20:00:00.000Z",
        available_at_basis=AvailabilityBasis.OBSERVATION_INSTANT.value,
        provider="RegressionFixture",
        source_type=SourceType.REGRESSION_FIXTURE.value,
        source_url=None,
        definition="Observed current or latest market price.",
        methodology="static regression fixture",
        retrieved_at="2026-09-29T12:00:00+00:00",
        raw={"regular_market_price": PRICE},
        status=ValidationStatus.SINGLE_SOURCE,
    )


class BoundaryFixture(unittest.TestCase):
    """A temporary archive with the real registry seeded into it."""

    archive_unknown_availability = True

    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.store = SQLiteArchive(
            path=str(Path(self._directory.name) / "boundary.sqlite"),
            archive_unknown_availability=self.archive_unknown_availability,
        )
        seed(CoreRegistry(self.store.connection))
        self.store.record_asset(
            TICKER, name="Micron Technology", exchange="NASDAQ", currency="USD"
        )
        self._accession_serial = 0

    def tearDown(self) -> None:
        self.store.close()
        self._directory.cleanup()

    def record(self, observation: Observation) -> None:
        fact = observation.raw["sec_fact"]
        # `source_fact_id` is unique, and one filing holds many facts, so it is
        # keyed on the fact rather than on the accession. Without the value in the
        # key a single filing reporting one measure twice would collide, which is
        # the shape the dimension-collision test needs to build.
        self.store.record_observation(
            TICKER,
            observation,
            first_archived_at="2026-09-29T11:00:00+00:00",
            filing=FilingRef(
                accession=fact["accession"],
                form=fact["form"],
                taxonomy=fact["taxonomy"],
                fiscal_year=fact["fy"],
                fiscal_period=fact["fp"],
                instant=1 if observation.period_start is None else 0,
                source_fact_id=f"sf-{observation.observation_id}-{observation.value}",
                source_concept=f"{fact['taxonomy']}:{fact['tag']}",
            ),
        )

    def next_accession(self) -> str:
        self._accession_serial += 1
        return f"0000723125-26-{self._accession_serial:06d}"

    def add_revenue(
        self,
        *,
        concept: str = EXACT_CONCEPT,
        value=QUARTER_VALUE,
        period=QUARTER,
        available_at: str = "2026-06-24T22:59:46.000Z",
        available_at_basis: str = ACCEPTED,
        unit: str = Unit.CURRENCY.value,
        currency: str = "USD",
        fidelity: str = "EXACT",
        form: str = "10-Q",
        fiscal_year: int = 2026,
        fiscal_period: str = "Q3",
        retrieved_at: str = "2026-09-29T12:00:00+00:00",
        instant: bool = False,
        accession: str = None,
    ) -> Observation:
        observation = filing_observation(
            METRIC_REVENUE,
            concept,
            value,
            period,
            available_at,
            available_at_basis,
            accession=accession or self.next_accession(),
            unit=unit,
            currency=currency,
            fidelity=fidelity,
            form=form,
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
            retrieved_at=retrieved_at,
            instant=instant,
        )
        self.record(observation)
        return observation

    def admit_revenue(self, as_of: str = "2026-09-29", **kwargs):
        return admit(self.store, TICKER, as_of, price_observation(), **kwargs)


class ScopeAndExistenceTests(BoundaryFixture):
    """Rules 1 and 2: the scope comes from the registry, and absence is a refusal."""

    def test_v1_scope_is_one_metric_and_comes_from_the_contract(self):
        self.assertEqual(V1_CROSSING_METRICS, (METRIC_REVENUE,))
        self.assertEqual(V1_CROSSING_METRICS[0], "revenue")

    def test_the_registry_agrees_that_revenue_is_a_monetary_duration_metric(self):
        entry = CoreRegistry(self.store.connection).metric(METRIC_REVENUE)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.status, "ACTIVE")
        self.assertEqual(entry.unit_family, "currency")
        self.assertEqual(entry.normal_period_type, "DURATION")

    def test_the_registry_really_does_map_both_test_concepts_as_expected(self):
        """The fixtures below depend on these windows, so they are asserted."""
        registry = CoreRegistry(self.store.connection)
        exact = [
            mapping
            for mapping in registry.mappings_for_metric(
                METRIC_REVENUE, as_of=QUARTER[1]
            )
            if mapping.concept_id == EXACT_CONCEPT
        ]
        partial = [
            mapping
            for mapping in registry.mappings_for_metric(
                METRIC_REVENUE, as_of=PARTIAL_ONLY_QUARTER[1]
            )
            if mapping.concept_id == PARTIAL_CONCEPT
        ]
        self.assertEqual([m.mapping_type for m in exact], ["EXACT"])
        self.assertEqual([m.mapping_type for m in partial], ["PARTIAL"])

    def test_an_out_of_scope_metric_is_refused_by_name(self):
        self.add_revenue()
        inputs, admissions = self.admit_revenue(metrics=("eps_diluted",))
        self.assertEqual(len(admissions), 1)
        self.assertFalse(admissions[0].admitted)
        self.assertEqual(admissions[0].refusal_labels, (METRIC_NOT_IN_V1_SCOPE,))
        self.assertEqual(inputs.current_revenue, UNAVAILABLE)

    def test_a_filed_eps_in_the_archive_is_not_a_revenue_candidate(self):
        self.record(
            filing_observation(
                "eps_diluted",
                EPS_CONCEPT,
                2.34,
                QUARTER,
                "2026-06-24T22:59:46.000Z",
                ACCEPTED,
                accession="0000723125-26-000900",
                unit=Unit.PER_SHARE.value,
            )
        )
        self.add_revenue()
        _, admissions = self.admit_revenue()
        self.assertTrue(admissions[0].admitted)
        self.assertEqual(admissions[0].considered_observations, 1)

    def test_no_observation_at_all_is_unavailable_not_zero(self):
        inputs, admissions = self.admit_revenue()
        self.assertFalse(admissions[0].admitted)
        self.assertEqual(admissions[0].refusal_labels, (UNAVAILABLE,))
        self.assertEqual(inputs.current_revenue, UNAVAILABLE)


class AdmittedRevenueTests(BoundaryFixture):
    """The admitted case, and the provenance it has to carry."""

    def test_a_valid_exact_revenue_quarter_is_admitted(self):
        self.add_revenue()
        inputs, admissions = self.admit_revenue()
        admitted = admissions[0]
        self.assertTrue(admitted.admitted)
        self.assertEqual(admitted.refusals, ())
        self.assertEqual(inputs.current_revenue, QUARTER_VALUE)
        self.assertEqual(admitted.metric, METRIC_REVENUE)
        self.assertEqual(admitted.value, QUARTER_VALUE)
        self.assertEqual(admitted.unit, "currency")
        self.assertEqual(admitted.currency, "USD")
        self.assertEqual(admitted.currency_basis, "REPORTED")
        self.assertEqual(admitted.period_start, QUARTER[0])
        self.assertEqual(admitted.period_end, QUARTER[1])
        self.assertEqual(admitted.duration_days, 90)
        self.assertEqual(admitted.mapping_type, "EXACT")
        self.assertEqual(admitted.relation_kind, "IDENTITY")
        self.assertEqual(admitted.mapping_fidelity, "EXACT")
        self.assertEqual(admitted.form, "10-Q")
        self.assertEqual(admitted.fiscal_year, 2026)
        self.assertEqual(admitted.fiscal_period, "Q3")
        self.assertEqual(admitted.availability_class, SOURCE_DECLARED)
        self.assertEqual(admitted.available_at_basis, ACCEPTED)
        self.assertEqual(admitted.available_at, "2026-06-24T22:59:46.000Z")
        self.assertEqual(admitted.superseded_accessions, 0)
        self.assertFalse(admitted.value_diverges_from_superseded)

    def test_the_admission_names_the_fact_it_came_from(self):
        """metric -> concept -> accession -> source_fact_id must all be readable."""
        self.add_revenue()
        _, admissions = self.admit_revenue()
        admitted = admissions[0]
        self.assertTrue(admitted.admitted)
        self.assertTrue(admitted.observation_id.startswith("ingest|revenue|"))
        self.assertEqual(admitted.contract_id, admitted.observation_id)
        self.assertEqual(admitted.taxonomy, "us-gaap")
        self.assertEqual(admitted.concept, EXACT_CONCEPT)
        self.assertEqual(admitted.source_concept_ref, EXACT_CONCEPT)
        self.assertTrue(admitted.accession.startswith("0000723125-26-"))
        self.assertEqual(
            admitted.source_fact_id, f"sf-{admitted.observation_id}-{QUARTER_VALUE}"
        )
        self.assertIsNotNone(admitted.retrieved_at)

    def test_a_fiscal_year_is_admitted_too(self):
        """A 10-K period is a trailing figure the filer actually reported."""
        self.add_revenue(
            period=ANNUAL,
            form="10-K",
            fiscal_year=2025,
            fiscal_period="FY",
            available_at="2025-10-03T21:02:11.000Z",
        )
        _, admissions = self.admit_revenue()
        self.assertTrue(admissions[0].admitted)
        self.assertEqual(admissions[0].duration_days, 364)
        self.assertEqual(admissions[0].form, "10-K")

    def test_a_non_monetary_unit_is_refused(self):
        self.add_revenue(unit=Unit.COUNT.value)
        inputs, admissions = self.admit_revenue()
        self.assertFalse(admissions[0].admitted)
        self.assertIn(UNIT_NOT_MONETARY, admissions[0].refusal_labels)
        self.assertEqual(inputs.current_revenue, UNAVAILABLE)

    def test_an_undeclared_currency_is_refused_rather_than_assumed(self):
        self.add_revenue(currency="")
        _, admissions = self.admit_revenue()
        self.assertFalse(admissions[0].admitted)
        self.assertIn(CURRENCY_UNDECLARED, admissions[0].refusal_labels)


class ComparativeReReportTests(BoundaryFixture):
    """
    Rule 10: several filings of one period.

    Measured on the MU pilot, one `net_income` period is published by six
    accessions over eighteen months. The selector answers which one a reader at the
    instant would have most recently seen; the record has to answer what the others
    were.
    """

    def test_the_latest_known_accession_is_named_and_the_rest_are_counted(self):
        first = self.add_revenue()
        second = self.add_revenue(available_at="2026-07-15T21:04:05.000Z")
        _, admissions = self.admit_revenue()
        admitted = admissions[0]
        self.assertTrue(admitted.admitted)
        self.assertEqual(admitted.accession, second.raw["sec_fact"]["accession"])
        self.assertNotEqual(admitted.accession, first.raw["sec_fact"]["accession"])
        self.assertEqual(admitted.superseded_accessions, 1)
        self.assertEqual(admitted.considered_observations, 2)
        self.assertFalse(admitted.value_diverges_from_superseded)

    def test_selection_is_point_in_time_and_not_merely_newest(self):
        first = self.add_revenue()
        self.add_revenue(available_at="2026-07-15T21:04:05.000Z")
        _, earlier = self.admit_revenue(as_of="2026-07-01")
        self.assertTrue(earlier[0].admitted)
        self.assertEqual(
            earlier[0].accession, first.raw["sec_fact"]["accession"]
        )
        self.assertEqual(earlier[0].superseded_accessions, 0)

    def test_a_restated_value_is_disclosed_and_not_erased(self):
        self.add_revenue(value=QUARTER_VALUE)
        self.add_revenue(
            value=RESTATED_VALUE, available_at="2026-08-01T20:00:00.000Z"
        )
        inputs, admissions = self.admit_revenue()
        admitted = admissions[0]
        self.assertTrue(admitted.admitted)
        self.assertEqual(inputs.current_revenue, RESTATED_VALUE)
        self.assertEqual(admitted.superseded_accessions, 1)
        self.assertEqual(admitted.superseded_values, (float(QUARTER_VALUE),))
        self.assertTrue(admitted.value_diverges_from_superseded)
        self.assertTrue(admitted.contract_dict()["value_diverges_from_superseded"])

    def test_a_disclosure_is_a_field_and_not_a_new_state(self):
        self.add_revenue(value=QUARTER_VALUE)
        self.add_revenue(
            value=RESTATED_VALUE, available_at="2026-08-01T20:00:00.000Z"
        )
        _, admissions = self.admit_revenue()
        admitted = admissions[0]
        self.assertTrue(admitted.admitted)
        self.assertEqual(admitted.refusals, ())
        for label in admitted.refusal_labels:
            self.assertIn(label, REFUSAL_LABELS)


class MappingAndConceptTests(BoundaryFixture):
    """Rules 5 and 6: the PARTIAL claim, and the contested period."""

    def test_a_partial_mapping_is_refused_even_on_its_own_window(self):
        self.add_revenue(
            concept=PARTIAL_CONCEPT,
            period=PARTIAL_ONLY_QUARTER,
            fidelity="PARTIAL",
            fiscal_year=2016,
            fiscal_period="Q1",
            available_at="2016-02-02T21:03:44.000Z",
        )
        _, admissions = self.admit_revenue()
        admitted = admissions[0]
        self.assertFalse(admitted.admitted)
        self.assertEqual(admitted.refusal_labels, (MAPPING_NOT_EXACT,))
        self.assertIn("PARTIAL", admitted.refusals[0].reason)

    def test_a_contested_period_is_refused_though_one_claim_is_exact(self):
        """
        MU's real shape: two concepts report the same period, one EXACT and one
        PARTIAL. The EXACT row passes rule 5 on its own and rule 6 still refuses,
        because the evidence has not established which figure the question was
        asking for. This is the case the crossing exists to catch.
        """
        self.add_revenue(
            concept=PARTIAL_CONCEPT,
            period=CONTESTED_QUARTER,
            fidelity="PARTIAL",
            fiscal_year=2018,
            fiscal_period="Q1",
            available_at="2018-01-30T21:05:12.000Z",
        )
        self.add_revenue(
            concept=EXACT_CONCEPT,
            period=CONTESTED_QUARTER,
            fiscal_year=2018,
            fiscal_period="Q1",
            available_at="2018-01-30T21:05:12.000Z",
        )
        _, admissions = self.admit_revenue()
        admitted = admissions[0]
        self.assertFalse(admitted.admitted)
        self.assertEqual(admitted.refusal_labels, (CONCEPT_AMBIGUOUS,))
        self.assertIn(EXACT_CONCEPT, admitted.refusals[0].reason)
        self.assertIn(PARTIAL_CONCEPT, admitted.refusals[0].reason)
        self.assertEqual(
            admitted.competing_concepts, (EXACT_CONCEPT, PARTIAL_CONCEPT)
        )

    def test_one_filings_two_reports_of_a_measure_collapse_before_the_crossing(self):
        """
        A measured limitation, and the reason `AMBIGUITY_RAISED` is barely reachable.

        One concept, one filing, one period, reported twice is the shape
        `EvidenceQuery` calls a dimension collision. It cannot reach the crossing,
        because `SQLiteArchive.observations_for` collapses on `contract_id` and
        `sec_ingest` builds that id from `metric|concept|accession|period|unit` --
        with no value and no dimension in it. The archive merges the two facts
        before admission runs, keeping whichever sorts last by
        `(replay_eligible_from, observation_id)`.

        So the surviving row is admitted on its own merits, and nothing in the
        admission record can disclose that a sibling figure existed. That is
        pre-existing archive behaviour, inherited identically by the existing
        replay path, and the crossing does not change it -- but a reader of this
        record should know that `superseded_accessions == 0` does not prove the
        filing reported the measure once.
        """
        self.add_revenue(
            value=QUARTER_VALUE, accession="0000723125-26-000777"
        )
        self.add_revenue(
            value=QUARTER_VALUE * 3,
            available_at="2026-06-24T22:59:47.000Z",
            accession="0000723125-26-000777",
        )
        stored = self.store.connection.execute(
            "SELECT COUNT(*) FROM observations"
        ).fetchone()[0]
        self.assertEqual(stored, 2, "the archive stored both facts")
        self.assertEqual(
            len(self.store.observations_for(TICKER, "2026-09-29")),
            1,
            "but the object-level read returns one",
        )
        _, admissions = self.admit_revenue()
        self.assertTrue(admissions[0].admitted)
        self.assertEqual(admissions[0].superseded_accessions, 0)
        self.assertEqual(admissions[0].considered_observations, 1)

    def test_the_ambiguity_gate_refuses_a_dimension_aggregate_it_is_given(self):
        """
        The gate itself, which the collapse above keeps the archive from feeding.

        A private helper is tested here on purpose: it is the only way to cover the
        branch, and a branch that refuses a dimension aggregate must not be left
        unexercised merely because the current archive reader cannot produce its
        input. If a future read path stops collapsing, this test is the one that
        says the refusal is already there.
        """
        from evidence_valuation_boundary import _ambiguity_refusals

        first = filing_observation(
            METRIC_REVENUE,
            EXACT_CONCEPT,
            QUARTER_VALUE,
            QUARTER,
            "2026-06-24T22:59:46.000Z",
            ACCEPTED,
            accession="0000723125-26-000888",
        )
        second = replace(first, value=QUARTER_VALUE * 3)
        refusals = _ambiguity_refusals(
            [first, second],
            [EXACT_CONCEPT, EXACT_CONCEPT],
            [
                {"accession": "0000723125-26-000888"},
                {"accession": "0000723125-26-000888"},
            ],
        )
        self.assertEqual([r.label for r in refusals], [AMBIGUITY_RAISED])
        self.assertIn("DIMENSION_COLLISION", refusals[0].reason)

    def test_the_ambiguity_gate_ignores_the_ordinary_re_report_case(self):
        """`MULTIPLE_FILINGS` is rule 10's work, not a refusal."""
        from evidence_valuation_boundary import _ambiguity_refusals

        first = filing_observation(
            METRIC_REVENUE,
            EXACT_CONCEPT,
            QUARTER_VALUE,
            QUARTER,
            "2026-06-24T22:59:46.000Z",
            ACCEPTED,
            accession="0000723125-26-000889",
        )
        second = replace(first, value=RESTATED_VALUE)
        refusals = _ambiguity_refusals(
            [first, second],
            [EXACT_CONCEPT, EXACT_CONCEPT],
            [
                {"accession": "0000723125-26-000889"},
                {"accession": "0000723125-26-000990"},
            ],
        )
        self.assertEqual(refusals, [])

    def test_a_single_row_is_never_ambiguous(self):
        """The classifier answers `DIMENSION_COLLISION` for one accession."""
        from evidence_valuation_boundary import _ambiguity_refusals

        only = filing_observation(
            METRIC_REVENUE,
            EXACT_CONCEPT,
            QUARTER_VALUE,
            QUARTER,
            "2026-06-24T22:59:46.000Z",
            ACCEPTED,
            accession="0000723125-26-000991",
        )
        self.assertEqual(
            _ambiguity_refusals(
                [only],
                [EXACT_CONCEPT],
                [{"accession": "0000723125-26-000991"}],
            ),
            [],
        )


class PeriodTests(BoundaryFixture):
    """Rule 7: a filed period, never a trailing aggregate."""

    def test_a_cumulative_stub_is_refused(self):
        self.add_revenue(period=YTD, value=YTD_VALUE)
        _, admissions = self.admit_revenue()
        admitted = admissions[0]
        self.assertFalse(admitted.admitted)
        self.assertEqual(admitted.refusal_labels, (PERIOD_NOT_DISCRETE,))
        self.assertIn("272 days", admitted.refusals[0].reason)

    def test_a_stub_is_refused_without_a_nearest_period_search(self):
        """The valid quarter is chosen; the stub is never annualised or trimmed."""
        self.add_revenue(period=YTD, value=YTD_VALUE)
        self.add_revenue()
        inputs, admissions = self.admit_revenue()
        self.assertTrue(admissions[0].admitted)
        self.assertEqual(admissions[0].considered_observations, 2)
        self.assertEqual(inputs.current_revenue, QUARTER_VALUE)
        self.assertNotEqual(inputs.current_revenue, YTD_VALUE)

    def test_an_instant_candidate_is_discarded_while_a_valid_quarter_survives(
        self,
    ):
        """
        The record is per metric, not per candidate, so this can only establish
        that the instant did not survive selection -- not that it was refused with
        a named reason. What it does establish is that an instant never displaces
        a discrete quarter no matter how recently it was published.
        """
        self.add_revenue(instant=True)
        self.add_revenue()
        _, admissions = self.admit_revenue()
        self.assertTrue(admissions[0].admitted)
        self.assertEqual(admissions[0].duration_days, 90)
        self.assertEqual(admissions[0].considered_observations, 2)


class AvailabilityTests(BoundaryFixture):
    """Rules 8 and 9: a declared publication time, and the declared-date boundary."""

    def test_an_archive_first_seen_fact_is_refused(self):
        """
        Two refusals, and both are true.

        Rule 8 refuses because the class records when ST-EVA asked rather than
        when the filer published. Rule 9 refuses independently because the row
        declares no `available_at` at all, and the contract's own `knowable_at`
        cannot place a fact with an unknown publication time at any instant. The
        row *is* replay-eligible -- `observations_for` returns it, since the store
        made it eligible from the archival moment -- so this is the case where the
        store's eligibility and the contract's knowability disagree, and the
        stricter of the two answers.
        """
        observation = self.add_revenue(
            available_at=None, available_at_basis=AvailabilityBasis.UNDECLARED.value
        )
        self.assertEqual(
            self.store.availability_classes(TICKER)[observation.observation_id],
            ARCHIVE_FIRST_SEEN,
        )
        self.assertEqual(
            len(self.store.observations_for(TICKER, "2026-09-29")), 1
        )
        _, admissions = self.admit_revenue()
        admitted = admissions[0]
        self.assertFalse(admitted.admitted)
        self.assertEqual(
            admitted.refusal_labels,
            (AVAILABILITY_UNDECLARED, NOT_KNOWABLE_AT_AS_OF),
        )
        self.assertIn("archive-first-seen", admitted.refusals[0].reason)

    def test_a_fact_is_not_knowable_before_its_declared_date_boundary(self):
        self.add_revenue(
            available_at="2026-06-24", available_at_basis=FILED_DATE
        )
        _, early = self.admit_revenue(as_of="2026-06-25")
        self.assertFalse(early[0].admitted)
        self.assertEqual(early[0].refusal_labels, (UNAVAILABLE,))

    def test_a_fact_is_knowable_once_its_declared_date_is_over(self):
        """`eligibility_for_declared_date` is start of day plus the one-day lag."""
        self.add_revenue(
            available_at="2026-06-24", available_at_basis=FILED_DATE
        )
        _, admitted = self.admit_revenue(as_of="2026-06-26")
        self.assertTrue(admitted[0].admitted)
        self.assertEqual(admitted[0].availability_class, SOURCE_DECLARED)
        self.assertEqual(admitted[0].available_at_basis, FILED_DATE)

    def test_retrieval_time_is_never_the_cutoff(self):
        """A fact retrieved in December is judged by when it was published."""
        self.add_revenue(retrieved_at="2026-12-31T00:00:00+00:00")
        _, admissions = self.admit_revenue(as_of="2026-07-01")
        self.assertTrue(admissions[0].admitted)
        self.assertEqual(admissions[0].available_at, "2026-06-24T22:59:46.000Z")

    def test_the_record_reports_whether_a_knowledge_overlay_exists(self):
        self.add_revenue()
        _, admissions = self.admit_revenue()
        self.assertFalse(admissions[0].knowledge_overlay_available)


class PermanentlyIneligibleTests(BoundaryFixture):
    """A store that keeps undated facts UNDECLARED, and so never replays them."""

    archive_unknown_availability = False

    def test_an_undeclared_fact_is_never_replay_eligible(self):
        observation = self.add_revenue(
            available_at=None, available_at_basis=AvailabilityBasis.UNDECLARED.value
        )
        self.assertEqual(
            self.store.availability_classes(TICKER)[observation.observation_id],
            UNDECLARED,
        )
        self.assertEqual(
            self.store.eligibility_for(TICKER), {}
        )
        inputs, admissions = self.admit_revenue()
        self.assertFalse(admissions[0].admitted)
        self.assertEqual(admissions[0].refusal_labels, (UNAVAILABLE,))
        self.assertEqual(inputs.current_revenue, UNAVAILABLE)


class CurrencyTests(BoundaryFixture):
    """Rule 4: same declared currency, or nothing."""

    def test_a_mismatched_currency_is_refused(self):
        self.add_revenue(currency="TWD")
        inputs, admissions = self.admit_revenue()
        self.assertFalse(admissions[0].admitted)
        self.assertEqual(admissions[0].refusal_labels, (CURRENCY_MISMATCH,))
        self.assertEqual(inputs.current_revenue, UNAVAILABLE)

    def test_a_mismatched_price_currency_is_refused_too(self):
        self.add_revenue()
        _, admissions = admit(
            self.store, TICKER, "2026-09-29", price_observation(currency="EUR")
        )
        self.assertFalse(admissions[0].admitted)
        self.assertEqual(admissions[0].refusal_labels, (CURRENCY_MISMATCH,))


class PriceRefusalTests(BoundaryFixture):
    """A price is not an evidence question, and the adapter will not invent one."""

    def test_a_missing_price_stops_the_crossing_instead_of_producing_zero(self):
        self.add_revenue()
        with self.assertRaises(ValuationAdmissionError) as caught:
            admit(self.store, TICKER, "2026-09-29", None)
        self.assertIn("fabricate", str(caught.exception))

    def test_a_non_positive_price_stops_the_crossing(self):
        self.add_revenue()
        with self.assertRaises(ValuationAdmissionError):
            admit(
                self.store,
                TICKER,
                "2026-09-29",
                replace(price_observation(), value=0.0),
            )

    def test_a_price_carrying_the_wrong_metric_is_refused(self):
        with self.assertRaises(ValuationAdmissionError):
            admit(
                self.store,
                TICKER,
                "2026-09-29",
                replace(price_observation(), metric="not_price"),
            )


class IntegrationTests(BoundaryFixture):
    """observations_for -> adapter -> ValuationInputs -> the existing engine."""

    def test_the_admitted_revenue_reaches_the_valuation_inputs(self):
        self.add_revenue()
        result = build_valuation_inputs(
            self.store, TICKER, "2026-09-29", price_observation()
        )
        inputs = result.valuation_inputs
        self.assertEqual(inputs.price, PRICE)
        self.assertEqual(inputs.currency, "USD")
        self.assertEqual(inputs.current_revenue, QUARTER_VALUE)
        self.assertEqual(result.valuation_side_currency, "USD")
        self.assertEqual(result.asset, TICKER)
        self.assertEqual(result.as_of, "2026-09-29")
        self.assertEqual(list(result.admitted), [METRIC_REVENUE])
        self.assertEqual(result.refused, {})

    def test_every_other_field_stays_valuation_side(self):
        self.add_revenue()
        inputs, _ = self.admit_revenue()
        for name in (
            "current_eps",
            "forward_eps",
            "consensus_forward_eps",
            "current_fcf",
            "current_ebitda",
            "current_enterprise_value",
            "current_market_cap",
        ):
            self.assertEqual(getattr(inputs, name), UNAVAILABLE, name)
        for name in (
            "historical_pe_band",
            "historical_ps_band",
            "historical_pfcf_band",
            "historical_ev_ebitda_band",
        ):
            self.assertEqual(getattr(inputs, name), {}, name)

    def test_the_existing_engine_accepts_the_constructed_inputs(self):
        self.add_revenue()
        inputs, _ = self.admit_revenue()
        analysis = MarketImpliedAssumptionsEngine.analyze(
            inputs, reference_multiple=20.0
        )
        self.assertEqual(
            analysis["implied_assumptions"]["forward_eps_at_reference_multiple"],
            PRICE / 20.0,
        )

    def test_the_conventional_p_uses_the_filed_revenue(self):
        self.add_revenue()
        inputs, _ = self.admit_revenue()
        # `current_market_cap` is valuation-side and V1 does not supply it, so the
        # test does -- exactly as a caller would.
        priced = replace(inputs, current_market_cap=MARKET_CAP)
        analysis = MarketImpliedAssumptionsEngine.analyze(priced, ps_multiple=8.0)
        self.assertEqual(
            analysis["observed_valuation"]["current_ps"],
            MARKET_CAP / QUARTER_VALUE,
        )

    def test_injecting_sec_revenue_makes_no_reverse_output_sec_derived(self):
        """
        The load-bearing negative assertion.

        `revenue_at_reference_multiple` is `market_cap / selected_ps` and reads no
        revenue. `forward_eps_at_reference_multiple` is `price / selected_pe`. Both
        must be identical whether `current_revenue` holds a filed figure or is
        unavailable, and neither may be reported as SEC-derived.
        """
        self.add_revenue()
        inputs, _ = self.admit_revenue()
        with_revenue = replace(inputs, current_market_cap=MARKET_CAP)
        without_revenue = replace(with_revenue, current_revenue=UNAVAILABLE)
        arguments = {"reference_multiple": 20.0, "ps_multiple": 8.0}
        injected = MarketImpliedAssumptionsEngine.analyze(
            with_revenue, **arguments
        )
        absent = MarketImpliedAssumptionsEngine.analyze(
            without_revenue, **arguments
        )
        for key in (
            "forward_eps_at_reference_multiple",
            "revenue_at_reference_multiple",
            "ebitda_at_reference_multiple",
            "fcf_at_reference_multiple",
        ):
            self.assertEqual(
                injected["implied_assumptions"][key],
                absent["implied_assumptions"][key],
                key,
            )
        self.assertEqual(
            injected["observed_valuation"]["current_ps"],
            MARKET_CAP / QUARTER_VALUE,
        )
        self.assertIsNone(absent["observed_valuation"]["current_ps"])

    def test_a_refused_revenue_leaves_the_engine_output_unchanged(self):
        self.add_revenue(period=YTD, value=YTD_VALUE)
        inputs, admissions = self.admit_revenue()
        self.assertFalse(admissions[0].admitted)
        priced = replace(inputs, current_market_cap=MARKET_CAP)
        analysis = MarketImpliedAssumptionsEngine.analyze(
            priced, reference_multiple=20.0, ps_multiple=8.0
        )
        self.assertIsNone(analysis["observed_valuation"]["current_ps"])
        self.assertEqual(
            analysis["implied_assumptions"]["revenue_at_reference_multiple"],
            MARKET_CAP / 8.0,
        )
        self.assertEqual(analysis["fundamental_snapshot"]["current_revenue"],
                         UNAVAILABLE)

    def test_the_contract_dict_carries_the_whole_provenance_chain(self):
        self.add_revenue()
        document = build_valuation_inputs(
            self.store, TICKER, "2026-09-29", price_observation()
        ).contract_dict()
        self.assertEqual(document["crossing_metrics"], ["revenue"])
        admission = document["admissions"][0]
        for key in (
            "metric",
            "admitted",
            "observation_id",
            "contract_id",
            "source_fact_id",
            "accession",
            "taxonomy",
            "concept",
            "source_concept_ref",
            "mapping_type",
            "relation_kind",
            "period_start",
            "period_end",
            "duration_days",
            "fiscal_year",
            "fiscal_period",
            "form",
            "value",
            "unit",
            "currency",
            "currency_basis",
            "available_at",
            "available_at_basis",
            "availability_class",
            "retrieved_at",
            "considered_observations",
            "superseded_accessions",
            "refusals",
            "as_of",
        ):
            self.assertIn(key, admission, key)

    def test_nothing_in_the_record_claims_an_implied_figure_is_sec_derived(self):
        self.add_revenue()
        result = build_valuation_inputs(
            self.store, TICKER, "2026-09-29", price_observation()
        )
        admitted = result.admitted["revenue"]
        self.assertEqual(admitted.metric, METRIC_REVENUE)
        rendered = str(result.contract_dict())
        for forbidden in (
            "implied",
            "SEC-derived",
            "sec_derived",
            "trailing",
            "TTM",
        ):
            self.assertNotIn(forbidden, rendered, forbidden)

    def test_the_crossing_writes_nothing_to_the_archive(self):
        """
        A read is a read. `SQLiteArchive` exposes no write path from here, and
        `connection.total_changes` is the direct check: the archive is append-only
        by trigger, so a single increment would mean a fact was added to make a
        valuation input work.
        """
        self.add_revenue()
        before_changes = self.store.connection.total_changes
        before_rows = self.store.connection.execute(
            "SELECT COUNT(*) FROM observations"
        ).fetchone()[0]
        build_valuation_inputs(
            self.store, TICKER, "2026-09-29", price_observation()
        )
        self.assertEqual(self.store.connection.total_changes, before_changes)
        self.assertEqual(
            self.store.connection.execute(
                "SELECT COUNT(*) FROM observations"
            ).fetchone()[0],
            before_rows,
        )

    def test_the_crossing_does_not_reach_a_second_source(self):
        """
        The guard `test_sec_validation.py` applies to the engine, applied to the
        crossing. `cross_validation` and `sec_provider` are how a filing and a
        vendor figure get compared, and a valuation input built through either
        would inherit a comparison the engine is not allowed to make.

        Checked over the AST rather than the source text, because the module's
        docstrings cite both filenames as evidence for why the crossing refuses
        them, and a citation is not a dependency. A docstring is the only kind of
        string literal that is excluded.
        """
        import ast
        import inspect
        import textwrap

        import evidence_valuation_boundary as module

        tree = ast.parse(textwrap.dedent(inspect.getsource(module)))
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
                body = getattr(node, "body", None)
                if body and isinstance(body[0], ast.Expr):
                    value = body[0].value
                    if isinstance(value, ast.Constant) and isinstance(
                        value.value, str
                    ):
                        docstrings.add(id(value))

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name for alias in node.names]
                if isinstance(node, ast.ImportFrom) and node.module:
                    names.append(node.module)
                for name in names:
                    root = name.split(".")[0]
                    self.assertNotIn(
                        root,
                        ("cross_validation", "sec_provider"),
                        f"the crossing must not import {root}",
                    )
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if id(node) in docstrings:
                    continue
                self.assertNotIn(
                    "cmp-",
                    node.value,
                    "a cross-source observation id must not be recognised here",
                )


if __name__ == "__main__":
    unittest.main()
