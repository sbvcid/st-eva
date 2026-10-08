"""
ST-EVA Phase 1B - SEC transport and filing parsers.

Thirty assertions about `sec_provider`'s new primitives. Every fixture here is a
frozen string derived from an already-verified real SEC response, trimmed to the
structures the parsers actually read. Nothing in this file opens a socket.

What the fixtures preserve, and why they are not invented:

* the directory listing keeps EDGAR's own order and its three generated index
  artefacts, including the entries whose `size` EDGAR publishes as an **empty
  string** rather than a number;
* the SGML `<DOCUMENT>` sequence keeps a repeated `<TYPE>XML</TYPE>`, because one
  measured filing carried 62 of them and any parser that assumed a type was
  unique would fail on it;
* the header keeps `FISCAL YEAR END` behind leading tabs, two `ITEM INFORMATION`
  lines, and the **unclosed** `<ACCEPTANCE-DATETIME>` element that EDGAR actually
  writes.

The last one is why `parse_sgml_header` bounds its capture to a line: verified
against a real filing, there is no `</ACCEPTANCE-DATETIME>` anywhere in the file,
so a regex requiring a closing tag returns `None` for every real submission, and
one capturing with `[^<]*` swallows the entire rest of the header. Both failures
are silent. `test_the_acceptance_element_is_read_though_it_is_unclosed` pins the
one that is right.

The three rules these tests exist to hold:

    * `index.json` reports a **MIME type** and never an SEC `<TYPE>`; the two are
      separate vocabularies and the directory parser cannot name an exhibit.
    * the two manifests' ordinals are different sequences and are never equated.
    * nothing here infers filed from furnished, earnings from `EX-99.1`, or a fact
      from a filename. The parsers return what the resource said.
"""

from __future__ import annotations

import gzip
import io
import json
import unittest
from typing import Any, Dict, List, Optional
from unittest import mock

import sec_provider
from sec_provider import (
    ACCEPTANCE_SOURCE_SGML_HEADER,
    ARCHIVES_HOST,
    DOCUMENT_COMPANY_CONCEPT,
    DOCUMENT_FILING,
    DOCUMENT_SUBMISSIONS,
    DOCUMENT_TICKER_MAP,
    SECProvider,
    SecFilingParseError,
    content_hash_of,
    filing_directory_url,
    filing_document_url,
    full_submission_url,
    parse_filing_directory,
    parse_full_submission,
    parse_sgml_header,
)

CIK = "0000320193"
ACCESSION_2026 = "0000320193-26-000018"
ACCESSION_2013 = "0001193125-13-170623"

# --------------------------------------------------------------------------
# Frozen fixtures
# --------------------------------------------------------------------------

# Verbatim shape of https://www.sec.gov/Archives/edgar/data/320193/
# 000032019326000018/index.json -- all seventeen entries, EDGAR's order.
INDEX_JSON_2026 = json.dumps({"directory": {"item": [
    {"name": "0000320193-26-000018-index-headers.html", "type": "text.gif",
     "size": "", "last-modified": "2026-07-30 16:30:28"},
    {"name": "0000320193-26-000018-index.html", "type": "text.gif",
     "size": "", "last-modified": "2026-07-30 16:30:28"},
    {"name": "0000320193-26-000018.txt", "type": "text.gif",
     "size": "", "last-modified": "2026-07-30 16:30:28"},
    {"name": "0000320193-26-000018-xbrl.zip", "type": "compressed.gif",
     "size": "24417", "last-modified": "2026-07-30 16:30:28"},
    {"name": "a8-kex991q3202606272026.htm", "type": "text.gif",
     "size": "173484", "last-modified": "2026-07-30 16:30:28"},
    {"name": "aapl-20260730.htm", "type": "text.gif", "size": "38350",
     "last-modified": "2026-07-30 16:30:28"},
    {"name": "aapl-20260730.xsd", "type": "text.gif", "size": "3650",
     "last-modified": "2026-07-30 16:30:28"},
    {"name": "aapl-20260730_def.xml", "type": "text.gif", "size": "18144",
     "last-modified": "2026-07-30 16:30:28"},
    {"name": "aapl-20260730_g1.jpg", "type": "image2.gif", "size": "1264",
     "last-modified": "2026-07-30 16:30:28"},
    {"name": "aapl-20260730_htm.xml", "type": "text.gif", "size": "7714",
     "last-modified": "2026-07-30 16:30:28"},
    {"name": "aapl-20260730_lab.xml", "type": "text.gif", "size": "34050",
     "last-modified": "2026-07-30 16:30:28"},
    {"name": "aapl-20260730_pre.xml", "type": "text.gif", "size": "19171",
     "last-modified": "2026-07-30 16:30:28"},
    {"name": "FilingSummary.xml", "type": "text.gif", "size": "1748",
     "last-modified": "2026-07-30 16:30:28"},
    {"name": "MetaLinks.json", "type": "text.gif", "size": "23754",
     "last-modified": "2026-07-30 16:30:28"},
    {"name": "R1.htm", "type": "text.gif", "size": "55284",
     "last-modified": "2026-07-30 16:30:28"},
    {"name": "report.css", "type": "text.gif", "size": "2767",
     "last-modified": "2026-07-30 16:30:28"},
    {"name": "Show.js", "type": "text.gif", "size": "1085",
     "last-modified": "2026-07-30 16:30:28"},
]}})

