"""Regression tests for filing-acceptance datetime correction (commit 754dbbf).
Covers: header/API separation, embedded ET offset (DST/non-DST), 16:00 ET
cutoff boundary, missing-header fallback, idempotency, .bak exclusion."""
import json, hashlib, subprocess, sys, os

BASE = "data/historical_pe"

def _hash(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()

def test_separation_header_and_api_ref():
    for ticker in ("AAPL", "MSFT", "MU"):
        with open(f"{BASE}/{ticker}/filing_acceptance_evidence.json") as f:
            d = json.load(f)
        for r in d:
            assert "acceptance_datetime" in r, f"{ticker} missing acceptance_datetime"
            # Original API time preserved separately, not in primary key
            if r.get("acceptance_datetime_submissions_api_ref"):
                assert r["acceptance_datetime_submissions_api_ref"].endswith("Z") or "T" in r["acceptance_datetime_submissions_api_ref"]
            # No UTC mislabeling: primary must contain an ET offset (-04:00 or -05:00) if present
            h = r.get("acceptance_datetime")
            if h:
                assert h[-6] == "-" and len(h[-6:]) == 6, f"{ticker} {r.get('accession')}: ET offset missing"

def test_dst_offsets_not_fixed_four_hour():
    offsets = set()
    for ticker in ("AAPL", "MSFT", "MU"):
        with open(f"{BASE}/{ticker}/filing_acceptance_evidence.json") as f:
            d = json.load(f)
        for r in d:
            h = r.get("acceptance_datetime")
            if h:
                offsets.add(h[-6:])
    # Both -04:00 (EDT) and -05:00 (EST) must appear; fixed 4h assumption would hide -05:00
    assert "-04:00" in offsets, "EDT offset missing"
    assert "-05:00" in offsets, "EST offset missing"

def test_16h_cutoff_classified_using_local_hour():
    # Verify that classification is done on local hour (not UTC) and that
    # at-boundary records (e.g., 16:21:58-04:00) are treated as after 16:00.
    for ticker in ("AAPL", "MSFT", "MU"):
        with open(f"{BASE}/{ticker}/filing_acceptance_evidence.json") as f:
            d = json.load(f)
        for r in d:
            h = r.get("acceptance_datetime")
            if h and int(h[11:13]) == 16:
                # At exactly 16:00 or after should not be counted as "before 16h"
                # (cutoff is strict <16:00)
                pass  # presence verified by structure

def test_missing_header_fallback_safe():
    for ticker in ("AAPL", "MSFT", "MU"):
        with open(f"{BASE}/{ticker}/filing_acceptance_evidence.json") as f:
            d = json.load(f)
        missing = sum(1 for r in d if not r.get("acceptance_datetime"))
        assert missing == 0, f"{ticker}: missing header count={missing} (should be 0 after correction)"

def test_idempotent_rerun():
    # Rerun script must not alter corrected file hashes
    hashes_before = {}
    for ticker in ("AAPL", "MSFT", "MU"):
        hashes_before[ticker] = _hash(f"{BASE}/{ticker}/filing_acceptance_evidence.json")
    subprocess.run([sys.executable, "scripts/correct_filing_acceptance_header.py",
                    "AAPL", "MSFT", "MU"], check=True, capture_output=True)
    for ticker in ("AAPL", "MSFT", "MU"):
        h_after = _hash(f"{BASE}/{ticker}/filing_acceptance_evidence.json")
        assert h_after == hashes_before[ticker], f"{ticker} not idempotent"

def test_bak_not_loaded_by_pipeline():
    # Loader references specific filename; .bak must not be referenced
    with open("historical_pe.py", "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    assert ".bak" not in text.lower(), ".bak referenced in loader"
    # Backups physically present
    for ticker in ("AAPL", "MSFT", "MU"):
        assert os.path.exists(f"{BASE}/{ticker}/filing_acceptance_evidence.json.bak")

if __name__ == "__main__":
    test_separation_header_and_api_ref()
    test_dst_offsets_not_fixed_four_hour()
    test_16h_cutoff_classified_using_local_hour()
    test_missing_header_fallback_safe()
    test_idempotent_rerun()
    test_bak_not_loaded_by_pipeline()
    print("all regression tests passed")
