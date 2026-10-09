# Amendment 10 — C2A Record Classification, Eligibility, Identity Collapse and Evidence Preservation

**Status:** DRAFT v10 — NOT IN FORCE. Document layer only. No code, test, schema,
data, or ADR(1–9) modification executed. This document confers NO authorization
of any kind: not an ADR append, not an implementation, not a deployment, not a
database operation. Every decision below takes effect only upon formal
ratification.
**Date:** 2026-10-09
**Baseline:** `468083941357efeb54e4cb61a607d6b08039a2ca`. Amendments 1–9
preserved byte-identically.
**Baseline implementation under comparison:**
`archive/parse_edgar_taxonomies_catalog.py` and
`archive/record_authority_taxonomy_assertion.py` as of the baseline commit.
**Trigger:** Captured catalog `doc_eb3d9eb2f741a4e844f7ed11`
(`sha256:c639c18647c52a594c74eb60573851de15b7391de84a723cd3b7cced15f0341b`,
`<Erxl version="78">`) aborts C2A on record #127 (0-based #126).

**Source note.** This is a standalone draft file. It is not part of the formal ADR
and has not been appended to it. The formal ADR
`docs/ADR-XBRL-SOURCE-DOCUMENT-PROVENANCE.md` is unchanged.

## 0. Numbering Convention (binding)

1. Every rule carries a top-level number `10.1` … `10.54`. A top-level number
   identifies exactly ONE rule.
2. A top-level number is realized EITHER as a single bare clause `10.n`
   **or** as a set of lettered sub-clauses `10.n(a)`, `10.n(b)`, … never as both.
   A `(number, letter)` pair identifies exactly ONE clause and MUST NOT be reused.
3. **Counting rule.** A *decision clause* is one rule heading, counted as a bare
   `10.n` heading or as a lettered `10.n(z)` heading. The total number of decision
   clauses equals bare headings plus lettered headings. A number realized through
   sub-clauses contributes one clause per letter and is NOT counted again as a
   bare heading.
4. Any duplicate top-level number, any number realized both bare and lettered, any
   duplicate `(number, letter)` pair, and any dangling internal reference is a
   document defect and blocks ratification.

**Verified totals for this revision, applying rule 3:** 54 distinct top-level
numbers; 10 of them have their rules realized through sub-clauses — top-level
numbers 2, 7, 12, 22, 30, 32, 34, 36, 39 and 42 — contributing 40 sub-clauses in
total; 44 bare clauses. **Total decision clauses: 84.**

---

## 1. Official Basis, Scope of Normative Authority, Element Vocabulary

SEC publishes the catalog's format schema at
`https://www.sec.gov/info/edgar/erxl.xsd` (referenced by the catalog root via
`xsi:noNamespaceSchemaLocation="erxl.xsd"`). It declares, verbatim:

    Href         minOccurs="1"  (required; maxOccurs defaults to 1)
    Elements     minOccurs="1"  (required; maxOccurs defaults to 1)
    Family       minOccurs="0"  (optional)
    Version      minOccurs="0"  (optional)
    AttType      minOccurs="0"  (optional; plain xsd:string, no enumeration)
    FileTypeName minOccurs="0"  (optional; plain xsd:string, no enumeration)
    Namespace    minOccurs="0"  (optional)
    Prefix       minOccurs="0"  (optional)

The captured bytes validate against this XSD
(`XSD_VALID_AGAINTS_SEC_erxl_xsd: true`).

**Decision 10.1 (cardinality fact).** In the authority's own format, `Namespace`,
`Family` and `Version` are optional; only `Href` and `Elements` are mandatory. The
pre-Amendment-10 reading that every record declares a namespace was stricter than
the authority's schema and is withdrawn as a validity criterion.

**Decision 10.2(a) (element vocabulary).** Throughout this amendment the eight
child elements declared by the SEC `erxl.xsd` are referred to by the single
defined name `LOC_CHILD_ELEMENTS`:

    Family, Version, Href, AttType, FileTypeName, Elements, Namespace, Prefix

A **record** is a direct child element of the root whose tag is exactly `Loc`. Any
other direct child of the root is a **non-record root element**; any child of a
record whose tag is not in `LOC_CHILD_ELEMENTS` is a **non-standard record
element**. Both categories are, together, **unknown child elements** for the
purposes of this amendment.

**Decision 10.2(b) (qualified-name representation of tags).** Wherever this
amendment names an element tag in an output structure, the value is the element's
qualified name: the bare local name when the element is in no namespace, and
`{namespace-uri}local-name` when it is in a namespace. All de-duplication,
distinct-name lists and counts are computed over this exact representation, so two
elements with the same local name in different namespaces are NEVER merged. This
rule applies identically at record level (Decision 10.22(a)) and at root level
(Decision 10.23).

**Decision 10.2(c) (exact known-tag matching).** A record child is a **known**
element if and only if its qualified name under Decision 10.2(b) is **exactly
string-equal** to one of the eight bare names in `LOC_CHILD_ELEMENTS`. No other
match is performed: not local-name matching, not namespace-insensitive matching,
not suffix matching.

Consequences:

- The unqualified `Family` and the namespaced `{urn:example}Family` are
  **DIFFERENT elements**. The first is a known element; the second is a
  non-standard record element.
- At root level, only the tag exactly `Loc` denotes a record. A namespaced
  `{urn:example}Loc` is a non-record root element.
- An element that fails the exact match is classified as an unknown child element,
  and is then retained, reported and counted under Decisions 10.22(a) and 10.23.
  It is never persisted and never affects Axis E eligibility.
- **S1 constrains only the root element.** A catalog whose root is the unqualified
  `Erxl` may still carry namespaced descendants; Decision 10.2(c) classifies them
  without adding any refusal and without relaxing S1 in any respect.
- This rule introduces **no namespace-aware lookup**. No qualified tag is ever
  searched for, resolved, or matched against `LOC_CHILD_ELEMENTS` beyond the exact
  string comparison stated above, and the limitation on namespace-aware lookup in
  §12 is unchanged.

**Decision 10.3 (scope of normative authority).** The SEC `erxl.xsd` is the sole
normative authority for **source format and cardinality claims only**: which
elements exist in a record, which are mandatory, which are optional, and the
maximum occurrence of each. It is NOT an authority for any consumer obligation.
The SEC publishes no requirement governing how a consumer must classify, retain
or persist catalog records. Consequently the following are **ST-EVA project
contracts carrying no normative weight from the authority**:

- Stage 0 input admission (§2, Decisions 10.7(a)–(c));
- Axis E assertion eligibility (§4, Decisions 10.15–10.18);
- the unknown-child-element retention and reporting policy (§5, Decisions
  10.22(a)–(e), 10.23, 10.24);
- the two-channel projection and its persistence boundary (§5, §7);
- the coverage invariants (§6);
- the pre-run expectation, baseline and ordering contracts (§8, §9; Decisions
  10.39(a)–(c), 10.40, 10.41, 10.42(a)–(d), 10.43, 10.44);
- the identity-collapse disclosure and its acceptance (§7, Decisions 10.37, 10.38);
- the identity-to-identifier collision checks (§7, Decisions 10.36(a)–(d));
- the output field contract (§7, Decisions 10.34(a)–(d)).

Where Axis S conforms to `erxl.xsd`, that is by deliberate alignment, not by
authority over consumer behaviour.

**Decision 10.4 (evidence tiering).**

- Tier 1 (normative, per Decision 10.3): the SEC `erxl.xsd` above, and the XSD
  validation of the captured bytes.
- Tier 2 (non-normative context): third-party architectural material, e.g. the
  IFRS Foundation taxonomy architecture guide describing `dimensions` folders as
  containing definition linkbases. Non-SEC publisher, excerpt-level retrieval, not
  byte-verified. It may support a structural *explanation* of why two records
  lack `<Namespace>`. It MUST NOT support a contract, MUST NOT classify a record,
  and MUST NOT assert anything about those records' meaning.

**Decision 10.5 (classification inputs).** Classification MUST NOT rely on
`AttType`, `FileTypeName`, filename, extension or path shape. The SEC publishes
no normative enumeration for those tokens. Classification rests solely on the
observable presence, absence, or emptiness of source-declared elements, matched
exactly as in Decision 10.2(c).

**Decision 10.6 (no semantic claim).** No semantic claim is made about any
non-eligible record. Such records are classified only as "does not satisfy this
project's assertion eligibility contract".

---

## 2. Stage 0 — Input Admission (executed before every other step)

Stage 0 is a closed set of input-admission conditions. It performs NO semantic
judgement, inspects NO element content, and is evaluated before any other workflow
step.

| ID | Failure condition | Error code | Action |
|---|---|---|---|
| A0-1 | The payload is not an instance of `bytes` | `INPUT_TYPE_INVALID` | refuse input |
| A0-2 | The payload is empty (length 0) | `INPUT_PAYLOAD_EMPTY` | refuse input |
| A0-3 | The payload is not well-formed XML and cannot be parsed | `INPUT_MALFORMED_XML` | refuse input |

**Decision 10.7(a) (Stage 0 rule).** Input is admitted if and only if none of
A0-1, A0-2 or A0-3 holds. The error code emitted is the code of the first
violated condition in A0-1…A0-3 order.

**Decision 10.7(b) (Stage 0 executes first; the two paths).** Stage 0 is the first
gate of the workflow and is evaluated IMMEDIATELY after the payload reference is
obtained and BEFORE any pre-run computation.