SUBMISSION_2026 = (
    "<SEC-DOCUMENT>0000320193-26-000018.txt : 20260730\n"
    "<SEC-HEADER>0000320193-26-000018.hdr.sgml : 20260730\n"
    "ACCESSION NUMBER:\t\t0000320193-26-000018\n"
    "CONFORMED SUBMISSION TYPE:\t8-K\n"
    "PUBLIC DOCUMENT COUNT:\t\t14\n"
    "CONFORMED PERIOD OF REPORT:\t20260730\n"
    "ITEM INFORMATION:\t\tResults of Operations and Financial Condition\n"
    "ITEM INFORMATION:\t\tFinancial Statements and Exhibits\n"
    "FILED AS OF DATE:\t\t20260730\n"
    "DATE AS OF CHANGE:\t\t20260730\n"
    "FILER:\n"
    "\tCOMPANY DATA:\t\n"
    "\t\tCOMPANY CONFORMED NAME:\t\t\tApple Inc.\n"
    "\t\tSTANDARD INDUSTRIAL CLASSIFICATION:\tELECTRONIC COMPUTERS [3571]\n"
    "\t\tFISCAL YEAR END:\t\t\t0926\n"
    "\tFILING VALUES:\n"
    "\t\tFORM TYPE:\t\t8-K\n"
    "\t\tSEC ACT:\t\t1934 Act\n"
    "\t\tSEC FILE NUMBER:\t001-36743\n"
    "\tBUSINESS ADDRESS:\n"
    "\t\tCITY:\t\tCUPERTINO\n"
    "\tFORMER COMPANY:\n"
    "\t\tFORMER CONFORMED NAME:\tAPPLE INC\n"
    "\t\tDATE OF NAME CHANGE:\t20070109\n"
    "<ACCEPTANCE-DATETIME>20260730163028\n"
    "<DOCUMENT>\n"
    "<TYPE>8-K\n"
    "<SEQUENCE>1\n"
    "<FILENAME>aapl-20260730.htm\n"
    "<DESCRIPTION>FORM 8-K\n"
    "</DOCUMENT>\n"
    "<DOCUMENT>\n"
    "<TYPE>EX-99.1\n"
    "<SEQUENCE>2\n"
    "<FILENAME>a8-kex991q3202606272026.htm\n"
    "<DESCRIPTION>EX-99.1 Press Release\n"
    "</DOCUMENT>\n"
    "<DOCUMENT>\n"
    "<TYPE>EX-101.SCH\n"
    "<SEQUENCE>3\n"
    "<FILENAME>aapl-20260730.xsd\n"
    "<DESCRIPTION>EX-101.SCH\n"
    "</DOCUMENT>\n"
    "<DOCUMENT>\n"
    "<TYPE>GRAPHIC\n"
    "<SEQUENCE>5\n"
    "<FILENAME>aapl-20260730_g1.jpg\n"
    "<DESCRIPTION>GRAPHIC\n"
    "</DOCUMENT>\n"
    "<DOCUMENT>\n"
    "<TYPE>XML\n"
    "<SEQUENCE>6\n"
    "<FILENAME>R1.htm\n"
    "<DESCRIPTION>XML\n"
    "</DOCUMENT>\n"
)

