"""The research calculation lane, and what keeps it out of production.

A research lane computes a named figure from filed evidence that the
production qualification regime does not admit. It borrows production's
arithmetic and none of production's authority: the same capture must produce
the same price, the same share count, the same market capitalisation and the
same enterprise value, while the two disagree about whether the figure may
be published at all.

These tests pin that separation. They check the isolation from both sides:
the research side may never claim production standing, and the production
side may never change because a research lane exists.
"""
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from historical_income import HistoricalIncomeConfig
from historical_multiples import (
    ISSUER_CONFIGS,
    HistoricalMultiplesConfig,
    load_issuer_historical_multiples,
)
from research_lane import (
    BRIDGE_SIGN_DEBT,
    CLOSED_REASON_CODES,
    FORMULA_BRIDGE_COMPONENT,
    FORMULA_DEPRECIATION,
    FORMULA_DENOMINATOR,
    FORMULA_OPERATING_INCOME,
    FORMULA_SHARES,
    REASON_INCOMPLETE_EV_BRIDGE,
    REASON_MIXED_BALANCE_SHEET_PERIODS,
    REASON_NO_DENOMINATOR_WINDOW,
    ResearchDistribution,
    ResearchLaneConfig,
    ResearchRole,
    assert_research_isolation,
    load_research_lane,
)
from research_lane_ko import (
    CAPTURE_DIR,
    CANDIDATE_LANE_IDS,
    LANE_CONFIGS,
    build_ko_research_lanes,
    write_ko_research_outputs,
)

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "data" / "research_lanes" / "KO"

# The number the Phase 9.1 audit reported for KO's enterprise-value figure and
# that could not be reproduced from the filed inputs. It is assembled from
# parts so that this test file does not itself carry it.
UNATTRIBUTED_NUMBER = "24.492" + "136"

# The production payload digests, pinned before the research lane existed.
# A research lane must not move them.
PRODUCTION_PAYLOAD_DIGESTS = {
    "AAPL": "ef7da465e7422f3e9429e2160be69ea5c3aeacbbd9bf1c77d000eec9f7b1b311",
    "AEP": "b9a53553bd9ebb75d0b25156520c842f05d32478933c049c8ed0b353ed1ed2e0",
    "MSFT": "a3f5d4e851848b71a9feb03abc35db5d884417dc355c38ea24bdf54fe7f3db2d",
}


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# The trees the research lane could plausibly write to: the research capture,
# the research results, and the versioned production datasets. The live
# archive directory is not among them: it holds SQLite databases that other
# tests open, and a file locked by another process is not a write by the
# lane.
VERSIONED_DATA_TREES = (
    "data/research_multiples",
    "data/research_lanes",
    "data/historical_pe",
    "data/historical_multiples",
    "data/historical_income",
    "data/historical_pfcf",
)


def _tree_digest(root: Path) -> str:
    """A digest over every file under a directory, path and content."""
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            entries.append(
                f"{path.relative_to(root).as_posix()}:{_sha256_of(path)}"
            )
    return hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()


def _versioned_data_digest() -> str:
    """A digest over the versioned data trees."""
    entries = []
    for name in VERSIONED_DATA_TREES:
        directory = ROOT / name
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                entries.append(
                    f"{path.relative_to(ROOT).as_posix()}:{_sha256_of(path)}"
                )
    return hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()


