"""
3.29 Part B -- source-type preservation on the material projection.

`material_observations` and `_absent_observation` are the two places where a
material observation is built from a `MarketData` view field plus an adapter's
own observation. Five of the six provenance arguments on those paths already
read the source observation when one exists -- `provider`, `methodology`,
`currency`, `currency_basis`, `source_url`. `source_type` alone read
`data.source_type`, so a figure the engine took from a filing was stamped with
the *view's* source type and the filing's own was discarded.

The tests are written against the intended behaviour, so the foreign-source
cases fail before the fix and pass after it. The vendor case exists to pin the
behaviour that must NOT change: on a Yahoo or fixture view the source
observation and the view carry the same `source_type` today, and the patch must
leave that identical.

The price is deliberately excluded. `price_observations` and the price/volume
history read `data.source_type` correctly, because the price *is* the view's own
value and there is no separate source observation behind it.
"""

import unittest

from data_contract import (
    METRIC_PRICE,
    ObservationSet,
    METRIC_REVENUE,
    AvailabilityBasis,
    Observation,
    SourceType,
    Unit,
    ValidationStatus,
)
from st_eva_runner import (
    CompanyResolver,
    _absent_observation,
    material_observations,
    price_observations,
)

RETRIEVED = "2026-09-28T12:00:00+00:00"


def filing_observation(observation_id: str, metric: str, value) -> Observation:
    """One SEC-sourced observation, shaped the way an adapter reports one."""
    return Observation(
        observation_id=observation_id,
        metric=metric,
        value=value,
        unit=Unit.CURRENCY.value,
        currency="USD",
        currency_basis="REPORTED",
        period_start="2025-08-29",
        period_end="2026-05-28",
        as_of="2026-05-28",
        available_at="2026-06-24T22:59:46.000Z",
        available_at_basis=AvailabilityBasis.FILED_AS_OF_DATE.value,
        provider="SecEdgar",
        source_type=SourceType.REGULATORY_FILING.value,
        source_url="https://www.sec.gov/Archives/edgar/data/723125/x.htm",
        definition="Revenue as filed.",
        methodology="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        retrieved_at=RETRIEVED,
        raw={"sec_fact": {"taxonomy": "us-gaap", "tag": "Revenue"}},
        status=ValidationStatus.UNVERIFIABLE,
    )


class TestVendorSourceTypeIsUnchanged(unittest.TestCase):
    """
    The no-op case, pinned.

    On a regression-fixture view the source observation is the provider's own,
    so its `source_type` and the view's are the same string. The patch must be
    invisible here.
    """

    def setUp(self) -> None:
        self.data = CompanyResolver.resolve("AAPL", mode="regression")

    def test_every_material_observation_carries_the_views_source_type(self):
        materials = material_observations(self.data)
        self.assertTrue(materials)
        for metric, observation in materials.items():
            self.assertEqual(
                observation.source_type,
                self.data.source_type,
                f"{metric} changed the vendor source_type",
            )

    def test_the_price_stays_view_owned(self):
        """The price has no separate source observation; it is the view's own."""
        price = price_observations(self.data)[0]
        self.assertEqual(price.metric, METRIC_PRICE)
        self.assertEqual(price.source_type, self.data.source_type)


class TestForeignSourceTypeIsPreserved(unittest.TestCase):
    """
    The case the patch exists for.

    When an adapter supplies a material observation, the projection must keep
    that observation's own `source_type`. It must not infer one from the
    provider, derive one from the observation id, or force a single value: it
    has to preserve whatever the source declared.
    """

    def setUp(self) -> None:
        self.data = CompanyResolver.resolve("AAPL", mode="regression")
        self.filing = filing_observation(
            "ingest|revenue|RevenueFromContractWithCustomerExcludingAssessedTax"
            "|0000723125-26-000020|2025-08-29|2026-05-28|USD",
            METRIC_REVENUE,
            78_959_000_000.0,
        )
        # The material source for a metric is the first non-`cmp-` available
        # observation the view carries for it, so replacing `ev-revenue-001` is
        # what makes the filing the source the engine actually read. That is the
        # real shape: revenue reaching the engine from a filing rather than from
        # the vendor.
        replaced = ObservationSet(
            ticker=self.data.ticker,
            observations=[
                o for o in (
                    self.data.observations.get(identifier)
                    for identifier in self.data.observations.ids()
                )
                if o is not None
                and o.observation_id != "ev-revenue-001"
                and o.metric != METRIC_REVENUE
            ],
        )
        replaced.add(self.filing)
        self.data.observations = replaced
        self.data.current_revenue = 78_959_000_000.0

    def test_the_filing_is_the_material_source_for_revenue(self):
        """Guards the premise: without this the other tests prove nothing."""
        source = self.data.observations.for_metric(METRIC_REVENUE)[0]
        self.assertIs(source, self.filing)

    def test_a_present_value_keeps_the_sources_source_type(self):
        observation = material_observations(self.data)[METRIC_REVENUE]
        self.assertEqual(
            observation.source_type,
            SourceType.REGULATORY_FILING.value,
        )

    def test_an_absent_value_keeps_the_sources_source_type(self):
        """
        The absent path is the one with a single call site and no other test
        over it, so it is the site most likely to be missed.
        """
        source = self.data.observations.for_metric(METRIC_REVENUE)[0]
        self.data.current_revenue = None
        observation = material_observations(self.data)[METRIC_REVENUE]
        self.assertIsNone(observation.value)
        self.assertEqual(
            observation.source_type,
            SourceType.REGULATORY_FILING.value,
        )
        # and the same rule read directly, so the projection is not the only
        # thing being checked
        direct = _absent_observation(
            self.data, METRIC_REVENUE, source,
            Unit.CURRENCY.value, is_band=False,
        )
        self.assertEqual(
            direct.source_type, SourceType.REGULATORY_FILING.value
        )

    def test_the_other_provenance_arguments_already_came_from_the_source(self):
        """
        Five sibling arguments already honour the source observation. This
        pins that they still do, so the fix reads as completing a set rather
        than as changing a policy.
        """
        observation = material_observations(self.data)[METRIC_REVENUE]
        source = self.data.observations.for_metric(METRIC_REVENUE)[0]
        self.assertEqual(observation.provider, source.provider)
        self.assertEqual(observation.methodology, source.methodology)
        self.assertEqual(observation.source_url, source.source_url)


if __name__ == "__main__":
    unittest.main()
