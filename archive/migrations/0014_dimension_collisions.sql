-- ST-EVA 2.21 - dimension collisions, at the grain the decision needs.
--
-- The problem this exists to fix, stated as a schema question.
--
-- `_store_facts` has counted a `dimension collision` since 2.11: one concept, one
-- period, one unit, two different values. That is the right detection -- an
-- aggregated endpoint such as `companyfacts` drops the dimensional axis, so two
-- facts that differ only by member arrive looking like one fact. But the count
-- was per run and per issuer, printed in the ingestion report and nowhere else:
--
--     eight bank filers, 404 collisions, 133 of them BBAR
--
-- which is useless at the moment it matters. Deciding whether a bank reports a
-- gross profit is a question about *a metric*, and the number that would answer
-- it is filed one level above where the question lives. A reader asking
-- "is BBAR's gross profit usable evidence?" has no way to learn that 133 of this
-- filer's facts arrived dimension-flattened, while NRIM -- one genuine
-- counterexample to the same rule -- sits under the same number.
--
-- So the count is persisted per event, with the metric, the concept, the filing
-- and the period attached:
--
--     ingestion_dimension_collisions
--         run_id, asset_id, metric_id, concept_id
--         accession, period_start, period_end, unit
--         distinct_values
--         collision_kind
--
-- `collision_kind` is closed by trigger, like every other vocabulary here,
-- because the useful answer to "why are these numbers ambiguous" is not the
-- count. There are two kinds, and the second one exists because writing a third
-- was wrong.
--
--     SAME_PERIOD_DIFFERENT_VALUE   one filing reported two values for one
--                                  period. A member was hidden by the endpoint.
--                                  Provable from this source.
--     LATER_FILING_DIFFERS          an earlier filing and a later one reported
--                                  different values for one period, each filing
--                                  reporting one value. Observable.
--
-- The obvious third member was `RESTATED_SAME_PERIOD`, and it was removed after
-- measurement. It asserted that the second case is an ordinary revision, and the
-- aggregated endpoint **cannot support that claim**: the dimensional axis was
-- dropped before ingestion saw anything, so "this filer revised the number" and
-- "these are two different members reported in two filings" are the same
-- observation. BBAR tags `ifrs-full:GrossProfit` for 2019 as 88.8bn, 120.9bn
-- and 182.5bn in three successive 20-F filings. A restatement does not move a
-- number by 36% and then by 51%; but nothing in what was fetched can prove it was
-- not, because the member axis that would say so is not in the document.
--
-- So the kind says what was seen and not what it means, and a consumer that wants
-- to distinguish a revision from a hidden member has to say so at a source that
-- still has the axis -- which is `companyconcept`, not `companyfacts`.
--
-- Nothing is deleted and nothing is excluded. The collision is recorded and the
-- facts stay, because 2.19 settled that a coverage interpretation is not a
-- deletion filter -- and the same reasoning applies here with more force: a
-- dimension-flattened fact is still a fact the filer published. What this table
-- buys is that a consumer can tell the difference between eighteen comparable
-- values and eighteen members of one period, which is the difference between a
-- counterexample and an artefact.
--
-- Keyed on (run_id, asset_id, metric_id, concept_id, period_start, period_end,
-- unit) so a rerun over the same window is idempotent, and a rerun over a wider
-- window adds rows rather than overwriting.

CREATE TABLE IF NOT EXISTS ingestion_dimension_collisions (
    run_id       TEXT NOT NULL REFERENCES ingestion_runs(run_id),
    asset_id     TEXT NOT NULL REFERENCES assets(asset_id),
    metric_id    TEXT NOT NULL,
    concept_id   TEXT NOT NULL,
    -- The filing the colliding facts came from, when they came from different
    -- ones. A restatement across two accessions is the ordinary case and is
    -- recorded as such rather than being flattened into one row.
    accession    TEXT,
    period_start TEXT,
    period_end   TEXT,
    unit         TEXT,
    -- How many distinct values were seen for this key. Two means a member was
    -- hidden; a growing count means the endpoint is hiding more than one axis.
    distinct_values INTEGER NOT NULL DEFAULT 2,
    -- Closed vocabulary; see above for why each member calls for a different
    -- response rather than a different warning level.
    collision_kind TEXT NOT NULL CHECK (collision_kind IN (
        'SAME_PERIOD_DIFFERENT_VALUE',
        'LATER_FILING_DIFFERS'
    )),
    detected_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ingestion_dimension_collisions_metric
    ON ingestion_dimension_collisions(asset_id, metric_id);
CREATE INDEX IF NOT EXISTS ingestion_dimension_collisions_concept
    ON ingestion_dimension_collisions(concept_id);
-- The same point, declared once, where it belongs.
--
-- Everything above is about how an *endpoint represents facts*, and it is
-- therefore a property of the source rather than of any metric. Measured across
-- eight bank filers: `gross_profit` had 11 affected keys, `operating_cash_flow`
-- 67, and `equity` more extra values per key than `gross_profit`. Without this
-- the natural reading is "gross_profit is weird" and the obvious next step is a
-- list of metric-specific exceptions, which would be a property of the accident
-- rather than of the data.
--
--     source fact
--         ↓
--     does the endpoint retain the dimensional axis?
--         ↓
--     no  → ambiguity may attach, and is recorded per event
--
-- Every endpoint this project uses is AGGREGATE: `companyfacts` drops the member
-- axis and `companyconcept` is per-concept over the same flattened view. So the
-- declaration is recorded rather than inferred, because a source that kept its
-- axes would need it, and because "we checked" is not the same claim as "we
-- assumed".

ALTER TABLE sources ADD COLUMN retains_dimensions TEXT
    CHECK (retains_dimensions IS NULL OR retains_dimensions IN ('AGGREGATE', 'NONE'));

ALTER TABLE sources ADD COLUMN aggregation_note TEXT;
