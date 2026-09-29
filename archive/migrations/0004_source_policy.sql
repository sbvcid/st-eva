-- ST-EVA 2.5.4 - redistribution policy on a source.
--
-- A source's redistribution tier is a property of the source, not of whichever
-- component happened to fetch it, and the query surface must be able to report
-- it so a consumer can tell a reference it may not republish from one it may.
--
-- Default is 'B', reference only, because a source nobody classified should
-- keep its bytes local until someone decides otherwise. Silently returning
-- content for an unclassified source would defeat the point of the tier.

ALTER TABLE sources ADD COLUMN redistribution_tier TEXT NOT NULL DEFAULT 'B';
ALTER TABLE sources ADD COLUMN fair_access_policy TEXT;
ALTER TABLE sources ADD COLUMN contact_identity TEXT;

-- 'A' retain and publish structured values with their citations
-- 'B' reference only; keep bytes locally, publish the pointer
-- 'C' never collect
CREATE TRIGGER IF NOT EXISTS sources_tier_vocabulary
BEFORE INSERT ON sources
WHEN NEW.redistribution_tier NOT IN ('A', 'B', 'C')
BEGIN
    SELECT RAISE(ABORT, 'sources.redistribution_tier must be A, B or C');
END;
