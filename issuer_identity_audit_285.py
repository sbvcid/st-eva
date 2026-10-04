"""
2.85 -- canonicalise issuer identity from payload CIK.

Narrowly scoped production corpus-layer fix, plus the audit that verifies it.

## What was wrong

Every payload-keyed reader in this repository derived the issuer from the filename
with `name.split("_")[0].upper()`. That assumes `<TICKER>_companyfacts.json`. Twelve
payloads in this harness are named `<CIK>.json`, so their derived keys were strings
like `0000026172.JSON` and each one appeared beside its canonical issuer as if it
were a different company. The consequence was not only a count: the census reported
75 filers for 63 issuers, and any research keyed on a filer could treat one company
as two.

## The fix

Identity comes from the payload document's own `cik`, joined to the archive
`assets` table. The filename is a diagnostic. `issuer_identity.py` is the single
place that decides, and every payload-keyed reader now routes through it.

Callers keep their ticker keys, because the resolved ticker is what the CIK join
produces -- so a conforming filename behaves exactly as before and the twelve
anomalies now collapse onto the issuers they belong to. What changed is *how* that
key was decided.

A filename that disagrees with the payload's CIK does not create a second issuer.
A payload with no usable CIK resolves to an explicit unresolved state rather than
falling back to the filename, because a silent fallback is the same defect one
step later.

## What is not done

No registry mapping, scope, effective date, observation, interpretation or
migration is touched. No R&D conclusion is revisited. `sbc` is not opened. The
historical 2.75 / 2.83 / 2.84 artefacts are left exactly as they were, including
2.75's "75 filers", which is a record of what was measured then; the corrected
figure lives here.
"""

from __future__ import annotations

import collections
import io
import json
import os
import sys
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import issuer_identity  # noqa: E402
from core_registry import CoreRegistry  # noqa: E402
from registry_seed import seed  # noqa: E402
from semantic_gap_census_275 import load_collection  # noqa: E402
from sqlite_archive import SQLiteArchive  # noqa: E402

H = os.path.join(HERE, "experiments", "003-llm-evidence-retrieval", "harness")

# Every payload-keyed reader this fix touches. Listed so the audit reports the
# surface it changed rather than asserting the fix is complete.
UPDATED_READERS = {
    "candidate_discovery_repair_277.py": "held_payloads",
    "semantic_gap_census_275.py": "load_payloads",
    "r_and_d_object_audit_276.py": "held_payloads",
    "exploration_expense_semantic_validation_280.py": "held_payloads",
    "core_coverage_audit_241.py": "held_documents",
    "primary_capex_context_236.py": "held_documents",
    "capex_characterisation_234.py": "held_documents",
    "ifrs_capex_characterisation_235.py": "held_documents",
    "ifrs_capex_proposition_238.py": "held_documents",
    "debt_vocabulary_229.py": "payloads",
    "debt_composition_231.py": "payloads",
    "short_term_borrowings_230.py": "payloads",
    "debt_currency_unit_audit_252.py": "payloads",
    "historical_debt_unit_rederivation_254.py": "payloads",
    "historical_non_usd_unit_repair_262.py": "payload_units_for",
}

METRIC = "r_and_d"
ATTEMPTED = {"COLLECTED", "SOURCE_SILENT", "MAPPED_NO_CURRENT_OBSERVATION",
             "NOT_APPLICABLE", "DELIBERATELY_DECLINED"}


