from __future__ import annotations

"""
ST-EVA 2.5 - the read-only Query Surface.

    Database -> EvidenceQuery -> an Evidence package an LLM can ground on

The package answers eleven questions about any figure it returns: what it is,
what period, what as-of and availability mean, what unit and currency, what
accounting and security basis, who reported it, which document contains it,
what state it is in, whether it was cross-validated, what a derived figure was
computed from, and whether the evidence can be followed further.

Three properties this module holds deliberately.

    It never resolves anything. A conflict is returned as a conflict. A missing
    item is returned with the reason it is missing. An unvalidated figure says
    so. The surface reports evidence and its provenance; the judgement belongs
    to whoever reads it.

    It preserves the 2.4.3 semantics exactly. UNAVAILABLE is not zero.
    SOURCE_DID_NOT_REPORT is not NOT_APPLICABLE. NOT_APPLICABLE is not a
    retrieval failure. UNVALIDATED is not incorrect. CONSISTENT is not
    independently verified. STALE is not historically false. A validation
    record is never reduced to a boolean "trusted".

    It is read-only and it owns its SQL. No arbitrary SQL crosses the
    interface, every parameter is bound, and the connection is opened for
    reading.
"""

import base64
import binascii
import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from data_contract import ValidationStatus, parse_iso_date, utc_now
from core_registry import CoreRegistry
from evidence_model import (
    CONFLICTING,
    EVIDENCE_STATES,
    NOT_APPLICABLE,
    REASON_CODES,
    SOURCE_DID_NOT_REPORT,
    SOURCE_REPORTED,
    STALE,
    UNAVAILABLE,
    STATE_STATUS,
    canonical_json,
)

# The cross-check statuses an observation can carry. Closed because an unmatched
# one returns an empty list, and an empty list reads as "no such data" rather
# than "you named something that does not exist".
VALIDATION_STATUSES: Tuple[str, ...] = tuple(
    status.value for status in ValidationStatus
)

# Lineage kinds. A consumer must not have to infer whether a figure was
# reported or computed.
KIND_OBSERVED = "OBSERVED"
KIND_DERIVED = "DERIVED"
KIND_UNAVAILABLE = "UNAVAILABLE"
KIND_CONFLICTING = "CONFLICTING"

# Why several figures share one metric and one period.
#
# A closed vocabulary, and every member of it is decidable from the rows
# themselves. The point of a closed set is that a consumer can branch on it: a
# `MULTIPLE_SOURCE_CONCEPTS` case is not a disagreement at all, and code that
# treats every reason alike will pick a figure it was never offered a choice
# between.
AMBIGUITY_CROSS_PROVIDER = "CROSS_PROVIDER_DISCREPANCY"
AMBIGUITY_MULTIPLE_CONCEPTS = "MULTIPLE_SOURCE_CONCEPTS"
AMBIGUITY_DIMENSION = "DIMENSION_COLLISION"
AMBIGUITY_MULTIPLE_FILINGS = "MULTIPLE_FILINGS"
AMBIGUITY_MULTIPLE_OBSERVATIONS = "MULTIPLE_OBSERVATIONS"
AMBIGUITY_REASONS: Tuple[str, ...] = (
    AMBIGUITY_CROSS_PROVIDER,
    AMBIGUITY_MULTIPLE_CONCEPTS,
    AMBIGUITY_DIMENSION,
    AMBIGUITY_MULTIPLE_FILINGS,
    AMBIGUITY_MULTIPLE_OBSERVATIONS,
)
# The archive declining to choose. Unchanged by 2.6.3: whatever the cause, the
# resolution is the same, and a run of this experiment already showed that
# weakening it is how a model ends up asserting a winner.
AMBIGUITY_NO_WINNER = "NO_WINNER_SELECTED"

# Ordering is a closed vocabulary, not a free string, so it cannot become a way
# to smuggle an expression into the SQL layer.
ORDER_ASC = "PERIOD_ASCENDING"
ORDER_DESC = "PERIOD_DESCENDING"
ORDER_AVAILABLE = "AVAILABLE_AT_ASCENDING"
ORDERS = (ORDER_ASC, ORDER_DESC, ORDER_AVAILABLE)

_MAX_LIMIT = 5000
_DEFAULT_LIMIT = 200


class QueryError(Exception):
    """A query was malformed. Raised before anything reaches the database."""


class UnknownMetricError(QueryError):
    """
    The metric named is not one ST-EVA knows.

    Distinct from an empty result, and the distinction is the whole point. A
    query for a metric that exists but has no matching observations returns
    `[]`; a query for a metric that does not exist used to return the same
    `[]`, and a caller could not tell a typo from an absence. In the first real
    model run that produced seven false negatives in fifteen tests, each
    answered "no data exists" against an archive holding 1,922 revenue
    observations.

    The available names travel with the error, so the recovery is one turn
    rather than a guess.
    """

    def __init__(self, requested: str, available: Sequence[str]) -> None:
        self.requested = requested
        self.available = list(available)
        super().__init__(
            f"UNKNOWN_METRIC: no metric named {requested!r}. "
            f"Known metrics: {', '.join(self.available)}"
        )


def _require_known_metric(
    connection: sqlite3.Connection,
    metric: str,
) -> None:
    """
    Refuse a metric ST-EVA has never heard of.

    The vocabulary is everything ST-EVA can name, and that includes the state
    table: a metric recorded as NOT_APPLICABLE or STALE is exactly the case
    where holding no observations is the correct answer, so refusing the name
    would turn a true answer into an error. Three places contribute — the
    registry, the observations themselves, and the states.

    A metric that is in that vocabulary but matches no rows is a different
    situation entirely and is not an error: that is an empty answer to a real
    question.
    """
    known = {
        row["metric_id"]
        for row in connection.execute("SELECT metric_id FROM metric_registry")
    }
    observed = {
        row["metric"]
        for row in connection.execute(
            "SELECT DISTINCT metric FROM observations"
        )
    }
    stated = {
        row["metric"]
        for row in connection.execute("SELECT DISTINCT metric FROM evidence_state")
    }
    available = sorted(known | observed | stated)
    if available and metric not in available:
        raise UnknownMetricError(metric, available)


def _validate_validation_status(value: str) -> str:
    """
    Cross-check status, from a closed vocabulary.

    Refused rather than matched, because an unmatched status returns `[]` and an
    empty list reads as "no such data" — which is how passing `SOURCE_REPORTED`
    here produced a false negative in the first real model run. `SOURCE_REPORTED`
    is an evidence *state*, not a validation status, and saying so in the error
    is more useful than returning nothing.
    """
    if value in VALIDATION_STATUSES:
        return value
    if value in EVIDENCE_STATES:
        raise QueryError(
            f"{value!r} is an evidence state, not a validation status. "
            "filter with `validation_status` for the cross-check status, or "
            "read `status.evidence_state.state` on an observation. Validation "
            f"statuses are: {', '.join(sorted(VALIDATION_STATUSES))}"
        )
    raise QueryError(
        f"validation_status must be one of "
        f"{', '.join(sorted(VALIDATION_STATUSES))}, got {value!r}"
    )


