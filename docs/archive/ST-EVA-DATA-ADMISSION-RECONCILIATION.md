# ST-EVA Data Admission Reconciliation

> **歷史資料／非現行指令。** 本文件只記錄撰寫時的設計、狀態、計畫或決策，不具有授權、禁止、限制或要求未來工作的效力。文中任何「binding」「frozen」「approved」「not authorized」「must」等措辭均為歷史內容，不得凌駕使用者目前的要求。當前狀態以現行程式碼、測試及實際 Git 狀態為準。
>
> **HISTORICAL ARCHIVE — NOT CURRENT INSTRUCTIONS.** This document records prior design, status, plans, or decisions. It does not grant, deny, restrict, or require work. Any “binding,” “frozen,” “approved,” “not authorized,” or “must” wording below is historical and does not override the user's current request. Determine current state from current source code, tests, and Git state.

**Status:** RECONCILIATION. Read-only analysis. No design, no migration, no
schema change.
**Date:** 2026-10-07
**Question:** *What does ST-EVA already permit into the canonical data layer, and
which parts of Historical P/E's newly verified evidence semantics can the
existing architecture already carry?*

**Inputs read:**

| Source | Role in this document |
|---|---|
| `archive/migrations/*.sql` (0001–0019, 26 tables) | what the schema enforces |
| `sqlite_archive.py`, `archive.py` | what the writer enforces |
| `data_contract.py`, `evidence_model.py` | Observation, EvidenceState, vocabularies |
| `evidence_query.py` | the read-only evidence surface |
| `evidence_valuation_boundary.py` | the admission boundary |
| `core_registry.py`, `registry_seed.py` | registry and filing identity |
| `sec_provider.py` | the SEC ingestion path |
| `cross_validation.py` | existing basis-comparison machinery |
| `docs/ADR-HISTORICAL-PE-METHODOLOGY.md` (Amendment 1) | frozen methodology |
| `docs/methodology/CONTRACT-HISTORICAL-PE.md` | the engine contract |
| `research/experiments/aapl-historical-pe-poc/amendment1_verify/` | AAPL 31/31 result |
| `research/experiments/aapl-historical-pe-poc/contract/msft_validation/` | MSFT second-issuer findings |

**What this document is not.** It is not a proposal. It proposes no column, no
table, no enum, no parser and no engine. Where it says something is missing it
says what is missing and stops there. Section J names one minimal next
engineering change and nothing more.

**Headline answer.** Of the five fields Historical P/E needs, **one is already
represented, one is derivable inside a container that already exists, and three
are genuinely missing** — and the three that are missing are missing in a way a
column alone would not fix. The single largest reconciliation finding is that
`observation_content_hash()` does **not** cover `basis_json` or `raw_json`, so any
classification parked only in those blobs is invisible to the observation's own
identity and is silently deduplicated on write. That is a writer-level fact, and
it changes the answer for exactly those three.

## Gap summary at a glance

Full reasoning in §G.3; the fourth gap in §H.4.

| Field | Verdict | One line |
|---|---|---|
| `evidence_class` | **genuinely missing** | `.form` is present and is the wrong discriminator (MSFT 2011–2015); the item code is stored nowhere |
| `legal_status_note` | **genuinely missing** | `sources.notes` is source-level and about redistribution; nothing is per-observation or about §18 |
| `audit_status` | **genuinely missing** | three non-implying values need three storage slots, not a derivation from `form` |
| `accounting_basis` | **already represented** (GAAP vs non-GAAP) / **derivable** (`as_traded` vs `split_adjusted`) | the non-GAAP half is registry metric identity and needs no field; the share-basis half has a container and a convention already |
| `fiscal_year_end_month` | **genuinely missing** | `.fiscal_year`/`.fiscal_period` are per-*report*; the month is per-*issuer* and lives only in SGML headers nobody captures |

Plus one gap found while reconciling that is not on the named list:
`available_at` records no **source discriminator**, and the path currently taken
reads the submissions API value that ADR D12 declares non-conformant (§H.4).

---

# A. Existing canonical data rules

These are the rules already in force. They were read from the code and the
migrations, not inferred from documentation, and several of them are enforced by
the database rather than by convention.

## A.1 The six separations the archive already holds

| Separation | Held by | Why it exists |
|---|---|---|
| observation vs admission | `observations` table vs `admissions` table (`0019`) | "what the source said" vs "which of it the engine took" |
| source fact vs interpretation | `observations` vs `interpretations` (`0017`) | a parser correction is a new *reading* of an existing fact, on its own time axis |
| source availability vs ST-EVA's knowledge vs the engine's decision | `available_at` / `knowledge_at` / `decided_at` | folding a correction into `available_at` dates it to a filing that did not contain it (`0017:32-36`) |
| concept vs metric | `concept_registry` vs `metric_registry` (`0007`) | a filer may change tag without changing the fact |
| adoption vs meaning | `issuer_concept_adoption` vs `metric_concept_mapping` (`0009`) | a window on a concept seeded from AAPL is one company's observation, not a rule |
| applicability vs availability | `metric_exclusion`/`metric_inapplicable_in` vs `evidence_state` | "no such line for this kind of company" is not "retrieval failed" |

## A.2 What enters an `Observation`

An observation is **one metric, one value, one provenance record**
(`data_contract.py:735-823`). Its identity is
`observation_content_hash()` (`sqlite_archive.py:112-135`) over exactly eleven
fields:

```
observation_id, metric, provider, concept, value, unit, currency,
period_start, period_end, as_of, available_at, accession
```

