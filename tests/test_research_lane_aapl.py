"""AAPL's research lane, end to end.

The Phase 9.9 work configured AAPL and left its capture unbuilt, so the
question this file answers is whether the shared, configuration-driven
research engine can carry a second issuer whose history is shaped differently
from the first: a 52/53-week fiscal calendar, two stock splits, a revenue
element that changed tag and a depreciation element that changed tag, and
filings that were accepted after the market closed.

The tests here are about that, and about isolation: a research figure for
AAPL must be the lane's own arithmetic over filed facts, must agree with the
production AAPL dataset wherever the two read the same facts, and must move
no production figure at all.
"""
from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from historical_multiples import (
    ISSUER_CONFIGS,
    HistoricalMultiplesConfig,
    load_issuer_historical_multiples,
)
from historical_pe import canonical_json_hash, resolve_usable_date
from research_lane import (
    CLOSED_REASON_CODES,
    REASON_ELEMENT_UNAVAILABLE,
    REASON_INCOMPLETE_EV_BRIDGE,
    REASON_MIXED_BALANCE_SHEET_PERIODS,
    REASON_NO_DENOMINATOR_WINDOW,
    REASON_UNIT_CONFLICT,
    ResearchLaneConfig,
    assert_research_isolation,
    load_research_lane,
)
from research_issuers import (
    build_lane_results,
    candidate_lane_ids,
    config_for_lane,
    settings_for_ticker,
)

ROOT = Path(__file__).resolve().parent.parent

_AAPL = settings_for_ticker("AAPL")
CAPTURE_DIR = _AAPL.capture_dir
LANE_DIR = ROOT / "data" / "research_lanes" / "AAPL"
PRICES_EXIST = (CAPTURE_DIR / "daily_prices.json").exists()
PRICES_SKIP = "AAPL research capture daily_prices.json excluded per C-1 / DATA-DELIVERY.md"

REVENUE_LANE = "aapl_reported_revenue_multiple"
OPERATING_LANE = "aapl_reported_operating_profit_plus_reported_d_and_a_multiple"
EV_LANE = "aapl_filed_ev_bridge_multiple_production_shape"

# The production payload digests, pinned before the research lane existed.
# A research lane must not move them.
PRODUCTION_PAYLOAD_DIGESTS = {
    "AAPL": "ef7da465e7422f3e9429e2160be69ea5c3aeacbbd9bf1c77d000eec9f7b1b311",
    "AEP": "b9a53553bd9ebb75d0b25156520c842f05d32478933c049c8ed0b353ed1ed2e0",
    "MSFT": "a3f5d4e851848b71a9feb03abc35db5d884417dc355c38ea24bdf54fe7f3db2d",
}


def _manifest() -> dict:
    return json.loads((CAPTURE_DIR / "manifest.json").read_text(encoding="utf-8"))


def _acceptance() -> list:
    return json.loads(
        (CAPTURE_DIR / "filing_acceptance_evidence.json").read_text(encoding="utf-8")
    )


def _concept(role: str) -> dict:
    return json.loads(
        (CAPTURE_DIR / f"{role}_concept.json").read_text(encoding="utf-8")
    )


def _rows(role: str, tag: str) -> list:
    for element in _concept(role)["elements"]:
        if element["tag"] == tag:
            return list(element["units"].values())[0]
    raise AssertionError(f"{role} does not carry {tag}")


def _price_payload() -> dict:
    return json.loads(
        (CAPTURE_DIR / "daily_prices.json").read_text(encoding="utf-8")
    )["chart"]["result"][0]


