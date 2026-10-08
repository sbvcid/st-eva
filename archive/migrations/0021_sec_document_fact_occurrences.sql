-- ST-EVA 0021 - XBRL document-fact provenance schema.
--
-- `0020` froze what a filing says about itself and captured its documents'
-- bytes. It did not say which document a *fact* was read out of, because no
-- code path that writes an observation ever opened a filing document: the
-- `companyconcept` aggregate is what the ingestion route reads, and that
-- response -- not an EX-101 instance, not an inline primary document -- is what
-- `observation_sources` records. So `observation_filing_documents` is, today,
-- empty for every observation, and that is the honest state rather than a gap.
--
-- This migration adds the two relations the document route will need, and
-- nothing else. It does not read XBRL, does not touch bytes, and writes no
-- rows of its own.
--
-- ------------------------------------------------------------------
-- What this migration deliberately does not do
-- ------------------------------------------------------------------
--
-- No parser. No scanner. No XBRL. No `INSERT`. No `UPDATE`. No `DELETE`. No
-- backfill and no re-key. `observations`, `observation_id`,
-- `content_hash`, `source_fact_id`, `observation_filing_documents`,
-- `interpretations`, `admissions` and every historical row are exactly as
-- `0020` left them. The two new tables start empty and stay empty until a
-- future phase actually reads a document, which is the whole point: an
-- assertion nobody made must not exist because a table was available.
--
-- ------------------------------------------------------------------
-- Pre-migration gate
-- ------------------------------------------------------------------
--
-- The guard below refuses `observation_sources` rows that point at a filing
-- document. Applying that guard to an archive that already contains such a row
-- would leave the archive in a state its own triggers forbid -- a row that can
-- never be inserted again and cannot be deleted either, because the relation
-- has no append-only triggers at all (`0001:167-175`). So the migration counts
-- them first and refuses to proceed if the count is non-zero.
--
-- RAISE() is trigger-only in SQLite, so the assertion is a CHECK constraint on
-- a table that exists for exactly one statement and is dropped immediately
-- after. On violation the statement raises `IntegrityError`, the script stops
-- inside its own transaction, and `_ensure_schema` rolls back
-- (`sqlite_archive.py:468-487`). Nothing is repaired, nothing is deleted, and
-- the migration is not recorded. Fixing such an archive is an operator
-- decision about which reading was extracted from where, not something a
-- schema change is entitled to decide.

BEGIN;

CREATE TABLE _migration_0021_gate (
    violating_rows INTEGER NOT NULL,
    CONSTRAINT migration_0021_observation_sources_are_not_filing_documents
        CHECK (violating_rows = 0)
);

INSERT INTO _migration_0021_gate (violating_rows)
SELECT COUNT(*) FROM observation_sources os
WHERE EXISTS (
    SELECT 1 FROM filing_document_captures c
    WHERE c.document_id = os.document_id
);

DROP TABLE _migration_0021_gate;

-- ----------------------------------------------------------------------
-- The write boundary the audit found
-- ----------------------------------------------------------------------
--
-- `_link_documents` runs on the `content_hash` dedup path as well as the insert
-- path (`sqlite_archive.py:1290,1373`), and `document_id_for` resolves by
-- content hash (`:1213-1226`). A filing document's bytes *are* stored in
-- `source_documents` (`sec_ingest.py:1964-1976`), so a caller holding a filing
-- hash gets a document id and a written row: a provenance claim about which
-- document a reading came from, in a relation that is multi-valued, has no
-- 0/1 discipline and carries no append-only trigger, and that a reader asking
-- "which document did this come from?" would answer from
-- `documents_for()`.
--
-- The two relations mean different things and the boundary is a fact about the
-- data, not a convention:
--
--     observation_sources            the acquisition RESPONSE a reading was
--                                    extracted from (an endpoint response)
--     observation_filing_documents   the exact source DOCUMENT, 0 or 1 rows,
--                                    the only relation permitted to name one
--
-- So the guard is a database trigger. A Python convention would leave the
-- weakest write path free to violate a frozen meaning, and the 0/1 semantics
-- are only as strong as that path.

CREATE TRIGGER IF NOT EXISTS observation_sources_excludes_filing_documents
BEFORE INSERT ON observation_sources
WHEN EXISTS (
    SELECT 1 FROM filing_document_captures c
    WHERE c.document_id = NEW.document_id
)
BEGIN
    SELECT RAISE(ABORT,
        'a filing document is evidence about a filing, not the acquisition response a reading was extracted from; an exact source document is asserted through observation_filing_documents, which is the only relation that may name one');
END;

