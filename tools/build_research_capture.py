"""Build a research capture from an issuer's configuration.

The builder reads one issuer's settings and writes the capture the research
lanes read: the price series, the filing acceptance index, and the filed
elements each capture role holds. It keeps the existing research policies:

* a fact is knowable from its filing's usable date, under the 16:00 ET
  acceptance cutoff, in America/New_York with the offset the date carries;
* the acceptance time comes from the filing's own SGML header, and from the
  submissions API when the header cannot be retrieved;
* the elements come from the filer's own filings, and the capture records
  which endpoint each came from.

Where the facts APIs serve nothing for an element, the builder reads the
filing's own instance document rather than concluding that the filing did not
provide it. An inline XBRL instance states its facts with a scale, and that
scale is the difference between an amount in units and an amount in
thousands, so the builder records it and applies it.

The builder never writes to a production data path.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from research_issuers import IssuerSettings, load_issuer_settings  # noqa: E402

EASTERN = ZoneInfo("America/New_York")
CUTOFF_ET = datetime.time(16, 0)
USER_AGENT = "ST-EVA research capture builder (research; st-eva@example.com)"
REQUEST_INTERVAL_SECONDS = 0.15
MAX_ATTEMPTS = 5

# The capture's own file names. The manifest names the role of each file, so
# the lanes do not depend on the names; the names are here so that two
# builds of the same issuer write the same files.
CONCEPT_FILE = "{role}_concept.json"
PRICES_FILE = "daily_prices.json"
ACCEPTANCE_FILE = "filing_acceptance_evidence.json"
MANIFEST_FILE = "manifest.json"

# The roles the capture reserves for its own files.
CAPTURE_ROLE_PRICES = "prices"
CAPTURE_ROLE_ACCEPTANCE = "acceptance index"

PRODUCTION_DATA_PREFIXES = ("data/historical_",)


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


def _fetch(url: str, cache_dir: Optional[Path]) -> bytes:
    cache_path = None
    if cache_dir is not None:
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        cache_path = cache_dir / f"{key}_{url.rsplit('/', 1)[-1][:48]}"
        cache_path = cache_path.parent / cache_path.name.replace("?", "_").replace(
            "&", "_"
        )
        if cache_path.exists():
            return cache_path.read_bytes()
    last: Optional[Exception] = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT}
            )
            with urllib.request.urlopen(request, timeout=300) as response:
                payload = response.read()
            if cache_path is not None:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_bytes(payload)
            time.sleep(REQUEST_INTERVAL_SECONDS)
            return payload
        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise
            last = error
        except (urllib.error.URLError, OSError) as error:
            last = error
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"failed to fetch {url}: {last}")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# The acceptance index
# ---------------------------------------------------------------------------


def header_acceptance_to_eastern(raw: str) -> datetime.datetime:
    """
    The header's ACCEPTANCE-DATETIME, as an aware Eastern datetime.

    The header gives Eastern local time and carries no offset, and Eastern
    local time is not a fixed offset: a standard-time filing is five hours
    from UTC and a daylight-time filing is four. The zone is therefore taken
    from the region, so the recorded instant is the instant the filing was
    accepted.
    """
    return datetime.datetime.strptime(raw, "%Y%m%d%H%M%S").replace(tzinfo=EASTERN)


def api_acceptance_to_eastern(iso: str) -> datetime.datetime:
    """The submissions API's acceptance datetime, as an aware Eastern one."""
    return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(
        EASTERN
    )


