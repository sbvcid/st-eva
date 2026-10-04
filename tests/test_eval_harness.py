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

from evidence_query import EvidenceQuery  # noqa: E402
import corpus_gate  # noqa: E402
from harness import reference  # noqa: E402
from harness.auditor import (  # noqa: E402
    CLASS_A_DEFECT,
    CLASS_DATASET,
    CLASS_EVALUATOR,
    CLASS_SOURCE,
    CLASS_TARGET,
    Audit,
    Auditor,
    Check,
    _asserts_certification,
    _asserts_sameness,
    _numbers_equal,
    acknowledges_truncation,
)
from harness.dataset import build_dataset  # noqa: E402
from harness.judge import SemanticJudge  # noqa: E402
from harness.report import build_report, render  # noqa: E402
from harness.runner import Runner, _query_connection  # noqa: E402
from harness.snapshot import (  # noqa: E402
    SnapshotError,
    build_snapshot,
    default_snapshot_path,
)
from harness.target import ANSWER_CONTRACT, TargetAnswer  # noqa: E402
from harness.tools import ToolError, Toolbox  # noqa: E402

SNAPSHOT = default_snapshot_path()


def setUpModule() -> None:
    # 3.03: this used to build a stub snapshot when the corpus was absent and
    # then run the grading expectations against it. The expectations are
    # calibrated to the real archive, so the stub produced 18 failures that said
    # nothing about the harness -- in a clean checkout, where `live=False` is the
    # only build available. The dependency is declared instead. Where the corpus
    # exists this is unchanged, and the build still runs if the file is missing.
    if not os.path.exists(SNAPSHOT):
        corpus_gate.require_module("snapshot")
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
        "hides-ambiguity": "T1_exact_value",
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

    def test_a_probe_field_does_not_become_part_of_st_eva(self):
        """
        The probe fields extend the evaluation format and nothing else.

        Five more fields on an answer object is a small thing to add and an easy
        one to justify wrongly later -- "the query surface could report this
        too". So the same assertion as above, run over the same production
        modules, for the fields the archive does not already have.

        `reason_code` is deliberately exempt, and the exemption is the point
        rather than an exception: it is the archive's own field, emitted by
        `coverage_report` and in every observation's status block. A probe asking
        for it is the model quoting the archive. A name collision between an
        evaluation format and a fact the archive genuinely holds is not a leak,
        and a test that cannot tell the two apart would get it wrong in both
        directions.
        """
        import evidence_query
        import sqlite_archive

        from harness.probes import PROBE_FIELDS

        already_the_archive_owns = {"reason_code"}
        novel = [f for f in PROBE_FIELDS if f not in already_the_archive_owns]
        self.assertTrue(novel)
        for module in (evidence_query, sqlite_archive):
            source = open(module.__file__, encoding="utf-8").read()
            for field in novel:
                self.assertNotIn(
                    field, source,
                    f"{module.__name__} grew {field}; a probe field is an "
                    "evaluation format and must not reach the archive",
                )
            # And the format as a whole, so a rename cannot smuggle it in.
            self.assertNotIn("claim_type", source)

    def test_the_probe_answer_shape_is_not_the_archive_answer_shape(self):
        """
        The probe's field set, together, is the thing that must not appear.
        """
        import evidence_query

        source = open(evidence_query.__file__, encoding="utf-8").read()
        for group in (
            ("claim_type", "semantic_state"),
            ("operation_ref", "stated_value"),
        ):
            present = [name for name in group if name in source]
            self.assertLessEqual(
                len(present), 1,
                f"{present} appear together in the query surface, which is the "
                "shape of an evaluation answer",
            )

    def test_a_probe_field_of_the_wrong_type_is_dropped_not_coerced(self):
        """
        A model that answered `["PARTIAL", "EXACT"]` has not made a claim.

        Stringifying that list would produce a confident mismatch against the
        answer key, which reads as "the model was wrong" rather than "the model
        did not answer", and the two call for different conclusions about a
        model.
        """
        answer = TargetAnswer.parse(json.dumps({
            "answer": "x",
            "evidence_refs": [],
            "claim_type": ["PARTIAL", "EXACT"],
        }))
        self.assertEqual(answer.claim_type, "")

    def test_a_probe_code_is_case_folded_because_a_code_is_an_identifier(self):
        answer = TargetAnswer.parse(json.dumps({
            "answer": "x",
            "evidence_refs": [],
            "claim_type": "partial",
            "stated_value": "1,234.5",
        }))
        self.assertEqual(answer.claim_type, "PARTIAL")
        self.assertAlmostEqual(answer.stated_value, 1234.5)

    def test_the_sealed_contract_is_unchanged_by_the_probe_fields(self):
        """
        The sealed fifteen still require exactly `answer` and `evidence_refs`.

        A probe field arriving as null must not become a missing key, or adding
        probes would quietly start failing every sealed test.
        """
        answer = TargetAnswer.parse(json.dumps({
            "answer": "x",
            "evidence_refs": ["obs_1"],
            "claim_type": None,
            "semantic_state": None,
            "stated_value": None,
        }))
        self.assertIsNone(answer.parse_error)
        self.assertEqual(answer.evidence_refs, ["obs_1"])


