-- ST-EVA 2.33 (migration 0016) - metric supersession, and the rename of `debt`.
--
-- The product decision is settled: Core `debt` denotes **long-term debt**, the
-- current plus non-current portions of it, and is renamed `long_term_debt`.
-- `total_debt` is a future semantic candidate and is deliberately NOT created.
--
-- What made this more than a rename: **the sealed 2.2.3 archive holds 180
-- observations recorded under `metric = 'debt'`**, and there are thousands more in
-- the working corpora. `observations.metric` is part of the contract id, so
-- rewriting those rows would change `observation_id` and manufacture new
-- historical Evidence out of a naming decision.
--
-- So the rename is a **semantic migration recorded alongside the old name**, not
-- an edit to the rows that carry it. Historical observations keep the metric id
-- they were archived under, byte for byte. What changes is the question "what does
-- this metric denote", and that is answered by following the supersession chain to
-- the successor that carries the decision.
--
--     observation.metric = 'debt'        -- unchanged, forever
--     metric_supersession: debt -> long_term_debt
--     metric_registry: 'debt' SUPERSEDED, 'long_term_debt' ACTIVE
--
-- Append-only, and enforced as such: a supersession is a decision that was taken
-- once, with a reason and the evidence it rested on. Rewriting one would rewrite
-- history, which is the exact failure this migration exists to avoid. The
-- no-update and no-delete triggers are the same ones every other immutable table
-- in this schema carries.
--
-- `scope` records why this row exists rather than only what it points at, because
-- the reason is what a reader needs in order to judge whether the successor is
-- still the right target.

CREATE TABLE IF NOT EXISTS metric_supersession (
    predecessor_id TEXT NOT NULL REFERENCES metric_registry(metric_id),
    successor_id   TEXT NOT NULL REFERENCES metric_registry(metric_id),
    decided_at     TEXT NOT NULL,
    -- Why the successor is the right semantic target. Not a restatement of the
    -- successor's own definition, which lives in `metric_registry`; this is the
    -- argument that connects the two names.
    reason         TEXT NOT NULL,
    -- What the decision rested on, as an identifier a reader can go and check.
    evidence       TEXT,
    recorded_at    TEXT NOT NULL,
    PRIMARY KEY (predecessor_id, successor_id),
    -- A name cannot be superseded by itself, and two metrics cannot share a
    -- successor in this direction: a chain is a chain, and a fork would make
    -- resolution ambiguous.
    CHECK (predecessor_id <> successor_id)
);

CREATE TRIGGER IF NOT EXISTS metric_supersession_no_update
BEFORE UPDATE ON metric_supersession
BEGIN
    SELECT RAISE(ABORT, 'metric supersession is append-only');
END;

CREATE TRIGGER IF NOT EXISTS metric_supersession_no_delete
BEFORE DELETE ON metric_supersession
BEGIN
    SELECT RAISE(ABORT, 'metric supersession is append-only');
END;

-- The decision this migration exists for is recorded by `registry_seed.seed()`,
-- not here. The supersession references `metric_registry` rows, and a migration
-- runs before any seed has created them -- so inserting the row here would fail
-- the foreign key on a fresh archive. The table and its triggers are the
-- migration's job; the decision is the registry's.
--
-- For the record, and because it is the reason the table exists:
--
--   `debt` said "Total debt" while its four declared components summed, by value
--   arithmetic across three filers, to `us-gaap:LongTermDebt` -- a quantity
--   excluding short-term borrowings and capital leases by the SEC's own
--   description of each concept. So the name, the components and the definition
--   each named a different quantity, and the definition was circular so it could
--   not adjudicate. The components are what filers actually report, so the metric
--   adopts them and the name follows.
--
-- `total_debt` is deliberately not created. It is unestablished, not refuted.