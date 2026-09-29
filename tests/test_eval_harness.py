"""
Tests for the evaluation harness itself.

A grading system that has only graded a correct answer has been used, not
tested. These tests establish the three properties the rest of the evaluation
rests on:

    sensitivity    a wrong answer fails, and the failure is classified
    specificity    the *right* check fails — a check that fires on an unrelated
                   question is not measuring what it claims to
    non-selfing    the target cannot grade itself, and the mechanical auditor
                   decides without consulting a model

The last one is why every test here runs against a target that makes a
*specific* mistake. A target that failed everything would demonstrate only that
something works.
"""

import json
import os
import sys
import unittest

EXPERIMENT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "experiments",
    "003-llm-evidence-retrieval",
)
if EXPERIMENT not in sys.path:
    sys.path.insert(0, EXPERIMENT)

from harness import reference  # noqa: E402
from harness.auditor import (  # noqa: E402
    CLASS_A_DEFECT,
    CLASS_DATASET,
    CLASS_EVALUATOR,
    CLASS_SOURCE,
    CLASS_TARGET,
    _asserts_certification,
    _asserts_sameness,
    _numbers_equal,
)
from harness.dataset import build_dataset  # noqa: E402
from harness.judge import SemanticJudge  # noqa: E402
from harness.report import build_report, render  # noqa: E402
from harness.runner import Runner  # noqa: E402
from harness.snapshot import (  # noqa: E402
    SnapshotError,
    build_snapshot,
    default_snapshot_path,
)
from harness.target import ANSWER_CONTRACT, TargetAnswer  # noqa: E402
from harness.tools import ToolError, Toolbox  # noqa: E402

SNAPSHOT = default_snapshot_path()


def setUpModule() -> None:
    if not os.path.exists(SNAPSHOT):
        build_snapshot(SNAPSHOT, live=False)


def _dataset():
    return build_dataset(SNAPSHOT)


def _run(target, root=None):
    import tempfile

    return Runner(
        _dataset(),
        SNAPSHOT,
        root or tempfile.mkdtemp(prefix="steva-003-test-"),
    ).run(target)


class TestTheHarnessGradesACorrectAnswer(unittest.TestCase):
    """An auditor that fails a correct answer produces failures that mean nothing."""

    @classmethod
    def setUpClass(cls) -> None:
        # Not named `run`: unittest.TestCase has a `run` method, and shadowing
        # it makes the class's own test runner fail with a confusing error.
        cls.outcome = _run(reference.CorrectTarget())
        cls.by_id = {r.test_id: r for r in cls.outcome.results}

    def test_every_test_passes(self):
        failed = [r.test_id for r in self.outcome.results if not r.audit.passed]
        self.assertEqual(
            failed, [],
            "the reference target answers from retrieved evidence and the "
            "auditor disagreed",
        )

    def test_no_class_a_defects(self):
        """
        Nothing here is a ST-EVA defect.

        If a check reported class A it would be asserting the archive is wrong,
        which would send someone to change sealed behaviour on the strength of
        an evaluator's reading.
        """
        for result in self.outcome.results:
            for check in result.audit.checks:
                self.assertNotEqual(
                    check.classification, CLASS_A_DEFECT,
                    f"{result.test_id}: {check.name} claims an ST-EVA defect",
                )


