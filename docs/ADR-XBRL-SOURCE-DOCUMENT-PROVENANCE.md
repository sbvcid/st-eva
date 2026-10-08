# ADR: XBRL Source-Document Provenance Identity (Phase 3C-A Close-Out)

**Status:** FROZEN — architectural decision record. **Not implemented.** No production, schema, migration, or test change accompanies this document.
**Date:** 2026-10-08
**Baseline:** `8a0a487` (`feat: extract SEC filing document statements`), working tree clean, `HEAD == origin/master`
**Scope:** ST-EVA Evidence Provenance Layer — `observation_filing_documents`, `source_fact_id`, and the boundary between a fact's *document* and a fact's *filing*
**Binding invariants:** `docs/ST-EVA-ARCHITECTURE.md` §D invariants 20–23, and §D invariant 19 (unchanged, extended in effect by Decision 3)

> Phase 3C-B is **not authorized by this document.** This record freezes five
> questions that must be decided before any code is written, because every one of
> them has at least one implementation that is easier and wrong.

---

## 1. Context & Problem Statement

`archive/migrations/0020_sec_provenance.sql:558-568` created
`observation_filing_documents`, a link from an observation to one filing document:

```sql
PRIMARY KEY (observation_id, asset_id, accession, filename),
FOREIGN KEY (asset_id, accession, filename)
    REFERENCES filing_documents(asset_id, accession, filename)
```

Its comment says the link is mandatory because "the document a fact came from is
NOT inferable": on one measured filing the diluted-EPS facts came from an
`EX-101` instance while the `EX-99.1` exhibit carried no inline XBRL at all.
The relation exists to stop an accession from being read as naming a document.

Phase 3C-A established six facts that make writing into it non-trivial:

1. `source_fact_id` is **accession-scoped, not document-scoped.** Production wires
   `document_ref=accession or document_hash` and `context=accession`
   (`sec_ingest.py:2247,2252`). No document is in the fact's identity.
2. **XBRL `contextRef` is not preserved.** The SEC `companyconcept` endpoint does
   not return it and `SecFact` has no field for it (`sec_provider.py:825-848`,
   `concept_history` → `company_concept`, `:2025-2039`). ST-EVA does not lose it; it
   is never delivered.
3. **Legacy XBRL yields cardinality 1** — the 2013 diluted-EPS facts occur in one
   document (`EX-101.INS`).
4. **Modern inline XBRL yields cardinality 2** — the verified AAPL 8-K
   `0000320193-26-000018` presents one fact in the filed primary document
   `aapl-20260730.htm` (SGML ordinal 1, `<TYPE>8-K</TYPE>`) *and* in
   `aapl-20260730_htm.xml` (SGML ordinal 7, `<TYPE>XML</TYPE>`), the EDGAR-generated
   extraction of that same inline document. 17 directory entries, 14 `<DOCUMENT>`
   blocks, 0 positional agreement between the manifests
   (`tests/test_sec_document_bytes.py:59-97`).
5. **Current evidence cannot distinguish the two.** Invariant 19
   (`docs/ST-EVA-ARCHITECTURE.md:394-410`) is a verified finding: extension and
   `<TYPE>` are shared between filer resources and EDGAR renderings
   (`aapl-20260730_htm.xml` and `report.css` are both `<TYPE>XML</TYPE>`).
6. **The PK fits an exact assertion, not a candidate set.** No ordinal, no
   confidence, no role column exists — and adding one would be a schema decision,
   not an implementation detail.

Phase 3C-A also proposed `scan captured documents for concept + period → cardinality`.
Decision 5 (§2) rejects it, with repository evidence.

---

## 2. Frozen Decisions

### Decision 1 — `observation_filing_documents` means `EXACT_SOURCE_DOCUMENT_ASSERTION`

The relation asserts exactly one thing: **this observation was read out of this one
filing document, and no other reading is claimed.**

