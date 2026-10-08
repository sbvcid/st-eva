from __future__ import annotations

"""
ST-EVA 2.4 - the SQLite archive.

The first implementation of `archive.ArchiveStore`, and deliberately only that.
Everything here is persistence: it turns contract objects into rows and rows
back into contract objects, and it enforces the append-only invariants with the
triggers declared in `archive/migrations/0001_initial.sql`.

Two rules shape the whole file:

    Observations are appended, never updated. A restatement is a new row in the
    same lineage, so a replay before the restatement still shows the original.

    A source document referenced by a stored observation is never deleted. A
    dangling `document_id` is worse than no capture at all, because it looks
    like evidence.
"""

import gzip
import hashlib
import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from archive import (
    ARCHIVE_FIRST_SEEN,
    DECLARED_BASES,
    SOURCE_DECLARED,
    UNDECLARED,
    ArchiveError,
    ArchiveStore,
    FilingRef,
    InterpretationError,
    StoredDocument,
    document_hash,
    utc_now,
)
from data_contract import (
    AvailabilityBasis,
    Observation,
    SourceType,
    ValidationStatus,
    eligibility_for_declared_date,
    point_in_time_cutoff,
)
from knowledge_axis import (
    KnowledgeAxis,
    KnowledgeAxisError,
    SourceFact,
)
# The provenance writers below receive identities from `sec_provenance` and the
# closed vocabularies those identities are validated against. Importing the
# vocabularies rather than restating them is the point: `0020_sec_provenance.sql`
# enforces the same sets in triggers, and a second copy here would be free to
# drift from the migration.
from sec_provenance import (
    ACCEPTANCE_PRECISIONS,
    ACCEPTANCE_SOURCES,
    ACQUISITION_CLASSES,
    CAPTURE_KINDS,
    DECLARATION_SOURCES,
    EXTRACTION_METHODS,
    FISCAL_CALENDAR_DECLARATION_SOURCES,
    ITEM_DECLARATION_SOURCES,
    MANIFEST_SOURCES,
    STATEMENT_KINDS,
)

MIGRATIONS_DIR = Path(__file__).resolve().parent / "archive" / "migrations"


def _require(field: str, value: Any, vocabulary: Tuple[str, ...]) -> None:
    """Refuse a value outside a closed vocabulary, naming the field.

    The migration's triggers are still the authority -- they fire for anything
    that reaches the database by another route -- but refusing here means a
    caller gets a message that names the column instead of a bare
    `sqlite3.IntegrityError`.
    """
    if value not in vocabulary:
        raise ValueError(
            f"{field} must be one of {', '.join(vocabulary)}; got {value!r}"
        )

# Fields round-tripped verbatim between a row and an Observation. The archive
# stores the contract's own field names, so a stored observation is a copy and
# not a rendering of one.
_SCALAR_FIELDS = (
    "observation_id",
    "metric",
    "unit",
    "currency",
    "currency_basis",
    "period_start",
    "period_end",
    "as_of",
    "available_at",
    "available_at_basis",
    "provider",
    "source_type",
    "source_url",
    "definition",
    "methodology",
    "retrieved_at",
)


def _canonical(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def _concept_of(observation: Observation) -> str:
    """
    The concept an observation is about, for lineage purposes.

    Taken from the preserved XBRL payload when present, because a vendor field
    name and a filing concept are the same fact expressed in two vocabularies,
    and merging them into one lineage would hide the switch between them.
    """
    raw = observation.raw if isinstance(observation.raw, dict) else {}
    fact = raw.get("sec_fact") if isinstance(raw.get("sec_fact"), dict) else {}
    taxonomy = fact.get("taxonomy")
    tag = fact.get("tag")
    if taxonomy and tag:
        return f"{taxonomy}:{tag}"
    if tag:
        return str(tag)
    return observation.metric


def _accession_of(observation: Observation) -> Optional[str]:
    raw = observation.raw if isinstance(observation.raw, dict) else {}
    fact = raw.get("sec_fact") if isinstance(raw.get("sec_fact"), dict) else {}
    return fact.get("accession") or raw.get("accession") or None


def observation_content_hash(observation: Observation) -> str:
    """
    The identity of a fact.

    Includes the accession, so the same period reported by a later filing with a
    different value is a different fact rather than a collision.
    """
    payload = {
        "observation_id": observation.observation_id,
        "metric": observation.metric,
        "provider": observation.provider,
        "concept": _concept_of(observation),
        "value": observation.value,
        "unit": observation.unit,
        "currency": observation.currency,
        "period_start": observation.period_start,
        "period_end": observation.period_end,
        "as_of": observation.as_of,
        "available_at": observation.available_at,
        "accession": _accession_of(observation),
    }
    return "obs_sha256:" + hashlib.sha256(
        _canonical(payload).encode("utf-8")
    ).hexdigest()


def _lineage_id(
    asset_id: str,
    observation: Observation,
) -> str:
    payload = {
        "asset": asset_id,
        "metric": observation.metric,
        "concept": _concept_of(observation),
        "period_start": observation.period_start,
        "period_end": observation.period_end,
    }
    return "line_" + hashlib.sha256(
        _canonical(payload).encode("utf-8")
    ).hexdigest()[:24]


#: A cutoff meaning "everything ST-EVA knows". Used where a caller expresses no
#: point in time and wants the effective reading rather than a historical one.
LATEST_KNOWLEDGE = "9999-12-31T23:59:59.999999+00:00"


def table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,)).fetchone() is not None


def _row_as_dict(connection: sqlite3.Connection, sql: str,
                 params: Tuple[Any, ...] = ()) -> Optional[Dict[str, Any]]:
    """
    One row as a dict, whatever the connection's row factory is.

    `interpretation_status` and `knowledge_axis_for` are module-level and take a
    caller's connection, and callers legitimately differ: `EvidenceQuery` is
    handed connections it did not open. Assuming `sqlite3.Row` would make the
    canonical selection rule depend on an incidental setting, and the first
    symptom would be a `TypeError` in a reader rather than a wrong answer.
    """
    cursor = connection.execute(sql, params)
    row = cursor.fetchone()
    if row is None:
        return None
    return dict(zip([description[0] for description in cursor.description], row))


def knowledge_axis_for(connection: sqlite3.Connection, source_fact_id: str
                       ) -> Optional[KnowledgeAxis]:
    """
    Rebuild one source fact's stored interpretation series as a validated axis.

    Returns None when no observation carries that `source_fact_id`, which is a
    statement about the fact rather than a failure.

    An observation whose source declared no availability has no availability to
    stand in for, and `KnowledgeAxis` insists on one. The earliest instant the
    archive recorded is used so the knowledge question can still be answered:
    availability gates whether a fact is replay-eligible, and plays no part in
    choosing between interpretations. A row with nothing at all recorded falls
    through to None, which callers read as "no source fact to interpret".
    """
    row = _row_as_dict(connection,
                       "SELECT * FROM observations WHERE source_fact_id = ?",
                       (source_fact_id,))
    if row is None:
        return None
    availability = (row["available_at"] or row["replay_eligible_from"]
                    or row["first_archived_at"])
    if availability is None:
        return None
    fact = SourceFact(
        source_fact_id=row["source_fact_id"],
        available_at=availability,
        replay_eligible_from=row["replay_eligible_from"] or availability,
        value=json.loads(row["value_json"]),
        period_start=row["period_start"],
        period_end=row["period_end"],
        metric=row["metric"],
        lineage_id=row["lineage_id"],
    )
    axis = KnowledgeAxis(fact)
    cursor = connection.execute(
        "SELECT * FROM interpretations WHERE source_fact_id = ?"
        " ORDER BY knowledge_at, interpretation_id", (source_fact_id,))
    columns = [description[0] for description in cursor.description]
    for stored_row in cursor:
        stored = dict(zip(columns, stored_row))
        axis.record(
            stored["knowledge_at"], stored["unit"], stored["currency"],
            stored["currency_basis"], supersedes=stored["supersedes"])
    return axis