def _acceptance_index(
    settings: IssuerSettings, cache_dir: Optional[Path]
) -> List[Dict[str, Any]]:
    """One record per periodic filing, with the acceptance time it was filed."""
    capture = settings.capture
    cik = settings.issuer_id.replace("CIK", "")
    forms = tuple(capture.get("periodic_forms") or ("10-K", "10-Q"))
    earliest = capture.get("earliest_filed_date") or "2010-01-01"

    rows: List[Tuple[str, str, str, str, str]] = []
    seen: set = set()
    submissions_urls = [
        f"https://data.sec.gov/submissions/CIK{cik}.json",
        f"https://data.sec.gov/submissions/CIK{cik}-submissions-001.json",
    ]
    for url in submissions_urls:
        try:
            payload = json.loads(_fetch(url, cache_dir).decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code == 404:
                continue
            raise
        recent = payload["filings"]["recent"] if "filings" in payload else payload
        for index in range(len(recent["form"])):
            form = recent["form"][index]
            if form not in forms:
                continue
            filed = recent["filingDate"][index]
            if filed < earliest:
                continue
            accession = recent["accessionNumber"][index]
            if accession in seen:
                continue
            seen.add(accession)
            rows.append(
                (
                    accession,
                    form,
                    recent["reportDate"][index],
                    filed,
                    recent["acceptanceDateTime"][index],
                )
            )
    rows.sort(key=lambda row: row[4])

    records: List[Dict[str, Any]] = []
    for accession, form, report_date, filed, acceptance in rows:
        bare = accession.replace("-", "")
        base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{bare}"
        header_url = f"{base}/{accession}-index-headers.html"
        try:
            text = _fetch(header_url, cache_dir).decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
            text = ""
        if "ACCEPTANCE-DATETIME" not in text:
            header_url = f"{base}/{accession}.txt"
            try:
                text = _fetch(header_url, cache_dir).decode("utf-8", "replace")
            except urllib.error.HTTPError:
                text = ""

        def grab(pattern: str) -> Optional[str]:
            found = re.search(pattern, text)
            return found.group(1) if found else None

        # The filing index renders the field as "ACCEPTANCE-DATETIME&gt;...";
        # the full submission's SGML header writes "<ACCEPTANCE-DATETIME>...".
        # Both shapes are read, so a filing whose index header is not
        # retrievable still yields its own acceptance time from the document
        # EDGAR itself filed.
        raw = grab(r"ACCEPTANCE-DATETIME(?:&gt;|>|:|\s)+(\d{14})")
        api_utc = datetime.datetime.fromisoformat(acceptance.replace("Z", "+00:00"))
        if raw:
            header_et = header_acceptance_to_eastern(raw)
            effective_et = header_et
            basis = "SGML header ACCEPTANCE-DATETIME"
        else:
            header_et = None
            effective_et = api_acceptance_to_eastern(acceptance)
            basis = (
                "submissions API acceptanceDateTime, converted to "
                "America/New_York; no SGML header was retrievable for this filing"
            )
        records.append(
            {
                "accession": accession,
                "form": form,
                "period_end": report_date,
                "filed_date_submissions": filed,
                "acceptance_datetime_header_et": (
                    header_et.isoformat() if header_et else None
                ),
                "acceptance_datetime_effective_et": effective_et.isoformat(),
                "acceptance_datetime_submissions_api": acceptance,
                "acceptance_basis": basis,
                "api_minus_header_hours": round(
                    (api_utc - effective_et).total_seconds() / 3600.0, 3
                ),
                "conformed_period_of_report_header": grab(
                    r"CONFORMED PERIOD OF REPORT:\s*(\d{8})"
                ),
                "date_as_of_change_header": grab(r"DATE AS OF CHANGE:\s*(\d{8})"),
                "filed_as_of_date_header": grab(r"FILED AS OF DATE:\s*(\d{8})"),
                "fiscal_year_end_header": grab(r"FISCAL YEAR END:\s*(\d{4})"),
                "header_source_url": header_url,
                "header_source_sha256": _sha256(text.encode("utf-8")),
            }
        )
    return records


# ---------------------------------------------------------------------------
# The elements
# ---------------------------------------------------------------------------


def _facts_rows(
    body: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for unit, items in (body.get("units") or {}).items():
        for row in items:
            rows.append({**row, "unit": unit})
    return rows


def _element_from_facts_api(
    settings: IssuerSettings,
    taxonomy: str,
    tag: str,
    cache_dir: Optional[Path],
    sources: Sequence[str] = ("companyfacts",),
) -> Tuple[Optional[Dict[str, Any]], str, Optional[str]]:
    """
    An element's rows, from the first configured source that serves it.

    The sources are tried in the order the issuer's configuration names
    them, and the source that served the element is recorded. An element that
    no source serves is not an absence: the builder falls to the filing's own
    instance document.
    """
    facts_url = (
        f"https://data.sec.gov/api/xbrl/companyfacts/{settings.issuer_id}.json"
    )
    concept_url = (
        f"https://data.sec.gov/api/xbrl/companyconcept/{settings.issuer_id}/"
        f"{taxonomy}/{tag}.json"
    )

    def _rows_of(payload: Mapping[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        units: Dict[str, List[Dict[str, Any]]] = {}
        for unit, items in (payload.get("units") or {}).items():
            units[unit] = [
                {
                    "start": row.get("start"),
                    "end": row.get("end"),
                    "val": row.get("val"),
                    "accn": row.get("accn"),
                    "fy": row.get("fy"),
                    "fp": row.get("fp"),
                    "form": row.get("form"),
                    "filed": row.get("filed"),
                    "frame": row.get("frame"),
                }
                for row in items
            ]
        return units

    for source_name in sources:
        if source_name == "companyconcept":
            try:
                payload = json.loads(
                    _fetch(concept_url, cache_dir).decode("utf-8")
                )
            except urllib.error.HTTPError as error:
                if error.code != 404:
                    raise
                continue
            units = _rows_of(payload)
            if not units:
                continue
            return (
                {
                    "taxonomy": taxonomy,
                    "tag": tag,
                    "label": payload.get("label"),
                    "description": payload.get("description"),
                    "units": units,
                },
                "companyconcept",
                concept_url,
            )
        if source_name == "companyfacts":
            try:
                facts = json.loads(_fetch(facts_url, cache_dir).decode("utf-8"))
            except urllib.error.HTTPError as error:
                if error.code != 404:
                    raise
                continue
            body = (facts.get("facts") or {}).get(taxonomy, {}).get(tag)
            if body is None:
                continue
            units = _rows_of(body)
            if not units:
                continue
            return (
                {
                    "taxonomy": taxonomy,
                    "tag": tag,
                    "label": body.get("label"),
                    "description": body.get("description"),
                    "units": units,
                },
                "companyfacts",
                facts_url,
            )
    return None, "unavailable", None


def _strip_namespace(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _parse_instance(
    payload: bytes, wanted: Sequence[str]
) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """
    The facts of an instance document that name one of the wanted elements.

    Both shapes are read: an inline XBRL instance, whose facts carry a
    scale, and a traditional instance, whose facts do not. The contexts are
    read too, and a context that carries a dimension is skipped: the facts
    APIs publish only the dimension-free facts, and a capture must hold the
    same ones.
    """
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError:
        return [], {}

    contexts: Dict[str, Dict[str, Any]] = {}
    for context in root.iter():
        if _strip_namespace(context.tag) != "context":
            continue
        identifier = context.get("id")
        if not identifier:
            continue
        start = end = None
        has_member = False
        for node in context.iter():
            name = _strip_namespace(node.tag)
            if name == "startDate":
                start = (node.text or "").strip()
            elif name == "endDate":
                end = (node.text or "").strip()
            elif name == "explicitMember":
                has_member = True
        contexts[identifier] = {
            "start": start,
            "end": end,
            "consolidated": not has_member,
        }

    facts: List[Dict[str, Any]] = []
    for node in root.iter():
        name = _strip_namespace(node.tag)
        if name not in ("nonFraction", "nonNumeric"):
            continue
        concept = node.get("name") or ""
        if concept not in wanted:
            continue
        context = contexts.get(node.get("contextRef") or "")
        if context is None or not context["consolidated"]:
            continue
        if name == "nonNumeric":
            continue
        text = (node.text or "").strip()
        scale = int(node.get("scale") or 0)
        sign = node.get("sign")
        try:
            value = float(text.replace(",", ""))
        except ValueError:
            continue
        value = value * (10**scale)
        if sign == "-":
            value = -value
        facts.append(
            {
                "start": context["start"],
                "end": context["end"],
                "val": value,
                "unit": node.get("unitRef") or "",
                "decimals": node.get("decimals"),
                "scale": scale,
                "context_ref": node.get("contextRef"),
                "concept": concept,
            }
        )
    return facts, contexts


def _element_from_instance(
    settings: IssuerSettings,
    taxonomy: str,
    tag: str,
    acceptance: Sequence[Mapping[str, Any]],
    cache_dir: Optional[Path],
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """
    An element read from the filer's own filings.

    The builder goes to the filings themselves, so that an element the facts
    APIs do not serve is still read from the document that states it. The
    scale each fact carries is recorded, because a fact stated in thousands
    is not a fact stated in units.
    """
    cik = settings.issuer_id.replace("CIK", "")
    concept = f"{taxonomy}:{tag}"
    rows: List[Dict[str, Any]] = []
    scales: Dict[str, int] = {}
    for record in acceptance:
        bare = record["accession"].replace("-", "")
        base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{bare}"
        for name in (
            f"{record['accession']}_htm.xml",
            f"{record['accession']}.xml",
        ):
            try:
                payload = _fetch(f"{base}/{name}", cache_dir)
            except urllib.error.HTTPError:
                continue
            facts, _contexts = _parse_instance(payload, [concept])
            if not facts:
                continue
            for fact in facts:
                rows.append(
                    {
                        "start": fact["start"],
                        "end": fact["end"],
                        "val": fact["val"],
                        "accn": record["accession"],
                        "form": record["form"],
                        "filed": record["filed_date_submissions"],
                        "fy": None,
                        "fp": None,
                        "frame": None,
                    }
                )
                scales[str(fact.get("scale", 0))] = (
                    scales.get(str(fact.get("scale", 0)), 0) + 1
                )
            break
    if not rows:
        return None, {"source": "unavailable"}
    return (
        {
            "taxonomy": taxonomy,
            "tag": tag,
            "label": None,
            "description": None,
            "units": {"USD": rows},
        },
        {"source": "filing_instance", "scales": scales},
    )


# ---------------------------------------------------------------------------
# The capture
# ---------------------------------------------------------------------------


def _role_scale(unit: str, policy: Mapping[str, Any]) -> float:
    """
    The scaling factor one role's rows are held under.

    A share count is a count, not an amount. Scaling it with the issuer's
    amounts would make the capture hold a thousand shares for every share
    filed, and would cancel the scale out of a market-capitalisation
    multiple instead of stating it. The count is therefore held unscaled,
    and the manifest records that it was.
    """
    share_unit = (
        policy.get("share_unit")
        if isinstance(policy, Mapping)
        else getattr(policy, "share_unit", None)
    )
    scale = (
        policy.get("scale", 1.0)
        if isinstance(policy, Mapping)
        else getattr(policy, "scale", 1.0)
    )
    if unit and unit == share_unit:
        return 1.0
    return float(scale)


def _normalise(
    rows: List[Dict[str, Any]], unit: str, scale: float
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    The rows, in the unit the issuer's policy names.

    Every scaling is recorded: the unit the filer used, the factor, the unit
    the capture holds, and the basis.
    """
    if scale == 1:
        return rows, {
            "source_unit": unit,
            "factor": 1,
            "target_unit": unit,
            "basis": "the filed amounts are already in the unit the capture holds",
            "scaled": False,
        }
    return (
        [{**row, "val": float(row["val"]) * scale} for row in rows],
        {
            "source_unit": unit,
            "factor": scale,
            "target_unit": unit,
            "basis": (
                "the filed amounts were stated in a scaled unit and are held "
                "in the unit the issuer's policy names"
            ),
            "scaled": True,
        },
    )


def build_capture(
    settings: IssuerSettings,
    output_dir: Path,
    cache_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Build one issuer's capture, and write its manifest."""
    relative = str(settings.capture["directory"]).replace("/", os.sep)
    if relative.startswith(PRODUCTION_DATA_PREFIXES):
        raise ValueError(
            f"the capture directory {settings.capture['directory']!r} is a "
            "production data path; a research capture never writes there"
        )
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    acceptance = _acceptance_index(settings, cache_dir)
    files: Dict[str, Dict[str, Any]] = {}

    # -- the price series ----------------------------------------------------
    price_url = _price_url(settings)
    price_bytes = _fetch(price_url, cache_dir)
    (output_dir / PRICES_FILE).write_bytes(price_bytes)
    files[PRICES_FILE] = {
        "sha256": _sha256(price_bytes),
        "bytes": len(price_bytes),
        "role": CAPTURE_ROLE_PRICES,
        "source": {
            "url": price_url,
            "retrieval": (
                "one daily-granularity chart request for the issuer's ticker; "
                "the payload is stored verbatim, including its split events"
            ),
            "source_document_sha256": _sha256(price_bytes),
            "note": (
                "The provider's close series reflects later split events. The "
                "lane restores the as-traded close from the split events in "
                "this payload before it pairs a price with a share count."
            ),
        },
    }

    # -- the acceptance index -------------------------------------------------
    acceptance_bytes = (
        json.dumps(acceptance, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    (output_dir / ACCEPTANCE_FILE).write_bytes(acceptance_bytes)
    files[ACCEPTANCE_FILE] = {
        "sha256": _sha256(acceptance_bytes),
        "bytes": len(acceptance_bytes),
        "role": CAPTURE_ROLE_ACCEPTANCE,
        "source": {
            "url": (
                "https://www.sec.gov/Archives/edgar/data/"
                "<cik>/<accession>/<accession>-index-headers.html"
            ),
            "retrieval": (
                "one request per periodic filing for the filing's SGML header; "
                "the acceptance datetime is read from the header's "
                "ACCEPTANCE-DATETIME field, which is America/New_York local "
                "time and carries the offset the date has"
            ),
            "source_document_sha256": None,
            "note": (
                "The acceptance datetime decides when a filing's facts first "
                "become knowable, which is the point-in-time rule the lane "
                "applies."
            ),
        },
    }

    # -- the elements ------------------------------------------------------------
    policy = settings.unit_policy
    element_sources: Dict[str, str] = {}
    substitutions: Dict[str, str] = {}
    normalisations: Dict[str, Dict[str, Any]] = {}
    accessions: Dict[str, Dict[str, Any]] = {}

    sources = list(settings.capture.get("element_sources") or ["companyfacts"])
    for role_name, element in settings.capture["elements"].items():
        taxonomy = element["taxonomy"]
        captured: List[Dict[str, Any]] = []
        role_source = "unavailable"
        role_url: Optional[str] = None
        scale_evidence: Dict[str, Any] = {}
        for tag in element["elements"]:
            payload, source, url = _element_from_facts_api(
                settings, taxonomy, tag, cache_dir, sources
            )
            if payload is None:
                payload, instance = _element_from_instance(
                    settings, taxonomy, tag, acceptance, cache_dir
                )
                if payload is None:
                    substitutions[f"{taxonomy}:{tag}"] = (
                        "None of the configured sources -- "
                        + ", ".join(sources)
                        + " -- served this element, and no periodic filing "
                        "stated it in an instance document the builder could "
                        "read."
                    )
                    continue
                source = instance["source"]
                scale_evidence = instance
            captured.append(payload)
            role_source = source
            role_url = url or role_url
        if not captured:
            continue

        units: Dict[str, List[Dict[str, Any]]] = {}
        for payload in captured:
            for unit, rows in payload["units"].items():
                units.setdefault(unit, []).extend(rows)
        if len(units) > 1:
            raise ValueError(
                f"the capture role {role_name!r} holds more than one unit: "
                f"{sorted(units)}; the unit policy must name one"
            )
        unit = next(iter(units))
        # A share count is a count, not an amount. Scaling it with the
        # issuer's amounts would make the capture hold a thousand shares
        # for every share filed, and would cancel the scale out of a
        # market-capitalisation multiple instead of stating it.
        role_scale = _role_scale(unit, policy)
        rows, normalisation = _normalise(units[unit], unit, role_scale)
        if captured[0].get("_scale"):
            normalisation["basis"] = (
                "the filed amounts were stated with a scale in the instance "
                "document; the scale, its factor and the unit are recorded"
            )
        normalisations[role_name] = {
            "unit": unit,
            "currency": policy.filing_currency,
            **normalisation,
        }

        document = {
            "issuer_id": settings.issuer_id,
            "ticker": settings.ticker,
            "role": role_name,
            "taxonomy": taxonomy,
            "captured_at": settings.capture.get("captured_at", ""),
            "context_policy": CONTEXT_POLICY,
            "elements": captured,
            "normalisation": normalisations[role_name],
        }
        name = CONCEPT_FILE.format(role=role_name)
        payload_bytes = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        )
        (output_dir / name).write_bytes(payload_bytes)
        role_accessions = sorted(
            {row.get("accn") for row in rows if row.get("accn")}
        )
        accessions[role_name] = {
            "count": len(role_accessions),
            "first": role_accessions[0] if role_accessions else None,
            "last": role_accessions[-1] if role_accessions else None,
        }
        files[name] = {
            "sha256": _sha256(payload_bytes),
            "bytes": len(payload_bytes),
            "role": role_name,
            "unit": unit,
            "currency": policy.filing_currency,
            "normalisation": normalisations[role_name],
            "accessions": accessions[role_name],
            "source": {
                "url": role_url,
                "retrieval": (
                    "the element's rows are taken from the filer's own XBRL "
                    "facts, verbatim, and re-keyed to the companyconcept shape"
                ),
                "source_document_sha256": role_url,
                "note": (
                    f"the element came from the {role_source}"
                    + (f"; {scale_evidence}" if scale_evidence else "")
                ),
            },
        }
        element_sources[role_name] = role_source

    manifest = _manifest_for(settings, output_dir, files, element_sources,
                            normalisations, accessions, substitutions)
    return manifest


def describe_capture(
    settings: IssuerSettings, output_dir: Path
) -> Dict[str, Any]:
    """
    The manifest of a capture that is already on disk.

    The files are read, their digests taken, and the unit and the accession
    coverage each one carries are read from them, so the manifest describes
    the capture as it is rather than as it was once intended to be.
    """
    output_dir = Path(output_dir)
    files: Dict[str, Dict[str, Any]] = {}
    element_sources: Dict[str, str] = {}
    normalisations: Dict[str, Dict[str, Any]] = {}
    accessions: Dict[str, Dict[str, Any]] = {}
    policy = settings.unit_policy
    # The source records the capture already holds are carried over verbatim:
    # they travel into the observations' evidence, and the observations' hashes
    # cover their evidence.
    existing: Dict[str, Any] = {}
    manifest_path = output_dir / MANIFEST_FILE
    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    existing_sources = {
        name: entry.get("source")
        for name, entry in (existing.get("files") or {}).items()
    }
    for path in sorted(output_dir.glob("*.json")):
        if path.name == MANIFEST_FILE:
            continue
        digest = _sha256(path.read_bytes())
        entry: Dict[str, Any] = {
            "sha256": digest,
            "bytes": path.stat().st_size,
        }
        if path.name == PRICES_FILE:
            entry["role"] = CAPTURE_ROLE_PRICES
            entry["source"] = existing_sources.get(path.name) or {
                "url": _price_url(settings),
                "retrieval": (
                    "one daily-granularity chart request for the issuer's "
                    "ticker; the payload is stored verbatim, including its "
                    "split events"
                ),
                "source_document_sha256": digest,
                "note": (
                    "The provider's close series reflects later split events. "
                    "The lane restores the as-traded close from the split "
                    "events in this payload before it pairs a price with a "
                    "share count."
                ),
            }
        elif path.name == ACCEPTANCE_FILE:
            entry["role"] = CAPTURE_ROLE_ACCEPTANCE
            entry["source"] = existing_sources.get(path.name) or {
                "url": (
                    "https://www.sec.gov/Archives/edgar/data/"
                    "<cik>/<accession>/<accession>-index-headers.html"
                ),
                "retrieval": (
                    "one request per periodic filing for the filing's SGML "
                    "header; the acceptance datetime is read from the header's "
                    "ACCEPTANCE-DATETIME field, which is America/New_York local "
                    "time and carries the offset the date has"
                ),
                "source_document_sha256": None,
                "note": (
                    "The acceptance datetime decides when a filing's facts "
                    "first become knowable, which is the point-in-time rule "
                    "the lane applies."
                ),
            }
        else:
            document = json.loads(path.read_text(encoding="utf-8"))
            role = document.get("role") or path.stem.replace("_concept", "")
            unit = None
            role_accessions: set = set()
            for element in document.get("elements") or []:
                for element_unit, rows in (element.get("units") or {}).items():
                    if unit is None:
                        unit = element_unit
                    if element_unit == unit:
                        role_accessions.update(
                            row.get("accn") for row in rows if row.get("accn")
                        )
            role_accessions = sorted(role_accessions)
            entry["role"] = role
            entry["unit"] = unit
            # The normalisation is the capture's own record of what it did to
            # the filed amounts, so it is read from the file rather than
            # re-derived from the configuration: a description that disagrees
            # with the file it describes is a disagreement, not a correction.
            normalisation = document.get("normalisation") or {
                "unit": unit,
                "currency": (
                    policy.filing_currency
                    if unit and unit != policy.share_unit
                    else None
                ),
                "source_unit": unit,
                "factor": _role_scale(unit, policy),
                "target_unit": unit,
                "basis": policy.scale_basis,
                "scaled": _role_scale(unit, policy) != 1,
            }
            entry["currency"] = normalisation.get("currency")
            entry["accessions"] = {
                "count": len(role_accessions),
                "first": role_accessions[0] if role_accessions else None,
                "last": role_accessions[-1] if role_accessions else None,
            }
            entry["normalisation"] = normalisation
            normalisations[role] = normalisation
            accessions[role] = entry["accessions"]
            element_sources[role] = (
                settings.capture.get("element_sources") or ["companyfacts"]
            )[0]
            entry["source"] = existing_sources.get(path.name) or {
                "url": (
                    "https://data.sec.gov/api/xbrl/companyfacts/"
                    f"{settings.issuer_id}.json"
                ),
                "retrieval": (
                    "the element's rows are taken from the filer's own XBRL "
                    "facts, verbatim, and re-keyed to the companyconcept shape"
                ),
                "source_document_sha256": None,
                "note": (
                    "The capture holds the rows as they were fetched; the "
                    "digests above are of the files themselves."
                ),
            }
        files[path.name] = entry
    manifest = _manifest_for(
        settings,
        output_dir,
        files,
        element_sources,
        normalisations,
        accessions,
        {},
    )
    (output_dir / MANIFEST_FILE).write_bytes(
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )
    return manifest


def _price_url(settings: IssuerSettings) -> str:
    price = settings.capture["price"]
    return (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{price['symbol']}"
        f"?period1={price['period_start_epoch']}"
        f"&period2={price['period_end_epoch']}"
        f"&interval={price['interval']}"
        f"&events={'%2C'.join(price.get('events') or ['div', 'split'])}"
    )


def _manifest_for(
    settings: IssuerSettings,
    output_dir: Path,
    files: Dict[str, Dict[str, Any]],
    element_sources: Dict[str, str],
    normalisations: Dict[str, Dict[str, Any]],
    accessions: Dict[str, Dict[str, Any]],
    substitutions: Dict[str, str],
) -> Dict[str, Any]:
    """
    The manifest, described from the files the capture holds.

    Every file's role, its unit, the accessions it carries and its digest
    are read from the capture itself, so the manifest cannot drift away from
    what it describes.
    """
    policy = settings.unit_policy
    manifest = {
        "dataset": f"{settings.ticker} research capture",
        "purpose": (
            "Research calculation lane inputs. Research use only: these files "
            "are not production inputs, they are not read by the production "
            "runner, and no figure computed from them is a production "
            "reference."
        ),
        "issuer": {
            "ticker": settings.ticker,
            "cik": settings.issuer_id,
            "entity_name": settings.entity_name,
            "fiscal_year_end": settings.fiscal_year_end,
        },
        "captured_at": settings.capture.get("captured_at", ""),
        "capture_policy": {
            "earliest_filed_date": settings.capture.get("earliest_filed_date"),
            "periodic_filings": settings.capture.get("periodic_forms"),
            "element_sources": settings.capture.get("element_sources"),
            "element_source_used": element_sources,
            "companyconcept_substitutions": substitutions,
            "context_policy": CONTEXT_POLICY,
            "dimensions": (
                "The SEC facts payloads publish only facts with no "
                "dimensional qualifiers, so every row here is a consolidated "
                "fact and the capture carries no segment or member variants."
            ),
            "unit_policy": {
                "filing_unit": policy.filing_unit,
                "filing_currency": policy.filing_currency,
                "price_currency": policy.price_currency,
                "share_unit": policy.share_unit,
                "scale": policy.scale,
                "scale_basis": policy.scale_basis,
                "fx_rule": policy.fx_rule,
            },
            "role_normalisation": normalisations,
            "accession_coverage": accessions,
        },
        "files": files,
    }
    (output_dir / MANIFEST_FILE).write_bytes(
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )
    return manifest


CONTEXT_POLICY = (
    "The SEC facts APIs publish facts without dimensional qualifiers, so every "
    "row in this capture is a fact with no dimensions. They do not publish the "
    "filing's contextRef, so each row's context is pinned by (accession, "
    "element, period, unit) with no dimensions, which identifies exactly one "
    "fact in that filing."
)


import os  # noqa: E402  (used for the path separator above)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="KO", help="the issuer to build")
    parser.add_argument(
        "--output-dir", default=None, help="where to write the capture"
    )
    parser.add_argument("--cache-dir", default=None, type=Path)
    parser.add_argument(
        "--manifest-only",
        action="store_true",
        help=(
            "write the manifest for the capture already on disk, without "
            "fetching anything"
        ),
    )
    arguments = parser.parse_args()

    settings = None
    for candidate in load_issuer_settings():
        if candidate.ticker == arguments.ticker:
            settings = candidate
            break
    if settings is None:
        raise SystemExit(f"no research issuer is configured for {arguments.ticker!r}")

    output = (
        Path(arguments.output_dir)
        if arguments.output_dir
        else ROOT / settings.capture["directory"]
    )
    if arguments.manifest_only:
        manifest = describe_capture(settings, output)
    else:
        manifest = build_capture(settings, output, arguments.cache_dir)
    print(f"the capture for {settings.ticker} is at {output}")
    for name, entry in manifest["files"].items():
        print(
            f"  {name:44s} role={entry.get('role'):30s}"
            f" unit={entry.get('unit')}  sha={entry['sha256'][:12]}"
        )


if __name__ == "__main__":
    main()
