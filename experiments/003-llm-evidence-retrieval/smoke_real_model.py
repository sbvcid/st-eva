"""
Run one real model against one question, and print everything.

The point of this before the full run is to fail cheaply. A tool-loop bug, a
schema the model cannot parse, a snapshot that has gone missing — all of them
show up in one question in a minute, rather than across fifteen in an hour.
"""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from harness.dataset import build_dataset
from harness.providers import ProviderConfig
from harness.runner import Runner
from harness.snapshot import default_snapshot_path
from harness.tool_target import ToolCallingTarget

model = os.environ.get("ST_EVA_TEST_MODEL", "qwen3:14b")
base = os.environ.get("ST_EVA_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
only = os.environ.get("ST_EVA_TEST_ID")

path = default_snapshot_path()
dataset = build_dataset(path)
if only:
    dataset.tests = [t for t in dataset.tests if t.test_id == only]
    if not dataset.tests:
        raise SystemExit(f"no test {only!r}; have {[t.test_id for t in dataset.tests]}")

config = ProviderConfig(
    base_url=base,
    model=model,
    provider="ollama-local",
    version=model,
    temperature=0.0,
    max_tokens=1600,
    timeout_seconds=900,
)
target = ToolCallingTarget(config=config)

print(f"model   {config.provider}/{config.model}")
print(f"tests   {[t.test_id for t in dataset.tests]}\n")

started = time.time()
run = Runner(dataset, path, HERE).run(target)
print(f"elapsed {time.time() - started:.0f}s\n")

for result in run.results:
    verdict = "PASS" if result.audit.passed else "FAIL"
    print(f"=== {result.test_id}  {verdict}  "
          f"({len(result.audit.checks)} checks, "
          f"{len(result.audit.failed_checks)} failed)")
    print(f"Q: {result.question[:150]}")
    print(f"A: {result.answer.answer[:400]}")
    print(f"   refs={result.answer.evidence_refs[:4]}")
    if result.answer.parse_error:
        print(f"   parse_error={result.answer.parse_error}")
    record = result.target_run or {}
    print(f"   stop_reason={record.get('stop_reason')} "
          f"exchanges={len(record.get('exchanges', []))} "
          f"tool_calls={len(result.trace)}")
    for check in result.audit.checks:
        if check.passed is not True:
            print(f"   - {check.name}: expected={str(check.expected)[:60]} "
                  f"actual={str(check.actual)[:60]} "
                  f"class={check.classification}")
    print()
