-- ST-EVA 2.5.3 - filing identity and source-fact identity.
--
-- Two things an observation could not previously be indexed on:
--
--   concept, taxonomy, accession, form, fiscal period, statement, instant
--       were all parsed correctly, and all of them lived inside `raw`. A query
--       cannot reach into raw, so the answer to "where does this come from"
--       was not answerable at the index level.
--
--   source_fact_id
--       is the identity of one raw fact inside one source document. It is what
--       deduplication is allowed to use, and it is deliberately NOT the
--       observation's identity across sources.

-- `concept` is NOT added here: 0001 already carries it on `observations`,
-- and this migration must stay additive against whatever shipped.

ALTER TABLE observations ADD COLUMN taxonomy      TEXT;
ALTER TABLE observations ADD COLUMN accession     TEXT;
ALTER TABLE observations ADD COLUMN form          TEXT;
ALTER TABLE observations ADD COLUMN fiscal_year   INTEGER;
ALTER TABLE observations ADD COLUMN fiscal_period TEXT;
ALTER TABLE observations ADD COLUMN statement     TEXT;
-- Explicit rather than inferred from period_start IS NULL, because "this is a
-- balance-sheet date" is a statement about the filer and not a side-effect of
-- how a period happened to be serialised.
ALTER TABLE observations ADD COLUMN instant       INTEGER;
ALTER TABLE observations ADD COLUMN source_fact_id TEXT;

CREATE INDEX IF NOT EXISTS observations_concept
    ON observations(asset_id, concept, period_end);
CREATE INDEX IF NOT EXISTS observations_filing
    ON observations(accession);
CREATE INDEX IF NOT EXISTS observations_statement
    ON observations(asset_id, statement, period_end);

-- The deduplication rule, enforced by the database rather than by discipline.
--
-- UNIQUE on (source_fact_id) means the same raw fact in the same document is
-- stored once, however many times it is parsed. NULL is excluded from the
-- constraint, so every row that predates 2.5 stays insertable and untouched.
--
-- Note what is NOT here: there is no uniqueness on concept, value or period
-- across sources. Two sources reporting the same number must remain two
-- observations, because collapsing them would delete the only record that two
-- independent readings existed, and with it the 2.3-B validation model. That
-- rule is an acceptance criterion, not just a comment: after any 2.5 ingestion
-- two sources reporting the same number still produce two observations and one
-- validation record.
CREATE UNIQUE INDEX IF NOT EXISTS observations_source_fact
    ON observations(source_fact_id)
    WHERE source_fact_id IS NOT NULL;
