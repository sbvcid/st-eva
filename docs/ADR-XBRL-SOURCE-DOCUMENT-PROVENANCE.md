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

---
---

# Amendment 1 — Document-Route Fact Identity

**Status:** FROZEN — design decision. **Still not implemented.** No production, schema,
migration, or test change accompanies this amendment.
**Date:** 2026-10-08
**Supersedes:** nothing in §§1–7. **Refines:** §3 item 1 and §6 item 4, which this
amendment now answers.
**Binding invariants:** `docs/ST-EVA-ARCHITECTURE.md` §D invariants 24–27

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