def _validate_limit(limit: Optional[int]) -> int:
    if limit is None:
        return _DEFAULT_LIMIT
    if isinstance(limit, str) and limit.strip().isdigit():
        # A caller that sent "50" wants fifty. Refusing it teaches nothing and
        # costs a round trip; the first real model run spent four failed calls
        # on numeric strings.
        limit = int(limit.strip())
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise QueryError(
            f"limit must be an integer, got {type(limit).__name__}"
        )
    if limit < 1:
        raise QueryError("limit must be at least 1")
    if limit > _MAX_LIMIT:
        raise QueryError(f"limit must not exceed {_MAX_LIMIT}")
    return limit


def _validate_date(name: str, value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str) or parse_iso_date(value) is None:
        raise QueryError(f"{name} must be an ISO-8601 date, got {value!r}")
    return value


def _validate_period(start: Optional[str], end: Optional[str]) -> None:
    if start and end and parse_iso_date(start) > parse_iso_date(end):
        raise QueryError("period start must not be after period end")


def _validate_order(order: Optional[str]) -> str:
    if order is None:
        return ORDER_ASC
    if order not in ORDERS:
        raise QueryError(f"order must be one of {list(ORDERS)}, got {order!r}")
    return order


def _encode_cursor(offset: int) -> str:
    """An opaque page cursor. Its shape is not part of the contract."""
    return base64.urlsafe_b64encode(
        f"offset:{offset}".encode("utf-8")
    ).decode("ascii")


def _decode_cursor(cursor: str) -> int:
    """
    Read a cursor this surface issued.

    An empty or absent cursor is refused rather than treated as the first page.
    Silently accepting "" would make a caller that lost its cursor believe it
    had read the whole series while holding the first page of it — the exact
    silent truncation this exists to prevent, reached by a different route.
    """
    if cursor is None:
        raise QueryError(
            "cursor is required. Start from the first page with cursor=None on "
            "`query_observations`, or call `page()` without one."
        )
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        if not decoded.startswith("offset:"):
            raise ValueError("not a cursor")
        offset = int(decoded.split(":", 1)[1])
        if offset < 0:
            raise ValueError("negative offset")
        return offset
    except (ValueError, UnicodeDecodeError, binascii.Error) as error:
        raise QueryError(
            f"cursor is not a cursor returned by this surface: {cursor!r}"
        ) from error


def _loads(payload: Optional[str], fallback: Any = None) -> Any:
    if not payload:
        return fallback
    try:
        return json.loads(payload)
    except (TypeError, ValueError):
        return fallback


def _read_only(connection: sqlite3.Connection) -> sqlite3.Connection:
    """
    Ask SQLite to refuse writes on this connection.

    `query_only` is a guarantee rather than a convention, which is the point:
    the surface is handed a database it must not change, and the database is
    the thing that enforces it.
    """
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def classify_ambiguity(basis: Dict[str, Any]) -> str:
    """
    Which kind of ambiguity this is, decided from the gathered evidence alone.

    A pure function of `basis`, deliberately separated from the SQL that gathers
    it. Two reasons. A classification that can only be tested through a
    database is a classification nobody will test, and this one decides whether
    a consumer is offered a choice at all. And keeping it pure makes the rule
    inspectable as a rule: each branch below is a claim about the rows, in the
    order the claims are made, and the order is part of the contract.

    The order is not arbitrary:

    1. **Different providers subsume everything.** Two figures from two sources
       are not two readings of one source's aggregate, whatever else is true of
       them, and a cross-source pair may carry a recorded cross-check.
    2. **Different concepts come before filing identity.** If the rows measure
       different things, no amount of agreement about which filing or which
       dimension member made them a choice between comparable figures. This is
       the branch the old prose got wrong for 68 of 107 groups, calling two
       different measures "the same source concept".
    3. **One concept, one filing, two values** is the only shape that licenses
       the dimension-aggregation story: a single filing reporting one concept
       for one period twice can only be reporting an aggregate over members it
       did not return. `accessions` is the set of *known* accessions, so
       exactly one means every row names that same filing.
    4. **Several filings, one concept** is a restatement or a re-filing, and the
       archive cannot say which filing a question was about.
    5. **Nothing identifiable** falls back to saying only that the archive holds
       more than one figure. That is the honest answer when the evidence
       supports no better, and it is the only branch that is a fallback.

    `unmapped_observations` is not a branch. A row with no source concept is
    reported in the basis but does not make two named concepts into one case,
    because "one row says nothing" is not "both rows say the same thing".
    """
    if len(basis.get("providers", [])) > 1:
        return AMBIGUITY_CROSS_PROVIDER
    if len(basis.get("source_concepts", [])) > 1:
        return AMBIGUITY_MULTIPLE_CONCEPTS
    accessions = basis.get("accessions", [])
    if len(accessions) == 1:
        return AMBIGUITY_DIMENSION
    if len(accessions) > 1:
        return AMBIGUITY_MULTIPLE_FILINGS
    return AMBIGUITY_MULTIPLE_OBSERVATIONS


def same_measure_established(basis: Dict[str, Any]) -> bool:
    """
    Whether the evidence establishes that the competing figures measure the same
    thing.

    Stated as a field rather than left to be inferred from the reason, because
    the inference is the failure. Two figures that measure different things are
    not a disagreement, and a reader who treats them as one is choosing between
    a question they did not ask and an answer that may not fit it.

    An unmapped row makes this False. A row whose concept the archive does not
    hold cannot be shown to measure the same thing as one whose concept it does,
    and "cannot be shown" is the honest reading.
    """
    if basis.get("unmapped_observations"):
        return False
    return len(basis.get("source_concepts", [])) <= 1