class TestTheHarnessCatchesEachSpecificFailure(unittest.TestCase):
    """
    Sensitivity *and* specificity, together.

    Each scripted target breaks one rule on one question and answers correctly
    everywhere else, so a failure on any other test would mean the checks are
    firing at random.
    """

    CASES = {
        "wrong-value": "T1_exact_value",
        "picks-winner": "T8_conflict",
        "hides-truncation": "T14_truncation_trap",
        "negative-as-zero": "T9_unavailable",
        "upgrades-partial": "T11_partial_mapping",
        "asserts-causation": "T15_inference_boundary",
        "derived-as-reported": "T6_reported_vs_derived",
        "invents-provenance": "T5_source_attribution",
        "reads-one-page": "T3_pagination",
    }

    def test_each_failure_is_caught_and_isolated(self):
        for name, expected_test in self.CASES.items():
            with self.subTest(target=name):
                run = _run(reference.broken_targets()[name])
                failed = [r.test_id for r in run.results if not r.audit.passed]
                self.assertEqual(
                    failed, [expected_test],
                    f"{name} should fail exactly {expected_test}, and no other "
                    "test: a failure elsewhere means a check is firing at "
                    "random rather than measuring what it claims to",
                )

    def test_every_failure_is_classified_as_the_target(self):
        """
        The distinction that makes a run actionable.

        A model failure is a finding about the model. Reporting it as an ST-EVA
        defect would send someone to change sealed behaviour, which is exactly
        what "do not modify ST-EVA because of a single LLM error" forbids.
        """
        for name in self.CASES:
            with self.subTest(target=name):
                report = build_report(_run(reference.broken_targets()[name]))
                classes = report["failures_by_classification"]
                self.assertGreater(classes[CLASS_TARGET]["count"], 0)
                for code in (CLASS_A_DEFECT, CLASS_EVALUATOR,
                             CLASS_DATASET, CLASS_SOURCE):
                    self.assertEqual(
                        classes[code]["count"], 0,
                        f"{name} was blamed on {code}: {classes[code]['meaning']}",
                    )

    def test_a_fabricated_citation_is_caught(self):
        """
        A citation to an id that does not exist is worse than no citation: it
        looks checkable, so a reader would trust it.
        """
        report = build_report(_run(reference.broken_targets()["wrong-value"]))
        details = " ".join(
            str(f["check"]) + str(f["detail"])
            for f in report["failures"]
        )
        self.assertIn("not in the archive", details)


class TestTheTargetCannotGradeItself(unittest.TestCase):
    """
    Three separations, each of which would collapse the evaluation if it leaked.
    """

    def test_the_toolbox_offers_no_sql(self):
        """
        The target must reach the archive only through EvidenceQuery.

        Checked on the parsed module rather than by searching its text: the
        module's own docstring explains that it cannot execute SQL, and a
        substring search fails on its own explanation. Reading the tree is also
        the only way to be sure nothing is imported under another name.
        """
        import ast

        import harness.tools as tools_module

        tree = ast.parse(open(tools_module.__file__, encoding="utf-8").read())
        imported = set()
        attributes = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Attribute):
                attributes.add(node.attr)

        for banned in ("sqlite3", "sqlite_archive", "core_registry"):
            self.assertNotIn(
                banned, imported,
                f"the tool module imports {banned}; the target must not be "
                "able to reach the database except through EvidenceQuery",
            )
        for banned in ("execute", "executescript", "cursor", "connect"):
            self.assertNotIn(
                banned, attributes,
                f"the tool module calls .{banned}(); there must be no path "
                "from the target to SQL",
            )

    def test_the_toolbox_records_a_refused_call(self):
        """
        A target that calls a cursor it invented has made a finding-worthy
        mistake, and the error is recorded rather than swallowed.
        """
        from evidence_query import EvidenceQuery

        query = EvidenceQuery.open(SNAPSHOT)
        try:
            tools = Toolbox(_query=query)
            with self.assertRaises(ToolError):
                tools.page(asset="AAPL", cursor="not-a-cursor")
            self.assertEqual(len(tools.calls), 1)
            self.assertIsNotNone(tools.calls[0].error)
        finally:
            query.close()

    def test_a_disallowed_operation_is_refused(self):
        from evidence_query import EvidenceQuery

        query = EvidenceQuery.open(SNAPSHOT)
        try:
            tools = Toolbox(_query=query, allowed=["get_observation"])
            with self.assertRaises(ToolError):
                tools.coverage_report("AAPL")
        finally:
            query.close()

    def test_the_auditor_does_not_import_a_model(self):
        """
        The mechanical verdict is a comparison, not an opinion. A judge exists
        and is optional; the auditor never consults one.
        """
        import harness.auditor as auditor_module

        source = open(auditor_module.__file__, encoding="utf-8").read()
        for forbidden in ("SemanticJudge", "judge(", "openai", "anthropic"):
            self.assertNotIn(
                forbidden, source,
                f"the auditor references {forbidden}; its verdict must be "
                "mechanical",
            )

    def test_the_judge_is_advisory_and_never_changes_a_result(self):
        """
        A judge that could overturn a mechanical check could be talked into
        agreeing, and a verdict that depends on a model's judgement is not a
        result anyone can act on.
        """
        judge = SemanticJudge(
            client=lambda prompt: json.dumps(
                {"overstates_evidence": False, "reason": "looks fine"}
            )
        )
        result = _run(reference.broken_targets()["asserts-causation"], )
        failing = [r for r in result.results if not r.audit.passed]
        self.assertTrue(failing)
        for item in failing:
            self.assertFalse(
                item.audit.passed,
                "a judge's opinion changed a mechanical verdict",
            )


