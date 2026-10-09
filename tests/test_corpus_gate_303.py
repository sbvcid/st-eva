"""
3.03 production contract -- `corpus_gate` and the corpus boundary.

## What is being defended

A clean checkout must be able to run the production suite, and it must be obvious
which tests it did not run.

That is only true if the boundary is *declared*. The failure 3.03 replaced was a
guard testing `os.path.isdir(H)` -- the harness directory, which is tracked, so
it exists in every checkout -- so the guard never fired and the corpus-dependent
tests failed with `OperationalError` instead. 3.02 measured that as 23 failures
and 19 errors.

So these tests defend three things:

  1. the gate's own behaviour, including the distinction the old guard lost:
     **absent corpus skips, present-but-empty corpus fails**
  2. the declaration itself is complete -- every corpus a tracked test can reach
     is named, and every name resolves to a declared corpus
  3. no tracked test can silently acquire a corpus dependency without declaring
     it, which is the property that actually prevents a regression

## Why no corpus count is pinned

The corpora are ~557 MB of fetched SQLite. Their presence is an environment fact,
so asserting they exist would make this test fail on a clean checkout -- which is
the bug in the other direction. What is pinned is the *declaration*, not the
data.
"""

from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import corpus_gate  # noqa: E402

ABSENT = "corpus-that-does-not-exist-303"


class TestTheGate(unittest.TestCase):
    """Cases 1-3, with a name guaranteed absent so the behaviour is testable."""

    def test_a_present_corpus_yields_its_path(self) -> None:
        for stem in corpus_gate.CORPORA:
            if corpus_gate.corpus_path(stem) is None:
                continue
            paths = corpus_gate.require(self, stem)
            self.assertEqual(paths[stem], corpus_gate.corpus_path(stem))
            return
        self.skipTest("no corpus present on this machine")

    def test_an_absent_corpus_skips_naming_itself(self) -> None:
        with self.assertRaises(unittest.SkipTest) as caught:
            corpus_gate.require(self, ABSENT)
        message = str(caught.exception)
        self.assertIn(ABSENT, message,
                      "a skip must name the file it is missing, or it is a "
                      "silently disabled test")
        self.assertIn(corpus_gate.RUN_COMMAND, message,
                      "and must say where the work happens instead")

    def test_require_needs_every_named_corpus(self) -> None:
        if corpus_gate.missing(corpus_gate.CORPORA):
            self.skipTest("no corpus present on this machine")
        with self.assertRaises(unittest.SkipTest):
            corpus_gate.require(self, "snapshot", ABSENT)

    def test_require_any_is_satisfied_by_one_present_corpus(self) -> None:
        """
        A test that globs a directory has no opinion about which archive it reads.
        Gating it on all of them would be a false claim; gating it on one named
        archive would be a brittle one.
        """
        present = [s for s in corpus_gate.CORPORA
                   if not corpus_gate.missing([s])]
        if not present:
            self.skipTest("no corpus present on this machine")
        self.assertTrue(corpus_gate.require_any(self, *present))
        with self.assertRaises(unittest.SkipTest):
            corpus_gate.require_any(self, ABSENT, "also-absent-303")

    def test_the_module_guard_raises_rather_than_returning(self) -> None:
        """
        A module-level guard that cannot fire is what caused this round. Raising
        makes "did it fire" unaskable.
        """
        with self.assertRaises(unittest.SkipTest):
            corpus_gate.require_module(ABSENT)

    def test_the_path_is_not_an_existence_test(self) -> None:
        """A caller must be able to ask where a corpus is without being gated."""
        path = corpus_gate.corpus_path(ABSENT)
        self.assertTrue(path.endswith("%s.sqlite" % ABSENT))
        self.assertFalse(os.path.isfile(path))

    def test_the_census_reports_presence_without_raising(self) -> None:
        state = corpus_gate.census()
        self.assertIn("corpora", state)
        self.assertEqual(set(state["corpora"]), set(corpus_gate.CORPORA))
        for stem, info in state["corpora"].items():
            self.assertIsInstance(info["present"], bool)
            self.assertTrue(info["purpose"],
                            "a corpus with no stated purpose cannot be judged")