def _results() -> dict:
    return build_lane_results(issuer_ids=["AAPL"])


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class TheCapture(unittest.TestCase):
    """The capture holds filed evidence, hashed and named."""

    def test_the_issuer_is_apple_and_not_just_a_ticker(self):
        self.assertEqual(_AAPL.issuer_id, "CIK0000320193")
        self.assertEqual(_AAPL.entity_name, "Apple Inc.")
        issuer = _manifest()["issuer"]
        self.assertEqual(issuer["cik"], "CIK0000320193")
        self.assertEqual(issuer["entity_name"], "Apple Inc.")
        self.assertEqual(issuer["ticker"], "AAPL")

    def test_every_file_the_manifest_declares_verifies(self):
        manifest = _manifest()
        for name, entry in manifest["files"].items():
            path = CAPTURE_DIR / name
            self.assertTrue(path.exists(), name)
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(), entry["sha256"], name
            )

    def test_the_manifest_names_the_source_of_every_file(self):
        for name, entry in _manifest()["files"].items():
            source = entry.get("source") or {}
            self.assertTrue(source.get("url"), name)
            self.assertTrue(source.get("retrieval"), name)
            self.assertTrue(source.get("note"), name)
        # The price payload is stored verbatim, so its source document is
        # the file itself.
        price = _manifest()["files"]["daily_prices.json"]
        self.assertEqual(
            price["source"]["source_document_sha256"], price["sha256"]
        )

    def test_the_acceptance_index_is_the_secs_own_header_time(self):
        rows = _acceptance()
        self.assertEqual(len(rows), 67)
        for row in rows:
            self.assertTrue(row["acceptance_datetime_header_et"], row["accession"])
            self.assertEqual(
                row["acceptance_basis"],
                "SGML header ACCEPTANCE-DATETIME",
                row["accession"],
            )
            self.assertTrue(row["acceptance_datetime_submissions_api"])

    def test_the_submissions_api_runs_four_to_five_hours_late_for_this_filer(self):
        """
        The SEC's submissions API and the filer's own SGML header disagree.

        The header is the SEC's own record of the acceptance time and is the
        one EDGAR itself displays; the submissions API serialises the same
        instant with the eastern offset applied twice for this filer. The
        capture keeps both, and the lane uses the header's.
        """
        for row in _acceptance():
            offset = row["api_minus_header_hours"]
            self.assertIn(offset, (4.0, 5.0), row["accession"])
            header = datetime.datetime.fromisoformat(
                row["acceptance_datetime_header_et"]
            )
            api = datetime.datetime.fromisoformat(
                row["acceptance_datetime_submissions_api"].replace("Z", "+00:00")
            )
            self.assertGreater(api, header, row["accession"])

    def test_the_capture_holds_no_dimensional_filtering(self):
        policy = _manifest()["capture_policy"]
        self.assertIn("no dimensional qualifiers", policy["dimensions"])
        self.assertIn("no dimensions", policy["context_policy"])

    def test_the_units_are_the_units_the_policy_names(self):
        policy = _manifest()["capture_policy"]["unit_policy"]
        self.assertEqual(policy["filing_unit"], "USD")
        for role in ("revenue", "operating_income", "depreciation", "cash"):
            for element in _concept(role)["elements"]:
                for unit in element["units"]:
                    self.assertEqual(unit, "USD", role)
        for element in _concept("shares_outstanding")["elements"]:
            for unit in element["units"]:
                self.assertEqual(unit, "shares")

    def test_the_price_series_carries_both_split_events(self):
        splits = _price_payload().get("events", {}).get("splits", {})
        ratios = sorted(
            event["splitRatio"] for event in splits.values()
        )
        self.assertEqual(ratios, ["4:1", "7:1"])
        days = sorted(
            datetime.datetime.fromtimestamp(
                event["date"], datetime.timezone.utc
            ).date().isoformat()
            for event in splits.values()
        )
        self.assertEqual(days, ["2014-06-09", "2020-08-31"])


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class TheFiscalCycle(unittest.TestCase):
    """AAPL's calendar is a 52/53-week fiscal year, not a calendar year."""

    def test_every_window_is_four_consecutive_fiscal_quarters(self):
        for lane_id, result in _results().items():
            published = [o for o in result.observations if o.value is not None]
            self.assertTrue(published, lane_id)
            for observation in published:
                positions = observation.denominator["positions"]
                self.assertEqual(len(positions), 4, observation.evaluation_date)
                for left, right in zip(positions, positions[1:]):
                    if right["fiscal_quarter"] == 1:
                        self.assertEqual(left["fiscal_quarter"], 4)
                        self.assertEqual(right["fiscal_year"], left["fiscal_year"] + 1)
                    else:
                        self.assertEqual(right["fiscal_quarter"], left["fiscal_quarter"] + 1)
                        self.assertEqual(right["fiscal_year"], left["fiscal_year"])

    def test_the_fiscal_year_ends_on_a_saturday_in_september(self):
        ends = set()
        for result in _results().values():
            for observation in result.observations:
                if observation.value is None or not observation.denominator:
                    continue
                for quarter in observation.denominator["quarters"]:
                    end = datetime.date.fromisoformat(quarter["period_end"])
                    if end.month == 9:
                        ends.add(end)
        self.assertTrue(ends)
        for end in ends:
            self.assertEqual(end.month, 9)
            self.assertEqual(end.weekday(), 5, end.isoformat())

    def test_the_quarters_are_thirteen_or_fourteen_weeks(self):
        """
        Consecutive fiscal quarters are thirteen or fourteen weeks apart,
        which a calendar quarter never is.
        """
        gaps = set()
        for result in _results().values():
            for observation in result.observations:
                if observation.value is None or not observation.denominator:
                    continue
                ends = [
                    datetime.date.fromisoformat(quarter["period_end"])
                    for quarter in observation.denominator["quarters"]
                ]
                for left, right in zip(ends, ends[1:]):
                    gaps.add((right - left).days)
        self.assertTrue(gaps)
        for gap in gaps:
            self.assertIn(gap // 7, (13, 14), gap)

    def test_the_quarter_ends_are_not_calendar_quarter_ends(self):
        """
        AAPL's quarters end on a Saturday, so at least one of them never
        coincides with a calendar quarter end.
        """
        ends = set()
        for result in _results().values():
            for observation in result.observations:
                if observation.value is None or not observation.denominator:
                    continue
                for quarter in observation.denominator["quarters"]:
                    ends.add(quarter["period_end"])
        calendar_ends = {"03-31", "06-30", "09-30", "12-31"}
        off_calendar = [
            end for end in ends if end[5:] not in calendar_ends
        ]
        self.assertTrue(off_calendar)


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class TheSplits(unittest.TestCase):
    """The price is the as-traded close, paired with the then-current shares."""

    def _observation(self, lane_id: str, day: str):
        for result in _results().values():
            if result.lane_id != lane_id:
                continue
            for observation in result.observations:
                if observation.evaluation_date == day:
                    return observation
        raise AssertionError(day)

    def test_the_close_before_the_seven_for_one_split_is_the_as_traded_close(self):
        before = self._observation(EV_LANE, "2014-04-25")
        after = self._observation(EV_LANE, "2014-07-24")
        self.assertEqual(before.price, 571.94)
        self.assertEqual(after.price, 97.03)
        # The provider's close is split-adjusted; the lane restores the close
        # the market actually printed.
        self.assertAlmostEqual(before.price / 7.0, 81.7057, places=3)
        self.assertGreater(before.price / after.price, 5.0)

    def test_the_shares_are_the_as_filed_counts_and_are_not_adjusted(self):
        before = self._observation(EV_LANE, "2014-04-25")
        after = self._observation(EV_LANE, "2014-07-24")
        self.assertEqual(before.shares_outstanding, 861381000.0)
        self.assertEqual(after.shares_outstanding, 5987867000.0)

    def test_the_market_cap_is_continuous_across_both_splits(self):
        for before_day, after_day, ratio in (
            ("2014-04-25", "2014-07-24", 7.0),
            ("2020-07-31", "2020-10-30", 4.0),
        ):
            before = self._observation(EV_LANE, before_day)
            after = self._observation(EV_LANE, after_day)
            self.assertAlmostEqual(
                before.market_cap, before.price * before.shares_outstanding, places=2
            )
            self.assertAlmostEqual(
                after.market_cap, after.price * after.shares_outstanding, places=2
            )
            # A market capitalisation that jumped by the split factor would
            # mean the price or the share count had been adjusted twice.
            change = after.market_cap / before.market_cap
            self.assertLess(change, ratio / 2.0, (before_day, after_day))
            self.assertGreater(change, 0.5, (before_day, after_day))

    def test_the_four_for_one_split_is_handled_the_same_way(self):
        before = self._observation(EV_LANE, "2020-07-31")
        after = self._observation(EV_LANE, "2020-10-30")
        self.assertEqual(before.price, 425.04)
        self.assertEqual(after.price, 108.86)
        self.assertEqual(before.shares_outstanding, 4275634000.0)
        self.assertEqual(after.shares_outstanding, 17001802000.0)
        self.assertAlmostEqual(before.price / 4.0, 106.26, places=2)


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class TheElementLineage(unittest.TestCase):
    """AAPL's depreciation element changed tag, and the lane says so."""

    def test_the_predecessor_element_is_annual_only(self):
        rows = _rows("depreciation", "DepreciationAndAmortization")
        self.assertTrue(rows)
        for row in rows:
            self.assertIsNotNone(row["start"], row)
            self.assertGreater(
                (datetime.date.fromisoformat(row["end"])
                 - datetime.date.fromisoformat(row["start"])).days,
                300,
                row,
            )

    def test_the_two_elements_overlap_on_fy2015_and_fy2016(self):
        predecessor = {
            row["end"] for row in _rows("depreciation", "DepreciationAndAmortization")
        }
        successor = {
            row["end"] for row in _rows(
                "depreciation", "DepreciationDepletionAndAmortization"
            )
        }
        overlap = predecessor & successor
        self.assertIn("2015-09-26", overlap)
        self.assertIn("2016-09-24", overlap)
        self.assertEqual(len(overlap), 2)

    def test_the_successor_carries_the_quarterly_spans_the_lane_reads(self):
        rows = _rows("depreciation", "DepreciationDepletionAndAmortization")
        quarterly = [
            row for row in rows
            if row.get("start")
            and (datetime.date.fromisoformat(row["end"])
                 - datetime.date.fromisoformat(row["start"])).days < 100
        ]
        self.assertTrue(quarterly)

    def test_the_pure_depreciation_element_is_not_read(self):
        self.assertNotIn("Depreciation", [role.name for role in _AAPL.roles])
        elements = {
            element
            for role in _AAPL.roles
            for element in role.elements
        }
        self.assertNotIn("Depreciation", elements)
        self.assertNotIn("DepreciationAmortizationAndAccretionNet", elements)

    def test_the_registry_standing_of_both_elements_is_recorded(self):
        result = _results()[OPERATING_LANE]
        observation = [o for o in result.observations if o.value is not None][0]
        standing = observation.registry_standing["depreciation"]
        self.assertEqual(
            standing["DepreciationAndAmortization"]["registry_decision"], "QUALIFIED"
        )
        self.assertEqual(
            standing["DepreciationDepletionAndAmortization"]["registry_decision"],
            "QUALIFIED",
        )

    def test_the_fy2016_re_presentation_is_recorded_as_a_revision(self):
        result = _results()[OPERATING_LANE]
        revisions = result.distribution.prior_period_revisions
        self.assertTrue(revisions)
        periods = {
            (row["period_end"], row["role"]) for row in revisions
        }
        self.assertIn(("2016-09-24", "depreciation"), periods)

    def test_the_revenue_element_change_is_recorded_on_the_observation(self):
        result = _results()[REVENUE_LANE]
        observation = [o for o in result.observations if o.value is not None][0]
        standing = observation.registry_standing["revenue"]
        self.assertEqual(
            standing["Revenues"]["registry_decision"], "NOT_QUALIFIED"
        )
        self.assertEqual(
            standing["RevenueFromContractWithCustomerExcludingAssessedTax"][
                "registry_decision"
            ],
            "QUALIFIED",
        )


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class ThePointInTime(unittest.TestCase):
    """A filing accepted after the close is knowable the next trading day."""

    def _trading_days(self) -> list:
        payload = _price_payload()
        quote = payload["indicators"]["quote"][0]
        return sorted(
            datetime.datetime.fromtimestamp(
                stamp, datetime.timezone.utc
            ).date().isoformat()
            for stamp, close in zip(payload["timestamp"], quote["close"])
            if close is not None
        )

    def test_an_after_close_acceptance_becomes_knowable_next_trading_day(self):
        days = self._trading_days()
        after_close = [
            row for row in _acceptance()
            if datetime.datetime.fromisoformat(
                row["acceptance_datetime_header_et"]
            ).time() >= datetime.time(16, 0)
        ]
        self.assertTrue(after_close)
        for row in after_close:
            moment = datetime.datetime.fromisoformat(
                row["acceptance_datetime_header_et"]
            )
            usable, rule = resolve_usable_date(moment, days)
            self.assertEqual(rule, "acceptance_at_or_after_1600ET_next_trading_day")
            self.assertGreater(usable, moment.date().isoformat())
            self.assertIn(usable, days)

    def test_a_before_close_acceptance_becomes_knowable_the_same_day(self):
        days = self._trading_days()
        before_close = [
            row for row in _acceptance()
            if datetime.datetime.fromisoformat(
                row["acceptance_datetime_header_et"]
            ).time() < datetime.time(16, 0)
        ]
        self.assertTrue(before_close)
        for row in before_close:
            moment = datetime.datetime.fromisoformat(
                row["acceptance_datetime_header_et"]
            )
            usable, rule = resolve_usable_date(moment, days)
            self.assertEqual(rule, "acceptance_before_1600ET_same_day")
            self.assertEqual(usable, moment.date().isoformat())

    def test_the_lanes_use_the_filings_own_usable_dates(self):
        rows = {row["accession"]: row for row in _acceptance()}
        days = self._trading_days()
        for result in _results().values():
            for observation in result.observations:
                if observation.value is None:
                    continue
                for quarter in observation.denominator["quarters"]:
                    for accession in quarter.get("accessions", []):
                        row = rows[accession]
                        moment = datetime.datetime.fromisoformat(
                            row["acceptance_datetime_header_et"]
                        )
                        usable, _rule = resolve_usable_date(moment, days)
                        self.assertLessEqual(
                            usable,
                            observation.evaluation_date,
                            (accession, observation.evaluation_date),
                        )


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class TheLanes(unittest.TestCase):
    """The two required lanes, and the third that shares their denominator."""

    def test_the_lane_counts_and_medians(self):
        results = _results()
        expected = {
            REVENUE_LANE: (28, 7.257709),
            OPERATING_LANE: (29, 22.054083),
            EV_LANE: (27, 22.326),
        }
        for lane_id, (count, median) in expected.items():
            distribution = results[lane_id].distribution
            self.assertEqual(distribution.sample_count, count, lane_id)
            self.assertEqual(distribution.total_evaluations, 67, lane_id)
            self.assertAlmostEqual(
                distribution.percentiles["median"], median, places=6, msg=lane_id
            )
            self.assertEqual(distribution.status, "RESEARCH_DISTRIBUTION", lane_id)

    def test_every_observation_is_recomputed_from_its_own_operands(self):
        for lane_id, result in _results().items():
            published = [o for o in result.observations if o.value is not None]
            self.assertTrue(published, lane_id)
            for observation in published:
                self.assertAlmostEqual(
                    observation.market_cap,
                    observation.price * observation.shares_outstanding,
                    places=2,
                    msg=(lane_id, observation.evaluation_date),
                )
                denominator = observation.denominator["value"]
                self.assertGreater(denominator, 0)
                if observation.enterprise_value is None:
                    expected = observation.market_cap / denominator
                else:
                    expected = observation.enterprise_value / denominator
                self.assertAlmostEqual(
                    observation.value, expected, places=6,
                    msg=(lane_id, observation.evaluation_date),
                )

    def test_the_enterprise_value_is_recomputed_from_the_bridge_components(self):
        result = _results()[EV_LANE]
        published = [o for o in result.observations if o.value is not None]
        self.assertTrue(published)
        for observation in published:
            components = observation.bridge["components"]
            debt = (
                components["commercial_paper"]["value"]
                + components["long_term_debt_noncurrent"]["value"]
                + components["long_term_debt_current"]["value"]
            )
            liquid = (
                components["cash"]["value"]
                + components["marketable_securities_current"]["value"]
            )
            self.assertAlmostEqual(observation.total_debt, debt, places=2)
            self.assertAlmostEqual(observation.liquid_funds, liquid, places=2)
            self.assertAlmostEqual(
                observation.enterprise_value,
                observation.market_cap + debt - liquid,
                places=2,
            )

    def test_the_denominator_is_the_sum_of_its_four_quarters(self):
        for lane_id, result in _results().items():
            for observation in result.observations:
                if observation.value is None or not observation.denominator:
                    continue
                quarters = observation.denominator["quarters"]
                self.assertEqual(len(quarters), 4, lane_id)
                self.assertAlmostEqual(
                    observation.denominator["value"],
                    sum(quarter["value"] for quarter in quarters),
                    places=2,
                    msg=(lane_id, observation.evaluation_date),
                )

    def test_the_bridge_components_describe_one_balance_sheet_date(self):
        result = _results()[EV_LANE]
        for observation in result.observations:
            if observation.value is None:
                continue
            components = observation.bridge["components"]
            period_ends = {c["period_end"] for c in components.values()}
            self.assertEqual(len(period_ends), 1, observation.evaluation_date)

    def test_no_figure_carries_a_production_reference(self):
        for result in _results().values():
            self.assertFalse(result.distribution.production_eligible)
            for observation in result.observations:
                self.assertFalse(
                    observation.production_refusal["production_eligible"]
                )


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class TheProductionCrossCheck(unittest.TestCase):
    """The research lane and the production dataset read the same facts."""

    @classmethod
    def setUpClass(cls):
        production = load_issuer_historical_multiples(
            ISSUER_CONFIGS["AAPL"]
        ).to_dict()
        cls.production = {
            observation["evaluation_date"]: observation
            for observation in production["observations"]
        }
        cls.results = _results()

    def test_the_enterprise_value_lane_matches_production_on_every_shared_date(self):
        lane = self.results[EV_LANE]
        shared = 0
        for observation in lane.observations:
            other = self.production.get(observation.evaluation_date)
            if other is None:
                continue
            shared += 1
            self.assertEqual(observation.price, other["price"])
            self.assertEqual(observation.shares_outstanding, other["shares_outstanding"])
            self.assertEqual(observation.market_cap, other["market_cap"])
            self.assertEqual(
                observation.enterprise_value, other["enterprise_value"]
            )
            self.assertAlmostEqual(
                observation.value, other["ev_ebitda_ratio"], places=6
            )
        self.assertEqual(shared, 35)

    def test_the_two_lanes_refuse_the_same_dates_with_the_same_reasons(self):
        """
        The two vocabularies are different, so the comparison is by
        condition: a date on which neither lane can build a window is
        refused by both, and a date on which the bridge holds two
        balance-sheet dates is refused by both.
        """
        lane = self.results[EV_LANE]
        for observation in lane.observations:
            other = self.production.get(observation.evaluation_date)
            if other is None or observation.value is not None:
                continue
            if observation.reason_code == REASON_MIXED_BALANCE_SHEET_PERIODS:
                self.assertEqual(
                    other["ev_reason_code"], "REASON_MIXED_BALANCE_SHEET_PERIODS"
                )
            else:
                self.assertEqual(
                    observation.reason_code, REASON_NO_DENOMINATOR_WINDOW
                )
                self.assertEqual(other["ev_reason_code"], "REASON_MISSING_EBITDA_WINDOW")

    def test_the_revenue_lane_matches_production_wherever_both_publish(self):
        lane = self.results[REVENUE_LANE]
        shared = 0
        for observation in lane.observations:
            other = self.production.get(observation.evaluation_date)
            if other is None or observation.value is None:
                continue
            if other.get("ps_ratio") is None:
                continue
            shared += 1
            self.assertEqual(observation.price, other["price"])
            self.assertEqual(observation.shares_outstanding, other["shares_outstanding"])
            self.assertAlmostEqual(
                observation.value, other["ps_ratio"], places=6,
                msg=observation.evaluation_date,
            )
        self.assertEqual(shared, 28)

    def test_the_four_dates_that_differ_are_the_second_revenue_element(self):
        """
        The research capture holds AAPL's own revenue chronology; the
        production dataset holds the element the registry accepts. The two
        differ only where the research capture can build a window production
        cannot, and the dates are named rather than reconciled away.
        """
        lane = self.results[REVENUE_LANE]
        differing = []
        for observation in lane.observations:
            other = self.production.get(observation.evaluation_date)
            if other is None:
                continue
            if observation.value is None and other.get("ps_ratio") is None:
                continue
            if observation.value is None or other.get("ps_ratio") is None:
                differing.append(observation.evaluation_date)
        self.assertEqual(
            differing, ["2018-11-05", "2019-01-31", "2019-05-02", "2019-08-01"]
        )

    def test_the_homogeneous_research_median_is_the_production_median(self):
        """
        The research lane's own median is published over the sample that
        rests on one element, and that sample is the production dataset's
        sample. The two medians therefore agree, which is what a pooled
        median over the mixed windows had been hiding.
        """
        production = load_issuer_historical_multiples(
            ISSUER_CONFIGS["AAPL"]
        ).to_dict()
        production_median = production["distributions"]["P_S_RATIO_REFERENCE"][
            "percentiles"
        ]["median"]
        distribution = self.results[REVENUE_LANE].distribution
        self.assertAlmostEqual(
            distribution.percentiles["median"], production_median, places=6
        )
        self.assertEqual(
            distribution.sample_count,
            production["distributions"]["P_S_RATIO_REFERENCE"]["sample_count"],
        )

    def test_the_research_lane_publishes_dates_production_does_not_reach(self):
        production = load_issuer_historical_multiples(
            ISSUER_CONFIGS["AAPL"]
        ).to_dict()
        production_dates = {
            observation["evaluation_date"] for observation in production["observations"]
        }
        research_dates = {
            observation.evaluation_date
            for observation in self.results[REVENUE_LANE].observations
        }
        self.assertTrue(research_dates - production_dates)


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class TheIsolation(unittest.TestCase):
    """Nothing here moves a production figure."""

    def test_the_production_payloads_are_unchanged(self):
        for ticker, digest in PRODUCTION_PAYLOAD_DIGESTS.items():
            payload = load_issuer_historical_multiples(
                ISSUER_CONFIGS[ticker]
            ).to_dict()
            self.assertEqual(canonical_json_hash(payload), digest, ticker)

    def test_the_research_ids_do_not_collide_with_production_names(self):
        evidence = assert_research_isolation(
            [config.metric_id for config in _AAPL.lanes]
        )
        self.assertEqual(evidence["collisions"], [])
        for metric_id in evidence["research_metric_ids"]:
            self.assertTrue(metric_id.startswith("RESEARCH_AAPL_"))

    def test_the_research_output_carries_no_production_reference(self):
        for path in sorted(LANE_DIR.glob("*.json")):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("refc:", text, path.name)

    def test_the_committed_outputs_hold_the_same_figures(self):
        results = _results()
        for lane_id, result in results.items():
            path = LANE_DIR / f"{lane_id}.json"
            self.assertTrue(path.exists(), path.name)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["input_set_id"], result.input_set_id)
            self.assertEqual(payload["content_hash"], result.content_hash)
            self.assertEqual(
                payload["distribution"]["sample_count"],
                result.distribution.sample_count,
            )
            self.assertEqual(
                payload["distribution"]["percentiles"]["median"],
                result.distribution.percentiles["median"],
            )

    def test_the_ko_case_is_unchanged(self):
        results = build_lane_results(issuer_ids=["KO"])
        expected = {
            "ko_reported_revenue_multiple": (29, 6.403373),
            "ko_reported_operating_denominator_multiple": (64, 19.774421),
            "ko_filed_ev_bridge_multiple_production_shape": (27, 23.654283),
            "ko_filed_ev_bridge_multiple_short_term_borrowings": (29, 24.675484),
        }
        for lane_id, (count, median) in expected.items():
            distribution = results[lane_id].distribution
            self.assertEqual(distribution.sample_count, count, lane_id)
            self.assertAlmostEqual(
                distribution.percentiles["median"], median, places=6, msg=lane_id
            )
        committed = json.loads(
            (ROOT / "data" / "research_lanes" / "KO" / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        for lane_id, entry in committed["lanes"].items():
            self.assertEqual(results[lane_id].input_set_id, entry["input_set_id"])
            self.assertEqual(results[lane_id].content_hash, entry["content_hash"])

    def test_the_aapl_lanes_are_offered(self):
        for lane_id in (REVENUE_LANE, OPERATING_LANE, EV_LANE):
            self.assertIn(lane_id, candidate_lane_ids())


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class TheRefusals(unittest.TestCase):
    """The lanes refuse what they cannot state."""

    def _config(self, lane_id: str, **overrides) -> ResearchLaneConfig:
        return dataclasses.replace(config_for_lane(lane_id), **overrides)

    def test_a_missing_denominator_window_is_refused(self):
        result = _results()[REVENUE_LANE]
        refusals = [
            o for o in result.observations if o.value is None
        ]
        self.assertTrue(refusals)
        for observation in refusals:
            self.assertEqual(
                observation.reason_code, REASON_NO_DENOMINATOR_WINDOW
            )
            self.assertIn(observation.reason_code, CLOSED_REASON_CODES)

    def test_an_element_the_capture_does_not_hold_is_refused(self):
        config = self._config(REVENUE_LANE)
        roles = tuple(
            dataclasses.replace(role, elements=role.elements + ("NoSuchElement",))
            if role.name == "revenue"
            else role
            for role in config.roles
        )
        lane = load_research_lane(dataclasses.replace(config, roles=roles))
        self.assertEqual(
            lane.distribution.reason_code, REASON_ELEMENT_UNAVAILABLE
        )
        self.assertEqual(lane.observations, [])

    def test_a_denominator_in_another_unit_is_refused(self):
        config = self._config(REVENUE_LANE)
        lane = load_research_lane(
            dataclasses.replace(
                config,
                unit_policy=dataclasses.replace(
                    config.unit_policy, filing_unit="EUR"
                ),
            )
        )
        self.assertEqual(lane.distribution.reason_code, REASON_UNIT_CONFLICT)
        self.assertEqual(lane.observations, [])

    def test_a_capture_whose_normalisation_disagrees_with_the_policy_is_refused(self):
        config = self._config(REVENUE_LANE)
        lane = load_research_lane(
            dataclasses.replace(
                config,
                unit_policy=dataclasses.replace(config.unit_policy, scale=1000.0),
            )
        )
        self.assertEqual(lane.distribution.reason_code, REASON_UNIT_CONFLICT)
        self.assertEqual(lane.observations, [])

    def test_an_incomplete_bridge_is_refused(self):
        """
        The two dates at which AAPL's commercial paper is stale are refused
        for a mixed balance sheet rather than completed by omission.
        """
        result = _results()[EV_LANE]
        mixed = [
            o for o in result.observations
            if o.reason_code == REASON_MIXED_BALANCE_SHEET_PERIODS
        ]
        self.assertEqual(
            [o.evaluation_date for o in mixed], ["2020-05-01", "2020-07-31"]
        )
        for observation in mixed:
            self.assertIn(observation.reason_code, CLOSED_REASON_CODES)
            self.assertIsNone(observation.enterprise_value)

    def test_the_missing_bridge_component_is_named(self):
        result = _results()[EV_LANE]
        mixed = [
            o for o in result.observations
            if o.reason_code == REASON_MIXED_BALANCE_SHEET_PERIODS
        ]
        self.assertTrue(mixed)
        for observation in mixed:
            self.assertIn("commercial_paper", observation.reason_detail)

    def test_the_incomplete_bridge_code_is_closed(self):
        self.assertIn(REASON_INCOMPLETE_EV_BRIDGE, CLOSED_REASON_CODES)


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class TheIdentityContract(unittest.TestCase):
    """What each identity covers, and what changes it."""

    def test_the_same_configuration_and_data_reproduce_the_same_figures(self):
        first = _results()
        second = _results()
        for lane_id, result in first.items():
            other = second[lane_id]
            self.assertEqual(result.input_set_id, other.input_set_id)
            self.assertEqual(result.content_hash, other.content_hash)
            self.assertEqual(
                result.distribution.percentiles["median"],
                other.distribution.percentiles["median"],
            )

    def test_the_input_set_id_covers_the_capture_files(self):
        result = _results()[REVENUE_LANE]
        manifest = _manifest()
        for name, entry in manifest["files"].items():
            self.assertIn(entry["sha256"], result.capture_manifest["files"][name].values())

    def test_a_descriptive_manifest_change_is_not_a_numeric_change(self):
        """
        The capture's manifest describes the capture; the files it describes
        are the identity. Changing the description alone moves neither the
        figures nor the identity.
        """
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "capture"
            target.mkdir()
            for path in CAPTURE_DIR.iterdir():
                if path.name == "manifest.json":
                    continue
                (target / path.name).write_bytes(path.read_bytes())
            manifest = _manifest()
            manifest["captured_at"] = "2026-11-01"
            manifest["description"] = "a descriptive change"
            (target / "manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
            )
            config = config_for_lane(REVENUE_LANE)
            lane = load_research_lane(dataclasses.replace(config, capture_dir=target))
            original = _results()[REVENUE_LANE]
            self.assertEqual(lane.input_set_id, original.input_set_id)
            self.assertEqual(lane.content_hash, original.content_hash)
            self.assertEqual(
                lane.distribution.percentiles["median"],
                original.distribution.percentiles["median"],
            )

    def test_a_scaling_policy_that_changes_the_calculation_changes_the_identity(self):
        """
        A capture whose amounts are scaled by a thousand is not the same
        capture, and the identity says so.
        """
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "capture"
            target.mkdir()
            manifest = _manifest()
            for path in CAPTURE_DIR.iterdir():
                if path.name == "manifest.json":
                    continue
                if path.name.endswith("_concept.json") and (
                    path.name != "shares_outstanding_concept.json"
                ):
                    document = json.loads(path.read_text(encoding="utf-8"))
                    for element in document.get("elements") or []:
                        for unit, rows in (element.get("units") or {}).items():
                            for row in rows:
                                row["val"] = float(row["val"]) * 1000.0
                    if document.get("normalisation"):
                        document["normalisation"]["factor"] = 1000.0
                        document["normalisation"]["scaled"] = True
                    (target / path.name).write_text(
                        json.dumps(document, indent=2, sort_keys=True), encoding="utf-8"
                    )
                else:
                    (target / path.name).write_bytes(path.read_bytes())
            for name, entry in manifest["files"].items():
                entry["sha256"] = hashlib.sha256(
                    (target / name).read_bytes()
                ).hexdigest()
            policy = manifest["capture_policy"]
            for role, record in policy.get("role_normalisation", {}).items():
                if role == "shares_outstanding":
                    continue
                record["factor"] = 1000.0
                record["scaled"] = True
            (target / "manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
            )
            config = config_for_lane(REVENUE_LANE)
            lane = load_research_lane(
                dataclasses.replace(
                    config,
                    capture_dir=target,
                    unit_policy=dataclasses.replace(
                        config.unit_policy, scale=1000.0
                    ),
                )
            )
            original = _results()[REVENUE_LANE]
            self.assertNotEqual(lane.input_set_id, original.input_set_id)
            self.assertNotEqual(lane.content_hash, original.content_hash)
            # A denominator a thousand times larger is a multiple a thousand
            # times smaller.
            scaled = {
                o.evaluation_date: o for o in lane.observations if o.value is not None
            }
            for observation in original.observations:
                if observation.value is None:
                    continue
                self.assertAlmostEqual(
                    scaled[observation.evaluation_date].value,
                    observation.value / 1000.0,
                    places=6,
                    msg=observation.evaluation_date,
                )

    def test_a_changed_role_element_is_detectable(self):
        """
        The registry standing of the elements a role reads is on every
        observation, so a change to the role's element list changes the
        observation's identity even when the capture has not been rebuilt.
        """
        config = config_for_lane(REVENUE_LANE)
        roles = tuple(
            dataclasses.replace(role, elements=("Revenues",))
            if role.name == "revenue"
            else role
            for role in config.roles
        )
        lane = load_research_lane(dataclasses.replace(config, roles=roles))
        original = _results()[REVENUE_LANE]
        self.assertNotEqual(lane.content_hash, original.content_hash)
        standing = lane.observations[0].registry_standing["revenue"]
        self.assertEqual(set(standing), {"Revenues"})
        self.assertEqual(standing["Revenues"]["registry_decision"], "NOT_QUALIFIED")

    def test_the_policy_is_recorded_on_the_distribution(self):
        policy = _results()[REVENUE_LANE].distribution.unit_policy
        self.assertEqual(policy["filing_unit"], "USD")
        self.assertEqual(policy["observed_price_currency"], "USD")
        self.assertEqual(policy["observed_share_unit"], "shares")
        self.assertEqual(policy["role_units"]["revenue"], "USD")


if __name__ == "__main__":
    unittest.main()
