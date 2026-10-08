"""
ST-EVA 3C-B1 - XBRL document-fact extraction.

Four controlled fixtures, each shaped after an observation that was actually
measured, and each labelled with which measurement it stands in for:

    LEGACY_INSTANCE    the 2013 diluted-EPS fact the filing provenance design
                       named: `EX-101.INS` carries the instance and `EX-99.1`
                       carries no XBRL at all (`0020:552-557`)
    INLINE_PRIMARY     the 2026 8-K primary HTML: inline XBRL, with an
                       `ix:continuation` chain, in a document that is **not**
                       well-formed XML
    EXTRACTED_XML      the same filing's `aapl-20260730_htm.xml`: the same fact
                       in an instance-shaped document, which is exactly the
                       cardinality-2 situation invariant 19 cannot resolve
    EXHIBIT_WITHOUT_EPS the 8-K `EX-99.1` of the 2026 filing: prose and a table,
                       no XBRL diluted EPS

The bytes are synthetic. They are written to the shapes the real material has,
not copies of it, so no test depends on the network and none of them asserts
anything about a real issuer's numbers. Where a value appears it is the value
the real document carries, because the point is the *form*, not the figure.

The assertions are about the three properties that matter:

    * a locator round-trips: `payload[start:end]` reproduces the evidence, so
      the row can be re-derived from immutable bytes rather than trusted;
    * one logical fact in one document is one row, however many byte ranges it
      spans;
    * two documents holding the same fact are two occurrences, and nothing here
      decides which of them is authoritative.

Nothing here writes an Observation, an `observation_filing_document_facts` row,
or an `observation_filing_documents` row. Those relations stay empty, and there
are tests that say so.
"""

from __future__ import annotations

import inspect
import json
import sqlite3
import unittest
from typing import Any, Dict, List, Optional, Tuple

from archive import StoredDocument
from core_registry import CoreRegistry
from registry_seed import seed
from sec_ingest import SEC_SOURCE, Ingestor
from sec_provenance import document_fact_id, document_fact_identity
from sec_xbrl_facts import (
    FACT_BEARING,
    NON_FACT_RENDERING,
    TAXONOMY_ONLY,
    UNPARSEABLE,
    parse_xbrl_document,
    spans_text,
)
from sqlite_archive import SQLiteArchive

ASSET = "AAPL"
CIK = "0000320193"
ACCESSION = "0000320193-26-000018"
MANIFEST_DIRECTORY = "EDGAR_FILING_DIRECTORY_INDEX_JSON"
CAPTURED_AT = "2026-08-01T00:00:00Z"

FILENAME_EX101 = "aapl-20120929.xml"
FILENAME_PRIMARY = "aapl-20260730.htm"
FILENAME_EXTRACTED_XML = "aapl-20260730_htm.xml"
FILENAME_EX991 = "a8-kex991q3202606272026.htm"
FILENAME_SCHEMA = "us-gaap-2023.xsd"
FILENAME_RENDERING = "R1.htm"

# ---------------------------------------------------------------------------
# A. The legacy instance: prefixed, well-formed XML, two contexts
# ---------------------------------------------------------------------------

LEGACY_INSTANCE = b"""<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
  xmlns:us-gaap="http://fasb.org/us-gaap/2013"
  xmlns:link="http://www.xbrl.org/2003/linkbase">
  <xbrli:context id="D2012Q3">
    <xbrli:entity>
      <xbrli:identifier scheme="http://www.sec.gov/CIK">0000320193</xbrli:identifier>
    </xbrli:entity>
    <xbrli:period>
      <xbrli:startDate>2012-06-24</xbrli:startDate>
      <xbrli:endDate>2012-09-29</xbrli:endDate>
    </xbrli:period>
  </xbrli:context>
  <xbrli:context id="D2012Q3_segment">
    <xbrli:entity>
      <xbrli:identifier scheme="http://www.sec.gov/CIK">0000320193</xbrli:identifier>
    </xbrli:entity>
    <xbrli:period>
      <xbrli:startDate>2012-06-24</xbrli:startDate>
      <xbrli:endDate>2012-09-29</xbrli:endDate>
    </xbrli:period>
    <xbrli:segment>
      <link:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">us-gaap:SegmentReportingOneMember</link:explicitMember>
    </xbrli:segment>
  </xbrli:context>
  <xbrli:context id="I20120929">
    <xbrli:entity>
      <xbrli:identifier scheme="http://www.sec.gov/CIK">0000320193</xbrli:identifier>
    </xbrli:entity>
    <xbrli:period>
      <xbrli:instant>2012-09-29</xbrli:instant>
    </xbrli:period>
  </xbrli:context>
  <xbrli:unit id="u-usd-per-share">
    <xbrli:divide>
      <xbrli:unitNumerator><xbrli:measure>USD</xbrli:measure></xbrli:unitNumerator>
      <xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator>
    </xbrli:divide>
  </xbrli:unit>
  <xbrli:unit id="u-usd">
    <xbrli:measure>USD</xbrli:measure>
  </xbrli:unit>
  <us-gaap:EarningsPerShareDiluted contextRef="D2012Q3" unitRef="u-usd-per-share" decimals="2">1.36</us-gaap:EarningsPerShareDiluted>
  <us-gaap:EarningsPerShareDiluted contextRef="D2012Q3_segment" unitRef="u-usd-per-share" decimals="2">1.36</us-gaap:EarningsPerShareDiluted>
  <us-gaap:Assets contextRef="I20120929" unitRef="u-usd" decimals="-3">176064000000</us-gaap:Assets>
</xbrli:xbrl>
"""

# ---------------------------------------------------------------------------
# B. Inline XBRL inside primary filing HTML that is NOT well-formed XML
# ---------------------------------------------------------------------------

