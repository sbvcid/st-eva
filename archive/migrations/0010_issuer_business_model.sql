-- ST-EVA 2.7 - issuer business model.
--
-- The problem this exists to fix, stated as a schema question.
--
-- `metric_inapplicable_in` is keyed by business model:
--
--     operating_income   NOT_APPLICABLE  in  BANK
--     r_and_d            NOT_APPLICABLE  in  MINING
--
-- and its own column comment says the right thing about why: "It is recorded
-- only when a business model is actually excluded; an empty list stays empty,
-- and never stands in for a retrieval that found nothing."
--
-- That rule was enforceable and completely unreachable. Nothing in the archive
-- said which business model an *issuer* was in. The table had a column no row
-- could fill, and the consequence was worse than a missing feature: asked for
-- an operating-income figure for a financial institution, the query surface had
-- to fall through to its evidence fallback and answer
--
--     UNAVAILABLE / RETRIEVAL_FAILED
--
-- which says "our last attempt failed" about a line that does not exist for
-- that kind of company. The metric was correctly declared inapplicable and the
-- declaration could not be reached, so the archive reported a retrieval failure
-- as though the metric were applicable and merely unfound. That is precisely
-- the collapse between applicability and availability that this round exists to
-- keep apart, and it was not a gap in the rule -- it was a gap in the wiring.
--
-- The fix is a link, not a new vocabulary of companies:
--
--     metric_inapplicable_in   which metrics do not exist for which business
--     issuer_business_model    which business each issuer is in
--
-- The second is *issuer metadata*, deliberately not a column on `assets` and
-- deliberately not a property of any metric. A metric's meaning does not vary
-- by company; which line of a filing a company uses does, and that already has
-- a home in `issuer_concept_adoption`. Adding a company to a metric definition
-- would put the two back together, which is the mistake 2.5.1 removed.
--
-- `basis` is closed by trigger, for the same reason `issuer_concept_adoption`'s
-- is and for the same substantive reason: a reader has to be able to answer "how
-- much do we actually know here?" from the row rather than from a comment.
--
--     DECLARED_BY_ISSUER            the filer publishes this classification
--     DERIVED_FROM_REPORTED_CONCEPTS  read off the concepts the issuer reports
--     MANUAL_CLASSIFICATION          a person decided, and that is the weakest
--
-- A declared classification is the strongest of the three and is the one an SEC
-- filer always has: the SIC code is part of the filer's own submission. It is
-- not a judgement about the company made by somebody who wanted a metric to come
-- out inapplicable, and it is exactly the kind of claim that can be checked by
-- anyone with the same filing.

CREATE TABLE IF NOT EXISTS issuer_business_model (
    asset_id       TEXT PRIMARY KEY REFERENCES assets(asset_id),
    business_model TEXT NOT NULL,
    -- Why this issuer is in that model. Closed below, and the whole point of
    -- closing it is that "we classified it ourselves, informally" and "the
    -- filer says so" must never read the same in a row.
    basis          TEXT NOT NULL DEFAULT 'MANUAL_CLASSIFICATION',
    -- The source that carries the classification: a filer category, an SIC
    -- code, a note. Kept verbatim so a reader can go and look at the same
    -- thing this was derived from.
    source         TEXT,
    recorded_at    TEXT
);

-- One model per issuer, and the vocabulary is closed. `REIT` and `INSURANCE`
-- already existed in the metric side without an issuer ever using them, and that
-- is correct: a metric may be declared inapplicable for a business nobody in
-- the archive happens to be. The reverse is not true, and an issuer classified
-- into a model nothing has been declared against is how a metric silently
-- becomes applicable again.
CREATE TRIGGER IF NOT EXISTS issuer_business_model_vocabulary
BEFORE INSERT ON issuer_business_model
WHEN NEW.business_model NOT IN (
    'OPERATING', 'MANUFACTURING', 'TECHNOLOGY', 'FINANCE_SERVICES',
    'BANK', 'INSURANCE', 'REIT', 'MINING'
)
BEGIN
    SELECT RAISE(ABORT, 'business model is not in the closed vocabulary');
END;

CREATE TRIGGER IF NOT EXISTS issuer_business_model_vocabulary_update
BEFORE UPDATE OF business_model ON issuer_business_model
WHEN NEW.business_model NOT IN (
    'OPERATING', 'MANUFACTURING', 'TECHNOLOGY', 'FINANCE_SERVICES',
    'BANK', 'INSURANCE', 'REIT', 'MINING'
)
BEGIN
    SELECT RAISE(ABORT, 'business model is not in the closed vocabulary');
END;

CREATE TRIGGER IF NOT EXISTS issuer_business_model_basis_vocabulary
BEFORE INSERT ON issuer_business_model
WHEN NEW.basis NOT IN (
    'DECLARED_BY_ISSUER', 'DERIVED_FROM_REPORTED_CONCEPTS',
    'MANUAL_CLASSIFICATION'
)
BEGIN
    SELECT RAISE(ABORT, 'business model basis is not in the closed vocabulary');
END;

CREATE TRIGGER IF NOT EXISTS issuer_business_model_basis_vocabulary_update
BEFORE UPDATE OF basis ON issuer_business_model
WHEN NEW.basis NOT IN (
    'DECLARED_BY_ISSUER', 'DERIVED_FROM_REPORTED_CONCEPTS',
    'MANUAL_CLASSIFICATION'
)
BEGIN
    SELECT RAISE(ABORT, 'business model basis is not in the closed vocabulary');
END;

-- A business model with no evidence behind it is a guess, and a guess that
-- silently removes metrics from a company's coverage is the one kind of guess
-- that must not be stored without saying so. The basis column already says so;
-- this refuses a row that says it in a way nobody can check.
CREATE TRIGGER IF NOT EXISTS issuer_business_model_requires_source
BEFORE INSERT ON issuer_business_model
WHEN NEW.basis IN ('DECLARED_BY_ISSUER', 'DERIVED_FROM_REPORTED_CONCEPTS')
 AND (NEW.source IS NULL OR TRIM(NEW.source) = '')
BEGIN
    SELECT RAISE(ABORT, 'a declared or derived business model must name the source it came from');
END;
