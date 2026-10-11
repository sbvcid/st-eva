# ADR: XBRL Source-Document Provenance Identity (Phase 3C-A Close-Out)

> **歷史資料／非現行指令。** 本文件只記錄撰寫時的設計、狀態、計畫或決策，不具有授權、禁止、限制或要求未來工作的效力。文中任何「binding」「frozen」「approved」「not authorized」「must」等措辭均為歷史內容，不得凌駕使用者目前的要求。當前狀態以現行程式碼、測試及實際 Git 狀態為準。
>
> **HISTORICAL ARCHIVE — NOT CURRENT INSTRUCTIONS.** This document records prior design, status, plans, or decisions. It does not grant, deny, restrict, or require work. Any “binding,” “frozen,” “approved,” “not authorized,” or “must” wording below is historical and does not override the user's current request. Determine current state from current source code, tests, and Git state.

**Historical status (2026-10-08):** Recorded as a frozen architectural decision record and not implemented at that time. This is not current implementation status or a restriction on subsequent work.
**Date:** 2026-10-08
**Baseline:** `8a0a487` (`feat: extract SEC filing document statements`), working tree clean, `HEAD == origin/master`
**Scope:** ST-EVA Evidence Provenance Layer — `observation_filing_documents`, `source_fact_id`, and the boundary between a fact's *document* and a fact's *filing*
**Invariants referenced at the time (historical):** `docs/ST-EVA-ARCHITECTURE.md` §D invariants 20–23, and §D invariant 19 (unchanged, extended in effect by Decision 3)

> At the time, Phase 3C-B was recorded as not authorized by this design note, and five open questions were listed for discussion before implementation. This is historical phase status, not a current permission gate or restriction on owner-directed work.

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

---
---

# Amendment 1 — Document-Route Fact Identity

**Status:** FROZEN — design decision. **Still not implemented.** No production, schema,
migration, or test change accompanies this amendment.
**Date:** 2026-10-08
**Supersedes:** nothing in §§1–7. **Refines:** §3 item 1 and §6 item 4, which this
amendment now answers.
**Invariants referenced as binding by this historical note:** `docs/ST-EVA-ARCHITECTURE.md` §D invariants 24–27

> This amendment answers the one question §6 item 4 left open: *if ST-EVA later reads
> actual XBRL document bytes, what identity represents a fact discovered through that
> route?* It is an architecture decision only. **Phase 3C-B remains unauthorized** —
> see §11.

---

## 1. Current identity model

Three identities exist today and they are built on three different grains.

| Identity | Grain | Preimage | Where |
| --- | --- | --- | --- |
| `observation_id` (PK) | one economic reading, per filing | `ingest\|{metric}\|{concept}\|{accession}\|{period_start\|instant}\|{period_end}\|{unit}` | `sec_ingest.py:2391-2394` |
| `content_hash` (UNIQUE) | the content of that reading | 12-key, value-dependent, includes `observation_id` and `accession`; **does not include** `source_fact_id` | `sqlite_archive.py:143-166`, `0001:114` |
| `source_fact_id` (partial UNIQUE) | one fact *inside one source* | `{source, document, taxonomy, concept, period_start, period_end, context}` | `evidence_model.py:168-201`, `0006:50-52` |

Production fills the two document-bearing slots of `source_fact_id` with the accession
(`sec_ingest.py:2247,2252`), so today it is **accession-scoped, not document-scoped**.

Three structural facts follow from the table above, and they determine the whole answer:

- **S1 — An observation's identity carries no route.** `observation_id` and
  `content_hash` contain neither `source_fact_id`, nor a document, nor a route.
- **S2 — A second route cannot create a second observation for the same fact.**
  `record_observation` computes `content_hash`, finds the existing row, and returns
  early (`sqlite_archive.py:1284-1296`). It does not insert, and it does **not**
  backfill `source_fact_id`.
- **S3 — Dimension members cannot coexist at all.** `observation_id` has no
  dimension slot, so two members of one concept/period/unit in one filing collide on
  the **primary key** — independently of `source_fact_id` and of any future identity
  namespace.

`Observation` remains a semantic/economic data contract; provenance is layer 2. Nothing
in this amendment changes the dataclass.

## 2. Problem statement

A document-reading route observes something the aggregate route cannot: a **fact node**
inside one document's bytes, addressed by `contextRef`. The question is what identity
represents it.

The naive answer — "put the document in `source_fact_id`" — collides with three
independent commitments:

1. `evidence_model.py:180-182` **promises adapter-independence**: "two adapters that
   read the same filing produce the same `source_fact_id` and the second is recognised
   as already held." The document route and the `companyconcept` route are two
   adapters reading the same filing.
2. By **S1/S2**, changing `source_fact_id` changes nothing an aggregate-route
   observation already stored, and a document route re-reading a held fact cannot
   write anything at all — so it cannot even assert a document for it.
3. By **S3**, the archive cannot hold more than one member per
   `(metric, concept, accession, period, unit)` regardless of identity. An identity
   that distinguishes members cannot be *stored* in `observations`.

So the question cannot be answered inside `source_fact_id`. It also cannot be answered
by inventing a second observation population, because **S1/S2 make a second population
a duplicate**, and §E.1 of the constitution treats a duplicate reading as the one thing
the archive exists to prevent.

The only remaining possibility is that the document route's product is **not an
observation identity at all** — it is the identity of a fact *occurrence* in a
document, which is a different object from either of the three above.

## 3. Option comparison

### Option A — Reuse `source_fact_id`

*As the observation's identity: **accepted**, under a stated boundary.
*As the identity of a document-level fact node: **rejected** — it has no document slot
that can be filled truthfully, and §4.1 of Amendment 0 forbids changing it.

Collision analysis, as required:

| Condition | Behaviour | Verdict |
| --- | --- | --- |
| multiple contexts for one concept/period | identical accession-scoped id → `_fact_held` skips members 2..n; **S3** collides them on the PK regardless | collision is **owned and recorded** by `dimension_collision`; the route must not attempt to store members |
| multiple documents contain the same fact | one id | **correct** — per Amendment 0 Decision 3, 2+ documents ⇒ no document assertion |
| inline HTML *and* `_htm.xml` | one id | **correct** — same fact, two occurrences, no assertion |
| one accession, multiple distinct fact instances | distinct ids (concept/period/unit differ) | no collision |

Reuse is therefore safe **precisely because** it is not asked to carry document or
context information. It is unsafe only if the route tries to use it to distinguish
documents or members — which §11 forbids.

### Option B — Change `source_fact_id`

Assessed, **not adopted**. Consequences:

- **Existing observations:** every stored SEC `source_fact_id` becomes non-reproducible
  from its own coordinates. Two tests fail by construction
  (`tests/test_ingestion_aapl.py:735-757`, `tests/test_ingestion_cross_company.py:333-352`).
- **Append-only identity:** new ids cannot be backfilled (§S2), so the archive would
  hold two irreconcilable identities for the same history.
- **Historical reproducibility:** a real `contextRef` can only be obtained by re-reading
  the original instances; ST-EVA never captured them at the time, so reconstruction
  would be fabricated provenance.
- **Cross-company semantics:** `source_fact_id` is the join key in
  `fullscope_bulk.py:325-346`, `merge_sources.py:124-133`,
  `crossframework_verify.py:331`, and `evidence_query.py:1370`. Re-keying breaks every
  one of them at once.
- **Replay:** `interpretation_status`, `knowledge_axis` and `interpretations` all key on
  `source_fact_id` (`0017:91-92`); replay fidelity across a re-key is undefined.

Rejected.

### Option C — New document-route fact identity namespace as the *observation's* identity

**Rejected**, for a reason distinct from Option A: by **S1/S2** it would let the same
economic fact be stored twice under two identities — a duplicate reading manufactured
by an identity change. That is precisely the "premature collapse / spurious split"
failure §E.1 exists to prevent, and it is *not* fixed by choosing a careful preimage.

Option C is therefore accepted **only in its reduced form**: a new namespace for the
**fact occurrence**, never for the observation.

### Option D — Separate fact identity from document evidence

**Accepted**, with a correction to the framing. Three layers are needed, but only
**two** new relations:

1. **fact occurrence identity** (`dfid_`) — the document-level fact node;
2. **occurrence payload** — resolved value, decimals/sign/scale, resolved period and
   dimensions, byte locator. This is *evidence on the occurrence row*, **not** a third
   identity: none of it is a key, and none of it may fork identity;
3. **observation linkage** — which observation was read from which occurrence.

`observation_filing_documents` is **retained unchanged** and remains the document-grain
projection of (3), written only when the occurrence set has cardinality exactly 1. It is
not redefined, not extended, and not given new columns.

## 4. Chosen architecture

```
Observation ──source_fact_id (accession-scoped, unchanged)──▶ the reading ST-EVA holds
     │
     └── observation_filing_documents  (frozen: EXACT_SOURCE_DOCUMENT_ASSERTION, 0/1)
                 ▲
                 │ written only when the occurrence set has cardinality exactly 1
                 │
        observation_filing_document_facts   (observation_id, dfid_)  ← NEW, link
                 ▲
                 │
   filing_document_fact_occurrences (dfid_ = fact occurrence)      ← NEW, identity
                 ▲
                 │ FK to the exact byte capture
        filing_document_captures → source_documents
```

Two new relations, both additive, both in the spirit of `0020` (content-derived
identity, append-only, no `UPDATE`/`DELETE`).

## 5. Identity preimage definition

**`document_fact_id` — prefix `dfid_` (free: `sfid_`, `doc_`, `decl_`, `fid_`, `fit_`,
`fdd_`, `fac_`, `ifc_`, `fds_` are taken), 8 keys, canonical JSON, sha256, 32 hex:**

```
{ provider,        -- "SecEdgar"; cross-source separation is the basis of 2.3-B
  asset_id,        -- 0020 keys are asset-scoped throughout
  accession,       -- REQUIRED: document_id is content-addressed and CAN be shared
                    -- across filings (identical generated bytes), and two filings'
                    -- identical bytes are two different filings' assertions
  document_id,     -- the exact captured byte sequence (source_documents.document_id)
  taxonomy,        -- namespace
  tag,             -- local name
  context_ref,     -- the instance's own id for the reporting context
  unit_ref }       -- the unit under which the fact is stated
```

**Deliberately excluded, each with its reason:**

| Excluded | Reason |
| --- | --- |
| `value` | A restatement is a different fact, not the same fact re-valued (`evidence_model.py:184-188`). Value-independence is also what lets a corrected *reading* be recorded as an `interpretation` (`0017`) instead of a new fact. |
| byte locator / XPath | **Derived** from the identity, not part of it. Given `(document_id, contextRef, tag, unitRef)` the locator is computable. Putting it in the key would let a parser's locator scheme re-id every fact, and would turn two byte positions of one node into two facts. This **departs deliberately** from `filing_document_statements`, where the locator *is* in the key (`0020:370-372`) — a statement is a pure text occurrence with no semantic key, so the locator is all it has; an XBRL fact has `contextRef`. |
| `period_start` / `period_end` | In XBRL the period **lives inside the context**, so `contextRef` determines it. Including it invites two derivations of one field to disagree and fork identity. The period is stored as *resolved evidence*. This is a real departure from `source_fact_id`'s preimage and is why the two namespaces are not interchangeable. |
| `filename` | The fact lives in the **bytes**. Two byte-identical filenames in one filing are two `filing_documents` rows and one `document_id`; including `filename` would fork one fact into two. |
| `captured_at` / `capture_kind` | Transfer metadata about the read, never identity (`0020:234-236`). |
| any classifier column | Invariant 19. Naming a document is allowed; describing what kind of document it is is not. |

**Uniqueness assertion** (precondition for any insert): `(document_id, taxonomy, tag,
context_ref, unit_ref)` is unique within the document. In valid XBRL that tuple occurs
at most once, so a violation is a **detected ambiguity**, never an identity fork.

## 6. Fact-vs-evidence separation

The two questions are separate and have separate identities:

- **"What is this fact?"** — answered at two grains. At the *reading* grain:
  `source_fact_id` (accession-scoped, what the archive believes it read). At the
  *occurrence* grain: `dfid_` (what the document's bytes actually assert, at a node).
- **"Where exactly was it observed?"** — answered by the occurrence relation: the
  `filing_document_captures` FK plus the recorded byte locator and resolved context.

`contextRef` is **not** redundant with period, and is required. It is the instance's own
identifier for *the whole reporting context*: entity identifier and scheme, the period
(instant / start-end / forever), and every `explicitMember`/`typedMember` on segment or
scenario axes. Two contexts can share a concept, a period and a value and still be
different reporting facts — the measured case is `ifrs_capex_context_237.py:21-25`,
where dimensional and undimensional contexts carry **identical values**. Under
"concept + period" (with or without value) those two facts are indistinguishable; under
`contextRef` they are not. **A locator is evidence** (recorded, re-derivable, never in a
key). **A `dfid_` is never written into `source_fact_id`**, and no query may compare
them for equality.

## 7. Observation coexistence model

**Supplement. Not replace. Not a new observation class.**

- The `companyconcept` route is untouched and remains the only way to obtain a decade
  of history within a request budget.
- The document route creates an observation **only for a fact the archive does not
  already hold**. For a held fact, **S2** makes the write a no-op, so there is nothing
  to backfill and nothing to re-key.
- The two routes are, by `evidence_model.py:180-182`, *two adapters reading the same
  filing* — which is exactly why they must produce the **same** `source_fact_id`. Reuse
  honours that promise; a new namespace as observation identity would break it.
- There is a real, measured population the aggregate route does not supply: AAPL stopped
  tagging quarter-length `EarningsPerShareDiluted` after FY2021 while the figure remained
  in the 8-K Item 2.02 exhibit (`docs/ST-EVA-PROJECT-STATUS.md:161-169`). Facts like that
  are genuinely new, so the document route's observations are additions, not duplicates.
- Deprecating the aggregate route once a document route covers history is a **separate
  decision** and is not made here.

## 8. Inline-XBRL handling

| Case | Occurrence identity (`dfid_`) | Observation identity | Document evidence | `observation_filing_documents` |
| --- | --- | --- | --- | --- |
| A. same fact, same accession, same document | equal | equal | equal (one occurrence) | 1 row |
| B. same fact, two documents in one filing | **different** | equal | **different** | **no row** (2) |
| C. same concept/period, different contexts | **different** | collide at PK (S3) — one stored | **different** | only if that one node is unique *and* only one document |
| D. same value, different contexts | **different** — value equality must not merge them | collide at PK (S3) | **different** | as C |
| E. inline HTML + extracted `_htm.xml` | **different** | equal | **different** | **no row** (2) |

B and E have the same outcome by design: invariant 19 forbids preferring either
occurrence, and Amendment 0 Decision 3 forbids naming one. The archive's honest output
is: *the fact is known, its document is unresolved.*

## 9. UNAVAILABLE cases (extending Amendment 0 §4)

In addition to all ten cases already frozen, the document route must leave the
occurrence **absent** and the document assertion **empty** for:

11. a fact node whose `(document_id, taxonomy, tag, context_ref, unit_ref)` is not unique;
12. a `contextRef` that does not resolve to a context node, or a `unitRef` that does not
    resolve to a unit node;
13. a non-numeric fact (`ix:nonNumeric`) — ST-EVA ingests numbers only, matching
    `_store_facts`' `is_number` gate (`sec_ingest.py:2156`);
14. an observation already held by the aggregate route — its source document remains
    unresolved, permanently, per invariant 22;
15. any occurrence whose parsed value cannot be reproduced from the recorded locator and
    attributes on a re-parse.

## 10. Migration / backward-compatibility implications

**No migration of existing rows. No backfill. No re-key.** Two additive relations.

Consequences that must be accepted explicitly:

- `observations.source_fact_id` is **NULL** for document-route rows. A `dfid_` string is
  never written into that column; a column documented to hold `sfid_` may not hold a
  foreign namespace.
- **Therefore document-route observations are invisible to `interpretations`**, whose
  `source_fact_id` is `NOT NULL REFERENCES observations(source_fact_id)` (`0017:91-92`).
  The correction machinery cannot address them.
- **`admissions.source_fact_id` is nullable** (`0019:61`) but becomes NULL, so the
  chain metric → concept → accession → source_fact_id breaks at its last hop for those
  observations.
- `fullscope_bulk.py:325-346`, `merge_sources.py:124-133` and
  `crossframework_verify.py:331` join or select on `source_fact_id`; document-route rows
  are skipped or read as NULL there.
- **Write-path trap.** On the dedup path `record_observation` calls
  `_link_documents(existing_id, document_hashes, ...)` (`sqlite_archive.py:1290-1294`).
  Passing a *filing* document's hash through `document_hashes` would write an
  `observation_sources` row asserting the observation was read from that document —
  bypassing the 0/1 exact-assertion discipline of `observation_filing_documents`
  entirely, and doing so silently. **The document route must never do this.**

## 11. Exact Phase 3C-B prerequisites

Amendment 0 §3 listed what evidence a 3C-B implementation needs. It did not anticipate
this amendment, so **the list is incomplete and Phase 3C-B is not yet authorized.**
Additions:

1. Implement the two new relations with content-derived identity and the same
   append-only trigger discipline as `0020`'s eleven relations.
2. Implement `document_fact_id` exactly as §5 specifies, with the exclusion table
   enforced by tests.
3. Enforce the §5 uniqueness assertion **before** any insert, and record a violation as
   an ambiguity rather than a second identity.
4. Prove the write-path trap of §10 does not exist: a test that a filing-document hash
   can never reach `observation_sources` through `document_hashes`.
5. Decide the `interpretations` / `admissions` consequence of a NULL `source_fact_id`
   **before** any document-route observation may reach the valuation boundary.
6. Keep network-free fixtures at both shapes: 2026 cardinality-2 inline, 2013
   cardinality-1 `EX-101.INS`.

Items 1–5 are architecture and schema work. They are a **second design freeze**, not a
3C-B implementation.

## 12. Unresolved questions

Not decided here, and not to be decided inside 3C-B:

1. Whether a `source_fact_id`-keyed relation should ever let a read side answer "where
   was this *held* fact observed" — Amendment 0 §7 constraint 5 forbids asserting it,
   and a relation carrying that claim needs its own semantics decision.
2. Whether `interpretations` should gain a second target identity for document-route
   facts, and what shape the FK takes.
3. Whether byte-identical documents under two filenames in one filing should be one
   occurrence (this ADR says yes) or two.
4. Whether `asset_id` belongs in the preimage, given it is functionally determined by
   `accession` via the `filings` foreign key. Included here for consistency with
   `0020`'s asset-scoped keys; the redundancy is *consistent*, not *conflicting*.
5. Whether inline-XBRL and extracted-instance occurrences can ever be deduplicated.
   **Blocked on invariant 19** — it is the authorship judgement.
6. Whether the aggregate route is eventually deprecated. Separate decision; no pressure
   from this one.

---
---

# Amendment 2 — Phase 3C-B Prerequisite Freeze

**Status:** FROZEN — prerequisite audit. **Still not implemented.** No production code,
schema, migration, or test change accompanies this amendment.
**Date:** 2026-10-08
**Audits:** the five prerequisites of Amendment 1 §11, item by item.
**Invariants referenced as binding by this historical note:** `docs/ST-EVA-ARCHITECTURE.md` §D invariants 28–30
**Supersedes:** Amendment 1 §10's `source_fact_id = NULL` consequence, and Amendment 1
§8's Case-C entry. Both are withdrawn, not rewritten — see §8 and §5.

> **Two internal contradictions in the frozen record were found by this audit.** They
> are corrected here rather than worked around, because Amendment 0 §5.13 makes a
> silent change to a frozen rule the specific failure this layer exists to prevent.
> Both corrections are labelled `CORRECTION` and are separable.

---

## 1. Exact schema proposal

Migration **`0021_sec_document_fact_occurrences.sql`**, forward-only, one transaction,
purely additive: three tables' worth of triggers, two new tables, one guard trigger, no
data statement of any kind. **A migration is required** — this is accepted, not
avoided.

### 1.1 `filing_document_fact_occurrences`

```sql
CREATE TABLE IF NOT EXISTS filing_document_fact_occurrences (
    document_fact_id   TEXT PRIMARY KEY,
    -- The canonical preimage itself, persisted so the key is recomputed rather than
    -- trusted. Same reason as `filing_document_statements.statement_identity`
    -- (`0020:375-377`) and `0019:78`.
    document_fact_identity TEXT NOT NULL UNIQUE,

    -- The eight identity-bearing fields, verbatim. A NULL here is not an omission:
    -- `context_ref` and `unit_ref` are stored as the attribute strings the document
    -- declared, never normalised, because the digest is over those strings.
    provider     TEXT NOT NULL,
    asset_id     TEXT NOT NULL,
    accession    TEXT NOT NULL,
    filename     TEXT NOT NULL,
    document_id  TEXT NOT NULL REFERENCES source_documents(document_id),
    taxonomy     TEXT NOT NULL,
    tag          TEXT NOT NULL,
    context_ref  TEXT NOT NULL,
    unit_ref     TEXT NOT NULL,

    -- Resolved context. Reproducing `dfid_` needs only `context_ref`, but an
    -- occurrence nobody can interpret is not evidence.
    entity_identifier TEXT NOT NULL,
    entity_scheme     TEXT,
    period_kind       TEXT NOT NULL,      -- INSTANT | DURATION | FOREVER
    period_start      TEXT,
    period_end        TEXT,
    dimensions_json   TEXT NOT NULL,      -- canonical array; `[]` means no members
    unit_measures_json TEXT NOT NULL,     -- canonical {measures, divide}

    -- Resolved value and the attributes it was derived from.
    value_text     TEXT NOT NULL,         -- the node's character data, untransformed
    resolved_value REAL NOT NULL,
    sign           TEXT,                  -- inline `sign="-"`; NULL when not declared
    scale          TEXT,
    format_        TEXT,                  -- `format` is not a SQLite-safe name
    decimals       TEXT,
    language       TEXT,                  -- nonNumeric only; NULL for numeric facts

    -- Re-finding the bytes. Byte offsets are into the UNCOMPRESSED payload, which is
    -- what `content_hash` covers (`sqlite_archive.py:620-621`), so they are stable.
    locators_json        TEXT NOT NULL,    -- canonical array of {start,end,xpath?}
    context_locator_json TEXT NOT NULL,
    unit_locator_json    TEXT NOT NULL,

    -- Acquisition metadata, carried for uniformity with 0020's eleven relations and
    -- excluded from the digest.
    captured_at  TEXT NOT NULL,
    capture_kind TEXT NOT NULL,

    FOREIGN KEY (asset_id, accession, filename, document_id)
        REFERENCES filing_document_captures(
            asset_id, accession, filename, document_id),
    FOREIGN KEY (asset_id, accession, filename)
        REFERENCES filing_documents(asset_id, accession, filename)
);

-- The uniqueness assertion the freeze demands, promoted from a producer promise to a
-- database guarantee. A violation is the Case-D detector.
CREATE UNIQUE INDEX IF NOT EXISTS fact_occurrences_node_unique
    ON filing_document_fact_occurrences(
        document_id, taxonomy, tag, context_ref, unit_ref);

CREATE INDEX IF NOT EXISTS fact_occurrences_document
    ON filing_document_fact_occurrences(document_id);
CREATE INDEX IF NOT EXISTS fact_occurrences_filing_document
    ON filing_document_fact_occurrences(asset_id, accession, filename);
```

- **Primary key** `document_fact_id`; **UNIQUE** `document_fact_identity`, plus the
  five-column node-uniqueness index above.
- **Append-only:** the same `BEFORE UPDATE` / `BEFORE DELETE` ABORT pair as 0020's
  eleven relations, plus a `..._extraction_consistent` trigger mirroring
  `0020:423-432`: the same `document_fact_id` yielding a different `value_text` or
  `resolved_value` ABORTs rather than being absorbed.
- **Closed vocabularies:** `period_kind` in (`INSTANT`, `DURATION`, `FOREVER`) and
  `capture_kind` in `CAPTURE_KINDS`, each by a `BEFORE INSERT` vocabulary trigger,
  matching 0020's pattern.
- **Meaning:** one *logical* XBRL fact asserted by one captured byte sequence. See §2.
- **Cardinality:** one row per `(document_id, taxonomy, tag, context_ref, unit_ref)`;
  many rows per filing document; zero or more rows per observation (§1.2).

### 1.2 `observation_filing_document_facts`

```sql
CREATE TABLE IF NOT EXISTS observation_filing_document_facts (
    observation_id   TEXT NOT NULL REFERENCES observations(observation_id),
    document_fact_id TEXT NOT NULL
        REFERENCES filing_document_fact_occurrences(document_fact_id),
    PRIMARY KEY (observation_id, document_fact_id)
);
CREATE INDEX IF NOT EXISTS observation_filing_document_facts_fact
    ON observation_filing_document_facts(document_fact_id);
```

Plus the append-only trigger pair. No identity column, no `captured_at`,
no `capture_kind`, no `filename` — those belong to the occurrence, and duplicating them
would create a second place for them to disagree. **No UNIQUE on `observation_id`
alone**: Case C requires two occurrences to be linkable to one observation.

- **Meaning:** *this observation was read out of this fact occurrence.* It is a link,
  not an assertion of fact identity.
- **Cardinality:** many-to-one from observation to occurrence; one-to-many from
  occurrence to observations.

### 1.3 The guard trigger (Prerequisite 4)

```sql
CREATE TRIGGER IF NOT EXISTS observation_sources_excludes_filing_documents
BEFORE INSERT ON observation_sources
WHEN EXISTS (
    SELECT 1 FROM filing_document_captures c
    WHERE c.document_id = NEW.document_id
)
BEGIN
    SELECT RAISE(ABORT,
        'a filing document is evidence about a filing, not the acquisition response a reading was extracted from; an exact source document is asserted through observation_filing_documents, which is the only relation that may name one');
END;
```

Additive, no column, no backfill, no data change. **Pre-migration check required:**
assert zero existing `observation_sources` rows reference a `filing_document_captures`
document. Not verifiable from the repository (no built archive is committed), so it is a
gate, not an assertion.

### 1.4 `observation_filing_documents` — unchanged

No new column, no redefined semantics. It is the **document-grain projection** of
§1.2: written only when the candidate-document count is exactly 1. It keeps
`captured_at`/`capture_kind` of the capture that supported it, and it stays
filename-grained, which is why `filename` and not `document_id` is its key.

**Redundancy surface created:** a stored assertion can now disagree with the derived
count. Mitigation is a conformance test asserting agreement for every observation —
listed in §10, not implemented here.

## 2. Exact meaning of "fact occurrence"

**Meaning A is frozen: `filing_document_fact_occurrences` is a LOGICAL
fact-in-document identity, with byte locator stored only as evidence payload.**

Reasoning, not preference:

- A *logical* fact in XBRL is the tuple `(concept, context, unit)`, which the instance
  guarantees is present **at most once**. That is a semantic identity the document
  itself declares.
- A *physical* occurrence is a byte span. It is an artifact of the serializer: inline
  XBRL emits `ix:continuation` chains, so **one fact legitimately spans several byte
  ranges**. Making the locator part of the identity would therefore fork a single fact
  into several, i.e. fabricate facts.
- The 0020 precedent does not transfer, and the difference is precise. A *statement* is
  a pure text occurrence with no semantic key, so its locator is all it has and belongs
  in the identity (`0020:370-372`). An XBRL fact has `contextRef`. Locator is
  **derived evidence**.

**Multiple physical appearances of one logical fact in one document → ONE row**, with
all spans in `locators_json` as a canonical, deterministically ordered array. No
separate evidence-occurrence relation is needed, because the set of spans is *derived
from* the identity rather than being an independent fact about the document.

## 3. Exact `dfid_` preimage

`document_fact_id = "dfid_" + sha256(canonical_json(preimage)).hexdigest()[:32]`

| Field | Identity role |
| --- | --- |
| `provider` | Keeps cross-source separation possible; the basis of 2.3-B. |
| `asset_id` | 0020 keys are asset-scoped throughout; functionally determined by `accession`, and the redundancy is *consistent*, not *conflicting*. |
| `accession` | **Required.** `document_id` is content-addressed and *can* be shared across filings (identical EDGAR-generated bytes), and two filings' identical bytes are two different filings' assertions. |
| `document_id` | **Required, and the only classifier-free way** to tell a filed primary HTML, an EDGAR `_htm.xml`, and a legacy `EX-101.INS` apart. Naming a document is permitted; describing what kind it is is not. |
| `taxonomy` | Namespace; two taxonomies may declare the same local name. |
| `tag` | Local name of the concept. |
| `context_ref` | **Required.** The instance's own identifier for the whole reporting context: entity, period, and every segment/scenario member. Without it, dimensional and undimensioned contexts carrying identical values are indistinguishable (`ifrs_capex_context_237.py:21-25`). |
| `unit_ref` | **Required.** The same `(tag, contextRef)` can be stated under different units; a fact without a unit is not a fact. |

**Excluded, each with its reason:**

| Excluded | Reason |
| --- | --- |
| `value` / `resolved_value` | A restatement is a different fact, not the same fact re-valued (`evidence_model.py:184-188`). It also *makes the Case-D ambiguity detectable*: two nodes with the same triple and different values collide on `dfid_` and hit the node-uniqueness index, instead of forking silently. |
| `filename` | The fact lives in the **bytes**. Two byte-identical filenames in one filing would fork one fact into two. Still carried as a column for the foreign key. *(Whether one byte sequence under two filenames is one occurrence remains unresolved — §12.1.)* |
| `period_start` / `period_end` | In XBRL the period lives **inside the context**, so `context_ref` determines it. Including it invites two derivations of one field to disagree and fork identity. Stored as resolved evidence. |
| byte locator | **Derived** from the identity (§2). |
| `captured_at` / `capture_kind` | Transfer metadata about the read, never identity (`0020:234-236`). |
| evidence classifier | Invariant 19. No authorship, legal-source, or precedence field may exist in this relation. |

### Cases A–F

| Case | `dfid_` | Occurrence rows | `observation_filing_documents` |
| --- | --- | --- | --- |
| A. same fact, same document, same context | **equal** | 1 (idempotent) | 1 row |
| B. same document, later capture with changed bytes | **different** (`document_id` differs) | 2 | 1 row (filename grain) |
| C. same concept/period, different `contextRef` | **different** | 2 | 1 row |
| D. same `contextRef`, different values | **equal → collision** | **0 — refused** | **no row** |
| E. same fact at several byte locations | **equal** | 1, locator set | 1 row |
| F. same fact in primary HTML and `_htm.xml` | **different** | 2 | **no row** (2 documents) |

## 4. Exact uniqueness algorithm

Five distinct notions, kept apart. Producer-side order; nothing is written before
everything below passes.

1. **Document identity.** `filing_documents` must hold the row. Identity is minted only
   by a directory-manifest declaration occurring exactly once (`0020:304-335`). A
   duplicate-declared filename mints nothing → UNAVAILABLE.
2. **Capture identity.** The occurrence must FK to a real
   `filing_document_captures(asset_id, accession, filename, document_id)` row.
   Enforced by the composite FK.
3. **Fact-locatability, per document.** For each capture, locate every node matching
   `(taxonomy, tag)`. Resolve `contextRef` and `unitRef` to real context and unit nodes.
   **Locatable = for each `(context_ref, unit_ref)` present, exactly one node.** All
   found spans go into one `locators_json`. Zero nodes, an unresolvable ref, or two
   nodes sharing one triple (**Case D**) → not locatable → mint nothing → UNAVAILABLE.
4. **Occurrence identity.** For every locatable node, mint `dfid_` and insert. The
   five-column UNIQUE index is the backstop; a collision is an ambiguity, never a second
   identity.
5. **Candidate-document cardinality.** Count **distinct `(asset_id, accession,
   filename)`** across all minted occurrences of this fact in this filing — *not*
   distinct `document_id`, and *not* capture rows, because Case B would otherwise turn a
   resolvable 1 into a spurious 2.
   - `= 0` → UNAVAILABLE.
   - `= 1` → write `observation_filing_documents` (1 row) **and** the link rows.
   - `≥ 2` → **no assertion** (Case F). Link rows may still be written, because an
     occurrence is a true statement about bytes; only the *source* assertion is withheld.

**Evidence required to prove a candidate is the exact source:** that the observation was
derived from that occurrence; that the occurrence's `dfid_` recomputes from its
persisted preimage; that its locator, applied to `source_documents.content` for that
`document_id`, recovers `value_text` byte-for-byte; that its context resolves to the
declared entity/period/dimensions; and that no other candidate document contains it.

**Prohibited, and absent from the algorithm:** filename, extension, MIME, `<TYPE>`,
primary-document status, inferred precedence, confidence scores, arbitrary tie-breaking.

## 5. Duplicate-fact treatment

`CORRECTION` to Amendment 1 §8. That table required, for **Case C**, "that one node is
unique **and** only one document" before writing `observation_filing_documents`. The
node-uniqueness half **is withdrawn**.

Reason: the frozen semantics is document-grain. Amendment 0 Decision 1 says the
relation asserts *"this observation was read out of this one filing document"*, and
Decision 2 counts **documents**. If a document contains two contexts that both match
the observation, the document is still certainly where the observation was read — that
is true and useful. Requiring node uniqueness would report UNAVAILABLE when the truth is
known, which is the unknown/unavailable collapse the architecture treats as a defect
(`evidence_model.py:40-55`).

What survives: **fact-locatability** (§4.3). A fact that cannot be located mints no
occurrence, hence 0 candidates, hence UNAVAILABLE. Case D stays UNAVAILABLE — not
because of two nodes in one document, but because *nothing was locatable*.

Net: Case C → 2 occurrences, 1 document, **1 assertion row**.

## 6. Dimension-collision treatment

Two or more `contextRef`s map to the same observation identity because `observation_id`
has no dimension slot (`sec_ingest.py:2391-2394`).

- Each context mints its **own** `dfid_` and its **own** occurrence row. Distinctness is
  preserved where the schema allows it.
- All are linked to the **one** observation. `observation_filing_documents` gets 1 row if
  they share one document.
- The observation stores the aggregate-route reading; which member it came from is
  **not** claimed. The existing `dimension_collision` / `DIMENSION_COLLISION` mechanism
  (`sec_ingest.py:2191-2236`, `evidence_query.py:94,349`) remains the only place that
  ambiguity is reported.
- **Nothing is solved by changing `Observation` in this phase**, and nothing may be: a
  dimension slot in `observation_id` would re-key history.

## 7. `document_hashes` trap decision

| | Finding |
| --- | --- |
| **A. Reachable?** | Yes. `_link_documents` runs on **both** paths — the dedup early-return (`sqlite_archive.py:1290`) and the insert (`:1373`). |
| **B. Relation written** | `observation_sources (observation_id, document_id, accession)`, `INSERT OR IGNORE` (`:1483-1487`). |
| **C. Semantics** | "The documents this reading was extracted from" — multi-valued, PK `(observation_id, document_id)`, **no append-only triggers at all** (only an index, `0001:167-175`). |
| **D. Bypass?** | **Yes, structurally.** Nothing distinguishes an acquisition response from a filing document: there is no FK from `observation_sources` to `filing_documents`, no 0/1 discipline, no append-only enforcement, and `documents_for()` (`:1228-1236`) returns the list a reader would consult to answer "which document did this come from?" |
| **E. Can a filing hash cause it?** | **Yes.** `document_id_for` (`:1213-1226`) resolves by `content_hash`, and filing documents *are* stored in `source_documents` (`sec_ingest.py:1964-1976`). The only guard refuses a hash that was **never captured** — a captured filing document passes. |
| **F. Block before 3C-B?** | **Yes.** 3C-B is precisely the route that holds filing hashes, so this becomes reachable the moment it exists. |
| **G. Minimal fix** | One additive `BEFORE INSERT` trigger (§1.3). No schema change, no data change, no Python change, no backfill. |

**Verdict: a latent architectural violation, not merely an evidence path.** It is not a
live defect today — the SEC path passes only the `companyconcept` response hash
(`sec_ingest.py:2145-2149, 2283`) — but the frozen 0/1 semantics are only as strong as
the weakest write path into any relation a reader could mistake for the frozen one. The
trigger makes the boundary a database fact rather than a convention. Whether a *Python*
guard is also wanted is a separate question and is not decided here.

## 8. `interpretations` / `admissions` decision

`CORRECTION`. Amendment 1 §10 and §D invariant 27 required `observations.
source_fact_id = NULL` for document-route observations, and listed the consequences:
invisible to `interpretations`, NULL in `admissions`, skipped by three join paths.

**That requirement is withdrawn. It was wrong, and it contradicts §D invariant 24,
which this audit verified in the same repository.**

- `§D invariant 24` requires the document route to compute `source_fact_id` **the
  production way**. A computation whose result is never persisted is not adapter-
  independence and produces no dedup; it is a discarded value. The two clauses cannot
  both hold.
- The NULL rule also **defeats the entire purpose of the document route**: with NULL,
  `knowledge_axis.SourceFact` raises `KnowledgeAxisError("a source fact must identify
  itself")` (`knowledge_axis.py:182-183`), `interpretations.source_fact_id` is `NOT NULL
  REFERENCES observations(source_fact_id)` (`0017:89-92`), and a document-route fact
  would be **structurally uncorrectable** — the very defect `interpretations` exists to
  fix (2.53).
- `observations_source_fact_full` is a **full** UNIQUE index (`0017:54-55`); SQLite
  treats NULLs as distinct, so it never obstructed a non-NULL value in the first place.

**Decisions:**

- **A. NULL is not acceptable and is not used.** A document-route observation carries the
  accession-scoped `sfid_` computed exactly as production computes it, and **never** a
  `dfid_`.
- **B. Not excluded from `interpretations`.** Nothing to decide: a non-NULL `sfid_`
  satisfies the FK, and the correction machinery works unchanged.
- **C. Not excluded from `admissions`.** `admissions.source_fact_id` is nullable
  (`0019:61`) but is populated; the metric → concept → accession → `source_fact_id`
  chain stays intact.
- **D. `knowledge_axis`** has no new dependency: it required non-NULL all along, which
  is now satisfied.
- **E. Another relation is required** — the two in §1, for a different reason: to hold
  document-level occurrences. Nothing extra is required for `interpretations` or
  `admissions`.
- **F. Another design decision IS required**, and this is why 3C-B stays closed: the
  `interpretations` / `admissions` item of Amendment 1 §11.5 was premised on the NULL
  rule and is now **retracted**. It is replaced by §10's items.

All three `source_fact_id` join paths (`fullscope_bulk.py:325-346`,
`merge_sources.py:124-133`, `crossframework_verify.py:331`) therefore need **no**
widening, exclusion, or modification. None is broadened.

## 9. Exact UNAVAILABLE cases

Amendment 0 §4's ten cases stand, extended by Amendment 1 §9's five, plus:

16. no directory-manifest declaration, or a duplicate one (no document identity);
17. no capture row for the document;
18. the concept is absent from every capture;
19. `contextRef` or `unitRef` does not resolve to a node;
20. **Case D** — two nodes sharing `(tag, contextRef, unitRef)` with differing
    attributes/values (invalid instance);
21. a fact node that is not numeric;
22. the observation is already held by the aggregate route — **permanent**, invariant 22.

## 10. Exact Phase 3C-B acceptance criteria

1. Migration `0021` applied; `pre_migration check` of §1.3 returns zero.
2. `dfid_` recomputes from the persisted `document_fact_identity` on every row.
3. Every `locators_json` entry, applied to the capture's uncompressed bytes, recovers
   `value_text` **byte-for-byte** — the exact round-trip standard `filing_document_
   statements` already meets.
4. `locators_json` is deterministic across repeated runs (same array, same order).
5. Case D is refused with the uniqueness-index violation, never forked.
6. Case F yields **zero** `observation_filing_documents` rows.
7. The `observation_sources` guard trigger is proven: a filing-document hash cannot be
   inserted.
8. Every `observation_filing_documents` row agrees with the derived count==1 case.
9. The §9 UNAVAILABLE set is each reproduced by a network-free fixture.
10. Network-free fixtures at both shapes: 2026 cardinality-2 inline, 2013 cardinality-1
    `EX-101.INS`.

## 11. Exact migration requirements

**One migration, `0021_sec_document_fact_occurrences.sql`.**

- Additive only: two `CREATE TABLE`, four append-only triggers, two closed-vocabulary
  triggers, one consistency trigger, one guard trigger, three indexes, one UNIQUE index.
- **No `UPDATE`, no `DELETE`, no `INSERT`, no data migration, no backfill, no re-key.**
- Forward-only, inside one explicit transaction (`0017:74-87`).
- **Pre-migration gate:** assert zero existing `observation_sources` rows reference a
  `filing_document_captures` document, and record the count. Not verifiable from the
  repository; no built archive is committed.
- Existing relations are **not** altered. `observations.source_fact_id` keeps accepting
  non-NULL values; `interpretations` and `admissions` are untouched.

## 12. Historical Phase 3C-B status (as recorded at the time)

**Historical status at the time:** this note recorded Phase 3C-B as not authorized and listed migration `0021` plus ten acceptance criteria as anticipated follow-up work. This description is not a current requirement, restriction, or permission gate; determine current work from the user's current instructions and actual implementation.

### Status of every decision

**Already frozen (unchanged by this audit):** `observation_filing_documents` semantics
and 0/1 cardinality (Amendment 0 D1–D2); Option 1 for the dual-document case (D3);
`contextRef` as a frozen limitation for the aggregate route (D4); byte scanning
rejected (D5); `source_fact_id` reuse at observation grain (Amendment 1 D, invariant
24); the `dfid_` namespace as occurrence-only (invariant 25); `contextRef`/`unitRef`
required and locator is evidence (invariant 26); supplement-not-replace.

**New in this audit:** the two relation schemas (§1); occurrence = *logical* fact (§2);
the eight-field preimage with per-field roles (§3); the five-step uniqueness algorithm
with document-grain counting (§4); Case C → 1 assertion (§5); dimension members as
distinct occurrences on one observation (§6); the `observation_sources` guard trigger
(§7); the `sfid_`-not-NULL correction (§8); five more UNAVAILABLE cases (§9); ten
acceptance criteria (§10); migration `0021` (§11).

**Corrections to frozen text:** Amendment 1 §10's NULL consequence **withdrawn**;
Amendment 1 §8's Case-C node-uniqueness condition **withdrawn**.

**Still unresolved (untouched):** the six of Amendment 1 §12 — the `source_fact_id`-
keyed "where was this held fact observed" relation; a second target identity for
`interpretations`; byte-identical documents under two filenames; `asset_id`'s
redundancy in the preimage; inline-vs-extracted dedup (**blocked on invariant 19**);
aggregate-route deprecation.

**Newly unresolved by this audit:** whether a Python-level guard should accompany the
§1.3 trigger; where the §10.8 agreement check lives (test vs. read-time derivation);
and whether the pre-migration gate of §11 is a test or a migration step.

---
---

# Amendment 3 — Taxonomy identity and locator payload, corrected

**Status:** FROZEN — identity correction found by the 3C-B1 pre-commit audit.
Implemented in the 3C-B1 extractor. **No migration change, no schema change.**
**Date:** 2026-10-08
**Refines:** Amendment 2 §3's `taxonomy` field and §1.1's `locators_json`.

> Amendment 2 named `taxonomy` without saying which representation it held. An
> implementation had to decide, decided it as the document-declared **prefix**,
> and the audit reproduced two ways that is wrong. This amendment records the
> corrected decision and the evidence for it.

## 1. `taxonomy` is the namespace URI, not the prefix

A prefix is an alias a document chooses; XML does not treat it as significant.
Two failure modes were reproduced on real XML before this was settled:

* **Fragmentation.** One namespace bound to two prefixes in a single document
  (`us-gaap:` and `gaap:` for `http://fasb.org/us-gaap/2026`) produced **two**
  `dfid_`s for one expanded name — and the five-column uniqueness index could not
  catch it, because that index reads `taxonomy` too.
* **Collapse — the serious direction.** XML permits a prefix to be rebound in a
  nested scope. `xmlns:my=".../tenant-a"` on the root with
  `xmlns:my=".../tenant-b"` inside a wrapper gave `tenant-a:Revenues = 100` and
  `tenant-b:Revenues = 200` the **same** `dfid_`. Two distinct concepts, one
  identity. Where the values happened to agree, the uniqueness index would not
  even fire.

The earlier justification for prefix — that us-gaap republishes its namespace each
year, so a URI would re-identify one concept per filing — **was wrong**.
`document_id` is already in the preimage, so a 2023 fact and a 2024 fact have
different identities whatever `taxonomy` says; identity granularity is per
captured document, and the year-to-year churn was never a reason.

`taxonomy` therefore holds the resolved **namespace URI**, with bindings resolved
per element against the scope that element sits in, never from a root-only map.
A QName in an inline fact's `name` attribute is resolved the same way, so a
concept asserted inline and the same concept asserted in an instance of one
document share a taxonomy.

**Accepted trade:** `taxonomy` here is a URI while the archive's concept
vocabulary elsewhere is `us-gaap:Tag`. That is acceptable because `dfid_` and
`sfid_` are different grains and are never joined. Joining a `dfid_` to the
registry will need a prefix-to-URI mapping, which belongs to the registry and is
not this layer's business.

## 2. What counts as a fact

`contextRef` alone is necessary but not sufficient: a **tuple** references a
context and declares a unit, and it is a container. Reading one as a fact had
produced `value_text = "2500000"` from its single numeric child — a fabricated
fact whose value came from somewhere else entirely.

The rule is now two structural conditions, neither of which is a namespace
allow-list:

1. the element declares `contextRef`; and
2. it has **no child elements**.

A fact may live in any extension namespace, so an enumeration of the namespaces
that count would be both incomplete and fixture-driven. A prefix list was not
introduced to patch this, and a test asserts that a namespace never heard of
still yields a fact.

## 3. `locators_json` is a list of appearances, not a flat span list

A document may state one logical fact more than once. Flattening every span of
one logical fact into a single list breaks the verification property: for a fact
asserted twice, the concatenation of all spans is the value **twice**, and no
longer round-trips to `value_text`.

`locators_json` is therefore a canonical array of span groups, one per
appearance. Each group independently reproduces `value_text`, so the payload is
verifiable span by span. An `ix:continuation` chain is one appearance and stays
one group; a fact in two separate elements is two groups.

Aggregation happens in the parser, **before** the row exists. The relation is
append-only and has no `UPDATE`, so a locator discovered after the insert could
never be added — which is why the aggregation cannot be deferred to the writer.

## 4. Conflicting repeats

Two appearances of one identity that resolve **differently** are not merged and
not written. They are a contradiction, reported as `CONFLICTING_REPEAT`. They are
deliberately not resolved by preferring the first occurrence: inventing precedence
is exactly what invariant 19 forbids, and it would also be silent.

## 5. What did not change

The eight-field preimage is unchanged. `filename`, value, period, locator,
`captured_at`, `capture_kind` and every classifier stay out of the digest. The
five-column uniqueness index is unchanged, and it now agrees with `dfid_` exactly:
its columns are the digest's fields minus `provider`, `asset_id` and `accession`,
which are functionally determined by `document_id` through the composite foreign
key.

---
---

# Amendment 4 — Taxonomy Equivalence Is Currently Unproven (Option A)

**Status:** FROZEN — conservative decision for Phase 3C-B2. **Implemented** by
`sec_xbrl_facts.occurrence_matches_observation` and pinned by
`tests/test_sec_observation_fact_links.py::TestTaxonomyUnproven`.
**Date:** 2026-10-08
**Supersedes:** nothing. **Bounds:** the linkage path's *production* reach; every
other B2 gate (context, cardinality, exact-source) is exercised and unaffected.

---

## 1. The two taxonomy representations, and why they are not compared

Two stored fields are both called `taxonomy`, and they are **not** the same
representation:

- an **Observation's** `taxonomy` is the SEC/companyconcept **prefix**
  representation, e.g. `us-gaap` — sourced from `concept_registry.taxonomy` and
  the companyconcept payload;
- a **document fact's** `taxonomy` is the **resolved namespace URI** the document
  bound that prefix to, e.g. `http://fasb.org/us-gaap/2026` (Amendment 3 §1).

This repository holds **no verified prefix-to-URI mapping**. Inventing one in this
phase is forbidden: a mapping is an evidence/architecture decision, not an
implementation detail, and a guessed table would collapse distinct concepts
(`us-gaap:Revenues` vs `custom:Revenues`) that share a local name, a period, a
unit and often a value.

The frozen comparison is therefore **equality only**, over the *stored* strings:

> **Taxonomy equivalence is UNPROVEN unless the Observation taxonomy and the
> document-fact taxonomy are directly comparable under existing evidence.**

A prefix and a URI are never equal strings, so no equivalence between them is
provable here and none is assumed.

## 2. Consequence: the production linkage path is intentionally inactive

For an **ordinary real SEC observation** (prefix form), no document fact ever
compares equal, so:

```
TAXONOMY_UNPROVEN
    → no observation_filing_document_facts
    → no observation_filing_documents
```

This is **intentional**, and it is a *limitation of the evidence representation*,
not a defect to be patched and not a reason to invent a mapping. The refusal is
reported (`TAXONOMY_UNPROVEN`), never absorbed silently.

**The accurate statement is:** *taxonomy equivalence is currently unproven by the
archived evidence representation.* It is **not** "SEC taxonomy is incompatible,"
and it is **not permanent**: the moment an Observation's taxonomy is persisted in
the same representation a document fact uses (a URI), matching begins to work
with **no change to the matching rule**, because the rule is already equality.

## 3. What remains reachable, and how it is pinned

The conservative gate does not make the rest of B2 dead code. The context gate,
the document-cardinality gate, append-only behaviour, idempotency, the
`observation_sources` bypass guard, and the no-amend rule are all independent of
the taxonomy question, and each is exercised by tests that use an **explicitly
comparable** taxonomy representation — both sides in the URI form — so the
machinery stays covered without any production prefix-to-URI map existing.

A future taxonomy-equivalence design, if one is wanted, requires its **own**
evidence and architecture decision. It is out of scope for B2 and must not be
smuggled in to make a fixture pass.

---
---

# Amendment 5 — Taxonomy Equivalence Architecture & Evidence Boundary

**Status:** FROZEN — design decision record and evidence audit. **Not implemented.**
No production code, schema, migration, or test change accompanies this amendment.
**Date:** 2026-10-08
**Baseline:** `5e6287b` (`feat: link observations to document XBRL facts`), working tree clean, `HEAD == origin/master`
**Refines:** Amendment 4's unproven boundary, defining the evidence requirements,
identity grain, authority vs. filing-use separation, and decision boundary for taxonomy equivalence.
**Invariants referenced as binding by this historical note:** `docs/ST-EVA-ARCHITECTURE.md` §D invariants 19–30.

> This amendment audits whether authoritative evidence exists to bridge the SEC
> `companyconcept` taxonomy representation (short family token, e.g. `us-gaap`) to
> the document fact taxonomy representation (resolved namespace URI, e.g.
> `http://fasb.org/us-gaap/2026`). It records the findings, proves the identity
> grain separating authority assertions from filing use, establishes provenance
> standards across SEC authority sources, and formalizes the design decision.
> **Taxonomy mapping remains unimplemented and B2 remains strictly unchanged.**

---

## 1. Authority Identity vs. Filing Use

Authority recognition and filing use are fundamentally different facts with different grains:

* **Authority Fact (Regulator / Standard-Setting Grain):**
  *"The SEC recognizes namespace URI `http://fasb.org/us-gaap/2026` as belonging to taxonomy family `US GAAP`, release/version `2026`."*
  This is a universal regulatory fact published by the SEC. It is true across all filers and all filings, and does not depend on any specific company having filed an instance. Its identity grain is:
  `{provider, taxonomy_family, taxonomy_version, namespace_uri}`.
* **Filing-Use Fact (Filing / Occurrence Grain):**
  *"Filing accession `0000320193-26-000018`, document `aapl-20260730.htm` contains a fact using namespace URI `http://fasb.org/us-gaap/2026`."*
  This is an empirical observation read from captured filing bytes. Its grain is:
  `{asset_id, accession, document_id, context_ref, tag, ...}` (the occurrence grain).

**Separation Requirement:**
Authority evidence must **not** be accession-scoped. Accession is evidence of *use*, not the identity of the authority mapping. Conflating the two would require re-asserting the regulator's taxonomy catalog for every filing, destroying identity purity.

---

## 2. Taxonomy Version Requirement & Identity Grain

### 2.1 Why `taxonomy_version` Is Required
The SEC's official Standard Taxonomies materials explicitly distinguish three levels:
1. **Taxonomy Family**: The high-level framework (e.g. `US GAAP`, `IFRS`, `DEI`, `FFD`, `ECD`, `CYD`).
2. **Taxonomy Release / Version**: The specific annual or interim release (e.g. `2026`, `2025`, `2025q4`, `2024Q2`).
3. **Namespace URI / Schema**: The specific targetNamespace (e.g. `http://fasb.org/us-gaap/2026`, `http://xbrl.sec.gov/ffd/2024q2`).

Preserving explicit `taxonomy_version` alongside `taxonomy_family` and `namespace_uri` is required because:
- **Non-Uniform URI Conventions:** While namespace URIs are unique per release, URI formatting across families is not uniform. US-GAAP uses annual years (`/2026`); historical DEI used ISO dates (`/2013-01-31`); IFRS uses dates (`/2025-03-27/ifrs-full`); FFD, CEF, and SPAC use quarterly releases (`/2024q2`, `2021Q4`, `2025q3`). Inferring version via regex would be an unmaintainable heuristic.
- **Regulatory Rules Key on Version:** EDGAR Filer Manual rules (EFM §6.5.7–6.5.8) regulate permitted taxonomy versions (e.g. restricting submissions to the latest 2–3 annual releases). Preserving `taxonomy_version` maintains 1:1 fidelity with SEC regulatory notices and deprecation schedules.
- **Authority Structure:** The SEC's machine-readable catalog (`edgartaxonomies.xml`) explicitly publishes `<Version>` as an independent attribute on every location record.

### 2.2 Complete Identity Preimage
Within one `(provider, taxonomy_family, taxonomy_version)`, multiple entry points and packages exist (e.g. `us-gaap` primary vs. `us-gaap-ebp` employee benefit plans vs. `srt` SEC reporting taxonomy). Therefore, `namespace_uri` is required in the preimage.
The canonical authority preimage is:
```
{ provider, taxonomy_family, taxonomy_version, namespace_uri }
```

---

## 3. Exact SEC Authority Sources

No single document is "the sole authoritative source". The SEC maintains a clear hierarchy of authority sources:

| Source | Location / Format | What It Proves | Authority Level | Provenance Viability |
|---|---|---|---|---|
| **1. SEC XML Taxonomy Catalog (`edgartaxonomies.xml`)** | `https://www.sec.gov/info/edgar/edgartaxonomies.xml` (Root `<Erxl>`, versioned, e.g. `version="78"`). | Exact machine-readable binding between `<Family>`, `<Version>`, `<Namespace>`, `<Prefix>`, `<FileTypeName>`, and schema `<Href>`. | **Primary Machine-Readable Operational Authority.** Produced by SEC staff specifically for EDGAR ingestion/validation. | **High.** Capturable raw XML bytes; stored in `source_documents` with SHA-256 digest. Versioned by SEC. |
| **2. EDGAR Filer Manual (EFM)** | SEC Form Filer Manual, Vol. II, Chap. 6 ("Interactive Data"). | Legal/regulatory mandate for acceptable taxonomy versions, permitted combinations, and tagging rules. | **Statutory / Regulatory Authority.** Promulgated by Commission rulemaking in the Federal Register. | **Very High.** Formally published per SEC release; dated and versioned. |
| **3. Standard Entry Point Schemas (`.xsd`)** | e.g. `https://xbrl.fasb.org/us-gaap/2026/elts/us-gaap-2026.xsd`, `https://xbrl.sec.gov/dei/2026/dei-2026.xsd`. | Technical XML schema definition, official targetNamespace, element QNames, and imported schemas. | **Technical Specification Authority.** W3C XML Schema definitions. | **Permanent.** Immutable once published at official schema URIs. Capturable as text bytes. |
| **4. SEC Standard Taxonomies Web Listing** | `https://www.sec.gov/data-research/structured-data/taxonomies-schemas/standard-taxonomies/operating-companies`. | Human-readable portal listing accepted releases, zip packages, and transition dates. | **Official Guidance.** Published by SEC Office of Structured Data. | **Medium.** Capturable as HTML; subject to CMS/portal redesigns. |
| **5. EDGAR Release Announcements** | Commission releases (e.g. "EDGAR Release 24.1", "SEC Announces Support for 2026 Taxonomies"). | Official deployment dates and retirement schedules for specific taxonomy releases. | **Regulatory Notice.** Formal administrative timeline. | **High.** Permanent archive on SEC.gov. |

*Descriptive guidance* (such as Staff Observations on Custom Tags and FAQ pages) explicitly disclaims legal authority and must not be used as an authority mapping source.

---

## 4. Namespace Declaration vs. Authority Recognition

Two independent statements must never be merged:
1. **Document Namespace Declaration (Filing Evidence):**
   A filing document's XML header declares `xmlns:prefix="URI"`.
   *Proves:* Inside that document, the author bound that prefix to that URI, yielding fact QName `(URI, tag)`.
   *Does NOT Prove:* That `URI` is an authorized SEC standard taxonomy. A filer could bind any prefix to a custom or invalid URI.
2. **SEC Authority Recognition (Authority Evidence):**
   The SEC XML catalog (`edgartaxonomies.xml`) maps `URI` to `(Family, Version)`.
   *Proves:* EDGAR recognizes `URI` as an official standard taxonomy family.
   *Does NOT Prove:* That any particular filing used it.

**Synthesis:** Linkage requires proving both: the filing document asserts the fact under `URI`, and the authority catalog proves `URI` is standard family `us-gaap`.

---

## 5. Custom Taxonomies & Issuer Extensions

* **Issuer Extension Namespaces:** Namespaces declared by issuers (e.g. `http://apple.com/20260730`) are absent from the SEC XML catalog. They have zero authority recognition and **never** match standard observations.
* **Custom Prefixes:** If a filer declares `xmlns:mygaap="http://fasb.org/us-gaap/2026"`, ST-EVA resolves the namespace URI per Amendment 3 §1. The arbitrary prefix string `mygaap` is discarded. Because `http://fasb.org/us-gaap/2026` is an authorized URI, it correctly matches standard `us-gaap`.
* **Custom Concepts:** An extension element `<xs:element name="Revenues">` defined under an issuer targetNamespace shares a local name with standard `Revenues`. Because its resolved namespace URI is the issuer URI, it is refused. Local tag equality never overrides namespace mismatch.
* **Standard Namespaces Imported by Extensions:** When an extension schema imports `http://fasb.org/us-gaap/2026`, standard facts tagged in the instance carry the standard URI and match. Extension facts carry the issuer URI and stay excluded.

---

## 6. Precise B2 Activation Proposition

For an Observation `obs` and a document fact occurrence `occ`:
`taxonomy_equivalent(obs, occ)` evaluates to **TRUE** if and only if:
1. `obs.provider == occ.provider` (e.g. `"SecEdgar"`).
2. `_local_name(obs.concept) == occ.tag`.
3. **Authority Recognition:** An authority assertion exists in captured authority evidence proving that `occ.taxonomy` (the resolved URI) belongs to `taxonomy_family == obs.taxonomy` for that provider.
4. **Filing Concordance:** `occ.accession == obs.accession` and `occ.asset_id == obs.asset_id`.

If Condition 3 is not proven from captured authority evidence:
`TAXONOMY_UNPROVEN` → 0 `observation_filing_document_facts` rows, 0 `observation_filing_documents` rows.

---

## 7. Data Model Comparison (Option C Adopted)

* **Option A (Authority + Accession in One Relation):** REJECTED. Conflates authority recognition with filing use, multiplies authority rows across millions of accessions, and destroys identity purity.
* **Option B (Separate Authority and Filing-Use Relations):** REJECTED AS REDUNDANT. `filing_document_fact_occurrences` already records `(document_id, taxonomy)` where `taxonomy` is the resolved URI. A separate `filing_document_taxonomies` table would duplicate existing layer 2 provenance.
* **Option C (Authority Relation Only; Filing Use Derived from Occurrences):** **ACCEPTED.**
  An append-only relation `authority_taxonomy_namespaces` records the regulator's authority mapping. Filing use is already captured by `filing_document_fact_occurrences`. B2 checks whether `occurrence.taxonomy` exists in `authority_taxonomy_namespaces` for the observation's provider and family.

### Candidate Schema: `authority_taxonomy_namespaces` (Specification Only — Not Implemented)
```sql
CREATE TABLE IF NOT EXISTS authority_taxonomy_namespaces (
    authority_taxonomy_id TEXT PRIMARY KEY,
    -- Preimage: {provider, taxonomy_family, taxonomy_version, namespace_uri}
    authority_taxonomy_identity TEXT NOT NULL UNIQUE,
    provider              TEXT NOT NULL,
    taxonomy_family       TEXT NOT NULL,
    taxonomy_version      TEXT NOT NULL,
    namespace_uri         TEXT NOT NULL,
    standard_prefix       TEXT NOT NULL,
    file_type_name        TEXT NOT NULL,
    href                  TEXT NOT NULL,
    authority_source      TEXT NOT NULL, -- e.g. 'https://www.sec.gov/info/edgar/edgartaxonomies.xml'
    authority_document_id TEXT NOT NULL REFERENCES source_documents(document_id),
    captured_at           TEXT NOT NULL,
    FOREIGN KEY (authority_document_id) REFERENCES source_documents(document_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS authority_taxonomy_lookup
    ON authority_taxonomy_namespaces(provider, namespace_uri, taxonomy_family);
```

---

## 8. Mutability & Append-Only Semantics

* **Authority Assertions:** Strictly append-only. Immutable once inserted. `BEFORE UPDATE` and `BEFORE DELETE` triggers abort. Updates by the SEC (new catalog versions) insert new rows; existing rows are never modified.
* **Filing-Use Assertions:** `filing_document_fact_occurrences` is already append-only (guaranteed by triggers in `0021`). No current-value or precedence model is permitted.

---

## 9. Strict Separation from Invariant 19

Taxonomy equivalence evaluates concept semantics; it does **not** evaluate document authoritativeness.
In the inline XBRL dual-document case (`0000320193-26-000018`):
- Both `aapl-20260730.htm` (inline HTML) and `aapl-20260730_htm.xml` (EDGAR extraction) declare the identical standard URI `http://fasb.org/us-gaap/2026`.
- Taxonomy equivalence proves equivalence for **both** documents identically.
- Both yield valid linked occurrences.
- Document-grain cardinality is 2.
- Under Amendment 0 Decision 3 and Amendment 2 §4.5, cardinality 2 yields `DOCUMENTS_AMBIGUOUS` and **zero rows in `observation_filing_documents`**.
- Taxonomy equivalence cannot break this tie and does not bypass Invariant 19.

---

## 10. Formal Design Decision Matrix & Corrections to Prior Audit

### 10.1 Corrections to Amendment 5 Initial Draft
1. **CORRECTION on Grain:** The initial draft proposed `(provider, taxonomy_family, namespace_uri) evaluated at accession scope`. This is corrected: accession is excluded from authority identity. Authority identity is `{provider, taxonomy_family, taxonomy_version, namespace_uri}`.
2. **CORRECTION on Authority Source:** The initial draft characterized EDGAR Standard Taxonomies as "the sole authoritative SEC-side evidence". This is corrected: `edgartaxonomies.xml` is the primary machine-readable operational catalog, governed legally by the EDGAR Filer Manual and technically by standard entry point schemas.

### 10.2 Decision Matrix

| Item | Question | Formal Decision |
|---|---|---|
| **A** | **Authority identity grain** | `{provider, taxonomy_family, taxonomy_version, namespace_uri}`. Accession is excluded. |
| **B** | **Version required?** | **Yes.** Required to capture exact SEC release metadata (e.g. `2026`, `2025q4`) and prevent fragile regex URI parsing. |
| **C** | **Exact SEC authority sources** | Hierarchy: 1) `edgartaxonomies.xml` (machine-readable), 2) EDGAR Filer Manual (regulatory), 3) `.xsd` entry points (technical). Guidance documents excluded. |
| **D** | **Accession in authority identity?** | **No.** Conflating authority recognition with filing use is rejected. |
| **E** | **Separate filing-use assertion table?** | **No (Option C adopted).** Filing use is already captured in `filing_document_fact_occurrences.taxonomy`. |
| **F** | **Evidence to activate B2** | Captured SEC authority document in `source_documents` + parsed authority rows + exact value/unit/context match + candidate document cardinality == 1. |
| **G** | **UNAVAILABLE cases** | Issuer extension namespaces, unmapped URIs, non-SEC sources, unmodelled taxonomies lacking URI mappings, and candidate document cardinality >= 2. |
| **H** | **Migration implications** | Requires a future forward-only migration for `authority_taxonomy_namespaces`. No changes to existing tables. |
| **I** | **Amendment 5 corrected?** | **Yes.** Corrected in §§1–10 of this record. |
| **J** | **B2 unchanged?** | **Yes.** B2 implementation and linkage logic remain 100% unchanged. |

