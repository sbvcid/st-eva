"""Issuer-declared fiscal period identity: classification rules, refusal of
unidentifiable periods, and the invariants that keep period identity from
leaking into point-in-time knowability.

Coverage per this round's mandate:

* month-end (calendar) filers and 52/53-week filers are classified by the
  same three rules, with no per-issuer special cases;
* Q4 from a 10-K period end, quarter ends that cross calendar months and
  fiscal years, and the 53-week year boundary (Micron FY2026: fiscal year
  2025-08-29..2026-09-03 with a 14-week fourth quarter);
* a period the declarations cannot identify is returned as unresolved and
  the loaders exclude it, never assign it to a neighbouring quarter;
* identity never changes when a value becomes knowable: usable dates are a
  property of each fact's own filing, so a comparative declared by a later
  filing cannot make an earlier period knowable earlier (no lookahead).
"""

from __future__ import annotations

import datetime
import unittest

from fiscal_calendar import (
    IDENTITY_COMPARATIVE,
    IDENTITY_PRIMARY,
    IDENTITY_SPAN_POSITION,
    build_fiscal_calendar,
    build_fiscal_calendar_from_identities,
)


def filing(accession, period_end, form):
    return {
        "accession": accession,
        "period_end": period_end,
        "form": form,
        "acceptance_datetime": "2020-01-01T12:00:00-05:00",
        "usable_date": period_end,
        "usable_date_rule": "acceptance_before_1600ET_same_day",
    }


def fact(start, end, accn, form, fy, fp, val=1.0):
    return {
        "start": start,
        "end": end,
        "val": val,
        "accn": accn,
        "form": form,
        "fy": fy,
        "fp": fp,
        "filed": "2020-01-01",
    }


class TestMonthEndFilerClassification(unittest.TestCase):
    """A calendar-quarter filer (December FYE): grid and declarations agree."""

    def setUp(self):
        index = {
            "Q1": filing("Q1", "2020-03-31", "10-Q"),
            "Q2": filing("Q2", "2020-06-30", "10-Q"),
            "Q3": filing("Q3", "2020-09-30", "10-Q"),
            "FY": filing("FY", "2020-12-31", "10-K"),
        }
        payload = {
            "units": {
                "USD": [
                    fact("2020-01-01", "2020-03-31", "Q1", "10-Q", 2020, "Q1"),
                    fact("2020-01-01", "2020-06-30", "Q2", "10-Q", 2020, "Q2"),
                    fact("2020-01-01", "2020-09-30", "Q3", "10-Q", 2020, "Q3"),
                    fact("2020-01-01", "2020-12-31", "FY", "10-K", 2020, "FY"),
                ]
            }
        }
        self.calendar = build_fiscal_calendar([payload], index)

    def test_calendar_quarters_take_their_own_focus_labels(self):
        expected = {
            "2020-03-31": (2020, 1),
            "2020-06-30": (2020, 2),
            "2020-09-30": (2020, 3),
            "2020-12-31": (2020, 4),
        }
        for end, (fy, q) in expected.items():
            identity = self.calendar.quarter_identity[end]
            with self.subTest(period_end=end):
                self.assertEqual((identity.fiscal_year, identity.fiscal_quarter), (fy, q))
                self.assertEqual(identity.identity_source, IDENTITY_PRIMARY)

    def test_cumulative_span_ends_are_quarter_ends_too(self):
        # A 6M cumulative span ends where Q2 ends; its primary filing (the
        # Q2 10-Q) declares the quarter. Cumulative-only filers depend on
        # this: their discrete Q2/Q3 are derived from 6M/9M spans.
        index = {
            "Q1": filing("Q1", "2020-03-31", "10-Q"),
            "Q2": filing("Q2", "2020-06-30", "10-Q"),
        }
        payload = {
            "units": {
                "USD": [
                    fact("2020-01-01", "2020-03-31", "Q1", "10-Q", 2020, "Q1"),
                    fact("2020-01-01", "2020-06-30", "Q2", "10-Q", 2020, "Q2"),
                ]
            }
        }
        calendar = build_fiscal_calendar([payload], index)
        self.assertEqual(calendar.quarter_identity["2020-06-30"].fiscal_quarter, 2)


