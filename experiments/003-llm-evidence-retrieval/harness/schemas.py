"""
Tool schemas, derived from the toolbox itself.

The model is told about the query surface by introspecting the same methods the
harness exposes to it. Hand-writing a parallel set of schemas would be a second
description of the interface that could drift from the first, and the drift
would show up as a model calling a tool the harness does not have — which would
be read as the model's failure rather than as the harness's.

The descriptions come from the methods' own docstrings, for the same reason:
there is now one place that says what `get_metric_history` returns and when it
is safe to call it.
"""

from __future__ import annotations

import inspect
import json
import typing
from typing import Any, Dict, List, get_args, get_origin

# Methods the model may call. Everything else on the toolbox is bookkeeping and
# is excluded by name, so a helper added for the harness is not automatically
# offered to the model.
EXPOSED = (
    "query_observations",
    "get_observation",
    "get_metric_history",
    "page",
    "get_lineage",
    "get_validation",
    "get_source_document",
    "coverage_report",
)

_PRIMITIVES = {str: "string", int: "integer", float: "number", bool: "boolean"}


def tool_schemas(toolbox: Any) -> List[Dict[str, Any]]:
    """JSON Schema tool definitions for every exposed operation."""
    schemas: List[Dict[str, Any]] = []
    for name in EXPOSED:
        method = getattr(toolbox, name)
        properties: Dict[str, Any] = {}
        required: List[str] = []
        signature = inspect.signature(method)
        for parameter, annotation in signature.parameters.items():
            if parameter == "self" or parameter.startswith("_"):
                continue
            if annotation is inspect.Parameter.empty:
                continue
            properties[parameter] = _schema_for(annotation)
            if parameter in _required_parameters(method, signature):
                required.append(parameter)
        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": (method.__doc__ or "").strip(),
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                },
            }
        )
    return schemas


def _required_parameters(
    method: Any,
    signature: inspect.Signature,
) -> List[str]:
    """
    Which parameters the model must supply.

    Read from the signature's default rather than from the type: `Optional[str]
    = None` means the model may omit it, and marking that required would make
    the model invent a value for a filter it did not need to set.
    """
    return [
        parameter
        for parameter, spec in signature.parameters.items()
        if parameter != "self"
        and spec.default is inspect.Parameter.empty
    ]


def _schema_for(annotation: Any) -> Dict[str, Any]:
    origin = get_origin(annotation)
    if origin is typing.Union or str(origin) == "types.UnionType":
        options = [a for a in get_args(annotation) if a is not type(None)]
        if len(options) == 1:
            return _schema_for(options[0])
        return {"type": "string", "description": "one of the listed forms"}
    if origin in (list, List):
        args = get_args(annotation)
        inner = _schema_for(args[0]) if args else {"type": "string"}
        return {"type": "array", "items": inner}
    if origin in (dict, Dict):
        return {"type": "object"}
    if annotation in _PRIMITIVES:
        return {"type": _PRIMITIVES[annotation]}
    if annotation is inspect.Parameter.empty:
        return {"type": "string"}
    return {"type": "string"}


def tool_manifest(toolbox: Any) -> List[Dict[str, Any]]:
    """
    The tool definitions as recorded in the trace.

    Kept verbatim so a run can be reproduced without the harness that produced
    it: the schemas are what the model was shown, and a reader has to be able to
    see exactly what those were.
    """
    return tool_schemas(toolbox)


def render_for_prompt(schemas: List[Dict[str, Any]]) -> str:
    """The same definitions, for a model that does not take a `tools` field."""
    return json.dumps(schemas, indent=2, sort_keys=True)
