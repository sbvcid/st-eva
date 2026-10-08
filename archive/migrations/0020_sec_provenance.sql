-- ST-EVA 0020 - SEC provenance: filing, filing item, filing document.
--
-- The archive already holds a fact, the bytes of the endpoint payload it was
-- read from, and an accession. It does not hold the filing those three belong
-- to, the items the filing declares, or the documents inside it. This migration
-- adds the four provenance objects the design passes accepted, and nothing else.
--
-- ------------------------------------------------------------------
-- What this migration deliberately does not do
-- ------------------------------------------------------------------
--
-- No Evidence table. No QuarterEpsEvidence. No Historical P/E relation.
-- `evidence_class`, `audit_status`, `sec_item` and `legal_status_note` appear
-- nowhere, because all four are pure functions of persisted inputs and are
-- derived at read time. Persisting them would freeze a computation at write
-- time and reopen the question `test_observation_identity_conformance.py` exists
-- to measure.
--
-- No column is added to `observations`, and no existing row is touched. The
-- conformance suite asserts an observation is byte-identical before and after
-- provenance is written underneath it.
--
-- **No backfill.** This follows `0019:36-39` exactly: populating a new relation
-- with current-state identities would assert a history that never happened. The
-- `held_filings` projection is therefore NOT a data statement in this file. It is
-- a deterministic, idempotent function exercised by the conformance suite, and
-- it is wired into a production writer only when that writer is in scope.
--
-- ------------------------------------------------------------------
-- Why every identity here is a digest of the *assertion*
-- ------------------------------------------------------------------
--
-- A key that names the producer rather than the assertion silently converts any
-- changed assertion into a discarded one: the second acquisition hits the same
-- primary key and is conflict-ignored, and the record of the change is lost. That
-- is the failure `admission_identity` (`sqlite_archive.py:283-308`) names when it
-- puts `registry_state_identity` and `resolver_policy_identity` inside the key
-- because "a key that omitted either would make a change of interpretation
-- invisible".
--
-- So every content-derived entity here carries a prefixed digest over its
-- asserted content, exactly as `sfid_` (`evidence_model.py:199`), `adm_`
-- (`sqlite_archive.py:1615`), `doc_` and `obsarch_` already do. The preimages
-- are computed by the writer, not by this file, and are documented on each table.
--
-- **`captured_at`, `capture_kind` and every migration timestamp are excluded from
-- every preimage.** Re-confirming the same assertion later must be a no-op, and
-- the first acquisition is the first-hand one. A migration timestamp that
-- impersonated a capture time would make the archive claim it could not know a
-- filing's form until the day it was upgraded.
--
-- ------------------------------------------------------------------
-- filings: identity only
-- ------------------------------------------------------------------
--
-- `filings` holds no field a later acquisition could contradict. `form`,
-- `filing_date`, `report_date`, `conformed_period_of_report`,
-- `public_document_count`, `is_xbrl` and `primary_document` all live in
-- `filing_declarations`, because every one of them is an *assertion by a source*
-- and a later, better source must be able to add one without mutating anything.
--
-- A filing row is not a filing's metadata. It is the fact that a filing exists.
--
-- ------------------------------------------------------------------
-- filing_document_captures is keyed on content identity
-- ------------------------------------------------------------------
--
-- Its key is `(asset_id, accession, filename, document_id)` with
-- `document_id` coming from `source_documents`. That is the one relation here
-- whose key is a natural composite rather than a digest, and deliberately: the
-- tuple already *is* the content identity, so re-fetching identical bytes is a
-- no-op and re-fetching changed bytes is a different `document_id` and therefore a
-- new row with the earlier one retained.
--
-- `acquisition_class` lives here rather than being read out of
-- `source_documents.document_type`. That column was verified to be plain TEXT
-- with no CHECK, no trigger and no writer validation, so it is deliberately
-- unconstrained -- which is exactly why no filing semantic may depend on it.
-- `source_documents` gains no column and no trigger here.
--
-- ------------------------------------------------------------------
-- filing_document_statements binds a quotation to one byte sequence
-- ------------------------------------------------------------------
--
-- A filing document may be captured more than once, so a statement's identity has
-- to name the capture and not merely the document. `quote_locator` is inside the
-- preimage because it is *position*, which is what distinguishes one quotation of
-- a kind from another; `quote_text` is payload and is deliberately excluded, per
-- "identity should not carry data that can drift from the row it names".
--
-- The consequence is that a re-extraction which produces a *different* quotation
-- from the *same* capture, kind and locator is not a new statement and not a
-- no-op. It is a contradiction, and `filing_document_statements_extraction_consistent`
-- refuses it with a message rather than letting a conflict-ignore hide it.
BEGIN;

