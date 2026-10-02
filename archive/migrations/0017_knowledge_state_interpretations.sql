-- ST-EVA 2.61 - knowledge-state interpretations.
--
-- A source fact is one thing a source said. An *interpretation* is how ST-EVA
-- has read that one thing, and that reading can change without the fact
-- changing at all.
--
--     source_fact_id   WHICH source fact
--     knowledge_at     WHEN ST-EVA held this interpretation of it
--
-- 2.53 fixed a parser defect that stored non-USD monetary facts as a ratio with
-- a NULL currency. 2.54 recovered the true unit for all 298 affected
-- observations from retained source evidence. 2.56 then measured that the
-- archive could not accept the repair in either direction: a corrected row is
-- refused by the `source_fact_id` unique index, and an in-place correction is
-- refused by the append-only triggers.
--
-- The reason is that a correction is not a new fact. It is a new *reading* of a
-- fact that already exists, at a later instant, and the archive had nowhere to
-- put a second reading. This migration is that place, and it is deliberately a
-- separate relation rather than more columns on `observations`:
--
--   * `observations` keeps meaning "a source-fact reading", and keeps its
--     identity, its `content_hash` and its immutability untouched.
--   * `interpretations` holds what ST-EVA later understood, ordered by
--     knowledge time.
--
-- Keeping them apart is what preserves three guarantees at once: the
-- `observations_source_fact` uniqueness, the append-only triggers, and the
-- source-availability column that point-in-time replay filters on. No existing
-- row is read, written or reinterpreted by this migration.
--
-- On the knowledge axis: `knowledge_at` is NOT `available_at`,
-- `retrieved_at`, `period_end` or a filing date. A parser correction moved none
-- of those -- the filing was published once and said the same thing every time.
-- Folding the correction into `available_at` would date it to a filing that did
-- not contain it, which is how a point-in-time contract is quietly destroyed.

-- ---------------------------------------------------------------- foreign key
--
-- `observations(source_fact_id)` cannot be a foreign-key parent as it stands.
-- Migration 0006's index is PARTIAL, and SQLite will not accept a partial index
-- as an FK parent -- it reports "foreign key mismatch" the moment
-- `PRAGMA foreign_keys = ON` and a row is written. A full UNIQUE index is
-- required, and it is still permissive of the NULLs that rows predating 2.5
-- carry, so it adds a constraint on no existing row.
--
-- 0006's partial index is deliberately RETAINED rather than dropped. The full
-- index is a superset of its constraint -- both permit many NULLs and neither
-- permits a repeated non-NULL -- so dropping it would remove a constraint
-- recorded by an already-applied migration for no gain. Migrations here are
-- forward-only, and relaxing one is a larger decision than this round makes.
BEGIN;

CREATE UNIQUE INDEX IF NOT EXISTS observations_source_fact_full
    ON observations(source_fact_id);

-- ---------------------------------------------------------------- the table
--
-- The reading payload is exactly the three fields a 2.53 correction changes.
-- `value`, `period`, `metric`, `available_at` and `replay_eligible_from` are
-- deliberately absent: they belong to the source fact and stay in
-- `observations`, so an interpretation cannot shadow or restate them.
--
-- `identity` is the 2.59 content-derived key over
-- (source_fact_id, knowledge_at, interpretation). UNIQUE on it is what makes a
-- repeated insertion a read rather than a second row, and it excludes any
-- free-text rendering from identity.

-- No backfill. The archive gains the ability to record a corrected reading and
-- nothing else; the 2.53 repair is applied in a later round, on purpose, once
-- the semantics have been exercised against real data rather than only against
-- a prototype.

-- ---------------------------------------------------------------- atomicity
--
-- The explicit transaction is load-bearing, not decoration. Python's
-- `executescript` issues a COMMIT before it runs a script, so a migration
-- written as bare statements is applied one autocommitted statement at a time.
-- A failure half-way through then leaves the earlier statements committed with
-- no `schema_migrations` row claiming them -- a schema state no migration
-- describes and no later run will reconcile. Verified, not assumed: a
-- deliberately broken copy of this migration left the `interpretations` table
-- behind until the transaction was added.
--
-- SQLite DDL is transactional, so this holds for CREATE TABLE and CREATE INDEX
-- as well as for rows. No statement in this migration may open a transaction of
-- its own, and none may be one SQLite cannot run inside one.

CREATE TABLE IF NOT EXISTS interpretations (
    interpretation_id TEXT PRIMARY KEY,
    source_fact_id    TEXT NOT NULL
        REFERENCES observations(source_fact_id),
    -- NOT NULL and named apart from every availability column on purpose: the
    -- two axes must never be substitutable for one another.
    knowledge_at      TEXT NOT NULL,
    unit              TEXT NOT NULL,
    currency          TEXT,
    currency_basis    TEXT NOT NULL,
    identity          TEXT NOT NULL UNIQUE,
    -- An explicit link to the preceding reading of the SAME source fact. The
    -- self-reference is the only cross-row check SQLite can make here; that the
    -- target shares this source_fact_id, precedes this row and is the
    -- immediately preceding reading are cross-row conditions SQLite cannot
    -- express, and they are enforced by the domain validators instead. This
    -- migration does not pretend a CHECK constraint could do it.
    supersedes        TEXT REFERENCES interpretations(interpretation_id),
    created_at        TEXT NOT NULL
);

-- Effective selection: the greatest `knowledge_at` at or before a cutoff.
CREATE INDEX IF NOT EXISTS interpretations_effective
    ON interpretations(source_fact_id, knowledge_at DESC);

-- Supersedes lookup. The self-reference needs no index of its own to be
-- enforceable, but a chain walk and any future integrity check read by
-- `supersedes`, and an index that exists only for that is not speculative.
CREATE INDEX IF NOT EXISTS interpretations_supersedes
    ON interpretations(supersedes);

-- An interpretation is a statement about what ST-EVA knew at an instant. Editing
-- or removing one would leave the archive asserting something it can no longer
-- support, exactly as for observations and context snapshots. A correction is an
-- INSERT that supersedes, never an UPDATE.
CREATE TRIGGER IF NOT EXISTS interpretations_no_update
BEFORE UPDATE ON interpretations
BEGIN
    SELECT RAISE(ABORT, 'interpretations are append-only');
END;

CREATE TRIGGER IF NOT EXISTS interpretations_no_delete
BEFORE DELETE ON interpretations
BEGIN
    SELECT RAISE(ABORT, 'interpretations are append-only');
END;

COMMIT;