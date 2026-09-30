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
    StoredDocument,
    document_hash,
    utc_now,
)
from data_contract import Observation, SourceType, ValidationStatus

MIGRATIONS_DIR = Path(__file__).resolve().parent / "archive" / "migrations"

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
            connection.executescript(sql)
            connection.execute(
                "INSERT INTO schema_migrations (version, name, checksum,"
                " applied_at) VALUES (?, ?, ?, ?)",
                (version, name, checksum, utc_now()),
            )
            connection.execute(f"PRAGMA user_version = {version}")
            connection.commit()

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
    ) -> str:
        source_id = "src_" + hashlib.sha256(
            f"{provider}|{source_type}|{base_url}".encode("utf-8")
        ).hexdigest()[:20]
        self.connection.execute(
            "INSERT OR IGNORE INTO sources (source_id, provider, source_type,"
            " base_url, declared, notes) VALUES (?, ?, ?, ?, ?, ?)",
            (source_id, provider, source_type, base_url, declared, notes),
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
        if klass == SOURCE_DECLARED:
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

    def observations_for(self, asset: str, cutoff: str) -> List[Observation]:
        """
        Every observation replay-eligible at `cutoff`, and nothing else.

        A `NULL` replay_eligible_from is excluded, which is what makes an
        undeclared observation permanently ineligible rather than merely late.

        Where two archived rows carry the same contract identifier — a band
        restated after archival, so the canonical per-metric identifier
        collided — the most recently eligible one is returned. That is the same
        rule `latest_knowable` applies, and the earlier row is still in the
        archive and still reachable by its own id.
        """
        rows = self.connection.execute(
            "SELECT o.* FROM observations o JOIN assets a"
            " ON a.asset_id = o.asset_id"
            " WHERE a.ticker = ? AND o.replay_eligible_from IS NOT NULL"
            " AND o.replay_eligible_from <= ?"
            " ORDER BY o.replay_eligible_from, o.observation_id",
            (asset.upper(), cutoff),
        ).fetchall()
        newest: Dict[str, sqlite3.Row] = {}
        for row in rows:
            newest[str(row["contract_id"])] = row
        return [self._row_to_observation(row) for row in newest.values()]

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