# A 2013 filing: FISCAL YEAR END differs by month *and* day, the header lists
# `Other Events` rather than an earnings item, PUBLIC DOCUMENT COUNT is 10 while
# the sequence below is far longer, the same <TYPE>XML</TYPE> repeats, and one
# block carries no <FILENAME> at all.
SUBMISSION_2013 = (
    "<SEC-DOCUMENT>0001193125-13-170623.txt : 20130424\n"
    "ACCESSION NUMBER:\t\t0001193125-13-170623\n"
    "CONFORMED SUBMISSION TYPE:\t8-K\n"
    "PUBLIC DOCUMENT COUNT:\t\t10\n"
    "CONFORMED PERIOD OF REPORT:\t20130424\n"
    "ITEM INFORMATION:\t\tOther Events\n"
    "ITEM INFORMATION:\t\tFinancial Statements and Exhibits\n"
    "FILED AS OF DATE:\t\t20130424\n"
    "FILER:\n"
    "\tCOMPANY DATA:\t\n"
    "\t\tFISCAL YEAR END:\t\t\t0929\n"
    "<ACCEPTANCE-DATETIME>20130424170542\n"
    "<DOCUMENT>\n"
    "<TYPE>8-K\n"
    "<FILENAME>d515445d8k.htm\n"
    "<DESCRIPTION>FORM 8-K\n"
    "</DOCUMENT>\n"
    "<DOCUMENT>\n"
    "<TYPE>EX-23.1\n"
    "<FILENAME>d515445dex231.htm\n"
    "<DESCRIPTION>EX-23.1 Consent\n"
    "</DOCUMENT>\n"
    "<DOCUMENT>\n"
    "<TYPE>EX-99.1\n"
    "<FILENAME>d515445dex991.htm\n"
    "<DESCRIPTION>EX-99.1\n"
    "</DOCUMENT>\n"
    "<DOCUMENT>\n"
    "<TYPE>EX-99.2\n"
    "<FILENAME>d515445dex992.htm\n"
    "<DESCRIPTION>EX-99.2\n"
    "</DOCUMENT>\n"
    + "".join(
        f"<DOCUMENT>\n<TYPE>XML\n<FILENAME>R{n}.htm\n<DESCRIPTION>XML\n"
        "</DOCUMENT>\n" for n in (39, 54, 48)
    )
    + "<DOCUMENT>\n"
    "<TYPE>EX-101.LAB\n"
    "<DESCRIPTION>EX-101.LAB without a filename element\n"
    "</DOCUMENT>\n"
)

HTML_BODY = b"<html><body>\xff\xfe\x00 binary but served as text " \
            b"shall not be deemed filed</body></html>"


# --------------------------------------------------------------------------
# A fake response, so no test opens a socket
# --------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, body: bytes, status: int = 200,
                 headers: Optional[Dict[str, str]] = None) -> None:
        self._body = body
        self._status = status
        self.headers = headers or {}

    def read(self) -> bytes:
        return self._body

    def getcode(self) -> int:
        return self._status

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exception: Any) -> bool:
        return False


def respond_with(body: bytes, status: int = 200,
                 headers: Optional[Dict[str, str]] = None):
    return mock.patch.object(
        sec_provider.urllib.request, "urlopen",
        return_value=FakeResponse(body, status, headers),
    )


def provider() -> SECProvider:
    return SECProvider(request_interval=0.0)


# --------------------------------------------------------------------------
# 1-6. Transport
# --------------------------------------------------------------------------


