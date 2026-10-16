"""Declared diluted-EPS evidence: the filing side of the EPS cross-check.

What this pins down.

A live run's vendor EPS anchor declares no period coverage and no accounting
basis, and the issuer's own answer lives in its filings. The SEC acquisition
path already reads the filed `us-gaap:EarningsPerShareDiluted` facts for a run;
`_build_declared_eps_evidence_block` publishes the latest *directly stated*
annual and interim facts from that acquisition, `_find_related_sec_evidence`
prefers them for the per-scenario cross-check (falling back to the packaged
dataset for runs that acquired no filing evidence), and both are evidence
only: they never become the source of the selected anchor, they never feed a
calculation, and derived windows (FY-minus-YTD roll-forwards, summed quarters)
are excluded because they are the acquisition's arithmetic, not the filer's
statement.

These tests never touch the network and never touch a persistent database.
"""
from __future__ import annotations

import sys
import unittest

sys.path.insert(0, ".")

from data_contract import (
    AvailabilityBasis,
    CurrencyBasis,
    METRIC_TRAILING_EPS,
    ObservationSet,
    SourceType,
    Unit,
    build_observation,
)
from st_eva_runner import (
    REGRESSION_TEST_FIXTURES,
    UNAVAILABLE,
    CompanyResolver,
    _build_declared_eps_evidence_block,
    _build_reverse_requirements,
    _declared_eps_fact_record,
    _declared_eps_facts_from_observations,
    _find_related_sec_evidence,
    run_st_eva,
)

SEC_EPS_URL = (
    "https://data.sec.gov/api/xbrl/companyconcept/"
    "CIK0000789019/us-gaap/EarningsPerShareDiluted.json"
)
LIVE_ACCESSION = "0001193125-26-987654"
FROZEN_ACCESSION = "0001193125-25-123456"


def _sec_eps_observation(
    value: float,
    period_start: str,
    period_end: str,
    *,
    form: str = "10-K",
    fp: str = "FY",
    fiscal_year: int = 2026,
    accession: str = LIVE_ACCESSION,
    filed: str = "2026-07-29",
    observation_id: str = "cmp-eps_diluted-sec-synthetic",
    derivation: str = "",
    unit: str = "USD/shares",
) -> object:
    """One live SEC acquisition observation, shaped as SECProvider mints them."""
    raw: dict = {
        "sec_fact": {
            "metric": "eps_diluted",
            "taxonomy": "us-gaap",
            "tag": "EarningsPerShareDiluted",
            "unit": unit,
            "value": value,
            "start": period_start,
            "end": period_end,
            "accession": accession,
            "form": form,
            "fy": fiscal_year,
            "fp": fp,
            "filed": filed,
        },
        "accession": accession,
        "form": form,
        "filed": filed,
        "reported_currency_unit": unit,
    }
    if derivation:
        raw = {
            "derivation": derivation,
            "span_days": 363,
            "constituents": [],
            "additive": False,
        }
    return build_observation(
        metric="eps_diluted",
        value=value,
        unit=Unit.PER_SHARE.value,
        provider="SecEdgar",
        source_type=SourceType.REGULATORY_FILING.value,
        definition="Diluted earnings per share as reported in a filing",
        methodology=(
            f"SEC XBRL us-gaap:EarningsPerShareDiluted as reported in "
            f"{form} accession {accession}"
        ),
        retrieved_at="2026-10-16T00:00:00+00:00",
        currency="USD",
        currency_basis=CurrencyBasis.REPORTED.value,
        period_start=period_start,
        period_end=period_end,
        as_of=period_end,
        available_at=filed + "T20:08:01.000Z",
        available_at_basis=AvailabilityBasis.ACCEPTANCE_DATETIME.value,
        source_url=SEC_EPS_URL,
        observation_id=observation_id,
        raw=raw,
    )