---
---

# Amendment 6 — Taxonomy Authority Relation Schema & Migration 0022 Prerequisites

**Status:** FROZEN — schema & architecture audit record. **Not implemented.**
No production code, schema, migration, or test change accompanies this amendment.
**Date:** 2026-10-08
**Baseline:** `1f0c321` (`docs: refine taxonomy authority evidence grain`), working tree clean, `HEAD == origin/master`
**Refines:** Amendment 5's Option C data model, freezing the exact DDL, identity preimage,
provenance integration, conflict handling, and acceptance criteria for Migration 0022.
**Invariants referenced as binding by this historical note:** `docs/ST-EVA-ARCHITECTURE.md` §D invariants 19–30.

> This amendment freezes the exact relational schema and trigger constraints for
> `authority_taxonomy_namespaces`. It proves the source document integration against
> `source_documents`, establishes contradiction refusal semantics, confirms the
> exclusion of filing-use and custom namespaces, and defines the frozen boundary
> for migration 0022. **Migration 0022 is not authorized by this document.**

---

## 1. Exact Semantic Definition of `authority_taxonomy_namespaces`

The relation `authority_taxonomy_namespaces` represents a **`SOURCE_BACKED_AUTHORITY_ASSERTION`** (not an unanchored canonical identity). Each row asserts exactly one proposition:

> *"According to cited authority source document `document_id`, provider `P` recognizes that the
> standard schema identified by namespace URI `U` belongs to taxonomy family `F`,
> release/version `V`."*

It is strictly bounded as follows:

| What It Is | What It Is NOT |
|---|---|
| A source-backed regulator / standard-setting assertion | An unanchored canonical identity (which would suffer first-writer-wins) |
| A universal standard schema mapping backed by `document_id` | A filing-use assertion (which belongs in `filing_document_fact_occurrences`) |
| Provider-level authority evidence | A document occurrence or node locator |
| An immutable, content-addressed evidence record | An Observation identity or fact identity (`source_fact_id` / `dfid_`) |
| A standard taxonomy membership check | A prefix-to-URI mapping derived from an issuer's filing |
| An observable evidence record preserving multi-source claims | An inline-XBRL document classifier (Invariant 19) |

---

## 2. Exact Relational Schema (Migration 0022 DDL Specification)

```sql
CREATE TABLE IF NOT EXISTS authority_taxonomy_namespaces (
    authority_taxonomy_id TEXT PRIMARY KEY,
    -- Canonical JSON preimage digest: {document_id, namespace_uri, provider, taxonomy_family, taxonomy_version}
    authority_taxonomy_identity TEXT NOT NULL UNIQUE,

    -- The identity-bearing fields, verbatim
    document_id      TEXT NOT NULL REFERENCES source_documents(document_id),
    provider         TEXT NOT NULL,
    taxonomy_family  TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    namespace_uri    TEXT NOT NULL,

    -- Evidence payload from authority source
    standard_prefix        TEXT,
    file_type_name         TEXT,
    schema_href            TEXT,
    authority_source       TEXT NOT NULL, -- URI or canonical identifier of source
    authority_source_class TEXT NOT NULL, -- closed vocabulary
    authority_source_version TEXT,        -- e.g. root version="78" from edgartaxonomies.xml

    -- Retrieval metadata
    captured_at  TEXT NOT NULL,

    FOREIGN KEY (document_id) REFERENCES source_documents(document_id)
);

-- Read-side composite lookup index for B2 taxonomy equivalence evaluation
CREATE INDEX IF NOT EXISTS authority_taxonomy_lookup
    ON authority_taxonomy_namespaces(provider, namespace_uri, taxonomy_family);

-- Append-only trigger pair: mutations and deletions strictly forbidden
CREATE TRIGGER IF NOT EXISTS authority_taxonomy_namespaces_no_update
BEFORE UPDATE ON authority_taxonomy_namespaces
BEGIN SELECT RAISE(ABORT, 'authority_taxonomy_namespaces is append-only; updates forbidden'); END;

CREATE TRIGGER IF NOT EXISTS authority_taxonomy_namespaces_no_delete
BEFORE DELETE ON authority_taxonomy_namespaces
BEGIN SELECT RAISE(ABORT, 'authority_taxonomy_namespaces is append-only; deletions forbidden'); END;

-- Closed vocabulary trigger for authority_source_class
CREATE TRIGGER IF NOT EXISTS authority_taxonomy_namespaces_source_class_vocabulary
BEFORE INSERT ON authority_taxonomy_namespaces
WHEN NEW.authority_source_class NOT IN (
    'MACHINE_READABLE_CATALOG',
    'REGULATORY_MANUAL',
    'TECHNICAL_SCHEMA'
)
BEGIN
    SELECT RAISE(ABORT,
        'authority_taxonomy_namespaces.authority_source_class outside closed vocabulary');
END;

-- Consistency trigger: refusing conflicting re-extraction of the same authority identity
CREATE TRIGGER IF NOT EXISTS authority_taxonomy_namespaces_extraction_consistent
BEFORE INSERT ON authority_taxonomy_namespaces
WHEN EXISTS (
    SELECT 1 FROM authority_taxonomy_namespaces a
    WHERE a.authority_taxonomy_id = NEW.authority_taxonomy_id
      AND (a.authority_taxonomy_identity <> NEW.authority_taxonomy_identity
           OR a.document_id <> NEW.document_id
           OR a.provider <> NEW.provider
           OR a.taxonomy_family <> NEW.taxonomy_family
           OR a.taxonomy_version <> NEW.taxonomy_version
           OR a.namespace_uri <> NEW.namespace_uri)
)
BEGIN
    SELECT RAISE(ABORT,
        'conflicting authority extraction: identical authority_taxonomy_id resolved to differing fields');
END;
```

### 2.1 Column-by-Column Architectural Justification

| Column | Role | Architectural Justification |
|---|---|---|
| `authority_taxonomy_id` | **Primary Key** | Content-derived digest: `"atn_" + sha256(canonical_json(preimage))[:32]`. Ensures deterministic, reproducible assertion identity. |
| `authority_taxonomy_identity` | **Unique Identity** | The verbatim canonical JSON preimage string, persisted for auditability and verification without trusting key derivation. |
| `document_id` | **Identity (Key) & Provenance Link** | Foreign key to `source_documents(document_id)` holding the exact captured uncompressed bytes of the authority document. Part of the identity preimage, guaranteeing source-specific retention without first-writer-wins. |
| `provider` | **Identity (Key)** | Isolates authority claims by source provider (e.g. `SecEdgar`). Basis of cross-provider isolation (Invariant 2.3-B). |
| `taxonomy_family` | **Identity (Key)** | High-level reporting framework (e.g. `US GAAP`, `IFRS`, `DEI`). Maps to Observation `taxonomy`. |
| `taxonomy_version` | **Identity (Key)** | Preserves exact declared authority release label (e.g. `2026`, `2025q4`). Required for regulatory release fidelity. |
| `namespace_uri` | **Identity (Key)** | The declared XML targetNamespace URI. Required because multiple entry points coexist within one family/version. |
| `standard_prefix` | **Evidence Payload** | Preserves standard prefix alias declared by the authority (e.g. `us-gaap`, `ffd`). Excluded from identity. |
| `file_type_name` | **Evidence Payload** | Authority role designation (`Schema`, `Entry Point`). Descriptive metadata from source. |
| `schema_href` | **Evidence Payload** | Official schema location URL published by the authority. |
| `authority_source` | **Evidence Payload** | The URL/origin of the authority publication (e.g. `https://www.sec.gov/info/edgar/edgartaxonomies.xml`). |
| `authority_source_class` | **Evidence Payload** | Closed vocabulary classifying source level without imposing arbitrary ranking. |
| `authority_source_version`| **Evidence Payload** | Version attribute declared by the authority document itself (e.g. `version="78"` on `<Erxl>`). |
| `captured_at` | **Transfer Metadata** | Timestamp of retrieval into ST-EVA. Excluded from identity preimage. |

**Deliberately Excluded Fields:**
- `confidence`: ST-EVA records proven assertions only; no probabilistic scores.
- `is_current` / `superseded`: Point-in-time replay relies on immutable historical captures, not mutable boolean flags.
- `valid_from` / `valid_to`: Not published by SEC in `edgartaxonomies.xml`. Inventing dates would fabricate provenance.
- `precedence`: Sources are not ranked by numeric weights.

### 2.2 Removal of `UNIQUE(provider, namespace_uri)` (Audit Evidence)

The initial draft included `CREATE UNIQUE INDEX authority_taxonomy_namespace_unique ON authority_taxonomy_namespaces(provider, namespace_uri)`. This constraint is **empirically invalid on real SEC data** and has been removed for two conclusive reasons:
1. **Shared Namespaces in Real SEC Taxonomies:** Empirical audit of `https://www.sec.gov/info/edgar/edgartaxonomies.xml` (`<Erxl version="78">`) proves that standard utility and linkbase role namespaces are explicitly declared under multiple families. For example:
   - `http://www.xbrl.org/2009/role/negated` is declared under 5 families: `US GAAP`, `BASE`, `CEF`, `VIP`, `RR`.
   - `http://www.xbrl.org/dtr/type/2020-01-21` is declared under 5 families: `US GAAP`, `BASE`, `CEF`, `VIP`, `RR`.
   - `http://xbrl.org/2020/extensible-enumerations-2.0` is declared under `US GAAP` and `IFRS`.
   - `http://www.xbrl.org/2009/role/net` is declared under `US GAAP` and `BASE`.
   Enforcing `UNIQUE(provider, namespace_uri)` would cause database insertion to abort on standard, valid SEC catalog ingestion.
2. **Provenance Contradiction Semantics:** In ST-EVA, contradictory or multi-family assertions must be retained as observable evidence states (Option B). When B2 queries `authority_taxonomy_namespaces`, if `SELECT DISTINCT taxonomy_family ...` yields more than 1 family for a given `(provider, namespace_uri)`, B2 detects ambiguity and refuses linkage with `TAXONOMY_AMBIGUOUS`.

---

## 3. Source Document Provenance Integration

`authority_taxonomy_namespaces` integrates directly with the existing immutable document layer:
- The raw XML response of `edgartaxonomies.xml` is stored in `source_documents` via `SQLiteArchive.record_document`.
- Content-addressed identity: `document_id = "doc_" + sha256(content_hash)[:24]`, where `content_hash` covers uncompressed bytes.
- Document metadata: `document_type = 'SEC_TAXONOMY_CATALOG'`, `uri = 'https://www.sec.gov/info/edgar/edgartaxonomies.xml'`.
- Every authority row enforces `document_id NOT NULL REFERENCES source_documents(document_id)`.
- **One-to-many relationship:** One captured authority catalog asserts all rows parsed from that release. No new blob store is introduced.
- **Corroborating Multi-Source Preservation:** When subsequent catalog versions (e.g. `edgartaxonomies.xml` v79) or technical schemas are ingested, their assertions are preserved under their respective `document_id`s, completely eliminating first-writer-wins and silent evidence loss.

---

## 4. Identity, Uniqueness, and Conflict Handling (Cases A–G)

The canonical authority identity preimage is:
```json
{
  "document_id": "doc_a1b2c3d4e5f6789012345678",
  "namespace_uri": "http://fasb.org/us-gaap/2026",
  "provider": "SecEdgar",
  "taxonomy_family": "US GAAP",
  "taxonomy_version": "2026"
}
```

Analysis of all uniqueness and collision cases:

* **Case A (Idempotent Re-parse of Same Document):** Re-extracting identical rows from the same document produces identical `authority_taxonomy_id`. Handled via `INSERT OR IGNORE` (idempotent no-op). This also cleanly handles verbatim duplicate `<Loc>` elements inside the same SEC catalog (e.g. `http://xbrl.sec.gov/cyd/2025` which appears twice verbatim in `edgartaxonomies.xml` v78).
* **Case B (Re-assertion in Subsequent Catalog):** A subsequent SEC catalog release (e.g. `edgartaxonomies.xml` version 79, stored under `doc_79`) re-asserts an existing mapping. Because `document_id` is part of the preimage, a new assertion row is inserted. Both source assertions are retained. When queried by B2, `SELECT DISTINCT taxonomy_family ...` returns `['US GAAP']` (cardinality 1, unambiguous). Provenance is never discarded; first-writer-wins is eliminated.
* **Case C (Multiple Namespaces in Same Family/Version):** Valid standard taxonomy packages define multiple schemas (e.g. `us-gaap` primary vs. `us-gaap-ebp` benefit plans). Distinct `namespace_uri`s yield distinct `authority_taxonomy_id`s. They coexist cleanly.
* **Case D (Shared Namespaces Across Families in SEC Catalog):** As proven in §2.2, standard utility/role schemas (e.g. `http://www.xbrl.org/2009/role/negated`) are assigned to multiple families (`US GAAP`, `BASE`, etc.) in `edgartaxonomies.xml`. These coexist as distinct source assertions in the table. If an observation references such a shared namespace, B2 detects `len(families) > 1` and refuses linkage via `TAXONOMY_AMBIGUOUS`.
* **Case E (Conflicting Authority Assertions Across Sources):** If two sources disagree on the family of a concept schema (e.g. Source 1 asserts `URI-X -> US GAAP / 2026` while Source 2 asserts `URI-X -> FFD / 2026`), both assertions are persisted in `authority_taxonomy_namespaces`. Contradiction is preserved as an observable state. When B2 queries `(provider, namespace_uri)`, `SELECT DISTINCT taxonomy_family` returns `['FFD', 'US GAAP']` (cardinality 2). B2 refuses linkage with `TAXONOMY_AMBIGUOUS`. The system never picks a winning authority by heuristic or first-writer precedence.
* **Case F (Repeated Ingestion of Identical Bytes):** Byte-identical authority files produce the same `document_id`. Re-ingestion is completely idempotent.
* **Case G (Same Family, Multiple Release Versions):** A family has multiple annual releases (`2025`, `2026`). Each release has its own targetNamespace URI (e.g. `/us-gaap/2025`, `/us-gaap/2026`), coexisting cleanly as distinct rows.

---

## 5. Taxonomy Version & Prefix Treatment

* **Taxonomy Version:** Preserved explicitly as declared in the SEC XML catalog `<Version>` element (e.g. `2026`, `2025q4`, `2024Q2`). It is never parsed from the URI using string heuristics.
* **Standard Prefix:** Preserved as evidence payload (`standard_prefix`), matching `<Prefix>` in `edgartaxonomies.xml` (e.g. `us-gaap`). It is strictly **excluded** from the identity preimage and join keys:
  * Filings choose arbitrary local XML prefixes (`xmlns:mygaap="URI"`).
  * Document facts store resolved namespace URIs (`filing_document_fact_occurrences.taxonomy`).
  * B2 matches resolved URI to `authority_taxonomy_namespaces.namespace_uri`. The prefix string is purely descriptive.

---

## 6. Custom Taxonomies Boundary

* Issuer extension namespaces (e.g. `http://apple.com/20260730`) are company-specific declarations absent from SEC Standard Taxonomies catalogs.
* They **never** enter `authority_taxonomy_namespaces`.
* Facts tagged under issuer extension URIs have zero rows in `authority_taxonomy_namespaces` and remain `TAXONOMY_UNPROVEN` in B2.
* When an issuer extension schema imports a standard schema (`<xs:import namespace="http://fasb.org/us-gaap/2026">`), standard facts tagged in that filing reside in the standard namespace URI and match via the authority table.

---

## 7. Migration 0022 Exact Boundary

Migration `0022_sec_authority_taxonomies.sql` is strictly bounded as follows:

### What Migration 0022 MUST Do:
1. Run in a single, explicit, atomic transaction (`BEGIN; ... COMMIT;`).
2. Additive DDL only:
   - `CREATE TABLE IF NOT EXISTS authority_taxonomy_namespaces`
   - Implicit unique index on primary key `authority_taxonomy_id`
   - Explicit unique constraint on `authority_taxonomy_identity`
   - Composite lookup index `authority_taxonomy_lookup` on `(provider, namespace_uri, taxonomy_family)`
   - Two append-only triggers (`..._no_update`, `..._no_delete`)
   - One closed-vocabulary trigger (`..._source_class_vocabulary`)
   - One consistency trigger (`..._extraction_consistent`)
