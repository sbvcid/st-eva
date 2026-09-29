"""
The first real-model run.

One model, the sealed 15-test dataset, the same snapshot, the same tools, the
same mechanical auditor that graded the scripted targets.

Nothing here is tuned for the model. The dataset was fixed before any model
ran, the auditor does not know which model produced an answer, and the only
thing that changes between this run and the next is the target.

    python run_real_model.py
"""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from harness import report as report_module
from harness.dataset import build_dataset
from harness.providers import ProviderConfig
from harness.runner import Runner
from harness.snapshot import default_snapshot_path
from harness.tool_target import ToolCallingTarget

# The model under test. Read from the environment so the same script runs the
# second model later without being edited, which is what keeps "the only
# variable is the model" true rather than merely intended.
MODEL = os.environ.get("ST_EVA_TEST_MODEL", "qwen3:14b")
BASE_URL = os.environ.get("ST_EVA_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
PROVIDER = os.environ.get("ST_EVA_LLM_PROVIDER", "ollama-local")
ONLY = os.environ.get("ST_EVA_TEST_ID")


def main() -> int:
    path = default_snapshot_path()
    if not os.path.exists(path):
        print(
            "no snapshot; build it with: python -m harness --build --live",
            file=sys.stderr,
        )
        return 2

    dataset = build_dataset(path)
    if ONLY:
        dataset.tests = [t for t in dataset.tests if t.test_id == ONLY]
        if not dataset.tests:
            raise SystemExit(f"no test {ONLY!r}")

    config = ProviderConfig(
        base_url=BASE_URL,
        model=MODEL,
        provider=PROVIDER,
        version=MODEL,
        temperature=0.0,
        max_tokens=1600,
        timeout_seconds=900,
    )
    target = ToolCallingTarget(config=config)

    print(f"model    {config.provider}/{config.model}")
    print(f"tests    {len(dataset.tests)}")
    print(f"snapshot {path}\n", flush=True)

    started = time.time()
    run = Runner(dataset, path, HERE).run(target)
    report = build_report_for(run)
    report_module.write_report(HERE, report, run.run_dir)

    print(f"\nelapsed  {time.time() - started:.0f}s")
    print(f"run dir  {run.run_dir}\n")
    print(report_module.render(report), flush=True)
    return 0


def build_report_for(run):
    """
    The standard report, plus the query-behaviour counts a real model makes
    possible and a scripted target never would.

    Tool calls per test, failed calls, abandoned pagination: these are how a
    model uses the surface, which is a different question from whether its
    answers were right, and the two diverge.
    """
    report = report_module.build_report(run)
    per_test = []
    for result in run.results:
        record = result.target_run or {}
        failed = [c for c in result.trace if c.get("error")]
        operations = [c["operation"] for c in result.trace]
        pagination = [o for o in operations if o == "page"]
        cursors = [
            c["arguments"].get("cursor")
            for c in result.trace
            if c["operation"] == "page"
        ]
        per_test.append(
            {
                "test_id": result.test_id,
                "passed": result.audit.passed,
                "tool_calls": len(result.trace),
                "failed_calls": len(failed),
                "operations": sorted(set(operations)),
                "page_calls": len(pagination),
                "cursors_used": len([c for c in cursors if c]),
                "abandoned_pagination": bool(
                    pagination and cursors and cursors[-1] is None and
                    len(pagination) == 1 and
                    (result.target_run or {}).get("stop_reason") == "answered"
                    and not result.audit.passed
                ),
                "first_reply_parsed": record.get("first_reply_parsed"),
                "format_repair_used": record.get("format_repair_used"),
                "stop_reason": record.get("stop_reason"),
                "elapsed_seconds": record.get("elapsed_seconds"),
                "observations_retrieved": len(result.retrieved_observations),
                "uncertainties": len(result.answer.uncertainties),
            }
        )
    report["query_behaviour"] = per_test
    report["query_totals"] = {
        "tests": len(per_test),
        "tool_calls": sum(t["tool_calls"] for t in per_test),
        "failed_calls": sum(t["failed_calls"] for t in per_test),
        "format_repair_turns": sum(
            1 for t in per_test if t["format_repair_used"]
        ),
        "first_reply_parse_failures": sum(
            1 for t in per_test if t["first_reply_parsed"] is False
        ),
        "tests_with_no_evidence_retrieved": sum(
            1 for t in per_test if t["observations_retrieved"] == 0
        ),
        "mean_tool_calls": (
            round(
                sum(t["tool_calls"] for t in per_test) / len(per_test), 2
            )
            if per_test else 0
        ),
    }
    return report


if __name__ == "__main__":
    raise SystemExit(main())
