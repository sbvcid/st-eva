"""
ST-EVA 3C-B1 - XBRL fact extraction from already-captured filing bytes.

This module reads **one captured byte sequence** and returns the XBRL facts that
byte sequence asserts. It fetches nothing, writes nothing, and knows nothing
about which filing a document belongs to: the accession and the asset are
supplied by the caller so that the identity it helps compute can name them.

Why the parser is told nothing about the document
-------------------------------------------------

The three empirically observed forms -- a legacy `EX-101.INS` instance, inline
XBRL inside a primary filing HTML, and EDGAR's extracted `_htm.xml` -- plus
taxonomy resources and renderings all arrive in the same table
(`filing_document_captures`), and invariant 19 records that current evidence
cannot reliably separate a filer-authored document from an EDGAR-generated one.
So nothing here may look at a filename, an extension, a MIME type or an SGML
`<TYPE>`. Fact presence is decided from the bytes: a document yields facts
because the bytes contain XBRL fact structures, and yields none because they do
not.

Two parse paths, and why both are needed
----------------------------------------

Real filing HTML is not well-formed XML -- unclosed `<br>`, bare `&`,
minimised attributes -- so a strict XML parser rejects the single most important
case. An XBRL instance *is* XML, and an XML parser reports byte offsets
directly. So:

    * `xml.parsers.expat` when the bytes are well-formed XML, with namespace
      processing **off** so element names arrive exactly as the document wrote
      them;
    * `html.parser.HTMLParser` otherwise, which tolerates what real HTML does.

Both paths build the same `_Node` tree from the same raw bytes, and both take
their offsets from the payload itself -- never from a DOM node id, and never
from a line/column pair a later reader would have to re-derive.

Byte locators are evidence, never identity
------------------------------------------

`document_fact_id` deliberately excludes the locator (ADR Amendment 2 §3):
inline XBRL lets one value span several byte ranges through `ix:continuation`,
so a locator in the key would split one logical fact into several. Every span
here is a plain `{"start": int, "end": int}` pair into the **uncompressed**
captured payload -- the same byte sequence `content_hash` covers -- and the
re-check property is exact:

    "".join(payload[s:e].decode("utf-8") for s, e in spans).strip() == value_text

That is the acceptance criterion, and it is what the tests assert.

What this module refuses to do
-------------------------------

* It never reconstructs a period or a dimension from the observed value.
* It never guesses an unknown inline `format`. An unrecognised format is a
  rejection, not a parse.
* It never emits a fact whose `contextRef` or `unitRef` does not resolve.
* It never classifies a document as filer-authored or EDGAR-generated. The only
  classification here is `content_kind`, and it names *what the bytes are*
  (`FACT_BEARING`, `TAXONOMY_ONLY`, `NON_FACT_RENDERING`, `UNPARSEABLE`), which
  is a parse outcome and not a provenance role. It is not persisted: `0021` has
  no column for it, and adding one would be exactly the classifier invariant 19
  forbids.
* It extracts **numeric** facts only. `0021` declares `resolved_value REAL NOT
  NULL`, so an `ix:nonNumeric` fact or an `xbrli:stringItem` cannot be stored
  without inventing a number. They are reported as rejections instead. That is a
  schema limit this phase inherits, not a choice it made.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Sequence, Tuple
from xml.parsers import expat

from evidence_model import canonical_json
from sec_provider import xbrl_unit_to_contract_unit

#: XBRL 2.1 instance namespace. An instance document's own elements live here,
#: including a `<xbrl>` written with or without an `xbrli:` prefix -- the two are
#: the same namespace and must not be two code paths.
XBRLI_NS = "http://www.xbrl.org/2003/instance"

#: Inline XBRL 1.1. Facts are carried in the *content* of these elements.
IX_NS = "http://www.xbrl.org/2013/inlineXBRL"

#: XBRL Dimension, used only to recognise member elements.
XBRLDI_NS = "http://xbrl.org/2006/xbrldi"

#: The three prefixes the specifications fix. A declared binding always wins;
#: these are only a fallback for a document that omits the declaration, which is
#: XML namespace resolution rather than a document-type guess.
_STANDARD_PREFIXES = {
    "xbrli": XBRLI_NS,
    "ix": IX_NS,
    "xbrldi": XBRLDI_NS,
}

#: Parse outcomes. Technical statements about bytes, not provenance roles, and
#: never persisted.
FACT_BEARING = "FACT_BEARING"
TAXONOMY_ONLY = "TAXONOMY_ONLY"
NON_FACT_RENDERING = "NON_FACT_RENDERING"
UNPARSEABLE = "UNPARSEABLE"

PERIOD_INSTANT = "INSTANT"
PERIOD_DURATION = "DURATION"
PERIOD_FOREVER = "FOREVER"

#: Root local names that make an XML document a taxonomy resource rather than a
#: fact-bearing instance. `.xsd` schema files and linkbases are XML too, and
#: parsing one as if it were an instance would be a silent false positive.
TAXONOMY_ROOTS = frozenset({
    "schema", "linkbase", "labellinkbase", "presentationlinkbase",
    "calculationlinkbase", "definitionlinkbase", "footnoteslinkbase",
    "schemaset", "loc", "ref", "link", "definitionlink",
})

#: Structural instance elements: they carry context and unit, never facts.
_STRUCTURAL = frozenset({"context", "unit"})

_ATTR_RE = re.compile(rb"""([^\s=/<>"']+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")
_NAME_RE = re.compile(r"^[^\s>/]+$")

#: The closed set of inline numeric formats this parser resolves. Anything else
#: is refused rather than guessed: a wrong resolved value would be stored as
#: evidence and would look exactly like a correct one.
_INLINE_FORMATS: Dict[str, Any] = {
    "numdotdecimal": lambda text: text.replace(",", ""),
    "num-dot-decimal": lambda text: text.replace(",", ""),
    "numcommadot": lambda text: text.replace(".", "").replace(",", "."),
    "num-comma-decimal": lambda text: text.replace(".", "").replace(",", "."),
    "numspacedot": lambda text: re.sub(r"[\s]", "", text).replace(",", ""),
    "numdash": lambda text: "0",
    "zerodash": lambda text: "0",
    "fixed-zero": lambda text: text.replace(",", ""),
}


class XbrlParseError(ValueError):
    """The bytes cannot be read as XBRL or inline XBRL."""


# ---------------------------------------------------------------------------
# Byte spans
# ---------------------------------------------------------------------------


def text_spans(payload: bytes, content_start: int,
               content_end: int) -> Tuple[Dict[str, int], ...]:
    """
    Every run of character data between ``content_start`` and ``content_end``.

    Markup inside the range is stepped over rather than stripped-and-ignored, so
    each surviving run keeps its own byte offsets and the concatenated decoded
    runs reproduce the element's text exactly. One element with nested markup, or
    an `ix:continuation` chain, therefore yields several spans -- which is
    precisely what a single ``start:end`` cannot express.
    """
    spans: List[Dict[str, int]] = []
    cursor = content_start
    while cursor < content_end:
        lt = payload.find(b"<", cursor, content_end)
        if lt == -1:
            if cursor < content_end:
                spans.append({"start": cursor, "end": content_end})
            break
        if lt > cursor:
            spans.append({"start": cursor, "end": lt})
        gt = payload.find(b">", lt, content_end)
        if gt == -1:
            # A '<' with no '>' inside the range is not markup; keep the rest as
            # text rather than silently dropping it.
            spans.append({"start": lt, "end": content_end})
            break
        cursor = gt + 1
    return tuple(spans)


def spans_text(payload: bytes,
               spans: Sequence[Dict[str, int]]) -> str:
    """The exact re-check property for a locator: decode, concatenate, strip."""
    return "".join(
        payload[span["start"]:span["end"]].decode("utf-8", "replace")
        for span in spans
    ).strip()


def _start_tag_end(payload: bytes, lt_index: int) -> int:
    """The byte offset just past the start tag beginning at ``lt_index``.

    A quoted attribute value may contain `>`, so the scan tracks quotes instead
    of trusting the first `>`.
    """
    index = lt_index + 1
    quote: Optional[int] = None
    while index < len(payload):
        byte = payload[index:index + 1]
        if quote is not None:
            if byte[0] == quote:
                quote = None
        elif byte in (b'"', b"'"):
            quote = byte[0]
        elif byte == b">":
            return index + 1
        index += 1
    raise XbrlParseError(f"unterminated start tag at byte {lt_index}")


def _attributes(tag_bytes: bytes) -> Dict[str, str]:
    """Attributes as the document wrote them, names and values untouched.

    `HTMLParser` lower-cases names and hands back unescaped values, neither of
    which is acceptable for an identity that has to be reproducible from the
    stored bytes, so the raw tag is re-read here.
    """
    found: Dict[str, str] = {}
    for match in _ATTR_RE.finditer(tag_bytes):
        name = match.group(1).decode("utf-8", "replace")
        raw = match.group(2) if match.group(2) is not None else match.group(3)
        found[name] = raw.decode("utf-8", "replace")
    return found


# ---------------------------------------------------------------------------
# The intermediate tree
# ---------------------------------------------------------------------------


@dataclass
class _Node:
    """One element, positioned in the captured payload."""

    tag: str = ""
    attrs: Dict[str, str] = field(default_factory=dict)
    start: int = 0
    content_start: int = 0
    content_end: int = 0
    end: int = 0
    self_closing: bool = False
    children: List["_Node"] = field(default_factory=list)
    spans: Tuple[Dict[str, int], ...] = ()
    text: str = ""

    def locator(self) -> Dict[str, int]:
        return {"start": self.start, "end": self.end}

    def inner(self) -> Tuple["_Node", ...]:
        return tuple(self.children)


def _seal(payload: bytes, node: _Node) -> None:
    node.spans = text_spans(payload, node.content_start, node.content_end)
    node.text = spans_text(payload, node.spans)


def _split_qname(name: str) -> Tuple[str, str]:
    """`(prefix, local)` for a qualified name; `("", name)` when there is no colon.

    `partition` alone would report an unprefixed name as its own prefix, which
    makes an unprefixed `<context>` look like a prefixed one -- and a default-
    namespace instance is exactly the form where that would go wrong.
    """
    prefix, separator, local = name.partition(":")
    return (prefix, local) if separator else ("", name)


def _walk(node: _Node) -> List[_Node]:
    found: List[_Node] = [node]
    for child in node.children:
        found.extend(_walk(child))
    return found


# ---------------------------------------------------------------------------
# Path 1: well-formed XML, parsed with expat
# ---------------------------------------------------------------------------


def _parse_xml(payload: bytes) -> Optional[_Node]:
    """
    Build the tree from well-formed XML, or return None if it is not XML.

    Namespace processing stays **off**, so a start element reports the qualified
    name exactly as written -- `us-gaap:Revenues`, or an unprefixed tag under a
    default namespace. Resolving prefixes is left to the caller, which is the
    only place that can see the `xmlns` declarations and say what a prefix means.
    """
    roots: List[_Node] = []
    stack: List[_Node] = []
    broken: List[str] = []

    parser = expat.ParserCreate()
    parser.buffer_text = True

    def start(name: str, attrs: Dict[str, str]) -> None:
        index = parser.CurrentByteIndex
        node = _Node(tag=name, attrs=dict(attrs), start=index)
        try:
            node.content_start = _start_tag_end(payload, index)
        except XbrlParseError:
            broken.append(name)
            return
        node.content_end = node.content_start
        node.end = node.content_start
        if stack:
            stack[-1].children.append(node)
        else:
            roots.append(node)
        stack.append(node)

    def end(_name: str) -> None:
        if not stack:
            return
        node = stack.pop()
        index = parser.CurrentByteIndex
        if index <= node.content_start:
            # expat reports the same index for `<a/>`: there is no content.
            node.self_closing = True
            _seal(payload, node)
            return
        node.content_end = index
        node.end = _start_tag_end(payload, index)
        _seal(payload, node)

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    try:
        parser.Parse(payload, True)
    except expat.ExpatError:
        return None
    if broken or not roots:
        return None
    return roots[0]


# ---------------------------------------------------------------------------
# Path 2: everything else, parsed with HTMLParser
# ---------------------------------------------------------------------------


class _TolerantTreeBuilder(HTMLParser):
    """
    The same `_Node` tree out of a document that is not well-formed XML.

    `HTMLParser` lower-cases names, rewrites entities and reports line/column
    positions, so none of those are used. Each start tag's *raw* source text is
    re-located in the payload by a monotonic forward scan, which is exact and
    cannot drift onto a later identical tag.
    """

    def __init__(self, payload: bytes) -> None:
        super().__init__(convert_charrefs=False)
        self._payload = payload
        self._cursor = 0
        self._root: Optional[_Node] = None
        self._stack: List[_Node] = []

    def _open(self, self_closing: bool) -> None:
        raw = (self.get_starttag_text() or "").encode("utf-8", "replace")
        start = self._payload.find(raw, self._cursor)
        if start == -1:
            start = self._cursor
        self._cursor = start
        body = raw[1:].decode("utf-8", "replace")
        if body.endswith(">"):
            body = body[:-1]
        tag = body.split(None, 1)[0].rstrip("/") if body.strip() else ""
        node = _Node(
            tag=tag,
            attrs=_attributes(raw),
            start=start,
            content_start=start + len(raw),
            content_end=start + len(raw),
            end=start + len(raw),
            self_closing=self_closing,
        )
        if self._stack:
            self._stack[-1].children.append(node)
        elif self._root is None:
            self._root = node
        self._stack.append(node)

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        self._open(False)

    def handle_startendtag(self, tag: str, attrs: Any) -> None:
        self._open(True)
        if self._stack:
            self._stack.pop()

    def handle_endtag(self, tag: str) -> None:
        if not self._stack:
            return
        node = self._stack.pop()
        # The node's own tag, not `tag`: `HTMLParser` lower-cases what it
        # reports, and `</ix:nonFraction>` must be found as the document wrote it.
        closing = f"</{node.tag}".encode("utf-8", "replace")
        index = self._payload.find(closing, self._cursor)
        if index == -1:
            index = node.content_start
        gt = self._payload.find(b">", index)
        node.content_end = index
        node.end = gt + 1 if gt != -1 else index
        self._cursor = max(self._cursor, node.end)
        _seal(self._payload, node)

    def unknown_decl(self, data: str) -> None:
        # A CDATA section carries character data like markup does; its bytes are
        # inside the current element's range and `text_spans` already steps over
        # the delimiters, so nothing extra is recorded here.
        return


def _parse_tolerant(payload: bytes) -> Optional[_Node]:
    builder = _TolerantTreeBuilder(payload)
    try:
        builder.feed(payload.decode("utf-8", "replace"))
        builder.close()
    except Exception:  # noqa: BLE001 - malformed input is a parse outcome
        return None
    return builder._root


# ---------------------------------------------------------------------------
# Resolved pieces
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class XbrlContext:
    context_ref: str
    entity_identifier: str
    entity_scheme: Optional[str]
    period_kind: str
    period_start: Optional[str]
    period_end: Optional[str]
    dimensions: Tuple[Dict[str, Any], ...]
    locator: Dict[str, int]


@dataclass(frozen=True)
class XbrlUnit:
    unit_ref: str
    measures: Tuple[str, ...]
    divide: Optional[int]
    locator: Dict[str, int]


@dataclass(frozen=True)
class XbrlFact:
    """One logical fact, already checked for a resolvable context and unit."""

    taxonomy: str
    tag: str
    context_ref: str
    unit_ref: str
    value_text: str
    resolved_value: float
    sign: Optional[str]
    scale: Optional[str]
    format_: Optional[str]
    decimals: Optional[str]
    language: Optional[str]
    locators: Tuple[Dict[str, int], ...]
    #: One group per *appearance* of this fact in the document. A single
    #: appearance -- even one split across an `ix:continuation` chain -- is one
    #: group; a fact stated in two separate elements is two. Each group
    #: independently reproduces `value_text`, which is why the payload is a list
    #: of groups and not a flat span list: flattening them would concatenate two
    #: copies of the value and no longer round-trip to it.
    appearance_locators: Tuple[Tuple[Dict[str, int], ...], ...] = ()


@dataclass(frozen=True)
class XbrlRejection:
    """A fact-shaped structure that is not stored, and the reason."""

    taxonomy: str
    tag: str
    context_ref: Optional[str]
    reason: str


@dataclass(frozen=True)
class XbrlDocument:
    content_kind: str
    contexts: Dict[str, XbrlContext]
    units: Dict[str, XbrlUnit]
    facts: Tuple[XbrlFact, ...]
    rejections: Tuple[XbrlRejection, ...]

    def dimensions_json(self, context_ref: str) -> str:
        return canonical_json(list(self.contexts[context_ref].dimensions))

    def unit_measures_json(self, unit_ref: str) -> str:
        unit = self.units[unit_ref]
        return canonical_json({"measures": list(unit.measures),
                               "divide": unit.divide})

    def context_locator_json(self, context_ref: str) -> str:
        return canonical_json([self.contexts[context_ref].locator])

    def unit_locator_json(self, unit_ref: str) -> str:
        return canonical_json([self.units[unit_ref].locator])

    def locators_json(self, fact: XbrlFact) -> str:
        """
        The recorded locator payload: one group per appearance of the fact.

        Every group independently reproduces `value_text`, so the payload is
        verifiable span by span against the captured bytes rather than only in
        aggregate.
        """
        groups = fact.appearance_locators or (fact.locators,)
        return canonical_json([list(group) for group in groups])


# ---------------------------------------------------------------------------
# Reading contexts and units
# ---------------------------------------------------------------------------


def _read_context(node: _Node) -> Optional[XbrlContext]:
    """One `xbrli:context`, or None when it does not say enough to be usable."""
    context_ref = node.attrs.get("id")
    if not context_ref:
        return None
    children = node.inner()

    entity = _find_local(children, "entity")
    identifier = None
    if entity is not None:
        identifier = _find_local(entity.inner(), "identifier")
    if identifier is None or not identifier.text:
        return None

    period = _find_local(children, "period")
    period_kind = PERIOD_FOREVER
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    if period is not None:
        inside = period.inner()
        if _find_local(inside, "forever") is not None:
            period_kind = PERIOD_FOREVER
        else:
            instant = _find_local(inside, "instant")
            start_node = _find_local(inside, "startDate")
            end_node = _find_local(inside, "endDate")
            if instant is not None:
                period_kind = PERIOD_INSTANT
                period_end = instant.text or None
            elif start_node is not None and end_node is not None:
                period_kind = PERIOD_DURATION
                period_start = start_node.text or None
                period_end = end_node.text or None
            else:
                # A period that declares neither shape cannot be reproduced.
                return None

    dimensions: List[Dict[str, Any]] = []
    for holder in children:
        if _split_qname(holder.tag)[1] not in ("segment", "scenario"):
            continue
        for member in _walk(holder)[1:]:
            member_local = _split_qname(member.tag)[1]
            axis = member.attrs.get("dimension")
            if member_local == "explicitMember":
                if axis is None:
                    return None
                dimensions.append({"axis": axis, "member": member.text})
            elif member_local == "typedMember":
                if axis is None:
                    return None
                dimensions.append({"axis": axis,
                                   "typed": member.text or None})
    dimensions.sort(key=lambda entry: (entry["axis"], entry.get("member") or "",
                                       entry.get("typed") or ""))

    return XbrlContext(
        context_ref=context_ref,
        entity_identifier=identifier.text,
        entity_scheme=identifier.attrs.get("scheme"),
        period_kind=period_kind,
        period_start=period_start,
        period_end=period_end,
        dimensions=tuple(dimensions),
        locator=node.locator(),
    )


def _read_unit(node: _Node) -> Optional[XbrlUnit]:
    """One `xbrli:unit`, or None when it does not name a measure.

    A measure is nested inside `unitNumerator`/`unitDenominator` under a
    `divide`, so the whole subtree is searched rather than the direct children
    only. A `divide` that does not declare both halves is malformed and is
    refused rather than half-read.
    """
    unit_ref = node.attrs.get("id")
    if not unit_ref:
        return None
    divide_node = _find_local(node.inner(), "divide")
    if divide_node is None:
        measures = tuple(
            child.text for child in _walk(node)[1:]
            if _split_qname(child.tag)[1] == "measure" and child.text
        )
        if not measures:
            return None
        return XbrlUnit(unit_ref=unit_ref, measures=measures, divide=None,
                        locator=node.locator())

    numerator = _find_local(divide_node.inner(), "unitNumerator")
    denominator = _find_local(divide_node.inner(), "unitDenominator")
    if numerator is None or denominator is None:
        return None
    top = _measure_texts(numerator)
    bottom = _measure_texts(denominator)
    if len(top) != 1 or len(bottom) != 1:
        return None
    return XbrlUnit(unit_ref=unit_ref, measures=(top[0], bottom[0]),
                    # `xbrli:divide` carries no integer: the divisor is 1 and the
                    # ratio is expressed by the two measures themselves.
                    divide=1, locator=node.locator())


def _measure_texts(node: _Node) -> Tuple[str, ...]:
    return tuple(
        child.text for child in _walk(node)[1:]
        if _split_qname(child.tag)[1] == "measure" and child.text
    )


def _find_local(nodes: Sequence[_Node], local: str) -> Optional[_Node]:
    for node in nodes:
        if _split_qname(node.tag)[1] == local:
            return node
    return None


# ---------------------------------------------------------------------------
# Value resolution
# ---------------------------------------------------------------------------


def _resolve_inline_value(raw: str, sign: Optional[str],
                          scale: Optional[str],
                          format_: Optional[str]) -> Optional[float]:
    """
    Resolve an inline numeric value, or return None rather than guess.

    An unrecognised `format` is a refusal. A scale that is not an integer, or a
    cleaned value that is not a number, is a refusal. Nothing falls back to
    `float()` of the untouched string, because that would silently read a
    comma-decimal European value as a thousands-separated one.
    """
    text = raw.strip()
    if format_:
        token = format_.split(":")[-1].lower()
        formatter = _INLINE_FORMATS.get(token)
        if formatter is None:
            return None
        text = formatter(text)
    exponent = 0
    if scale is not None and scale != "":
        try:
            exponent = int(scale)
        except ValueError:
            return None
    cleaned = text.replace(",", "").strip() if "," in text else text.strip()
    if cleaned in ("", "-"):
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if sign == "-":
        value = -abs(value)
    return value * (10 ** exponent) if exponent else value


def _resolve_instance_value(raw: str) -> Optional[float]:
    """An instance numeric element already holds a number; nothing to scale."""
    text = raw.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# The entry point
# ---------------------------------------------------------------------------


def _declared_namespaces(node: _Node) -> Dict[str, str]:
    """The `xmlns` bindings an element declares for itself."""
    declared: Dict[str, str] = {}
    for name, value in node.attrs.items():
        if name == "xmlns":
            declared[""] = value
        elif name.startswith("xmlns:"):
            declared[name[6:]] = value
    return declared


def _scoped_walk(root: _Node) -> List[Tuple[_Node, Dict[str, str]]]:
    """
    Every element, paired with the namespace bindings **in scope at that element**.

    Scope matters and a flat root-level map gets it wrong in both directions. A
    prefix bound twice in one document (`xmlns:my=".../a"` on the root and
    `xmlns:my=".../b"` inside a wrapper) names two different expanded names, and a
    root-only map would give both the root's binding -- merging two distinct
    concepts into one identity. XML allows a prefix to be rebound, so the bindings
    have to travel down the tree rather than be collected once at the top.
    """
    pairs: List[Tuple[_Node, Dict[str, str]]] = []

    def visit(node: _Node, inherited: Dict[str, str]) -> None:
        scope = inherited
        own = _declared_namespaces(node)
        if own:
            scope = dict(inherited)
            scope.update(own)
        pairs.append((node, scope))
        for child in node.children:
            visit(child, scope)

    visit(root, {})
    return pairs


def _resolve_prefix(prefix: str, namespaces: Dict[str, str]) -> Optional[str]:
    """
    The namespace a prefix is bound to.

    A declared binding always wins. The three standard XBRL prefixes are
    recognised even when a document omits the declaration, because those
    spellings are fixed by the specifications rather than by any filing: this is
    XML namespace resolution, not a document-type guess, and it has nothing to
    do with filenames or authorship.
    """
    return namespaces.get(prefix) or _STANDARD_PREFIXES.get(prefix)


def _is_inline(node: _Node, namespaces: Dict[str, str]) -> bool:
    prefix, local = _split_qname(node.tag)
    if prefix:
        return _resolve_prefix(prefix, namespaces) == IX_NS and local in (
            "nonFraction", "nonNumeric")
    return namespaces.get("", IX_NS) == IX_NS and local in (
        "nonFraction", "nonNumeric")


def _is_structural(node: _Node, namespaces: Dict[str, str]) -> bool:
    """A `xbrli:context` or `xbrli:unit`, and nothing merely named like one."""
    prefix, local = _split_qname(node.tag)
    if local not in _STRUCTURAL:
        return False
    if prefix:
        return _resolve_prefix(prefix, namespaces) == XBRLI_NS
    return namespaces.get("") == XBRLI_NS


def _is_instance_fact(node: _Node, namespaces: Dict[str, str]) -> bool:
    """
    Whether a tag names an XBRL fact.

    Two structural conditions, neither of which is a namespace allow-list:

    * it declares `contextRef`. An XBRL fact is by definition an item that
      references a reporting context, and nothing else in an instance does. That
      is what excludes `<link:explicitMember>` dimension members, footnote links
      and role declarations, all of which carry plenty of other attributes.

    * it has **no child elements**. This is what excludes a tuple: a tuple also
      references a context and also declares a unit, but it is a container, not a
      value. Without this, a tuple's own text is the concatenation of its
      descendants', and a tuple holding one numeric child reads as a fact with
      that child's number -- a fabricated fact whose value came from somewhere
      else entirely.

    The taxonomy check is a *rejection* of the two structural namespaces, not an
    enumeration of the ones that count: a fact may live in any extension
    namespace, so any list would be both incomplete and fixture-driven.
    """
    prefix, local = _split_qname(node.tag)
    if not local or _is_structural(node, namespaces):
        return False
    if not node.attrs.get("contextRef"):
        return False
    if node.children:
        return False
    if prefix:
        bound = _resolve_prefix(prefix, namespaces)
        return bound not in (None, XBRLI_NS, IX_NS)
    return namespaces.get("") == XBRLI_NS


def _qualify(node: _Node, namespaces: Dict[str, str]) -> Tuple[str, str]:
    """
    The expanded name of an instance element: namespace URI and local name.

    The **namespace URI** is the identity, not the prefix, because a prefix is an
    alias the document chose and XML does not treat it as significant. Both
    failure modes are real and were reproduced before this was decided:

    * one namespace bound to two prefixes (`us-gaap:` and `gaap:` for
      `http://fasb.org/us-gaap/2026`) -- a prefix-keyed identity splits one
      concept into two;
    * one prefix rebound to two namespaces in different scopes
      (`xmlns:my=".../a"` on the root, `xmlns:my=".../b"` inside a wrapper) -- a
      prefix-keyed identity *merges* two distinct concepts into one `dfid_`,
      which is the worse direction: the five-column uniqueness index then reads
      two real facts as a duplicate node.

    The URI is not disqualified by taxonomies republishing a namespace each year.
    That argument was wrong when it was first made: `document_id` is already in the
    preimage, so a 2023 fact and a 2024 fact have different identities whatever the
    taxonomy field says, and identity granularity is per captured document.

    The trade is accepted knowingly: `taxonomy` here is a URI while the archive's
    concept vocabulary elsewhere is `us-gaap:Tag`. That is fine because `dfid_` and
    `sfid_` are different grains and are never joined; joining a `dfid_` to the
    registry will need a prefix-to-URI mapping, which belongs to the registry.
"""
    prefix, local = _split_qname(node.tag)
    if prefix:
        # Only a *declared* binding may name a taxonomy. The standard-prefix
        # fallback exists for `xbrli`/`ix`/`xbrldi`, whose spellings the
        # specifications fix; an arbitrary prefix the document never bound is
        # not a name for anything, and substituting the prefix text here would
        # smuggle an alias back into the identity that Amendment 3 removed --
        # and it would never compare equal to the URI another document binds,
        # so the same concept would split by spelling.
        return namespaces.get(prefix), local
    return namespaces.get("", "") or XBRLI_NS, local


def _inline_qname(raw: Optional[str],
                  namespaces: Dict[str, str]) -> Optional[Tuple[str, str]]:
    """
    The expanded name in an inline fact's `name` attribute.

    A QName written in an attribute is resolved against the bindings in scope
    where the element sits, exactly as an element's own name is, so a concept
    asserted inline and the same concept asserted in an instance of the same
    document share a taxonomy. An unprefixed value resolves against the default
    namespace.
    """
    if not raw or ":" not in raw:
        return None
    prefix, _, local = raw.partition(":")
    if not prefix or not local:
        return None
    return namespaces.get(prefix), local


def parse_xbrl_document(payload: bytes) -> XbrlDocument:
    """
    Read one captured byte sequence and return what it asserts.

    `content_kind` is a parse outcome, never a provenance role:

        FACT_BEARING       at least one fact with a resolvable context and unit
        TAXONOMY_ONLY      a taxonomy resource: schema, linkbase, no facts
        NON_FACT_RENDERING parses, declares no XBRL facts, holds no taxonomy root
        UNPARSEABLE        the bytes are not readable as XML or as HTML

    A fact whose context or unit does not resolve is a *rejection*, not a fact
    and not an error: it is recorded with a reason so the caller can report it
    under the frozen run-level failure semantics.
    """
    root = _parse_xml(payload)
    if root is None:
        root = _parse_tolerant(payload)
    if root is None:
        return XbrlDocument(UNPARSEABLE, {}, {}, (), ())

    scoped = _scoped_walk(root)
    nodes = [node for node, _ in scoped]

    contexts: Dict[str, XbrlContext] = {}
    units: Dict[str, XbrlUnit] = {}
    for node, namespaces in scoped:
        if not _is_structural(node, namespaces):
            continue
        local = _split_qname(node.tag)[1]
        if local == "context":
            context = _read_context(node)
            if context is not None:
                contexts[context.context_ref] = context
        elif local == "unit":
            unit = _read_unit(node)
            if unit is not None:
                units[unit.unit_ref] = unit

    facts: List[XbrlFact] = []
    rejections: List[XbrlRejection] = []

    for node, namespaces in scoped:
        if _is_structural(node, namespaces):
            continue
        if _is_inline(node, namespaces):
            recorded = _read_inline_fact(node, nodes, namespaces, contexts,
                                         units, rejections)
            if recorded is not None:
                facts.append(recorded)
            continue
        if not _is_instance_fact(node, namespaces):
            continue
        taxonomy, tag = _qualify(node, namespaces)
        context_ref = node.attrs.get("contextRef")
        unit_ref = node.attrs.get("unitRef")
        if not taxonomy:
            rejections.append(XbrlRejection(tag, tag, context_ref,
                                            "NAMESPACE_UNDECLARED"))
            continue
        if not context_ref or context_ref not in contexts:
            rejections.append(XbrlRejection(taxonomy, tag, context_ref,
                                            "CONTEXT_UNRESOLVED"))
            continue
        if not unit_ref or unit_ref not in units:
            rejections.append(XbrlRejection(taxonomy, tag, context_ref,
                                            "UNIT_UNRESOLVED"))
            continue
        resolved = _resolve_instance_value(node.text)
        if resolved is None:
            rejections.append(XbrlRejection(taxonomy, tag, context_ref,
                                            "VALUE_NOT_NUMERIC"))
            continue
        facts.append(XbrlFact(
            taxonomy=taxonomy, tag=tag, context_ref=context_ref,
            unit_ref=unit_ref, value_text=node.text,
            resolved_value=resolved, sign=None, scale=None, format_=None,
            decimals=node.attrs.get("decimals"), language=None,
            locators=node.spans,
        ))

    merged, conflicts = merge_fact_occurrences(facts)
    for conflict in conflicts:
        rejections.append(conflict)

    root_local = _split_qname(root.tag)[1]
    if merged:
        kind = FACT_BEARING
    elif root_local in TAXONOMY_ROOTS or any(
            _split_qname(node.tag)[1] in TAXONOMY_ROOTS for node in nodes):
        kind = TAXONOMY_ONLY
    else:
        kind = NON_FACT_RENDERING
    return XbrlDocument(kind, contexts, units, tuple(merged),
                        tuple(rejections))


def merge_fact_occurrences(
    facts: Sequence[XbrlFact],
) -> Tuple[Tuple[XbrlFact, ...], Tuple[XbrlRejection, ...]]:
    """
    Collapse every physical appearance of one logical fact into one fact.

    An instance may state the same fact more than once -- inline XBRL hidden
    facts duplicate a visible one, and a document may carry a fact in two
    separate elements. Those are one logical fact with several byte ranges, so
    they must become one occurrence whose `locators` holds every span.

    Aggregating here, before the row exists, is the point: the relation is
    append-only and has no `UPDATE`, so a locator discovered after the insert
    could never be added. The caller writes each merged fact exactly once.

    Two appearances that resolve *differently* are not merged and not written:
    that is a document asserting one fact twice with two numbers, which is a
    contradiction rather than a second fact. It is returned as a rejection so the
    caller can report it, and it is deliberately not resolved by preferring the
    first -- inventing precedence is exactly what invariant 19 forbids.
    """
    order: List[Tuple[str, str, str, str]] = []
    grouped: Dict[Tuple[str, str, str, str], XbrlFact] = {}
    appearances: Dict[Tuple[str, str, str, str],
                      List[Tuple[Dict[str, int], ...]]] = {}
    conflicts: List[XbrlRejection] = []

    for fact in facts:
        key = (fact.taxonomy, fact.tag, fact.context_ref, fact.unit_ref)
        first = grouped.get(key)
        if first is None:
            order.append(key)
            grouped[key] = fact
            appearances[key] = [tuple(fact.locators)]
            continue
        if (first.value_text != fact.value_text
                or first.resolved_value != fact.resolved_value):
            conflicts.append(XbrlRejection(
                fact.taxonomy, fact.tag, fact.context_ref,
                "CONFLICTING_REPEAT"))
            continue
        appearances[key].append(tuple(fact.locators))

    merged = tuple(
        replace(
            grouped[key],
            appearance_locators=tuple(
                tuple(sorted(group, key=lambda span: (span["start"], span["end"])))
                for group in appearances[key]
            ),
        )
        for key in order if key in grouped
    )
    return merged, tuple(conflicts)


def _read_inline_fact(node: _Node, document: Sequence[_Node],
                      namespaces: Dict[str, str],
                      contexts: Dict[str, XbrlContext],
                      units: Dict[str, XbrlUnit],
                      rejections: List[XbrlRejection]) -> Optional[XbrlFact]:
    """One `ix:nonFraction`, following its `ix:continuation` chain."""
    qualified = _inline_qname(node.attrs.get("name"), namespaces)
    if qualified is None:
        rejections.append(XbrlRejection("", _split_qname(node.tag)[1], None,
                                        "NAME_ABSENT"))
        return None
    taxonomy, tag = qualified
    if not taxonomy:
        rejections.append(XbrlRejection(tag, tag, None,
                                        "NAMESPACE_UNDECLARED"))
        return None

    context_ref = node.attrs.get("contextRef")
    if not context_ref or context_ref not in contexts:
        rejections.append(XbrlRejection(taxonomy, tag, context_ref,
                                        "CONTEXT_UNRESOLVED"))
        return None
    unit_ref = node.attrs.get("unitRef")
    if not unit_ref or unit_ref not in units:
        rejections.append(XbrlRejection(taxonomy, tag, context_ref,
                                        "UNIT_UNRESOLVED"))
        return None

    spans = list(node.spans)
    chain = _continuation_chain(node, document, spans, node.text)
    if chain is None:
        rejections.append(XbrlRejection(taxonomy, tag, context_ref,
                                        "CONTINUATION_UNRESOLVED"))
        return None

    resolved = _resolve_inline_value(chain, node.attrs.get("sign"),
                                     node.attrs.get("scale"),
                                     node.attrs.get("format"))
    if resolved is None:
        rejections.append(XbrlRejection(taxonomy, tag, context_ref,
                                        "VALUE_NOT_NUMERIC"))
        return None

    return XbrlFact(
        taxonomy=taxonomy, tag=tag, context_ref=context_ref,
        unit_ref=unit_ref, value_text=chain.strip(),
        resolved_value=resolved,
        sign=node.attrs.get("sign"),
        scale=node.attrs.get("scale"),
        format_=node.attrs.get("format"),
        decimals=node.attrs.get("decimals"),
        language=node.attrs.get("lang"),
        locators=tuple(spans),
    )


def _continuation_chain(node: _Node, document: Sequence[_Node],
                        spans: List[Dict[str, int]],
                        value_text: str) -> Optional[str]:
    """
    Follow `ix:continuedAt` and concatenate the chain's text.

    One logical value spread over several byte ranges is still one fact, and this
    is where those several ranges are collected into one span list. The
    continuation element is a *sibling* in the document, not a descendant, so
    the lookup is document-wide.

    A chain that names an id no element declares is a rejection rather than a
    truncated value: a partial number stored as evidence would be indistinguishable
    from a complete one.
    """
    pending = [value_text]
    current = node
    seen = {id(current)}
    while True:
        continued_at = current.attrs.get("continuedAt")
        if not continued_at:
            return "".join(pending)
        target = _element_with_id(document, continued_at)
        if target is None or id(target) in seen:
            return None
        seen.add(id(target))
        spans.extend(target.spans)
        pending.append(target.text)
        current = target


def _element_with_id(document: Sequence[_Node],
                     element_id: str) -> Optional[_Node]:
    for candidate in document:
        if candidate.attrs.get("id") == element_id:
            return candidate
    return None


# ---------------------------------------------------------------------------
# Phase 3C-B2 -- linking an occurrence to an Observation that already exists
# ---------------------------------------------------------------------------

#: Refusal reasons. Every one of them means the same thing to a reader -- the
#: exact source document is *unresolved* -- and none of them is an error to fix
#: by guessing.
MATCHED = "MATCHED"
NO_OBSERVATION = "NO_OBSERVATION"
AMBIGUOUS_OBSERVATION = "AMBIGUOUS_OBSERVATION"
TAXONOMY_AMBIGUOUS = "TAXONOMY_AMBIGUOUS"
TAXONOMY_UNPROVEN = "TAXONOMY_UNPROVEN"
CONTEXT_AMBIGUOUS = "CONTEXT_AMBIGUOUS"
DOCUMENTS_AMBIGUOUS = "DOCUMENTS_AMBIGUOUS"
UNIT_UNRESOLVED = "UNIT_UNRESOLVED"

#: The XBRL "pure" unit means one share. The companyconcept endpoint spells that
#: as `/shares`, and that correspondence is what lets an existing frozen unit
#: rule be reused instead of a second one being written here.
_PURE_SHARES = ("shares", "xbrli:shares")


def unit_spelling(unit: XbrlUnit) -> Optional[str]:
    """
    Render a resolved XBRL unit into the spelling the aggregate endpoint uses.

    A single measure is its own name; a divided unit is `numerator/denominator`
    with the XBRL "pure shares" denominator written the way the endpoint writes
    it. Anything else returns None, and the caller then refuses to match rather
    than guessing -- this is a rendering, not a conversion, and the conversion
    that follows is `sec_provider.xbrl_unit_to_contract_unit`, which is the rule
    the archive already uses.
    """
    if unit.divide is None:
        return unit.measures[0] if len(unit.measures) == 1 else None
    if len(unit.measures) != 2:
        return None
    numerator, denominator = unit.measures
    if denominator in _PURE_SHARES:
        denominator = "shares"
    return f"{numerator}/{denominator}"


def contract_unit_of(unit_measures_json: str) -> Optional[str]:
    """
    The contract unit of a stored `unit_measures_json`, or None if unrecognised.

    The payload is the canonical `{measures, divide}` object the occurrence row
    already holds, so this reuses the recorded evidence rather than re-reading the
    document. The rendering is `unit_spelling`'s; the conversion is the archive's
    existing `xbrl_unit_to_contract_unit`, imported here so that one rule decides
    what a unit means rather than two rules disagreeing.
    """
    try:
        payload = json.loads(unit_measures_json)
    except (TypeError, ValueError):
        return None
    measures = payload.get("measures")
    if not isinstance(measures, list) or not measures:
        return None
    unit = XbrlUnit(
        unit_ref="", measures=tuple(measures),
        divide=payload.get("divide"), locator={"start": 0, "end": 0},
    )
    spelling = unit_spelling(unit)
    return xbrl_unit_to_contract_unit(spelling) if spelling else None


@dataclass(frozen=True)
class OccurrenceMatch:
    """What the matching rule concluded about one occurrence."""

    document_fact_id: str
    observation_id: Optional[str]
    reason: str


def _local_name(concept: str) -> str:
    """The local half of a `taxonomy:concept` concept string."""
    _, _, local = concept.partition(":")
    return local or concept


def occurrence_matches_observation_ordinary(
    occurrence: Dict[str, Any],
    observation: Dict[str, Any],
) -> bool:
    """
    Whether one occurrence and one Observation describe the same fact under
    ordinary exact-match predicates (Stage A).

    Seven exact comparisons:
    * filing scope -- provider, asset_id and accession are equal;
    * concept -- the occurrence's local tag equals the Observation's concept
      local name;
    * period -- the resolved context period equals the Observation's
      period_start/period_end, with an instant context requiring a NULL
      period_start;
    * unit -- the resolved unit equals the Observation's unit;
    * value -- the resolved value equals the stored value exactly.

    Taxonomy MUST NOT participate in this evaluation.
    """
    if occurrence.get("provider") != observation.get("provider"):
        return False
    if occurrence.get("asset_id") != observation.get("asset_id"):
        return False
    if occurrence.get("accession") != observation.get("accession"):
        return False
    if occurrence.get("tag") != _local_name(str(observation.get("concept") or "")):
        return False

    period_kind = occurrence.get("period_kind")
    period_start = observation.get("period_start")
    period_end = observation.get("period_end")
    if period_kind == PERIOD_INSTANT:
        if period_start is not None or period_end != occurrence.get("period_end"):
            return False
    elif period_kind == PERIOD_DURATION:
        if period_start != occurrence.get("period_start"):
            return False
        if period_end != occurrence.get("period_end"):
            return False
    elif period_kind == PERIOD_FOREVER:
        if period_start is not None or period_end is not None:
            return False
    else:
        return False

    contract_unit = occurrence.get("contract_unit")
    if contract_unit is None or contract_unit != observation.get("unit"):
        return False

    try:
        stored = float(observation.get("value_json"))
    except (TypeError, ValueError):
        return False
    return stored == occurrence.get("resolved_value")


def occurrence_matches_observation(
    occurrence: Dict[str, Any],
    observation: Dict[str, Any],
) -> bool:
    """
    Whether one occurrence and one Observation describe the same fact.

    Combines ordinary predicates (Stage A) with taxonomy adjudication (Stage C).
    """
    if not occurrence_matches_observation_ordinary(occurrence, observation):
        return False

    tax_ok, _ = evaluate_taxonomy_equivalence(
        occurrence.get("taxonomy"),
        observation.get("taxonomy"),
        observation.get("provider"),
    )
    return tax_ok


def evaluate_taxonomy_equivalence(
    occurrence_taxonomy: Optional[str],
    observation_taxonomy: Optional[str],
    provider: Optional[str],
) -> Tuple[bool, str]:
    """
    Evaluate whether occurrence taxonomy and observation taxonomy describe the same concept taxonomy.

    Under frozen Amendment 7 / C4I Evidence Sufficiency Matrix:
    - Claim C3 (Company Concept taxonomy == Catalog Prefix): NOT PROVEN.
    - Claim C7 (Observation <-> Filing Occurrence representation equivalence): NOT PROVEN.
    - Lexical equality != vocabulary equivalence != semantic taxonomy equivalence.
    - Direct equality bypass (occurrence.taxonomy == observation.taxonomy) is STRICTLY PROHIBITED
      across prefix/prefix, URI/URI, prefix/URI, or normalized strings.
    - In production evidence state, C3/C7 NOT PROVEN -> TAXONOMY_UNPROVEN.
    """
    if not occurrence_taxonomy or not observation_taxonomy or not provider:
        return False, TAXONOMY_UNPROVEN

    # In production evidence state, C3 and C7 are NOT PROVEN.
    # Production taxonomy adjudication must remain TAXONOMY_UNPROVEN.
    return False, TAXONOMY_UNPROVEN


def match_occurrence(
    occurrence: Dict[str, Any],
    observations: Sequence[Dict[str, Any]],
) -> OccurrenceMatch:
    """
    Resolve one occurrence against the Observations the archive already holds.

    Strict diagnostic precedence (Stage B):
    1. Evaluate ordinary matching across observations.
       - If 0 observations match ordinary predicates -> NO_OBSERVATION.
         (An occurrence whose period, unit, or value differs is NO_OBSERVATION,
          even if its tag matches and taxonomy is unproven.)
       - If > 1 observations match ordinary predicates -> AMBIGUOUS_OBSERVATION.
         (Observation ambiguity is handled first; taxonomy cannot be used to pick one.)
    2. Exactly 1 observation matches ordinary predicates:
       Evaluate taxonomy adjudication (Stage C).
       - tax_ok is True -> MATCHED with observation_id.
       - tax_ok is False -> return tax_reason (TAXONOMY_UNPROVEN or TAXONOMY_AMBIGUOUS).
    """
    ordinary_candidates = [
        obs for obs in observations
        if occurrence_matches_observation_ordinary(occurrence, obs)
    ]

    if not ordinary_candidates:
        return OccurrenceMatch(
            occurrence["document_fact_id"], None, NO_OBSERVATION)

    distinct_obs_ids = {obs["observation_id"] for obs in ordinary_candidates}
    if len(distinct_obs_ids) != 1:
        return OccurrenceMatch(
            occurrence["document_fact_id"], None, AMBIGUOUS_OBSERVATION)

    matched_obs = ordinary_candidates[0]
    tax_ok, tax_reason = evaluate_taxonomy_equivalence(
        occurrence.get("taxonomy"),
        matched_obs.get("taxonomy"),
        matched_obs.get("provider"),
    )
    if tax_ok:
        return OccurrenceMatch(
            occurrence["document_fact_id"], matched_obs["observation_id"], MATCHED)
    return OccurrenceMatch(
        occurrence["document_fact_id"], None, tax_reason)


def exact_source_document(
    linked: Sequence[Dict[str, Any]],
    candidate_docs: Optional[Sequence[Tuple[str, str, str]]] = None,
    candidate_occurrences: Optional[Sequence[Dict[str, Any]]] = None,
    has_unresolved_ambiguity: bool = False,
) -> Tuple[Optional[Tuple[str, str, str]], Optional[str]]:
    """
    The one document to assert, or None with the reason it cannot be decided.

    Cardinality invariant (Stage E):
    - candidate_docs represents the FULL pre-taxonomy candidate document set.
    - TAXONOMY_REFUSAL_MUST_NOT_SHRINK_EXACT_SOURCE_CANDIDATES:
      If candidate_docs has > 1 documents, exact source document can NEVER be
      asserted (DOCUMENTS_AMBIGUOUS).
    - If has_unresolved_ambiguity is True, exact source cannot be asserted
      (AMBIGUOUS_OBSERVATION).
    - If competing contexts exist across candidate occurrences, exact source
      cannot be asserted (CONTEXT_AMBIGUOUS).
    - If candidate_docs is not provided, defaults to candidate_occurrences or linked.
    - If linked is empty (e.g. taxonomy refusal), exact source cannot be asserted.
    """
    if has_unresolved_ambiguity:
        return None, AMBIGUOUS_OBSERVATION

    if candidate_docs is not None:
        docs = set(candidate_docs)
    elif candidate_occurrences is not None:
        docs = {
            (row["asset_id"], row["accession"], row["filename"])
            for row in candidate_occurrences
        }
    else:
        docs = {
            (row["asset_id"], row["accession"], row["filename"]) for row in linked
        }

    if not docs:
        return None, NO_OBSERVATION

    # TAXONOMY_REFUSAL_MUST_NOT_SHRINK_EXACT_SOURCE_CANDIDATES:
    # If raw candidate document cardinality > 1, exact source can NEVER be asserted!
    if len(docs) > 1:
        return None, DOCUMENTS_AMBIGUOUS

    # Context uniqueness across full candidate set
    if candidate_occurrences is not None:
        contexts = {
            row["context_ref"] for row in candidate_occurrences
            if row.get("context_ref") is not None
        }
        if len(contexts) > 1:
            return None, CONTEXT_AMBIGUOUS

    if not linked:
        return None, TAXONOMY_UNPROVEN

    if len({row["context_ref"] for row in linked}) != 1:
        return None, CONTEXT_AMBIGUOUS

    asset_id, accession, filename = next(iter(docs))
    return (asset_id, accession, filename), None