def _vendor_eps_observation(value: float = 16.79) -> object:
    return build_observation(
        metric=METRIC_TRAILING_EPS,
        value=value,
        unit=Unit.PER_SHARE.value,
        provider="YahooFinance+YahooFinanceFundamentals",
        source_type=SourceType.API_LIVE.value,
        definition="Trailing earnings per share",
        methodology="Yahoo quoteSummary defaultKeyStatistics.trailingEps",
        retrieved_at="2026-10-16T00:00:00+00:00",
        currency="USD",
        currency_basis=CurrencyBasis.INSTRUMENT_DEFAULT.value,
        as_of="2026-10-15",
        observation_id="ev-current-eps-001",
        raw={"module": "quoteSummary", "field": "trailingEps"},
    )


def _msft_reverse_package(sec_eps_evidence=None) -> dict:
    """The reverse-requirements stage over one constructed MSFT acquisition."""
    data = CompanyResolver._from_fixture(REGRESSION_TEST_FIXTURES["MSFT"])
    data.current_eps = 16.79
    data.forward_eps = UNAVAILABLE
    data.consensus_forward_eps = UNAVAILABLE
    data.observations = ObservationSet(
        ticker="MSFT", observations=[_vendor_eps_observation()]
    )
    analysis = {"observed_valuation": {}, "fundamental_snapshot": {}}
    return _build_reverse_requirements(
        data,
        analysis,
        horizons_years=(3.0,),
        required_returns=(0.10,),
        reference_multiple=25.0,
        reference_multiples=None,
        pfcf_multiple=None,
        ev_ebitda_multiple=None,
        ps_multiple=None,
        include_risk_free_rates=False,
        include_dcf=False,
        beta=None,
        equity_risk_premium=None,
        risk_free_tenor="10_YEAR",
        sec_observations=None,
        sec_eps_evidence=sec_eps_evidence,
        cross_validation=None,
        production_historical_pe=None,
        prefer_eps_anchor="trailing",
        user_eps=None,
    )


class TestDeclaredFactRecord(unittest.TestCase):
    """A record is built from identity, and refused when identity is missing."""

    def test_a_live_direct_fact_becomes_a_full_record(self):
        observation = _sec_eps_observation(
            74.33, "2025-08-29", "2026-09-03", observation_id="cmp-live-fy"
        )
        record = _declared_eps_fact_record(observation, cik="0000723125")
        self.assertIsNotNone(record)
        self.assertEqual(record["value"], 74.33)
        self.assertEqual(record["period_start"], "2025-08-29")
        self.assertEqual(record["period_end"], "2026-09-03")
        self.assertEqual(record["form"], "10-K")
        self.assertEqual(record["fiscal_period"], "FY")
        self.assertEqual(record["concept"], "us-gaap:EarningsPerShareDiluted")
        self.assertEqual(record["accession"], LIVE_ACCESSION)
        self.assertEqual(record["filed_date"], "2026-07-29")
        self.assertEqual(record["available_at_basis"], "ACCEPTANCE_DATETIME")
        self.assertIn("/723125/", record["document_url"])
        self.assertIn(LIVE_ACCESSION.replace("-", ""), record["document_url"])

    def test_a_derived_observation_is_not_a_declared_fact(self):
        derived = _sec_eps_observation(
            16.79,
            "2025-04-01",
            "2026-03-31",
            form="10-Q",
            fp="Q3",
            derivation="ANNUAL_ROLL_FORWARD",
        )
        self.assertIsNone(_declared_eps_fact_record(derived, cik="0000789019"))

    def test_an_observation_without_filing_identity_is_refused(self):
        observation = _sec_eps_observation(1.0, "2026-01-01", "2026-03-31")
        observation.raw.pop("accession")
        observation.raw["sec_fact"].pop("accession")
        self.assertIsNone(_declared_eps_fact_record(observation))
        observation = _sec_eps_observation(1.0, "2026-01-01", "2026-03-31")
        observation.raw.pop("form")
        observation.raw["sec_fact"].pop("form")
        self.assertIsNone(_declared_eps_fact_record(observation))
        observation = _sec_eps_observation(1.0, "2026-01-01", "2026-03-31")
        observation.raw["filed"] = ""
        observation.raw["sec_fact"].pop("filed")
        self.assertIsNone(_declared_eps_fact_record(observation))

    def test_a_non_per_share_unit_is_a_different_fact(self):
        observation = _sec_eps_observation(
            1.0, "2026-01-01", "2026-03-31", unit="USD"
        )
        self.assertIsNone(_declared_eps_fact_record(observation))

    def test_a_vendor_observation_is_never_a_declared_fact(self):
        self.assertIsNone(
            _declared_eps_fact_record(_vendor_eps_observation(16.79))
        )