-- ----------------------------------------------------------------------
-- Filing
-- ----------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS filings (
    asset_id          TEXT NOT NULL REFERENCES assets(asset_id),
    -- The filing's identity is its accession, which is what 0008:17-20 already
    -- settled. Asset-scoped, because the archive is asset-scoped everywhere:
    -- `observations.asset_id`, `held_filings`, `evidence_state` all are.
    accession         TEXT NOT NULL,
    -- When this archive first saw the filing. Archive capture provenance, not a
    -- filing attribute, and it is the only non-key column here on purpose.
    first_archived_at TEXT NOT NULL,
    PRIMARY KEY (asset_id, accession)
);

CREATE INDEX IF NOT EXISTS filings_accession
    ON filings(accession);

-- Preimage: {asset_id, accession, declaration_source, form, filing_date,
--            report_date, conformed_period_of_report, public_document_count,
--            is_xbrl, primary_document}
-- NULLs are part of the assertion and are preserved explicitly: omitted-vs-null
-- is a difference in what the source said and must change the digest.
CREATE TABLE IF NOT EXISTS filing_declarations (
    declaration_id             TEXT PRIMARY KEY,
    asset_id                   TEXT NOT NULL,
    accession                  TEXT NOT NULL,
    -- Which resource asserted this. Not a precedence: every source's row is kept
    -- and resolution is a read-time decision.
    declaration_source         TEXT NOT NULL,
    form                       TEXT,
    filing_date                TEXT,
    report_date                TEXT,
    conformed_period_of_report TEXT,
    public_document_count      INTEGER,
    is_xbrl                    INTEGER,
    primary_document           TEXT,
    declared_at                TEXT,
    captured_at                TEXT NOT NULL,
    capture_kind               TEXT NOT NULL,
    FOREIGN KEY (asset_id, accession)
        REFERENCES filings(asset_id, accession)
);

CREATE INDEX IF NOT EXISTS filing_declarations_filing
    ON filing_declarations(asset_id, accession);
CREATE INDEX IF NOT EXISTS filing_declarations_source
    ON filing_declarations(asset_id, accession, declaration_source);

CREATE TRIGGER IF NOT EXISTS filing_declarations_source_vocabulary
BEFORE INSERT ON filing_declarations
WHEN NEW.declaration_source NOT IN (
    'MIGRATION_PROJECTION_HELD_FILINGS',
    'SUBMISSIONS_API_FILING_INDEX',
    'SGML_SUBMISSION_HEADER',
    'FACT_RECORD'
)
BEGIN
    SELECT RAISE(ABORT,
        'filing_declarations.declaration_source is outside the closed vocabulary');
END;

CREATE TRIGGER IF NOT EXISTS filing_declarations_is_xbrl_shape
BEFORE INSERT ON filing_declarations
WHEN NEW.is_xbrl IS NOT NULL AND NEW.is_xbrl NOT IN (0, 1)
BEGIN
    SELECT RAISE(ABORT,
        'filing_declarations.is_xbrl is 0, 1 or NULL -- not acquired');
END;

-- ----------------------------------------------------------------------
-- Filing item
-- ----------------------------------------------------------------------