- **Path R — rejected input.** If any of A0-1…A0-3 holds: refuse with the
  corresponding code under Decision 10.7(a). On this path the workflow MUST NOT
  execute P1, P2, P3 or P4, because each presupposes valid `bytes` (P1 hashes the
  payload; P3 parses it). The workflow MUST NOT execute E1, so **no database write
  of any kind occurs on Path R**. Axis S is NOT evaluated and no Axis S error code
  may be emitted. No Class A or Class B quantity exists, so the post-run
  comparison of Decision 10.44 does not apply.
- **Path A — admitted input.** Only after Stage 0 admits the payload does the
  workflow proceed to the read-only pre-run steps P1…P4 and then to E1…E5, as
  ordered by Decision 10.45.

**Decision 10.7(c) (Axis S is conditioned on Path A).** Axis S (Decision 10.9) is
evaluated only on Path A. A Stage 0 refusal is not an Axis S refusal and MUST NOT
be reported as one.

**Decision 10.8 (Stage 0 scope).** Stage 0 does not inspect, require or validate
any element, attribute, namespace or value. Adding a condition to Stage 0 is a
change to this amendment. All Stage 0 refusals raise the existing
`CatalogParseError`; no new exception type is introduced by this amendment.

---

## 3. Axis S — Structural Failure Conditions (closed set)

Axis S is a CLOSED set of failure conditions and consists of exactly S1–S5. It is
NOT an XSD validator and does not claim full schema conformance.

| ID | Failure condition | Error code | Action |
|---|---|---|---|
| S1 | The root element's tag is not exactly `Erxl`, unqualified — including any namespace-qualified form | `STRUCTURAL_ERROR_ROOT_ELEMENT` | refuse catalog |
| S2 | The root element has no `version` attribute, or its value is empty after whitespace removal | `STRUCTURAL_ERROR_ROOT_VERSION` | refuse catalog |
| S3 | A tag in `LOC_CHILD_ELEMENTS` occurs more than once within one record | `STRUCTURAL_ERROR_DUPLICATE_KNOWN_CHILD` | refuse catalog |
| S4 | A record has no `Href` child element | `STRUCTURAL_ERROR_HREF_ABSENT` | refuse catalog |
| S5 | A record has no `Elements` child element | `STRUCTURAL_ERROR_ELEMENTS_ABSENT` | refuse catalog |

**Decision 10.9 (Axis S refusal rule, conditioned).** An **input admitted by
Stage 0** is refused by Axis S if and only if at least one of S1–S5 holds. S1–S5
are the complete set of Axis S failure conditions; each refuses only on its own
stated condition, and no other condition refuses. The error code emitted is the
code of the first violated condition in S1–S5 order. If Stage 0 refused the input,
this decision does not apply.

**Decision 10.10 (S1 strict; qualified root refused).** S1 is exact-tag matching,
applied to the root element only. A namespace-qualified root element is REFUSED in
every case, and the pre-existing defensive local-name branch (baseline lines
66–72) is REMOVED.

Rationale, verified against the baseline implementation: the XSD declares an
unqualified root element, so a qualified root is not schema-conformant. The
baseline accepts such a root without error, after which record discovery uses
unqualified `findall("Loc")` (line 83) and `find(...)`. The resulting record count
is therefore DATA-DEPENDENT and is not uniformly zero; the measured sub-cases are
tabulated in Decision 10.12(c). The rule is removed because it admits an input
shape the authority does not define, and because one of its outcomes is a silent
record loss that would invalidate the coverage invariants of §6 at their
foundation. No tolerance is retained; a consistent namespace-aware lookup contract
would be required first and remains out of scope (§12).

**Decision 10.11 (S3 scope).** S3 applies ONLY to tags matching
`LOC_CHILD_ELEMENTS` exactly under Decision 10.2(c), including `AttType` and
`Elements`, which the baseline never reads and which therefore have no prior
observable behaviour. A repeated unknown child element does NOT trigger S3 and
does NOT refuse the catalog; it is handled under Decision 10.22(d). First-wins,
last-wins and any other selection strategy for a repeated known child element are
forbidden: selecting one would fabricate a precedence the source never expressed,
and for identity-bearing elements could silently alter assertion content.

**Decision 10.12(a) (single-variable comparison rule).** Every row of the behaviour
table isolates exactly one changed factor; all other factors are held at the value
on which the baseline and the amended contract agree. Where the baseline outcome
depends on a further factor that this amendment does not change — as with a
duplicated required element, where the baseline's first match may itself trigger
the existing required-field refusal — the row is restricted to the case that
isolates the variable, and the dependent case is given its own row carrying its
own, unchanged, refusal outcome.

**Decision 10.12(b) (counting rule; change identifiers versus situations).** A
**refusal-outcome change** is a change of the catalog's ACCEPTED / REFUSED status.
A change of the emitted error code, of the error message, or of any diagnostic
detail is NOT a refusal-outcome change and MUST NOT be counted as one.

Changes are given stable identifiers so that each is individually reviewable:

- **11 change identifiers**: `BC-1`, `BC-2`, `BC-3`, `BC-4`, `BC-5`
  (accepted→refused) and `CR-1`…`CR-6` (refused→accepted);
- spread over **12 refusal-outcome-changing situations** in the table below,
  because `BC-1` covers two distinct situations (rows B-05 and B-06) that differ
  in whether the baseline could observe the duplication at all.

These counts are properties of the enumeration in this decision, not claims about
the total effect of the amendment. Any behaviour not listed below is unchanged.
The "before" column of every row is supported by the baseline source, cited by
line.

| # | Input condition (one variable) | Accepted/refused — before → after | Record classification — before → after | Output structure — before → after | Change |
|---|---|---|---|---|---|
| B-01 | Root tag unqualified but not `Erxl` | refused → refused (S1) `:65,72` | not reached | error code only | unchanged |
| B-02 | Root tag namespace-qualified in any form | **accepted** by the local-name branch `:66-72` — outcome data-dependent, see Decision 10.12(c) → **refused** (S1) | before: dependent on child qualification; after: not reached | before: may be a silent zero-record result | **BC-2** |
| B-03 | Root `version` attribute absent | refused → refused (S2) `:76-77` | not reached | error code only | unchanged |
| B-04 | Root `version` present but whitespace-only | **accepted** — baseline does not strip `:76-77` → **refused** (S2) | not reached | — | **BC-5** |
| B-05 | Duplicate of one of the six elements the baseline reads (`Family`, `Version`, `Namespace`, `Prefix`, `FileTypeName`, `Href`), **first occurrence non-empty** `:85-87,104-106` | **accepted**, first value projected, later occurrences ignored → **refused** (S3) | before: first-match value projected; after: not reached | — | **BC-1** |
| B-06 | Duplicate of `AttType` or `Elements` | **accepted**, and the duplication was never observed — neither element is referenced anywhere in the baseline → **refused** (S3) | before: no effect on output; after: not reached | — | **BC-1** |
| B-07 | Duplicate of `Family` / `Version` / `Namespace`, **first occurrence empty or whitespace-only** | refused → refused | not reached | **error code may change** (baseline `:98-100` required-field refusal; after, S3). Per Decision 10.12(b) this is NOT a refusal-outcome change | unchanged |
| B-08 | Record without `<Href>` | **accepted**; `schema_href = None` `:106,114` → **refused** (S4) | before: assertion emitted with `schema_href = None`; after: not reached | — | **BC-3** |
| B-09 | Record without `<Elements>` | **accepted**; the element is never read → **refused** (S5) | before: assertion emitted; after: not reached | — | **BC-4** |
| B-10 | Record without `<Namespace>` | **refused** `:89-92` → **accepted** | before: whole parse aborted; after: `NON_ASSERTION_LOC`, `namespace_absent` | channel-2 record emitted | **CR-1** |
| B-11 | `<Namespace>` present, text empty or whitespace-only | **refused** `:98-100` → **accepted** | `NON_ASSERTION_LOC`, `namespace_empty` | channel-2 record | **CR-2** |
| B-12 | Record without `<Family>` | **refused** `:89-92` → **accepted** | `NON_ASSERTION_LOC`, `family_absent` | channel-2 record | **CR-3** |
| B-13 | `<Family>` present, text empty or whitespace-only | **refused** `:98-100` → **accepted** | `NON_ASSERTION_LOC`, `family_empty` | channel-2 record | **CR-4** |
| B-14 | Record without `<Version>` | **refused** `:89-92` → **accepted** | `NON_ASSERTION_LOC`, `version_absent` | channel-2 record | **CR-5** |
| B-15 | `<Version>` present, text empty or whitespace-only | **refused** `:98-100` → **accepted** | `NON_ASSERTION_LOC`, `version_empty` | channel-2 record | **CR-6** |
| B-16 | `Namespace`, `Family`, `Version` all present and non-empty | accepted → accepted | `ASSERTION_ELIGIBLE`; identical 10-field `ParsedAuthorityAssertion` projection as at the baseline | additionally reported under the §7 metrics | output structure |
| B-17 | `<Prefix>` absent or empty | accepted, `standard_prefix = None` `:104,109-111` → unchanged | unchanged | unchanged | unchanged |
| B-18 | `<FileTypeName>` absent or empty | accepted, `file_type_name = None` `:105,112-114` → unchanged | unchanged | unchanged | unchanged |
| B-19 | `<Href>` present but empty | accepted, `schema_href = None` `:106,115-117` → unchanged | unchanged | unchanged | unchanged |
| B-20 | `<Elements>` present but empty | accepted; the element is never read → unchanged | unchanged | unchanged | unchanged |
| B-21 | Non-standard record element on an ELIGIBLE record | silently ignored → retained and occurrence-reported (channel-1 reporting included) | classification unaffected | output structure changed | output structure |
| B-22 | Non-standard record element on a NON-ELIGIBLE record | silently ignored → retained and occurrence-reported | classification unaffected | output structure changed | output structure |
| B-23 | Repeated non-standard record element | silently ignored → retained and occurrence-reported; **NOT refused** | unaffected | output structure changed | output structure |
| B-24 | Non-record root element | silently ignored by `findall("Loc")` `:83` → retained and occurrence-reported | unaffected | output structure changed | output structure |
| B-25 | Zero records | empty result `:83` → accepted; both channels empty; `N_source_loc` 0; zero writer calls; `assertion_count` 0. **NOT an Axis S refusal** (Decision 10.13, 10.34(d)) | — | — | unchanged |
| B-26 | Child order deviating from the XSD sequence | accepted (name-based lookup) → accepted, still unchecked | — | — | unchanged |
| B-27 | Non-empty `version` violating the XSD pattern | accepted → accepted, still unchecked | — | — | unchanged |
| B-28 | Payload not `bytes` | refused `:53-54` → refused (A0-1) | — | — | unchanged |
| B-29 | Payload empty | refused `:55-56` → refused (A0-2) | — | — | unchanged |
| B-30 | Payload not well-formed XML | refused `:59-62` → refused (A0-3) | — | — | unchanged |
| B-31 | Parser return value / workflow result structure | list of assertions; result without the §7 fields | — | two-channel structured result plus the §7 fields | output structure |
| B-32 | Distinct identities resolving to one `authority_taxonomy_id` | unspecified; aborted by the uniqueness constraint or the extraction-consistency trigger | — | fail closed; no merge, no continuation | fail-closed clarification |
| B-33 | `assertion_count` when non-eligible records exist | refused, so no figure was produced `:89-100` | equals the eligible record count, which MAY be 0 (Decision 10.34(d)) | — | consequence of CR-1…CR-6 |