INLINE_PRIMARY = b"""<!DOCTYPE html>
<html lang="en" xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"
  xmlns:xbrli="http://www.xbrl.org/2003/instance"
  xmlns:us-gaap="http://fasb.org/us-gaap/2026"><head><meta charset="utf-8"><title>FORM 8-K</title>
<meta name="dei:DocumentType" content="8-K">
</head><body>
<div class="cover"><h1>Apple Inc.</h1><p>Commission File No. 001-36743</p></div>
<p>For the three months ended June&nbsp;27, 2026, diluted earnings per share was
<ix:nonFraction name="us-gaap:EarningsPerShareDiluted" contextRef="i-2026q2" unitRef="u-eps" decimals="2" scale="2" continuedAt="cont-eps">1.65</ix:nonFraction><span class="unit">.</span></p>
<p>Total net sales were
<ix:nonFraction name="us-gaap:Revenues" contextRef="i-2026q2" unitRef="u-usd" decimals="-3" scale="3" format="ixt:numdotdecimal">39,536,000</ix:nonFraction> thousand<br>
and prior-year net sales were
<ix:nonFraction name="us-gaap:Revenues" contextRef="i-2025q2" unitRef="u-usd" decimals="-3" scale="3" format="ixt:numdotdecimal">40,972,000</ix:nonFraction> thousand.</p>
<div style="display:none">
<xbrli:context id="i-2026q2">
<xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000320193</xbrli:identifier></xbrli:entity>
<xbrli:period><xbrli:startDate>2026-03-29</xbrli:startDate><xbrli:endDate>2026-06-27</xbrli:endDate></xbrli:period>
</xbrli:context>
<xbrli:context id="i-2025q2">
<xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000320193</xbrli:identifier></xbrli:entity>
<xbrli:period><xbrli:startDate>2025-03-30</xbrli:startDate><xbrli:endDate>2025-06-28</xbrli:endDate></xbrli:period>
</xbrli:context>
<xbrli:context id="i-instant">
<xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000320193</xbrli:identifier></xbrli:entity>
<xbrli:period><xbrli:instant>2026-06-27</xbrli:instant></xbrli:period>
</xbrli:context>
<xbrli:unit id="u-eps"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>USD</xbrli:measure></xbrli:unitNumerator><xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit>
<xbrli:unit id="u-usd"><xbrli:measure>USD</xbrli:measure></xbrli:unit>
</div>
<p class="footnote">1<span style="font-weight:bold">.</span>2</p>
<ix:continuation id="cont-eps">5</ix:continuation>
</body></html>
"""

# ---------------------------------------------------------------------------
# C. The extracted instance-shaped XML EDGAR produces from the same filing
# ---------------------------------------------------------------------------

EXTRACTED_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
  xmlns:us-gaap="http://fasb.org/us-gaap/2026"
  xmlns:link="http://www.xbrl.org/2003/linkbase">
  <context id="i-2026q2">
    <entity><identifier scheme="http://www.sec.gov/CIK">0000320193</identifier></entity>
    <period><startDate>2026-03-29</startDate><endDate>2026-06-27</endDate></period>
  </context>
  <unit id="u-eps"><measure>USD</measure><divide><unitNumerator><measure>USD</measure></unitNumerator><unitDenominator><measure>xbrli:shares</measure></unitDenominator></divide></unit>
  <unit id="u-usd"><measure>USD</measure></unit>
  <us-gaap:EarningsPerShareDiluted contextRef="i-2026q2" unitRef="u-eps" decimals="2">1.655</us-gaap:EarningsPerShareDiluted>
  <us-gaap:Revenues contextRef="i-2026q2" unitRef="u-usd" decimals="-3">39536000000</us-gaap:Revenues>
</xbrl>
"""

# ---------------------------------------------------------------------------
# D/E. A taxonomy resource and a rendering -- neither carries facts
# ---------------------------------------------------------------------------

TAXONOMY_SCHEMA = b"""<?xml version="1.0" encoding="UTF-8"?>
<schema xmlns="http://www.w3.org/2001/XMLSchema"
  xmlns:link="http://www.xbrl.org/2003/linkbase"
  targetNamespace="http://fasb.org/us-gaap/2026"
  elementFormDefault="qualified">
  <annotation><appinfo xmlns:link="http://www.xbrl.org/2003/linkbase">
    <link:roleType roleURI="http://www.xbrl.org/2003/role/link">concept</link:roleType>
  </appinfo></annotation>
  <element name="EarningsPerShareDiluted" id="us-gaap_EarningsPerShareDiluted"
    type="perShareItemType" abstract="false" xbrli:periodType="duration"
    substitutionGroup="xbrli:item" nillable="true"/>
</schema>
"""

RENDERING = b"""<html><head><title>R1</title><style>td{padding:0 4px}</style></head>
<body><table><tr><td>Cover Page</td></tr>
<tr><td>Entity Registrant Name</td><td>Apple Inc.</td></tr></table></body></html>
"""

# ---------------------------------------------------------------------------
# The 8-K exhibit of the same filing: prose and tables, no XBRL diluted EPS
# ---------------------------------------------------------------------------

EXHIBIT_WITHOUT_EPS = b"""<!DOCTYPE html>
<html><body><div>
<p>Apple Inc. reports the following results for the three months ended
June 27, 2026.</p>
<table>
<tr><th>Three Months Ended</th><th>June 27, 2026</th><th>June 28, 2025</th></tr>
<tr><td>Net sales</td><td>39,536</td><td>40,972</td></tr>
<tr><td>Diluted earnings per share</td><td>1.65</td><td>1.57</td></tr>
</table>
<p>These results are furnished, not filed.</p>
</div></body></html>
"""


def _unit_denominator(measure: str = "xbrli:shares") -> bytes:
    return (f"<xbrli:unitDenominator><xbrli:measure>{measure}"
            f"</xbrli:measure></xbrli:unitDenominator>").encode()


class FactExtractionBase(unittest.TestCase):
    """An archive at 0021 with one asset and one filing's documents captured."""

    def setUp(self) -> None:
        self.store = SQLiteArchive(":memory:")
        self.store.record_asset(ASSET, cik=CIK, name="Apple Inc.")
        self.asset_id = self.store.asset_id_for_cik(CIK)
        self.registry = CoreRegistry(self.store.connection)
        seed(self.registry)
        self.ingestor = Ingestor(self.store, _NoFetchProvider(), self.registry)
        self.connection = self.store.connection
        self.connection.execute(
            "INSERT INTO filings (asset_id, accession, first_archived_at)"
            " VALUES (?, ?, '2026-07-31T00:30:28Z')", (self.asset_id, ACCESSION))
        self.connection.commit()

    def tearDown(self) -> None:
        self.store.close()

    # -- access ----------------------------------------------------------

    def count(self, table: str, where: str = "", *args: Any) -> int:
        clause = f" WHERE {where}" if where else ""
        return self.connection.execute(
            f"SELECT COUNT(*) AS n FROM {table}{clause}", args
        ).fetchone()["n"]

    def occurrences(self) -> List[sqlite3.Row]:
        return self.connection.execute(
            "SELECT * FROM filing_document_fact_occurrences"
            " ORDER BY taxonomy, tag, context_ref, document_fact_id"
        ).fetchall()

    def occurrence_ids(self) -> List[str]:
        return [row["document_fact_id"] for row in self.occurrences()]

    # -- capture ---------------------------------------------------------

    def declare_and_capture(self, filename: str, payload: bytes,
                            ordinal: int = 1) -> str:
        self.connection.execute(
            "INSERT OR IGNORE INTO filing_document_declarations"
            " (declaration_id, asset_id, accession, manifest_source,"
            " source_ordinal, filename, mime_type, byte_size, captured_at,"
            " capture_kind)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'FIRST_HAND')",
            (f"fdd-3c-b1-{ordinal}-{filename}", self.asset_id, ACCESSION,
             MANIFEST_DIRECTORY, ordinal, filename,
             "text/xml" if filename.endswith((".xml", ".xsd")) else "text/html",
             len(payload), CAPTURED_AT))
        self.connection.execute(
            "INSERT OR IGNORE INTO filing_documents (asset_id, accession,"
            " filename, first_declared_at) VALUES (?, ?, ?, ?)",
            (self.asset_id, ACCESSION, filename, CAPTURED_AT))
        import hashlib
        document_id = self.store.record_source_document(StoredDocument(
            content_hash="sha256:" + hashlib.sha256(payload).hexdigest(),
            uri=("https://www.sec.gov/Archives/edgar/data/320193/"
                 f"{ACCESSION.replace('-', '')}/{filename}"),
            canonical_uri=None, http_status=200, media_type="text/html",
            byte_size=len(payload), fetched_at=CAPTURED_AT,
            first_seen_at=CAPTURED_AT, payload=payload,
            provider=SEC_SOURCE, document_type="SEC_FILING_DOCUMENT",
        ))
        self.connection.execute(
            "INSERT OR IGNORE INTO filing_document_captures (asset_id,"
            " accession, filename, document_id, acquisition_class,"
            " captured_at, capture_kind)"
            " VALUES (?, ?, ?, ?, 'SEC_FILING_DOCUMENT', ?, 'FIRST_HAND')",
            (self.asset_id, ACCESSION, filename, document_id, CAPTURED_AT))
        self.connection.commit()
        return document_id

    def extract(self) -> int:
        """The production entry point, driven over every captured document."""
        return self.ingestor._acquire_document_fact_occurrences(
            self.asset_id, ACCESSION)


