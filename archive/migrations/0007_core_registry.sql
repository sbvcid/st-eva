-- ST-EVA 2.5 - the Core Registry: what a metric means, what a source concept
-- is, and how one relates to the other.
--
-- The distinction this exists for: a source concept is not a metric.
--
--     us-gaap:Revenues                     is a tag a filer applies.
--     revenue                                 is a meaning ST-EVA names.
--
-- They are related only by an explicit mapping, because a filer may change
-- which tag it uses without changing the fact, and may use a different tag
-- for a genuinely different quantity. Deciding that from the name is how a
-- silent discontinuity gets spliced into one series.
--
-- Nothing here ranks a source, resolves a conflict, or infers a value.

CREATE TABLE IF NOT EXISTS metric_registry (
    metric_id            TEXT PRIMARY KEY,
    display_name         TEXT NOT NULL,
    statement            TEXT NOT NULL,
    semantic_definition  TEXT NOT NULL,
    unit_family          TEXT NOT NULL,
    normal_period_type   TEXT NOT NULL,
    -- APPLICABLE | CONDITIONAL | NOT_APPLICABLE. A metric is never
    -- NOT_APPLICABLE merely because no observation was retrieved for it:
    -- absence of retrieval is not evidence of inapplicability.
    applicability        TEXT NOT NULL DEFAULT 'APPLICABLE',
    comparability_group  TEXT,
    status               TEXT NOT NULL DEFAULT 'ACTIVE'
);

CREATE INDEX IF NOT EXISTS metric_registry_statement
    ON metric_registry(statement);

CREATE TABLE IF NOT EXISTS concept_registry (
    concept_id        TEXT PRIMARY KEY,
    taxonomy          TEXT NOT NULL,
    concept           TEXT NOT NULL,
    label             TEXT,
    -- The source's own definition, quoted. Never paraphrased: a paraphrase
    -- would let two concepts look equal when the source says otherwise.
    source_definition TEXT,
    UNIQUE (taxonomy, concept)
);

CREATE TABLE IF NOT EXISTS metric_concept_mapping (
    metric_id      TEXT NOT NULL REFERENCES metric_registry(metric_id),
    concept_id     TEXT NOT NULL REFERENCES concept_registry(concept_id),
    -- EXACT           the source states this concept and it means the metric
    -- EQUIVALENT      a different name, an equal meaning; a series continues
    -- PARTIAL         a component or a wider aggregate; not comparable across
    --                 a change of concept
    -- NON_COMPARABLE related but a different quantity; a different metric
    mapping_type    TEXT NOT NULL,
    effective_from  TEXT,
    effective_to    TEXT,
    notes           TEXT,
    PRIMARY KEY (metric_id, concept_id, effective_from)
);

CREATE INDEX IF NOT EXISTS mapping_by_metric
    ON metric_concept_mapping(metric_id, mapping_type);
CREATE INDEX IF NOT EXISTS mapping_by_concept
    ON metric_concept_mapping(concept_id);

-- Every vocabulary is closed. An unknown value would make "is this series
-- comparable?" unanswerable, because nothing would know what the value means.
CREATE TRIGGER IF NOT EXISTS metric_registry_vocabulary
BEFORE INSERT ON metric_registry
WHEN NEW.statement NOT IN (
        'INCOME', 'BALANCE_SHEET', 'CASH_FLOW', 'CAPITAL_RETURN', 'MARKET')
  OR NEW.unit_family NOT IN (
        'currency', 'per_share', 'count', 'ratio', 'multiple')
  OR NEW.normal_period_type NOT IN ('DURATION', 'INSTANT')
  OR NEW.applicability NOT IN ('APPLICABLE', 'CONDITIONAL', 'NOT_APPLICABLE')
  OR NEW.status NOT IN ('ACTIVE', 'DEPRECATED', 'PROPOSED')
BEGIN
    SELECT RAISE(ABORT, 'metric_registry carries a value outside its vocabulary');
END;

CREATE TRIGGER IF NOT EXISTS concept_registry_source_required
BEFORE INSERT ON concept_registry
WHEN NEW.concept_id IS NULL OR NEW.taxonomy IS NULL OR NEW.concept IS NULL
BEGIN
    SELECT RAISE(ABORT, 'a concept must identify its taxonomy and its name');
END;

CREATE TRIGGER IF NOT EXISTS mapping_type_vocabulary
BEFORE INSERT ON metric_concept_mapping
WHEN NEW.mapping_type NOT IN (
        'EXACT', 'EQUIVALENT', 'PARTIAL', 'NON_COMPARABLE')
BEGIN
    SELECT RAISE(ABORT,
        'metric_concept_mapping.mapping_type is outside the vocabulary');
END;

-- A mapping that breaks a series has to say when. A PARTIAL or NON_COMPARABLE
-- mapping with no window would let a reader assume the break never happened.
CREATE TRIGGER IF NOT EXISTS mapping_break_needs_window
BEFORE INSERT ON metric_concept_mapping
WHEN NEW.mapping_type IN ('PARTIAL', 'NON_COMPARABLE')
     AND (NEW.effective_from IS NULL AND NEW.effective_to IS NULL)
BEGIN
    SELECT RAISE(ABORT,
        'PARTIAL and NON_COMPARABLE mappings must record effective dates');
END;
