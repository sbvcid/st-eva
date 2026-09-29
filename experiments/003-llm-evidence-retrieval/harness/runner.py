"""
Run one model over the whole dataset, and keep everything.

The runner's job is to make a result *repeatable and attributable*: same
dataset, same archive, same tool surface, and a record of what produced each
answer. A finding about a model is worthless if the run cannot be reproduced
with the same inputs and read back afterwards.

Each run writes its own directory. Runs do not overwrite each other, because
comparing two models means having both, and because a run that overwrote its
own results could not be checked after the fact.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from data_contract import utc_now

from .auditor import Audit, Auditor
from .target import Target, TargetAnswer
from .tools import Toolbox

RUNS_DIRNAME = "runs"
AUDIT_DIRNAME = "audit"
REPORTS_DIRNAME = "reports"


@dataclass
class TestResult:
    """One test, for one model, with everything needed to review it."""

    test_id: str
    capability: str
    question: str
    model_identity: Dict[str, Any]
    answer: TargetAnswer
    audit: Audit
    trace: List[Dict[str, Any]] = field(default_factory=list)
    expectations: Dict[str, Any] = field(default_factory=dict)
    retrieved_observations: List[str] = field(default_factory=list)
    semantic_judgement: Optional[Dict[str, Any]] = None

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "capability": self.capability,
            "question": self.question,
            "model": self.model_identity,
            "answer": self.answer.contract_dict(),
            "audit": self.audit.contract_dict(),
            "trace": self.trace,
            "expectations": self.expectations,
            "retrieved_observations": self.retrieved_observations,
            "semantic_judgement": self.semantic_judgement,
        }


@dataclass
class RunResult:
    """One model's pass over the dataset."""

    model_identity: Dict[str, Any]
    dataset_id: str
    snapshot_path: str
    results: List[TestResult] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    run_dir: str = ""

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.audit.passed)

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "run_dir": self.run_dir,
            "dataset_id": self.dataset_id,
            "snapshot": self.snapshot_path,
            "model": self.model_identity,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total": len(self.results),
            "passed": self.passed,
            "results": [r.contract_dict() for r in self.results],
        }


class Runner:
    """
    Drives a target over a dataset and audits each answer.

    The target receives a fresh toolbox per test. Sharing one would let a later
    test's evidence leak into an earlier test's answer, and a model that had
    already seen the archive would not be answering the question it was given.
    """

    def __init__(
        self,
        dataset: Any,
        snapshot_path: str,
        root: str,
        judge: Optional[Any] = None,
    ) -> None:
        self.dataset = dataset
        self.snapshot_path = snapshot_path
        self.root = root
        self.judge = judge

    @staticmethod
    def identity_of(target: Target) -> Dict[str, Any]:
        """
        What the target says it is.

        `contract_dict` is preferred where the target publishes one, because a
        target may compute its identity from its configuration; falling back to
        the raw attribute would record an incomplete identity for exactly those
        targets whose identity varies.
        """
        if hasattr(target, "contract_dict"):
            return dict(target.contract_dict())
        return dict(target.identity)

    def run(self, target: Target) -> RunResult:
        identity = self.identity_of(target)
        run = RunResult(
            model_identity=identity,
            dataset_id=self.dataset.dataset_id,
            snapshot_path=self.snapshot_path,
            started_at=utc_now(),
        )
        run.run_dir = self._run_dir(identity)
        os.makedirs(os.path.join(run.run_dir, AUDIT_DIRNAME), exist_ok=True)
        os.makedirs(os.path.join(run.run_dir, RUNS_DIRNAME), exist_ok=True)

        for test in self.dataset.tests:
            result = self._run_one(test, target)
            run.results.append(result)
            self._write(os.path.join(run.run_dir, AUDIT_DIRNAME,
                                     f"{test.test_id}.json"),
                        result.contract_dict())
            self._write(os.path.join(run.run_dir, RUNS_DIRNAME,
                                     f"{test.test_id}.trace.json"),
                        {"trace": result.trace,
                         "answer": result.answer.contract_dict()})

        run.finished_at = utc_now()
        self._write(os.path.join(run.run_dir, "run.json"), run.contract_dict())
        return run

    def _run_one(self, test: Any, target: Target) -> TestResult:
        from evidence_query import EvidenceQuery

        query = EvidenceQuery.open(self.snapshot_path)
        try:
            tools = Toolbox(_query=query)
            try:
                answer = target.answer(test.question, tools)
            finally:
                trace = tools.contract_dict()
                retrieved = tools.observations_cited()
                close = query.close

            auditor = Auditor(_query_connection(self.snapshot_path), query)
            # The expectations travel with the audit so that a check reads them
            # off the object it was handed, rather than from shared state where
            # one test's ground truth could answer another's question.
            audit = Audit(
                test_id=test.test_id,
                expectations=dict(test.expectations),
                answer_text=answer.answer,
            )
            test.audit(auditor, audit, answer, tools, retrieved)
            close()
        finally:
            pass

        semantic = None
        if self.judge is not None:
            semantic = self.judge.judge(test, answer)

        return TestResult(
            test_id=test.test_id,
            capability=test.capability,
            question=test.question,
            model_identity=Runner.identity_of(target),
            answer=answer,
            audit=audit,
            trace=trace,
            expectations=test.expectations_for_review(),
            retrieved_observations=sorted(retrieved),
            semantic_judgement=semantic,
        )

    def _run_dir(self, identity: Dict[str, Any]) -> str:
        """
        A directory named for the model, so two runs never collide.

        A missing identity field is refused rather than filled with
        "unknown": a run directory called `unknown-wrong-value-unknown` is not
        attributable, and a result nobody can attribute is not evidence.
        """
        missing = [
            part for part in ("provider", "model", "version")
            if not identity.get(part)
        ]
        if missing:
            raise ValueError(
                f"the target's identity is missing {missing}; a run cannot be "
                "attributed to a model that does not say which model it is"
            )
        name = "-".join(
            str(identity[part]) for part in ("provider", "model", "version")
        ).replace("/", "_")
        return os.path.join(self.root, RUNS_DIRNAME, name)

    @staticmethod
    def _write(path: str, payload: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, default=str)


def _query_connection(snapshot_path: str) -> Any:
    """
    The auditor's own read-only connection.

    Separate from the target's, on purpose. The auditor must be able to see the
    database directly, and the target must not be able to, and sharing one
    connection would make the boundary a convention rather than a fact.
    """
    import sqlite3

    connection = sqlite3.connect(snapshot_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection
