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

---
---

# Amendment 2 — Phase 3C-B Prerequisite Freeze

**Status:** FROZEN — prerequisite audit. **Still not implemented.** No production code,
schema, migration, or test change accompanies this amendment.
**Date:** 2026-10-08
**Audits:** the five prerequisites of Amendment 1 §11, item by item.
**Binding invariants:** `docs/ST-EVA-ARCHITECTURE.md` §D invariants 28–30
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

## 12. Whether Phase 3C-B is authorized

**Not authorized.** The design questions are now closed (§§1–11), so the remaining gate
is no longer a design question but an implementation one: writing migration `0021`,
plus the ten acceptance criteria. That is a distinct task with its own verification, and
the six unresolved questions of Amendment 1 §12 remain open.

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
**Binding invariants:** `docs/ST-EVA-ARCHITECTURE.md` §D invariants 19–30.

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