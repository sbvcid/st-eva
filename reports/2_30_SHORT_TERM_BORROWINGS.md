# 2.30 — `ShortTermBorrowings` against the current side of `debt`: UNDECIDED

One candidate, no search. 2.29 established Proposition A and left B undecided;
this tests exactly one candidate against B and, in the process, splits 2.29's
compound statement.

No mapping, registry entry, coverage status or applicability rule was changed.
Nothing was fetched. Suite 714 run / 640 passed / 74 skipped. Not committed.

---

## A. First, 2.29's verdict is withdrawn and replaced by two

A compound statement must not carry a single verdict, and 2.29's did.

```
Proposition A   the concepts currently mapped to `debt` describe nothing the
                29 SOURCE_SILENT filers report
                                                    SUPPORTED
Proposition B   some unmapped concept is a corresponding representation of
                Core `debt`, sufficient to close the gap A establishes
                                                    UNDECIDED
```

A is established by a **subtraction over every silent filer**, with no name
matching: zero coverage of the four declared concepts. B needs a concept's
accounting identity tested against existing evidence, and that had not happened.
A single verdict for both would let the proved half carry the unproved one, which
is the failure this round exists to close.

---

## B. Proposition C: UNDECIDED

> `us-gaap:ShortTermBorrowings` has sufficient evidence to be treated as a
> **current-side candidate** for the `debt` composition.

Deliberately **not** "does it equal `us-gaap:LongTermDebtCurrent`". Their own SEC
definitions say they are different quantities:

```
ShortTermBorrowings        "Reflects the total carrying amount as of the balance
                            sheet date of debt having initial terms less than one
                            year or the normal operating cycle, if longer."

LongTermDebtCurrent        "Amount, after unamortized (discount) premium and debt
                            issuance costs, of long-term debt, classified as
                            current. Includes ... notes payable, bonds payable,
                            debentures, mortgage loans and commercial paper.
                            Excludes capital lease obligations."
```

One is *all* short-dated borrowing; the other is the current slice of *long-term*
debt. Both are current liabilities, and they are not the same quantity, so a
greater-than relationship was expected in advance and would not be a refutation.

### The four pre-registered conditions

```
PASS  1  the definition denotes an outstanding carrying amount
PASS  2  period shape, unit and basis are compatible
FAIL  3  the relationship is reproducible
PASS  4  no competing interpretation explains the observations better
```

### Why condition 3 failed — and why the relationship is not an identity

19 of the 75 filers with a payload report the candidate; 11 of those are among the
filers `debt` reports nothing for. Only **5** co-report the comparator, giving
**57 comparable periods**:

```
equal               29   50.9%
candidate_greater   18   31.6%
candidate_less      10   17.5%
```

I first read that as an unstable relationship, and the inversions look alarming
until they are looked at:

```
CMI    2012-04-01   candidate  33,000,000   current side  95,000,000   0.35
MSFT   2013-06-30   candidate           0   current side 2,999,000,000   0.00
MSFT   2013-12-31   candidate 300,000,000   current side 2,000,000,000   0.15
```

**MSFT reports zero short-term borrowings against $3.0bn of current long-term
debt.** That is not a contradiction and it is not an identity failure. It is what
a company with no commercial paper looks like.

Which means the two concepts are **complementary, not nested**: they are siblings
under "current debt", and a filer may have either or both. `ShortTermBorrowings` is
therefore not the declared current side, and it is not a substitute for it either.
My comparator encoded an assumption — that the candidate *contains* the declared
side — which their own definitions do not support, and condition 3 was measuring
the wrong thing. It failed, and the reason it failed is more informative than the
failure.

### The structural reason the proposition cannot be settled here

```
filers reporting the candidate                    19
   of which `debt` is SOURCE_SILENT                11
filers comparable against the declared current side 5
OVERLAP between the two                              none
```

**Every one of the 11 filers that would need the candidate reports zero
current-side concepts of any kind.** The five filers that do co-report one all
have `debt = COLLECTED` — they do not need the candidate.

So the identity test the proposition requires can only be run on filers that
already report `debt` successfully, and **the population that needs the candidate
is, by construction, the population where no comparator exists to test it
against.** That is a fact about the corpus rather than about the candidate, and it
names exactly what would change the answer: a filer reporting
`ShortTermBorrowings` *and* a declared current-side concept *and* silent for
`debt`. Zero such filers exist among 75.

### Two flaws in my own conditions, caught before they became conclusions

