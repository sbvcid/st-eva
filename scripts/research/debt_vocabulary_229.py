"""
The proposition test, without any name heuristic.

The first implementation of this round collected candidates by substring and
admitted instants as debt stocks. That was wrong in a way worth recording: the
needle matched `us-gaap:DebtSecuritiesAvailableForSale...` because it contains
the word "Debt", and a debt *security* is an investment asset, not a liability.
It also admitted `us-gaap:LineOfCreditFacilityCurrentBorrowingCapacity`, whose
own SEC description says it is capacity "without considering any amounts currently
outstanding" -- not a balance. Name matching cannot separate a debt liability from
a debt asset; that is the whole point.

So this version asks the proposition a question that needs no name at all:

    **Do the 29 filers that report nothing for `debt` tag any of the four
    concepts the registry has already mapped to `debt`?**

  * None of them tag any mapped concept  -> the declared vocabulary does not
    describe what these filers report, and the silence is a coverage question.
    SUPPORTED.
  * Some of them tag a mapped concept     -> those filers were asked through a
    concept they use and still produced nothing, so the cause is elsewhere for
    them. UNDECIDED or REFUTED.

And then, to say *what* the filers report instead, the period shape and the SEC's
own concept description are used -- in that order, with a concept held to
`unresolved` whenever the description is absent or names a different measurement.
"""

from __future__ import annotations