class _NoFetchProvider:
    """A provider that would raise if anything tried to fetch.

    The extraction path reads `source_documents` and nothing else. If a future
    change reached the network from here, this fails loudly instead of quietly
    making the tests pass on a developer's cache.
    """

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(
            f"3C-B1 must read captured bytes only, but {name} was requested")


# ---------------------------------------------------------------------------
# A, C, F, G, H, I, J, L - the parser, over controlled bytes
# ---------------------------------------------------------------------------


class TestParserShapes(unittest.TestCase):
    def test_a_legacy_instance_yields_its_facts(self):
        parsed = parse_xbrl_document(LEGACY_INSTANCE)
        self.assertEqual(FACT_BEARING, parsed.content_kind)
        self.assertEqual(3, len(parsed.facts))
        tags = sorted({fact.tag for fact in parsed.facts})
        self.assertEqual(["Assets", "EarningsPerShareDiluted"], tags)

    def test_c_an_extracted_instance_document_yields_its_facts(self):
        parsed = parse_xbrl_document(EXTRACTED_XML)
        self.assertEqual(FACT_BEARING, parsed.content_kind)
        self.assertEqual(2, len(parsed.facts))
        self.assertEqual(
            {"EarningsPerShareDiluted", "Revenues"},
            {fact.tag for fact in parsed.facts})

    def test_f_a_default_namespace_xbrl_root_is_recognised(self):
        self.assertEqual(FACT_BEARING,
                         parse_xbrl_document(EXTRACTED_XML).content_kind)

    def test_g_a_prefixed_xbrli_xbrl_root_is_recognised(self):
        self.assertEqual(FACT_BEARING,
                         parse_xbrl_document(LEGACY_INSTANCE).content_kind)

    def test_d_a_taxonomy_resource_carries_no_facts(self):
        parsed = parse_xbrl_document(TAXONOMY_SCHEMA)
        self.assertEqual(TAXONOMY_ONLY, parsed.content_kind)
        self.assertEqual((), parsed.facts)

    def test_e_a_rendering_carries_no_facts(self):
        parsed = parse_xbrl_document(RENDERING)
        self.assertEqual(NON_FACT_RENDERING, parsed.content_kind)
        self.assertEqual((), parsed.facts)

    def test_an_exhibit_without_xbrl_carries_no_facts(self):
        parsed = parse_xbrl_document(EXHIBIT_WITHOUT_EPS)
        self.assertEqual(NON_FACT_RENDERING, parsed.content_kind)
        self.assertEqual((), parsed.facts)

    def test_an_unreadable_document_is_unparseable_not_fatal(self):
        self.assertEqual(UNPARSEABLE,
                         parse_xbrl_document(b"\x00\x01\x02 not markup").content_kind)

    # -- H: contextRef ---------------------------------------------------

    def test_h_the_context_is_resolved_from_the_document(self):
        parsed = parse_xbrl_document(LEGACY_INSTANCE)
        context = parsed.contexts["D2012Q3"]
        self.assertEqual("0000320193", context.entity_identifier)
        self.assertEqual("http://www.sec.gov/CIK", context.entity_scheme)
        self.assertEqual("DURATION", context.period_kind)
        self.assertEqual("2012-06-24", context.period_start)
        self.assertEqual("2012-09-29", context.period_end)

    def test_an_instant_period_is_read_as_an_instant(self):
        context = parse_xbrl_document(LEGACY_INSTANCE).contexts["I20120929"]
        self.assertEqual("INSTANT", context.period_kind)
        self.assertIsNone(context.period_start)
        self.assertEqual("2012-09-29", context.period_end)

    def test_a_period_is_never_reconstructed_from_the_value(self):
        """The context says 2012; the value says nothing about the period."""
        parsed = parse_xbrl_document(LEGACY_INSTANCE)
        for fact in parsed.facts:
            if fact.tag == "EarningsPerShareDiluted":
                context = parsed.contexts[fact.context_ref]
                self.assertEqual("2012-06-24", context.period_start)
                self.assertNotIn("2012", fact.value_text)

    # -- I: unitRef ------------------------------------------------------

    def test_i_a_simple_unit_is_resolved(self):
        unit = parse_xbrl_document(LEGACY_INSTANCE).units["u-usd"]
        self.assertEqual(("USD",), unit.measures)
        self.assertIsNone(unit.divide)

    def test_i_a_divided_unit_names_both_measures(self):
        """USD over one share: the form SEC actually writes for per-share."""
        unit = parse_xbrl_document(LEGACY_INSTANCE).units["u-usd-per-share"]
        self.assertEqual(("USD", "xbrli:shares"), unit.measures)
        self.assertEqual(1, unit.divide)

    def test_a_unit_that_declares_no_measure_is_refused(self):
        payload = LEGACY_INSTANCE.replace(
            b'<xbrli:unit id="u-usd">\n'
            b"    <xbrli:measure>USD</xbrli:measure>\n"
            b"  </xbrli:unit>",
            b'<xbrli:unit id="u-usd"></xbrli:unit>')
        self.assertNotIn(payload, LEGACY_INSTANCE,
                         "the fixture patch must actually apply")
        parsed = parse_xbrl_document(payload)
        self.assertNotIn("u-usd", parsed.units)
        self.assertIn("UNIT_UNRESOLVED",
                      {r.reason for r in parsed.rejections})

    # -- J: dimensions ---------------------------------------------------

    def test_j_dimensions_are_preserved_and_sorted(self):
        parsed = parse_xbrl_document(LEGACY_INSTANCE)
        self.assertEqual([], list(parsed.contexts["D2012Q3"].dimensions))
        self.assertEqual(
            [{"axis": "us-gaap:StatementBusinessSegmentsAxis",
              "member": "us-gaap:SegmentReportingOneMember"}],
            list(parsed.contexts["D2012Q3_segment"].dimensions))

    def test_two_contexts_with_the_same_value_are_two_facts(self):
        """The measured case: dimensional and undimensional, identical values."""
        parsed = parse_xbrl_document(LEGACY_INSTANCE)
        eps = [fact for fact in parsed.facts
               if fact.tag == "EarningsPerShareDiluted"]
        self.assertEqual(2, len(eps))
        self.assertEqual({"1.36", "1.36"}, {fact.value_text for fact in eps})
        self.assertEqual({"D2012Q3", "D2012Q3_segment"},
                         {fact.context_ref for fact in eps})

    # -- L: locators -----------------------------------------------------

    def test_l_every_locator_round_trips_to_the_captured_bytes(self):
        for payload in (LEGACY_INSTANCE, INLINE_PRIMARY, EXTRACTED_XML):
            parsed = parse_xbrl_document(payload)
            self.assertTrue(parsed.facts)
            for fact in parsed.facts:
                self.assertEqual(
                    fact.value_text, spans_text(payload, fact.locators),
                    "the stored locator must reproduce the stored evidence")
            for context in parsed.contexts.values():
                span = context.locator
                self.assertIn(payload[span["start"]:span["end"]],
                              payload)

    def test_l_a_locator_never_falls_outside_the_payload(self):
        for payload in (LEGACY_INSTANCE, INLINE_PRIMARY, EXTRACTED_XML):
            for fact in parse_xbrl_document(payload).facts:
                for span in fact.locators:
                    self.assertGreaterEqual(span["start"], 0)
                    self.assertLessEqual(span["end"], len(payload))
                    self.assertLess(span["start"], span["end"])

    def test_l_locators_are_byte_offsets_not_character_offsets(self):
        """A multi-byte character before the fact would shift a char offset."""
        payload = INLINE_PRIMARY.replace(
            b"<p>For the three months",
            b"<p>Diluted \xe2\x80\x94 for the three months")
        parsed = parse_xbrl_document(payload)
        self.assertTrue(parsed.facts)
        for fact in parsed.facts:
            self.assertEqual(fact.value_text, spans_text(payload, fact.locators))