class TestTransport(unittest.TestCase):
    def test_json_still_works_through_get(self):
        """`_get` is untouched: it still parses JSON and still raises otherwise."""
        with respond_with(b'{"units": {}}', headers={
            "Content-Type": "application/json",
        }):
            self.assertEqual({"units": {}},
                             provider()._get("https://data.sec.gov/x.json"))
        with self.assertRaises(ValueError):
            with respond_with(b"<html>not json</html>"):
                provider()._get("https://data.sec.gov/x.json")

    def test_bytes_work_through_fetch_bytes(self):
        with respond_with(HTML_BODY, headers={"Content-Type": "text/html"}):
            fetched = provider()._fetch_bytes(
                f"{ARCHIVES_HOST}/Archives/edgar/data/1/a.htm"
            )
        self.assertIsNotNone(fetched)
        self.assertEqual(HTML_BODY, fetched.content)
        self.assertEqual(len(HTML_BODY), fetched.byte_size)
        self.assertEqual(200, fetched.http_status)

    def test_non_json_is_accepted_by_fetch_bytes(self):
        for body in (HTML_BODY, b"ACCESSION NUMBER:\t0001", b"not json at all"):
            with respond_with(body):
                fetched = provider()._fetch_bytes("https://www.sec.gov/a.txt")
            self.assertEqual(body, fetched.content)

    def test_404_honours_allow_missing_and_otherwise_raises(self):
        import urllib.error

        error = urllib.error.HTTPError(
            "u", 404, "Not Found", {}, io.BytesIO(b"")
        )
        with mock.patch.object(
            sec_provider.urllib.request, "urlopen", side_effect=error
        ):
            self.assertIsNone(
                provider()._fetch_bytes("https://www.sec.gov/a.htm",
                                        allow_missing=True)
            )
            with self.assertRaises(urllib.error.HTTPError):
                provider()._fetch_bytes("https://www.sec.gov/a.htm")
        server_error = urllib.error.HTTPError(
            "u", 500, "Server Error", {}, io.BytesIO(b"")
        )
        with mock.patch.object(
            sec_provider.urllib.request, "urlopen", side_effect=server_error
        ):
            with self.assertRaises(urllib.error.HTTPError):
                provider()._fetch_bytes("https://www.sec.gov/a.htm",
                                        allow_missing=True)

    def test_an_empty_response_is_a_fact_not_a_failure(self):
        with respond_with(b"", headers={"Content-Type": "text/plain"}):
            fetched = provider()._fetch_bytes("https://www.sec.gov/a.htm")
        self.assertEqual(b"", fetched.content)
        self.assertEqual(0, fetched.byte_size)

    def test_the_throttle_path_is_reused_and_not_reinvented(self):
        engine = provider()
        with mock.patch.object(
            SECProvider, "_throttle", autospec=True
        ) as throttle:
            with respond_with(HTML_BODY):
                engine._fetch_bytes("https://www.sec.gov/a.htm")
        throttle.assert_called_once()

    def test_raw_bytes_are_preserved_and_hashed_uncompressed(self):
        payload = bytes(range(256))
        compressed = gzip.compress(payload)
        with respond_with(compressed, headers={
            "Content-Type": "application/octet-stream",
            "Content-Encoding": "gzip",
        }):
            fetched = provider()._fetch_bytes("https://www.sec.gov/a.bin")
        self.assertEqual(payload, fetched.content)
        self.assertEqual(content_hash_of(payload), fetched.content_hash)
        self.assertNotEqual(content_hash_of(compressed), fetched.content_hash)

    def test_the_byte_ledger_and_fetch_log_are_shared_with_get(self):
        engine = provider()
        with respond_with(b'{"a": 1}'):
            engine._get("https://data.sec.gov/x.json")
        with respond_with(HTML_BODY):
            engine._fetch_bytes(f"{ARCHIVES_HOST}/Archives/edgar/data/1/a.htm")
        self.assertEqual(2, engine.network_fetches)
        self.assertEqual(2, len(engine._documents))
        self.assertEqual(2, engine.transport_stats()["requests_made"])

    def test_a_filing_document_is_its_own_acquisition_class(self):
        self.assertEqual(
            DOCUMENT_FILING,
            sec_provider._document_type_for(
                f"{ARCHIVES_HOST}/Archives/edgar/data/320193/0000320193260/a.htm"
            ),
        )
        for uri, expected in (
            ("https://data.sec.gov/api/xbrl/companyconcept/CIK1/us-gaap/X.json",
             DOCUMENT_COMPANY_CONCEPT),
            ("https://data.sec.gov/submissions/CIK0000320193.json",
             DOCUMENT_SUBMISSIONS),
            ("https://www.sec.gov/files/company_tickers.json",
             DOCUMENT_TICKER_MAP),
        ):
            self.assertEqual(expected, sec_provider._document_type_for(uri))

    def test_uris_are_built_from_the_accession_without_its_dashes(self):
        self.assertEqual(
            f"{ARCHIVES_HOST}/Archives/edgar/data/320193/"
            "000032019326000018/index.json",
            filing_directory_url(CIK, ACCESSION_2026),
        )
        self.assertEqual(
            f"{ARCHIVES_HOST}/Archives/edgar/data/320193/"
            "000032019326000018/0000320193-26-000018.txt",
            full_submission_url(CIK, ACCESSION_2026),
        )
        self.assertEqual(
            f"{ARCHIVES_HOST}/Archives/edgar/data/320193/"
            "000032019326000018/aapl-20260730.htm",
            filing_document_url(CIK, ACCESSION_2026, "aapl-20260730.htm"),
        )


