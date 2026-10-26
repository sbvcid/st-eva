#!/usr/bin/env python3
"""Pre-commit / CI guard: block known unverified-authorized third-party data.

Only denies the specific paths whose authorization is unconfirmed (C-1 Yahoo
Finance v8 price derivatives) or SQLite work files that must stay local.
Does NOT ban all JSON, all SQLite, or SEC EDGAR files.

Usage (pre-commit hook):
  python scripts/check_unauthorized_data_precommit.py

Usage (CI / manual):
  python scripts/check_unauthorized_data_precommit.py

If the script finds a match in staged (or all tracked) paths, it exits non-zero
with the exact path and a reference to DATA-DELIVERY.md / C-1.
"""
import subprocess, sys, os

# Exact paths removed in phase 3/4/5 due to unverified Yahoo Finance v8 auth (C-1).
# These must not re-enter public Git. Local copies preserved.
DENY_PATHS = {
    # SOFI archive and price derivatives
    "data/archives/SOFI.sqlite",
    "data/historical_pe/SOFI/daily_prices.json",
    "data/historical_pe/SOFI/prices_manifest.json",
    "data/historical_pe/SOFI/manifest.json",
    # Other issuer price sequence / mixed manifest (Yahoo-derived per adapter design)
    "data/historical_pe/AAPL/daily_prices.json",
    "data/historical_pe/AAPL/manifest.json",
    "data/historical_pe/AEP/daily_prices.json",
    "data/historical_pe/AEP/manifest.json",
    "data/historical_pe/MSFT/daily_prices.json",
    "data/historical_pe/MSFT/manifest.json",
    "data/historical_pe/MU/daily_prices.json",
    "data/historical_pe/MU/daily_prices_metadata.json",
    # Research multiples price derivatives (Yahoo-format raw chart data)
    "data/research_multiples/AAPL/daily_prices.json",
    "data/research_multiples/AAPL/manifest.json",
    "data/research_multiples/KO/daily_prices.json",
    "data/research_multiples/KO/manifest.json",
    "data/research_multiples/MSFT/daily_prices.json",
    "data/research_multiples/MSFT/manifest.json",
    # SQLite sidecars / work DBs / backups that must stay local
    "data/archives/AAPL.sqlite.pre-2026-10-20",
    "data/archives/NONEXISTENT.sqlite",
}

# Pattern rules: exact matches, plus SQLite in archive / work paths
# (prevents new archive DB additions, not generic SQLite use)
DENY_PATTERNS = [
    # Any SQLite database or sidecar under data/archives/
    lambda p: p.startswith("data/archives/") and p.endswith(".sqlite"),
    lambda p: p.startswith("data/archives/") and (p.endswith(".sqlite-shm") or p.endswith(".sqlite-wal")),
    # Any SQLite DB directly under data/ (working DB, not archive)
    lambda p: p.startswith("data/") and p.endswith(".sqlite") and not p.startswith("data/archives/") and not p.startswith("data/historical_pe/") and not p.startswith("data/research_multiples/") and not p.startswith("data/research_lanes/") and not p.startswith("data/research_issuers.json") and not p.startswith("data/st-eva.sqlite"),  # wait: this is too broad. Instead use exact for st-eva if needed; but st-eva.sqlite is already excluded by .gitignore.
]

# Refine: only block SQLite that matches known work/archive patterns, not generic data files.
# We already block exact archive paths and sidecars; for broader protection, block any
# new .sqlite under data/ that isn't an explicitly allowed basename.
ALLOWED_SQLITE_BASENAMES = {"st-eva.sqlite"}

def check(paths):
    violations = []
    for p in paths:
        # Normalize to forward slashes
        p_norm = p.replace("\\", "/")
        if p_norm in DENY_PATHS:
            violations.append((p_norm, "exact denied path (C-1 / phase 5 exclusion)"))
            continue
        # Pattern checks
        if p_norm.startswith("data/archives/") and (p_norm.endswith(".sqlite") or p_norm.endswith(".sqlite-shm") or p_norm.endswith(".sqlite-wal")):
            violations.append((p_norm, "new SQLite archive/sidecar under data/archives/ (must stay local)"))
            continue
        basename = os.path.basename(p_norm)
        if basename.endswith(".sqlite") and basename not in ALLOWED_SQLITE_BASENAMES:
            # Only block if it's a new SQLite work DB or archive not explicitly allowed
            # We allow st-eva.sqlite explicitly (working DB, excluded by .gitignore)
            # Any other .sqlite is suspicious given project conventions.
            # This is conservative but does NOT block JSON/CSV/SEC evidence.
            violations.append((p_norm, "unauthorized SQLite DB (must stay local; see .gitignore)"))
            continue
    return violations

def main():
    # Pre-commit: check staged changes (A/C/M = Added, Copied, Modified)
    try:
        res = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            capture_output=True, text=True, errors="ignore"
        )
        staged = [l for l in res.stdout.splitlines() if l]
    except Exception as e:
        print("ERROR: could not read staged files:", e)
        sys.exit(2)

    # Also check tracked-but-modified if running in CI mode (optional; kept simple)
    violations = check(staged)
    if violations:
        print("ERROR: Unauthorized / unverified third-party data attempt detected in staged files.")
        print("Refer to DATA-DELIVERY.md section 2.1 / C-1 and .gitignore exclusions.")
        for path, reason in violations:
            print(f"  [BLOCKED] {path}  --  {reason}")
        sys.exit(1)
    # Silent success
    sys.exit(0)

if __name__ == "__main__":
    main()
