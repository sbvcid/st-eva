"""
Full Core scope, bulk, reconciled against the archive the API path built.

2.13 settled the merge and the irreversibility, and in doing so produced a rule
that this script exists to apply rather than to re-argue:

    bulk must bootstrap a fresh archive at the full Core scope, and a change to
    the Core metric set is a re-bootstrap rather than an incremental run

So far the full Core scope has only ever been run over **six** issuers, through
the API path, in `build_crossframework_snapshot.py`. The one population-scale
archive that exists, `snapshot-universe.sqlite`, holds 54,602 observations over
75 issuers and **eight** of the twenty seeded Core metrics. The 8-metric path
has been shown to scale; the 20-metric path has been shown to work on six
filers; the two have never met.

This is the controlled experiment that makes them meet, and it is offline by
construction. The six `companyfacts` documents 2.10 fetched are already on disk,
they carry their own CIK, and the reference archive carries the ticker-to-CIK
map the bulk source needs -- so a full-scope bulk bootstrap, a per-observation
reconciliation and a gate run need no network, no rate limit, no zip, and no
mega-cap. Whatever this finds is about the chain, not about delivery.

    full Core scope, 6 issuers, bulk, fresh archive
        -> reconcile every observation against the API-built reference
        -> run the existing eight gates and coverage ledger over the result

## Why the scope is asserted rather than passed in

There are three metric-set definitions in this repository and they do not
agree:

    sec_ingest.DEFAULT_METRICS                 8    the vertical slice
    build_crossframework_snapshot.ALL_METRICS  20   the Core set
    merge_sources.FULL_CORE_METRICS            20   the Core set, other order

A run that silently used the first would look exactly like a 20-metric run that
collected nothing, which is the failure 2.13 already had once. So the script
imports all three, checks that the two twenty-metric sets are the same set,
checks that the registry seed declares exactly that set, and refuses to run
otherwise.

## Why the reference is a fair comparison

The reference archive and the payload were built from the same EDGAR window.
Measured before the run rather than assumed: the newest `filed` date per issuer
is identical in both (AAPL 2026-07-31, MSFT 2026-07-29, MU 2026-06-25,
NVDA 2026-08-26, TSM 2026-04-16, NU 2025-04-16), so the reconciliation is not
confounded by recency and a one-sided observation means a difference in what
was asked for, not a difference in when.

## What is compared, and what is only classified

The join key is **`source_fact_id`**, and it is the strongest one available. 2.5
built fact identity deliberately on the fact's *position in the filing* rather
than on its value, its document or its retrieval time, precisely so that a
different delivery path reporting the same fact does not re-append it. A
reconciliation keyed on it is therefore a direct test of the identity model,
not a convenient join.

`observation_id` is **not** usable as a cross-archive key, and this run found
that out rather than assuming it. Both archives store an archive-assigned
`obsarch_<hash>`, because `record_observation` re-keys whatever contract id it
is handed. The route-independent string is `contract_id`
(`ingest|<metric>|<concept>|<accession>|<period>|<unit>`), so that is compared
too, and the difference in `observation_id` is reported as what it is -- an
archive-local key -- rather than being used to hide a real divergence.

Compared as **semantic**: value, unit, currency, period, as-of, availability and
its basis, taxonomy, concept, accession, form, fiscal period, contract id,
source concept ref, basis block, definition, methodology, status, instant.

Compared as **provenance only**: document id, content hash, retrieval time,
first-archived time, and the source URI. 2.12 established that the two paths
read the same fact from different bytes -- a `companyconcept` document on one
side, a `companyfacts` document on the other -- and that a diff reporting that
as a disagreement would train a reader to ignore diffs. So provenance is
separated rather than counted as divergence, and the semantic fields are
compared strictly.

A third class is `ONE_SIDED`: a fact one archive holds and the other does not,
under an identity both would agree on. That is the interesting one, and it is
what a scope difference or a missing classification looks like from outside.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from build_crossframework_snapshot import (  # noqa: E402
    ALL_METRICS,
    DEFAULT_ISSUERS,
)
from core_registry import CoreRegistry  # noqa: E402
from coverage_semantics import scoped_ledger  # noqa: E402
from data_contract import AvailabilityBasis  # noqa: E402
from merge_sources import FULL_CORE_METRICS  # noqa: E402
from registry_seed import seed  # noqa: E402
from sec_bulk import BulkFactsSource  # noqa: E402
from sec_ingest import DEFAULT_METRICS, Ingestor  # noqa: E402
from sqlite_archive import SQLiteArchive  # noqa: E402

HARNESS = os.path.join(
    HERE, "experiments", "003-llm-evidence-retrieval", "harness"
)
DEFAULT_FACTS = os.path.join(HARNESS, "inventory")
DEFAULT_REFERENCE = os.path.join(HARNESS, "snapshot-crossframework.sqlite")
DEFAULT_TARGET = os.path.join(HARNESS, "snapshot-fullscope.sqlite")
DEFAULT_CHAIN_DIR = os.path.join(HARNESS, "collection-fullscope")
REFERENCE_CHAIN_DIR = os.path.join(HARNESS, "collection")

# The fields a disagreement about *what the number is* lives in. Compared
# strictly and without exception: if one of these differs the two archives do
# not hold the same evidence.
SEMANTIC_FIELDS: Tuple[str, ...] = (
    "contract_id",
    "metric",
    "value_json",
    "unit",
    "currency",
    "currency_basis",
    "period_start",
    "period_end",
    "as_of",
    "available_at",
    "available_at_basis",
    "availability_class",
    "instant",
    "taxonomy",
    "concept",
    "accession",
    "form",
    "fiscal_year",
    "fiscal_period",
    "source_fact_id",
    "source_concept_ref",
    "basis_json",
    "definition",
    "methodology",
    "status",
    "observation_count",
)

# The fields that say *where the bytes came from*. Two delivery paths read the
# same fact from different documents, both honestly, and calling that a
# divergence is what makes a diff useless.
PROVENANCE_FIELDS: Tuple[str, ...] = (
    "document_id",
    "content_hash",
    "retrieved_at",
    "first_archived_at",
    "source_url",
)

SELECT = (
    "SELECT o.*, (SELECT os.document_id FROM observation_sources os"
    " WHERE os.observation_id = o.observation_id LIMIT 1) AS document_id"
    " FROM observations o"
)

FILED_AS_OF_DATE = AvailabilityBasis.FILED_AS_OF_DATE.value


def confirm_scope() -> Dict[str, Any]:
    """
    The three metric-set definitions, compared, and a refusal to continue.

    A run that quietly used the 8-metric slice is indistinguishable from a
    20-metric run that collected nothing, which is the same shape as the bug
    2.13 caught. So this raises rather than warns.
    """
    definitions = {
        "sec_ingest.DEFAULT_METRICS": list(DEFAULT_METRICS),
        "build_crossframework_snapshot.ALL_METRICS": list(ALL_METRICS),
        "merge_sources.FULL_CORE_METRICS": list(FULL_CORE_METRICS),
    }
    core_a, core_b = set(ALL_METRICS), set(FULL_CORE_METRICS)
    probe = SQLiteArchive(":memory:")
    try:
        probe_registry = CoreRegistry(probe.connection)
        seeded = seed(probe_registry)
        seeded_metrics = sorted(
            m.metric_id for m in probe_registry.metrics()
        )
    finally:
        probe.close()

    if core_a != core_b:
        raise SystemExit(
            "the two twenty-metric definitions are different sets: "
            f"{sorted(core_a - core_b)} only in ALL_METRICS, "
            f"{sorted(core_b - core_a)} only in FULL_CORE_METRICS"
        )
    if core_a != set(seeded_metrics):
        raise SystemExit(
            "the registry seed declares a different metric set: "
            f"{sorted(core_a - set(seeded_metrics))} undeclared, "
            f"{sorted(set(seeded_metrics) - core_a)} unrequested"
        )
    return {
        "definitions": definitions,
        "core_scope": sorted(core_a),
        "core_scope_size": len(core_a),
        "ingestion_slice_is_a_subset": set(DEFAULT_METRICS) < core_a,
        "metrics_outside_the_slice": sorted(core_a - set(DEFAULT_METRICS)),
        "registry_seed_metrics": seeded_metrics,
        "registry_seed_size": len(seeded_metrics),
        "registry_seed": seeded,
        "all_three_agree": True,
    }


def ticker_map_from(reference: str, wanted: Sequence[str]) -> Dict[str, str]:
    """
    Ticker to CIK, read out of the reference archive's own `assets` table.

    The bulk source refuses to infer this from a company name -- 2.12 recorded
    that the first version resolved 2 of 12 issuers by prefix match, both
    accidentally, and would have attached one issuer's filings to another. So
    the map is passed in rather than guessed, and the reference archive is an
    acceptable source for it because those CIKs came from EDGAR's own company
    map when that archive was built. The CIK inside each payload document is
    what the bulk source matches on; this map only says which ticker asked.
    """
    connection = sqlite3.connect(reference)
    connection.row_factory = sqlite3.Row
    out: Dict[str, str] = {}
    for ticker in wanted:
        row = connection.execute(
            "SELECT cik FROM assets WHERE ticker = ?", (ticker.upper(),)
        ).fetchone()
        if row is None or not row["cik"]:
            raise SystemExit(
                f"the reference archive holds no CIK for {ticker!r}, so there "
                "is no honest ticker map to give the bulk source"
            )
        out[ticker.upper()] = str(row["cik"])
    connection.close()
    return out


def build(
    target: str,
    facts_dir: str,
    tickers: Dict[str, str],
    metrics: Sequence[str],
    issuers: Sequence[Tuple[str, Tuple[str, ...]]],
    chain_dir: Optional[str],
    submissions_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """A fresh archive, bulk-bootstrap, full Core scope, zero network."""
    if os.path.exists(target):
        os.remove(target)
    if chain_dir and os.path.isdir(chain_dir):
        for name in os.listdir(chain_dir):
            os.remove(os.path.join(chain_dir, name))
    os.makedirs(chain_dir, exist_ok=True)

    store = SQLiteArchive(target)
    registry = CoreRegistry(store.connection)
    seeded = seed(registry)
    source = BulkFactsSource(
        facts_dir,
        label="bulk-fullscope",
        ticker_map=tickers,
        submissions_directory=submissions_dir,
    )
    ingestor = Ingestor(store, source, registry)

    started = time.monotonic()
    reports: Dict[str, Any] = {}
    for ticker, forms in issuers:
        report = ingestor.ingest(
            ticker, metrics=metrics, forms=forms
        )
        chain = ingestor.collection_chain(ticker)
        with open(
            os.path.join(chain_dir, f"{ticker.upper()}.json"),
            "w", encoding="utf-8",
        ) as handle:
            json.dump(chain, handle, indent=2, sort_keys=True, default=str)
        reports[ticker.upper()] = {
            **report.contract_dict(),
            "chain_totals": chain["totals"],
        }
        print(
            f"  {ticker.upper():<6} {report.observations_stored:>6} obs  "
            f"{report.documents_stored:>3} docs  "
            f"filings_ingested={report.filings_ingested:<4} "
            f"{report.outcome}  {report.elapsed_seconds}s",
            flush=True,
        )
    elapsed = round(time.monotonic() - started, 2)
    transport = source.transport_stats()
    store.close()

    size = os.path.getsize(target)
    return {
        "seeded": seeded,
        "elapsed_seconds": elapsed,
        "archive_bytes": size,
        "documents_read": source.documents_read,
        "concept_fetches": source.concept_fetches,
        "network_fetches": source.network_fetches,
        "issuers_held": transport["issuers_held"],
        "submissions_stream": bool(submissions_dir),
        "issuers": reports,
    }


def load(path: str) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, int]]]:
    """
    Every observation of one archive, keyed by `source_fact_id`.

    Not keyed by `observation_id`: the archive assigns `obsarch_<hash>` itself,
    so that column is archive-local and two archives built from the same
    evidence will disagree on every value of it. `source_fact_id` is the 2.5
    identity and is route-independent by construction.
    """
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    observations: Dict[str, Dict[str, Any]] = {}
    per_issuer: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"observations": 0, "metrics": 0, "filings": 0}
    )
    metrics_seen: Dict[str, set] = defaultdict(set)
    ticker_of: Dict[str, str] = {
        str(row["asset_id"]): str(row["ticker"]).upper()
        for row in connection.execute("SELECT asset_id, ticker FROM assets")
    }
    for row in connection.execute(SELECT):
        record = {field: row[field] for field in row.keys()}
        record["ticker"] = ticker_of.get(str(row["asset_id"]), "")
        observations[str(row["source_fact_id"])] = record
        ticker = record["ticker"]
        per_issuer[ticker]["observations"] += 1
        metrics_seen[ticker].add(str(row["metric"]))
    for ticker, metrics in metrics_seen.items():
        per_issuer[ticker]["metrics"] = len(metrics)
    for row in connection.execute(
        "SELECT a.ticker AS ticker, COUNT(*) AS n FROM held_filings h"
        " JOIN assets a ON a.asset_id = h.asset_id GROUP BY a.ticker"
    ):
        per_issuer[str(row["ticker"]).upper()]["filings"] = int(row["n"])
    connection.close()
    return observations, per_issuer


def reconcile(bulk_path: str, reference_path: str) -> Dict[str, Any]:
    """
    Every fact, both archives, joined on `source_fact_id`.

    Three classes and a per-field breakdown, because "they agree" and "they
    agree about different things" are different results and a single number
    cannot carry both.
    """
    bulk, _ = load(bulk_path)
    api, _ = load(reference_path)

    shared = set(bulk) & set(api)
    only_bulk = sorted(set(bulk) - set(api))
    only_api = sorted(set(api) - set(bulk))

    matched = 0
    provenance_only: List[str] = []
    divergent: List[str] = []
    archive_key_differs = 0
    field_counts: Counter = Counter()
    examples: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for key in sorted(shared):
        mine, theirs = bulk[key], api[key]
        if mine.get("observation_id") != theirs.get("observation_id"):
            archive_key_differs += 1
        semantic = [
            field for field in SEMANTIC_FIELDS
            if mine.get(field) != theirs.get(field)
        ]
        provenance = [
            field for field in PROVENANCE_FIELDS
            if mine.get(field) != theirs.get(field)
        ]
        # Counted for every shared fact, not only for the ones with no semantic
        # difference. A row that is divergent *and* differently attributed is
        # still differently attributed, and a count that only looked at the
        # clean rows would report zero here when the answer is "all of them".
        for field in provenance:
            field_counts[f"provenance:{field}"] += 1
        if semantic:
            divergent.append(key)
            for field in semantic:
                field_counts[field] += 1
            if len(examples["divergent"]) < 12:
                examples["divergent"].append({
                    "source_fact_id": key,
                    "ticker": mine.get("ticker"),
                    "metric": mine.get("metric"),
                    "accession": mine.get("accession"),
                    "differing_fields": {
                        field: {
                            "bulk": mine.get(field), "api": theirs.get(field)
                        }
                        for field in semantic
                    },
                    "differing_provenance_fields": provenance,
                })
        else:
            matched += 1
            if provenance:
                provenance_only.append(key)

    def detail(
        identities: Sequence[str], source: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        return {
            "count": len(identities),
            "by_metric": dict(sorted(Counter(
                source[key]["metric"] for key in identities
            ).items())),
            "by_ticker": dict(sorted(Counter(
                source[key].get("ticker", "") for key in identities
            ).items())),
            "sample": [
                {
                    "source_fact_id": key,
                    "ticker": source[key].get("ticker"),
                    "metric": source[key]["metric"],
                    "accession": source[key]["accession"],
                    "period_end": source[key]["period_end"],
                }
                for key in identities[:15]
            ],
        }

    # The residual divergence, named.
    #
    # A single "17,043 divergent" would be a number nobody can act on, and it is
    # not one thing. The reference archive was built by the 2.13-era code, so it
    # carries that code's behaviours, while the bulk archive is the only side
    # written under the corrected contract. Splitting it by *why* is the only way
    # to tell a stale artefact from a real semantic difference.
    split: Counter = Counter()
    for key in divergent:
        their_value = str(api[key].get("available_at") or "")
        my_value = str(bulk[key].get("available_at") or "")
        if their_value.endswith("T00:00:00+00:00"):
            split["reference holds the pre-fix midnight fabrication"] += 1
        elif my_value and their_value[:10] == my_value[:10]:
            split["same day, the API route holds a real acceptance instant"] += 1
        elif my_value and their_value[:10] < my_value[:10]:
            split["API accepted before the filed date the bulk route has"] += 1
        else:
            split["the two routes have different source precision"] += 1

    # A one-sided row is only a finding if the reference was asked for it. Two
    # things decide that, and only checking the first produced a number that was
    # both wrong and alarming: the 8-metric population archive holds 75 issuers
    # and was never asked for twelve of the twenty metrics, so "only in bulk" is
    # the scope rule of 2.13 doing its job -- and 63 of its issuers are simply not
    # in this run, so "only in reference" is a population difference. An
    # unexplained one-sided count is indistinguishable from a dropped fact, so
    # both axes are named.
    reference_metrics = {str(row["metric"]) for row in api.values()}
    run_metrics = {str(row["metric"]) for row in bulk.values()}
    reference_issuers = {str(row.get("ticker") or "") for row in api.values()}
    run_issuers = {str(row.get("ticker") or "") for row in bulk.values()}

    def cause(key: str, side: Dict[str, Dict[str, Any]]) -> str:
        # A fact that is one-sided is missing from the *other* archive, so the
        # question is always "was the other archive asked for it?" -- asking
        # whether the archive that holds it was asked makes every one-sided row
        # look like a disagreement.
        metric = str(side[key]["metric"])
        ticker = str(side[key].get("ticker") or "")
        other_metrics = reference_metrics if side is bulk else run_metrics
        other_issuers = reference_issuers if side is bulk else run_issuers
        if ticker not in other_issuers:
            return "the other archive covers issuers this run did not"
        if metric not in other_metrics:
            return (
                "outside the reference's metric scope"
                if side is bulk
                else "outside this run's metric scope"
            )
        return "the two archives hold a different fact under this identity"

    one_sided: Counter = Counter()
    for key in only_bulk:
        one_sided[cause(key, bulk)] += 1
    for key in only_api:
        one_sided[cause(key, api)] += 1

    return {
        "join_key": "source_fact_id",
        "bulk_total": len(bulk),
        "api_total": len(api),
        "reference_metric_scope_size": len(reference_metrics),
        "this_run_metric_scope_size": len(
            {str(row["metric"]) for row in bulk.values()}
        ),
        "shared_identity": len(shared),
        "matched": matched,
        "provenance_only": len(provenance_only),
        "divergent": len(divergent),
        "divergent_field_counts": dict(field_counts.most_common()),
        "divergent_by_cause": dict(sorted(split.items())),
        "one_sided_by_cause": dict(sorted(one_sided.items())),
        "only_in_bulk": detail(only_bulk, bulk),
        "only_in_api": detail(only_api, api),
        "archive_assigned_observation_id_differs": archive_key_differs,
        "reference_built_by_pre_fix_code": True,
        "examples": examples,
    }


def pit_safety(bulk_path: str, reference_path: str) -> Dict[str, Any]:
    """
    Is any fact in the bulk-built archive knowable before it was published?

    The reference archive was built by the API path *before* the availability
    contract was fixed, so it is used here for what only it has: EDGAR's genuine
    acceptance instants. For a fact whose accession sat inside the submissions
    window, `available_at` is the real moment of dissemination, and that is the
    strongest available statement of when the evidence became public.

    The invariant is one line: no fact may be replayable before the moment the
    source says it became public. Checked per fact, not in aggregate, because an
    aggregate cannot distinguish "all correct" from "correct on average".

    The reference's own 8,825 fallback rows are excluded from the comparison and
    counted separately. Their value is `T00:00:00+00:00` on the filed date --
    the fabrication 2.14 found -- so they are not evidence of a known instant and
    comparing against them would compare against a fiction.
    """
    bulk, _ = load(bulk_path)
    api, _ = load(reference_path)

    promoted = 0
    basis_counts: Counter = Counter()
    eligible_before_source = 0
    eligible_before_source_rows: List[Dict[str, Any]] = []
    compared_against_instant = 0
    compared_against_fallback = 0
    not_comparable = 0

    for key, mine in bulk.items():
        basis = str(mine.get("available_at_basis"))
        value = str(mine.get("available_at") or "")
        basis_counts[basis] += 1
        if value and "T" in value and basis == FILED_AS_OF_DATE:
            promoted += 1

        eligible = str(mine.get("replay_eligible_from") or "")
        declared = str(mine.get("available_at") or "")
        theirs = api.get(key)
        if theirs is None:
            not_comparable += 1
            continue
        their_value = str(theirs.get("available_at") or "")
        if not their_value:
            not_comparable += 1
            continue
        if their_value.endswith("T00:00:00+00:00"):
            # The reference's own fabricated midnight. Not an instant.
            compared_against_fallback += 1
            continue
        compared_against_instant += 1
        if not eligible or not _instant_at_or_after(eligible, their_value):
            eligible_before_source += 1
            if len(eligible_before_source_rows) < 10:
                eligible_before_source_rows.append({
                    "source_fact_id": key,
                    "ticker": mine.get("ticker"),
                    "metric": mine.get("metric"),
                    "bulk_declared": declared,
                    "bulk_eligible_from": eligible,
                    "api_acceptance_instant": their_value,
                })

    return {
        "basis_counts": dict(basis_counts),
        "declared_value_was_promoted_to_an_instant": promoted,
        "compared_against_a_genuine_acceptance_instant":
            compared_against_instant,
        "compared_against_the_reference_fallback_fiction":
            compared_against_fallback,
        "not_comparable": not_comparable,
        "eligible_before_the_source_said_it_was_public":
            eligible_before_source,
        "examples": eligible_before_source_rows,
        "invariant": (
            "no observation is replayable before the instant EDGAR published it"
        ),
        "holds": eligible_before_source == 0 and promoted == 0,
    }


def _instant_at_or_after(candidate: str, boundary: str) -> bool:
    """
    `candidate` is at or after `boundary`, compared as instants.

    Not as strings. The two sides here are written by different producers -- the
    archive emits `+00:00` and EDGAR emits `Z` -- and a string comparison of two
    UTC spellings of the same instant can order them wrongly, which would make
    this check report a safety failure that is not one. A check that cries wolf
    on formatting gets ignored, and then it catches nothing.
    """
    left = _as_utc(candidate)
    right = _as_utc(boundary)
    if left is None or right is None:
        return False
    return left >= right


def _as_utc(value: str):
    from datetime import datetime, timezone

    text = (value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def issuer_forms_from(reference: str, tickers: Sequence[str]) -> Dict[str, List[str]]:
    """
    Each issuer's own recorded form set, read out of the reference archive.

    Taken from evidence rather than from a hand-written list, because a
    coverage difference that is really a form-policy difference is not a finding
    about coverage. Three of the twelve issuers in the population run are foreign
    private issuers filing 20-F and never 10-K; a policy of "10-K and 10-Q"
    would have reported them as SOURCE_SILENT when the real answer is that the
    archive never asked the right question.
    """
    connection = sqlite3.connect(reference)
    connection.row_factory = sqlite3.Row
    out: Dict[str, List[str]] = {}
    for ticker in tickers:
        rows = [
            str(row["form"])
            for row in connection.execute(
                "SELECT DISTINCT h.form FROM held_filings h JOIN assets a"
                " ON a.asset_id = h.asset_id WHERE a.ticker = ?"
                " AND h.form IS NOT NULL",
                (ticker.upper(),),
            )
        ]
        out[ticker.upper()] = sorted(set(rows))
    connection.close()
    return out


def business_models_from(reference: str) -> Dict[str, str]:
    """
    The business model each issuer was classified as, from the reference archive.

    The bulk path cannot derive this: `companyfacts` carries no SIC, which is
    why a bulk-only corpus makes no applicability ruling at all. The reference
    archive recorded the classification when it had submissions, so it is the
    only place in this repository where these twelve issuers have a type.

    Read as a stratification axis for measurement, never as a source of truth
    about a filer -- a model the archive already recorded is evidence, and this
    is a report about coverage shape, not a new ruling.
    """
    connection = sqlite3.connect(reference)
    connection.row_factory = sqlite3.Row
    out = {
        str(row["ticker"]).upper(): str(row["business_model"])
        for row in connection.execute(
            "SELECT a.ticker AS ticker, b.business_model AS business_model"
            " FROM issuer_business_model b JOIN assets a"
            " ON a.asset_id = b.asset_id"
        )
    }
    connection.close()
    return out


def completeness_panel(path: str) -> Dict[str, Any]:
    """
    Seven counters, because "the observations look right" is not a result.

    Added after a lost indentation level collapsed a derived filing index from 72
    entries to 50 and **nothing failed**: the observations were byte-identical,
    because a fact's own `filed` date supplies the same answer when the index
    entry is missing. A false success with correct output is the failure mode a
    counter on one dimension cannot see, so the panel counts every dimension that
    could have moved independently.

        filings       documents      source facts
        observations  identity       coverage        provenance
    """
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row

    def scalar(sql: str, *args) -> int:
        row = connection.execute(sql, args).fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    documents = scalar("SELECT COUNT(*) FROM source_documents")
    observations = scalar("SELECT COUNT(*) FROM observations")
    distinct_identity = scalar(
        "SELECT COUNT(DISTINCT source_fact_id) FROM observations"
    )
    duplicate_identity = scalar(
        "SELECT COUNT(*) FROM (SELECT 1 FROM observations"
        " GROUP BY source_fact_id HAVING COUNT(*) > 1)"
    )
    distinct_accessions = scalar(
        "SELECT COUNT(DISTINCT accession) FROM observations"
    )
    held_filings = scalar("SELECT COUNT(*) FROM held_filings")
    # A fact with no accession has no filing to point at, which breaks the
    # provenance chain one link short rather than dropping the fact.
    facts_without_accession = scalar(
        "SELECT COUNT(*) FROM observations WHERE accession IS NULL OR accession = ''"
    )
    # Every observation must reach at least one stored document. A reference that
    # dangles is evidence that looks like evidence and is not.
    without_document = scalar(
        "SELECT COUNT(*) FROM observations o WHERE NOT EXISTS"
        " (SELECT 1 FROM observation_sources s"
        "  WHERE s.observation_id = o.observation_id)"
    )
    scope = {
        str(row["metric_id"]): int(row["n"])
        for row in connection.execute(
            "SELECT metric_id, COUNT(*) AS n FROM ingestion_scope GROUP BY metric_id"
        )
    }
    scope_status = {
        str(row["metric_id"]): str(row["status"])
        for row in connection.execute(
            "SELECT metric_id, status FROM ingestion_scope"
        )
    }
    runs = scalar("SELECT COUNT(*) FROM ingestion_runs")
    scoped_assets = scalar("SELECT COUNT(DISTINCT asset_id) FROM ingestion_scope")
    connection.close()

    return {
        "runs": runs,
        "scoped_assets": scoped_assets,
        "filings_held": held_filings,
        "distinct_accessions_in_observations": distinct_accessions,
        "documents_stored": documents,
        "observations": observations,
        "distinct_source_fact_ids": distinct_identity,
        "duplicate_identities": duplicate_identity,
        "facts_without_accession": facts_without_accession,
        "observations_without_a_stored_document": without_document,
        "scope_metrics": len(scope),
        "scope_by_status": scope_status,
        "provenance_chain_complete": (
            facts_without_accession == 0 and without_document == 0
        ),
    }


def coverage_matrix(
    path: str,
    metrics: Sequence[str],
    models: Dict[str, str],
) -> Dict[str, Any]:
    """
    Metric by issuer, and metric by company type, cell by cell.

    The question this exists to answer is 2.10's, left open: *which* Core
    metrics get thin, and is that the metric's fault or the filer's. A single
    "20 metrics collected X%" answers neither, because averaging over metrics and
    issuers together is exactly the operation that hides both effects.

    So the unit of report is a cell, and a cell carries three things: the ledger's
    own status, the number of observations, and

        coverage_ratio = periods of this metric's own kind that hold it
                       / periods of that kind the issuer has any evidence for

    **The denominator is keyed on the metric's own `normal_period_type`**, which
    the registry already declares -- 13 metrics are DURATION and 7 are INSTANT.
    A single denominator across both was tried first and it does not work: every
    metric landed near 0.5 and the measure separated nothing, because a
    balance-sheet instant and a quarterly duration can never both be complete in
    the same column. The ratio is a measurement and never becomes a status; it
    does not add a word to the ledger's vocabulary.

    The denominator is what the archive can see that it did not ask for. A ratio
    below 1.0 means the metric is absent for periods of its own kind that the
    archive holds evidence about, which is the whole question.
    """
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    registry = CoreRegistry(connection)

    kind_of_metric = {
        metric.metric_id: str(metric.normal_period_type)
        for metric in registry.metrics()
    }

    # Distinct period_ends of each kind, per issuer. A period is an INSTANT when
    # the observation carries no start, and a DURATION when it does -- the same
    # distinction the registry's `normal_period_type` is describing.
    periods_by_asset: Dict[str, Dict[str, set]] = defaultdict(
        lambda: {"INSTANT": set(), "DURATION": set()}
    )
    for row in connection.execute(
        "SELECT asset_id, period_end, period_start FROM observations"
        " WHERE period_end IS NOT NULL"
    ):
        kind = "DURATION" if row["period_start"] else "INSTANT"
        periods_by_asset[str(row["asset_id"])][kind].add(str(row["period_end"]))

    cells: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in connection.execute(
        "SELECT asset_id, metric, period_end, period_start, COUNT(*) AS n"
        " FROM observations GROUP BY asset_id, metric, period_end, period_start"
    ):
        key = (str(row["metric"]), str(row["asset_id"]))
        entry = cells.setdefault(
            key, {"observations": 0, "periods": set()}
        )
        entry["observations"] += int(row["n"])
        if row["period_end"]:
            entry["periods"].add(str(row["period_end"]))

    # Filings that reported something the archive holds. This is the second
    # denominator, and it is the one that answers the operational question.
    #
    # The first denominator -- every instant the archive knows for this issuer --
    # turned out to be an artefact. RBC holds 152 distinct instants, but
    # `Assets` spans 68, `Cash` 77 and `Equity` 73, and their union is 86; the
    # remaining ~66 come from a `dei` cover-page concept and two alternate
    # cash/equity tags, each with its own history. So a metric scored 0.45
    # against a union that no single concept spans, which reads as "this metric
    # is thin" when the truth is "no concept spans the union". Against the 66
    # filings RBC actually made, `Assets` is complete.
    #
    # Both are reported, and neither is hidden: a ratio needs its denominator
    # stated or it is not a measurement.
    filings_by_asset: Dict[str, int] = defaultdict(int)
    for row in connection.execute(
        "SELECT asset_id, COUNT(DISTINCT accession) AS n FROM observations"
        " WHERE accession IS NOT NULL AND accession != '' GROUP BY asset_id"
    ):
        filings_by_asset[str(row["asset_id"])] = int(row["n"])

    matrix: List[Dict[str, Any]] = []
    for row in connection.execute("SELECT asset_id, ticker FROM assets"):
        asset_id = str(row["asset_id"])
        ticker = str(row["ticker"]).upper()
        ledger = scoped_ledger(connection, registry, asset_id, ticker)
        issuer_periods = periods_by_asset.get(
            asset_id, {"INSTANT": set(), "DURATION": set()}
        )
        filings = filings_by_asset.get(asset_id, 0)
        for item in ledger["rows"]:
            metric = str(item["metric"])
            kind = kind_of_metric.get(metric, "UNKNOWN")
            entry = cells.get((metric, asset_id), {})
            observed = len(entry.get("periods", ()))
            available = len(issuer_periods.get(kind, ()))
            matrix.append({
                "metric": metric,
                "ticker": ticker,
                "business_model": models.get(ticker, "UNCLASSIFIED"),
                "normal_period_type": kind,
                "status": str(item["status"]),
                "observations": int(entry.get("observations", 0)),
                "periods_with_metric": observed,
                "periods_of_that_kind": available,
                "coverage_ratio": (
                    round(observed / available, 4) if available else None
                ),
                "filings_reporting_something_held": filings,
                # Reported in each filing the filer made. Can exceed 1.0 because a
                # 10-K reports the prior year-end instant as a comparative, which
                # is a real fact at a real date and not a duplicate.
                "filing_ratio": (
                    round(observed / filings, 4) if filings else None
                ),
            })
    connection.close()

    by_metric: Dict[str, Counter] = defaultdict(Counter)
    by_model: Dict[str, Counter] = defaultdict(Counter)
    by_model_metric: Dict[Tuple[str, str], Counter] = defaultdict(Counter)
    ratios_by_metric: Dict[str, List[float]] = defaultdict(list)
    ratios_by_model: Dict[str, List[float]] = defaultdict(list)
    ratios_by_model_metric: Dict[Tuple[str, str], List[float]] = defaultdict(list)
    filings_by_metric: Dict[str, List[float]] = defaultdict(list)
    for cell in matrix:
        by_metric[cell["metric"]][cell["status"]] += 1
        by_model[cell["business_model"]][cell["status"]] += 1
        by_model_metric[
            (cell["business_model"], cell["metric"])
        ][cell["status"]] += 1
        if cell["filing_ratio"] is not None:
            ratios_by_metric[cell["metric"]].append(cell["filing_ratio"])
            ratios_by_model[cell["business_model"]].append(
                cell["filing_ratio"]
            )
            ratios_by_model_metric[
                (cell["business_model"], cell["metric"])
            ].append(cell["filing_ratio"])
        if cell["coverage_ratio"] is not None:
            filings_by_metric[cell["metric"]].append(cell["coverage_ratio"])

    def summarise(counter: Counter, ratios: List[float]) -> Dict[str, Any]:
        total = sum(counter.values())
        ordered = sorted(ratios)
        return {
            "cells": total,
            "status_counts": dict(sorted(counter.items())),
            "collected_fraction": (
                round(counter.get("COLLECTED", 0) / total, 4) if total else None
            ),
            "median_filing_ratio": (
                round(ordered[len(ordered) // 2], 4) if ordered else None
            ),
            "min_filing_ratio": ordered[0] if ordered else None,
            "cells_below_one_filing": sum(1 for r in ordered if r < 1.0),
            "ratio_measured_cells": len(ordered),
        }

    return {
        "metric_by_issuer": matrix,
        "by_metric": {
            metric: {
                **summarise(counter, ratios_by_metric[metric]),
                # Kept beside the filing ratio, and named for what it is: the
                # share of the union of all instants the archive knows that this
                # metric's concepts span. Useful for spotting a concept that
                # reaches a different window, misleading as a thinness measure.
                "median_union_instant_ratio": (
                    round(
                        sorted(filings_by_metric[metric])[
                            len(filings_by_metric[metric]) // 2
                        ],
                        4,
                    )
                    if filings_by_metric[metric] else None
                ),
            }
            for metric, counter in sorted(by_metric.items())
        },
        "by_business_model": {
            model: summarise(counter, ratios_by_model[model])
            for model, counter in sorted(by_model.items())
        },
        "by_model_and_metric": {
            f"{model}::{metric}": dict(sorted(counter.items()))
            for (model, metric), counter in sorted(by_model_metric.items())
        },
        "filing_ratio_by_model_and_metric": {
            f"{model}::{metric}": summarise(
                Counter(), ratios
            )["median_filing_ratio"]
            for (model, metric), ratios in sorted(
                ratios_by_model_metric.items()
            )
        },
        "the_two_axes_can_be_separated": len(by_model) > 1,
        "business_models_present": sorted(by_model),
    }


def duplicate_scan(path: str) -> Dict[str, Any]:
    """
    Duplication is a property of the identity, not of the row count.

    A fingerprint counts rows, so a second row for the same evidence would
    look like a successful addition rather than a duplication.
    """
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    rows = [
        dict(row)
        for row in connection.execute(
            "SELECT a.ticker AS ticker, o.metric AS metric,"
            " o.period_end AS period_end, o.source_fact_id AS source_fact_id,"
            " COUNT(*) AS n FROM observations o"
            " JOIN assets a ON a.asset_id = o.asset_id"
            " GROUP BY a.ticker, o.metric, o.period_end, o.source_fact_id"
            " HAVING COUNT(*) > 1"
        )
    ]
    connection.close()
    return {
        "identities_with_more_than_one_observation": len(rows),
        "sample": rows[:10],
    }


def metric_yield(path: str, metrics: Sequence[str]) -> Dict[str, Any]:
    """Per metric, per issuer: how much each of the twenty actually yields."""
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    counts: Dict[str, Counter] = defaultdict(Counter)
    for row in connection.execute(
        "SELECT a.ticker AS ticker, o.metric AS metric, COUNT(*) AS n"
        " FROM observations o JOIN assets a ON a.asset_id = o.asset_id"
        " GROUP BY a.ticker, o.metric"
    ):
        counts[str(row["metric"])][str(row["ticker"]).upper()] = int(row["n"])
    issuers = sorted({
        str(row["ticker"]).upper()
        for row in connection.execute("SELECT ticker FROM assets")
    })
    out: Dict[str, Any] = {}
    for metric in metrics:
        per_issuer = counts.get(metric, Counter())
        out[metric] = {
            "total": sum(per_issuer.values()),
            "issuers_holding": len(per_issuer),
            "per_issuer": {t: per_issuer.get(t, 0) for t in issuers},
        }
    connection.close()
    return out


def statuses(path: str) -> Dict[str, Any]:
    """The coverage ledger's own status vocabulary, per issuer."""
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    registry = CoreRegistry(connection)
    out: Dict[str, Any] = {}
    for row in connection.execute("SELECT asset_id, ticker FROM assets"):
        ticker = str(row["ticker"]).upper()
        ledger = scoped_ledger(
            connection, registry, str(row["asset_id"]), ticker
        )
        tally: Counter = Counter(str(item["status"]) for item in ledger["rows"])
        out[ticker] = {
            "metrics": len(ledger["rows"]),
            "status_counts": dict(sorted(tally.items())),
            "metrics_by_status": {
                status: sorted(
                    str(item["metric"]) for item in ledger["rows"]
                    if str(item["status"]) == status
                )
                for status in sorted(tally)
            },
        }
    connection.close()
    return out


