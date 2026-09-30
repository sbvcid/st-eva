"""
Read XBRL facts the way a bulk archive delivers them, and reconcile the two paths.

2.11 established that the incremental path costs 23.4 requests per company and
that every subsequent pass costs **zero**. It also said what was left: at
234,000 requests for ten thousand issuers, the SEC's own guidance is that bulk
archives are the right mechanism rather than that many individual calls — and
that the reconciliation between a bulk bootstrap and an incremental archive was
**documented but never exercised**. That gap is this module's whole reason to
exist, and it is the single untested step between a seventy-five-company sample
and a corpus.

## The bulk source is thin, and that is the finding

A `companyconcept` payload is *exactly* a `companyfacts` slice plus four envelope
fields — `cik`, `entityName`, `taxonomy`, `tag` — with byte-identical fact rows,
verified before anything here was written. So a bulk source does not need its own
ingestion path. It needs to read one local document per issuer and hand back the
same per-concept payload the API path would have produced. If that is all it
takes, the abstraction held; if it needs a second ingestor, it did not.

Two things do not come from companyfacts, and both are recorded rather than
papered over:

**The filing index.** `companyfacts` has no submissions index, and this source
derives one from the facts themselves: every accession that contributed a fact
becomes an accepted filing, with its form and filing date. That is a *narrower*
index than the API path's — a filing that contributed no fact we can see is
invisible here — and it is a better one for bootstrap, because every entry in it
is a filing that actually carries evidence.

**The SIC classification.** `companyfacts` does not carry it, so an issuer
classified from bulk alone is unclassified and every declared metric stays
applicable. That is the safe default, and it is exactly the situation 2.10
measured for a filer whose SIC major group the rule does not recognise. Support
for an accompanying `submissions` file is therefore part of the interface rather
than a convenience: without it, applicability is unavailable, and a reader needs
to be able to see that it is unavailable rather than infer it from a metric that
happened to come back empty.
"""

from __future__ import annotations

import glob
import gzip
import json
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sec_provider import (
    SecCompany,
    SECDocument,
    DOCUMENT_COMPANY_CONCEPT,
    content_hash_of,
    normalize_cik,
)
from data_contract import utc_now


TICKER_MAP_NAME = "tickers.json"