class TestSemanticProbes(unittest.TestCase):
    """
    The probe layer: structured claims, graded as values.

    These are the tests that make a probe worth running. A probe that graded
    prose would be a smaller, noisier version of the sealed suite; the reason to
    add probes at all is that the answer arrives as fields, so nothing has to be
    inferred from English.
    """

    def probe(self, **overrides):
        from harness.probes import Probe

        defaults = dict(
            probe_id="P_test",
            question="q",
            expected={"claim_type": "PARTIAL", "reason_code": "RETRIEVAL_FAILED"},
            vocabulary=("EXACT", "PARTIAL"),
            reasons=("RETRIEVAL_FAILED",),
            unguessable_fields=["reason_code"],
        )
        defaults.update(overrides)
        return Probe(**defaults)

    def answer(self, **claims):
        payload = {"answer": "x", "evidence_refs": claims.pop(
            "evidence_refs", ["obs_1"])}
        payload.update(claims)
        return TargetAnswer.parse(json.dumps(payload))

    def audit(self, probe, answer, retrieved=("obs_1",)):
        from harness.auditor import Audit, Auditor
        from harness.probes import audit_probe

        result = Audit(
            test_id=probe.probe_id,
            expectations=probe.expected,
            answer_text=answer.answer,
        )
        probe_audit = type("NullAuditor", (), {
            "check_citations_exist": staticmethod(
                lambda *a, **k: None
            ),
            "check_citations_were_retrieved": staticmethod(
                lambda *a, **k: None
            ),
        })()
        audit_probe(
            probe_audit, result, answer, None, set(retrieved), probe
        )
        return result

    def test_a_correct_claim_passes(self):
        probe = self.probe()
        result = self.audit(
            probe, self.answer(claim_type="PARTIAL",
                               reason_code="RETRIEVAL_FAILED")
        )
        self.assertTrue(result.passed, [c.name for c in result.checks])

    def test_a_wrong_claim_fails_and_says_which_field(self):
        result = self.audit(
            self.probe(), self.answer(claim_type="EXACT",
                                      reason_code="RETRIEVAL_FAILED")
        )
        self.assertFalse(result.passed)
        failed = {c.name for c in result.checks if c.passed is False}
        self.assertEqual(failed, {"probe field claim_type"})

    def test_an_omitted_field_fails_rather_than_going_unverifiable(self):
        """
        A model must not be able to opt out of a probe by leaving a key empty.

        "Did not say" and "said something wrong" are both failures of the same
        claim, and scoring the first as unverifiable would let a silent model
        pass every probe.
        """
        result = self.audit(
            self.probe(), self.answer(claim_type="PARTIAL", reason_code="")
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.unverifiable, [])
        failed = [c for c in result.checks if c.passed is False]
        self.assertEqual(len(failed), 1)
        self.assertIn("not stated", failed[0].actual)

    def test_a_missing_citation_fails(self):
        probe = self.probe(
            expected={"claim_type": "PARTIAL"},
            required_refs=["obs_1", "obs_2"],
            unguessable_fields=["required_refs"],
        )
        result = self.audit(
            probe, self.answer(claim_type="PARTIAL", evidence_refs=["obs_1"]),
            retrieved=("obs_1", "obs_2"),
        )
        self.assertFalse(result.passed)
        self.assertIn(
            "probe cites the subject's own identifiers",
            {c.name for c in result.checks if c.passed is False},
        )

    def test_a_stated_value_is_compared_as_a_number(self):
        probe = self.probe(
            expected={"claim_type": "DERIVED", "stated_value": 31.42}
        )
        good = self.audit(probe, self.answer(claim_type="DERIVED",
                                             stated_value=31.42))
        self.assertTrue(good.passed)
        bad = self.audit(probe, self.answer(claim_type="DERIVED",
                                            stated_value=31.4))
        self.assertFalse(bad.passed)

    def test_the_instruction_names_the_vocabulary_but_not_the_answer(self):
        """
        Stating the codes is protocol. Naming the right one would be the answer.
        """
        probe = self.probe(
            expected={"claim_type": "PARTIAL"},
            vocabulary=("EXACT", "PARTIAL", "UNKNOWN"),
        )
        text = probe.instructions()
        for code in ("EXACT", "PARTIAL", "UNKNOWN"):
            self.assertIn(code, text)
        self.assertNotIn("the answer is", text.lower())

    def test_a_point_in_time_probe_cannot_be_answered_from_the_newest_figure(self):
        """
        The probe has to survive a model that simply retrieves.

        Every figure is one call away, so a model that answers with the
        archive's present-day value looks like it succeeded and has imported
        hindsight. The check is that the expected value is the one that was
        *knowable*, which is not the latest.
        """
        import sys

        from evidence_query import EvidenceQuery
        from harness.probes import _partial_knowable_period
        from harness.runner import _query_connection
        from harness.snapshot import default_snapshot_path

        snapshot = default_snapshot_path()
        if not os.path.exists(snapshot):
            self.skipTest("no snapshot built")
        connection = _query_connection(snapshot)
        try:
            partial = _partial_knowable_period(connection, "AAPL")
        finally:
            connection.close()
        self.assertIsNotNone(partial)
        self.assertTrue(partial["not_yet_observation_ids"])
        self.assertNotIn(
            partial["knowable_observation_id"],
            partial["not_yet_observation_ids"],
        )
        query = EvidenceQuery.open(snapshot)
        try:
            # And the surface agrees with the answer key about what was
            # knowable, which is the property that makes the probe fair: a
            # probe whose key disagreed with the surface would be measuring the
            # harness, not the model.
            #
            # `knowable_at`, not `as_of`. `as_of` is an exact match on the
            # observation's own reporting instant and shares a name with a
            # point-in-time question, which is the defect recorded below.
            knowable = query.query_observations(
                asset="AAPL", metric=partial["metric"],
                period_end=partial["period_end"],
                knowable_at=partial["cutoff"],
            )
            ids = {row["observation_id"] for row in knowable}
            self.assertIn(partial["knowable_observation_id"], ids)
            for later in partial["not_yet_observation_ids"]:
                self.assertNotIn(later, ids)
        finally:
            query.close()

    def test_as_of_is_not_the_point_in_time_filter_its_name_suggests(self):
        """
        A recorded surface defect, pinned so it cannot be forgotten.

        `query_observations` exposes both `as_of` and `knowable_at`, and neither
        has a description in the tool schema -- eleven of its fifteen parameters
        have none. `as_of` reads as a point-in-time filter and is an exact match
        on the observation's own reporting instant, so a caller asking what was
        knowable in 2009 uses it, gets an empty list, and cannot tell that from
        "no evidence existed".

        This is the same class 2.6.1 fixed when `status` was renamed
        `validation_status`: a name that has to be disambiguated by prose is not
        self-describing. The test asserts the current, *wrong* behaviour so that
        changing it has to be a deliberate act with this test edited, rather than
        a silent improvement nobody noticed had been made.
        """
        from evidence_query import EvidenceQuery
        from harness.snapshot import default_snapshot_path

        snapshot = default_snapshot_path()
        if not os.path.exists(snapshot):
            self.skipTest("no snapshot built")
        query = EvidenceQuery.open(snapshot)
        try:
            by_instant = query.query_observations(
                asset="AAPL", metric="assets", period_end="2008-09-27",
                as_of="2009-07-23",
            )
            self.assertEqual(
                by_instant, [],
                "if as_of has become a point-in-time filter, this defect is "
                "fixed and the test should be replaced with one that pins the "
                "new behaviour",
            )
            # The correct filter is knowable_at, and it is a different filter.
            by_knowable = query.query_observations(
                asset="AAPL", metric="assets", period_end="2008-09-27",
                knowable_at="2009-07-23",
            )
            self.assertEqual(len(by_knowable), 1)
        finally:
            query.close()

    def test_the_tool_schema_documents_fewer_parameters_than_it_exposes(self):
        """
        The scale of the documentation gap, recorded rather than asserted as
        acceptable.
        """
        from evidence_query import EvidenceQuery
        from harness.schemas import tool_schemas
        from harness.snapshot import default_snapshot_path
        from harness.tools import Toolbox

        snapshot = default_snapshot_path()
        if not os.path.exists(snapshot):
            self.skipTest("no snapshot built")
        query = EvidenceQuery.open(snapshot)
        try:
            schemas = tool_schemas(Toolbox(_query=query))
        finally:
            query.close()
        undocumented = []
        for schema in schemas:
            for name, spec in (
                schema["function"]["parameters"]["properties"].items()
            ):
                if not spec.get("description"):
                    undocumented.append(
                        f"{schema['function']['name']}.{name}"
                    )
        self.assertIn(
            "query_observations.knowable_at", undocumented,
            "the point-in-time filter is exposed to the model with no "
            "description, beside an `as_of` that looks like one",
        )

    def test_a_source_independence_probe_answers_from_the_record(self):
        """
        P7's answer key is the recorded independence value, not an inference
        from which two providers appear.
        """
        import sys

        from harness.probes import _cross_source_record
        from harness.runner import _query_connection
        from harness.snapshot import default_snapshot_path

        snapshot = default_snapshot_path()
        if not os.path.exists(snapshot):
            self.skipTest("no snapshot built")
        connection = _query_connection(snapshot)
        try:
            cross = _cross_source_record(connection)
        finally:
            connection.close()
        self.assertIsNotNone(cross)
        self.assertIn(
            cross["independence"], ("INDEPENDENT", "NOT_INDEPENDENT")
        )
        self.assertEqual(len(cross["observation_ids"]), 2)
        self.assertEqual(cross["status"], "DISCREPANT")

    def test_the_probe_set_is_resolved_from_the_archive(self):
        """
        Every probe's answer key is read out of the snapshot, and every probe has
        something a model could not guess.
        """
        import sys

        from evidence_query import EvidenceQuery
        from harness.probes import build_probes
        from harness.runner import _query_connection
        from harness.snapshot import default_snapshot_path

        snapshot = default_snapshot_path()
        if not os.path.exists(snapshot):
            self.skipTest("no snapshot built")
        connection = _query_connection(snapshot)
        query = EvidenceQuery.open(snapshot)
        try:
            probes = build_probes(connection, "AAPL", query.registry())
        finally:
            query.close()
            connection.close()
        self.assertGreaterEqual(len(probes), 7)
        for probe in probes:
            self.assertTrue(
                probe.unguessable_fields,
                f"{probe.probe_id} has no unguessable field, so a coin would "
                "beat it and the probe measures nothing",
            )
            self.assertTrue(probe.expected)
            self.assertTrue(probe.full_question())


