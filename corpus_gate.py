"""
ST-EVA 3.03 -- declaring which tests need the research corpus.

## The defect this replaces

Five tracked test modules guarded their corpus with a test of the wrong thing:

    if not os.path.isdir(H):
        self.skipTest("harness archives are not present")

`H` is the harness *directory*, and that directory is tracked -- 33 files of it
are in Git, including the harness package itself. So in a clean checkout
`os.path.isdir(H)` is true, the guard never fires, and `sqlite3.connect` then
raises `OperationalError: unable to open database file`. 3.02 measured 23
failures and 19 errors in a clean checkout; this is where they came from.

The corpora are ~557 MB of SQLite snapshots, fetched from EDGAR and deliberately
not committed. Their absence is an environment fact, not a code defect, and it
should read as one.

## Absent is not the same as empty

This is the distinction the old guard lost, and it matters more than the skip.

    the corpus is ABSENT        -> skip, naming the file and how to run it
    the corpus is PRESENT but
    lacks the expected rows     -> FAIL

`tests/test_basis_framework_query.py` says it outright, and it is right:

    If the archive has no such rows the positive control fails rather than
    skipping, because a skipped positive control is how a broken filter hides.

A gate that skipped whenever the corpus was unreadable would let a filter that
matches nothing pass in every clean checkout, and the corpus suite is the only
place it could ever be caught. So the guard below checks *existence*, and the
positive control that checks *content* is left to fail loudly in the corpus run.

## What this module is and is not

It declares which corpora exist, where they live, and which tracked tests need
them. It does not fetch anything, does not build anything, and does not decide
what a corpus proves. `run_corpus_tests.py` uses it to run exactly the
corpus-dependent classes.

The per-round JSON artefacts -- 188 untracked files, mostly companyfacts payloads
and the record each research round wrote -- are deliberately NOT declared here.
3.03 measured that every tracked test that reads them is itself an untracked
research test, so declaring them here would put the research corpus into the
production contract.
"""

from __future__ import annotations

import os
import unittest
from typing import Dict, Iterable, List, Optional, Sequence

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.join(HERE, "experiments", "003-llm-evidence-retrieval",
                       "harness")

# stem -> what the corpus is for. Names are stems, not filenames, because that is
# how the tests refer to them: `ARCHIVE = "snapshot-crossframework"`.
CORPORA: Dict[str, str] = {
    "snapshot-universe": "the cross-issuer observation corpus; most retrieval "
                         "and knowledge-state integration reads it",
    "snapshot-crossframework": "rows carrying a basis framework, for the basis "
                               "filter and its near-miss cases",
    "snapshot-227-a1": "the 2.27 first archive slice",
    "snapshot-227-b": "the 2.27 second archive slice",
    "snapshot": "the sealed 2.2.3 snapshot: digest-locked, never regenerated",
}

# Which tracked test classes need which corpus. Declared rather than inferred so
# the answer to "what does the corpus suite run?" is one readable table, and so a
# test that starts needing a corpus has to say so.
CORPUS_TESTS: Dict[str, Sequence[str]] = {
    # `test_eval_harness` was archived with its experiment at `b124123`; the two
    # assertions it made about active production modules are kept in
    # `tests/test_evaluation_format_boundary.py`, which needs no corpus. It is not
    # listed here because it is no longer a module of this repository's active
    # suite, and `run_corpus_tests.py` loads every name in this table by module.
    "test_vendor_debt_projection": ("snapshot",),
    "test_basis_framework_query": ("snapshot-crossframework",),
    "test_source_conditional_metric_retrieval": ("snapshot-universe",),
    "test_evidence_query_knowledge_state": (
        "snapshot-universe", "snapshot-crossframework",
        "snapshot-227-a1", "snapshot-227-b"),
    "test_knowledge_state_reader_integration": (
        "snapshot-universe", "snapshot-crossframework",
        "snapshot-227-a1", "snapshot-227-b"),
}

# Corpora a test accepts in any combination, because it globs rather than names.
CORPUS_TESTS_ANY: Dict[str, Sequence[str]] = {
    "test_vendor_debt_projection": (
        "snapshot-universe", "snapshot-crossframework",
        "snapshot-227-a1", "snapshot-227-b", "snapshot"),
}