Rejected alternatives, each for a stated reason:

| Rejected meaning | Why it is rejected |
| --- | --- |
| candidate document | The PK has no slot to say "candidate". A second row is indistinguishable from a second assertion, so a reader cannot tell a guess from a proof. |
| supporting document | A fact about the *provenance of the evidence* belongs to `observation_sources` / `filing_document_captures`. It does not locate the observation. |
| duplicate occurrence | Two renderings of one XBRL fact are one assertion about the world. Recording both manufactures a second independent reading and destroys the 2.3-B validation basis (`evidence_model.py:15-19`). |
| "document containing an equivalent fact" | Equivalence is a judgement. This relation may not host one; mapping equivalence already has to be `EXACT` or it is refused (`mapping_type`). |

**The relation has exactly one meaning. Any second meaning requires a new relation
and a new ADR, not a reuse of this one.**

### Decision 2 — Cardinality is 0 / 1 / none

| Rows | State |
| --- | --- |
| 0 | `UNAVAILABLE` / unresolved — **not** an error, **not** a gap to fill |
| 1 | the exact source-document assertion |
| 2 or more | **no assertion.** The evidence names more than one document, so the assertion cannot be made |

Explicitly prohibited, absent a separately justified architecture decision:

- confidence scores or weights of any kind;
- candidate rows;
- ordering tiebreaks ("first by filename", "first by manifest ordinal", "prefer the primary");
- deleting or superseding an existing row to resolve a cardinality that later turns out to be wrong.

**The cardinality check is a producer-side precondition, not a schema guarantee.**
The relation cannot see the candidate set, so the database cannot enforce this. It
must therefore be enforced by the producer and **pinned by a test**, in the same way
the append-only rule is enforced by triggers and *also* asserted by the conformance
suite.

**Read-side requirement.** `0 rows` must be readable as *"the exact source document is
unresolved"*, and must be distinguishable from *"no document-scoped read was ever
attempted"*. These are the same sentence to a counter and are opposite facts — the
defect that produced `NO_OBSERVATIONS` in 2.7 (`evidence_model.py:40-55`). This
distinction **must not** be implemented by adding a row to this relation.

### Decision 3 — Inline-XBRL dual-document case: **Option 1**. Neither document is asserted.

**Option 2 — "the primary document is the source by virtue of being primary" — is rejected.**

The question asked was whether Option 2 violates invariant 19 or is a distinct
methodology rule. The answer is precise: **it is a distinct rule in form and a
violation in substance.**

*In form it is legitimate.* "Primary document" is a **declared role**, not an
inference: `_primary_document_filename` reads SGML `source_ordinal = 1`
(`sec_ingest.py:2045-2065`), which is the filing's own statement about its contents.
It is not a filename heuristic and not a classifier of authorship, so the letter of
invariant 19's first prohibition is not touched.

*In substance it performs the undecidable determination.* The rule's entire
discriminating work is: **"this occurrence, not that one, is the filed one."** That
is exactly the determination invariant 19 records as unavailable under current
evidence. A rule that selects one of two documents *because* they differ in the very
respect that cannot be decided is a classifier in all but name — it simply takes the
undecidable fact as its premise instead of inventing a heuristic for it. Option 2
was also the option that makes implementation easiest (`_primary_document_filename`
already exists and always resolves), which is the one justification the Phase 3C-A
brief explicitly forbids.

*And Option 2 independently fails the relation's question.* An assertion here is
about where the observation **was read from**. Production ingestion reads the SEC
`companyconcept` aggregate (`sec_ingest.py:985-1005`) and links the observation to
that concept document (`document_hashes=[document_hash]`, `:2283`). **No filing
document is opened by any code path that writes an observation today.** Naming the
primary document would assert a byte sequence ST-EVA never read.