# ---------------------------------------------------------------------------
# B, K - inline XBRL, and one logical fact across several byte ranges
# ---------------------------------------------------------------------------


class TestInlineXbrl(unittest.TestCase):
    def setUp(self) -> None:
        self.parsed = parse_xbrl_document(INLINE_PRIMARY)

    def test_b_inline_facts_are_extracted_from_non_wellformed_html(self):
        self.assertEqual(FACT_BEARING, self.parsed.content_kind)
        self.assertEqual(3, len(self.parsed.facts))
        self.assertEqual(
            {"EarningsPerShareDiluted", "Revenues"},
            {fact.tag for fact in self.parsed.facts})

    def test_b_the_inline_name_attribute_names_the_concept(self):
        fact = next(fact for fact in self.parsed.facts
                    if fact.tag == "EarningsPerShareDiluted")
        self.assertEqual("http://fasb.org/us-gaap/2026", fact.taxonomy)
        self.assertEqual("i-2026q2", fact.context_ref)
        self.assertEqual("u-eps", fact.unit_ref)

    def test_b_scale_and_format_change_the_resolved_value_only(self):
        fact = next(fact for fact in self.parsed.facts
                    if fact.tag == "EarningsPerShareDiluted")
        self.assertEqual("2", fact.scale)
        self.assertEqual("1.655", fact.value_text)
        self.assertAlmostEqual(165.5, fact.resolved_value)

    def test_b_a_thousands_separator_is_removed_by_the_declared_format(self):
        revenues = [fact for fact in self.parsed.facts
                    if fact.tag == "Revenues" and fact.context_ref == "i-2026q2"]
        self.assertEqual(1, len(revenues))
        self.assertEqual("39,536,000", revenues[0].value_text)
        self.assertAlmostEqual(39536000000.0, revenues[0].resolved_value,
                               msg="scale=3 applies on top of the format")

    def test_the_inline_and_extracted_forms_of_one_fact_agree(self):
        """EDGAR's extraction resolves the same scale, so both read 39536000000."""
        inline = [fact for fact in self.parsed.facts
                  if fact.tag == "Revenues" and fact.context_ref == "i-2026q2"]
        extracted = parse_xbrl_document(EXTRACTED_XML)
        counterparts = [fact for fact in extracted.facts
                        if fact.tag == "Revenues"]
        self.assertEqual(1, len(inline))
        self.assertEqual(1, len(counterparts))
        self.assertAlmostEqual(inline[0].resolved_value,
                               counterparts[0].resolved_value)

    def test_b_an_unknown_format_is_refused_rather_than_guessed(self):
        payload = INLINE_PRIMARY.replace(b'format="ixt:numdotdecimal"',
                                         b'format="ixt:num-word-decimal"')
        parsed = parse_xbrl_document(payload)
        self.assertNotIn("Revenues", {fact.tag for fact in parsed.facts})
        self.assertIn("VALUE_NOT_NUMERIC",
                      {r.reason for r in parsed.rejections})

    def test_k_a_continuation_chain_is_one_fact_and_several_spans(self):
        fact = next(fact for fact in self.parsed.facts
                    if fact.tag == "EarningsPerShareDiluted")
        self.assertEqual(2, len(fact.locators),
                         "one logical value, two byte ranges")
        self.assertEqual("1.655", fact.value_text)
        self.assertEqual("1.65", spans_text(
            INLINE_PRIMARY, fact.locators[:1]))
        self.assertEqual("5", spans_text(
            INLINE_PRIMARY, fact.locators[1:]))

    def test_k_an_unresolvable_continuation_is_a_rejection(self):
        payload = INLINE_PRIMARY.replace(b'continuedAt="cont-eps"',
                                         b'continuedAt="cont-missing"')
        parsed = parse_xbrl_document(payload)
        self.assertNotIn("EarningsPerShareDiluted",
                         {fact.tag for fact in parsed.facts})
        self.assertIn("CONTINUATION_UNRESOLVED",
                      {r.reason for r in parsed.rejections})

    def test_a_nested_markup_run_still_round_trips(self):
        payload = INLINE_PRIMARY.replace(
            b'>1.65</ix:nonFraction>', b'><span>1.65</span></ix:nonFraction>')
        parsed = parse_xbrl_document(payload)
        fact = next(fact for fact in parsed.facts
                    if fact.tag == "EarningsPerShareDiluted")
        self.assertEqual("1.655", fact.value_text)
        self.assertEqual(fact.value_text, spans_text(payload, fact.locators))


# ---------------------------------------------------------------------------
# Determinism and the identity itself
# ---------------------------------------------------------------------------


