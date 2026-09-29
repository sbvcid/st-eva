"""
Reporting: per-test results, aggregated by capability, with failures surfaced.

Deliberately no single quality score. A weighted total over these capabilities
would be a number with no unit: it would let a model that is exact on values
and invents provenance score the same as one that does the opposite, and the
average would be the only figure anyone quoted.

What is reported instead:

    per test        pass or fail, and the checks that decided it
    per capability  how many passed, which is the unit a reader can act on
    failures        all of them, each classified
    a sample of passes, so the evaluator can be calibrated against successes
                    as well as failures

The classified failure counts are the part that changes what happens next. A
run with many B failures is a finding about the model. A run with A failures is
a defect report. A run with C failures means the evaluation itself is broken and
nothing else in it should be believed until that is fixed.
"""

from __future__ import annotations

import json
import os
import random
from typing import Any, Dict, List, Optional

from .auditor import CAPABILITIES, CLASSIFICATION_MEANING


def build_report(
    run: Any,
    human_review_sample: int = 5,
    seed: int = 17,
) -> Dict[str, Any]:
    """
    Summarise one run.

    `seed` is fixed so the "random sample of passes" is reproducible: a review
    sample that changes on every run cannot be compared between two runs, which
    defeats the purpose of sampling.
    """
    results = run.results
    by_capability: Dict[str, Dict[str, Any]] = {
        code: {
            "capability": code,
            "name": name,
            "passed": 0,
            "total": 0,
            "failed_tests": [],
        }
        for code, name in CAPABILITIES.items()
    }
    by_class: Dict[str, int] = {}
    failures: List[Dict[str, Any]] = []
    passes: List[str] = []
    unverifiable: List[Dict[str, Any]] = []

    for result in results:
        # Aggregated by the capability of each *check*, not by the one the test
        # was declared under. A test for an exact value also checks the unit
        # and the period, and reporting those against "value accuracy" only
        # would show F3 as untested while checks for it were running.
        for code in {check.capability for check in result.audit.checks}:
            if code not in by_capability:
                continue
            by_capability[code]["total"] += 1
            if result.audit.passed:
                by_capability[code]["passed"] += 1
            else:
                by_capability[code]["failed_tests"].append(result.test_id)

        if result.audit.passed:
            passes.append(result.test_id)
            continue

        for check in result.audit.failed_checks:
            # A check that could not be made is not a failure. Counting it as
            # one would make an evaluator's blindness look like a model's
            # mistake, which is the error this whole classification scheme
            # exists to prevent.
            if check.passed is None:
                unverifiable.append(
                    {
                        "test_id": result.test_id,
                        "check": check.name,
                        "detail": check.detail,
                        "classification": check.classification,
                    }
                )
                continue
            classification = check.classification or "B"
            by_class[classification] = by_class.get(classification, 0) + 1
            failures.append(
                {
                    "test_id": result.test_id,
                    "capability": check.capability,
                    "capability_name": CAPABILITIES.get(check.capability, ""),
                    "check": check.name,
                    "expected": check.expected,
                    "actual": check.actual,
                    "detail": check.detail,
                    "classification": classification,
                    "answer": result.answer.answer,
                    "evidence_refs": result.answer.evidence_refs,
                    "trace": result.trace,
                }
            )

    reviewer = random.Random(seed)
    sample = sorted(reviewer.sample(passes, min(human_review_sample, len(passes))))

    return {
        "run_dir": run.run_dir,
        "model": run.model_identity,
        "dataset_id": run.dataset_id,
        "snapshot": run.snapshot_path,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "totals": {
            "tests": len(results),
            "passed": sum(1 for r in results if r.audit.passed),
            "failed": sum(1 for r in results if not r.audit.passed),
        },
        "by_capability": list(by_capability.values()),
        "failures_by_classification": {
            code: {
                "count": by_class.get(code, 0),
                "meaning": meaning,
            }
            for code, meaning in CLASSIFICATION_MEANING.items()
        },
        "failures": failures,
        "unverifiable_checks": unverifiable,
        "human_review": {
            "sample_of_passes": sample,
            "sampled_failures": sorted({f["test_id"] for f in failures}),
            "purpose": (
                "calibration: a sample of passes and all failures, so the "
                "evaluator can be checked against successes as well as "
                "failures"
            ),
        },
        "scoring_note": (
            "No overall quality score is produced. The capabilities are not "
            "interchangeable, and averaging them would let exact values buy "
            "invented provenance."
        ),
    }


def render(report: Dict[str, Any]) -> str:
    """
    The review view.

    Short on purpose: a report nobody reads to the end is a report that gets
    skimmed for the headline number, and the headline number is the thing this
    evaluation refuses to produce.
    """
    lines: List[str] = []
    model = report["model"]
    lines.append(
        f"model      {model.get('provider')}/{model.get('model')}"
        f" v{model.get('version')}"
    )
    lines.append(f"dataset    {report['dataset_id']}")
    totals = report["totals"]
    lines.append(
        f"tests      {totals['passed']}/{totals['tests']} passed, "
        f"{totals['failed']} failed"
    )
    lines.append("")
    lines.append("capability                 passed/total")
    for entry in report["by_capability"]:
        if not entry["total"]:
            continue
        lines.append(
            f"  {entry['capability']} {entry['name']:<26}"
            f"{entry['passed']}/{entry['total']}"
        )
    lines.append("")
    lines.append("failures by classification")
    for code, entry in report["failures_by_classification"].items():
        if entry["count"]:
            lines.append(f"  {code}  {entry['count']:>3}  {entry['meaning']}")
    if report["unverifiable_checks"]:
        lines.append("")
        lines.append(
            f"unverifiable checks: {len(report['unverifiable_checks'])} "
            "(not counted as failures)"
        )
    if report["failures"]:
        lines.append("")
        lines.append("failed tests")
        for test_id in report["human_review"]["sampled_failures"]:
            lines.append(f"  {test_id}")
    lines.append("")
    lines.append(f"review sample of passes: {report['human_review']['sample_of_passes']}")
    return "\n".join(lines)


def write_report(root: str, report: Dict[str, Any], run_dir: str) -> str:
    path = os.path.join(run_dir, "reports", "report.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True, default=str)
    return path