-- ----------------------------------------------------------------------
-- Relation A: a logical fact asserted by one document
-- ----------------------------------------------------------------------
--
-- One row per `(document_id, taxonomy, tag, context_ref, unit_ref)`: one
-- LOGICAL XBRL fact in one document. Not a physical byte occurrence. The
-- instance guarantees `(concept, context, unit)` appears at most once, so that
-- tuple is a semantic identity the document itself declares. Inline XBRL
-- `ix:continuation` lets one fact legitimately span several byte ranges, so a
-- locator in the key would split one fact into several and manufacture facts.
-- Every span therefore lives in `locators_json` as a canonical, sorted array.
--
-- Identity is a content-derived digest over eight fields, and the canonical
-- preimage is persisted beside it so the key is recomputed rather than trusted
-- -- the same reason `0020:375-377` persists `statement_identity` and `0019:78`
-- persists a decision's identity.
--
-- `document_id` is required and it is the classifier-free way to tell a filed
-- primary HTML from an EDGAR-generated `_htm.xml` from a legacy `EX-101.INS`:
-- naming a document is permitted, describing what kind of document it is is
-- not (invariant 19). `accession` is required because `document_id` is
-- content-addressed and *can* be shared across filings -- identical generated
-- bytes -- and two filings' identical bytes are two different filings'
-- assertions.
--
-- Deliberately NOT in the preimage, each for a stated reason:
--
--   value            A restatement is a different fact, not the same fact
--                    re-valued (`evidence_model.py:184-188`). It also makes
--                    the duplicate-node detector *work*: two nodes sharing one
--                    context and unit collide on this digest and hit the
--                    uniqueness index below instead of forking silently.
--   filename         The fact lives in the bytes. Two byte-identical filenames
--                    in one filing are two `filing_documents` rows and one
--                    `document_id`; a filename in the key would fork one fact.
--                    Carried as a column because the foreign keys need it.
--   period_start /
--   period_end       In XBRL the period lives inside the context, so
--                    `context_ref` determines it. Carrying it as well invites
--                    two derivations of one field to disagree and fork
--                    identity. Resolved and stored as evidence below.
--   locators         Derived from the identity, not part of it.
--   captured_at /
--   capture_kind     Transfer metadata about the read (`0020:234-236`).
--   any classifier   Invariant 19. No authorship, legal-source or precedence
--                    field may exist in this relation.
--
-- `context_ref` and `unit_ref` are stored verbatim as the attribute strings the
-- document declared, never normalised, because the digest is over those
-- strings. The same concept, period and value under a dimensional and an
-- undimensional context are two reporting facts, and that pair is
-- indistinguishable under concept+period+value and distinguishable only here
-- (`ifrs_capex_context_237.py:21-25`).
--
-- There is no parse-failure column, and the omission is deliberate: a fact
-- whose context or unit does not resolve, or which cannot be located at all,
-- is recorded by minting nothing. Amendment 0 §3 item 7 places the
-- "attempted and unresolved" signal at run level
-- (`sec_ingest.py:1291-1302`) precisely so that an absence here can be
-- distinguished from "no document-scoped read was ever attempted".

CREATE TABLE IF NOT EXISTS filing_document_fact_occurrences (
    document_fact_id TEXT PRIMARY KEY,
    -- The canonical preimage itself, so the key can be recomputed rather than
    -- trusted.
    document_fact_identity TEXT NOT NULL UNIQUE,

    -- The eight identity-bearing fields, verbatim.
    provider     TEXT NOT NULL,
    asset_id     TEXT NOT NULL,
    accession    TEXT NOT NULL,
    filename     TEXT NOT NULL,
    document_id  TEXT NOT NULL REFERENCES source_documents(document_id),
    taxonomy     TEXT NOT NULL,
    tag          TEXT NOT NULL,
    context_ref  TEXT NOT NULL,
    unit_ref     TEXT NOT NULL,

    -- The resolved context. Reproducing the digest needs only `context_ref`;
    -- an occurrence nobody can interpret is not evidence.
    entity_identifier  TEXT NOT NULL,
    entity_scheme      TEXT,
    period_kind        TEXT NOT NULL,
    period_start       TEXT,
    period_end         TEXT,
    dimensions_json    TEXT NOT NULL,
    unit_measures_json TEXT NOT NULL,

    -- The resolved value and the attributes it was derived from. `value_text`
    -- is the node's character data, untransformed, so a re-parse can be
    -- compared against it byte for byte.
    value_text     TEXT NOT NULL,
    resolved_value REAL NOT NULL,
    sign           TEXT,
    scale          TEXT,
    format_        TEXT,
    decimals       TEXT,
    language       TEXT,

    -- Re-finding the bytes. Offsets are into the UNCOMPRESSED payload, which is
    -- what `content_hash` covers (`sqlite_archive.py:620-621`), so they stay
    -- valid however the payload is stored.
    locators_json        TEXT NOT NULL,
    context_locator_json TEXT NOT NULL,
    unit_locator_json    TEXT NOT NULL,

    captured_at  TEXT NOT NULL,
    capture_kind TEXT NOT NULL,

    -- An occurrence is about captured bytes of a named document, not about an
    -- abstract document: both parents are enforced, not one.
    FOREIGN KEY (asset_id, accession, filename, document_id)
        REFERENCES filing_document_captures(
            asset_id, accession, filename, document_id),
    FOREIGN KEY (asset_id, accession, filename)
        REFERENCES filing_documents(asset_id, accession, filename)
);