**Condition 3 tested presence rather than reproducibility.** The first run
returned SUPPORTED because the relationship table was non-empty. Every wrong
verdict in 2.29 came from a condition a plausible-looking list satisfied; this
was the same mistake wearing a different hat. "Reproducible" now means *one
direction accounts for at least 90% of comparable periods, across at least two
filers*.

**The comparator's definition was sampled from a document that lacks it**, and
came back `None`, which would have made condition 2 pass vacuously. It is now read
from a document that actually carries the comparator.

---

## C. What is established, and what this does not do

**Established.** The candidate is a genuine outstanding-carrying-amount debt
concept, by its own SEC definition — condition 1 is not in doubt. It is
period- and unit-compatible with a debt balance. It is **complementary to, not
nested within, the declared current side** — they partition current debt, and the
inversions are the signature of that rather than of an unstable identity. And it
**cannot be tested in the population that would use it**, because every filer
silent for `debt` reports no current-side concept to compare against.

**Not established.** That `ShortTermBorrowings` *is* the current side, contains
it, or is contained by it — its own definition says otherwise. That it belongs to
`long_term_debt_current`, to `debt`, or to neither. That its presence in 11
silent filers would close Proposition B.

**Not attempted, deliberately.** No mapping was changed and no candidate was
promoted. Even had C returned SUPPORTED, the result would have been
`ShortTermBorrowings -> current-side *candidate*`, which is a weaker and different
proposition from `ShortTermBorrowings -> EXACT long_term_debt_current`.

And the composition question remains open underneath all of it. `debt` is declared
as current + non-current so a filer's own split can be assembled. If the candidate
is a *sibling* of the current side rather than the current side itself, then the
natural end state is

```
debt
├── LongTermDebtCurrent
├── LongTermDebtNoncurrent
└── ShortTermBorrowings
```

which **changes what `debt`'s composition means**, not merely widens its coverage.
A filer's current debt would be `ShortTermBorrowings + LongTermDebtCurrent`, which
no current mapping expresses. That is a separate decision about the composition,
and it is not this round's.

---

## D. The method, and the reason it is reusable

2.29 established that `label`, period shape and frequency can **generate**
candidates and can never **establish** one. 2.30 is the first test of a single
candidate against an accounting identity, and the shape of it is what should be
reused:

1. **Start from one named candidate.** No search, so no shortlist to be wrong in a
   new way each pass.
2. **Read the two definitions side by side.** The distinction between the candidate
   and its comparator is entirely in the prose, and it is what says they are
   different quantities.
3. **Pre-register what each condition means, including the direction.** Equality
   was never the hypothesis; a direction was, and the direction failed.
4. **Make the competing interpretation a measured condition.** Not an afterthought
   — if `ShortTermBorrowings` is at or above the comparator everywhere, then "it is
   the parent, not the current side" explains the observations and wins.
5. **Fail a condition on absence of evidence, not on presence of a plausible list.**

---

## E. The next proposition, if there is one

The failing condition was mis-specified — it asked for nesting where the
definitions describe complementarity — and correcting it makes the *next*
proposition obvious and different:

> **Is a filer's current debt `ShortTermBorrowings + LongTermDebtCurrent`?**

That is a statement about the composition, not about one concept, and it is
testable from what is held: for every filer reporting both, does the sum behave
like the current portion of total debt across periods, and does it stop being
needed where either component is absent?

It also cannot be answered by fetching more filers, because the filers needed are
the ones that report nothing for `debt` and are silent on both components — and
those are the 11 whose comparator is absent by construction.

**The honest position is that `debt` is under-specified as a composition.** It is
declared as current + non-current, and there is a third current-liability concept
that is common in the corpus and that no mapping reaches. Whether that means the
composition is wrong or that a fourth representation of the parent is needed is a
real question, and 2.29 and 2.30 together have narrowed it to exactly that — with
both halves of the original compound proposition kept apart.

## F. State

| | |
| --- | --- |
| full suite | **714 run, 640 passed, 74 skipped**, unchanged |
| production files changed | **none** |
| fetched | **nothing** |
| registry / mappings / coverage / applicability | **unchanged** |
| refusal surface | empty; audit green |
| commits | 2.27 at `7cb5e27`; 2.28–2.30 not committed |

`short_term_borrowings_230.py` is read-only and writes
`harness/230-short-term-borrowings.json`, including every comparable period and
its ratio, so the 10 inversions can be inspected rather than taken on trust.