Refusal-outcome-changing rows, counted under Decision 10.12(b): B-02, B-04, B-05,
B-06, B-08, B-09, B-10, B-11, B-12, B-13, B-14, B-15 — **twelve situations**,
carrying identifiers BC-1…BC-5 and CR-1…CR-6 — **eleven identifiers**. Row B-07
is refused under both contracts and, its error code differing notwithstanding, is
not counted.

**Decision 10.12(c) (measured sub-cases of B-02).** The baseline outcome for a
namespace-qualified root is data-dependent. Measured on constructed input against
the baseline implementation:

| Sub-case | Root | Records | Baseline outcome |
|---|---|---|---|
| a | `{urn:example:erxl}Erxl` | children qualified in the same namespace | no error; `findall("Loc")` `:83` matches nothing; **0 assertions** |
| b | `{urn:example:erxl}Erxl` | children unqualified `Loc` | no error; `findall("Loc")` matches; **1 assertion** |
| control | unqualified `Erxl` | children unqualified `Loc` | no error; **1 assertion** |

Sub-case (a) is the silent record loss that motivates removing the tolerance.
Sub-case (b) shows the baseline parses records normally in that shape. **This
amendment does not claim that every qualified-root document yields zero records**;
it claims only that S1 refuses the qualified root in both sub-cases, and that
sub-case (a) is an unacceptably silent outcome.

**Net effect on the captured catalog:** the baseline refused the whole parse at
the record lacking `<Namespace>` (`:89-92`); after this amendment the parse
completes with 201 eligible records and 2 `NON_ASSERTION_LOC` records.

**Decision 10.12(d) (alignment note).** BC-1, BC-2, BC-3, BC-4 and BC-5 all align
the implementation with `erxl.xsd`: `Href` and `Elements` are `minOccurs="1"`;
`version` is `use="required"` and pattern-constrained; the root element declaration
is unqualified; and each record child has default `maxOccurs="1"`. All five are
alignments, not deviations from the authority's schema, and none is listed in §13.
BC-5's whitespace rule is consistent with the XSD pattern for that specific case;
the pattern as a whole remains a declared non-check (Decision 10.14).

**Decision 10.13 (non-failure list).** None of the following is an Axis S failure
and none may refuse an admitted catalog: absence of any `LOC_CHILD_ELEMENTS`
member other than `Href` or `Elements`; a present-but-empty `Href`; a
present-but-empty `Elements`; presence of any unknown child element at root or
record level; repetition of an unknown child element; zero records; zero eligible
records.

**Decision 10.14 (known non-checks).** Axis S does NOT check: child element ORDER;
the `version` attribute PATTERN `[1-9][0-9]*([.][1-9][0-9]*)*`; datatypes of any
child value; or full-document XSD validation. Each is a declared limitation.
Adding any of them is a separate decision and is not authorized here.

---

## 4. Axis E — Assertion Eligibility (ST-EVA project contract)

**Decision 10.15 (eligibility definition).** A record is `ASSERTION_ELIGIBLE` if
and only if `Namespace`, `Family` and `Version` are each PRESENT and each
NON-EMPTY under the text-extraction rule of §10. Otherwise it is
`NON_ASSERTION_LOC`. Axis E operates on the same three attributes that the
identity preimage uses, and `0022` declares the corresponding columns
`namespace_uri`, `taxonomy_family` and `taxonomy_version` as `NOT NULL`. A SQL
`NOT NULL` declaration does NOT entail non-emptiness — the column may hold an
empty string — so the requirement that each value be non-empty is an **ADDITIONAL
ST-EVA project contract** under Decision 10.3, not a consequence of the schema and
not a requirement stated by the authority. The authority states nothing about which
records a consumer may assert on.

**Decision 10.16 (reason vocabulary).** Reason codes are drawn from this CLOSED
vocabulary, evaluated in this fixed precedence:

    namespace_absent, namespace_empty,
    family_absent,    family_empty,
    version_absent,   version_empty

`primary_reason` is the first match in that order; `reasons` is the full ordered
match set. Precedence fixes reporting order only and implies no value judgement. A
record MAY carry several reasons. Any code outside this list is a contract
violation.

**Decision 10.17 (absence is not emptiness).** `*_absent` means the element does
not exist; `*_empty` means it exists but its text is empty after the §10 extraction
rule. The two MUST NOT be conflated anywhere in the record contracts.

**Decision 10.18 (retention claim, bounded).** A `NON_ASSERTION_LOC` record
retains the value of every `LOC_CHILD_ELEMENTS` member, each as either its
`SOURCE_DECLARED_TEXT` value or an explicit ABSENT marker, including any
`Namespace` that is present. It does NOT claim to retain the textual content of
unknown child elements; see Decision 10.22(c). "Resource without a declared
namespace" and "namespace present but claim fields incomplete" are never collapsed
into one another.

---

## 5. Record Field Contracts (ST-EVA project contract)

**Decision 10.19 (single read, two projections).** Each record is read exactly once
into a uniform intermediate form covering all `LOC_CHILD_ELEMENTS` plus any
non-standard record elements, and both channels are projected from that single
read, so both are provably derived from the same observation.

**Decision 10.20 (channel 1 contract, frozen).** `ASSERTION_ELIGIBLE` records are
projected to `ParsedAuthorityAssertion`, which has exactly **10** fields, in this
order: `taxonomy_family`, `taxonomy_version`, `namespace_uri`, `provider`,
`standard_prefix`, `file_type_name`, `schema_href`, `authority_source`,
`authority_source_class`, `authority_source_version`. The projection is identical
to the baseline projection; no field is added, removed, renamed or reordered. That
type has no `att_type` and no `elements` field, and `0022` has no corresponding
columns, so `AttType` and `Elements` are read for channel-1 records but are NOT
persisted. This is a pre-existing schema limitation, disclosed here rather than
implied complete, and it is not a loss of source evidence, which remains intact at
`L1`.

**Decision 10.21 (channel 2 contract, with per-field derivability).** A
`NON_ASSERTION_LOC` record carries, for each of the eight `LOC_CHILD_ELEMENTS`, a
value that is either the `SOURCE_DECLARED_TEXT` value or an explicit ABSENT
marker, plus the following fields. Each field is classified as **additional
per-record data**, **globally derivable**, or **scoped-de-duplicated**, and the
derivation or comparison rule is stated:

| Field | Type | Classification | Derivation / comparison rule |
|---|---|---|---|
| `source_loc_index` | int | additional per-record data | equals the record's index in `source_records` |
| `child_element_sequence` | ordered tuple of qualified tag names | **additional per-record data** | NOT derivable from `unknown_record_child_occurrences`, which contains only non-standard elements. Covers ALL children of the record, known and non-standard alike, in document order. No global counterpart exists or is required. |
| `present_known_elements` | set of qualified tag names | additional per-record data | derived from `child_element_sequence` by filtering to `LOC_CHILD_ELEMENTS` under Decision 10.2(c) |
| `unknown_child_elements` | ordered tuple of qualified tag names, one entry per occurrence | **globally derivable** | equals `[ occ.tag_name for occ in unknown_record_child_occurrences if occ.source_loc_index == this record's index ]`, in global order |
| `unknown_element_names` | ordered tuple of qualified tag names, de-duplicated **within this record**, first-occurrence order | **scoped-de-duplicated** | equals the de-duplication of this record's `unknown_child_elements` under Decision 10.2(b). It is NOT equal to the global `unknown_record_child_names`, whose scope is all records; the two MUST NOT be conflated |
| `reasons` | ordered tuple of reason codes | additional per-record data | per Decision 10.16 |
| `primary_reason` | str | additional per-record data | first entry of `reasons` |

**Decision 10.22(a) (non-standard record elements: run-level retention and
reporting across BOTH channels).** A non-standard record element MUST NOT be
silently ignored, on an eligible record any more than on a non-eligible record.
Retention and reporting are defined ONCE, at run level, and cover **every** record
in `source_records` regardless of channel.

