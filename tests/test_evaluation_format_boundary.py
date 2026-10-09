"""
The evaluation answer format must not reach production modules.

## Why this file exists, separated from `test_eval_harness.py`

`tests/test_eval_harness.py` tested the grading harness of the LLM evidence
retrieval experiment. That experiment was archived at `b124123`
("archive: remove experiment 003 from current tree"), which removed 646 files
under `experiments/003-llm-evidence-retrieval/` and left the harness test module
in `tests/`. It has therefore been uncollectable since that commit: nine
module-level imports resolve into the archived `harness` package, and the
corpora the suite needed went with the same commit.

It is archived, not repaired. Making it run again would mean restoring the
archived experiment, which is the opposite of what `b124123` decided.

Two of its assertions did not belong to the harness at all. They assert
properties of `evidence_query.py` and `sqlite_archive.py`, which are **active
production modules** in this repository, and no other tracked test covers them.
Deleting the module outright would have dropped that boundary silently, so the
two are kept here, verbatim, against the same production modules.

The rest of that suite -- auditor checks, probe grading, consumer
classification, reporting, budget and provider handling -- tested archived code
and is no longer part of this repository's test coverage. It has **not** been
shown to pass here and is not claimed to. Its original content is preserved
verbatim in Git at `b8543d0:tests/test_eval_harness.py`.

## What is being guarded

The harness defined a structured answer: an `answer` string plus `evidence_refs`,
and later a probe layer adding `claim_type`, `semantic_state`, `stated_value` and
`operation_ref`. None of that is ST-EVA. It is an evaluation format, and the
hazard is that someone later grows one of those fields on the query surface or
the archive because "it would be useful there" -- at which point the model's
answers would be scoring against a format the product itself already speaks, and
the evaluation would no longer be measuring anything.

`reason_code` is deliberately not on the forbidden list: it is the archive's own
field, emitted by `coverage_report` and in every observation's status block. A
name collision between an evaluation format and a fact the archive genuinely
holds is not a leak.

## Absent is not the same as checked

Both assertions read module source and need no corpus and no network, so unlike
the rest of the archived suite they run everywhere, including a clean checkout.
"""

from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class TheEvaluationFormatStaysOutOfProduction(unittest.TestCase):
    """The structured answer is an evaluation format, not an archive field."""

    def test_the_contract_is_not_part_of_st_eva(self):
        """
        The structured answer must not leak into production semantics.
        """
        import evidence_query
        import sqlite_archive

        for module in (evidence_query, sqlite_archive):
            source = open(module.__file__, encoding="utf-8").read()
            for field in ("evidence_refs", "derived_refs", "uncertainties"):
                self.assertNotIn(
                    field, source,
                    f"{module.__name__} grew {field}; the evaluation format "
                    "must not become part of the archive or the query surface",
                )

    def test_the_probe_answer_shape_is_not_the_archive_answer_shape(self):
        """
        The probe's field set, together, is the thing that must not appear.

        One of a pair appearing is fine -- any of these could plausibly be an
        archive concept name. The pair appearing *together* is the shape of an
        evaluation answer, and that is what the check refuses.
        """
        import evidence_query

        source = open(evidence_query.__file__, encoding="utf-8").read()
        for group in (
            ("claim_type", "semantic_state"),
            ("operation_ref", "stated_value"),
        ):
            present = [name for name in group if name in source]
            self.assertLessEqual(
                len(present), 1,
                f"{present} appear together in the query surface, which is the "
                "shape of an evaluation answer",
            )


if __name__ == "__main__":
    unittest.main()