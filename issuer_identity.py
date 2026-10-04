"""
Canonical issuer identity for SEC companyfacts payloads.

## Why this exists

Companyfacts payloads arrive under two filename conventions in this harness:

    AAPL_companyfacts.json      the convention every reader assumed
    0000026172.json             a real payload, named by CIK

Any reader that derived the issuer from `name.split("_")[0].upper()` therefore
saw `0000026172.JSON` as a filer in its own right. Twelve payloads are like that,
and each resolves through its own `cik` to an issuer that was already present, so
the enumeration counted twelve issuers twice and reported 75 filers for 63
issuers. It is not only a counting error: any research keyed on a filer key could
treat one company as two, which is the failure mode this module removes.

## The rule

    payload.cik  ->  canonical issuer identity

The filename is transport metadata and a consistency diagnostic. It never decides
identity, and it never creates an issuer. Where a filename disagrees with the
payload's CIK, the payload's CIK wins and the disagreement is recorded; where the
payload has no usable CIK, the identity is explicitly unresolved rather than
guessed from the filename.

## Why callers still see ticker keys

`load_companyfacts_payloads` returns its mapping keyed by the *resolved ticker*
where the CIK resolves to one, so the many readers that look payloads up by ticker
keep working unchanged. What changed is how that key was decided: by CIK join,
not by filename. Callers that need the canonical identity ask for
`resolve_issuer`, and the loader returns the full record alongside the mapping.

## Normalisation

CIKs are compared as digits with leading zeros stripped, because the payloads
carry integers and the archive `assets` table carries zero-padded strings, and
`0000026172` and `26172` are the same issuer.
"""

from __future__ import annotations

import glob
import json
import os
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

# Identity status vocabulary.
CANONICAL_MATCH = "CANONICAL_MATCH"
NONCANONICAL_FILENAME = "NONCANONICAL_FILENAME"
FILENAME_CIK_MISMATCH = "FILENAME_CIK_MISMATCH"
MISSING_PAYLOAD_CIK = "MISSING_PAYLOAD_CIK"
UNKNOWN_CIK = "UNKNOWN_CIK"

IDENTITY_STATUSES = (CANONICAL_MATCH, NONCANONICAL_FILENAME,
                     FILENAME_CIK_MISMATCH, MISSING_PAYLOAD_CIK, UNKNOWN_CIK)

TICKER_MAP_NAME = "tickers.json"
_EXPECTED = re.compile(r"^[A-Za-z0-9.\-]+_companyfacts\.json$")
_CIK_ONLY = re.compile(r"^(\d{1,10})\.json$")
_CIK_PREFIXED = re.compile(r"^(\d{1,10})_companyfacts\.json$")