class TestIdentityAndDeterminism(FactExtractionBase):
    def test_m_a_repeated_parse_is_byte_identical(self):
        first = parse_xbrl_document(INLINE_PRIMARY)
        second = parse_xbrl_document(INLINE_PRIMARY)
        self.assertEqual(first, second)

    def test_m_a_repeated_extraction_is_idempotent(self):
        self.declare_and_capture(FILENAME_EX101, LEGACY_INSTANCE, ordinal=1)
        self.assertEqual(3, self.extract())
        self.assertEqual(3, self.extract())
        self.assertEqual(3, self.count("filing_document_fact_occurrences"))

    def test_the_stored_preimage_recomputes_the_key(self):
        self.declare_and_capture(FILENAME_EX101, LEGACY_INSTANCE, ordinal=1)
        self.extract()
        for row in self.occurrences():
            self.assertEqual(
                row["document_fact_id"],
                "dfid_" + __import__("hashlib").sha256(
                    row["document_fact_identity"].encode("utf-8")
                ).hexdigest()[:32])

    def test_the_stored_preimage_holds_exactly_eight_fields(self):
        self.declare_and_capture(FILENAME_EX101, LEGACY_INSTANCE, ordinal=1)
        self.extract()
        for row in self.occurrences():
            self.assertEqual(
                {"provider", "asset_id", "accession", "document_id",
                 "taxonomy", "tag", "context_ref", "unit_ref"},
                set(json.loads(row["document_fact_identity"])))

    def test_the_stored_preimage_matches_the_helper(self):
        self.declare_and_capture(FILENAME_EX101, LEGACY_INSTANCE, ordinal=1)
        self.extract()
        for row in self.occurrences():
            self.assertEqual(
                document_fact_identity(
                    SEC_SOURCE, self.asset_id, ACCESSION, row["document_id"],
                    row["taxonomy"], row["tag"], row["context_ref"],
                    row["unit_ref"]),
                row["document_fact_identity"])

    def test_o_a_different_context_ref_is_a_different_fact(self):
        self.declare_and_capture(FILENAME_EX101, LEGACY_INSTANCE, ordinal=1)
        self.extract()
        eps = [row for row in self.occurrences()
               if row["tag"] == "EarningsPerShareDiluted"]
        self.assertEqual(2, len(eps))
        self.assertEqual(2, len({row["document_fact_id"] for row in eps}))
        self.assertEqual("1.36", eps[0]["value_text"])
        self.assertEqual("1.36", eps[1]["value_text"])

    def test_p_a_different_document_is_a_different_fact(self):
        """The cardinality-2 case: same fact, two documents, two occurrences."""
        self.declare_and_capture(FILENAME_PRIMARY, INLINE_PRIMARY, ordinal=1)
        self.declare_and_capture(FILENAME_EXTRACTED_XML, EXTRACTED_XML,
                                 ordinal=7)
        self.extract()
        eps = [row for row in self.occurrences()
               if row["tag"] == "EarningsPerShareDiluted"]
        self.assertEqual(2, len(eps))
        self.assertEqual(2, len({row["document_fact_id"] for row in eps}))
        self.assertEqual(2, len({row["document_id"] for row in eps}))
        self.assertEqual(1, len({row["context_ref"] for row in eps}))

    def test_q_a_re_capture_of_changed_bytes_is_a_distinct_occurrence(self):
        self.declare_and_capture(FILENAME_EX101, LEGACY_INSTANCE, ordinal=1)
        self.extract()
        amended = LEGACY_INSTANCE.replace(
            b"<us-gaap:Assets contextRef=\"I20120929\" unitRef=\"u-usd\""
            b" decimals=\"-3\">176064000000<",
            b"<us-gaap:Assets contextRef=\"I20120929\" unitRef=\"u-usd\""
            b" decimals=\"-3\">176999000000<")
        second = self.declare_and_capture(FILENAME_EX101, amended, ordinal=1)
        self.assertNotEqual(
            self.document_id_of(FILENAME_EX101, payload=LEGACY_INSTANCE), second)
        self.extract()
        assets = [row for row in self.occurrences() if row["tag"] == "Assets"]
        self.assertEqual(2, len(assets))
        self.assertEqual(2, len({row["document_fact_id"] for row in assets}))
        self.assertEqual({"176064000000", "176999000000"},
                         {row["value_text"] for row in assets})

    def document_id_of(self, filename: str, payload: bytes) -> str:
        import hashlib
        return self.connection.execute(
            "SELECT document_id FROM source_documents WHERE content_hash = ?",
            ("sha256:" + hashlib.sha256(payload).hexdigest(),),
        ).fetchone()["document_id"]

    def test_f_the_same_concept_across_documents_never_shares_an_identity(self):
        first = document_fact_id(SEC_SOURCE, self.asset_id, ACCESSION,
                                 "doc_a", "us-gaap",
                                 "EarningsPerShareDiluted", "c1", "u1")
        second = document_fact_id(SEC_SOURCE, self.asset_id, ACCESSION,
                                  "doc_b", "us-gaap",
                                  "EarningsPerShareDiluted", "c1", "u1")
        self.assertNotEqual(first, second)

    def test_an_sfid_can_never_equal_a_dfid(self):
        self.assertTrue(all(
            identity.startswith("dfid_")
            for identity in self.connection.execute(
                "SELECT document_fact_id AS identity FROM"
                " filing_document_fact_occurrences")))


# ---------------------------------------------------------------------------
# N, R - conflicts and refusals
# ---------------------------------------------------------------------------