# --------------------------------------------------------------------------
# 7-11. Directory parser
# --------------------------------------------------------------------------


class TestFilingDirectoryParser(unittest.TestCase):
    def parse(self, payload: Any = INDEX_JSON_2026):
        body = payload if isinstance(payload, bytes) else payload.encode()
        return parse_filing_directory(body, "https://www.sec.gov/x/index.json")

    def test_edgars_own_order_is_preserved_and_nothing_is_sorted(self):
        parsed = self.parse()
        names = [e.filename for e in parsed.entries]
        self.assertEqual(17, len(names))
        self.assertEqual("0000320193-26-000018-index-headers.html", names[0])
        self.assertEqual("a8-kex991q3202606272026.htm", names[4])
        self.assertEqual("aapl-20260730.htm", names[5])
        self.assertEqual("Show.js", names[-1])
        self.assertEqual(
            list(range(1, 18)), [e.source_ordinal for e in parsed.entries]
        )

    def test_the_generated_index_artefacts_are_returned_like_any_other(self):
        parsed = self.parse()
        artefacts = {
            e.filename for e in parsed.entries
            if e.filename and e.filename.endswith(
                ("-index.html", "-index-headers.html", ".txt")
            )
        }
        self.assertEqual(3, len(artefacts))

    def test_an_empty_size_is_absent_and_not_a_zero_byte_document(self):
        parsed = self.parse()
        header = parsed.entries[0]
        self.assertEqual("text.gif", header.mime_type)
        self.assertIsNone(header.byte_size)
        self.assertEqual(24417, parsed.entries[3].byte_size)

    def test_a_directory_entry_cannot_carry_a_sec_document_type(self):
        """index.json does not publish one, so the object has nowhere to put it."""
        fields = {f.name for f in sec_provider.DirectoryEntry.__dataclass_fields__.values()}
        self.assertEqual(
            {"source_ordinal", "filename", "mime_type", "byte_size",
             "last_modified"}, fields,
        )
        self.assertNotIn("sec_document_type", fields)
        self.assertNotIn("evidence_class", fields)
        self.assertNotIn("audit_status", fields)

    def test_a_missing_or_empty_name_is_not_guessed(self):
        payload = json.dumps({"directory": {"item": [
            {"type": "text.gif", "size": "1"},
            {"name": "", "type": "text.gif", "size": "1"},
        ]}})
        entries = self.parse(payload).entries
        self.assertIsNone(entries[0].filename)
        self.assertEqual("", entries[1].filename)

    def test_a_malformed_or_absent_directory_is_an_explicit_error(self):
        for payload in (
            b"<html>not json</html>",
            b"[]",
            b'{"nope": 1}',
            b'{"directory": {}}',
            b'{"directory": {"item": "not a list"}}',
            b'{"directory": {"item": ["not an object"]}}',
        ):
            with self.assertRaises(SecFilingParseError, msg=repr(payload)):
                self.parse(payload)

    def test_an_empty_directory_is_a_legitimate_empty_list(self):
        parsed = self.parse(b'{"directory": {"item": []}}')
        self.assertEqual((), parsed.entries)

    def test_the_content_hash_covers_the_bytes_not_the_parse(self):
        body = INDEX_JSON_2026.encode()
        parsed = self.parse(body)
        self.assertEqual(content_hash_of(body), parsed.content_hash)


