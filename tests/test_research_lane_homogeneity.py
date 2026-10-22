"""The research lane's distributions are described over one basis.

A research lane reads the filer's own chronology of elements, so two of its
published observations may rest on different elements. A median over both
would be a statistic over a sample that is not one kind of figure, and this
file holds the lane to publishing a median over one basis only, and to saying
which basis.

The file also holds the capture's manifest to describing the capture: the
accession coverage of a role that holds more than one element is the union of
the elements' accessions, and the manifest is rebuilt from the files without
touching them.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from historical_pe import canonical_json_hash
from research_calculator import list_research_metrics
from research_issuers import (
    build_lane_results,
    config_for_lane,
    settings_for_ticker,
)
from research_lane import (
    BASIS_KIND_DIAGNOSTIC,
    BASIS_KIND_SAMPLE,
    STATUS_RESEARCH_DIAGNOSTIC,
    STATUS_RESEARCH_DISTRIBUTION,
    STATUS_RESEARCH_THIN_SAMPLE,
)

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from build_research_capture import describe_capture  # noqa: E402

_AAPL = settings_for_ticker("AAPL")
_KO = settings_for_ticker("KO")
CAPTURE_DIR = _AAPL.capture_dir
KO_CAPTURE_DIR = _KO.capture_dir

REVENUE_LANE = "aapl_reported_revenue_multiple"
OPERATING_LANE = "aapl_reported_operating_profit_plus_reported_d_and_a_multiple"
EV_LANE = "aapl_filed_ev_bridge_multiple_production_shape"

RETIRED_ELEMENT = "us-gaap:Revenues"
ACCEPTED_ELEMENT = "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"

LEGACY_DATES = ("2018-11-05",)
MIXED_DATES = ("2019-01-31", "2019-05-02", "2019-08-01")


def _results():
    return build_lane_results(issuer_ids=["AAPL"])


def _group(distribution, element):
    for group in distribution.basis_groups:
        if group["elements"] == [element]:
            return group
        if set(group["elements"]) == {element}:
            return group
    raise AssertionError(f"no group reads {element}")


def _median(values):
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


class TheHomogeneousGroups(unittest.TestCase):
    """AAPL's revenue lane's three semantic sub-samples."""

    def setUp(self):
        self.lane = _results()[REVENUE_LANE]
        self.distribution = self.lane.distribution

    def test_the_published_observations_fall_into_three_groups(self):
        kinds = sorted(group["kind"] for group in self.distribution.basis_groups)
        self.assertEqual(
            kinds, [BASIS_KIND_DIAGNOSTIC, BASIS_KIND_SAMPLE, BASIS_KIND_SAMPLE]
        )

    def test_the_legacy_only_group_is_the_retired_element_alone(self):
        group = _group(self.distribution, RETIRED_ELEMENT)
        self.assertEqual(group["kind"], BASIS_KIND_SAMPLE)
        self.assertEqual(group["status"], STATUS_RESEARCH_THIN_SAMPLE)
        self.assertEqual(group["sample_count"], 1)
        self.assertEqual(group["evaluation_dates"], list(LEGACY_DATES))
        self.assertEqual(group["basis"], {"revenue": [RETIRED_ELEMENT]})

    def test_the_successor_only_group_is_the_accepted_element_alone(self):
        group = _group(self.distribution, ACCEPTED_ELEMENT)
        self.assertEqual(group["kind"], BASIS_KIND_SAMPLE)
        self.assertEqual(group["status"], STATUS_RESEARCH_DISTRIBUTION)
        self.assertEqual(group["sample_count"], 28)
        self.assertEqual(group["period_start"], "2019-10-31")
        self.assertEqual(group["period_end"], "2026-07-31")
        self.assertEqual(group["basis"], {"revenue": [ACCEPTED_ELEMENT]})

    def test_the_mixed_group_is_a_diagnostic_and_publishes_no_statistic(self):
        mixed = [
            group
            for group in self.distribution.basis_groups
            if group["kind"] == BASIS_KIND_DIAGNOSTIC
        ]
        self.assertEqual(len(mixed), 1)
        group = mixed[0]
        self.assertEqual(group["status"], STATUS_RESEARCH_DIAGNOSTIC)
        self.assertEqual(group["sample_count"], 3)
        self.assertEqual(group["evaluation_dates"], list(MIXED_DATES))
        self.assertEqual(
            set(group["elements"]), {RETIRED_ELEMENT, ACCEPTED_ELEMENT}
        )
        self.assertEqual(group["percentiles"], {})
        self.assertIsNone(group["mean"])
        self.assertIsNone(group["min"])
        self.assertIsNone(group["max"])

    def test_each_group_matches_the_elements_its_quarters_were_read_from(self):
        for group in self.distribution.basis_groups:
            for day in group["evaluation_dates"]:
                observation = next(
                    o for o in self.lane.observations if o.evaluation_date == day
                )
                read = {
                    element
                    for quarter in observation.denominator["quarters"]
                    for element in quarter["elements"]
                }
                self.assertEqual(read, set(group["elements"]), day)

    def test_the_headline_is_the_successor_only_sample(self):
        self.assertEqual(self.distribution.sample_count, 28)
        self.assertEqual(
            self.distribution.basis, {"revenue": [ACCEPTED_ELEMENT]}
        )
        self.assertEqual(self.distribution.percentiles["median"], 7.257709)
        self.assertEqual(self.distribution.published_observation_count, 32)

    def test_the_headline_median_uses_only_its_own_sample(self):
        group = _group(self.distribution, ACCEPTED_ELEMENT)
        values = [
            o.value
            for o in self.lane.observations
            if o.value is not None and o.evaluation_date in group["evaluation_dates"]
        ]
        self.assertEqual(len(values), 28)
        self.assertAlmostEqual(
            self.distribution.percentiles["median"], _median(values), places=6
        )

    def test_the_mixed_windows_are_not_in_the_headline_sample(self):
        group = _group(self.distribution, ACCEPTED_ELEMENT)
        for day in MIXED_DATES:
            self.assertNotIn(day, group["evaluation_dates"])
        for day in LEGACY_DATES:
            self.assertNotIn(day, group["evaluation_dates"])

    def test_the_mixed_windows_are_kept_as_traceable_observations(self):
        for day in MIXED_DATES:
            observation = next(
                o for o in self.lane.observations if o.evaluation_date == day
            )
            self.assertIsNotNone(observation.value)
            self.assertTrue(observation.basis_breaks)
            spans = [
                span
                for quarter in observation.denominator["quarters"]
                for span in quarter.get("input_spans", [])
            ]
            self.assertTrue(spans)
            self.assertTrue(
                {span["element"] for span in spans}
                == {RETIRED_ELEMENT, ACCEPTED_ELEMENT}
            )

    def test_the_catalogue_does_not_pool_the_mixed_windows(self):
        summary = next(
            item
            for item in list_research_metrics()
            if item.metric_id == "RESEARCH_AAPL_REPORTED_REVENUE_MULTIPLE"
        )
        self.assertEqual(summary.sample_count, 28)
        self.assertEqual(summary.median, 7.257709)
        self.assertEqual(summary.published_observation_count, 32)
        self.assertEqual(summary.basis, {"revenue": [ACCEPTED_ELEMENT]})
        kinds = sorted(group["kind"] for group in summary.basis_groups)
        self.assertEqual(
            kinds, [BASIS_KIND_DIAGNOSTIC, BASIS_KIND_SAMPLE, BASIS_KIND_SAMPLE]
        )

    def test_the_calculation_service_applies_the_homogeneous_median(self):
        from research_calculator import (
            MULTIPLE_HISTORY_MEDIAN,
            ResearchCalculationRequest,
            run_research_calculation,
        )

        result = run_research_calculation(
            ResearchCalculationRequest(
                metric_id="RESEARCH_AAPL_REPORTED_REVENUE_MULTIPLE",
                multiple=10.0,
                multiple_source=MULTIPLE_HISTORY_MEDIAN,
                numerator_value=1000.0,
            )
        )
        self.assertEqual(result.multiple_evidence["sample_count"], 28)
        self.assertEqual(
            result.multiple_evidence["basis"],
            {"revenue": [ACCEPTED_ELEMENT]},
        )

    def test_the_other_aapl_lanes_hold_one_group_each(self):
        for lane_id in (OPERATING_LANE, EV_LANE):
            distribution = _results()[lane_id].distribution
            self.assertEqual(len(distribution.basis_groups), 1, lane_id)
            self.assertEqual(
                distribution.basis_groups[0]["kind"], BASIS_KIND_SAMPLE, lane_id
            )
            self.assertEqual(
                distribution.sample_count,
                distribution.basis_groups[0]["sample_count"],
                lane_id,
            )

    def test_the_ko_lanes_hold_one_group_each(self):
        for lane_id, result in build_lane_results(issuer_ids=["KO"]).items():
            distribution = result.distribution
            self.assertEqual(len(distribution.basis_groups), 1, lane_id)
            self.assertEqual(
                distribution.basis_groups[0]["kind"], BASIS_KIND_SAMPLE, lane_id
            )
            self.assertEqual(
                distribution.sample_count,
                distribution.basis_groups[0]["sample_count"],
                lane_id,
            )


class TheIdentityContract(unittest.TestCase):
    """A change to a published observation moves the identity that says so."""

    def test_the_lane_identity_is_the_hash_of_its_observation_hashes(self):
        result = _results()[REVENUE_LANE]
        self.assertEqual(
            result.content_hash,
            canonical_json_hash(
                {
                    "input_set_id": result.input_set_id,
                    "observations": [o.content_hash for o in result.observations],
                }
            ),
        )

    def test_adding_an_observation_moves_the_lane_identity(self):
        result = _results()[REVENUE_LANE]
        hashes = [o.content_hash for o in result.observations]
        with_one_more = canonical_json_hash(
            {
                "input_set_id": result.input_set_id,
                "observations": hashes + ["an-observation-not-yet-made"],
            }
        )
        self.assertNotEqual(with_one_more, result.content_hash)

    def test_removing_an_observation_moves_the_lane_identity(self):
        result = _results()[REVENUE_LANE]
        hashes = [o.content_hash for o in result.observations]
        with_one_fewer = canonical_json_hash(
            {
                "input_set_id": result.input_set_id,
                "observations": hashes[:-1],
            }
        )
        self.assertNotEqual(with_one_fewer, result.content_hash)

    def test_changing_an_observation_basis_moves_its_hash_and_the_lane_hash(self):
        result = _results()[REVENUE_LANE]
        observation = next(
            o for o in result.observations if o.evaluation_date == "2018-11-05"
        )
        # The same figure, filed on the successor element instead: the
        # observation's content changes, and so does its identity.
        changed = dataclasses.replace(
            observation,
            content_hash="",
            denominator=dict(
                observation.denominator,
                quarters=[
                    dict(
                        quarter,
                        elements=[ACCEPTED_ELEMENT],
                        input_spans=[
                            dict(span, element=ACCEPTED_ELEMENT)
                            for span in quarter["input_spans"]
                        ],
                    )
                    for quarter in observation.denominator["quarters"]
                ],
            ),
        )
        self.assertNotEqual(changed.content_hash, observation.content_hash)
        hashes = [
            changed.content_hash if o.evaluation_date == "2018-11-05" else o.content_hash
            for o in result.observations
        ]
        self.assertNotEqual(
            canonical_json_hash(
                {
                    "input_set_id": result.input_set_id,
                    "observations": hashes,
                }
            ),
            result.content_hash,
        )

    def test_the_distribution_construction_is_versioned(self):
        result = _results()[REVENUE_LANE]
        self.assertEqual(result.distribution.logic_version, "research-multiples/1.1.0")
        self.assertEqual(result.distribution.methodology, "research-multiples/1.0")


class TheCaptureManifest(unittest.TestCase):
    """The manifest describes the capture, and the capture is not touched."""

    def _describe(self, directory):
        target = Path(directory) / "capture"
        shutil.copytree(CAPTURE_DIR, target)
        describe_capture(_AAPL, target)
        return target, json.loads(
            (target / "manifest.json").read_text(encoding="utf-8")
        )

    def test_the_manifest_reproduces_from_the_capture_files(self):
        committed = json.loads(
            (CAPTURE_DIR / "manifest.json").read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory() as directory:
            _target, described = self._describe(directory)
        for name, entry in committed["files"].items():
            self.assertEqual(described["files"][name]["sha256"], entry["sha256"], name)
            self.assertEqual(described["files"][name]["role"], entry["role"], name)
            if "unit" in entry:
                self.assertEqual(described["files"][name]["unit"], entry["unit"], name)
            if "accessions" in entry:
                self.assertEqual(
                    described["files"][name]["accessions"], entry["accessions"], name
                )
        self.assertEqual(
            described["capture_policy"]["accession_coverage"],
            committed["capture_policy"]["accession_coverage"],
        )
        self.assertEqual(
            described["capture_policy"]["role_normalisation"],
            committed["capture_policy"]["role_normalisation"],
        )
        self.assertEqual(described["captured_at"], committed["captured_at"])

    def test_a_multi_element_role_counts_every_elements_accessions(self):
        """
        A role that holds two elements is filed in more filings than its
        first element alone: the coverage is the union, de-duplicated.
        """
        document = json.loads(
            (CAPTURE_DIR / "revenue_concept.json").read_text(encoding="utf-8")
        )
        accessions = set()
        for element in document["elements"]:
            for rows in element["units"].values():
                accessions.update(row["accn"] for row in rows if row.get("accn"))
        committed = json.loads(
            (CAPTURE_DIR / "manifest.json").read_text(encoding="utf-8")
        )
        entry = committed["files"]["revenue_concept.json"]
        self.assertEqual(entry["accessions"]["count"], len(accessions))
        self.assertEqual(entry["accessions"]["first"], min(accessions))
        self.assertEqual(entry["accessions"]["last"], max(accessions))
        self.assertEqual(
            committed["capture_policy"]["accession_coverage"]["revenue"],
            entry["accessions"],
        )
        # The first element alone would have been fewer: the union is what
        # the manifest now states.
        first = set()
        for rows in document["elements"][0]["units"].values():
            first.update(row["accn"] for row in rows if row.get("accn"))
        self.assertGreater(len(accessions), len(first))

    def test_the_ko_manifest_states_the_union_for_its_multi_element_roles(self):
        committed = json.loads(
            (KO_CAPTURE_DIR / "manifest.json").read_text(encoding="utf-8")
        )
        for name, entry in committed["files"].items():
            if not name.endswith("_concept.json"):
                continue
            document = json.loads(
                (KO_CAPTURE_DIR / name).read_text(encoding="utf-8")
            )
            accessions = set()
            for element in document.get("elements") or []:
                for rows in (element.get("units") or {}).values():
                    accessions.update(
                        row["accn"] for row in rows if row.get("accn")
                    )
            self.assertEqual(entry["accessions"]["count"], len(accessions), name)

    def test_re_describing_the_capture_touches_no_file_and_moves_no_figure(self):
        before_files = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(CAPTURE_DIR.iterdir())
            if path.name != "manifest.json"
        }
        before_lanes = {
            lane_id: (result.input_set_id, result.content_hash)
            for lane_id, result in build_lane_results(issuer_ids=["AAPL"]).items()
        }
        with tempfile.TemporaryDirectory() as directory:
            self._describe(directory)
        after_files = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(CAPTURE_DIR.iterdir())
            if path.name != "manifest.json"
        }
        after_lanes = {
            lane_id: (result.input_set_id, result.content_hash)
            for lane_id, result in build_lane_results(issuer_ids=["AAPL"]).items()
        }
        self.assertEqual(before_files, after_files)
        self.assertEqual(before_lanes, after_lanes)

    def test_the_manifest_does_not_stand_in_for_the_files(self):
        """
        The manifest describes the files; the files are the capture. A file
        whose bytes have changed since it was built is refused.
        """
        from research_lane import load_research_lane

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


if __name__ == "__main__":
    unittest.main()
