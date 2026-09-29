"""
Re-audit the recorded real-model run with the corrected evaluator.

The recorded answers do not change — the model produced them under conditions
that are now sealed. Only the grading changes, and the question is whether the
two false passes flip. Re-auditing stored answers is also the cheapest possible
way to test a change to the auditor: no model, no network, and the new
evaluator is held against real behaviour rather than against a target written
to please it.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from evidence_query import EvidenceQuery
from harness.auditor import Audit, Auditor
from harness.dataset import build_dataset
from harness.snapshot import default_snapshot_path
from harness.target import TargetAnswer
from harness.tools import Call, Toolbox
from harness.runner import _query_connection

run_dir = os.environ.get(
    "ST_EVA_REAUDIT",
    os.path.join(HERE, "runs", "ollama-local-qwen3-14b"),
)
snapshot = default_snapshot_path()
dataset = build_dataset(snapshot)
by_id = {t.test_id: t for t in dataset.tests}
query = EvidenceQuery.open(snapshot)
connection = _query_connection(snapshot)
auditor = Auditor(connection, query)

import json

before = json.load(open(os.path.join(run_dir, "reports", "report.json")))
before_pass = {t["test_id"]: t["passed"]
               for t in before["query_behaviour"]}

rows = []
for test in dataset.tests:
    stored = json.load(
        open(os.path.join(run_dir, "audit", f"{test.test_id}.json"))
    )
    answer = TargetAnswer.parse(json.dumps(stored["answer"]["answer"] and {
        "answer": stored["answer"]["answer"],
        "evidence_refs": stored["answer"]["evidence_refs"],
        "derived_refs": stored["answer"]["derived_refs"],
        "uncertainties": stored["answer"]["uncertainties"],
    }))
    # Rebuild the toolbox's call log from the stored trace, so the checks that
    # read the trace (did it consult the series? did the filter run?) see what
    # the model actually did rather than an empty log.
    tools = Toolbox(_query=query)
    tools.calls = [
        Call(
            sequence=c["sequence"],
            operation=c["operation"],
            arguments=c["arguments"],
            error=c.get("error"),
        )
        for c in stored["trace"]
    ]
    retrieved = set(stored["retrieved_observations"])
    audit = Audit(
        test_id=test.test_id,
        expectations=dict(test.expectations),
        answer_text=answer.answer,
    )
    test.audit(auditor, audit, answer, tools, retrieved)
    rows.append((test.test_id, before_pass[test.test_id], audit.passed, audit))

print("%-28s %-8s %-8s %s" % ("test", "before", "after", "changed by"))
print("-" * 78)
flips = 0
for test_id, was, now, audit in rows:
    changed = "FLIPPED" if was != now else ""
    if was != now:
        flips += 1
    print("%-28s %-8s %-8s %s" % (test_id, was, now, changed))
print()
print(f"flipped: {flips}")
print(f"passed before: {sum(1 for _, w, _, _ in rows if w)}/{len(rows)}")
print(f"passed after:  {sum(1 for _, _, n, _ in rows if n)}/{len(rows)}")
for test_id, was, now, audit in rows:
    if was != now:
        for check in audit.checks:
            if check.passed is not True:
                print(f"  {test_id}: {check.name} -> {check.detail[:90]}")
query.close()
connection.close()