**Option 3 — "both are valid occurrences, needing different semantics" — is rejected
as an answer here.** It is the most accurate description of the bytes, and it is
still wrong for *this* relation: it redefines the relation as an occurrence set,
which contradicts Decision 1, makes `0 rows` ambiguous between "not present" and
"present twice", and becomes useful only once each occurrence carries a role —
i.e. once the classifier invariant 19 forbids exists. Recording occurrences is a
legitimate future project; it requires a **separate relation and a separate ADR**.

**Consequence:** for `0000320193-26-000018`, the exact source document of the EPS
fact is `UNAVAILABLE` — permanently, under current evidence. This is a *different*
state from the 2013 filing, which is resolvable to `EX-101.INS`. Both must be
reportable as `UNAVAILABLE`, and only one of them is a limitation that more evidence
would fix.

### Decision 4 — `contextRef`: **a known limitation, frozen explicitly**

Not acceptable-in-silence (1) and not a blocker (3). It is option 2.

- **It is a property of the endpoint, not a defect.** `companyconcept` unit entries
  carry `start/end/val/accn/fy/fp/form/filed/frame` and no `contextRef`; `SecFact`
  has no field. ST-EVA does not drop it.
- **Its production consequence is already recorded rather than silent.** Because
  `context=accession` duplicates `document_ref=accession`
  (`sec_ingest.py:2247,2252`), the context slot carries *zero* dimensional
  information. For one `(accession, taxonomy, concept, period_start, period_end)`,
  every dimension member collapses to one `source_fact_id`; members 2..n are skipped
  by `_fact_held` (`:2254-2257`, `:2344-2351`). A `dimension_collision` row is
  written with kind `SAME_PERIOD_DIFFERENT_VALUE` when one accession reported more
  than one distinct value (`:2191-2236`), and is read back as `DIMENSION_COLLISION`
  (`evidence_query.py:94,349`). The collapse is visible, not invisible.
- **The two test families are not in tension; they assert different things.**
  `test_different_dimensions_never_share_a_fact` (`tests/test_ingestion_aapl.py:95-109`)
  pins the **preimage**: context is a key, so a real `contextRef` *would* separate
  members. `tests/test_ingestion_aapl.py:735-757` and
  `tests/test_ingestion_cross_company.py:333-352` pin the **stored** value and
  therefore pin `context=accession` as a compatibility requirement on historical
  rows.

**Frozen consequences.**

1. Changing the production `context` argument is **out of bounds for 3C-B**. It is a
   new identity for every stored SEC fact: it fails both reproducibility tests,
   re-appends the whole SEC history as new `source_fact_id`s, and would require
   re-provenance of history that cannot be reconstructed without re-reading the
   original instances — fabricating historical provenance is forbidden.
2. Any change to `source_fact_id`'s preimage requires its own ADR plus a
   migration-safe treatment of historical identity.
3. A future document-reading XBRL route **may** read `contextRef`, and **must** use it
   to *locate* a fact — to prove uniqueness and to separate dimension members — and
   **must not** use it to mint a new fact identity.

### Decision 5 — Byte-level `concept + period` scanning **cannot** establish exact source provenance

The Phase 3C-A proposal is rejected. Six reasons, all grounded in this repository:

1. **It is not unique inside one filing.** In TSM's 20-F a single
   `ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities`
   has **seven** fact instances (`ifrs_capex_context_237.py:21-25`).
2. **Value equality cannot break the tie.** The same finding records that
   *"the dimensional and undimensional contexts carry the same values"*
   (`:25`). Three periods × undimensioned and the same three × dimensioned, with
   identical values — so even scanning value *and* period cannot select one.
3. **Occurrences are not facts.** Inline XBRL and EDGAR's `_htm.xml` extraction
   present **one** fact twice; a per-document scan returns 2 for 1 (the verified
   2026 case).
4. **Rendered duplicates carry no tags.** `R1.htm`, `FilingSummary.xml`,
   `report.css`, `Show.js` are EDGAR products in the same directory. A text-level
   concept+period match in them is a rendering, and invariant 19 forbids excluding
   them by appearance — so the scan cannot be narrowed without a classifier.
