"""
3.31 Commit A -- tests for the two admission state identities.

These pin the properties the identities are for, and three of them are the
properties that 3.29 measured as necessary:

  * a semantic change must move the registry identity
  * a storage accident must not
  * a code change must move the policy identity

The registry cases build a throwaway archive with `seed()` and then perturb one
thing at a time, so each test names the single property it is about. The policy
cases read from a temporary copy of the tree rather than the repository, so a
test can change a covered file's bytes without touching production code.
"""

import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

import registry_identity
from archive import REPLAY_DIVERGED, REPLAY_MATCH, replay
from core_registry import CoreRegistry
from registry_identity import (
    _POLICY_FILES,
    POLICY_PREFIX,
    registry_state_identity,
    resolver_policy_identity,
)
from registry_seed import seed
from sqlite_archive import SQLiteArchive
from st_eva_runner import build_context_from_observations

from test_replay_evidence_symmetry import (  # noqa: E402  frozen fixtures, reused
    CMP_ID,
    price,
    replay_doc,
    sec_net_income,
)
from evidence_valuation_boundary import V1_CROSSING_METRICS, admit


class RegistryIdentityFixture(unittest.TestCase):
    """A temporary archive with the real registry seeded into it."""

    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.path = str(Path(self._directory.name) / "identity.sqlite")
        self.store = SQLiteArchive(path=self.path)
        seed(CoreRegistry(self.store.connection))

    def tearDown(self) -> None:
        self.store.close()
        self._directory.cleanup()

    def identity(self) -> str:
        return registry_state_identity(self.store.connection)

    def seed_rows(self) -> int:
        return self.store.connection.execute(
            "SELECT COUNT(*) FROM metric_concept_mapping"
        ).fetchone()[0]


class TestRegistryIdentityIsDeterministic(RegistryIdentityFixture):
    def test_the_same_state_gives_the_same_identity(self):
        self.assertEqual(self.identity(), self.identity())

    def test_two_separately_seeded_archives_agree(self):
        """
        Identity is a function of meaning, not of how the rows arrived.

        Two archives seeded independently must agree, or the digest identifies
        the seed run rather than the registry.
        """
        with tempfile.TemporaryDirectory() as other:
            second = SQLiteArchive(
                path=str(Path(other) / "second.sqlite")
            )
            try:
                seed(CoreRegistry(second.connection))
                self.assertEqual(
                    registry_state_identity(second.connection),
                    self.identity(),
                )
            finally:
                second.close()


