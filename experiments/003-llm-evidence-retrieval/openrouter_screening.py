"""
Model-capability screening against OpenRouter.

This is not a new evaluation. It is the sealed 15-test dataset, the sealed
snapshot, the sealed eight-operation tool surface, the sealed mechanical
auditor, and a different model answering. Nothing here changes what counts as a
failure, because the question is not "which model is best" — it is "which models
can consume ST-EVA evidence at all, and which failure modes do they have".

Three phases, in this order, and a model only advances if it earned it:

    smoke     one question, one tool call. Proves the wire format, the tool
              schemas, the tool loop, the trace and the audit pipeline work
              before any screening request is spent.
    screen    five tests chosen to separate retrieval, tool use, semantic
              distinction, conflict handling and provenance discipline.
    full      the sealed 15. Only for models that pass the capability gate.

Cost discipline is part of the design. Free endpoints have a daily request
allowance, a failed request can spend it, and an evaluation that retries its way
through a rate limit is not an evaluation. So: bounded retries on transport
errors only, every request recorded whether it succeeded or not, and the ledger
stops the run when the allowance is gone rather than quietly switching provider.

Credentials are read from the environment at call time and are never written into
a config, a trace, a report or a run directory. The run is attributable from its
provider, model and inference settings alone, which is the point of writing any
of it down.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from evidence_query import EvidenceQuery
from harness import report as report_module
from harness import consumer as consumer_module
from harness.auditor import (
    CLASS_DATASET,
    CLASS_EVALUATOR,
    Audit,
    Auditor,
    Check,
)
from harness.dataset import Dataset, Test, build_dataset
from harness.probes import as_tests as probes_as_tests
from harness.probes import probe_dataset
from harness.providers import ProviderConfig
from harness.runner import Runner, TestResult, _query_connection
from harness.schemas import tool_schemas
from harness.snapshot import default_snapshot_path
from harness.target import TargetAnswer
from harness.tool_target import MAX_EXCHANGES, ToolCallingTarget
from harness.tools import OPERATIONS, Toolbox

SCREENING_DIRNAME = "openrouter-screening"
PROVIDER = "openrouter"
BASE_URL = "https://openrouter.ai/api/v1"

SCREENING_TESTS = (
    "T1_exact_value",
    "T3_pagination",
    "T6_reported_vs_derived",
    "T8_conflict",
    "T13_provenance_chain",
)

# The four models fixed for this round. `requested_slug` is what was asked for
# and `model_id` is what OpenRouter's catalogue actually serves today; where they
# differ, both are recorded rather than one quietly replacing the other, because
# "the model we tested" has to mean one specific thing to anyone reading this
# later. A slug that does not exist is never quietly swapped for a neighbouring
# model: it is reported unavailable and the model is skipped.
MODELS: List[Dict[str, Any]] = [
    {
        "name": "stealth-space-bunny-alpha",
        "requested_slug": "stealth/space-bunny-alpha:free",
        "model_id": "stealth/space-bunny-alpha",
        "dir": "stealth-space-bunny-alpha",
        "seed": None,
    },
    {
        "name": "nvidia-nemotron-3-ultra",
        "requested_slug": "nvidia/nemotron-3-ultra-550b-a55b:free",
        "model_id": "nvidia/nemotron-3-ultra-550b-a55b:free",
        "dir": "nvidia-nemotron-3-ultra",
        "seed": 7,
    },
    {
        "name": "google-gemma-4-26b-a4b-it",
        "requested_slug": "google/gemma-4-26b-a4b-it:free",
        "model_id": "google/gemma-4-26b-a4b-it:free",
        "dir": "google-gemma-4-26b-a4b-it",
        "seed": 7,
    },
    {
        "name": "inclusionai-ling-3-0-flash-fin",
        "requested_slug": "inclusionai/ling-3.0-flash-fin:free",
        "model_id": None,
        "dir": "inclusionai-ling-3-0-flash-fin",
        "seed": 7,
    },
]

SMOKE_TEST_ID = "S0_tool_call_smoke"

# What each test is for, in the language a consumer of the evidence would use.
#
# The sealed dataset classifies by check id (F1..F11), which is right for a
# grader and wrong for a decision: nobody decides whether to use a model by
# asking which F-numbers it satisfies. These are the questions that actually get
# asked of a model reading financial evidence, and the rollup is reported in
# them, with the F-ids left in the per-test detail.
CONSUMER_CAPABILITY: Dict[str, str] = {
    "T1_exact_value": "evidence retrieval",
    "T2_series": "evidence retrieval",
    "T3_pagination": "pagination",
    "T4_point_in_time": "temporal discipline",
    "T5_source_attribution": "provenance",
    "T6_reported_vs_derived": "reported vs derived",
    "T7_validation": "provenance",
    "T8_conflict": "conflict handling",
    "T9_unavailable": "negative states",
    "T10_concept_evolution": "concept semantics",
    "T11_partial_mapping": "concept semantics",
    "T12_non_comparable": "concept semantics",
    "T13_provenance_chain": "provenance",
    "T14_truncation_trap": "pagination",
    "T15_inference_boundary": "reported vs derived",
}

# What each probe is for, in the same language.
#
# A probe is not a sealed test and gets its own line here, because the two are
# measured differently: a sealed test grades a prose answer, and a probe grades
# fields. Putting them in one table would invite reading a probe's rate as if it
# were comparable to a sealed test's.
PROBE_CAPABILITY: Dict[str, str] = {
    "probe-P1_reported_or_derived": "reported vs derived",
    "probe-P2_negative_state_cause": "negative states",
    "probe-P3_disagreement_meaning": "conflict handling",
    "probe-P4_partial_mapping_meaning": "concept semantics",
    "probe-P5_two_concepts_one_series": "concept semantics",
}

# Retries are for the transport, never for the model. A refused request and a
# wrong answer are both results; an unreachable endpoint is neither, and only the
# second is worth spending another request on.
TRANSPORT_RETRIES = 2

_SMOKE_QUESTION = (
    "Run the coverage_report tool for AAPL. Then state how many metrics ST-EVA "
    "holds for AAPL. If the report names a source document reference, fetch it "
    "with get_source_document and say whether the filing text is available."
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _git(*args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=HERE,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _file_hash(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def environment_block(snapshot_path: str) -> Dict[str, Any]:
    """
    Everything a later reader needs to know this run was the run it claims.

    Hashes rather than file copies: the snapshot is a build artefact and is not
    committed, so "which snapshot" has to be answerable from the run directory
    alone. The tool schema hash matters for the same reason — if the surface a
    model was shown changes, results from before and after are not comparable,
    and only a hash makes that visible after the fact.
    """
    dataset = build_dataset(snapshot_path)
    query = EvidenceQuery.open(snapshot_path)
    try:
        schemas = tool_schemas(Toolbox(_query=query))
    finally:
        query.close()
    dataset_bytes = json.dumps(
        dataset.contract_dict(), sort_keys=True, default=str
    ).encode("utf-8")
    auditor_path = os.path.join(HERE, "harness", "auditor.py")
    return {
        "provider": PROVIDER,
        "harness_commit": _git("rev-parse", "HEAD"),
        "harness_dirty": bool(_git("status", "--porcelain")),
        "snapshot_path": snapshot_path,
        "snapshot_sha256": _file_hash(snapshot_path),
        "dataset_id": dataset.dataset_id,
        "dataset_version": dataset.version,
        "dataset_sha256": _sha256(dataset_bytes),
        "dataset_test_count": len(dataset.tests),
        "tool_schema_sha256": _sha256(
            json.dumps(schemas, sort_keys=True).encode("utf-8")
        ),
        "tool_operations": list(OPERATIONS),
        "evaluator_version": _git("log", "-1", "--format=%h", "--",
                                 "experiments/003-llm-evidence-retrieval/"
                                 "harness/auditor.py"),
        "evaluator_sha256": _file_hash(auditor_path),
        "max_exchanges": MAX_EXCHANGES,
    }


class ScreeningRunner(Runner):
    """
    The sealed runner, with the run directory fixed in advance.

    The runner normally names a directory after the model's identity, which is
    right for one run per model and wrong for a screening round: these runs are
    grouped by experiment first and by model second, so that the smoke, the five
    screening tests and the full run for one model are read together. Nothing else
    is overridden — the audit, the trace and the artifacts are the runner's.
    """

    def __init__(self, *args: Any, run_dir: str, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fixed_run_dir = run_dir

    def _run_dir(self, identity: Dict[str, Any]) -> str:
        return self.fixed_run_dir

    # One retry per test, on the transport only. The phase-level retry in
    # `run_phase` would re-run every test already completed, and against a daily
    # allowance that is the difference between one lost question and a lost
    # round. A model that never answers is recorded as never answering, which is
    # a result; it is not retried until the allowance is gone.
    TEST_TRANSPORT_RETRIES = 1

    def _run_one(self, test, target):
        from harness.budget import RequestBudget
        from harness.providers import TransportError

        budget = getattr(target.client, "budget", None)
        if isinstance(budget, RequestBudget):
            budget.current_label = test.test_id
        if target.client is not None:
            target.client.current_test = test.test_id
        if budget is not None and not budget.can_start(test.test_id):
            # The allowance is gone. The test is recorded as not run, which is a
            # different thing from failed: nothing here says anything about the
            # model, and marking it failed would spend the run's credibility on
            # a fact about the provider.
            return self._unreached(
                test,
                target,
                f"not run: {budget.stopped_because or 'request budget reached'}",
                0,
                kind="budget",
            )

        attempts = 0
        while True:
            attempts += 1
            try:
                result = super()._run_one(test, target)
                result.target_run = dict(result.target_run or {})
                result.target_run["test_attempts"] = attempts
                return result
            except TransportError as failure:
                self._last_refusal_kind = failure.kind
                retryable = (
                    budget is None
                    or budget.should_retry(failure.kind)
                ) and attempts <= self.TEST_TRANSPORT_RETRIES
                if retryable:
                    time.sleep(
                        budget.retry_after(failure.kind) if budget else 5
                    )
                    continue
                return self._unreached(
                    test, target, str(failure), attempts, kind="transport_error"
                )

    def _unreached(
        self,
        test,
        target,
        detail: str,
        attempts: int,
        kind: str = "transport_error",
    ) -> Any:
        """
        Record a test the model never answered, without inventing a verdict.

        The audit carries a single undecidable check rather than a failure. An
        unreachable model has not been shown to be right or wrong, and grading
        it either way would put a transport fact into the model column — which
        is the specific confusion the classification scheme exists to prevent.

        A budget stop and a transport error are the same kind of fact: the
        experiment did not happen. They are kept apart in the record so a reader
        can tell a provider problem from a spending decision, and both are
        reported as E.
        """
        from harness.tools import Toolbox

        audit = Audit(
            test_id=test.test_id,
            expectations=dict(test.expectations),
            answer_text="",
        )
        audit.checks.append(
            Check(
                capability="F10",
                name=(
                    "the model was reached"
                    if kind == "transport_error"
                    else "the test was run"
                ),
                passed=None,
                expected="a completion from the provider",
                actual="none",
                detail=detail,
                classification="E",
            )
        )
        record = {
            "stop_reason": "budget_exhausted" if kind == "budget"
            else "transport_error",
            "unreached_kind": kind,
            "elapsed_seconds": 0.0,
            "error": detail,
            "first_reply_parsed": None,
            "format_repair_used": False,
            "exchanges": [],
            "tool_definitions": [],
            "initial_messages": [],
            "tool_results": [],
            "test_attempts": attempts,
        }
        return TestResult(
            test_id=test.test_id,
            capability=test.capability,
            question=test.question,
            model_identity=Runner.identity_of(target),
            answer=TargetAnswer(answer="", parse_error=f"TRANSPORT: {detail}"),
            audit=audit,
            trace=[],
            target_run=record,
            expectations=test.expectations_for_review(),
            retrieved_observations=[],
        )


def build_smoke_dataset(snapshot_path: str):
    """
    One question, and the mechanical checks that can be made on it.

    The smoke is not about the answer being right. It is about the plumbing:
    whether the endpoint answered, whether the tool schemas were accepted,
    whether the model emitted a legal tool call, whether the result went back,
    and whether the auditor can ingest the result. A smoke that graded the
    answer would be a very small experiment wearing a smoke test's clothes.
    """

    def audit(auditor, result, answer, tools, retrieved):
        calls = tools.contract_dict()
        succeeded = [c for c in calls if c.get("error") is None]
        result.checks.append(
            Check(
                capability="F10",
                name="the model used the tool surface",
                passed=bool(succeeded),
                expected=">= 1 tool call that returned",
                actual=len(succeeded),
                detail="" if succeeded else "no tool call succeeded",
                classification=None if succeeded else "B",
            )
        )
        result.checks.append(
            Check(
                capability="F4",
                name="the answer parsed into the contract",
                passed=answer.parse_error is None,
                expected="a JSON answer object",
                actual=answer.parse_error or "parsed",
                detail=answer.parse_error or "",
                classification=None if answer.parse_error is None else "B",
            )
        )
        # Citation checks, but only when there was something to cite. A
        # coverage report is an aggregate, not an observation, so a model that
        # answers it correctly and cites no observation id has not failed
        # anything: requiring a citation here would grade the question, not the
        # model. On the real dataset the same checks apply unconditionally,
        # because there the evidence is observations and an uncited answer is
        # an unsupported one.
        if retrieved:
            auditor.check_citations_exist(result, set(answer.evidence_refs))
            auditor.check_citations_were_retrieved(
                result, set(answer.evidence_refs), set(retrieved)
            )
        result.checks.append(
            Check(
                capability="F4",
                name="citation checks applied",
                passed=True,
                expected="applied, or skipped because no observation was returned",
                actual=(
                    f"applied over {len(retrieved)} retrieved observations"
                    if retrieved else "skipped: the tool returned no observations"
                ),
                detail="",
                classification=None,
            )
        )

    test = Test(
        test_id=SMOKE_TEST_ID,
        class_name="Smoke",
        capability="F10",
        question=_SMOKE_QUESTION,
        audit=audit,
        expectations={},
        rubric="the plumbing works, not the answer",
    )

    dataset = Dataset([test], snapshot_path)
    # Its own id, so a smoke artifact can never be mistaken for a dataset run
    # by someone reading the run directory later.
    dataset.dataset_id = "steva-003-openrouter-smoke"
    dataset.version = "1"
    return dataset, test


def quota_snapshot(api_key: str) -> Dict[str, Any]:
    """
    How much of the free allowance is left, read from the account itself.

    Recorded before and after every phase rather than inferred, because a
    screening round that silently runs out of requests produces a result that
    looks like a model failure. Only the counters are kept: the key label and
    anything else identifying the account is dropped, because a run directory
    is a committed artifact and the account is not part of the experiment.
    """
    import urllib.error
    import urllib.request

    request = urllib.request.Request(
        BASE_URL + "/auth/key",
        headers={"Authorization": f"Bearer {api_key}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8")).get("data", {})
    except (urllib.error.URLError, ValueError, OSError) as error:
        return {"error": f"{type(error).__name__}: {error}"}
    return {
        "is_free_tier": data.get("is_free_tier"),
        "limit": data.get("limit"),
        "usage": data.get("usage"),
        "limit_daily": data.get("limit_daily"),
        "usage_daily": data.get("usage_daily"),
        "usage_weekly": data.get("usage_weekly"),
        "limit_weekly": data.get("limit_weekly"),
    }


def select_models(names: Optional[List[str]]) -> List[Dict[str, Any]]:
    if not names:
        return MODELS
    known = {m["name"]: m for m in MODELS}
    chosen = []
    for name in names:
        if name not in known:
            raise SystemExit(f"unknown model {name!r}; have {sorted(known)}")
        chosen.append(known[name])
    return chosen


def make_target(model: Dict[str, Any], api_key: str) -> ToolCallingTarget:
    config = ProviderConfig(
        base_url=BASE_URL,
        model=model["model_id"],
        provider=PROVIDER,
        version=model["model_id"],
        temperature=0.0,
        max_tokens=1600,
        timeout_seconds=900,
        seed=model.get("seed"),
        wire_style="openai",
    )
    return ToolCallingTarget(config=config, client=None, max_exchanges=MAX_EXCHANGES)


def build_probe_phase(snapshot_path: str) -> Dataset:
    """
    The five probes, resolved against the snapshot and wrapped as `Test`s.

    Built from the archive rather than written down, for the same reason the
    sealed dataset is: a hard-coded expected value is a test that can be
    satisfied by the evaluator agreeing with itself. P4 and P5 take their
    comparability answer from the core registry's own `series_breaks`, because
    whether a series is comparable is the registry's rule and a probe that
    restates it would eventually disagree with it.
    """
    from harness.runner import _query_connection
    from evidence_query import EvidenceQuery

    connection = _query_connection(snapshot_path)
    query = EvidenceQuery.open(snapshot_path)
    try:
        tests = probes_as_tests(connection, "AAPL", query.registry())
    finally:
        query.close()
        connection.close()
    dataset = Dataset(tests, snapshot_path)
    dataset.dataset_id = "steva-003a-semantic-probes"
    dataset.version = "1"
    return dataset


def build_screen2(snapshot_path: str) -> Dataset:
    """
    The sealed screening five, plus the five probes, in one run.

    One run series rather than two, for a reason about what is being controlled
    for. 2.6.4's comparison is between models, and every source of variation
    except the model has to be held still: same snapshot, same evaluator, same
    tool schema, same prompt, same day, same provider. Splitting the probes into
    their own run would mean a second set of conditions, and a difference between
    a model's screening score and its probe score would then be a difference
    between two runs rather than between two kinds of question.

    The five sealed tests keep their test_ids unchanged, so a 2.6.4 screening
    result is comparable with 2.6.2's and 2.6.3's for the same tests.
    """
    dataset = build_dataset(snapshot_path)
    sealed = [t for t in dataset.tests if t.test_id in SCREENING_TESTS]
    dataset.tests = sealed + build_probe_phase(snapshot_path).tests
    dataset.dataset_id = "steva-003b-screening-plus-probes"
    dataset.version = "2"
    return dataset


def run_phase(
    phase: str,
    model: Dict[str, Any],
    api_key: str,
    snapshot_path: str,
    env: Dict[str, Any],
    request_budget: Optional[int] = None,
    run_label: str = "",
) -> Dict[str, Any]:
    """
    One phase, one model, one run directory.

    The credential is passed to the client explicitly rather than left to the
    environment inside the harness, so that it exists as a value in this frame
    and is not reachable from anything that gets serialised.
    """
    from harness.budget import RequestBudget
    from harness.providers import OpenAICompatibleClient, TransportError

    dataset = build_dataset(snapshot_path)
    if phase == "smoke":
        dataset, _ = build_smoke_dataset(snapshot_path)
    elif phase == "screen":
        dataset.tests = [t for t in dataset.tests if t.test_id in SCREENING_TESTS]
    elif phase == "screen2":
        dataset = build_screen2(snapshot_path)
    elif phase == "probes":
        dataset = build_probe_phase(snapshot_path)
    elif phase != "full":
        raise SystemExit(f"unknown phase {phase!r}")

    run_dir = os.path.join(
        HERE, "runs", SCREENING_DIRNAME, model["dir"], phase, run_label
    ) if run_label else os.path.join(
        HERE, "runs", SCREENING_DIRNAME, model["dir"], phase
    )
    target = make_target(model, api_key)
    client = OpenAICompatibleClient(target.config, api_key=api_key)
    budget = RequestBudget(request_budget, label=f"{model['name']}/{phase}")
    client.budget = budget
    target.client = client

    started = time.time()
    ledger: List[Dict[str, Any]] = []
    attempts = 0
    run = None
    error: Optional[str] = None
    while attempts <= TRANSPORT_RETRIES:
        attempts += 1
        try:
            run = ScreeningRunner(
                dataset, snapshot_path, HERE, run_dir=run_dir
            ).run(target)
            error = None
            break
        except TransportError as failure:
            error = str(failure)
            ledger.append(
                {
                    "phase": phase,
                    "attempt": attempts,
                    "outcome": f"transport_error:{failure.kind}",
                    "detail": error,
                }
            )
            print(f"  {failure.kind} (attempt {attempts}): {error}", flush=True)
            if not budget.should_retry(failure.kind):
                break
            if attempts <= TRANSPORT_RETRIES:
                time.sleep(budget.retry_after(failure.kind))
    elapsed = time.time() - started

    metadata = {
        "phase": phase,
        "run_label": run_label or None,
        "provider": PROVIDER,
        "base_url": BASE_URL,
        "requested_slug": model["requested_slug"],
        "model_id": model["model_id"],
        "seed": model.get("seed") if model.get("seed") is not None
        else "unsupported",
        "environment": env,
        "attempts": attempts,
        "elapsed_seconds": round(elapsed, 1),
        "transport_error": error,
        "rate_limit_headers": getattr(client, "last_response_headers", {}),
        "transport_ledger": ledger,
    }

    if run is None:
        os.makedirs(run_dir, exist_ok=True)
        with open(os.path.join(run_dir, "run_metadata.json"), "w",
                  encoding="utf-8") as handle:
            json.dump(metadata, handle, indent=2, sort_keys=True, default=str)
        budget.write(
            os.path.join(run_dir, "budget.json"),
            getattr(client, "last_response_headers", {}),
        )
        return {"phase": phase, "model": model, "run": None, "metadata": metadata}

    report = _build_report(run)
    report_module.write_report(HERE, report, run.run_dir)
    _write(os.path.join(run.run_dir, "run_metadata.json"), metadata)
    _write(os.path.join(run.run_dir, "usage_ledger.json"), _usage_ledger(run))
    written = budget.write(
        os.path.join(run.run_dir, "budget.json"),
        getattr(client, "last_response_headers", {}),
    )

    return {
        "phase": phase,
        "model": model,
        "run": run,
        "report": report,
        "metadata": metadata,
        "budget": written,
    }


def _build_report(run) -> Dict[str, Any]:
    report = report_module.build_report(run)
    rows = []
    for result in run.results:
        record = result.target_run or {}
        operations = [c["operation"] for c in result.trace]
        exchanges = record.get("exchanges", [])
        usages = [
            (e.get("response") or {}).get("usage")
            for e in exchanges
            if isinstance(e.get("response"), dict)
        ]
        usages = [u for u in usages if u]
        rows.append(
            {
                "test_id": result.test_id,
                "verdict": verdict_of(
                    result.audit,
                    record.get("stop_reason")
                    in ("transport_error", "budget_exhausted"),
                ),
                "stop_reason": record.get("stop_reason"),
                "interrupted_by_transport": record.get("stop_reason")
                in ("transport_error", "budget_exhausted"),
                "failed_checks": [c.name for c in result.audit.failed_checks],
                "unverifiable": [c.name for c in result.audit.unverifiable],
                "tool_calls": len(result.trace),
                "failed_tool_calls": len([c for c in result.trace if c.get("error")]),
                "operations": operations,
                "off_surface_calls": [
                    c["operation"] for c in result.trace
                    if c["operation"] not in OPERATIONS
                ],
                "stop_reason": record.get("stop_reason"),
                "first_reply_parsed": record.get("first_reply_parsed"),
                "format_repair_used": record.get("format_repair_used"),
                "answer_parsed": result.answer.parse_error is None,
                "parse_error": result.answer.parse_error,
                "elapsed_seconds": record.get("elapsed_seconds"),
                "exchanges": len(exchanges),
                "usage": usages[-1] if usages else None,
                "evidence_refs": list(result.answer.evidence_refs),
                "derived_refs": list(result.answer.derived_refs),
                "uncertainties": list(result.answer.uncertainties),
                "retrieved_observations": list(result.retrieved_observations),
                "answer": result.answer.answer,
            }
        )
    report["screening_rows"] = rows
    return report


def verdict_of(audit: Audit, interrupted: bool = False) -> str:
    """
    PASS, FAIL, E (the model was never reached), or AMBIGUOUS.

    A test that stopped on a transport error is neither a pass nor a model
    failure. The archive is the grader for what the model did; an upstream
    endpoint returning 502 is not something the model did, and scoring it as a
    model failure is the same confusion as grading a network drop as bad
    reasoning. Those tests are reported as E and counted apart, because a run
    where a third of the tests were cut short must not be read as a run where a
    third of the capabilities were weak.

    A test with no decidable failure has decided nothing, and an evaluator's
    blindness is not a model's failure. But a test that *did* fail a decided
    check has failed, whatever else could not be decided alongside it: an
    undecidable check next to a decided one does not make the failure less of
    a failure.
    """
    if interrupted:
        return "E"
    if audit.passed:
        return "PASS"
    decided = [c for c in audit.failed_checks if c.passed is False]
    if not decided:
        return "AMBIGUOUS"
    blamed_on_the_evaluation = [
        c for c in decided
        if c.classification in (CLASS_EVALUATOR, CLASS_DATASET)
    ]
    if blamed_on_the_evaluation and len(blamed_on_the_evaluation) == len(decided):
        return "AMBIGUOUS"
    return "FAIL"


def _usage_ledger(run) -> List[Dict[str, Any]]:
    """
    Every request the model was sent, and what it cost, in order.

    Written whether or not the run succeeded, because an evaluation that cannot
    account for its own requests cannot claim it stayed inside an allowance.
    """
    entries: List[Dict[str, Any]] = []
    for result in run.results:
        record = result.target_run or {}
        for exchange in record.get("exchanges", []):
            response = exchange.get("response")
            entries.append(
                {
                    "test_id": result.test_id,
                    "index": exchange.get("index"),
                    "elapsed_seconds": exchange.get("elapsed_seconds"),
                    "error": exchange.get("error"),
                    "provider_generation_id": (
                        response.get("id") if isinstance(response, dict) else None
                    ),
                    "usage": (
                        response.get("usage") if isinstance(response, dict) else None
                    ),
                }
            )
    return entries


def _write(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, default=str)


def reaudit_phase(model: Dict[str, Any], phase: str, snapshot_path: str) -> Dict[str, Any]:
    """
    Re-grade a stored run with the current evaluator, spending no requests.

    The recorded answers do not change when the evaluator does — the model
    answered once, under conditions that are recorded — so re-auditing them is
    the cheapest possible test of a change to the grader: no network, and the
    new evaluator held against a real cloud model rather than against a target
    written to please it.

    Written beside the run rather than over it. The first grading is part of the
    record of what happened; the correction is a statement about the grader.
    """
    from harness.runner import _query_connection
    from harness.tools import Call

    run_dir = os.path.join(HERE, "runs", SCREENING_DIRNAME, model["dir"], phase)
    audit_dir = os.path.join(run_dir, "audit")
    if not os.path.isdir(audit_dir):
        return {"phase": "reaudit", "model": model, "status": "NOT_FOUND"}

    dataset = build_dataset(snapshot_path)
    query = EvidenceQuery.open(snapshot_path)
    connection = _query_connection(snapshot_path)
    auditor = Auditor(connection, query)
    out_dir = os.path.join(run_dir, "reaudit")
    os.makedirs(out_dir, exist_ok=True)

    rows = []
    for test in dataset.tests:
        stored_path = os.path.join(audit_dir, f"{test.test_id}.json")
        if not os.path.exists(stored_path):
            continue
        stored = json.load(open(stored_path, encoding="utf-8"))
        stop_reason = (stored.get("target_run") or {}).get("stop_reason")
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
                stored_returned_count=c.get("returned_count"),
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
        _write(os.path.join(out_dir, f"{test.test_id}.json"), {
            "test_id": test.test_id,
            "stop_reason": stop_reason,
            "interrupted_by_transport": stop_reason == "transport_error",
            "recorded_verdict": stored["audit"]["passed"],
            "reaudited_verdict": audit.passed,
            "changed": stored["audit"]["passed"] != audit.passed,
            "audit": audit.contract_dict(),
            "answer": answer.contract_dict(),
        })
        rows.append({
            "test_id": test.test_id,
            "recorded": stored["audit"]["passed"],
            "reaudited": audit.passed,
            "changed": stored["audit"]["passed"] != audit.passed,
            "stop_reason": stop_reason,
            "interrupted_by_transport": stop_reason == "transport_error",
            "verdict": verdict_of(audit, stop_reason == "transport_error"),
            "failed_checks": [
                {"name": c.name, "capability": c.capability,
                 "classification": c.classification, "detail": c.detail}
                for c in audit.failed_checks
            ],
            "unverifiable": [c.name for c in audit.unverifiable],
        })

    _write(os.path.join(out_dir, "reaudit.json"), {
        "model_id": model["model_id"],
        "phase": phase,
        "dataset_id": dataset.dataset_id,
        "evaluator_sha256": _file_hash(
            os.path.join(HERE, "harness", "auditor.py")
        ),
        "rows": rows,
    })
    query.close()
    connection.close()
    return {
        "phase": "reaudit",
        "model": model,
        "status": "RAN",
        "rows": rows,
        "flips": [r for r in rows if r["changed"]],
        "run_dir": out_dir,
    }


def _identifier_kinds(snapshot_path: str) -> Dict[str, str]:
    """
    Every identifier the archive holds, and which kind each one is.

    Built so a cited identifier can be classified against the archive rather
    than inferred from an auditor's check name.

    That distinction is the whole argument, and it took three attempts to get
    right in one round. The auditor emits one check called "every cited
    observation exists" for *any* citation that is not an observation id, and
    three different faults all land on it: an invented `obs_ff00…`, a real
    `sfid_…` filed in the wrong column, and a line of tool output copied into
    the array. Reading that check as fabrication rejects a model for any of
    the three, and only one of them is invention.

    `kinds` says what the archive holds. The shape test below says what the
    model was trying to write. Between them a citation is one of:

        fabricated  identifier-shaped, and the archive does not hold it
        misfiled    the archive holds it, as a different kind of identifier
        not_an_id   not identifier-shaped at all -- a transcript line

    The third is a real fault and a real one for a consumer to worry about, but
    it is a contract violation rather than a false statement about the archive,
    and it must not be counted as invention.
    """
    connection = _query_connection(snapshot_path)
    kinds: Dict[str, str] = {}
    for row in connection.execute("SELECT observation_id FROM observations"):
        kinds[row[0]] = "observation"
    for row in connection.execute(
        "SELECT DISTINCT source_fact_id FROM observations"
        " WHERE source_fact_id IS NOT NULL"
    ):
        kinds.setdefault(row[0], "source_fact")
    for row in connection.execute("SELECT document_id FROM source_documents"):
        kinds.setdefault(row[0], "document")
    for row in connection.execute("SELECT lineage_id FROM observation_lineage"):
        kinds.setdefault(row[0], "lineage")
    for row in connection.execute("SELECT ref FROM derived_values"):
        kinds.setdefault(row[0], "derived")
    connection.close()
    return kinds


# The prefixes and shapes the archive issues, and nothing else.
#
# A token is "identifier-shaped" if it could plausibly be one of ours. The test
# is deliberately about shape rather than about lookup: `sfid_…` and `doc_…` are
# ours even when the particular one is not in the database, and a sentence with
# spaces and an arrow never is, however much of it came from a tool result.
IDENTIFIER_SHAPES = re.compile(
    r"^(obs|obsarch|obs_|obsarch_|sfid|doc|line|der|concept|asset|ctx|val)_"
    r"[A-Za-z0-9_.\-]*$"
    r"|^obsarch_[0-9a-f]{8,}$"
    r"|^der:[A-Za-z0-9_.\-:]+$"
    r"|^obs:[A-Za-z0-9_.\-:]+$"
)


def classify_citation(ref: str, kinds: Dict[str, str]) -> str:
    """
    One citation, against the archive: fabricated, misfiled, or not an id.
    """
    if ref in kinds:
        return "observation" if kinds[ref] == "observation" else "misfiled"
    if IDENTIFIER_SHAPES.match(ref):
        return "fabricated"
    return "not_an_identifier"


def variance_phase(
    model: Dict[str, Any],
    phase: str,
    snapshot_path: str,
) -> Dict[str, Any]:
    """
    What held up across repeated runs, and what the model is actually for.

    A pass count is the wrong summary of a run series. 9/15 says less than "it
    paged correctly in three runs out of three and fabricated an identifier in
    none", and the second is the thing a consumer of an evidence database is
    actually buying. So the rows are grouped by what the capability is *for*, a
    run series is read as a distribution rather than a score, and a test that
    moved between runs is called unstable instead of being averaged into it.

    Read from the recorded runs, with no requests sent: three runs of the same
    configuration is the only kind of evidence that can say anything about
    stability, and gathering more of it here would change nothing.
    """
    base = os.path.join(HERE, "runs", SCREENING_DIRNAME, model["dir"], phase)
    candidates = sorted(
        d for d in glob.glob(os.path.join(base, "run*"))
        if os.path.isdir(os.path.join(d, "audit"))
    )
    # A directory where the model never answered is not a run of the model.
    #
    # The 2.6.3 attempt-1 directory is the case: three consecutive upstream
    # overloads, the budget stopped the phase, and fifteen tests were recorded
    # as not run. Averaging that in as a fourth run would turn every stable
    # result into "unstable" and would be a pure artefact of a provider having a
    # bad minute. Excluded, and *listed* in the output — an exclusion that
    # leaves no trace is indistinguishable from one that never happened.
    run_dirs: List[str] = []
    excluded: List[Dict[str, Any]] = []
    for candidate in candidates:
        answered = 0
        for path in glob.glob(os.path.join(candidate, "audit", "*.json")):
            stored = json.load(open(path, encoding="utf-8"))
            if (stored.get("target_run") or {}).get("stop_reason") not in (
                "transport_error", "budget_exhausted"
            ):
                answered += 1
        if answered:
            run_dirs.append(candidate)
        else:
            budget_path = os.path.join(candidate, "budget.json")
            budget = (
                json.load(open(budget_path, encoding="utf-8"))
                if os.path.exists(budget_path) else {}
            )
            excluded.append({
                "run": os.path.basename(candidate),
                "reason": "the model answered no test in this attempt",
                "requests_sent": budget.get("requests_sent"),
                "refusals_by_kind": budget.get("refusals_by_kind", {}),
                "stopped_because": budget.get("stopped_because"),
            })
    if len(run_dirs) < 2:
        return {
            "phase": "variance",
            "model": model,
            "status": "NOT_ENOUGH_RUNS",
            "detail": (
                f"{len(run_dirs)} of {len(candidates)} attempts produced at "
                f"least one answer; a series needs two"
            ),
            "excluded_attempts": excluded,
        }

    runs: List[Dict[str, Any]] = []
    kinds = _identifier_kinds(snapshot_path)
    for run_dir in run_dirs:
        rows: Dict[str, Dict[str, Any]] = {}
        for path in sorted(glob.glob(os.path.join(run_dir, "audit", "*.json"))):
            stored = json.load(open(path, encoding="utf-8"))
            stop = (stored.get("target_run") or {}).get("stop_reason")
            failed = [
                c["name"] for c in stored["audit"]["checks"]
                if c["passed"] is False
            ]
            cited = list(stored["answer"]["evidence_refs"])
            verdict_of_citation = [
                (ref, classify_citation(ref, kinds)) for ref in cited
            ]
            rows[stored["test_id"]] = {
                "verdict": verdict_of_unread(
                    stored["audit"]["passed"],
                    stop in ("transport_error", "budget_exhausted"),
                ),
                "stop_reason": stop,
                "failed_checks": failed,
                # The two citation checks, by name. Kept, because they are the
                # grader's own record -- but not used to decide fabrication,
                # which is decided against the archive above.
                "provenance_check_failures": [
                    name for name in failed
                    if name in (
                        "every cited observation exists",
                        "cited observations were actually retrieved",
                    )
                ],
                "identifiers_cited": len(cited),
                "fabricated_identifiers": [
                    ref for ref, kind in verdict_of_citation
                    if kind == "fabricated"
                ],
                "misfiled_identifiers": [
                    {"identifier": ref, "kind": kinds[ref]}
                    for ref, kind in verdict_of_citation if kind == "misfiled"
                ],
                "non_identifier_citations": [
                    ref for ref, kind in verdict_of_citation
                    if kind == "not_an_identifier"
                ],
                "tool_calls": len(stored.get("trace", [])),
                "failed_tool_calls": len([
                    call for call in stored.get("trace", []) if call.get("error")
                ]),
                "off_surface_calls": [
                    call["operation"] for call in stored.get("trace", [])
                    if call.get("operation") not in OPERATIONS
                ],
                "evidence_refs": len(cited),
            }
        budget = {}
        budget_path = os.path.join(run_dir, "budget.json")
        if os.path.exists(budget_path):
            budget = json.load(open(budget_path, encoding="utf-8"))
        runs.append({
            "run": os.path.basename(run_dir),
            "run_dir": os.path.relpath(run_dir, HERE).replace("\\", "/"),
            "requests": budget.get("requests_sent"),
            "refusals_by_kind": budget.get("refusals_by_kind", {}),
            "stopped_because": budget.get("stopped_because"),
            "tests": rows,
        })

    tests: List[Dict[str, Any]] = []
    for test_id in sorted({t for run in runs for t in run["tests"]}):
        observed = [run["tests"].get(test_id) for run in runs]
        verdicts = [row["verdict"] if row else "NOT_RUN" for row in observed]
        decided = [v for v in verdicts if v in ("PASS", "FAIL")]
        passed = verdicts.count("PASS")
        tests.append({
            "test_id": test_id,
            "consumer_capability": CONSUMER_CAPABILITY.get(
                test_id, PROBE_CAPABILITY.get(test_id, "unclassified")
            ),
            "verdicts": verdicts,
            "passes": passed,
            "fails": verdicts.count("FAIL"),
            "interrupted": verdicts.count("E"),
            "stability": (
                "stable_pass" if decided and passed == len(decided)
                and len(decided) == len(verdicts)
                else "stable_fail" if decided and not passed
                and len(decided) == len(verdicts)
                else "unstable"
            ),
            "failed_checks": sorted({
                name for row in observed if row
                for name in row["failed_checks"]
            }),
            "provenance_check_failures": sorted({
                name for row in observed if row
                for name in row["provenance_check_failures"]
            }),
            "off_surface_calls": sorted({
                call for row in observed if row
                for call in row["off_surface_calls"]
            }),
            "tool_calls": [row["tool_calls"] for row in observed if row],
            "evidence_refs": [row["evidence_refs"] for row in observed if row],
        })

    capability: Dict[str, Dict[str, Any]] = {}
    for test in tests:
        entry = capability.setdefault(
            test["consumer_capability"],
            {"tests": [], "passes": 0, "failures": 0, "interrupted": 0,
             "stable_pass": 0, "unstable": 0},
        )
        entry["tests"].append(test["test_id"])
        entry["passes"] += test["passes"]
        entry["failures"] += test["fails"]
        entry["interrupted"] += test["interrupted"]
        entry["stable_pass"] += 1 if test["stability"] == "stable_pass" else 0
        entry["unstable"] += 1 if test["stability"] == "unstable" else 0

    # The gate reads per-test-run rows, not the aggregated ones: it needs each
    # run's tool calls and citation checks separately, and a criterion that
    # counted test *kinds* would let a capability that passed in one run out of
    # three look like three passes.
    flat_rows: List[Dict[str, Any]] = []
    for run in runs:
        for test_id, row in run["tests"].items():
            flat_rows.append({
                "test_id": test_id,
                "verdict": row["verdict"],
                "tool_calls": row["tool_calls"],
                "failed_tool_calls": row["failed_tool_calls"],
                "off_surface_calls": row["off_surface_calls"],
                "provenance_check_failures": row["provenance_check_failures"],
                "evidence_refs": row["evidence_refs"],
                "identifiers_cited": row["identifiers_cited"],
                "fabricated_identifiers": row["fabricated_identifiers"],
                "misfiled_identifiers": row["misfiled_identifiers"],
                "non_identifier_citations": row["non_identifier_citations"],
            })

    out = {
        "phase": "variance",
        "model_id": model["model_id"],
        "phase_under_test": phase,
        "run_count": len(runs),
        "excluded_attempts": excluded,
        "runs": runs,
        "tests": tests,
        "by_consumer_capability": capability,
        "grounding": _grounding_summary(runs),
        # Both gates, decided from the same rows, so a verdict and the evidence
        # behind it are read from one artifact and cannot disagree.
        "consumer": consumer_module.assess(
            flat_rows, len(runs), excluded
        ),
        "probe_set": probe_dataset(
            _query_connection(snapshot_path), "AAPL",
            EvidenceQuery.open(snapshot_path).registry(),
        ),
    }
    path = os.path.join(
        base, f"variance-{model['dir']}-{phase}.json"
    )
    _write(path, out)
    out["status"] = "RAN"
    out["path"] = os.path.relpath(path, HERE).replace("\\", "/")
    return out


def verdict_of_unread(passed: bool, interrupted: bool) -> str:
    """
    The same verdict rule as `verdict_of`, for a run read back from disk.

    Kept as a second entry point rather than reconstructing an `Audit` from a
    JSON file, because a variance table is about what the runs recorded and the
    recorded verdict is the fact. `verdict_of` remains the rule for a live audit,
    and the two agreeing is itself worth a test.
    """
    if interrupted:
        return "E"
    return "PASS" if passed else "FAIL"


def _grounding_summary(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    The two numbers that decide whether this model may read ST-EVA evidence.

    Cited identifiers, and whether the ones it cited exist. A model can pass
    eight tests and be useless as a consumer if any of its citations are
    invented, because an invented citation is worse than none: it looks
    checkable to the person reading the answer. That is why this is measured
    over every run rather than summarised as a pass count.
    """
    cited = 0
    per_run = []
    for run in runs:
        total = sum(row["evidence_refs"] for row in run["tests"].values())
        cited += total
        per_run.append({"run": run["run"], "identifiers_cited": total})
    return {
        "identifiers_cited": cited,
        "per_run": per_run,
        "note": (
            "Existence and retrieval of every cited identifier are checked "
            "mechanically by the auditor on each run; a failure there would "
            "appear in that run's audit as a B-class check."
        ),
    }