-- The uniqueness assertion the design froze, promoted from a producer promise
-- to a database guarantee. This is the duplicate-node detector: a document that
-- states one concept twice under one context and unit is invalid XBRL, and the
-- second row is refused rather than accepted as a second logical fact.
CREATE UNIQUE INDEX IF NOT EXISTS fact_occurrences_node_unique
    ON filing_document_fact_occurrences(
        document_id, taxonomy, tag, context_ref, unit_ref);

CREATE INDEX IF NOT EXISTS fact_occurrences_document
    ON filing_document_fact_occurrences(document_id);
CREATE INDEX IF NOT EXISTS fact_occurrences_filing_document
    ON filing_document_fact_occurrences(asset_id, accession, filename);

CREATE TRIGGER IF NOT EXISTS fact_occurrences_period_kind_vocabulary
BEFORE INSERT ON filing_document_fact_occurrences
WHEN NEW.period_kind NOT IN ('INSTANT', 'DURATION', 'FOREVER')
BEGIN
    SELECT RAISE(ABORT,
        'filing_document_fact_occurrences.period_kind is outside the closed vocabulary');
END;

CREATE TRIGGER IF NOT EXISTS fact_occurrences_capture_kind_vocabulary
BEFORE INSERT ON filing_document_fact_occurrences
WHEN NEW.capture_kind NOT IN ('FIRST_HAND', 'LATER_ACQUISITION', 'DECLARED_NOT_CAPTURED')
BEGIN
    SELECT RAISE(ABORT,
        'filing_document_fact_occurrences.capture_kind is outside the closed vocabulary');
END;

-- The same contradiction `0020:423-432` watches for in a quotation. One
-- identity means one fact, so a second reading of that identity that resolves
-- differently means the parse is not deterministic, and that has to be visible
-- rather than absorbed.
CREATE TRIGGER IF NOT EXISTS fact_occurrences_extraction_consistent
BEFORE INSERT ON filing_document_fact_occurrences
WHEN EXISTS (
    SELECT 1 FROM filing_document_fact_occurrences o
    WHERE o.document_fact_id = NEW.document_fact_id
      AND (o.value_text <> NEW.value_text
           OR o.resolved_value <> NEW.resolved_value
           OR o.document_fact_identity <> NEW.document_fact_identity)
)
BEGIN
    SELECT RAISE(ABORT,
        'the same document, concept, context and unit resolved to different fact evidence; the extraction is not deterministic and the second reading is not being absorbed silently');
END;

-- ----------------------------------------------------------------------
-- Relation B: which observation came out of which occurrence
-- ----------------------------------------------------------------------
--
-- A link, not an assertion of fact identity, so it carries no identity column
-- and no `captured_at`/`capture_kind`/`filename`: those belong to the
-- occurrence, and a second copy of them would be a second place for them to
-- disagree.
--
-- There is deliberately NO UNIQUE on `observation_id` alone. Two contexts in
-- one document are two occurrences and one observation, because
-- `observation_id` has no dimension slot (`sec_ingest.py:2391-2394`); the link
-- must be able to hold both. Which member a stored value came from is not
-- claimed here -- the existing `dimension_collision` mechanism reports that
-- ambiguity -- and nothing in this table may be used to re-key an observation.
--
-- This relation supplements the `companyconcept` route. It does not replace it,
-- it does not replace or re-key an existing observation, and it is not a
-- candidate-document relation: the exact source-document assertion stays where
-- the previous freeze put it, in `observation_filing_documents`, at 0 or 1 rows.

CREATE TABLE IF NOT EXISTS observation_filing_document_facts (
    observation_id   TEXT NOT NULL REFERENCES observations(observation_id),
    document_fact_id TEXT NOT NULL
        REFERENCES filing_document_fact_occurrences(document_fact_id),
    PRIMARY KEY (observation_id, document_fact_id)
);

CREATE INDEX IF NOT EXISTS observation_filing_document_facts_fact
    ON observation_filing_document_facts(document_fact_id);

-- ----------------------------------------------------------------------
-- Append-only
-- ----------------------------------------------------------------------
--
-- Same discipline as `0020:581-634`, and for the same reason: every row here is
-- a claim about what a source declared. A re-acquisition inserts; it never
-- amends the reading it re-made.

CREATE TRIGGER IF NOT EXISTS filing_document_fact_occurrences_no_update
BEFORE UPDATE ON filing_document_fact_occurrences
BEGIN SELECT RAISE(ABORT, 'filing_document_fact_occurrences are append-only'); END;
CREATE TRIGGER IF NOT EXISTS filing_document_fact_occurrences_no_delete
BEFORE DELETE ON filing_document_fact_occurrences
BEGIN SELECT RAISE(ABORT, 'filing_document_fact_occurrences are append-only'); END;

CREATE TRIGGER IF NOT EXISTS observation_filing_document_facts_no_update
BEFORE UPDATE ON observation_filing_document_facts
BEGIN SELECT RAISE(ABORT, 'observation_filing_document_facts are append-only'); END;
CREATE TRIGGER IF NOT EXISTS observation_filing_document_facts_no_delete
BEFORE DELETE ON observation_filing_document_facts
BEGIN SELECT RAISE(ABORT, 'observation_filing_document_facts are append-only'); END;

COMMIT;