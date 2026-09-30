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
import hashlib
import json
import os
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from evidence_query import EvidenceQuery
from harness import report as report_module
from harness.auditor import (
    CLASS_DATASET,
    CLASS_EVALUATOR,
    Audit,
    Auditor,
    Check,
)
from harness.dataset import Dataset, Test, build_dataset
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
        from harness.providers import TransportError

        attempts = 0
        while True:
            attempts += 1
            try:
                result = super()._run_one(test, target)
                result.target_run = dict(result.target_run or {})
                result.target_run["test_attempts"] = attempts
                return result
            except TransportError as failure:
                if attempts > self.TEST_TRANSPORT_RETRIES:
                    return self._unreached(test, target, str(failure), attempts)
                time.sleep(5)

    def _unreached(self, test, target, detail: str, attempts: int) -> Any:
        """
        Record a test the model never answered, without inventing a verdict.

        The audit carries a single undecidable check rather than a failure. An
        unreachable model has not been shown to be right or wrong, and grading
        it either way would put a transport fact into the model column — which
        is the specific confusion the classification scheme exists to prevent.
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
                name="the model was reached",
                passed=None,
                expected="a completion from the provider",
                actual="none",
                detail=detail,
                classification="E",
            )
        )
        record = {
            "stop_reason": "transport_error",
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


def run_phase(
    phase: str,
    model: Dict[str, Any],
    api_key: str,
    snapshot_path: str,
    env: Dict[str, Any],
) -> Dict[str, Any]:
    """
    One phase, one model, one run directory.

    The credential is passed to the client explicitly rather than left to the
    environment inside the harness, so that it exists as a value in this frame
    and is not reachable from anything that gets serialised.
    """
    from harness.providers import OpenAICompatibleClient, TransportError

    dataset = build_dataset(snapshot_path)
    if phase == "smoke":
        dataset, _ = build_smoke_dataset(snapshot_path)
    elif phase == "screen":
        dataset.tests = [t for t in dataset.tests if t.test_id in SCREENING_TESTS]
    elif phase != "full":
        raise SystemExit(f"unknown phase {phase!r}")

    run_dir = os.path.join(HERE, "runs", SCREENING_DIRNAME, model["dir"], phase)
    target = make_target(model, api_key)
    client = OpenAICompatibleClient(target.config, api_key=api_key)
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
                    "outcome": "transport_error",
                    "detail": error,
                }
            )
            print(f"  transport error (attempt {attempts}): {error}", flush=True)
            if attempts <= TRANSPORT_RETRIES:
                time.sleep(5 * attempts)
    elapsed = time.time() - started

    metadata = {
        "phase": phase,
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
        return {"phase": phase, "model": model, "run": None, "metadata": metadata}

    report = _build_report(run)
    report_module.write_report(HERE, report, run.run_dir)
    _write(os.path.join(run.run_dir, "run_metadata.json"), metadata)
    _write(os.path.join(run.run_dir, "usage_ledger.json"), _usage_ledger(run))

    return {
        "phase": phase,
        "model": model,
        "run": run,
        "report": report,
        "metadata": metadata,
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
                    result.audit, record.get("stop_reason") == "transport_error"
                ),
                "stop_reason": record.get("stop_reason"),
                "interrupted_by_transport": record.get("stop_reason")
                == "transport_error",
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "phase", choices=("smoke", "screen", "full", "reaudit"),
        help="which phase to run; reaudit re-grades a stored run, no requests",
    )
    parser.add_argument(
        "--reaudit-phase", default="screen",
        help="which stored phase reaudit should re-grade",
    )
    parser.add_argument(
        "--model", action="append", dest="models", help="restrict to a model name"
    )
    parser.add_argument("--summary", help="write a phase summary json here")
    args = parser.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if args.phase != "reaudit" and not api_key:
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
        outcome = run_phase(args.phase, model, api_key, snapshot_path, env)
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
        summary.append(
            {
                "phase": args.phase,
                "model": model,
                "status": "RAN",
                "totals": totals,
                "quota_after": quota_snapshot(api_key),
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
