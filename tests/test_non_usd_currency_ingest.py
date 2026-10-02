"""
Non-USD monetary units, end to end.

2.52 measured the defect and 2.53 fixed it. This suite is the regression the fix
needs in order to stay fixed, and it deliberately drives a **non-USD fact
through the real ingestion path** rather than asserting on the helper functions
alone -- a unit mapper can be correct while the code that calls it still asks the
old question.

## What went wrong, in one line per site

`sec_ingest` and two `sec_provider` write paths all asked `is this unit USD?`
when they meant `is this unit monetary?`, and `xbrl_unit_to_contract_unit`
answered from a five-entry table. So a TWD, CAD or JPY fact missed the table,
took the `or Unit.RATIO.value` fallback, and was stored as a ratio with a NULL
currency. Measured in 2.52: 51 of 51 non-USD facts lost their currency, 60 of 60
USD facts kept it.

## Why a currency and not a guess

An ISO 4217 code in a unit position is the currency the filing declared. Using it
records what the source said; it does not infer a currency from a domicile, a
listing, a ticker or a filing country. That distinction is the whole reason the
rule is a shape check rather than a per-filer special case.

## What is deliberately not here

No historical observation is repaired. Existing rows do not carry their raw unit,
so they cannot be re-derived from the archive and are a separate round. These
tests are about ingestion only.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from core_registry import CoreRegistry  # noqa: E402
from data_contract import Unit  # noqa: E402
from registry_seed import seed  # noqa: E402
from sec_ingest import Ingestor  # noqa: E402
from sec_provider import (  # noqa: E402
    _basis_for,
    monetary_currency_of,
    observation_currency_of,
    xbrl_unit_to_contract_unit,
)
from sqlite_archive import SQLiteArchive  # noqa: E402

# The currencies 2.52 actually measured as lost, plus a spread so a future
# enumeration mistake cannot hide behind the two filers that were checked.
LOST_IN_252 = ("TWD", "CAD")
SPREAD = ("JPY", "EUR", "GBP", "SEK", "CHF", "AUD", "BRL", "INR", "KRW",
          "SGD", "HKD", "MXN", "ZAR", "NOK", "DKK")


class TestTheUnitMapper(unittest.TestCase):
    def test_a_currency_the_seed_table_never_listed_still_maps(self):
        for code in LOST_IN_252:
            self.assertEqual(
                xbrl_unit_to_contract_unit(code), Unit.CURRENCY.value, code)

    def test_the_mapper_does_not_stoop_at_the_seed_table(self):
        """The seed lists five strings; the rule is not an enumeration."""
        for code in SPREAD:
            self.assertEqual(
                xbrl_unit_to_contract_unit(code), Unit.CURRENCY.value, code)

    def test_case_and_shape_matter(self):
        """Lower case is not an ISO 4217 code, and is not coerced into one."""
        for unit_name in ("twd", "Twd", "TW", "TWDX", "TWDD", " TWD"):
            self.assertIsNone(
                xbrl_unit_to_contract_unit(unit_name), unit_name)

    def test_a_compound_divisor_is_still_refused(self):
        self.assertIsNone(xbrl_unit_to_contract_unit("TWD/shares/diluted"))
        self.assertIsNone(xbrl_unit_to_contract_unit("USD/shares/diluted"))

    def test_a_currency_per_share_unit_resolves_and_keeps_its_code(self):
        for code in LOST_IN_252 + ("USD", "JPY"):
            unit_name = f"{code}/shares"
            self.assertEqual(
                xbrl_unit_to_contract_unit(unit_name),
                Unit.PER_SHARE.value, unit_name)
            self.assertEqual(monetary_currency_of(unit_name), code, unit_name)

    def test_a_currency_observation_carries_its_code(self):
        """A plain monetary unit is what the observation is measured in."""
        self.assertEqual(observation_currency_of("TWD"), "TWD")
        self.assertEqual(observation_currency_of("CAD"), "CAD")
        self.assertEqual(observation_currency_of("USD"), "USD")

    def test_a_per_share_observation_records_no_currency_of_its_own(self):
        """Its unit is already `per_share`; the currency lives in the basis."""
        self.assertIsNone(observation_currency_of("TWD/shares"))
        self.assertIsNone(observation_currency_of("USD/shares"))
        self.assertIsNone(observation_currency_of("shares"))
        self.assertIsNone(observation_currency_of("pure"))

    def test_the_unit_fallback_is_no_longer_reachable_for_a_currency(self):
        """The `or Unit.RATIO.value` branch must be dead for every currency."""
        for code in LOST_IN_252 + SPREAD:
            resolved = xbrl_unit_to_contract_unit(code)
            self.assertIsNotNone(resolved, code)
            self.assertNotEqual(resolved, Unit.RATIO.value, code)


class TestTheBasis(unittest.TestCase):
    """`_basis_for` had the same USD-only assumption, per 2.52."""

    class _Fact:
        def __init__(self, unit, taxonomy="ifrs-full",
                     tag="CurrentPortionOfLongtermBorrowings"):
            self.unit = unit
            self.taxonomy = taxonomy
            self.tag = tag

    def test_reporting_currency_is_the_declared_code(self):
        for code in LOST_IN_252 + SPREAD:
            basis = _basis_for(self._Fact(code))
            self.assertEqual(basis["reporting_currency"], code, code)

    def test_reporting_currency_is_still_undeclared_for_a_non_currency(self):
        for unit_name in ("shares", "pure", "kWh"):
            basis = _basis_for(self._Fact(unit_name))
            self.assertEqual(basis["reporting_currency"], "UNDECLARED",
                             unit_name)

    def test_usd_reporting_currency_did_not_move(self):
        for unit_name in ("USD", "USD/shares", "USD-per-shares"):
            basis = _basis_for(self._Fact(unit_name))
            self.assertEqual(basis["reporting_currency"], unit_name, unit_name)


class _TwdSource:
    """
    One filing whose only debt fact is denominated in TWD.

    The provider reads the counters off the source, so they have to exist. The
    shape is the `companyfacts` one, with the unit key left as the filing states
    it -- which is the whole point: the unit is not normalised on the way in.
    """

    documents_read = 0
    concept_fetches = 0
    network_fetches = 0

    def resolve_company(self, ticker):
        class Company:
            cik = "0001046179"
            name = "Taiwan Semiconductor"
            exchanges = ()
        return Company()

    def submissions(self, cik):
        return {"sic": "3674", "sicDescription": "Semiconductors"}

    def filing_index(self, cik):
        return [{
            "accession": "0001193125-25-083423", "form": "20-F",
            "filing_date": "2025-04-22", "report_date": "2024-12-31",
            "acceptance_datetime": "2025-04-22T06:30:00.000Z",
            "acceptance_precision": "INSTANT",
            "primary_document": "", "is_xbrl": 1,
        }]

    def concept_history(self, cik, taxonomy, concept):
        if f"{taxonomy}:{concept}" != (
                "ifrs-full:CurrentPortionOfLongtermBorrowings"):
            return None
        return {"label": None, "units": {"TWD": [{
            "start": None, "end": "2024-12-31", "val": 59857900000.0,
            "accn": "0001193125-25-083423", "fy": 2024, "fp": "FY",
            "form": "20-F", "filed": "2025-04-22"}]}}

    def documents_for(self, taxonomy, concept):
        return ()


class TestIngestionEndToEnd(unittest.TestCase):
    """
    The path that actually produced the 278 rows 2.52 found.

    Asserted on the archived row rather than on a returned object, because the
    defect was only ever visible in storage.
    """

    def _ingested(self):
        directory = tempfile.mkdtemp()
        store = SQLiteArchive(os.path.join(directory, "a.sqlite"))
        registry = CoreRegistry(store.connection)
        seed(registry)
        Ingestor(store, _TwdSource(), registry).ingest(
            "TSM", metrics=("debt",), forms=("20-F",))
        return store

    def test_a_twd_fact_is_stored_as_a_currency_with_its_code(self):
        store = self._ingested()
        try:
            rows = list(store.connection.execute(
                "SELECT unit, currency, currency_basis FROM observations"
                " WHERE concept = ?",
                ("ifrs-full:CurrentPortionOfLongtermBorrowings",)))
            self.assertEqual(len(rows), 1, "the TWD fact did not survive")
            unit, currency, basis = rows[0]
            self.assertEqual(unit, "currency")
            self.assertEqual(currency, "TWD")
            self.assertEqual(basis, "REPORTED")
        finally:
            store.close()

    def test_the_twd_fact_is_not_typed_as_a_ratio(self):
        store = self._ingested()
        try:
            ratios = store.connection.execute(
                "SELECT COUNT(*) FROM observations WHERE unit = 'ratio'"
            ).fetchone()[0]
            self.assertEqual(ratios, 0)
        finally:
            store.close()

    def test_the_value_is_unchanged_by_the_typing(self):
        """Only the typing is fixed; the figure must be exactly what was filed."""
        store = self._ingested()
        try:
            value = store.connection.execute(
                "SELECT value_json FROM observations WHERE concept = ?",
                ("ifrs-full:CurrentPortionOfLongtermBorrowings",)
            ).fetchone()[0]
            self.assertEqual(float(value), 59857900000.0)
        finally:
            store.close()

    def test_the_fact_is_not_dropped_by_the_unmapped_unit_refusal(self):
        """
        The refusal gate.

        `concept_history` skips a unit it cannot map, so before the fix a non-USD
        fact was not merely mistyped on the path that stored it -- on this path
        it was dropped. Both symptoms were the same wrong question.
        """
        store = self._ingested()
        try:
            count = store.connection.execute(
                "SELECT COUNT(*) FROM observations").fetchone()[0]
            self.assertGreater(count, 0)
        finally:
            store.close()


class TestHistoricalRowsAreOutOfScope(unittest.TestCase):
    """This round repairs ingestion only. Stated so it stays true."""

    def test_no_migration_or_repair_is_attempted_here(self):
        self.assertFalse(hasattr(Ingestor, "repair_units"))
        self.assertFalse(hasattr(Ingestor, "migrate_currency"))

    def test_the_raw_payload_still_records_no_unit(self):
        """
        Why the repair cannot be folded into this round.

        Measured on a real ingested row rather than a hand-built one: the
        stored `raw_json` carries the fact's tag, taxonomy, accession, form, fy
        and fp but not its unit. So once a non-USD fact was stored as a ratio
        with a NULL currency, the archive cannot say what it should have been,
        and the repair has to re-derive it from the source.
        """
        store = TestIngestionEndToEnd()._ingested()
        try:
            raw = store.connection.execute(
                "SELECT raw_json FROM observations WHERE concept = ?",
                ("ifrs-full:CurrentPortionOfLongtermBorrowings",)
            ).fetchone()[0]
            self.assertIsNotNone(raw)
            fact = json.loads(raw).get("sec_fact", {})
            self.assertEqual(fact.get("tag"),
                             "CurrentPortionOfLongtermBorrowings")
            self.assertNotIn("unit", fact)
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()