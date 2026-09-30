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

from data_contract import utc_now

# Business models a metric can be excluded for. A model is a property of the
# issuer, not of the metric, and it is recorded only when a concept genuinely
# does not exist for that kind of business.
BANK = "BANK"
INSURANCE = "INSURANCE"
REIT = "REIT"
MINING = "MINING"
INSURANCE = "INSURANCE"
REIT = "REIT"
MINING = "MINING"
# A filer classified by the SEC under SIC major group 61 or 62: banks, insurers
# and finance companies. Added in 2.7 because a filer that publishes that
# classification was previously unrepresentable, and a financial institution
# that could not be recorded was a financial institution whose inapplicable
# metrics fell through to `UNAVAILABLE` and reported a retrieval failure for a
# line that does not exist.
#
# `BANK` stays in the vocabulary. It was declared against a metric before any
# issuer could be classified at all, and deleting it would silently make
# operating income applicable to every issuer this round did not touch.
FINANCE_SERVICES = "FINANCE_SERVICES"
# `OPERATING` is what a filer is when nothing more specific is warranted, and it
# is deliberately a member rather than the absence of one: an issuer recorded as
# `None` has had no ruling made, and an issuer recorded as `OPERATING` has been
# looked at and found to be an ordinary business. The two read the same in a
# coverage report and mean different things, and the difference is the whole
# point of the record.
OPERATING = "OPERATING"
MANUFACTURING = "MANUFACTURING"
TECHNOLOGY = "TECHNOLOGY"
# SIC major group 70-89: services. Added in 2.10 because the 2.9 collection gates
# failed for one issuer on all twenty of its metrics, and the reason was not a
# wrong ruling -- it was that there were none, because a services classification
# fell outside the rule and an unrecognised classification deliberately makes
# none.
#
# It carries no exclusion of its own, and that is the point. A business model
# earns a place in this vocabulary by carrying a ruling, and this one currently
# does not, so adding it closes a metadata gap and deliberately moves no
# coverage. Had the collection numbers moved, that would have been the first
# thing to check rather than a result.
SERVICES = "SERVICES"
BUSINESS_MODELS = (
    OPERATING,
    MANUFACTURING,
    TECHNOLOGY,
    SERVICES,
    FINANCE_SERVICES,
    BANK,
    INSURANCE,
    REIT,
    MINING,
)

# Why a taxonomy carries no semantic metric. The distinctions are not decoration:
# a taxonomy of transaction mechanics needs no work, an industry taxonomy might,
# and a reader who cannot tell those apart gets a number with no remedy attached.
UNMODELLED_TRANSACTION_DISCLOSURE = "TRANSACTION_DISCLOSURE"
UNMODELLED_EXECUTIVE_COMPENSATION = "EXECUTIVE_COMPENSATION"
UNMODELLED_NARRATIVE_TEXT = "NARRATIVE_TEXT"
UNMODELLED_INDUSTRY_SPECIFIC = "INDUSTRY_SPECIFIC"
UNMODELLED_OUT_OF_SCOPE = "OUT_OF_SCOPE"
UNMODELLED_KINDS = (
    UNMODELLED_TRANSACTION_DISCLOSURE,
    UNMODELLED_EXECUTIVE_COMPENSATION,
    UNMODELLED_NARRATIVE_TEXT,
    UNMODELLED_INDUSTRY_SPECIFIC,
    UNMODELLED_OUT_OF_SCOPE,
)

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
METRIC_STATUSES = ("ACTIVE", "DEPRECASED", "PROPOSED")

# How an issuer came to be classified, mirroring the migration's trigger. A
# reader has to be able to tell "the filer publishes this" from "somebody decided
# this" without opening a comment, because the two support very different
# confidence in an inapplicability ruling.
BUSINESS_MODEL_BASES = (
    "DECLARED_BY_ISSUER",
    "DERIVED_FROM_REPORTED_CONCEPTS",
    "MANUAL_CLASSIFICATION",
)

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