# --------------------------------------------------------------------------
# 12-17. Full submission document parser
# --------------------------------------------------------------------------


class TestFullSubmissionParser(unittest.TestCase):
    def test_the_2026_structure_parses_to_its_real_document_sequence(self):
        parsed = parse_full_submission(
            SUBMISSION_2026.encode(), "https://www.sec.gov/x.txt"
        )
        self.assertEqual(5, len(parsed.documents))
        first = parsed.documents[0]
        self.assertEqual((1, "8-K", "aapl-20260730.htm", "FORM 8-K"),
                         (first.source_ordinal, first.sec_document_type,
                          first.filename, first.description))
        self.assertEqual(
            "EX-99.1", parsed.documents[1].sec_document_type
        )
        self.assertEqual("a8-kex991q3202606272026.htm",
                         parsed.documents[1].filename)
        self.assertEqual(
            list(range(1, 6)),
            [d.source_ordinal for d in parsed.documents],
        )

    def test_the_same_type_repeats_and_the_parser_does_not_care(self):
        parsed = parse_full_submission(
            SUBMISSION_2013.encode(), "https://www.sec.gov/x.txt"
        )
        xml = [d for d in parsed.documents if d.sec_document_type == "XML"]
        self.assertEqual(3, len(xml))
        self.assertEqual(["R39.htm", "R54.htm", "R48.htm"],
                         [d.filename for d in xml])
        self.assertEqual([5, 6, 7], [d.source_ordinal for d in xml])
        self.assertEqual(8, len(parsed.documents))

    def test_a_block_without_a_filename_yields_a_declaration_with_none(self):
        parsed = parse_full_submission(
            SUBMISSION_2013.encode(), "https://www.sec.gov/x.txt"
        )
        missing = parsed.documents[-1]
        self.assertIsNone(missing.filename)
        self.assertEqual("EX-101.LAB", missing.sec_document_type)
        self.assertIsNotNone(missing.description)

    def test_the_ordinal_is_the_blocks_own_sequence_and_is_deterministic(self):
        first = parse_full_submission(SUBMISSION_2013.encode(), "u")
        second = parse_full_submission(SUBMISSION_2013.encode(), "u")
        self.assertEqual(first.documents, second.documents)

    def test_the_index_ordinal_and_the_sgml_ordinal_are_different_sequences(self):
        """Structurally separate, not merely numerically different."""
        directory_fields = set(
            sec_provider.DirectoryEntry.__dataclass_fields__
        )
        submission_fields = set(
            sec_provider.SubmissionDocument.__dataclass_fields__
        )
        self.assertEqual(
            {"source_ordinal", "filename", "mime_type", "byte_size",
             "last_modified"}, directory_fields,
        )
        self.assertEqual(
            {"source_ordinal", "sec_document_type", "filename", "description"},
            submission_fields,
        )
        # Neither object can carry the other's vocabulary, so an ordinal from one
        # can never be read as an ordinal from the other.
        self.assertIn("mime_type", directory_fields)
        self.assertNotIn("mime_type", submission_fields)
        self.assertIn("sec_document_type", submission_fields)
        self.assertNotIn("sec_document_type", directory_fields)

    def test_a_payload_without_the_marker_is_an_error_not_an_empty_list(self):
        with self.assertRaises(SecFilingParseError) as caught:
            parse_full_submission(b"<html>a filing that is not one</html>", "u")
        self.assertIn("<SEC-DOCUMENT>", str(caught.exception))

    def test_an_unclosed_document_block_is_an_error_not_a_shifted_sequence(self):
        broken = (
            "<SEC-DOCUMENT>x.txt : 20260730\n"
            "ACCESSION NUMBER:\t0001\n"
            "<DOCUMENT>\n<TYPE>8-K\n<FILENAME>a.htm\n"
            "<DOCUMENT>\n<TYPE>EX-99.1\n<FILENAME>b.htm\n</DOCUMENT>\n"
        )
        with self.assertRaises(SecFilingParseError) as caught:
            parse_full_submission(broken.encode(), "u")
        self.assertIn("closed correctly", str(caught.exception))

    def test_a_submission_declaring_no_documents_is_an_explicit_empty(self):
        parsed = parse_full_submission(
            b"<SEC-DOCUMENT>x.txt : 20260730\nACCESSION NUMBER:\t0001\n",
            "u",
        )
        self.assertEqual((), parsed.documents)
        self.assertEqual("0001", parsed.header.accession_number)

    def test_the_content_hash_covers_the_bytes_not_the_decoded_text(self):
        body = SUBMISSION_2013.encode()
        parsed = parse_full_submission(body, "u")
        self.assertEqual(content_hash_of(body), parsed.content_hash)


