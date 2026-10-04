"""
ST-EVA 3.01 -- token selection for metric candidate discovery.

## What lives here and why it is here

This module owns one decision and nothing else:

> when a source concept's name is tokenised for candidate discovery, which of
> its tokens are searched for.

It exists as production code because the rule was wrong, and being wrong was
invisible. It was previously implemented inside the 2.77 research round and was
therefore untracked, unversioned and untested by anything the repository
committed -- which is how a defect that removed 223 candidates from one metric
and 598 and 409 from two others could sit in the tree through a production
commit without a single test failing.

Nothing here reads the corpus, opens an archive, writes a mapping or decides
anything about accounting meaning. It is a pure function of a metric's mapped
concepts and a caller-supplied set of informative tokens, and it is the only
place the fallback rule is written down.

## The invariant

    D(R1) is a subset of D(R2)      where R2 = R1 + one additional mapped concept

An added concept may add discovery signal. It may not erase existing signal.

## The defect this module exists to prevent

The discriminating-token filter exists for precision: a token occurring in more
than 1% of the held vocabulary identifies nothing, so it is dropped from
generation. The fallback exists for recall: if filtering leaves a concept with
nothing to search on, search on something rather than nothing.

The rule used to be tested against the metric's **union** of mapped-concept
tokens, which made the two interfere:

    a_metric_tokens = (union of tokens(c) for c in mapped) & informative
    token_fallback  = not a_metric_tokens          <-- all-or-nothing

A union that can do *something* is not the same as every member being able to.
While `sbc` had one mapped concept, all three of its tokens were filtered away,
the union filtered to empty, the fallback fired, and both lexical channels
searched on all three. Production commit `b02e932` then gave `sbc` a second
mapped concept whose tokens include exactly one discriminating token. The union
became non-empty, which switched the fallback off for **every** mapped concept --
including the first one, whose tokens the same filter had already emptied.

Measured, on the real corpus: `sbc` discovery fell from 224 candidates to 17,
`long_term_debt_current` from 643 to 45, and `long_term_debt_noncurrent` from
447 to 38. All 223, 598 and 409 lost candidates left with no documented filter
behind them. The debt metrics had been silently losing recall all along and were
never noticed; `sbc` was merely the first metric where a promotion made it
visible.

## The rule, stated once

    for each mapped concept:
        keep the tokens the filter kept; if the filter kept none, keep them all
    the metric's effective set is the union of those

Read globally this is also "every discriminating token, plus the fallback tokens
of any concept the filter emptied" -- so the union reading and the per-concept
reading are the same function, not two competing designs.

It is not a loosening of the filter. A concept with usable tokens still searches
on those alone; only a concept the filter would have silenced gets to speak
again. And it is monotone by construction: the effective set is a union over
mapped concepts, so adding one adds a term and cannot remove one.

## What is deliberately not decided here

Channel selection, the definition-text channel, alias channels, the union of
candidates, every gate, threshold and ordering, and any judgement about whether
a candidate means the metric. Those belong to `discover()` and are unchanged by
3.01. The only behavioural change is the one named above: **the fallback is
evaluated per mapped concept rather than globally for the metric.**
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Set, Tuple

# Tokens used ONLY to generate candidates. Splitting a concept name into words is
# a retrieval aid and nothing more.
STOP = {"and", "of", "for", "to", "the", "in", "on", "a", "an", "or"}

# A token this short carries no discriminating power and collides with ordinary
# English, so it is never a search term.
MIN_TOKEN_LENGTH = 4


def tokens(*names: str) -> Set[str]:
    """
    Split concept names into lowercase search tokens.

    CamelCase is split rather than the whole string lowercased, so
    `ShareBasedCompensation` yields `share`, `based`, `compensation` and not one
    opaque token. Only the LOCAL name is ever passed here: the taxonomy prefix is
    not part of what a concept is about, and an earlier version of the research
    matched `ifrs-full:ResearchAndDevelopmentExpense` whole, which contributed
    `ifrs` and `full` and then pulled oil and gas depletion into a research and
    development candidate pool on the strength of "full cost method".
    """
    out: Set[str] = set()
    for name in names:
        for part in re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z]+|[a-z]+", name):
            low = part.lower()
            if len(low) >= MIN_TOKEN_LENGTH and low not in STOP:
                out.add(low)
    return out


def effective_metric_tokens(
        mapped: Iterable[str],
        informative: Set[str],
) -> Tuple[Set[str], List[Dict[str, Any]]]:
    """
    The tokens a metric's mapped concepts contribute to its lexical channels,
    plus an account of how each one arrived there.

    `mapped` is the metric's mapped concept ids; `informative` is the set of
    tokens the caller's frequency filter kept. The filter is applied per concept
    and the fallback rescues only the concepts it emptied.

    Returns the union, and one report row per mapped concept recording its tokens,
    which of them the filter kept, which it discarded, whether the fallback was
    needed, and what it contributed. The report is part of the result rather than
    a diagnostic extra, because the failure this module prevents was invisible:
    a rule that decides what is searched for, silently, produced a pool that was
    non-empty and a metric that looked ready while 223 candidates were missing.

    An empty `mapped` yields an empty set and an empty report. That state is real
    -- `debt` is in it today -- and must not raise.
    """
    effective: Set[str] = set()
    report: List[Dict[str, Any]] = []
    for concept in mapped:
        raw = tokens(concept.partition(":")[2])
        kept = raw & informative
        # `kept or raw`: the filter gets to speak whenever it has something to
        # say, and the fallback gets to speak only for the concept the filter
        # silenced. Deciding this per concept is the whole fix.
        effective |= (kept or raw)
        report.append({
            "concept_id": concept,
            "tokens": sorted(raw),
            "discriminating": sorted(kept),
            "filtered_out": sorted(raw - kept),
            "token_fallback_used": not kept,
            "effective": sorted(kept or raw),
        })
    return effective, report


if __name__ == "__main__":  # pragma: no cover
    print("effective_metric_tokens owns the discovery token-selection rule.")
    print("See tests/test_metric_discovery_tokens_301.py for the contract.")