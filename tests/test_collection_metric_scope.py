"""
A canonical collection run asks the registry which metrics are active.

## The rule being pinned

`status = 'ACTIVE'` is the status predicate this project applies everywhere it
enumerates the metric universe: the coverage universe, the cross-framework verifier
and the evidence surface each run the same query. A collection run is another such
consumer, so it runs it too:

    canonical_metrics = registry enumeration WHERE status = 'ACTIVE'
    Ingestor.ingest(..., metrics=canonical_metrics)

The alternative -- letting `Ingestor.ingest` fall back on its own parameter default
-- was the implicit behaviour of three tracked orchestration callers.
`sec_ingest.DEFAULT_METRICS` still names `debt`, the metric 2.33 superseded, and it
omits thirteen metrics the canonical universe contains. So a default-driven run
asked for a metric outside the universe while leaving thirteen unasked.

## Which callers, and why not more

Three, and the exclusions are asserted rather than assumed:

    ingest_universe          passed `metrics=DEFAULT_METRICS`
    merge_sources            passed `metrics=DEFAULT_METRICS`, and `metrics=
                             FULL_CORE_METRICS` -- a frozen pre-2.33 list naming
                             the superseded key
    harness/snapshot.py      passed `metrics=metrics or DEFAULT_METRICS`

`build_crossframework_snapshot.py` also mentions `DEFAULT_METRICS`, but it defines
its own deliberately narrowed 2.7 constant and imports only `Ingestor`: a run that
quietly tests more than it says is a run whose scope nobody wrote down.
`fullscope_bulk.py` and `reconcile_bulk.py` construct an `Ingestor` too, and pass an
explicit list. None of the three is a canonical collection caller.

## Why the enumeration is a query and not a frozen tuple

`merge_sources.FULL_CORE_METRICS` is the counter-example, and it is still in the
tree because `fullscope_bulk` imports it to compare three metric-list definitions
against the registry seed and raise when they disagree. That comparison is the
detector for exactly this class of drift. It is also the proof: that list is a
frozen twenty names whose sole disagreement with the canonical universe is the
superseded key, because a frozen list and a registry can only agree until the
registry moves.

So the tests include one that changes the ACTIVE set **at run time** and asserts the
callers follow it with no source edit. A hard-coded twenty would pass every other
assertion in this file and fail that one.

## What these tests do not do

No collection run over a real archive, no network, no SEC request, no download.
Every archive is `:memory:`. Where an ingest is exercised at all it is driven by a
local fixture source, so the assertion is about the metric scope reaching the
writer rather than about any figure.
"""

from __future__ import annotations

import inspect
import io
import os
import re
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
HARNESS = os.path.join(
    ROOT, "experiments", "003-llm-evidence-retrieval", "harness")
if HARNESS not in sys.path:
    sys.path.insert(0, HARNESS)

import ingest_universe  # noqa: E402
import merge_sources  # noqa: E402
import reconcile_bulk  # noqa: E402
import sec_ingest  # noqa: E402
import snapshot as harness_snapshot  # noqa: E402
from core_registry import CoreRegistry  # noqa: E402
from registry_seed import seed  # noqa: E402
from sqlite_archive import SQLiteArchive  # noqa: E402

LEGACY = "debt"
SUCCESSOR = "long_term_debt"

# Imported by name rather than looked up in sys.modules, because the harness module
# is bound to a local alias here and lives under a different key in sys.modules.
CALLERS = {
    "ingest_universe": ingest_universe,
    "merge_sources": merge_sources,
    "reconcile_bulk": reconcile_bulk,
    "harness_snapshot": harness_snapshot,
}

SOURCES = {
    "ingest_universe": os.path.join(ROOT, "ingest_universe.py"),
    "merge_sources": os.path.join(ROOT, "merge_sources.py"),
    "reconcile_bulk": os.path.join(ROOT, "reconcile_bulk.py"),
    "harness_snapshot": os.path.join(HARNESS, "snapshot.py"),
}

