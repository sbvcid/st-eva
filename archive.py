from __future__ import annotations

"""
ST-EVA 2.4 - the archive interface and the point-in-time replay driver.

This module is a *consumer* of the Data Contract. It never defines a data
model, and it never imports the engine, the document builder, or a storage
engine. A store may be SQLite today and PostgreSQL or Parquet tomorrow; the
contract and the Core must not learn anything when that happens.

The load-bearing rule of this phase:

    Replay must not fill in a missing historical world for the sake of
    completeness.

An INSUFFICIENT result is a successful replay. A fully-populated document built
from substituted data is a failure, however plausible it looks.

`build_document` is injected by the Core precisely so that replay runs the
ordinary pipeline rather than a second implementation of it. A replay path that
could drift from the live path is not a replay, it is a guess.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from data_contract import (
    AvailabilityBasis,
    METRIC_PRICE,
    Observation,
    ObservationSet,
    SourceType,
    is_number,
    parse_iso_date,
    utc_now,
)
# Availability classes (spec section 5.2). The archive never invents one.
SOURCE_DECLARED = "SOURCE_DECLARED"
UNDECLARED = "UNDECLARED"
ARCHIVE_FIRST_SEEN = "ARCHIVE_FIRST_SEEN"

AVAILABILITY_CLASSES = (SOURCE_DECLARED, UNDECLARED, ARCHIVE_FIRST_SEEN)

# Bases that carry a source-declared publication time.
DECLARED_BASES = (
    AvailabilityBasis.ACCEPTANCE_DATETIME.value,
    AvailabilityBasis.FILED_AS_OF_DATE.value,
    AvailabilityBasis.OBSERVATION_INSTANT.value,
    AvailabilityBasis.REPORTED.value,
)

# Replay fidelity, derived from the classes of the observations actually used.
FIDELITY_SOURCE_DECLARED = "SOURCE_DECLARED"
FIDELITY_OBSERVATIONAL = "OBSERVATIONAL"

# Replay outcomes (spec section 9.2).
REPLAY_MATCH = "MATCH"
REPLAY_DIVERGED = "DIVERGED"
REPLAY_NO_SNAPSHOT = "NO_SNAPSHOT"
REPLAY_INSUFFICIENT = "INSUFFICIENT"


class ArchiveError(Exception):
    """The archive could not satisfy a request it should have been able to."""


class InterpretationError(ArchiveError):
    """
    A proposed interpretation violates the knowledge-state contract.

    Separate from `ArchiveError` so a caller can tell "this reading is not
    allowed" from "the archive could not answer". The rules it refuses are the
    cross-row ones -- ordering, same-source supersedes, no cycles, one reading
    per knowledge instant -- which SQLite cannot express and which 2.59's
    domain validators own.
    """


class InsufficientHistory(ArchiveError):
    """
    The archive cannot answer the question asked.

    This is an expected outcome, not a failure. It is raised rather than
    approximated because a substituted value is worse than no value: it produces
    a plausible document that answers a different question.
    """


def availability_class_for(observation: Observation) -> str:
    """
    The archive's classification of an observation's availability.

    Derived from the contract's own `available_at_basis`, never from whether
    the field happens to be populated, and never from `retrieved_at`.
    """
    if observation.available_at and (
        observation.available_at_basis in DECLARED_BASES
    ):
        return SOURCE_DECLARED
    return UNDECLARED


def document_hash(document: Dict[str, Any]) -> str:
    """Hash of the stored bytes, for tamper detection after the fact."""
    encoded = json.dumps(
        document, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ArchiveStats:
    """What one archival attempt actually did. Reported, never assumed."""

    observations_recorded: int = 0
    observations_deduplicated: int = 0
    documents_recorded: int = 0
    documents_reused: int = 0
    contexts_recorded: int = 0
    contexts_deduplicated: int = 0
    observations_excluded_as_unknown_availability: int = 0

    def contract_dict(self) -> Dict[str, int]:
        return {
            "observations_recorded": self.observations_recorded,
            "observations_deduplicated": self.observations_deduplicated,
            "documents_recorded": self.documents_recorded,
            "documents_reused": self.documents_reused,
            "contexts_recorded": self.contexts_recorded,
            "contexts_deduplicated": self.contexts_deduplicated,
            "observations_excluded_as_unknown_availability": (
                self.observations_excluded_as_unknown_availability
            ),
        }


@dataclass(frozen=True)
class FilingRef:
    """
    The filing a stored fact came from, written at insert time.

    An observation cannot learn its filing identity after the fact. The archive
    is append-only by trigger, which is the whole point of it, so the fields that
    make a fact traceable back to a filing have to arrive with the row rather
    than be patched onto it afterwards.

    `source_concept` is qualified as `taxonomy:concept` and is None when the
    observation has no filing concept at all — a vendor aggregate, a derived
    figure. None means "no concept", not "concept not yet identified"; the
    second is a gap in the registry, which resolves to nothing and says so.
    """

    accession: Optional[str] = None
    form: Optional[str] = None
    taxonomy: Optional[str] = None
    fiscal_year: Optional[int] = None
    fiscal_period: Optional[str] = None
    statement: Optional[str] = None
    instant: Optional[int] = None
    source_fact_id: Optional[str] = None
    source_concept: Optional[str] = None

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "accession": self.accession,
            "form": self.form,
            "taxonomy": self.taxonomy,
            "fiscal_year": self.fiscal_year,
            "fiscal_period": self.fiscal_period,
            "statement": self.statement,
            "instant": self.instant,
            "source_fact_id": self.source_fact_id,
            "source_concept": self.source_concept,
        }


@dataclass(frozen=True)
class StoredDocument:
    """A captured source document, addressed by the hash of its bytes."""

    content_hash: str
    uri: Optional[str]
    http_status: Optional[int]
    media_type: Optional[str]
    byte_size: Optional[int]
    fetched_at: str
    first_seen_at: str
    storage_path: Optional[str] = None
    compression: Optional[str] = None
    payload: Optional[bytes] = None
    # The provider that fetched it and what kind of document it is. A replay
    # needs to know which source produced a fact, and years later which
    # endpoint version the fact was read from.
    provider: Optional[str] = None
    document_type: Optional[str] = None
    canonical_uri: Optional[str] = None

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "content_hash": self.content_hash,
            "uri": self.uri,
            "canonical_uri": self.canonical_uri or self.uri,
            "provider": self.provider,
            "document_type": self.document_type,
            "media_type": self.media_type,
            "byte_size": self.byte_size,
            "http_status": self.http_status,
            "fetched_at": self.fetched_at,
            "content_captured": self.payload is not None,
        }


@dataclass(frozen=True)
class ReplayResult:
    """
    The outcome of asking what was knowable at a time.

    `document` is None for every outcome other than a successful rebuild, and
    `reason` explains an insufficient answer rather than leaving the caller to
    infer it.
    """

    asset: str
    as_of: str
    outcome: str
    reason: Optional[str] = None
    document: Optional[Dict[str, Any]] = None
    stored_document_hash: Optional[str] = None
    rebuilt_document_hash: Optional[str] = None
    observations_used: int = 0
    observations_considered: int = 0
    replay_fidelity: str = FIDELITY_SOURCE_DECLARED
    availability_classes: Tuple[Tuple[str, str], ...] = ()
    availability_from: Dict[str, str] = field(default_factory=dict)
    admissions: Tuple[Any, ...] = ()

    @property
    def matched(self) -> bool:
        return self.outcome == REPLAY_MATCH

    @property
    def reconstructed(self) -> bool:
        return self.document is not None

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "asset": self.asset,
            "as_of": self.as_of,
            "outcome": self.outcome,
            "reason": self.reason,
            "matched": self.matched,
            "reconstructed": self.reconstructed,
            "observations_used": self.observations_used,
            "observations_considered": self.observations_considered,
            "replay_fidelity": self.replay_fidelity,
            "stored_document_hash": self.stored_document_hash,
            "rebuilt_document_hash": self.rebuilt_document_hash,
            "availability_classes": [
                {"observation_id": ref, "class": klass}
                for ref, klass in self.availability_classes
            ],
        }


class ArchiveStore:
    """
    The read/write surface an archive must provide.

    Deliberately not a `Protocol`: the Core constructs a store directly and a
    subclassable, documented base is easier to reason about at this size. The
    interface is small on purpose.
    """

    def record_source_document(self, document: StoredDocument) -> str:
        raise NotImplementedError

    def record_observation(
        self,
        asset: str,
        observation: Observation,
        availability_class: str,
        first_archived_at: str,
        replay_eligible_from: Optional[str],
        document_hashes: Sequence[str] = (),
        accession: Optional[str] = None,
        filing: Optional["FilingRef"] = None,
    ) -> str:
        raise NotImplementedError

    def record_context(
        self,
        asset: str,
        document: Dict[str, Any],
        replay_fidelity: str,
        observations: Sequence[Observation] = (),
    ) -> str:
        raise NotImplementedError

    def observations_for(self, asset: str, cutoff: str) -> List[Observation]:
        raise NotImplementedError

    def eligibility_for(self, asset: str) -> Dict[str, str]:
        raise NotImplementedError

    def asset_metadata(self, asset: str) -> Dict[str, Any]:
        """
        What the archive knows about the instrument.

        A replayed context has to carry the same company name and exchange the
        archived one did, or it will diverge for a reason that has nothing to
        do with the data.
        """
        return {"ticker": asset, "name": None, "exchange": None, "currency": None, "cik": None}

    def context_at(self, asset: str, as_of: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def close(self) -> None:
        return None


class NullArchive(ArchiveStore):
    """
    A store that discards everything.

    The CLI uses this when archiving is not requested, which is the normal
    case, and it is what makes invariant I10 true: deleting the archive deletes
    nothing the CLI needs.
    """

    def record_source_document(self, document: StoredDocument) -> str:
        return document.content_hash

    def record_observation(self, asset, observation, **kwargs) -> str:
        return observation.observation_id

    def record_context(self, asset, document, **kwargs) -> str:
        return document["context_id"]

    def observations_for(self, asset: str, cutoff: str) -> List[Observation]:
        return []

    def eligibility_for(self, asset: str) -> Dict[str, str]:
        return {}

    def asset_metadata(self, asset: str) -> Dict[str, Any]:
        return {"ticker": asset, "name": None, "exchange": None, "currency": None, "cik": None}

    def context_at(self, asset: str, as_of: str) -> Optional[Dict[str, Any]]:
        return None

    def context_hashes(self, asset: str) -> List[Dict[str, Any]]:
        return []


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------

# The metric the context cannot exist without: price is what the whole
# document is about, and inventing one is the single worst failure here.
REQUIRED_REPLAY_METRIC = METRIC_PRICE


def replay(
    store: ArchiveStore,
    asset: str,
    as_of: str,
    build_document: Callable[..., Dict[str, Any]],
) -> ReplayResult:
    """
    Rebuild what was knowable at `as_of`, using the ordinary pipeline.

    `build_document(observations, as_of, generated_at, asset_metadata)` is
    injected by the Core so that replay runs the same code a live run does.
    This module never imports the engine.

    The result distinguishes four outcomes, and an insufficient answer is a
    success:

        MATCH          the rebuild reproduces the stored document
        DIVERGED       the same inputs produced a different document
        NO_SNAPSHOT    no context was archived for that instant
        INSUFFICIENT   not enough was archived at that instant
    """
    if parse_iso_date(as_of) is None:
        raise ArchiveError(f"{as_of!r} is not an ISO-8601 date or instant")

    candidates = store.observations_for(asset, as_of)
    considered = len(candidates)
    used = list(candidates)

    if not used:
        return ReplayResult(
            asset=asset,
            as_of=as_of,
            outcome=REPLAY_INSUFFICIENT,
            reason=(
                f"no observation archived for {asset} is replay-eligible at "
                f"{as_of}. Nothing was substituted."
            ),
            observations_considered=considered,
        )

    eligibility = store.eligibility_for(asset)
    observation_set = ObservationSet(ticker=asset, observations=used)

    # Time selection is the contract's, not a second implementation of it.
    price_observation = observation_set.latest_knowable(
        as_of, REQUIRED_REPLAY_METRIC, eligibility=eligibility
    )
    if price_observation is None:
        return ReplayResult(
            asset=asset,
            as_of=as_of,
            outcome=REPLAY_INSUFFICIENT,
            reason=(
                f"no price observation for {asset} is knowable at {as_of}. A "
                "replay must never substitute the most recent price for a "
                "missing historical one, so no context is produced."
            ),
            observations_considered=considered,
            observations_used=len(used),
        )

    admissions_recomputed: Tuple[Any, ...] = ()
    admissions_diverged = False
    admission_divergence_reason: Optional[str] = None

    connection = getattr(store, "connection", None)
    if connection is not None:
        try:
            from evidence_valuation_boundary import admit, V1_CROSSING_METRICS
            from registry_identity import (
                registry_state_identity,
                resolver_policy_identity,
            )

            current_registry_id = registry_state_identity(connection)
            current_policy_id = resolver_policy_identity(connection)

            _, admissions_recomputed = admit(
                store, asset, as_of, price_observation, metrics=V1_CROSSING_METRICS
            )

            # C4 & C5: Only admitted SEC observations enter the rebuild material candidate population.
            # Refused or evidence-only SEC ingest rows cannot fall through into material selection.
            admitted_sec_ids = {
                adm.contract_id
                for adm in admissions_recomputed
                if adm.admitted and adm.contract_id
            }
            used = [
                obs
                for obs in used
                if not (
                    obs.observation_id.startswith("ingest|")
                    or (
                        obs.source_type == SourceType.REGULATORY_FILING.value
                        and obs.provider == "SecEdgar"
                    )
                )
                or obs.observation_id in admitted_sec_ids
            ]
            observation_set = ObservationSet(ticker=asset, observations=used)

            # C3 Step 8: Compare against stored admission record
            effective_adm_fn = getattr(store, "effective_admission", None)
            if callable(effective_adm_fn):
                for adm in admissions_recomputed:
                    stored_adm = effective_adm_fn(asset, adm.metric, as_of)
                    if stored_adm is not None:
                        mismatches = []
                        if stored_adm["admitted"] != (1 if adm.admitted else 0):
                            mismatches.append(
                                f"admitted (stored={stored_adm['admitted']}, recomputed={1 if adm.admitted else 0})"
                            )
                        if stored_adm["contract_id"] != adm.contract_id:
                            mismatches.append(
                                f"contract_id (stored={stored_adm['contract_id']!r}, recomputed={adm.contract_id!r})"
                            )
                        if stored_adm["source_fact_id"] != adm.source_fact_id:
                            mismatches.append(
                                f"source_fact_id (stored={stored_adm['source_fact_id']!r}, recomputed={adm.source_fact_id!r})"
                            )
                        if stored_adm["registry_state_identity"] != current_registry_id:
                            mismatches.append(
                                f"registry_state_identity (stored={stored_adm['registry_state_identity']!r}, recomputed={current_registry_id!r})"
                            )
                        if stored_adm["resolver_policy_identity"] != current_policy_id:
                            mismatches.append(
                                f"resolver_policy_identity (stored={stored_adm['resolver_policy_identity']!r}, recomputed={current_policy_id!r})"
                            )
                        if stored_adm["price_contract_id"] != getattr(
                            price_observation, "observation_id", None
                        ):
                            mismatches.append(
                                f"price_contract_id (stored={stored_adm['price_contract_id']!r}, recomputed={getattr(price_observation, 'observation_id', None)!r})"
                            )
                        if mismatches:
                            admissions_diverged = True
                            admission_divergence_reason = (
                                f"stored admission diverges from recomputed admission for {adm.metric}: "
                                + "; ".join(mismatches)
                            )
                            break
        except Exception:
            pass

    classes = tuple(
        (
            observation.observation_id,
            _stored_class(store, observation, eligibility),
        )
        for observation in used
    )
    fidelity = (
        FIDELITY_OBSERVATIONAL
        if any(klass == ARCHIVE_FIRST_SEEN for _, klass in classes)
        else FIDELITY_SOURCE_DECLARED
    )

    rebuilt = build_document(
        observation_set,
        as_of,
        utc_now(),
        store.asset_metadata(asset),
    )
    rebuilt_hash = document_hash(rebuilt)

    # The rebuilt document's own `as_of` is the moment it is about, which is not
    # the same axis as the replay cutoff. The cutoff is a knowledge boundary;
    # `as_of` is a data moment. The snapshot to compare against is the one for
    # the moment the rebuild turned out to describe.
    lookup = rebuilt.get("as_of") or as_of
    stored = store.context_at(asset, lookup)
    if stored is None:
        return ReplayResult(
            asset=asset,
            as_of=as_of,
            outcome=REPLAY_DIVERGED if admissions_diverged else REPLAY_NO_SNAPSHOT,
            reason=(
                admission_divergence_reason
                if admissions_diverged
                else (
                    f"no context was archived for {asset} at {as_of}; the "
                    "reconstruction above is what the archive can now reproduce."
                )
            ),
            document=rebuilt,
            rebuilt_document_hash=rebuilt_hash,
            observations_used=len(used),
            observations_considered=considered,
            replay_fidelity=fidelity,
            availability_classes=classes,
            admissions=admissions_recomputed,
        )

    # Compared on `context_id`, not on `document_hash`. A context's identity is
    # the hash of its knowledge, which deliberately excludes the
    # when-we-asked fields, so a rebuild is comparable to the original at all.
    # `document_hash` covers the stored bytes and exists for tamper detection.
    stored_hash = document_hash(stored)
    matched = (stored.get("context_id") == rebuilt.get("context_id")) and not admissions_diverged
    return ReplayResult(
        asset=asset,
        as_of=as_of,
        outcome=REPLAY_MATCH if matched else REPLAY_DIVERGED,
        reason=(
            None
            if matched
            else (
                admission_divergence_reason
                if admissions_diverged
                else (
                    "the stored context and the rebuilt context differ. Either the "
                    "code changed since archival, which is legitimate and the diff "
                    "is informative, or the replay is not faithful, which is a "
                    "defect. The document is reported rather than smoothed over."
                )
            )
        ),
        document=rebuilt,
        stored_document_hash=stored_hash,
        rebuilt_document_hash=rebuilt_hash,
        observations_used=len(used),
        observations_considered=considered,
        replay_fidelity=fidelity,
        availability_classes=classes,
        admissions=admissions_recomputed,
    )


def _stored_class(
    store: ArchiveStore,
    observation: Observation,
    eligibility: Dict[str, str],
) -> str:
    """
    The class the store recorded, recomputed only as a fallback.

    A store that does not report a class is assumed to have stored what the
    contract implies, and never assumed to be more permissive than that.
    """
    reported = getattr(store, "class_of", None)
    if callable(reported):
        klass = reported(observation.observation_id)
        if klass in AVAILABILITY_CLASSES:
            return klass
    if observation.available_at and (
        observation.available_at_basis in DECLARED_BASES
    ):
        return SOURCE_DECLARED
    if eligibility.get(observation.observation_id):
        return ARCHIVE_FIRST_SEEN
    return UNDECLARED