-- Preimage: {asset_id, accession, declaration_source, raw_items_text}
-- The verbatim string is the assertion. Splitting it into rows happens in
-- `filing_items`, so a changed parse cannot silently discard a row.
CREATE TABLE IF NOT EXISTS filing_item_declarations (
    declaration_id      TEXT PRIMARY KEY,
    asset_id            TEXT NOT NULL,
    accession           TEXT NOT NULL,
    declaration_source  TEXT NOT NULL,
    raw_items_text      TEXT NOT NULL,
    declared_item_count INTEGER,
    declared_at         TEXT,
    captured_at         TEXT NOT NULL,
    capture_kind        TEXT NOT NULL,
    FOREIGN KEY (asset_id, accession)
        REFERENCES filings(asset_id, accession)
);

CREATE INDEX IF NOT EXISTS filing_item_declarations_filing
    ON filing_item_declarations(asset_id, accession);

CREATE TRIGGER IF NOT EXISTS filing_item_declarations_source_vocabulary
BEFORE INSERT ON filing_item_declarations
WHEN NEW.declaration_source NOT IN (
    'SUBMISSIONS_API_ITEMS',
    'SGML_ITEM_INFORMATION'
)
BEGIN
    SELECT RAISE(ABORT,
        'filing_item_declarations.declaration_source is outside the closed vocabulary');
END;