The occurrence element is a **named structure**, not a bare tuple:

    RecordChildOccurrence
        source_loc_index   int   -- index in source_records
        channel            str   -- "ASSERTION_ELIGIBLE" | "NON_ASSERTION_LOC"
        child_position     int   -- 0-based index within that record's
                                   child_element_sequence
        tag_name           str   -- qualified name per Decision 10.2(b)

Occurrences are accessed by field name (`occ.tag_name`, `occ.source_loc_index`).
Bare positional tuples MUST NOT be used interchangeably with this structure
anywhere in the output or in the rules.

    unknown_record_child_occurrences
        ordered tuple of RecordChildOccurrence, one entry per non-standard child
        element occurrence, ordered by (source_loc_index, child_position)
    unknown_record_child_names
        ordered tuple of str; the DISTINCT qualified tag names of the occurrences,
        de-duplicated ACROSS ALL RECORDS, in first-occurrence order
    unknown_record_child_count
        int; len(unknown_record_child_occurrences)

Agreement requirements:

    A1  unknown_record_child_count == len(unknown_record_child_occurrences)
    A2  unknown_record_child_names == distinct tag names of those occurrences,
        de-duplicated across all records, in first-occurrence order
    A3  for every i in source_indices, the local `unknown_child_elements` of the
        channel-2 record at index i (if any) equals the tag_names of the global
        occurrences whose source_loc_index == i, in global order
    A4  for every occurrence, its `channel` equals "ASSERTION_ELIGIBLE" if
        source_loc_index is in eligible_indices, else "NON_ASSERTION_LOC"

**Decision 10.22(b) (classification precedes labelling).** Axis E determines the
classification FIRST. The `channel` field of an occurrence is a **projection** of
that already-determined classification and MUST NOT be an input to it, and MUST
NOT be able to influence it. A4 is a post-hoc consistency assertion on the
reported label, never a mechanism of classification. A failure of A4 is an E3 gate
failure; it does not reclassify anything.

**Decision 10.22(c) (retention boundary).** What IS retained for a non-standard
record element: its qualified tag name, its owning record index, its channel, its
position within the record's child sequence, and its occurrence. What is NOT
claimed: that its textual content is retained, structured, or recoverable from the
run result. The complete original content is available ONLY at `L1` and is
recoverable by replaying the immutable bytes. A non-standard record element MUST
NOT affect eligibility. The global structure MUST NOT depend on
`non_assertion_records` being retained by the caller; if the caller discards
channel-2 records, the global occurrence structure remains complete and
self-sufficient.

**Decision 10.22(d) (no conflict with S3).** This policy MUST NOT conflict with
S3: S3 governs repeated elements matching `LOC_CHILD_ELEMENTS` only (Decision
10.11), so a repeated non-standard element is retained and reported rather than
refused (row B-23). Refusing the catalog instead would reproduce the failure mode
this amendment exists to remove, since a future SEC field addition would again
abort C2A.

**Decision 10.22(e) (index validation ordering).** Occurrence validation proceeds
in this fixed order, and each step MUST complete before the next begins:

    V1  every occurrence's `source_loc_index` is a member of source_indices
    V2  only if V1 holds for every occurrence, validate A4 (channel agreement)
    V3  `channel` is a projection of the Axis E classification and MUST NOT be
        used as an input to, or a determinant of, that classification
    V4  a failure of V1 or V2 is an E3 gate failure and MUST NOT trigger
        reclassification

V1 and V2 are part of the E3 gate under Decision 10.46, consistent with C1–C8 and
with A1–A4.

**Decision 10.23 (root direct-child scope, partition, and occurrence/name
separation).** Exactly three sets are defined, over the root element's direct
children:

    root_direct_children   = every direct child ELEMENT of the root element,
                             in document order
    source_records         = [ e for e in root_direct_children
                               if e.tag == "Loc" exactly, per Decision 10.2(c) ]
    non_record_root_elements
                           = [ e for e in root_direct_children
                               if e.tag != "Loc" exactly ]

`source_records` and `non_record_root_elements` are mutually exclusive and their
union is exactly `root_direct_children`. Tag comparison is exact and unqualified,
consistent with S1 and Decision 10.2(c); a namespaced `{urn:example}Loc` is a
non-record root element. XML comments and processing instructions are not elements
and are excluded from all three sets by definition. Descendants at any greater
depth are out of scope of all three sets.

Output separates **per-occurrence** from **de-duplicated names**, using the
qualified-name representation of Decision 10.2(b). The occurrence element is a
named structure:

    RootChildOccurrence
        root_child_position  int   -- 0-based index within root_direct_children
        tag_name            str   -- qualified name per Decision 10.2(b)

    root_direct_child_count           int; len(root_direct_children)
    non_record_root_element_occurrences
        ordered tuple of RootChildOccurrence, one entry per non-record root element
        occurrence, in document order
    unknown_root_child_count          int; len(non_record_root_element_occurrences)
    unknown_root_child_names          ordered tuple of str; the DISTINCT qualified
                                       tag names of the occurrences, de-duplicated
                                       ACROSS THE ROOT LEVEL, first-occurrence order

Agreement requirements:

    R1  unknown_root_child_count == len(non_record_root_element_occurrences)
    R2  unknown_root_child_names == distinct qualified tag names of those
        occurrences, de-duplicated across the root level, first-occurrence order
    R3  root_direct_child_count == N_source_loc + unknown_root_child_count

R3 follows from the partition above and is the check that keeps the reporting scope
and the indexing scope from being conflated. R2's scope (root level) is disjoint
from A2's scope (record level); the two name lists MUST NOT be merged or compared
for equality.

Textual content retention for a non-record root element is NOT claimed; that
content is available only at `L1`. Such an element is NOT a record, MUST NOT
affect Axis E eligibility, MUST NOT be persisted, and — per Decision 10.26 — MUST
NOT be assigned a `source_loc_index`.

**Decision 10.24 (unknown elements are not Axis S conditions).** Unknown child
elements at either level are covered by the non-failure list (Decision 10.13) and
by the declared deviations (§13). Their retention and reporting MUST NOT create a
new Axis S condition, and no Axis S condition may be defined over them.

**Decision 10.25 (channel 2 is not persisted).** `NON_ASSERTION_LOC` records are
emitted in the run result only. Persistence of per-resource records is deferred
(§12). Their continued recoverability rests on `L1` replay.

---

## 6. Classification Coverage Invariants (ST-EVA project contract)

**Decision 10.26 (the source set, established independently).** Using the sets
defined in Decision 10.23:

    N_source_loc   = len(source_records)
    source_indices = set(range(N_source_loc))

`source_loc_index` is defined **only over `source_records`**, ascending in document
order. `source_indices` MUST be established from `source_records` **before** any
Axis E evaluation and before either channel exists, from the complete and
not-yet-classified set. It MUST NOT be assembled from, reconciled against, or
derived from either channel, and it MUST NOT be extended to include
`non_record_root_elements`. The reporting scope of Decision 10.23
(`root_direct_children`, and hence `non_record_root_elements`) and the indexing
scope of this decision (`source_records`) are DISJOINT and MUST NOT be conflated
in any count, field name or invariant. The same separation applies to
`RecordChildOccurrence.source_loc_index`, whose values are drawn from
`source_indices` and from nowhere else.

**Decision 10.27 (invariants).** Both channels are index-bearing collections over
`source_indices`:

    C1  source_indices == set(range(N_source_loc))
    C2  eligible_indices.isdisjoint(non_assertion_indices)
    C3  eligible_indices | non_assertion_indices == source_indices
    C4  len(eligible_indices) == N_assertion_eligible
    C5  len(non_assertion_indices) == N_non_assertion
    C6  len(eligible_indices) + len(non_assertion_indices) == N_source_loc
    C7  each index is emitted exactly once within its channel
    C8  both channels preserve ascending source order

No invariant in this decision ranges over `root_direct_children` or
`non_record_root_elements`; those are reported but not indexed. C1–C8 hold
vacuously when `N_source_loc` is 0.

**Decision 10.28 (C2/C3 are the operative proof).** Disjointness rules out double
counting and union equality rules out omission; together they are the proof of "no
silent filtering". Aggregate totals alone are insufficient for this purpose and
MUST NOT be substituted for C2 and C3. This is a testable code contract, not a
schema change.

**Decision 10.29 (index is in-process).** `source_loc_index` is an in-process
verification device only. It is NOT persisted, requires no migration, and does not
enter the identity preimage.

---

## 7. Persistence, Identity Collapse and Run Metrics (ST-EVA project contract)

Only `ASSERTION_ELIGIBLE` records reach C2B / `authority_taxonomy_namespaces`. No
change to `0022`, to the `atn_` identity definition, or to
`record_authority_taxonomy_assertion.py`.

**Decision 10.30(a) (four metrics, each with an explicit scope).** Because the
writer returns the existing `authority_taxonomy_id` on identity collision instead
of inserting a row, four metrics are distinct and MUST be reported separately. No
metric may be computed over the whole table.

| Metric | Definition | Scope | Read or derived at |
|---|---|---|---|
| `writer_call_count` | number of `record_authority_taxonomy_assertion()` invocations in this execution | run-scoped | end of E4 |
| `unique_identity_count` | distinct identity preimages over admitted records in this execution | run-scoped | E3 |
| `document_row_total` | ALIAS of `document_row_total_after`; see Decision 10.30(b) | table-scoped by `document_id` D | E5 |
| `rows_inserted_this_run` | `document_row_total_after - document_row_total_before`, both read for the same D | table-scoped by `document_id` D | E5; computable only under Decision 10.32(a) |