class TestDeclaredFactSelection(unittest.TestCase):
    """Latest annual and latest interim, by stated identity."""

    def test_latest_annual_and_interim_are_selected_independently(self):
        observations = [
            _sec_eps_observation(7.59, "2024-08-30", "2025-08-28",
                                 accession="a-25", filed="2025-10-03",
                                 observation_id="fy2025"),
            _sec_eps_observation(4.60, "2025-08-29", "2025-11-27",
                                 form="10-Q", fp="Q1", accession="a-q1",
                                 filed="2025-12-18", observation_id="q1"),
            _sec_eps_observation(24.67, "2026-02-27", "2026-05-28",
                                 form="10-Q", fp="Q3", accession="a-q3",
                                 filed="2026-06-25", observation_id="q3"),
            _sec_eps_observation(74.33, "2025-08-29", "2026-09-03",
                                 accession="a-fy26", filed="2026-10-09",
                                 observation_id="fy2026"),
        ]
        latest_annual, latest_interim = _declared_eps_facts_from_observations(
            observations, cik="0000723125"
        )
        self.assertEqual(latest_annual["observation_id"], "fy2026")
        self.assertEqual(latest_annual["value"], 74.33)
        self.assertEqual(latest_interim["observation_id"], "q3")
        self.assertEqual(latest_interim["value"], 24.67)

    def test_derived_observations_never_win(self):
        observations = [
            _sec_eps_observation(2.02, "2026-03-29", "2026-06-27",
                                 form="10-Q", fp="Q3", accession="a-q3",
                                 filed="2026-07-31", observation_id="q3"),
            _sec_eps_observation(8.72, "2025-06-29", "2026-06-27",
                                 form="10-Q", fp="Q3", accession="a-ttm",
                                 filed="2026-07-31", observation_id="ttm",
                                 derivation="ANNUAL_ROLL_FORWARD"),
        ]
        _, latest_interim = _declared_eps_facts_from_observations(observations)
        self.assertEqual(latest_interim["observation_id"], "q3")

    def test_a_longer_cumulative_fact_wins_at_the_same_period_end(self):
        observations = [
            _sec_eps_observation(1.68, "2025-02-28", "2025-05-29",
                                 form="10-Q", fp="Q3", accession="a-q3",
                                 filed="2025-06-26", observation_id="quarter"),
            _sec_eps_observation(4.75, "2024-08-30", "2025-05-29",
                                 form="10-Q", fp="Q3", accession="a-q3",
                                 filed="2025-06-26", observation_id="ytd"),
        ]
        _, latest_interim = _declared_eps_facts_from_observations(observations)
        self.assertEqual(latest_interim["observation_id"], "ytd")

    def test_absent_annual_is_none_not_fabricated(self):
        observations = [
            _sec_eps_observation(4.60, "2025-08-29", "2025-11-27",
                                 form="10-Q", fp="Q1", accession="a-q1",
                                 filed="2025-12-18", observation_id="q1"),
        ]
        latest_annual, latest_interim = _declared_eps_facts_from_observations(
            observations
        )
        self.assertIsNone(latest_annual)
        self.assertIsNotNone(latest_interim)