-- Preimage: {declaration_id, item_ordinal, item_code, item_title, title_source}
-- `item_ordinal` is scoped to its declaration, never to the filing: the same
-- ordinal under two declaring sources is two different assertions and was the
-- collision an accession-scoped key could not express.
CREATE TABLE IF NOT EXISTS filing_items (
    item_id        TEXT PRIMARY KEY,
    declaration_id TEXT NOT NULL
        REFERENCES filing_item_declarations(declaration_id),
    item_ordinal   INTEGER NOT NULL,
    item_code      TEXT NOT NULL,
    item_title     TEXT,
    title_source   TEXT,
    captured_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS filing_items_declaration
    ON filing_items(declaration_id, item_ordinal);
CREATE INDEX IF NOT EXISTS filing_items_code
    ON filing_items(item_code);

-- ----------------------------------------------------------------------
-- Filing document
-- ----------------------------------------------------------------------

-- Preimage: {asset_id, accession, manifest_source, source_ordinal, filename,
--            sec_document_type, mime_type, byte_size, description}
--
-- `source_ordinal` is the position in ONE manifest and means nothing across
-- manifests. Measured: `index.json` and the SGML `<DOCUMENT>` sequence disagree
-- at every position, so the two ordinals are kept independent and are never
-- equated.
--
-- `last_modified` is transfer metadata about the read, not an assertion about
-- the document, and is excluded from the preimage on purpose.
CREATE TABLE IF NOT EXISTS filing_document_declarations (
    declaration_id    TEXT PRIMARY KEY,
    asset_id          TEXT NOT NULL,
    accession         TEXT NOT NULL,
    manifest_source   TEXT NOT NULL,
    source_ordinal    INTEGER NOT NULL,
    filename          TEXT,
    -- The SEC SGML <TYPE>: '8-K', 'EX-99.1', 'EX-101.INS'. Never the MIME type,
    -- which is the column below. `index.json` cannot supply this at all, which
    -- is why a directory-sourced row leaves it NULL rather than guessing.
    sec_document_type TEXT,
    -- The MIME type `index.json` supplies: 'text.gif', 'compressed.gif'.
    mime_type         TEXT,
    byte_size         INTEGER,
    description       TEXT,
    last_modified     TEXT,
    captured_at       TEXT NOT NULL,
    capture_kind      TEXT NOT NULL,
    FOREIGN KEY (asset_id, accession)
        REFERENCES filings(asset_id, accession)
);

CREATE INDEX IF NOT EXISTS filing_document_declarations_position
    ON filing_document_declarations(asset_id, accession, manifest_source, source_ordinal);
CREATE INDEX IF NOT EXISTS filing_document_declarations_filename
    ON filing_document_declarations(asset_id, accession, filename);

CREATE TRIGGER IF NOT EXISTS filing_document_declarations_manifest_vocabulary
BEFORE INSERT ON filing_document_declarations
WHEN NEW.manifest_source NOT IN (
    'EDGAR_FILING_DIRECTORY_INDEX_JSON',
    'EDGAR_FULL_SUBMISSION_TEXT'
)
BEGIN
    SELECT RAISE(ABORT,
        'filing_document_declarations.manifest_source is outside the closed vocabulary');
END;

CREATE TRIGGER IF NOT EXISTS filing_document_declarations_ordinal_positive
BEFORE INSERT ON filing_document_declarations
WHEN NEW.source_ordinal < 1
BEGIN
    SELECT RAISE(ABORT,
        'a manifest position is 1-based; there is no ordinal zero');
END;

-- Identity only. No `document_type`, no `mime_type`, no `source_ordinal`, no
-- `document_id`, no `capture_kind`: this row asserts one thing, that a document
-- with this filename belongs to this filing, and carries nothing a declaration
-- could contradict or overwrite.
--
-- A filename is a filesystem identity inside a filing's EDGAR directory, so the
-- directory manifest mints identity and the SGML manifest only ever annotates.
-- The triggers below enforce that at the database rather than by discipline.
CREATE TABLE IF NOT EXISTS filing_documents (
    asset_id           TEXT NOT NULL,
    accession          TEXT NOT NULL,
    filename           TEXT NOT NULL,
    first_declared_at  TEXT,
    PRIMARY KEY (asset_id, accession, filename),
    FOREIGN KEY (asset_id, accession)
        REFERENCES filings(asset_id, accession)
);

CREATE INDEX IF NOT EXISTS filing_documents_filename
    ON filing_documents(filename);

CREATE TRIGGER IF NOT EXISTS filing_documents_identity_is_declared
BEFORE INSERT ON filing_documents
WHEN NOT EXISTS (
    SELECT 1 FROM filing_document_declarations d
    WHERE d.asset_id = NEW.asset_id
      AND d.accession = NEW.accession
      AND d.filename = NEW.filename
      AND d.manifest_source = 'EDGAR_FILING_DIRECTORY_INDEX_JSON'
)
BEGIN
    SELECT RAISE(ABORT, 'a filing document identity is minted only by a directory-manifest declaration of that filename; the SGML manifest annotates and never mints identity');
END;

-- The count is compared with `> 1`, not `<> 1`, and that is load-bearing rather
-- than stylistic: SQLite runs `BEFORE INSERT` triggers in reverse order of
-- creation, so whichever of these two fires first depends on their order in
-- this file. With `<> 1` a filename declared *zero* times would be reported as
-- declared more than once, which names a duplicate that does not exist. The two
-- conditions are therefore mutually exclusive on their own, and the message a
-- reader gets does not depend on trigger ordering.
CREATE TRIGGER IF NOT EXISTS filing_documents_identity_is_unambiguous
BEFORE INSERT ON filing_documents
WHEN (
    SELECT COUNT(*) FROM filing_document_declarations d
    WHERE d.asset_id = NEW.asset_id
      AND d.accession = NEW.accession
      AND d.filename = NEW.filename
      AND d.manifest_source = 'EDGAR_FILING_DIRECTORY_INDEX_JSON'
) > 1
BEGIN
    SELECT RAISE(ABORT, 'a filename declared more than once by the directory manifest cannot mint an identity row; the duplicate declarations are kept and the document is left unresolved rather than merged');
END;

-- Keyed on content identity, the one relation here whose key is a natural
-- composite rather than a digest: the tuple already names the byte sequence, so
-- an identical re-fetch is a no-op and changed bytes are a new row.
CREATE TABLE IF NOT EXISTS filing_document_captures (
    asset_id          TEXT NOT NULL,
    accession         TEXT NOT NULL,
    filename          TEXT NOT NULL,
    -- From `source_documents`, whose `content_hash` is NOT NULL UNIQUE. Different
    -- bytes are therefore a different document_id, which is what makes a changed
    -- re-fetch a new capture rather than a mutation of the old one.
    document_id       TEXT NOT NULL REFERENCES source_documents(document_id),
    -- Closed here rather than read out of `source_documents.document_type`, which
    -- was verified to carry no CHECK, no trigger and no writer validation.
    acquisition_class TEXT NOT NULL,
    captured_at       TEXT NOT NULL,
    capture_kind      TEXT NOT NULL,
    PRIMARY KEY (asset_id, accession, filename, document_id),
    FOREIGN KEY (asset_id, accession, filename)
        REFERENCES filing_documents(asset_id, accession, filename)
);

CREATE INDEX IF NOT EXISTS filing_document_captures_document
    ON filing_document_captures(document_id);

CREATE TRIGGER IF NOT EXISTS filing_document_captures_acquisition_vocabulary
BEFORE INSERT ON filing_document_captures
WHEN NEW.acquisition_class NOT IN ('SEC_FILING_DOCUMENT')
BEGIN
    SELECT RAISE(ABORT,
        'filing_document_captures.acquisition_class is outside the closed vocabulary');
END;

-- Preimage: {asset_id, accession, filename, document_id, statement_kind,
--            quote_locator}
-- `quote_locator` is position, so it belongs. `quote_text` is payload and does
-- not, which is why the identity stays stable while the wording can be checked.
CREATE TABLE IF NOT EXISTS filing_document_statements (
    statement_id  TEXT PRIMARY KEY,
    -- The canonical preimage itself, persisted as `0019:78` persists a
    -- decision's identity, so the key can be recomputed rather than trusted.
    statement_identity TEXT NOT NULL UNIQUE,
    asset_id      TEXT NOT NULL,
    accession     TEXT NOT NULL,
    filename      TEXT NOT NULL,
    -- The exact captured byte sequence the quotation was taken from.
    document_id   TEXT NOT NULL REFERENCES source_documents(document_id),
    statement_kind TEXT NOT NULL,
    quote_locator TEXT NOT NULL,
    quote_text    TEXT NOT NULL,
    extraction_method TEXT NOT NULL,
    extracted_at  TEXT NOT NULL,
    capture_kind  TEXT NOT NULL,
    -- The Section 18 language is in the primary 8-K body and governs a named
    -- exhibit, so its scope is stated rather than inferred from adjacency.
    applies_to_document_type   TEXT,
    applies_to_filing_item_code TEXT,
    -- A statement is about captured bytes, not about an abstract document.
    FOREIGN KEY (asset_id, accession, filename, document_id)
        REFERENCES filing_document_captures(
            asset_id, accession, filename, document_id)
);

CREATE INDEX IF NOT EXISTS filing_document_statements_document
    ON filing_document_statements(document_id);
CREATE INDEX IF NOT EXISTS filing_document_statements_kind
    ON filing_document_statements(asset_id, accession, statement_kind);

CREATE TRIGGER IF NOT EXISTS filing_document_statements_kind_vocabulary
BEFORE INSERT ON filing_document_statements
WHEN NEW.statement_kind NOT IN ('SECTION_18_NOT_DEEMED_FILED')
BEGIN
    SELECT RAISE(ABORT,
        'filing_document_statements.statement_kind is outside the closed vocabulary');
END;

CREATE TRIGGER IF NOT EXISTS filing_document_statements_method_vocabulary
BEFORE INSERT ON filing_document_statements
WHEN NEW.extraction_method NOT IN ('DECLARED_VERBATIM_QUOTE')
BEGIN
    SELECT RAISE(ABORT,
        'filing_document_statements.extraction_method is outside the closed vocabulary');
END;

-- The contradiction the design named. Re-extracting the same capture, kind and
-- locator must produce the same words; if it does not, the extraction is not
-- deterministic and the conflict has to be visible rather than absorbed.
CREATE TRIGGER IF NOT EXISTS filing_document_statements_extraction_consistent
BEFORE INSERT ON filing_document_statements
WHEN EXISTS (
    SELECT 1 FROM filing_document_statements s
    WHERE s.statement_id = NEW.statement_id
      AND (s.quote_text <> NEW.quote_text
           OR s.extraction_method <> NEW.extraction_method)
)
BEGIN
    SELECT RAISE(ABORT, 'the same capture, statement kind and locator yielded a different quotation; the extraction is not deterministic and the second reading is not being absorbed silently');
END;

-- ----------------------------------------------------------------------
-- Filing acceptance
-- ----------------------------------------------------------------------

-- Preimage: {asset_id, accession, acceptance_source, acceptance_datetime,
--            acceptance_precision, raw_value}
--
-- Exactly two producers, because exactly two SEC resources publish an acceptance
-- instant. A fact's own `filed` date is NOT an acceptance: it is a different
-- claim about a different object, it stays on `observations.available_at_basis`
-- as FILED_AS_OF_DATE, and no value here can be read as it. Both producers are
-- kept; neither overwrites the other; precedence is a read-time decision.
CREATE TABLE IF NOT EXISTS filing_acceptances (
    declaration_id       TEXT PRIMARY KEY,
    asset_id             TEXT NOT NULL,
    accession            TEXT NOT NULL,
    acceptance_source    TEXT NOT NULL,
    -- NULL exactly when precision is NONE: the producer was consulted and
    -- declared nothing, which is a different fact from never having been
    -- consulted, and is told apart by the row's presence.
    acceptance_datetime  TEXT,
    acceptance_precision TEXT NOT NULL,
    -- The verbatim value as served, kept so a negative observation stays
    -- auditable. An accession outside the recent-filings window serves ''.
    raw_value            TEXT,
    captured_at          TEXT NOT NULL,
    capture_kind         TEXT NOT NULL,
    FOREIGN KEY (asset_id, accession)
        REFERENCES filings(asset_id, accession)
);

CREATE INDEX IF NOT EXISTS filing_acceptances_filing
    ON filing_acceptances(asset_id, accession, acceptance_source);

CREATE TRIGGER IF NOT EXISTS filing_acceptances_source_vocabulary
BEFORE INSERT ON filing_acceptances
WHEN NEW.acceptance_source NOT IN (
    'SGML_HEADER_ACCEPTANCE_DATETIME',
    'SUBMISSIONS_API_ACCEPTANCE_DATETIME'
)
BEGIN
    SELECT RAISE(ABORT,
        'filing_acceptances.acceptance_source is outside the closed vocabulary');
END;

CREATE TRIGGER IF NOT EXISTS filing_acceptances_precision_vocabulary
BEFORE INSERT ON filing_acceptances
WHEN NEW.acceptance_precision NOT IN ('INSTANT', 'DATE', 'NONE')
BEGIN
    SELECT RAISE(ABORT,
        'filing_acceptances.acceptance_precision is outside the closed vocabulary');
END;

CREATE TRIGGER IF NOT EXISTS filing_acceptances_none_has_no_value
BEFORE INSERT ON filing_acceptances
WHEN NEW.acceptance_precision = 'NONE' AND NEW.acceptance_datetime IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'precision NONE means the producer declared no instant, so acceptance_datetime must be NULL');
END;

