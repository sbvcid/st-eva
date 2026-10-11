"""POC fetch stage: capture raw inputs for the AAPL Historical P/E proof of concept.

Scratch only. Nothing here is production code and nothing is written outside
this directory. The point of this stage is to freeze raw bytes on disk so the
computation stage can be replayed without re-hitting the network.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"

CIK = "0000320193"
TICKER = "AAPL"
USER_AGENT = "ST-EVA Historical P/E POC (research; st-eva@example.com)"

SUBMISSIONS_URL = (
    f"https://data.sec.gov/submissions/CIK{CIK}.json"
)
CONCEPT_URL = (
    "https://data.sec.gov/api/xbrl/companyconcept/"
    f"CIK{CIK}/us-gaap/EarningsPerShareDiluted.json"
)
CHART_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/"
    f"{TICKER}?period1=1546300800&period2=1750000000&interval=1d"
    "&events=div%2Csplit"
)

SOURCES = {
    "submissions": SUBMISSIONS_URL,
    "eps_diluted_concept": CONCEPT_URL,
    "daily_prices": CHART_URL,
}


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, url in SOURCES.items():
        target = RAW / f"{name}.json"
        if not target.exists():
            payload = fetch(url)
            target.write_bytes(payload)
            time.sleep(0.5)
        else:
            payload = target.read_bytes()
        manifest[name] = {
            "url": url,
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        print(f"{name}: {len(payload)} bytes")
    (RAW / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