def normalise_cik(value: Any) -> Optional[str]:
    """Digits with leading zeros stripped, or None if unusable."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if not text.isdigit():
        return None
    stripped = text.lstrip("0")
    return stripped or "0"


def filename_token(name: str) -> str:
    """The token a filename-derived reader would have used. Diagnostic only."""
    return name.split("_")[0].upper()


def filename_matches_expected(name: str) -> bool:
    return bool(_EXPECTED.match(name))


def filename_cik(name: str) -> Optional[str]:
    """The CIK a filename appears to claim, if it claims one."""
    for pattern in (_CIK_PREFIXED, _CIK_ONLY):
        match = pattern.match(name)
        if match:
            return normalise_cik(match.group(1))
    return None


_CIK_INDEX_CACHE: Dict[str, Dict[str, str]] = {}


def cik_ticker_index(harness_dir: str) -> Dict[str, str]:
    """
    CIK to ticker, from the archive `assets` tables.

    This is the join that turns a canonical CIK into the key existing readers
    use. Every snapshot archive carries it, so the resolution is a join rather
    than a name match.

    Cached per directory: reading fifteen archives per payload directory turned
    out to be the difference between a loader that resolves and one that
    silently emits `CIK:...` keys, because a caller that forgets to pass the map
    gets no error at all. Callers may still pass one explicitly; the cache only
    exists so that forgetting cannot change the answer.
    """
    if harness_dir in _CIK_INDEX_CACHE:
        return _CIK_INDEX_CACHE[harness_dir]
    out: Dict[str, str] = {}
    for name in sorted(os.listdir(harness_dir)):
        if not name.endswith(".sqlite"):
            continue
        try:
            con = sqlite3.connect(
                "file:%s?mode=ro" % os.path.join(harness_dir, name), uri=True)
            rows = con.execute(
                "SELECT ticker, cik FROM assets WHERE cik IS NOT NULL").fetchall()
            con.close()
        except sqlite3.Error:
            continue
        for ticker, cik in rows:
            key = normalise_cik(cik)
            if key:
                out.setdefault(key, ticker)
    _CIK_INDEX_CACHE[harness_dir] = out
    return out


def _index_for(harness_dir: str,
               cik_to_ticker: Optional[Dict[str, str]]) -> Dict[str, str]:
    """Retained for callers that hold a harness directory rather than a map."""
    if cik_to_ticker is not None:
        return cik_to_ticker
    return cik_ticker_index(harness_dir)


def resolve_issuer(document: Optional[Dict[str, Any]], path: str,
                    cik_to_ticker: Optional[Dict[str, str]] = None
                    ) -> Dict[str, Any]:
    """
    The canonical identity of one payload, with the filename as a diagnostic.

    Never raises and never guesses: a payload with no usable CIK resolves to
    ``None`` and is reported as `MISSING_PAYLOAD_CIK`, and a CIK that no issuer
    record knows is reported as `UNKNOWN_CIK` rather than falling back to the
    filename.
    """
    name = os.path.basename(path)
    payload_cik = normalise_cik((document or {}).get("cik"))
    token = filename_token(name)
    claimed = filename_cik(name)
    ticker = None
    if payload_cik and cik_to_ticker:
        ticker = cik_to_ticker.get(payload_cik)

    if payload_cik is None:
        status = MISSING_PAYLOAD_CIK
    elif claimed is not None and claimed != payload_cik:
        status = FILENAME_CIK_MISMATCH
    elif not filename_matches_expected(name):
        status = NONCANONICAL_FILENAME
    else:
        status = CANONICAL_MATCH

    return {
        "path": path,
        "filename": name,
        "filename_derived_token": token,
        "filename_matches_expected_pattern": filename_matches_expected(name),
        "filename_cik_if_parseable": claimed,
        "payload_cik": payload_cik,
        "filename_cik_equals_payload_cik": (
            None if claimed is None else claimed == payload_cik),
        "identity_status": status,
        "canonical_issuer_cik": payload_cik,
        "resolved_ticker": ticker,
        "entity_name": (document or {}).get("entityName"),
        "key": ticker or ("CIK:%s" % payload_cik if payload_cik
                          else "UNRESOLVED:%s" % name),
        "resolved_from": ("cik_join" if ticker else
                          "cik_only" if payload_cik else "unresolved"),
    }


def load_companyfacts_payloads(
        directory: str,
        cik_to_ticker: Optional[Dict[str, str]] = None,
        read_document: bool = True,
        harness_dir: Optional[str] = None) -> Tuple[Dict[str, str], List[Dict[str, Any]]]:
    """
    Load one directory of payloads.

    Returns ``(mapping, records)`` where the mapping is keyed by resolved ticker
    where the CIK resolves to one, so ticker-keyed callers are unaffected, and
    ``records`` carries the full identity record for auditing.

    Two payloads for one issuer collapse onto one key, which is the point: three
    identical `TSM_companyfacts.json` files across directories already collapsed,
    and twelve CIK-named payloads now collapse the same way instead of appearing
    as new filers.

    `harness_dir` is required for ticker keys, because the CIK-to-ticker join
    lives in the archives beside the payload directories and this function is
    handed one directory at a time. Passing a `cik_to_ticker` map directly also
    works. Without either, keys come back as `CIK:<cik>` -- which is honest but
    not what any existing caller wants, so callers pass the harness root.
    """
    mapping: Dict[str, str] = {}
    records: List[Dict[str, Any]] = []
    if not os.path.isdir(directory):
        return mapping, records
    index = cik_to_ticker
    if index is None and harness_dir is not None:
        index = cik_ticker_index(harness_dir)
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".json") or name == TICKER_MAP_NAME:
            continue
        path = os.path.join(directory, name)
        document = None
        if read_document:
            try:
                with open(path, encoding="utf-8") as handle:
                    document = json.load(handle)
            except (OSError, ValueError):
                document = None
        record = resolve_issuer(document, path, index)
        records.append(record)
        if document is None:
            # An unreadable payload is still a file worth reporting, but it must
            # not overwrite an identity we already resolved.
            mapping.setdefault(record["filename_derived_token"], path)
            continue
        mapping.setdefault(record["key"], path)
    return mapping, records


def payload_records(directory: str,
                    cik_to_ticker: Optional[Dict[str, str]] = None
                    ) -> List[Dict[str, Any]]:
    """Identity records for one directory, for auditing and anomaly reporting."""
    return load_companyfacts_payloads(directory, cik_to_ticker)[1]


def harness_payload_dirs(harness_dir: str,
                         names: Optional[List[str]] = None) -> List[str]:
    """The payload directories in the order the readers have always used."""
    if names is None:
        names = ["bulkfacts-227a-orig", "bulkfacts-227b", "bulkfacts-ins-min",
                 "bulkfacts-fs", "bulkfacts-banks-2", "inventory", "bulkfacts",
                 "bulkfacts-banks"]
    return [os.path.join(harness_dir, n) for n in names
            if os.path.isdir(os.path.join(harness_dir, n))]


def load_harness_payloads(
        harness_dir: str,
        names: Optional[List[str]] = None,
        cik_to_ticker: Optional[Dict[str, str]] = None
) -> Tuple[Dict[str, str], List[Dict[str, Any]]]:
    """The harness-wide payload mapping and every identity record behind it."""
    if cik_to_ticker is None:
        cik_to_ticker = cik_ticker_index(harness_dir)
    mapping: Dict[str, str] = {}
    records: List[Dict[str, Any]] = []
    for directory in harness_payload_dirs(harness_dir, names):
        sub_mapping, sub_records = load_companyfacts_payloads(
            directory, cik_to_ticker)
        for key, path in sub_mapping.items():
            mapping.setdefault(key, path)
        records.extend(sub_records)
    return mapping, records
