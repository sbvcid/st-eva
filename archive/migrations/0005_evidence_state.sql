-- ST-EVA 2.5.1 - evidence state, so a missing item can say why.
--
-- A single "missing" cannot distinguish four different situations that imply
-- different next actions: the source omits the item, the concept does not
-- exist for this business, our retrieval failed, or what we hold has gone
-- stale. This table makes the distinction queryable.
--
-- NOT_APPLICABLE is a statement, not an absence. A bank has no operating-income
-- tag and a mining company has no inventory; recorded as null, both would be
-- indistinguishable from a failed request.

CREATE TABLE IF NOT EXISTS evidence_state (
    asset_id    TEXT NOT NULL,
    metric      TEXT NOT NULL,
    state       TEXT NOT NULL,
    reason_kind TEXT,
    reason_code TEXT,
    detail      TEXT,
    as_of       TEXT,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (asset_id, metric),
    FOREIGN KEY (asset_id) REFERENCES assets(asset_id)
);

-- The state vocabulary is closed, so a consumer can branch on it and a
-- coverage report can be compared across runs.
CREATE TRIGGER IF NOT EXISTS evidence_state_vocabulary
BEFORE INSERT ON evidence_state
WHEN NEW.state NOT IN (
    'SOURCE_REPORTED', 'SOURCE_DID_NOT_REPORT', 'NOT_APPLICABLE',
    'UNAVAILABLE', 'CONFLICTING', 'STALE'
)
BEGIN
    SELECT RAISE(ABORT, 'evidence_state.state is outside the closed vocabulary');
END;

-- A reported item must carry a value, and a non-reported one must not claim
-- one. Otherwise the table becomes a second, unchecked copy of the value.
CREATE TRIGGER IF NOT EXISTS evidence_state_consistent
BEFORE INSERT ON evidence_state
WHEN (NEW.state = 'SOURCE_REPORTED' AND NEW.detail IS NULL)
  OR (NEW.state IN ('SOURCE_DID_NOT_REPORT', 'NOT_APPLICABLE')
      AND NEW.detail IS NOT NULL)
BEGIN
    SELECT RAISE(ABORT,
        'SOURCE_REPORTED requires a locator; the negative states must not');
END;

CREATE INDEX IF NOT EXISTS evidence_state_by_metric ON evidence_state(metric, state);
