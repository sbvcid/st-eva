-- ST-EVA 3.32 - admission records.
--
-- An `Observation` is what a provider reported. An *admission* is which of those
-- observations the engine was allowed to consume, at one asset, at one instant,
-- under one registry and one policy. Those are different things and 3.27
-- established why they must stay in different relations:
--
--     observations      WHAT the source said
--     admissions        WHICH of it the engine took, and why
--
-- The temptation is to put the consumption role on the observation. That would
-- be wrong twice over. It would make `observations` carry a context-dependent
-- truth -- the same fact is EVIDENCE_ONLY at one instant and ENGINE_INPUT at
-- another -- and it would require a new row per role, because
-- `ObservationSet.add` refuses a duplicate identity. Both were measured: an
-- `Observation.role` field would either re-key all 291,134 archived rows or be
-- silently dropped by the content-hash dedup, and it would freeze an
-- as-of-scoped decision at the instant that wrote it.
--
-- This migration is deliberately NOT keyed by `context_id`. The crossing
-- produces a `BoundaryResult`, not a document, and `record_context` is never
-- called on that path, so there is no context document to associate with. A
-- context id is a grouping of a different product; using it as decision
-- identity would make the admission record depend on a document that may never
-- have been built. Decision identity is `(asset_id, decided_at, metric)`.
--
-- The price is recorded by identity and never by value. `_currency_refusals`
-- (`evidence_valuation_boundary.py:611-648`) answers CURRENCY_UNDECLARED when
-- the *price* declares no currency, and CURRENCY_MISMATCH when it does not
-- match, so the price decides rule 4 and therefore participates in the
-- outcome. Which price decided it is therefore part of what this record is.
-- Its figure is not: the price is an observation, it is already in the archive
-- under its own identity, and copying the number here would create a second
-- copy that can disagree with the first.
--
-- No backfill. Every archive on disk predates the two identity functions this
-- record would carry, so there is nothing to populate it with, and populating
-- it with current-state identities would assert a history that never happened.
-- The archive gains the ability to record a decision and nothing else.
--
-- `value`, `unit`, `currency` and the period columns are deliberately absent:
-- they belong to the observation and are re-derivable from `contract_id`. So is
-- the registry and the code: `registry_state_identity` and
-- `resolver_policy_identity` are digests of state that lives in the
-- repository, and copying a registry snapshot per row would make every row
-- carry data that git already holds and that a digest can verify.
BEGIN;

CREATE TABLE IF NOT EXISTS admissions (
    admission_id            TEXT PRIMARY KEY,
    -- The decision identity: which asset, which instant, which metric.
    asset_id                TEXT NOT NULL REFERENCES assets(asset_id),
    decided_at              TEXT NOT NULL,
    metric                  TEXT NOT NULL,
    admitted                INTEGER NOT NULL,

    -- Which observation the decision was about. NULL when nothing was
    -- admissible: a refusal is a decision too, and the persistence tests assert
    -- that a refused admission is a row rather than an absence.
    contract_id             TEXT,
    source_fact_id          TEXT,

    -- The two halves of the interpretation that produced it, from 3.31. Both
    -- NOT NULL: an admission recorded without them could not say what read it,
    -- and would be evidence for a decision whose conditions are unrecoverable.
    registry_state_identity TEXT NOT NULL,
    resolver_policy_identity TEXT NOT NULL,

    -- The price dependency, by identity. See the header: the price decides
    -- rule 4, so which price decided is part of the record; what it said is not.
    price_contract_id       TEXT,
    price_source_fact_id    TEXT,

    -- Content-derived key over the decision above. UNIQUE makes a repeated
    -- identical insertion a read rather than a second row, and keeps any
    -- free-text rendering out of identity. A *changed* decision is a different
    -- identity and is inserted as a row that supersedes.
    identity                TEXT NOT NULL UNIQUE,

    -- An explicit link to the preceding decision for the same
    -- (asset_id, metric). The self-reference is the only cross-row check SQLite
    -- can make here; that the target shares the asset and metric and precedes
    -- this row is enforced by the writer, and this migration does not pretend a
    -- CHECK constraint could do it.
    supersedes              TEXT REFERENCES admissions(admission_id),
    created_at              TEXT NOT NULL,

    -- Audit. Every field below is re-derivable by re-running admission, and is
    -- present so that a divergence between a stored record and a recomputation
    -- can be *described* rather than only reported as a mismatch.
    refusals_json           TEXT,
    considered_observations INTEGER,
    superseded_accessions   TEXT,
    superseded_values       INTEGER,
    competing_concepts      INTEGER,
    mapping_type            TEXT,
    relation_kind           TEXT,
    availability_class      TEXT
);

-- The decision lookup: everything recorded for one asset and metric, newest
-- decision first.
CREATE INDEX IF NOT EXISTS admissions_decision
    ON admissions(asset_id, metric, decided_at DESC);

-- Supersedes lookup, for the same reason as interpretations_supersedes.
CREATE INDEX IF NOT EXISTS admissions_supersedes
    ON admissions(supersedes);

-- An admission is a statement about what the engine was allowed to take, at an
-- instant, under a named interpretation. Editing or removing one would leave
-- the archive asserting something it can no longer support, exactly as for
-- observations, context snapshots and interpretations. A re-decision is an
-- INSERT that supersedes, never an UPDATE.
CREATE TRIGGER IF NOT EXISTS admissions_no_update
BEFORE UPDATE ON admissions
BEGIN
    SELECT RAISE(ABORT, 'admissions are append-only');
END;

CREATE TRIGGER IF NOT EXISTS admissions_no_delete
BEFORE DELETE ON admissions
BEGIN
    SELECT RAISE(ABORT, 'admissions are append-only');
END;

COMMIT;