class TestFiftyThreeWeekFilerClassification(unittest.TestCase):
    """Micron FY2026: fiscal year 2025-08-29..2026-09-03, 53 weeks."""

    def setUp(self):
        # The 10-Qs whose conformed period of report equals each quarter end;
        # the 10-K's period end is the fiscal year end (2026-09-03).
        index = {
            "Q1": filing("Q1", "2025-11-27", "10-Q"),
            "Q2": filing("Q2", "2026-02-26", "10-Q"),
            "Q3": filing("Q3", "2026-05-28", "10-Q"),
            "FY": filing("FY", "2026-09-03", "10-K"),
        }
        payload = {
            "units": {
                "USD/shares": [
                    # FY2026 quarters: three 13-week quarters and a 14-week
                    # fiscal Q4 (2026-05-29..2026-09-03 = 98 days).
                    fact("2025-08-29", "2025-11-27", "Q1", "10-Q", 2026, "Q1", 4.60),
                    fact("2025-11-28", "2026-02-26", "Q2", "10-Q", 2026, "Q2", 12.07),
                    fact("2026-02-27", "2026-05-28", "Q3", "10-Q", 2026, "Q3", 24.67),
                    fact("2026-02-27", "2026-05-28", "Q3N", "10-Q", 2027, "Q3", 24.67),
                    fact("2025-08-29", "2026-09-03", "FY", "10-K", 2026, "FY", 74.33),
                ]
            }
        }
        self.calendar = build_fiscal_calendar([payload], index)

    def test_the_fiscal_year_end_is_fiscal_2026_q4_not_next_year_q1(self):
        # The month grid mapped 2026-09-03 to fiscal 2027 Q1; the issuer's
        # own 10-K focus fields place it in fiscal 2026 Q4.
        identity = self.calendar.quarter_identity["2026-09-03"]
        self.assertEqual((identity.fiscal_year, identity.fiscal_quarter), (2026, 4))
        self.assertEqual(identity.identity_source, IDENTITY_PRIMARY)

    def test_comparative_instances_do_not_relabel_the_quarter(self):
        # The same quarter re-reported as a comparative in next year's 10-Q
        # carries that filing's focus (2027, Q3); the identity stays the
        # declaring filing's (2026, Q3).
        identity = self.calendar.quarter_identity["2026-05-28"]
        self.assertEqual((identity.fiscal_year, identity.fiscal_quarter), (2026, 3))

    def test_the_annual_span_declares_fiscal_2026(self):
        self.assertEqual(self.calendar.annual_fiscal_year["2026-09-03"], 2026)

    def test_fiscal_year_end_lookup(self):
        self.assertEqual(self.calendar.fiscal_year_end(2026), "2026-09-03")


class TestPriorYearComparativeRule(unittest.TestCase):
    """An end whose primary filing is absent is identified by the 10-Q that
    reports it as the prior-year comparative (one fiscal year back)."""

    def test_364_day_comparative(self):
        index = {
            "CUR": filing("CUR", "2015-12-26", "10-Q"),  # AAPL FY2016 Q1 10-Q
        }
        payload = {
            "units": {
                "USD/shares": [
                    # The FY2015 Q1 quarter (ended 2014-12-27) appears only as
                    # the comparative inside the FY2016 Q1 10-Q.
                    fact("2014-09-28", "2014-12-27", "CUR", "10-Q", 2016, "Q1"),
                ]
            }
        }
        calendar = build_fiscal_calendar([payload], index)
        identity = calendar.quarter_identity["2014-12-27"]
        self.assertEqual((identity.fiscal_year, identity.fiscal_quarter), (2015, 1))
        self.assertEqual(identity.identity_source, IDENTITY_COMPARATIVE)

    def test_371_day_comparative_53_week_year(self):
        # A 53-week fiscal year puts the prior-year quarter end 371 days
        # behind the filing's own quarter end; the rule still holds.
        index = {
            "CUR": filing("CUR", "2021-01-02", "10-Q"),
        }
        payload = {
            "units": {
                "USD": [
                    fact("2019-12-29", "2020-01-04", "CUR", "10-Q", 2021, "Q1"),
                ]
            }
        }
        calendar = build_fiscal_calendar([payload], index)
        identity = calendar.quarter_identity["2020-01-04"]
        self.assertEqual((identity.fiscal_year, identity.fiscal_quarter), (2020, 1))

    def test_a_two_year_old_fact_is_not_one_year_comparative(self):
        # A fact two fiscal years behind the filing's own quarter end is not
        # the 10-Q's comparative; without another declaration it stays
        # unresolved rather than being assigned a guessed year.
        index = {
            "CUR": filing("CUR", "2016-12-31", "10-Q"),
        }
        payload = {
            "units": {
                "USD": [
                    fact("2014-01-01", "2014-12-31", "CUR", "10-Q", 2016, "Q4"),
                ]
            }
        }
        calendar = build_fiscal_calendar([payload], index)
        self.assertNotIn("2014-12-31", calendar.quarter_identity)
        self.assertEqual(len(calendar.unresolved), 1)