def taxonomies(path: str) -> Dict[str, Any]:
    """
    What the archive holds, by taxonomy, and what it declares unmodelled.

    A taxonomy that appears in neither column is a taxonomy a filer reports and
    the semantic layer says nothing about, which is the third column of the 2.10
    table and the only one that is work.
    """
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    held = {
        str(row[0]): int(row[1])
        for row in connection.execute(
            "SELECT taxonomy, COUNT(*) FROM observations GROUP BY taxonomy"
        )
    }
    unmodelled = {
        str(row["taxonomy"]): {
            "kind": row["kind"], "reason": row["reason"]
        }
        for row in connection.execute(
            "SELECT taxonomy, kind, reason FROM unmodelled_taxonomies"
        )
    }
    models = {
        str(row["ticker"]).upper(): {
            "business_model": row["business_model"], "source": row["source"]
        }
        for row in connection.execute(
            "SELECT a.ticker AS ticker, b.business_model AS business_model,"
            " b.source AS source FROM issuer_business_model b"
            " JOIN assets a ON a.asset_id = b.asset_id"
        )
    }
    connection.close()
    return {
        "observations_by_taxonomy": dict(sorted(held.items())),
        "declared_unmodelled": unmodelled,
        "issuer_business_model": dict(sorted(models.items())),
    }