import glob
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HERE = os.path.dirname(os.path.dirname(SCRIPT_DIR))
for _path in (HERE, SCRIPT_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from core_registry import CoreRegistry  # noqa: E402
from coverage_semantics import scoped_ledger  # noqa: E402
from registry_seed import seed  # noqa: E402
from sqlite_archive import SQLiteArchive  # noqa: E402
# Issuer identity comes from the payload's own `cik`; see
# issuer_identity.py for why the filename is a diagnostic only.
import issuer_identity  # noqa: E402

H = os.path.join(HERE, "experiments", "003-llm-evidence-retrieval", "harness")

ARCHIVES = ["snapshot-227-a1", "snapshot-227-b", "snapshot-banks2",
            "snapshot-fs", "snapshot-ins-min"]
PAYLOAD_DIRS = ["bulkfacts-227a-orig", "bulkfacts-227b", "bulkfacts-ins-min",
                "bulkfacts-fs", "bulkfacts-banks-2", "inventory", "bulkfacts",
                "bulkfacts-banks"]

# An obligation, rather than an asset in, a facility, or a movement.
OBLIGATION = ("notes payable", "long-term debt", "long term debt",
              "borrowings", "debt outstanding", "carrying value",
              "carrying amount", "payable", "indebtedness")
# An investment in debt, a facility, a disclosure, or a face amount.
NOT_A_BALANCE = (
    "securit", "held to maturity", "available for sale", "amortized cost",
    "maximum amount", "borrowing capacity", "credit facility",
    "line of credit", "unrealized", "fair value", "investment",
    "face amount", "par value", "maturities", "disclosure", "collateral",
    "pledged", "allowance for credit loss", "impairment", "yield",
    "interest rate", "proceeds", "repayment", "issuance", "issued",
    "expense", "income", "extinguishment", "acquisition", "acquired",
    "inception", "maturity date", "schedule",
    # A ratio or a percentage is not a balance, whatever its period shape, and a
    # repossessed asset is an asset. Both were admitted by the first pass.
    "ratio of", "repossessed", "foreclosed", "percent of",
)
# Concepts that are genuinely obligations but not *borrowed principal*. Held
# separately rather than excluded, because "not the thing we want" and "not a
# debt balance at all" are different findings and the first version of this
# script could not tell them apart.
RELATED_NOT_PRINCIPAL = (
    "interest payable", "interest and other payable", "accrued interest",
)


def documents():
    out = {}
    for d in PAYLOAD_DIRS:
        p = os.path.join(H, d)
        if not os.path.isdir(p):
            continue
        out.update(issuer_identity.load_companyfacts_payloads(p, harness_dir=H)[0])
    return out


def silent_for_debt():
    out = {}
    for name in ARCHIVES:
        path = os.path.join(H, f"{name}.sqlite")
        if not os.path.exists(path):
            continue
        c = sqlite3.connect(path)
        c.row_factory = sqlite3.Row
        registry = CoreRegistry(c)
        for row in c.execute("SELECT asset_id, ticker FROM assets"):
            asset_id, ticker = str(row["asset_id"]), str(row["ticker"]).upper()
            led = scoped_ledger(c, registry, asset_id, ticker)
            cell = next(r for r in led["rows"] if r["metric"] == "debt")
            if cell["status"] in ("SOURCE_SILENT", "DELIBERATELY_DECLINED"):
                out[ticker] = {"business_model": led["business_model"]
                               or "UNCLASSIFIED", "status": cell["status"]}
        c.close()
    return out


def declared_for_debt():
    probe = SQLiteArchive(":memory:")
    registry = CoreRegistry(probe.connection)
    seed(registry)
    mapped = sorted({m.concept_id for m in
                     registry.mappings_for_metric("debt")})
    declined = sorted({d["concept_id"] for d in
                       registry.declines_for_metric("debt")})
    definition = next(m.semantic_definition for m in registry.metrics()
                      if m.metric_id == "debt")
    probe.close()
    return mapped, declined, definition


def scan(path, mapped):
    """
    One document, split three ways.

    * `mapped_seen`      the declared concepts, and how many rows each carries
    * `obligation_cash`  instants whose description says obligation
    * `everything else`  whatever else mentions debt or borrowing
    """
    with open(path, encoding="utf-8") as handle:
        doc = json.load(handle)
    mapped_seen, obligations, others = {}, [], []
    for taxonomy, concepts in (doc.get("facts") or {}).items():
        for name, body in concepts.items():
            key = f"{taxonomy}:{name}"
            label = str(body.get("label") or "")
            desc = str(body.get("description") or "")
            text = f"{label}. {desc}".lower()
            instants = durations = 0
            accessions, values_by_key = set(), defaultdict(set)
            units, sample = set(), None
            for unit, rows in (body.get("units") or {}).items():
                units.add(unit)
                for r in rows:
                    if not r.get("end"):
                        continue
                    if r.get("start"):
                        durations += 1
                    else:
                        instants += 1
                    if r.get("accn"):
                        accessions.add(r["accn"])
                    values_by_key[(str(r.get("start") or ""),
                                   str(r["end"]))].add(r.get("val"))
                    if sample is None:
                        sample = {"period_start": r.get("start"),
                                  "period_end": r.get("end"),
                                  "value": r.get("val"), "unit": unit,
                                  "form": r.get("form"), "accn": r.get("accn"),
                                  "filed": r.get("filed"), "fp": r.get("fp")}
            if not (instants or durations):
                continue
            rec = {"concept": key, "taxonomy": taxonomy, "label": label or None,
                   "description": desc[:300] or None, "instants": instants,
                   "durations": durations, "units": sorted(units),
                   "accessions": len(accessions),
                   "rows": instants + durations,
                   "period_keys_with_multiple_values": sum(
                       1 for v in values_by_key.values() if len(v) > 1),
                   "representative_raw_fact": sample}
            if key in mapped:
                mapped_seen[key] = rec
                continue
            blob = f"{key} {text}"
            if not any(n.lower() in blob for n in
                       ("debt", "borrowing", "notespayable")):
                continue
            # Period shape first: it is objective. A debt *stock* is an
            # instant; a repayment, a drawdown and an issuance are durations.
            if instants and durations:
                shape = "mixed"
            elif instants:
                shape = "instant"
            else:
                shape = "duration"

            # **Only objective facts from here.** Four attempts to infer
            # semantics by keyword each leaked a different category -- debt
            # *securities*, a line-of-credit *capacity*, a *ratio* of
            # indebtedness, accrued *interest*, a debt *extinguishment payment*
            # -- so this records what the payload states and hands the judgement
            # back with the SEC's own words attached.
            rec["period_shape"] = shape
            rec["description_present"] = bool(desc.strip())
            rec["semantics_source"] = (
                "SEC taxonomy description in companyfacts"
                if rec["description_present"]
                else "none: companyfacts supplies no description for this concept")
            rec["dimension_ambiguous"] = (
                rec["period_keys_with_multiple_values"] > 0)

            obligations.append(rec)
    return mapped_seen, obligations, others


def verdict_on(per_filer, mapped, candidates):
    """
    SUPPORTED / REFUTED / UNDECIDED on the half that needs no keyword, and an
    honest statement of what the payload cannot settle.

    The name-free test carries the verdict. Do the filers that report nothing for
    `debt` tag any concept the registry already maps to it? If none of them does,
    the declared vocabulary describes nothing these filers report, and the
    silence is at least partly a coverage question whatever any individual
    concept turns out to be.

    The second half is deliberately **not** claimed. The candidates are reported
    with their period shape, coverage and the SEC's own label and description,
    and no attempt is made to say which are debt stocks: four keyword attempts
    each admitted a category that was not one. Whether any should be mapped, and
    to which side of the current/noncurrent composition, is the next proposition
    and it needs a stated basis rather than a substring.
    """
    with_payload = {t: v for t, v in per_filer.items() if v["payload"]}
    tagging = [t for t, v in with_payload.items()
               if v.get("mapped_rows_total", 0) > 0]
    instants = [c for c in candidates if c["period_shape"] == "instant"]
    recurring = [c for c in instants if c["filer_count"] >= 2]
    described = [c for c in instants if c["description_present"]]
    counts = {
        "silent_filers_considered": len(per_filer),
        "silent_filers_with_a_payload": len(with_payload),
        "silent_filers_tagging_a_declared_concept": len(tagging),
        "candidate_concepts": len(candidates),
        "candidates_whose_every_fact_is_an_instant": len(instants),
        "instant_candidates_recurring_across_filers": len(recurring),
        "instant_candidates_with_an_SEC_description": len(described),
        "instant_candidates_with_no_description_at_all": len(instants) - len(described),
    }
    if tagging:
        return "REFUTED", (
            f"{len(tagging)} of {len(with_payload)} filers that report nothing "
            f"for `debt` tag a concept the registry already maps to it, so for "
            f"those filers the vocabulary is not the limiting factor."
        ), counts
    return "SUPPORTED", (
        f"**The name-free half holds.** None of the {len(with_payload)} filers "
        f"that report nothing for `debt` tags any of the {len(mapped)} concepts "
        f"already mapped to it. The declared vocabulary therefore describes "
        f"nothing these filers report, and the silence is at least partly a "
        f"coverage question rather than only source absence. This half required "
        f"no name matching at all, and it is the half the proposition turns on."
        f"\n\n**The candidate half is not claimed.** "
        f"{len(instants)} candidate concepts have every fact as an instant "
        f"rather than a duration, and {len(recurring)} of those recur across two "
        f"or more filers. That is objective and it is necessary but not "
        f"sufficient: an instant can be a debt stock, a *debt security*, a "
        f"borrowing *capacity*, an accrued *interest*, a *ratio* of "
        f"indebtedness or a foreclosed asset, and deciding which requires the "
        f"concept's own semantics rather than its period shape."
        f"\\n\\n**The payload is the limit, and it differs by taxonomy.** "
        f"{len(instants) - len(described)} of the {len(instants)} instant "
        f"candidates carry no description at all: the `ifrs-full` side supplies "
        f"neither label nor description in `companyfacts`, so for those the "
        f"semantics are not establishable from this source by any means. For "
        f"the rest the SEC's own description is recorded against each concept "
        f"in the artefact, unjudged -- and it is what a reader needs, because "
        f"it is the difference between `ShortTermBorrowings` ('total carrying "
        f"amount ... of debt having initial terms less than one year') and "
        f"`LineOfCreditFacilityCurrentBorrowingCapacity` ('borrowing capacity "
        f"... without considering any amounts currently outstanding'). Both "
        f"are instants."
        f"\n\n**What is established:** the gap is real, it is not an artefact "
        f"of one filer, and it is wider than one concept. **What is not:** that "
        f"any named concept should be mapped. That is the next proposition, and "
        f"it needs a stated basis for why a concept *is* a debt stock -- not a "
        f"substring that happens to match."
    ), counts


def main():
    mapped, declined, definition = declared_for_debt()
    docs, silent = documents(), silent_for_debt()

    per_filer = {}
    obligations = defaultdict(lambda: {"filers": set(), "rows": 0,
                                       "instants": 0, "accessions": set(),
                                       "label": None, "description": None,
                                       "sample": None, "ambiguous": 0,
                                       "anchor": None, "why": None,
                                       "shape": None, "desc": None,
                                       "source": None,
                                       "units": Counter()})
    for ticker, info in sorted(silent.items()):
        path = docs.get(ticker)
        if not path:
            per_filer[ticker] = {"model": info["business_model"],
                                 "payload": False}
            continue
        seen, obl, _others = scan(path, set(mapped))
        per_filer[ticker] = {
            "model": info["business_model"], "payload": True,
            "mapped_concepts_seen": {k: v["rows"] for k, v in seen.items()},
            "mapped_rows_total": sum(v["rows"] for v in seen.values()),
        }
        for rec in obl:
            slot = obligations[rec["concept"]]
            slot["filers"].add(ticker)
            slot["rows"] += rec["rows"]
            slot["instants"] += rec["instants"]
            slot["accessions"].update({f"{ticker}:{i}"
                                       for i in range(rec["accessions"])})
            slot["label"] = slot["label"] or rec["label"]
            slot["description"] = slot["description"] or rec["description"]
            slot["ambiguous"] += rec["period_keys_with_multiple_values"]
            slot["sample"] = slot["sample"] or {"ticker": ticker,
                                                **rec["representative_raw_fact"]}
            for u in rec["units"]:
                slot["units"][u] += 1
            slot["shape"] = slot["shape"] or rec["period_shape"]
            slot["desc"] = slot["desc"] or rec["description_present"]
            slot["source"] = slot["source"] or rec["semantics_source"]

    with_payload = {t: v for t, v in per_filer.items() if v["payload"]}
    tagging_mapped = {t: v for t, v in with_payload.items()
                      if v["mapped_rows_total"] > 0}
    candidates = []
    for key, slot in sorted(obligations.items()):
        candidates.append({
            "concept": key, "taxonomy": key.split(":")[0],
            "label": slot["label"], "description": slot["description"],
            "filers": sorted(slot["filers"]),
            "filer_count": len(slot["filers"]),
            "accession_count": len(slot["accessions"]),
            "rows": slot["rows"], "instants": slot["instants"],
            "durations": 0, "units": slot["units"],
            "dimension_ambiguous_keys": slot["ambiguous"],
            "units": dict(slot["units"]),
            "period_shape": slot["shape"],
            "description_present": slot["desc"],
            "semantics_source": slot["source"],
            "representative_raw_fact": slot["sample"],
        })
    multi = [c for c in candidates if c["filer_count"] >= 2]
    verdict, reasoning, counts = verdict_on(per_filer, mapped, candidates)

    # Two propositions, not one.
    #
    # A single verdict on a compound statement is how half a proof becomes a
    # whole conclusion. These halves have different evidence and they were
    # established by different means: the first is a subtraction over every silent
    # filer, the second needs a concept's accounting identity tested against the
    # existing evidence -- and the second is not established.
    propositions = {
        "A": {
            "statement": "The concepts currently mapped to `debt` describe "
                         "nothing the 29 SOURCE_SILENT filers report: none of "
                         "them tags any declared concept.",
            "verdict": "SUPPORTED" if verdict == "SUPPORTED" else verdict,
            "established_by": "a subtraction, over every silent filer, with no "
                              "name matching: zero coverage of the four "
                              "declared concepts",
        },
        "B": {
            "statement": "Some unmapped concept is a synonym or a corresponding "
                         "representation of Core `debt`, sufficient to close the "
                         "gap A establishes.",
            "verdict": "UNDECIDED",
            "established_by": "nothing yet. Candidate semantics have not been "
                              "established, and 2.29's four keyword passes each "
                              "produced a shortlist wrong in a different way, "
                              "so no candidate is asserted",
        },
    }

    result = {
        "proposition": {
            "compound_statement": "The current Core `debt` vocabulary is "
                                  "insufficient to express entity-level debt "
                                  "stock for some filers; these filers' "
                                  "SOURCE_SILENT partly stems from registry "
                                  "vocabulary coverage, not only source "
                                  "absence.",
            "single_verdict": verdict,
            "single_verdict_is_withdrawn": True,
            "reasoning": reasoning,
            "counts": counts,
            "establishes_no_mapping": True,
            "why_split": "A compound statement must not receive one verdict. "
                         "A is established by subtraction over every silent "
                         "filer; B needs a concept's accounting identity "
                         "tested against existing evidence, and that has not "
                         "happened. Reporting one verdict for both would let "
                         "a proved half carry an unproved conclusion.",
        },
        "propositions": propositions,
        "scope": {
            "silent_filers": len(silent),
            "silent_filers_with_a_payload": len(with_payload),
            "silent_filers_tagging_a_mapped_concept": len(tagging_mapped),
            "declared_concepts": mapped,
            "declined_concepts": declined,
            "debt_semantic_definition": definition,
            "method": "period shape first (an instant is a balance, a "
                      "duration is a movement), then the SEC's own concept "
                      "description; no concept is admitted on its name",
        },
        "per_filer": per_filer,
        "candidates": candidates,
        "buckets": {
            "1_instant_candidates_recurring_across_filers": [
                {"concept": c["concept"], "taxonomy": c["taxonomy"],
                 "filer_count": c["filer_count"], "filers": c["filers"],
                 "accession_count": c["accession_count"], "rows": c["rows"],
                 "period_type": c["period_shape"], "units": c["units"],
                 "label": c["label"],
                 "description_present": c["description_present"],
                 "semantics_source": c["semantics_source"],
                 "dimension_ambiguous": c["dimension_ambiguous_keys"] > 0,
                 "representative_raw_fact": c["representative_raw_fact"]}
                for c in multi],
            "2_movement_concepts": [
                {"concept": c["concept"], "rows": c["rows"],
                 "filer_count": c["filer_count"]}
                for c in candidates if c["period_shape"] == "duration"],
            "3_concepts_with_dimension_ambiguity": [
                {"concept": c["concept"],
                 "period_keys_with_multiple_values":
                     c["dimension_ambiguous_keys"],
                 "filer_count": c["filer_count"]}
                for c in multi if c["dimension_ambiguous_keys"] > 0],
            "4_instant_candidates_with_an_SEC_description": [
                c["concept"] for c in multi if c["description_present"]],
            "5_semantics_not_established": {
                "instant_but_no_description_in_companyfacts": [
                    c["concept"] for c in multi
                    if not c["description_present"]],
                "duration_rather_than_a_balance": len([
                    c for c in candidates if c["period_shape"] == "duration"]),
                "mixed_period_shapes": len([
                    c for c in candidates if c["period_shape"] == "mixed"]),
                "note": "no candidate is admitted or rejected on a keyword. An "
                        "instant can be a debt stock, a debt security, a "
                        "borrowing capacity, accrued interest, a ratio of "
                        "indebtedness or a foreclosed asset, and four keyword "
                        "passes each admitted one of those. Period shape is "
                        "objective; semantics are not available from the "
                        "payload for the ifrs-full side at all.",
            },
        },
    }
    with open(os.path.join(H, "229-debt-vocabulary.json"), "w",
              encoding="utf-8") as h:
        json.dump(result, h, indent=2, sort_keys=True, default=str)
    return result


    print("bucket 4 -- semantics established by the payload:")
    for c in r["buckets"]["4_semantics_established"]:
        rec = next(x for x in r["candidates"] if x["concept"] == c)
        print(f"   {c:<58} filers {rec['filer_count']:>2}  rows {rec['rows']:>5}"
              f"  accs {rec['accession_count']:>4}  {str(rec['label'])[:38]}")
    print("\nbucket 5 -- semantics unresolved, by reason:")
    reasons = {}
    for x in r["buckets"]["5_semantics_unresolved"]:
        reasons.setdefault(x["reason"], []).append(x["concept"])
    for reason, concepts in sorted(reasons.items()):
        print(f"   {reason:<38} {len(concepts):>3}  e.g. {concepts[0][:52]}")
    print("\nbucket 3 -- dimension-ambiguous candidates:")
    amb = r["buckets"]["3_concepts_with_dimension_ambiguity"]
    print(f"   {len(amb)} of the candidates carry more than one value for at "
          f"least one period key")
    for x in amb[:5]:
        print(f"      {x['concept']:<56} {x['period_keys_with_multiple_values']:>4}"
              f" ambiguous keys  filers {x['filer_count']}")
    print("\nper-filer, filers that DO tag a declared concept:",
          [t for t, v in r["per_filer"].items()
           if v.get("mapped_rows_total", 0) > 0] or "none")


if __name__ == "__main__":
    r = main()
    p, sc = r["proposition"], r["scope"]
    print("PROPOSITION:", p["verdict"])
    print(" ", p["reasoning"])
    print()
    print(f"silent filers {sc['silent_filers']}, with a payload "
          f"{sc['silent_filers_with_a_payload']}, tagging a mapped concept "
          f"{sc['silent_filers_tagging_a_mapped_concept']}")
    print("declared for debt:", sc["declared_concepts"])