class TestAnnualSpanPositionRule(unittest.TestCase):
    """A quarter end inside an issuer-declared annual span sits a whole
    number of quarters before that fiscal year's end."""

    def setUp(self):
        # The FY2015 annual span exists only through a later 10-K's
        # comparative (its own 10-K is not indexed), and the quarter ends
        # only through that same 10-K's Item 302-style instances.
        index = {
            "LATER_FY": filing("LATER_FY", "2016-09-24", "10-K"),
        }
        payload = {
            "units": {
                "USD/shares": [
                    fact("2014-09-28", "2015-09-26", "LATER_FY", "10-K", 2016, "FY", 9.28),
                    fact("2014-09-28", "2014-12-27", "LATER_FY", "10-K", 2016, "FY", 3.28),
                    fact("2014-09-28", "2015-03-28", "LATER_FY", "10-K", 2016, "FY", 6.11),
                    fact("2014-09-28", "2015-06-27", "LATER_FY", "10-K", 2016, "FY", 7.96),
                ]
            }
        }
        self.calendar = build_fiscal_calendar([payload], index)

    def test_the_annual_span_is_the_prior_fiscal_year(self):
        self.assertEqual(self.calendar.annual_fiscal_year["2015-09-26"], 2015)

    def test_quarter_ends_follow_their_span_offsets(self):
        expected = {
            "2014-12-27": (2015, 1),
            "2015-03-28": (2015, 2),
            "2015-06-27": (2015, 3),
            "2015-09-26": (2015, 4),
        }
        for end, (fy, q) in expected.items():
            identity = self.calendar.quarter_identity[end]
            with self.subTest(period_end=end):
                self.assertEqual((identity.fiscal_year, identity.fiscal_quarter), (fy, q))
                self.assertEqual(identity.identity_source, IDENTITY_SPAN_POSITION)


class TestUncertainIdentityIsRefused(unittest.TestCase):
    """An unidentifiable period is unresolved, never a neighbouring quarter."""

    def test_no_declaration_at_all(self):
        # A quarter-length fact whose only instance belongs to an unindexed
        # filing carries no usable declaration.
        payload = {
            "units": {
                "USD": [
                    fact("2020-01-01", "2020-03-31", "GHOST", "10-Q", 2020, "Q1"),
                ]
            }
        }
        calendar = build_fiscal_calendar([payload], {})
        self.assertNotIn("2020-03-31", calendar.quarter_identity)
        self.assertEqual(
            calendar.unresolved[0]["period_end"], "2020-03-31"
        )
        self.assertIn(
            "no issuer declaration", calendar.unresolved[0]["reason"]
        )

    def test_contradictory_comparative_and_span_rules_stay_unresolved(self):
        # The 10-Q comparative rule places 2020-12-31 in fiscal 2020 (one
        # year back from a 2021 Q4 filing) while the containing annual span
        # says fiscal 2021; the disagreement refuses the end.
        index = {
            "CUR": filing("CUR", "2021-12-31", "10-Q"),
            "FY": filing("FY", "2021-03-31", "10-K"),
        }
        payload = {
            "units": {
                "USD": [
                    # Comparative basis: (2021-1, Q4) = (2020, Q4).
                    fact("2020-01-01", "2020-12-31", "CUR", "10-Q", 2021, "Q4"),
                    # Containment basis: annual span 2020-04-01..2021-03-31
                    # places 2020-12-31 about one quarter before its end, so
                    # it resolves to fiscal 2021 Q3, disagreeing with the
                    # comparative's fiscal 2020 Q4.
                    fact("2020-04-01", "2021-03-31", "FY", "10-K", 2021, "FY"),
                ]
            }
        }
        calendar = build_fiscal_calendar([payload], index)
        self.assertNotIn("2020-12-31", calendar.quarter_identity)
        self.assertTrue(
            any(item.get("period_end") == "2020-12-31" for item in calendar.unresolved)
        )

    def test_contradictory_primary_instances_stay_unresolved(self):
        index = {
            "A": filing("A", "2020-03-31", "10-Q"),
            "B": filing("B", "2020-03-31", "10-Q"),
        }
        payload = {
            "units": {
                "USD": [
                    fact("2020-01-01", "2020-03-31", "A", "10-Q", 2020, "Q1"),
                    fact("2020-01-01", "2020-03-31", "B", "10-Q", 2021, "Q2"),
                ]
            }
        }
        calendar = build_fiscal_calendar([payload], index)
        self.assertNotIn("2020-03-31", calendar.quarter_identity)
        self.assertTrue(
            any(item.get("period_end") == "2020-03-31" for item in calendar.unresolved)
        )

    def test_contradictory_annual_fiscal_years_stay_unresolved(self):
        index = {
            "A": filing("A", "2020-12-31", "10-K"),
            "B": filing("B", "2020-12-31", "10-K"),
        }
        payload = {
            "units": {
                "USD": [
                    fact("2020-01-01", "2020-12-31", "A", "10-K", 2020, "FY"),
                    fact("2020-01-01", "2020-12-31", "B", "10-K", 2021, "FY"),
                ]
            }
        }
        calendar = build_fiscal_calendar([payload], index)
        self.assertNotIn("2020-12-31", calendar.annual_fiscal_year)
        self.assertTrue(
            any(item.get("annual_period_end") == "2020-12-31" for item in calendar.warnings)
        )


