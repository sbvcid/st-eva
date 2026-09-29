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

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from data_contract import parse_iso_date, utc_now
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

# Lineage kinds. A consumer must not have to infer whether a figure was
# reported or computed.
KIND_OBSERVED = "OBSERVED"
KIND_DERIVED = "DERIVED"
KIND_UNAVAILABLE = "UNAVAILABLE"
KIND_CONFLICTING = "CONFLICTING"

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


def _validate_limit(limit: Optional[int]) -> int:
    if limit is None:
        return _DEFAULT_LIMIT
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise QueryError("limit must be an integer")
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
        status: Optional[str] = None,
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
        """
        period_start = _validate_date("period_start", period_start)
        period_end = _validate_date("period_end", period_end)
        as_of = _validate_date("as_of", as_of)
        knowable_at = _validate_date("knowable_at", knowable_at)
        _validate_period(period_start, period_end)
        order = _validate_order(order)
        bounded = _validate_limit(limit)

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
        if status:
            where.append("o.status = ?")
            params.append(status)
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
        return results

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
            "source": {
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
            },
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
        return package

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
            "operands": resolved,
            "recomputation": {
                "expression": derived["expression"],
                "operation": operation,
                "recomputed_by_query": False,
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
            "point_count": len(points),
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