def gates(target: str, chain_dir: str, out_json: str) -> Dict[str, Any]:
    """
    The existing eight gates, run as a subprocess against the new archive.

    Run the committed tool rather than reimplementing it. A gate reimplemented
    for a report is a gate that can disagree with the one the project measures
    with, and the instrument that found the SIC hole and the unmodelled
    taxonomies has to stay the same instrument.
    """
    for path in (out_json,):
        if os.path.exists(path):
            os.remove(path)
    completed = subprocess.run(
        [
            sys.executable, os.path.join(HERE, "score_collection_gates.py"),
            "--snapshot", target, "--chain-dir", chain_dir, "--json", out_json,
        ],
        cwd=HERE, capture_output=True, text=True,
    )
    if completed.returncode != 0:
        return {
            "ran": False,
            "returncode": completed.returncode,
            "stderr": completed.stderr[-2000:],
        }
    with open(out_json, encoding="utf-8") as handle:
        payload = json.load(handle)
    # `score_collection_gates.py` writes `{"issuers": ..., "measured": ...,
    # "skipped": ...}` so that a run's universe is counted rather than asserted
    # and a skipped issuer is named. Older artefacts were a bare
    # `{ticker: entry}` map; both shapes are read so the tool can be pointed at an
    # artefact from either version of the report format.
    if isinstance(payload.get("issuers"), dict):
        report = payload["issuers"]
        skipped = payload.get("skipped") or []
    else:
        report = {
            key: value for key, value in payload.items()
            if isinstance(value, dict) and "gate_totals" in value
        }
        skipped = []
    totals: Counter = Counter()
    failures: Counter = Counter()
    for entry in report.values():
        for gate, count in entry["gate_totals"].items():
            totals[gate] += count
        for metric, gates_by_name in entry["metrics"].items():
            for gate, ok in gates_by_name.items():
                if not ok:
                    failures[f"{gate}:{metric}"] += 1
    universe = sum(entry["metrics_total"] for entry in report.values())
    return {
        "ran": True,
        "issuers_measured": len(report),
        "issuers_skipped": skipped,
        "metric_issuers": universe,
        "gate_totals": dict(sorted(totals.items())),
        "gate_pass_rate": {
            gate: f"{count}/{universe}" for gate, count in sorted(totals.items())
        },
        "failing_gates": dict(sorted(failures.items())),
        "per_issuer": {
            ticker: {
                "business_model": entry["business_model"],
                "business_model_source": entry["business_model_source"],
                "metrics_total": entry["metrics_total"],
                "chain_totals": entry["chain_totals"],
            }
            for ticker, entry in sorted(report.items())
        },
    }