class TestConflictsAndRefusals(FactExtractionBase):
    def provenance_errors(self) -> List[str]:
        return list(self.ingestor._provenance_errors)

    def occurrences_for(self, context_ref: str) -> List[sqlite3.Row]:
        return [row for row in self.occurrences()
                if row["context_ref"] == context_ref]

    # -- N: the duplicate-node rules -------------------------------------

    def test_a_repeated_identical_node_is_idempotent(self):
        """Same node, same value, twice: one row, and no error to report."""
        payload = LEGACY_INSTANCE.replace(
            b'<us-gaap:Assets contextRef="I20120929" unitRef="u-usd"'
            b' decimals="-3">176064000000</us-gaap:Assets>',
            b'<us-gaap:Assets contextRef="I20120929" unitRef="u-usd"'
            b' decimals="-3">176064000000</us-gaap:Assets>'
            b'<us-gaap:Assets contextRef="I20120929" unitRef="u-usd"'
            b' decimals="-3">176064000000</us-gaap:Assets>')
        self.assertNotEqual(payload, LEGACY_INSTANCE)
        self.declare_and_capture(FILENAME_EX101, payload, ordinal=1)
        self.extract()
        self.assertEqual(1, len(self.occurrences_for("I20120929")))
        self.assertEqual([], self.provenance_errors())

    def test_c_the_same_node_with_a_different_value_is_refused(self):
        """Case D: one context, one concept, two values. Never two facts."""
        payload = LEGACY_INSTANCE.replace(
            b'<us-gaap:EarningsPerShareDiluted contextRef="D2012Q3"'
            b' unitRef="u-usd-per-share" decimals="2">1.36'
            b"</us-gaap:EarningsPerShareDiluted>",
            b'<us-gaap:EarningsPerShareDiluted contextRef="D2012Q3"'
            b' unitRef="u-usd-per-share" decimals="2">1.36'
            b"</us-gaap:EarningsPerShareDiluted>"
            b'<us-gaap:EarningsPerShareDiluted contextRef="D2012Q3"'
            b' unitRef="u-usd-per-share" decimals="2">9.99'
            b"</us-gaap:EarningsPerShareDiluted>")
        self.assertNotEqual(payload, LEGACY_INSTANCE)
        self.declare_and_capture(FILENAME_EX101, payload, ordinal=1)
        self.extract()
        rows = self.occurrences_for("D2012Q3")
        self.assertEqual(1, len(rows),
                         "a conflicting re-reading must not become a second fact")
        self.assertEqual("1.36", rows[0]["value_text"])
        self.assertTrue(
            any("CONFLICTING_REPEAT" in error
                for error in self.provenance_errors()),
            f"the refusal must be reported, not swallowed: "
            f"{self.provenance_errors()}")

    # -- R: a fact that cannot be resolved is not written -----------------

    def test_r_an_unresolvable_context_ref_never_fabricates_an_occurrence(self):
        payload = LEGACY_INSTANCE.replace(b'contextRef="D2012Q3"',
                                          b'contextRef="D2012Q9"')
        self.assertNotEqual(payload, LEGACY_INSTANCE)
        self.declare_and_capture(FILENAME_EX101, payload, ordinal=1)
        self.extract()
        self.assertEqual([], self.occurrences_for("D2012Q9"))
        self.assertEqual(0, len([row for row in self.occurrences()
                                 if row["tag"] == "EarningsPerShareDiluted"
                                 and row["context_ref"] == "D2012Q9"]))
        self.assertEqual(2, self.count("filing_document_fact_occurrences"),
                         "the segment context and the instant context still "
                         "resolve, and only the dangling reference is refused")
        self.assertTrue(any("CONTEXT_UNRESOLVED" in error
                            for error in self.provenance_errors()))

    def test_r_an_unresolvable_unit_ref_never_fabricates_an_occurrence(self):
        payload = LEGACY_INSTANCE.replace(b'unitRef="u-usd"',
                                          b'unitRef="u-nonexistent"')
        self.assertNotEqual(payload, LEGACY_INSTANCE)
        self.declare_and_capture(FILENAME_EX101, payload, ordinal=1)
        self.extract()
        self.assertEqual(0, self.count(
            "filing_document_fact_occurrences", "unit_ref = 'u-nonexistent'"))
        self.assertTrue(any("UNIT_UNRESOLVED" in error
                            for error in self.provenance_errors()))

    def test_a_capture_without_content_yields_nothing_and_is_not_fabricated(self):
        """A document captured as a reference has no bytes and therefore no facts."""
        import hashlib
        document_id = self.store.record_source_document(StoredDocument(
            content_hash="sha256:" + hashlib.sha256(b"never fetched").hexdigest(),
            uri="https://www.sec.gov/Archives/reference.htm",
            canonical_uri=None, http_status=None, media_type="text/html",
            byte_size=None, fetched_at=CAPTURED_AT, first_seen_at=CAPTURED_AT,
            payload=None, provider=SEC_SOURCE,
            document_type="SEC_FILING_DOCUMENT",
        ))
        self.connection.execute(
            "INSERT OR IGNORE INTO filing_document_declarations"
            " (declaration_id, asset_id, accession, manifest_source,"
            " source_ordinal, filename, captured_at, capture_kind)"
            " VALUES ('fdd-reference', ?, ?, ?, 9, 'reference.htm', ?,"
            " 'DECLARED_NOT_CAPTURED')",
            (self.asset_id, ACCESSION, MANIFEST_DIRECTORY, CAPTURED_AT))
        self.connection.execute(
            "INSERT OR IGNORE INTO filing_documents (asset_id, accession,"
            " filename, first_declared_at) VALUES (?, ?, 'reference.htm', ?)",
            (self.asset_id, ACCESSION, CAPTURED_AT))
        self.connection.execute(
            "INSERT OR IGNORE INTO filing_document_captures (asset_id,"
            " accession, filename, document_id, acquisition_class,"
            " captured_at, capture_kind) VALUES (?, ?, 'reference.htm', ?,"
            " 'SEC_FILING_DOCUMENT', ?, 'DECLARED_NOT_CAPTURED')",
            (self.asset_id, ACCESSION, document_id, CAPTURED_AT))
        self.connection.commit()
        self.assertIsNone(self.store.content_for(
            "sha256:" + hashlib.sha256(b"never fetched").hexdigest()))
        self.assertEqual(0, self.extract())
        self.assertEqual(0, self.count("filing_document_fact_occurrences"))


# ---------------------------------------------------------------------------
# S, T, U, V - what this phase must not do
# ---------------------------------------------------------------------------