# Why a source concept was considered for a metric and not mapped to it.
#
# Closed, because the distinction that matters is *which kind* of near-miss it
# is, and a free-text reason cannot be branched on. A component of the metric, a
# wider aggregate of it, a measure of something else, a count of a different
# population and a figure that is not a measurement at all all read as "not
# mapped" in a flat list, and they call for completely different responses:
# the first two are the metric's own definition, the third is a different
# question, the fourth is a near miss worth revisiting, and the fifth is out of
# scope entirely.
REASON_COMPONENT_OF = "COMPONENT_OF"
REASON_WIDER_AGGREGATE = "WIDER_AGGREGATE"
REASON_NARROWER_AGGREGATE = "NARROWER_AGGREGATE"
REASON_DIFFERENT_QUANTITY = "DIFFERENT_QUANTITY"
REASON_IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
REASON_NOT_A_METRIC = "NOT_A_METRIC"
DECLINE_REASONS = (
    REASON_COMPONENT_OF,
    REASON_WIDER_AGGREGATE,
    REASON_NARROWER_AGGREGATE,
    REASON_DIFFERENT_QUANTITY,
    REASON_IDENTITY_MISMATCH,
    REASON_NOT_A_METRIC,
)

# A series continues only through these. A PARTIAL mapping is a wider or
# narrower aggregate, and NON_COMPARABLE is a different quantity, so splicing
# across either would splice two different numbers into one line.
CONTINUING_MAPPINGS = frozenset({MAPPING_EXACT, MAPPING_EQUIVALENT})

# The adoption basis, closed for the same reason every other vocabulary here is
# closed. `OBSERVED_ADOPTION` is the only honest claim available from a filing:
# "this filer's own filings reported this concept in these periods". It is not
# the taxonomy's validity period and not a statement that the filer intends to
# stop, and a value that let a stronger claim in would make "how much do we
# actually know here?" unanswerable.
OBSERVED_ADOPTION = "OBSERVED_ADOPTION"
ADOPTION_BASES = (OBSERVED_ADOPTION,)


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
class DeclinedConcept:
    """
    A source concept that was weighed against a metric and rejected.

    The counterpart to `ConceptMapping`, and the more informative of the two for
    a coverage question. A mapping says "this concept means this metric". This
    says "this concept was considered, and here is why it is not" -- which is
    what separates a metric ST-EVA has no opinion about from one it has decided
    about, and those are different things to read in a coverage report.
    """

    concept_id: str
    considered_for_metric: str
    reason_code: str
    reason: str
    # Which framework reading produced it, so a decline about an IFRS element is
    # not read as a claim about the US-GAAP one. None where the judgement does
    # not depend on the framework.
    framework_basis: Optional[str] = None

    def __post_init__(self) -> None:
        if self.reason_code not in DECLINE_REASONS:
            raise RegistryError(
                f"decline reason_code {self.reason_code!r} is not in "
                f"{list(DECLINE_REASONS)}"
            )
        if not self.reason or not self.reason.strip():
            # A decline with no stated reason is an omission wearing a
            # decision's clothes, and the code alone does not say which of the
            # six it is.
            raise RegistryError(
                "a decline must state why, not only which category"
            )
        if ":" not in (self.concept_id or ""):
            raise RegistryError(
                "a decline concept_id must be qualified as taxonomy:concept"
            )

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "concept_id": self.concept_id,
            "considered_for_metric": self.considered_for_metric,
            "reason_code": self.reason_code,
            "reason": self.reason,
            "framework_basis": self.framework_basis,
        }


