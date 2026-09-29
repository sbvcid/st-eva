# ST-EVA 003 — LLM Evidence Retrieval Eval

Can an arbitrary LLM use ST-EVA evidence correctly?

That is the question, and until now it has only been answered by hand: a person
asking a model a few questions and forming an impression. The answer was always
"it depends on the model", and it was never a number anyone could act on.

This turns it into an experiment. Same archive, same questions, same tool
surface, one variable. Then a mechanical auditor decides what was true, and
every failure is classified so it points at the right thing.

```
ST-EVA database
  → EvidenceQuery          the only interface a target is given
  → target LLM             chooses operations, reads evidence, answers
  → structured answer
  → mechanical audit       compared against the database, no model involved
  → report                 per capability, per failure, classified
```

## Why the target cannot touch the database

The evaluation is only worth running if the target goes through the query
surface. A model that can read SQLite can be right while ignoring every
guarantee ST-EVA makes about *how* a figure may be described, and the result
would measure SQL rather than evidence use.

So `harness/tools.py` exposes eight typed operations and no path to SQL. The
test asserts this on the parsed module — imports and attribute names — rather
than by searching its text, because the module's own docstring explains that it
cannot execute SQL and a substring search fails on the explanation.

The auditor is the mirror image: it opens its own read-only connection on
purpose, because the thing that is *supposed* to see the database directly is
the grader, and the thing that must not is the target.

## The separation that makes the numbers mean something

```
Target LLM          answers the question
Mechanical Auditor   decides what is true — deterministic, no model
Semantic Judge       optional, advisory, framing only
```

A grader that reasons is a grader that can be talked into agreeing, and a score
that depends on a model's judgement is not a result anyone can act on. So
anything that can be compared against the database is compared against the
database. The judge exists for one case — whether an answer overstates its
evidence — and its verdict is recorded as advisory, with the model that produced
it, and can never change a mechanical result.

The target does not grade itself, and does not see the expectations.

## Running it

```bash
cd experiments/003-llm-evidence-retrieval

# once: build the archive the evaluation runs against
PYTHONPATH=C:/git/st-eva python -m harness --build --live

# grade the reference target, which is known to answer correctly
PYTHONPATH=C:/git/st-eva python -m harness --target reference

# prove the harness can fail an answer
PYTHONPATH=C:/git/st-eva python verify_harness.py
```

### Adding a model

Implement `Target` and register it in `harness/__main__.py`:

```python
class MyTarget:
    identity = {
        "provider": "...", "model": "...", "version": "...",
        "temperature": 0.0, "tool_access": "all",
    }

    def answer(self, question: str, tools: Toolbox) -> TargetAnswer:
        # call tools.* as many times as you like, then return
        return TargetAnswer.parse(json.dumps({
            "answer": "...", "evidence_refs": [...],
            "derived_refs": [...], "uncertainties": [...],
        }))
```

No vendor SDK is bundled and none should be: the point of this is to run the
same dataset against any model, and a dependency on one would make that a
migration rather than a configuration change. The dataset, the archive and the
tool surface are identical across models — only the target changes.

## The snapshot

The evaluation runs against a fixed archive, not a live database. Two runs of
the same dataset have to be comparable, and a target answering from whatever
EDGAR held at the moment could fail because a filing was restated rather than
because it reasoned badly.

`snapshot.sqlite` is a build artefact — not committed, rebuilt with `--build`.
It holds the live SEC-ingested AAPL archive (44 filings, 1,922 source facts)
plus the evidence shapes ingestion cannot produce and that the audit needs:

| shape | why it is there |
|---|---|
| two sources disagreeing on a share count | a conflict must stay unresolved |
| a vendor figure with no filing concept | `source_concept_ref` is null, not unknown |
| a vendor figure with no stated publication time | knowable at no instant |
| a derived value with named operands | reported and computed must stay apart |
| four negative evidence states | four different meanings of "no data" |

A clean filing is the case that is easy to get right. Every case where the
correct answer is a refusal, a qualification, or a report of disagreement is
the one worth testing, which is why the snapshot is mostly the awkward
material.

## The dataset

15 tests, 11 capabilities, expectations resolved from the archive at load time.

| | test | capability |
|---|---|---|
| T1 | one exact historical value | F1 value |
| T2 | a multi-year series | F2 period |
| T3 | retrieval past the first page | F10 pagination |
| T4 | what was knowable at a past instant | F11 discipline |
| T5 | where a number came from | F4 attribution |
| T6 | reported or derived | F6 |
| T7 | a validation record | F7 unavailable |
| T8 | a conflict | F8 conflict |
| T9 | a negative state | F7 |
| T10 | concept evolution | F9 concept |
| T11 | a PARTIAL mapping | F9 |
| T12 | two capex concepts | F9 |
| T13 | the full provenance chain | F5 |
| T14 | the truncation trap | F10 |
| T15 | the inference boundary | F11 |