# Modules that construct an Ingestor but are not canonical callers. The exclusion
# is asserted below, so the scope is a decision on record rather than an assumption.
#
# `reconcile_bulk` was in this set and was wrong. It never named the constant --
# it called `.ingest(ticker)` with no `metrics=` at all -- which is the same
# implicit-default defect, in a different disguise. The source-level test below is
# what found it.
NOT_CANONICAL = {
    "build_crossframework_snapshot": "defines its own narrowed 2.7 constant",
    "fullscope_bulk": "passes an explicit list; the default appears only in an audit",
}

DEFAULT_METRICS_BEFORE = (
    "revenue", "net_income", "eps_diluted", "assets", "cash", "debt", "capex",
    "shares_outstanding",
)


def active_metric_ids(registry: CoreRegistry) -> tuple:
    """The predicate written out, so a test does not have to trust a helper."""
    return tuple(
        row["metric_id"]
        for row in registry.connection.execute(
            "SELECT metric_id FROM metric_registry WHERE status = 'ACTIVE'"
            " ORDER BY metric_id"
        )
    )


def fresh() -> tuple:
    store = SQLiteArchive(":memory:")
    registry = CoreRegistry(store.connection)
    seed(registry)
    store.connection.commit()
    return store, registry


class CanonicalEnumeration(unittest.TestCase):
    """Every canonical caller enumerates the registry instead of naming a list."""

    def test_the_registry_declares_twenty_active_metrics(self) -> None:
        store, registry = fresh()
        try:
            self.assertEqual(len(active_metric_ids(registry)), 20)
        finally:
            store.close()

    def test_every_caller_returns_the_active_enumeration(self) -> None:
        store, registry = fresh()
        try:
            expected = active_metric_ids(registry)
            for name, module in CALLERS.items():
                with self.subTest(caller=name):
                    self.assertEqual(module.canonical_metrics(registry),
                                     expected)
        finally:
            store.close()

    def test_the_enumeration_excludes_the_superseded_key(self) -> None:
        store, registry = fresh()
        try:
            for name, module in CALLERS.items():
                with self.subTest(caller=name):
                    self.assertNotIn(LEGACY, module.canonical_metrics(registry))
        finally:
            store.close()

    def test_the_enumeration_includes_the_canonical_successor(self) -> None:
        store, registry = fresh()
        try:
            for name, module in CALLERS.items():
                with self.subTest(caller=name):
                    self.assertIn(SUCCESSOR, module.canonical_metrics(registry))
        finally:
            store.close()

    def test_the_enumeration_is_not_the_ingestion_default(self) -> None:
        store, registry = fresh()
        try:
            canonical = set(active_metric_ids(registry))
            default = set(sec_ingest.DEFAULT_METRICS)
            self.assertNotEqual(canonical, default)
            self.assertIn(LEGACY, default)
            self.assertNotIn(LEGACY, canonical)
            self.assertLess(len(default & canonical), len(canonical))
        finally:
            store.close()


class TheEnumerationFollowsTheRegistry(unittest.TestCase):
    """
    The anti-hard-coding test.

    A caller handed the current twenty names as a tuple would pass every other
    assertion here and fail this one. No source edit is made to prove it.
    """

    def test_deprecating_a_metric_changes_the_runtime_set(self) -> None:
        store, registry = fresh()
        try:
            for name, module in CALLERS.items():
                with self.subTest(caller=name):
                    before = module.canonical_metrics(registry)
                    registry.connection.execute(
                        "UPDATE metric_registry SET status = 'DEPRECATED'"
                        " WHERE metric_id = ?", ("r_and_d",))
                    registry.connection.commit()
                    try:
                        after = module.canonical_metrics(registry)
                        self.assertEqual(len(after), len(before) - 1)
                        self.assertNotIn("r_and_d", after)
                    finally:
                        registry.connection.execute(
                            "UPDATE metric_registry SET status = 'ACTIVE'"
                            " WHERE metric_id = ?", ("r_and_d",))
                        registry.connection.commit()
        finally:
            store.close()

    def test_promoting_the_superseded_key_changes_the_runtime_set(self) -> None:
        store, registry = fresh()
        try:
            for name, module in CALLERS.items():
                with self.subTest(caller=name):
                    before = set(module.canonical_metrics(registry))
                    registry.connection.execute(
                        "UPDATE metric_registry SET status = 'ACTIVE'"
                        " WHERE metric_id = ?", (LEGACY,))
                    registry.connection.commit()
                    try:
                        after = set(module.canonical_metrics(registry))
                        self.assertEqual(after - before, {LEGACY})
                    finally:
                        registry.connection.execute(
                            "UPDATE metric_registry SET status = 'DEPRECATED'"
                            " WHERE metric_id = ?", (LEGACY,))
                        registry.connection.commit()
        finally:
            store.close()

    def test_the_helper_carries_no_metric_names(self) -> None:
        """
        The helper's body is a query. If someone pasted the twenty names into it,
        the string literals would show up here.
        """
        for name, module in CALLERS.items():
            source = inspect.getsource(module.canonical_metrics)
            with self.subTest(caller=name):
                body = source.split('"""')[-1]
                self.assertNotIn("debt", body.replace(
                    "`debt` is DEPRECATED and permanently closed", ""))
                self.assertNotIn("revenue", body)
                self.assertNotIn("net_income", body)
                self.assertIn("status = 'ACTIVE'", source)