def _print_consumer(assessment: Dict[str, Any]) -> None:
    """
    The two verdicts, each with the evidence that decided it.

    Printed with every criterion's observation next to its threshold, because a
    gate whose reasoning is not visible is an assertion. And the two classes are
    never combined into a single label, because the whole reason for splitting
    them is that a model can be one without the other.
    """
    evidence = assessment["evidence_consumer"]
    semantic = assessment["semantic_consumer"]
    print(
        f"\n   EVIDENCE CONSUMER: {evidence['verdict']}"
        f"   SEMANTIC CONSUMER: {semantic['verdict']}"
        f"   -> {assessment['classification']}"
    )
    for label, gate in (("evidence", evidence), ("semantic", semantic)):
        print(f"     {label}:")
        for criterion in gate["criteria"]:
            mark = {
                True: "ok  ", False: "FAIL", None: "n/a ",
            }[criterion["passed"]]
            print(
                f"       [{mark}] {criterion['id']}: {criterion['observed']} "
                f"(needs {criterion['threshold']})"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "phase",
        choices=("smoke", "screen", "screen2", "probes", "full", "reaudit",
                 "variance", "consumer"),
        help=(
            "which phase to run; reaudit re-grades a stored run and variance "
            "reads a run series -- neither sends a request"
        ),
    )
    parser.add_argument(
        "--reaudit-phase", default="screen",
        help="which stored phase reaudit should re-grade",
    )
    parser.add_argument(
        "--model", action="append", dest="models", help="restrict to a model name"
    )
    parser.add_argument("--summary", help="write a phase summary json here")
    parser.add_argument(
        "--request-budget",
        type=int,
        help=(
            "ceiling on requests for this phase, counted on the way out so a "
            "refused request spends it too; the phase stops and says so rather "
            "than continuing into a rate limit"
        ),
    )
    parser.add_argument(
        "--run-label",
        default="",
        help=(
            "subdirectory under the phase, for a repeated run. Run 1, run 2 and "
            "run 3 of one configuration belong side by side, not overwriting "
            "each other -- a variance figure needs all three to still exist."
        ),
    )
    args = parser.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if args.phase not in ("reaudit", "variance") and not api_key:
        print(
            "OPENROUTER_API_KEY is not set in this process; the screening "
            "needs it and will not run without it",
            file=sys.stderr,
        )
        return 2

    snapshot_path = default_snapshot_path()
    if not os.path.exists(snapshot_path):
        print("no snapshot; build it with: python -m harness --build --live",
              file=sys.stderr)
        return 2

    env = environment_block(snapshot_path)
    print(f"harness   {env['harness_commit']}")
    print(f"snapshot  {env['snapshot_sha256'][:16]}")
    print(f"dataset   {env['dataset_id']} {env['dataset_sha256'][:16]}")
    print(f"tools     {env['tool_schema_sha256'][:16]}")
    before = quota_snapshot(api_key) if api_key else {"skipped": "no request sent"}
    print(f"quota     {json.dumps(before)}\n", flush=True)

    summary = []
    for model in select_models(args.models):
        if args.phase == "variance":
            outcome = variance_phase(model, args.reaudit_phase, snapshot_path)
            print(f"== {model['name']}  {outcome['status']}", flush=True)
            if outcome["status"] != "RAN":
                print(f"   {outcome.get('detail')}\n", flush=True)
                summary.append(outcome)
                continue
            print(f"   {outcome['run_count']} runs of {model['model_id']}\n")
            for dropped in outcome.get("excluded_attempts", []):
                print(
                    f"   (excluded {dropped['run']}: {dropped['reason']}"
                    f" -- {dropped['stopped_because']})\n"
                )
            for test in outcome["tests"]:
                marks = " ".join(
                    f"{v:<5}" for v in test["verdicts"]
                )
                print(
                    f"   {test['test_id']:<26} {marks} {test['stability']:<13}"
                    f" {test['consumer_capability']}"
                )
            print("\n   by consumer capability:")
            for name, entry in sorted(outcome["by_consumer_capability"].items()):
                print(
                    f"   {name:<22} {entry['passes']:>2} pass "
                    f"{entry['failures']:>2} fail  {entry['interrupted']:>2} "
                    f"interrupted  ({entry['stable_pass']} stable, "
                    f"{entry['unstable']} unstable)"
                )
            print(
                f"\n   identifiers cited across runs: "
                f"{outcome['grounding']['identifiers_cited']}"
            )
            _print_consumer(outcome["consumer"])
            print(f"\n   written to {outcome['path']}\n", flush=True)
            summary.append(outcome)
            continue
        if args.phase == "reaudit":
            outcome = reaudit_phase(model, args.reaudit_phase, snapshot_path)
            print(f"== {model['name']}  {outcome['status']}", flush=True)
            for row in outcome.get("rows", []):
                mark = "FLIPPED" if row["changed"] else ""
                print(
                    f"   {row['test_id']:<28} {str(row['recorded']):<6} -> "
                    f"{str(row['reaudited']):<6} {row['verdict']:<10} {mark}"
                )
            summary.append(outcome)
            print("", flush=True)
            continue
        print(f"== {model['name']}  {model['model_id']}", flush=True)
        if not model["model_id"]:
            summary.append(
                {
                    "phase": args.phase,
                    "model": model,
                    "status": "UNAVAILABLE",
                    "detail": (
                        f"{model['requested_slug']} is not in the OpenRouter "
                        "catalogue; no other model was substituted"
                    ),
                }
            )
            print("   UNAVAILABLE — not in the catalogue, skipped\n", flush=True)
            continue
        outcome = run_phase(
            args.phase,
            model,
            api_key,
            snapshot_path,
            env,
            request_budget=args.request_budget,
            run_label=args.run_label,
        )
        if outcome["run"] is None:
            summary.append(
                {
                    "phase": args.phase,
                    "model": model,
                    "status": "TRANSPORT_ERROR",
                    "detail": outcome["metadata"]["transport_error"],
                }
            )
            print("   no run completed\n", flush=True)
            continue
        report = outcome["report"]
        totals = report["totals"]
        print(
            f"   {totals['passed']}/{totals['tests']} passed  "
            f"{outcome['metadata']['elapsed_seconds']}s",
            flush=True,
        )
        for row in report.get("screening_rows", []):
            print(
                f"   {row['test_id']:<28} {row['verdict']:<10} "
                f"calls={row['tool_calls']} stop={row['stop_reason']}"
            )
        spent = outcome.get("budget") or {}
        print(
            f"   budget: {spent.get('requests_sent')} requests, "
            f"{spent.get('remaining_budget')} left"
            + (
                f", refusals {json.dumps(spent.get('refusals_by_kind'))}"
                if spent.get("refusals_by_kind") else ""
            )
            + (
                f"  STOPPED: {spent['stopped_because']}"
                if spent.get("stopped_because") else ""
            ),
            flush=True,
        )
        summary.append(
            {
                "phase": args.phase,
                "run_label": args.run_label or None,
                "model": model,
                "status": "RAN",
                "totals": totals,
                "quota_after": quota_snapshot(api_key),
                "budget": {
                    key: value for key, value in spent.items()
                    if key != "attempts"
                },
                "rows": [
                    {k: v for k, v in row.items() if k != "answer"}
                    for row in report.get("screening_rows", [])
                ],
                "run_dir": report["run_dir"],
            }
        )
        print("", flush=True)

    after = quota_snapshot(api_key) if api_key else {"skipped": "no request sent"}
    print(f"quota after  {json.dumps(after)}")
    if args.summary:
        _write(args.summary, {"models": summary, "quota_before": before,
                              "quota_after": after})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
