"""
3.31 -- identity for the two things that decide an admission.

3.29 measured that admission interpretation is a function of two independent
things that the repository records neither of:

    registry data state    which rows the registry holds
    resolver policy state  which code reads them

`de896b5` changed the second with the first byte-identical, and flipped
fourteen concepts' resolution. `8696e97` changed the first with the resolver
byte-identical, and turned a concept from UNRESOLVED into RESOLVED. A single
`registry_version` would have missed both. These are two primitives, not a
framework, and neither of them stores anything.

`registry_state_identity` answers "which rows does the registry hold" and
`resolver_policy_identity` answers "which code would read them". Both return a
prefixed digest and both are pure functions of their inputs.

Two properties are load-bearing and are worth stating before the code:

**The registry identity is over semantic rows, not physical rows.**
`metric_concept_mapping` declares `PRIMARY KEY (metric_id, concept_id,
effective_from)` and `effective_from` is nullable, so SQLite does not enforce
uniqueness for an unbounded mapping. The MU pilot archive holds 74 physical
mapping rows for 50 distinct mappings, because `add_mapping` is
`INSERT OR REPLACE` (`core_registry.py:1217`) and the archive was seeded more
than once. A digest over physical rows would therefore encode how many times
the archive was seeded, which is not registry meaning. Duplicates are removed.

**The policy identity is over whole files, not parsed functions.**
`git log -- core_registry.py` shows 11 commits, 5 of which changed nothing the
resolver reads. A per-function audit is also unstable in the other direction:
`e45c8df` *added* `_has_table`, which `resolve_metric` did not depend on until
two commits later, so a function-level record mislabels it twice. Whole-file
digests are monotonic in the cheap direction -- every change is noticed -- and
that is the property a replay check needs. A false positive costs a re-run; a
false negative produces a wrong number.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import core_registry  # noqa: F401  -- pins the module identity below
import data_contract  # noqa: F401
import evidence_query  # noqa: F401
import registry_seed  # noqa: F401

REPO_ROOT = Path(__file__).resolve().parent
MIGRATIONS_DIR = REPO_ROOT / "archive" / "migrations"

IDENTITY_PREFIX = "rgs:"
POLICY_PREFIX = "pol:"


# ---------------------------------------------------------------------------
# Canonicalisation
# ---------------------------------------------------------------------------


def _canonical(value: Any) -> str:
    """
    One JSON rendering, used for every digest input in this module.

    `sort_keys` fixes field order, `separators` fixes spacing, and
    `ensure_ascii=False` keeps a concept's characters as themselves rather than
    as escapes, so two rows that differ only in escaping hash the same.
    """
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def _digest(prefix: str, payload: Any) -> str:
    encoded = _canonical(payload).encode("utf-8")
    return prefix + hashlib.sha256(encoded).hexdigest()


def _normalise_json_text(raw: Any) -> Any:
    """
    A stored JSON text column, as a value.

    `scope_json` is declared TEXT and written by `add_mapping` with
    `json.dumps(..., sort_keys=True, separators=(",", ":"))`
    (`core_registry.py:1228`). Two archives that mean the same thing can still
    hold different bytes -- a value written by an older build, or one written
    by hand -- so the text is parsed and re-rendered rather than hashed raw.
    Formatting-only differences must not change the identity; a semantic change
    must.

    Anything unparseable, empty or non-object is reported as `None`, which is
    what `_read_scope` (`core_registry.py:738-752`) does with it. Two different
    unparseable texts therefore collide, and that is accepted deliberately: the
    reader cannot tell them apart either, so an identity that pretended to
    would be claiming a distinction the code does not make.
    """
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


# ---------------------------------------------------------------------------
# Registry data state
# ---------------------------------------------------------------------------

# The eight tables that decide what a registry read returns, in a fixed order
# so the payload never depends on iteration order.
#
# Excluded, with reasons:
#
#   metric_exclusion      the hypothesis layer. It carries
#                         PROPOSED/TESTABLE/SUPPORTED/REFUTED/UNDECIDED states
#                         (`core_registry.py:824-828`) and `resolve_source_concept`
#                         never reads it.
#   ingestion_scope       per-run collection metadata, not registry meaning.
#   schema_migrations     the archive's shape, which the policy identity covers.
#
# `metric_supersession.decided_at` is deliberately excluded, and this was
# measured rather than assumed. `record_supersession` stamps it with
# `utc_now()` (`core_registry.py:1500`) and `seed()` does not override that, so
# two archives seeded from the same declarations carry different `decided_at`
# values and would disagree on the digest while holding identical registries.
# The column is a record of when a seed ran, not of when 2.33 decided. Nothing
# on the resolution path reads it either: `resolve_metric` follows the
# successor chain and `supersession_of` returns the row for disclosure only, so
# dropping it loses no resolution input and buys reproducibility.
_REGISTRY_TABLES: Tuple[Tuple[str, Tuple[str, ...], bool], ...] = (
    (
        "concept_registry",
        ("concept_id", "taxonomy", "concept", "label", "source_definition"),
        False,
    ),
    (
        "declined_concept_mappings",
        ("concept_id", "considered_for_metric", "reason_code", "reason",
         "framework_basis"),
        False,
    ),
    (
        "issuer_concept_adoption",
        ("asset_id", "concept_id", "first_used", "last_used", "fact_count",
         "filing_count", "basis"),
        False,
    ),
    (
        "issuer_business_model",
        ("asset_id", "business_model", "basis", "source"),
        False,
    ),
    ("metric_concept_mapping",
     ("metric_id", "concept_id", "mapping_type", "effective_from",
      "effective_to", "relation_kind", "scope_json"),
     True),
    ("metric_inapplicable_in", ("metric_id", "business_model"), False),
    ("metric_registry",
     ("metric_id", "display_name", "statement", "semantic_definition",
      "unit_family", "normal_period_type", "applicability",
      "comparability_group", "status"),
     False),
    ("metric_supersession",
     ("predecessor_id", "successor_id", "reason", "evidence"),
     False),
    ("unmodelled_taxonomies", ("taxonomy", "kind", "reason"), False),
)


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _table_columns(connection: sqlite3.Connection, table: str) -> List[str]:
    return [
        str(row[1])
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    ]


def _rows_for(
    connection: sqlite3.Connection,
    table: str,
    columns: Sequence[str],
    normalise_json: bool,
) -> List[Any]:
    """
    One table as a sorted, de-duplicated list of canonical row values.

    Three normalisations, each earning its place:

    * Columns are projected by name, so a migration that adds a column cannot
      silently change the identity.
    * Rows are sorted after projection, so physical order cannot either.
    * Duplicates are removed, so seeding an archive twice cannot.

    A column this archive does not have is treated as an all-NULL column rather
    than as an error, which follows the design of the migration that introduced
    the columns in question: `archive/migrations/0018_mapping_relation_kind.sql:27`
    states that both are nullable and additive "so an archive opened read-only
    without applying migrations has neither, and every reader treats a missing
    column as absent metadata rather than failing." `_read_scope`
    (`core_registry.py:738-752`) does the same for a missing or empty value.

    Absent is therefore the same reading as NULL, which is correct for registry
    meaning -- no row asserts a relation either way -- and it keeps the two
    concerns apart. The schema generation that distinguishes an archive without
    `relation_kind` from one whose rows are all NULL is recorded by the policy
    identity's migration component, where it belongs, rather than being smuggled
    into the data digest.

    A missing *table* yields no rows for the same reason: an archive that never
    applied the migration has no meaning from that table to record.
    """
    if not _table_exists(connection, table):
        return []
    present = set(_table_columns(connection, table))
    selected = [column for column in columns if column in present]
    if not selected:
        return []
    projection = ", ".join(
        column if column in present else f"NULL AS {column}" for column in columns
    )
    cursor = connection.execute(f"SELECT {projection} FROM {table}")
    rows: List[Any] = []
    for raw in cursor.fetchall():
        values = list(raw)
        if normalise_json:
            index = columns.index("scope_json")
            values[index] = _normalise_json_text(values[index])
        rows.append(values)
    # Sorting the projected values, not the raw rows, so a NULL and an empty
    # string cannot be ordered by SQLite's own collation.
    rows.sort(key=lambda values: _canonical(
        [None if value is None else str(value) for value in values]
    ))
    # Duplicates are then removed. `metric_concept_mapping` cannot enforce
    # uniqueness on an unbounded mapping, so re-seeding an archive inserts those
    # rows again; without this the digest would identify how many times the
    # archive was seeded rather than what the registry holds.
    unique: List[Any] = []
    previous = None
    for values in rows:
        key = _canonical(values)
        if key != previous:
            unique.append(values)
            previous = key
    return unique


def registry_state_identity(connection: sqlite3.Connection) -> str:
    """
    The identity of the registry data this connection holds.

    Read-only. It issues SELECTs and nothing else, and it is a pure function of
    the connection's contents: the same registry state always produces the same
    digest, and no registry table is modified.

    Three normalisations make the digest mean registry meaning rather than
    storage accident:

    * columns are projected by name, so an added column does not change the
      identity on its own
    * rows are sorted, so physical order does not
    * duplicates are removed, so seeding an archive twice does not

    The tables are the eight that decide a registry read. `metric_exclusion` is
    excluded because it is the hypothesis layer and nothing on the resolution
    path consults it; `ingestion_scope` is excluded because it records a run
    rather than a meaning.
    """
    payload = []
    for table, columns, normalise_json in _REGISTRY_TABLES:
        payload.append({
            "table": table,
            "columns": list(columns),
            "rows": _rows_for(connection, table, columns, normalise_json),
        })
    return _digest(IDENTITY_PREFIX, {"tables": payload})


# ---------------------------------------------------------------------------
# Resolver policy state
# ---------------------------------------------------------------------------

# The files whose content can change what a registry read returns.
#
#   core_registry.py              the resolver itself: resolve_source_concept,
#                                 mappings_for_observation, resolve_metric,
#                                 supersession_of, _scope_is_measured, _read_scope
#   registry_seed.py              the authoritative source for relation_kind and
#                                 scope_json (archive/migrations/0018:20-23).
#                                 A seed-only commit changes admission while the
#                                 resolver is byte-identical -- 8696e97 did
#                                 exactly that.
#   data_contract.py              rules 7, 9 and 10 live here: knowable_at,
#                                 latest_knowable, Observation.is_available, the
#                                 YEAR_*/QUARTER_* day bounds,
#                                 AvailabilityBasis, DECLARED_DATE_LAG_DAYS.
#                                 evidence_valuation_boundary imports none of the
#                                 last three, yet they gate rule 9.
#   evidence_valuation_boundary.py  rules 1-10 and the V1_* scope constants
#   evidence_query.py             classify_ambiguity, which is rule 6
#   archive.py                    availability_class_for, which is rule 8
#
# Deliberately absent: `sqlite_archive.py`, because it is covered through the
# applied-migration identity below and is storage rather than policy;
# `st_eva_runner.py`, because the crossing does not import it and admission
# cannot reach the engine through it.
_POLICY_FILES: Tuple[str, ...] = (
    "archive.py",
    "core_registry.py",
    "data_contract.py",
    "evidence_valuation_boundary.py",
    "evidence_query.py",
    "registry_seed.py",
)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _applied_migrations(connection: Optional[sqlite3.Connection]) -> List[Any]:
    """
    The migrations that actually ran, using the archive's own mechanism.

    `SQLiteArchive._ensure_schema` (`sqlite_archive.py:343-402`) records
    `version, name, checksum` in `schema_migrations`, where the checksum is
    `sha256(file text)` and is verified on every run. Reading that table reuses
    the mechanism rather than inventing a second notion of migration identity,
    and it answers the question that matters -- what shape is this archive --
    rather than what migrations exist on disk today.

    With no connection, the on-disk files are digested instead. That is a
    weaker answer: it includes migrations this archive has not applied.
    """
    if connection is not None and _table_exists(connection, "schema_migrations"):
        return [
            [row[0], row[1], row[2]]
            for row in connection.execute(
                "SELECT version, name, checksum FROM schema_migrations"
                " ORDER BY version"
            ).fetchall()
        ]
    entries = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version, _, name = path.stem.partition("_")
        entries.append([int(version), name, _file_sha256(path)])
    return entries


def resolver_policy_identity(
    connection: Optional[sqlite3.Connection] = None,
) -> str:
    """
    The identity of the code that reads the registry.

    A SHA-256 over a fixed, ordered manifest of whole-file digests plus the
    applied-migration identity. It is a pure function: the same tree and the
    same archive always produce the same value, and nothing is written.

    Whole files rather than parsed functions, deliberately. Five of the eleven
    commits that touched `core_registry.py` changed nothing the resolver reads,
    so a narrower record would carry false positives -- but a narrower record
    also carries false negatives, and `de896b5` is one: it flipped fourteen
    concepts on a forty-line change to a single predicate. The cheap direction
    of error is the safe one here. A false positive costs a re-run; a false
    negative produces a wrong revenue figure.

    No manual version constant. 3.28 established that the repository's existing
    version strings -- `CONTEXT_SCHEMA_VERSION`, `CONTRACT_VERSION`,
    `CROSS_SOURCE_VERSION` -- are documentary labels that are hardcoded twice,
    never incremented past "2.3-A", and compared in no gate. Nothing here reads
    them, and nothing here writes a constant that a later change could forget to
    bump.
    """
    files = []
    for name in _POLICY_FILES:
        path = REPO_ROOT / name
        if not path.exists():
            raise FileNotFoundError(
                f"the policy manifest names {name!r} and it is not present. A "
                "policy identity with a hole in it would claim a coverage it "
                "does not have."
            )
        files.append({"name": name, "sha256": _file_sha256(path)})
    return _digest(POLICY_PREFIX, {
        "manifest": list(_POLICY_FILES),
        "files": files,
        "migrations": _applied_migrations(connection),
    })


def admission_state_identity(connection: sqlite3.Connection) -> Dict[str, str]:
    """
    Both halves, together.

    Convenience for a caller that records them side by side; it adds no
    meaning. A stored admission record wants the two as separate fields, because
    they are separately diagnosable: a registry digest that moved says the rows
    changed, a policy digest that moved says the reading changed.
    """
    return {
        "registry_state": registry_state_identity(connection),
        "resolver_policy": resolver_policy_identity(connection),
    }