class NoCallerFallsBackOnTheDefault(unittest.TestCase):
    """
    Source-level, because the fallback was invisible at the call site.

    The defect was never that a caller named `DEFAULT_METRICS`; it was that a caller
    omitted `metrics=` and let the parameter default apply. So this checks both: the
    import is gone, and no `ingest(` call can fall through to the default.
    """

    def test_no_canonical_caller_imports_the_ingestion_default(self) -> None:
        for name, path in SOURCES.items():
            with io.open(path, encoding="utf-8") as handle:
                text = handle.read()
            with self.subTest(caller=name):
                self.assertNotRegex(
                    text, r"from sec_ingest import[^\n]*DEFAULT_METRICS")
                self.assertNotRegex(
                    text, r"from sec_ingest import[^\n]*\bDEFAULT_METRICS\b")

    def test_no_ingest_call_omits_the_metrics_keyword(self) -> None:
        for name, path in SOURCES.items():
            with io.open(path, encoding="utf-8") as handle:
                lines = handle.read().splitlines()
            sites = [index for index, line in enumerate(lines)
                     if re.search(r"\.ingest\s*\(", line)]
            self.assertTrue(sites, "%s has no ingest call site" % name)
            for index in sites:
                window = " ".join(lines[index:index + 4])
                self.assertIn(
                    "metrics=", window,
                    "%s:%d can fall through to the default"
                    % (name, index + 1))

    def test_no_collection_call_uses_the_frozen_core_list(self) -> None:
        with io.open(SOURCES["merge_sources"], encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        for index, line in enumerate(lines):
            if not re.search(r"\.ingest\s*\(|^\s*ticker, metrics=", line):
                continue
            with self.subTest(line=index + 1):
                self.assertNotIn("FULL_CORE_METRICS", line)

    def test_the_default_itself_is_untouched(self) -> None:
        self.assertEqual(tuple(sec_ingest.DEFAULT_METRICS),
                         DEFAULT_METRICS_BEFORE)

    def test_the_default_definition_is_untouched_in_the_working_tree(self) -> None:
        """
        The source-level half of `DEFAULT_METRICS` being read-only.

        This used to assert that `sec_ingest.py` had no diff at all, which was a
        proxy for the claim rather than the claim itself: it forbade any edit to
        the file, so a later round with an unrelated reason to touch the ingest
        path failed a test about a constant. 3.16 had exactly that -- it fixed
        `ingestion_scope.observations_stored` in the same file.

        So the assertion is narrowed to what it means: no changed line may touch
        `DEFAULT_METRICS`. Everything else in the file is free to move.
        """
        result = subprocess.run(
            ["git", "diff", "-U0", "--", "sec_ingest.py"],
            cwd=ROOT, capture_output=True, text=True, check=False)
        changed = [line for line in result.stdout.splitlines()
                   if (line.startswith("+") or line.startswith("-"))
                   and not line.startswith(("+++", "---"))
                   and "DEFAULT_METRICS" in line]
        self.assertEqual(
            changed, [],
            "DEFAULT_METRICS is read-only for this work; these lines changed it:\n"
            + "\n".join(changed))

    def test_the_three_non_canonical_callers_still_pass_explicit_lists(
            self) -> None:
        """
        The exclusion is a decision on record, so it is asserted rather than
        assumed: each of these passes an explicit metric list at every call site.
        """
        for name in NOT_CANONICAL:
            path = os.path.join(ROOT, "%s.py" % name)
            with io.open(path, encoding="utf-8") as handle:
                lines = handle.read().splitlines()
            sites = [index for index, line in enumerate(lines)
                     if re.search(r"\.ingest\s*\(", line)]
            self.assertTrue(sites, "%s has no ingest call site" % name)
            for index in sites:
                window = " ".join(lines[index:index + 4])
                with self.subTest(module=name, line=index + 1):
                    self.assertIn("metrics=", window)


class HistoricalIdsAreNotRewritten(unittest.TestCase):
    """
    A canonical run writes new rows under canonical ids; it does not re-key old
    ones. 2.33 made `observations.metric` immutable, and this is the regression
    guard for that reached from the collection side.
    """

    def test_the_legacy_key_still_resolves_to_its_successor(self) -> None:
        store, registry = fresh()
        try:
            self.assertEqual(registry.resolve_metric(LEGACY), SUCCESSOR)
            self.assertIn(LEGACY, registry.superseded_metric_ids())
        finally:
            store.close()

    def test_a_stored_legacy_row_keeps_its_id(self) -> None:
        """
        Written through the production writer, so the row is one the collection
        path could actually produce. Its id must survive any canonical run.
        """
        from sec_provider import Observation
        store, registry = fresh()
        try:
            store.record_asset("TESTCO", cik="0000000001", name="Test Co")
            store.record_observation("TESTCO", Observation(
                observation_id="obs_test",
                metric=LEGACY,
                value=1.0,
                unit="USD",
                currency="USD",
                currency_basis="AS_REPORTED",
                period_start="2024-01-01",
                period_end="2024-12-31",
                as_of="2024-12-31",
                available_at="2025-02-01T00:00:00+00:00",
                available_at_basis="ACCEPTANCE_DATETIME",
                provider="SecEdgar",
                source_type="REGULATORY_FILING",
                source_url=None,
                definition="a long-term debt balance",
                methodology="as reported in 10-K accession 0000000000-25-000001",
                retrieved_at="2026-01-01T00:00:00+00:00",
            ))
            store.connection.commit()
            metrics = ingest_universe.canonical_metrics(registry)
            self.assertNotIn(LEGACY, metrics)
            row = store.connection.execute(
                "SELECT observation_id, metric FROM observations"
                " WHERE metric = ?", (LEGACY,)).fetchone()
            self.assertIsNotNone(row, "the legacy row was not stored at all")
            self.assertEqual(row["metric"], LEGACY)
            self.assertEqual(registry.resolve_metric(row["metric"]), SUCCESSOR)
        finally:
            store.close()

    def test_a_fixture_ingest_writes_only_canonical_ids(self) -> None:
        """No network: a local bulk source, an in-memory archive, one filer."""
        facts_dir = _bulk_facts_dir()
        if facts_dir is None:
            self.skipTest("no local companyfacts fixture directory available")
        import sec_bulk
        store, registry = fresh()
        try:
            source = sec_bulk.BulkFactsSource(facts_dir, label="test")
            ticker = _resolvable_ticker(source)
            if ticker is None:
                self.skipTest("fixture source resolves no issuer")
            metrics = ingest_universe.canonical_metrics(registry)
            sec_ingest.Ingestor(store, source, registry).ingest(
                ticker, metrics=metrics)
            written = {row[0] for row in store.connection.execute(
                "SELECT DISTINCT metric FROM observations")}
            self.assertNotIn(LEGACY, written)
            self.assertTrue(
                written.issubset(set(metrics)),
                "wrote outside the canonical scope: %s"
                % sorted(written - set(metrics)))
        finally:
            store.close()


class RegistryIsUnchanged(unittest.TestCase):
    """The enumeration reads the registry; it does not write to it."""

    TABLES = ("metric_registry", "metric_concept_mapping", "concept_registry",
              "metric_supersession", "observations", "derived_values",
              "interpretations", "ingestion_runs", "ingestion_scope")

    def test_enumerating_changes_no_row(self) -> None:
        store, registry = fresh()
        try:
            before = {table: store.connection.execute(
                "SELECT count(*) FROM %s" % table).fetchone()[0]
                for table in self.TABLES}
            for module in CALLERS.values():
                module.canonical_metrics(registry)
            after = {table: store.connection.execute(
                "SELECT count(*) FROM %s" % table).fetchone()[0]
                for table in self.TABLES}
            self.assertEqual(before, after)
        finally:
            store.close()

    def test_enumerating_writes_no_observation_or_run(self) -> None:
        store, registry = fresh()
        try:
            for module in CALLERS.values():
                module.canonical_metrics(registry)
            for table in ("observations", "ingestion_runs", "ingestion_scope",
                          "source_documents", "held_filings"):
                self.assertEqual(store.connection.execute(
                    "SELECT count(*) FROM %s" % table).fetchone()[0], 0,
                    table)
        finally:
            store.close()


class AuditDataIsPreserved(unittest.TestCase):
    """
    `fullscope_bulk` imports `FULL_CORE_METRICS` to compare three metric-list
    definitions against the registry seed and raise when they disagree. That
    comparison is the detector for this class of drift, so removing the constant
    would have removed the detector rather than fixed anything.
    """

    def test_the_frozen_list_is_still_importable(self) -> None:
        import fullscope_bulk
        self.assertEqual(len(fullscope_bulk.FULL_CORE_METRICS), 20)
        self.assertEqual(len(merge_sources.FULL_CORE_METRICS), 20)
        self.assertIn(LEGACY, merge_sources.FULL_CORE_METRICS,
                      "the retained list is the pre-2.33 copy, closed key and "
                      "all; it is audit data, not a collection scope")

    def test_every_module_depending_on_a_changed_module_still_imports(self) -> None:
        tracked = subprocess.run(
            ["git", "ls-files", "*.py"], cwd=ROOT, capture_output=True,
            text=True, check=False).stdout.splitlines()
        dependents: list = []
        for rel in sorted(t for t in tracked if t.strip().endswith(".py")):
            path = os.path.join(ROOT, rel.replace("/", os.sep))
            if not os.path.exists(path):
                continue
            if os.path.basename(rel) == "__main__.py":
                continue  # a package entry point is not importable by name
            parts = rel.split("/")
            if len(parts) > 1:
                # A path is importable as a dotted name only when its leading
                # directory is a real package. `tests/` has no `__init__.py`, so
                # `tests.test_x` is not a module -- and this file lives there, so
                # probing it would fail once it is tracked.
                if not os.path.exists(os.path.join(ROOT, parts[0],
                                                   "__init__.py")):
                    continue
            with io.open(path, encoding="utf-8") as handle:
                text = handle.read()
            names_any = any(name in text for name in
                            ("merge_sources", "ingest_universe",
                             "reconcile_bulk"))
            harness_snapshot_user = (
                rel.startswith("experiments/003-llm-evidence-retrieval"
                               "/harness/")
                and "import snapshot" in text)
            if not (names_any or harness_snapshot_user):
                continue
            dotted = rel[:-3].replace("/", ".")
            if dotted.endswith(".__init__"):
                dotted = dotted[:-9]
            dependents.append((rel, dotted))
        self.assertTrue(dependents, "found no dependent modules to probe")
        environment = dict(os.environ)
        environment["PYTHONPATH"] = os.pathsep.join(
            [ROOT, HARNESS, environment.get("PYTHONPATH", "")])
        broken: list = []
        for rel, dotted in dependents:
            result = subprocess.run(
                [sys.executable, "-c", "import " + dotted],
                cwd=ROOT, capture_output=True, text=True, env=environment,
                timeout=120)
            if result.returncode != 0:
                broken.append("%s: %s" % (rel, result.stderr.strip()[-200:]))
        self.assertEqual(broken, [], "modules failing to import: %s" % broken)


def _bulk_facts_dir():
    for name in ("bulkfacts-universe", "bulkfacts-227b", "bulkfacts",
                 "bulkfacts-227a"):
        path = os.path.join(HARNESS, name)
        if os.path.isdir(path) and any(
                entry.endswith(".json") for entry in os.listdir(path)):
            return path
    return None


def _resolvable_ticker(source):
    for name in sorted(getattr(source, "_tickers", {}) or {}):
        if source.resolve_company(name) is not None:
            return name
    return None


if __name__ == "__main__":
    unittest.main()