"""
ST-EVA 003 - the evidence snapshot the evaluation runs against.

Two problems this solves, both of which would otherwise make the eval
meaningless.

    The evaluation needs a *fixed* archive. An LLM answering from a live
    database would be answering from whatever EDGAR had at the moment, so two
    runs of the same dataset would not be comparable and a failure could be a
    new filing rather than a reasoning error. The archive is built once and
    frozen; the expected answers are read out of *that* archive, so the ground
    truth cannot drift from what the target was shown.

    The evaluation needs the awkward evidence types too. SEC ingestion produces
    filed observations, which is exactly the case that is easy to get right. A
    target that handles a clean filing and then invents a number when the state
    is UNAVAILABLE has failed the thing worth testing, so the snapshot also
    carries a conflict, an undeclared vendor figure, a derived value, a
    validation record and the negative evidence states.

The snapshot is additive to the sealed archive: it appends rows through the
same paths ingestion uses, and changes no production semantics.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Sequence

from archive import FilingRef
from core_registry import CoreRegistry
from data_contract import (
    Observation,
    SourceType,
    Unit,
    ValidationStatus,
    utc_now,
)
from evidence_model import source_fact_id
from registry_seed import seed
from sec_ingest import DEFAULT_FORMS, DEFAULT_METRICS, Ingestor
from sec_provider import SECProvider
from sqlite_archive import SQLiteArchive

SNAPSHOT_FILENAME = "snapshot.sqlite"


class SnapshotError(Exception):
    """The evaluation archive is not the shape the evaluation depends on."""


# The filer the evaluation asks about. One company, deliberately: the question
# is whether a model can use the evidence correctly, and varying the company at
# the same time would make a failure ambiguous between the two.
EVAL_ASSET = "AAPL"

# The awkward cases, appended to the ingested evidence so that both live filing
# history and the difficult shapes are present in one archive.
CONFLICT_METRIC = "shares_outstanding"
UNAVAILABLE_METRIC = "free_cash_flow"
DERIVED_REF = "der:current_ps"
CONTEXT_ID = "ctx_eval_1"


def build_snapshot(
    path: str,
    issuers: Optional[List[str]] = None,
    live: bool = True,
    forms: Optional[Sequence[str]] = None,
    metrics: Optional[Sequence[str]] = None,
    include_fixture: bool = True,
) -> Dict[str, Any]:
    """
    Build (or reopen) the evaluation archive.

    `live=False` skips SEC ingestion and produces an archive holding only the
    fixture evidence, which is what the offline harness tests use: it exercises
    the audit machinery without spending a source's request budget or making the
    test suite depend on a network.

    `forms` and `metrics` narrow what ingestion asks for, and exist because an
    issuer that files on Form 20-F has nothing in a 10-K index: without them a
    foreign private issuer is not a thin archive but an *empty* one, which looks
    like a semantic failure and is a filing-form mismatch. Defaulting to the
    10-K set keeps every existing build identical.

    `include_fixture` controls the synthetic single-issuer evidence appended
    below. Those rows are evaluation scaffolding for one issuer's difficult
    shapes -- a cross-source conflict, a stale figure, a derived value -- and
    putting them in a cross-framework archive would put one issuer's synthetic
    disagreement in the middle of a generalisation test, where a reader could
    not tell which rows came from EDGAR.
    """
    issuers = issuers or [EVAL_ASSET]
    if os.path.exists(path):
        return {"path": path, "reused": True, "issuers": issuers, "live": live}
    forms = tuple(forms) if forms else None
    metrics = tuple(metrics) if metrics else None

    store = SQLiteArchive(path)
    registry = CoreRegistry(store.connection)
    seed(registry)

    ingested: Dict[str, Dict[str, Any]] = {}
    if live:
        for issuer in issuers:
            report = Ingestor(
                store, SECProvider(), registry
            ).ingest(issuer, metrics=metrics or DEFAULT_METRICS,
                     forms=forms or DEFAULT_FORMS)
            ingested[issuer] = report.contract_dict()

    if include_fixture:
        _append_fixture_evidence(store, registry)
    store.close()
    return {
        "path": path,
        "reused": False,
        "issuers": issuers,
        "live": live,
        "forms": list(forms or DEFAULT_FORMS),
        "metrics": list(metrics or DEFAULT_METRICS),
        "include_fixture": include_fixture,
        "ingested": ingested,
    }


def _append_fixture_evidence(
    store: SQLiteArchive,
    registry: CoreRegistry,
) -> None:
    """
    The evidence types ingestion cannot produce.

    Each of these is a case where the *correct* answer is a refusal, a
    qualification, or a report of disagreement. A target that answers them
    confidently and wrongly is exactly the failure this evaluation exists to
    find, so the archive has to contain them.
    """
    asset_id = store.record_asset(
        EVAL_ASSET, cik="0000320193", name="Apple Inc."
    )
    period = ("2023-09-30", "2023-11-03")
    filing_accession = "0000320193-24-000001"
    now = utc_now()

    # Documents first. The archive refuses an observation that references a
    # document it has not captured, because a dangling reference looks like
    # evidence and is not.
    for document_id, content_hash, uri, provider, kind in (
        (
            "doc_eval_filing",
            "sha256:eval-filing-shares",
            "https://data.sec.gov/api/xbrl/companyconcept/CIK0000320193/"
            "dei/EntityCommonStockSharesOutstanding.json",
            "SecEdgar",
            "SEC_COMPANY_CONCEPT",
        ),
        (
            "doc_eval_vendor",
            "sha256:eval-vendor",
            "https://query.example.invalid/shares",
            "YahooFinance",
            "VENDOR_QUOTE",
        ),
    ):
        store.connection.execute(
            "INSERT OR IGNORE INTO source_documents (document_id,"
            " content_hash, uri, canonical_uri, http_status, media_type,"
            " byte_size, fetched_at, first_seen_at, provider, document_type,"
            " content, content_encoding) VALUES (?, ?, ?, ?, 200,"
            " 'application/json', ?, ?, ?, ?, ?, ?, 'gzip')",
            (
                document_id,
                content_hash,
                uri,
                uri,
                128,
                "2024-05-02T22:06:00.000Z",
                "2024-05-02T22:06:00.000Z",
                provider,
                kind,
                json.dumps({"evaluation": "fixture"}).encode("utf-8"),
            ),
        )

    # -- a second source that disagrees about the share count ------------
    # The SEC figure is stored as an ordinary observation with a filing
    # concept; the vendor figure has no filing concept at all, which is the
    # distinction `source_concept_ref` was added for. Neither is a winner.
    sec_observation_id = _store(
        store,
        asset_id,
        contract_id="eval-shares-sec",
        metric=CONFLICT_METRIC,
        value=15_504_000_000.0,
        unit=Unit.COUNT.value,
        currency=None,
        period_start=None,
        period_end=period[1],
        concept="EntityCommonStockSharesOutstanding",
        taxonomy="dei",
        accession=filing_accession,
        form="10-K",
        provider="SecEdgar",
        source_type=SourceType.REGULATORY_FILING.value,
        statement="MARKET",
        document_hashes=["sha256:eval-filing-shares"],
    )
    vendor_observation_id = _store(
        store,
        asset_id,
        contract_id="eval-shares-vendor",
        metric=CONFLICT_METRIC,
        value=14_640_000_000.0,
        unit=Unit.COUNT.value,
        currency=None,
        period_start=None,
        period_end=period[1],
        # No filing concept: a null here means "this observation has no filing
        # concept", which is the truth for a vendor aggregate.
        concept=None,
        taxonomy=None,
        accession=None,
        form=None,
        provider="YahooFinance",
        source_type=SourceType.API_LIVE.value,
        statement="MARKET",
        available_at=None,
        available_at_basis="UNDECLARED",
        availability_class="UNDECLARED",
        document_hashes=["sha256:eval-vendor"],
    )

    # -- a vendor revenue figure with no stated publication time ---------
    # Knowable at no instant, because its recency cannot be established. It is
    # archive-dated rather than source-dated: eligible from when the archive
    # first held it, which is neither its period end nor a retrieval time. The
    # archive refuses any other pairing, which is the 2.4.3 rule and not an
    # obstacle to it.
    _store(
        store,
        asset_id,
        contract_id="eval-revenue-vendor",
        metric="revenue",
        value=95_000_000_000.0,
        unit=Unit.CURRENCY.value,
        currency="USD",
        period_start="2023-07-01",
        period_end="2024-06-30",
        concept="trailingTotalRevenue",
        taxonomy="vendor",
        accession=None,
        form=None,
        provider="YahooFinance",
        source_type=SourceType.API_LIVE.value,
        statement="INCOME",
        available_at=None,
        available_at_basis="UNDECLARED",
        availability_class="ARCHIVE_FIRST_SEEN",
        document_hashes=["sha256:eval-vendor"],
    )

    # -- a validation record recording the disagreement ------------------
    _store_validation(store, now, sec_observation_id, vendor_observation_id)

    # -- a context with a derived value ----------------------------------
    _store_derived(store, asset_id, now, sec_observation_id)

    # -- the negative evidence states ------------------------------------
    # Recorded explicitly, because a state that exists only as the absence of a
    # row is indistinguishable from a lookup that failed.
    _store_states(store, asset_id, now)
    store.connection.commit()
    assert_no_shadow_assets(store)


def assert_no_shadow_assets(store: SQLiteArchive) -> None:
    """
    Refuse a snapshot in which evidence is unreachable by ticker.

    An asset whose ticker looks like an asset id is the signature of passing an
    id to a method that registers what it is given. Every row is present, every
    count looks right, and a query by ticker returns nothing — which reads as
    "the evaluation asset has no data" rather than as a bug, and would quietly
    turn every test into a pass-by-absence.

    Both bugs of this shape appeared in this codebase while it was being built,
    so the check is structural rather than a convention.
    """
    shadows = store.connection.execute(
        "SELECT ticker FROM assets WHERE UPPER(ticker) LIKE 'ASSET/_%' ESCAPE '/'"
    ).fetchall()
    if shadows:
        raise SnapshotError(
            "an asset is registered under its own asset_id, which means "
            "evidence is filed where a ticker query cannot find it: "
            + ", ".join(str(row["ticker"]) for row in shadows)
        )


def _store(
    store: SQLiteArchive,
    asset_id: str,
    *,
    contract_id: str,
    metric: str,
    value: float,
    unit: str,
    currency: Optional[str],
    period_start: Optional[str],
    period_end: str,
    concept: Optional[str],
    taxonomy: Optional[str],
    accession: Optional[str],
    form: Optional[str],
    provider: str,
    source_type: str,
    statement: Optional[str],
    available_at: Optional[str] = "2024-11-01T16:30:00.000Z",
    available_at_basis: str = "ACCEPTANCE_DATETIME",
    availability_class: str = "SOURCE_DECLARED",
    first_archived_at: Optional[str] = None,
    document_hashes: Optional[List[str]] = None,
) -> str:
    """
    Append one observation through the archive, the way ingestion does.

    A filing concept and a vendor aggregate differ in more than a label, and the
    difference is written here: a vendor figure gets no `source_concept_ref` at
    all, which the database reads as "no filing concept" rather than "concept
    unknown".

    `replay_eligible_from` is deliberately not passed. The archive derives it
    from the availability class and the source's own timing, and that
    derivation is the sealed 2.4.3 behaviour. A fixture that set it by hand
    would be testing a value the production path never produces.
    """
    raw = {"sec_fact": {"accession": accession}} if accession else {}
    observation = Observation(
        observation_id=contract_id,
        metric=metric,
        value=value,
        unit=unit,
        currency=currency,
        currency_basis="REPORTED" if currency else "NOT_APPLICABLE",
        period_start=period_start,
        period_end=period_end,
        as_of=period_end,
        available_at=available_at,
        available_at_basis=available_at_basis,
        provider=provider,
        source_type=source_type,
        source_url=None,
        definition=metric,
        methodology=(
            "evaluation fixture; a value ST-EVA did not retrieve from a source"
        ),
        retrieved_at=utc_now(),
        raw=raw,
        status=ValidationStatus.UNVERIFIABLE,
        status_reasons=(
            "a single official source cannot cross-validate itself",
        ),
        basis={
            "reporting_framework": taxonomy or "UNDECLARED",
            "statement": statement or "UNDECLARED",
            "source_declared": availability_class == "SOURCE_DECLARED",
        },
    )
    filing = None
    if accession:
        filing = FilingRef(
            accession=accession,
            form=form,
            taxonomy=taxonomy,
            fiscal_year=2024,
            fiscal_period="FY",
            statement=statement,
            instant=1 if period_start is None else 0,
            source_fact_id=source_fact_id(
                "SecEdgar", accession, taxonomy, concept, period_start,
                period_end, accession,
            ),
            # `concept` is the bare local name and `taxonomy` the namespace, so
            # the qualified form is assembled here. Concatenating a name that
            # already carried its prefix would produce `dei:dei:...`, which
            # still parses and means nothing.
            source_concept=f"{taxonomy}:{concept}" if concept else None,
        )
    return store.record_observation(
        # The ticker, never the asset_id. `record_observation` registers
        # whatever it is handed, so passing an id here silently creates a second
        # asset named after the id and files the evidence under it, where a
        # query by ticker finds nothing while the rows all look present. The
        # ingestion path hit exactly this bug; `assert_no_shadow_assets` below
        # is what stops it coming back quietly.
        asset=EVAL_ASSET,
        observation=observation,
        availability_class=availability_class,
        first_archived_at=first_archived_at,
        document_hashes=document_hashes or (),
        filing=filing,
    )


def _store_validation(
    store: SQLiteArchive,
    now: str,
    filing_observation_id: str,
    vendor_observation_id: str,
) -> None:
    """
    Record the disagreement, and record that neither side won.

    A conflict that resolves to one number is the 2.4.2 defect returning in a
    new place, so the record carries both sides and the independence metadata
    that says how much the agreement is worth.

    The record references the archive-assigned `observation_id`, not the
    contract id: that is the column the foreign key is declared against, and
    guessing the other one is how a validation record ends up attached to
    nothing while still appearing in a trace.
    """
    store.connection.execute(
        "INSERT OR REPLACE INTO validation_records (record_id,"
        " observation_id, kind, status, reasons_json, comparison_basis_json,"
        " tolerance_json, explanation, references_json, value_snapshot_json,"
        " checked_at) VALUES ('val_eval_conflict', ?,"
        " 'cross_source', 'DISCREPANT', ?, ?, '{}', ?, ?, ?, ?)",
        (
            filing_observation_id,
            json.dumps(["counts differ by 5.9%"]),
            json.dumps(
                {
                    "vendor_observation": f"obs:{vendor_observation_id}",
                    "filing_observation": f"obs:{filing_observation_id}",
                    "provider": "YahooFinance",
                    "vendor_unit": "count",
                    "filing_unit": "count",
                    "vendor_currency": None,
                    "filing_currency": None,
                    "independence": "NOT_INDEPENDENT",
                    "period_offset_days": 0,
                }
            ),
            "the two sources report different share counts; neither is "
            "selected",
            json.dumps([filing_observation_id, vendor_observation_id]),
            json.dumps([15_504_000_000.0, 14_640_000_000.0]),
            now,
        ),
    )


def _store_derived(
    store: SQLiteArchive,
    asset_id: str,
    now: str,
    operand_observation_id: str,
) -> None:
    """
    A derived figure, with its operands named.

    The point of the test is that this is not a filed number. It is computed,
    and the archive has to say from what, or a reader cannot tell a calculated
    figure from a reported one.
    """
    store.connection.execute(
        "INSERT OR REPLACE INTO context_snapshots (context_id, asset_id,"
        " as_of, knowledge_cutoff, replay_fidelity, built_from_json,"
        " document_json, document_hash, supersedes, archived_at)"
        " VALUES (?, ?, '2024-11-02', '2024-11-02T00:00:00+00:00',"
        " 'OBSERVATIONAL', '{}', '{}', 'sha256:ctx_eval', NULL, ?)",
        (CONTEXT_ID, asset_id, now),
    )
    store.connection.execute(
        "INSERT OR REPLACE INTO derived_values (context_id, ref,"
        " operation_json, expression, value_json, unit, deterministic,"
        " depends_on_json) VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
        (
            CONTEXT_ID,
            DERIVED_REF,
            json.dumps(
                {
                    "op": "divide",
                    "version": "1",
                    "operands": [f"obs:{operand_observation_id}"],
                }
            ),
            "price / earnings per share",
            json.dumps(31.42),
            "multiple",
            json.dumps([f"obs:{operand_observation_id}"]),
        ),
    )


def _store_states(
    store: SQLiteArchive,
    asset_id: str,
    now: str,
) -> None:
    """
    The four negative states, written down.

    Each says something different and each is a thing a model is likely to
    flatten into "no data" or, worse, into a zero. They are recorded with their
    reason codes so a target can be held to the specific one it should have
    preserved.
    """
    for metric, state, reason, detail in (
        # The source does not carry this item. Not an error, not zero.
        ("dividend_per_share", "SOURCE_DID_NOT_REPORT", "SOURCE_OMITS_CONCEPT",
         None),
        # The business has no such measure. Not a retrieval that failed.
        ("operating_margin_bank", "NOT_APPLICABLE",
         "BUSINESS_MODEL_NOT_MEANINGFUL", None),
        # Our retrieval failed. Distinct from the source omitting it.
        ("segment_revenue", "UNAVAILABLE", "RETRIEVAL_FAILED", None),
        # What we hold has gone stale. Not historically false.
        ("guidance", "STALE", "NO_RECENT_VALUE", None),
        # Reported, with a locator, so the positive case is in the archive too.
        ("revenue", "SOURCE_REPORTED", "SOURCE_STATED_VALUE",
         "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"),
    ):
        store.connection.execute(
            "INSERT OR REPLACE INTO evidence_state (asset_id, metric, state,"
            " reason_code, detail, as_of, updated_at) VALUES (?, ?, ?, ?, ?,"
            " NULL, ?)",
            (asset_id, metric, state, reason, detail, now),
        )


def open_snapshot(path: str) -> SQLiteArchive:
    return SQLiteArchive(path)


def snapshot_root() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def default_snapshot_path() -> str:
    return os.path.join(snapshot_root(), "snapshot.sqlite")
