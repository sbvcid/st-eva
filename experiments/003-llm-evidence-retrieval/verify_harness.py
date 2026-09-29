"""Run every deliberately-broken target and print what the auditor caught.

A harness that has only graded a correct answer has been used, not tested. This
is the check that it can fail an answer, and that it attributes the failure to
the model rather than to ST-EVA.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import reference, report as report_module
from harness.dataset import build_dataset
from harness.runner import Runner
from harness.snapshot import default_snapshot_path

path = default_snapshot_path()
root = os.path.dirname(os.path.abspath(__file__))
dataset = build_dataset(path)

print("%-24s %-12s %-22s %s" % (
    "target", "failed", "classified", "tests that caught it"))
print("-" * 100)

reference_run = Runner(dataset, path, root).run(reference.CorrectTarget())
print("%-24s %-12s %-22s %s" % (
    "reference (correct)",
    f"{reference_run.results and sum(1 for r in reference_run.results if not r.audit.passed)}"
    f"/{len(reference_run.results)}",
    "-",
    "none, as it should be",
))
print()

for name, factory in sorted(reference.BROKEN_TARGETS.items()):
    run = Runner(dataset, path, root).run(factory())
    report = report_module.build_report(run)
    classes = " ".join(
        f"{code}={entry['count']}"
        for code, entry in report["failures_by_classification"].items()
        if entry["count"]
    )
    caught = ", ".join(report["human_review"]["sampled_failures"][:5])
    print("%-24s %-12s %-22s %s" % (
        name,
        f"{report['totals']['failed']}/{report['totals']['tests']}",
        classes or "NONE CAUGHT",
        caught,
    ))
