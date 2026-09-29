-- ST-EVA 2.4.1 - source document capture.
--
-- Forward-only. `0001_initial` is never edited; a changed shape is a new
-- migration. The recorded checksum of 0001 is verified at startup, so an
-- archive created by an earlier build migrates cleanly.
--
-- This adds the captured content itself, so "which document did this
-- observation come from" is answerable years later rather than merely
-- asserted by a URL.

ALTER TABLE source_documents ADD COLUMN provider TEXT;
ALTER TABLE source_documents ADD COLUMN document_type TEXT;
ALTER TABLE source_documents ADD COLUMN canonical_uri TEXT;

-- The captured bytes, gzip-compressed. `content_hash` is always the hash of the
-- *uncompressed* bytes, so it means the same thing whether or not the content
-- was kept. NULL content means the policy was to keep an immutable reference
-- (the hash and the URI) rather than the payload.
ALTER TABLE source_documents ADD COLUMN content BLOB;
ALTER TABLE source_documents ADD COLUMN content_encoding TEXT;

-- A captured document whose content is kept must be complete: a hash with no
-- bytes is a reference, and conflating the two would let a truncated capture
-- pass for an intact one.
CREATE TRIGGER IF NOT EXISTS source_documents_capture_consistent
BEFORE INSERT ON source_documents
WHEN NEW.content IS NOT NULL
     AND (NEW.content_hash IS NULL OR NEW.content_encoding IS NULL
          OR NEW.byte_size IS NULL)
BEGIN
    SELECT RAISE(ABORT,
        'a stored document needs a content hash, an encoding, and a byte size');
END;

-- A document that is referenced by a stored observation is evidence, and this
-- table offers no delete path at all. The constraint below makes the intent
-- explicit for a reader rather than implicit in the absence of code.
CREATE TRIGGER IF NOT EXISTS source_documents_no_delete
BEFORE DELETE ON source_documents
BEGIN
    SELECT RAISE(ABORT,
        'a captured source document is evidence and is never deleted');
END;
