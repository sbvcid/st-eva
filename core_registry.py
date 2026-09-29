from __future__ import annotations

"""
ST-EVA 2.5 - the Core Registry.

    metric_registry          what a metric means
    concept_registry         what a source concept is
    metric_concept_mapping   how one relates to the other

The registry exists so the database can answer *what an item is* rather than
only *what it is called*. A filer may change the tag it uses for a fact without
changing the fact, and may use a different tag for a genuinely different
quantity. Only an explicit mapping tells those apart.

Three rules the module holds, each because the alternative was measured to be
wrong against real AAPL filings:

    A concept is not a metric. `us-gaap:Revenues` is a tag a filer applies;
    `revenue` is a meaning ST-EVA names. Equating them by name is how a silent
    discontinuity gets spliced into one series.

    A missing retrieval is never evidence of inapplicability. A metric is
    NOT_APPLICABLE because of what the concept means for that business, or
    because the registry says so, and never because a fetch returned nothing.

    The registry resolves nothing. It does not rank sources, pick a winner in a
    conflict, or infer a value. It states what things mean and how they relate,
    and the 2.4.3 states stay where they were decided.
"""

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Business models a metric can be excluded for. A model is a property of the
# issuer, not of the metric, and it is recorded only when a concept genuinely
# does not exist for that kind of business.
BANK = "BANK"
INSURANCE = "INSURANCE"
REIT = "REIT"
MINING = "MINING"
BUSINESS_MODELS = (BANK, INSURANCE, REIT, MINING)

# Metric vocabularies, mirroring the migration's triggers.
STATEMENTS = (
    "INCOME",
    "BALANCE_SHEET",
    "CASH_FLOW",
    "CAPITAL_RETURN",
    "MARKET",
)
UNIT_FAMILIES = ("currency", "per_share", "count", "ratio", "multiple")
PERIOD_TYPES = ("DURATION", "INSTANT")
APPLICABILITIES = ("APPLICABLE", "CONDITIONAL", "NOT_APPLICABLE")
METRIC_STATUSES = ("ACTIVE", "DEPRECATED", "PROPOSED")

# The mapping vocabulary, and the one rule that matters: only EXACT and
# EQUIVALENT let a series continue across a change of concept.
MAPPING_EXACT = "EXACT"
MAPPING_EQUIVALENT = "EQUIVALENT"
MAPPING_PARTIAL = "PARTIAL"
MAPPING_NON_COMPARABLE = "NON_COMPARABLE"

MAPPING_TYPES = (
    MAPPING_EXACT,
    MAPPING_EQUIVALENT,
    MAPPING_PARTIAL,
    MAPPING_NON_COMPARABLE,
)

# A series continues only through these. A PARTIAL mapping is a wider or
# narrower aggregate, and NON_COMPARABLE is a different quantity, so splicing
# across either would splice two different numbers into one line.
CONTINUING_MAPPINGS = frozenset({MAPPING_EXACT, MAPPING_EQUIVALENT})


class RegistryError(Exception):
    """The registry was asked for something it does not hold."""


@dataclass(frozen=True)
class Metric:
    """What a metric means, independently of who reports it."""

    metric_id: str
    display_name: str
    statement: str
    semantic_definition: str
    unit_family: str
    normal_period_type: str
    applicability: str = "APPLICABLE"
    comparability_group: Optional[str] = None
    status: str = "ACTIVE"
    # Business models in which the concept does not exist. A metric is never
    # added to this list because nothing was retrieved for it.
    inapplicable_in: Tuple[str, ...] = ()

    def applies_to(self, business_model: Optional[str]) -> bool:
        """
        Whether the metric is applicable to a business.

        A business model we do not know about is not evidence of
        inapplicability, so an unknown model applies rather than being refused.
        """
        if self.applicability == "NOT_APPLICABLE":
            return False
        if not business_model or not self.inapplicable_in:
            return True
        return business_model not in self.inapplicable_in

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "display_name": self.display_name,
            "statement": self.statement,
            "semantic_definition": self.semantic_definition,
            "unit_family": self.unit_family,
            "normal_period_type": self.normal_period_type,
            "applicability": self.applicability,
            "comparability_group": self.comparability_group,
            "status": self.status,
            "inapplicable_in": list(self.inapplicable_in),
        }


