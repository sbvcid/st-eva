"""Generic, reusable acquisition helpers for ST-EVA production historical datasets.

This module automates only the parts of the production historical dataset that
can be obtained directly from authoritative public sources with full
provenance. It never synthesises EPS, prices, acceptance times or share
counts, and it never fills a missing value with zero or an estimate.

Automated (full provenance, deterministic):
  - daily_prices.json        Yahoo Finance chart response (as-traded, split-aware)
  - eps_diluted_concept.json SEC company-concept response for
                            us-gaap:EarningsPerShareDiluted
  - submissions.json is NOT written as a production input, but is used to build
    the semi-automated review package.

Semi-automated (requires manual verification before promotion):
  - filing_acceptance_evidence.json  submissions API gives filed dates; exact
                            ET acceptance timestamps require the SGML header
                            of each filing and must be checked by a human.
  - manual_review_package.json candidate evidence list for human verification.

Manual (not automated here, must be sourced from the filing text):
  - q4_evidence_records.json 8-K Item 2.02 EX-99.1 furnished Q4 GAAP EPS facts
  - manifest.json            hashes and promotion metadata
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple
from zoneinfo import ZoneInfo

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={range}&interval=1d&events=div,splits"
SEC_CONCEPT_URL = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/EarningsPerShareDiluted.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

USER_AGENT = "ST-EVA/2.2 historical-data-builder"
ET = ZoneInfo("America/New_York")
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = 1.0
DEFAULT_TIMEOUT_SECONDS = 30

_REQUIRED_PRICE_FIELDS = ("chart",)
_SOURCE_DESCRIPTIONS = {
    "daily_prices.json": "Yahoo Finance chart response (as-traded, split-aware; not dividend-reinvestment adjusted)",
    "eps_diluted_concept.json": "SEC EDGAR company concept EarningsPerShareDiluted",
    "filing_acceptance_evidence.submissions.json": "SEC submissions API (unverified filed dates; acceptance timestamps require SGML headers)",
    "manual_review_package.json": "Semi-automated candidate evidence list requiring human verification",
    "manifest.json": "SHA-256 manifest and promotion metadata",
}


class BuilderValidationError(ValueError):
    """Raised when a payload or parameter does not satisfy the builder contract."""


def _validate_ticker(ticker: Any) -> str:
    if not isinstance(ticker, str) or not ticker.strip():
        raise BuilderValidationError("ticker must be a non-empty string")
    value = ticker.strip().upper()
    if not all(ch.isalnum() or ch in ".-" for ch in value):
        raise BuilderValidationError(f"invalid ticker: {ticker!r}")
    return value


def _validate_cik(cik: Any) -> str:
    digits = "".join(ch for ch in str(cik) if ch.isdigit())
    if not digits or len(digits) > 10:
        raise BuilderValidationError(f"invalid CIK: {cik!r}")
    return digits.zfill(10)


def _validate_years(years: Any) -> int:
    if isinstance(years, bool) or not isinstance(years, int):
        raise BuilderValidationError("years must be an integer")
    if years < 1 or years > 20:
        raise BuilderValidationError("years must be between 1 and 20")
    return years


def _http_get_json(url: str, retries: int = DEFAULT_RETRIES, timeout: int = DEFAULT_TIMEOUT_SECONDS, backoff: float = DEFAULT_BACKOFF_SECONDS) -> Any:
    last_exc: Optional[Exception] = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw = response.read()
            try:
                return json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise BuilderValidationError(f"invalid JSON received from {url}: {exc}") from exc
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(backoff * (2 ** attempt))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(backoff * (2 ** attempt))
                continue
            raise
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"failed to fetch {url}")


def _http_get_text(url: str, retries: int = DEFAULT_RETRIES, timeout: int = DEFAULT_TIMEOUT_SECONDS, backoff: float = DEFAULT_BACKOFF_SECONDS) -> Tuple[str, bytes]:
    last_exc: Optional[Exception] = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw = response.read()
            try:
                return raw.decode("utf-8", errors="replace"), raw
            except UnicodeDecodeError as exc:
                raise BuilderValidationError(f"invalid text received from {url}: {exc}") from exc
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(backoff * (2 ** attempt))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(backoff * (2 ** attempt))
                continue
            raise
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"failed to fetch {url}")


def fetch_daily_prices(ticker: str, years: int = 6, retries: int = DEFAULT_RETRIES) -> Dict[str, Any]:
    """Return the raw Yahoo chart response for ``ticker`` over ``years`` years."""
    ticker = _validate_ticker(ticker)
    years = _validate_years(years)
    rng = "%dy" % years if years < 10 else "max"
    url = YAHOO_CHART_URL.format(ticker=ticker, range=rng)
    payload = _http_get_json(url, retries=retries)
    _validate_daily_prices_payload(payload)
    return payload


def fetch_eps_concept(cik: str, retries: int = DEFAULT_RETRIES) -> Dict[str, Any]:
    """Return the SEC company-concept response for diluted EPS."""
    cik = _validate_cik(cik)
    url = SEC_CONCEPT_URL.format(cik=cik)
    payload = _http_get_json(url, retries=retries)
    _validate_eps_concept_payload(payload)
    return payload


def fetch_submissions(cik: str, retries: int = DEFAULT_RETRIES) -> Dict[str, Any]:
    """Return the SEC submissions document for ``cik``."""
    cik = _validate_cik(cik)
    url = SEC_SUBMISSIONS_URL.format(cik=cik)
    payload = _http_get_json(url, retries=retries)
    _validate_submissions_payload(payload)
    return payload


def _validate_daily_prices_payload(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise BuilderValidationError("daily prices payload must be a JSON object")
    chart = payload.get("chart")
    if not isinstance(chart, dict):
        raise BuilderValidationError("daily prices payload missing 'chart' object")
    results = chart.get("result")
    if not isinstance(results, list) or not results:
        raise BuilderValidationError("daily prices payload missing chart results")
    result = results[0]
    if not isinstance(result, dict):
        raise BuilderValidationError("daily prices chart result must be an object")
    meta = result.get("meta")
    if not isinstance(meta, dict) or not meta.get("symbol"):
        raise BuilderValidationError("daily prices payload missing meta.symbol")
    timestamps = result.get("timestamp")
    if not isinstance(timestamps, list) or not timestamps:
        raise BuilderValidationError("daily prices payload missing timestamps")
    indicators = result.get("indicators")
    if not isinstance(indicators, dict):
        raise BuilderValidationError("daily prices payload missing indicators")
    quote_list = indicators.get("quote")
    if not isinstance(quote_list, list) or not quote_list:
        raise BuilderValidationError("daily prices payload missing quote")
    quote = quote_list[0]
    if not isinstance(quote, dict) or not isinstance(quote.get("close"), list):
        raise BuilderValidationError("daily prices payload missing quote.close")
    close = quote["close"]
    if len(close) != len(timestamps):
        raise BuilderValidationError("daily prices close/timestamp length mismatch")
    if not any(value is not None for value in close):
        raise BuilderValidationError("daily prices payload has no non-null close values")
    # indicators.adjclose is optional in mocks but required for real Yahoo responses.
    adj = indicators.get("adjclose")
    if adj is not None:
        if not isinstance(adj, list) or not adj or not isinstance(adj[0], dict):
            raise BuilderValidationError("daily prices payload has malformed adjclose")
        if not isinstance(adj[0].get("adjclose"), list):
            raise BuilderValidationError("daily prices payload missing adjclose.adjclose")
        if len(adj[0]["adjclose"]) != len(timestamps):
            raise BuilderValidationError("daily prices adjclose/timestamp length mismatch")


def _validate_eps_concept_payload(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise BuilderValidationError("EPS concept payload must be a JSON object")
    if not payload.get("cik"):
        raise BuilderValidationError("EPS concept payload missing cik")
    if not payload.get("units"):
        raise BuilderValidationError("EPS concept payload missing units")
    units = payload.get("units")
    if not isinstance(units, dict) or not units:
        raise BuilderValidationError("EPS concept payload units must be a non-empty object")
    # At least one unit must contain a list of fact dictionaries.
    has_fact_list = False
    for values in units.values():
        if isinstance(values, list) and values and all(isinstance(v, dict) for v in values):
            has_fact_list = True
            break
    if not has_fact_list:
        raise BuilderValidationError("EPS concept payload has no fact lists")


def _validate_submissions_payload(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise BuilderValidationError("submissions payload must be a JSON object")
    filings = payload.get("filings")
    if not isinstance(filings, dict):
        raise BuilderValidationError("submissions payload missing filings object")
    recent = filings.get("recent")
    if not isinstance(recent, dict):
        raise BuilderValidationError("submissions payload missing filings.recent")
    if not isinstance(recent.get("accessionNumber"), list):
        raise BuilderValidationError("submissions payload missing accessionNumber list")


def validate_daily_prices_payload(payload: Any) -> None:
    _validate_daily_prices_payload(payload)


def validate_eps_concept_payload(payload: Any) -> None:
    _validate_eps_concept_payload(payload)


def validate_submissions_payload(payload: Any) -> None:
    _validate_submissions_payload(payload)


def build_acceptance_index_from_submissions(submissions: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build a lower-fidelity acceptance list from the submissions API.

    Each entry carries the filed date and form. The exact ET acceptance time
    is intentionally left as None: it must be filled from the SGML header
    before the evidence is promoted to a production dataset.
    """
    _validate_submissions_payload(submissions)
    recent = (submissions.get("filings") or {}).get("recent") or {}
    accessions = recent.get("accessionNumber", []) or []
    forms = recent.get("form", []) or []
    filed_dates = recent.get("filingDate", []) or []
    periods = recent.get("reportDate", []) or []
    items_list = recent.get("items", []) or []
    acceptance_list = recent.get("acceptanceDateTime", []) or []

    out: List[Dict[str, Any]] = []
    count = max(len(accessions), len(forms), len(filed_dates), len(periods))
    for i in range(count):
        accn = accessions[i] if i < len(accessions) else None
        form = forms[i] if i < len(forms) else None
        filed = filed_dates[i] if i < len(filed_dates) else None
        period = periods[i] if i < len(periods) else None
        items = items_list[i] if i < len(items_list) else None
        acceptance_utc = acceptance_list[i] if i < len(acceptance_list) else None
        if not accn or not form:
            continue
        if form not in ("10-K", "10-Q", "8-K"):
            continue
        out.append({
            "accession": accn,
            "form": form,
            "filed_date_submissions": filed,
            "period_end": period,
            "items": items,
            "acceptance_datetime_submissions_utc": acceptance_utc,
            "acceptance_datetime_header_et": None,
            "acceptance_datetime_header_raw": None,
            "acceptance_source": "SUBMISSIONS_API_ONLY_UNVERIFIED",
            "review_status": "UNVERIFIED",
        })
    return out


