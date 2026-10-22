"""The research lane's semantic boundaries, and its deterministic replay.

Two contracts are pinned here.

The first is the semantic boundary. A role names a quantity and the filer's
own chronology of the elements it filed that quantity on, so a window that
reads from more than one element is on neither element alone. The lane has
to say so on the observation, and the reader has to be able to see which
element each quarter was read from, without inferring it from the issuer's
configuration.

The second is the replay. A replay over the committed capture files and the
committed configuration must reproduce the same observations, the same lane
outputs and the same hashes, and it must do so without a network: a replay
that quietly re-downloads a source is a new snapshot, not a replay, and the
two are not the same thing.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import shutil
import socket
import tempfile
import unittest
from pathlib import Path

from research_issuers import (
    build_lane_results,
    config_for_lane,
    settings_for_ticker,
)
from research_lane import (
    REASON_UNIT_CONFLICT,
    load_research_lane,
)

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"

_AAPL = settings_for_ticker("AAPL")
CAPTURE_DIR = _AAPL.capture_dir
LANE_DIR = ROOT / "data" / "research_lanes" / "AAPL"

REVENUE_LANE = "aapl_reported_revenue_multiple"
OPERATING_LANE = "aapl_reported_operating_profit_plus_reported_d_and_a_multiple"
EV_LANE = "aapl_filed_ev_bridge_multiple_production_shape"

# The four dates at which the research lane and the production AAPL dataset
# do not both publish, and the reason each is where it is.
DIVERGENT_DATES = ("2018-11-05", "2019-01-31", "2019-05-02", "2019-08-01")

RETIRED_ELEMENT = "us-gaap:Revenues"
ACCEPTED_ELEMENT = "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"


def _results() -> dict:
    return build_lane_results(issuer_ids=["AAPL"])


def _observation(lane_id: str, day: str):
    for result in _results().values():
        if result.lane_id != lane_id:
            continue
        for observation in result.observations:
            if observation.evaluation_date == day:
                return observation
    raise AssertionError(f"{lane_id} has no observation for {day}")


def _elements(observation) -> set:
    return {
        element
        for quarter in (observation.denominator or {}).get("quarters", [])
        for element in quarter.get("elements", [])
    }


class TheSemanticBoundary(unittest.TestCase):
    """The revenue lane reads two elements, and discloses it."""

    def test_the_first_window_is_read_entirely_from_the_retired_element(self):
        observation = _observation(REVENUE_LANE, "2018-11-05")
        self.assertEqual(_elements(observation), {RETIRED_ELEMENT})
        self.assertEqual(observation.value, 3.601818)

    def test_the_three_later_windows_are_read_from_both_elements(self):
        for day in DIVERGENT_DATES[1:]:
            observation = _observation(REVENUE_LANE, day)
            self.assertEqual(
                _elements(observation), {RETIRED_ELEMENT, ACCEPTED_ELEMENT}, day
            )

    def test_every_observation_names_the_element_each_quarter_was_read_from(self):
        """
        The element is not inferred from the issuer's configuration: it is
        read from the quarter.
        """
        for result in _results().values():
            for observation in result.observations:
                if observation.value is None or not observation.denominator:
                    continue
                for quarter in observation.denominator["quarters"]:
                    self.assertTrue(quarter.get("elements"), observation.evaluation_date)
                    for span in quarter.get("input_spans", []):
                        self.assertIn(span["element"], quarter["elements"])
                        self.assertTrue(span.get("accession"))
                        self.assertTrue(span.get("usable_date"))

    def test_a_window_that_mixes_two_elements_carries_the_break(self):
        for day in DIVERGENT_DATES[1:]:
            observation = _observation(REVENUE_LANE, day)
            notes = [
                note
                for note in observation.basis_breaks
                if "changes element inside this window" in note
            ]
            self.assertEqual(len(notes), 1, day)
            self.assertIn(RETIRED_ELEMENT, notes[0])
            self.assertIn(ACCEPTED_ELEMENT, notes[0])

    def test_the_break_states_whether_the_amount_moved(self):
        """
        The break is not a bare assertion. It says what the change did to the
        filed amount, on the evidence of the periods the two elements share.
        """
        observation = _observation(REVENUE_LANE, "2019-05-02")
        notes = [
            note
            for note in observation.basis_breaks
            if "changes element inside this window" in note
        ]
        self.assertEqual(len(notes), 1)
        self.assertIn("the same amount", notes[0])
        self.assertIn("re-tagging of the same quantity", notes[0])

    def test_the_series_change_is_disclosed_where_it_happens(self):
        observation = _observation(REVENUE_LANE, "2019-01-31")
        notes = [
            note for note in observation.basis_breaks if "changed element at" in note
        ]
        self.assertEqual(len(notes), 1)
        self.assertIn(RETIRED_ELEMENT, notes[0])
        self.assertIn(ACCEPTED_ELEMENT, notes[0])

    def test_the_two_elements_carry_the_same_filed_amounts(self):
        """
        The comparability question, answered from the capture: the two
        elements file the same amount for every period they both cover.
        """
        document = json.loads(
            (CAPTURE_DIR / "revenue_concept.json").read_text(encoding="utf-8")
        )
        filed: dict = {}
        for element in document["elements"]:
            for rows in element["units"].values():
                for row in rows:
                    key = (row.get("start"), row["end"])
                    filed.setdefault(key, {}).setdefault(element["tag"], set()).add(
                        row["val"]
                    )
        shared = [key for key, value in filed.items() if len(value) == 2]
        self.assertTrue(shared)
        for key in shared:
            values = filed[key]
            self.assertEqual(
                values["Revenues"], values["RevenueFromContractWithCustomerExcludingAssessedTax"],
                key,
            )

    def test_the_registry_standing_of_both_elements_is_recorded(self):
        observation = _observation(REVENUE_LANE, "2019-05-02")
        standing = observation.registry_standing["revenue"]
        self.assertEqual(standing["Revenues"]["registry_decision"], "NOT_QUALIFIED")
        self.assertEqual(
            standing["RevenueFromContractWithCustomerExcludingAssessedTax"][
                "registry_decision"
            ],
            "QUALIFIED",
        )

    def test_the_distribution_says_where_the_element_changed(self):
        distribution = _results()[REVENUE_LANE].distribution
        notes = {
            note: dates
            for note, dates in (distribution.basis_breaks or {}).items()
            if "changes element inside this window" in note
        }
        self.assertEqual(len(notes), 1)
        self.assertEqual(
            sorted(next(iter(notes.values()))), list(DIVERGENT_DATES[1:])
        )

    def test_the_earnings_lanes_are_not_mixed(self):
        """
        The earnings lanes' denominators are operating income and
        depreciation. The depreciation element changes tag, but both of the
        elements this role reads are annual before FY2018, so no window is
        mixed and no break is raised.
        """
        for lane_id in (OPERATING_LANE, EV_LANE):
            for observation in _results()[lane_id].observations:
                if observation.value is None or not observation.denominator:
                    continue
                self.assertEqual(
                    _elements(observation),
                    {
                        "us-gaap:OperatingIncomeLoss",
                        "us-gaap:DepreciationDepletionAndAmortization",
                    },
                    lane_id,
                )
                self.assertEqual(
                    [
                        note
                        for note in observation.basis_breaks
                        if "changes element inside this window" in note
                    ],
                    [],
                    lane_id,
                )


class TheDeterministicReplay(unittest.TestCase):
    """The same committed inputs give the same figures, offline."""

    def _no_network(self):
        """A socket that refuses to open, and a urlopen that refuses to run."""

        def refuse(*args, **kwargs):
            raise AssertionError("the replay must not reach the network")

        return socket.socket, refuse

    def test_the_replay_reaches_no_network(self):
        original_socket = socket.socket
        original_urlopen = None
        try:
            import urllib.request

            original_urlopen = urllib.request.urlopen
            socket.socket = self._no_network()[1]
            urllib.request.urlopen = self._no_network()[1]
            results = build_lane_results(issuer_ids=["AAPL"])
        finally:
            socket.socket = original_socket
            if original_urlopen is not None:
                import urllib.request

                urllib.request.urlopen = original_urlopen
        self.assertEqual(len(results), 3)
        for result in results.values():
            self.assertTrue(result.content_hash)

    def test_the_replay_reproduces_the_committed_outputs(self):
        results = _results()
        for lane_id, result in results.items():
            committed = json.loads(
                (LANE_DIR / f"{lane_id}.json").read_text(encoding="utf-8")
            )
            self.assertEqual(committed["input_set_id"], result.input_set_id, lane_id)
            self.assertEqual(committed["content_hash"], result.content_hash, lane_id)
            self.assertEqual(
                committed["distribution"]["sample_count"],
                result.distribution.sample_count,
                lane_id,
            )
            self.assertEqual(
                committed["distribution"]["percentiles"]["median"],
                result.distribution.percentiles["median"],
                lane_id,
            )

    def test_the_replay_reproduces_every_observation_hash(self):
        first = _results()[REVENUE_LANE]
        second = _results()[REVENUE_LANE]
        self.assertEqual(
            [o.content_hash for o in first.observations],
            [o.content_hash for o in second.observations],
        )
        self.assertEqual(first.content_hash, second.content_hash)

    def test_the_replay_leaves_the_capture_untouched(self):
        before = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(CAPTURE_DIR.iterdir())
        }
        _results()
        after = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(CAPTURE_DIR.iterdir())
        }
        self.assertEqual(before, after)

    def test_the_manifest_is_a_function_of_the_capture_files(self):
        """
        The manifest describes the files. A manifest written from the same
        files is the same manifest, so the manifest can be re-derived
        offline and the capture's identity does not depend on when it was
        described.
        """
        sys_path = str(TOOLS)
        import sys

        if sys_path not in sys.path:
            sys.path.insert(0, sys_path)
        from build_research_capture import describe_capture

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "AAPL"
            shutil.copytree(CAPTURE_DIR, target)
            describe_capture(_AAPL, target)
            self.assertEqual(
                (target / "manifest.json").read_text(encoding="utf-8"),
                (CAPTURE_DIR / "manifest.json").read_text(encoding="utf-8"),
            )


class TheIdentityContract(unittest.TestCase):
    """What each identity covers, and what moves it."""

    def test_a_calculation_effective_capture_change_moves_the_identity(self):
        """
        A file's own digest covers what that file says, so a capture whose
        amounts are scaled is a different capture.
        """
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "capture"
            target.mkdir()
            manifest = json.loads(
                (CAPTURE_DIR / "manifest.json").read_text(encoding="utf-8")
            )
            for path in CAPTURE_DIR.iterdir():
                if path.name == "manifest.json":
                    continue
                if path.name.endswith("_concept.json") and (
                    path.name != "shares_outstanding_concept.json"
                ):
                    document = json.loads(path.read_text(encoding="utf-8"))
                    for element in document.get("elements") or []:
                        for rows in (element.get("units") or {}).values():
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
            for role, record in manifest["capture_policy"]["role_normalisation"].items():
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

    def test_a_descriptive_manifest_change_moves_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "capture"
            target.mkdir()
            for path in CAPTURE_DIR.iterdir():
                if path.name == "manifest.json":
                    continue
                (target / path.name).write_bytes(path.read_bytes())
            manifest = json.loads(
                (CAPTURE_DIR / "manifest.json").read_text(encoding="utf-8")
            )
            manifest["captured_at"] = "2027-01-01"
            manifest["purpose"] = "a different description of the same capture"
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

    def test_a_manifest_that_disagrees_with_its_own_file_is_refused(self):
        """
        The manifest describes the capture; the files are the capture. When
        the two disagree about the unit or the scaling, the lane refuses
        rather than adopting one of the two silently.
        """
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "capture"
            target.mkdir()
            for path in CAPTURE_DIR.iterdir():
                if path.name == "manifest.json":
                    continue
                (target / path.name).write_bytes(path.read_bytes())
            manifest = json.loads(
                (CAPTURE_DIR / "manifest.json").read_text(encoding="utf-8")
            )
            manifest["capture_policy"]["role_normalisation"]["revenue"][
                "target_unit"
            ] = "EUR"
            (target / "manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
            )
            config = config_for_lane(REVENUE_LANE)
            lane = load_research_lane(dataclasses.replace(config, capture_dir=target))
            self.assertEqual(lane.distribution.reason_code, REASON_UNIT_CONFLICT)
            self.assertEqual(lane.observations, [])

    def test_a_manifest_that_disagrees_with_the_policy_is_refused(self):
        config = config_for_lane(REVENUE_LANE)
        lane = load_research_lane(
            dataclasses.replace(
                config,
                unit_policy=dataclasses.replace(
                    config.unit_policy, scale=1000.0
                ),
            )
        )
        self.assertEqual(lane.distribution.reason_code, REASON_UNIT_CONFLICT)
        self.assertEqual(lane.observations, [])

    def test_a_capture_whose_files_do_not_match_their_digests_is_refused(self):
        """
        A capture that has changed since it was built is not read. The lane
        raises rather than computing from evidence it cannot vouch for.
        """
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "capture"
            target.mkdir()
            for path in CAPTURE_DIR.iterdir():
                if path.name == "manifest.json":
                    continue
                (target / path.name).write_bytes(path.read_bytes())
            manifest = json.loads(
                (CAPTURE_DIR / "manifest.json").read_text(encoding="utf-8")
            )
            (target / "manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
            )
            document = json.loads(
                (target / "revenue_concept.json").read_text(encoding="utf-8")
            )
            document["elements"][0]["label"] = "a changed label"
            (target / "revenue_concept.json").write_text(
                json.dumps(document, indent=2, sort_keys=True), encoding="utf-8"
            )
            config = config_for_lane(REVENUE_LANE)
            with self.assertRaises(ValueError):
                load_research_lane(dataclasses.replace(config, capture_dir=target))


class TheShareCountIsNotScaled(unittest.TestCase):
    """The unit policy scales amounts, not counts."""

    def test_the_builder_holds_the_share_count_unscaled(self):
        import sys

        if str(TOOLS) not in sys.path:
            sys.path.insert(0, str(TOOLS))
        from build_research_capture import _role_scale

        policy = {
            "share_unit": "shares",
            "scale": 1000.0,
        }
        self.assertEqual(_role_scale("shares", policy), 1.0)
        self.assertEqual(_role_scale("USD", policy), 1000.0)

    def test_the_capture_states_the_share_count_unscaled(self):
        document = json.loads(
            (CAPTURE_DIR / "shares_outstanding_concept.json").read_text(
                encoding="utf-8"
            )
        )
        normalisation = document.get("normalisation") or {}
        self.assertEqual(normalisation.get("factor"), 1)
        self.assertFalse(normalisation.get("scaled"))

    def test_a_scaled_capture_leaves_the_market_cap_alone(self):
        """
        A capture whose amounts are scaled a thousandfold holds a
        thousandfold denominator, and the multiple falls a thousandfold. The
        market capitalisation does not move, because the share count was not
        scaled with the amounts.
        """
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "capture"
            target.mkdir()
            manifest = json.loads(
                (CAPTURE_DIR / "manifest.json").read_text(encoding="utf-8")
            )
            for path in CAPTURE_DIR.iterdir():
                if path.name == "manifest.json":
                    continue
                if path.name.endswith("_concept.json") and (
                    path.name != "shares_outstanding_concept.json"
                ):
                    document = json.loads(path.read_text(encoding="utf-8"))
                    for element in document.get("elements") or []:
                        for rows in (element.get("units") or {}).values():
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
            for role, record in manifest["capture_policy"]["role_normalisation"].items():
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
            scaled = {
                o.evaluation_date: o for o in lane.observations if o.value is not None
            }
            for observation in original.observations:
                if observation.value is None:
                    continue
                other = scaled[observation.evaluation_date]
                self.assertEqual(
                    observation.market_cap, other.market_cap, observation.evaluation_date
                )
                self.assertEqual(
                    observation.shares_outstanding,
                    other.shares_outstanding,
                    observation.evaluation_date,
                )
                self.assertAlmostEqual(
                    other.value,
                    observation.value / 1000.0,
                    places=6,
                    msg=observation.evaluation_date,
                )


class TheUnchangedCase(unittest.TestCase):
    """The KO case, and the production payloads, do not move."""

    def test_the_ko_lanes_publish_the_same_figures_and_identities(self):
        from research_issuers import build_lane_results

        committed = json.loads(
            (ROOT / "data" / "research_lanes" / "KO" / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        results = build_lane_results(issuer_ids=["KO"])
        for lane_id, entry in committed["lanes"].items():
            result = results[lane_id]
            self.assertEqual(result.input_set_id, entry["input_set_id"], lane_id)
            self.assertEqual(result.content_hash, entry["content_hash"], lane_id)
            self.assertEqual(
                result.distribution.sample_count,
                entry["sample_count"],
                lane_id,
            )
            self.assertEqual(
                result.distribution.percentiles["median"],
                entry["median"],
                lane_id,
            )

    def test_the_ko_comparison_hashes_are_unchanged(self):
        from research_comparison import compare_bridges, compare_history

        self.assertEqual(
            compare_history(
                "RESEARCH_KO_REPORTED_REVENUE_MULTIPLE", "2024-10-24", "2026-07-29"
            )["comparison_hash"],
            "c76adc8be8e26666e2e0420caaf4edee87bb044c7ee2a4f9a79439cb1905a1db",
        )
        self.assertEqual(
            compare_history(
                "RESEARCH_KO_REPORTED_OPERATING_PROFIT_PLUS_REPORTED_D_AND_A_MULTIPLE",
                "2024-10-24",
                "2026-07-29",
            )["comparison_hash"],
            "713f29bad7720bdbc33b5126871edd7a6f2ee0fe1a1ee93ad7748a4e7bbba00d",
        )
        self.assertEqual(
            compare_history(
                "RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_PRODUCTION_SHAPE",
                "2024-10-24",
                "2026-07-29",
            )["comparison_hash"],
            "9da67e1c760d86e8e69bde79d658118b9a36daddbe4804490024cb6272f98560",
        )
        self.assertEqual(
            compare_history(
                "RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_SHORT_TERM_BORROWINGS",
                "2024-10-24",
                "2026-07-29",
            )["comparison_hash"],
            "dec3bfa1c8593dc3cd7eeae1cc23d2f4cc3d9e9c2213b51a56eddc13e5d00502",
        )
        self.assertEqual(
            compare_bridges(
                "RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_PRODUCTION_SHAPE",
                "RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_SHORT_TERM_BORROWINGS",
            )["comparison_hash"],
            "a92a45a348cf04d15be9bb71fb8b1720b44f48a8fbf476d82b69e31ebc718a99",
        )
        self.assertEqual(
            compare_bridges(
                "RESEARCH_KO_REPORTED_REVENUE_MULTIPLE",
                "RESEARCH_KO_REPORTED_OPERATING_PROFIT_PLUS_REPORTED_D_AND_A_MULTIPLE",
            )["comparison_hash"],
            "f864b06c54e60bc750f52f73403648c579339906ce6880ad3131db57bd4c79cd",
        )

    def test_the_production_payloads_are_unchanged(self):
        from historical_multiples import ISSUER_CONFIGS, load_issuer_historical_multiples
        from historical_pe import canonical_json_hash

        digests = {
            "AAPL": "ef7da465e7422f3e9429e2160be69ea5c3aeacbbd9bf1c77d000eec9f7b1b311",
            "AEP": "b9a53553bd9ebb75d0b25156520c842f05d32478933c049c8ed0b353ed1ed2e0",
            "MSFT": "a3f5d4e851848b71a9feb03abc35db5d884417dc355c38ea24bdf54fe7f3db2d",
        }
        for ticker, digest in digests.items():
            payload = load_issuer_historical_multiples(
                ISSUER_CONFIGS[ticker]
            ).to_dict()
            self.assertEqual(canonical_json_hash(payload), digest, ticker)

    def test_every_research_result_is_ineligible_for_production(self):
        from research_issuers import build_lane_results

        for result in build_lane_results().values():
            self.assertFalse(result.distribution.production_eligible)
            for observation in result.observations:
                self.assertFalse(
                    observation.production_refusal["production_eligible"]
                )

    def test_no_research_output_carries_a_production_reference(self):
        for path in sorted(
            (ROOT / "data" / "research_lanes").rglob("*.json")
        ):
            self.assertNotIn("refc:", path.read_text(encoding="utf-8"), path.name)


if __name__ == "__main__":
    unittest.main()