def _production_shaped_capture(target: Path) -> HistoricalMultiplesConfig:
    """
    A production-shaped view of the research capture.

    The research capture holds a role's element chronology in one file; the
    production loader reads one element per file. The view is built here, in
    a temporary directory, so that the production arithmetic can be run over
    the same filed facts the research lane reads. The acceptance index is
    mapped onto the field the production loader expects, which is the
    research capture's effective acceptance datetime.
    """
    income_dir = target / "income"
    multiples_dir = target / "multiples"
    for directory in (income_dir, multiples_dir):
        directory.mkdir(parents=True, exist_ok=True)

    def element_of(role: str, tag: str) -> dict:
        document = json.loads(
            (CAPTURE_DIR / f"{role}_concept.json").read_text(encoding="utf-8")
        )
        for element in document["elements"]:
            if element["tag"] == tag:
                return element
        raise AssertionError(f"{role} does not carry {tag}")

    for role, tag in (
        ("revenue", "Revenues"),
        ("operating_income", "OperatingIncomeLoss"),
        ("depreciation", "DepreciationDepletionAndAmortization"),
    ):
        (income_dir / f"{role}_concept.json").write_text(
            json.dumps(element_of(role, tag), sort_keys=True), encoding="utf-8"
        )
    for component, role, tag in (
        ("cash", "cash", "CashAndCashEquivalentsAtCarryingValue"),
        (
            "marketable_securities_current",
            "marketable_securities_current",
            "MarketableSecuritiesCurrent",
        ),
        ("commercial_paper", "commercial_paper", "CommercialPaper"),
        (
            "long_term_debt_noncurrent",
            "long_term_debt_noncurrent",
            "LongTermDebtNoncurrent",
        ),
        (
            "long_term_debt_current",
            "long_term_debt_current",
            "LongTermDebtCurrent",
        ),
    ):
        (multiples_dir / f"{component}_concept.json").write_text(
            json.dumps(element_of(role, tag), sort_keys=True), encoding="utf-8"
        )

    acceptance = json.loads(
        (CAPTURE_DIR / "filing_acceptance_evidence.json").read_text(encoding="utf-8")
    )
    for row in acceptance:
        row["acceptance_datetime_header_et"] = row["acceptance_datetime_effective_et"]
    acceptance_path = target / "filing_acceptance_evidence.json"
    acceptance_path.write_text(json.dumps(acceptance), encoding="utf-8")

    shares_path = target / "shares_outstanding_concept.json"
    shares_path.write_text(
        json.dumps(
            element_of("shares_outstanding", "EntityCommonStockSharesOutstanding"),
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    return HistoricalMultiplesConfig(
        ticker="KO",
        issuer_id="CIK0000021344",
        entity_name="The Coca-Cola Company",
        fye_month=12,
        data_dir=multiples_dir,
        prices_path=CAPTURE_DIR / "daily_prices.json",
        acceptance_path=acceptance_path,
        shares_path=shares_path,
        income_config=HistoricalIncomeConfig(
            ticker="KO",
            issuer_id="CIK0000021344",
            entity_name="The Coca-Cola Company",
            fye_month=12,
            data_dir=income_dir,
            prices_path=CAPTURE_DIR / "daily_prices.json",
            acceptance_path=acceptance_path,
            revenue_concept="Revenues",
            operating_income_concept="OperatingIncomeLoss",
            depreciation_concept="DepreciationDepletionAndAmortization",
        ),
        balance_sheet_concepts={
            "cash": "CashAndCashEquivalentsAtCarryingValue",
            "marketable_securities_current": "MarketableSecuritiesCurrent",
            "commercial_paper": "CommercialPaper",
            "long_term_debt_noncurrent": "LongTermDebtNoncurrent",
            "long_term_debt_current": "LongTermDebtCurrent",
        },
    )


class TheIsolation(unittest.TestCase):
    """The research lane may not take a production name."""

    def test_the_research_ids_do_not_collide_with_production_names(self):
        evidence = assert_research_isolation(
            [config.metric_id for config in LANE_CONFIGS]
        )
        self.assertEqual(evidence["collisions"], [])
        self.assertIn("PRODUCTION_PS_MEDIAN", evidence["production_reference_bases"])
        self.assertIn(
            "PRODUCTION_EV_EBITDA_MEDIAN", evidence["production_reference_bases"]
        )
        for metric_id in evidence["research_metric_ids"]:
            self.assertTrue(metric_id.startswith("RESEARCH_"))

    def test_a_colliding_id_is_refused(self):
        for name in ("PRODUCTION_PS_MEDIAN", "P_S_RATIO_REFERENCE"):
            with self.assertRaises(ValueError):
                assert_research_isolation([name])

    def test_every_distribution_is_not_production_eligible(self):
        for result in build_ko_research_lanes():
            self.assertIs(result.distribution.production_eligible, False)

    def test_the_flag_cannot_be_set_at_construction(self):
        with self.assertRaises(TypeError):
            ResearchDistribution(
                metric_id="RESEARCH_X",
                metric_label="x",
                research_use_label="x",
                lane_id="x",
                issuer_id="x",
                instrument_id="x",
                production_eligible=True,
            )

    def test_the_flag_cannot_be_changed_after_construction(self):
        distribution = ResearchDistribution(
            metric_id="RESEARCH_X",
            metric_label="x",
            research_use_label="x",
            lane_id="x",
            issuer_id="x",
            instrument_id="x",
        )
        with self.assertRaises(Exception):
            distribution.production_eligible = True

    def test_no_production_module_imports_the_research_lane(self):
        for name in (
            "archive.py",
            "investment_context.py",
            "st_eva_runner.py",
            "historical_multiples.py",
            "historical_income.py",
            "semantic_qualification.py",
        ):
            source = (ROOT / name).read_text(encoding="utf-8")
            self.assertNotIn("research_lane", source, f"{name} references the lane")

    def test_the_research_outputs_carry_no_production_reference_rows(self):
        for path in sorted(OUTPUT_DIR.glob("*.json")):
            document = json.loads(path.read_text(encoding="utf-8"))
            keys = json.dumps(document)
            self.assertNotIn("refc:", keys)
            isolation = (document.get("capture_manifest") or {}).get("isolation")
            if isolation:
                # The check's evidence names the production bases it compared
                # against. It must record that nothing collided.
                self.assertEqual(isolation["collisions"], [])
            distribution = document.get("distribution")
            if distribution:
                self.assertIs(distribution["production_eligible"], False)


class TheCapture(unittest.TestCase):
    """The capture is versioned, hashed and read-only."""

    def test_every_capture_file_matches_its_recorded_hash(self):
        manifest = json.loads(
            (CAPTURE_DIR / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertTrue(manifest["files"])
        for name, entry in manifest["files"].items():
            path = CAPTURE_DIR / name
            self.assertTrue(path.exists(), f"{name} is missing from the capture")
            self.assertEqual(_sha256_of(path), entry["sha256"], name)
            self.assertTrue(entry["source"].get("url"), name)
            self.assertTrue(entry["source"].get("retrieval"), name)

    def test_the_capture_names_a_source_and_a_role_for_each_file(self):
        manifest = json.loads(
            (CAPTURE_DIR / "manifest.json").read_text(encoding="utf-8")
        )
        for name, entry in manifest["files"].items():
            self.assertIn("role", entry, name)
            self.assertIn("source", entry, name)

    def test_the_capture_lives_under_no_production_path(self):
        for path in CAPTURE_DIR.rglob("*"):
            self.assertNotIn("historical_pe", path.parts)
            self.assertNotIn("historical_multiples", path.parts)
            self.assertNotIn("historical_income", path.parts)
            self.assertNotIn("historical_pfcf", path.parts)

    def test_the_capture_holds_only_the_files_the_lanes_read(self):
        manifest = json.loads(
            (CAPTURE_DIR / "manifest.json").read_text(encoding="utf-8")
        )
        declared = set(manifest["files"])
        expected = {
            "daily_prices.json",
            "filing_acceptance_evidence.json",
            "shares_outstanding_concept.json",
            "revenue_concept.json",
            "operating_income_concept.json",
            "depreciation_concept.json",
            "cash_concept.json",
            "marketable_securities_current_concept.json",
            "commercial_paper_concept.json",
            "notes_and_loans_payable_concept.json",
            "long_term_debt_noncurrent_concept.json",
            "long_term_debt_current_concept.json",
        }
        self.assertEqual(declared, expected)

    def test_running_the_lanes_leaves_the_capture_unchanged(self):
        before = _tree_digest(CAPTURE_DIR)
        build_ko_research_lanes()
        self.assertEqual(_tree_digest(CAPTURE_DIR), before)

    def test_the_lane_writes_nothing_outside_the_directory_it_is_given(self):
        repo_before = _versioned_data_digest()
        with tempfile.TemporaryDirectory() as directory:
            write_ko_research_outputs(Path(directory))
            written = sorted(path.name for path in Path(directory).iterdir())
            self.assertEqual(len(written), len(LANE_CONFIGS) + 1)
        self.assertEqual(_versioned_data_digest(), repo_before)


class TheProductionArithmetic(unittest.TestCase):
    """The lane and production compute the same figures on the same facts."""

    @classmethod
    def setUpClass(cls):
        cls.results = {
            result.lane_id: result for result in build_ko_research_lanes()
        }
        with tempfile.TemporaryDirectory() as directory:
            cls.config = _production_shaped_capture(Path(directory))
            cls.production = load_issuer_historical_multiples(cls.config).to_dict()

    def test_ko_has_no_production_reference(self):
        distributions = self.production["distributions"]
        for name in ("P_S_RATIO_REFERENCE", "EV_EBITDA_RATIO_REFERENCE"):
            self.assertEqual(distributions[name]["status"], "UNAVAILABLE")
            self.assertEqual(distributions[name]["sample_count"], 0)

    def test_the_price_shares_and_market_cap_match_production(self):
        lane = self.results["ko_reported_revenue_multiple"]
        production = {
            observation["evaluation_date"]: observation
            for observation in self.production["observations"]
        }
        compared = 0
        for observation in lane.observations:
            other = production[observation.evaluation_date]
            self.assertEqual(observation.price, other["price"])
            self.assertEqual(
                observation.shares_outstanding, other["shares_outstanding"]
            )
            self.assertEqual(observation.market_cap, other["market_cap"])
            compared += 1
        self.assertEqual(compared, len(lane.observations))

    def test_the_enterprise_value_matches_production_where_both_are_complete(self):
        lane = self.results["ko_filed_ev_bridge_multiple_production_shape"]
        production = {
            observation["evaluation_date"]: observation
            for observation in self.production["observations"]
        }
        compared = 0
        for observation in lane.observations:
            other = production[observation.evaluation_date]
            production_bridge = other.get("ev_bridge") or {}
            if not production_bridge.get("complete"):
                continue
            self.assertEqual(
                observation.enterprise_value, other["enterprise_value"]
            )
            compared += 1
        self.assertGreater(compared, 0)

    def test_the_production_payloads_are_unchanged(self):
        from historical_pe import canonical_json_hash

        for ticker, digest in PRODUCTION_PAYLOAD_DIGESTS.items():
            payload = load_issuer_historical_multiples(
                ISSUER_CONFIGS[ticker]
            ).to_dict()
            self.assertEqual(canonical_json_hash(payload), digest, ticker)


class TheLanes(unittest.TestCase):
    """The four candidate lanes and the one diagnostic."""

    @classmethod
    def setUpClass(cls):
        cls.results = {result.lane_id: result for result in build_ko_research_lanes()}

    def test_the_lane_counts_and_medians(self):
        # The medians follow the capture's acceptance times. The FY2018,
        # FY2019 and FY2022 annual filings were accepted between 16:00 and
        # 17:00 Eastern, so they became knowable on the next trading day
        # rather than on the day they were accepted. Lanes B and C1 publish
        # an observation on each of those dates, so their medians moved when
        # the capture's acceptance instants were corrected.
        expected = {
            "ko_reported_revenue_multiple": (29, 6.403373),
            "ko_reported_operating_denominator_multiple": (64, 19.774421),
            "ko_filed_ev_bridge_multiple_production_shape": (27, 23.654283),
            "ko_filed_ev_bridge_multiple_short_term_borrowings": (29, 24.675484),
        }
        for lane_id, (count, median) in expected.items():
            distribution = self.results[lane_id].distribution
            self.assertEqual(distribution.sample_count, count, lane_id)
            self.assertEqual(distribution.total_evaluations, 67, lane_id)
            self.assertAlmostEqual(
                distribution.percentiles["median"], median, places=6, msg=lane_id
            )

    def test_the_statistics_recompute_from_the_observations(self):
        for result in self.results.values():
            values = sorted(
                observation.value
                for observation in result.observations
                if observation.value is not None
            )
            self.assertEqual(len(values), result.distribution.sample_count)
            position = (len(values) - 1) * 0.5
            lower = int(position)
            upper = min(lower + 1, len(values) - 1)
            weight = position - lower
            median = values[lower] * (1 - weight) + values[upper] * weight
            self.assertAlmostEqual(
                result.distribution.percentiles["median"], median, places=6
            )

    def test_the_valid_and_refused_counts_add_up(self):
        for result in self.results.values():
            distribution = result.distribution
            self.assertEqual(
                distribution.sample_count + len(distribution.excluded_observations),
                distribution.total_evaluations,
            )

    def test_the_diagnostic_lane_is_not_a_candidate(self):
        diagnostic = self.results[
            "ko_filed_ev_bridge_multiple_double_counted_diagnostic"
        ]
        self.assertFalse(diagnostic.candidate_metric)
        self.assertFalse(diagnostic.distribution.candidate_metric)
        self.assertNotIn(
            "ko_filed_ev_bridge_multiple_double_counted_diagnostic",
            CANDIDATE_LANE_IDS,
        )

    def test_the_candidate_lanes_are_the_four_named_metrics(self):
        self.assertEqual(len(CANDIDATE_LANE_IDS), 4)
        for lane_id in CANDIDATE_LANE_IDS:
            self.assertTrue(self.results[lane_id].candidate_metric)

    def test_the_diagnostic_overstates_the_short_term_borrowings_lane(self):
        diagnostic = {
            observation.evaluation_date: observation.value
            for observation in self.results[
                "ko_filed_ev_bridge_multiple_double_counted_diagnostic"
            ].observations
            if observation.value is not None
        }
        correct = {
            observation.evaluation_date: observation.value
            for observation in self.results[
                "ko_filed_ev_bridge_multiple_short_term_borrowings"
            ].observations
            if observation.value is not None
        }
        shared = sorted(set(diagnostic) & set(correct))
        self.assertTrue(shared)
        for day in shared:
            self.assertGreater(diagnostic[day], correct[day], day)

    def test_every_observation_carries_its_lineage(self):
        for result in self.results.values():
            for observation in result.observations:
                self.assertTrue(observation.input_set_id)
                self.assertTrue(observation.content_hash)
                self.assertEqual(observation.methodology, "research-multiples/1.0")
                self.assertEqual(observation.formula["formula_version"], "research-multiples/1.0")
                if observation.value is None:
                    continue
                self.assertIsNotNone(observation.price)
                self.assertIsNotNone(observation.shares_outstanding)
                self.assertTrue(observation.shares_accession)
                self.assertTrue(observation.denominator)
                for quarter in observation.denominator["quarters"]:
                    self.assertTrue(quarter["accessions"])
                    self.assertTrue(quarter["knowable_from"])
                    self.assertTrue(quarter["input_spans"])
                for component in (observation.bridge.get("components") or {}).values():
                    self.assertTrue(component["accession"])
                    self.assertTrue(component["usable_date"])
                    self.assertTrue(component["content_sha256"])
                    self.assertIn("USD", component["currency"])

    def test_the_registry_standing_is_recorded_on_every_observation(self):
        for result in self.results.values():
            for observation in result.observations:
                self.assertTrue(observation.registry_standing)
                for role, standing in observation.registry_standing.items():
                    self.assertTrue(standing)
                    for record in standing.values():
                        self.assertIn(
                            record["registry_decision"],
                            ("QUALIFIED", "NOT_QUALIFIED", "NOT_APPLICABLE"),
                        )

    def test_every_exclusion_carries_a_closed_reason_code_and_a_readable_reason(self):
        for result in self.results.values():
            for item in result.distribution.excluded_observations:
                self.assertIn(item["reason_code"], CLOSED_REASON_CODES)
                self.assertTrue(item["reason_detail"])
                self.assertGreater(len(item["reason_detail"]), 20)

    def test_the_same_input_produces_the_same_identity(self):
        first = build_ko_research_lanes()
        second = build_ko_research_lanes()
        for left, right in zip(first, second):
            self.assertEqual(left.input_set_id, right.input_set_id)
            self.assertEqual(left.content_hash, right.content_hash)

    def test_the_committed_outputs_match_a_fresh_run(self):
        index = json.loads(
            (OUTPUT_DIR / "manifest.json").read_text(encoding="utf-8")
        )
        for lane_id, entry in index["lanes"].items():
            result = self.results[lane_id]
            self.assertEqual(entry["input_set_id"], result.input_set_id)
            self.assertEqual(entry["content_hash"], result.content_hash)
            self.assertEqual(entry["sample_count"], result.distribution.sample_count)


class TheRefusals(unittest.TestCase):
    """A lane refuses what production refuses."""

    def test_a_window_that_cannot_be_formed_is_not_admitted(self):
        # An instant element cannot make a trailing window. The lane must
        # refuse every observation rather than treat the absence as zero.
        config = ResearchLaneConfig(
            lane_id="ko_instant_denominator_probe",
            issuer_id="CIK0000021344",
            instrument_id="KO",
            entity_name="The Coca-Cola Company",
            fye_month=12,
            capture_dir=CAPTURE_DIR,
            metric_id="RESEARCH_KO_INSTANT_DENOMINATOR_PROBE",
            metric_label="probe",
            research_purpose="A probe that must refuse every observation.",
            formula_expression="probe",
            formula_numerator="probe",
            formula_denominator="probe",
            denominator_roles=("probe_instant",),
            roles=(
                ResearchRole(
                    name="operating_income",
                    taxonomy="us-gaap",
                    elements=("OperatingIncomeLoss",),
                    formula_role="OPERATING_INCOME",
                    registry_metric_id="operating_income",
                ),
                ResearchRole(
                    name="depreciation",
                    taxonomy="us-gaap",
                    elements=("DepreciationDepletionAndAmortization",),
                    formula_role="DEPRECIATION",
                    registry_metric_id="depreciation_and_amortization",
                ),
                ResearchRole(
                    name="probe_instant",
                    taxonomy="us-gaap",
                    elements=("CommercialPaper",),
                    formula_role=FORMULA_DENOMINATOR,
                    registry_metric_id="commercial_paper",
                ),
            ),
        )
        result = load_research_lane(config)
        self.assertEqual(result.distribution.sample_count, 0)
        self.assertEqual(result.distribution.status, "RESEARCH_UNAVAILABLE")
        for observation in result.observations:
            self.assertIsNone(observation.value)
            self.assertEqual(observation.reason_code, REASON_NO_DENOMINATOR_WINDOW)

    def test_a_missing_bridge_component_is_not_admitted(self):
        # A bridge component the issuer stopped filing is a gap in the
        # bridge, not a zero, and the lane must refuse the enterprise value.
        config = ResearchLaneConfig(
            lane_id="ko_partial_bridge_component_probe",
            issuer_id="CIK0000021344",
            instrument_id="KO",
            entity_name="The Coca-Cola Company",
            fye_month=12,
            capture_dir=CAPTURE_DIR,
            metric_id="RESEARCH_KO_PARTIAL_BRIDGE_COMPONENT_PROBE",
            metric_label="probe",
            research_purpose="A probe that must refuse the enterprise value.",
            formula_expression="probe",
            formula_numerator="probe",
            formula_denominator="probe",
            denominator_roles=("operating_income", "depreciation"),
            numerator_kind="enterprise_value",
            roles=(
                ResearchRole(
                    name="operating_income",
                    taxonomy="us-gaap",
                    elements=("OperatingIncomeLoss",),
                    formula_role="OPERATING_INCOME",
                    registry_metric_id="operating_income",
                ),
                ResearchRole(
                    name="depreciation",
                    taxonomy="us-gaap",
                    elements=("DepreciationDepletionAndAmortization",),
                    formula_role="DEPRECIATION",
                    registry_metric_id="depreciation_and_amortization",
                ),
                ResearchRole(
                    name="cash",
                    taxonomy="us-gaap",
                    elements=("CashAndCashEquivalentsAtCarryingValue",),
                    formula_role=FORMULA_BRIDGE_COMPONENT,
                    registry_metric_id="cash",
                    bridge_sign="LIQUID_FUNDS",
                ),
                ResearchRole(
                    name="probe_notes",
                    taxonomy="us-gaap",
                    elements=("NotesAndLoansPayableCurrent",),
                    formula_role=FORMULA_BRIDGE_COMPONENT,
                    registry_metric_id=None,
                    bridge_sign=BRIDGE_SIGN_DEBT,
                ),
                ResearchRole(
                    name="shares_outstanding",
                    taxonomy="dei",
                    elements=("EntityCommonStockSharesOutstanding",),
                    formula_role="SHARES",
                    registry_metric_id=None,
                ),
            ),
        )
        result = load_research_lane(config)
        refusals = 0
        for observation in result.observations:
            if observation.value is not None:
                continue
            refusals += 1
            self.assertIn(
                observation.reason_code,
                (
                    REASON_INCOMPLETE_EV_BRIDGE,
                    REASON_MIXED_BALANCE_SHEET_PERIODS,
                    REASON_NO_DENOMINATOR_WINDOW,
                ),
            )
        self.assertGreater(refusals, 0)
        # Where the component is missing the lane says so by name.
        absent = [
            observation
            for observation in result.observations
            if observation.value is None
            and "probe_notes" in (observation.bridge.get("components_absent") or [])
        ]
        self.assertTrue(absent)

    def test_no_published_observation_uses_a_fact_that_was_not_yet_known(self):
        for result in build_ko_research_lanes():
            for observation in result.observations:
                day = observation.evaluation_date
                for quarter in (observation.denominator or {}).get("quarters", []):
                    for span in quarter["input_spans"]:
                        self.assertLessEqual(span["usable_date"], day)
                for component in (observation.bridge.get("components") or {}).values():
                    self.assertLessEqual(component["usable_date"], day)
                if observation.shares_accession:
                    self.assertLessEqual(observation.shares_usable_date, day)

    def test_no_published_observation_carries_a_discontinuous_window(self):
        for result in build_ko_research_lanes():
            for observation in result.observations:
                if observation.value is None:
                    continue
                positions = observation.denominator["positions"]
                self.assertEqual(len(positions), 4)
                for left, right in zip(positions, positions[1:]):
                    if right["fiscal_quarter"] == 1:
                        self.assertEqual(left["fiscal_quarter"], 4)
                        self.assertEqual(left["fiscal_year"] + 1, right["fiscal_year"])
                    else:
                        self.assertEqual(
                            left["fiscal_quarter"] + 1, right["fiscal_quarter"]
                        )
                        self.assertEqual(left["fiscal_year"], right["fiscal_year"])

    def test_no_published_enterprise_value_spans_two_balance_sheets(self):
        result = next(
            result
            for result in build_ko_research_lanes()
            if result.lane_id == "ko_filed_ev_bridge_multiple_production_shape"
        )
        for observation in result.observations:
            if observation.value is None:
                continue
            self.assertTrue(observation.bridge["complete"])
            self.assertEqual(
                len(observation.bridge["distinct_period_ends"]), 1
            )
            self.assertEqual(observation.bridge["components_absent"], [])


class TheBasisBreaks(unittest.TestCase):
    """What changed in the evidence is recorded, not absorbed."""

    @classmethod
    def setUpClass(cls):
        cls.results = {result.lane_id: result for result in build_ko_research_lanes()}

    def test_the_prior_period_value_revisions_are_recorded(self):
        revisions = self.results[
            "ko_reported_revenue_multiple"
        ].distribution.prior_period_revisions
        self.assertTrue(revisions)
        for revision in revisions:
            self.assertEqual(
                revision["classification"], "PRIOR_PERIOD_VALUE_REVISION"
            )
            self.assertNotEqual(revision["old_value"], revision["new_value"])
            self.assertTrue(revision["old_accession"])
            self.assertTrue(revision["new_accession"])
            self.assertTrue(revision["old_usable_date"])
            self.assertTrue(revision["new_usable_date"])
            self.assertAlmostEqual(
                revision["difference"],
                revision["new_value"] - revision["old_value"],
            )
            self.assertIn("affected_observation_count", revision)

    def test_the_coca_cola_beverages_africa_revision_is_recorded(self):
        revisions = self.results[
            "ko_reported_revenue_multiple"
        ].distribution.prior_period_revisions
        annual = {
            revision["period_end"]: revision
            for revision in revisions
            if revision["period_start"].endswith("01-01")
            and revision["period_end"].endswith("12-31")
        }
        self.assertIn("2018-12-31", annual)
        self.assertIn("2017-12-31", annual)
        self.assertAlmostEqual(
            annual["2018-12-31"]["difference"], 2444000000.0, places=2
        )
        self.assertAlmostEqual(
            annual["2017-12-31"]["difference"], 802000000.0, places=2
        )
        self.assertGreater(annual["2018-12-31"]["difference_ratio"], 0.07)

    def test_a_first_appearance_is_not_a_revision(self):
        for result in self.results.values():
            for revision in result.distribution.prior_period_revisions:
                self.assertTrue(revision["old_accession"])
                self.assertNotEqual(
                    revision["old_accession"], revision["new_accession"]
                )

    def test_the_marketable_securities_element_change_is_recorded(self):
        result = self.results["ko_filed_ev_bridge_multiple_production_shape"]
        notes = " ".join(
            note for observation in result.observations for note in observation.basis_breaks
        )
        self.assertIn("MarketableSecurities", notes)
        self.assertIn("marketable_securities_current", notes)

    def test_the_long_term_debt_scope_change_is_recorded(self):
        result = self.results["ko_filed_ev_bridge_multiple_production_shape"]
        notes = " ".join(
            note for observation in result.observations for note in observation.basis_breaks
        )
        self.assertIn("LongTermDebtAndCapitalLeaseObligations", notes)
        self.assertIn("scope change", notes)

    def test_the_bridge_records_the_element_change_it_reads(self):
        result = self.results["ko_filed_ev_bridge_multiple_production_shape"]
        seen = set()
        for observation in result.observations:
            component = (observation.bridge.get("components") or {}).get(
                "marketable_securities_current"
            )
            if component:
                seen.add(component["element"])
        self.assertIn("us-gaap:MarketableSecuritiesCurrent", seen)
        self.assertIn("us-gaap:MarketableSecurities", seen)


class TheUnattributedNumber(unittest.TestCase):
    """A number that could not be reproduced is not published as an expectation."""

    def test_the_number_appears_in_no_research_output(self):
        for path in sorted(OUTPUT_DIR.glob("*.json")):
            self.assertNotIn(UNATTRIBUTED_NUMBER, path.read_text(encoding="utf-8"))

    def test_the_number_appears_in_no_source_or_document(self):
        for path in sorted(ROOT.glob("*.py")):
            self.assertNotIn(UNATTRIBUTED_NUMBER, path.read_text(encoding="utf-8"))
        for path in sorted((ROOT / "docs").glob("*.md")):
            self.assertNotIn(UNATTRIBUTED_NUMBER, path.read_text(encoding="utf-8"))

    def test_the_number_is_not_a_lane_expectation(self):
        for result in build_ko_research_lanes():
            median = result.distribution.percentiles.get("median")
            if median is None:
                continue
            self.assertNotAlmostEqual(median, float(UNATTRIBUTED_NUMBER), places=6)


if __name__ == "__main__":
    unittest.main()