@dataclass(frozen=True)
class ConceptAdoption:
    """
    One filer's observed use of one concept, over a period.

    The counterpart to `ConceptMapping`, and the reason that class cannot answer
    every question. A mapping says what a concept means; this says when one
    company was seen using it. They differ, and conflating them is what produced
    a global window that was really AAPL's filing history.

    `basis` is `OBSERVED_ADOPTION` and nothing else. These are the periods that
    filer's filings reported, which is a weaker claim than a statement of intent:
    a filer that stopped reporting in 2018 has not necessarily retired the
    concept, and this record must never be read as saying that it has.
    """

    asset_id: str
    concept_id: str
    first_used: Optional[str]
    last_used: Optional[str]
    fact_count: int
    filing_count: int
    basis: str = OBSERVED_ADOPTION

    def covers(self, when: Optional[str]) -> bool:
        """
        Whether this filer was observed using the concept on a date.

        No date means no time filter, matching `ConceptMapping.applies_on`. An
        unobserved date is not evidence of non-use, so a caller asking about a
        date with no adoption record must not read this as a refusal.
        """
        if not when:
            return True
        if self.first_used and when < self.first_used:
            return False
        if self.last_used and when > self.last_used:
            return False
        return True

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "concept_id": self.concept_id,
            "first_used": self.first_used,
            "last_used": self.last_used,
            "fact_count": self.fact_count,
            "filing_count": self.filing_count,
            "basis": self.basis,
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
    # What the filing evidence says this filer did with the concept, when it has
    # been ingested. None means "not observed", which is a gap in what we hold
    # and never a claim that the filer did not use the concept.
    adoption: Optional[ConceptAdoption] = None
    # True when adoption supplied a period the mapping window did not cover. It
    # is surfaced rather than silently absorbed, because a figure that resolves
    # outside its concept's stated window is worth a reader knowing about.
    adopted_outside_mapping_window: bool = False

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
            "issuer_adoption": (
                self.adoption.contract_dict() if self.adoption else None
            ),
            "adopted_outside_mapping_window": (
                self.adopted_outside_mapping_window
            ),
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

    def set_issuer_business_model(
        self,
        asset_id: str,
        business_model: str,
        basis: str = "MANUAL_CLASSIFICATION",
        source: Optional[str] = None,
    ) -> None:
        """
        Record which business an issuer is in, and how that was established.

        Issuer metadata, not a metric property and not a company code path. The
        reason this exists is that `metric_inapplicable_in` had a column no row
        could fill, so a metric correctly declared inapplicable for a financial
        institution could never be resolved for one -- and the surface fell
        through to `UNAVAILABLE`, reporting a retrieval failure for a line that
        does not exist.
        """
        if business_model not in BUSINESS_MODELS:
            raise RegistryError(
                f"business_model {business_model!r} is not in "
                f"{list(BUSINESS_MODELS)}"
            )
        if not self._has_business_models():
            raise RegistryError(
                "this archive predates migration 0010 and has no "
                "issuer_business_model table. Writing a classification into an "
                "archive that cannot be migrated would record a fact with "
                "nothing enforcing its vocabulary."
            )
        if basis not in BUSINESS_MODEL_BASES:
            raise RegistryError(
                f"business model basis {basis!r} is not in "
                f"{list(BUSINESS_MODEL_BASES)}"
            )
        if basis != "MANUAL_CLASSIFICATION" and not source:
            raise RegistryError(
                "a declared or derived business model must name the source it "
                "came from; an inapplicability ruling rests on it"
            )
        self.connection.execute(
            "INSERT OR REPLACE INTO issuer_business_model (asset_id,"
            " business_model, basis, source, recorded_at) VALUES (?, ?, ?, ?, ?)",
            (asset_id, business_model, basis, source, utc_now()),
        )
        self.connection.commit()

    def mark_taxonomy_unmodelled(
        self,
        taxonomy: str,
        kind: str,
        reason: str,
    ) -> None:
        """
        Declare that a source taxonomy carries no semantic metric, and say why.

        2.8 could not answer "what does a filer report that we have no mapping
        for?", and the answer turned out to be worth having: across six issuers
        the unmodelled part of a filer's XBRL is nineteen concepts in four
        taxonomies, and reading them shows they are the mechanics of securities
        offerings, executive compensation, narrative tagging and one industry
        namespace. None is a financial-statement metric.

        So the record is a *declaration about a taxonomy*, not a decline per
        concept and certainly not a coverage gap. A table rather than a name
        rule in the ledger, because a taxonomy is the unit at which the answer
        exists and because a name-based rule would have to match a concept to a
        metric -- the "similar label" problem 2.7 spent a phase refusing to
        solve by name.
        """
        if kind not in UNMODELLED_KINDS:
            raise RegistryError(
                f"unmodelled taxonomy kind {kind!r} is not in "
                f"{list(UNMODELLED_KINDS)}"
            )
        if not (reason or "").strip():
            raise RegistryError(
                "a taxonomy declared unmodelled must say why; a reader cannot "
                "tell whether it needs work without it"
            )
        self.connection.execute(
            "INSERT OR REPLACE INTO unmodelled_taxonomies (taxonomy, kind,"
            " reason, recorded_at) VALUES (?, ?, ?, ?)",
            (taxonomy, kind, reason, utc_now()),
        )
        self.connection.commit()

    def unmodelled_taxonomies(self) -> Dict[str, Dict[str, Any]]:
        """
        Every taxonomy the semantic layer declares nothing against, with its
        reason. Empty on an archive predating migration 0013, which is correct:
        such an archive has made no such declaration.
        """
        if self.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table'"
            " AND name = 'unmodelled_taxonomies'"
        ).fetchone() is None:
            return {}
        return {
            row["taxonomy"]: {
                "kind": row["kind"],
                "reason": row["reason"],
            }
            for row in self.connection.execute(
                "SELECT taxonomy, kind, reason FROM unmodelled_taxonomies"
                " ORDER BY taxonomy"
            )
        }

    def modelled_taxonomies(self) -> List[str]:
        """
        The taxonomies the semantic layer does model.

        Read from the concepts themselves rather than from a configured list, so
        it cannot fall behind a mapping that was added. A taxonomy is modelled
        when something in it has been given a definition.
        """
        return [
            row["taxonomy"]
            for row in self.connection.execute(
                "SELECT DISTINCT taxonomy FROM concept_registry"
                " ORDER BY taxonomy"
            )
        ]

    def decline_concept_mapping(
        self,
        concept_id: str,
        considered_for_metric: str,
        reason_code: str,
        reason: str,
        framework_basis: Optional[str] = None,
    ) -> None:
        """
        Record a source concept that was weighed against a metric and rejected.

        The counterpart to `add_mapping`, and the more informative of the two.
        A mapping says "this concept means this metric"; a decline says "this
        concept was considered for this metric and here is why it is not", which
        is the information a coverage figure needs and cannot get from a count.

        Without it, 2.7's nine IFRS decisions lived in seed-file prose, and an
        archive holding 3.0% of a filer's concepts could report what it held and
        not what it had deliberately left out. Those are different claims and a
        reader is entitled to the difference.

        Validated by building a `DeclinedConcept` and writing that, rather than
        by writing the fields directly. Two validation paths is how a blank
        reason ends up in a table whose trigger refuses one: the dataclass
        checked it on the seed path and the method did not check it here.
        """
        record = DeclinedConcept(
            concept_id=concept_id,
            considered_for_metric=considered_for_metric,
            reason_code=reason_code,
            reason=reason,
            framework_basis=framework_basis,
        )
        self.connection.execute(
            "INSERT OR REPLACE INTO declined_concept_mappings (concept_id,"
            " considered_for_metric, reason_code, reason, framework_basis,"
            " recorded_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                record.concept_id,
                record.considered_for_metric,
                record.reason_code,
                record.reason,
                record.framework_basis,
                utc_now(),
            ),
        )
        self.connection.commit()

    def declines_for_metric(
        self,
        metric_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Every concept that was considered for one metric and declined.

        Sorted by concept so a coverage report is stable between runs, which
        matters more here than it sounds: this list is read by a language model
        through the query surface, and a reordering would look like a change in
        what ST-EVA holds.

        Empty on an archive predating migration 0012, for the same reason
        `business_model_of` is: an archive that cannot have recorded a decision
        has recorded none, and the read path may not demand a migration it cannot
        ask for.
        """
        if not self._has_decline_records():
            return []
        return [
            dict(row)
            for row in self.connection.execute(
                "SELECT concept_id, considered_for_metric, reason_code, reason,"
                " framework_basis FROM declined_concept_mappings"
                " WHERE considered_for_metric = ? ORDER BY concept_id",
                (metric_id,),
            )
        ]

    def _has_decline_records(self) -> bool:
        return self.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table'"
            " AND name = 'declined_concept_mappings'"
        ).fetchone() is not None

    def all_declines(self) -> List[Dict[str, Any]]:
        if not self._has_decline_records():
            return []
        return [
            dict(row)
            for row in self.connection.execute(
                "SELECT concept_id, considered_for_metric, reason_code, reason,"
                " framework_basis FROM declined_concept_mappings"
                " ORDER BY considered_for_metric, concept_id"
            )
        ]

    def business_model_of(self, asset_id: str) -> Optional[Dict[str, Any]]:
        """
        The issuer's business model, with its basis and source.

        `None` for an issuer nobody has classified, and that is a meaningful
        answer rather than a missing one: an unclassified issuer gets no
        inapplicability ruling, so every declared metric stays applicable. A
        business model we do not know about is not evidence that a metric does
        not apply, and `Metric.applies_to` is written the same way.

        `None` also for an archive built before migration 0010, which has no such
        table. That is the same answer and for the same reason, and it is
        deliberate: the read path must not require a migration it cannot demand.
        An evaluation archive is a frozen record of what a build produced, and
        every 2.1 through 2.6 result was read out of one that predates this
        migration. Applying it would change the bytes and the contents of the
        ground truth those results were graded against, so the older archive has
        to keep answering -- with no classifications in it, and therefore no
        inapplicability rulings, which is exactly what it knew before.
        """
        if not self._has_business_models():
            return None
        row = self.connection.execute(
            "SELECT asset_id, business_model, basis, source, recorded_at"
            " FROM issuer_business_model WHERE asset_id = ?",
            (asset_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    def _has_business_models(self) -> bool:
        return self.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table'"
            " AND name = 'issuer_business_model'"
        ).fetchone() is not None

    def inapplicable_metrics(self, business_model: str) -> List[str]:
        """Every metric declared inapplicable to one business, in metric order."""
        return [
            row["metric_id"]
            for row in self.connection.execute(
                "SELECT metric_id FROM metric_inapplicable_in"
                " WHERE business_model = ? ORDER BY metric_id",
                (business_model,),
            )
        ]

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

    def record_adoption(
        self,
        asset_id: str,
        concept_id: str,
        first_used: Optional[str],
        last_used: Optional[str],
        fact_count: int = 0,
        filing_count: int = 0,
        observed_at: Optional[str] = None,
    ) -> None:
        """
        Record that one filer was observed using one concept.

        Evidence, not a claim about intent. `first_used` and `last_used` are the
        periods that filer's own filings reported; they say nothing about
        whether the filer intends to continue, and a filer that stopped in 2018
        is recorded as having stopped in 2018 rather than as having retired the
        concept. The basis column is `OBSERVED_ADOPTION` and only that, enforced
        by trigger.

        Idempotent and monotone: re-observing a period extends the window rather
        than replacing it, so a later ingestion covering more history widens what
        is known instead of silently narrowing it.
        """
        stamp = observed_at or utc_now()
        self.connection.execute(
            "INSERT INTO issuer_concept_adoption (asset_id, concept_id,"
            " first_used, last_used, fact_count, filing_count, basis,"
            " first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?,"
            " 'OBSERVED_ADOPTION', ?, ?)"
            " ON CONFLICT(asset_id, concept_id) DO UPDATE SET"
            "   first_used = CASE"
            "     WHEN issuer_concept_adoption.first_used IS NULL THEN excluded.first_used"
            "     WHEN excluded.first_used IS NULL THEN issuer_concept_adoption.first_used"
            "     WHEN excluded.first_used < issuer_concept_adoption.first_used"
            "       THEN excluded.first_used"
            "     ELSE issuer_concept_adoption.first_used END,"
            "   last_used = CASE"
            "     WHEN excluded.last_used IS NULL THEN issuer_concept_adoption.last_used"
            "     WHEN issuer_concept_adoption.last_used IS NULL THEN excluded.last_used"
            "     WHEN excluded.last_used > issuer_concept_adoption.last_used"
            "       THEN excluded.last_used"
            "     ELSE issuer_concept_adoption.last_used END,"
            "   fact_count = issuer_concept_adoption.fact_count + excluded.fact_count,"
            "   filing_count = issuer_concept_adoption.filing_count + excluded.filing_count,"
            "   last_seen_at = excluded.last_seen_at",
            (
                asset_id,
                concept_id,
                first_used,
                last_used,
                fact_count,
                filing_count,
                stamp,
                stamp,
            ),
        )
        self.connection.commit()

    def adoption_for(
        self,
        asset_id: str,
        concept_id: str,
    ) -> Optional[ConceptAdoption]:
        """
        What one filer was observed doing with one concept.

        None means *not observed*, which is not the same as *not used*: a filer
        whose evidence has not been ingested has no adoption record, and that is
        a gap in what we hold rather than a fact about the filer. Callers must
        treat None as unknown and must not read it as "never used".
        """
        row = self.connection.execute(
            "SELECT * FROM issuer_concept_adoption"
            " WHERE asset_id = ? AND concept_id = ?",
            (asset_id, concept_id),
        ).fetchone()
        if row is None:
            return None
        return ConceptAdoption(
            asset_id=row["asset_id"],
            concept_id=row["concept_id"],
            first_used=row["first_used"],
            last_used=row["last_used"],
            fact_count=row["fact_count"],
            filing_count=row["filing_count"],
            basis=row["basis"],
        )

    def adoptions_for_asset(
        self,
        asset_id: str,
    ) -> List[ConceptAdoption]:
        rows = self.connection.execute(
            "SELECT * FROM issuer_concept_adoption WHERE asset_id = ?"
            " ORDER BY concept_id",
            (asset_id,),
        ).fetchall()
        return [
            ConceptAdoption(
                asset_id=row["asset_id"],
                concept_id=row["concept_id"],
                first_used=row["first_used"],
                last_used=row["last_used"],
                fact_count=row["fact_count"],
                filing_count=row["filing_count"],
                basis=row["basis"],
            )
            for row in rows
        ]

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
        asset_id: Optional[str] = None,
    ) -> ResolvedEvidence:
        """
        Resolve a concept to the metric it means.

        An unmapped concept resolves to nothing. It is not attached to the
        metric whose name looks nearest, because that is precisely the inference
        this registry exists to make explicit and to refuse to make silently.

        `asset_id` separates the two questions that were previously one. The
        mapping window answers *what the concept means*; a filer's observed
        adoption answers *when this filer used it*. When both are available the
        adoption window widens the mapping rather than replacing it, so a filer
        that used a concept outside the seeded window is no longer reported as
        unmapped — which was a fact about the seed, not about the filer.
        """
        mappings = [
            mapping
            for mapping, _ in self.metrics_for_concept(concept_id, as_of=None)
        ]
        adoption = (
            self.adoption_for(asset_id, concept_id) if asset_id else None
        )

        # Adoption governs when it covers the period, and the mapping governs
        # everything else. It replaces the window rather than deferring to it,
        # because the window was seeded from one filer's filings and is that
        # filer's timeline: NVDA reported `Revenues` through 2026, long after
        # the 2018 close that AAPL's last period produced. A real filing from
        # the filer being asked about is better evidence than another filer's
        # inferred boundary. The mapping's *fidelity* is untouched — a PARTIAL
        # concept is still PARTIAL and still breaks the series — so adoption
        # widens when a concept applied and never how faithfully it applied.
        effective = [
            mapping
            for mapping in mappings
            if mapping.applies_on(as_of)
            or (adoption is not None and adoption.covers(as_of))
        ]
        candidates = [
            (mapping, self.metric(mapping.metric_id)) for mapping in effective
        ]
        if not candidates:
            return ResolvedEvidence(
                observation_id="",
                concept_id=concept_id if self.concept(concept_id) else None,
                metric=None,
                adoption=adoption,
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
            adoption=adoption,
            adopted_outside_mapping_window=bool(
                adoption is not None
                and not mapping.applies_on(as_of)
                and as_of
            ),
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
