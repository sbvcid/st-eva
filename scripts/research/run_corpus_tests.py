"""
ST-EVA 3.03 -- run the corpus-dependent tests, and only those.

## Why this exists

3.03 made a clean checkout's production suite honest: tests that need the
research corpora declare that and skip with a reason naming the missing file,
rather than failing with `OperationalError: unable to open database file`.

That is only half of the arrangement. A skip is a promise that the work happens
somewhere else, and this is where it happens. Without it, "skipped in CI" is
indistinguishable from "never checked", and the whole point of gating rather than
fixing is that the gated tests still get run.

    python scripts/research/run_corpus_tests.py            # the corpus-dependent tests
    python scripts/research/run_corpus_tests.py --census   # what is present and what is not
    python scripts/research/run_corpus_tests.py --all      # production suite, then the corpus one

## What it will not do

It will not build, fetch or substitute a corpus. A test that passes because it
was quietly pointed at a different archive is worse than a test that skipped,
because it reports coverage it does not have. If a corpus is absent, the runner
says so and stops.

## The two modes, and why both exist

`CORPUS_TESTS`  requires specific corpora. A test here reads a named archive.
`CORPUS_TESTS_ANY` accepts any one of several, for a test that globs a
directory rather than naming a file. Those are different claims and the gate
distinguishes them; the runner reports them separately rather than flattening
them into one list.
"""

from __future__ import annotations

# Keep repository modules, repository-relative data paths, and sibling research
# scripts available after this utility is stored under scripts/research/.
import os as _os
import sys as _sys
from pathlib import Path as _Path

_SCRIPT_DIR = _Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parents[1]
for _path in (str(_REPO_ROOT), str(_SCRIPT_DIR)):
    if _path not in _sys.path:
        _sys.path.insert(0, _path)

import argparse
import io
import json
import os
import sys
import unittest

HERE = str(_REPO_ROOT)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import corpus_gate  # noqa: E402


def load(modules) -> list:
    """
    `tests/` is not a package -- there is no `__init__.py` -- and every test
    module puts its own directory on `sys.path`. The corpus runner does the same
    so that a module named here loads the way `unittest discover` loads it,
    rather than through a package path that does not exist.
    """
    tests_dir = os.path.join(HERE, "tests")
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    suite = unittest.TestSuite()
    for name in modules:
        suite.addTests(unittest.defaultTestLoader.loadTestsFromName(name))
    return suite


def report_census() -> int:
    state = corpus_gate.census()
    print("harness directory present: %s" % state["harness_dir_present"])
    print("\n%-28s %-9s %12s  %s"
          % ("corpus", "present", "bytes", "purpose"))
    for stem, info in state["corpora"].items():
        print("%-28s %-9s %12s  %s"
              % (stem, "yes" if info["present"] else "NO",
               format(info["bytes"], ",") if info["present"] else "-",
               info["purpose"][:58]))
    absent = state["absent"]
    print("\n%d of %d corpora present." % (
        len(state["corpora"]) - len(absent), len(state["corpora"])))
    if absent:
        print("absent: %s" % ", ".join(absent))
        print("\nThe corpus-dependent tests cannot run. This is an environment "
              "fact, not a code defect.")
        return 1
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census", action="store_true",
                        help="report which corpora are present, then exit")
    parser.add_argument("--all", action="store_true",
                        help="run the production suite first, then this one")
    args = parser.parse_args(argv)

    if args.census:
        return report_census()

    if args.all:
        print("== production suite (no corpus required) ==")
        production = unittest.defaultTestLoader.discover(
            os.path.join(HERE, "tests"))
        production_result = unittest.TextTestRunner(verbosity=1).run(production)
        if not production_result.wasSuccessful():
            return 1

    state = corpus_gate.census()
    if state["absent"]:
        report_census()
        return 1

    named = sorted(corpus_gate.CORPUS_TESTS)
    any_of = sorted(set(corpus_gate.CORPUS_TESTS_ANY) - set(named))
    print("== corpus suite ==")
    print("requires a named corpus : %s" % ", ".join(named))
    if any_of:
        print("requires any one corpus : %s" % ", ".join(any_of))

    suite = load(named + any_of)
    result = unittest.TextTestRunner(verbosity=2).run(suite)

    report = {
        "corpora": state["corpora"],
        "modules_named_corpus": named,
        "modules_any_corpus": any_of,
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
    }
    out = os.path.join(corpus_gate.HARNESS,
                       "303-corpus-suite-result.json")
    with io.open(out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())