@dataclass(frozen=True)
class Concept:
    """A source concept, with the source's own definition of it."""

    concept_id: str
    taxonomy: str
    concept: str
    label: Optional[str] = None
    source_definition: Optional[str] = None

    @property
    def qualified(self) -> str:
        return f"{self.taxonomy}:{self.concept}"

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "concept_id": self.concept_id,
            "taxonomy": self.taxonomy,
            "concept": self.concept,
            "qualified": self.qualified,
            "label": self.label,
            "source_definition": self.source_definition,
        }


@dataclass(frozen=True)
class ConceptMapping:
    """How one source concept expresses one metric, and how exactly."""

    metric_id: str
    concept_id: str
    mapping_type: str
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    notes: Optional[str] = None

    def __post_init__(self) -> None:
        if self.mapping_type not in MAPPING_TYPES:
            raise RegistryError(
                f"mapping_type {self.mapping_type!r} is not in {list(MAPPING_TYPES)}"
            )
        if self.mapping_type not in CONTINUING_MAPPINGS and not (
            self.effective_from or self.effective_to
        ):
            raise RegistryError(
                f"{self.mapping_type} mapping must record effective dates, "
                "because the series does not continue across it"
            )

    @property
    def series_continues(self) -> bool:
        return self.mapping_type in CONTINUING_MAPPINGS

    def applies_on(self, when: Optional[str]) -> bool:
        """
        Whether the mapping held on a date.

        No date means no time filter, so every mapping applies. Narrowing to the
        unbounded ones would silently hide a concept that stopped being reported,
        which is the one thing this table exists to make visible.
        """
        if not when:
            return True
        if self.effective_from and when < self.effective_from:
            return False
        if self.effective_to and when > self.effective_to:
            return False
        return True

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "concept_id": self.concept_id,
            "mapping_type": self.mapping_type,
            "series_continues": self.series_continues,
            "effective_from": self.effective_from,
            "effective_to": self.effective_to,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ResolvedEvidence:
    """
    An observation resolved through the registry.

    `metric` is None when the registry does not hold the concept. That is the
    answer, and it is deliberately not filled with a name-based guess: an
    unmapped concept must be visible as unmapped rather than quietly attached
    to the nearest metric.
    """

    observation_id: str
    concept_id: Optional[str]
    metric: Optional[Metric]
    mappings: Tuple[ConceptMapping, ...] = ()
    series_breaks: Tuple[Dict[str, Any], ...] = ()

    @property
    def is_resolved(self) -> bool:
        return self.metric is not None

    def contract_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "observation_id": self.observation_id,
            "resolved": self.is_resolved,
            "concept": self.concept_id,
            "metric": self.metric.metric_id if self.metric else None,
            "metric_definition": (
                self.metric.semantic_definition if self.metric else None
            ),
            "mappings": [mapping.contract_dict() for mapping in self.mappings],
            "series_breaks": [dict(break_) for break_ in self.series_breaks],
        }
        if not self.is_resolved:
            payload["reason"] = (
                self.series_breaks[0]["explanation"]
                if self.series_breaks
                else (
                    "NOT_EXPLAINED. No registry mapping relates this concept to "
                    "a metric. It is left unresolved rather than attached to "
                    "the metric whose name looks nearest."
                )
            )
        return payload


def concept_id_for(taxonomy: str, concept: str) -> str:
    return f"{taxonomy}:{concept}"


