-- ST-EVA 2.4.2 - persist the security / share / price basis of an observation.
--
-- Forward-only. `0001_initial` and `0002_source_capture` are not edited.
--
-- An observation gained a `basis` block so that a price quoted per ADS and a
-- filing count of ordinary shares cannot be silently combined. An archive that
-- dropped that field on the way out would replay a document that disagrees
-- with the one it stored, for a reason that has nothing to do with the data:
-- a stored observation must round-trip to the same observation.

ALTER TABLE observations ADD COLUMN basis_json TEXT;