def main() -> Dict[str, Any]:
    store = SQLiteArchive(":memory:")
    registry = CoreRegistry(store.connection)
    seed(registry)
    store.connection.commit()

    cik_to_ticker = issuer_identity.cik_ticker_index(H)
    mapping, records = issuer_identity.load_harness_payloads(H, None,
                                                             cik_to_ticker)

    statuses = collections.Counter(r["identity_status"] for r in records)
    anomalies = [r for r in records
                 if r["identity_status"] != issuer_identity.CANONICAL_MATCH]

    # Every anomaly must resolve onto an issuer that already exists, which is the
    # whole claim: none of them introduces an issuer.
    asset_tickers = set(load_collection())
    for record in anomalies:
        record["resolves_to_an_existing_issuer"] = (
            record["resolved_ticker"] in asset_tickers)
        record["introduces_a_new_issuer"] = False
    anomalies_table = [
        {"issuer": r["resolved_ticker"],
         "payload_path": os.path.relpath(r["path"], HERE).replace("\\", "/"),
         "payload_cik": r["payload_cik"],
         "filename": r["filename"],
         "filename_derived_token": r["filename_derived_token"],
         "filename_cik_if_parseable": r["filename_cik_if_parseable"],
         "mismatch_type": r["identity_status"],
         "canonical_resolution": r["key"],
         "resolved_from": r["resolved_from"]}
        for r in sorted(anomalies, key=lambda r: (r["resolved_ticker"] or "",
                                                  r["filename"]))]

    # ---- cohort regression, against the canonical 2.75 loader ---------------
    assets = load_collection()
    statuses_by_asset: Dict[str, str] = {}
    for asset, body in assets.items():
        entry = (body["metrics"] or {}).get(METRIC) or {}
        statuses_by_asset[asset] = entry.get("status")
    attempted = [a for a, s in statuses_by_asset.items() if s in ATTEMPTED]
    collected = [a for a in attempted if statuses_by_asset[a] == "COLLECTED"]
    silent = [a for a in attempted if statuses_by_asset[a] == "SOURCE_SILENT"]
    not_yet = [a for a, s in statuses_by_asset.items()
               if s == "NOT_YET_COLLECTED"]

    cohort = {
        "total_assets": len(assets),
        "attempted": len(attempted),
        "collected": len(collected),
        "source_silent": len(silent),
        "not_yet_collected_excluded": len(not_yet),
        "matches_2_75": (len(assets), len(attempted), len(collected),
                         len(silent), len(not_yet)) == (99, 24, 8, 16, 75),
        "why_it_should_not_have_changed": (
            "the cohort is keyed on the coverage record, which identity "
            "normalisation does not touch. A change here would have meant the "
            "fix had reached into cohort semantics, which it must not."),
        "collected_members": sorted(collected),
        "source_silent_members": sorted(silent),
    }

    # ---- coverage records and payloads stay distinct ------------------------
    assets_without_payload = sorted(a for a in assets if a not in mapping)
    payloads_without_coverage = sorted(
        r["key"] for r in records
        if r["resolved_ticker"] and r["resolved_ticker"] not in asset_tickers)

    result = {
        "experiment": "2.85 canonicalise issuer identity from payload CIK",
        "production_change": True,
        "registry_changed": False,
        "mappings_added_or_promoted": 0,
        "scope_set": False,
        "effective_from_set": False,
        "migrated": False,
        "observations_changed": False,
        "interpretations_changed": False,
        "supersession_changed": False,
        "semantic_research_performed": False,
        "sbc_accessed": False,
        "historical_artefacts_edited": [],
        "identity_rule": (
            "payload.cik is the canonical issuer identity, joined to the "
            "archive assets table for the ticker. The filename is a transport "
            "diagnostic and never decides identity."),
        "readers_updated": UPDATED_READERS,
        "counts": {
            "payload_files": len(records),
            "unique_canonical_issuers": len(mapping),
            "filename_anomalies": len(anomalies),
            "identity_status_counts": dict(statuses),
            "filers_keyed_by_ticker": len(
                [k for k in mapping if not k.startswith(("CIK:", "UNRESOLVED:"))]),
            "filers_unresolved": len(
                [k for k in mapping if k.startswith("UNRESOLVED:")]),
        },
        "anomaly_table": anomalies_table,
        "anomalies_introduce_no_new_issuer": all(
            r["resolves_to_an_existing_issuer"] for r in anomalies),
        "cik_ticker_index_size": len(cik_to_ticker),
        "cohort_regression": cohort,
        "coverage_and_payloads_remain_distinct": {
            "coverage_records_without_a_payload": assets_without_payload,
            "coverage_records_without_a_payload_count": len(
                assets_without_payload),
            "payloads_without_a_coverage_record": payloads_without_coverage,
            "statement": (
                "an issuer with a coverage record and no payload is "
                "payload-unavailable, not a duplicate and not a new issuer; the "
                "two are counted separately and never merged"),
        },
        "semantic_state_untouched": {
            "r_and_d": "OPEN_MIXED_PRESENTATION, scope audited 16-filer cohort",
            "note": "no semantic classification was recomputed; identity "
                    "normalisation does not alter any semantic state",
        },
        "temporal": {
            "note": "no period is asserted; identity is not temporal",
            "fixed_dates_used": False,
        },
        "status": "IDENTITY_CANONICALISED",
    }
    out = os.path.join(H, "285-issuer-identity-canonicalisation.json")
    with io.open(out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, indent=2, sort_keys=True, default=str)
    store.close()
    return result


if __name__ == "__main__":
    r = main()
    print("status                  :", r["status"])
    counts = r["counts"]
    print("payload files           :", counts["payload_files"])
    print("unique canonical issuers:", counts["unique_canonical_issuers"])
    print("filename anomalies      :", counts["filename_anomalies"],
          counts["identity_status_counts"])
    print("resolved from cik join  :",
          counts["filers_keyed_by_ticker"],
          "| unresolved:", counts["filers_unresolved"])
    print("cik index size          :", r["cik_ticker_index_size"])
    print()
    cohort = r["cohort_regression"]
    print("cohort  assets %d attempted %d collected %d silent %d not_yet %d"
          % (cohort["total_assets"], cohort["attempted"], cohort["collected"],
             cohort["source_silent"], cohort["not_yet_collected_excluded"]))
    print("        matches 2.75    :", cohort["matches_2_75"])
    print()
    print("anomaly table (%d rows):" % len(r["anomaly_table"]))
    for row in r["anomaly_table"]:
        print("   %-8s cik=%-9s %-26s %s -> %s"
              % (row["issuer"], row["payload_cik"], row["filename"],
                 row["filename_derived_token"], row["canonical_resolution"]))
    print()
    print("anomalies introduce no new issuer:",
          r["anomalies_introduce_no_new_issuer"])
    distinct = r["coverage_and_payloads_remain_distinct"]
    print("coverage records without a payload:",
          distinct["coverage_records_without_a_payload_count"])
    print("payloads without a coverage record :",
          len(distinct["payloads_without_a_coverage_record"]))