RUN_COMMAND = "python run_corpus_tests.py"


def corpus_path(stem: str) -> str:
    """
    Where a corpus is, or would be.

    No existence test. A caller that needs to know whether it is there must ask,
    so that "missing" is always a decision somebody made visible rather than an
    `OperationalError` three frames later.
    """
    return os.path.join(HARNESS, "%s.sqlite" % stem)


def available(stems: Iterable[str]) -> Dict[str, Optional[str]]:
    """
    stem -> path, or None when absent. One query for all of them, so a test never
    discovers its corpus is missing one file at a time.
    """
    return {stem: (corpus_path(stem)
                   if os.path.isfile(corpus_path(stem)) else None)
            for stem in stems}


def missing(stems: Iterable[str]) -> List[str]:
    return sorted(stem for stem in stems
                  if not os.path.isfile(corpus_path(stem)))


def require(testcase: unittest.TestCase, *stems: str) -> Dict[str, str]:
    """
    Skip unless every named corpus is present. Returns the paths when it does.

    The skip message names each missing corpus, its purpose, and the command that
    runs the tests which need it -- so a skip reads as a declaration about the
    environment rather than as a test that quietly stopped testing anything.
    """
    absent = missing(stems)
    if absent:
        detail = "; ".join(
            "%s (%s)" % (stem, CORPORA.get(stem, "research corpus"))
            for stem in absent)
        testcase.skipTest(
            "research corpus not present: %s. %d of %d required. "
            "These are corpus-dependent tests; run `%s` where the corpora are "
            "available." % (detail, len(absent), len(stems), RUN_COMMAND))
    return {stem: corpus_path(stem) for stem in stems}


def require_any(testcase: unittest.TestCase, *stems: str) -> Dict[str, str]:
    """
    Skip only when *every* named corpus is absent.

    For a test that inspects whatever archives it finds -- it globs a directory
    rather than naming a file. Such a test has no opinion about which corpus it
    reads, so requiring all of them would be a false declaration, and requiring
    one specific archive would be a brittle one.

    The distinction from `require` matters when a corpus is present but empty: if
    any archive is there, the test runs, and the caller's own positive control
    decides whether an empty result is a failure. Absence is the only thing this
    gate suppresses.
    """
    present = {stem: path for stem, path in available(stems).items() if path}
    if not present:
        testcase.skipTest(
            "no research corpus present. %s looks in any of: %s. Run `%s` where "
            "the corpora are available."
            % (testcase.id().rsplit(".", 1)[-1], ", ".join(sorted(stems)),
               RUN_COMMAND))
    return present


def require_module(*stems: str) -> None:
    """
    Module-level guard: raises `unittest.SkipTest`, which skips the whole module.

    Raises rather than returns, because a module-level guard that fails to fire
    is exactly the bug that made this round necessary -- the previous guard tested
    `os.path.isdir(H)`, which is true in every checkout because the harness
    directory is tracked, so it never fired anywhere.
    """
    if missing(stems):
        raise unittest.SkipTest(reason(*stems))


def reason(*stems: str) -> str:
    """
    The message `require` would skip with, for a module-level guard.

    `setUpModule` cannot call `require` -- there is no TestCase -- but it can
    raise `unittest.SkipTest` with the same text, and the whole module is then
    reported as skipped with a reason rather than as a wall of failures.
    """
    absent = missing(stems)
    detail = "; ".join("%s (%s)" % (stem, CORPORA.get(stem, "research corpus"))
                       for stem in absent)
    return ("research corpus not present: %s. These are corpus-dependent "
            "tests; run `%s` where the corpora are available."
            % (detail, RUN_COMMAND))


def census() -> Dict[str, object]:
    """
    Which corpora this machine actually has. For the corpus runner's preamble and
    for a human deciding whether a clean-checkout result means anything.
    """
    state = available(CORPORA)
    return {
        "harness_dir_present": os.path.isdir(HARNESS),
        "corpora": {stem: {"present": path is not None,
                           "bytes": (os.path.getsize(path)
                                     if path and os.path.isfile(path) else 0),
                           "purpose": CORPORA[stem]}
                   for stem, path in sorted(state.items())},
        "absent": [s for s, p in sorted(state.items()) if p is None],
        "run_command": RUN_COMMAND,
    }