def interpretation_status(connection: sqlite3.Connection,
                          source_fact_id: Optional[str],
                          cutoff: Optional[str] = None
                          ) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    THE canonical effective-interpretation selection rule.

    Every reader goes through this one function. A second resolver would be a
    second answer to the same question, and the two would eventually disagree at
    a boundary -- which is the defect 2.64 exists to remove between two readers
    that already had.

    The selection itself is `KnowledgeAxis.effective_at`, validated in 2.59, so
    the inclusive boundary and the tie refusal live in exactly one place.

    Status is one of

        APPLIED              an interpretation was found and applies
        BASELINE             none applies; the observation's own reading stands
        UNAVAILABLE_LEGACY   the archive predates the interpretations table
        NO_SOURCE_FACT       the observation carries no source-fact identity

    `cutoff=None` means "everything ST-EVA knows", which is what a reader with
    no point in time in the question is asking for.
    """
    if not table_exists(connection, "interpretations"):
        return None, "UNAVAILABLE_LEGACY"
    if not source_fact_id:
        return None, "NO_SOURCE_FACT"
    axis = knowledge_axis_for(connection, source_fact_id)
    if axis is None:
        return None, "NO_SOURCE_FACT"
    chosen = axis.effective_at(cutoff or LATEST_KNOWLEDGE)
    if chosen is None:
        return None, "BASELINE"
    stored = _row_as_dict(
        connection, "SELECT * FROM interpretations WHERE identity = ?",
        (chosen.identity,))
    if stored is None:
        return None, "BASELINE"
    return stored, "APPLIED"


def admission_identity(
    asset_id: str,
    decided_at: str,
    metric: Optional[str],
    admitted: bool,
    contract_id: Optional[str],
    registry_state_identity: str,
    resolver_policy_identity: str,
    price_contract_id: Optional[str] = None,
) -> str:
    """
    The content-derived key that identifies one admission decision.

    Built over the decision itself rather than over its rendering, so a
    repeated identical decision is a read and a changed decision is a new row.

    Three parts of it are the interpretation, not the data:

    * both identity digests. The same asset, instant and metric under a
      different registry or a different policy is a *different decision*, and a
      key that omitted either would make a change of interpretation invisible.
    * `price_contract_id`. `_currency_refusals`
      (`evidence_valuation_boundary.py:611-648`) answers CURRENCY_UNDECLARED
      when the price declares no currency and CURRENCY_MISMATCH when it does not
      match, so the price decides rule 4 and therefore the outcome. Two prices
      can decide differently, so which one decided is part of what was decided.
      Its figure is not -- that is the observation's business.

    Nothing about the payload is here: no value, no refusal text, no registry
    content. All of it is re-derivable, and identity should not carry data that
    can drift from the row it names.

    Canonicalised the same way `registry_identity` canonicalises, for the same
    reason: one rendering, so the same decision hashes the same way on any
    machine.
    """
    return hashlib.sha256(
        json.dumps(
            {
                "asset_id": asset_id,
                "decided_at": decided_at,
                "metric": metric,
                "admitted": bool(admitted),
                "contract_id": contract_id,
                "registry_state_identity": registry_state_identity,
                "resolver_policy_identity": resolver_policy_identity,
                "price_contract_id": price_contract_id,
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


class SQLiteArchive(ArchiveStore):
    """A single-file SQLite archive. One connection, opened lazily."""

    def __init__(
        self,
        path: str = "data/st-eva.sqlite",
        archive_unknown_availability: bool = True,
        create: bool = True,
        capture_content: bool = True,
    ) -> None:
        """
        `archive_unknown_availability` decides the class of an observation whose
        source declared no availability.

        True archives it as ARCHIVE_FIRST_SEEN, eligible from the moment the
        archive first held it and permanently labelled observational. False
        keeps it UNDECLARED and permanently ineligible. Neither setting ever
        promotes an undated value to source-declared knowledge.

        `capture_content` decides whether a fetched document's bytes are kept
        or only its hash and URI. The hash is always recorded, so a
        content-addressed store is deduplicated either way; storing the payload
        additionally makes the archive self-contained years later.
        """
        self.path = str(path)
        self.archive_unknown_availability = archive_unknown_availability
        self.capture_content = capture_content
        self._connection: Optional[sqlite3.Connection] = None
        # Keyed by the contract observation id, which is what a replay holds.
        self._class_cache: Dict[str, str] = {}
        if create:
            self._ensure_schema()

    # -- connection -------------------------------------------------------

    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            if self.path != ":memory:":
                Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            # A lost write here is a lost fact, and this workload is nowhere
            # near throughput-bound.
            connection.execute("PRAGMA synchronous = FULL")
            self._connection = connection
        return self._connection

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __enter__(self) -> "SQLiteArchive":
        return self

    def __exit__(self, *exception: Any) -> None:
        self.close()

    # -- migrations -------------------------------------------------------

    def _migrations(self) -> List[Tuple[int, str, Path]]:
        found: List[Tuple[int, str, Path]] = []
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version, _, name = path.stem.partition("_")
            found.append((int(version), name, path))
        return found

    def _ensure_schema(self) -> None:
        """
        Apply pending migrations, forward only.

        The recorded checksum is verified on every run. A migration that has
        been edited since it was applied aborts startup, because the archive's
        shape would no longer be the one that actually ran.
        """
        connection = self.connection
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version INTEGER PRIMARY KEY, name TEXT NOT NULL,"
            " checksum TEXT NOT NULL, applied_at TEXT NOT NULL)"
        )
        applied = {
            row["version"]: row["checksum"]
            for row in connection.execute(
                "SELECT version, checksum FROM schema_migrations"
            )
        }
        for version, name, path in self._migrations():
            sql = path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
            if version in applied:
                if applied[version] != checksum:
                    raise ArchiveError(
                        f"migration {version}_{name} was modified after it "
                        "was applied. Migrations are forward-only; add a new "
                        "one instead of editing this."
                    )
                continue
            current = connection.execute(
                "PRAGMA user_version"
            ).fetchone()[0]
            if version <= current:
                raise ArchiveError(
                    f"migration {version} is below the recorded user_version "
                    f"{current}. The archive was created by a newer build."
                )
            # `executescript` commits any pending transaction before it runs, so
            # a migration that fails part-way through would otherwise leave DDL
            # applied and unrecorded -- a schema state that no migration claims
            # and no later run will reconcile. The rollback is explicit for that
            # reason, and it is a no-op on the success path.
            try:
                connection.executescript(sql)
                connection.execute(
                    "INSERT INTO schema_migrations (version, name, checksum,"
                    " applied_at) VALUES (?, ?, ?, ?)",
                    (version, name, checksum, utc_now()),
                )
                connection.execute(f"PRAGMA user_version = {version}")
                connection.commit()
            except Exception:
                try:
                    connection.rollback()
                except sqlite3.Error:
                    pass
                raise

    # -- assets and sources ----------------------------------------------

    def asset_id_for_cik(self, cik: str) -> Optional[str]:
        """
        The asset this CIK is already stored as, or None.

        Added because `assets.cik` is UNIQUE and that constraint is right: two
        rows for one filer would put the same filing under two names and make
        every later comparison ambiguous. It also means a company that trades
        several share classes has several tickers and one issuer, so a caller
        working from a ticker list will arrive here with the same CIK twice and
        the second arrival is a lookup rather than a violation.

        Matches both the zero-padded and the bare form rather than importing the
        provider's `normalize_cik`. The archive is the layer *below* the
        provider, and a storage class that reaches up to a source adapter for a
        string format has the dependency backwards -- the padded form is
        EDGAR's convention, and matching both is also the more forgiving thing
        to do with a value that arrives from a caller.
        """
        bare = str(cik).strip()
        padded = bare.zfill(10) if bare.isdigit() else bare
        row = self.connection.execute(
            "SELECT asset_id FROM assets WHERE cik IN (?, ?) LIMIT 1",
            (bare, padded),
        ).fetchone()
        return row["asset_id"] if row is not None else None

    def record_asset(
        self,
        ticker: str,
        cik: Optional[str] = None,
        name: Optional[str] = None,
        exchange: Optional[str] = None,
        currency: Optional[str] = None,
    ) -> str:
        """Register an asset, or return the existing one unchanged."""
        existing = self.connection.execute(
            "SELECT asset_id, cik, name, exchange, currency FROM assets"
            " WHERE ticker = ?",
            (ticker.upper(),),
        ).fetchone()
        if existing is not None:
            # Assets are identity, not observation: filling in metadata a later
            # run knows is a correction, not a rewrite of history.
            merged = {
                "cik": cik or existing["cik"],
                "name": name or existing["name"],
                "exchange": exchange or existing["exchange"],
                "currency": currency or existing["currency"],
            }
            self.connection.execute(
                "UPDATE assets SET cik = ?, name = ?, exchange = ?,"
                " currency = ? WHERE asset_id = ?",
                (
                    merged["cik"],
                    merged["name"],
                    merged["exchange"],
                    merged["currency"],
                    existing["asset_id"],
                ),
            )
            self.connection.commit()
            return existing["asset_id"]

        asset_id = "asset_" + hashlib.sha256(
            ticker.upper().encode("utf-8")
        ).hexdigest()[:20]
        self.connection.execute(
            "INSERT INTO assets (asset_id, ticker, cik, name, exchange,"
            " currency, first_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (asset_id, ticker.upper(), cik, name, exchange, currency, utc_now()),
        )
        self.connection.commit()
        return asset_id

    def record_source(
        self,
        provider: str,
        source_type: str = SourceType.API_LIVE.value,
        base_url: Optional[str] = None,
        declared: str = "YES",
        notes: Optional[str] = None,
        retains_dimensions: Optional[str] = None,
        aggregation_note: Optional[str] = None,
    ) -> str:
        """
        Register a source and, optionally, what shape its facts arrive in.

        `retains_dimensions` is a property of the **endpoint**, not of a metric
        and not of a filer, and 2.22 is why it is declared here rather than
        inferred per metric:

            AGGREGATE   the endpoint returns facts without the dimensional axis,
                        so two facts that differ only by member arrive looking
                        like one. Not a defect; it is what the endpoint is.
            NONE        every endpoint this project uses is AGGREGATE, which is
                        why the distinction is recorded rather than inferred --
                        a source that kept its axes would need it.

        The per-event `ingestion_dimension_collisions` rows are then **evidence**
        for this declaration rather than a set of metric-specific exceptions.
        Without it the natural reading of 392 collisions across eight banks is
        "`gross_profit` is weird", when the measurement actually showed
        `operating_cash_flow` with six times more affected keys and `equity` with
        more extra values per key than `gross_profit` had. The property belongs
        to how the source represents facts, so it is stated where that lives.
        """
        source_id = "src_" + hashlib.sha256(
            f"{provider}|{source_type}|{base_url}".encode("utf-8")
        ).hexdigest()[:20]
        self.connection.execute(
            "INSERT OR IGNORE INTO sources (source_id, provider, source_type,"
            " base_url, declared, notes, retains_dimensions, aggregation_note)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                source_id, provider, source_type, base_url, declared, notes,
                retains_dimensions, aggregation_note,
            ),
        )
        self.connection.commit()
        return source_id

    # -- source documents -------------------------------------------------

    def record_source_document(self, document: StoredDocument) -> str:
        """
        Store a captured document, addressed by the hash of its bytes.

        The same bytes are stored once however many observations reference
        them, so a stable endpoint costs one row forever. When the payload is
        kept it is compressed here, but `content_hash` always covers the
        *uncompressed* bytes, so the hash means the same thing either way.
        Requirement 13 is enforced by offering no delete path at all.
        """
        existing = self.connection.execute(
            "SELECT document_id FROM source_documents WHERE content_hash = ?",
            (document.content_hash,),
        ).fetchone()
        if existing is not None:
            return existing["document_id"]

        payload: Optional[bytes] = None
        encoding: Optional[str] = None
        byte_size = document.byte_size
        if self.capture_content and document.payload is not None:
            payload = gzip.compress(document.payload, 6)
            encoding = "gzip"
            byte_size = len(document.payload)

        document_id = "doc_" + hashlib.sha256(
            document.content_hash.encode("utf-8")
        ).hexdigest()[:24]
        self.connection.execute(
            "INSERT INTO source_documents (document_id, content_hash, uri,"
            " canonical_uri, http_status, media_type, byte_size, fetched_at,"
            " first_seen_at, storage_path, compression, provider,"
            " document_type, content, content_encoding)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                document_id,
                document.content_hash,
                document.uri,
                document.canonical_uri or document.uri,
                document.http_status,
                document.media_type,
                byte_size,
                document.fetched_at,
                document.first_seen_at,
                document.storage_path,
                document.compression or encoding,
                document.provider,
                document.document_type,
                payload,
                encoding,
            ),
        )
        self.connection.commit()
        return document_id

    def content_for(self, content_hash: str) -> Optional[bytes]:
        """
        The captured bytes of a document, decompressed.

        Returns None for a document that was captured as a reference rather
        than as content. The distinction is recorded in `document_type` and
        the returned value, so a missing payload is never mistaken for an
        empty document.
        """
        row = self.connection.execute(
            "SELECT content, content_encoding, compression FROM source_documents"
            " WHERE content_hash = ? OR document_id = ?",
            (content_hash, content_hash),
        ).fetchone()
        if row is None or row["content"] is None:
            return None
        blob = row["content"]
        if (row["content_encoding"] or row["compression"]) == "gzip":
            return gzip.decompress(blob)
        return bytes(blob)

    # -- SEC provenance (0020) ----------------------------------------------
    #
    # One writer per relation added by `0020_sec_provenance.sql`, in the same
    # idiom as every other writer here: it receives an identity that has already
    # been computed by `sec_provenance`, it performs no SEC parsing, no network
    # access and no classification policy, and it never writes an Observation.
    #
    # Idempotency is a read-then-write, the shape `record_source_document` already
    # uses: an assertion that is already held returns its existing identity and
    # writes nothing. No writer here issues an UPDATE -- every relation refuses
    # one -- so a re-acquisition can only add, never amend.
    #
    # A writer returning `True` means it created a row and `False` means the row
    # was already there. The digest-keyed writers return the identity instead,
    # so a caller can use the same value either way.

    def record_filing(
        self,
        asset_id: str,
        accession: str,
        first_archived_at: str,
    ) -> bool:
        """
        Record that a filing exists. Nothing else.

        `filings` deliberately holds no filing attribute. `form`, `filing_date`,
        `report_date`, `conformed_period_of_report`, `public_document_count`,
        `is_xbrl` and `primary_document` are all assertions by a source and live
        in `filing_declarations`, because a later and better source has to be able
        to add one without mutating anything. A filing row is the fact that a
        filing exists, not what it says.

        `first_archived_at` is this archive's own clock and is not part of any
        identity.
        """
        existing = self.connection.execute(
            "SELECT 1 FROM filings WHERE asset_id = ? AND accession = ?",
            (asset_id, accession),
        ).fetchone()
        if existing is not None:
            return False
        self.connection.execute(
            "INSERT INTO filings (asset_id, accession, first_archived_at)"
            " VALUES (?, ?, ?)",
            (asset_id, accession, first_archived_at),
        )
        self.connection.commit()
        return True

    def record_filing_declaration(
        self,
        declaration_id: str,
        asset_id: str,
        accession: str,
        declaration_source: str,
        captured_at: str,
        capture_kind: str,
        form: Optional[str] = None,
        filing_date: Optional[str] = None,
        report_date: Optional[str] = None,
        conformed_period_of_report: Optional[str] = None,
        public_document_count: Optional[int] = None,
        is_xbrl: Optional[int] = None,
        primary_document: Optional[str] = None,
        declared_at: Optional[str] = None,
    ) -> str:
        """
        Record one source's assertion about a filing.

        `declaration_id` comes from `sec_provenance.filing_declaration_id` and is
        a digest of the asserted metadata, so the same assertion is a no-op and a
        changed assertion is a second row. The earlier row is never amended, and
        no precedence between sources is stored: which one a reader trusts is a
        read-time decision the methodology has not made.
        """
        _require("declaration_source", declaration_source, DECLARATION_SOURCES)
        _require("capture_kind", capture_kind, CAPTURE_KINDS)
        existing = self.connection.execute(
            "SELECT 1 FROM filing_declarations WHERE declaration_id = ?",
            (declaration_id,),
        ).fetchone()
        if existing is not None:
            return declaration_id
        self.connection.execute(
            "INSERT INTO filing_declarations (declaration_id, asset_id,"
            " accession, declaration_source, form, filing_date, report_date,"
            " conformed_period_of_report, public_document_count, is_xbrl,"
            " primary_document, declared_at, captured_at, capture_kind)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (declaration_id, asset_id, accession, declaration_source, form,
             filing_date, report_date, conformed_period_of_report,
             public_document_count, is_xbrl, primary_document, declared_at,
             captured_at, capture_kind),
        )
        self.connection.commit()
        return declaration_id

    def record_filing_item_declaration(
        self,
        declaration_id: str,
        asset_id: str,
        accession: str,
        declaration_source: str,
        raw_items_text: str,
        captured_at: str,
        capture_kind: str,
        declared_at: Optional[str] = None,
        declared_item_count: Optional[int] = None,
    ) -> str:
        """
        Record one source's verbatim item declaration.

        `raw_items_text` is stored unsplit. Splitting it into rows is a separate
        step (`record_filing_item`), which keeps a changed parse from silently
        discarding an item: the declaration is the source's assertion and the
        items are this archive's reading of it.
        """
        _require("declaration_source", declaration_source, ITEM_DECLARATION_SOURCES)
        _require("capture_kind", capture_kind, CAPTURE_KINDS)
        existing = self.connection.execute(
            "SELECT 1 FROM filing_item_declarations WHERE declaration_id = ?",
            (declaration_id,),
        ).fetchone()
        if existing is not None:
            return declaration_id
        self.connection.execute(
            "INSERT INTO filing_item_declarations (declaration_id, asset_id,"
            " accession, declaration_source, raw_items_text,"
            " declared_item_count, declared_at, captured_at, capture_kind)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (declaration_id, asset_id, accession, declaration_source,
             raw_items_text, declared_item_count, declared_at, captured_at,
             capture_kind),
        )
        self.connection.commit()
        return declaration_id

    def record_filing_item(
        self,
        item_id: str,
        declaration_id: str,
        item_ordinal: int,
        item_code: str,
        captured_at: str,
        item_title: Optional[str] = None,
        title_source: Optional[str] = None,
    ) -> str:
        """
        Record one parsed item inside one declaration.

        The ordinal is declaration-scoped. Two sources may both declare item
        `2.02` at ordinal 1 and those are two rows, which is why the identity
        carries the declaration rather than the accession.
        """
        existing = self.connection.execute(
            "SELECT 1 FROM filing_items WHERE item_id = ?", (item_id,)
        ).fetchone()
        if existing is not None:
            return item_id
        self.connection.execute(
            "INSERT INTO filing_items (item_id, declaration_id, item_ordinal,"
            " item_code, item_title, title_source, captured_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (item_id, declaration_id, item_ordinal, item_code, item_title,
             title_source, captured_at),
        )
        self.connection.commit()
        return item_id

    def record_filing_document_declaration(
        self,
        declaration_id: str,
        asset_id: str,
        accession: str,
        manifest_source: str,
        source_ordinal: int,
        captured_at: str,
        capture_kind: str,
        filename: Optional[str] = None,
        sec_document_type: Optional[str] = None,
        mime_type: Optional[str] = None,
        byte_size: Optional[int] = None,
        description: Optional[str] = None,
        last_modified: Optional[str] = None,
    ) -> str:
        """
        Record one entry of one manifest.

        Both manifests are recorded and neither is merged. `source_ordinal` is
        the position inside `manifest_source` and is not comparable between
        manifests; `sec_document_type` and `mime_type` are separate columns
        because they are separate vocabularies from separate resources.

        `last_modified` is stored for the audit trail but is not part of the
        identity, so a re-read whose only change is an mtime stays a no-op.
        """
        _require("manifest_source", manifest_source, MANIFEST_SOURCES)
        _require("capture_kind", capture_kind, CAPTURE_KINDS)
        existing = self.connection.execute(
            "SELECT 1 FROM filing_document_declarations WHERE declaration_id = ?",
            (declaration_id,),
        ).fetchone()
        if existing is not None:
            return declaration_id
        self.connection.execute(
            "INSERT INTO filing_document_declarations (declaration_id,"
            " asset_id, accession, manifest_source, source_ordinal, filename,"
            " sec_document_type, mime_type, byte_size, description,"
            " last_modified, captured_at, capture_kind)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (declaration_id, asset_id, accession, manifest_source,
             source_ordinal, filename, sec_document_type, mime_type, byte_size,
             description, last_modified, captured_at, capture_kind),
        )
        self.connection.commit()
        return declaration_id

    def record_filing_document(
        self,
        asset_id: str,
        accession: str,
        filename: str,
        first_declared_at: Optional[str] = None,
    ) -> bool:
        """
        Record the existence of a document inside a filing.

        Identity only. This row carries no source-asserted attribute -- no
        `document_type`, no `mime_type`, no ordinal, no capture state -- so a
        declaration can never overwrite it, and nothing it says can be
        contradicted by a later read of a different resource.

        Only a directory-manifest declaration mints this row, and the database
        says so: `filing_documents_identity_is_declared` aborts unless a
        `EDGAR_FILING_DIRECTORY_INDEX_JSON` declaration of this filename exists,
        and `filing_documents_identity_is_unambiguous` aborts when the directory
        manifest declared the filename more than once. A filename declared twice
        therefore yields two surviving declarations and no identity row, which
        is the unresolved state rather than a merge.
        """
        existing = self.connection.execute(
            "SELECT 1 FROM filing_documents"
            " WHERE asset_id = ? AND accession = ? AND filename = ?",
            (asset_id, accession, filename),
        ).fetchone()
        if existing is not None:
            return False
        self.connection.execute(
            "INSERT INTO filing_documents (asset_id, accession, filename,"
            " first_declared_at) VALUES (?, ?, ?, ?)",
            (asset_id, accession, filename, first_declared_at),
        )
        self.connection.commit()
        return True

    def record_filing_document_capture(
        self,
        asset_id: str,
        accession: str,
        filename: str,
        document_id: str,
        acquisition_class: str,
        captured_at: str,
        capture_kind: str,
    ) -> bool:
        """
        Link one captured byte sequence to one document of one filing.

        The key is the content identity, not a digest: `(asset_id, accession,
        filename, document_id)`. Re-fetching identical bytes resolves to the same
        `document_id` -- `source_documents.content_hash` is UNIQUE and
        `document_id` derives from it -- so the retry is a no-op, while re-fetched
        bytes are a different `document_id` and therefore a second row with the
        first one retained.

        Both prerequisites are enforced rather than assumed: the composite
        foreign key requires the `filing_documents` row, and `document_id`
        requires the `source_documents` row.
        """
        _require("acquisition_class", acquisition_class, ACQUISITION_CLASSES)
        _require("capture_kind", capture_kind, CAPTURE_KINDS)
        existing = self.connection.execute(
            "SELECT 1 FROM filing_document_captures"
            " WHERE asset_id = ? AND accession = ? AND filename = ?"
            " AND document_id = ?",
            (asset_id, accession, filename, document_id),
        ).fetchone()
        if existing is not None:
            return False
        self.connection.execute(
            "INSERT INTO filing_document_captures (asset_id, accession,"
            " filename, document_id, acquisition_class, captured_at,"
            " capture_kind) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (asset_id, accession, filename, document_id, acquisition_class,
             captured_at, capture_kind),
        )
        self.connection.commit()
        return True

    def record_filing_document_statement(
        self,
        statement_id: str,
        statement_identity: str,
        asset_id: str,
        accession: str,
        filename: str,
        document_id: str,
        statement_kind: str,
        quote_locator: str,
        quote_text: str,
        extraction_method: str,
        extracted_at: str,
        capture_kind: str,
        applies_to_document_type: Optional[str] = None,
        applies_to_filing_item_code: Optional[str] = None,
    ) -> str:
        """
        Record one verbatim quotation, bound to one captured byte sequence.

        `statement_id` is a digest over the capture and the locator, so a second
        capture of the same document yields a different statement and leaves the
        first alone.

        A re-extraction that produces the same words is a no-op here. A
        re-extraction that produces *different* words from the same capture, kind
        and locator is a contradiction, and it is not this writer's call to
        absorb it: the pre-check below lets the write proceed to the database so
        that `filing_document_statements_extraction_consistent` refuses it with a
        message naming the non-determinism. That trigger is the authority, and
        this writer deliberately does not reimplement the rule -- it only avoids
        raising a primary-key violation for a genuinely idempotent repeat.
        """
        _require("statement_kind", statement_kind, STATEMENT_KINDS)
        _require("extraction_method", extraction_method, EXTRACTION_METHODS)
        _require("capture_kind", capture_kind, CAPTURE_KINDS)
        existing = self.connection.execute(
            "SELECT quote_text, extraction_method FROM"
            " filing_document_statements WHERE statement_id = ?",
            (statement_id,),
        ).fetchone()
        if existing is not None and (
            existing["quote_text"] == quote_text
            and existing["extraction_method"] == extraction_method
        ):
            return statement_id
        self.connection.execute(
            "INSERT INTO filing_document_statements (statement_id,"
            " statement_identity, asset_id, accession, filename, document_id,"
            " statement_kind, quote_locator, quote_text, extraction_method,"
            " extracted_at, capture_kind, applies_to_document_type,"
            " applies_to_filing_item_code)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (statement_id, statement_identity, asset_id, accession, filename,
             document_id, statement_kind, quote_locator, quote_text,
             extraction_method, extracted_at, capture_kind,
             applies_to_document_type, applies_to_filing_item_code),
        )
        self.connection.commit()
        return statement_id

    def record_filing_document_fact_occurrence(
        self,
        document_fact_id: str,
        document_fact_identity: str,
        asset_id: str,
        accession: str,
        filename: str,
        document_id: str,
        provider: str,
        taxonomy: str,
        tag: str,
        context_ref: str,
        unit_ref: str,
        entity_identifier: str,
        entity_scheme: Optional[str],
        period_kind: str,
        period_start: Optional[str],
        period_end: Optional[str],
        dimensions_json: str,
        unit_measures_json: str,
        value_text: str,
        resolved_value: float,
        sign: Optional[str],
        scale: Optional[str],
        format_: Optional[str],
        decimals: Optional[str],
        language: Optional[str],
        locators_json: str,
        context_locator_json: str,
        unit_locator_json: str,
        captured_at: str,
        capture_kind: str,
    ) -> str:
        """
        Record one logical fact asserted by one captured byte sequence.

        `document_fact_id` is a digest over the eight-field preimage, so a second
        capture of changed bytes yields a different occurrence and leaves the
        first alone, and one value split across several `ix:continuation` ranges
        is still one occurrence because no locator is in the key.

        Idempotency is the same read-then-write `record_filing_document_statement`
        uses: an occurrence already held with the same evidence returns. A repeat
        that produces *different* evidence for the same identity is a
        non-deterministic parse, and this writer deliberately does not absorb it
        -- the pre-check lets the write reach the database so that
        `fact_occurrences_extraction_consistent` refuses it with a message
        naming the non-determinism. That trigger is the authority.
        """
        _require("capture_kind", capture_kind, CAPTURE_KINDS)
        existing = self.connection.execute(
            "SELECT value_text, resolved_value FROM"
            " filing_document_fact_occurrences WHERE document_fact_id = ?",
            (document_fact_id,),
        ).fetchone()
        if existing is not None and (
            existing["value_text"] == value_text
            and existing["resolved_value"] == resolved_value
        ):
            return document_fact_id
        self.connection.execute(
            "INSERT INTO filing_document_fact_occurrences (document_fact_id,"
            " document_fact_identity, asset_id, accession, filename,"
            " document_id, provider, taxonomy, tag, context_ref, unit_ref,"
            " entity_identifier, entity_scheme, period_kind, period_start,"
            " period_end, dimensions_json, unit_measures_json, value_text,"
            " resolved_value, sign, scale, format_, decimals, language,"
            " locators_json, context_locator_json, unit_locator_json,"
            " captured_at, capture_kind)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,"
            " ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (document_fact_id, document_fact_identity, asset_id, accession,
             filename, document_id, provider, taxonomy, tag, context_ref,
             unit_ref, entity_identifier, entity_scheme, period_kind,
             period_start, period_end, dimensions_json, unit_measures_json,
             value_text, resolved_value, sign, scale, format_, decimals,
             language, locators_json, context_locator_json, unit_locator_json,
             captured_at, capture_kind),
        )
        self.connection.commit()
        return document_fact_id

    def record_filing_acceptance(
        self,
        declaration_id: str,
        asset_id: str,
        accession: str,
        acceptance_source: str,
        acceptance_precision: str,
        captured_at: str,
        capture_kind: str,
        acceptance_datetime: Optional[str] = None,
        raw_value: Optional[str] = None,
    ) -> str:
        """
        Record one acceptance instant as one producer declared it.

        `acceptance_source` is checked against a two-member vocabulary, so a
        fact's filed date raises here rather than being stored as if it were a
        dissemination instant. That fact's date stays on
        `observations.available_at_basis` as `FILED_AS_OF_DATE`, which is a
        different statement about a different object and lives in a different
        relation.

        Both producers persist for one filing. The SGML header publishes the ET
        wall clock and the Submissions API publishes the same instant as UTC;
        neither overwrites the other, and no precedence column exists because the
        methodology has not chosen one.

        `acceptance_precision = 'NONE'` is the "consulted, declared nothing" state
        and requires a NULL `acceptance_datetime`. No row at all means the
        producer was never consulted.
        """
        _require("acceptance_source", acceptance_source, ACCEPTANCE_SOURCES)
        _require("acceptance_precision", acceptance_precision, ACCEPTANCE_PRECISIONS)
        _require("capture_kind", capture_kind, CAPTURE_KINDS)
        existing = self.connection.execute(
            "SELECT 1 FROM filing_acceptances WHERE declaration_id = ?",
            (declaration_id,),
        ).fetchone()
        if existing is not None:
            return declaration_id
        self.connection.execute(
            "INSERT INTO filing_acceptances (declaration_id, asset_id,"
            " accession, acceptance_source, acceptance_datetime,"
            " acceptance_precision, raw_value, captured_at, capture_kind)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (declaration_id, asset_id, accession, acceptance_source,
             acceptance_datetime, acceptance_precision, raw_value, captured_at,
             capture_kind),
        )
        self.connection.commit()
        return declaration_id

    def record_fiscal_calendar_declaration(
        self,
        declaration_id: str,
        asset_id: str,
        fiscal_year_end_mmdd: str,
        declaration_source: str,
        captured_at: str,
        capture_kind: str,
        declaring_accession: Optional[str] = None,
        observed_filing_date: Optional[str] = None,
    ) -> str:
        """
        Record one declared fiscal year end.

        There is no `fiscal_year` argument and no such column: Contract section
        K.4 leaves per-fiscal-year resolution open, and taking a fiscal year here
        would freeze an undecided semantic into the schema. `declaring_accession`
        and `observed_filing_date` keep the context a later resolution would need,
        so deciding it later needs no migration.
        """
        _require(
            "declaration_source", declaration_source,
            FISCAL_CALENDAR_DECLARATION_SOURCES,
        )
        _require("capture_kind", capture_kind, CAPTURE_KINDS)
        existing = self.connection.execute(
            "SELECT 1 FROM issuer_fiscal_calendar_declarations"
            " WHERE declaration_id = ?", (declaration_id,)
        ).fetchone()
        if existing is not None:
            return declaration_id
        self.connection.execute(
            "INSERT INTO issuer_fiscal_calendar_declarations (declaration_id,"
            " asset_id, fiscal_year_end_mmdd, declaration_source,"
            " declaring_accession, observed_filing_date, captured_at,"
            " capture_kind) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (declaration_id, asset_id, fiscal_year_end_mmdd,
             declaration_source, declaring_accession, observed_filing_date,
             captured_at, capture_kind),
        )
        self.connection.commit()
        return declaration_id

    def record_observation_filing_document(
        self,
        observation_id: str,
        asset_id: str,
        accession: str,
        filename: str,
        captured_at: str,
        capture_kind: str,
    ) -> bool:
        """
        Link one observation to the one document it was read from.

        The link is always explicit. Nothing here derives a document from an
        accession, and in particular nothing treats an 8-K accession as naming an
        `EX-99.1`: measured on a real filing, the diluted-EPS facts carried by one
        8-K accession came from an `EX-101.INS` instance while its `EX-99.1`
        exhibit contained no inline XBRL at all. An observation with no row here
        is a complete, honest state -- unlinked -- rather than a gap to be filled
        by a guess.

        This writer has no write path to `observations` at all. It reads an
        observation's id and writes only this relation.
        """
        _require("capture_kind", capture_kind, CAPTURE_KINDS)
        existing = self.connection.execute(
            "SELECT 1 FROM observation_filing_documents"
            " WHERE observation_id = ? AND asset_id = ? AND accession = ?"
            " AND filename = ?",
            (observation_id, asset_id, accession, filename),
        ).fetchone()
        if existing is not None:
            return False
        self.connection.execute(
            "INSERT INTO observation_filing_documents (observation_id,"
            " asset_id, accession, filename, captured_at, capture_kind)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (observation_id, asset_id, accession, filename, captured_at,
             capture_kind),
        )
        self.connection.commit()
        return True

    def documents_summary(self) -> List[Dict[str, Any]]:
        """One row per captured document, for reporting on capture coverage."""
        return [
            dict(row)
            for row in self.connection.execute(
                "SELECT content_hash, canonical_uri, document_type, provider,"
                " byte_size, fetched_at, content_encoding FROM source_documents"
                " ORDER BY document_type, byte_size DESC"
            )
        ]

    def captured_bytes(self) -> int:
        return int(
            self.connection.execute(
                "SELECT COALESCE(SUM(byte_size), 0) AS total FROM source_documents"
            ).fetchone()["total"]
        )

    def documents_with_content(self) -> int:
        return int(
            self.connection.execute(
                "SELECT COUNT(*) AS n FROM source_documents"
                " WHERE content IS NOT NULL"
            ).fetchone()["n"]
        )

    def document_id_for(self, reference: str) -> Optional[str]:
        """
        Resolve a document reference to its id.

        Accepts either the content hash or the id, because a caller that just
        captured a document naturally holds whichever `record_source_document`
        returned, and making it look the other one up is a pointless trap.
        """
        row = self.connection.execute(
            "SELECT document_id FROM source_documents"
            " WHERE content_hash = ? OR document_id = ?",
            (reference, reference),
        ).fetchone()
        return row["document_id"] if row is not None else None

    def documents_for(self, observation_id: str) -> List[str]:
        return [
            row["document_id"]
            for row in self.connection.execute(
                "SELECT document_id FROM observation_sources"
                " WHERE observation_id = ? ORDER BY document_id",
                (observation_id,),
            )
        ]

    def dangling_document_references(self) -> List[str]:
        """
        Documents a stored observation points at but that do not exist.

        A test asserts this stays empty. A dangling reference looks like
        evidence and is not, which is worse than an absent capture.
        """
        return [
            row["document_id"]
            for row in self.connection.execute(
                "SELECT DISTINCT os.document_id FROM observation_sources os"
                " LEFT JOIN source_documents d ON d.document_id ="
                " os.document_id WHERE d.document_id IS NULL"
            )
        ]

    # -- observations -----------------------------------------------------

    def record_observation(
        self,
        asset: str,
        observation: Observation,
        availability_class: Optional[str] = None,
        first_archived_at: Optional[str] = None,
        replay_eligible_from: Optional[str] = None,
        document_hashes: Sequence[str] = (),
        accession: Optional[str] = None,
        filing: Optional[FilingRef] = None,
    ) -> str:
        """
        Append one observation.

        `replay_eligible_from` is never derived from `retrieved_at`. It is the
        source's own `available_at` for a declared observation, the archival
        moment for a first-seen one, and NULL for an undeclared one, which is
        why that last case is permanently ineligible rather than merely late.
        """
        archived_at = first_archived_at or utc_now()
        klass = availability_class or self._class_for(
            observation, archived_at
        )
        if replay_eligible_from is None:
            replay_eligible_from = self._eligibility_for(
                observation, klass, archived_at
            )

        content_hash = observation_content_hash(observation)
        existing = self.connection.execute(
            "SELECT observation_id FROM observations WHERE content_hash = ?",
            (content_hash,),
        ).fetchone()
        if existing is not None:
            self._link_documents(
                existing["observation_id"],
                document_hashes,
                _accession_of(observation),
            )
            self._class_cache[observation.observation_id] = klass
            return existing["observation_id"]

        asset_id = self.record_asset(asset)
        lineage_id = self._lineage_for(asset_id, observation)
        row_id = "obsarch_" + hashlib.sha256(
            content_hash.encode("utf-8")
        ).hexdigest()[:24]

        columns = (
            "observation_id", "contract_id", "asset_id", "lineage_id", "metric",
            "provider", "source_type", "source_url", "concept", "value_json",
            "unit", "currency", "currency_basis", "period_start", "period_end",
            "as_of", "available_at", "available_at_basis", "availability_class",
            "retrieved_at", "first_archived_at", "replay_eligible_from",
            "definition", "methodology", "status", "status_reasons_json",
            "inputs_json", "observation_count", "basis_json", "raw_json",
            "content_hash",
        )
        values = (
            row_id,
            observation.observation_id,
            asset_id,
            lineage_id,
            observation.metric,
            observation.provider,
            observation.source_type,
            observation.source_url,
            _concept_of(observation),
            _canonical(observation.value),
            observation.unit,
            observation.currency,
            observation.currency_basis,
            observation.period_start,
            observation.period_end,
            observation.as_of,
            observation.available_at,
            observation.available_at_basis,
            klass,
            observation.retrieved_at,
            archived_at,
            replay_eligible_from,
            observation.definition,
            observation.methodology,
            observation.status.value,
            _canonical(list(observation.status_reasons)),
            _canonical(list(observation.inputs)),
            observation.observation_count,
            _canonical(observation.basis) if observation.basis else None,
            _canonical(observation.raw) if observation.raw is not None else None,
            content_hash,
        )
        if filing is not None:
            # The filing identity is part of the row, not a correction to it. The
            # archive rejects every UPDATE, which is correct: an observation that
            # could be amended after the fact would not be evidence of what was
            # known when it was written.
            columns += (
                "taxonomy", "accession", "form", "fiscal_year", "fiscal_period",
                "statement", "instant", "source_fact_id", "source_concept_ref",
            )
            values += (
                filing.taxonomy,
                filing.accession or _accession_of(observation),
                filing.form,
                filing.fiscal_year,
                filing.fiscal_period,
                filing.statement,
                filing.instant,
                filing.source_fact_id,
                filing.source_concept,
            )
        placeholders = ", ".join("?" for _ in columns)
        self.connection.execute(
            f"INSERT INTO observations ({', '.join(columns)})"
            f" VALUES ({placeholders})",
            values,
        )
        self._link_documents(row_id, document_hashes, _accession_of(observation))
        self.connection.commit()
        self._class_cache[observation.observation_id] = klass
        return row_id

    def _class_for(self, observation: Observation, archived_at: str) -> str:
        if observation.available_at and (
            observation.available_at_basis in DECLARED_BASES
        ):
            return SOURCE_DECLARED
        if self.archive_unknown_availability:
            return ARCHIVE_FIRST_SEEN
        return UNDECLARED

    def _eligibility_for(
        self,
        observation: Observation,
        klass: str,
        archived_at: str,
    ) -> Optional[str]:
        """
        The first instant from which this fact may be used in a replay.

        Three cases, decided by what the source actually declared, and never by
        whether a value happens to be populated.

            an instant the source published   that instant
            a date the source published       the moment that date is over
            nothing declared                   never eligible

        The middle case is the one 2.14 added. A `FILED_AS_OF_DATE` fact carries
        a date, so it is replayable from the day *after* its declared date and
        not before. Using it from midnight would assert that EDGAR disseminated
        the filing at 00:00; measured across the two delivery routes, that made
        6,508 of 17,043 facts replayable from a moment before the filer
        published them. The evidence is real and it is not discarded ??a date
        proves publication happened on that day, so the fact becomes usable once
        the day is provably elapsed.

        `retrieved_at` is never an input. It is when this process asked, not
        when the data existed, and using it is how a backtest ends up worthless.
        """
        if klass == SOURCE_DECLARED:
            if (
                observation.available_at_basis
                == AvailabilityBasis.FILED_AS_OF_DATE.value
            ):
                return eligibility_for_declared_date(
                    observation.available_at
                )
            return observation.available_at
        if klass == ARCHIVE_FIRST_SEEN:
            return archived_at
        return None

    def _lineage_for(self, asset_id: str, observation: Observation) -> str:
        """
        Find or create the lineage for a fact about a period.

        The existence check is explicit rather than `INSERT OR IGNORE`,
        because OR IGNORE also swallows a NOT NULL or CHECK violation. That
        turns a data defect into a missing row, which then surfaces as a
        confusing foreign-key error somewhere else entirely.
        """
        lineage_id = _lineage_id(asset_id, observation)
        existing = self.connection.execute(
            "SELECT lineage_id FROM observation_lineage WHERE lineage_id = ?",
            (lineage_id,),
        ).fetchone()
        if existing is not None:
            return lineage_id
        self.connection.execute(
            "INSERT INTO observation_lineage (lineage_id, asset_id, metric,"
            " concept, period_start, period_end, created_at, note)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                lineage_id,
                asset_id,
                observation.metric,
                _concept_of(observation),
                observation.period_start,
                observation.period_end,
                utc_now(),
                "one fact about a period, however many times it was restated",
            ),
        )
        return lineage_id

    def _link_documents(
        self,
        row_id: str,
        document_hashes: Sequence[str],
        accession: Optional[str] = None,
    ) -> None:
        """
        Attach captured documents to an observation.

        The same fact seen in several filings gets one row and several links,
        so the value is not duplicated and neither is the filing that saw it.
        A hash that was never captured is refused rather than skipped: a
        dangling reference looks like evidence and is not.
        """
        for content_hash in document_hashes:
            document_id = self.document_id_for(content_hash)
            if document_id is None:
                raise ArchiveError(
                    f"observation {row_id} references source document "
                    f"{content_hash}, which has not been captured. A dangling "
                    "reference looks like evidence and is not."
                )
            self.connection.execute(
                "INSERT OR IGNORE INTO observation_sources (observation_id,"
                " document_id, accession) VALUES (?, ?, ?)",
                (row_id, document_id, accession),
            )

    def class_of(self, observation_id: str) -> Optional[str]:
        """
        The availability class recorded for an observation.

        Accepts either the contract id or the archive's physical row id, because
        a replay holds the former and a caller auditing the table has the
        latter.
        """
        if observation_id in self._class_cache:
            return self._class_cache[observation_id]
        row = self.connection.execute(
            "SELECT availability_class FROM observations WHERE"
            " contract_id = ? OR observation_id = ?",
            (observation_id, observation_id),
        ).fetchone()
        return row["availability_class"] if row is not None else None

    def record_observation_with(
        self,
        asset: str,
        observation: Observation,
        **kwargs: Any,
    ) -> str:
        return self.record_observation(asset, observation, **kwargs)

    # -- reads ------------------------------------------------------------

    def _row_to_observation(self, row: sqlite3.Row) -> Observation:
        raw = json.loads(row["raw_json"]) if row["raw_json"] else None
        status = ValidationStatus.UNVERIFIABLE
        if row["status"]:
            try:
                status = ValidationStatus(row["status"])
            except ValueError:
                status = ValidationStatus.UNVERIFIABLE
        return Observation(
            observation_id=str(row["contract_id"]),
            metric=row["metric"],
            value=json.loads(row["value_json"]),
            unit=row["unit"],
            currency=row["currency"],
            currency_basis=row["currency_basis"],
            period_start=row["period_start"],
            period_end=row["period_end"],
            as_of=row["as_of"],
            available_at=row["available_at"],
            available_at_basis=row["available_at_basis"],
            provider=row["provider"],
            source_type=row["source_type"],
            source_url=row["source_url"],
            definition=row["definition"] or "",
            methodology=row["methodology"] or "",
            retrieved_at=row["retrieved_at"],
            raw=raw,
            observation_count=row["observation_count"],
            status=status,
            status_reasons=tuple(
                json.loads(row["status_reasons_json"])
                if row["status_reasons_json"]
                else ()
            ),
            inputs=tuple(
                json.loads(row["inputs_json"]) if row["inputs_json"] else ()
            ),
            basis=json.loads(row["basis_json"]) if row["basis_json"] else None,
        )

    # -- reader integration for the knowledge-state axis (2.63) --------------
    #
    # The original observation is the BASELINE interpretation of its source
    # fact. The interpretation table holds only later changes in what ST-EVA
    # understood, so a missing interpretation at a cutoff must never make a
    # source fact disappear -- it means the baseline still stands. That is the
    # whole point of 2.62's layout, and it is why this is an overlay rather than
    # a replacement.
    #
    # Only three fields may be overlaid. Value, period, metric, availability,
    # contract_id, lineage_id and source_fact_id belong to the fact and are not
    # reachable from an interpretation row, so the restriction is structural
    # rather than a filter someone has to remember to apply.

    #: The only columns an interpretation is permitted to contribute.
    INTERPRETATION_OVERLAY_FIELDS = ("unit", "currency", "currency_basis")

    def knowledge_state_available(self) -> bool:
        """
        Whether this archive can answer a knowledge-state question at all.

        Distinct from "no applicable interpretation". An archive predating 2.61
        has no `interpretations` table, and for that archive the question is
        unanswerable rather than answered with nothing. Collapsing the two would
        let a legacy archive look like an archive that knows the reading was
        always wrong.
        """
        return self._has_interpretations()

    def interpretation_for(self, source_fact_id: str, cutoff: str
                           ) -> Tuple[Optional[Dict[str, Any]], str]:
        """
        The interpretation effective at `cutoff`, and how confident that is.

        Returns `(row_or_None, status)` where status is one of

            "APPLIED"                  an interpretation was found and overlaid
            "BASELINE"                 none applies; the observation stands
            "UNAVAILABLE_LEGACY"       this archive has no interpretations table

        The three are separate because they mean different things to a caller and
        the difference is invisible if they are collapsed into a single None.
        """
        if not self._has_interpretations():
            return None, "UNAVAILABLE_LEGACY"
        if not source_fact_id:
            return None, "NO_SOURCE_FACT"
        axis = knowledge_axis_for(self.connection, source_fact_id)
        if axis is None:
            return None, "NO_SOURCE_FACT"
        chosen = axis.effective_at(cutoff or LATEST_KNOWLEDGE)
        if chosen is None:
            return None, "BASELINE"
        row = self.connection.execute(
            "SELECT * FROM interpretations WHERE identity = ?",
            (chosen.identity,)).fetchone()
        if row is None:
            return None, "BASELINE"
        return dict(row), "APPLIED"

    def _overlay_interpretation(self, observation: Observation, cutoff: str
                                 ) -> Tuple[Observation, str]:
        source_fact_id = self._source_fact_id_of(observation)
        if source_fact_id is None:
            # An observation with no source-fact identity cannot carry an
            # interpretation, and that is a fact about it rather than a failure.
            return observation, "NO_SOURCE_FACT"
        interpretation, status = self.interpretation_for(source_fact_id, cutoff)
        if interpretation is None:
            return observation, status
        overlay = {
            field: interpretation[field]
            for field in self.INTERPRETATION_OVERLAY_FIELDS
        }
        basis = dict(observation.basis or {})
        basis["knowledge_interpretation"] = {
            "identity": interpretation["identity"],
            "knowledge_at": interpretation["knowledge_at"],
            "applied_at_cutoff": cutoff,
        }
        return replace(observation, basis=basis, **overlay), "APPLIED"

    def _source_fact_id_of(self, observation: Observation) -> Optional[str]:
        row = self.connection.execute(
            "SELECT source_fact_id FROM observations WHERE contract_id = ?",
            (observation.observation_id,)).fetchone()
        return row["source_fact_id"] if row and row["source_fact_id"] else None

    def audit_for_source_fact(self, source_fact_id: str) -> Dict[str, Any]:
        """
        The full reading history of one source fact.

        The normal reader answers "what did ST-EVA understand at this instant";
        this answers "what has it ever understood, and when". Both are needed,
        and collapsing them would hide the original faulty reading the moment a
        correction exists.
        """
        row = self.connection.execute(
            "SELECT * FROM observations WHERE source_fact_id = ?",
            (source_fact_id,)).fetchone()
        observation = self._row_to_observation(row) if row else None
        interpretations = (self.interpretations_for_source_fact(source_fact_id)
                           if self._has_interpretations() else [])
        return {
            "source_fact_id": source_fact_id,
            "knowledge_state_available": self._has_interpretations(),
            "original_observation": (
                {"observation_id": observation.observation_id,
                 "unit": observation.unit,
                 "currency": observation.currency,
                 "currency_basis": observation.currency_basis}
                if observation else None),
            "interpretations": [
                {"interpretation_id": i["interpretation_id"],
                 "knowledge_at": i["knowledge_at"], "unit": i["unit"],
                 "currency": i["currency"],
                 "currency_basis": i["currency_basis"],
                 "supersedes": i["supersedes"]} for i in interpretations],
        }

    def observations_for(self, asset: str, cutoff: str) -> List[Observation]:
        """
        Every observation replay-eligible at `cutoff`, and nothing else.

        A `NULL` replay_eligible_from is excluded, which is what makes an
        undeclared observation permanently ineligible rather than merely late.

        The cutoff is read through `point_in_time_cutoff`, so a bare date means
        the whole of that day. Comparing the stored string directly read "as of
        2026-03-05" as midnight, which excluded a fact whose eligibility is that
        day -- and the in-memory selector, which compares dates, included it.
        Same question, two answers. A cutoff that cannot be read returns nothing,
        because returning everything for an unreadable question is the failure a
        point-in-time contract exists to prevent.

        Where two archived rows carry the same contract identifier ??a band
        restated after archival, so the canonical per-metric identifier
        collided ??the most recently eligible one is returned. That is the same
        rule `latest_knowable` applies, and the earlier row is still in the
        archive and still reachable by its own id.

        Each returned observation carries the interpretation effective at that
        cutoff, so a later correction becomes visible without the stored row ever
        being rewritten. Before its knowledge time the stored reading stands,
        which is why an interpretation table is an overlay and not a replacement.
        """
        at = point_in_time_cutoff(cutoff)
        if at is None:
            return []
        rows = self.connection.execute(
            "SELECT o.* FROM observations o JOIN assets a"
            " ON a.asset_id = o.asset_id"
            " WHERE a.ticker = ? AND o.replay_eligible_from IS NOT NULL"
            " AND o.replay_eligible_from <= ?"
            " ORDER BY o.replay_eligible_from, o.observation_id",
            (asset.upper(), at),
        ).fetchall()
        newest: Dict[str, sqlite3.Row] = {}
        for row in rows:
            newest[str(row["contract_id"])] = row
        # The overlay is applied after the per-contract collapse, so a
        # restatement and a correction are resolved independently: the collapse
        # answers "which row", the overlay answers "how was it understood".
        return [
            self._overlay_interpretation(
                self._row_to_observation(row), cutoff)[0]
            for row in newest.values()
        ]

    def all_observations(self, asset: str) -> List[Observation]:
        rows = self.connection.execute(
            "SELECT o.* FROM observations o JOIN assets a"
            " ON a.asset_id = o.asset_id WHERE a.ticker = ?"
            " ORDER BY o.first_archived_at, o.observation_id",
            (asset.upper(),),
        ).fetchall()
        return [self._row_to_observation(row) for row in rows]

    def eligibility_for(self, asset: str) -> Dict[str, str]:
        """
        The archive-side eligibility times, for observations that have no
        source-declared availability.

        This is the archive's own knowledge and is kept separate from
        `available_at`, which belongs to the source.
        """
        rows = self.connection.execute(
            "SELECT o.contract_id AS observation_id, o.replay_eligible_from"
            " FROM observations o JOIN assets a ON a.asset_id = o.asset_id"
            " WHERE a.ticker = ? AND o.availability_class = ?"
            " AND o.replay_eligible_from IS NOT NULL",
            (asset.upper(), ARCHIVE_FIRST_SEEN),
        ).fetchall()
        return {
            row["observation_id"]: row["replay_eligible_from"]
            for row in rows
        }

    def availability_classes(self, asset: str) -> Dict[str, str]:
        rows = self.connection.execute(
            "SELECT o.contract_id AS observation_id, o.availability_class"
            " FROM observations o JOIN assets a ON a.asset_id = o.asset_id"
            " WHERE a.ticker = ?",
            (asset.upper(),),
        ).fetchall()
        return {
            row["observation_id"]: row["availability_class"]
            for row in rows
        }

    def asset_metadata(self, asset: str) -> Dict[str, Any]:
        row = self.connection.execute(
            "SELECT ticker, cik, name, sec_entity_name, exchange, currency"
            " FROM assets WHERE ticker = ?",
            (asset.upper(),),
        ).fetchone()
        if row is None:
            return {
                "ticker": asset,
                "cik": None,
                "name": None,
                "sec_entity_name": None,
                "exchange": None,
                "currency": None,
            }
        return dict(row)

    def lineage_for(self, asset: str, metric: str) -> List[Dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT l.lineage_id, l.concept, l.period_start, l.period_end,"
            " COUNT(o.observation_id) AS versions"
            " FROM observation_lineage l"
            " JOIN assets a ON a.asset_id = l.asset_id"
            " LEFT JOIN observations o ON o.lineage_id = l.lineage_id"
            " WHERE a.ticker = ? AND l.metric = ?"
            " GROUP BY l.lineage_id ORDER BY l.period_end DESC",
            (asset.upper(), metric),
        ).fetchall()
        return [dict(row) for row in rows]

    # -- contexts ---------------------------------------------------------

    def record_context(
        self,
        asset: str,
        document: Dict[str, Any],
        replay_fidelity: str = SOURCE_DECLARED,
        observations: Sequence[Observation] = (),
    ) -> str:
        """
        Store a context snapshot, deduplicated by `context_id`.

        A context is a statement about knowledge, so re-archiving the same
        statement adds nothing.
        """
        context_id = document["context_id"]
        existing = self.connection.execute(
            "SELECT context_id FROM context_snapshots WHERE context_id = ?",
            (context_id,),
        ).fetchone()
        if existing is not None:
            return context_id

        asset_id = self.record_asset(
            asset,
            name=document.get("asset", {}).get("company_name"),
            exchange=document.get("asset", {}).get("exchange"),
            currency=document.get("asset", {}).get("currency"),
        )
        identifiers = document.get("asset", {}).get("identifiers") or {}
        if identifiers.get("cik") or identifiers.get("sec_entity_name"):
            self.connection.execute(
                "UPDATE assets SET cik = COALESCE(cik, ?),"
                " sec_entity_name = COALESCE(sec_entity_name, ?)"
                " WHERE asset_id = ?",
                (
                    identifiers.get("cik"),
                    identifiers.get("sec_entity_name"),
                    asset_id,
                ),
            )

        self.connection.execute(
            "INSERT INTO context_snapshots (context_id, asset_id, as_of,"
            " knowledge_cutoff, replay_fidelity, built_from_json,"
            " document_json, document_hash, supersedes, archived_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                context_id,
                asset_id,
                document.get("as_of"),
                document.get("knowledge_cutoff"),
                replay_fidelity,
                _canonical(document.get("built_from")),
                _canonical(document),
                document_hash(document),
                document.get("supersedes"),
                utc_now(),
            ),
        )

        provenance = document.get("provenance") or {}
        for ref, derivation in (provenance.get("derivations") or {}).items():
            operation = derivation.get("operation") or {}
            self.connection.execute(
                "INSERT OR REPLACE INTO derived_values (context_id, ref,"
                " operation_json, expression, value_json, unit, deterministic,"
                " depends_on_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    context_id,
                    ref,
                    _canonical(operation),
                    derivation.get("expression"),
                    _canonical(
                        (document.get("derived", {}).get(ref.split(":")[-1], {}) or {})
                        .get("figure", {})
                        .get("value")
                    ),
                    (document.get("derived", {}).get(ref.split(":")[-1], {}) or {})
                    .get("figure", {})
                    .get("unit"),
                    1 if derivation.get("deterministic") else 0,
                    _canonical(derivation.get("depends_on") or []),
                ),
            )

        self.connection.commit()
        return context_id

    def record_validation(self, record: Dict[str, Any]) -> str:
        record_id = "val_" + hashlib.sha256(
            _canonical(record).encode("utf-8")
        ).hexdigest()[:24]
        # A caller holds the contract's observation id, while the table keys on
        # the physical row id. Resolving here keeps that translation in one
        # place instead of every caller having to know about it.
        subject = record.get("observation_id")
        row_id = None
        if subject:
            row = self.connection.execute(
                "SELECT observation_id FROM observations"
                " WHERE contract_id = ? OR observation_id = ?",
                (subject, subject),
            ).fetchone()
            row_id = row["observation_id"] if row is not None else None
        self.connection.execute(
            "INSERT OR IGNORE INTO validation_records (record_id,"
            " observation_id, kind, status, reasons_json,"
            " comparison_basis_json, tolerance_json, explanation,"
            " references_json, value_snapshot_json, checked_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record_id,
                row_id,
                record.get("kind", "single_source"),
                record.get("status", ""),
                _canonical(record.get("reasons") or []),
                _canonical(record.get("comparison_basis"))
                if record.get("comparison_basis")
                else None,
                _canonical(record.get("tolerance"))
                if record.get("tolerance")
                else None,
                record.get("explanation"),
                _canonical(record.get("references") or []),
                _canonical(record.get("value_snapshot"))
                if record.get("value_snapshot") is not None
                else None,
                record.get("checked_at") or utc_now(),
            ),
        )
        self.connection.commit()
        return record_id

    def context_at(
        self,
        asset: str,
        as_of: str,
    ) -> Optional[Dict[str, Any]]:
        """
        The archived context for an instant.

        Exact match only. Walking backwards to a nearby instant would answer a
        different question than the one asked, and reporting it as the answer
        would be the quiet substitution this phase exists to prevent.
        """
        row = self.connection.execute(
            "SELECT c.document_json FROM context_snapshots c"
            " JOIN assets a ON a.asset_id = c.asset_id"
            " WHERE a.ticker = ? AND c.as_of = ? ORDER BY c.archived_at LIMIT 1",
            (asset.upper(), as_of),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["document_json"])

    def context_hashes(self, asset: str) -> List[Dict[str, Any]]:
        return [
            dict(row)
            for row in self.connection.execute(
                "SELECT c.context_id, c.as_of, c.knowledge_cutoff,"
                " c.replay_fidelity, c.document_hash FROM context_snapshots c"
                " JOIN assets a ON a.asset_id = c.asset_id"
                " WHERE a.ticker = ? ORDER BY c.as_of",
                (asset.upper(),),
            )
        ]

    def lineage_count(self) -> int:
        return int(
            self.connection.execute(
                "SELECT COUNT(*) AS n FROM observation_lineage"
            ).fetchone()["n"]
        )

    def observation_count(self) -> int:
        return int(
            self.connection.execute(
                "SELECT COUNT(*) AS n FROM observations"
            ).fetchone()["n"]
        )

    # -- interpretations (knowledge-state axis, 2.61) ----------------------
    #
    # Persistence for the axis validated in 2.59 and designed in 2.60. These
    # operations are deliberately NOT wired into any existing reader:
    # `observations_for` and `get_metric_history` are untouched, so current
    # point-in-time behaviour is unchanged until a reader is deliberately pointed
    # at this layer.
    #
    # The ordering, same-fact, backwards-only and no-cycles rules are enforced
    # by the 2.59 domain validators, not by SQLite. The schema contributes
    # NOT NULL, the foreign key, the unique identity and append-only; the rest is
    # cross-row and cannot be expressed as a CHECK constraint. The validator
    # logic lives in one place -- `knowledge_axis` -- and is replayed here over
    # the stored series rather than reimplemented.

    def _has_table(self, name: str) -> bool:
        return self.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (name,)).fetchone() is not None

    def _has_interpretations(self) -> bool:
        """
        Whether this archive carries the 2.61 table at all.

        An archive built before 2.61 must still open and must still serve every
        existing call. The same defensive shape `resolve_metric` uses for an
        archive that predates the supersession table: report the absence rather
        than raise, so an older archive is merely older and not broken.
        """
        return self._has_table("interpretations")

    # -- admissions -------------------------------------------------------

    def _asset_id_for_ticker(self, asset: str) -> Optional[str]:
        """
        The asset id for a ticker, or None if the archive has never seen it.

        The same join `observations_for` uses, so an admission is filed against
        the same asset row an observation would be. Recording against an unknown
        ticker is refused by the foreign key; returning None here makes that a
        decision the caller makes rather than a constraint violation it
        discovers.
        """
        row = self.connection.execute(
            "SELECT asset_id FROM assets WHERE ticker = ? LIMIT 1",
            (asset.upper(),),
        ).fetchone()
        return row["asset_id"] if row is not None else None

    def _admission_head(
        self, asset_id: str, metric: Optional[str], cutoff: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        The decision currently in force: the one nothing supersedes.

        Ordering by `created_at` was the obvious way to pick the latest of two
        decisions made at one instant, and it does not work.
        `utc_now()` is `datetime.now(timezone.utc).isoformat()`
        (`data_contract.py:60-61`), and on Windows the underlying clock has
        roughly 15.6ms granularity, so two insertions inside the same tick get
        *identical* `created_at` values -- measured, not assumed. Ordering a tie
        by a timestamp that is equal orders it by nothing.

        The `supersedes` chain is the recorded order, so it is what this reads.
        A row that no other row supersedes is the head of its chain, and there
        is exactly one head per chain by construction, because every insert
        points at the previous head. That makes the answer deterministic from
        recorded data alone, with no clock and no inference from physical order.
        """
        clauses = ["asset_id = ?"]
        parameters: List[Any] = [asset_id]
        if metric is not None:
            clauses.append("metric = ?")
            parameters.append(metric)
        if cutoff is not None:
            clauses.append("decided_at <= ?")
            parameters.append(cutoff)
        where = " AND ".join(clauses)
        row = self.connection.execute(
            f"SELECT * FROM admissions WHERE {where}"
            " AND admission_id NOT IN ("
            "   SELECT supersedes FROM admissions"
            f"   WHERE {where} AND supersedes IS NOT NULL"
            " )"
            " ORDER BY decided_at DESC, admission_id DESC LIMIT 1",
            parameters + parameters,
        ).fetchone()
        return dict(row) if row is not None else None

    def _has_admissions(self) -> bool:
        """
        Whether this archive carries the 3.32 table at all.

        Same reasoning as `_has_interpretations`: every archive on disk predates
        it, so its absence is a fact about age rather than an error.
        """
        return self._has_table("admissions")

    def record_admission(
        self,
        asset: str,
        decided_at: str,
        admission: Any,
        registry_state_identity: str,
        resolver_policy_identity: str,
        price: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Record one admission decision.

        `admission` is an `evidence_valuation_boundary.Admission`; it is not
        imported here, because the archive is beneath the crossing and must not
        depend on it. The fields this reads off it are named in the caller's
        terms.

        What is written is identity and reasons. `value`, `unit`, `currency` and
        the period columns are deliberately not written: they belong to the
        observation, which is already stored under `contract_id`, and a second
        copy is a second thing that can disagree. The price is written by
        identity for the same reason, and because `_currency_refusals` makes the
        price decide rule 4 -- so which price decided is part of the record even
        though what it said is not.

        A repeated identical decision is a read, not a second row: `identity` is
        content-derived and UNIQUE. A *changed* decision is a new identity and
        supersedes the previous one for this asset and metric.
        """
        if not self._has_admissions():
            return {"created": False, "reason": "this archive has no admissions table"}
        asset_id = self._asset_id_for_ticker(asset)
        if asset_id is None:
            return {"created": False,
                    "reason": f"this archive has never recorded an asset for {asset!r}"}

        refusals = [
            {"label": refusal.label, "reason": refusal.reason}
            for refusal in getattr(admission, "refusals", ())
        ]
        contract_id = getattr(admission, "contract_id", None) or getattr(
            admission, "observation_id", None
        )
        admitted = bool(getattr(admission, "admitted", False))
        price_contract_id = None if price is None else getattr(
            price, "observation_id", None
        )
        identity = admission_identity(
            asset_id=asset_id,
            decided_at=decided_at,
            metric=getattr(admission, "metric", None),
            admitted=admitted,
            contract_id=contract_id,
            registry_state_identity=registry_state_identity,
            resolver_policy_identity=resolver_policy_identity,
            price_contract_id=price_contract_id,
        )
        existing = self.connection.execute(
            "SELECT admission_id FROM admissions WHERE identity = ?",
            (identity,),
        ).fetchone()
        if existing is not None:
            return {"created": False, "admission_id": existing["admission_id"],
                    "reason": "an identical decision is already recorded"}

        previous = self._admission_head(asset_id, getattr(admission, "metric", None))
        row = {
            "admission_id": "adm_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32],
            "asset_id": asset_id,
            "decided_at": decided_at,
            "metric": getattr(admission, "metric", None),
            "admitted": 1 if admitted else 0,
            "contract_id": contract_id if admitted else contract_id,
            "source_fact_id": getattr(admission, "source_fact_id", None),
            "registry_state_identity": registry_state_identity,
            "resolver_policy_identity": resolver_policy_identity,
            "price_contract_id": price_contract_id,
            "price_source_fact_id": (
                None if price is None
                else getattr(price, "basis", {}).get("source_fact_id")
                if isinstance(getattr(price, "basis", None), dict) else None
            ),
            "identity": identity,
            "supersedes": None if previous is None else previous["admission_id"],
            "created_at": utc_now(),
            "refusals_json": json.dumps(refusals, sort_keys=True),
            "considered_observations": getattr(admission, "considered_observations", None),
            "superseded_accessions": (
                json.dumps(sorted(set(getattr(admission, "superseded_accessions", ()))))
                if isinstance(getattr(admission, "superseded_accessions", None), (list, tuple, set))
                else str(getattr(admission, "superseded_accessions", None))
                if getattr(admission, "superseded_accessions", None) is not None
                else None
            ),
            "superseded_values": (
                len(getattr(admission, "superseded_values", ()))
                if isinstance(getattr(admission, "superseded_values", None), (list, tuple, set))
                else getattr(admission, "superseded_values", None)
            ),
            "competing_concepts": (
                json.dumps(sorted(set(getattr(admission, "competing_concepts", ()))))
                if isinstance(getattr(admission, "competing_concepts", None), (list, tuple, set))
                else str(getattr(admission, "competing_concepts", None))
                if getattr(admission, "competing_concepts", None) is not None
                else None
            ),
            "mapping_type": getattr(admission, "mapping_type", None),
            "relation_kind": getattr(admission, "relation_kind", None),
            "availability_class": getattr(admission, "availability_class", None),
        }
        columns = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        self.connection.execute(
            f"INSERT INTO admissions ({columns}) VALUES ({marks})",
            tuple(row.values()),
        )
        self.connection.commit()
        return {"created": True, "admission_id": row["admission_id"], "admission": row}

    def admissions_for(
        self, asset: str, metric: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Every decision recorded for one asset, newest first."""
        if not self._has_admissions():
            return []
        asset_id = self._asset_id_for_ticker(asset)
        if asset_id is None:
            return []
        if metric is None:
            rows = self.connection.execute(
                "SELECT * FROM admissions WHERE asset_id = ?"
                " ORDER BY decided_at DESC, admission_id DESC",
                (asset_id,),
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT * FROM admissions WHERE asset_id = ? AND metric = ?"
                " ORDER BY decided_at DESC, admission_id DESC",
                (asset_id, metric),
            ).fetchall()
        return [dict(row) for row in rows]

    def effective_admission(
        self, asset: str, metric: str, cutoff: str
    ) -> Optional[Dict[str, Any]]:
        """
        The decision in force for one asset and metric at a cutoff.

        Greatest `decided_at` at or before `cutoff`. This is the *comparison
        target* a replay checks its recomputation against, never an input to it:
        `archive.replay` re-derives the decision and reports whether the two
        agree, and the recomputation is what stands when they do not. Reading
        this row to *decide* would make replay a lookup, which is the one thing
        `archive.py` forbids.
        """
        if not self._has_admissions():
            return None
        asset_id = self._asset_id_for_ticker(asset)
        if asset_id is None:
            return None
        return self._admission_head(asset_id, metric, cutoff)

    def get_admission(self, admission_id: str) -> Optional[Dict[str, Any]]:
        if not self._has_admissions():
            return None
        row = self.connection.execute(
            "SELECT * FROM admissions WHERE admission_id = ?", (admission_id,)
        ).fetchone()
        return dict(row) if row else None

    def admission_count(self) -> int:
        if not self._has_admissions():
            return 0
        return int(self.connection.execute(
            "SELECT COUNT(*) AS n FROM admissions").fetchone()["n"])

    def _source_fact(self, source_fact_id: str) -> Optional[SourceFact]:
        """The source fact an interpretation refers to, from `observations`."""
        row = self.connection.execute(
            "SELECT o.* FROM observations o WHERE o.source_fact_id = ?",
            (source_fact_id,),
        ).fetchone()
        if row is None:
            return None
        return SourceFact(
            source_fact_id=row["source_fact_id"],
            available_at=row["available_at"] or row["replay_eligible_from"],
            replay_eligible_from=row["replay_eligible_from"],
            value=json.loads(row["value_json"]),
            period_start=row["period_start"],
            period_end=row["period_end"],
            metric=row["metric"],
            lineage_id=row["lineage_id"],
        )

    def _axis_for(self, source_fact_id: str) -> KnowledgeAxis:
        """
        Rebuild the stored series as a validated axis.

        Replaying the persisted rows through `record` means the validators see
        the real series rather than a reimplementation of it, so a row that was
        written by an older build with looser rules cannot slip a new one past
        them.
        """
        axis = knowledge_axis_for(self.connection, source_fact_id)
        if axis is None:
            raise InterpretationError(
                f"no observation carries source_fact_id {source_fact_id!r}, so "
                "there is no source fact to interpret. An interpretation may "
                "not create a source fact.")
        return axis

    def _interpretations_for(self, source_fact_id: str) -> List[Dict[str, Any]]:
        return [dict(row) for row in self.connection.execute(
            "SELECT * FROM interpretations WHERE source_fact_id = ?"
            " ORDER BY knowledge_at, interpretation_id", (source_fact_id,))]

    def add_interpretation(
        self,
        source_fact_id: str,
        knowledge_at: str,
        unit: str,
        currency: Optional[str],
        currency_basis: str,
    ) -> Dict[str, Any]:
        """
        Record one interpretation of an existing source fact.

        Returns the stored row, and `created` says whether this call wrote it. A
        repeat of an identical interpretation is recognised and reported as
        `created: False` rather than raising, because re-running a repair has to
        be safe. Everything else the 2.59 contract forbids is refused.

        Transaction ownership is decided ONCE, here, before any statement can
        begin a transaction.

        It used to be decided after the INSERT, by asking whether a transaction
        was open -- which is always true by then, because the INSERT is what
        opened it. The method therefore never committed its own work, and a
        standalone caller saw the row on its own connection and nowhere else: the
        return value said "written" while the file said "absent". A caller that
        began its own transaction was unaffected, which is why the batch path
        worked and the standalone path silently did not.

        So this method owns the transaction when none was open when it was
        called, and then commits on success and rolls back on failure. When a
        transaction was already open the caller owns it, and this method commits
        nothing and rolls back nothing. Both modes are legal.
        """
        started_transaction = not self.connection.in_transaction
        if not self._has_interpretations():
            raise InterpretationError(
                "this archive predates the knowledge-state migration, so it "
                "cannot hold an interpretation. Open it with create=True to "
                "apply migration 17.")
        axis = self._axis_for(source_fact_id)
        # A new reading supersedes the one currently last in knowledge order.
        # The first reading supersedes nothing, and every later one must name
        # its predecessor -- which is what makes the series an auditable chain
        # rather than an unordered pile of readings.
        held = axis.audit()
        try:
            interpretation, created = axis.record(
                knowledge_at, unit, currency, currency_basis,
                supersedes=held[-1].identity if held else None)
        except KnowledgeAxisError as error:
            # The validators live in one place; the archive reports its own
            # error type so a caller can tell "this reading is not allowed"
            # from "the archive could not answer".
            raise InterpretationError(str(error)) from error
        if not created:
            existing = self.connection.execute(
                "SELECT * FROM interpretations WHERE identity = ?",
                (interpretation.identity,)).fetchone()
            return {"created": False, "interpretation": dict(existing)}
        row = {
            "interpretation_id": f"interp_{interpretation.identity[7:31]}",
            "source_fact_id": interpretation.source_fact_id,
            "knowledge_at": interpretation.knowledge_at,
            "unit": interpretation.unit,
            "currency": interpretation.currency,
            "currency_basis": interpretation.currency_basis,
            "identity": interpretation.identity,
            "supersedes": interpretation.supersedes,
            "created_at": utc_now(),
        }
        try:
            self.connection.execute(
                "INSERT INTO interpretations (interpretation_id,"
                " source_fact_id, knowledge_at, unit, currency, currency_basis,"
                " identity, supersedes, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", tuple(row.values()))
        except sqlite3.Error:
            # Roll back only a transaction this call opened. A caller's
            # transaction is theirs to commit or roll back, and silently undoing
            # their work would be a worse bug than the one being fixed.
            if started_transaction:
                self.connection.rollback()
            raise
        # Commit only when this call owned the transaction, decided at entry.
        # A caller repairing a whole archive needs every interpretation in it to
        # land or none of them, so a per-row commit is wrong for a
        # caller-owned batch. That is why ownership is captured rather than
        # inferred from SQLite's state after the INSERT.
        if started_transaction:
            self.connection.commit()
        return {"created": True, "interpretation": row}

    def interpretations_for_source_fact(
        self, source_fact_id: str
    ) -> List[Dict[str, Any]]:
        """Every interpretation of one source fact, in knowledge order."""
        if not self._has_interpretations():
            return []
        return self._interpretations_for(source_fact_id)

    def get_interpretation(self, interpretation_id: str) -> Optional[Dict[str, Any]]:
        if not self._has_interpretations():
            return None
        row = self.connection.execute(
            "SELECT * FROM interpretations WHERE interpretation_id = ?",
            (interpretation_id,)).fetchone()
        return dict(row) if row else None

    def effective_interpretation(
        self, source_fact_id: str, cutoff: str
    ) -> Optional[Dict[str, Any]]:
        """
        The one interpretation effective at a knowledge cutoff.

        Greatest `knowledge_at` at or before `cutoff`, inclusive. Not wired into
        any existing reader: this is the layer 2.60 said readers would need, and
        2.61 deliberately stops short of changing reader semantics.
        """
        if not self._has_interpretations():
            return None
        axis = self._axis_for(source_fact_id)
        chosen = axis.effective_at(cutoff)
        if chosen is None:
            return None
        row = self.connection.execute(
            "SELECT * FROM interpretations WHERE identity = ?",
            (chosen.identity,)).fetchone()
        return dict(row) if row else None

    def interpretation_count(self) -> int:
        if not self._has_interpretations():
            return 0
        return int(self.connection.execute(
            "SELECT COUNT(*) AS n FROM interpretations").fetchone()["n"])

    def document_count(self) -> int:
        return int(
            self.connection.execute(
                "SELECT COUNT(*) AS n FROM source_documents"
            ).fetchone()["n"]
        )

    def table_names(self) -> List[str]:
        return [
            row["name"]
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
                " ORDER BY name"
            )
        ]