class TestTheDeclarationIsComplete(unittest.TestCase):
    """The tables must name only real corpora, and every real one must be named."""

    def test_every_declared_corpus_exists_in_the_registry(self) -> None:
        for module, stems in corpus_gate.CORPUS_TESTS.items():
            for stem in stems:
                self.assertIn(stem, corpus_gate.CORPORA,
                              "%s requires an undeclared corpus %s"
                              % (module, stem))

    def test_the_any_table_is_declared_too(self) -> None:
        for module, stems in corpus_gate.CORPUS_TESTS_ANY.items():
            for stem in stems:
                self.assertIn(stem, corpus_gate.CORPORA, module)

    def test_every_corpus_is_used_by_something(self) -> None:
        """
        A declared corpus nothing needs is a corpus someone will assume is
        covered. Measured 3.03: five corpora, all reachable from a tracked test.
        """
        used = {s for stems in corpus_gate.CORPUS_TESTS.values()
                for s in stems}
        used |= {s for stems in corpus_gate.CORPUS_TESTS_ANY.values()
                 for s in stems}
        self.assertEqual(used, set(corpus_gate.CORPORA))

    def test_the_measured_corpus_modules_are_all_declared(self) -> None:
        """
        3.03 measured these six by instrumenting a full suite run and reading
        every `sqlite3.connect`. The declaration must cover exactly that set, or a
        module will be corpus-dependent without saying so.

        `test_vendor_debt_projection` appears in both tables on purpose: one test
        reads the sealed snapshot by name, another globs for any archive.
        """
        # `test_eval_harness` dropped at `b124123` with its experiment. The two
        # assertions it made that survived the archive need no corpus and are
        # covered by `test_evaluation_format_boundary`, which is correctly absent.
        measured = {
            "test_basis_framework_query",
            "test_evidence_query_knowledge_state",
            "test_knowledge_state_reader_integration",
            "test_source_conditional_metric_retrieval",
            "test_vendor_debt_projection",
        }
        declared = set(corpus_gate.CORPUS_TESTS) | set(
            corpus_gate.CORPUS_TESTS_ANY)
        self.assertEqual(measured, declared)


class TestTheBoundaryIsHonest(unittest.TestCase):
    """
    The property that stops a regression.

    Every corpus-bearing guarded test must reach its corpus through the gate, so a
    new corpus dependency cannot appear without a declaration. Checked by source
    rather than by running the suite, because a clean checkout cannot run the
    corpus-dependent tests at all -- which is the whole reason the gate exists.
    """

    # `test_eval_harness.py` was archived at `b124123` along with its experiment.
    # It is absent here rather than deleted from the list because these two tests
    # open each named file: a name whose module no longer exists would fail them
    # for a reason that has nothing to do with the corpus boundary.
    GUARDED_MODULES = (
        "test_basis_framework_query.py",
        "test_evidence_query_knowledge_state.py",
        "test_knowledge_state_reader_integration.py",
        "test_source_conditional_metric_retrieval.py",
        "test_vendor_debt_projection.py",
    )

    @staticmethod
    def code_only(path: str) -> str:
        """
        The module's code with comments and docstrings removed.

        Tokenised rather than regexed, because 3.03 explains this defect *in* the
        modules it fixes. A scan that counted the prose would fail on the very
        comments that document the repair, which is how a guard test ends up
        punishing the person who wrote the explanation.
        """
        import io
        import tokenize

        with io.open(path, "rb") as handle:
            out = []
            for token in tokenize.tokenize(handle.readline):
                if token.type in (tokenize.COMMENT, tokenize.STRING):
                    continue
                out.append(token.string)
        return "\n".join(out)

    def test_no_module_guards_on_the_container_directory(self) -> None:
        """
        The exact 3.02 defect: `os.path.isdir(H)` is true in every checkout,
        because the harness directory is tracked and the archives are not. Any
        module still testing the container has the bug back.
        """
        for name in self.GUARDED_MODULES:
            code = self.code_only(os.path.join(HERE, name))
            self.assertNotIn('skipTest("harness archives are not present")',
                             code, name)
            self.assertNotIn("os.path.isdir(H)", code, name)

    def test_every_corpus_dependent_module_imports_the_gate(self) -> None:
        for name in self.GUARDED_MODULES:
            path = os.path.join(HERE, name)
            with open(path, encoding="utf-8") as handle:
                body = handle.read()
            self.assertIn("corpus_gate", body, name)

    def test_the_gate_never_runs_the_corpus_suite_for_you(self) -> None:
        """
        A skip is a promise that the work happens elsewhere. The runner exists to
        keep that promise, so it must be a real entry point rather than a
        suggestion in a docstring.
        """
        runner = os.path.join(ROOT, "run_corpus_tests.py")
        self.assertTrue(os.path.isfile(runner))
        with open(runner, encoding="utf-8") as handle:
            body = handle.read()
        self.assertIn("CORPUS_TESTS", body)
        self.assertNotIn("build_snapshot", body,
                         "the corpus runner must not substitute a corpus")


if __name__ == "__main__":
    unittest.main()