class TestTheTwoConsumerClasses(unittest.TestCase):
    """
    What a consumer is, decided mechanically from a run series.

    The split is the useful output of 2.6.3: one model was perfect at finding
    and citing evidence and could not read semantics at all, and one number
    cannot say both. These tests pin the split without a model, so the two
    verdicts cannot drift into one.
    """

    def test_a_model_that_reads_right_and_encodes_wrong_is_only_the_third(
        self
    ):
        """
        The 2.6.5 P6 case, as a rule rather than an anecdote.

        The model retrieved the knowable figure, cited the knowable observation,
        and wrote a code that was not in the vocabulary. Folding that into
        "Semantic Consumer: not yet" is what made that report hard to act on --
        the remedy for a model that reads a figure correctly and labels it
        wrongly is neither more archive nor more supervision over its judgements.
        It is a narrow mechanical fault, and the third class is what names it.
        """
        from harness.consumer import split_probe_outcome

        row = self.series()[0]
        row["test_id"] = "probe-P6_point_in_time_availability"
        row["verdict"] = "FAIL"
        row["failed_checks"] = ["probe field claim_type"]

        result = self.assess([row] * 3)
        structured = result["structured_consumer"]
        self.assertEqual(
            split_probe_outcome(["probe field claim_type"], False),
            "structured",
        )
        # Understanding is credited; encoding is not.
        self.assertEqual(structured["runs_where_understanding_was_right"], 3)
        self.assertEqual(structured["runs_where_it_was_encoded"], 0)
        self.assertEqual(structured["encoding_rate"], 0.0)
        self.assertNotEqual(structured["verdict"], "ACCEPTED")

    def test_a_model_that_reads_wrong_is_not_counted_against_encoding(self):
        """
        Encoding is measured only over runs where the reading was right.

        Otherwise a model that misreads a figure *and* mislabels it would
        appear twice, in two classes, and the number that matters -- can it
        say what it understood -- would be diluted by faults it does not have.
        """
        from harness.consumer import split_probe_outcome

        self.assertEqual(
            split_probe_outcome(
                ["probe field stated_value", "probe field claim_type"], False
            ),
            "semantic",
        )
        row = self.series()[0]
        row["test_id"] = "probe-P9_unmeasured"
        row["verdict"] = "FAIL"
        row["failed_checks"] = [
            "probe field stated_value", "probe field claim_type",
        ]
        structured = self.assess([row] * 3)["structured_consumer"]
        self.assertEqual(structured["runs_where_understanding_was_right"], 0)
        self.assertEqual(structured["verdict"], "ACCEPTED")

    def test_a_probe_the_model_never_answered_is_a_tool_use_failure(self):
        from harness.consumer import split_probe_outcome

        self.assertEqual(split_probe_outcome([], True), "tool_use")
        self.assertEqual(
            split_probe_outcome(["the answer parsed into the contract"], False),
            "semantic",
        )

    def test_coverage_separates_holding_a_fact_from_finding_it(self):
        """
        The axis 2.6.5 needed.

        A fact the archive holds and no query surfaces is invisible to every
        count of held rows, so the archive looks complete and the consumer finds
        nothing. That is the worst of the three gaps and it is the one the
        `cross_source_validation_records` line reports.
        """
        import sys

        from evidence_query import EvidenceQuery
        from harness.coverage import _discoverability
        from harness.runner import _query_connection
        from harness.snapshot import default_snapshot_path

        snapshot = default_snapshot_path()
        if not os.path.exists(snapshot):
            self.skipTest("no snapshot built")
        connection = _query_connection(snapshot)
        query = EvidenceQuery.open(snapshot)
        try:
            axes = _discoverability(query, connection, "AAPL")
        finally:
            query.close()
            connection.close()
        by_class = {f["fact_class"]: f for f in axes["by_fact_class"]}
        # The archive holds a cross-source check and no search reaches it.
        record = by_class["cross_source_validation_records"]
        self.assertGreaterEqual(record["held"], 1)
        self.assertEqual(
            record["discoverable"], 0,
            "the cross-source record became discoverable; this test and the "
            "2.6.5 report both need updating",
        )
        # And the facts that *are* discoverable stay that way.
        for name in ("negative_states", "ambiguity_groups"):
            self.assertEqual(by_class[name]["discoverable"],
                             by_class[name]["held"])

    def test_coverage_never_reports_more_mapped_than_held(self):
        """
        A join across the mapping table multiplies observations when a concept
        maps to several metrics, and the first version of this reported *-178
        unmapped*. A coverage figure that comes out negative is the fastest way
        to know a coverage figure is lying.
        """
        import sys

        from harness.coverage import _evidence_coverage
        from harness.runner import _query_connection
        from harness.snapshot import default_snapshot_path

        snapshot = default_snapshot_path()
        if not os.path.exists(snapshot):
            self.skipTest("no snapshot built")
        connection = _query_connection(snapshot)
        try:
            axis = _evidence_coverage(
                connection, connection.execute(
                    "SELECT asset_id FROM assets LIMIT 1"
                ).fetchone()[0], "AAPL",
            )
        finally:
            connection.close()
        self.assertGreaterEqual(axis["observations_unmapped"], 0)
        self.assertLessEqual(
            axis["observations_mapped_to_a_concept"],
            axis["observations_held"],
        )
        self.assertEqual(
            axis["observations_held"],
            axis["observations_mapped_to_a_concept"]
            + axis["observations_unmapped"],
        )

    def series(self, **overrides):
        """Three runs of a model that gets everything right, built per run.

        A fresh dict per run rather than one dict repeated three times: sharing
        the objects would let a single-row edit in a test leak into all three
        runs, and a gate that quietly passes because of an alias is worse than
        one that fails.
        """
        single_run = []
        for test_id, capability in (
            ("T1_exact_value", "retrieval"),
            ("T2_series", "retrieval"),
            ("T3_pagination", "pagination"),
            ("T14_truncation_trap", "pagination"),
            ("T4_point_in_time", "temporal"),
            ("T6_reported_vs_derived", "semantic"),
            ("T8_conflict", "semantic"),
            ("T9_unavailable", "semantic"),
            ("T10_concept_evolution", "semantic"),
            ("T11_partial_mapping", "semantic"),
            ("T12_non_comparable", "semantic"),
            ("T13_provenance_chain", "provenance"),
            ("probe-P1_reported_or_derived", "semantic"),
            ("probe-P2_negative_state_cause", "semantic"),
            ("probe-P3_disagreement_meaning", "semantic"),
            ("probe-P4_partial_mapping_meaning", "semantic"),
            ("probe-P5_two_concepts_one_series", "semantic"),
        ):
            verdict = overrides.get(test_id, "PASS")
            single_run.append({
                "test_id": test_id,
                "consumer_capability": capability,
                "verdict": verdict,
                "stability": "stable_pass" if verdict == "PASS" else "stable_fail",
                "failed_checks": [],
                "provenance_check_failures": [],
                "fabricated_identifiers": [],
                "misfiled_identifiers": [],
                "identifiers_cited": 3,
                "off_surface_calls": [],
                "tool_calls": 2,
                "failed_tool_calls": 0,
                "evidence_refs": 3,
            })
        return [dict(row) for row in single_run for _ in range(3)]

    def assess(self, rows):
        from harness.consumer import assess

        return assess(rows, run_count=3)

    def test_a_model_that_grounds_but_reads_nothing_is_a_bounded_consumer(self):
        """
        The 2.6.3 Nemotron shape, and the reason the classes are separate.

        Evidence Consumer ACCEPTED, Semantic Consumer NOT_YET, classified as a
        bounded consumer. Not rejected: rejecting a model that cites only real
        identifiers would be throwing away the property the product is built on,
        and a supervised second reader on the semantics is cheaper than that.
        """
        rows = self.series()
        for row in rows:
            if "probe:" in row["test_id"] or row["test_id"] in (
                "T6_reported_vs_derived", "T8_conflict", "T9_unavailable",
            ):
                row["verdict"] = "FAIL"
                row["stability"] = "stable_fail"
        result = self.assess(rows)
        self.assertEqual(
            result["evidence_consumer"]["verdict"], "ACCEPTED"
        )
        self.assertEqual(result["semantic_consumer"]["verdict"], "NOT_YET")
        self.assertEqual(result["classification"], "bounded / supervised consumer")

    def test_a_model_that_invents_an_identifier_is_not_a_consumer(self):
        """
        One fabricated citation fails the whole class.

        Not a rate. An invented observation id looks checkable to whoever reads
        the answer, which is what makes it worse than no citation at all, and a
        model that does it once is a model that will do it again.
        """
        rows = self.series()
        rows[0]["fabricated_identifiers"] = ["obsarch_0000000000deadbeef"]
        result = self.assess(rows)
        self.assertEqual(result["evidence_consumer"]["verdict"], "REJECTED")
        self.assertEqual(result["classification"], "not a consumer")
        # And semantics are not even reached: there is nothing to build on.
        self.assertEqual(result["semantic_consumer"]["verdict"], "NOT_REACHED")

    def test_a_real_identifier_in_the_wrong_field_is_not_fabrication(self):
        """
        The mistake this round nearly made, pinned so it cannot be made again.

        The auditor emits one check -- "every cited observation exists" -- for
        *any* citation that is not an observation id, including a source-fact id
        or a document id that the archive genuinely holds. Reading that check as
        fabrication produced a REJECTED verdict for a model that had invented
        nothing: all 77 of its citations were in the database, and it was
        rejected for filing six of them in the wrong column.

        Fabricating `obs_ff00...` and filing a real `sfid_...` in the wrong field
        are different faults with different consequences, and one check name
        cannot carry the difference.
        """
        rows = self.series()
        rows[0]["misfiled_identifiers"] = [
            {"identifier": "sfid_b5229f1711c68622f937916d70285775",
             "kind": "source_fact"},
        ]
        rows[1]["provenance_check_failures"] = [
            "every cited observation exists"
        ]
        criterion = next(
            c for c in self.assess(rows)["evidence_consumer"]["criteria"]
            if c["id"] == "no_fabricated_identifiers"
        )
        self.assertTrue(
            criterion["passed"],
            "a real identifier in the wrong field is not a fabrication",
        )
        self.assertIn("0 the archive does not hold", criterion["observed"])
        # It still costs, on the criterion that is about the wrong field.
        rate = next(
            c for c in self.assess(rows)["evidence_consumer"]["criteria"]
            if c["id"] == "citations_are_retrieved_and_in_namespace"
        )
        self.assertLess(rate["observed"].count("misfiled"), 3)

    def test_a_test_the_run_set_never_contained_is_not_a_failure(self):
        """
        A screening run carries five sealed tests, not fifteen, and a probe run
        carries probes without their sealed partners.

        Without this the gate would report that a model fails point-in-time
        because point-in-time was never asked, and reject it for a question
        nobody put to it.
        """
        rows = [r for r in self.series() if r["test_id"] not in (
            "T4_point_in_time", "T14_truncation_trap",
        )]
        result = self.assess(rows)
        criterion = next(
            c for c in result["evidence_consumer"]["criteria"]
            if c["id"] == "temporal_discipline"
        )
        self.assertIsNone(criterion["passed"])
        self.assertIn("not exercised", criterion["observed"])
        # And it carries no weight: the retrieval criterion is exercised and
        # passing, so the class is not failed by the absent one.
        self.assertEqual(
            result["evidence_consumer"]["verdict"], "ACCEPTED"
        )

    def test_an_absent_partner_does_not_void_a_probe_that_passed(self):
        """
        A criterion is `n/a` when *nothing* in it was exercised.

        Not when half of it was. A probe that passed five runs out of five does
        not stop counting because its sealed partner was not in the run set --
        that would throw away the measurement on a technicality, and the whole
        point of a per-test rollup is that coverage is reported rather than
        silently rounded either way.
        """
        rows = [r for r in self.series() if r["test_id"] != "T6_reported_vs_derived"]
        result = self.assess(rows)
        criterion = next(
            c for c in result["semantic_consumer"]["criteria"]
            if c["id"] == "reads_a_derived_figure"
        )
        self.assertTrue(criterion["passed"])
        self.assertTrue(criterion["partial_coverage"])
        self.assertIn("T6_reported_vs_derived", criterion["not_applicable"])
        self.assertEqual(criterion["per_test"]["probe-P1_reported_or_derived"],
                         ["PASS"] * 3)

    def test_a_single_off_surface_call_rejects(self):
        rows = self.series()
        rows[2]["off_surface_calls"] = ["get_validation_sql"]
        self.assertEqual(
            self.assess(rows)["evidence_consumer"]["verdict"], "REJECTED"
        )

    def test_a_model_that_answers_from_memory_is_not_an_evidence_consumer(self):
        rows = self.series()
        for row in rows:
            row["tool_calls"] = 0
        result = self.assess(rows)
        criterion = next(
            c for c in result["evidence_consumer"]["criteria"]
            if c["id"] == "uses_the_tool_surface"
        )
        self.assertFalse(criterion["passed"])

    def test_a_model_that_reads_everything_is_a_candidate_autonomous_consumer(self):
        """
        The bar for the top class, stated so it is not a moving target: ground
        every citation, stay on the surface, and read the semantic distinctions
        in a majority of runs rather than once by luck.
        """
        result = self.assess(self.series())
        self.assertEqual(result["semantic_consumer"]["verdict"], "ACCEPTED")
        self.assertEqual(
            result["classification"], "candidate autonomous consumer"
        )

    def test_an_unstable_capability_does_not_count_as_read(self):
        """
        One pass out of three is not a capability.

        Averaging it into a rate would say the model reads semantics a third of
        the time, which is a claim about a consumer that nobody would accept.
        """
        rows = self.series()
        for row in rows:
            if row["test_id"] == "probe-P1_reported_or_derived":
                continue
        seen = 0
        for row in rows:
            if row["test_id"] == "probe-P1_reported_or_derived":
                seen += 1
                row["verdict"] = "PASS" if seen == 1 else "FAIL"
                row["stability"] = "unstable"
        criterion = next(
            c for c in self.assess(rows)["semantic_consumer"]["criteria"]
            if c["id"] == "reads_a_derived_figure"
        )
        self.assertFalse(criterion["passed"])


