"""
The only interface a target model is given.

This is the boundary the whole evaluation turns on. A target that could read
SQLite could answer correctly while ignoring every guarantee ST-EVA makes about
*how* a number may be described, and the evaluation would then be measuring
whether it can write SQL rather than whether it can use evidence. So the target
gets a closed set of typed operations and nothing else — no SQL, no filesystem,
no direct connection.

Every call is recorded. A trace that shows the target made two calls and cited a
third thing is itself a finding, and it is only visible if the calls are kept.

This module does not import sqlite3. It cannot execute arbitrary SQL because
there is no path here to do it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from evidence_query import EvidenceQuery, QueryError

# The operations a target may call. Named so the trace reads as what the model
# did, not as what the harness did.
OPERATIONS = (
    "query_observations",
    "get_observation",
    "get_metric_history",
    "page",
    "get_lineage",
    "get_validation",
    "get_source_document",
    "coverage_report",
)


class ToolError(Exception):
    """A call the target made that the surface refuses. Recorded, never hidden."""


@dataclass
class Call:
    """One recorded tool invocation."""

    sequence: int
    operation: str
    arguments: Dict[str, Any]
    result: Any = None
    error: Optional[str] = None
    result_shape: str = "unknown"
    # Set when a call is rebuilt from a stored trace, where the result itself
    # is not kept but the count it returned is.
    stored_returned_count: Optional[int] = None

    def contract_dict(self) -> Dict[str, Any]:
        """
        The trace: what was asked, in order, and what shape came back.

        `returned_count` is kept because a trace that records only a shape
        cannot reproduce the audit. The pagination check counts how many points
        the target actually read, which is a property of the result and not of
        the call -- and a trace that dropped it would re-audit differently from
        the run it came from, which is the one thing a trace must never do.
        """
        return {
            "sequence": self.sequence,
            "operation": self.operation,
            "arguments": self.arguments,
            "error": self.error,
            "result_shape": self.result_shape,
            "returned_count": self.returned_count(),
        }

    @property
    def succeeded(self) -> bool:
        """
        Whether the call ran and returned something.

        Derived from fields that survive into a stored trace. A check that
        reads `self.result` cannot be re-audited from the trace, because the
        trace deliberately does not keep every result -- and a check that
        cannot be reproduced from the artefact the run produced is a check whose
        verdict changes when nobody re-ran the model.
        """
        if self.error is not None:
            return False
        if self.result is not None:
            return True
        return self.result_shape != "unknown" and self.result_shape != "null"

    def returned_count(self) -> Optional[int]:
        """How many items came back, where that is well defined."""
        if self.stored_returned_count is not None:
            return self.stored_returned_count
        if self.result is None:
            return None
        if isinstance(self.result, list):
            return len(self.result)
        if isinstance(self.result, dict):
            for key in ("returned_count", "point_count"):
                if key in self.result:
                    return self.result[key]
        return None


@dataclass
class Toolbox:
    """
    A read-only window onto one archive, with every call recorded.

    Constructed by the harness and handed to the target. The target sees the
    method names below and the docstrings; it does not see the connection.
    """

    _query: EvidenceQuery = field(repr=False)
    calls: List[Call] = field(default_factory=list, repr=False)
    allowed: Optional[List[str]] = None

    # -- the permitted surface -------------------------------------------

    def query_observations(
        self,
        asset: Optional[str] = None,
        metric: Optional[str] = None,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
        as_of: Optional[str] = None,
        knowable_at: Optional[str] = None,
        provider: Optional[str] = None,
        source_type: Optional[str] = None,
        validation_status: Optional[str] = None,
        unit: Optional[str] = None,
        currency: Optional[str] = None,
        instant: Optional[bool] = None,
        basis_framework: Optional[str] = None,
        order: str = "PERIOD_ASCENDING",
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Observations matching a filter, oldest first.

        `metric` must be one ST-EVA knows. An unknown name is refused with the
        list of real ones rather than returning an empty result, because an
        empty result is what a genuinely absent figure looks like and the two
        were indistinguishable.

        `limit` truncates silently. Use `page` when the length of a series
        matters.
        """
        return self._call(
            "query_observations",
            {
                "asset": asset,
                "metric": metric,
                "period_start": period_start,
                "period_end": period_end,
                "as_of": as_of,
                "knowable_at": knowable_at,
                "provider": provider,
                "source_type": source_type,
                "validation_status": validation_status,
                "unit": unit,
                "currency": currency,
                "instant": instant,
                "basis_framework": basis_framework,
                "order": order,
                "limit": limit,
            },
            lambda: self._query.query_observations(
                asset=asset,
                metric=metric,
                period_start=period_start,
                period_end=period_end,
                as_of=as_of,
                knowable_at=knowable_at,
                provider=provider,
                source_type=source_type,
                validation_status=validation_status,
                unit=unit,
                currency=currency,
                instant=instant,
                basis_framework=basis_framework,
                order=order,
                limit=limit,
            ),
        )

    def get_observation(
        self,
        observation_id: str,
        include_validation: bool = True,
        include_lineage: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """One observation by its stable identity, with full metadata."""
        return self._call(
            "get_observation",
            {
                "observation_id": observation_id,
                "include_validation": include_validation,
                "include_lineage": include_lineage,
            },
            lambda: self._query.get_observation(
                observation_id,
                include_validation=include_validation,
                include_lineage=include_lineage,
            ),
        )

    def get_metric_history(
        self,
        asset: str,
        metric: str,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        A historical series with its state, comparability and completeness.

        Read `point_count`, `returned_count` and `truncated` before describing
        the series: a truncated series is not a whole one, and nothing in the
        payload says so except those three fields.
        """
        return self._call(
            "get_metric_history",
            {
                "asset": asset,
                "metric": metric,
                "period_start": period_start,
                "period_end": period_end,
                "limit": limit,
            },
            lambda: self._query.get_metric_history(
                asset,
                metric,
                period_start=period_start,
                period_end=period_end,
                limit=limit,
            ),
        )

    def page(
        self,
        asset: Optional[str] = None,
        metric: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: Optional[int] = None,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
        order: str = "PERIOD_ASCENDING",
    ) -> Dict[str, Any]:
        """
        One page of observations, with the total, what was returned, whether
        more remains, and the cursor to continue from.
        """
        return self._call(
            "page",
            {
                "asset": asset,
                "metric": metric,
                "cursor": cursor,
                "limit": limit,
                "period_start": period_start,
                "period_end": period_end,
                "order": order,
            },
            lambda: self._query.page(
                asset=asset,
                metric=metric,
                cursor=cursor,
                limit=limit,
                period_start=period_start,
                period_end=period_end,
                order=order,
            ),
        )

    def get_lineage(
        self,
        reference: str,
        depth: int = 4,
    ) -> Dict[str, Any]:
        """
        What a figure was computed from, or the chain of documents behind it.

        A `der:` reference returns the derived value with its operands and the
        stored expression. An observation reference returns its lineage chain.
        """
        return self._call(
            "get_lineage",
            {"reference": reference, "depth": depth},
            lambda: self._query.get_lineage(reference, depth=depth),
        )

    def get_validation(self, observation_id: str) -> List[Dict[str, Any]]:
        """
        Every cross-check recorded for one observation.

        `CONSISTENT` means two comparable sources agreed. It does not mean the
        figure is correct, and `independence` says how much the agreement is
        worth.
        """
        return self._call(
            "get_validation",
            {"observation_id": observation_id},
            lambda: self._query.get_validation(observation_id),
        )

    def get_source_document(self, reference: str) -> Optional[Dict[str, Any]]:
        """Source-document metadata by id, content hash or canonical URI."""
        return self._call(
            "get_source_document",
            {"reference": reference},
            lambda: self._query.get_source_document(reference),
        )

    def coverage_report(self, asset: str) -> Dict[str, Any]:
        """
        What is held for one company and in what state.

        Counts by state, never a completeness percentage.
        """
        return self._call(
            "coverage_report",
            {"asset": asset},
            lambda: self._query.coverage_report(asset),
        )

    # -- recording --------------------------------------------------------

    def _call(
        self,
        operation: str,
        arguments: Dict[str, Any],
        run: Callable[[], Any],
    ) -> Any:
        if self.allowed is not None and operation not in self.allowed:
            raise ToolError(
                f"{operation} is not part of this evaluation's tool set "
                f"{self.allowed}"
            )
        call = Call(
            sequence=len(self.calls) + 1,
            operation=operation,
            arguments=arguments,
        )
        try:
            call.result = run()
        except QueryError as error:
            # Recorded rather than raised onward. A target that calls
            # `page()` with a cursor it invented has made a finding-worthy
            # mistake, and swallowing the error would hide it.
            call.error = f"{type(error).__name__}: {error}"
            self.calls.append(call)
            raise ToolError(call.error) from error
        call.result_shape = _shape_of(call.result)
        self.calls.append(call)
        return call.result

    def contract_dict(self) -> List[Dict[str, Any]]:
        """The trace: what was asked, in order, and what shape came back."""
        return [call.contract_dict() for call in self.calls]

    def observations_cited(self) -> List[str]:
        """
        Every observation id that appeared in any result.

        Used to detect a target citing evidence it never retrieved, which is a
        failure the trace alone would not show.
        """
        seen: List[str] = []
        for call in self.calls:
            payload = json.dumps(call.result, default=str)
            for token in payload.split('"'):
                if token.startswith(("obsarch_", "obs_")) and token not in seen:
                    seen.append(token)
        return seen


def _shape_of(result: Any) -> str:
    """
    A compact description of a result, not the result itself.

    Traces stay readable and stay small. A trace holding every payload of a
    338-point series would be unusable for review and would mostly be copies of
    the snapshot.
    """
    if result is None:
        return "null"
    if isinstance(result, list):
        return f"list[{len(result)}]"
    if isinstance(result, dict):
        if "point_count" in result:
            return (
                f"series(point_count={result['point_count']},"
                f"returned={result.get('returned_count')},"
                f"truncated={result.get('truncated')})"
            )
        if "total_count" in result:
            return (
                f"page(total={result['total_count']},"
                f"returned={result.get('returned_count')},"
                f"truncated={result.get('truncated')})"
            )
        if "kind" in result:
            return f"lineage({result['kind']})"
        return f"object[{len(result)}]"
    return type(result).__name__