# --------------------------------------------------------------------------
# 18-26. SGML header parser
# --------------------------------------------------------------------------


class TestSgmlHeaderParser(unittest.TestCase):
    def setUp(self) -> None:
        self.header_2026 = parse_full_submission(
            SUBMISSION_2026.encode(), "u"
        ).header
        self.header_2013 = parse_full_submission(
            SUBMISSION_2013.encode(), "u"
        ).header

    def test_the_accession_and_the_conformed_form(self):
        self.assertEqual("0000320193-26-000018", self.header_2026.accession_number)
        self.assertEqual("8-K", self.header_2026.conformed_submission_type)

    def test_the_period_of_report_is_read_from_the_header(self):
        self.assertEqual("20260730", self.header_2026.conformed_period_of_report)

    def test_every_item_information_line_is_kept_verbatim(self):
        self.assertEqual(
            ("Results of Operations and Financial Condition",
             "Financial Statements and Exhibits"),
            self.header_2026.item_information,
        )
        self.assertEqual(2, self.header_2026.item_information_count)
        self.assertEqual("Other Events", self.header_2013.item_information[0])

    def test_filed_as_of_date_is_kept_apart_from_acceptance(self):
        self.assertEqual("20260730", self.header_2026.filed_as_of_date)
        self.assertEqual("20130424", self.header_2013.filed_as_of_date)
        self.assertNotEqual(
            self.header_2026.filed_as_of_date,
            self.header_2026.acceptance_datetime,
        )

    def test_the_acceptance_element_is_read_though_it_is_unclosed(self):
        self.assertEqual("20260730163028", self.header_2026.acceptance_datetime)
        self.assertEqual("20130424170542", self.header_2013.acceptance_datetime)
        self.assertTrue(self.header_2026.has_acceptance_datetime)

    def test_the_acceptance_value_is_labelled_as_coming_from_the_header(self):
        self.assertEqual(ACCEPTANCE_SOURCE_SGML_HEADER,
                         self.header_2026.acceptance_source)

    def test_the_acceptance_capture_does_not_swallow_the_rest_of_the_header(self):
        """The failure a `[^<]*` capture produces, pinned against."""
        self.assertNotIn("ACCESSION", self.header_2026.acceptance_datetime)
        self.assertNotIn("FILER", self.header_2026.acceptance_datetime)
        self.assertNotIn("\n", self.header_2026.acceptance_datetime)
        self.assertEqual("8-K", self.header_2026.conformed_submission_type)

    def test_the_public_document_count_is_read_as_a_number(self):
        self.assertEqual(14, self.header_2026.public_document_count)

    def test_the_document_count_is_not_a_completeness_check(self):
        """Measured: one filing declared 10 while carrying 76 blocks."""
        self.assertEqual(10, self.header_2013.public_document_count)
        self.assertEqual(8, len(parse_full_submission(
            SUBMISSION_2013.encode(), "u"
        ).documents))

    def test_the_fiscal_year_end_keeps_its_raw_four_character_form(self):
        self.assertEqual("0926", self.header_2026.fiscal_year_end)
        self.assertEqual("0929", self.header_2013.fiscal_year_end)
        self.assertNotEqual(self.header_2026.fiscal_year_end,
                            self.header_2013.fiscal_year_end)

    def test_absent_and_present_empty_are_different_answers(self):
        empty = parse_sgml_header("COMPANY CONFORMED NAME:\t\nACCESSION NUMBER:\t\n")
        absent = parse_sgml_header("SOMETHING ELSE:\tvalue\n")
        self.assertEqual("", empty.accession_number)
        self.assertIsNone(absent.accession_number)
        self.assertIsNone(empty.acceptance_datetime)
        self.assertFalse(empty.has_acceptance_datetime)

    def test_the_header_decides_nothing(self):
        fields = set(sec_provider.SubmissionHeader.__dataclass_fields__)
        for forbidden in ("evidence_class", "audit_status", "legal_status_note",
                          "item_codes", "precedence"):
            self.assertNotIn(forbidden, fields)