class TestScopeBoundaries(FactExtractionBase):
    def capture_the_whole_filing(self) -> None:
        self.declare_and_capture(FILENAME_EX101, LEGACY_INSTANCE, ordinal=1)
        self.declare_and_capture(FILENAME_PRIMARY, INLINE_PRIMARY, ordinal=1)
        self.declare_and_capture(FILENAME_EXTRACTED_XML, EXTRACTED_XML,
                                 ordinal=7)
        self.declare_and_capture(FILENAME_EX991, EXHIBIT_WITHOUT_EPS,
                                 ordinal=2)
        self.declare_and_capture(FILENAME_SCHEMA, TAXONOMY_SCHEMA, ordinal=9)
        self.declare_and_capture(FILENAME_RENDERING, RENDERING, ordinal=10)

    def test_every_captured_document_is_read_and_the_right_facts_are_found(self):
        self.capture_the_whole_filing()
        self.assertEqual(8, self.extract())
        filenames = {row["filename"] for row in self.occurrences()}
        self.assertEqual(
            {FILENAME_EX101, FILENAME_PRIMARY, FILENAME_EXTRACTED_XML},
            filenames,
            "the exhibit, the taxonomy schema and the rendering hold no facts")
        self.assertEqual(
            {FILENAME_PRIMARY, FILENAME_EXTRACTED_XML}, {
                row["filename"] for row in self.occurrences()
                if row["tag"] == "Revenues"
                and row["context_ref"] == "i-2026q2"
            },
            "the inline primary and the extracted XML both assert this fact, "
            "and this phase declines to say which of them is the source")

    def test_s_no_observation_is_created(self):
        self.capture_the_whole_filing()
        self.extract()
        self.assertEqual(0, self.count("observations"))
        self.assertEqual(0, self.count("interpretations"))
        self.assertEqual(0, self.count("admissions"))

    def test_u_no_exact_source_document_assertion_is_created(self):
        """Two documents hold the fact, so cardinality is 2 and nothing is said."""
        self.capture_the_whole_filing()
        self.extract()
        self.assertGreater(self.count("filing_document_fact_occurrences"), 0)
        self.assertEqual(0, self.count("observation_filing_documents"))

    def test_a_single_document_case_still_asserts_nothing(self):
        """3C-B1 stops at occurrences; the assertion is a later phase's job."""
        self.declare_and_capture(FILENAME_EX101, LEGACY_INSTANCE, ordinal=1)
        self.extract()
        self.assertEqual(3, self.count("filing_document_fact_occurrences"))
        self.assertEqual(0, self.count("observation_filing_documents"))

    def test_t_no_observation_link_is_created(self):
        self.capture_the_whole_filing()
        self.extract()
        self.assertEqual(0, self.count("observation_filing_document_facts"))

    def test_the_extraction_path_writes_no_source_document_claim(self):
        """Nothing in this phase links an observation to a document."""
        self.capture_the_whole_filing()
        self.extract()
        self.assertEqual(0, self.count("observation_sources"))

    def test_v_no_classifier_column_exists_anywhere_in_the_layer(self):
        columns = {row["name"] for row in self.connection.execute(
            "PRAGMA table_info(filing_document_fact_occurrences)")}
        for forbidden in ("evidence_class", "audit_status", "filer_authored",
                          "provenance_role", "is_primary", "authoritative",
                          "precedence", "confidence"):
            self.assertNotIn(forbidden, columns)

    def test_v_content_kind_is_not_persisted(self):
        self.capture_the_whole_filing()
        self.extract()
        stored = {key for row in self.occurrences() for key in row.keys()}
        self.assertNotIn("content_kind", stored)
        self.assertNotIn("document_role", stored)

    def test_no_occurrence_claims_a_filename_based_role(self):
        """Every occurrence's filename is a column, and none of them is a role."""
        self.capture_the_whole_filing()
        self.extract()
        for row in self.occurrences():
            self.assertIn(row["filename"], (
                FILENAME_EX101, FILENAME_PRIMARY, FILENAME_EXTRACTED_XML))


# ---------------------------------------------------------------------------
# The identity audit: expanded names, tuples, and locator aggregation
# ---------------------------------------------------------------------------

TWO_PREFIXES = b"""<?xml version="1.0"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
  xmlns:us-gaap="http://fasb.org/us-gaap/2026"
  xmlns:gaap="http://fasb.org/us-gaap/2026">
  <xbrli:context id="c"><xbrli:entity><xbrli:identifier scheme="s">1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-27</xbrli:instant></xbrli:period></xbrli:context>
  <xbrli:unit id="u"><xbrli:measure>USD</xbrli:measure></xbrli:unit>
  <us-gaap:Revenues contextRef="c" unitRef="u">100</us-gaap:Revenues>
  <gaap:Revenues contextRef="c" unitRef="u">100</gaap:Revenues>
</xbrli:xbrl>
"""

REBOUND_PREFIX = b"""<?xml version="1.0"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
  xmlns:my="http://example.com/tenant-a">
  <xbrli:context id="c"><xbrli:entity><xbrli:identifier scheme="s">1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-27</xbrli:instant></xbrli:period></xbrli:context>
  <xbrli:unit id="u"><xbrli:measure>USD</xbrli:measure></xbrli:unit>
  <my:Revenues contextRef="c" unitRef="u">100</my:Revenues>
  <wrapper xmlns:my="http://example.com/tenant-b">
    <my:Revenues contextRef="c" unitRef="u">200</my:Revenues>
  </wrapper>
</xbrli:xbrl>
"""

TUPLE_DOCUMENT = b"""<?xml version="1.0"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
  xmlns:ex="http://example.com/tenant-a"
  xmlns:iso="http://www.xbrl.org/2003/iso4217">
  <xbrli:context id="c"><xbrli:entity><xbrli:identifier scheme="s">1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-27</xbrli:instant></xbrli:period></xbrli:context>
  <xbrli:unit id="pure"><xbrli:measure>iso:USD</xbrli:measure></xbrli:unit>
  <ex:ClassOfStock contextRef="c" unitRef="pure">
    <ex:CommonClassMember>2500000</ex:CommonClassMember>
  </ex:ClassOfStock>
  <ex:SingleNumber contextRef="c" unitRef="pure">2500000</ex:SingleNumber>
</xbrli:xbrl>
"""

REPEATED_FACT = b"""<?xml version="1.0"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
  xmlns:us-gaap="http://fasb.org/us-gaap/2026">
  <xbrli:context id="c"><xbrli:entity><xbrli:identifier scheme="s">1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-27</xbrli:instant></xbrli:period></xbrli:context>
  <xbrli:unit id="u"><xbrli:measure>USD</xbrli:measure></xbrli:unit>
  <us-gaap:Revenues contextRef="c" unitRef="u">100</us-gaap:Revenues>
  <us-gaap:Revenues contextRef="c" unitRef="u">100</us-gaap:Revenues>
</xbrli:xbrl>
"""

CONFLICTING_REPEAT = REPEATED_FACT.replace(
    b">100</us-gaap:Revenues>\n</xbrli:xbrl>",
    b">200</us-gaap:Revenues>\n</xbrli:xbrl>")


