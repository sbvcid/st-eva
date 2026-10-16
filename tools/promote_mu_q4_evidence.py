"""Promote the MU Q4 evidence study output to the canonical production dataset.

Reads research/experiments/mu-historical-pe-q4-study/out/mu_q4_evidence_records.json,
keeps only records that pass the production loader's evidence gate
(source_type='SEC_8K_ITEM_2_02_EX_99_1' and meets_st_eva_q4_evidence=true), and
writes data/historical_pe/MU/q4_evidence_records.json in the same canonical
record shape the MSFT production dataset uses (the loader reads
'document_identifier' into evidence source_document; do not rename it).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1] if HERE.name != "tools" else HERE.parent
STUDY_OUT = REPO / "research" / "experiments" / "mu-historical-pe-q4-study" / "out"
CANONICAL = REPO / "data" / "historical_pe" / "MU" / "q4_evidence_records.json"

SOURCE_TYPE = "SEC_8K_ITEM_2_02_EX_99_1"

# Study-record field -> canonical-record field. The study names the PIT date
# 'pit_usable_date'; the canonical MSFT shape names it 'usable_date'.
FIELD_SOURCES = {
    "usable_date": "pit_usable_date",
}

# Canonical record fields, in the MSFT production dataset's shape.
RECORD_FIELDS = (
    "accession",
    "form",
    "sec_item",
    "quarter_period_end",
    "acceptance_datetime",
    "diluted_eps",
    "fiscal_year",
    "fiscal_quarter",
    "source_type",
    "source_url",
    "stated_directly",
    "audit_status",
    "evidence_class",
    "currency",
    "meets_st_eva_q4_evidence",
    "usable_date",
    "content_sha256",
    "extraction_method",
    "document_identifier",
)


def main() -> None:
    study = json.loads((STUDY_OUT / "mu_q4_evidence_records.json").read_text(encoding="utf-8"))
    accepted = [
        r
        for r in study["records"]
        if r.get("source_type") == SOURCE_TYPE and r.get("meets_st_eva_q4_evidence")
    ]
    canonical_records = [
        {
            field: rec[FIELD_SOURCES.get(field, field)]
            for field in RECORD_FIELDS
        }
        for rec in accepted
    ]
    payload = {
        "records": canonical_records,
        "metadata": {
            "issuer": "MU",
            "cik": study["cik"],
            "source": "MU fiscal Q4 evidence study (promoted to canonical production layout)",
            "source_file": "research/experiments/mu-historical-pe-q4-study/out/mu_q4_evidence_records.json",
            "canonical_role": "production",
            "study_content_hash": study["content_hash"],
            "total_q4_records": len(canonical_records),
            "evidence_class": "furnished",
            "form_type": "8-K",
            "sec_item": "Item 2.02",
            "schema_notes": (
                "Records carry 'document_identifier'; the production loader reads "
                "this field into evidence source_document. Do not rename it to "
                "'source_document'. This canonical file contains only the records "
                "that pass the loader evidence gate (source_type="
                "'SEC_8K_ITEM_2_02_EX_99_1' and meets_st_eva_q4_evidence=true); the "
                "full-provenance study records, including comparative cross-checks "
                "and the quoted-but-excluded non-GAAP figures, remain in the source "
                "study file named by 'source_file'."
            ),
        },
    }
    CANONICAL.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"promoted {len(canonical_records)} records to {CANONICAL} "
        f"(study content_hash {study['content_hash'][:16]})"
    )


if __name__ == "__main__":
    sys.exit(main())