class TestRegistryIdentityIgnoresStorageAccidents(RegistryIdentityFixture):
    def test_duplicated_physical_rows_do_not_change_it(self):
        """
        The defect 3.31 found: `metric_concept_mapping` declares
        `PRIMARY KEY (metric_id, concept_id, effective_from)` and
        `effective_from` is nullable, so SQLite enforces no uniqueness for an
        unbounded mapping. Re-seeding inserts the unbounded rows a second time.
        The MU pilot archive holds 74 physical rows for 50 distinct mappings as
        a result, and an identity that changed with the seed count would be
        identifying the build rather than the registry.
        """
        before = self.identity()
        self.store.connection.execute(
            "INSERT INTO metric_concept_mapping (metric_id, concept_id,"
            " mapping_type, effective_from, effective_to, notes, relation_kind,"
            " scope_json)"
            " SELECT metric_id, concept_id, mapping_type, effective_from,"
            " effective_to, notes, relation_kind, scope_json"
            " FROM metric_concept_mapping WHERE effective_from IS NULL"
        )
        self.store.connection.commit()
        self.assertGreater(self.seed_rows(), 50, "the duplication did not happen")
        self.assertEqual(
            self.identity(), before,
            "a second seed pass must not move the registry identity",
        )

    def test_row_order_does_not_change_it(self):
        """
        Physical order is not a property of the registry.

        The digest sorts the projected rows, so a rebuild that inserts in a
        different order describes the same state.
        """
        before = self.identity()
        rows = self.store.connection.execute(
            "SELECT metric_id, concept_id, mapping_type, effective_from,"
            " effective_to, notes, relation_kind, scope_json"
            " FROM metric_concept_mapping ORDER BY concept_id DESC"
        ).fetchall()
        self.store.connection.execute("DELETE FROM metric_concept_mapping")
        self.store.connection.executemany(
            "INSERT INTO metric_concept_mapping (metric_id, concept_id,"
            " mapping_type, effective_from, effective_to, notes, relation_kind,"
            " scope_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [tuple(row) for row in rows],
        )
        self.store.connection.commit()
        self.assertEqual(self.identity(), before)

    def test_a_reformatted_scope_json_does_not_change_it(self):
        """
        Formatting is not meaning.

        `add_mapping` writes `scope_json` with sorted keys and no whitespace,
        but an archive written by an older build, or edited by hand, can hold
        the same object rendered differently. The reader parses it, so the
        identity must too.
        """
        row = self.store.connection.execute(
            "SELECT metric_id, concept_id, effective_from FROM"
            " metric_concept_mapping WHERE scope_json IS NOT NULL LIMIT 1"
        ).fetchone()
        self.assertIsNotNone(row, "the seed declares no measured scope")
        before = self.identity()
        compact = self.store.connection.execute(
            "SELECT scope_json FROM metric_concept_mapping"
            " WHERE metric_id = ? AND concept_id = ? AND effective_from = ?",
            tuple(row),
        ).fetchone()[0]
        parsed = json.loads(compact)
        self.store.connection.execute(
            "UPDATE metric_concept_mapping SET scope_json = ?"
            " WHERE metric_id = ? AND concept_id = ? AND effective_from = ?",
            (json.dumps(parsed, sort_keys=True, indent=4), *tuple(row)),
        )
        self.store.connection.commit()
        self.assertNotEqual(
            self.store.connection.execute(
                "SELECT scope_json FROM metric_concept_mapping"
                " WHERE metric_id = ? AND concept_id = ? AND effective_from = ?",
                tuple(row),
            ).fetchone()[0],
            compact,
            "the stored text was not actually reformatted",
        )
        self.assertEqual(self.identity(), before)


class TestRegistryIdentityMovesWithMeaning(RegistryIdentityFixture):
    def test_a_mapping_type_change_moves_it(self):
        before = self.identity()
        self.store.connection.execute(
            "UPDATE metric_concept_mapping SET mapping_type = 'PARTIAL'"
            " WHERE mapping_type = 'EXACT'"
        )
        self.store.connection.commit()
        self.assertNotEqual(self.identity(), before)

    def test_a_relation_kind_change_moves_it(self):
        """
        2.73 flipped `relation_kind` on two rows covering 48 real MU facts and
        admission outcome did not move. The identity still must: a replay that
        recorded the old value has to be able to detect that the reading
        changed, even when the decision did not.
        """
        row = self.store.connection.execute(
            "SELECT metric_id, concept_id, effective_from FROM"
            " metric_concept_mapping WHERE relation_kind = 'IDENTITY' LIMIT 1"
        ).fetchone()
        self.assertIsNotNone(row, "the seed declares no relation_kind")
        before = self.identity()
        self.store.connection.execute(
            "UPDATE metric_concept_mapping SET relation_kind = 'COMPOSITION'"
            " WHERE metric_id = ? AND concept_id = ? AND effective_from = ?",
            tuple(row),
        )
        self.store.connection.commit()
        self.assertNotEqual(self.identity(), before)

    def test_a_semantic_scope_change_moves_it(self):
        row = self.store.connection.execute(
            "SELECT metric_id, concept_id, effective_from, scope_json FROM"
            " metric_concept_mapping WHERE scope_json IS NOT NULL LIMIT 1"
        ).fetchone()
        self.assertIsNotNone(row, "the seed declares no measured scope")
        metric_id, concept_id, effective_from, scope = tuple(row)
        before = self.identity()
        parsed = json.loads(scope)
        parsed["variation"] = "SOMETHING_ELSE"
        self.store.connection.execute(
            "UPDATE metric_concept_mapping SET scope_json = ?"
            " WHERE metric_id = ? AND concept_id = ? AND effective_from = ?",
            (json.dumps(parsed, sort_keys=True, separators=(",", ":")), metric_id,
             concept_id, effective_from),
        )
        self.store.connection.commit()
        self.assertNotEqual(self.identity(), before)

    def test_retiring_a_row_moves_it(self):
        """
        Retirement is the deletion of a declaration, which is how 2.99 retired
        the `us-gaap:Revenues` mapping. A digest that cannot see a deletion
        would report two different registries as one.
        """
        before = self.identity()
        self.store.connection.execute(
            "DELETE FROM metric_concept_mapping WHERE metric_id = 'revenue'"
        )
        self.store.connection.commit()
        self.assertNotEqual(self.identity(), before)

    def test_a_supersession_row_is_covered(self):
        """
        `metric_supersession` carries the supersession decision, and
        `resolve_metric` follows the chain. A digest that could not see a new
        row would report two registries as one.

        `decided_at` is not in the identity and `recorded_at` is required by
        the column, so both are supplied only to satisfy the schema; the test
        is about the decision row being covered, not about its timestamps.
        """
        before = self.identity()
        self.store.connection.execute(
            "INSERT OR REPLACE INTO metric_supersession (predecessor_id,"
            " successor_id, decided_at, reason, evidence, recorded_at)"
            " VALUES ('revenue', 'net_income', '2026-01-01', 'probe', 'probe',"
            " '2026-01-01T00:00:00+00:00')"
        )
        self.store.connection.commit()
        self.assertNotEqual(self.identity(), before)

    def test_the_supersession_decision_date_is_not_the_identity(self):
        """
        The seed stamps `decided_at` with the clock
        (`core_registry.py:1500`) and does not override it, so two archives
        seeded from the same declarations carry different values in it. If it
        were in the identity, no rebuild would ever reproduce a digest.

        The column cannot be rewritten to prove it -- `metric_supersession` is
        append-only -- so the property is asserted on the manifest itself.
        """
        columns = {
            table: cols
            for table, cols, _ in registry_identity._REGISTRY_TABLES
        }
        self.assertNotIn("decided_at", columns["metric_supersession"])
        self.assertIn("reason", columns["metric_supersession"])
        self.assertIn("evidence", columns["metric_supersession"])