class CoreRegistry:
    """A read/write view over the three registry tables."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    # -- writes ----------------------------------------------------------

    def add_metric(
        self,
        metric: Metric,
        inapplicable_in: Sequence[str] = (),
    ) -> str:
        self.connection.execute(
            "INSERT OR REPLACE INTO metric_registry (metric_id, display_name,"
            " statement, semantic_definition, unit_family, normal_period_type,"
            " applicability, comparability_group, status)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                metric.metric_id,
                metric.display_name,
                metric.statement,
                metric.semantic_definition,
                metric.unit_family,
                metric.normal_period_type,
                metric.applicability,
                metric.comparability_group,
                metric.status,
            ),
        )
        if inapplicable_in:
            self._set_inapplicable(metric.metric_id, inapplicable_in)
        self.connection.commit()
        return metric.metric_id

    def _set_inapplicable(self, metric_id: str, models: Sequence[str]) -> None:
        """
        Applicability per business model.

        Held beside the metric rather than inside it, because a model is a
        property of the issuer and not of the metric. It is recorded only when
        a business model is actually excluded; an empty list stays empty, and
        never stands in for a retrieval that found nothing.

        The table is created once and never rebuilt. Dropping it per call would
        silently discard the previous metric's exclusions, which is how an
        operating income would quietly become applicable to a bank.
        """
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS metric_inapplicable_in ("
            " metric_id TEXT NOT NULL REFERENCES metric_registry(metric_id),"
            " business_model TEXT NOT NULL,"
            " PRIMARY KEY (metric_id, business_model))"
        )
        for model in models:
            self.connection.execute(
                "INSERT OR IGNORE INTO metric_inapplicable_in"
                " (metric_id, business_model) VALUES (?, ?)",
                (metric_id, model),
            )

    def add_concept(self, concept: Concept) -> str:
        self.connection.execute(
            "INSERT OR REPLACE INTO concept_registry (concept_id, taxonomy,"
            " concept, label, source_definition) VALUES (?, ?, ?, ?, ?)",
            (
                concept.concept_id,
                concept.taxonomy,
                concept.concept,
                concept.label,
                concept.source_definition,
            ),
        )
        self.connection.commit()
        return concept.concept_id

    def add_mapping(self, mapping: ConceptMapping) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO metric_concept_mapping (metric_id,"
            " concept_id, mapping_type, effective_from, effective_to, notes)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                mapping.metric_id,
                mapping.concept_id,
                mapping.mapping_type,
                mapping.effective_from,
                mapping.effective_to,
                mapping.notes,
            ),
        )
        self.connection.commit()

    # -- reads -----------------------------------------------------------

    def metric(self, metric_id: str) -> Optional[Metric]:
        row = self.connection.execute(
            "SELECT * FROM metric_registry WHERE metric_id = ?",
            (metric_id,),
        ).fetchone()
        if row is None:
            return None
        models = [
            r["business_model"]
            for r in self.connection.execute(
                "SELECT business_model FROM metric_inapplicable_in"
                " WHERE metric_id = ?",
                (metric_id,),
            )
        ]
        return Metric(
            metric_id=row["metric_id"],
            display_name=row["display_name"],
            statement=row["statement"],
            semantic_definition=row["semantic_definition"],
            unit_family=row["unit_family"],
            normal_period_type=row["normal_period_type"],
            applicability=row["applicability"],
            comparability_group=row["comparability_group"],
            status=row["status"],
            inapplicable_in=tuple(sorted(models)),
        )

    def concept(self, concept_id: str) -> Optional[Concept]:
        row = self.connection.execute(
            "SELECT * FROM concept_registry WHERE concept_id = ?"
            " OR (taxonomy || ':' || concept) = ? LIMIT 1",
            (concept_id, concept_id),
        ).fetchone()
        if row is None:
            return None
        return Concept(
            concept_id=row["concept_id"],
            taxonomy=row["taxonomy"],
            concept=row["concept"],
            label=row["label"],
            source_definition=row["source_definition"],
        )

    def metrics(self, statement: Optional[str] = None) -> List[Metric]:
        if statement:
            rows = self.connection.execute(
                "SELECT metric_id FROM metric_registry WHERE statement = ?"
                " ORDER BY metric_id",
                (statement,),
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT metric_id FROM metric_registry ORDER BY metric_id"
            ).fetchall()
        return [
            metric
            for metric in (self.metric(row["metric_id"]) for row in rows)
            if metric is not None
        ]

    def mappings_for_metric(
        self,
        metric_id: str,
        as_of: Optional[str] = None,
    ) -> List[ConceptMapping]:
        rows = self.connection.execute(
            "SELECT * FROM metric_concept_mapping WHERE metric_id = ?"
            " ORDER BY mapping_type, effective_from, concept_id",
            (metric_id,),
        ).fetchall()
        return [
            mapping
            for mapping in (self._mapping(row) for row in rows)
            if mapping is not None and mapping.applies_on(as_of)
        ]

    def metrics_for_concept(
        self,
        concept_id: str,
        as_of: Optional[str] = None,
    ) -> List[Tuple[ConceptMapping, Optional[Metric]]]:
        """
        Every metric a concept can express.

        More than one is a legitimate answer rather than a defect to resolve: a
        vendor's "total cash" may be an aggregate, and returning only the
        closest-looking metric would be the name-based guess this registry
        exists to avoid.
        """
        rows = self.connection.execute(
            "SELECT * FROM metric_concept_mapping WHERE concept_id = ?"
            " ORDER BY mapping_type, metric_id",
            (concept_id,),
        ).fetchall()
        results: List[Tuple[ConceptMapping, Optional[Metric]]] = []
        for row in rows:
            mapping = self._mapping(row)
            if mapping is None or not mapping.applies_on(as_of):
                continue
            results.append((mapping, self.metric(mapping.metric_id)))
        return results

    def _mapping(self, row: sqlite3.Row) -> Optional[ConceptMapping]:
        try:
            return ConceptMapping(
                metric_id=row["metric_id"],
                concept_id=row["concept_id"],
                mapping_type=row["mapping_type"],
                effective_from=row["effective_from"],
                effective_to=row["effective_to"],
                notes=row["notes"],
            )
        except RegistryError:
            return None

    def resolve(
        self,
        concept_id: str,
        as_of: Optional[str] = None,
    ) -> ResolvedEvidence:
        """
        Resolve a concept to the metric it means.

        An unmapped concept resolves to nothing. It is not attached to the
        metric whose name looks nearest, because that is precisely the inference
        this registry exists to make explicit and to refuse to make silently.
        """
        candidates = self.metrics_for_concept(concept_id, as_of=as_of)
        if not candidates:
            return ResolvedEvidence(
                observation_id="",
                concept_id=concept_id if self.concept(concept_id) else None,
                metric=None,
            )

        # A concept that maps to more than one metric is a registry question,
        # not something to settle here. It is reported as unresolved with every
        # candidate attached, so the ambiguity is visible instead of resolved.
        if len(candidates) > 1:
            return ResolvedEvidence(
                observation_id="",
                concept_id=concept_id,
                metric=None,
                mappings=tuple(mapping for mapping, _ in candidates),
                series_breaks=(
                    {
                        "kind": "AMBIGUOUS_MAPPING",
                        "metric_ids": [
                            mapping.metric_id for mapping, _ in candidates
                        ],
                        "explanation": (
                            "NOT_EXPLAINED. One concept maps to several "
                            "metrics, so the registry does not choose. This "
                            "is a registry question for a filer to answer, not "
                            "one to settle by name."
                        ),
                    },
                ),
            )

        mapping, metric = candidates[0]
        return ResolvedEvidence(
            observation_id="",
            concept_id=concept_id,
            metric=metric,
            mappings=(mapping,),
        )

    def series_breaks(
        self,
        metric_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Where a metric's series must break.

        A PARTIAL or NON_COMPARABLE mapping is a change in what was measured,
        so joining the periods on either side of it would splice two different
        numbers into one line. This is the 2.4.3 rule applied to a change of
        concept rather than a change of period length.
        """
        breaks: List[Dict[str, Any]] = []
        for mapping in self.mappings_for_metric(metric_id):
            if mapping.series_continues:
                continue
            breaks.append(
                {
                    "kind": "CONCEPT_MAPPING_BREAK",
                    "metric_id": metric_id,
                    "concept_id": mapping.concept_id,
                    "mapping_type": mapping.mapping_type,
                    "effective_from": mapping.effective_from,
                    "effective_to": mapping.effective_to,
                    "explanation": "NOT_EXPLAINED_BY_ST_EVA",
                }
            )
        return breaks
