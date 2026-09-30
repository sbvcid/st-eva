"""
Talking to a model, without a vendor dependency.

The harness must run the same dataset against any model. A bundled SDK for one
provider would make every other model a migration rather than a configuration
change, so this speaks the OpenAI-compatible chat-completions wire format over
stdlib `urllib` and nothing else. Ollama, llama.cpp's server, vLLM, LM Studio
and the hosted APIs all expose that shape.

What is recorded, and why each of it:

    model identity      a result nobody can attribute to a configuration is
                        not a result
    inference settings  a run at temperature 0.7 is not the same run
    the tool schemas    what the model was shown, verbatim, so a reader can
                        reproduce it without this code
    every request       the trace, for a run to be re-read later
    raw responses       so a mechanical failure can be distinguished from a
                        transport failure

The target never sees the dataset's expectations. The only thing that crosses
the boundary is the question, the tool definitions, and the answer contract.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# The states the model must be told about, because the whole test set is about
# whether it turns them into stronger claims. Told what they *mean*, never what
# any particular answer should say.
EVIDENCE_VOCABULARY = """
SOURCE_REPORTED  a value a source stated. The ordinary case.
DERIVED          computed by ST-EVA from named operands, not reported by
                 anyone. It is a calculation and it says so.
VALIDATED        cross-checked against another source. Agreement between two
                 comparable sources is not proof the figure is correct.
UNAVAILABLE      retrieval failed. Not zero, and not "no data exists".
CONFLICTING      two sources disagree. Neither is selected.
NOT_APPLICABLE   the measure is not meaningful for this business. Different
                 from UNAVAILABLE, and different from a zero.
STALE            what is held has gone out of date. Not historically false.
NOT_COMPARABLE   the series must break here; the measure changed.
PARTIAL          a source concept that expresses the metric only partially, as
                 a wider or narrower aggregate. Never the same as EXACT.
EXACT            a source concept that expresses the metric exactly.
""".strip()

SYSTEM_PROMPT = f"""\
You are answering questions using ST-EVA, an evidence database of filed \
financial data. You answer only from what its query tools return.

You cannot see the database directly. You have tools that read it. Use them.

The evidence carries states, and each one means something different:

{EVIDENCE_VOCABULARY}

Each observation carries a `status` with two separate parts:

- `status.evidence_state.state` is one of the states above.
- `status.validation_status` says whether cross-checking found anything, and
  is `UNVERIFIABLE` for a figure only one source has reported.

To filter on either, the parameter names it. `query_observations` takes
`validation_status` for the cross-check status; the evidence state is not
filterable and is read from each observation.

An unknown metric is refused by name, with the real ones attached. A metric
ST-EVA knows but has no rows for your filter returns an empty list, which is a
different answer and means the data is not there for that period.

Rules:

- Use a tool before making a factual claim. Do not state a number no tool
  returned.
- An empty result means your filter matched nothing. Widen the filter before
  concluding that evidence is absent.
- Report a figure's state when the state changes how it may be read. A PARTIAL
  concept is not an EXACT one. A disagreement is not settled. A derived value
  is not a reported one.
- If a series is truncated, say so. Do not present part of a series as the
  whole of it.
- If evidence is missing, say what is missing. Do not fill a gap with a
  plausible value, and do not report a negative state as a number.
- Report what the evidence establishes and stop there. Do not explain why
  something happened unless the evidence states why.
- Cite the observation ids the tools gave you, in `evidence_refs`.

Your reply must be a single JSON object and nothing else. No prose before it,
no prose after it, no markdown fence:

{{
  "answer": "the answer in prose, with every claim traceable to evidence",
  "evidence_refs": ["the observation ids the tools returned"],
  "derived_refs": [],
  "uncertainties": ["anything the evidence does not settle"]
}}