def _ticker_map_from_file(path: str) -> Dict[str, str]:
    """
    The ticker map that shipped with the payload.

    Read from the payload rather than from an archive, because an archive need not
    hold the issuers being ingested -- 2.23 ran eight filers that exist in no
    archive here yet, and the honest source for their CIKs is the SEC's own
    company ticker map, which `fetch_source_inventory.py` writes out via the
    same provider ingestion resolves through. Nothing is inferred from a name.
    """
    with open(path, encoding="utf-8") as handle:
        mapping = json.load(handle)
    return {str(k).upper(): str(v) for k, v in mapping.items()}


def _tickers_from_map(path: str) -> List[str]:
    """Issuer list and ticker map from a payload's own `tickers.json`."""
    with open(path, encoding="utf-8") as handle:
        mapping = json.load(handle)
    return sorted(str(ticker).upper() for ticker in mapping)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts-dir", default=DEFAULT_FACTS)
    parser.add_argument(
        "--submissions-dir",
        help="each issuer's submissions document, as the SEC's bulk "
             "distribution ships it. The second stream: companyfacts is "
             "everything a filer ever tagged, submissions is the filer's own "
             "filing history and its own SIC. 2.17 measured that a "
             "companyfacts-only bulk bootstrap records no business model, so no "
             "applicability rule is reachable -- the facts do not stop, the "
             "context does.",
    )
    parser.add_argument("--reference", default=DEFAULT_REFERENCE)
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument("--chain-dir", default=DEFAULT_CHAIN_DIR)
    parser.add_argument("--gates-json", default=os.path.join(
        HARNESS, "gates-fullscope.json"
    ))
    parser.add_argument("--reference-gates-json", default=os.path.join(
        HARNESS, "gates-reference.json"
    ))
    parser.add_argument("--reference-chain-dir", default=REFERENCE_CHAIN_DIR)
    parser.add_argument(
        "--ticker-map",
        help="a payload's own tickers.json; the issuer list and the ticker map "
             "then come from the payload rather than from a list of six",
    )
    parser.add_argument(
        "--forms",
        choices=("reference", "periodic", "submissions"),
        default="reference",
        help="reference: each issuer's own recorded forms, from --reference; "
             "periodic: a hand-written periodic set; submissions: each issuer's "
             "own forms, read from the submissions document the bulk source "
             "already holds. A coverage difference that is really a form-policy "
             "difference is not a finding about coverage, and 'submissions' is "
             "the only option that needs no second archive.",
    )
    parser.add_argument("--label", default="full Core scope, bulk, equivalence")
    parser.add_argument("--out")
    args = parser.parse_args(argv)

    scope = confirm_scope()
    metrics = tuple(scope["core_scope"])
    print(
        f"scope confirmed: {scope['core_scope_size']} Core metrics, "
        f"the 8-metric slice is a strict subset, and the registry seed "
        f"declares exactly the same set",
        flush=True,
    )

    forms_by_ticker: Dict[str, List[str]] = {}
    if args.ticker_map:
        names = _tickers_from_map(args.ticker_map)
        # The payload's own map. An archive is not required to hold the filers
        # being ingested, and reading the CIK from the archive the run is being
        # reconciled against would fail for any filer that has never been in one.
        tickers = _ticker_map_from_file(args.ticker_map)
        if args.forms == "reference":
            forms_by_ticker = issuer_forms_from(args.reference, names)
        elif args.forms == "submissions":
            # The filer's own declaration, read from the submissions document the
            # run already holds. No second archive needed, and no hand-written
            # list that could quietly differ from what the filer files.
            probe = BulkFactsSource(
                args.facts_dir,
                submissions_directory=args.submissions_dir,
                label="forms-probe",
            )
            forms_by_ticker = {
                name: sorted({
                    str(entry.get("form") or "")
                    for entry in probe.filing_index(tickers[name])
                    if entry.get("form")
                }) or ["10-K", "10-Q"]
                for name in names
            }
        else:
            forms_by_ticker = {
                name: ["10-K", "10-Q", "20-F"] for name in names
            }
        issuers = tuple(
            (name, tuple(forms_by_ticker.get(name) or ("10-K", "10-Q")))
            for name in names
        )
    else:
        issuers = tuple(DEFAULT_ISSUERS)
        tickers = ticker_map_from(args.reference, [t for t, _ in issuers])

    models = business_models_from(args.reference)

    print(
        f"issuers: {len(issuers)}  forms: {args.forms}  "
        f"business models present: {sorted(set(models.get(t, 'UNCLASSIFIED') for t, _ in issuers))}",
        flush=True,
    )

    print("\n-- full Core scope bulk bootstrap, fresh archive, zero network")
    built = build(
        args.target, args.facts_dir, tickers, metrics, issuers, args.chain_dir,
        submissions_dir=args.submissions_dir,
    )
    print(
        f"   {built['elapsed_seconds']}s  "
        f"{sum(r['observations_stored'] for r in built['issuers'].values())} "
        f"observations  {built['archive_bytes'] / 1e6:.1f} MB  "
        f"network_fetches={built['network_fetches']}  "
        f"documents_read={built['documents_read']}  "
        f"submissions_stream={built['submissions_stream']}",
        flush=True,
    )

    print("\n-- completeness panel")
    panel = completeness_panel(args.target)
    for key, value in panel.items():
        if key != "scope_by_status":
            print(f"       {key}: {value}", flush=True)

    print("\n-- reconciliation against the reference archive")
    reconciliation = reconcile(args.target, args.reference)
    print(
        f"   reference scope {reconciliation['reference_metric_scope_size']} "
        f"metrics, this run {reconciliation['this_run_metric_scope_size']}",
        flush=True,
    )
    print(
        f"   shared identity {reconciliation['shared_identity']}  "
        f"matched {reconciliation['matched']}  "
        f"divergent {reconciliation['divergent']}  "
        f"only-in-bulk {reconciliation['only_in_bulk']['count']}  "
        f"only-in-reference {reconciliation['only_in_api']['count']}",
        flush=True,
    )
    print("   one-sided by cause:", flush=True)
    for cause, count in reconciliation["one_sided_by_cause"].items():
        print(f"       {cause}: {count}", flush=True)

    print("\n-- point-in-time safety, against the reference's real instants")
    safety = pit_safety(args.target, args.reference)
    print(
        f"   declared value promoted to an instant: "
        f"{safety['declared_value_was_promoted_to_an_instant']}",
        flush=True,
    )
    print(
        f"   compared against {safety['compared_against_a_genuine_acceptance_instant']}"
        f" genuine acceptance instants, "
        f"{safety['eligible_before_the_source_said_it_was_public']}"
        f" eligible too early   "
        f"[{safety['basis_counts']}]",
        flush=True,
    )
    print(f"   invariant holds: {safety['holds']}", flush=True)

    print("\n-- the eight gates")
    bulk_gates = gates(args.target, args.chain_dir, args.gates_json)
    print(f"   this run     {bulk_gates.get('gate_pass_rate')}", flush=True)
    reference_gates = gates(
        args.reference, args.reference_chain_dir, args.reference_gates_json
    )
    print(f"   reference    {reference_gates.get('gate_pass_rate')}", flush=True)

    print("\n-- coverage matrix, metric by issuer")
    # The reference's classifications stratify the matrix when it has them, but a
    # filer the reference has never seen is not unclassified: the archive this run
    # just built holds the model's own classification, read from its submissions,
    # and that is the better evidence of the two. 2.23 ran eight filers that exist
    # in no archive here beforehand.
    for ticker, entry in taxonomies(args.target).get(
        "issuer_business_model", {}
    ).items():
        models[ticker] = str(entry["business_model"])
    matrix = coverage_matrix(args.target, metrics, models)
    print(
        f"   {'metric':<32}{'coll':>6}{'med_filing':>12}{'min':>8}{'<1':>5}  statuses",
        flush=True,
    )
    for metric, summary in matrix["by_metric"].items():
        median = summary["median_filing_ratio"]
        print(
            f"   {metric:<32}{summary['collected_fraction']:>6}"
            f"{(median if median is not None else 0):>12}"
            f"{(summary['min_filing_ratio'] or 0):>8}"
            f"{summary['cells_below_one_filing']:>5}  "
            f"{summary['status_counts']}",
            flush=True,
        )
    print(
        f"   the two axes can be separated: "
        f"{matrix['the_two_axes_can_be_separated']} "
        f"({matrix['business_models_present']})",
        flush=True,
    )

    bulk_observations, bulk_per_issuer = load(args.target)
    api_observations, api_per_issuer = load(args.reference)
    del bulk_observations, api_observations

    result = {
        "experiment": args.label,
        "network_used": False,
        "scope": scope,
        "forms_policy": args.forms,
        "issuers": [ticker for ticker, _ in issuers],
        "forms": {ticker: list(forms) for ticker, forms in issuers},
        "business_models": {
            ticker: models.get(ticker, "UNCLASSIFIED")
            for ticker, _ in issuers
        },
        "bootstrap": built,
        "completeness_panel": panel,
        "reconciliation": reconciliation,
        "pit_safety": safety,
        "duplicates": duplicate_scan(args.target),
        "duplicates_reference": duplicate_scan(args.reference),
        "metric_yield_bulk": metric_yield(args.target, metrics),
        "metric_yield_api": metric_yield(args.reference, metrics),
        "statuses_bulk": statuses(args.target),
        "statuses_api": statuses(args.reference),
        "taxonomies_bulk": taxonomies(args.target),
        "taxonomies_api": taxonomies(args.reference),
        "per_issuer_bulk": bulk_per_issuer,
        "per_issuer_api": api_per_issuer,
        "coverage_matrix": matrix,
        "gates_bulk": bulk_gates,
        "gates_api": reference_gates,
    }
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, sort_keys=True, default=str)
        print(f"\nwritten: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