class TestRelatedEvidencePrefersTheRun(unittest.TestCase):
    """Live acquisition first, packaged dataset as the fallback it always was."""

    def test_frozen_fallback_is_unchanged_when_no_observations_are_passed(self):
        record = _find_related_sec_evidence("AAPL")
        self.assertIsNotNone(record)
        self.assertEqual(record["accession"], "0000320193-25-000079")
        self.assertIn("cross-check", record["note"])
        self.assertIsNone(record["value"] if "value" in record else None)

    def test_a_ticker_without_any_source_has_no_related_evidence(self):
        self.assertIsNone(_find_related_sec_evidence("ZZZZ"))

    def test_live_observations_win_over_the_frozen_dataset(self):
        live = _sec_eps_observation(
            9.10, "2025-09-28", "2026-09-26", accession="0000320193-26-000099",
            filed="2026-10-30", observation_id="aapl-fy2026-live",
        )
        record = _find_related_sec_evidence(
            "AAPL", sec_observations=[live], cik="0000320193"
        )
        self.assertEqual(record["accession"], "0000320193-26-000099")
        self.assertEqual(record["period_end"], "2026-09-26")
        # The packaged AAPL fact has a different accession; identity, not value
        # or dataset preference, decides.
        self.assertIn("cross-check", record["note"])

    def test_live_observations_without_an_annual_fall_back_to_the_dataset(self):
        interim_only = _sec_eps_observation(
            2.02, "2026-03-29", "2026-06-27", form="10-Q", fp="Q3",
            accession="0000320193-26-000020", filed="2026-07-31",
        )
        record = _find_related_sec_evidence(
            "AAPL", sec_observations=[interim_only], cik="0000320193"
        )
        self.assertEqual(record["accession"], "0000320193-25-000079")


class TestTheReportBlock(unittest.TestCase):
    """Three states, stated rather than implied; nothing filled in."""

    def test_available_from_the_run_names_both_facts(self):
        observations = [
            _sec_eps_observation(17.95, "2025-07-01", "2026-06-30",
                                 accession="a-fy26", filed="2026-07-29",
                                 observation_id="fy2026"),
            _sec_eps_observation(4.27, "2026-01-01", "2026-03-31",
                                 form="10-Q", fp="Q3", accession="a-q3",
                                 filed="2026-04-29", observation_id="q3"),
        ]
        block = _build_declared_eps_evidence_block(
            "MSFT", {"observations": observations, "cik": "0000789019"}
        )
        self.assertEqual(block["status"], "AVAILABLE")
        self.assertEqual(block["source"], "RUN_ACQUISITION")
        self.assertEqual(block["provider"], "SecEdgar")
        self.assertEqual(block["basis"], "GAAP_DILUTED_EPS")
        self.assertEqual(block["latest_annual"]["value"], 17.95)
        self.assertEqual(block["latest_interim"]["value"], 4.27)
        self.assertEqual(block["unavailable"], [])

    def test_a_silent_source_is_unavailable_not_filled(self):
        block = _build_declared_eps_evidence_block(
            "MSFT", {"observations": [], "cik": "0000789019"}
        )
        self.assertEqual(block["status"], "UNAVAILABLE")
        self.assertEqual(block["source"], "RUN_ACQUISITION")
        self.assertIsNone(block["latest_annual"])
        self.assertEqual(block["unavailable"][0]["reason_kind"], "SOURCE_SILENT")

    def test_a_run_without_filing_evidence_states_not_acquired(self):
        block = _build_declared_eps_evidence_block("ZZZZ", None)
        self.assertEqual(block["status"], "NOT_ACQUIRED")
        self.assertIsNone(block["source"])
        self.assertEqual(block["unavailable"][0]["reason_kind"], "NOT_ACQUIRED")

    def test_the_packaged_dataset_is_named_as_the_source_it_is(self):
        block = _build_declared_eps_evidence_block("MSFT", None)
        self.assertEqual(block["status"], "AVAILABLE")
        self.assertEqual(block["source"], "PACKAGED_DATASET")
        self.assertEqual(block["latest_annual"]["accession"], "0001193125-26-323660")
        self.assertIsNone(block["latest_interim"])
        self.assertEqual(
            block["unavailable"][0]["reason_kind"], "NOT_AVAILABLE_IN_DATASET"
        )


