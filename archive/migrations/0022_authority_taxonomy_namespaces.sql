-- ST-EVA 0022 - Taxonomy authority provenance schema (Amendment 6 frozen).
-- Forward-only. Additive DDL only. Zero data. Zero backfill.
-- Frozen design: docs/ADR-XBRL-SOURCE-DOCUMENT-PROVENANCE.md Amendment 6.
-- Relation represents SOURCE_BACKED_AUTHORITY_ASSERTION only.
-- Not canonical current state; not filing-use; not Observation identity.

BEGIN;

CREATE TABLE IF NOT EXISTS authority_taxonomy_namespaces (
    authority_taxonomy_id TEXT PRIMARY KEY,
    -- Canonical JSON preimage digest of {document_id, namespace_uri, provider,
    -- taxonomy_family, taxonomy_version}; persisted verbatim for audit.
    authority_taxonomy_identity TEXT NOT NULL UNIQUE,

    -- Identity-bearing fields (preimage components).
    document_id      TEXT NOT NULL REFERENCES source_documents(document_id),
    provider         TEXT NOT NULL,
    taxonomy_family  TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    namespace_uri    TEXT NOT NULL,

    -- Evidence payload from the captured authority source document.
    standard_prefix        TEXT,
    file_type_name         TEXT,
    schema_href            TEXT,
    authority_source       TEXT NOT NULL,
    authority_source_class TEXT NOT NULL,
    authority_source_version TEXT,

    -- Retrieval / capture metadata. Excluded from identity.
    captured_at  TEXT NOT NULL,

    FOREIGN KEY (document_id) REFERENCES source_documents(document_id)
);

-- Read-side composite lookup index for B2 taxonomy equivalence evaluation.
-- Explicitly NOT unique; multiple families may share the same namespace URI.
CREATE INDEX IF NOT EXISTS authority_taxonomy_lookup
    ON authority_taxonomy_namespaces(provider, namespace_uri, taxonomy_family);

-- Append-only: mutations strictly forbidden.
CREATE TRIGGER IF NOT EXISTS authority_taxonomy_namespaces_no_update
BEFORE UPDATE ON authority_taxonomy_namespaces
BEGIN
    SELECT RAISE(ABORT, 'authority_taxonomy_namespaces is append-only; updates forbidden');
END;

-- Append-only: deletions strictly forbidden.
CREATE TRIGGER IF NOT EXISTS authority_taxonomy_namespaces_no_delete
BEFORE DELETE ON authority_taxonomy_namespaces
BEGIN
    SELECT RAISE(ABORT, 'authority_taxonomy_namespaces is append-only; deletions forbidden');
END;

-- Closed vocabulary enforcement for authority_source_class (no numeric rank).
CREATE TRIGGER IF NOT EXISTS authority_taxonomy_namespaces_source_class_vocabulary
BEFORE INSERT ON authority_taxonomy_namespaces
WHEN NEW.authority_source_class NOT IN (
    'MACHINE_READABLE_CATALOG',
    'REGULATORY_MANUAL',
    'TECHNICAL_SCHEMA'
)
BEGIN
    SELECT RAISE(ABORT,
        'authority_taxonomy_namespaces.authority_source_class outside closed vocabulary');
END;

-- Extraction consistency: identical authority_taxonomy_id must resolve to the
-- same identity fields; conflicting reuse of the same id aborts.
CREATE TRIGGER IF NOT EXISTS authority_taxonomy_namespaces_extraction_consistent
BEFORE INSERT ON authority_taxonomy_namespaces
WHEN EXISTS (
    SELECT 1 FROM authority_taxonomy_namespaces a
    WHERE a.authority_taxonomy_id = NEW.authority_taxonomy_id
      AND (a.authority_taxonomy_identity <> NEW.authority_taxonomy_identity
           OR a.document_id <> NEW.document_id
           OR a.provider <> NEW.provider
           OR a.taxonomy_family <> NEW.taxonomy_family
           OR a.taxonomy_version <> NEW.taxonomy_version
           OR a.namespace_uri <> NEW.namespace_uri)
)
BEGIN
    SELECT RAISE(ABORT,
        'conflicting authority extraction: identical authority_taxonomy_id resolved to differing fields');
END;

COMMIT;

-- Migration runner will advance PRAGMA user_version = 22 and record checksum.