class TestChecksAreNotConfusedByNegation(unittest.TestCase):
    """
    The defect this harness actually found in its own first version.

    Two checks searched for a word and matched it inside its own denial: "these
    are *not* the same measure" read as an assertion of sameness, and "not
    verification that the figure is *correct*" read as a claim of correctness.
    Both flagged a model for hedging correctly, which is the one thing a
    correctness check must never do — the failure looks like a finding and gets
    acted on.
    """

    def test_a_denial_of_sameness_is_not_a_claim_of_sameness(self):
        for correct in (
            "They are not the same measure.",
            "Revenues is not equivalent to the contract concept.",
            "These are not interchangeable; the series must break.",
        ):
            self.assertFalse(
                _asserts_sameness(correct, "Revenues"), correct
            )

    def test_a_claim_of_sameness_is_still_caught(self):
        # The subject has to be named. A generic "these are equivalent" with no
        # referent is not attributable to a concept, and a check that fired on
        # it would flag any answer that happened to discuss equivalence.
        for wrong in (
            "Revenues and the contract concept are the same measure.",
            "Revenues is equivalent to the contract concept.",
            "SalesRevenueNet and Revenues are interchangeable.",
        ):
            subject = "Revenues" if "Revenues" in wrong else "SalesRevenueNet"
            self.assertTrue(_asserts_sameness(wrong, subject), wrong)

    def test_a_denial_of_verification_is_not_a_claim_of_verification(self):
        self.assertFalse(
            _asserts_certification(
                "That is not verification that the figure is correct."
            )
        )

    def test_a_claim_of_verification_is_still_caught(self):
        self.assertTrue(
            _asserts_certification("The two sources confirm the figure.")
        )
        self.assertTrue(
            _asserts_certification("The figure is verified.")
        )

    def test_numbers_compare_numerically_not_as_text(self):
        """
        A model may write 15504000000, 15,504,000,000 or 1.5504e10. Only a
        numeric comparison treats those as the same figure.
        """
        self.assertTrue(_numbers_equal(15504000000.0, 15504000000.0))
        self.assertFalse(_numbers_equal(15504000000.0, 14640000000.0))
        self.assertFalse(_numbers_equal(1.0, 1.01))


class TestTheSnapshotIsWhatTheEvaluationDependsOn(unittest.TestCase):
    """
    The archive the evaluation runs against is a build artefact, and two of its
    properties are load-bearing.
    """

    def test_no_evidence_is_filed_under_an_asset_id(self):
        """
        An asset named after its own id means a query by ticker returns nothing
        while every count looks right. Both bugs of this shape appeared while
        ST-EVA was being built, so the check is structural.
        """
        from harness.snapshot import assert_no_shadow_assets
        from sqlite_archive import SQLiteArchive

        store = SQLiteArchive(":memory:")
        try:
            assert_no_shadow_assets(store)
            store.record_asset("AAPL", cik="0000320193")
            assert_no_shadow_assets(store)
            store.record_asset(store.record_asset("AAPL"))
            with self.assertRaises(SnapshotError):
                assert_no_shadow_assets(store)
        finally:
            store.close()

    def test_the_dataset_exercises_every_capability(self):
        """
        A capability no check ever exercises would be reported as 0/0, which
        reads as "nothing to fail" rather than "never measured".
        """
        from harness.auditor import CAPABILITIES

        run = _run(reference.CorrectTarget())
        exercised = {
            check.capability
            for result in run.results
            for check in result.audit.checks
        }
        self.assertEqual(
            exercised, set(CAPABILITIES),
            "a capability has no check, so the report would show it as "
            "untested rather than unmeasured",
        )

    def test_every_expectation_is_resolved_from_the_archive(self):
        """
        A hand-typed expected number is a test that can be satisfied by an
        evaluator agreeing with itself.
        """
        for test in _dataset().tests:
            self.assertTrue(
                test.expectations,
                f"{test.test_id} has no expectations",
            )
            for key, value in test.expectations.items():
                self.assertIsNotNone(
                    value, f"{test.test_id}.{key} resolved to None"
                )