class TestTheReverseReportIntegration(unittest.TestCase):
    """The block and the per-scenario cross-check, over a constructed run."""

    def test_live_evidence_flows_to_the_report_and_the_scenario_rows(self):
        observations = [
            _sec_eps_observation(
                17.95, "2025-07-01", "2026-06-30", accession="a-fy26",
                filed="2026-07-29", observation_id="fy2026-live",
            ),
            _sec_eps_observation(
                4.27, "2026-01-01", "2026-03-31", form="10-Q", fp="Q3",
                accession="a-q3", filed="2026-04-29", observation_id="q3-live",
            ),
        ]
        package = _msft_reverse_package(
            {"observations": observations, "cik": "0000789019"}
        )
        block = package["declared_eps_evidence"]
        self.assertEqual(block["status"], "AVAILABLE")
        self.assertEqual(block["latest_annual"]["accession"], "a-fy26")

        scenario = package["reverse_requirements_matrix"][0]
        related = scenario["evidence"]["related_sec_evidence"]
        self.assertIsNotNone(related)
        self.assertEqual(related["accession"], "a-fy26")
        self.assertEqual(related["form"], "10-K")
        self.assertIn("cross-check", related["note"])
        # R2.1 stays intact: the vendor anchor keeps no direct SEC source, even
        # though a declared fact exists and the values are the same.
        self.assertIsNone(scenario["evidence"]["eps_evidence"]["sec_fact"])
        self.assertTrue(
            any(
                "related filing shown for cross-check only" in item
                for item in scenario["evidence"]["missing_or_unvalidated"]
            )
        )

    def test_the_declared_facts_feed_no_calculation(self):
        observations = [
            _sec_eps_observation(
                17.95, "2025-07-01", "2026-06-30", accession="a-fy26",
                filed="2026-07-29", observation_id="fy2026-live",
            )
        ]
        without = _msft_reverse_package(None)
        with_live = _msft_reverse_package(
            {"observations": observations, "cik": "0000789019"}
        )
        # Every computed figure is identical. (The fingerprint is not compared:
        # it covers the anchor's own contract view, whose related-evidence
        # record legitimately changed -- a pre-existing fingerprint contract,
        # not a moved calculation.)
        self.assertEqual(
            [
                (row["required_terminal_eps"], row["required_eps_cagr"])
                for row in without["reverse_requirements_matrix"]
            ],
            [
                (row["required_terminal_eps"], row["required_eps_cagr"])
                for row in with_live["reverse_requirements_matrix"]
            ],
        )
        self.assertEqual(
            without["status"], with_live["status"]
        )
        self.assertEqual(
            [u["item"] for u in without["unavailable"]],
            [u["item"] for u in with_live["unavailable"]],
        )

    def test_the_fixture_path_keeps_the_packaged_cross_check(self):
        # A regression run acquires no filing evidence, so the block reports
        # the packaged dataset and the scenario cross-check is exactly the
        # record every existing caller saw.
        result = run_st_eva("MSFT", mode="regression", save_snapshot=False)
        package = result["reverse_requirements"]
        block = package["declared_eps_evidence"]
        self.assertEqual(block["source"], "PACKAGED_DATASET")
        scenario = package["reverse_requirements_matrix"][0]
        related = scenario["evidence"]["related_sec_evidence"]
        self.assertIsNotNone(related)
        self.assertEqual(related["accession"], "0001193125-26-323660")
        self.assertIn("cross-check", related["note"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
