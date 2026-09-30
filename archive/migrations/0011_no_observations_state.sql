-- ST-EVA 2.7 - NO_OBSERVATIONS, and the availability/applicability split.
--
-- Migration 0010 made an issuer's business model recordable, which is what let
-- `NOT_APPLICABLE` be derived from the registry rather than asserted per issuer.
-- That exposed the state that was hiding behind it.
--
-- With applicability reachable, there are three different facts a coverage
-- report can be asked about a metric, and the closed vocabulary had room for
-- two of them:
--
--     NOT_APPLICABLE    this metric does not exist for this kind of company
--     UNAVAILABLE       an attempt was made and produced no figure
--     (nothing)         the metric applies and nothing has been collected yet
--
-- The third had no token, so it was reported as the second. That is a fact about
-- the archive being small wearing the vocabulary of a fact about retrieval
-- having failed, and it is the same collapse 0005 was written to prevent from
-- the other direction -- there, a recorded absence was at least not allowed to
-- masquerade as a failed request; here a not-yet-collected figure is.
--
-- The new state is closed like the others, and the "negative states must not
-- carry a locator" rule is extended to it for the same reason it exists: a
-- negative state that also points at a value is a second, unchecked copy of
-- that value.
--
-- The triggers are dropped and recreated rather than edited, because migrations
-- are forward-only and an archive that ran the earlier build must keep running
-- the earlier rules. Recreating them with the wider vocabulary is the honest
-- form of a change: a row written under 0005 is still valid, and a row written
-- under this one is valid under a rule that says one more thing.

DROP TRIGGER IF EXISTS evidence_state_vocabulary;

CREATE TRIGGER IF NOT EXISTS evidence_state_vocabulary
BEFORE INSERT ON evidence_state
WHEN NEW.state NOT IN (
    'SOURCE_REPORTED', 'SOURCE_DID_NOT_REPORT', 'NOT_APPLICABLE',
    'NO_OBSERVATIONS', 'UNAVAILABLE', 'CONFLICTING', 'STALE'
)
BEGIN
    SELECT RAISE(ABORT, 'evidence_state.state is outside the closed vocabulary');
END;

DROP TRIGGER IF EXISTS evidence_state_consistent;

CREATE TRIGGER IF NOT EXISTS evidence_state_consistent
BEFORE INSERT ON evidence_state
WHEN (NEW.state = 'SOURCE_REPORTED' AND NEW.detail IS NULL)
  OR (NEW.state IN ('SOURCE_DID_NOT_REPORT', 'NOT_APPLICABLE',
                    'NO_OBSERVATIONS')
      AND NEW.detail IS NOT NULL)
BEGIN
    SELECT RAISE(ABORT, 'SOURCE_REPORTED requires a locator; the negative states must not');
END;

-- NOT_APPLICABLE is reachable two ways and both are legitimate.
--
--     an explicit state row, recorded with its own reason code
--     derived from the registry, for an issuer whose business model says so
--
-- An earlier draft of this migration closed the second path by refusing a
-- `NOT_APPLICABLE` row for an issuer with no recorded business model. That was
-- wrong and it broke the 2.5 fixtures, which record a reasoned negative state
-- for a single issuer and have always been allowed to. The trigger confused
-- "this row is a claim" with "this row must be registry-derived", and the two
-- are different: the row is a recorded assertion with a reason, and the
-- registry is simply a second, independent route to the same state.
--
-- What is worth forbidding is the *absence* being read as inapplicability,
-- and that is not a trigger's job -- it is a derivation, and
-- `EvidenceQuery._inapplicable_reason` only fires when a business model has
-- actually been recorded.

CREATE INDEX IF NOT EXISTS evidence_state_by_metric
    ON evidence_state(metric, state);