3. Enforce FK integrity against `source_documents(document_id)`.
4. Update `PRAGMA user_version = 22`.

### What Migration 0022 MUST NOT Do:
- **Zero Network Calls:** No HTTP fetch of `edgartaxonomies.xml`.
- **Zero Parsing:** No XML parsing of taxonomy catalogs.
- **Zero Data Statements:** No `INSERT`, no `UPDATE`, no `DELETE`. Table starts completely empty.
- **Zero Backfill:** No historical data synthesized or backfilled.
- **Zero Changes to Existing Relations:** `observations`, `source_facts`, `filing_documents`, `filing_document_captures`, and `filing_document_fact_occurrences` are untouched.
- **Zero B2 Linkage Changes:** No changes to matching rules or activation logic.

---

## 8. Frozen Acceptance Criteria for Migration 0022

A future implementation of Migration 0022 must satisfy all twelve acceptance criteria:

1. **Clean Apply:** Migration executes cleanly on a populated archive; `PRAGMA user_version` advances to 22.
2. **Atomic Rollback:** Any execution error rolls back all DDL statements completely; schema version remains 21.
3. **Checksum Conformance:** SHA-256 of `0022_sec_authority_taxonomies.sql` matches the entry recorded in `schema_migrations`.
4. **Append-Only UPDATE Refusal:** Any `UPDATE` on `authority_taxonomy_namespaces` raises an ABORT exception.
5. **Append-Only DELETE Refusal:** Any `DELETE` on `authority_taxonomy_namespaces` raises an ABORT exception.
6. **Closed-Vocabulary Enforcement:** Inserting an `authority_source_class` outside the allowed three values raises an ABORT exception.
7. **Foreign Key Integrity:** Inserting an authority row referencing a non-existent `document_id` fails with a foreign key violation.
8. **Preimage Identity Uniqueness:** Inserting two rows with the same `authority_taxonomy_identity` violates the unique constraint.
9. **Multi-Source Assertion Retention:** Inserting two rows for the same `(provider, namespace_uri)` from different `document_id`s or with different families succeeds, preserving both source assertions.
10. **Deterministic Extraction Consistency:** A duplicate `authority_taxonomy_id` with conflicting columns triggers an extraction consistency ABORT.
11. **Zero Data Footprint:** Migration completes leaving `authority_taxonomy_namespaces` with exactly 0 rows.
12. **Zero Regression:** All existing test suites (115 B2 tests, 458 SEC provenance tests) pass without modification.

---

## 9. Formal Architectural Decision Summary

| Item | Question | Formal Decision |
|---|---|---|
| **A** | **Authority relation schema** | `authority_taxonomy_namespaces` with 14 columns, 1 PK, 1 unique constraint on `authority_taxonomy_identity`, 1 composite lookup index, and 4 triggers (§2). |
| **B** | **Identity preimage** | `{document_id, namespace_uri, provider, taxonomy_family, taxonomy_version}` (§4). |
| **C** | **Source document relationship** | Foreign key `document_id REFERENCES source_documents(document_id)` (§3). Eliminates first-writer-wins. |
| **D** | **Prefix treatment** | Standard prefix preserved as evidence payload column (`standard_prefix`); excluded from identity (§5). |
| **E** | **Version treatment** | Explicit `<Version>` from authority preserved verbatim; regex URI parsing forbidden (§5). |
| **F** | **Duplicate / conflict treatment** | Re-assertions from same document are idempotent no-ops; assertions from different documents coexist; conflicting mappings of the same URI result in `TAXONOMY_AMBIGUOUS` in B2; no arbitrary tie-breaks (§4). |
| **G** | **Custom taxonomy treatment** | Issuer extension namespaces strictly excluded; facts remain `TAXONOMY_UNPROVEN` (§6). |
| **H** | **Migration 0022 scope** | Additive DDL only; zero data statements, zero backfill, zero code changes (§7). |
| **I** | **Test requirements** | Twelve frozen acceptance criteria covering DDL, triggers, and FK integrity (§8). |
| **J** | **Unresolved questions** | SEC catalog fetch scheduler; historical XML catalog capture archive; multi-year catalog merge strategy. |
| **K** | **Is Migration 0022 authorized?** | **Not authorized.** This record freezes the schema design only. Implementation requires its own explicit authorization. |

---

# 15. Acquisition / Parser Design Freeze — Read-Only Phase (Post-0022)

**Status:** READ-ONLY DESIGN FREEZE. No ingestion, no parsing, no new rows, no B2 change, no 0022 modification, no Observation / dfid_ / sfid_ change. This section freezes decisions A–J required before any authority ingestion phase; it does not authorize that phase.

**Baseline:** `b38b1e0` (`feat: add taxonomy authority provenance schema`); `HEAD == origin/master`; working tree clean; `0022_authority_taxonomy_namespaces` applied (user_version=22); zero authority rows; `B2` unchanged; `Observation` untouched.

**Evidence reviewed (current repo, not invented):**
- `docs/ADR-XBRL-SOURCE-DOCUMENT-PROVENANCE.md` Amendment 5 (§3 source hierarchy, §6 B2 activation, §7 Option C), Amendment 6 (§2 DDL, §3 provenance, §4 identity/conflict, §7 boundary, §8 criteria).
- `archive/migrations/0022_authority_taxonomy_namespaces.sql` (frozen DDL, 4 triggers, FK to `source_documents`, no `UNIQUE(provider, namespace_uri)`).
- `archive/migrations/0001_initial.sql` (`source_documents` schema: `document_id` PK, `content_hash` UNIQUE, `uri`, `media_type`, `byte_size`, `fetched_at`, `first_seen_at`, `document_type`, `content`, `content_encoding`; idempotency by `content_hash` at `sqlite_archive.py:625-629`; `document_id` derived `"doc_" + sha256(content_hash)[:24]` at `:639`).
- `sec_provider.py` (fetch architecture: `urllib.request`, `DEFAULT_USER_AGENT`, `timeout=15`, `SAFE_REQUEST_INTERVAL_SECONDS = 1/4`, `ARCHIVES_HOST = "https://www.sec.gov"`, `ARCHIVES_API_HOST = "https://data.sec.gov"`; no generic network layer beyond provider instance; `fetch_log`, `requests_made` tracking).
- `sqlite_archive.py` (document recording inserts all fields above; no separate blob store; `compression`/`storage_path` optional; `provider` stored per document).
- `evidence_model.py` (`canonical_json`: `json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",",":"))`); `sha256(canonical_json(...).encode("utf-8")).hexdigest()[:32]` convention used by `sfid_`, `adm_`, `line_`, `document_fact_id` (`sec_provenance.py:557-560`).
- ADR Amendment 5 §3, §5 (custom/extension namespaces absent from catalog → `TAXONOMY_UNPROVEN`).
- `tests/test_authority_taxonomy_namespace_schema.py` (20 PASS; covers identity uniqueness, no hidden unique, conflict retention, vocabulary, append-only, extraction consistency, FK, schema-only).

No live `edgartaxonomies.xml` bytes are present in the repo; no cached snapshot; no historical archive evidence; no ingestion code exists. The freeze below is architectural (design of future acquisition/parser phases) and must not be interpreted as authorization of ingestion.

---

## 15.1 A. Exact Acquisition Route (Freeze)

**Live source:** `https://www.sec.gov/info/edgar/edgartaxonomies.xml` (SEC.gov direct; not `data.sec.gov`; root `<Erxl>` versioned, e.g. `version="78"`; see ADR §3 source table and Amendment 5 §3).

**Route layer:** Independent of `sec_provider.py`'s per-accession ingestion (`sec_ingest.py`). The catalog is a universal authority publication, not an issuer filing. It belongs in a **separate acquisition / archive-maintenance phase**, not in `SecEdgar`'s per-company fetch loop.

**Provider identity:** `provider = "SecEdgar"` (same provider identity used by `observations.provider` and `source_documents.provider`; consistent with `SecEdgar` as the SEC filing authority; ADR §3 Source 1).

**Fetch mechanism:** Existing `sec_provider.py` `urllib.request` mechanism (same `DEFAULT_USER_AGENT`, `timeout=15`, safe request interval, `ARCHIVES_HOST`) is sufficient; no new generic network layer required. The acquisition function may be a standalone CLI / scheduler call (e.g., `archive/authority_fetch.py` — not created in this phase) using the same `urllib.request` settings, or a direct `sqlite_archive.py` document-registration call with explicit `uri` and `provider`.

**Headers / User-Agent:** Must use the repository's existing `DEFAULT_USER_AGENT` (SEC requires identifying User-Agent for automated access; `sec_provider.py:86-89`). Must include `User-Agent` header; must not omit it.

**Timeout / error:** Same as provider default (`timeout=15`). Failure is not fatal to archive integrity (authority evidence is optional for B2; absence yields `TAXONOMY_UNPROVEN`, never a crash). Retries are out of scope for this freeze; if added later, they must be idempotent by `content_hash` (same bytes → same `document_id`).

**Byte preservation:** Exact uncompressed response bytes MUST be preserved as `source_documents.content` (or `content_encoding` if compressed, with `compression` noted); `content_hash` covers uncompressed bytes (`sqlite_archive.py:620-621`). The catalog is XML text; no binary encoding conversion permitted; `media_type` = `"application/xml"` or derived from `Content-Type`; `document_type` = `"SEC_TAXONOMY_CATALOG"` (descriptive; no vocabulary constraint on `source_documents.document_type`; consistent with loose typing of existing column).

**Retrieval timestamp:** `fetched_at` = retrieval time; `first_seen_at` = first retrieve time (idempotency: second retrieve with identical bytes returns existing `document_id` without updating `first_seen_at`; see `sqlite_archive.py:625-629`). `captured_at` on `authority_taxonomy_namespaces` = same retrieval semantics (transfer metadata, excluded from identity per Amendment 6 §2.1).

**Retry / idempotency:** `sqlite_archive.py` already enforces idempotency by `content_hash`. If `edgartaxonomies.xml` is re-fetched with identical bytes → same `content_hash` → same `document_id`; no new authority rows created (parser must handle insert-idempotency via `INSERT OR IGNORE` / identity-check trigger). If bytes change (new SEC release, new root `version`) → new `content_hash` → new `document_id`; parser produces new authority assertions; old assertions retained (append-only; no UPDATE/DELETE per 0022 triggers).

**Network access rule:** The acquisition phase is the ONLY phase permitted network access. The parser (`parse_edgar_taxonomies_catalog`) is strictly offline (consumes captured bytes from `sqlite_archive.py.content_for` / `source_documents`). 0022 is schema-only (no network); this freeze does not authorize any change to that boundary.

---

## 15.2 B. Exact Source Document Semantics (Freeze)

**Table:** `source_documents` (`0001_initial.sql`; unchanged by 0022).

**Identity of authority catalog document:** `document_id = "doc_" + sha256(content_hash)[:24]` where `content_hash = sha256(uncompressed response bytes).hexdigest()`. No accession, no filename, no ordinal. The catalog is the document; its bytes are the provenance.

**Required fields (all from `sqlite_archive.py` insertion):** `document_id`, `content_hash`, `uri = "https://www.sec.gov/info/edgar/edgartaxonomies.xml"`, `canonical_uri = uri`, `http_status`, `media_type`, `byte_size = len(bytes)`, `fetched_at`, `first_seen_at`, `document_type = "SEC_TAXONOMY_CATALOG"`, `provider = "SecEdgar"`, `content = bytes` (or NULL if external storage used), `content_encoding = None` (XML is text; no encoding transformation). `compression`, `storage_path` optional.

**No second store:** `source_documents` IS the authority document store. `authority_taxonomy_namespaces` refers to it via `document_id` FK (`0022` line 1529 + 1546). No `authority_document_id` separate table; Amendment 5 §7 Option C adopted; no redundant relation.

**Document type value:** `SEC_TAXONOMY_CATALOG` is sufficient and consistent. `source_documents.document_type` is a loose descriptive text column with no vocabulary trigger or CHECK; existing usage is descriptive (not enforced by schema). No vocabulary change needed; no alteration to `0001`.

---

## 15.3 C. Exact Parser Contract (Freeze)

**Function signature (design, not implemented):**
```python
def parse_edgar_taxonomies_catalog(payload: bytes) -> Iterable[Dict[str, str]]:
    """Consume uncompressed XML bytes of edgartaxonomies.xml.
    Return authority assertions with fields matching 0022 columns.
    Preserve source values verbatim; never infer from URI syntax."""
```

**Input:** Raw uncompressed `bytes` from captured `source_documents.content` (or re-read from `sqlite_archive.py.content_for` / storage path). Must not open network; must not normalize XML (preserve whitespace/encoding of captured bytes for hash consistency; parsing may use `xml.etree.ElementTree` or `lxml` over the bytes, but output must reflect source, not reconstructed XML).

**Output fields per assertion (direct mapping to `0022` columns; identity fields mandatory, evidence fields optional but preserved when present):**

| Output key | 0022 column | Source element / attribute (per frozen ADR §3, §5, Amendment 6 §2.1) | Inference rule |
|---|---|---|---|
| `provider` | `provider` | Fixed `"SecEdgar"` (authority source identity, not from XML) | Fixed; never inferred from URI |
| `taxonomy_family` | `taxonomy_family` | `<Family>` text / attr (e.g., `US GAAP`, `IFRS`, `FFD`, `DEI`, `ECD`, `CYD`) | Verbatim from XML; never derived from namespace content |
| `taxonomy_version` | `taxonomy_version` | `<Version>` text / attr (e.g., `2026`, `2025q4`, `2024Q2`) | Verbatim; never parsed from URI regex |
| `namespace_uri` | `namespace_uri` | `<Namespace>` or `namespace` attribute / text (absolute URI, e.g., `http://fasb.org/us-gaap/2026`) | Verbatim; must be absolute; never inferred |
| `standard_prefix` | `standard_prefix` | `<Prefix>` text / attr (e.g., `us-gaap`, `ffd`) | Evidence payload; excluded from identity |
| `file_type_name` | `file_type_name` | `<FileTypeName>` text / attr (e.g., `Schema`, `Entry Point`) | Evidence payload |
| `schema_href` | `schema_href` | `<Href>` text / attr (URL to `.xsd`) | Evidence payload |
| `authority_source` | `authority_source` | `"https://www.sec.gov/info/edgar/edgartaxonomies.xml"` (URI of captured document) | Fixed to source document URI |
| `authority_source_class` | `authority_source_class` | `"MACHINE_READABLE_CATALOG"` (closed vocabulary, §6) | Fixed for this route; not derived |
| `authority_source_version` | `authority_source_version` | Root `<Erxl version="...">` value (e.g., `"78"`) | Catalog release version; separate from taxonomy version |

**Excluded from parser output / identity:** `document_id` (handled by archive layer via `content_hash` → `doc_...`), `authority_taxonomy_id` (derived from identity), `authority_taxonomy_identity` (derived from identity), `captured_at` (archive layer), `standard_prefix` (not identity; preserved only as evidence).

**Structural rules (from ADR §4, §5, Amendment 6 §2.2, live catalog audit):**
- Root: `<Erxl version="...">`.
- Records: nested `<Loc>` (or equivalent catalog record) containing `<Family>`, `<Version>`, `<Namespace>`, `<Prefix>`, `<FileTypeName>`, `<Href>`.
- Duplicate `<Loc>` elements inside one catalog with identical family/version/namespace/prefix/filetype/href → identical identity → idempotent via insert logic (PK uniqueness, `INSERT OR IGNORE` or identity-check trigger).
- Same namespace URI under different families → separate assertions (no hidden unique; confirmed by Amendment 6 §2.2 empirical audit of `http://www.xbrl.org/2009/role/negated` under 5 families; `http://xbrl.org/2020/extensible-enumerations-2.0` under `US GAAP` + `IFRS`).
- One family/version can contain multiple namespace URIs (e.g., `us-gaap` primary + `us-gaap-ebp` benefit plans); each URI yields distinct `authority_taxonomy_id`.
- Same family/version/namespace inside same catalog repeated verbatim → one assertion (idempotent); parser must not invent duplicates from structural repetition.
- No precedence, no ranking, no current/superseded flags (0022 explicitly excludes; Amendment 6 §2.1, §10).

**Parser must NOT:** infer `taxonomy_version` from `namespace_uri` (e.g., `/2026`); infer `taxonomy_family` from `namespace_uri`; infer `standard_prefix` from file content; derive `authority_source_version` from taxonomy version; normalize `namespace_uri` (e.g., resolve relative); filter by file_type; exclude `TECHNICAL_SCHEMA` entries (if any); produce `authority_taxonomy_identity` differently from `canonical_json(preimage)`.

---

## 15.4 D. Exact Duplicate / Idempotency Behavior (Freeze)

Based on `0022` triggers, PK, unique identity, and `sqlite_archive.py` idempotency:

**A. Same `<Loc>` repeated inside one catalog:** Same all fields → same `authority_taxonomy_identity` → same PK (`authority_taxonomy_id`) → `INSERT` fails PK; `INSERT OR IGNORE` → count unchanged. Parser should emit identical dict; archive insert logic handles idempotency.

**B. Same assertion encountered twice in parser output (e.g., structural duplication):** Same behavior as A. No second row.

**C. Catalog re-fetched with identical bytes:** `content_hash` same → `document_id` same (`sqlite_archive.py:625-629`) → parser receives same bytes → same assertions → insert idempotent (no new rows, no UPDATE). `first_seen_at` unchanged.

**D. Catalog re-fetched with changed bytes (new SEC release, new root `version`):** New `content_hash` → new `document_id` → parser produces assertions with same identity fields but different `document_id` in preimage → new `authority_taxonomy_id` (because preimage includes `document_id`) → new rows inserted; old rows retained (append-only; 0022 `BEFORE UPDATE/DELETE` aborts any attempt to modify). B2 will see both sources; if families agree, no ambiguity; if families differ, `TAXONOMY_AMBIGUOUS`. No first-writer-wins.

**E. Same assertion appears in another source document:** Different `document_id` → different preimage → different `authority_taxonomy_id` → distinct rows retained (multi-source preservation; eliminates first-writer-wins; supports corroboration per ADR §3, §4 Cases B/E).

---

## 15.5 E. Exact Release / Version Semantics (Freeze)

