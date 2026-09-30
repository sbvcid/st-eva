-- ST-EVA 2.8 - coverage semantics: what was asked, and what was declined.
--
-- Two records, and both exist because a question could not be answered from the
-- archive rather than because a feature was wanted.
--
-- ------------------------------------------------------------------
-- 1. ingestion_scope
-- ------------------------------------------------------------------
--
-- "This metric has no observations" is a sentence with at least three different
-- meanings, and 2.7 could not tell them apart:
--
--     we never asked                      the registry maps nothing we queried
--     we asked and the filer was silent    the concept endpoint returned nothing
--     we asked and it returned, but        deduplicated away, or the mapping
--     the rows were not kept              window excludes every held period
--
-- `ingestion_runs` records what a run *did* -- filings seen, documents stored,
-- facts kept -- and nothing about what it was *for*. So all three collapsed into
-- one number, and a coverage figure built on it says "we have none" about a
-- metric nobody had looked for.
--
-- The distinction is the difference between "ST-EVA does not cover this" and
-- "ST-EVA has not got to this", and only the second is a backlog item. This
-- table is the record that separates them: one row per metric per run, with the
-- scope that was requested and what came back.
--
-- Recorded per run and not per issuer because a run's scope is what it was. A
-- later run that widens the scope does not erase that an earlier one did not,
-- and the union across runs is the honest answer to "have we ever looked".
--
-- ------------------------------------------------------------------
-- 2. declined_concept_mappings
-- ------------------------------------------------------------------
--
-- 2.7 declined nine IFRS concepts and recorded why, in prose, in the seed file.
-- A reader of the archive could see what ST-EVA held and not what it had
-- considered and rejected -- and with 3.0% of a filer's concepts collected, the
-- difference between "not collected" and "declined on purpose" is most of what
-- a coverage claim has to be honest about.
--
-- A decline is a *positive* act: someone looked at a source concept, worked out
-- which metric it might express, and concluded it does not. That conclusion is
-- worth more than the mapping it replaces, because it is the difference between
-- a metric ST-EVA has no opinion about and one it has an opinion about.
--
-- Keyed on (concept, metric considered) rather than on the concept alone,
-- because the interesting declines are *near misses*: a concept that expresses
-- almost the right thing is the one worth recording, and keying on the concept
-- would lose the metric it was nearly good enough for.
--
-- It is a concept-and-metric record, not a per-issuer one, on purpose. "This
-- element measures continuing operations" is a fact about the element and does
-- not become true or false per company. A per-issuer decline would multiply one
-- decision by the number of filers and invite a reader to think a framework
-- judgement had been made separately for each of them.
--
-- The reason vocabulary is closed for the same reason every other one here is:
-- "how much do we actually know here?" has to be answerable from the row. The
-- codes are the distinction the phase was written to preserve, and
-- COMPONENT_OF is the one that matters most: it says the concept is a part of
-- the metric rather than the metric itself, which is the difference between
-- omitting it and mistaking it for the whole.

CREATE TABLE IF NOT EXISTS ingestion_scope (
    run_id       TEXT NOT NULL REFERENCES ingestion_runs(run_id),
    asset_id     TEXT NOT NULL REFERENCES assets(asset_id),
    metric_id    TEXT NOT NULL,
    -- How many declared source mappings this metric had at the time of the run.
    -- Zero is a real and common answer, and it is what "we never asked" looks
    -- like from the outside.
    mapping_count INTEGER NOT NULL DEFAULT 0,
    -- Whether the run actually reached the source for this metric. A run that
    -- returned early because nothing was new has asked nothing, and must not be
    -- recorded as having looked and found silence.
    attempted    INTEGER NOT NULL DEFAULT 0,
    observations_stored INTEGER NOT NULL DEFAULT 0,
    status       TEXT NOT NULL,
    PRIMARY KEY (run_id, metric_id)
);

CREATE INDEX IF NOT EXISTS ingestion_scope_by_asset
    ON ingestion_scope(asset_id, metric_id);

