"""Generate the committed MSFT Historical P/E regression fixture.

Values are taken from the verified POC oracle (the contract-validation output),
NOT from a production run, so the fixture is an independent expectation.
Run once; the output is committed and the tests consume it.
"""
import json, pathlib, hashlib

ROOT = pathlib.Path(r"C:\git\st-eva")
POC = ROOT / "research/experiments/aapl-historical-pe-poc/contract/msft_validation/out/msft_pe_points.json"
OUT = ROOT / "tests/fixtures/msft_historical_pe_expected.json"

poc = json.loads(POC.read_text(encoding="utf-8"))
poc_by_date = {o["evaluation_date"]: o for o in poc["observations"]}


def ttm_pe(o):
    t = o.get("TTM_GAAP_DILUTED_PE") or {}
    return t.get("value")


def ttm_status(o):
    t = o.get("TTM_GAAP_DILUTED_PE") or {}
    return t.get("status")


def components(o):
    t = o.get("TTM_GAAP_DILUTED_PE") or {}
    out = []
    for c in t.get("components", []):
        if c.get("accession") is None:      # drop the POC's synthetic composite row
            continue
        out.append({
            "accession": c.get("accession"),
            "form": c.get("form"),
            "evidence_class": c.get("evidence_class"),
            "source_document": c.get("source_document"),
            "content_sha256": c.get("content_sha256"),
        })
    return sorted(out, key=lambda x: (x["evidence_class"], x["accession"]))


obs = []
for d in sorted(poc_by_date):
    o = poc_by_date[d]
    obs.append({
        "evaluation_date": d,
        "status": ttm_status(o),
        "pe": ttm_pe(o),
        "price_close_as_traded": o.get("price_close_as_traded"),
        "components": components(o),
    })

vals = sorted(x["pe"] for x in obs if x["pe"] is not None)
n = len(vals)
mean = sum(vals) / n
var = sum((v - mean) ** 2 for v in vals) / (n - 1)

fixture = {
    "fixture_version": 1,
    "issuer": "MSFT",
    "issuer_id": "CIK0000789019",
    "derived_from": {
        "artifact": "MSFT contract-validation POC output",
        "path": "research/experiments/aapl-historical-pe-poc/contract/msft_validation/out/msft_pe_points.json",
        "logic_version": poc.get("logic_version"),
        "content_sha256": hashlib.sha256(POC.read_bytes()).hexdigest(),
        "note": (
            "Expected values below are transcribed from the verified POC oracle, "
            "not from a production run, so this file is an independent expectation. "
            "The POC itself is git-ignored and is NOT required at test runtime."
        ),
    },
    "tolerance": {
        "pe_abs": 1e-4,
        "distribution_abs": 1e-4,
        "note": "Production rounds prices to 4dp, so P/E differs from POC by ~1e-6.",
    },
    "expected": {
        "evaluation_date_count": len(obs),
        "available_count": n,
        "status": "USABLE_FOR_REFERENCE",
        "distribution": {
            "mean": mean,
            "std": var ** 0.5,
            "min": vals[0],
            "max": vals[-1],
        },
    },
    "observations": obs,
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(fixture, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
print(f"wrote {OUT.relative_to(ROOT)}")
print(f"  evaluation_dates={len(obs)} available={n}")
print(f"  mean={mean:.6f} std={var**0.5:.6f} min={vals[0]:.6f} max={vals[-1]:.6f}")
print(f"  POC sha256={hashlib.sha256(POC.read_bytes()).hexdigest()[:32]}...")