# --------------------------------------------------------------------------
# 27-30. Separation: the provider parses and nothing more
# --------------------------------------------------------------------------


class TestProviderSeparation(unittest.TestCase):
    def test_no_parsed_object_carries_a_classification(self):
        for cls in (sec_provider.DirectoryEntry, sec_provider.SubmissionDocument,
                    sec_provider.SubmissionHeader, sec_provider.FetchedDocument):
            fields = set(cls.__dataclass_fields__)
            for forbidden in ("evidence_class", "audit_status",
                              "legal_status_note", "sec_item", "admitted"):
                self.assertNotIn(forbidden, fields, cls.__name__)

    def test_an_8_k_item_2_02_submission_yields_no_classification(self):
        """The exact inference the design forbids, shown to be unreachable."""
        parsed = parse_full_submission(SUBMISSION_2026.encode(), "u")
        self.assertEqual("8-K", parsed.header.conformed_submission_type)
        self.assertIn("Results of Operations and Financial Condition",
                      parsed.header.item_information)
        self.assertEqual("EX-99.1", parsed.documents[1].sec_document_type)
        for obj in (parsed, parsed.header, *parsed.documents):
            self.assertFalse(
                [a for a in dir(obj) if a in
                 ("evidence_class", "audit_status", "is_furnished", "furnished")]
            )

    def test_the_provider_persists_nothing_and_holds_no_store(self):
        engine = provider()
        for attribute in ("store", "connection", "archive", "_store"):
            self.assertFalse(hasattr(engine, attribute), attribute)

    def test_parsing_leaves_the_archive_untouched(self):
        from sqlite_archive import SQLiteArchive

        archive = SQLiteArchive(":memory:")
        try:
            before = {
                table: archive.connection.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]
                for table in ("filings", "filing_declarations",
                              "filing_document_declarations",
                              "filing_documents", "filing_document_captures",
                              "filing_document_statements",
                              "filing_acceptances",
                              "observation_filing_documents")
            }
            with respond_with(INDEX_JSON_2026.encode()):
                provider().filing_directory(CIK, ACCESSION_2026)
            with respond_with(SUBMISSION_2026.encode()):
                provider().full_submission(CIK, ACCESSION_2026)
            after = {
                table: archive.connection.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]
                for table in before
            }
            self.assertEqual(before, after)
        finally:
            archive.close()

    def test_the_archives_source_registration_declares_and_does_not_write(self):
        registration = sec_provider.SEC_ARCHIVES_SOURCE_REGISTRATION
        self.assertEqual(ARCHIVES_HOST, registration["base_url"])
        self.assertEqual("NONE", registration["retains_dimensions"])
        self.assertIn("provider", registration)
        self.assertIn("source_type", registration)
        # The provider and the ingestor must agree on the provider name even
        # though neither can import the other.
        import sec_ingest

        self.assertEqual(sec_ingest.SEC_SOURCE, registration["provider"])


if __name__ == "__main__":
    unittest.main()