**Decision 10.30(b) (before, after and the alias).** Because the same table is read
twice, the two readings are distinct quantities with distinct read points and are
each reported under their own name:

    document_row_total_before   read at P4; the SAME VALUE as the Class B quantity
                                baseline_document_row_total (Decision 10.39(b));
                                the two names denote one reading and MUST be equal
    document_row_total_after    read at E5
    document_row_total          ALIAS of document_row_total_after; the two names
                                denote one reading and MUST be equal

`document_row_total_before` and `document_row_total_after` are read at different
times and MUST NOT be asserted equal in general. Only the two alias identities
above are unconditional. An alias identity is a naming fact and is NOT evidence
that the shared value is correct.

**Decision 10.30(c) (invariants and the run classes).**

    I5a  document_row_total_after == unique_identity_count
    I5b  rows_inserted_this_run == document_row_total_after - document_row_total_before
    I5c  0 <= rows_inserted_this_run <= unique_identity_count
    I5d  FIRST:       the baseline identity set for D is empty
                      (equivalently baseline_authority_identity_count == 0
                       and document_row_total_before == 0)
    I5e1 FULL_REPLAY: the baseline identity set for D equals the expected identity
                      set; document_row_total_after == document_row_total_before;
                      rows_inserted_this_run == 0
    I5e2 RECOVERY:   the baseline identity set for D is a PROPER SUBSET of the
                      expected identity set; rows_inserted_this_run MAY be greater
                      than 0
    I5f  document_row_total(D) is INVARIANT to the presence of any other catalog
         document in the archive

I5a, I5b, I5c and I5f apply to ALL run classes. I5d, I5e1 and I5e2 are the
class-specific forms; run classification is defined at P4 by Decision 10.42(c) and
is defined on identity SETS, never on row counts alone.

**Decision 10.30(d) (derived property: post-run identity set).** After a successful
run on any legal class, the identity set stored for D equals the expected identity
set. Derivation: at P4 the baseline set is a subset of the expected set for every
legal class (Decision 10.42(c)); this run inserts only identities drawn from the
expected set; therefore the final set is a subset of the expected set; and I5a
together with `|expected| == unique_identity_count` gives a final cardinality equal
to the expected cardinality. Hence the two sets are equal. No additional emitted
field is required for this property.

**Decision 10.30(e) (worked illustration, non-normative).** A first run that
committed 57 rows and then raised at the 58th writer call leaves a baseline of 57
identities for a subsequent identical-bytes run. Provided those 57 identities are a
proper subset of the expected set and each stored identifier satisfies Decision
10.36(a), that run classifies as RECOVERY, inserts the remaining identities, and
ends at the expected set. The figures "57" and the implied insertion count are
**illustrative only**. They MUST NOT be encoded as test constants, and they do not
describe any particular document.

**Decision 10.31 (table-scoped metrics are scoped by document_id).** Both readings
underlying `document_row_total_after` and `rows_inserted_this_run` MUST filter on
`authority_taxonomy_namespaces.document_id` equal to the specified document `D`.
Whole-table `COUNT(*)` MUST NOT be used as an expected value for any metric in
Decision 10.30(a). When a future catalog version is admitted, `document_row_total`
for the earlier document remains scoped to that document.

**Decision 10.32(a) (concurrency precondition).** PRECOND-1: from the P4 reading
through the E5 reading, no other writer inserts, updates or deletes any row in
`authority_taxonomy_namespaces`. PRECOND-1 is an operator and harness obligation.
It is NOT established by this amendment, and no locking, transaction or other
mechanism is authorized here.

**PRECOND-1 is a concurrency precondition and is NOT a classification.** It
neither determines nor qualifies `run_class`; it is NOT a run class and NOT a
rejection outcome under Decision 10.42(d). A run in which PRECOND-1 cannot be
asserted still has a `run_class`, drawn from exactly the three values of Decision
10.34(a) field 21; only its acceptance expressions become UNVERIFIED under
Decision 10.32(c). PRECOND-1 failure MUST NOT be reported as a class, as a
rejection, or as a change of `run_class`.

**Decision 10.32(b) (computability of `rows_inserted_this_run`).**
`rows_inserted_this_run` is computable ONLY if PRECOND-1 is asserted. If PRECOND-1
is not asserted, the field is UNDEFINED, MUST NOT be assigned a value, and MUST NOT
be defaulted.

**Decision 10.32(c) (what becomes UNVERIFIED without PRECOND-1).** Without
PRECOND-1, EVERY acceptance expression whose left-hand side is
`document_row_total_after` or `rows_inserted_this_run` is UNVERIFIED and MUST NOT
be reported as passed. That set is exactly: I5a, I5b, I5c, I5e1, I5f, and the
RECOVERY acceptance condition of Decision 10.44. The baseline side of those
expressions is a single P4 reading and remains a well-defined observation.

**Decision 10.32(d) (what remains valid without PRECOND-1).** The following are
unaffected by concurrency and remain verifiable: C1–C8; A1–A4; V1–V4; R1–R3; the
Class A comparisons on `source_loc_count`, `assertion_eligible_count`,
`non_assertion_count`, `reason_distribution`, `unique_identity_count` and
`unique_authority_taxonomy_ids`; the CC-1 and CC-2 outcomes; the baseline checks
G1 and G2 of Decision 10.42(b); and the two alias identities of Decision
10.30(b). "Verifiable" here means the expression can be evaluated; it is not a
claim that the value is evidence about any concurrent activity, and a single E5
reading being well-defined does NOT make any before/after comparison verified.

**Decision 10.32(e) (failure before E5).** If the run does not reach E5 — including
a failure inside E4 — NO post-run acceptance expression may be claimed as passed.
`document_row_total_after`, `document_row_total` and `rows_inserted_this_run` MUST
be reported as not read. The run MUST NOT report success. Rows committed before
the failure remain in place; this amendment does not roll them back and does not
delete them.

**Decision 10.33 (per-call insert status not observable).** The writer's return type
remains `str` on both the collision path and the insert path (baseline
`record_authority_taxonomy_assertion.py` lines 98–103 and 137), so per-call insert
status is not observable to the caller, and the writer is NOT modified.
`rows_inserted_this_run` is therefore measured by the scoped before/after
difference of I5b.

**Decision 10.34(a) (output field contract).** The workflow result MUST carry
exactly the fields below, with the stated type, scope, read point and purpose. No
field required by Decisions 10.30(a)–(d), 10.35, 10.36(a)–(d), 10.42(c), 10.42(d) or 10.44 may
be omitted,
and no additional persistence of any field is authorized (§12).

| # | Field | Type | Scope | Read or derived at | Verification purpose |
|---|---|---|---|---|---|
| 1 | `source_loc_count` | int | run; over `source_records` | E2 | Class A; C4 + C6 |
| 2 | `root_direct_child_count` | int | run; over `root_direct_children` | E2 | R3 |
| 3 | `non_record_root_element_occurrences` | ordered tuple of `RootChildOccurrence` | run | E2 | R1, R2 |
| 4 | `unknown_root_child_count` | int | run | E2 | R1 |
| 5 | `unknown_root_child_names` | ordered tuple of str | run; de-duplicated, first-occurrence order | E2 | R2 |
| 6 | `unknown_record_child_occurrences` | ordered tuple of `RecordChildOccurrence` | run; over `source_records` | E2 | A1, A2, A3, A4, V1, V2 |
| 7 | `unknown_record_child_count` | int | run | E2 | A1 |
| 8 | `unknown_record_child_names` | ordered tuple of str | run; de-duplicated across all records, first-occurrence order | E2 | A2 |
| 9 | `assertion_eligible_count` | int | run | E2 | Class A; C4 |
| 10 | `non_assertion_count` | int | run | E2 | Class A; C5 |
| 11 | `reason_distribution` | mapping reason code to int | run | E2 | Class A reason distribution |
| 12 | `non_assertion_records` | ordered tuple of channel-2 records, ascending by `source_loc_index` | run | E2 | C5, C7, C8 |
| 13 | `unique_identity_count` | int | run | E3 | 10.30(a) metric 2; I5a |
| 14 | `unique_authority_taxonomy_ids` | ordered tuple of str, lexicographically sorted ascending, no duplicates | run | E3 | 10.35 |
| 15 | `writer_call_count` | int | run | end of E4 | 10.30(a) metric 1; 10.34(b) |
| 16 | `assertion_count` | int | run | end of E4, from the SAME tally as `writer_call_count` | 10.34(b); == `assertion_eligible_count` |
| 17 | `authority_taxonomy_ids` | ordered tuple of str, one per writer call, in writer call order; MAY contain duplicates | run | end of E4 | 10.34(b) |
| 18 | `baseline_source_document_row` | int | table-scoped by content_hash H | P2 | 10.39(b); Decision 10.40 cross-check |
| 19 | `baseline_document_row_total` (alias `document_row_total_before`) | int | table-scoped by `document_id` D | P4 | I5b, I5d, I5e1, I5e2; 10.42(c) |
| 20 | `baseline_authority_identity_count` | int | table-scoped by `document_id` D | P4 | I5d; G1; 10.42(c) |
| 21 | `run_class` | str; value domain exactly {`FIRST`, `FULL_REPLAY`, `RECOVERY`}; NOT emitted on a pre-check rejection | run; assigned only on the three admitted branches | P4 | 10.42(c); selects the applicable acceptance rule in 10.44; mutually exclusive with field 25 |
| 22 | `document_row_total_after` | int | table-scoped by `document_id` D | E5 | I5a, I5b, I5e1 |
| 23 | `document_row_total` | int | table-scoped by `document_id` D | E5; ALIAS of `document_row_total_after` | 10.30(a) metric 3 |
| 24 | `rows_inserted_this_run` | int | table-scoped by `document_id` D | E5; only under PRECOND-1 | 10.30(a) metric 4; I5b, I5c |
| 25 | `baseline_rejection` | structured value per Decision 10.42(d): `outcome` str; `reason_codes` ordered tuple of str; `offending_identities` ordered tuple of str; `expected_count` int; `baseline_count` int; `document_id` str; NOT emitted on an admitted run | run; rejection outcome only | P4, at rejection | 10.42(d); mutually exclusive with field 21 |

