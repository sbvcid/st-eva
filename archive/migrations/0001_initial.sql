-- ST-EVA 2.4 initial archive schema.
--
-- Append-only. The observations and context_snapshots tables carry triggers
-- that reject UPDATE and DELETE, because invariants I1, I2 and I8 are enforced
-- by the database rather than by convention. A rule that lives only in a
-- docstring is a rule that gets broken by the first bugfix under time pressure.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    checksum    TEXT NOT NULL,
    applied_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assets (
    asset_id    TEXT PRIMARY KEY,
    ticker      TEXT NOT NULL,
    cik         TEXT,
    name        TEXT,
    exchange    TEXT,
    currency    TEXT,
    -- The name the filing source gives the entity, which is not always the
    -- name the market data source uses. Both are kept, because a replayed
    -- context has to carry the same identifiers the archived one did.
    sec_entity_name TEXT,
    first_seen_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS assets_ticker ON assets(ticker);
CREATE UNIQUE INDEX IF NOT EXISTS assets_cik ON assets(cik) WHERE cik IS NOT NULL;

CREATE TABLE IF NOT EXISTS sources (
    source_id   TEXT PRIMARY KEY,
    provider    TEXT NOT NULL,
    source_type TEXT NOT NULL,
    base_url    TEXT,
    declared    TEXT NOT NULL DEFAULT 'NO',
    notes       TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS sources_identity
    ON sources(provider, source_type, base_url);

CREATE TABLE IF NOT EXISTS source_documents (
    document_id  TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL UNIQUE,
    uri          TEXT,
    http_status  INTEGER,
    media_type   TEXT,
    byte_size    INTEGER,
    fetched_at   TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    storage_path TEXT,
    compression  TEXT
);
CREATE TABLE IF NOT EXISTS observation_lineage (
    lineage_id   TEXT PRIMARY KEY,
    asset_id     TEXT NOT NULL REFERENCES assets(asset_id),
    metric       TEXT NOT NULL,
    concept      TEXT NOT NULL,
    -- Nullable: a point-in-time fact, or one that was never reported, has no
    -- period. A lineage must still exist for it.
    period_start TEXT,
    period_end   TEXT,
    created_at   TEXT NOT NULL,
    note         TEXT
);

CREATE INDEX IF NOT EXISTS lineage_lookup
    ON observation_lineage(asset_id, metric, period_end);

CREATE TABLE IF NOT EXISTS observations (
    observation_id       TEXT PRIMARY KEY,
    -- The contract's own identifier, preserved so a replayed context carries
    -- the same refs as the context that was archived. The row id is a
    -- physical key derived from the content hash, because the contract id is
    -- canonical per metric and a restatement of a band would collide on it.
    contract_id          TEXT NOT NULL,
    asset_id             TEXT NOT NULL REFERENCES assets(asset_id),
    lineage_id           TEXT NOT NULL REFERENCES observation_lineage(lineage_id),
    metric               TEXT NOT NULL,
    provider             TEXT NOT NULL,
    source_type          TEXT NOT NULL,
    source_url           TEXT,
    concept              TEXT NOT NULL,
    value_json           TEXT NOT NULL,
    unit                 TEXT,
    currency             TEXT,
    currency_basis       TEXT,
    period_start         TEXT,
    period_end           TEXT,
    as_of                TEXT,
    -- available_at is the source's own publication time and is frequently NULL.
    -- It is never filled from retrieved_at.
    available_at         TEXT,
    available_at_basis   TEXT,
    availability_class   TEXT NOT NULL,
    -- retrieved_at is when ST-EVA asked. It is not a publication time.
    retrieved_at         TEXT NOT NULL,
    first_archived_at    TEXT NOT NULL,
    -- The one column replay filters on. NULL means "archived, and not
    -- replay-eligible at any instant".
    replay_eligible_from TEXT,
    definition           TEXT,
    methodology          TEXT,
    status               TEXT,
    -- The remaining contract fields, so a stored observation round-trips
    -- faithfully. Dropping any of them would make a replayed context differ
    -- from the archived one for a reason that has nothing to do with the data.
    status_reasons_json  TEXT,
    inputs_json          TEXT,
    observation_count    INTEGER,
    raw_json             TEXT,
    content_hash         TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS observations_replay
    ON observations(asset_id, replay_eligible_from);
CREATE INDEX IF NOT EXISTS observations_metric
    ON observations(asset_id, metric, period_end);
CREATE INDEX IF NOT EXISTS observations_lineage
    ON observations(lineage_id);
CREATE INDEX IF NOT EXISTS observations_contract
    ON observations(contract_id);

-- Invariant I1 and I2: append-only, enforced by the database.
CREATE TRIGGER IF NOT EXISTS observations_no_update
BEFORE UPDATE ON observations
BEGIN
    SELECT RAISE(ABORT, 'observations are append-only');
END;

CREATE TRIGGER IF NOT EXISTS observations_no_delete
BEFORE DELETE ON observations
BEGIN
    SELECT RAISE(ABORT, 'observations are append-only');
END;

-- An eligibility claim must be supported by the class that justifies it. A row
-- cannot claim source-declared availability while storing no available_at.
CREATE TRIGGER IF NOT EXISTS observations_availability_consistent
BEFORE INSERT ON observations
WHEN NEW.availability_class = 'SOURCE_DECLARED' AND NEW.available_at IS NULL
BEGIN
    SELECT RAISE(ABORT,
        'a SOURCE_DECLARED observation must carry available_at');
END;

CREATE TRIGGER IF NOT EXISTS observations_archival_consistent
BEFORE INSERT ON observations
WHEN NEW.availability_class = 'ARCHIVE_FIRST_SEEN'
     AND NEW.replay_eligible_from IS NOT NEW.first_archived_at
BEGIN
    SELECT RAISE(ABORT,
        'an ARCHIVE_FIRST_SEEN observation is eligible from first_archived_at');
END;

CREATE TRIGGER IF NOT EXISTS observations_undeclared_not_eligible
BEFORE INSERT ON observations
WHEN NEW.availability_class = 'UNDECLARED'
     AND NEW.replay_eligible_from IS NOT NULL
BEGIN
    SELECT RAISE(ABORT,
        'an UNDECLARED observation is never replay-eligible');
END;

CREATE TABLE IF NOT EXISTS observation_sources (
    observation_id TEXT NOT NULL REFERENCES observations(observation_id),
    document_id    TEXT NOT NULL REFERENCES source_documents(document_id),
    accession      TEXT,
    PRIMARY KEY (observation_id, document_id)
);

CREATE INDEX IF NOT EXISTS observation_sources_document
    ON observation_sources(document_id);

CREATE TABLE IF NOT EXISTS validation_records (
    record_id           TEXT PRIMARY KEY,
    observation_id      TEXT REFERENCES observations(observation_id),
    kind                TEXT NOT NULL,
    status              TEXT NOT NULL,
    reasons_json        TEXT,
    comparison_basis_json TEXT,
    tolerance_json      TEXT,
    explanation         TEXT,
    references_json     TEXT,
    value_snapshot_json TEXT,
    checked_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS validation_observation
    ON validation_records(observation_id);

CREATE TABLE IF NOT EXISTS context_snapshots (
    context_id       TEXT PRIMARY KEY,
    asset_id         TEXT NOT NULL REFERENCES assets(asset_id),
    as_of            TEXT NOT NULL,
    knowledge_cutoff TEXT,
    replay_fidelity  TEXT NOT NULL,
    built_from_json  TEXT,
    document_json    TEXT NOT NULL,
    document_hash    TEXT NOT NULL,
    supersedes       TEXT,
    archived_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS contexts_at
    ON context_snapshots(asset_id, as_of);

CREATE TRIGGER IF NOT EXISTS context_snapshots_no_update
BEFORE UPDATE ON context_snapshots
BEGIN
    SELECT RAISE(ABORT, 'context snapshots are immutable');
END;

CREATE TRIGGER IF NOT EXISTS context_snapshots_no_delete
BEFORE DELETE ON context_snapshots
BEGIN
    SELECT RAISE(ABORT, 'context snapshots are immutable');
END;

CREATE TABLE IF NOT EXISTS derived_values (
    context_id    TEXT NOT NULL REFERENCES context_snapshots(context_id),
    ref           TEXT NOT NULL,
    operation_json TEXT,
    expression    TEXT,
    value_json    TEXT,
    unit          TEXT,
    deterministic INTEGER NOT NULL DEFAULT 1,
    depends_on_json TEXT,
    PRIMARY KEY (context_id, ref)
);