class TestIdentityNeverChangesKnowability(unittest.TestCase):
    """Period identity is labelling; it must not move usable dates."""

    def test_a_comparative_declaration_does_not_pull_a_quarter_forward(self):
        # The 2026-05-28 quarter is first reported by its own 10-Q (usable
        # 2026-06-25) and re-reported a year later (usable 2027-06-24). The
        # identity is (2026, Q3) either way, and the instance in force on
        # 2026-07-01 is still only the first one.
        index = {
            "OWN": filing("OWN", "2026-05-28", "10-Q"),
            "NEXT": filing("NEXT", "2027-05-27", "10-Q"),
        }
        payload = {
            "units": {
                "USD/shares": [
                    fact("2026-02-27", "2026-05-28", "OWN", "10-Q", 2026, "Q3", 24.67),
                    fact("2026-02-27", "2026-05-28", "NEXT", "10-Q", 2027, "Q3", 24.67),
                ]
            }
        }
        calendar = build_fiscal_calendar([payload], index)
        identity = calendar.quarter_identity["2026-05-28"]
        self.assertEqual((identity.fiscal_year, identity.fiscal_quarter), (2026, 3))
        self.assertEqual(identity.primary_accession, "OWN")

    def test_identity_is_value_independent(self):
        # A restated comparative (different value, same period end) does not
        # change the period's fiscal identity.
        index = {
            "OWN": filing("OWN", "2020-06-27", "10-Q"),
            "LATER": filing("LATER", "2020-10-31", "10-K"),
        }
        payload = {
            "units": {
                "USD/shares": [
                    fact("2020-03-29", "2020-06-27", "OWN", "10-Q", 2020, "Q3", 2.58),
                    # The FY2020 10-K restates the quarter (split adjustment).
                    fact("2020-03-29", "2020-06-27", "LATER", "10-K", 2020, "FY", 0.65),
                ]
            }
        }
        calendar = build_fiscal_calendar([payload], index)
        identity = calendar.quarter_identity["2020-06-27"]
        self.assertEqual((identity.fiscal_year, identity.fiscal_quarter), (2020, 3))


class TestSyntheticIdentityConstructor(unittest.TestCase):
    """The fixture constructor feeds declared identities straight in."""

    def test_declared_identities_flow_through(self):
        calendar = build_fiscal_calendar_from_identities(
            {
                "2020-03-31": (2020, 1),
                "2020-06-30": (2020, 2),
                "2020-09-30": (2020, 3),
                "2020-12-31": (2020, 4),
            }
        )
        self.assertEqual(calendar.quarter_identity["2020-12-31"].fiscal_quarter, 4)
        self.assertEqual(calendar.fiscal_year_end(2020), None)


if __name__ == "__main__":
    unittest.main()