CREATE TRIGGER IF NOT EXISTS filing_acceptances_value_has_precision
BEFORE INSERT ON filing_acceptances
WHEN NEW.acceptance_precision IN ('INSTANT', 'DATE')
     AND NEW.acceptance_datetime IS NULL
BEGIN
    SELECT RAISE(ABORT, 'a declared acceptance precision requires an acceptance_datetime');
END;

-- ----------------------------------------------------------------------
-- Issuer fiscal calendar
-- ----------------------------------------------------------------------

-- Preimage: {asset_id, fiscal_year_end_mmdd, declaration_source,
--            declaring_accession}
--
-- Declarations, not a resolved calendar. There is deliberately NO fiscal_year
-- column: Contract §K.4 leaves per-fiscal-year resolution open, and a column
-- would freeze an undecided semantic into the schema. What applies to which
-- fiscal year stays a derivation, so a later decision needs no migration.
--
-- The raw four-character form is kept because '0929' and '0926' differ in the
-- day as well as the month, and storing only a month integer would let two
-- different declarations compare equal.
CREATE TABLE IF NOT EXISTS issuer_fiscal_calendar_declarations (
    declaration_id       TEXT PRIMARY KEY,
    asset_id             TEXT NOT NULL REFERENCES assets(asset_id),
    fiscal_year_end_mmdd TEXT NOT NULL,
    declaration_source   TEXT NOT NULL,
    -- Which filing declared it. NULL for an issuer-level declaration that names
    -- no single filing; the composite foreign key is then trivially satisfied.
    declaring_accession  TEXT,
    observed_filing_date TEXT,
    captured_at          TEXT NOT NULL,
    capture_kind         TEXT NOT NULL,
    FOREIGN KEY (asset_id, declaring_accession)
        REFERENCES filings(asset_id, accession),
    CHECK (LENGTH(fiscal_year_end_mmdd) = 4
           AND fiscal_year_end_mmdd NOT GLOB '*[^0-9]*')
);

