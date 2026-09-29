"""
A real model as the target: the tool loop, and nothing else.

The loop is deliberately plain. Ask, read the tool calls, run them, append the
results, ask again, stop when the model answers. Everything else the model might
need — retrying, repairing a bad argument, re-asking after a refusal — is left
out, because a harness that quietly helps the model succeeds at measuring the
help rather than the model.

Two decisions worth stating, because both could reasonably have gone the other
way.

    Malformed arguments are an error, not a repair. If the model emits JSON the
    tool cannot take, the run records that and moves on. Repairing it silently
    would hide a capability finding behind a harness feature, and a model that
    cannot emit valid arguments has a finding worth having.

    The loop is bounded. A model that keeps calling tools forever is stopped and
    recorded as what it is, rather than being left to burn a machine.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .providers import (
    OpenAICompatibleClient,
    ProviderConfig,
    SYSTEM_PROMPT,
    TransportError,
)
from .schemas import tool_schemas
from .target import TargetAnswer
from .tools import ToolError, Toolbox

# A model that has not answered after this many exchanges is not going to. The
# bound is a property of the harness, not of the model, and is recorded.
MAX_EXCHANGES = 8


@dataclass
class TargetRun:
    """What one model did on one question."""

    exchanges: List[Dict[str, Any]] = field(default_factory=list)
    tool_definitions: List[Dict[str, Any]] = field(default_factory=list)
    stop_reason: str = ""
    elapsed_seconds: float = 0.0
    error: Optional[str] = None
    # Whether the model's first reply was usable as it stands, and whether a
    # single protocol-repair turn was spent to get past it. Both are reported
    # separately from the audit result, because a model that reasons correctly
    # and cannot follow an output contract is a different finding from a model
    # that reasons incorrectly, and averaging them hides both.
    first_reply_parsed: bool = True
    format_repair_used: bool = False

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "stop_reason": self.stop_reason,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "error": self.error,
            "first_reply_parsed": self.first_reply_parsed,
            "format_repair_used": self.format_repair_used,
            "exchanges": self.exchanges,
            "tool_definitions": self.tool_definitions,
        }


@dataclass
class ToolCallingTarget:
    """Drives any OpenAI-compatible model through the harness's tool surface."""

    config: ProviderConfig
    client: Optional[OpenAICompatibleClient] = None
    max_exchanges: int = MAX_EXCHANGES
    # Per-test record, read by the runner when it writes the trace. Kept here
    # because the runner has no other way to see what the transport did.
    last_run: Optional[TargetRun] = None

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = OpenAICompatibleClient(self.config)

    @property
    def identity(self) -> Dict[str, Any]:
        return self.config.identity()

    def answer(self, question: str, tools: Toolbox) -> TargetAnswer:
        started = time.time()
        run = TargetRun()
        self.last_run = run
        schemas = tool_schemas(tools)
        run.tool_definitions = schemas

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"{question}\n\n"
                    "Reply with the JSON object described in your "
                    "instructions, and nothing else."
                ),
            },
        ]

        try:
            for index in range(self.max_exchanges):
                completion = self._exchange(run, messages, schemas, index)
                message = completion["choices"][0]["message"]
                calls = message.get("tool_calls") or []
                if not calls:
                    answer = TargetAnswer.parse(message.get("content") or "")
                    if index == 0:
                        run.first_reply_parsed = answer.parse_error is None
                    if answer.parse_error is not None and not run.format_repair_used:
                        # One protocol-repair turn, and no more.
                        #
                        # This asks for the output *shape* and nothing else: the
                        # model has already done the retrieval and the reasoning
                        # by this point. Refusing to spend it would report a
                        # formatting failure as though the substance had failed
                        # too, and spending more than one would be the harness
                        # writing the answer. Both the first-reply failure and
                        # this turn are recorded, so the two can be reported
                        # separately.
                        run.format_repair_used = True
                        messages.append(message)
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "Your reply could not be read: "
                                    f"{answer.parse_error}\n\n"
                                    "Reply again as a single JSON object with the "
                                    "keys answer, evidence_refs, derived_refs "
                                    "and uncertainties. Keep the content you "
                                    "already wrote; change only the format. No "
                                    "prose, no markdown fence."
                                ),
                            }
                        )
                        continue
                    run.stop_reason = "answered"
                    run.elapsed_seconds = time.time() - started
                    return answer
                messages.append(message)
                for call in calls:
                    messages.append(
                        self._invoke(call, tools, messages, run)
                    )
            run.stop_reason = "exchange_limit"
            run.elapsed_seconds = time.time() - started
            return TargetAnswer(
                answer="",
                parse_error=(
                    f"the model used all {self.max_exchanges} exchanges without "
                    "producing an answer"
                ),
            )
        except TransportError as error:
            run.stop_reason = "transport_error"
            run.error = str(error)
            run.elapsed_seconds = time.time() - started
            return TargetAnswer(answer="", parse_error=f"TRANSPORT: {error}")

    def _exchange(
        self,
        run: TargetRun,
        messages: List[Dict[str, Any]],
        schemas: List[Dict[str, Any]],
        index: int,
    ) -> Dict[str, Any]:
        started = time.time()
        try:
            response = self.client.complete(messages, schemas)
        except TransportError as error:
            run.exchanges.append(
                {
                    "index": index,
                    "error": str(error),
                    "elapsed_seconds": round(time.time() - started, 2),
                }
            )
            raise
        run.exchanges.append(
            {
                "index": index,
                "elapsed_seconds": round(time.time() - started, 2),
                "message_count": len(messages),
                "response": response,
            }
        )
        return response

    def _invoke(
        self,
        call: Dict[str, Any],
        tools: Toolbox,
        messages: List[Dict[str, Any]],
        run: TargetRun,
    ) -> Dict[str, Any]:
        """
        Run one tool call the model asked for.

        The result goes back to the model verbatim, including refusals. A target
        that calls a tool with a forged cursor should be told so, because the
        alternative — dropping the call — hides the mistake from a model that
        could have recovered from it.
        """
        name = call["function"]["name"]
        raw = call["function"].get("arguments") or "{}"
        try:
            arguments = json.loads(raw)
            if not isinstance(arguments, dict):
                raise ValueError("arguments were not an object")
        except (TypeError, ValueError) as error:
            return {
                "role": "tool",
                "tool_call_id": call.get("id", name),
                "name": name,
                "content": json.dumps(
                    {"error": f"the arguments were not a JSON object: {error}"}
                ),
            }
        if not hasattr(tools, name):
            return {
                "role": "tool",
                "tool_call_id": call.get("id", name),
                "name": name,
                "content": json.dumps(
                    {"error": f"{name} is not a tool on this surface"}
                ),
            }
        try:
            result = getattr(tools, name)(**arguments)
        except ToolError as error:
            content = json.dumps({"error": str(error)})
        except TypeError as error:
            content = json.dumps({"error": f"bad arguments: {error}"})
        except Exception as error:  # noqa: BLE001
            # The model is told the call failed. Swallowing it would let a run
            # proceed as though the evidence had been returned.
            content = json.dumps(
                {"error": f"{type(error).__name__}: {error}"}
            )
        else:
            content = json.dumps(result, default=str)
        run.exchanges.append(
            {
                "index": len(run.exchanges),
                "tool_call": {"name": name, "arguments": arguments},
                "result_bytes": len(content),
            }
        )
        return {
            "role": "tool",
            "tool_call_id": call.get("id", name),
            "name": name,
            "content": content,
        }
