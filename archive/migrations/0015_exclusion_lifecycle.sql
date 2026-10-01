-- ST-EVA 2.25 - applicability exclusions as a hypothesis layer.
--
-- The problem this exists to fix, stated as a schema question.
--
-- `metric_inapplicable_in` was one table with two jobs. It held which business
-- models a metric was *ruled out for*, and it had nowhere to record how much
-- evidence that ruling rested on. So a proposition and a refusal were the same
-- row, and four refusals written in 2.7 from category intuition sat there
-- indistinguishable from a fact:
--
--     gross_profit     x BANK              refuted by NRIM,   22 obs
--     r_and_d          x MINING            refuted by NEM,   236 obs
--     gross_profit     x FINANCE_SERVICES  refuted by 3 of 7, 39 obs
--     operating_income x FINANCE_SERVICES  refuted by 6 of 7, 666 obs
--
-- Removing them left the question that was underneath the whole problem: **a rule
-- whose state is `TESTABLE` had been holding production authority.** It was
-- refusing Evidence collection with no affirmative basis, which is the same defect
-- as a screening heuristic wearing a rule's clothes -- and the one difference is
-- that this one also edited the archive's coverage surface.
--
-- So the two jobs are separated:
--
--     metric_exclusion       a proposition and its evidence state. Recorded
--                            whatever the state. Carries the falsifiable claim,
--                            so "why was this proposed" survives.
--     metric_inapplicable_in the refusal surface. A row here means the metric is
--                            actually NOT_APPLICABLE and its evidence is not
--                            collected. Only a SUPPORTED proposition reaches it.
--
-- The consequence, and it is the point of the whole exercise: **with no SUPPORTED
-- exclusion anywhere, the refusal surface is empty.** Not as a loss -- as the
-- finding that ST-EVA's first generation of applicability rules was, in four
-- cases out of four, unsupported by evidence.
--
-- `state` is closed by trigger for the reason every vocabulary here is. The
-- distinction the table is drawing is the one that cannot be recovered
-- afterwards, because `TESTABLE` and `SUPPORTED` look identical in a coverage
-- report and mean opposite things: the first is a hypothesis, the second is a
-- refusal.
--
-- Nothing is deleted. `metric_inapplicable_in` is emptied and `metric_exclusion`
-- is populated, so the hypotheses remain queryable and the refusal surface no
-- longer depends on their existence.

CREATE TABLE IF NOT EXISTS metric_exclusion (
    metric_id     TEXT NOT NULL REFERENCES metric_registry(metric_id),
    business_model TEXT NOT NULL,
    state         TEXT NOT NULL CHECK (state IN (
        -- Declared; no filer of this class has been collected at full Core scope.
        'PROPOSED',
        -- A filer of this class exists and has been collected; no counterexample
        -- found. **Consistency with silence is not affirmative support.**
        'TESTABLE',
        -- An affirmative evidentiary basis, named. The only state with
        -- production authority over Evidence collection.
        'SUPPORTED',
        -- A filer of this class contradicts it. Must not serve as a refusal.
        'REFUTED',
        -- The replacement proposition has not been established. Does not mean the
        -- old rule may continue to exist.
        'UNDECIDED'
    )),
    -- The falsifiable claim, stated before the test rather than after it. Kept
    -- because a rule that cannot say what would refute it cannot be refuted, and
    -- one that never says what would support it cannot be supported.
    proposition   TEXT,
    -- Who contradicted it: a ticker, the concept, and how many observations.
    -- This is the record that makes REFUTED irreversible, so it is structured
    -- rather than left in prose.
    refuted_by_ticker    TEXT,
    refuted_by_concept   TEXT,
    refuted_by_observations INTEGER,
    -- What evidence would be enough, decided in advance. Empty is a smell.
    support_basis   TEXT,
    recorded_at   TEXT NOT NULL,
    PRIMARY KEY (metric_id, business_model)
);

-- Created here rather than left to the registry's lazy `CREATE TABLE IF NOT
-- EXISTS`. The two statements below read and write this table during the
-- migration, and a table that exists only once something has tried to write to it
-- is not there to be read. Making it part of the schema also means the refusal
-- surface is versioned like everything else rather than appearing whenever a
-- metric happened to be declared inapplicable.
CREATE TABLE IF NOT EXISTS metric_inapplicable_in (
    metric_id      TEXT NOT NULL REFERENCES metric_registry(metric_id),
    business_model TEXT NOT NULL,
    PRIMARY KEY (metric_id, business_model)
);

-- Any row already in the refusal surface predates this table and therefore
-- predates any evidence claim for it. Carried over as `TESTABLE` -- which is the
-- honest reading of a rule that was written in 2.7 and never tested, and the
-- state that carries no production authority.
INSERT OR IGNORE INTO metric_exclusion
    (metric_id, business_model, state, proposition, recorded_at)
SELECT metric_id, business_model, 'TESTABLE',
       'carried over from the pre-lifecycle refusal surface; no evidence claim '
       'was ever recorded for it',
       '2026-10-01T00:00:00+00:00'
FROM metric_inapplicable_in;

-- The refusal surface is now only what `SUPPORTED` authorises.
DELETE FROM metric_inapplicable_in;