`basis_json`, `raw_json`, `definition`, `methodology`, `status`,
`status_reasons_json` and `inputs_json` are **not** in the preimage.

**This has a direct consequence that the rest of this document depends on.**
`record_observation` (`sqlite_archive.py:756-768`) looks the hash up first and, on
a hit, returns the existing row id and links documents to it:

```python
content_hash = observation_content_hash(observation)
existing = self.connection.execute(
    "SELECT observation_id FROM observations WHERE content_hash = ?", ...
).fetchone()
if existing is not None:
    self._link_documents(existing["observation_id"], ...)
    return existing["observation_id"]
```

For SEC facts `observation_id` is
`comparable_observation_id(metric, "sec", period=label, accession=accession)`
(`sec_provider.py:1607-1612`), so it does not vary with any classification.
Therefore **two observations of the same fact that differ only inside
`basis_json` or `raw_json` produce the same hash, and the second one is
discarded as a duplicate.** The archive would keep whichever was ingested first
and silently drop the reclassification. Any Historical P/E field that is
load-bearing *and* differs between two readings of the same fact therefore cannot
live only in those blobs.

## A.3 What enters `Evidence`

`evidence_state` records *why something is absent*, in a closed 7-state
vocabulary (`evidence_model.py:57-103`) with a closed reason code per state.
`Evidence` itself is **not persisted**: `evidence_query.py` assembles a package
at read time from a stored row, the registry, the documents and any validation
records (`evidence_query.py:1068-1204`). Null fields are still present with an
explicit marker, because "the source did not state this" and "we do not know"
are different answers.

The surface **never resolves anything**: a conflict is returned as a conflict, a
missing item is returned with its reason, and an unvalidated figure says so
(`evidence_query.py:16-20`).

## A.4 What enters an `Admission`