5. **Same-period restatements.** One concept, one period, different values inside
   one filing is the measured `SAME_PERIOD_DIFFERENT_VALUE` case: two genuine facts,
   no tiebreak.
6. **Multiple instance documents per filing** is already observed (`EX-101.INS`
   plus `_htm.xml` plus the inline primary).

**Permitted role for scanning: a candidate generator that reduces the search space.
It may never be the assertion.**

An assertion requires, per document: an XBRL-instance-level parse that resolves
`contextRef` to its context node, locates the fact node by
(namespace, tag, contextRef, unitRef, period, decimals/sign), and **proves that node
unique in that document**; and, across the filing, a candidate set over **all**
eligible documents whose cardinality is exactly 1.

---

## 3. Required Evidence for a Future Phase 3C-B

A 3C-B implementation is admissible only if **all** of the following hold.

1. **A new ingestion route that reads facts from captured filing-document bytes**
   (`filing_document_captures` → `source_documents.content`, read via
   `SQLiteArchive.content_for`). Without a route that opens a filing document there
   is nothing to link, and Decision 3's premise still holds for every observation.
2. `filing_documents` and a `filing_document_captures` row
   (`acquisition_class = 'SEC_FILING_DOCUMENT'`) exist for the accession. A document
   with no capture has no bytes and therefore no assertion.
3. The candidate set is computed over **all corroborated documents of the filing**
   — the dual-manifest rule at `sec_ingest.py:1845-1881`. Choosing a subset first is
   Option 2 in disguise and is forbidden.
4. XBRL instance-level fact resolution with `contextRef`: `ix:nonFraction` /
   `ix:nonNumeric` for inline, `xbrli:context` for an extracted instance.
5. **A uniqueness assertion per document, and a cardinality assertion across
   documents**, both evaluated before any insert.
6. **A recorded byte locator for the fact node** (offset or XPath), so the assertion
   is re-derivable from the captured bytes. This is the standard
   `filing_document_statements` already meets: the locator is part of the identity,
   the payload is not (`0020:370-372`).
7. **A recorded "attempted and unresolved" signal, distinct from "never attempted"**,
   implemented **without** adding a row to `observation_filing_documents` (2.7
   `NO_OBSERVATIONS` precedent, `evidence_model.py:40-55`; run-level reporting is the
   existing mechanism, `sec_ingest.py:1291-1302`).
8. **Network-free fixtures at both shapes**: the 2026 cardinality-2 inline case and
   the 2013 cardinality-1 `EX-101.INS` case. A test that can only pass with network
   access is a test that cannot run.

---

## 4. Cases That MUST Remain `UNAVAILABLE` (0 rows)

| # | Case | Why |
| --- | --- | --- |
| 1 | **Every observation written by the current concept-endpoint route** — i.e. every existing SEC observation | No filing document was opened (`sec_ingest.py:985-1005`). Any row would be fabricated. |
| 2 | The verified 2026 inline-XBRL + `_htm.xml` fact | Two documents, one fact, no decisive evidence (Decision 3). |
| 3 | Any filing whose submission manifest was never read | No corroborated document set; absence of one manifest is not permission to fetch on the word of the other (`sec_ingest.py:1869-1873`). |
| 4 | Any fact whose candidate set includes a duplicate-declared filename | No document identity is minted (`0020:324-335`); the document is unresolved, not merged. |
| 5 | Any observation with no accession | No document scope to assert within. |
| 6 | Any fact with >1 matching fact node in one document | Identity is ambiguous inside one document; cardinality 2 before the filing is even considered. |
| 7 | Any fact present only in an EDGAR-rendered resource with no tagged instance (`R1.htm`, `report.css`, `FilingSummary.xml`) | A rendering is not an assertion, and invariant 19 forbids excluding it by appearance — so it cannot be silently dropped either; the observation stays unresolved. |
| 8 | Any non-separable dimensional member set | Which member a stored value came from is not recoverable from an aggregate (`ifrs_capex_context_237.py:48-50`). |
| 9 | Any non-SEC source (vendor, market data) | The relation has no filing-document scope for them. |
| 10 | Any case resolvable only by a filer-authored / EDGAR-generated classifier | Invariant 19. |

