-- ST-EVA 2.5.1 - the incremental ingestion ledger.
--
-- Two things the archive could not do before this.
--
-- First, it could prevent duplicate *storage* by content hash, but it had no
-- record of which filings it had already seen. Without that, every run
-- re-downloaded a decade of filings, which is correct for the store and
-- indefensible for a source that asks callers to be considerate.
--
-- Second, an observation could not say "this has no filing concept" as
-- distinct from "this concept is unknown". The `concept` column is doing double
-- duty, and a view-derived figure puts a metric name where a filing concept
-- belongs. `source_concept_ref` separates them and is nullable on purpose.

CREATE TABLE IF NOT EXISTS held_filings (
    asset_id      TEXT NOT NULL REFERENCES assets(asset_id),
    -- The filing's identity, which is its accession number. Not a filename, not
    -- a retrieval timestamp, and not a content hash: those identify content or
    -- a fetch, and a filing is neither. An amendment arrives under a new
    -- accession, which is exactly why the accession is what diffs.
    accession     TEXT NOT NULL,
    form          TEXT,
    filed_at      TEXT,
    period_end    TEXT,
    report_date   TEXT,
    primary_document TEXT,
    document_id   TEXT,
    first_seen_at TEXT NOT NULL,
    PRIMARY KEY (asset_id, accession)
);

CREATE INDEX IF NOT EXISTS held_filings_recent
    ON held_filings(asset_id, filed_at);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    run_id             TEXT PRIMARY KEY,
    asset_id           TEXT NOT NULL REFERENCES assets(asset_id),
    source_id          TEXT,
    started_at         TEXT NOT NULL,
    finished_at        TEXT,
    filings_seen       INTEGER NOT NULL DEFAULT 0,
    filings_already_held INTEGER NOT NULL DEFAULT 0,
    filings_ingested   INTEGER NOT NULL DEFAULT 0,
    documents_stored   INTEGER NOT NULL DEFAULT 0,
    documents_reused   INTEGER NOT NULL DEFAULT 0,
    source_facts_stored INTEGER NOT NULL DEFAULT 0,
    source_facts_skipped INTEGER NOT NULL DEFAULT 0,
    observations_stored INTEGER NOT NULL DEFAULT 0,
    observations_skipped INTEGER NOT NULL DEFAULT 0,
    network_fetches    INTEGER NOT NULL DEFAULT 0,
    concepts_unresolved INTEGER NOT NULL DEFAULT 0,
    status             TEXT,
    error              TEXT
);

CREATE INDEX IF NOT EXISTS ingestion_runs_asset
    ON ingestion_runs(asset_id, started_at);

ALTER TABLE observations ADD COLUMN source_concept_ref TEXT;

-- A source concept is qualified as taxonomy:concept, or it is absent. A bare
-- word here is the exact confusion this column exists to remove, so it is
-- refused at the database rather than noticed later. Ingestion supplies it on
-- the insert; the append-only trigger makes an update impossible anyway, so
-- guarding the insert is guarding the only path that exists.
CREATE TRIGGER IF NOT EXISTS observations_concept_ref_shape
BEFORE INSERT ON observations
WHEN NEW.source_concept_ref IS NOT NULL
     AND NEW.source_concept_ref NOT LIKE '%:%'
BEGIN
    SELECT RAISE(ABORT, 'source_concept_ref must be qualified as taxonomy:concept, or NULL');
END;

-- The registry resolves a source concept to a semantic metric. It never
-- infers one, so a row may legitimately carry a concept with no metric yet,
-- and a metric with no concept at all.
CREATE INDEX IF NOT EXISTS observations_source_concept
    ON observations(asset_id, source_concept_ref, period_end);