def write_json(path: Path, payload: Any, sort_keys: bool = True) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=sort_keys, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_sgml_header_url(cik: str, accession: str) -> str:
    cik_int = str(int(_validate_cik(cik)))
    acc_nodash = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{accession}-index-headers.html"


def build_filing_index_url(cik: str, accession: str) -> str:
    cik_int = str(int(_validate_cik(cik)))
    acc_nodash = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/index.json"


def fetch_sgml_acceptance_candidate(cik: str, accession: str, retries: int = DEFAULT_RETRIES) -> Dict[str, Any]:
    """Fetch an SGML header and return candidate acceptance timestamp evidence.

    The returned value is a candidate only. It is not verified production
    evidence until a human confirms it.
    """
    url = build_sgml_header_url(cik, accession)
    text, raw = _http_get_text(url, retries=retries)
    match = re.search(r"ACCEPTANCE-DATETIME(?:&gt;|>)(\d{14})", text)
    raw_accept = match.group(1) if match else None
    iso_accept = None
    if raw_accept:
        dt = datetime.strptime(raw_accept, "%Y%m%d%H%M%S").replace(tzinfo=ET)
        iso_accept = dt.isoformat()
    # Cross-check accession and type where present.
    type_match = re.search(r"<TYPE>([^\s<]+)", text)
    acc_match = re.search(r"<ACCESSION-NUMBER>([0-9-]+)", text)
    return {
        "sgml_header_url": url,
        "sgml_header_sha256": hashlib.sha256(raw).hexdigest(),
        "acceptance_datetime_header_raw": raw_accept,
        "acceptance_datetime_header_et": iso_accept,
        "header_type": type_match.group(1) if type_match else None,
        "header_accession": acc_match.group(1) if acc_match else None,
        "accession_matches_header": (acc_match.group(1) == accession) if acc_match else None,
        "candidate_only": True,
        "verified": False,
    }