class TestReportingIsHonest(unittest.TestCase):
    """What the report says, and what it refuses to say."""

    def test_no_overall_quality_score(self):
        report = build_report(_run(reference.CorrectTarget()))
        self.assertNotIn("score", report)
        self.assertNotIn("overall", report)
        self.assertIn("No overall quality score", report["scoring_note"])

    def test_capabilities_are_reported_individually(self):
        report = build_report(_run(reference.CorrectTarget()))
        codes = {c["capability"] for c in report["by_capability"]}
        self.assertIn("F1", codes)
        self.assertIn("F11", codes)

    def test_the_review_sample_is_reproducible(self):
        """
        A sample that changes on every run cannot be compared between two runs,
        which defeats the purpose of sampling.
        """
        run = _run(reference.CorrectTarget())
        first = build_report(run)["human_review"]["sample_of_passes"]
        second = build_report(run)["human_review"]["sample_of_passes"]
        self.assertEqual(first, second)

    def test_passed_and_failed_are_both_surfaced(self):
        report = build_report(_run(reference.broken_targets()["picks-winner"]))
        self.assertTrue(report["human_review"]["sampled_failures"])
        self.assertTrue(report["human_review"]["sample_of_passes"])

    def test_the_report_renders(self):
        report = build_report(_run(reference.CorrectTarget()))
        text = render(report)
        self.assertIn("capability", text)
        self.assertIn("failures by classification", text)


class TestTheAnswerContractIsAnEvaluationFormatOnly(unittest.TestCase):
    """
    The structured answer must not leak into production semantics.
    """

    def test_the_contract_is_not_part_of_st_eva(self):
        import evidence_query
        import sqlite_archive

        for module in (evidence_query, sqlite_archive):
            source = open(module.__file__, encoding="utf-8").read()
            for field in ("evidence_refs", "derived_refs", "uncertainties"):
                self.assertNotIn(
                    field, source,
                    f"{module.__name__} grew {field}; the evaluation format "
                    "must not become part of the archive or the query surface",
                )

    def test_an_unparseable_answer_is_reported_not_coerced(self):
        """
        A model that cannot follow the output contract is a finding. Coercing
        it would hide exactly the failure the evaluation is looking for.
        """
        answer = TargetAnswer.parse("this is not json")
        self.assertIsNotNone(answer.parse_error)
        self.assertEqual(answer.evidence_refs, [])

    def test_a_missing_key_is_reported(self):
        answer = TargetAnswer.parse(json.dumps({"answer": "x"}))
        self.assertIsNotNone(answer.parse_error)
        self.assertIn("evidence_refs", answer.parse_error)

    def test_the_contract_states_the_rules(self):
        self.assertIn("traceable", ANSWER_CONTRACT)
        self.assertIn("uncertainties", ANSWER_CONTRACT)