---

## 5. Architectural Constraints Future Agents Must Not Violate

1. `observation_filing_documents` carries **one** meaning (Decision 1). No second
   meaning may be added to it, and no column may be added to express a second one
   without a new ADR.
2. **0 / 1 / none cardinality.** No confidence, no candidates, no tiebreak ordering,
   no superseding a row to fix a cardinality.
3. **Never derive a document from an accession**, in any direction. In particular, an
   8-K accession does not name an `EX-99.1` (`sqlite_archive.py:1154-1163`).
4. **Never invent or infer a filer-authored / EDGAR-generated classifier**, and never
   exclude a document because it looks like an EDGAR product (invariant 19).
5. **Never assert a document an observation was not read from.** The concept-endpoint
   route reads no filing document; the relation stays empty for its output.
6. **Never change `source_fact_id`'s preimage or its production wiring** in a
   provenance phase (Decision 4.1). `document_ref=accession`, `context=accession` are
   frozen compatibility requirements pinned by reproducibility tests.
7. **Never change the `Observation` dataclass** to carry provenance fields. Provenance
   is layer 2's (`0020`), and layer 1 columns are content-hashed.
8. **Never `UPDATE` or `DELETE` provenance rows.** A re-acquisition inserts.
9. **Never let `captured_at` / `capture_kind` into an identity preimage.**
10. **Never use concept+period (with or without value) as a source assertion**
    (Decision 5). Scanning is a candidate generator.
11. **Every assertion must be re-derivable from captured bytes**, via a recorded
    locator — the `filing_document_statements` standard.
12. **Every `UNAVAILABLE` must be distinguishable from a value of `0`.** Absence of a
    row is a state; it is never a default.
13. **Frozen documents may only be extended by new verified evidence plus a new
    architectural decision.** Silently adding a column, a heuristic, or an ordering
    default is the specific failure this record exists to prevent.

---

## 6. Explicitly Unresolved

These are **not** decided here and must not be decided inside 3C-B.

1. Whether occurrence-level recording is ever wanted. If yes: a new relation, a new
   ADR, and it stays blocked on invariant 19 until new verified evidence exists.
2. Whether "attempted and unresolved" deserves its own persisted relation, or whether
   run-level reporting suffices. Run-level is sufficient for 3C-B; persistence would
   need its own ADR.
3. Whether SEC ever publishes evidence resolving invariant 19. Unknown, and
   out of scope. It is not a reason to relax anything now.
4. Whether a document-reading route should mint facts under a *new* identity
   namespace rather than reuse `source_fact_id`. **Not decided** — two incompatible
   namespaces in one column is precisely why this needs a separate decision, and it
   is the single largest unresolved item blocking a document-reading route.
5. Whether the concept-endpoint route should stop storing one member of a
   non-separable dimensional set. It is an existing, recorded, deliberate collapse;
   changing it is outside 3C.
6. Whether a 3C XBRL parse should cover inline XBRL, extracted instance, or both.
   **This is blocked on invariant 19**, because the 2026 cardinality-2 case is only
   resolvable by excluding one of the two — which is the authorship judgement
   invariant 19 records as undecidable.

---

## 7. What Was Not Touched

No schema, no migration, no production code, no test, no `Observation` field, no
`observation_filing_documents` row, no XBRL parsing, no byte scanning, no change to
historical P/E methodology, evidence classification, or `audit_status`. The only
files written are this record and the binding invariants added to
`docs/ST-EVA-ARCHITECTURE.md` §D.