class TestRegistryIdentityExcludesTheRightTables(RegistryIdentityFixture):
    def test_the_hypothesis_layer_is_not_covered(self):
        """
        `metric_exclusion` carries PROPOSED/TESTABLE/SUPPORTED states and
        `resolve_source_concept` never reads it. Including it would make a
        research decision look like a change of registry meaning.
        """
        before = self.identity()
        self.store.connection.execute(
            "INSERT OR REPLACE INTO metric_exclusion (metric_id, business_model,"
            " state, proposition, recorded_at)"
            " VALUES ('revenue', 'ANY', 'PROPOSED', 'probe',"
            " '2026-01-01T00:00:00+00:00')"
        )
        self.store.connection.commit()
        self.assertEqual(self.identity(), before)

    def test_run_metadata_is_not_covered(self):
        before = self.identity()
        self.store.connection.execute(
            "UPDATE ingestion_scope SET mapping_count = mapping_count + 1"
        )
        self.store.connection.commit()
        self.assertEqual(self.identity(), before)


class TestResolverPolicyIdentity(unittest.TestCase):
    """
    Whole-file hashing, tested against a temporary copy of the tree.

    The repository is never modified: the manifest is redirected at a
    scratch directory holding copies, so a test can change a covered file's
    bytes and prove the digest notices.
    """

    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        for name in _POLICY_FILES:
            shutil.copyfile(
                Path(registry_identity.REPO_ROOT) / name, self.root / name
            )
        self._original_root = registry_identity.REPO_ROOT
        registry_identity.REPO_ROOT = self.root

    def tearDown(self) -> None:
        registry_identity.REPO_ROOT = self._original_root
        self._directory.cleanup()

    def test_the_same_files_give_the_same_identity(self):
        self.assertEqual(
            resolver_policy_identity(), resolver_policy_identity()
        )

    def test_each_covered_file_is_covered(self):
        """
        Every file in the manifest must matter.

        A manifest with a hole in it claims a coverage it does not have, which
        is worse than a smaller honest manifest: the caller stops looking.
        """
        baseline = resolver_policy_identity()
        for name in _POLICY_FILES:
            path = self.root / name
            original = path.read_bytes()
            try:
                path.write_bytes(original + b"\n# perturbation\n")
                self.assertNotEqual(
                    resolver_policy_identity(), baseline,
                    f"{name} is in the manifest but changing it changed nothing",
                )
            finally:
                path.write_bytes(original)

    def test_the_manifest_is_declared_not_discovered(self):
        """
        The manifest is a literal in source, not a directory listing.

        A glob would silently change the identity the moment a file was added
        to the repository, which would make every unrelated new module look
        like a policy change.
        """
        self.assertIsInstance(_POLICY_FILES, tuple)
        for name in _POLICY_FILES:
            self.assertIsInstance(name, str)
            self.assertTrue(
                (Path(registry_identity.REPO_ROOT) / name).exists(),
                f"{name} is in the manifest but absent from the tree",
            )

    def test_a_reversed_manifest_is_a_different_declared_identity(self):
        """
        Reordering the manifest is a change to what is declared, so the digest
        is *supposed* to move. What must not happen is the digest depending on
        filesystem iteration order, which is covered by
        `test_the_same_files_give_the_same_identity` and by the manifest being a
        tuple. This test pins the intended direction rather than an accident.
        """
        baseline = resolver_policy_identity()
        original = registry_identity._POLICY_FILES
        try:
            registry_identity._POLICY_FILES = tuple(reversed(original))
            self.assertNotEqual(
                resolver_policy_identity(), baseline,
                "a reordered manifest is a different declaration",
            )
        finally:
            registry_identity._POLICY_FILES = original

    def test_the_manifest_names_no_duplicate(self):
        self.assertEqual(
            len(set(_POLICY_FILES)), len(_POLICY_FILES),
            "a repeated name would be hashed twice and prove nothing extra",
        )

    def test_a_missing_covered_file_is_refused(self):
        """
        A digest over six files that silently ignores a missing seventh is a
        false negative. It is refused instead.
        """
        path = self.root / "registry_seed.py"
        saved = path.read_bytes()
        try:
            path.unlink()
            with self.assertRaises(FileNotFoundError):
                resolver_policy_identity()
        finally:
            path.write_bytes(saved)

    def test_an_excluded_module_is_not_covered(self):
        """
        `sqlite_archive.py` is storage, not policy, and is reached through the
        applied-migration identity instead.
        """
        self.assertNotIn("sqlite_archive.py", _POLICY_FILES)
        self.assertNotIn("st_eva_runner.py", _POLICY_FILES)

    def test_equivalent_content_in_either_line_ending_shares_one_identity(self):
        """
        A newline convention is a property of the checkout, never of the policy.

        `core.autocrlf` is true in this repository and there is no
        `.gitattributes`, so the same commit checks out CRLF on one machine and
        LF on another. Three of the six covered files differ on exactly that
        between an operator's tree and a fresh worktree of one commit, so a
        byte digest called two identical policies different and replay asked
        for a re-run of code that had not changed.

        LF, CRLF and a lone CR all carry the same text, so all three must give
        one identity here.
        """
        saved = {name: (self.root / name).read_bytes() for name in _POLICY_FILES}
        try:
            identities = {}
            for label, transform in (
                ("LF", lambda text: text),
                ("CRLF", lambda text: text.replace("\n", "\r\n")),
                ("CR", lambda text: text.replace("\n", "\r")),
            ):
                for name, payload in saved.items():
                    text = payload.decode("utf-8").replace("\r\n", "\n")
                    (self.root / name).write_bytes(
                        transform(text).encode("utf-8")
                    )
                identities[label] = resolver_policy_identity()

            self.assertEqual(
                identities["LF"], identities["CRLF"],
                "CRLF and LF carry the same policy text",
            )
            self.assertEqual(
                identities["LF"], identities["CR"],
                "a lone carriage return is the same line ending",
            )
        finally:
            for name, payload in saved.items():
                (self.root / name).write_bytes(payload)

    def test_the_identity_is_deterministic(self):
        first = resolver_policy_identity()
        for _ in range(3):
            self.assertEqual(resolver_policy_identity(), first)
        self.assertTrue(
            first.startswith(POLICY_PREFIX),
            f"the policy digest must carry its own prefix, got {first!r}",
        )

    def test_a_meaningful_policy_change_still_moves_the_identity(self):
        """
        Neutralising newlines must not blind the digest.

        A change to a constant the resolver reads is a policy change and must
        still move the identity. This is the property that stops the
        normalisation above from being a suppression.
        """
        baseline = resolver_policy_identity()
        target = self.root / "evidence_valuation_boundary.py"
        original = target.read_text(encoding="utf-8")
        try:
            target.write_text(
                original.replace(
                    'UNAVAILABLE = "UNAVAILABLE"',
                    'UNAVAILABLE = "UNAVAILABLE_ALSO"',
                    1,
                ),
                encoding="utf-8",
            )
            self.assertIn('UNAVAILABLE = "UNAVAILABLE_ALSO"', target.read_text(encoding="utf-8"))
            self.assertNotEqual(resolver_policy_identity(), baseline)
        finally:
            target.write_text(original, encoding="utf-8")

    def test_a_change_that_is_only_a_comment_still_moves_the_digest(self):
        """
        The whole-file property, stated once more from the newline side.

        The digest is deliberately monotonic in the cheap direction: every
        change is noticed, including one that cannot alter behaviour, because
        the expensive direction of error is the other one. Appending a line
        therefore moves the digest even though the resolver reads nothing from
        it -- newline style is the single exception, and it is tested above.
        """
        baseline = resolver_policy_identity()
        target = self.root / "core_registry.py"
        original = target.read_text(encoding="utf-8")
        try:
            target.write_text(
                original + "\n# a comment the resolver never reads\n",
                encoding="utf-8",
            )
            self.assertNotEqual(resolver_policy_identity(), baseline)
        finally:
            target.write_text(original, encoding="utf-8")

    def test_the_migration_identity_is_line_ending_insensitive_too(self):
        """
        `_file_sha256` also feeds the applied-migration identity.

        With no connection the on-disk migration files are digested, and with a
        connection the checksums `sqlite_archive` recorded when it applied them
        are read back. Both are text digests now, so an LF checkout and a CRLF
        checkout agree on both branches instead of one agreeing and the other
        not, which is what a byte digest on one side and a text digest on the
        other produces.

        The migration files are mirrored into this test's own scratch
        directory, because the class fixture copies the covered modules only.
        """
        source = registry_identity.MIGRATIONS_DIR
        saved = {
            path.name: path.read_bytes()
            for path in sorted(source.glob("*.sql"))
        }
        self.assertTrue(saved, "the repository must carry migration files")

        scratch = self.root / "migrations"
        scratch.mkdir(exist_ok=True)
        saved_root = registry_identity.REPO_ROOT
        saved_migrations = registry_identity.MIGRATIONS_DIR
        try:
            identities = {}
            for label, transform in (
                ("LF", lambda text: text),
                ("CRLF", lambda text: text.replace("\n", "\r\n")),
            ):
                for name, payload in saved.items():
                    text = payload.decode("utf-8").replace("\r\n", "\n")
                    (scratch / name).write_bytes(
                        transform(text).encode("utf-8")
                    )
                registry_identity.MIGRATIONS_DIR = scratch
                identities[label] = registry_identity._applied_migrations(None)

            self.assertEqual(
                identities["LF"], identities["CRLF"],
                "migration checksums must not depend on the checkout",
            )
            self.assertEqual(
                len(identities["LF"]), len(saved),
                "every migration file must still be covered",
            )
        finally:
            registry_identity.REPO_ROOT = saved_root
            registry_identity.MIGRATIONS_DIR = saved_migrations