`run_class` (field 21) and `baseline_rejection` (field 25) are mutually exclusive:
an execution emits at most one of them. The three run classes describe successful
runs; `baseline_rejection` describes a pre-check rejection and is not a run class
(Decision 10.42(d)).

The identity sets themselves — `baseline_authority_identities`,
`baseline_authority_id_map`, `expected_identity_preimages` — are NOT emitted. They
are internal to the P4 precheck (Decision 10.42(b)) and to the harness-side Class A
computation. A harness that needs them may recompute them read-only from the same
definitions; their absence from the result is deliberate and is not an omission
from the acceptance rules. The rejection structure of Decision 10.42(d) reports
the offending identity strings themselves, so a rejection remains diagnosable
without emitting either set in full.

**Decision 10.34(b) (`assertion_count`, and the shared tally).** `assertion_count`
is the number of records admitted to C2B, which is the writer call count. For any
catalog in which every record is eligible the value is unchanged. For a catalog
containing `NON_ASSERTION_LOC` records, those records are no longer included in the
figure (row B-33).

`assertion_count` and `writer_call_count` are two NAMES for one underlying tally —
the number of writer invocations — and MUST be equal. They are retained as two
fields because Decision 10.30(a) names `writer_call_count` while the pre-existing
workflow contract names `assertion_count`. They are NOT two independent
measurements and MUST NOT be presented or compared as such.

**Decision 10.34(c) (superseded reading, explicitly withdrawn).** An earlier draft
stated that the existing assertion `assertion_count > 0` "remains valid". That
statement is **withdrawn as a general contract claim**. The surviving compatibility
statement is narrow: the existing assertion
`len(authority_taxonomy_ids) == assertion_count` continues to hold, including at
zero. The existing assertion `assertion_count > 0` is satisfied by the current test
fixture because that fixture contains at least one eligible record; it is NOT a
requirement of this amendment, and this amendment does not make it a precondition
for a valid run.

**Decision 10.34(d) (zero-assertion cases).** Two legal cases produce a zero
admission count, and neither is an error:

1. `N_source_loc` is 0. Both channels are empty; C1–C8 hold vacuously (Decision
   10.27); no writer call occurs; `assertion_count` is 0; `writer_call_count` is 0;
   `unique_identity_count` is 0; `unique_authority_taxonomy_ids` is the empty
   tuple; `reason_distribution` is empty. Zero records is expressly NOT an Axis S
   refusal (Decision 10.13, row B-25).
2. `N_source_loc` is greater than 0 and every record is `NON_ASSERTION_LOC`. Then
   `non_assertion_count == N_source_loc`, `assertion_eligible_count` is 0, and the
   remainder of case 1 applies.

In both cases the run MUST NOT call the C2B writer at all, and all count and
invariant relations of Decisions 10.27 and 10.35 remain consistent at zero. No Axis
S condition may be introduced for either case, and no undeclared
`assertion_count > 0` assumption may be used to fail either case.

**Decision 10.35 (cardinality relations, and their precondition).** The following
hold by construction, unconditionally, including at zero:

    assertion_count == assertion_eligible_count
    writer_call_count == assertion_count
    source_loc_count == assertion_eligible_count + non_assertion_count
    len(authority_taxonomy_ids) == assertion_count
    set(unique_authority_taxonomy_ids) == set(authority_taxonomy_ids)
    sum(reason_distribution.values()) >= non_assertion_count
    len(non_assertion_records) == non_assertion_count
    root_direct_child_count == source_loc_count + unknown_root_child_count
    unknown_record_child_count == len(unknown_record_child_occurrences)
    unknown_root_child_count  == len(non_record_root_element_occurrences)
    document_row_total        == document_row_total_after
    document_row_total_before == baseline_document_row_total

The following hold ONLY in the absence of an identity-to-identifier collision as
defined in Decisions 10.36(a)–(d), and are subject to Decision 10.32(c):

    len(unique_authority_taxonomy_ids)  == unique_identity_count
    document_row_total_after           == unique_identity_count    (I5a)
    len(unique_authority_taxonomy_ids) == document_row_total_after

The following is FORBIDDEN as a verification rule:

    assert db_row_count == result["assertion_count"]

**Decision 10.36(a) (identity formula, unchanged).** The identifier is defined, at
the baseline commit (`record_authority_taxonomy_assertion.py` lines 51–54), as:

    authority_taxonomy_id = "atn_" + sha256(
        canonical_json(preimage).encode("utf-8")
    ).hexdigest()[:32]

The identity is the verbatim canonical JSON preimage of
`{document_id, namespace_uri, provider, taxonomy_family, taxonomy_version}`, and
the stored `authority_taxonomy_identity` column holds that preimage verbatim.
Consequently the digest input is the UTF-8 encoding of the stored identity string,
and an existing row's identifier can be re-derived directly from that column
without re-canonicalising anything. **This amendment changes neither the identity
nor this derivation.** The formula is restated so that the checks below refer to
the exact derivation in force.

**Decision 10.36(b) (injectivity is not established).** Being a pure function of
the identity does NOT establish injectivity: the digest is truncated to 32
hexadecimal characters, so distinct identity preimages may in principle map to the
same identifier. This amendment therefore does NOT assert a one-to-one mapping
between identities and identifiers.

**Decision 10.36(c) (collision space).** The collision space covered here has two
components. This count is definitional — it bounds the space this decision
addresses, and is not a claim that no other failure exists.

- **CC-1 — within this run.** Two eligible records of THIS run with DISTINCT
  identity preimages resolve to the same `authority_taxonomy_id`.
- **CC-2 — against existing rows.** An `authority_taxonomy_id` newly computed in
  THIS run is already present in `authority_taxonomy_namespaces` under a DIFFERENT
  `authority_taxonomy_identity`. This includes rows belonging to other catalog
  documents already stored in the shared archive.

An existing row carrying the SAME identity is ordinary idempotent replay and is
NOT a collision. It MUST NOT be reported as one.

**Decision 10.36(d) (execution point and fail-closed behaviour).** CC-1 and CC-2
MUST both be evaluated over ALL eligible records BEFORE the first C2B writer call,
as part of the E3 gate of Decision 10.45. CC-2 is evaluated by read-only queries
over `authority_taxonomy_namespaces`; no writer, schema or migration change is
required or authorized.

If either check fails, the run MUST fail closed. It MUST terminate with an error
and MUST NOT report success; it MUST NOT begin any C2B write at all; it MUST NOT
merge the colliding records, MUST NOT treat either as a duplicate of the other,
and MUST NOT persist either as though no collision occurred; and it MUST NOT
continue ingestion of any further record.

Evaluating both checks before the first writer call is what makes the requirement
"MUST NOT begin any C2B write at all" achievable: the baseline writer commits per
record, so a collision detected only at the offending insert would leave previously
committed rows in place.

The concrete exception type used to signal this failure is an implementation
choice and is NOT fixed by this amendment, provided it is distinguishable from other
failure modes. Fail-closed specifies the required OUTCOME.

**Decision 10.37 (disclosed pre-existing identity collapse).** The frozen preimage
`{document_id, namespace_uri, provider, taxonomy_family, taxonomy_version}`
excludes `href` (Amendment 6). For the captured catalog, 201 eligible records yield
194 distinct identities. Seven records collapse into existing identities: six are
byte-identical duplicate `href` repeats within the CYD family; one namespace,
`http://xbrl.org/2020/extensible-enumerations-2.0`, is declared under two distinct
URLs (`https://...xsd` and `http://...xsd`), and the writer stores neither a second
row nor the second URL on the existing row. This collapse is DISTINCT from a
collision: here several records share ONE identity, whereas a collision would be
several identities sharing ONE identifier, or one new identity colliding with one
existing identity.

**Decision 10.38 (values are document-specific).** The values 203 / 201 / 2 / 194
describe THIS captured document only. The contract is the invariant family of §4–§8,
not those numbers. No test may encode 194, 201, 203, 57 or any other observed count
as a universal constant across documents.

---

## 8. Pre-Run Expectations and Ordering (ST-EVA project contract)

**Decision 10.39(a) (Class A — source-derived expectations).** Computed before the
run from the workflow's input payload bytes:

    expected_source_loc_count          int
    expected_assertion_eligible_count  int
    expected_non_assertion_count       int
    expected_reason_distribution       mapping reason code to int
    expected_identity_preimages        ordered tuple of distinct canonical-JSON
                                       identity strings, lexicographically sorted
    expected_unique_identity_count     int; == len(expected_identity_preimages)

For each expected eligible record the preimage
`{document_id, namespace_uri, provider, taxonomy_family, taxonomy_version}` is
formed with the document `D` of Decision 10.40, canonicalised exactly as in
Decision 10.36(a), and de-duplicated. Denote the resulting set `E`.