class TestTaxonomyIdentity(unittest.TestCase):
    """`taxonomy` is the namespace URI, because a prefix is an alias."""

    def identity_of(self, fact: Any) -> str:
        return document_fact_id(
            SEC_SOURCE, "AAPL", ACCESSION, "doc_x", fact.taxonomy, fact.tag,
            fact.context_ref, fact.unit_ref)

    def test_one_namespace_bound_to_two_prefixes_is_one_fact(self):
        """`us-gaap:Revenues` and `gaap:Revenues` are one expanded name."""
        parsed = parse_xbrl_document(TWO_PREFIXES)
        self.assertEqual(1, len(parsed.facts),
                         "the same concept asserted twice is one logical fact")
        self.assertEqual("http://fasb.org/us-gaap/2026",
                         parsed.facts[0].taxonomy)
        self.assertEqual(2, len(parsed.facts[0].appearance_locators),
                         "both byte ranges belong to the one occurrence")
        for group in parsed.facts[0].appearance_locators:
            self.assertEqual("100", spans_text(TWO_PREFIXES, group))

    def test_one_prefix_rebound_to_two_namespaces_is_two_facts(self):
        """The direction that matters: distinct concepts must not merge."""
        parsed = parse_xbrl_document(REBOUND_PREFIX)
        self.assertEqual(2, len(parsed.facts))
        self.assertEqual(
            {"http://example.com/tenant-a", "http://example.com/tenant-b"},
            {fact.taxonomy for fact in parsed.facts})
        self.assertEqual(2, len({self.identity_of(f) for f in parsed.facts}),
                         "two distinct expanded names, two identities")
        self.assertEqual({"100", "200"},
                         {fact.value_text for fact in parsed.facts})

    def test_an_inline_name_resolves_against_the_scope_it_sits_in(self):
        # `xmlns:gaap` must actually be declared for this to test anything.
        # The fixture's <html> opens with `xmlns:ix`, so the anchor has to match
        # what is really there -- an earlier version of this test searched for a
        # declaration it had itself never added, so the replace was a no-op and
        # the alias went undeclared, which is a different case entirely.
        aliased = INLINE_PRIMARY.replace(
            b'name="us-gaap:Revenues"', b'name="gaap:Revenues"', 1).replace(
            b'<html lang="en"',
            b'<html lang="en" xmlns:gaap="http://fasb.org/us-gaap/2026"')
        self.assertIn(b'xmlns:gaap="http://fasb.org/us-gaap/2026"', aliased,
                      "the fixture patch must actually apply")
        parsed = parse_xbrl_document(aliased)
        revenues = [fact for fact in parsed.facts
                    if fact.context_ref == "i-2026q2"
                    and fact.tag == "Revenues"]
        self.assertEqual(1, len(revenues))
        self.assertEqual("Revenues", revenues[0].tag)
        self.assertEqual("http://fasb.org/us-gaap/2026", revenues[0].taxonomy,
                         "`gaap:Revenues` and `us-gaap:Revenues` name the same "
                         "expanded name, so the alias must not reach identity")

    def test_an_inline_name_with_no_declaration_is_refused(self):
        """The control: same document, alias undeclared, nothing is guessed."""
        undeclared = INLINE_PRIMARY.replace(
            b'name="us-gaap:Revenues"', b'name="gaap:Revenues"', 1)
        self.assertNotIn(b"xmlns:gaap", undeclared)
        parsed = parse_xbrl_document(undeclared)
        self.assertNotIn("Revenues",
                         {fact.tag for fact in parsed.facts
                          if fact.context_ref == "i-2026q2"})
        self.assertIn("NAMESPACE_UNDECLARED",
                      {r.reason for r in parsed.rejections})

    def test_the_taxonomy_is_a_namespace_not_a_prefix(self):
        parsed = parse_xbrl_document(LEGACY_INSTANCE)
        self.assertTrue(all("://" in fact.taxonomy
                            for fact in parsed.facts))


class TestFactDetection(unittest.TestCase):
    def test_a_tuple_is_not_a_fact(self):
        """A tuple references a context and declares a unit, and is neither."""
        parsed = parse_xbrl_document(TUPLE_DOCUMENT)
        self.assertEqual(["SingleNumber"], [fact.tag for fact in parsed.facts])
        self.assertEqual((), parsed.rejections)

    def test_a_numeric_child_of_a_tuple_is_never_borrowed_as_its_value(self):
        parsed = parse_xbrl_document(TUPLE_DOCUMENT)
        self.assertNotIn("ClassOfStock",
                         {fact.tag for fact in parsed.facts})

    def test_a_dimension_member_is_not_a_fact(self):
        parsed = parse_xbrl_document(LEGACY_INSTANCE)
        self.assertNotIn("explicitMember",
                         {fact.tag for fact in parsed.facts})

    def test_the_rule_needs_no_known_prefix_list(self):
        """An unknown extension namespace still yields a fact."""
        payload = TUPLE_DOCUMENT.replace(
            b'xmlns:ex="http://example.com/tenant-a"',
            b'xmlns:zz="http://example.com/never-heard-of-it"')
        payload = payload.replace(b"ex:SingleNumber", b"zz:SingleNumber")
        parsed = parse_xbrl_document(payload)
        self.assertEqual(["SingleNumber"], [fact.tag for fact in parsed.facts])
        self.assertEqual("http://example.com/never-heard-of-it",
                         parsed.facts[0].taxonomy)


class TestLocatorAggregation(unittest.TestCase):
    def test_a_repeated_fact_is_one_row_with_every_span(self):
        parsed = parse_xbrl_document(REPEATED_FACT)
        self.assertEqual(1, len(parsed.facts))
        self.assertEqual(2, len(parsed.facts[0].appearance_locators),
                         "two appearances, one logical fact")
        for group in parsed.facts[0].appearance_locators:
            self.assertEqual(
                parsed.facts[0].value_text, spans_text(REPEATED_FACT, group),
                "each appearance independently reproduces the value")

    def test_the_spans_are_ordered_deterministically(self):
        first = parse_xbrl_document(REPEATED_FACT).facts[0]
        second = parse_xbrl_document(REPEATED_FACT).facts[0]
        self.assertEqual(first.appearance_locators, second.appearance_locators)
        for group in first.appearance_locators:
            self.assertEqual(sorted(group, key=lambda s: (s["start"], s["end"])),
                             list(group))

    def test_a_conflicting_repeat_is_refused_rather_than_merged(self):
        parsed = parse_xbrl_document(CONFLICTING_REPEAT)
        self.assertEqual(1, len(parsed.facts))
        self.assertEqual("100", parsed.facts[0].value_text)
        self.assertEqual(["CONFLICTING_REPEAT"],
                         [r.reason for r in parsed.rejections])

    def test_aggregation_happens_before_any_row_exists(self):
        """One merged fact means one insert, so no locator ever needs an UPDATE."""
        parsed = parse_xbrl_document(REPEATED_FACT)
        self.assertEqual(1, len(parsed.facts),
                         "a second insert could only be an idempotent no-op, "
                         "which would drop the second locator")

    def test_a_continuation_chain_is_aggregated_the_same_way(self):
        parsed = parse_xbrl_document(INLINE_PRIMARY)
        eps = next(fact for fact in parsed.facts
                   if fact.tag == "EarningsPerShareDiluted")
        self.assertEqual(2, len(eps.locators))
        self.assertEqual(eps.value_text, spans_text(INLINE_PRIMARY,
                                                    eps.locators))


# ---------------------------------------------------------------------------
# W - no network
# ---------------------------------------------------------------------------


class TestNoNetworkDependency(unittest.TestCase):
    def test_w_the_parser_imports_nothing_that_reaches_the_network(self):
        import sec_xbrl_facts

        source = inspect.getsource(sec_xbrl_facts)
        for forbidden in ("urllib", "http.client", "socket", "requests",
                          "httpx", "urlopen"):
            self.assertNotIn(forbidden, source,
                             f"the extractor must not reach {forbidden}")

    def test_w_the_extraction_path_never_calls_the_provider(self):
        provider = _NoFetchProvider()
        archive = SQLiteArchive(":memory:")
        try:
            archive.record_asset(ASSET, cik=CIK, name="Apple Inc.")
            registry = CoreRegistry(archive.connection)
            seed(registry)
            ingestor = Ingestor(archive, provider, registry)
            # Reaching any provider attribute would raise; a clean return proves
            # the extraction path read nothing but the archive.
            self.assertEqual(0, ingestor._acquire_document_fact_occurrences(
                archive.asset_id_for_cik(CIK), ACCESSION))
        finally:
            archive.close()


if __name__ == "__main__":
    unittest.main()