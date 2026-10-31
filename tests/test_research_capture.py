"""The research capture: its acceptance times, their time zone, and the
usable dates they produce.

The capture records when each filing was accepted. The SEC states that time
in Eastern local time, and Eastern local time is not a fixed offset: a
standard-time filing is five hours from UTC and a daylight-time filing is
four. A capture that writes a fixed offset records a wrong instant for
every winter filing, and a filing accepted between 16:00 and 17:00 Eastern
then appears to be knowable a trading day before it was.

These tests pin the conversion in both seasons, and pin the usable dates
the capture produces so that a change to the representation cannot quietly
move a filing's knowability.
"""
from __future__ import annotations

import datetime
import json
import unittest
from pathlib import Path

from historical_pe import resolve_usable_date
from tools.build_research_capture import (
    api_acceptance_to_eastern,
    header_acceptance_to_eastern,
)

ROOT = Path(__file__).resolve().parent.parent
CAPTURE = ROOT / "data" / "research_multiples" / "KO"
PRICES_EXIST = (CAPTURE / "daily_prices.json").exists()
PRICES_SKIP = "KO daily_prices.json excluded per C-1 / DATA-DELIVERY.md"

# The usable dates the capture produces, pinned. Three of them moved when the
# acceptance times were corrected to the real Eastern offset: the FY2018,
# FY2019 and FY2022 annual filings were accepted between 16:00 and 17:00
# Eastern, so they become knowable on the next trading day and not on the
# day they were accepted.
PINNED_USABLE_DATES = (
    "2010-02-26", "2010-04-29", "2010-08-02", "2010-10-29", "2011-02-28", "2011-05-02",
    "2011-08-01", "2011-10-27", "2012-02-23", "2012-04-26", "2012-07-26", "2012-10-25",
    "2013-02-27", "2013-04-25", "2013-07-25", "2013-10-24", "2014-02-27", "2014-04-24",
    "2014-07-30", "2014-10-29", "2015-02-25", "2015-04-30", "2015-07-29", "2015-10-28",
    "2016-02-25", "2016-04-28", "2016-07-28", "2016-10-27", "2017-02-24", "2017-04-28",
    "2017-07-27", "2017-10-26", "2018-02-23", "2018-05-01", "2018-07-26", "2018-10-30",
    "2019-02-22", "2019-04-25", "2019-07-26", "2019-10-24", "2020-02-25", "2020-04-24",
    "2020-07-22", "2020-10-22", "2021-02-25", "2021-04-27", "2021-07-27", "2021-10-28",
    "2022-02-22", "2022-04-28", "2022-07-27", "2022-10-26", "2023-02-22", "2023-04-26",
    "2023-07-27", "2023-10-24", "2024-02-20", "2024-05-02", "2024-07-29", "2024-10-24",
    "2025-02-20", "2025-05-01", "2025-07-24", "2025-10-23", "2026-02-20", "2026-04-30",
    "2026-07-29",
)


def _capture() -> dict:
    return json.loads(
        (CAPTURE / "filing_acceptance_evidence.json").read_text(encoding="utf-8")
    )


def _trading_days() -> list:
    price = json.loads((CAPTURE / "daily_prices.json").read_text(encoding="utf-8"))[
        "chart"
    ]["result"][0]
    quote = price["indicators"]["quote"][0]
    return sorted(
        datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc)
        .date()
        .isoformat()
        for stamp, close in zip(price["timestamp"], quote["close"])
        if close is not None
    )


class TheAcceptanceTime(unittest.TestCase):
    """The acceptance time is Eastern local time, in both seasons."""

    def test_a_standard_time_header_keeps_its_winter_offset(self):
        moment = header_acceptance_to_eastern("20200224160817")
        self.assertEqual(moment.utcoffset(), datetime.timedelta(hours=-5))
        self.assertEqual(moment.isoformat(), "2020-02-24T16:08:17-05:00")
        self.assertEqual(
            moment.astimezone(datetime.timezone.utc).isoformat(),
            "2020-02-24T21:08:17+00:00",
        )

    def test_a_daylight_time_header_keeps_its_summer_offset(self):
        moment = header_acceptance_to_eastern("20190725160930")
        self.assertEqual(moment.utcoffset(), datetime.timedelta(hours=-4))
        self.assertEqual(moment.isoformat(), "2019-07-25T16:09:30-04:00")
        self.assertEqual(
            moment.astimezone(datetime.timezone.utc).isoformat(),
            "2019-07-25T20:09:30+00:00",
        )

    def test_the_two_agreements_agree(self):
        for raw, api in (
            ("20200224160817", "2020-02-24T21:08:17.000Z"),
            ("20190725160930", "2019-07-25T20:09:30.000Z"),
        ):
            self.assertEqual(
                header_acceptance_to_eastern(raw),
                api_acceptance_to_eastern(api),
            )

    def test_every_capture_record_holds_the_secs_own_instant(self):
        for row in _capture():
            recorded = datetime.datetime.fromisoformat(
                row["acceptance_datetime_effective_et"]
            )
            api = datetime.datetime.fromisoformat(
                row["acceptance_datetime_submissions_api"].replace("Z", "+00:00")
            )
            self.assertEqual(
                recorded,
                api.astimezone(recorded.tzinfo),
                f"{row['accession']} does not hold the acceptance instant the "
                "submissions API states",
            )

    def test_the_capture_states_the_offset_of_each_record(self):
        for row in _capture():
            recorded = datetime.datetime.fromisoformat(
                row["acceptance_datetime_effective_et"]
            )
            eastern = recorded.astimezone(
                __import__("zoneinfo").ZoneInfo("America/New_York")
            )
            self.assertEqual(
                recorded.utcoffset(),
                eastern.utcoffset(),
                f"{row['accession']} carries the wrong Eastern offset",
            )


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class TheUsableDates(unittest.TestCase):
    """The capture's acceptance times produce the pinned usable dates."""

    def test_the_usable_dates_are_the_pinned_ones(self):
        trading_days = _trading_days()
        dates = []
        for row in _capture():
            moment = datetime.datetime.fromisoformat(
                row["acceptance_datetime_effective_et"]
            )
            usable, _rule = resolve_usable_date(moment, trading_days)
            dates.append(usable)
        self.assertEqual(sorted(set(dates)), list(PINNED_USABLE_DATES))

    def test_a_filing_accepted_after_the_cutoff_becomes_knowable_next_trading_day(self):
        trading_days = _trading_days()
        rows = {row["accession"]: row for row in _capture()}
        record = rows["0000021344-20-000006"]
        moment = datetime.datetime.fromisoformat(
            record["acceptance_datetime_effective_et"]
        )
        usable, rule = resolve_usable_date(moment, trading_days)
        self.assertEqual(usable, "2020-02-25")
        self.assertEqual(rule, "acceptance_at_or_after_1600ET_next_trading_day")

    def test_the_capture_manifest_matches_its_files(self):
        import hashlib

        manifest = json.loads(
            (CAPTURE / "manifest.json").read_text(encoding="utf-8")
        )
        for name, entry in manifest["files"].items():
            digest = hashlib.sha256((CAPTURE / name).read_bytes()).hexdigest()
            self.assertEqual(digest, entry["sha256"], name)


if __name__ == "__main__":
    unittest.main()