class TestReplayAcrossEquivalentCheckouts(unittest.TestCase):
    """
    Replay between two checkouts of one commit that differ only in newlines.

    Not hypothetical. `core.autocrlf` is true here with no `.gitattributes`, so
    an operator's tree and a fresh worktree of the same commit disagree on the
    newline convention of three of the six covered policy files. While the
    policy identity hashed bytes, that was enough to make replay report
    DIVERGED on `resolver_policy_identity` for code that had not changed.

    Two properties, and the second is the one that keeps this from being a
    suppression:

      * an LF mirror and a CRLF mirror of the same policy text give one
        identity, and a replay across them can MATCH
      * a real change to a covered file still diverges, named explicitly

    The archives are temporary and the repository is never rewritten: the
    policy trees are mirrored into a scratch directory rather than edited in
    place.
    """

    ASSET = "MU"
    AS_OF = "2026-06-30"

    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        base = Path(self._dir.name)
        self.store = SQLiteArchive(path=str(base / "replay.sqlite"))
        seed(CoreRegistry(self.store.connection))
        self.store.record_asset(
            self.ASSET, name="Micron", exchange="NASDAQ", currency="USD"
        )

        # Two mirrors of the covered policy files, identical in content and
        # opposite in newline convention, plus a third carrying a real change.
        # The migrations are mirrored too, so the applied-migration identity is
        # exercised the same way whichever branch reads it.
        self.trees = {}
        source_migrations = registry_identity.MIGRATIONS_DIR
        for label, transform in (
            ("lf", lambda text: text),
            ("crlf", lambda text: text.replace("\n", "\r\n")),
        ):
            root = base / label
            (root / "archive" / "migrations").mkdir(parents=True)
            for name in _POLICY_FILES:
                text = (
                    Path(registry_identity.REPO_ROOT) / name
                ).read_text(encoding="utf-8").replace("\r\n", "\n")
                (root / name).write_bytes(transform(text).encode("utf-8"))
            for path in sorted(source_migrations.glob("*.sql")):
                text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
                (root / "archive" / "migrations" / path.name).write_bytes(
                    transform(text).encode("utf-8")
                )
            self.trees[label] = root
        self.trees["changed"] = self._with_real_change(self.trees["lf"])

        # The recorded context and admission come from one tree, exactly as a
        # live run would store them.
        self._record_observations()
        self.stored, self.admissions = self._archive_live_run()

        self._original_root = registry_identity.REPO_ROOT
        self._original_migrations = registry_identity.MIGRATIONS_DIR

    def _with_real_change(self, source: Path) -> Path:
        target = Path(source.parent) / "changed"
        (target / "archive" / "migrations").mkdir(parents=True)
        for path in sorted((source / "archive" / "migrations").glob("*.sql")):
            shutil.copyfile(path, target / "archive" / "migrations" / path.name)
        for name in _POLICY_FILES:
            text = (source / name).read_text(encoding="utf-8")
            if name == "core_registry.py":
                text += "\n# a policy change that did not exist when this ran\n"
            (target / name).write_text(text, encoding="utf-8")
        return target

    def tearDown(self) -> None:
        registry_identity.REPO_ROOT = self._original_root
        registry_identity.MIGRATIONS_DIR = self._original_migrations
        self.store.close()
        self._dir.cleanup()

    def _record_observations(self) -> None:
        for observation, eligible in (
            (price(), True),
            # A comparable cross-check row, which is evidence and needs no
            # admission, keeps the stored context from depending on admission.
            (sec_net_income(CMP_ID), False),
        ):
            self.store.record_observation(
                self.ASSET,
                observation,
                availability_class="SOURCE_DECLARED",
                first_archived_at="2026-06-30T21:00:00.000Z",
                replay_eligible_from=(
                    "2026-06-30T20:00:00.000Z" if eligible
                    else "2025-10-03T21:02:11.000Z"
                ),
            )

    def _archive_live_run(self):
        """What a live run stores: a context over every observation, plus admission."""
        rows = self.store.observations_for(self.ASSET, self.AS_OF)
        stored = build_context_from_observations(
            rows, ticker=self.ASSET, as_of=self.AS_OF,
            generated_at="2026-06-30T21:30:00+00:00",
            asset_metadata=self.store.asset_metadata(self.ASSET),
        )
        self.store.record_context(self.ASSET, stored, replay_fidelity="SOURCE_DECLARED")
        _, admissions = admit(
            self.store, self.ASSET, self.AS_OF, price(),
            metrics=V1_CROSSING_METRICS,
        )
        reg = registry_state_identity(self.store.connection)
        for adm in admissions:
            self.store.record_admission(
                self.ASSET, self.AS_OF, adm, reg,
                resolver_policy_identity(self.store.connection), price(),
            )
        return stored, admissions

    def _under(self, label: str):
        registry_identity.REPO_ROOT = self.trees[label]
        registry_identity.MIGRATIONS_DIR = self.trees[label] / "archive" / "migrations"
        return self.trees[label]

    def test_equivalent_checkouts_agree_on_the_identity_itself(self):
        lf = self._under("lf")
        first = resolver_policy_identity(self.store.connection)
        self._under("crlf")
        second = resolver_policy_identity(self.store.connection)
        self._under("lf")

        self.assertEqual(first, second)
        # The mirrors really do differ in bytes, so this is not a vacuous pass.
        self.assertNotEqual(
            (lf / "core_registry.py").read_bytes(),
            (self.trees["crlf"] / "core_registry.py").read_bytes(),
        )

    def test_replay_across_equivalent_checkouts_can_match(self):
        """
        A stored run replayed from the other newline convention is faithful.

        The recorded admission was written from the LF mirror; the replay below
        recomputes it against the CRLF mirror. Nothing about the evidence, the
        registry, the context or the code differs, so replay must MATCH rather
        than DIVERGE on `resolver_policy_identity`.
        """
        self._under("crlf")
        result = replay(self.store, self.ASSET, self.AS_OF, replay_doc)

        self.assertEqual(REPLAY_MATCH, result.outcome, result.reason)
        self.assertNotIn("resolver_policy_identity", result.reason or "")

    def test_a_real_policy_change_still_diverges_and_is_named(self):
        """
        The normalisation does not swallow a genuine policy difference.

        A change to a covered file must still DIVERGE, and the divergence must
        name `resolver_policy_identity` rather than being absorbed into a
        faithful MATCH. Admission behaviour is untouched by this change, so the
        mismatch is the identity alone and not a side effect.
        """
        self._under("changed")
        result = replay(self.store, self.ASSET, self.AS_OF, replay_doc)

        self.assertEqual(REPLAY_DIVERGED, result.outcome, result.reason)
        self.assertIn("resolver_policy_identity", result.reason or "")



