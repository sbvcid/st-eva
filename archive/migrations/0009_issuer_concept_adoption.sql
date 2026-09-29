-- ST-EVA 2.5.1 - issuer concept adoption.
--
-- The problem this exists to fix, stated as a schema question.
--
-- `metric_concept_mapping` answers "under what conditions does this concept
-- stand for this metric". Its `effective_from` / `effective_to` window was
-- seeded from AAPL. But a window on a *concept* is a claim about the filer who
-- was observed, not about the concept:
--
--     us-gaap:Revenues  maps to  revenue,  window 2016-09-24 -> 2018-09-29
--
-- and the real filings say:
--
--     AAPL   2016-09-24 -> 2018-09-29     (matches, by construction)
--     MSFT   2007-09-30 -> 2010-12-31     (nine years before the window opens)
--     NVDA   2008-01-27 -> 2026-07-26     (still filing, eight years after it
--                                          closes)
--
-- So one row was carrying two different claims: a semantic one about the
-- concept, and an empirical one about one company's filing history. Widening
-- the window to cover MSFT and NVDA would have "fixed" the symptom by deleting
-- the distinction, and would have made the window look authoritative when it is
-- in fact a single company's observation wearing a general rule's clothes.
--
-- The separation is:
--
--     metric_concept_mapping   what a concept means, and how faithfully
--     issuer_concept_adoption  when one filer was observed using it
--
-- Adoption is evidence, and it says so. It is derived from the periods that
-- filer's own filings actually reported, which is a lower and weaker claim than
-- "this filer stopped using this concept": absence of a fact is not a decision
-- to stop, and a filer that stopped in 2018 may well be holding it dormant
-- rather than having retired it. The `basis` column is closed by trigger for
-- the same reason every other vocabulary in this archive is closed, because an
-- undeclared basis would make "how much do we actually know here?"
-- unanswerable.

CREATE TABLE IF NOT EXISTS issuer_concept_adoption (
    asset_id     TEXT NOT NULL REFERENCES assets(asset_id),
    concept_id   TEXT NOT NULL,
    -- The first period this filer was *observed* reporting, and the last. Both
    -- are observations and neither is a claim about intent.
    first_used   TEXT,
    last_used    TEXT,
    -- How many facts and how many filings produced the observation. A window
    -- derived from two facts and one derived from two hundred are not the same
    -- kind of claim, and the difference is visible rather than implied.
    fact_count   INTEGER NOT NULL DEFAULT 0,
    filing_count INTEGER NOT NULL DEFAULT 0,
    basis        TEXT NOT NULL DEFAULT 'OBSERVED_ADOPTION',
    first_seen_at TEXT,
    last_seen_at  TEXT,
    PRIMARY KEY (asset_id, concept_id)
);

CREATE INDEX IF NOT EXISTS issuer_concept_adoption_recent
    ON issuer_concept_adoption(asset_id, last_used);

-- The basis is closed. `OBSERVED_ADOPTION` means "the periods this filer's own
-- filings reported this concept", and nothing else. It is not the taxonomy's
-- validity period, not a statement that the filer intends to stop, and not a
-- claim about any other filer.
CREATE TRIGGER IF NOT EXISTS issuer_concept_adoption_basis_vocabulary
BEFORE INSERT ON issuer_concept_adoption
WHEN NEW.basis NOT IN ('OBSERVED_ADOPTION')
BEGIN
    SELECT RAISE(ABORT, 'adoption basis must be OBSERVED_ADOPTION');
END;

CREATE TRIGGER IF NOT EXISTS issuer_concept_adoption_basis_vocabulary_update
BEFORE UPDATE OF basis ON issuer_concept_adoption
WHEN NEW.basis NOT IN ('OBSERVED_ADOPTION')
BEGIN
    SELECT RAISE(ABORT, 'adoption basis must be OBSERVED_ADOPTION');
END;

-- An adoption record without a concept is a fact about nothing. And a
-- qualified concept, because an unqualified one is the ambiguity the registry
-- exists to remove.
CREATE TRIGGER IF NOT EXISTS issuer_concept_adoption_concept_shape
BEFORE INSERT ON issuer_concept_adoption
WHEN NEW.concept_id IS NULL OR NEW.concept_id NOT LIKE '%:%'
BEGIN
    SELECT RAISE(ABORT, 'adoption concept_id must be qualified as taxonomy:concept');
END;

-- A window that ends before it starts is not a window.
CREATE TRIGGER IF NOT EXISTS issuer_concept_adoption_window_ordered
BEFORE INSERT ON issuer_concept_adoption
WHEN NEW.first_used IS NOT NULL AND NEW.last_used IS NOT NULL
     AND NEW.last_used < NEW.first_used
BEGIN
    SELECT RAISE(ABORT, 'adoption last_used cannot precede first_used');
END;