**Decision 10.39(b) (Class B — database baselines).** Obtained by read-only query,
and NOT derivable from the payload bytes:

    baseline_source_document_row       int; COUNT(*) FROM source_documents
                                       WHERE content_hash = H                    (P2)
    baseline_document_row_total        int; COUNT(*) FROM
                                       authority_taxonomy_namespaces
                                       WHERE document_id = D                    (P4)
    baseline_authority_identity_count  int; COUNT(DISTINCT
                                       authority_taxonomy_identity)
                                       WHERE document_id = D                    (P4)
    baseline_authority_identities      ordered tuple of distinct identity strings
                                       for D, lexicographically sorted          (P4)
    baseline_authority_id_map          mapping identity -> authority_taxonomy_id
                                       for D                                               (P4)

Denote the set of `baseline_authority_identities` by `B`.

**Decision 10.39(c) (circularity prohibition).** No Class A quantity may be derived
from the run's own output, and no Class B quantity may be derived from the payload.
Deriving an expectation from the run's output and then comparing that output to the
same expectation is circular and FORBIDDEN. A missing database baseline MUST NOT be
substituted by a value reconstructed from the payload, and a row count MUST NOT be
substituted for an identity-set comparison.

**Decision 10.40 (mutual independence of pre-run quantities).** Four pre-run
quantities are established independently, each from exactly one permitted source:

| Quantity | Sole permitted source |
|---|---|
| `candidate_sha256` | independently computed SHA-256 over the input payload bytes |
| document `D` | existing content-addressing convention applied to `candidate_sha256`: `"doc_" + sha256(candidate_sha256.encode("utf-8")).hexdigest()[:24]` |
| Class A | independent reference enumeration over the input payload bytes (Decision 10.41) |
| Class B | read-only SQL queries scoped to `D` and `H` respectively |

No quantity may be derived from another, from the production parser, or from any
workflow write, except that `D` is derived from `candidate_sha256` by the
convention stated above. When a `source_documents` row for `candidate_sha256`
already exists, its stored `content_hash` MUST equal `candidate_sha256`, and the
bytes returned by `content_for(D)` MUST be byte-equal to the input payload; both
are read-only cross-checks, and neither may replace the independent computation.

**Decision 10.41 (Class A independence).** Class A MUST be produced by an
independent reference enumeration and MUST NOT be produced by the production parser
`parse_edgar_taxonomies_catalog`, nor by any code path the production parser
shares. The reference enumeration must therefore also reproduce the canonical
identity preimage of Decision 10.36(a) for each expected eligible record,
independently of the production writer. If the reference enumeration and the
production parser or writer are later refactored to share a helper, the independence
is void and this contract is violated. The reference enumeration exists for
verification only; it MUST NOT be imported by, or reachable from, production parser
or workflow code. Its location — a test-only reference, or an offline verification
step — is an implementation decision not fixed by this amendment.

**Decision 10.42(a) (pre-run order on Path A; all read-only, all before any
write).**

    P0  obtain the input payload (supplied bytes; the workflow MUST NOT perform a
        network fetch when payload bytes are supplied)
    E0  Stage 0 admission guard (Decision 10.7(b)); on failure the run stops here,
        on Path R
    P1  compute candidate_sha256 independently
    P2  read-only lookup of source_documents by content_hash = candidate_sha256;
        establish D; read-only cross-checks per Decision 10.40
    P3  compute Class A by independent reference enumeration
    P4  compute Class B by read-only query; perform the baseline checks of Decision
        10.42(b); classify the run under Decision 10.42(c)

P0 through P4 are read-only and MUST complete before any workflow write. P1 through
P4 exist only on Path A; on Path R the run terminates at E0.

**Decision 10.42(b) (baseline consistency checks at P4).** Before any C2B write, the
following are verified against Class B:

    G1  baseline_document_row_total == baseline_authority_identity_count
        (0022 declares authority_taxonomy_identity UNIQUE; a mismatch indicates a
         corrupt or unexpected state)
    G2  for every (identity, stored_id) in baseline_authority_id_map:
        recomputed := "atn_" + sha256(identity.encode("utf-8")).hexdigest()[:32]
        recomputed == stored_id

The re-derivation in G2 is exact because `authority_taxonomy_identity` holds the
canonical JSON preimage verbatim (Decision 10.36(a)). A failure of G1 or G2 is a
**pre-check rejection under Decision 10.42(d)**; it is NOT a run class and it
produces no successful workflow result. No new migration, schema or writer
capability is used or authorized.

**Decision 10.42(c) (run classification at P4).** Using `E` from Decision 10.39(a)
and `B` from Decision 10.39(b), evaluated in this order:

    if B is empty                                         -> FIRST
    elif G1 and G2 hold and B == E                        -> FULL_REPLAY
    elif G1 and G2 hold and B is a PROPER SUBSET of E      -> RECOVERY
    else                                                   -> INCONSISTENT_BASELINE

`INCONSISTENT_BASELINE` covers every remaining situation, in particular: `B`
contains any identity outside `E`; `B` is a strict superset of `E`; `B` and `E` are
incomparable; or G1 or G2 failed. A row count equal to the expected count does NOT
establish `B == E` and MUST NOT be used in place of the set comparison, and a
baseline larger than the expected set is NOT a legal RECOVERY.

`FIRST` is tested first, so the case `E` empty and `B` empty classifies as `FIRST`.
`run_class` is assigned ONLY on one of the three admitted branches above, and is
then emitted as field 21 of Decision 10.34(a). On the `INCONSISTENT_BASELINE`
branch no run class is assigned, `run_class` is reported as not emitted, and the
run is a pre-check rejection under Decision 10.42(d).

A run class describes ONLY the database state observed at P4. It is **not** evidence
that any past workflow execution succeeded, and no inference about history is
permitted from it.

**Decision 10.42(d) (pre-check rejection outcome; distinct from a run class).**
`INCONSISTENT_BASELINE` is a **pre-check rejection outcome**. It is NOT a run
class, NOT a workflow result, NOT a successful outcome of any kind, and NOT a fourth
class. It MUST NOT be added to the value domain of `run_class`, MUST NOT be
presented as a class of run, and MUST NOT be counted among the three run classes of
Decision 10.30(c).

A run that reaches `INCONSISTENT_BASELINE` at P4:

- MUST terminate with an error and MUST NOT report success;
- MUST NOT execute E1 and MUST NOT perform any database write of any kind. The
  ordering of Decisions 10.42(a) and 10.45 — P4 precedes E1 — is what guarantees
  this; no other mechanism is involved and none is authorized;
- MUST NOT assign, emit or imply any `run_class`;
- MUST report `document_row_total_after`, `document_row_total` and
  `rows_inserted_this_run` as not read, consistently with Decision 10.32(e);
- MUST NOT be evaluated against Decision 10.44 or against the class-specific forms
  I5d, I5e1 and I5e2, none of which applies to it.

**Diagnostics ARE provided.** The rejection emits exactly one structure,
`baseline_rejection` (field 25 of Decision 10.34(a)):

    baseline_rejection
        outcome              str; always "INCONSISTENT_BASELINE"
        reason_codes         ordered tuple of str, each drawn from this CLOSED
                             vocabulary, listed in a deterministic order:
                               G1_ROW_COUNT_IDENTITY_COUNT_MISMATCH
                               G2_IDENTITY_ID_MISMATCH
                               BASELINE_HAS_IDENTITY_OUTSIDE_EXPECTED
                               BASELINE_IS_SUPERSET_OF_EXPECTED
                               BASELINE_INCOMPARABLE_WITH_EXPECTED
        offending_identities ordered tuple of str; the verbatim stored identity
                             strings responsible, lexicographically sorted — for
                             G2, the identities whose stored identifier does not
                             match the derivation of Decision 10.36(a); for the
                             set cases, the members of B not in E together with
                             the members of E not in B
        expected_count       int; len(E)
        baseline_count       int; len(B)
        document_id          str; the D of Decision 10.40

`baseline_rejection` is a rejection result only. It is NOT a workflow result, MUST
NOT be presented as one, and MUST NOT be combined with any `run_class`. Any code
outside the reason vocabulary is a contract violation.

**Decision 10.43 (expected values for the captured catalog).** Class A:
`expected_source_loc_count` 203, `expected_assertion_eligible_count` 201,
`expected_non_assertion_count` 2, `expected_unique_identity_count` 194, reason
distribution `{namespace_absent: 2}` with all other codes absent; `E` therefore has
194 elements. Class B on the archive holding
`doc_eb3d9eb2f741a4e844f7ed11`: `baseline_source_document_row` 1,
`baseline_document_row_total` 0, `baseline_authority_identity_count` 0, `B` empty,
and G1 and G2 hold vacuously. The run class at P4 is therefore `FIRST`, and no
pre-check rejection under Decision 10.42(d) arises for this archive at the stated
Class B.

**Decision 10.44 (post-run comparison, by run class).** On Path A, after the run:

- universal, all run classes: `unique_identity_count` equals Class A
  `expected_unique_identity_count`; `source_loc_count` equals Class A
  `expected_source_loc_count`; `assertion_eligible_count` equals Class A
  `expected_assertion_eligible_count`; `non_assertion_count` equals Class A
  `expected_non_assertion_count`; `reason_distribution` equals Class A
  `expected_reason_distribution`; `document_row_total_before` equals Class B
  `baseline_document_row_total`.
- table-scoped, subject to Decision 10.32(c): `document_row_total_after` equals
  `unique_identity_count` (I5a); `rows_inserted_this_run` equals
  `document_row_total_after` minus `document_row_total_before` (I5b); and
  `rows_inserted_this_run` lies between 0 and `unique_identity_count` (I5c).
- class-specific: `FIRST` requires I5d; `FULL_REPLAY` requires I5e1, including
  `rows_inserted_this_run == 0`; `RECOVERY` requires I5e2, in which
  `rows_inserted_this_run` MAY exceed 0 and the acceptance condition is I5a
  together with the derived property of Decision 10.30(d), namely that the identity
  set stored for D equals `E`.

