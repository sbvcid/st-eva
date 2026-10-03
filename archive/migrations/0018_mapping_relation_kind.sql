-- ST-EVA 2.73 - separate identity from composition in the mapping model.
--
-- One row shape has been carrying two different relations.
-- `us-gaap:LongTermDebtCurrent` -> `long_term_debt` says "this concept is one of
-- my components"; the same concept -> `long_term_debt_current` says "this
-- concept expresses that metric". The registry could not tell them apart, because
-- DIRECT-ness was derived from whether the declaring metric was superseded -- and
-- an aggregate naming its own components passes that test while meaning
-- something categorically different.
--
-- 2.72 measured the consequence: promoting the component mapping left the
-- concept AMBIGUOUS between the aggregate that names it and the component it
-- belongs to, even though the two rows are the same relation read in opposite
-- directions. The fix is neither to weaken a row nor to date one out.
--
-- SCHEMA ONLY. Two nullable columns, and it classifies nothing.
--
-- An earlier draft carried UPDATE statements setting relation_kind. That does not
-- work and must not be reintroduced: migrations run before the seed populates the
-- registry, so `seed()` re-inserts every row through `add_mapping` with the
-- dataclass default and overwrites the classification. `registry_seed.py` is the
-- authoritative source for relation_kind and scope_json; this file only gives them
-- somewhere to live.
--
-- Both columns are nullable and additive, so an archive opened read-only without
-- applying migrations has neither, and every reader treats a missing column as
-- absent metadata rather than failing.

ALTER TABLE metric_concept_mapping ADD COLUMN relation_kind TEXT;
ALTER TABLE metric_concept_mapping ADD COLUMN scope_json TEXT;