def fetch_filing_index_documents(cik: str, accession: str, retries: int = DEFAULT_RETRIES) -> List[Dict[str, str]]:
    """Return document candidates from a filing index, including EX-99.* files."""
    url = build_filing_index_url(cik, accession)
    payload = _http_get_json(url, retries=retries)
    directory = payload.get("directory") if isinstance(payload, dict) else None
    items = directory.get("item") if isinstance(directory, dict) else None
    if not isinstance(items, list):
        return []
    cik_int = str(int(_validate_cik(cik)))
    acc_nodash = accession.replace("-", "")
    out: List[Dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name:
            continue
        lower = name.lower()
        kind = None
        if "exhibit99" in lower or "ex99" in lower or "exhibit-99" in lower or "99.1" in lower:
            kind = "ex99_candidate"
        elif name.endswith((".htm", ".html", ".txt")):
            kind = "document"
        if kind is None:
            continue
        out.append({
            "name": name,
            "url": f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{name}",
            "kind": kind,
        })
    return out


def build_review_candidates(
    submissions: Dict[str, Any],
    cik: str,
    fetch_headers: bool = False,
    fetch_indexes: bool = False,
    retries: int = DEFAULT_RETRIES,
) -> List[Dict[str, Any]]:
    """Build a semi-automated candidate evidence list from submissions.

    Candidates are NOT verified evidence. Fields that require human judgment are
    left as None or marked UNVERIFIED.
    """
    _validate_submissions_payload(submissions)
    _validate_cik(cik)
    cik_norm = _validate_cik(cik)
    recent = (submissions.get("filings") or {}).get("recent") or {}
    accessions = recent.get("accessionNumber", []) or []
    forms = recent.get("form", []) or []
    filed_dates = recent.get("filingDate", []) or []
    periods = recent.get("reportDate", []) or []
    items_list = recent.get("items", []) or []
    acceptance_list = recent.get("acceptanceDateTime", []) or []

    out: List[Dict[str, Any]] = []
    count = max(len(accessions), len(forms), len(filed_dates), len(periods))
    for i in range(count):
        accession = accessions[i] if i < len(accessions) else None
        form = forms[i] if i < len(forms) else None
        filed = filed_dates[i] if i < len(filed_dates) else None
        period = periods[i] if i < len(periods) else None
        items = items_list[i] if i < len(items_list) else None
        acceptance_utc = acceptance_list[i] if i < len(acceptance_list) else None
        if not accession or not form:
            continue
        if form not in ("10-K", "10-Q", "8-K"):
            continue
        candidate: Dict[str, Any] = {
            "accession": accession,
            "form": form,
            "filed_date_submissions": filed,
            "period_end": period,
            "items": items,
            "acceptance_datetime_submissions_utc": acceptance_utc,
            "sgml_header_url": build_sgml_header_url(cik_norm, accession),
            "acceptance_datetime_header_et": None,
            "acceptance_datetime_header_raw": None,
            "sgml_header_sha256": None,
            "header_type": None,
            "header_accession": None,
            "accession_matches_header": None,
            "filing_index_url": build_filing_index_url(cik_norm, accession),
            "document_candidates": [],
            "ex99_candidates": [],
            "q4_candidate": bool(form == "8-K" and isinstance(items, str) and "2.02" in items),
            "review_status": "UNVERIFIED",
            "promotion_eligible": False,
            "notes": "Candidate only. Human must verify SGML header acceptance timestamp and Q4 EPS source text before promotion.",
        }
        if fetch_headers:
            try:
                header = fetch_sgml_acceptance_candidate(cik_norm, accession, retries=retries)
                candidate.update({
                    "acceptance_datetime_header_et": header["acceptance_datetime_header_et"],
                    "acceptance_datetime_header_raw": header["acceptance_datetime_header_raw"],
                    "sgml_header_sha256": header["sgml_header_sha256"],
                    "header_type": header["header_type"],
                    "header_accession": header["header_accession"],
                    "accession_matches_header": header["accession_matches_header"],
                })
            except Exception as exc:  # noqa: BLE001 - candidate collection must not abort the whole run
                candidate["header_fetch_error"] = f"{type(exc).__name__}: {exc}"
        if fetch_indexes:
            try:
                docs = fetch_filing_index_documents(cik_norm, accession, retries=retries)
                candidate["document_candidates"] = docs
                candidate["ex99_candidates"] = [d for d in docs if d.get("kind") == "ex99_candidate"]
            except Exception as exc:  # noqa: BLE001
                candidate["index_fetch_error"] = f"{type(exc).__name__}: {exc}"
        out.append(candidate)
    return out


def build_manifest(
    ticker: str,
    cik: str,
    out_dir: Path,
    years: int,
    role: str = "staging_unverified",
) -> Path:
    """Generate a SHA-256 manifest for the files currently present in out_dir."""
    ticker = _validate_ticker(ticker)
    cik_norm = _validate_cik(cik)
    years = _validate_years(years)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    files_info: Dict[str, Any] = {}
    for name in ("daily_prices.json", "eps_diluted_concept.json", "filing_acceptance_evidence.submissions.json", "manual_review_package.json"):
        path = out_dir / name
        if path.exists():
            files_info[name] = {
                "bytes": path.stat().st_size,
                "content_sha256": sha256_file(path),
                "source": _SOURCE_DESCRIPTIONS.get(name, "unknown"),
            }

    manifest = {
        "ticker": ticker,
        "issuer_id": f"CIK{cik_norm}",
        "role": role,
        "generated_by": "historical_data_builder",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "years_requested": years,
        "promotion_status": "NOT_PROMOTED",
        "manual_review_required": True,
        "point_in_time_rule": (
            "usable_date is derived from acceptance_datetime_header_et using the 16:00 ET "
            "cutoff rule at load time; acceptance timestamps are preserved verbatim from "
            "the EDGAR SGML headers. Filed dates alone are not precise acceptance times."
        ),
        "sources": {
            "yahoo_chart": YAHOO_CHART_URL.format(ticker=ticker, range=("%dy" % years if years < 10 else "max")),
            "sec_concept": SEC_CONCEPT_URL.format(cik=cik_norm),
            "sec_submissions": SEC_SUBMISSIONS_URL.format(cik=cik_norm),
        },
        "files": files_info,
    }
    path = out_dir / "manifest.json"
    write_json(path, manifest)
    return path


def _promotion_readiness(out_dir: Path) -> Tuple[bool, Dict[str, Any]]:
    out_dir = Path(out_dir)
    report: Dict[str, Any] = {"out_dir": str(out_dir), "checks": {}}
    required = ["daily_prices.json", "eps_diluted_concept.json", "manifest.json"]
    ready = True
    for name in required:
        exists = (out_dir / name).exists()
        report["checks"][f"file:{name}"] = exists
        ready = ready and exists
    # Manual review package must exist and have all candidates verified with
    # header acceptance timestamps and accession match.
    review_path = out_dir / "manual_review_package.json"
    review_ok = False
    if review_path.exists():
        try:
            review = json.loads(review_path.read_text(encoding="utf-8"))
            candidates = review.get("candidates", [])
            if isinstance(candidates, list) and candidates:
                review_ok = all(
                    isinstance(c, dict)
                    and c.get("review_status") == "VERIFIED"
                    and c.get("acceptance_datetime_header_et")
                    and c.get("accession_matches_header") is True
                    for c in candidates
                )
        except (OSError, json.JSONDecodeError):
            review_ok = False
    report["checks"]["manual_review_complete"] = review_ok
    ready = ready and review_ok
    # Production also requires curated filing acceptance and Q4 evidence. The
    # generic builder does not create them, so their absence blocks promotion.
    for name in ("filing_acceptance_evidence.json", "q4_evidence_records.json"):
        present = (out_dir / name).exists()
        report["checks"][f"production_input:{name}"] = present
        ready = ready and present
    report["ready"] = ready
    return ready, report


def assert_promotion_ready(out_dir: Path) -> None:
    ready, report = _promotion_readiness(out_dir)
    if not ready:
        raise BuilderValidationError(f"dataset is not eligible for production promotion: {report}")


def promote_to_production(out_dir: Path, target_dir: Path) -> None:
    """Refuse to promote unless all manual and production requirements are met."""
    assert_promotion_ready(out_dir)
    out_dir = Path(out_dir)
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    for path in out_dir.iterdir():
        if path.is_file():
            (target_dir / path.name).write_bytes(path.read_bytes())


def generate_base_inputs(
    ticker: str,
    cik: str,
    out_dir: Path,
    years: int = 6,
    generate_manifest: bool = True,
    review_package: bool = False,
    fetch_review_candidates: bool = False,
    retries: int = DEFAULT_RETRIES,
) -> Dict[str, Path]:
    """Generate the automatable base inputs into ``out_dir``.

    Returns the paths written. Does not create a production dataset and does
    not register the ticker in any ISSUER_CONFIGS.
    """
    ticker = _validate_ticker(ticker)
    cik_norm = _validate_cik(cik)
    years = _validate_years(years)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    prices = fetch_daily_prices(ticker, years=years, retries=retries)
    concept = fetch_eps_concept(cik_norm, retries=retries)
    subs = fetch_submissions(cik_norm, retries=retries)
    acceptance = build_acceptance_index_from_submissions(subs)

    paths: Dict[str, Path] = {}
    paths["daily_prices.json"] = out_dir / "daily_prices.json"
    paths["eps_diluted_concept.json"] = out_dir / "eps_diluted_concept.json"
    paths["filing_acceptance_evidence.submissions.json"] = out_dir / "filing_acceptance_evidence.submissions.json"

    write_json(paths["daily_prices.json"], prices)
    write_json(paths["eps_diluted_concept.json"], concept)
    write_json(paths["filing_acceptance_evidence.submissions.json"], acceptance)

    if review_package:
        candidates = build_review_candidates(
            subs,
            cik_norm,
            fetch_headers=fetch_review_candidates,
            fetch_indexes=fetch_review_candidates,
            retries=retries,
        )
        review_payload = {
            "ticker": ticker,
            "issuer_id": f"CIK{cik_norm}",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "role": "manual_review_required",
            "promotion_status": "NOT_PROMOTED",
            "manual_review_required": True,
            "point_in_time_rule": (
                "Conservative usable date: if acceptance timestamp is unknown or on/after "
                "16:00 ET, treat as next business day. Never use filed date as an exact time."
            ),
            "candidate_count": len(candidates),
            "candidates": candidates,
        }
        paths["manual_review_package.json"] = out_dir / "manual_review_package.json"
        write_json(paths["manual_review_package.json"], review_payload)

    if generate_manifest:
        manifest_path = build_manifest(ticker, cik_norm, out_dir, years)
        paths["manifest.json"] = manifest_path

    return paths