class TestHistoricalStateCorpus(unittest.TestCase):
    """
    The five-state corpus 3.29 measured, as a regression.

    Two properties are asserted, and they are the answer to the question 3.30
    asked about historical reconstruction:

      * every state's registry data identity is reconstructable
      * only HEAD's resolver policy identity is materialisable

    The second is not a defect in the identity functions. `evidence_valuation_
    boundary.py` arrived in `d032b82`, one commit before HEAD, so at the other
    four states the code that would read those registries is not in the
    repository in any form. A shim would have to supply a module that was never
    written, which means writing the admission rules afresh and reporting the
    result as history.

    The corpus is a committed artefact so that a future change to the identity
    algorithms shows up here as a diff, rather than silently reinterpreting what
    the historical states were.
    """

    ARTIFACT = (
        Path(__file__).resolve().parent.parent
        / "experiments" / "003-llm-evidence-retrieval" / "harness"
        / "331-historical-state-reconstruction.json"
    )

    @classmethod
    def setUpClass(cls) -> None:
        if not cls.ARTIFACT.exists():
            raise unittest.SkipTest(
                "run scripts/research/historical_state_reconstruction_331.py to build the corpus"
            )
        cls.corpus = json.loads(cls.ARTIFACT.read_text(encoding="utf-8"))

    def test_the_corpus_covers_the_five_states_3_29_measured(self):
        self.assertEqual(len(self.corpus["states"]), 5)

    def test_every_registry_state_is_reconstructable(self):
        for label, state in self.corpus["states"].items():
            self.assertEqual(
                state["registry"]["status"], "RECONSTRUCTABLE",
                f"{label} could not be rebuilt: "
                f"{state['registry'].get('reason')}",
            )

    def test_the_five_registry_identities_are_distinct(self):
        digests = {
            state["registry"]["registry_state_identity"]
            for state in self.corpus["states"].values()
        }
        self.assertEqual(
            len(digests), 5,
            "the digest must separate the five states rather than collapsing "
            "registry evolution",
        )

    def test_only_head_can_materialise_a_policy_identity(self):
        materialisable = [
            label for label, state in self.corpus["states"].items()
            if state["policy"]["status"] == "MATERIALIZABLE"
        ]
        self.assertEqual(materialisable, ["head"])

    def test_the_unmaterialisable_states_all_predate_the_boundary_module(self):
        for label, state in self.corpus["states"].items():
            if state["policy"]["status"] == "MATERIALIZABLE":
                continue
            self.assertIn(
                "evidence_valuation_boundary.py",
                state["policy"]["missing_from_manifest"],
                f"{label} is not materialisable for an unexpected reason, so "
                "the corpus is out of date rather than the answer having moved",
            )
            self.assertIsNone(state["policy"]["resolver_policy_identity"])


if __name__ == "__main__":
    unittest.main()