-- What came back, closed so that "no answer" is distinguishable from "an
-- answer we have not parsed yet". SOURCE_SILENT means the concept endpoint
-- returned nothing for this filer, which is a fact about the filer; NO_MAPPING
-- means the registry had no concept to ask about, which is a fact about us.
CREATE TRIGGER IF NOT EXISTS ingestion_scope_status_vocabulary
BEFORE INSERT ON ingestion_scope
WHEN NEW.status NOT IN (
    'INGESTED', 'SOURCE_SILENT', 'NO_MAPPING', 'NOT_ATTEMPTED', 'ERROR'
)
BEGIN
    SELECT RAISE(ABORT, 'ingestion_scope.status is outside the closed vocabulary');
END;

CREATE TRIGGER IF NOT EXISTS ingestion_scope_status_vocabulary_update
BEFORE UPDATE OF status ON ingestion_scope
WHEN NEW.status NOT IN (
    'INGESTED', 'SOURCE_SILENT', 'NO_MAPPING', 'NOT_ATTEMPTED', 'ERROR'
)
BEGIN
    SELECT RAISE(ABORT, 'ingestion_scope.status is outside the closed vocabulary');
END;

CREATE TABLE IF NOT EXISTS declined_concept_mappings (
    concept_id            TEXT NOT NULL,
    -- The metric this concept was weighed against. The near-miss is the
    -- interesting case, so the metric it nearly matched is part of the record
    -- and not something to be inferred.
    considered_for_metric TEXT NOT NULL,
    reason_code           TEXT NOT NULL,
    reason                TEXT,
    -- Which framework reading produced it, so a decline about an IFRS element is
    -- not read as a claim about the US-GAAP one. Null when the judgement does
    -- not depend on the framework.
    framework_basis       TEXT,
    recorded_at           TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS declined_concept_mappings_unique
    ON declined_concept_mappings(concept_id, considered_for_metric);

-- The reason codes, and what each one claims. Closed, because a free-text reason
-- in a coverage ledger is a comment with a foreign key on it.
--
--   COMPONENT_OF            a part of the metric, not the metric itself
--   WIDER_AGGREGATE         the metric plus other income or other holders
--   NARROWER_AGGREGATE      a part of the metric
--   DIFFERENT_QUANTITY      measures something else, with a stated qualifier
--   IDENTITY_MISMATCH       counts a different population than the metric names
--   NOT_A_METRIC            a line, an amount or a rate, not a measurement of
--                            any semantic metric
CREATE TRIGGER IF NOT EXISTS declined_concept_mappings_reason_vocabulary
BEFORE INSERT ON declined_concept_mappings
WHEN NEW.reason_code NOT IN (
    'COMPONENT_OF', 'WIDER_AGGREGATE', 'NARROWER_AGGREGATE',
    'DIFFERENT_QUANTITY', 'IDENTITY_MISMATCH', 'NOT_A_METRIC'
)
BEGIN
    SELECT RAISE(ABORT, 'decline reason_code is outside the closed vocabulary');
END;

CREATE TRIGGER IF NOT EXISTS declined_concept_mappings_reason_vocabulary_update
BEFORE UPDATE OF reason_code ON declined_concept_mappings
WHEN NEW.reason_code NOT IN (
    'COMPONENT_OF', 'WIDER_AGGREGATE', 'NARROWER_AGGREGATE',
    'DIFFERENT_QUANTITY', 'IDENTITY_MISMATCH', 'NOT_A_METRIC'
)
BEGIN
    SELECT RAISE(ABORT, 'decline reason_code is outside the closed vocabulary');
END;

-- A concept is qualified, for the same reason every other concept id is: an
-- unqualified one is the ambiguity the registry exists to remove, and a decline
-- recorded against "Revenue" rather than "ifrs-full:Revenue" would not say which
-- framework's revenue.
CREATE TRIGGER IF NOT EXISTS declined_concept_mappings_concept_shape
BEFORE INSERT ON declined_concept_mappings
WHEN NEW.concept_id IS NULL OR NEW.concept_id NOT LIKE '%:%'
BEGIN
    SELECT RAISE(ABORT, 'decline concept_id must be qualified as taxonomy:concept');
END;

-- A decline with no reason is an omission wearing a decision's clothes. The
-- code says which category; the sentence says why this one, and a reader
-- deciding whether to disagree needs the second.
CREATE TRIGGER IF NOT EXISTS declined_concept_mappings_requires_reason
BEFORE INSERT ON declined_concept_mappings
WHEN NEW.reason IS NULL OR TRIM(NEW.reason) = ''
BEGIN
    SELECT RAISE(ABORT, 'a decline must state why, not only which category');
END;
