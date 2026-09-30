-- ST-EVA 2.10 - the two gaps the 2.9 gates found.
--
-- ------------------------------------------------------------------
-- 1. A services business model
-- ------------------------------------------------------------------
--
-- 2.9 scored the eight collection gates across 120 metric-issuers and gate 6
-- failed for exactly one issuer, on all twenty of its metrics. The reason was
-- not a wrong ruling: it was that there were no rulings, because the issuer's
-- SIC classification falls outside the groups the rule recognises and an
-- unrecognised classification deliberately makes none.
--
-- The rule covers SIC major groups 10-14, 20-39 and 60-67. A services company
-- is major group 70-89, and adding it is a one-line change that makes twenty
-- failing gates pass. It is made here deliberately, and the constraint on it is
-- the point:
--
--     adding SERVICES must not make any metric *more collectible*
--
-- A business model earns its place in the vocabulary by carrying a ruling --
-- some metric whose meaning changes for that kind of company. A services
-- issuer currently carries none, so nothing is excluded for it and every metric
-- stays applicable. The classification is a statement about the filer, not a
-- licence to drop lines, and `Metric.applies_to` is unchanged by it.
--
-- That is the honest shape of this change: it closes a metadata gap and
-- deliberately moves no coverage. Had the numbers moved, that would have been
-- the thing to check first.
--
-- The trigger is dropped and recreated rather than edited, as in 0011:
-- migrations are forward-only and an archive that ran the earlier build has to
-- keep running the earlier rules.

DROP TRIGGER IF EXISTS issuer_business_model_vocabulary;

CREATE TRIGGER IF NOT EXISTS issuer_business_model_vocabulary
BEFORE INSERT ON issuer_business_model
WHEN NEW.business_model NOT IN (
    'OPERATING', 'MANUFACTURING', 'TECHNOLOGY', 'SERVICES',
    'FINANCE_SERVICES', 'BANK', 'INSURANCE', 'REIT', 'MINING'
)
BEGIN
    SELECT RAISE(ABORT, 'business model is not in the closed vocabulary');
END;

DROP TRIGGER IF EXISTS issuer_business_model_vocabulary_update;

CREATE TRIGGER IF NOT EXISTS issuer_business_model_vocabulary_update
BEFORE UPDATE OF business_model ON issuer_business_model
WHEN NEW.business_model NOT IN (
    'OPERATING', 'MANUFACTURING', 'TECHNOLOGY', 'SERVICES',
    'FINANCE_SERVICES', 'BANK', 'INSURANCE', 'REIT', 'MINING'
)
BEGIN
    SELECT RAISE(ABORT, 'business model is not in the closed vocabulary');
END;

-- ------------------------------------------------------------------
-- 2. Taxonomies the semantic layer does not model, and why
-- ------------------------------------------------------------------
--
-- 2.8 left a question open: *what does a filer report that ST-EVA has no
-- mapping for?* The ledger could not answer it, and the gap was visible in the
-- data -- two of the six filers report elements in taxonomies the registry
-- declares nothing against, and those elements appeared nowhere.
--
-- The answer is not 2,000 unmapped concepts. Across all six issuers the
-- unmodelled part of a filer's XBRL is **19 concepts in four taxonomies**, and
-- reading them says something the counts cannot:
--
--     ffd     offering-fee disclosure. Fee amounts, offering amounts and
--             offsets -- the mechanics of a securities offering, which is not a
--             measure of a business.
--     ecd     executive compensation, pay-versus-performance: total
--             compensation actually paid, and total shareholder return.
--     srt     supplementary narrative tagging, e.g. a share repurchase
--             authorisation.
--     invest  an industry taxonomy; one derivative-notional element.
--
-- None of them is a financial-statement metric that a consumer asking about
-- revenue, assets or equity would want. So the correct record is a
-- **declaration that the taxonomy is outside the semantic layer, with the
-- reason** -- not a decline per concept, and certainly not a coverage gap.
--
-- Two reasons why it is a table and not a name-based rule in the ledger:
-- a name-based rule has to match a concept to a metric, which is the
-- "similar label" problem 2.7 spent a phase refusing to solve by name; and a
-- taxonomy is the unit at which the answer actually exists. These four
-- taxonomies have nothing to do with each other and share nothing but being
-- unmodelled.
--
-- The kind vocabulary is closed, because "we do not model this" is only useful
-- if a reader can tell *why not* and the answer changes the remedy. A taxonomy
-- of transaction mechanics needs no work; an industry taxonomy might.

CREATE TABLE IF NOT EXISTS unmodelled_taxonomies (
    taxonomy   TEXT PRIMARY KEY,
    kind       TEXT NOT NULL,
    reason     TEXT NOT NULL,
    recorded_at TEXT
);

-- Why a taxonomy carries no semantic metric. The distinctions are not
-- decoration:
--
--   TRANSACTION_DISCLOSURE  mechanics of a transaction -- fees, offering
--                           amounts. Not a measure of a business at all.
--   EXECUTIVE_COMPENSATION  pay-versus-performance. Measures of remuneration,
--                           not of the enterprise.
--   NARRATIVE_TEXT          supplementary tagging for narrative disclosure.
--   INDUSTRY_SPECIFIC       a real taxonomy for a real industry, which may
--                           become worth modelling and has not been assessed.
--   OUT_OF_SCOPE            declared without one of the above, for a reason
--                           recorded in the row.
CREATE TRIGGER IF NOT EXISTS unmodelled_taxonomies_kind_vocabulary
BEFORE INSERT ON unmodelled_taxonomies
WHEN NEW.kind NOT IN (
    'TRANSACTION_DISCLOSURE', 'EXECUTIVE_COMPENSATION', 'NARRATIVE_TEXT',
    'INDUSTRY_SPECIFIC', 'OUT_OF_SCOPE'
)
BEGIN
    SELECT RAISE(ABORT, 'unmodelled taxonomy kind is outside the closed vocabulary');
END;

CREATE TRIGGER IF NOT EXISTS unmodelled_taxonomies_kind_vocabulary_update
BEFORE UPDATE OF kind ON unmodelled_taxonomies
WHEN NEW.kind NOT IN (
    'TRANSACTION_DISCLOSURE', 'EXECUTIVE_COMPENSATION', 'NARRATIVE_TEXT',
    'INDUSTRY_SPECIFIC', 'OUT_OF_SCOPE'
)
BEGIN
    SELECT RAISE(ABORT, 'unmodelled taxonomy kind is outside the closed vocabulary');
END;

CREATE TRIGGER IF NOT EXISTS unmodelled_taxonomies_requires_reason
BEFORE INSERT ON unmodelled_taxonomies
WHEN NEW.reason IS NULL OR TRIM(NEW.reason) = ''
BEGIN
    SELECT RAISE(ABORT, 'a taxonomy declared unmodelled must say why');
END;