CREATE INDEX IF NOT EXISTS issuer_fiscal_calendar_declarations_asset
    ON issuer_fiscal_calendar_declarations(asset_id, fiscal_year_end_mmdd);

CREATE TRIGGER IF NOT EXISTS issuer_fiscal_calendar_declarations_source_vocabulary
BEFORE INSERT ON issuer_fiscal_calendar_declarations
WHEN NEW.declaration_source NOT IN (
    'SUBMISSIONS_API_FISCAL_YEAR_END',
    'SGML_HEADER_FISCAL_YEAR_END'
)
BEGIN
    SELECT RAISE(ABORT, 'issuer_fiscal_calendar_declarations.declaration_source is outside the closed vocabulary');
END;

-- ----------------------------------------------------------------------
-- Observation linkage
-- ----------------------------------------------------------------------

-- Which document inside an accession a fact was read from. Mandatory rather than
-- optional: one accession holds many documents of differing legal status, so
-- accession alone cannot resolve a classification, and the document a fact came
-- from is NOT inferable -- for one measured filing the diluted-EPS facts came
-- from an EX-101 instance while the EX-99.1 exhibit carried no inline XBRL at
-- all. Hence a link row rather than a column, and never a guess from accession.
CREATE TABLE IF NOT EXISTS observation_filing_documents (
    observation_id TEXT NOT NULL REFERENCES observations(observation_id),
    asset_id       TEXT NOT NULL,
    accession      TEXT NOT NULL,
    filename       TEXT NOT NULL,
    captured_at    TEXT NOT NULL,
    capture_kind   TEXT NOT NULL,
    PRIMARY KEY (observation_id, asset_id, accession, filename),
    FOREIGN KEY (asset_id, accession, filename)
        REFERENCES filing_documents(asset_id, accession, filename)
);