def _ambiguity_explanation(reason: str, basis: Dict[str, Any]) -> str:
    """
    The prose for a classification, written from the class and the evidence.

    Generated rather than asserted, so it cannot drift from the code. Every
    branch names what the archive can see and stops there: an explanation that
    went past the evidence is exactly the defect 2.6.3 exists to remove.
    """
    concepts = ", ".join(basis.get("source_concepts", [])) or "no named concept"
    providers = ", ".join(basis.get("providers", [])) or "no named provider"
    filings = ", ".join(basis.get("accessions", [])) or "no identified filing"
    count = basis.get("observation_count", 0)
    if reason == AMBIGUITY_CROSS_PROVIDER:
        return (
            f"Different sources report different values for this metric and "
            f"period: {providers}. The figures come from different providers, so "
            f"they are not two readings of one source's aggregate. ST-EVA has "
            f"not selected one. Any recorded cross-check between them is carried "
            f"in `recorded_cross_check`."
        )
    if reason == AMBIGUITY_MULTIPLE_CONCEPTS:
        return (
            "Different source concepts report different values for this metric "
            f"and period: {concepts}. These are different measures, not two "
            "readings of one measure, so the evidence does not establish that "
            "either is the figure a question about this metric was asking for. "
            "ST-EVA has not selected one and does not claim either is a "
            "candidate."
        )
    if reason == AMBIGUITY_DIMENSION:
        return (
            f"One filing ({filings}) and one source concept ({concepts}) report "
            f"more than one value for this period. A single filing reporting one "
            f"concept for one period twice can only be an aggregate over "
            f"dimension members it does not return, and the member is not "
            f"identified in the evidence held. ST-EVA has not selected one."
        )
    if reason == AMBIGUITY_MULTIPLE_FILINGS:
        return (
            f"The same source concept ({concepts}) is reported with different "
            f"values by {len(basis.get('accessions', []))} filings: {filings}. "
            f"The figures may be a restatement, a re-filing or two different "
            f"periods of coverage, and the evidence held does not establish "
            f"which filing a question was about. ST-EVA has not selected one."
        )
    return (
        f"ST-EVA holds {count} observations for this metric and period reporting "
        f"different values, and the evidence held does not identify what "
        f"distinguishes them. ST-EVA has not selected one and is not offering a "
        f"choice between them on the basis of anything it can see."
    )


def _strip_ref_prefix(reference: str) -> str:
    """
    The bare id behind an optional `<kind>:` prefix.

    `obs:ev-price-001` and `ev-price-001` name the same thing, and a lookup
    that fails because the caller included the kind would make a derived
    figure's operands unreachable.
    """
    if ":" in reference:
        return reference.split(":", 1)[1]
    return reference