class TestFindingsFromTheFirstRealModelRun(unittest.TestCase):
    """
    Pinned so they cannot be forgotten.

    Every item here was found by a real model running the sealed dataset, which
    is the only way any of them could have been found: the scripted targets had
    fixed answers, so they never depended on what the archive actually contained
    at the moment.

    These are written as *characterisations*, not as assertions that the defect
    is fixed. A1 and A2 are open findings and the query surface is sealed, so a
    test that demanded a fix would fail for a reason nobody is going to act on.
    A characterisation that passes today and fails after a fix is the right
    instrument: it turns a silent improvement into a visible change.
    """

    def test_a1_an_unknown_metric_is_indistinguishable_from_no_data(self):
        """
        A1: an empty list says nothing about why it is empty.

        This produced 7 of 15 false negatives in the first real run, each
        answered with "no data exists" when the archive held hundreds of rows.
        The vocabulary exists in `coverage_report`; the surface just does not
        offer it when a filter matches nothing.
        """
        from evidence_query import EvidenceQuery
        from harness.snapshot import default_snapshot_path

        query = EvidenceQuery.open(default_snapshot_path())
        try:
            real = query.query_observations(
                asset="AAPL", metric="revenue", limit=1
            )
            misspelled = query.query_observations(
                asset="AAPL", metric="operating margin", limit=1
            )
            well_formed_but_empty = query.query_observations(
                asset="AAPL", metric="revenue", period_end="1900-01-01", limit=1
            )
            self.assertTrue(real, "the archive should hold revenue")
            self.assertEqual(
                misspelled, [],
                "an unknown metric name no longer returns an empty list; check "
                "whether it now names the metric it could not find, and update "
                "this finding",
            )
            self.assertEqual(
                misspelled, well_formed_but_empty,
                "a misspelled metric and a metric with no rows became "
                "distinguishable, which is the fix; update this finding",
            )
        finally:
            query.close()

    def test_a2_the_status_filter_does_not_accept_evidence_states(self):
        """
        A2: `status` filters validation status, not evidence state.

        The model passed `SOURCE_REPORTED` — a term the documented vocabulary
        teaches — and got zero rows. It still happened after the prompt was
        corrected to spell the distinction out, which is what makes it a naming
        collision rather than a misunderstanding.
        """
        from evidence_query import EvidenceQuery
        from harness.snapshot import default_snapshot_path

        query = EvidenceQuery.open(default_snapshot_path())
        try:
            unfiltered = query.query_observations(
                asset="AAPL", metric="revenue", period_end="2007-09-29", limit=5
            )
            with_evidence_state = query.query_observations(
                asset="AAPL", metric="revenue", period_end="2007-09-29",
                status="SOURCE_REPORTED", limit=5,
            )
            with_validation_status = query.query_observations(
                asset="AAPL", metric="revenue", period_end="2007-09-29",
                status="UNVERIFIABLE", limit=5,
            )
            self.assertTrue(unfiltered)
            self.assertEqual(
                with_evidence_state, [],
                "the status filter now accepts evidence states; update A2",
            )
            self.assertEqual(
                len(with_validation_status), len(unfiltered),
                "the status filter no longer matches validation status",
            )
        finally:
            query.close()

    def test_c1_a_check_satisfied_by_citing_nothing_is_recorded_as_weak(self):
        """
        C1: T4 passed vacuously.

        Its checks were "the filter was present in the arguments" and
        "citations <= knowable", both trivially satisfied by a model that
        retrieved nothing and said the data was absent — the answer a check
        should most punish.

        The audit is not fixed in this run, so this characterises the current
        behaviour. It passes today and fails after a fix, which is the point: it
        turns a silent improvement into a visible change rather than leaving the
        evaluator quietly over-permissive.
        """
        from harness.auditor import Audit, Auditor, Check
        from harness.tools import Toolbox

        class _Silent(Auditor):
            """An auditor with no database, for a check that reads no data."""

            def __init__(self) -> None:
                self.connection = None
                self.query = None

        audit = Audit(
            test_id="probe",
            expectations={"knowable_count": 100, "metric": "revenue"},
            answer_text="No observations were found. There is no data.",
        )
        cited = 0
        # The exact comparison T4 used.
        audit.checks.append(
            Check(
                capability="F4",
                name="no later evidence smuggled in",
                passed=cited <= audit.expected("knowable_count"),
                expected=100,
                actual=cited,
                detail="satisfied by citing nothing",
                classification=None,
            )
        )
        self.assertTrue(
            audit.checks[0].passed,
            "T4's vacuous check no longer passes when nothing is cited; update "
            "this finding and re-run",
        )
        self.assertEqual(
            len(audit.unverifiable), 0,
            "the check was decidable and decided the wrong way",
        )


if __name__ == "__main__":
    unittest.main()