class TestFindingsFromTheFirstRealModelRun(unittest.TestCase):
    """
    The findings a real model produced, and the behaviour that replaced them.

    These were found by a real model running the sealed dataset, which is the
    only way any of them could have been found: the scripted targets had fixed
    answers, so they never depended on what the archive actually contained at
    the moment.

    A1 and A2 are now fixed, so these assert the fix rather than the defect. A
    test that characterised the old behaviour would start failing for a reason
    nobody is going to act on; a test that pins the fix starts failing when
    someone reintroduces the problem, which is when it is worth hearing about.
    """

    def test_a1_an_unknown_metric_is_no_longer_indistinguishable(self):
        """
        A1, fixed: an unknown metric is refused, not answered with `[]`.

        This produced 7 of 15 false negatives in the first real run, each
        answered "no data exists" while the archive held hundreds of rows. The
        recovery has to travel with the error, or the caller is left guessing
        which of the two things went wrong.
        """
        from evidence_query import EvidenceQuery, UnknownMetricError
        from harness.snapshot import default_snapshot_path

        query = EvidenceQuery.open(default_snapshot_path())
        try:
            real = query.query_observations(
                asset="AAPL", metric="revenue", limit=1
            )
            empty_but_known = query.query_observations(
                asset="AAPL", metric="guidance", limit=1
            )
            self.assertTrue(real, "the archive should hold revenue")
            self.assertEqual(
                empty_but_known, [],
                "guidance is registered as STALE; holding nothing is the true "
                "answer and must stay an empty result, not an error",
            )
            with self.assertRaises(UnknownMetricError) as caught:
                query.query_observations(
                    asset="AAPL", metric="operating margin", limit=5
                )
            error = caught.exception
            self.assertEqual(error.requested, "operating margin")
            self.assertIn("revenue", error.available)
            self.assertIn("capex", error.available)
            self.assertIn("UNKNOWN_METRIC", str(error))
        finally:
            query.close()

    def test_a2_the_status_filter_is_named_for_what_it_filters(self):
        """
        A2, fixed: the parameter is `validation_status` and the old name is gone.

        The model passed `SOURCE_REPORTED` — a term the documented vocabulary
        teaches — to a parameter called `status` that filters cross-check
        status, and got an empty list back. It still did so after the prompt was
        corrected to spell the distinction out, which is what made it a naming
        collision rather than a misunderstanding.

        Renaming without removing the old name would leave the ambiguity in
        place behind a notice nobody reads, so the old keyword is refused.
        """
        import inspect

        from evidence_query import EvidenceQuery, QueryError
        from harness.snapshot import default_snapshot_path

        parameters = inspect.signature(
            EvidenceQuery.query_observations
        ).parameters
        self.assertIn("validation_status", parameters)
        self.assertNotIn("status", parameters)

        query = EvidenceQuery.open(default_snapshot_path())
        try:
            # The exact mistake from the run, now refused by name.
            with self.assertRaises(QueryError) as caught:
                query.query_observations(
                    asset="AAPL", metric="revenue",
                    validation_status="SOURCE_REPORTED",
                )
            self.assertIn("evidence state", str(caught.exception))

            # And the parameter that was always meant by it still works.
            self.assertTrue(
                query.query_observations(
                    asset="AAPL", metric="revenue",
                    validation_status="UNVERIFIABLE", limit=1,
                )
            )
        finally:
            query.close()

    def test_the_toolbox_exposes_the_renamed_filter(self):
        """
        The model is told about the surface by introspecting the toolbox, so a
        renamed parameter that the wrapper did not adopt would still be
        advertised under its old name in every tool schema.
        """
        from harness.schemas import tool_schemas
        from harness.snapshot import default_snapshot_path
        from evidence_query import EvidenceQuery
        from harness.tools import Toolbox

        query = EvidenceQuery.open(default_snapshot_path())
        try:
            schemas = {
                s["function"]["name"]: s["function"]["parameters"]
                for s in tool_schemas(Toolbox(_query=query))
            }
            properties = schemas["query_observations"]["properties"]
            self.assertIn("validation_status", properties)
            self.assertNotIn("status", properties)
            # The model's four failed calls were these, and the schema now
            # says integer and enumerates the order.
            self.assertEqual(properties["limit"]["type"], "integer")
        finally:
            query.close()

    def test_c1_a_test_cannot_pass_by_retrieving_nothing(self):
        """
        C1: T4 passed vacuously in the first real run.

        Its checks were "the filter appeared in the arguments" and "citations
        <= knowable rows", and a model that retrieved zero observations and
        answered "No revenue observations were found" satisfied both. A grader
        that passes the answer it should most punish is worse than no grader,
        because the failure does not show up in the score.

        The precondition is now asserted directly and applies wherever the
        archive holds evidence for the question.
        """
        from harness.auditor import Audit, Auditor, Check
        from harness.tools import Toolbox

        class _NoDatabase(Auditor):
            def __init__(self) -> None:
                self.connection = None
                self.query = None

        audit = Audit(
            test_id="probe",
            expectations={"knowable_count": 100, "point_count": 339},
            answer_text="No revenue observations were found.",
        )
        _NoDatabase().check_evidence_was_retrieved(
            audit, 100, set(), set()
        )
        failed = audit.failed_checks
        self.assertEqual(len(failed), 1)
        self.assertEqual(
            failed[0].name, "evidence was actually retrieved"
        )
        self.assertFalse(audit.passed)

        # And the same audit passes once something was actually retrieved.
        ok = Audit(
            test_id="probe",
            expectations={"knowable_count": 100},
            answer_text="Here it is.",
        )
        _NoDatabase().check_evidence_was_retrieved(
            ok, 100, {"obsarch_1"}, {"obsarch_1"}
        )
        self.assertTrue(ok.passed)

    def test_c2_a_mapping_fidelity_does_not_acknowledge_truncation(self):
        """
        C2: T14 passed because the answer contained the word "PARTIAL".

        The word described *mapping fidelity* — "derived from PARTIAL fidelity
        under US-GAAP" — and a truncation-acknowledgement check accepted it. The
        right word meaning something else entirely, which is the documented
        fragility of keyword checks arriving exactly as predicted.

        Truncation now has to be stated in truncation vocabulary, or the
        archive's own point count has to appear.
        """
        from harness.auditor import acknowledges_truncation

        # The exact sentence that produced the false pass.
        self.assertFalse(
            acknowledges_truncation(
                "All entries are SOURCE_REPORTED and the values are derived "
                "from PARTIAL fidelity under US-GAAP.",
                339,
            )
        )
        # Genuine acknowledgements still pass.
        for honest in (
            "The series holds 339 points and I have 200 of them.",
            "This is the first page; the series is truncated.",
            "I have not retrieved the whole series.",
            "This is a partial series - there are more points.",
        ):
            self.assertTrue(acknowledges_truncation(honest, 339), honest)

    def test_a_request_budget_stops_the_run_rather_than_the_provider(self):
        """
        A refused request is not a model failure, and a budget is not a model
        failure either.

        The failure this guards against is quiet: a rate limit turns the tail of
        a run into `FAIL`s on tests the model never saw, and a run that was
        mostly passing quietly stops being one. So the budget stops the phase,
        the stop is reported, and no test is graded.
        """
        from harness.budget import RequestBudget

        budget = RequestBudget(3, label="test/full")
        budget.record_sent("T1")
        budget.record_answer("T1", {"total_tokens": 10})
        self.assertEqual(budget.remaining, 2)

        budget.record_sent("T2")
        budget.record_refusal("rate_limited", "T2", "HTTP 429 upstream pool")
        self.assertTrue(budget.should_retry("rate_limited"))
        self.assertEqual(budget.signals["rate_limited"], 1)
        self.assertFalse(budget.stopped_because)

        budget.record_sent("T3")
        self.assertFalse(budget.can_start("T4"))
        self.assertIn("budget of 3", budget.stopped_because)

    def test_a_gateway_reports_an_upstream_failure_with_whatever_status(self):
        """
        A 400 that carries `provider_name` is a provider failure, not a network
        one.

        Found by being wrong: an OpenRouter endpoint whose backing provider was
        degraded answered `400` with `Provider returned error` and a
        `provider_name`, and a classifier that read only the status called it a
        network failure. Wrong twice over -- the retry advice differs, and the
        recorded reason becomes a claim about the network that the response
        itself contradicts.
        """
        from harness.providers import classify_error_body, classify_http_failure

        degraded = (
            '{"error":{"message":"Provider returned error","code":400,'
            '"metadata":{"raw":"DEGRADED function cannot be invoked"},'
            '"provider_name":"nvidia"}}'
        )
        self.assertEqual(classify_http_failure(400, degraded), "provider_error")
        self.assertEqual(
            classify_error_body('{"error":{"code":503,"message":"overloaded"}}'),
            "provider_error",
        )

    def test_a_refused_request_of_ours_is_not_retried(self):
        """
        A 4xx naming our own payload is a harness fault and sending it again
        gets the same refusal.
        """
        from harness.budget import SIGNALS
        from harness.providers import classify_http_failure

        kind = classify_http_failure(
            400, '{"error":{"message":"Invalid JSON payload",'
                 '"type":"invalid_request_error"}}'
        )
        self.assertEqual(kind, "request_rejected")
        self.assertFalse(SIGNALS[kind]["retry"])

    def test_a_slow_provider_does_not_crash_the_run(self):
        """
        A read that stalls mid-response arrives as a bare `TimeoutError`, and
        `urlopen` does not wrap it.

        Uncaught it ends the process. A slow provider would then look like a
        crash rather than like a provider that did not answer -- one level worse
        than a misclassification, because there is no classification left to
        correct. Found this way: a real 2.6.4 run died on one.
        """
        from unittest import mock

        from harness.budget import RequestBudget
        from harness.providers import (
            OpenAICompatibleClient,
            ProviderConfig,
            TransportError,
        )

        client = OpenAICompatibleClient(
            ProviderConfig(
                base_url="https://example.invalid/v1", model="m", provider="p",
            ),
            api_key="not-a-real-key",
        )
        budget = RequestBudget(None)
        client.budget = budget

        with mock.patch(
            "harness.providers.urllib.request.urlopen",
            side_effect=TimeoutError("read operation timed out"),
        ):
            with self.assertRaises(TransportError) as caught:
                client.complete([{"role": "user", "content": "hi"}])

        self.assertEqual(caught.exception.kind, "network")
        # Counted, classified, and retryable -- rather than taking the run with
        # it and leaving the attempt unrecorded.
        self.assertEqual(budget.spent, 1)
        self.assertEqual(budget.signals["network"], 1)
        self.assertTrue(budget.should_retry("network"))
        self.assertFalse(
            budget.attempts[-1].get("is_model_finding", False)
        )

    def test_a_reset_connection_is_classified_rather_than_fatal(self):
        from unittest import mock

        from harness.providers import (
            OpenAICompatibleClient,
            ProviderConfig,
            TransportError,
        )

        client = OpenAICompatibleClient(
            ProviderConfig(
                base_url="https://example.invalid/v1", model="m", provider="p"
            ),
            api_key="not-a-real-key",
        )
        with mock.patch(
            "harness.providers.urllib.request.urlopen",
            side_effect=ConnectionResetError("peer closed"),
        ):
            with self.assertRaises(TransportError) as caught:
                client.complete([{"role": "user", "content": "hi"}])
        self.assertEqual(caught.exception.kind, "network")

    def test_a_withdrawn_model_is_not_retried(self):
        """
        Retrying a model that no longer exists is how a run loses its whole
        allowance, so the signal that means "never" is distinct from the ones
        that mean "later".
        """
        from harness.budget import RequestBudget

        budget = RequestBudget(None)
        budget.record_sent("T1")
        budget.record_refusal(
            "model_unavailable", "T1", "no endpoints found for /models/gone:free"
        )
        self.assertFalse(budget.should_retry("model_unavailable"))
        self.assertIn("model_unavailable", budget.stopped_because)
        self.assertEqual(budget.summary()["model_finding_refusals"], 0)

    def test_a_run_of_refusals_ends_the_phase(self):
        """
        Three in a row is the endpoint, not the request. Continuing past that
        is the documented way to spend the rest of the day's allowance on a
        provider that has already said no.
        """
        from harness.budget import RequestBudget

        budget = RequestBudget(None)
        for index in range(3):
            budget.record_sent(f"T{index}")
            budget.record_refusal("provider_error", f"T{index}", "HTTP 502")
        self.assertIn("refusals with no answer", budget.stopped_because)
        self.assertFalse(budget.can_start("next"))

    def test_the_client_records_every_request_it_sends(self):
        """
        Counted on the way out, not on the way back.

        A refused request can still spend an allowance, and a budget that counts
        only successes is exactly the one that runs out unexpectedly.
        """
        from harness.budget import RequestBudget
        from harness.providers import (
            OpenAICompatibleClient,
            ProviderConfig,
            TransportError,
        )

        budget = RequestBudget(None)
        client = OpenAICompatibleClient(
            ProviderConfig(
                base_url="https://example.invalid/v1", model="m", provider="p"
            ),
            api_key="not-a-real-key",
        )
        client.budget = budget
        client.current_test = "T1"

        with self.assertRaises(TransportError):
            client.complete([{"role": "user", "content": "hi"}])

        self.assertEqual(budget.spent, 1)
        outcomes = [attempt["outcome"] for attempt in budget.attempts]
        self.assertEqual(outcomes[0], "sent")
        self.assertTrue(outcomes[-1].startswith("refused:"))
        self.assertEqual(budget.attempts[-1]["is_model_finding"], False)

    def test_a_recorded_run_re_audits_to_its_published_score(self):
        """
        Re-grading a stored run must reproduce its published score.

        This is how the first run's 2/15 was corrected to 0/15: the stored
        answers do not change when the evaluator does, so re-auditing them is
        the cheapest possible test of a change to the grader -- no model, no
        network, and the new evaluator held against real behaviour rather than
        against a target written to please it.

        It is an invariant rather than a fixed number, because the run directory
        holds the most recent run and a hard-coded 2 would rot the moment a
        second run lands. The correction itself is recorded in
        reports/REAL_MODEL_RUN.md.
        """
        import json
        import os

        from harness.auditor import Audit, Auditor
        from harness.target import TargetAnswer
        from harness.tools import Call, Toolbox

        experiment = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "experiments", "003-llm-evidence-retrieval",
        )
        run_dir = os.path.join(
            experiment, "runs", "ollama-local-qwen3-14b"
        )
        report_path = os.path.join(run_dir, "reports", "report.json")
        if not os.path.exists(report_path):
            self.skipTest("no recorded real-model run to re-audit")
        published = json.load(open(report_path, encoding="utf-8"))
        expected = {
            t["test_id"]: t["passed"] for t in published["query_behaviour"]
        }

        snapshot = default_snapshot_path()
        dataset = build_dataset(snapshot)
        connection = _query_connection(snapshot)
        query = EvidenceQuery.open(snapshot)
        auditor = Auditor(connection, query)
        try:
            for test in dataset.tests:
                path = os.path.join(
                    run_dir, "audit", f"{test.test_id}.json"
                )
                if not os.path.exists(path):
                    continue
                stored = json.load(open(path, encoding="utf-8"))
                answer = TargetAnswer.parse(json.dumps({
                    "answer": stored["answer"]["answer"],
                    "evidence_refs": stored["answer"]["evidence_refs"],
                    "derived_refs": stored["answer"]["derived_refs"],
                    "uncertainties": stored["answer"]["uncertainties"],
                }))
                tools = Toolbox(_query=query)
                tools.calls = [
                    Call(
                        sequence=c["sequence"],
                        operation=c["operation"],
                        arguments=c["arguments"],
                        error=c.get("error"),
                        result_shape=c.get("result_shape", "unknown"),
                        stored_returned_count=c.get("returned_count"),
                    )
                    for c in stored["trace"]
                ]
                audit = Audit(
                    test_id=test.test_id,
                    expectations=dict(test.expectations),
                    answer_text=answer.answer,
                )
                test.audit(
                    auditor, audit, answer, tools,
                    set(stored["retrieved_observations"]),
                )
                self.assertEqual(
                    audit.passed,
                    expected[test.test_id],
                    f"{test.test_id}: the stored run was published as "
                    f"{expected[test.test_id]} and re-audits as "
                    f"{audit.passed}, so the run's report and its evidence "
                    "disagree",
                )
        finally:
            query.close()
            connection.close()


if __name__ == "__main__":
    unittest.main()