@dataclass(frozen=True)
class EvidenceQuery:
    """
    A read-only service over the archive.

    The read-only guarantee is the surface's own, not the caller's: however the
    connection arrived, the surface asks SQLite to refuse writes. A caller that
    hands in a writable connection and gets a mutating query surface out of it
    would be a caller with no reason to know the difference.
    """

    connection: sqlite3.Connection

    def __init__(self, connection: sqlite3.Connection) -> None:
        # A frozen dataclass forbids assignment even in __init__.
        object.__setattr__(self, "connection", connection)
        # The registry is a cache rather than part of the value.
        object.__setattr__(self, "_registry", None)
        # How many rows the last query matched before its limit. Kept on the
        # instance because the count is a property of the filter, not of the
        # rows returned, and a caller that cannot see it is being told a
        # truncated series is a whole one.
        object.__setattr__(self, "_last_result_total", 0)
        # Writing __init__ suppresses the generated one, and the generated one
        # is what calls __post_init__. Without this the read-only guarantee is
        # silently inactive and the tests still pass, because the append-only
        # triggers happen to refuse the same writes.
        self.__post_init__()

    def registry(self) -> "CoreRegistry":
        """
        The Core Registry over the same connection.

        Resolving a figure to the concept and the semantic metric it means is a
        registry answer, not a query answer. Guessing it from a taxonomy or a
        basis string is exactly what the registry exists to replace.
        """
        if self._registry is None:
            object.__setattr__(
                self, "_registry", CoreRegistry(self.connection)
            )
        return self._registry

    def __post_init__(self) -> None:
        try:
            object.__setattr__(
                self, "connection", _read_only(self.connection)
            )
        except sqlite3.Error:
            # A connection mid-transaction cannot be switched. The append-only
            # triggers remain, so the guarantee degrades to "refused by the
            # database" rather than disappearing.
            pass

    @classmethod
    def open(cls, path: str) -> "EvidenceQuery":
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        return cls(connection=connection)

    def close(self) -> None:
        self.connection.close()

    # -- states ----------------------------------------------------------

    def _state_map(self, asset: Optional[str]) -> Dict[str, Dict[str, Any]]:
        """
        Evidence state per metric, for the asset or for every asset.

        The state table is authoritative where a row exists. A metric with no
        row falls back to what the observations themselves say, because an
        absence of a state is not itself a state.
        """
        if asset:
            rows = self.connection.execute(
                "SELECT metric, state, reason_code, detail, as_of, updated_at"
                " FROM evidence_state WHERE asset_id = ?",
                (self._asset_id(asset),),
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT metric, state, reason_code, detail, as_of, updated_at"
                " FROM evidence_state"
            ).fetchall()
        return {row["metric"]: dict(row) for row in rows}

    def _asset_id(self, ticker: str) -> str:
        row = self.connection.execute(
            "SELECT asset_id FROM assets WHERE ticker = ? COLLATE NOCASE",
            (ticker,),
        ).fetchone()
        if row is None:
            raise QueryError(f"{ticker} is not a known asset in this archive")
        return row["asset_id"]

    def _state_for(
        self,
        metric: str,
        states: Dict[str, Dict[str, Any]],
        status: Optional[str],
        has_value: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        The state of one metric, resolved and always present.

        A metric the state table does not mention falls back to what the
        observations themselves say, because an absence of a state is not
        itself a state. `has_value` matters: an observation that exists with no
        value is an absent value, not an absent observation, and reporting
        UNAVAILABLE for a metric we do hold would be its own kind of wrong.
        """
        row = states.get(metric)
        if row is not None:
            state = row["state"]
            return {
                "state": state,
                "reason_kind": None,
                "reason_code": row["reason_code"]
                or REASON_CODES.get(state),
                "explanation": row["detail"],
                "as_of": row["as_of"],
                "resolved_from": "evidence_state",
            }
        if has_value is False:
            state = UNAVAILABLE
        elif status is not None and str(status) == str(STALE):
            state = STALE
        elif status is not None or has_value:
            state = SOURCE_REPORTED
        else:
            state = UNAVAILABLE
        return {
            "state": state,
            "reason_kind": None,
            "reason_code": REASON_CODES.get(state),
            "explanation": None,
            "as_of": None,
            "resolved_from": "observation_status",
        }

    # -- observations ----------------------------------------------------

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
        basis_framework: Optional[str] = None,
        currency: Optional[str] = None,
        unit: Optional[str] = None,
        instant: Optional[bool] = None,
        order: Optional[str] = None,
        limit: Optional[int] = None,
        include_validation: bool = True,
        include_lineage: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Observations matching explicit filters.

        Every filter is a bound parameter, and the sort is chosen from a closed
        vocabulary, so nothing a caller supplies can reach the SQL layer as
        syntax.

        `knowable_at` filters on the *source's* availability, never on a
        retrieval time. A value whose source published no availability cannot be
        asserted to have been knowable at any instant, and this is where the
        2.4.2 distinction is enforced on the read path.

        `validation_status` filters the cross-check status -- UNVERIFIABLE,
        CONFLICTING and the rest. It was named `status` until the first real
        model run, where that name cost more than it explained: every
        observation also carries an *evidence state* (SOURCE_REPORTED,
        UNAVAILABLE, STALE), the two sat adjacent in every payload, and a
        caller had no way to know which one `status` meant except by being told
        in a prompt. The model was told in a prompt, and still passed
        `SOURCE_REPORTED` here. A name that has to be disambiguated by prose
        is not self-describing, so the filter now names what it filters.

        An unknown metric raises `UnknownMetricError` rather than returning an
        empty list. A misspelling and a genuinely empty answer used to produce
        the same `[]`, and a reader could not tell a typo from an absence -- a
        distinction that is the difference between "try another name" and
        "report that the data is not there".
        """
        period_start = _validate_date("period_start", period_start)
        period_end = _validate_date("period_end", period_end)
        as_of = _validate_date("as_of", as_of)
        knowable_at = _validate_date("knowable_at", knowable_at)
        _validate_period(period_start, period_end)
        order = _validate_order(order)
        bounded = _validate_limit(limit)
        if validation_status is not None:
            validation_status = _validate_validation_status(validation_status)
        if metric is not None:
            _require_known_metric(self.connection, metric)

        where: List[str] = []
        params: List[Any] = []

        if asset:
            where.append("o.asset_id = ?")
            params.append(self._asset_id(asset))
        if metric:
            where.append("o.metric = ?")
            params.append(metric)
        if period_start:
            where.append("(o.period_end IS NULL OR o.period_end >= ?)")
            params.append(period_start)
        if period_end:
            where.append("(o.period_end IS NULL OR o.period_end <= ?)")
            params.append(period_end)
        if as_of:
            where.append("o.as_of = ?")
            params.append(as_of)
        if knowable_at:
            # The source's publication time, never `retrieved_at`.
            where.append("o.replay_eligible_from IS NOT NULL")
            where.append("o.replay_eligible_from <= ?")
            params.append(knowable_at)
        if provider:
            where.append("o.provider = ?")
            params.append(provider)
        if source_type:
            where.append("o.source_type = ?")
            params.append(source_type)
        if validation_status:
            where.append("o.status = ?")
            params.append(validation_status)
        if currency:
            where.append("o.currency = ?")
            params.append(currency)
        if unit:
            where.append("o.unit = ?")
            params.append(unit)
        if instant is True:
            where.append("o.period_start IS NULL")
        elif instant is False:
            where.append("o.period_start IS NOT NULL")
        if basis_framework:
            where.append("o.basis_json LIKE ?")
            params.append(f'%"reporting_framework": "{basis_framework}"%')

        clause = (" WHERE " + " AND ".join(where)) if where else ""
        sort = {
            ORDER_ASC: "o.period_end IS NULL, o.period_end ASC, o.metric ASC",
            ORDER_DESC: "o.period_end IS NULL, o.period_end DESC, o.metric ASC",
            ORDER_AVAILABLE: "o.replay_eligible_from ASC, o.period_end ASC",
        }[order]

        rows = self.connection.execute(
            "SELECT o.*, a.ticker AS asset_ticker FROM observations o"
            " JOIN assets a ON a.asset_id = o.asset_id"
            f"{clause} ORDER BY {sort} LIMIT ?",
            (*params, bounded),
        ).fetchall()

        states = self._state_map(asset)
        results = []
        for row in rows:
            result = self._observation_package(
                row, states, include_validation, include_lineage
            )
            if basis_framework and basis_framework not in _canonical(
                result.get("basis")
            ):
                continue
            results.append(result)
        object.__setattr__(
            self, "_last_result_total", self._count_matching(clause, params)
        )
        return results
    def _count_matching(self, clause: str, params: List[Any]) -> int:
        """
        How many rows the filter matches, ignoring the limit.

        Without this a caller cannot tell a complete series from a truncated
        one. A limit of 200 on a 338-point series returns 200 rows, and a count
        that reports 200 is a claim that the series has 200 points — which is
        exactly the kind of quiet falsehood an evidence database exists to
        prevent, and it is invisible precisely because the JSON looks complete.
        """
        return self.connection.execute(
            "SELECT COUNT(*) AS n FROM observations o"
            " JOIN assets a ON a.asset_id = o.asset_id" + clause,
            tuple(params),
        ).fetchone()["n"]

    def page(
        self,
        cursor: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        A page of observations that says whether it is the whole answer.

        `query_observations` keeps its list return and its silent limit, because
        changing it would break every caller that already depends on it. This is
        the honest form: `total_count` is the size of the series, `returned_count`
        is what arrived, and `truncated` is the difference stated outright.
        """
        offset = _decode_cursor(cursor) if cursor is not None else 0
        limit = kwargs.pop("limit", None)
        bounded = _validate_limit(limit)
        rows = self.query_observations(limit=offset + bounded + 1, **kwargs)
        window = rows[offset : offset + bounded]
        has_more = len(rows) > offset + bounded
        return {
            **self._result_envelope(kwargs),
            "total_count": self._last_result_total,
            "returned_count": len(window),
            "truncated": has_more or offset > 0,
            "next_cursor": (
                _encode_cursor(offset + len(window)) if has_more else None
            ),
            "results": window,
        }

    @staticmethod
    def _result_envelope(kwargs: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "asset": kwargs.get("asset"),
            "metric": kwargs.get("metric"),
            "period_start": kwargs.get("period_start"),
            "period_end": kwargs.get("period_end"),
        }

    def get_observation(
        self,
        observation_id: str,
        include_validation: bool = True,
        include_lineage: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """One observation by its stable identity, with full evidence metadata."""
        row = self.connection.execute(
            "SELECT o.*, a.ticker AS asset_ticker FROM observations o"
            " JOIN assets a ON a.asset_id = o.asset_id"
            " WHERE o.observation_id = ? OR o.contract_id = ?"
            " ORDER BY o.first_archived_at LIMIT 1",
            (observation_id, observation_id),
        ).fetchone()
        if row is None:
            return None
        states = self._state_map(row["asset_ticker"])
        return self._observation_package(
            row, states, include_validation, include_lineage
        )

    def get_observations(
        self,
        observation_ids: Sequence[str],
    ) -> List[Dict[str, Any]]:
        """A batch, in the order given, so a caller can follow a ref list."""
        found: List[Dict[str, Any]] = []
        states: Dict[str, Dict[str, Any]] = {}
        for identifier in observation_ids:
            row = self.connection.execute(
                "SELECT o.*, a.ticker AS asset_ticker FROM observations o"
                " JOIN assets a ON a.asset_id = o.asset_id"
                " WHERE o.observation_id = ? OR o.contract_id = ?"
                " ORDER BY o.first_archived_at LIMIT 1",
                (identifier, identifier),
            ).fetchone()
            if row is None:
                continue
            if not states:
                states = self._state_map(row["asset_ticker"])
            found.append(self._observation_package(row, states, True, True))
        return found

    # -- assembly --------------------------------------------------------

    def _observation_package(
        self,
        row: sqlite3.Row,
        states: Dict[str, Dict[str, Any]],
        include_validation: bool,
        include_lineage: bool,
    ) -> Dict[str, Any]:
        """
        One observation, in the canonical evidence shape.

        Fields that are null are still present, with an explicit marker, because
        "the source did not state this" and "we do not know" are different
        answers and a consumer must be able to tell them apart.
        """
        status = row["status"]
        state = self._state_for(row["metric"], states, status)
        raw = _loads(row["raw_json"], {}) or {}
        fact = raw.get("sec_fact", {}) if isinstance(raw, dict) else {}
        value = _loads(row["value_json"], None)
        basis = _loads(row["basis_json"], None)
        available_at = row["available_at"]

        source = {
            "provider": row["provider"],
            "source_type": row["source_type"],
            "source_url": row["source_url"],
            "taxonomy": row["taxonomy"] or fact.get("taxonomy"),
            "concept": row["concept"] or fact.get("tag"),
            "accession": row["accession"] or fact.get("accession"),
            "form": row["form"] or fact.get("form"),
            "fiscal_year": row["fiscal_year"] or fact.get("fy"),
            "fiscal_period": row["fiscal_period"] or fact.get("fp"),
            "documents": self._documents_for(row["observation_id"]),
        }

        package: Dict[str, Any] = {
            "observation_id": row["observation_id"],
            "contract_id": row["contract_id"],
            "asset": row["asset_ticker"],
            "metric": row["metric"],
            "value": value,
            "has_value": value is not None,
            "unit": row["unit"],
            "currency": row["currency"],
            "currency_basis": row["currency_basis"],
            "period": {
                "start": row["period_start"],
                "end": row["period_end"],
                "instant": row["period_end"] if row["period_start"] is None else None,
                "start_is_instant": row["period_start"] is None,
            },
            "as_of": row["as_of"],
            "available_at": {
                "instant": available_at,
                "basis": row["available_at_basis"],
                "class": row["availability_class"],
                "knowable_at": row["replay_eligible_from"],
            },
            "status": {
                "validation_status": status,
                "reasons": _loads(row["status_reasons_json"], []) or [],
                "evidence_state": state,
            },
            "source": source,
            "semantic": self._semantic_for(row, source),
            "definition": row["definition"],
            "methodology": row["methodology"],
            "basis": basis,
            "retrieved_at": row["retrieved_at"],
            "first_archived_at": row["first_archived_at"],
        }
        if include_validation:
            package["validation"] = self.get_validation(
                row["observation_id"]
            )
        if include_lineage:
            package["lineage"] = {
                "kind": KIND_OBSERVED,
                "source_fact_id": row["source_fact_id"],
                "content_hash": row["content_hash"],
                "follow_to": [
                    ref
                    for ref in (
                        row["source_fact_id"],
                        next(
                            (
                                document["content_hash"]
                                for document in package["source"]["documents"]
                            ),
                            None,
                        ),
                    )
                    if ref
                ],
            }
        ambiguity = self._ambiguity_for(row)
        if ambiguity is not None:
            package["ambiguity"] = ambiguity

        return package

    def _ambiguity_for(
        self,
        row: sqlite3.Row,
    ) -> Optional[Dict[str, Any]]:
        """
        Whether this figure is one of several ST-EVA cannot choose between.

        Two observations for one metric and one period with different values are
        not a duplicate. They are two facts the archive holds, and the block says
        so, because a consumer that reads only one of them has no way to know the
        other exists — the same failure as an unknown metric returning an empty
        list, an answer that looks complete and is not.

        **The reason is read out of the evidence, never assumed.**

        This method used to return one sentence for every case: that the
        observations "share this metric, period and source concept" and that "the
        source endpoint aggregates dimension members without returning the
        member". That sentence is a story, and it was wrong for every ambiguity
        in the AAPL snapshot:

        ==========================  ===================================
        reason                      how it was established
        ==========================  ===================================
        CROSS_PROVIDER_DISCREPANCY  the rows carry different providers
        MULTIPLE_SOURCE_CONCEPTS    the rows carry different concepts
        MULTIPLE_FILINGS            one concept, several accessions
        DIMENSION_COLLISION         one concept, one filing, two values
        MULTIPLE_OBSERVATIONS       the evidence identifies nothing
        ==========================  ===================================

        68 of 107 groups were `MULTIPLE_SOURCE_CONCEPTS` — `cash` reported as
        both `CashAndCashEquivalentsAtCarryingValue` and
        `CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents`, which
        are two different measures, not two readings of one. 38 were
        `MULTIPLE_FILINGS`, including the FY2007 revenue the old docstring used
        as its own worked example: a 10-K and a 10-K/A, two filings, not two
        dimension members. The one `CROSS_PROVIDER_DISCREPANCY` was a filing
        against a vendor figure, which the archive's own DISCREPANT validation
        record describes as two sources disagreeing.

        Both free cloud models read that sentence and repeated it to their users
        as the archive's finding. A wrong explanation offered confidently is
        worse than no explanation, because it is checkable-looking and it
        contaminates the capability the evidence exists to support: whether a
        consumer can tell a genuine disagreement from two different measures.

        So the classification is a pure function of the gathered evidence
        (`classify_ambiguity`), the explanation is written from the class rather
        than asserted, and `same_measure_established` says outright whether the
        evidence establishes that the competing figures measure the same thing.
        For `MULTIPLE_SOURCE_CONCEPTS` it is False, and a reader who wanted one
        number is being told that neither of these may be it.
        """
        siblings = self.connection.execute(
            "SELECT observation_id, value_json, source_concept_ref, provider,"
            " source_type, accession FROM observations"
            " WHERE metric = ? AND asset_id = ?"
            " AND period_start IS ? AND period_end IS ?"
            " AND observation_id != ?",
            (
                row["metric"],
                row["asset_id"],
                row["period_start"],
                row["period_end"],
                row["observation_id"],
            ),
        ).fetchall()
        if not siblings:
            return None
        rows = [row, *siblings]
        values = {(member["value_json"] or "").strip() for member in rows}
        if len(values) < 2:
            # Same value from the same period: a restatement or a duplicate
            # filing, not an ambiguity about which figure is meant.
            return None

        concepts = sorted({
            member["source_concept_ref"]
            for member in rows
            if member["source_concept_ref"]
        })
        basis = {
            "source_concepts": concepts,
            "unmapped_observations": sum(
                1 for member in rows if not member["source_concept_ref"]
            ),
            "providers": sorted({member["provider"] for member in rows
                                 if member["provider"]}),
            "source_types": sorted({member["source_type"] for member in rows
                                    if member["source_type"]}),
            "accessions": sorted({member["accession"] for member in rows
                                  if member["accession"]}),
            "observation_count": len(rows),
            "distinct_value_count": len({v for v in values if v}),
        }

        reason = classify_ambiguity(basis)
        block: Dict[str, Any] = {
            "competing_observation_ids": sorted(
                member["observation_id"] for member in siblings
            ),
            "competing_values": sorted(value for value in values if value),
            # The code, not a sentence. A prose reason cannot be checked; a code
            # can be asserted against the evidence in `basis`, and a consumer can
            # tell a genuine disagreement from two different measures without
            # parsing English.
            "reason": reason,
            "determination": "FROM_EVIDENCE",
            "resolution": AMBIGUITY_NO_WINNER,
            "same_measure_established": same_measure_established(basis),
            "basis": basis,
            "explanation": _ambiguity_explanation(reason, basis),
        }
        # Only a cross-provider pair can have a recorded cross-check behind it,
        # and only that one case pays for the lookup. A validation record is the
        # archive knowing why, which is strictly better evidence than the rows
        # alone, so where one exists it is quoted rather than re-derived.
        if reason == AMBIGUITY_CROSS_PROVIDER:
            records: List[Dict[str, Any]] = []
            seen: set = set()
            for member in rows:
                for record in self.get_validation(member["observation_id"]):
                    if record.get("record_id") in seen:
                        continue
                    seen.add(record.get("record_id"))
                    records.append(
                        {
                            "record_id": record.get("record_id"),
                            "status": record.get("status"),
                            "kind": record.get("kind"),
                            "explanation": record.get("explanation"),
                            "independence": (record.get("comparison") or {}).get(
                                "independence"
                            ),
                        }
                    )
            if records:
                block["recorded_cross_check"] = records
                block["determination"] = "FROM_RECORDED_EVIDENCE"
        return block

    def _semantic_for(
        self,
        row: sqlite3.Row,
        source: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        What this figure *is*, as distinct from what it is called.

        Resolved through the registry: observation -> source concept -> semantic
        metric. An unmapped concept is reported as unmapped. It is not attached
        to the metric whose name looks nearest, because a name is not a
        definition and a silent guess here would be indistinguishable from a
        resolved mapping.
        """
        concept_id = source.get("concept")
        taxonomy = source.get("taxonomy")
        if concept_id and ":" not in concept_id and taxonomy:
            concept_id = f"{taxonomy}:{concept_id}"
        if not concept_id:
            return {
                "resolved": False,
                "reason": "the observation carries no source concept",
            }

        resolved = self.registry().resolve(
            concept_id,
            as_of=row["period_end"],
            # The filer matters here and nowhere else. A concept's meaning is
            # filer-independent; when a filer used it is not. Resolving without
            # this reported a filer's own filing as unmapped whenever the
            # concept's window had been seeded from a different company.
            asset_id=row["asset_id"],
        )
        payload = resolved.contract_dict()
        payload["observation_id"] = row["observation_id"]
        # A metric whose series breaks across a concept change says so here, at
        # the figure, rather than leaving it to be discovered by diffing a
        # history.
        if resolved.metric is not None:
            payload["series_breaks"] = self.registry().series_breaks(
                resolved.metric.metric_id
            )
        return payload

    def _documents_for(self, observation_id: str) -> List[Dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT d.document_id, d.content_hash, d.canonical_uri, d.uri,"
            " d.provider, d.document_type, d.media_type, d.byte_size,"
            " d.http_status, d.fetched_at, d.first_seen_at, d.compression,"
            " (d.content IS NOT NULL) AS content_available,"
            " s.redistribution_tier"
            " FROM observation_sources os"
            " JOIN source_documents d ON d.document_id = os.document_id"
            " LEFT JOIN sources s ON s.provider = d.provider"
            " WHERE os.observation_id = ? ORDER BY d.document_id",
            (observation_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    # -- source documents -------------------------------------------------

    def get_source_document(
        self,
        reference: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Source-document metadata by id, content hash, or canonical URI.

        The payload is never returned. Whether the archive holds the bytes is
        reported, along with the source's redistribution tier, so a consumer
        can tell a reference it may not redistribute from one it may. Silently
        serving restricted content would defeat the tier's purpose.
        """
        row = self.connection.execute(
            "SELECT d.*, s.redistribution_tier, s.fair_access_policy,"
            " s.contact_identity FROM source_documents d"
            " LEFT JOIN sources s ON s.provider = d.provider"
            " WHERE d.document_id = ? OR d.content_hash = ?"
            " OR d.canonical_uri = ? OR d.uri = ? LIMIT 1",
            (reference, reference, reference, reference),
        ).fetchone()
        if row is None:
            return None

        observations = [
            {
                "observation_id": r["observation_id"],
                "accession": r["accession"],
            }
            for r in self.connection.execute(
                "SELECT observation_id, accession FROM observation_sources"
                " WHERE document_id = ? ORDER BY observation_id",
                (row["document_id"],),
            )
        ]
        return {
            "source_document_id": row["document_id"],
            "content_hash": row["content_hash"],
            "provider": row["provider"],
            "document_type": row["document_type"],
            "canonical_uri": row["canonical_uri"] or row["uri"],
            "uri": row["uri"],
            "http_status": row["http_status"],
            "media_type": row["media_type"],
            "byte_size": row["byte_size"],
            "fetched_at": row["fetched_at"],
            "first_seen_at": row["first_seen_at"],
            "compression": row["compression"],
            "content_available": bool(row["content"]),
            "redistribution_tier": row["redistribution_tier"] or "B",
            "fair_access_policy": row["fair_access_policy"],
            "contact_identity": row["contact_identity"],
            "content_returned": False,
            "content_note": (
                "The payload is not returned by the query surface. Reference "
                "the content_hash to verify a copy you already hold."
            ),
            "observations": observations,
        }

    # -- validation -------------------------------------------------------

    def get_validation(
        self,
        observation_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Validation records for an observation, with their comparisons intact.

        Never reduced to a boolean. A consumer can see that two sources agreed,
        on what basis, with what independence, and still decide for itself
        whether agreement means corroboration.
        """
        row = self.connection.execute(
            "SELECT observation_id FROM observations"
            " WHERE observation_id = ? OR contract_id = ? LIMIT 1",
            (observation_id, observation_id),
        ).fetchone()
        if row is None:
            return []

        records = self.connection.execute(
            "SELECT * FROM validation_records WHERE observation_id = ?"
            " ORDER BY checked_at",
            (row["observation_id"],),
        ).fetchall()

        results: List[Dict[str, Any]] = []
        for record in records:
            basis = _loads(record["comparison_basis_json"], {}) or {}
            results.append(
                {
                    "record_id": record["record_id"],
                    "kind": record["kind"],
                    "status": record["status"],
                    "reasons": _loads(record["reasons_json"], []) or [],
                    "checked_at": record["checked_at"],
                    "comparison": {
                        "vendor_ref": basis.get("vendor_observation"),
                        "filing_ref": basis.get("filing_observation"),
                        "provider": basis.get("provider"),
                        "period": {
                            "vendor_as_of": basis.get("vendor_as_of"),
                            "filing_period_end": basis.get(
                                "filing_period_end"
                            ),
                        },
                        "period_match": basis.get("period_offset_days"),
                        "unit_match": basis.get("vendor_unit")
                        == basis.get("filing_unit"),
                        "currency_match": basis.get("vendor_currency")
                        == basis.get("filing_currency"),
                        "methodology_match": basis.get("methodology_match"),
                        "independence": basis.get("independence"),
                        "tolerance": _loads(record["tolerance_json"], None),
                        "basis": basis,
                    },
                    "explanation": record["explanation"],
                    "references": _loads(record["references_json"], []) or [],
                    "value_snapshot": _loads(
                        record["value_snapshot_json"], None
                    ),
                    "trusted": None,
                    "trusted_note": (
                        "Validation is a record, not a boolean. A CONSISTENT "
                        "status means two comparable sources agreed within a "
                        "declared tolerance; whether that is corroboration "
                        "depends on the independence field, which this "
                        "surface reports and does not interpret."
                    ),
                }
            )
        return results

    # -- lineage ----------------------------------------------------------

    def get_lineage(
        self,
        reference: str,
        depth: int = 4,
    ) -> Dict[str, Any]:
        """
        Machine-readable lineage for an observation or a derived value.

        For an observed fact: source document -> source fact -> observation.
        For a derived value: result -> operation -> operands -> source
        observations. The kind is always stated, because a consumer must not
        have to infer whether a number was reported or computed.
        """
        if depth < 1:
            raise QueryError("depth must be at least 1")

        derived = self._derived_row(reference)
        if derived is not None:
            return self._derived_lineage(derived, depth)

        observation = self.get_observation(reference)
        if observation is None:
            return {
                "reference": reference,
                "kind": KIND_UNAVAILABLE,
                "reason": "no observation or derived value with this reference",
                "chain": [],
            }

        documents = observation["source"]["documents"]
        chain: List[Dict[str, Any]] = []
        for document in documents:
            chain.append(
                {
                    "step": "SOURCE_DOCUMENT",
                    "id": document["document_id"],
                    "content_hash": document["content_hash"],
                    "canonical_uri": document["canonical_uri"],
                    "document_type": document["document_type"],
                    "content_available": document["content_available"],
                    "redistribution_tier": document["redistribution_tier"],
                }
            )
        if observation["lineage"]["source_fact_id"]:
            chain.append(
                {
                    "step": "SOURCE_FACT",
                    "id": observation["lineage"]["source_fact_id"],
                    "scope": (
                        "one raw fact inside one source document; the only "
                        "identity deduplication may use"
                    ),
                }
            )
        chain.append(
            {
                "step": "OBSERVATION",
                "id": observation["observation_id"],
                "metric": observation["metric"],
                "state": observation["status"]["evidence_state"]["state"],
            }
        )
        if observation["validation"]:
            chain.append(
                {
                    "step": "VALIDATION",
                    "id": observation["validation"][0]["record_id"],
                    "status": observation["validation"][0]["status"],
                    "independence": observation["validation"][0]["comparison"][
                        "independence"
                    ],
                }
            )
        return {
            "reference": reference,
            "kind": KIND_OBSERVED,
            "state": observation["status"]["evidence_state"]["state"],
            "chain": chain,
        }

    def _derived_row(self, reference: str) -> Optional[sqlite3.Row]:
        return self.connection.execute(
            "SELECT * FROM derived_values WHERE ref = ? ORDER BY context_id LIMIT 1",
            (reference,),
        ).fetchone()

    def _derived_lineage(
        self,
        derived: sqlite3.Row,
        depth: int,
    ) -> Dict[str, Any]:
        operation = _loads(derived["operation_json"], {}) or {}
        # 2.3-C writes dependencies as a list of refs. A dict is accepted too,
        # because a caller that already resolved an operand should not have to
        # discard that work.
        operands: List[Dict[str, Any]] = []
        for operand in (_loads(derived["depends_on_json"], []) or []):
            if isinstance(operand, str):
                operands.append({"ref": operand})
            elif isinstance(operand, dict):
                operands.append(operand)
        operand_refs = [operand.get("ref") for operand in operands]

        resolved: List[Dict[str, Any]] = []
        for operand in operands:
            ref = operand.get("ref")
            detail = {
                "ref": ref,
                "observation_id": operand.get("observation_id"),
                "value": operand.get("value"),
                "unit": operand.get("unit"),
            }
            if detail["value"] is None and ref:
                found = self.get_observation(
                    _strip_ref_prefix(ref), include_validation=False,
                    include_lineage=False,
                )
                if found is not None:
                    detail["value"] = found["value"]
                    detail["unit"] = found["unit"]
                    detail["observation_id"] = found["observation_id"]
            resolved.append(detail)
        chain: List[Dict[str, Any]] = [
            {
                "step": "DERIVED",
                "id": derived["ref"],
                "value": _loads(derived["value_json"], None),
                "unit": derived["unit"],
                "expression": derived["expression"],
                "deterministic": bool(derived["deterministic"]),
            },
            {
                "step": "OPERATION",
                "operation_id": operation.get("op"),
                "operation_version": operation.get("version"),
                "parameters": operation.get("parameters"),
                "operands": operand_refs,
            },
        ]
        if depth > 1:
            for ref in operand_refs:
                if not ref:
                    continue
                # An operand may be written as a bare id or as a prefixed ref
                # such as `obs:<id>`. Resolving the id itself keeps a prefixed
                # reference from being looked up twice over.
                nested = self.get_lineage(
                    _strip_ref_prefix(ref), depth=depth - 1
                )
                chain.append(
                    {
                        "step": "OPERAND",
                        "ref": ref,
                        "kind": nested.get("kind"),
                        "state": nested.get("state"),
                        "chain": nested.get("chain", []),
                    }
                )
        return {
            "reference": derived["ref"],
            "kind": KIND_DERIVED,
            "state": KIND_DERIVED,
            "context_id": derived["context_id"],
            # The stored value, at the top level, next to the operands it was
            # stored with.
            #
            # It was already in the chain at step DERIVED, and a consumer that
            # wanted "what is this derived figure, and how was it made" had to
            # walk the chain to get it -- which meant the one question the
            # reference exists to answer could not be answered from the payload
            # that names the reference. Both cloud models in 2.6.2 asked exactly
            # that question, and neither reached for `get_lineage` at all.
            #
            # This is the archived value read back, not a recalculation. The
            # database value and the authoritative calculation stay separate, and
            # `recomputation.recomputed_by_query` says so in the same payload so
            # that cannot be misread as the query layer having computed it.
            "value": _loads(derived["value_json"], None),
            "unit": derived["unit"],
            "expression": derived["expression"],
            "operands": resolved,
            "recomputation": {
                "expression": derived["expression"],
                "operation": operation,
                "recomputed_by_query": False,
                "value_source": "STORED_DERIVED_VALUE",
                "note": (
                    "The stored derived value is returned as archived. The "
                    "query surface does not recompute it; the database value "
                    "and the authoritative calculation stay separate."
                ),
            },
            "chain": chain,
        }

    # -- metric history ---------------------------------------------------

    def get_metric_history(
        self,
        asset: str,
        metric: str,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        An LLM-facing historical series for one metric.

        A wrapper over `query_observations`, not a second storage model. It
        exists to carry the things a naive series would drop: the unit, the
        currency, the basis, the source, the state, and whether the series is
        comparable at all. Series that are not comparable are reported as such
        and are not merged, which is the 2.4.3 rule applied on the read path.
        """
        observations = self.query_observations(
            asset=asset,
            metric=metric,
            period_start=period_start,
            period_end=period_end,
            order=ORDER_ASC,
            limit=limit,
        )
        total = self._last_result_total
        truncated = total > len(observations)
        states = self._state_map(asset)
        # A metric with a value in hand is reported, even when the state table
        # says nothing about it. A metric with observations but no value is
        # absent in a way the state table would describe, not one we guess at.
        state = self._state_for(
            metric,
            states,
            observations[-1]["status"]["validation_status"]
            if observations
            else None,
            has_value=any(point["has_value"] for point in observations)
            if observations
            else False,
        )

        bases = sorted(
            {
                (observation.get("basis") or {}).get("reporting_framework")
                or "UNDECLARED"
                for observation in observations
                if observation.get("basis")
            }
        )
        reporting_framworks = bases[0] if len(bases) == 1 else None

        points = [
            {
                "period": observation["period"],
                "as_of": observation["as_of"],
                "available_at": observation["available_at"],
                "value": observation["value"],
                "has_value": observation["has_value"],
                "unit": observation["unit"],
                "currency": observation["currency"],
                "basis": observation.get("basis"),
                "state": observation["status"]["evidence_state"]["state"],
                "status": observation["status"]["validation_status"],
                "observation_id": observation["observation_id"],
                "source": {
                    "provider": observation["source"]["provider"],
                    "accession": observation["source"]["accession"],
                    "concept": observation["source"]["concept"],
                    "form": observation["source"]["form"],
                    "content_hashes": [
                        document["content_hash"]
                        for document in observation["source"]["documents"]
                    ],
                },
                "validation": [
                    {
                        "status": record["status"],
                        "independence": record["comparison"]["independence"],
                    }
                    for record in observation.get("validation", [])
                ],
            }
            for observation in observations
        ]

        return {
            "asset": asset,
            "metric": metric,
            "state": state,
            # What the series holds, not what this call returned. A truncated
            # page that reported 200 for a 338-point series would be a JSON
            # document that looks complete and is not, which is the one failure
            # an evidence surface cannot afford: a reader cannot detect it.
            "point_count": total,
            "returned_count": len(observations),
            "truncated": truncated,
            "truncation_note": (
                "This series holds %d points and this response carries %d. "
                "The series is not complete; ask again with a higher limit or "
                "page through `page()` to reach the rest."
                % (total, len(observations))
                if truncated
                else None
            ),
            "series_comparability": {
                "reporting_frameworks": bases,
                "single_framework": reporting_framworks is not None,
                "comparable": reporting_framworks is not None,
                "reason": (
                    None
                    if reporting_framworks is not None
                    else "points on this series declare different reporting "
                    "frameworks, so they are not one comparable series and "
                    "have not been merged"
                ),
            },
            "points": points,
        }

    # -- coverage ---------------------------------------------------------

    def coverage_report(
        self,
        asset: str,
    ) -> Dict[str, Any]:
        """
        What is held for one company, and in what state.

        Counts by state, never a single completeness number. A percentage would
        be an interpretation, and it would hide which of the four distinct
        negatives is in play for any given metric.
        """
        asset_id = self._asset_id(asset)
        states = self._state_map(asset)
        held = self.connection.execute(
            "SELECT metric, COUNT(*) AS n FROM observations"
            " WHERE asset_id = ? GROUP BY metric",
            (asset_id,),
        ).fetchall()
        by_metric = {row["metric"]: row["n"] for row in held}

        metrics = set(by_metric) | set(states)
        counts = {state: 0 for state in EVIDENCE_STATES}
        detail = []
        for metric in sorted(metrics):
            latest = self.connection.execute(
                "SELECT status, value_json FROM observations"
                " WHERE asset_id = ? AND metric = ?"
                " ORDER BY first_archived_at DESC LIMIT 1",
                (asset_id, metric),
            ).fetchone()
            resolved = self._state_for(
                metric,
                states,
                latest["status"] if latest else None,
                has_value=(
                    _loads(latest["value_json"], None) is not None
                    if latest
                    else False
                ),
            )
            counts[resolved["state"]] += 1
            detail.append(
                {
                    "metric": metric,
                    "state": resolved["state"],
                    "reason_code": resolved["reason_code"],
                    "observations_held": by_metric.get(metric, 0),
                    "resolved_from": resolved["resolved_from"],
                }
            )
        return {
            "asset": asset,
            "metric_count": len(metrics),
            "state_counts": counts,
            "metrics": detail,
            "note": (
                "States are counted, not scored. A single completeness figure "
                "would be an interpretation and would hide which distinct "
                "negative applies to which metric."
            ),
        }