CREATE INDEX IF NOT EXISTS observation_filing_documents_document
    ON observation_filing_documents(asset_id, accession, filename);

-- ----------------------------------------------------------------------
-- Append-only
-- ----------------------------------------------------------------------
--
-- Every relation here is immutable provenance. A re-acquisition inserts a new
-- row; it never amends the one it re-read. Same discipline as `0019:115-125` and
-- `0002:38-43`, and the conformance suite asserts it for all eleven.

CREATE TRIGGER IF NOT EXISTS filings_no_update BEFORE UPDATE ON filings
BEGIN SELECT RAISE(ABORT, 'filings are append-only'); END;
CREATE TRIGGER IF NOT EXISTS filings_no_delete BEFORE DELETE ON filings
BEGIN SELECT RAISE(ABORT, 'filings are append-only'); END;

CREATE TRIGGER IF NOT EXISTS filing_declarations_no_update BEFORE UPDATE ON filing_declarations
BEGIN SELECT RAISE(ABORT, 'filing_declarations are append-only'); END;
CREATE TRIGGER IF NOT EXISTS filing_declarations_no_delete BEFORE DELETE ON filing_declarations
BEGIN SELECT RAISE(ABORT, 'filing_declarations are append-only'); END;

CREATE TRIGGER IF NOT EXISTS filing_item_declarations_no_update BEFORE UPDATE ON filing_item_declarations
BEGIN SELECT RAISE(ABORT, 'filing_item_declarations are append-only'); END;
CREATE TRIGGER IF NOT EXISTS filing_item_declarations_no_delete BEFORE DELETE ON filing_item_declarations
BEGIN SELECT RAISE(ABORT, 'filing_item_declarations are append-only'); END;