Both `answer` and `evidence_refs` are required. If you cannot cite evidence,
that belongs in `uncertainties`, not in `answer`.
""".strip()


@dataclass
class ProviderConfig:
    """Everything needed to reproduce a call, and nothing secret."""

    base_url: str
    model: str
    provider: str = "openai-compatible"
    version: str = "unknown"
    temperature: float = 0.0
    max_tokens: int = 1600
    timeout_seconds: int = 600
    seed: Optional[int] = 7
    # "ollama" nests temperature/seed/max_tokens under `options`, which is the
    # shape Ollama's OpenAI-compatible endpoint accepts. "openai" puts them at
    # the top level, which is what a hosted OpenAI-compatible gateway expects
    # and what OpenRouter requires: a gateway that does not see `temperature`
    # at the top level will not apply it, and a run that claims temperature 0
    # while the model sampled at its default is a mislabelled run.
    #
    # This is a transport detail and nothing more. It changes no prompt, no tool
    # schema, no dataset, no expectation and no check, so two providers still
    # differ in exactly one variable: which model answered.
    wire_style: str = "ollama"

    @property
    def endpoint(self) -> str:
        return self.base_url.rstrip("/") + "/chat/completions"

    def identity(self) -> Dict[str, Any]:
        """
        The identity recorded with every result.

        No key, no auth header, no secret of any kind: a run is attributable
        from its configuration, and a configuration that contains a credential
        is one that cannot be written down.
        """
        return {
            "provider": self.provider,
            "model": self.model,
            "version": self.version,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "seed": self.seed,
            "base_url": self.base_url,
            "wire_style": self.wire_style,
        }


@dataclass
class Exchange:
    """One request and its response, kept whole."""

    index: int
    request: Dict[str, Any]
    response: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    elapsed_seconds: float = 0.0

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "error": self.error,
            "request": _redact(self.request),
            "response": self.response,
        }


def _redact(payload: Any) -> Any:
    """
    Strip anything that should not be written to disk.

    The request carries the conversation, which is what a trace needs. It does
    not carry credentials, because credentials are read from the environment
    and never placed in a request body — this is a backstop, not the mechanism.
    """
    if isinstance(payload, dict):
        return {
            key: _redact(value)
            for key, value in payload.items()
            if key.lower() not in ("authorization", "api_key", "x-api-key")
        }
    if isinstance(payload, list):
        return [_redact(item) for item in payload]
    return payload


class OpenAICompatibleClient:
    """
    A chat-completions client over stdlib HTTP.

    Deliberately minimal. Anything clever here — retries with backoff, streaming
    reassembly, schema coercion — would be behaviour the harness could not
    explain when a run failed, and this stage is about finding out what the
    model does, not about making the transport forgiving.
    """

    def __init__(
        self,
        config: ProviderConfig,
        api_key: Optional[str] = None,
    ) -> None:
        self.config = config
        # Read from the environment and never stored on the config, so a config
        # can be logged, written to a run directory, and committed.
        self._api_key = api_key or os.environ.get("ST_EVA_LLM_API_KEY", "")
        # Response headers from the most recent call, so a hosted provider's
        # rate-limit and retry-after signals can be recorded with the run instead
        # of guessed at afterwards. Read-only bookkeeping; never sent anywhere.
        self.last_response_headers: Dict[str, str] = {}
        # A request allowance to account against, if the caller has one. Set from
        # the outside rather than configured here, because how much a run may
        # spend is the caller's decision and this class has no business guessing
        # it. Every request is recorded on the way out, so a refused request
        # spends the allowance too -- which is the case that actually bites.
        self.budget: Any = None
        # Which test the next request belongs to, for the ledger. A label, not a
        # control: nothing here branches on it.
        self.current_test: str = ""

    def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        if self.budget is not None:
            self.budget.record_sent(self.current_test)
        try:
            payload = self._complete(messages, tools)
        except TransportError as error:
            if self.budget is not None:
                self.budget.record_refusal(
                    error.kind, self.current_test, str(error)
                )
            raise
        if self.budget is not None:
            self.budget.record_answer(self.current_test, payload.get("usage"))
        return payload

    def _complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        request: Dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
        }
        if self.config.wire_style == "openai":
            request["temperature"] = self.config.temperature
            request["max_tokens"] = self.config.max_tokens
            if self.config.seed is not None:
                request["seed"] = self.config.seed
        else:
            request["options"] = {
                "temperature": self.config.temperature,
                "seed": self.config.seed,
                "num_predict": self.config.max_tokens,
            }
        if tools:
            request["tools"] = tools
        return self._post(request)

    def _post(self, request: Dict[str, Any]) -> Dict[str, Any]:
        body = json.dumps(request).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        http_request = urllib.request.Request(
            self.config.endpoint, data=body, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(
                http_request, timeout=self.config.timeout_seconds
            ) as response:
                self.last_response_headers = {
                    key.lower(): value for key, value in response.headers.items()
                }
                payload = json.loads(response.read().decode("utf-8"))
            # A gateway can answer 200 and still not have an answer: an upstream
            # provider that was unavailable comes back as a body carrying an
            # `error` and no choices. Passing that on as a completion would have
            # the harness read `choices[0]` out of a body that has none, and the
            # crash would be recorded as a model failure. It is a transport
            # failure, which is what the caller needs to be able to tell.
            if isinstance(payload, dict) and "choices" not in payload:
                body_text = json.dumps(payload)
                raise TransportError(
                    f"no completion in the response from {self.config.endpoint}: "
                    f"{body_text[:800]}",
                    classify_error_body(body_text),
                )
            return payload
        except urllib.error.HTTPError as error:
            self.last_response_headers = {
                key.lower(): value for key, value in error.headers.items()
            } if error.headers else {}
            detail = error.read().decode("utf-8", "replace")[:800]
            raise TransportError(
                f"HTTP {error.code} from {self.config.endpoint}: {detail}",
                classify_http_failure(error.code, detail),
            ) from error
        except urllib.error.URLError as error:
            raise TransportError(
                f"could not reach {self.config.endpoint}: {error.reason}"
            ) from error


class TransportError(Exception):
    """
    The model was never reached.

    Kept distinct from a model failure on purpose: a run that reports
    "transport error" tells the reader the experiment did not happen, and
    grading it as though the model had answered would put a fault in the model
    column that belongs to the network.

    `kind` says *which* network fact, because the three that matter call for
    different behaviour and none of them is a finding about the model:

        rate_limited        a quota or an upstream shared pool. Wait.
        provider_error      the provider behind the model failed. Retry later.
        model_unavailable   the model or its endpoint is gone. Stop on it.
        malformed_response  a 200 that is not a completion. Treat as suspect.
        network             no answer at all. Retry within reason.

    A caller that retries all five the same way will turn a saturated free pool
    into an hour of burned quota, and a deleted model into an infinite loop.
    """

    def __init__(self, message: str, kind: str = "network") -> None:
        super().__init__(message)
        self.kind = kind


def classify_http_failure(status: int, body: str) -> str:
    """
    Which kind of failure an HTTP status is, from the status and the body.

    Deliberately coarse. The point is not to diagnose the provider but to
    separate "this will never work" from "this will work later", because those
    two need opposite handling and a harness that cannot tell them apart either
    gives up on a model that was about to recover or hammers one that is gone.
    """
    if status == 429:
        return "rate_limited"
    if status in (404, 408):
        return "model_unavailable"
    if 500 <= status < 600:
        return "provider_error"
    return "network"


def classify_error_body(body: str) -> str:
    """
    The same judgement for a 200 that carried an error instead of a completion.

    A gateway that answers 200 with an `error` object is reporting an upstream
    failure through a success status, so the status code cannot be trusted on
    its own and the body's own error metadata is what says what happened.
    """
    lowered = body.lower()
    if "rate-limit" in lowered or "rate_limit" in lowered or "429" in lowered:
        return "rate_limited"
    if "no endpoints found" in lowered or "model not found" in lowered:
        return "model_unavailable"
    if "provider" in lowered:
        return "provider_error"
    return "malformed_response"