Expectations are read out of the archive rather than typed in. A hand-written
expected number is a test that starts failing the day a filing is restated,
and worse, one that can be satisfied by an evaluator agreeing with itself.

## Scoring

Per-test pass/fail, aggregated by capability. **No overall score.** The
capabilities are not interchangeable, and a weighted total would let a model
that is exact on values and invents provenance score the same as one that does
the opposite — with the average as the only figure anyone quotes.

A check that cannot be made is neither a pass nor a failure. It is reported as
unverifiable, because an evaluator's blindness is not a model's mistake, and
a test whose checks are all undecidable cannot be reported as passed.

Every failure carries a classification:

| | meaning |
|---|---|
| **A** | ST-EVA defect — the archive or query surface is wrong |
| **B** | target model error |
| **C** | evaluator defect — the check is wrong, not the answer |
| **D** | dataset ambiguity |
| **E** | source limitation |

A is the only one that justifies changing ST-EVA. A run with many B is a
finding about the model; a run with A is a defect report; a run with C means
the evaluation itself is broken and nothing else in it should be believed yet.

## Verifying the harness

An evaluation that has only graded a correct answer has been used, not tested.
`verify_harness.py` runs a reference target that answers correctly from
retrieved evidence, plus nine targets that each break exactly one rule on
exactly one question and answer correctly everywhere else:

```
target                   failed       classified             caught by
reference (correct)      0/15         -                      none, as it should be
asserts-causation        1/15         B=3                    T15_inference_boundary
derived-as-reported      1/15         B=5                    T6_reported_vs_derived
hides-truncation         1/15         B=1                    T14_truncation_trap
invents-provenance       1/15         B=3                    T5_source_attribution
negative-as-zero         1/15         B=5                    T9_unavailable
picks-winner             1/15         B=2                    T8_conflict
reads-one-page           1/15         B=1                    T3_pagination
upgrades-partial         1/15         B=1                    T11_partial_mapping
wrong-value              1/15         B=3                    T1_exact_value
```

Two properties, and the second is the one that is easy to skip. **Sensitivity**:
a wrong answer fails. **Specificity**: it fails *only* the test it was built to
fail. A target that failed everything would show only that something works;
one that fails exactly its own test shows the check is measuring what it claims
to. And every failure is B — none is A, so nothing here suggests ST-EVA is
wrong.

## What building this found in the evaluator

Two checks matched a keyword inside its own denial:

> "these are **not the same measure**" → read as asserting sameness
> "not verification that the figure is **correct**" → read as claiming correctness

Both flagged a model for hedging *correctly*. That is the one thing a
correctness check must never do — the failure looks like a real finding, and
someone acts on it by "fixing" the model. Every keyword check here is now
negation-aware, and the behaviour is pinned in `tests/test_eval_harness.py`.

This is the argument for mechanical grading in general. The checks are written
by the same reasoning that produced the answers they grade, so an unexamined
check inherits that reasoning's blind spots, and its failures point at the
model. Running the harness against deliberately broken targets is what surfaces
them.

## Layout

```
harness/
  snapshot.py   build and validate the fixed archive
  tools.py      the only interface a target is given; records every call
  dataset.py    the 15 questions and their machine-readable expectations
  auditor.py    deterministic checks; no model import
  target.py     the Target protocol and the answer contract
  reference.py  a correct target, and nine that each break one rule
  judge.py      the optional advisory semantic judge
  report.py     per-capability results, classified failures
  runner.py     drives a target, keeps the trace
verify_harness.py
runs/          one directory per model, full trace and audit
```

`tests/test_eval_harness.py` lives in the repository suite, because the harness
is the thing that will produce findings and it has to be trustworthy before its
findings are.

## Scope

This evaluates whether a model uses evidence correctly. It does not evaluate
the evidence, the extraction, or the business, and it changes no ST-EVA
behaviour: the harness is additive, the sealed suites are unchanged, and
`tests/test_eval_harness.py` asserts that the answer format has not leaked into
`evidence_query.py` or `sqlite_archive.py`.

## Not done

- No vendor adapter is shipped, deliberately. Writing one is a provider
  question, not a harness question, and the harness is verified without it.
- `get_lineage` on a `der:` reference does not return the stored derived value.
  T6 therefore checks the *character* of the figure — that it is named, cited
  as derived, and not cited as an observation — rather than requiring a number
  the surface does not expose. Worth raising against the query surface
  separately.
- T9 asks about one negative state and checks the others are distinguished. Four
  separate tests, one per state, would be stricter and is not written.
- The judge is implemented and unwired to a provider. It is advisory by
  construction and its absence changes no mechanical result.