class BulkFactsSource:
    """
    A provider-shaped source over locally held `companyfacts` documents.

    Implements the six members `Ingestor` actually calls, and nothing more. The
    point of the exercise is that this list is the *whole* interface: a source
    that reads a nightly archive and a source that makes 23 requests per company
    are interchangeable to the archive, which is the property that makes a bulk
    bootstrap and an incremental run reconcilable at all.
    """

    def __init__(
        self,
        directory: str,
        submissions_directory: Optional[str] = None,
        label: str = "bulk",
        ticker_map: Optional[Dict[str, str]] = None,
    ) -> None:
        self.directory = directory
        self.submissions_directory = submissions_directory
        self.label = label
        self._facts: Dict[str, Dict[str, Any]] = {}
        self._submissions: Dict[str, Dict[str, Any]] = {}
        self._documents: List[SECDocument] = []
        self._document_by_concept: Dict[str, str] = {}
        self._loaded: Dict[str, Dict[str, Any]] = {}
        self.concept_fetches = 0
        self.network_fetches = 0
        self.documents_read = 0
        self._path_by_cik: Dict[str, str] = self._index()
        self._tickers = self._load_ticker_map(ticker_map)

    # -- discovery ------------------------------------------------------

    def _index(self) -> Dict[str, str]:
        """
        CIK -> path, from the files on disk.

        Matched on the `cik` *inside* each document rather than on the filename,
        because a bulk archive names files by whatever its publisher chose and a
        filename convention is a thing to discover rather than assume.
        """
        index: Dict[str, str] = {}
        for path in sorted(glob.glob(os.path.join(self.directory, "*.json"))):
            try:
                with open(path, encoding="utf-8") as handle:
                    head = json.load(handle)
            except (OSError, ValueError):
                continue
            cik = normalize_cik(head.get("cik") or "")
            if cik:
                index[cik] = path
        return index

    def available_ciks(self) -> List[str]:
        return sorted(self._path_by_cik)

    # -- the Ingestor interface ------------------------------------------

    def _load_ticker_map(
        self,
        given: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """
        Ticker to CIK, from a mapping beside the documents.

        **Not** inferred from the company name. The first version did
        `entityName.startswith(ticker)`, which resolved 2 of 12 issuers and is
        exactly the guess the API provider refuses to make: matching a name to a
        ticker attaches one issuer's filings to another, and every comparison
        after that is false.

        A bulk archive is keyed by CIK and says nothing about tickers, so the
        mapping has to come from the file that has it -- here, the same EDGAR
        company map the incremental path resolves through, written beside the
        documents when they were fetched.
        """
        if given:
            return {str(k).upper(): normalize_cik(v) for k, v in given.items()}
        path = os.path.join(self.directory, TICKER_MAP_NAME)
        if not os.path.exists(path):
            return {}
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
        return {
            str(key).upper(): normalize_cik(value)
            for key, value in (payload or {}).items()
        }

    def resolve_company(self, ticker: str) -> Optional[SecCompany]:
        """
        The issuer behind a ticker, from the mapping and nothing else.

        Returns None when the ticker is not in the map, which is a *classified*
        outcome upstream rather than an error, and is the correct answer: the
        document set does not cover this issuer, and inventing a link to the
        nearest-named document would be the one mistake that cannot be detected
        later.
        """
        ticker = str(ticker).upper().strip()
        cik = self._tickers.get(ticker)
        if cik is None or cik not in self._path_by_cik:
            return None
        facts = self._facts_for(cik)
        return SecCompany(
            ticker=ticker,
            cik=cik,
            name=str((facts or {}).get("entityName") or ""),
            exchanges=(),
        )

    def submissions(self, cik: str) -> Dict[str, Any]:
        """
        The issuer's submission history, from an accompanying file.

        `companyfacts` does not carry a SIC, and this is where that becomes
        visible rather than silent: with a submissions file the issuer is
        classified and applicability is derived; without one it is unclassified
        and every declared metric stays applicable. Both are safe and they are
        not the same answer, so the caller is told which happened.
        """
        cik = normalize_cik(cik)
        if self.submissions_directory:
            path = os.path.join(self.submissions_directory, f"{cik}.json")
            if not os.path.exists(path):
                matches = glob.glob(
                    os.path.join(self.submissions_directory, f"*{cik}*.json")
                )
                if not matches:
                    return {}
                path = matches[0]
            with open(path, encoding="utf-8") as handle:
                return json.load(handle)
        # A submissions file is absent. Say so in a shape the caller can read,
        # rather than returning the filing index or nothing: the business-model
        # derivation looks for `sic` here, finds none, and makes no ruling --
        # the safe default -- and a reader can tell *why* it made none instead of
        # inferring it from a metric that happened to come back empty.
        facts = self._facts_for(cik)
        return {
            "cik": cik,
            "entityName": (facts or {}).get("entityName"),
            "submissions_available": False,
            "derived_filing_count": len(self.filing_index(cik)),
        }

    def filing_index(self, cik: str) -> List[Dict[str, Any]]:
        """
        An index derived from the facts, one entry per accession that carries one.

        This is the material difference from the API path's index, and it is a
        difference in kind rather than in degree. An entry here is a filing that
        actually contributed a fact, so every entry earns its place; a filing that
        contributed nothing we can see is absent, which for a bootstrap is
        exactly what you want and for a diff against an API-built archive is
        something the reconciliation must classify rather than count as a
        missing filing.
        """
        facts = self._facts_for(normalize_cik(cik))
        if facts is None:
            return []
        seen: Dict[str, Dict[str, Any]] = {}
        for concepts in (facts.get("facts") or {}).values():
            for body in concepts.values():
                for rows in (body.get("units") or {}).values():
                    for row in rows:
                        accession = str(row.get("accn") or "")
                        if not accession or accession in seen:
                            continue
                        seen[accession] = {
                            "accession": accession,
                            "form": str(row.get("form") or ""),
                            "filing_date": str(row.get("filed") or ""),
                            "acceptance_datetime": str(row.get("filed") or ""),
                            "report_date": str(row.get("end") or ""),
                            "primary_document": "",
                            "is_xbrl": 1,
                        }
        return [seen[key] for key in sorted(seen)]

    def concept_history(
        self,
        cik: str,
        taxonomy: str,
        concept: str,
    ) -> Optional[Dict[str, Any]]:
        """
        The `companyconcept` payload, reconstructed from the local document.

        Four envelope fields and nothing else. The fact rows are the same bytes
        the API path would have received, which is the whole basis for expecting
        a reconciled archive rather than a merely similar one.
        """
        cik = normalize_cik(cik)
        facts = self._facts_for(cik)
        if facts is None:
            return None
        body = ((facts.get("facts") or {}).get(taxonomy) or {}).get(concept)
        if body is None:
            return None
        self.concept_fetches += 1
        payload = {
            "cik": cik,
            "entityName": facts.get("entityName"),
            "taxonomy": taxonomy,
            "tag": concept,
            "label": body.get("label"),
            "description": body.get("description"),
            "units": body.get("units") or {},
        }
        self._retain(cik, taxonomy, concept, payload)
        return payload

    def documents_for(
        self,
        taxonomy: str,
        concept: str,
    ) -> Tuple[SECDocument, ...]:
        digest = self._document_by_concept.get(f"{taxonomy}:{concept}")
        if digest is None:
            return ()
        return tuple(
            document for document in self._documents
            if document.content_hash == digest
        )

    # -- transport accounting -------------------------------------------

    def transport_stats(self) -> Dict[str, Any]:
        return {
            "source": self.label,
            "requests_made": self.network_fetches,
            "bytes_downloaded": sum(
                os.path.getsize(path)
                for path in self._path_by_cik.values()
                if os.path.exists(path)
            ),
            "documents_retained": len(self._documents),
            "issuers_held": len(self._path_by_cik),
            "documents_read": self.documents_read,
            "concept_fetches": self.concept_fetches,
            "note": (
                "A bulk source reads one local document per issuer and issues "
                "no network requests at all, so `requests_made` is zero by "
                "construction and the meaningful comparison is documents per "
                "issuer against the API path's requests per issuer."
            ),
        }

    # -- internals -------------------------------------------------------

    def _facts_for(self, cik: str) -> Optional[Dict[str, Any]]:
        cik = normalize_cik(cik)
        if cik in self._loaded:
            return self._loaded[cik]
        path = self._path_by_cik.get(cik)
        if path is None:
            return None
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
        self._loaded[cik] = payload
        # A document *read*, not a request made. Named for what it is so the
        # transport report cannot be misread as a network figure: the bulk path's
        # cost is disk and parsing, and `network_fetches` stays zero.
        self.documents_read += 1
        return payload

    def _retain(
        self,
        cik: str,
        taxonomy: str,
        concept: str,
        payload: Dict[str, Any],
    ) -> None:
        """
        Attribute a fact to the document it was actually read from.

        The API path reads it from that issuer's `companyconcept` document; the
        bulk path reads it from the `companyfacts` document. Both are honest and
        they are **not the same document**, so the two archives attribute the same
        fact to different provenance bytes. That is a real difference, it is
        expected, and the reconciliation classifies it as such rather than
        counting it as divergence -- an archive rebuilt from a different source
        would otherwise look like it disagreed with itself.
        """
        raw = json.dumps(
            {"cik": cik, "taxonomy": taxonomy, "payload": payload},
            sort_keys=True,
        ).encode("utf-8")
        digest = content_hash_of(raw)
        self._document_by_concept[f"{taxonomy}:{concept}"] = digest
        if any(
            document.content_hash == digest for document in self._documents
        ):
            return
        self._documents.append(
            SECDocument(
                content_hash=digest,
                uri=f"bulk://companyfacts/{cik}/{taxonomy}/{concept}.json",
                payload=raw,
                media_type="application/json",
                byte_size=len(raw),
                http_status=200,
                # Stamped like any other retained document, so a bulk-built
                # archive's provenance reads the same as an API-built one and a
                # reader cannot tell which path produced a row from the shape of
                # the row.
                fetched_at=utc_now(),
                provider=self.label,
                document_type=DOCUMENT_COMPANY_CONCEPT,
            )
        )

def decompress(path: str) -> str:
    """
    Handle a gzipped bulk member.

    The nightly archives ship as `.zip` and some members arrive gzipped. Reading
    the compression is here rather than in the caller so that a source built from
    an archive and one built from extracted files behave identically -- a
    difference in delivery format must not become a difference in evidence.
    """
    if path.endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return handle.read()
    with open(path, encoding="utf-8") as handle:
        return handle.read()