CREATE TRIGGER IF NOT EXISTS filing_items_no_update BEFORE UPDATE ON filing_items
BEGIN SELECT RAISE(ABORT, 'filing_items are append-only'); END;
CREATE TRIGGER IF NOT EXISTS filing_items_no_delete BEFORE DELETE ON filing_items
BEGIN SELECT RAISE(ABORT, 'filing_items are append-only'); END;

CREATE TRIGGER IF NOT EXISTS filing_document_declarations_no_update BEFORE UPDATE ON filing_document_declarations
BEGIN SELECT RAISE(ABORT, 'filing_document_declarations are append-only'); END;
CREATE TRIGGER IF NOT EXISTS filing_document_declarations_no_delete BEFORE DELETE ON filing_document_declarations
BEGIN SELECT RAISE(ABORT, 'filing_document_declarations are append-only'); END;

CREATE TRIGGER IF NOT EXISTS filing_documents_no_update BEFORE UPDATE ON filing_documents
BEGIN SELECT RAISE(ABORT, 'filing_documents are append-only'); END;
CREATE TRIGGER IF NOT EXISTS filing_documents_no_delete BEFORE DELETE ON filing_documents
BEGIN SELECT RAISE(ABORT, 'filing_documents are append-only'); END;

CREATE TRIGGER IF NOT EXISTS filing_document_captures_no_update BEFORE UPDATE ON filing_document_captures
BEGIN SELECT RAISE(ABORT, 'filing_document_captures are append-only'); END;
CREATE TRIGGER IF NOT EXISTS filing_document_captures_no_delete BEFORE DELETE ON filing_document_captures
BEGIN SELECT RAISE(ABORT, 'filing_document_captures are append-only'); END;

CREATE TRIGGER IF NOT EXISTS filing_document_statements_no_update BEFORE UPDATE ON filing_document_statements
BEGIN SELECT RAISE(ABORT, 'filing_document_statements are append-only'); END;
CREATE TRIGGER IF NOT EXISTS filing_document_statements_no_delete BEFORE DELETE ON filing_document_statements
BEGIN SELECT RAISE(ABORT, 'filing_document_statements are append-only'); END;

CREATE TRIGGER IF NOT EXISTS filing_acceptances_no_update BEFORE UPDATE ON filing_acceptances
BEGIN SELECT RAISE(ABORT, 'filing_acceptances are append-only'); END;
CREATE TRIGGER IF NOT EXISTS filing_acceptances_no_delete BEFORE DELETE ON filing_acceptances
BEGIN SELECT RAISE(ABORT, 'filing_acceptances are append-only'); END;

CREATE TRIGGER IF NOT EXISTS issuer_fiscal_calendar_declarations_no_update BEFORE UPDATE ON issuer_fiscal_calendar_declarations
BEGIN SELECT RAISE(ABORT, 'issuer_fiscal_calendar_declarations are append-only'); END;
CREATE TRIGGER IF NOT EXISTS issuer_fiscal_calendar_declarations_no_delete BEFORE DELETE ON issuer_fiscal_calendar_declarations
BEGIN SELECT RAISE(ABORT, 'issuer_fiscal_calendar_declarations are append-only'); END;

CREATE TRIGGER IF NOT EXISTS observation_filing_documents_no_update BEFORE UPDATE ON observation_filing_documents
BEGIN SELECT RAISE(ABORT, 'observation_filing_documents are append-only'); END;
CREATE TRIGGER IF NOT EXISTS observation_filing_documents_no_delete BEFORE DELETE ON observation_filing_documents
BEGIN SELECT RAISE(ABORT, 'observation_filing_documents are append-only'); END;

COMMIT;