On Path R, for any run that does not reach E5 (Decision 10.32(e)), and for any
pre-check rejection under Decision 10.42(d), no post-run comparison applies and none
may be claimed.

---

## 9. Workflow Execution Order (normative gate)

**Decision 10.45 (order).**

    P0    obtain the input payload
    E0    Stage 0 admission guard                      (Decision 10.7(b))
          -- refused here: STOP, Path R, no database write --
    P1..P4  read-only pre-run steps, ending with the baseline checks and run
            classification (Decisions 10.42(a)–(c))
    E1    C1: record the source document (existing idempotent path)
    E2    C2A: Axis S, then Axis E — producing both channels
    E3    execute invariants C1..C8, agreement requirements A1..A4 and R1..R3,
          validations V1..V4, then collision checks CC-1 and CC-2
    E4    only after E3 passes in full: call the C2B writer for eligible records;
          if the eligible set is empty, make no writer call at all
          (Decision 10.34(d))
    E5    read post-run metrics, apply Decision 10.44 for the run class

**Decision 10.46 (gate before C2B).** C1–C8, A1–A4, R1–R3, V1–V4, CC-1 and CC-2
are evaluated at E3, after C2A has produced both channels and BEFORE the first C2B
writer call. Any violation MUST raise an error. It MUST NOT be reported as a
warning, a status value, or a partial result, and no eligible record may be
persisted before the gate passes. Stage 0 and Axis S failures are refusals that
occur earlier, at E0 and E2 respectively, and never reach E3. This does not preclude
unrelated failures during database writing; it prevents the classification,
reporting and identifier contracts from being violated while rows have already
landed.

**Decision 10.47 (gate scope, and the data state after an E3 failure).** The gate
governs C2B writes only. E1's source-document record is an existing idempotent
behaviour and may already be committed; that is permitted and preserves the bytes
unchanged.

On failure at E3:

- this execution MUST NOT have begun any C2B write;
- every `authority_taxonomy_namespaces` row that existed before this execution is
  unchanged;
- `document_row_total_before`, `B` and the `run_class` computed at P4 therefore
  remain valid for any subsequent identical-bytes run;
- the claim "this document has zero authority rows" holds ONLY under the additional
  condition that `B` is empty, i.e. only for `run_class` `FIRST`. Under
  `FULL_REPLAY` and `RECOVERY` it does not hold and MUST NOT be asserted.

A failure at E4 is OUTSIDE the gate's guarantee: the baseline writer commits per
record, so an E4 failure MAY leave partially committed rows. Those rows are left in
place; this amendment does not roll them back and does not delete them (Decision
10.32(e)). They are exactly the condition that makes a subsequent identical-bytes
run a candidate for `RECOVERY` under Decision 10.42(c), subject to the subset and
G1/G2 conditions there.

---

## 10. Evidence Fidelity — Two Guarantee Layers (ST-EVA project contract)

The word "verbatim" alone is retired from this amendment's operative text.

**Layer `L1` — `BYTE_EXACT_SOURCE`.** The gzip-stored payload retrieved through the
existing `content_for(document_id)`; SHA-256
`c639c18647c52a594c74eb60573851de15b7391de84a723cd3b7cced15f0341b`. The only
byte-exact evidence, and the only layer from which any record — including unknown
child elements at either level — may be replayed.

**Layer `L2` — `SOURCE_DECLARED_TEXT`.** Field values defined as the element text
with leading and trailing whitespace removed (current `.strip()`); interior
characters preserved; no case folding, no Unicode normalization, no URI resolution
or normalization, no truncation.

**Decision 10.48 (layers are distinct).** `L1` and `L2` are different guarantee
levels and MUST NOT be described with the same word. `L2` values are not
byte-identical to the raw XML character data. Channel-2 records are `L2`; they exist
for classification, counting and diagnosis, and MUST NOT be presented as a
substitute for `L1` or as proof that every field of every record is retained in
structured form.

**Decision 10.49 (no text-handling change).** This amendment does NOT change
`.strip()` behaviour and does NOT change any identity text handling. A future
change to text extraction or normalisation requires its own decision plus an
explicit identity impact analysis.

---

## 11. Relationship to Amendments 1–9 (no existing text is modified)

**Decision 10.50 (no modification; byte-identity condition).** This amendment edits,
strikes and annotates NO existing section of the formal ADR. Amendments 1–9 and all
earlier text remain byte-identical. The condition that must hold for any future
write is: the formal ADR's first 2,597 lines remain byte-identical to the baseline
commit (file SHA-256 baseline
`b5b00556e15e657256711c4349ebd97fba6d172dfe3fa9d2c777fda0b866a333`), and this
amendment appears only as an append after line 2597. **While this document is a
DRAFT it does not authorize that append**; the append requires a separate, explicit
authorization after formal ratification of this text.

**Decision 10.51 (precedence, narrow scope, and commencement).** Upon formal
ratification of this amendment, and only then, where it conflicts with existing text
it governs FOR C2A OPERATION ONLY. Outside C2A operation, existing text is unchanged
and remains in force. **While this document is a DRAFT, no precedence is claimed and
nothing in it displaces any existing text.**

**Decision 10.52 (what is withdrawn, and its provenance).** Upon ratification, for
C2A operation, the reading that every record declares a `<Namespace>` — implicit in
the record-structure note at ADR §15.3 and enforced by the baseline parser (lines
89–92 and 98–100) — is withdrawn as a validity criterion. The original text is NOT
rewritten; it remains in place as a historical record, and Decisions 10.1, 10.15 and
10.18 supply the operative rule. For C2A, presence of `Namespace`, `Family` and
`Version` is optional and governs eligibility (Axis E), not validity (Axis S).

**Decision 10.53 (filter prohibition retained).** The ADR §15.3 prohibition on
filtering by `file_type` is RETAINED and is NOT relaxed. Classification may not use
`file_type` semantics, filename or path shape. What is replaced is silent omission:
every record must be countable, traceable to `L1`, and explainable by a closed reason
code.

**Decision 10.54 (this amendment is not itself an authorization).** **While this
document is a DRAFT, it confers no authorization of any kind** — not an ADR append,
not an implementation, not a schema or migration change, not a database operation.
Upon formal ratification, and only then, this amendment becomes the separate
authorization basis for the changes it describes, distinct from and without
retroactive effect on Amendment 9's own execution, whose "ZERO changes to code,
tests, migrations, schemas, or DB" row describes that execution alone.

---

## 12. Explicit Non-Authorizations and Deferrals

No migration `0023`; no change to migrations 0001–0022; no change to the `atn_`
identity definition and no change to the derivation stated in Decision 10.36(a); no
change to the 10-field `ParsedAuthorityAssertion` projection; no change to
`record_authority_taxonomy_assertion.py`; no change to `sqlite_archive.py`,
`authority_evidence_resolver.py` or `authority_evidence_gate.py`; no change to
Observation or evidence identity; no B2 activation; no C4G re-implementation; no
`observation_filing_document_facts` / `observation_filing_documents` writes; no
cross-archive reads, `ATTACH` or cross-database foreign keys; no re-fetch or
replacement of the captured SEC bytes; no writes to `data/archives/*.sqlite`; no
persistence of `source_loc_index` or of channel-2 records; no persistence of unknown
child elements at either level, including no persistence of
`RecordChildOccurrence`, `RootChildOccurrence`,
`unknown_record_child_occurrences`, `non_record_root_element_occurrences`,
`baseline_authority_identities`, `baseline_authority_id_map`,
`expected_identity_preimages`, `run_class`, `baseline_rejection`, or any occurrence or
name list defined
by Decisions 10.21, 10.22(a) and 10.23; no persistence of any field of the Decision
10.34(a) contract; **no namespace-aware lookup contract** and no relaxation of that
limitation, per Decision 10.2(c); no XSD validator dependency; no child-order,
version-pattern or datatype validation; no new locking, transaction or concurrency
mechanism; no rollback or deletion of partially committed authority rows; no new
exception type for Stage 0 or Axis S failures; no new writer API — the baseline
consistency and collision checks are performed by the workflow using read-only
queries; no production parser or workflow code path may be used as the source of
pre-run expectations (Decision 10.41); no ADR write; no schema-file or WAL/SHM
sidecar cleanup bundled with this work.

**Deferred (former Option C):** a dedicated catalog-resource relation remains
UNPROVEN and unauthorized. It requires its own ADR, its own migration, and an
explicit identity-extension decision on whether `href` enters identity.

---

## 13. Declared Deviations from the Authority's Schema

1. Non-standard record elements and non-record root elements are retained and
   reported rather than refused, and repeated non-standard elements do not trigger
   S3 (§5 Decisions 10.22(a)–(e), 10.23; §3 Decisions 10.11, 10.13).
2. Axis S does not validate child element order, the `version` pattern, or child
   value datatypes, and does not perform full-document XSD validation (§3,
   Decision 10.14).

Each deviation is deliberate, bounded, reported, and non-silent. No other deviation
exists. Per Decision 10.12(d), BC-1, BC-2, BC-3, BC-4 and BC-5 are alignments with
the authority's schema rather than deviations from it, and CR-1…CR-6 are relaxations
of a consumer-side rule that the authority never stated; none is listed here.

---

## 14. Claim Statuses (Unchanged)

- **C3:** `NOT PROVEN`
- **C7:** `NOT PROVEN`
- **C9:** `UNAVAILABLE / UNPROVEN`
- **C10:** `UNAVAILABLE`

Retaining SEC catalog records that do not satisfy this project's assertion
eligibility contract is not, and must not be represented as, proof of any taxonomy
equivalence.