`evidence_valuation_boundary.py` admits **one metric**: `revenue`
(`V1_CROSSING_METRICS`, line 103). Admission applies ten rules in a fixed order
(`_admit_one` docstring, line 942: *"Rules 1 through 10 for one metric, in that
order"*):

| # | Rule | Refusal label |
|---|---|---|
| 1 | metric scope, asked of the registry (ACTIVE, `currency`, DURATION) | `METRIC_NOT_IN_V1_SCOPE`, `UNIT_NOT_MONETARY` |
| 2 | something to consider | `UNAVAILABLE` |
| 3 | unit | `UNIT_NOT_MONETARY` |
| 4 | currency, declared and matching the price | `CURRENCY_UNDECLARED`, `CURRENCY_MISMATCH` |
| 5 | exact concept mapping, at this period | `MAPPING_NOT_EXACT` |
| 6 | one period, one concept | `CONCEPT_AMBIGUOUS`, `AMBIGUITY_RAISED` |
| 7 | an observed annual filing and nothing else | `PERIOD_NOT_DISCRETE` |
| 8 | a source-declared publication time, never archive-first-seen | `AVAILABILITY_UNDECLARED` |
| 9 | knowable at the requested instant | `NOT_KNOWABLE_AT_AS_OF` |
| 10 | select among survivors, disclosing the rest | — |

Refusals are **rows, not absences**, and every one leaves the engine field at its
existing `UNAVAILABLE` default. There is no fallback, no nearest-period search and
no substitution of a related figure, "because a refused input and a wrong input
differ only in whether the reader can tell" (lines 50-53).

## A.5 Replay authority

Replay filters on `replay_eligible_from` only. The writer never derives it from
`retrieved_at` (`sqlite_archive.py:741-746`); it is the source's `available_at`
for a declared observation, the archival moment for a first-seen one, and NULL
for an undeclared one — which is why an undeclared row is permanently ineligible
rather than merely late.

`availability_class` ∈ {`SOURCE_DECLARED`, `UNDECLARED`, `ARCHIVE_FIRST_SEEN`}
(`archive.py:42-46`) is derived from `available_at_basis`, never from whether the
field happens to be populated. Two triggers enforce the consequences: a
`SOURCE_DECLARED` row must carry `available_at`; an `UNDECLARED` row is never
replay-eligible (`0001:141-165`).

## A.6 Registry and filing identity

A concept is never promoted to a metric by name. It is promoted only through
`metric_concept_mapping`, and every vocabulary is closed by trigger (`0007:67-78`).
`eps_diluted` already exists as a registry metric — `statement=INCOME`,
`unit_family=per_share`, `normal_period_type=DURATION` — with
`us-gaap:EarningsPerShareDiluted` and `ifrs-full:DilutedEarningsLossPerShare`
mapped `EXACT` (`registry_seed.py:264-274, 1134-1138, 1422-1431`), and the
continuing-operations IFRS variant explicitly **declined** with a reason
(`registry_seed.py:1879-1892`).

Filing identity is the accession, carried on `observations`, on
`observation_sources`, and as the primary key of `held_filings` (`0008:15-30`).

---

# B. Observation boundary

## B.1 What an observation is

`data_contract.Observation` is frozen, so a validation pass cannot write to it —
"which is how the 'validation must not overwrite a raw observation' rule is
enforced structurally rather than by convention" (`data_contract.py:735-744`).
The archive mirror is append-only by trigger: `observations`, `context_snapshots`,
`interpretations`, `admissions`, `metric_supersession` and `source_documents` all
reject UPDATE and DELETE with `RAISE(ABORT)`.

## B.2 What is *not* an observation

This is the boundary the Historical P/E work must respect, and it is enforced
today:

1. **A source document is not an observation.** Bytes live in
   `source_documents` (content-addressed, `content_hash` UNIQUE). An observation
   cites documents through `observation_sources`. A document that no observation
   references is stored content, not a fact.
2. **A registry concept is not an observation.** `us-gaap:Revenues` is a tag a
   filer applies; `revenue` is a meaning ST-EVA names (`0007:5-12`).
3. **An engine decision is not an observation.** It is an admission
   (`0019:8-14`).
4. **A finding in prose is not an observation.** It is a report.
5. **A raw SEC filing is not an observation** merely because it was downloaded.
   `source_documents` may hold it; only a parsed fact on a mapped concept
   becomes an observation.

## B.3 The one place the Observation boundary is currently porous

The **furnished Item 2.02 EX-99.1 earnings release** is document text, not an
XBRL fact. For AAPL FY2021–FY2025 Q4, no XBRL fact exists
(`amendment1_verify/README.md`; ADR §6.1). Extracting the quarter EPS from the
exhibit text therefore means a **new ingestion path** that produces a fact from
a document rather than from the XBRL company-concept API.

`sec_provider.py` has **no form filter**. It reads `form` from the XBRL fact
entry and records it (`sec_provider.py:1080`, `1568`), so an 8-K XBRL-tagged
fact already becomes an observation with `form='8-K'`. That is why the MSFT
validation's Finding J.3 is a data-layer finding and not only a contract one:
Microsoft tags quarter-length diluted EPS in 8-K filings from 2011–2015, and
those 16 facts are, right now, indistinguishable from any other 8-K fact in the
archive.

---

# C. Evidence boundary

## C.1 Three vocabularies that must not be merged

| Vocabulary | Members | Owner |
|---|---|---|
| Evidence state | `SOURCE_REPORTED`, `SOURCE_DID_NOT_REPORT`, `NOT_APPLICABLE`, `NO_OBSERVATIONS`, `UNAVAILABLE`, `CONFLICTING`, `STALE` | `evidence_model.py:57-65` |
| Evidence reason code | one closed code per state (`SOURCE_STATED_VALUE` … `NO_RECENT_VALUE`) | `evidence_model.py:95-103` |
| Admission refusal label | 11 labels, "admission findings and not validation statuses and not evidence reasons" | `evidence_valuation_boundary.py:118-148` |

The ADR and the Contract add a **fourth**: `AVAILABLE` / `UNAVAILABLE` /
`REFUSED` plus the closed `REASON_*` enumeration. It is a different vocabulary
from all three, and `evidence_state.state` does not contain any of its members.
That is a real collision to be aware of and is **not** a defect in either — but
it means a Historical P/E state cannot be stored in `evidence_state.state`
without inventing a fourth meaning for that column.

## C.2 Evidence is a read product

`Evidence` is assembled at read time from: the stored row, `basis_json`, the
resolved registry semantics, the linked documents, the validation records, the
ambiguity classification and any interpretation effective at the cutoff
(`evidence_query.py:1068-1204`). Nothing in that assembly persists a verdict.

## C.3 The basis container already exists, with a convention

`observations.basis_json` (`0003`) is a per-observation structured dict with a
stated convention: an adapter declares only what its source states, every other
key is absent rather than guessed, and an explicit `UNDECLARED` sentinel is used
where a value exists but is unstated (`sec_provider.py:412-443`; the reader treats
`UNDECLARED`/`UNKNOWN`/`NONE` as absence, not as a value —
`cross_validation.py:367-381`).

Declared keys today: `reporting_currency`, `source_declared`, `taxonomy`,
`concept`, `shares_basis`, `security_type`, `excludes_listing_adjustment`,
`vendor_basis`, `mapping_fidelity`.

## C.4 One existing mechanism already does basis-conflict detection

`cross_validation.py:289-294` defines `_BASIS_EXCLUSIONARY_KEYS`:

```python
_BASIS_EXCLUSIONARY_KEYS = (
    "security_type", "shares_basis", "reporting_currency", "measurement_basis",
)
```

When two observations of the **same metric** declare different values for one of
these keys, the pair is treated as counting different things rather than
disagreeing about the same thing (`cross_validation.py:384-408`).

**Two limits that matter here.** It operates on *a pair of observations of one
metric*, not on price versus EPS, so it cannot express Contract Invariant F-6.
And `measurement_basis` in that list already means *period aggregation*
(`TTM`, `INSTANT`, `AS_OF`, `TRAILING_AGGREGATE`) — **not** GAAP versus non-GAAP,
and **not** `as_traded` versus `split_adjusted`. Reusing that key name for either
meaning would silently overload an existing conflict detector.

---

# D. Admission boundary

## D.1 Admission is a decision, recorded with identity

`admissions` (`0019`) is append-only, keyed by
`(asset_id, decided_at, metric)` for the decision, with a content-derived
`identity` UNIQUE column, a `supersedes` chain, and **both**
`registry_state_identity` and `resolver_policy_identity` NOT NULL — "an admission
recorded without them could not say what read it" (`0019:65-68`).

A refusal is a row: `contract_id` is NULL when nothing was admissible, "because
a refusal is a decision too, and the persistence tests assert that a refused
admission is a row rather than an absence" (`0019:57-60`).

## D.2 What is deliberately *not* on the observation

`0019:4-18` records the measurement: `Observation.role` was considered and
rejected. It would have made `observations` carry a context-dependent truth (the
same fact is evidence-only at one instant and engine input at another), and it
would have required either re-keying all 291,134 archived rows or being silently
dropped by content-hash dedup.

## D.3 Values are recorded by identity, never by value

`admissions` carries `price_contract_id` and `price_source_fact_id` but
deliberately no price figure: "the price is an observation, it is already in the
archive under its own identity, and copying the number here would create a second
copy that can disagree with the first" (`0019:29-36`). It likewise carries no
`value`, `unit`, `currency` or period columns, and no registry snapshot.

## D.4 What admission will not do with furnished evidence

Admission does not have, and does not need, a rule about evidence class — because
it does not have a rule about forms either. Rule 5 asks the registry about the
**concept**; no rule reads `form`. `form` is carried on the `Admission` record for
disclosure (`evidence_valuation_boundary.py:277`).

This is the correct place for the separation to sit. **A furnished document is
not admitted because it is filed, and it is not refused because it is furnished.**
It is admitted or refused because it satisfies or fails rules 1–9, and the record
of which it was is provenance.

---

# E. Existing SQLite / schema representation

## E.1 What is already stored for a Historical P/E quarter EPS fact

| Contract / ADR field | Existing home | Status |
|---|---|---|
| value, unit, currency | `observations.value_json`, `.unit`, `.currency`, `.currency_basis` | present |
| period start/end | `.period_start`, `.period_end` | present, both nullable |
| instant vs duration | `.period_start IS NULL`, plus explicit `.instant` (`0006:22-27`) | present |
| fiscal year, fiscal period | `.fiscal_year`, `.fiscal_period` (`0006:21-22`) | present as columns; see E.1.1 on which write path fills them |
| accession | `.accession` + `observation_sources.accession` + `held_filings` PK | present, indexed |
| form | `.form` (`0006:20`) | present, indexed via `observations_filing` |
| taxonomy, concept | `.taxonomy`, `.concept`, `.source_concept_ref` | present |
| source document | `source_documents` content-addressed, `observation_sources` | present |
| availability instant | `.available_at` + `.available_at_basis` + `.availability_class` + `.replay_eligible_from` | present |
| acceptance / filing / report dates | `raw_json.acceptance_datetime`, `.filing_date`, `.report_date` (`sec_provider.py:1573-1576`), kept apart on purpose | present, blob only |
| source-fact identity | `.source_fact_id`, partial UNIQUE (`0006:50-52`) | present |
| negative state | `evidence_state` (7 closed states) | present |
| decision record | `admissions` | present |
| derived figure with a recomputable operation | `derived_values.depends_on_json` + `deterministic` | present |

## E.1.1 The 0006 filing-identity columns are not written by the API path

`SQLiteArchive.record_observation`'s insert column list
(`sqlite_archive.py:776-785`) contains **none** of `taxonomy`, `accession`,
`form`, `fiscal_year`, `fiscal_period`, `statement`, `instant`, `source_fact_id`
or `source_concept_ref`. The bulk path writes them
(`fullscope_bulk.py:145-146`); the SEC API path leaves them NULL and everything
falls back to `raw.sec_fact` — `evidence_query.py:1111-1116` and
`evidence_valuation_boundary.py:434-442` both read the column first and the raw
payload second.

This does not make the identity unrecoverable, and the read side handles it
deliberately. It does mean the columns are **not** a reliable index for "which
filing said this" on an API-built archive: a query filtering on `observations.form`
would silently return nothing while the evidence packages still carry a form.
Any future decision about where evidence class lives must account for both write
paths, because a column the API path never fills is a column that is NULL on
exactly the rows a furnished-evidence ingestion path would create.

## E.2 What is not stored anywhere

Zero occurrences of `evidence_class`, `legal_status_note`, `audit_status`,
`accounting_basis`, `fiscal_year_end_month` or `XBRL_FACT*` in any `.py` or
`.sql` file in the repository. They exist only in `docs/`.

## E.3 Enforcement style, stated precisely

Closed **by trigger**: `metric_registry.statement`, `.unit_family`,
`.normal_period_type`, `.applicability`, `.status`; `mapping_type`;
`evidence_state.state`; `business_model` and its `basis`; `declined reason_code`;
`unmodelled_taxonomies.kind`; `ingestion_scope.status`; `redistribution_tier`;
`metric_exclusion.state`; `adoption basis`.

Closed **in code, not by trigger**: `availability_class`
(`archive.py:42-46`), `AvailabilityBasis` (`data_contract.py:238-246`),
`REASON_CODES` (`evidence_model.py:95`), `REFUSAL_LABELS`.

**Free text**: `observations.statement` is **not** closed — the `statement NOT IN`
trigger belongs to `metric_registry` (`0007:69-70`), and `observations.statement`
(`0006:23`) is an indexed plain `TEXT` column. `source_documents.document_type`
(`0002:12`) is likewise free text. `sources.notes` is free text and is about
redistribution, not legal status.

---

# F. Historical P/E requirements

What Amendment 1 and the Contract add, stated as data requirements only.

| # | Requirement | Source |
|---|---|---|
| R1 | `evidence_class ∈ {filed, furnished}` per component, determined by **item code**, not by form | ADR D10; Contract §B.2, §B.2.1(5) |
| R2 | `legal_status_note` — the document's own Section 18 language, **mandatory** when class is furnished, and part of the evidence's identity, not commentary | ADR D10; Contract §B.2, F-5 |
| R3 | `audit_status ∈ {audited, unaudited_reviewed, unaudited}` as **three distinct, non-implying** attributes in lineage | ADR D11; Contract §B.2, D.4, C.3 |
| R4 | `accounting_basis ∈ {as_traded, split_adjusted}` stated on price evidence, with price basis and EPS basis agreeing | Contract §B.3, F-6 |
| R5 | `fiscal_year_end_month` from the issuer's **own declaration**, with fiscal identity a function of `period_end` + that month and **never** of a list of filed 10-K period ends | Contract §E.1, F-3 |
| R6 | mandatory disclosure of mixed-class windows: `evidence_classes_present`, `forms_present`, `audit_statuses_present`, `mixed_class_window` | Contract §H.2; ADR D14 |
| R7 | `acceptance_source` must be an enumerated provenance string; the submissions-API `acceptanceDateTime` is **non-conformant** | ADR D12; Contract §B.2 |
| R8 | `acceptance_datetime` bound to a PIT usable date by the 16:00 ET rule, applied identically to filed and furnished | ADR D2, D12, D3 |
| R9 | `candidate_evidence_classes_enumerated` as the audit precondition for `REASON_MISSING_Q4_EPS` | Contract §G.2; ADR D13 |
| R10 | GAAP and non-GAAP never mixed; a presented non-GAAP figure is **constructed and excluded**, visibly | ADR §5.1; Contract §B.2, F-9 |

## F.1 What the second issuer proved about these

- **R1 is not satisfiable from `form`.** Finding J.3: MSFT tags quarter-length
  diluted EPS in 8-K filings 2011–2015 (16 facts). Deciding class by form would
  have called them `filed`.
- **R1 is also not satisfiable from "is it XBRL".** The discriminator the
  implementation used is the **Item 2.02 item code**, recorded on every evidence
  instance so the decision is auditable.
- **R2 is obtainable but not yet automatic.** The Section 18 language is in the
  8-K body; AAPL read it from there.
- **R3's derivation is form-shaped and therefore inherits R1's weakness.** The
  Contract's table maps 10-K → `audited`, 10-Q → `unaudited_reviewed`,
  8-K EX-99.1 → `unaudited`. All three values were observed on both issuers. But
  the `8-K EX-99.1` qualifier is the item code again, and an 8-K can also carry
  Item 9.01 financial statements, which are a different thing.
- **R4 held vacuously on MSFT.** MSFT had no split in the window, so the
  price-basis restoration path never fired. F-6 is genuinely exercised only on
  AAPL's 4:1 split.
- **R5 passed, and the naive alternative failed loudly.** 8 of 32 quarters are
  misassigned by a 10-K-list rule, as a systematic full-year shift. 29 quarters
  became usable before their own fiscal year's 10-K existed; judged against only
  the 10-Ks available at each quarter's own usable date, the naive rule was wrong
  for 25 of 29 and returned **no answer at all** for 21.
- **R10's exclusion test is weak on MSFT** and labelled so: MSFT's releases
  present no non-GAAP EPS line, so the run showed the enumeration was scoped, not
  that a presented non-GAAP figure was refused.

---

# G. Mapping

## G.1 Existing capability → already sufficient

| Historical P/E need | Already carried by | Why sufficient |
|---|---|---|
| A quarter EPS value with unit and currency | `observations` + `us-gaap:EarningsPerShareDiluted → eps_diluted` EXACT | the metric, the concept and the mapping all exist today (`registry_seed.py:1134-1138`) |
| Which fiscal quarter a fact belongs to | `.period_start`, `.period_end`, `.instant` always; `.fiscal_year`, `.fiscal_period` on the bulk write path only | the columns exist (0006) but see E.1.1 — on an API-built archive these are NULL and the raw `fy`/`fp` is the fallback |
| Which filing said it | `.accession`, `.form`, `.taxonomy`, `held_filings`, with `raw.sec_fact` as fallback | accession-keyed by design; again subject to E.1.1 |
| Which document, which bytes, which hash | `source_documents` + `observation_sources` | content-addressed, bytes retained |
| When it became public | `.available_at` + `.available_at_basis` + `.availability_class` + `.replay_eligible_from` | three-level vocabulary already distinguishes precise / date-only / undeclared |
| No lookahead | `replay_eligible_from`, append-only, three separated time axes | 0017 header states the rule explicitly |
| The Q4 is not synthesised | `is_discrete_period()` rejects year-to-date stubs at ingestion (`sec_provider.py:446`); admission rule 7 refuses non-annual periods; F-1 is structural | a cumulative figure cannot become a quarter by any existing path |
| Negative states (`UNAVAILABLE`, missing quarter) | `evidence_state`, `observations.status_reasons_json`, `admissions.refusals_json` | structured JSON is already the convention |
| The decision record with reasons | `admissions` (0019) | refusal-as-row is already enforced |
| A derived TTM denominator with a recomputable operation | `derived_values.depends_on_json` + `deterministic` | the intended home |
| Non-GAAP held apart from GAAP | **registry metric identity**: a non-GAAP figure is a different concept, so it is a different metric, so it cannot satisfy `eps_diluted`'s EXACT mapping | the separation is structural, and no new field is needed |
| Applicability vs availability | `metric_exclusion` / `metric_inapplicable_in` / `evidence_state` | already three separate places |

**GAAP versus non-GAAP is already represented.** ADR §5.1 and Contract F-9 do
not need a new field. They need the presented non-GAAP figure to be *constructed
as a separate observation against a separate registry metric* and then excluded
— which is exactly what the registry's concept≠metric discipline already
produces. F-9 becomes checkable by asking whether all four components resolve to
one metric id, not by reading a basis flag.

## G.2 Existing capability → insufficient

| Need | Nearest existing thing | Why it is insufficient |
|---|---|---|
| R1 `evidence_class` | `.form` | `form='8-K'` is ambiguous by measurement (Finding J.3) and the discriminator — the item code — is stored nowhere |
| R2 `legal_status_note` | `sources.notes` (source-level, redistribution) | wrong granularity, wrong subject, and free text; the Contract requires it to be part of the evidence's identity |
| R3 `audit_status` | derivable from `form` under a policy | form gets you two of the three values and is insufficient for the third — the 8-K Item 2.02 exhibit again needs the item code; and three non-implying values must be individually assertable, which a derivation does not give you |
| R4 `accounting_basis` | `basis_json.shares_basis` / `.security_type` | the container and the `UNDECLARED` convention exist, but there is **no mechanism** anywhere that compares a price basis against an EPS basis — F-6 is currently unmechanised |
| R5 `fiscal_year_end_month` | `.fiscal_year` / `.fiscal_period` | those are a *particular filing's* declared fiscal identity (per-report DEI `fy`/`fp`), not the issuer's declared FYE month; the month itself lives only in SGML header bytes the archive does not capture on this path |
| R6 mixed-class disclosure | `.form` per observation | the four components live on four rows; there is no place that states the *set* |
| R7 `acceptance_source` | `AvailabilityBasis` ∈ {`REPORTED`, `OBSERVATION_INSTANT`, `UNDECLARED`, `ACCEPTANCE_DATETIME`, `FILED_AS_OF_DATE`} | no member corresponds to the SGML-header Eastern Time value that ADR D12 makes authoritative; and `sec_provider.acceptance_index` reads the **submissions API** `acceptanceDateTime` (`sec_provider.py:1016`) and records it as `ACCEPTANCE_DATETIME` (`sec_provider.py:1517`) — the exact value D12 declares non-conformant |

## G.3 Per-field verdict — the five named fields

Judged against: `already represented` / `derivable` / `genuinely missing` /
`not a DB concern`.

### `evidence_class` — **genuinely missing**

Not represented anywhere in `.py` or `.sql`. `.form` is present but is the wrong
discriminator, and this is measured rather than argued: MSFT's 2011–2015 8-K
quarter EPS facts already sit in the archive as `form='8-K'` with no way to say
what item they came from.

`filed` is *derivable* today under a policy — "form ∈ {10-K, 10-Q, 10-K/A} implies
filed" — and for the current corpus that policy agrees with reality. It is stated
here as a **policy, not as data**, because the policy is exactly what fails the
moment an 8-K enters, and ADR D10's five eligibility conditions are keyed on item
code, document type and a verbatim period column. A policy that has to be
re-derived per run is not a representation.

**Not a DB concern for the eligibility conditions themselves.** Conditions 1–5
(D10) are parser and admission rules, not stored columns. Only the resulting
class label needs to persist.

### `legal_status_note` — **genuinely missing**

Not represented. `sources.notes` is source-level and about redistribution;
`sources.redistribution_tier` is about what may be republished. Neither is about
Section 18 legal status, and neither is per-observation.

The contract's requirement is stronger than provenance: it is in the hash
preimage (`Contract §I.2` — "Everything else is included, including
`usable_date_rule`, `fiscal_position_source`, `derivation`, `legal_status_note`").
The archive's equivalent requirement is `content_hash`, and
`observation_content_hash` **does not cover `basis_json`** (§A.2). So a
`legal_status_note` placed only in `basis_json` would be outside the observation's
identity — which means the archive could hold two different Section 18
renderings of the same fact under one hash and silently keep the first.

### `audit_status` — **genuinely missing**

Not represented. ADR D11 requires it as a **distinct attribute that neither
implies nor omits the other**, which is a statement about storage: three values
that must be individually assertable. The archive already has the exact
precedent for this shape — `availability_class`, three values, closed, with its
own consistency triggers — and `observations` already stores the per-filing
fiscal and form identity that a derivation would read.

Its **derivation** is a separate question and is currently only partly
determined: form narrows it to {10-K family → `audited`, 10-Q family →
`unaudited_reviewed`, 8-K Item 2.02 exhibit → `unaudited`}, but the exhibit case
again requires the item code. Notably, `form` is *not* the wrong discriminator for
audit status in the way it is for evidence class — 10-Q interim statements are
reviewed and 10-K annual statements are audited — but it is insufficient for the
8-K case.

### `accounting_basis` — **derivable, and the GAAP/non-GAAP half is not a DB concern**

Two distinct things share this name in the discussion. Separating them is the
whole answer.

**(a) GAAP vs non-GAAP — not a DB concern.** Already represented, structurally,
by registry metric identity (§G.1). The presented non-GAAP figure is a different
concept, therefore a different metric, therefore structurally unable to satisfy
`eps_diluted`'s EXACT mapping. Contract F-9 is satisfiable by asking which
metric each component resolved to. No field, column or enum is required. The
MSFT finding that this test is weak is a **coverage** observation about one
issuer's releases, not a representation gap.

**(b) `as_traded` vs `split_adjusted` — derivable, container already exists.**
`basis_json` is built for exactly this class of statement
(`sec_provider.py:412-443`) and already carries `shares_basis` and
`security_type` with an `UNDECLARED` sentinel for "source did not state it".
`_basis_for` runs on every SEC fact today. Adding one more declared key is an
ingestion change, not a schema change.

What is genuinely absent is narrower and worth stating on its own: **no mechanism
anywhere compares a price basis against an EPS basis.** F-6 has no implementation
and no analogue. `_basis_conflict` is the closest thing and it operates on two
observations of the *same metric*, not on price versus EPS
(`cross_validation.py:384-408`). And `measurement_basis` must not be reused for
this: it is already an exclusionary key meaning `TTM`/`INSTANT`/`AS_OF`/
`TRAILING_AGGREGATE` (`cross_validation.py:293`).

### `fiscal_year_end_month` — **genuinely missing**

Not represented. `observations.fiscal_year` and `.fiscal_period` are the *filing's*
declared fiscal identity — the XBRL `fy`/`fp` values from `raw.sec_fact`
(`evidence_valuation_boundary.py:434-442`) — not the issuer's declared fiscal
year end month. The month is not derivable from them: an issuer can file a Q3 10-Q
whose `fy`/`fp` say `2025/Q3` without the stored row ever recording that its year
ends in September. The DEI tags are per-*report*; the fiscal year end is
per-*issuer*, and nothing in the schema records the second.

It is not derivable from anything the archive captures on this path either. The
value comes from the SGML header `FISCAL YEAR END: 0930`, read from 48 filings for
MSFT (unanimous `0630`) and from 10-K headers for AAPL. `sec_provider`'s
acceptance index reads the **submissions API**, not SGML headers
(`sec_provider.py:1004-1021`), and no ingestion path in the repository captures an
SGML header as a `source_documents` row.

The precedent for the fix is exact and already in the schema:
`issuer_business_model` (`0010`) is asset-keyed issuer metadata with a closed
`basis` and a mandatory `source` for any declared or derived value
(`0010:114-124`). A fiscal calendar would be the same shape.

**Contract §E.1 and §K.4 both flag that `fiscal_year_end_month` is a property of
a *fiscal year*, not of the issuer**, and that per-fiscal-year resolution is
OPEN. That OPEN item is untouched by this document and is not resolved here.

---

# H. Genuine schema gaps only

Four. Each is stated as what is absent, not as what should be built.

## H.1 No discriminator for evidence class

Absent: any stored, per-observation attribute that distinguishes a §13(a)
periodic report from an Item 2.02 furnished exhibit. `.form` is present and is
insufficient by measurement. The discriminating attribute — the item code — has
no column and no place in `raw_json` today, because `sec_provider` never writes
one.

*Already sufficient for everything around it:* accession, form, taxonomy, concept,
period, document, availability.

## H.2 No three-valued audit status, and no place for a mandatory legal-status note

Absent: two per-observation provenance attributes. The archive has the shape
(`availability_class`, `available_at_basis`) and the enforcement idiom
(`RAISE(ABORT)` on insert), but neither attribute exists.

## H.3 No issuer fiscal calendar

Absent: any issuer-level declared fiscal year end month. `assets` has none.
`issuer_business_model` is the established home for this class of fact and the
`issuer_business_model` triggers are the established enforcement idiom.

## H.4 No provenance discriminator for the acceptance instant

Absent: any way to record *which source* produced `available_at`.
`AvailabilityBasis` has three relevant members and none of them distinguishes the
SGML-header Eastern Time value from the submissions-API value, which ADR D12
declares non-conformant. `raw_json.acceptance_datetime` records the value; nothing
records which source it came from, so a non-conformant value is indistinguishable
from a conformant one after the fact.

**Not listed as gaps, to prevent them being re-raised:** security/instrument
identity, research-run and research-artifact relations, multi-tenancy
convergence, price time-series storage. They are real and were recorded in
`ST-EVA-DATA-LAYER-AUDIT.md` §C.2. None is on the Historical P/E critical path
for the five fields in question, and adding them here would be the large
architecture this document declines to propose.

---

# I. Things that must NOT be changed

Binding on any future work arising from this reconciliation.

## I.1 Semantic boundaries

1. **Do not merge Evidence into Observation.** `Evidence` is a read product
   assembled at query time; `evidence_state` is the persisted record of *absence*.
   Historical P/E's `QuarterEpsEvidence` is a **view over a Core observation**
   (Contract §A.3), not a replacement. Making it a stored relation would
   reintroduce the duplication `0019` and `0017` were written to prevent.
2. **Do not put the consumption role on the observation.** Measured: 291,134
   archived rows would have to be re-keyed, or the field would be dropped by
   content-hash dedup (`0019:11-18`).
3. **Do not collapse the three time axes.** `available_at` ≠ `knowledge_at` ≠
   `decided_at` ≠ `retrieved_at`. Folding a parser correction into `available_at`
   "is how a point-in-time contract is quietly destroyed" (`0017:32-36`).
4. **Do not make `furnished` mean `admitted`.** Admission rules 1–10 do not read
   `form`, and they must not start reading evidence class. A furnished document
   qualifies because it satisfies the rules, not because of what it is. ADR D10
   makes a *component* requirement, not a blanket admission.
5. **Do not treat a raw SEC document as an Observation.** Bytes in
   `source_documents`; facts on `observations`; decisions in `admissions`. A
   downloaded filing that no observation references is stored content.
6. **Do not treat research artifacts as canonical data.** `raw/`, `out/`,
   manifests, `historical_pe_points.json`, `msft_negative_path.json`,
   `fiscal_quarters.csv` are research material under
   `ST-EVA-PROJECT-STRUCTURE.md` §2.10. They become canonical only when an
   observation cites them. Nothing in `research/` may be loaded into the archive
   because it exists.
7. **Do not re-open the reason-code enumeration.** ADR D's seven codes are closed
   and Amendment 1 added none. `XBRL_FACT_UNAVAILABLE` is **not** a reason code
   (ADR D13; Contract F-12). No new code is needed for anything in this document.
8. **Do not reuse `measurement_basis` for GAAP/non-GAAP or for share basis.** It
   is an existing exclusionary key meaning period aggregation
   (`cross_validation.py:293`).
9. **Do not use `availability_class` or `available_at_basis` to carry evidence
   class or audit status.** They are the replay axis. Overloading them would
   corrupt the one thing the point-in-time contract depends on.
10. **Do not put a new `statement` value on `observations`.** That column is free
    text and semantically means *which statement the fact came from*; it is not a
    classification surface, and it is not closed by trigger.

## I.2 Frozen documents

`docs/ADR-HISTORICAL-PE-METHODOLOGY.md` and
`docs/methodology/CONTRACT-HISTORICAL-PE.md` are untouched by this reconciliation
and this document must not be read as amending either. The nine Contract §K
items — Reference Sufficiency, the 20/24 requirement, Sampling Frequency,
Corporate Action schema, FPI fallback, furnished weighting in other contexts,
`XBRL_FACT_UNAVAILABLE` observability, tie-breaking, non-USD pairing — remain OPEN
and are not addressed here.

## I.3 Engineering

No migration was authored. No SQLite file was opened or altered. No Core,
provider, boundary, registry, query-surface or web file was modified. No research
artifact was modified, moved or deleted. No ADR or Contract text was changed. No
Historical P/E engine, parser or provider was created.

---

# J. Minimal next engineering step

**One step, and it is not a migration.**

> Write a conformance test that takes one real furnished quarter EPS fact from the
> existing MSFT frozen input set and runs it through the *existing* archive writer
> path, asserting what the writer actually does with a classification-bearing
> observation.

Specifically, the test asserts three things and nothing else:

1. `observation_content_hash()` is **unchanged** when two observations differ only
   in `basis_json` and in `raw_json` classification keys — holding `accession`
   and `concept` constant, since `_accession_of` and `_concept_of` do read `raw`
   (`sqlite_archive.py:96-110`). This confirms §A.2's dedup consequence as an
   observed fact rather than a reading of the code.
2. `record_observation` returns the **first** row's id for the second
   differently-classified insert — i.e. the reclassification is silently absorbed.
3. `EvidenceQuery` does **not** surface any of the five named fields for either
   row, because no ingestion path writes them.

**Why this step and not a migration.** Every one of the four gaps in §H is a
*representation* gap, and the cheapest way to tell a representation gap from an
enforcement gap is to observe the current behaviour on real bytes. If step 2
confirms the silent absorb, then no amount of `basis_json` key-adding helps and a
column — plus a hash-preimage decision — becomes unavoidable. If it is refuted,
the gaps in §H shrink and one of them may not be a gap at all. A migration
authored before this test would encode an unstated choice as structure, which is
the failure mode ADR D4 already documents once.

**What the step deliberately does not do.** It proposes no column, no enum, no
table, no parser and no provider. It writes a test against existing behaviour and
records the result. Nothing in the archive changes if it passes.

**What remains undecided by design.** The hash-preimage question (does
`content_hash` need to cover a classification?), the `AvailabilityBasis`
question (H.4), the item-code carrier (H.1), and the per-fiscal-year fiscal
calendar resolution (Contract §K.4). All four are named and none is answered here.

---

## Consistency review

| Check | Result |
|---|---|
| Consistent with the ADR | Yes. No frozen decision is re-opened, weakened or extended. Every Historical P/E requirement in §F is quoted from Amendment 1 rather than paraphrased into a new rule. |
| Consistent with the Contract | Yes. No invariant is reinterpreted. The `fiscal_year_end_month` verdict records Contract §E.1/§K.4's per-fiscal-year OPEN as untouched. |
| Observation / Evidence / Admission separation preserved | Yes, and it is the document's main claim (§A.1, §A.5, §C.2, §D.1, §I.1 items 1–2). The reconciliation argues the separation is *sufficient* for everything except four named representational gaps. |
| `furnished` is not treated as `filed` | §B.3 records that `form='8-K'` is already ambiguous in the archive and that the item code is unstored; §G.3 gives `evidence_class` a verdict of **genuinely missing**, not "derivable from form". |
| `furnished` is not treated as `admitted` | §D.4 and §I.1 item 4. Admission rules 1–10 read no form and no class; the conclusion is that a furnished document qualifies on rules 1–9, not on its nature. |
| `unaudited` is not treated as `audited` | §G.3 gives `audit_status` a verdict of **genuinely missing**, and states that the three values must be individually assertable per ADR D11 rather than derived from one another. |
| non-GAAP cannot reach GAAP TTM | §G.1 and §G.3(`accounting_basis`(a)): the separation is already structural in registry metric identity, and needs no new field. |
| No research artifact treated as canonical data | §I.1 item 6, with the specific artifacts named. |
| No raw SEC document treated as an Observation | §B.2 items 1 and 5. |
| Observation / Evidence / Admission semantics unchanged | §I.1. No production file was modified. |
| No migration, no SQLite change | §I.3. Neither was authored nor applied. |
| Core, ADR and Contract unmodified | §I.2 and §I.3. |
| No large new architecture proposed | §H's explicit exclusion list; §J proposes exactly one test. |

---

*Reconciliation complete: read-only. No schema, migration, SQLite file, Core
module, provider, registry, query surface, ADR, Contract or research artifact was
modified, created, moved or deleted. No `git add`, `commit`, `reset` or `clean`.
This document is the only file written, and it is not staged.*