**Two independent version axes:**
- `authority_source_version` = root `<Erxl version="X">` (catalog release). Example: `"78"`. This is transfer/provenance metadata (the document's version), not taxonomy metadata. Preserved as evidence payload (`0022:authority_source_version`), excluded from identity.
- `taxonomy_version` = per-entry `<Version>` (taxonomy release). Example: `"2026"`, `"2025q4"`. This is part of identity (`0022` identity fields). Must be preserved verbatim; must not be derived from URI.

**No merging:** Catalog root version must not substitute for taxonomy version. If `version="78"` but taxonomy entry says `<Version>2026</Version>`, `taxonomy_version = "2026"`; `authority_source_version = "78"`.

**No regression on historical versions:** Current catalog proves current releases; historical versions (e.g., `2025`) present in current catalog if SEC includes them; if not, they are not provable from current bytes. No inference permitted.

---

## 15.6 F. Historical Catalog Coverage Rule (Freeze)

**Evidence in repo:** None. No `edgartaxonomies.xml` snapshot; no `archive/` historical catalog directory; no `data/` taxonomy archive; `data/st-eva.sqlite` does not exist (`docs/ST-EVA-DATA-LAYER-AUDIT.md`).

**Honest rule:** One captured current catalog is NOT sufficient to prove mappings for older filings (e.g., 2013 filings using older taxonomy releases). B2 must evaluate authority evidence only from captured `source_documents` + parsed `authority_taxonomy_namespaces` rows.

**B2 consequence:** If a filing uses namespace `U` with taxonomy family/version that is not present in any captured authority document → no authority rows match → condition 3 of B2 activation (§12 / ADR §6) fails → `TAXONOMY_UNPROVEN` (zero `observation_filing_document_facts` rows). Never infer historical mapping from current `version="78"` catalog.

**Future acquisition (unresolved, not authorized):** Historical catalog snapshots require separate acquisition schedule (e.g., SEC annual releases archived by date); multi-year merge policy requires deciding whether to retain all versions or only the latest per release; not within this freeze.

---

## 15.7 G. Custom Taxonomy / Extension Rule (Freeze)

**Custom issuer namespaces** (e.g., `http://apple.com/20260730`) are absent from SEC catalog (`edgartaxonomies.xml`). Parser must NOT invent authority assertions for them. `authority_taxonomy_namespaces` must have zero rows for such URIs.

**Standard namespace imported by extension:** If extension schema imports `http://fasb.org/us-gaap/2026`, facts with that URI are standard; authority match applies. If extension defines its own targetNamespace, it is custom; `TAXONOMY_UNPROVEN`.

**Custom prefix:** `xmlns:mygaap="http://fasb.org/us-gaap/2026"` → resolved URI is standard; prefix `mygaap` is evidence payload (`standard_prefix`) excluded from identity; parser must resolve URI, not preserve prefix as identity.

---

## 15.8 H. Exact B2 Activation Evidence (Freeze)

Per ADR Amendment 5 §6 / Amendment 6 §12 / frozen `0022` design; B2 unchanged; implementation deferred.

For `taxonomy_equivalent(obs, occ)` to evaluate TRUE:
1. `obs.provider == occ.provider` (`SecEdgar`).
2. `_local_name(obs.concept) == occ.tag`.
3. **Authority Recognition:** An assertion exists in `authority_taxonomy_namespaces` for `(provider, taxonomy_family=obs.taxonomy, taxonomy_version=..., namespace_uri=occ.taxonomy)` derived from captured `source_documents` document (`document_id`). Must be proven from captured evidence, not inferred.
4. **Filing Concordance:** `occ.accession == obs.accession`; `occ.asset_id == obs.asset_id`; `occ.filename / document_id` links to `filing_document_captures` (cardinality must be resolvable to exactly 1 via `observation_filing_documents` / `filing_document_captures`; see Invariant 19 and Amendment 1 §§2–3 for cardinality rules).

Only when all four hold → `TAXONOMY_EQUIVALENT` (and therefore `observation_filing_document_facts` / `observation_filing_documents` link permitted). Otherwise: `TAXONOMY_UNPROVEN`.

**UNAVAILABLE (not errors):**
- Issuer extension namespace (`TAXONOMY_UNPROVEN`).
- Namespace not in any captured authority document (`TAXONOMY_UNPROVEN`).
- Non-SEC source (`TAXONOMY_UNPROVEN`).
- Candidate filing document cardinality >= 2 (`DOCUMENTS_AMBIGUOUS`; zero `observation_filing_documents`; does NOT become `TAXONOMY_EQUIVALENT` just because authority evidence exists; see Amendment 6 §9 / Amendment 1 §3 / Invariant 19).
- Unmodelled taxonomy lacking URI mapping (`TAXONOMY_UNPROVEN`).

---

## 15.9 I. Exact UNAVAILABLE Cases (Freeze, for future B2 / parser design)

From frozen decisions (Amendment 5 §5–§7, Amendment 6 §6, 0022 DDL, Invariant 19, ADR §D):

| Case | Evidence | B2 / parser result |
|---|---|---|
| Issuer extension namespace (e.g., `http://apple.com/...`) | Absent from `edgartaxonomies.xml` | `TAXONOMY_UNPROVEN`; zero authority rows |
| Standard namespace unlisted in captured catalog (e.g., newer release not yet fetched) | Zero matching `authority_taxonomy_namespaces` rows for `(provider, family, version, URI)` | `TAXONOMY_UNPROVEN` |
| Filing with 2+ candidate documents (inline XBRL dual-document; `DOCUMENTS_AMBIGUOUS`) | `filing_document_captures` cardinality >= 2; `observation_filing_documents` = 0 | `DOCUMENTS_AMBIGUOUS`; B2 linkage refused regardless of authority evidence |
| Custom prefix with standard URI | `namespace_uri` matches authority; prefix discarded | `TAXONOMY_EQUIVALENT` if other conditions hold |
| Custom concept under standard namespace (local tag matches but URI matches standard) | `occ.tag` match; `occ.taxonomy` standard URI; authority evidence present | `TAXONOMY_EQUIVALENT` (concept is standard family concept; local tag is occurrence tag) |
| Custom concept under custom namespace | `namespace_uri` not in authority; no authority evidence | `TAXONOMY_UNPROVEN` |

---

## 15.10 J. Implementation Split Recommendation (Freeze — Decision Reached)

**Split into two independent phases with independent failure/acceptance boundaries:**

1. **Phase A — Acquisition (network-dependent, external, retryable, independent of archive schema changes):** Fetch `https://www.sec.gov/info/edgar/edgartaxonomies.xml`; verify `Content-Type` / `byte_size`; compute `content_hash`; insert into `source_documents` via `sqlite_archive.py` (or direct `INSERT` if using external storage). If fetch fails, archive unchanged; no B2 impact; retry later. Acceptance: captured bytes + `document_id` + `content_hash` verified.

2. **Phase B — Parsing / Insertion (offline, deterministic, dependency on Phase A):** Read `source_documents.content_for(document_id)` (or storage); run `parse_edgar_taxonomies_catalog`; derive `authority_taxonomy_id` / `authority_taxonomy_identity`; insert into `authority_taxonomy_namespaces` via `INSERT OR IGNORE` (idempotent). If parser fails (bad XML, unexpected structure), Phase A bytes remain; parser can be fixed independently; no data corruption. Acceptance: exactly 14-column rows with verified identity/preimage; trigger tests pass; zero hidden constraints.

**Reasons for split (frozen):** Acquisition has external/network failure modes; parsing has internal/XML failure modes; 0022 DDL is already frozen and must not be altered by either; B2 evaluation depends on both being complete; separate phases allow independent testing (Phase A can be validated by `content_hash` + `document_type`; Phase B by identity + trigger conformance) without requiring full B2 activation.

**Not authorized by this freeze:** Phase A execution (no fetch); Phase B execution (no parser invocation); any B2 linkage; any test inserting real authority assertions (existing tests use synthetic preimages; no real XML parsed).

---

## 15.11 Unresolved Questions (Explicitly Preserved, Not Resolved)

From ADR Amendment 6 §7 / §8 / Amendment 5 / this audit. No silent assumption; no invented resolution.

1. **Authority acquisition job / CLI route:** No schedule defined; no `archive/authority_fetch.py`; no cron; no CLI argument. Freeze: design exists; execution deferred.
2. **Historical catalog availability:** No `edgartaxonomies.xml` snapshots in repo or `data/`. Freeze: current catalog only proves current releases; historical mappings require separate acquisition evidence; not assumed available.
3. **Multi-year catalog merge policy:** If multiple years' catalogs are captured (e.g., v78 + v79), whether to retain all or keep only latest per `(family, version)` is not decided. Freeze: append-only (`0022`) permits multi-source retention; merge logic is a future ingestion policy, not a schema decision.
4. **Issuer custom extensions:** Already frozen (§5, §11, §15.7): never enter `authority_taxonomy_namespaces`; always `TAXONOMY_UNPROVEN`. No unresolved question here — rule is fixed.

---

## 15.12 Formal Decision Summary (Freeze End)

| Item | Decision | Evidence |
|---|---|---|
| **A. Acquisition route** | Independent phase; `https://www.sec.gov/info/edgar/edgartaxonomies.xml`; `SecEdgar`; existing `urllib`/user-agent/timeout mechanism sufficient; no new generic layer | ADR §3; `sec_provider.py:76-84`; `sqlite_archive.py:643` |
| **B. Source document semantics** | `source_documents` only; `document_type="SEC_TAXONOMY_CATALOG"`; `provider="SecEdgar"`; idempotency by `content_hash`; no second store | `0001_initial.sql`; `sqlite_archive.py:625-639`; 0022 FK |
| **C. Parser contract** | Offline; consumes uncompressed bytes; preserves `<Family>/<Version>/<Namespace>/<Prefix>/<FileTypeName>/<Href>` verbatim; identity from `{document_id, namespace_uri, provider, taxonomy_family, taxonomy_version}`; no URI inference | Amendment 5 §3; Amendment 6 §2.1–§4; `evidence_model.py` convention |
| **D. Duplicate behavior** | Same doc same identity = idempotent; changed bytes = new `document_id`; different doc = separate rows; no update/delete | 0022 triggers (no_update/no_delete); `sqlite_archive.py:625-629`; Amendment 6 §4 |
| **E. Release/version** | `authority_source_version` = root `<Erxl>` version; `taxonomy_version` = entry `<Version>`; not merged; preserved verbatim | Amendment 6 §2.1, §5; ADR §3 Source 1 |
| **F. Historical coverage** | Current catalog insufficient for older filings; no historical archive in repo; `TAXONOMY_UNPROVEN` when missing; never infer | `ST-EVA-DATA-LAYER-AUDIT.md`; repo inspection (zero cached files); ADR §6 |
| **G. Custom taxonomy** | Absent from catalog → zero authority rows; `TAXONOMY_UNPROVEN`; standard URI imported by extension → standard match | Amendment 5 §5; Amendment 6 §6 |
| **H. B2 precondition** | Requires (1) `source_documents` captured, (2) parsed `authority_taxonomy_namespaces` rows with identity match, (3) exact `occ.taxonomy` match to family/version, (4) filing concordance, (5) cardinality == 1; B2 unchanged | Amendment 5 §6; Amendment 6 §12; 0022 schema (no B2 changes) |
| **I. UNAVAILABLE** | Extension NS, unlisted NS after fetch, cardinality >= 2 (Document Ambiguous), unmodelled taxonomy, non-SEC source | Amendment 1 §3 (Invariant 19); Amendment 6 §6; 0022 design |
| **J. Split** | Acquisition (network, independent) + Parsing (offline, independent); both verified separately; B2 activates only when both complete | This freeze §15.10; architecture convention (separate failure modes) |

---

*Design freeze complete. No ingestion executed. No 0022 edit. No Observation / B2 / dfid_ / sfid_ change. No new specification file created (update to existing ADR only). Freeze preserved for future authorization.

---

# Amendment 7 — Claim-Specific Evidence Sufficiency (C4I)

**Status:** FROZEN — methodology / ADR only. No implementation authorization.
**Date:** 2026-10-09
**Baseline:** `d067444`. C4F `d067444`, C4C `879cacb`, and C4B `a7effc6` are sealed.
**Refines:** Amendments 4–6 and their taxonomy / authority evidence boundaries.
**Current C4G status:** `NOT SEALABLE`; its uncommitted candidate changes are outside this amendment and must remain untouched until separately authorized.

This amendment defines how ST-EVA judges whether evidence is sufficient for a
particular claim. It does not rank sources, define source precedence, combine
grades, or select a winner. It records current sufficiency without deleting or
rewriting the historical design decisions above. Where an earlier amendment
describes a proposed bridge or activation design, that description is not itself
evidence that the current cross-source claim has been proven.

## 1. Evidence-Form Labels

The labels below describe the form of support for one claim. They are not an
ordinal scale, source ranking, authority hierarchy, global score, or input to a
winner-selection rule. No grade may be summed with another grade or used to
prefer one source over another.

| Label | Evidence form | Meaning |
|---|---|---|
| `E0` | Unavailable | No admissible evidence is currently available for this claim. This does not establish that the claim is false. |
| `E1` | Single-source direct observation | One source directly states or exhibits the proposition, within that source's scope. |
| `E2` | Same-source structured relation | One source contains a structured row, identity, or scope relation connecting the relevant fields. |
| `E3` | Independent corroboration | Multiple authoritative sources with independent provenance separately support the same explicitly stated claim. Separate support for two component claims does not prove a relation between them. |
| `E4` | Explicit cross-source contract | An authoritative contract or schema explicitly defines the relationship between the named source fields or vocabularies. |

Sufficiency is claim-specific. An `E1` direct statement may be sufficient for a
single-source field-definition claim and insufficient for a cross-source
equivalence claim. In particular, `E3` support for each side of a proposed
relationship is not a substitute for `E4` evidence of that relationship.

The matrix statuses are also claim outcomes, not grades:

| Status | Meaning |
|---|---|
| `SUPPORTED` | The minimum admissible evidence for the stated scope is present. |
| `CONDITIONAL` | The claim is supportable only when the required captured source bytes and scope evidence are available. |
| `NOT PROVEN` | Some component claims may be supported, but a required relation or bridge is not. |
| `UNAVAILABLE` | The source evidence needed to evaluate the claim is not present in the current evidence set. This does not mean the claim is false. |

## 2. Claim-Specific Evidence Sufficiency Matrix

The C1 and C2 current statuses reflect the C4G SEC-source audit: SEC material
describes the Company Concept API taxonomy token as a taxonomy identifier and
describes catalog namespace prefixes and their relationship to namespace URIs.
Those findings are limited to the individual fields and do not establish C3.

| Claim | Required Evidence | Current Evidence | Sufficiency Status | Allowed Use |
|---|---|---|---|---|
| **C1. Company Concept API `taxonomy` field semantics** | At least `E1`: SEC documentation or response semantics directly describing that API field. | The C4G source audit supports the narrow description “standard taxonomy identifier/token.” It does not define this field as the catalog `<Prefix>` vocabulary. | **SUPPORTED — narrow field semantics** | Describe the API field as SEC's taxonomy identifier/token. Do not infer a QName-prefix contract from this claim. |
| **C2. SEC taxonomy catalog `<Prefix>` semantics** | At least `E1` for field meaning; `E2` for a particular catalog row and its associated fields. | SEC taxonomy material describes standard namespace prefixes and their relationship to namespace URIs/releases. | **SUPPORTED — narrow field semantics** | Interpret `<Prefix>` within the catalog's own vocabulary. Do not equate it with the API field based only on spelling. |
| **C3. Company Concept `taxonomy=P` and catalog `<Prefix>=P` share one controlled vocabulary** | `E4`: an explicit authoritative contract connecting the Company Concept field to the catalog `<Prefix>` field/vocabulary. | C1 and C2 have separate support; no explicit cross-source contract has been established. Lexical equality is not that contract. | **NOT PROVEN** | Do not create or consume a cross-source prefix mapping. C1 plus C2 cannot be promoted to C3. |
| **C4. Filing-local namespace binding `P → U`** | `E1`: actual `xmlns:P="U"` in captured bytes. To claim a fact uses that binding, also establish `E2`: the declaration is in scope for that fact QName. | The XBRL parser constructs in-scope namespace bindings and resolves fact QNames. The current occurrence output stores the URI, not the original prefix/declaration; retained filing bytes can be re-parsed. | **CONDITIONAL** on captured bytes and scope reconstruction | State only that this filing document declares/uses `P → U` in the evidenced scope. This does not prove taxonomy authority or historical validity. |
| **C5. Authority catalog assertion `P + Family + Version + U`** | `E2`: the fields occur together in a particular captured official authority-document row, linked to that document's exact bytes and identity. | Migration `0022` defines a schema for authority assertions. The repository has only a synthetic catalog fixture for parser tests, not a production-captured catalog assertion. | **UNAVAILABLE** for a production assertion | Use schema and fixture to test parser/model behavior only. Never describe the synthetic fixture as production authority evidence. |
| **C6. Filing occurrence uses namespace URI `U`** | `E2`: source-backed QName resolution tied to the captured filing document and a locatable occurrence. | The parser resolves the QName to a namespace URI, and `filing_document_fact_occurrences` stores that URI with the source document and occurrence evidence. Availability depends on the corresponding captured bytes. | **CONDITIONAL** on captured, locatable occurrence evidence | State that the specific occurrence uses URI `U`. Do not infer that `U` is standard or belongs to a particular family. |
| **C7. Observation and filing occurrence taxonomy representations are equivalent** | An admissible bridge explicitly relating the Observation representation to the filing QName/URI representation (a general `E4` contract is one possible route), plus source-backed `E2` occurrence and exact fact-level correspondence. | C3 is not proven; filing-local `P → U` proves only the filing's binding. Accession/source-fact identity scopes an Observation to a filing but does not define the API taxonomy vocabulary. | **NOT PROVEN**; production result remains `TAXONOMY_UNPROVEN` | No taxonomy-equivalence claim and no exact Observation-to-occurrence link. |
| **C8. Filing occurrence's taxonomy family** | `E2`: a captured authority row relates the occurrence URI `U` to the stated Family/Version. Preserve all conflicting or multiple assertions; do not choose a family by preference. | No production-captured catalog assertion is present in the current evidence set; the schema and synthetic fixture are not such an assertion. | **UNAVAILABLE** for a production classification | If an exact authority row is later captured, report what that row asserts for `U`. This alone does not establish C7 or historical validity. |
| **C9. Filing-date historical authority validity** | A historical authority source applicable to the filing date, plus explicit evidence of the release's effective/applicable period at that date. | No historical catalog snapshot or filing-date authority applicability evidence is available. A current catalog describes its own captured state, not an earlier filing-date state. | **UNAVAILABLE / UNPROVEN** | Do not infer filing-date validity from a current catalog, a filing-local declaration, a namespace URI, or an accession. |
| **C10. Exact source document assertion** | Exact Observation-to-occurrence correspondence, filing concordance, all applicable fact/context predicates, and a complete candidate set with cardinality exactly one at `(asset_id, accession, filename)`. | C7 is not proven for the production prefix/URI representations. The current C4G candidate also has an untyped direct-equality bypass and can discard taxonomy-refused candidates before exact-source cardinality. | **UNAVAILABLE** for the current C4G production case | Do not write `observation_filing_documents` unless the exact assertion and full cardinality precondition are proven. This relation remains `EXACT_SOURCE_DOCUMENT_ASSERTION`, never a candidate set. |

For C5 and C8, schema existence, successful parser tests, and a synthetic fixture
are not production authority assertions. A production assertion requires the
actual captured authority document bytes and a parsed row whose provenance points
to those bytes.

## 3. Non-Transitive Equivalence Boundaries

The following are three different claims and are not interchangeable:

1. **Lexical equality:** the strings are identical, for example `"us-gaap" == "us-gaap"`.
2. **Vocabulary equivalence:** two source fields use the same controlled vocabulary.
3. **Semantic taxonomy equivalence:** a particular Observation and a particular filing fact belong to the same taxonomy representation.

The implications are frozen as:

```text
1 does not prove 2
2 does not prove 3
```

C3 requires evidence of the cross-source vocabulary relationship. C7 additionally
requires evidence that the Observation corresponds to the particular filing
occurrence. A matching spelling alone cannot discharge either requirement.

## 4. Authority, Filing Use, and Historical Validity

These are independent evidence layers with separate claims and identity grains:

| Layer | Claim | What it establishes | What it does not establish |
|---|---|---|---|
| **Authority assertion** | Authority document `D` asserts `P / Family / Version / U`. | The exact statement contained in that captured authority document. | That a particular filing used `U`, or that the assertion was valid on a historical filing date. |
| **Filing-local assertion** | Filing document `D'` binds `P → U` in scope `S`, and a fact QName uses that binding. | The namespace binding and URI used by that occurrence in those captured filing bytes. | That `U` is an SEC-authorized standard taxonomy or that the binding was historically valid as an authority matter. |
| **Historical authority validity** | The authority relationship applied at filing date `T`. | Only what a date-applicable historical authority source and effective-period evidence establish. | It cannot be inferred merely from a current catalog row or from filing-local namespace syntax. |

Neither an authority assertion nor a filing-local assertion proves
`HISTORICAL_AUTHORITY_VALIDITY`. A current SEC catalog is not, by itself, proof of
filing-date validity. Historical catalog acquisition and date-applicability
analysis remain a separate future evidence phase.

C7 representation equivalence and C9 historical validity are separate claims.
The absence of C9 evidence does not, by itself, disprove a representation bridge;
however, C7 still requires its own admissible Observation-to-occurrence bridge and
is currently `NOT PROVEN` for the reason stated in the matrix.

## 5. Exact-Source Candidate Cardinality Invariant

The following invariant applies independently of taxonomy sufficiency:

> **`TAXONOMY_REFUSAL_MUST_NOT_SHRINK_EXACT_SOURCE_CANDIDATES`**

An occurrence that satisfies the applicable pre-taxonomy candidate predicates but
has `TAXONOMY_UNPROVEN` or `TAXONOMY_AMBIGUOUS` must not be silently removed in a
way that upgrades the remaining source set from cardinality 2 to cardinality 1.
If an unresolved or ambiguous competing candidate could change the exact-source
result, the exact-source assertion remains unresolved; taxonomy refusal is not
evidence that the candidate does not exist.

The candidate-document identity grain remains exactly:

```text
(asset_id, accession, filename)
```

Authority-row count, capture-row count, and `document_id` count must not replace
that grain. Candidate state is not written to `observation_filing_documents`:
that relation remains exclusively `EXACT_SOURCE_DOCUMENT_ASSERTION`, with zero
rows when unresolved and a row only when the exact assertion's full preconditions
are met. No confidence score or tie-break is introduced.

## 6. Direct Equality Is Not a Production Bridge

In the production representations described in Amendment 4, an Observation's
`taxonomy` is a prefix/token while a filing occurrence's `taxonomy` is a resolved
namespace URI. Therefore:

```text
occurrence.taxonomy == observation.taxonomy
```

proves at most lexical equality of the stored strings. It does not prove
vocabulary equivalence or semantic taxonomy equivalence. An untyped direct-equality
branch that returns `MATCHED` before authority/bridge evidence is checked is a B2
defect, not a permitted shortcut. The production result must remain
`TAXONOMY_UNPROVEN` until the applicable claim-specific evidence is sufficient.

This clarification does not prohibit equality between values whose identical
representation semantics have independently been established. It prohibits using
raw string equality alone to bypass the production prefix-to-URI evidence gate.

## 7. Clarification of Existing Source-Hierarchy Wording

Amendment 5 §3 and its decision summary use “hierarchy” and “authority level”
wording to describe SEC source roles. That historical text is retained; this
amendment does not delete or rewrite it. For evidence sufficiency and conflict
handling, those labels must not be read as global source precedence.

In particular, neither an evidence grade nor an `authority_source_class` such as
`REGULATORY_MANUAL` or `MACHINE_READABLE_CATALOG` is a global winner key. A rule
such as `REGULATORY_MANUAL > MACHINE_READABLE_CATALOG` must not automatically select
one assertion when sources differ. Evidence conflicts require a claim-specific
reconciliation rule. Until such a rule is established and its claim is met,
retain the source assertions and report the conflict as unresolved/ambiguous;
do not silently discard or rank them.

This clarification is not a new source hierarchy. It separates source role and
legal function from the form and sufficiency of evidence for a particular claim.

## 8. C4G Status and Re-Authorization Boundary

C4G taxonomy correction is **PAUSED**, not permanently prohibited. C7 remains
`NOT PROVEN`; therefore production B2 must continue to return
`TAXONOMY_UNPROVEN` for the unresolved prefix/URI representation bridge, with no
`observation_filing_document_facts` or `observation_filing_documents` assertion
based on that bridge.

For avoidance of doubt, Amendment 5 §6 and Amendment 6 §15.12 H record earlier
design predicates; they are not evidence that the source-field relationship
needed to evaluate those predicates has been established. In particular, neither
comparing `Observation.taxonomy` with an authority `taxonomy_family` nor a
proposed comparison with catalog `standard_prefix` proves C3. Such a predicate
cannot activate production B2 until its required claim-specific evidence is met.

Re-authorization requires either admissible evidence sufficient for the taxonomy
bridge claim, or a separately frozen weaker claim that is not represented as
taxonomy equivalence. For example, captured evidence may support the narrower
claim `FILING_LOCAL_NAMESPACE_BINDING_OBSERVED`. If the only cross-source fact is
that an Observation token and a filing prefix have the same spelling, the maximum
claim is `OBSERVATION_PREFIX_TOKEN_MATCH_ONLY`; C7 remains `TAXONOMY_UNPROVEN` and
that token observation does not authorize a B2 fact/document link.

## 9. Architecture and Implementation Consequences

This methodology freeze adds no migration, database field, evidence-grade table,
mapping table, or identity. The ESM exists only in the ADR/methodology layer.
Future code that evaluates one of these claims must cite its frozen claim contract
and use the required evidence form; it must not invent or tune an implicit
threshold, global score, source precedence, or winner rule.

No C4G candidate code or tests are authorized or changed by this amendment. The
uncommitted C4G candidate remains outside this freeze. Any direct-equality or
candidate-cardinality correction requires a separately authorized implementation
phase and must preserve this matrix and the existing exact-source relation
semantics.

**Freeze summary:** C3 = `NOT PROVEN`; C7 = `NOT PROVEN`; C9 = `UNAVAILABLE /
UNPROVEN`; C10 = `UNAVAILABLE` for the current production C4G case; C4/C6 are
conditional on captured, scoped, locatable filing evidence; C5/C8 require a
production-captured authority assertion and are not satisfied by schema or
synthetic fixtures. No source ranking, source precedence, or global evidence score
is created.


---
---

# Amendment 8 — Official-Source Taxonomy Bridge Research (C3 / C7)

**Status:** FROZEN — official research record / methodology only. No implementation authorization.
**Date:** 2026-10-09
**Baseline:** `9b3a8a8` (C4G implementation archived and pushed to `origin/master`).
**Scope:** Investigation of official SEC and EDGAR publications regarding cross-source taxonomy equivalence bridging Claims C3, C7, C9, and C10.
**Outcome:** `BRIDGE_NOT_FOUND` across all investigated official sources.
**Claim Statuses (Unchanged):**
- **C3:** `NOT PROVEN`
- **C7:** `NOT PROVEN`
- **C9:** `UNAVAILABLE / UNPROVEN`
- **C10:** `UNAVAILABLE`
**C4G Status:** C4G implementation is archived at baseline `9b3a8a8`; production continues to reject unproven taxonomy equivalence (`evaluate_taxonomy_equivalence` returns `False, TAXONOMY_UNPROVEN`). No authorization for C4G reimplementation.
**Preservation:** Amendment 7 and its historical context and Evidence Sufficiency Matrix (ESM) remain intact without modification.

---

## 1. Context, Executive Summary & Core Finding

Following the freeze of Amendment 7 and the formal archival of the C4G candidate implementation at baseline `9b3a8a8`, an official-source research investigation was conducted to determine whether an authoritative cross-source bridge exists between the SEC Company Concept API taxonomy representation and the EDGAR taxonomy catalog prefix or filing-local namespace URIs.

### 1.1 Core Finding: `BRIDGE_NOT_FOUND`

The empirical result across all audited official sources is **`BRIDGE_NOT_FOUND`**:
- No official SEC specification, regulatory manual, XML catalog schema, or developer API documentation establishes an explicit, authoritative relationship (`E4`) bridging Company Concept API taxonomy tokens to EDGAR taxonomy catalog `<Prefix>` elements or filing-local namespace URIs.
- In accordance with the Evidence Sufficiency Matrix established in Amendment 7 §2:
  - **C3** remains **`NOT PROVEN`** (no cross-source contract connecting API token to catalog `<Prefix>`).
  - **C7** remains **`NOT PROVEN`** (Observation representation and filing occurrence representation equivalence unproven).
  - **C9** remains **`UNAVAILABLE / UNPROVEN`** (historical authority validity not established by current catalog snapshots).
  - **C10** remains **`UNAVAILABLE`** for the current production architecture.
- Production continues to refuse unproven taxonomy equivalence: `sec_xbrl_facts.py:evaluate_taxonomy_equivalence` returns `(False, TAXONOMY_UNPROVEN)`, preventing unverified `observation_filing_document_facts` and `observation_filing_documents` rows from being created.

### 1.2 Meaning and Scope of `BRIDGE_NOT_FOUND`

The finding `BRIDGE_NOT_FOUND` is strictly scoped:
1. **Scope of the finding:** Within the exhaustive scope of official SEC and EDGAR publications examined, no evidence was found to support C3 or C7.
2. **Not a universal impossibility claim:** Stating `BRIDGE_NOT_FOUND` records the absence of bridge evidence within the investigated official sources. It **does not claim that no lawful bridge could ever exist in the world**, nor does it assert that SEC systems are incapable of being bridged under future, newly published, or uninvestigated authority sources.
3. **Preservation of Amendment 7:** Amendment 7's text, historical context, and claim statuses are preserved verbatim. This amendment appends empirical audit findings to the record without modifying or diluting any prior decision.

---

## 2. Strict Separation of Four Semantic Entities

To prevent conflation across distinct architectural layers, four separate semantic entities are strictly distinguished. Evidence supporting one entity must never be promoted to prove another, and single-source semantics from separate sources must not be merged into a cross-source contract:

1. **Company Concept API Taxonomy Token Semantics (`obs.taxonomy`):**
   - The token appearing in the URL path of the SEC Company Concept API (`/api/xbrl/companyconcept/CIK{cik}/{taxonomy}/{tag}.json`) and echoed in the JSON payload `taxonomy` field.
   - Its verified official role is an API-level routing and aggregation identifier (e.g., `"us-gaap"`, `"dei"`, `"invest"`, `"srt"`, `"ifrs-full"`).
   - It is an endpoint-scoped parameter, not a QName prefix and not an XML namespace URI.

2. **Catalog `<Prefix>` Semantics and its Family, Version, and Namespace Relations:**
   - The `<Prefix>` element defined in schema `erxl.xsd` and populated in `<Loc>` entries within `edgartaxonomies.xml`.
   - Its verified official role is a descriptive or suggested prefix associated with a specific schema entry point `<Href>`, `<Namespace>` URI, `<Family>`, and `<Version>`.
   - It belongs strictly to the catalog's internal XML vocabulary.

3. **Filing-Local Namespace Prefix → Namespace URI Binding (`xmlns:prefix="URI"`):**
   - The XML namespace declaration bound within captured filing instance document bytes or DTS (e.g., `xmlns:us-gaap="http://fasb.org/us-gaap/2026"` or custom extension prefixes).
   - Its scope is strictly local to the filing document's XML scope. The August 2026 EDGAR XBRL Guide keeps two distinct filing-side tables separate: §1.2.2 ("Standard Taxonomies", Tables 6-5/6-6) lists standard taxonomy *entry-point abbreviations* (e.g., `us-gaap`, `dei`, `srt`, `ifrs2`, `ebp`, `cef`) — short names for taxonomy entry-point URLs such as `https://xbrl.sec.gov/us-gaap/2026/us-gaap-2026.xsd`, **not** XML namespace prefixes; §8.2 ("Standard Namespace Prefixes") is a separately tabled binding of XBRL-infrastructure XML namespace prefixes (e.g., `ix`, `i`, `iso4217`, `xlink`, `xhtml`, `xs`, `xml`, `xbrli`, `xl`, `ref`, `dtr`, `dtr-types`, `ixt`, `xbrldt`, `xbrldi`, `enum`, `enum2`, `ixt-sec`) to namespace URIs. The Company Concept API token `invest` appears in neither table — it belongs to entity 1 (API taxonomy token), not to a Guide prefix table. Neither §1.2.2 nor §8.2 is a cross-source contract bridging Company Concept API tokens to catalog `<Prefix>` or to filing-local declarations; filers' local prefix declarations remain syntactic bindings within the document scope.
   - Crucially, this limited submission-side designated prefix convention cannot be promoted into a cross-source contract bridging the SEC Company Concept API taxonomy tokens to filing occurrence taxonomy equivalence (does not prove C3 or C7).

4. **Observation → Filing Occurrence Taxonomy Equivalence:**
   - The semantic identity assertion that an Observation extracted from the Company Concept API and a document-level fact occurrence extracted from filing bytes represent the exact same concept under the exact same accounting taxonomy.
   - Requires proving both cross-source vocabulary equivalence and exact fact-level correspondence.

```text
+-----------------------------------------------------------------------------------------+
| STRICT NON-PROMOTION BOUNDARIES                                                         |
|                                                                                         |
|  [1. API Token Semantics]   <--x-- (NO PROMOTION) --x-->   [2. Catalog <Prefix>]        |
|            |                                                       |                    |
|            x (no cross-source promotion)                           x (no cross-source)  |
|            v                                                       v                    |
|  [3. Filing-Local Binding]  <--x-- (NO PROMOTION) --x-->   [4. Taxonomy Equivalence]   |
|                                                                                         |
| Rule: Evidence for (1), (2), or (3) DOES NOT constitute proof of (4).                   |
| Rule: Evidence for (1) + Evidence for (2) CANNOT be merged into an E4 contract for (3).|
+-----------------------------------------------------------------------------------------+
```

---

## 3. Official-Source Investigation and Audit Evidence

Seven official regulatory, technical, and data delivery sources published by the SEC were audited. For each source, this record notes the exact locator/URL, version/date, specific claims supported, and strict limitations (what inferences cannot be supported).

### 3.1 Source 1: SEC Company Concept API Documentation and Live Responses

* **Locator / URL:**
  - Documentation: `https://www.sec.gov/edgar/sec-api-documentation`
  - Endpoint: `https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/[taxonomy]/[tag].json`
* **Version / Date:** EDGAR Data Delivery RESTful APIs (Current, 2024–2026).
* **Audited Payloads:** Live responses for CIK `0000320193` (AAPL) and other issuers under taxonomies `us-gaap` and `dei`.
* **Specific Claims Supported:**
  - `E1` support that `{taxonomy}` in the URL path is an accepted routing token selecting a standard taxonomy dataset (e.g., `"us-gaap"`, `"dei"`).
  - `E1` support that response JSON payloads echo `taxonomy` as a top-level string field alongside `tag`, `label`, `description`, `entityName`, and `units`.
* **Limitations / Anti-Claims (What it CANNOT support):**
  - **No XML prefix contract:** The API documentation nowhere specifies `{taxonomy}` as an XML namespace prefix, QName prefix, or catalog `<Prefix>`.
  - **No namespace URI:** The API responses contain no namespace URI (e.g., `http://fasb.org/us-gaap/2026`) or schema targetNamespace.
  - **No contextRef / dimensional breakdown:** The endpoint returns aggregated units without XBRL `contextRef` attributes (Amendment 0 Decision 4).
  - **No cross-source bridge:** Does not cite `edgartaxonomies.xml` or declare any normative relationship with catalog `<Prefix>`.

### 3.2 Source 2: EDGAR Taxonomy Catalog and its Schema (`edgartaxonomies.xml` & `erxl.xsd`)

* **Locator / URL:**
  - Catalog: `https://www.sec.gov/info/edgar/edgartaxonomies.xml`
  - Schema: `https://www.sec.gov/info/edgar/erxl.xsd` (declared via `xsi:noNamespaceSchemaLocation="erxl.xsd"`)
* **Version / Date:** Schema `erxl.xsd`; root `<Erxl version="78">` (updated per EDGAR release).
* **Structure Audited:** Elements `<Loc>`, `<Family>`, `<Version>`, `<Namespace>`, `<Prefix>`, `<FileTypeName>`, `<Href>`.
* **Specific Claims Supported:**
  - `E1` support for the catalog's XML vocabulary and schema structure governed by `erxl.xsd`.
  - `E2` support relating `<Prefix>` as a descriptive attribute associated with a schema entry point `<Href>`, `<Namespace>` URI, `<Family>`, and `<Version>`.
* **Limitations / Anti-Claims (What it CANNOT support):**
  - **Does not govern REST APIs:** The catalog is an operational catalog for EDGAR filing acceptance; it does not define or govern REST API route parameters at `data.sec.gov`.
  - **Does not govern filing-local prefixes as a cross-source bridge:** The EDGAR XBRL Guide distinguishes §1.2.2 ("Standard Taxonomies") — which lists standard taxonomy *entry-point abbreviations* (e.g., `us-gaap`, `dei`, `srt`) — from §8.2 ("Standard Namespace Prefixes"), a table binding XBRL-infrastructure XML namespace prefixes (e.g., `ix`, `i`, `iso4217`, `xlink`) to namespace URIs; neither table equates filing-local prefix declarations with Company Concept API query parameters, so catalog `<Prefix>` entries do not constitute a cross-source contract.
  - **No historical filing-date validity proof:** The current catalog reflects active and accepted taxonomies at the time of the catalog release (e.g., release version 78). It does not prove what was valid on historical filing dates years earlier (e.g., in 2013).

### 3.3 Source 3: EDGAR Filer Manual (EFM Volume II: "EDGAR Filing")

* **Locator / Citation:** SEC EDGAR Filer Manual, Volume II (EDGAR Filing), Chapter 6 ("Interactive Data").
* **Version / Date:** Current EFM Volume II (Version 70+ / EDGAR Releases 24.x–25.x).
* **Specific Claims Supported:**
  - Regulatory requirements governing filers submitting XBRL / Inline XBRL instances to the SEC.
  - Mandates the use of SEC-approved standard taxonomies and defines acceptable schema entry points and extension taxonomy rules.
* **Limitations / Anti-Claims (What it CANNOT support):**
  - **Regulates inbound submissions, not outbound APIs:** The EFM specifies filing format requirements for issuers; it does not define the outbound `data.sec.gov` REST APIs or their query parameters.
  - **No API-to-catalog bridge:** Contains no provision equating the REST API query parameter `{taxonomy}` with the catalog `<Prefix>` or with instance QName prefixes.
  - **No cross-source equivalence contract:** Does not provide an `E4` contract bridging data consumer representations.

### 3.4 Source 4: EDGAR XBRL Guide / Staff Interactive Data Guidance

* **Locator / Citation:** EDGAR XBRL Guide (Prepared by SEC Staff, August 2026, corresponding to EDGAR Filer Manual Draft Version 78), `https://www.sec.gov/files/edgar/filer-information/specifications/xbrl-guide.pdf`; §1.2.2 "Standard Taxonomies" (Tables 6-5/6-6 of standard taxonomy entry-point abbreviations); §8.2 "Standard Namespace Prefixes" (XML namespace prefix → namespace URI table); §8.3 "Standard Locations" (`edgartaxonomies.xml` cross-reference); SEC Staff Guidance on Interactive Data; Interactive Data Test Suite documentation.
* **Version / Date:** EDGAR XBRL Guide, August 2026 (corresponds to EDGAR Filer Manual Draft Version 78; catalog root `<Erxl version="78">`).
* **Evidence — §8.2 "Standard Namespace Prefixes" (URI → Prefix bindings, verbatim from the August 2026 table):** `http://www.w3.org/1999/xhtml`→`xhtml`; `http://www.w3.org/1999/xlink`→`xlink`; `http://www.w3.org/2001/XMLSchema`→`xs`/`xsd`; `http://www.w3.org/2001/XMLSchema-instance`→`xsi`; `http://www.w3.org/XML/1998/namespace`→`xml`; `http://www.xbrl.org/2003/instance`→`xbrli`/`i`; `http://www.xbrl.org/2003/iso4217`→`iso4217`; `http://www.xbrl.org/2003/linkbase`→`link`; `http://www.xbrl.org/2003/XLink`→`xl`; `http://www.xbrl.org/2006/ref`→`ref`; `http://www.xbrl.org/2009/dtr`→`dtr`; `http://www.xbrl.org/2013/inlineXBRL`→`ix`; `http://www.xbrl.org/dtr/type/2020-01-21`, `2022-03-31`, `2024-01-31`→`dtr-types`; `http://www.xbrl.org/inlineXBRL/transformation/2015-02-26`, `2020-02-12`, `2022-02-16`→`ixt`; `http://xbrl.org/2005/xbrldt`→`xbrldt`; `http://xbrl.org/2006/xbrldi`→`xbrldi`; `http://xbrl.org/2014/extensible-enumerations`→`enum`; `http://xbrl.org/2020/extensible-enumerations-2.0`→`enum2`; `http://www.sec.gov/inlineXBRL/transformation/2015-08-31`→`ixt-sec`. (Note: this table binds only XBRL-*infrastructure* prefixes; taxonomy abbreviations such as `us-gaap`, `dei`, `srt` are absent. The §8.2 table spells the inline namespace `http://www.xbrl.org/2013/InlineXBRL` with a capital I; the guide uses the canonical lowercase `http://www.xbrl.org/2013/inlineXBRL` elsewhere, e.g. p. 24 and p. 181.)
* **Evidence — §1.2.2 "Standard Taxonomies" (standard taxonomy entry-point abbreviations per Tables 6-5/6-6):** `cef`, `country`, `currency`, `cyd`, `dei`, `ecd`, `exch`, `ffd`, `fnd`, `naics`, `oef`, `rr`, `rxp`, `sbs`, `sic`, `snj`, `spac`, `sro`, `stpr`, `vip`, `ifrs2`, `ebp` (a.k.a. `us-gaap-ebp`), `srt`, `us-gaap`. These name taxonomy entry-point URLs (e.g. `https://xbrl.sec.gov/us-gaap/2026/us-gaap-2026.xsd`), **not** XML namespace prefixes; `invest` is not among them.
* **Specific Claims Supported:**
  - §1.2.2 lists the standard taxonomy *entry-point abbreviations* that name taxonomy entry-point URLs (e.g., `us-gaap`, `dei`, `srt`, `ifrs2`, `ebp`, `cef`); these are filing-preparation identifiers locating taxonomy entry points, **not** XML namespace prefixes.
  - §8.2 lists the standard *XML namespace prefix* bindings (prefix → namespace URI) for XBRL-infrastructure namespaces used in instance/schema/HTML documents (e.g., `ix`→inline XBRL namespace, `i`→`http://www.xbrl.org/2003/instance`, `iso4217`, `xlink`→`http://www.w3.org/1999/xlink`, `xhtml`→`http://www.w3.org/1999/xhtml`, `xs`→`http://www.w3.org/2001/XMLSchema`, `xml`→`http://www.w3.org/XML/1998/namespace`).
  - §8.3 notes that `edgartaxonomies.xml` (EFM v68 § 6.2.2) enumerates the non-local taxonomy namespace URLs that a submission may use, and references the SEC taxonomy catalog at `https://www.sec.gov/info/edgar/edgartaxonomies.xml`.
  - Practical guidance for issuers and filing agents regarding element selection, extension modeling, and validation practices.
* **Limitations / Anti-Claims (What it CANNOT support):**
  - **Informational / non-normative for data consumers:** Guidance notices are advisory aids for preparers, not normative engineering contracts for data consumers.
  - **No API parameter specifications:** Does not define REST API endpoints, routing tokens, or database schemas.
  - **Two tables, no cross-source bridge:** §1.2.2 (entry-point abbreviations) and §8.2 (namespace-prefix bindings) are distinct tables addressing different filing-side purposes; neither equates Company Concept API tokens to catalog `<Prefix>` or to filing-local namespace declarations, and neither can be promoted into a cross-source `E4` contract bridging data consumer representations.

### 3.5 Source 5: SEC XBRL Glossary of Terms

* **Locator / URL:** `https://www.sec.gov/data-research/structured-data/inline-xbrl/xbrl-glossary-terms` (XBRL Glossary of Terms). (The path previously cited, `/data-research/standardized-data/xbrl-glossary-of-terms`, is superseded: SEC's "Office of Data Standards and Innovation Webpage Address Changes" notice (July 25, 2024) states that changed webpage addresses are automatically redirected to the respective new address, and lists the glossary under its new "Data and Research" location; the canonical live URL is the one above.)
* **Version / Date:** Published May 28, 2024; last reviewed or updated: June 26, 2024.
* **Specific Claims Supported:**
  - High-level, informational definitions of core XBRL terms: *Taxonomy*, *Element*, *Fact*, *Instance Document*, *Context*, *Extension*.
* **Limitations / Anti-Claims (What it CANNOT support):**
  - **Informational dictionary only:** Contains no formal technical specifications or schema definitions.
  - **No technical field bindings:** Does not mention API query parameters, catalog element bindings, or prefix mapping rules.

### 3.6 Source 6: SEC Financial Statement Data Sets Documentation

* **Locator / URL:** `https://www.sec.gov/dera/data/financial-statement-data-sets.html` (DERA Data Sets Readme and Notes).
* **Version / Date:** DERA Quarterly Financial Statement Data Sets documentation (Current).
* **Structure Audited:** Flat file tables (`sub.txt`, `num.txt`, `tag.txt`, `pre.txt`).
* **Specific Claims Supported:**
  - `E1` support for DERA's data representation: `tag.txt` uses a compound `version` field (e.g., `"us-gaap/2023"`, `"dei/2023"`, or custom accession numbers for extension concepts).
* **Limitations / Anti-Claims (What it CANNOT support):**
  - **Distinct schema / different vocabulary:** DERA flat files use an independent naming and schema convention distinct from both the Company Concept API and `edgartaxonomies.xml`.
  - **No cross-source merge permitted:** DERA documentation cannot be merged with Company Concept API documentation to synthesize a cross-source contract.
  - **Does not bridge API tokens to catalog prefixes:** The existence of `"us-gaap/2023"` in DERA does not prove that Company Concept API `"us-gaap"` is catalog `<Prefix>` `"us-gaap"`.

### 3.7 Source 7: SEC EDGAR Developer API Documentation and Machine-Readable Contract Investigation

* **Locator / URL:** `https://www.sec.gov/edgar/sec-api-documentation`
* **Version / Date:** EDGAR Developer Documentation (Current, 2024–2026).
* **Specific Claims Supported:**
  - Prose developer documentation defines endpoint URI patterns: `/api/xbrl/companyconcept/CIK{cik}/[taxonomy]/[tag].json`.
  - Documents `[taxonomy]` and `[tag]` path components and describes their high-level role in selecting company concept disclosures.
* **Limitations / Anti-Claims (What it CANNOT support):**
  - **No published machine-readable contract:** The investigation found no official machine-readable OpenAPI or Swagger schema definition published by the SEC for the `data.sec.gov` Company Concept API.
  - **No normative schema binding:** Because no machine-readable OpenAPI schema is published, there is no formal schema contract or enum defining acceptable taxonomy tokens against the XML catalog schema `erxl.xsd`.
  - **No semantic bridge:** The prose documentation describes query parameters for web consumers but does not define an explicit cross-source bridge equating API taxonomy tokens to catalog `<Prefix>` or instance namespace URIs.
  - **Conclusion:** No formal machine-readable cross-source contract exists between the Company Concept API and the EDGAR taxonomy catalog.

---

## 4. Analysis of Identifier Surfaces vs. Universal Contradiction

Across the audited SEC interfaces, several distinct identifier surfaces were observed:

| Surface Identifier | Source System / Interface | Example Representation | Primary Architectural Purpose |
|---|---|---|---|
| **API Path Token** | Company Concept REST API | `"us-gaap"`, `"dei"` | URL routing & REST resource addressing |
| **Catalog Element** | `edgartaxonomies.xml` | `<Prefix>us-gaap</Prefix>` | Suggested prefix in operational catalog |
| **Catalog Namespace** | `edgartaxonomies.xml` | `http://fasb.org/us-gaap/2026` | Formal targetNamespace identifier |
| **Filing QName Prefix** | Instance XML (`xmlns:...`) | `xmlns:us-gaap="..."` (document-local; §8.2 binds only XBRL-infrastructure namespace prefixes such as `ix`/`i`/`iso4217`/`xlink`/`xhtml`/`xs`/`xml`/`xbrli`; the taxonomy entries named by §1.2.2 abbreviations like `us-gaap`/`dei`/`srt` resolve by namespace URI per §8.3/`edgartaxonomies.xml`, not by §8.2) | Document-local XML syntactic prefix |
| **DERA Bulk Version** | DERA `tag.txt` | `"us-gaap/2023"` | Relational version/family compound key |

### 4.1 Surface Differences Do Not Equal Universal Contradiction

These observed differences must be characterized with precision:
- **Purpose-driven specialization:** The differences in identifier format reflect distinct architectural purposes across SEC systems (REST routing, XML cataloging, XML document parsing, bulk data distribution).
- **Not universally contradictory:** It is inaccurate to characterize these different identifier fields as fundamentally or universally contradictory. They are specialized identifiers serving different architectural layers.
- **Surface similarity is not proof:** Conversely, the fact that several systems use the character string `"us-gaap"` on their surface does not constitute proof that they share a single controlled vocabulary or cross-source contract.

---

## 5. Historical Validity and Catalog Evolution (Claim C9)

### 5.1 Catalog Evolution and the Snapshot Limitation

The official EDGAR taxonomy catalog (`edgartaxonomies.xml`) is a dynamic document updated with each major EDGAR release (identified by the root `<Erxl version="...">` attribute, e.g., `version="78"`).

Consequently:
- A current snapshot of `edgartaxonomies.xml` reflects only the taxonomies accepted and active under that specific EDGAR release.
- **A current snapshot cannot prove historical filing-date validity:** Capturing the current catalog does not establish whether a namespace URI used in a historical filing (e.g., an AAPL 2013 filing using `http://fasb.org/us-gaap/2013`) was recognized, accepted, or active on that historical filing date.

### 5.2 Preservation of Future C9 Verification

This record explicitly avoids overstating the limitation:
- **C9 is NOT declared permanently unprovable:** ST-EVA does not assert that historical authority validity can never be established.
- **Path to verification preserved:** Claim C9 remains `UNAVAILABLE / UNPROVEN` in current repository evidence. The architecture explicitly preserves the possibility that future acquisition of historical authority catalog snapshots, archived EDGAR release announcements, and effective-date schedules may provide the necessary evidence to evaluate C9 for historical filings.

---

## 6. Prohibitions and Production Integrity

Under this amendment, the following prohibitions remain strictly binding:

1. **No new mappings:** No hardcoded dictionaries, heuristic prefix mappings, or normalization lookup tables may be created.
2. **No change to claim statuses:** Claims C3 and C7 remain `NOT PROVEN`. Claim C9 remains `UNAVAILABLE / UNPROVEN`. Claim C10 remains `UNAVAILABLE`.
3. **No C4G reimplementation authorized:** The C4G candidate implementation remains archived at baseline `9b3a8a8`. Production B2 code must continue to evaluate `evaluate_taxonomy_equivalence` as `(False, TAXONOMY_UNPROVEN)`.
4. **No DB / schema / migration additions:** No new SQLite tables, columns, or triggers are authorized.
5. **No alteration of Amendment 7:** Amendment 7 and its Evidence Sufficiency Matrix are preserved in their entirety.
6. **No modification of production code:** Production ingestion, linking, and archival code paths remain untouched.

---

## 7. Amendment 8 Summary Matrix

| Dimension | Record / Status |
|---|---|
| **Research Result** | `BRIDGE_NOT_FOUND` across investigated official SEC/EDGAR sources |
| **Claim C3** | `NOT PROVEN` (no cross-source contract connecting API token to catalog `<Prefix>`) |
| **Claim C7** | `NOT PROVEN` (Observation vs. occurrence representation equivalence unproven) |
| **Claim C9** | `UNAVAILABLE / UNPROVEN` (current catalog snapshot cannot prove historical filing-date validity; future proof preserved) |
| **Claim C10** | `UNAVAILABLE` for current production architecture |
| **Investigated Sources** | 7 official sources audited (Company Concept API, Catalog XML/erxl.xsd, EFM, XBRL Guide, Glossary of Terms, DERA Data Sets, Developer API Docs) |
| **Four Semantic Entities** | Strictly separated: API token, Catalog Prefix, Filing-local prefix, Observation-to-occurrence equivalence |
| **Production State** | Baseline `9b3a8a8` intact; C4G archived; production returns `TAXONOMY_UNPROVEN`; no unproven links written |
| **Code / DB Changes** | ZERO changes to code, tests, migrations, schemas, or DB |


---
---

# Amendment 9 — Shared Authority Archive Target & C1–C2B Operational Boundary

**Status:** FROZEN — architectural decision / operational boundary only. No ingestion executed.
**Date:** 2026-10-09
**Baseline:** `62ddee6`.
**Scope:** Designating the persistent storage target for the SEC taxonomy catalog (`edgartaxonomies.xml`) and defining the operational conditions and architectural boundaries for executing Phase 3C-C1 → C2A → C2B.
**Decision:** Designate `data/st-eva.sqlite` as the shared central authority archive.
**Current Disk State:** `data/st-eva.sqlite` does NOT exist. Execution is gated behind an independent audit.
**Claim Statuses (Unchanged):**
- **C3:** `NOT PROVEN`
- **C7:** `NOT PROVEN`
- **C9:** `UNAVAILABLE / UNPROVEN`
- **C10:** `UNAVAILABLE`
**Cross-Archive Read Boundary:** Per-ticker archives (`data/archives/<TICKER>.sqlite`) remain separate; no cross-archive reading, no B2/C4G activation, and no observation link writes are authorized.
**Preservation:** Amendments 1–8, production code, tests, Observation identity, evidence identity, and migrations 0001–0022 remain completely untouched.

---

## 1. Storage Location Decision: Shared Central Authority Archive

This amendment resolves the unassigned target archive question identified during preflight audit and formalizes the persistent storage destination for SEC taxonomy catalog acquisition and authority assertions.

### 1.1 Designated Target: `data/st-eva.sqlite`

The designated persistent archive for the official SEC taxonomy catalog (`edgartaxonomies.xml`) and its parsed authority assertions is:

```text
data/st-eva.sqlite
```

### 1.2 Decision Rationale

Four architectural reasons determine this selection:

1. **Alignment with canonical default:** The repository's primary SQLite interface already defaults to `data/st-eva.sqlite` (`sqlite_archive.py:364` and `st_eva_runner.py:2493`). Adopting this canonical path requires zero configuration alterations, zero new environment variables, and zero CLI argument extensions.
2. **Shared cross-issuer authority semantics:** The SEC taxonomy catalog is a regulatory, system-wide authority published by the SEC for the entire EDGAR system. It is not tied to any single issuer or ticker. Storing it in a central archive truthfully reflects its cross-issuer scope.
3. **Prevention of fragmented duplication:** Placing the authority catalog in a central archive avoids redundant copying of identical catalog bytes (~200+ KB) and hundreds of authority assertion rows across disparate per-ticker archives (`data/archives/<TICKER>.sqlite`).
4. **Avoidance of redundant storage subsystems:** Designating `data/st-eva.sqlite` avoids inventing an ad-hoc, separate authority database (e.g., `data/authority.sqlite`). A separate database would introduce an unnecessary second storage lifecycle, distinct connection pooling, and dual-schema management overhead.

### 1.3 Explicit Non-Existence and Initialization Baseline

- **Current state:** `data/st-eva.sqlite` does **not** currently exist on disk.
- **Controlled initialization:** When future execution is authorized, the archive will be intentionally initialized by instantiating `SQLiteArchive("data/st-eva.sqlite")`, which executes existing migrations `0001` through `0022` within its standard transactional migration runner.
- **Honest historical record:** Initializing a fresh archive at this designated path does not imply that pre-existing historical database rows or prior corpus observations existed in the repository. It creates a dedicated, clean baseline strictly for authority catalog storage.

---

## 2. Acquisition Authorization and Operational Conditions

Execution of the acquisition and persistence workflow is **NOT** authorized by the adoption of this decision alone. Execution remains strictly gated until this Amendment has been verified by an independent read-only audit.

### 2.1 Authorized Operational Scope (Post-Audit)

Only after independent audit confirmation may an operator execute the following bounded sequence:

1. **Pre-flight safety verification:**
   - Confirm that `data/st-eva.sqlite` does not pre-exist on disk immediately before initialization, ensuring no existing user or production data can be overwritten.
   - Confirm that the parent directory `data/` exists and has proper filesystem write permissions.
2. **Archive initialization and migration head check:**
   - Instantiate `SQLiteArchive("data/st-eva.sqlite")`.
   - Confirm that migration head is exactly `22` (`authority_taxonomy_namespaces`), matching frozen checksum `3347303174edb0a48040883a81edf45dc4e0120eb80fa435e86c4875c2caaed3`.
   - Confirm that tables `source_documents` and `authority_taxonomy_namespaces` are present and empty.
3. **Workflow execution (C1 → C2A → C2B):**
   - Execute the existing thin orchestrator `archive/authority_taxonomy_workflow.py:run_authority_taxonomy_workflow(archive)`.
   - **C1 Acquisition:** Fetch uncompressed bytes from `https://www.sec.gov/info/edgar/edgartaxonomies.xml` using `DEFAULT_USER_AGENT` and record into `source_documents` via `record_taxonomy_catalog`, generating canonical document ID `doc_...`.
   - **C2A Parsing:** Parse payload bytes via `parse_edgar_taxonomies_catalog` into deterministic `ParsedAuthorityAssertion` structures without network or DB access.
   - **C2B Persistence:** Persist parsed assertions into `authority_taxonomy_namespaces` via `record_authority_taxonomy_assertion` under the shared `document_id`.
4. **Post-write verification:**
   - Verify `source_documents` row: exactly 1 row with `document_type = 'SEC_TAXONOMY_CATALOG'`, `uri = 'https://www.sec.gov/info/edgar/edgartaxonomies.xml'`, and matching SHA-256 `content_hash`.
   - Verify `authority_taxonomy_namespaces` rows: non-zero count, all rows referencing `doc_...`, all IDs starting with `atn_`, and all identity preimages verified against `canonical_json`.
   - Verify foreign key integrity: zero orphaned authority rows.
   - Verify idempotency: re-executing `run_authority_taxonomy_workflow(archive, payload_bytes=captured_bytes)` results in zero new rows and identical counts.

### 2.2 Operational Prohibitions

During acquisition and persistence:
- **No new migrations:** No migration `0023` or schema change is permitted.
- **No schema modification:** No table, column, trigger, or index may be altered.
- **No per-ticker contamination:** No authority assertions may be written into `data/archives/AAPL.sqlite`, `data/archives/MSFT.sqlite`, `data/archives/TSM.sqlite`, or any other per-ticker database.

---

## 3. Future Cross-Archive Read Boundary

The central authority archive (`data/st-eva.sqlite`) and the per-ticker runtime archives (`data/archives/<TICKER>.sqlite`) represent two distinct storage and lifecycle boundaries:

```text
+-----------------------------------------------------------------------------------+
| STORAGE BOUNDARY SEPARATION                                                       |
|                                                                                   |
|  [Central Authority Archive]                   [Per-Ticker Runtime Archives]      |
|  data/st-eva.sqlite                            data/archives/<TICKER>.sqlite      |
|  - source_documents (SEC catalog)              - filings & company concept data   |
|  - authority_taxonomy_namespaces               - observations & admissions        |
|                                                                                   |
|                   <--- NO CROSS-ARCHIVE READ AUTHORIZATION --->                   |
|                   <--- NO CROSS-DATABASE ATTACH OR FK      --->                   |
+-----------------------------------------------------------------------------------+
```

### 3.1 Non-Authorizations

This amendment strictly **DOES NOT** authorize:
1. Modifying per-ticker analysis or linking routines (`sec_xbrl_facts.py`, `sec_ingest.py`, `web/service_adapter.py`) to query the central authority archive.
2. Activating B2 or re-implementing C4G.
3. Writing `observation_filing_document_facts` or exact-source assertions (`observation_filing_documents`).
4. Creating SQLite `ATTACH DATABASE` dependencies, cross-database foreign keys, or unified views connecting the central archive to per-ticker archives.

### 3.2 Prerequisite for Future Cross-Archive Integration

If future analytical tasks require per-ticker pipelines to consult central authority assertions, that capability requires an independent architecture and evidence integration design decision. Such a decision must define how read isolation, reproducibility, and point-in-time evidence integrity are maintained without violating Invariant 19 or the Evidence Sufficiency Matrix.

---

## 4. Claims and Frozen Invariants

All claim evaluations established in Amendment 7 and reaffirmed in Amendment 8 remain strictly frozen:

* **C3:** `NOT PROVEN` (no cross-source vocabulary contract).
* **C7:** `NOT PROVEN` (Observation vs. occurrence taxonomy equivalence unproven).
* **C9:** `UNAVAILABLE / UNPROVEN` (historical filing-date validity unproven by current snapshot).
* **C10:** `UNAVAILABLE` (production refuses unproven taxonomy equivalence).

**Frozen Code & Schema Boundaries:**
- Amendments 1–8 text, context, and matrices are preserved verbatim without modification.
- Production code (`sec_ingest.py`, `sec_xbrl_facts.py`, `sqlite_archive.py`, etc.) is unchanged.
- Test suites and test boundaries are unchanged.
- Observation identity and evidence models are unchanged.
- Migrations `0001` through `0022` remain unchanged.

---

## 5. Amendment 9 Summary Matrix

| Dimension | Specification / Decision |
|---|---|
| **Designated Archive Path** | `data/st-eva.sqlite` (canonical central shared archive) |
| **Current Disk Status** | Does not exist; clean initialization when authorized |
| **Authority Acquisition Route** | Existing C1 → C2A → C2B (`archive/authority_taxonomy_workflow.py`) |
| **Operational Gating** | Execution blocked until independent read-only audit passes |
| **Per-Ticker Archive Policy** | `data/archives/*.sqlite` untouched; zero authority rows written |
| **Cross-Archive Interaction** | Strictly prohibited; no cross-DB queries, links, or FKs |
| **Claim Statuses** | C3: `NOT PROVEN`; C7: `NOT PROVEN`; C9: `UNAVAILABLE / UNPROVEN`; C10: `UNAVAILABLE` |
| **Code / Schema Changes** | ZERO changes to code, tests, migrations, schemas, or DB |
