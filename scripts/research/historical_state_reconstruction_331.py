"""
3.31 A4/A5 -- historical reconstruction of the five states 3.29 measured.

This is a research harness, not production code. Nothing here is imported by
the archive, the crossing or the replay path, and it modifies no sealed
historical artefact: every historical tree is materialised into a temporary
directory from `git show`, and every rebuild happens in a throwaway database.

The question it answers is narrow. For each state, can the two admission
identities be computed from that state's own material?

    registry_state_identity   the tables the seed declares
    resolver_policy_identity  the files that would read them

They are separate questions and 3.29's result does not transfer to either.

A finding this harness established before it ran a single rebuild:

    `evidence_valuation_boundary.py` did not exist at ANY of the four
    historical commits.

It arrived in `d032b82`, the commit before HEAD. So for those four states the
policy manifest cannot be materialised at all, and the admission rules they
would be read under are not in the repository in any form. That is not a gap a
compatibility shim can close: a shim would have to supply the missing module,
which means writing the admission rules afresh and then reporting the result as
history. The brief forbids exactly that, so those states are reported
`NOT_MATERIALIZABLE` with the reason, and the registry half is reported
separately because it *is* recoverable.

Run:  python historical_state_reconstruction_331.py
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[2]
for _path in (REPO, SCRIPT_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from registry_identity import (  # noqa: E402
    _POLICY_FILES,
    registry_state_identity,
    resolver_policy_identity,
)
import registry_identity  # noqa: E402

HERE = REPO
HARNESS = (
    HERE / "experiments" / "003-llm-evidence-retrieval" / "harness"
)
ARTIFACT = HARNESS / "331-historical-state-reconstruction.json"

# The five states 3.29 measured. Each is named by its own commit so the corpus
# is reproducible from the repository rather than from this file's memory.
STATES: Tuple[Tuple[str, str], ...] = (
    ("head", "HEAD"),
    ("ef38c6b_2.73_pre_measured_scope", "ef38c6b"),
    ("63b1243_2.99_after_revenues_retired", "63b1243"),
    ("8696e97_2.71_after_ifrs_current_portion", "8696e97"),
    ("27693a0_2.39_after_ifrs_capex", "27693a0"),
)


def _git(*args: str) -> Optional[bytes]:
    result = subprocess.run(
        ["git", "-C", str(REPO), *args],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def materialise(commit: str, destination: Path) -> Dict[str, List[str]]:
    """
    Write a commit's tree into `destination`.

    Only the files the identities need: the six policy-manifest modules and the
    migrations directory. Anything missing is recorded rather than faked, so a
    state that genuinely predates a file reports it instead of borrowing the
    current one.
    """
    present: List[str] = []
    missing: List[str] = []
    for name in _POLICY_FILES:
        blob = _git("show", f"{commit}:{name}")
        if blob is None:
            missing.append(name)
            continue
        (destination / name).write_bytes(blob)
        present.append(name)

    migrations = destination / "archive" / "migrations"
    migrations.mkdir(parents=True, exist_ok=True)
    found = _git("ls-tree", "--name-only", commit, "archive/migrations/")
    names: List[str] = []
    if found:
        for line in found.decode("utf-8").splitlines():
            stem = Path(line).name
            if not stem.endswith(".sql"):
                continue
            blob = _git("show", f"{commit}:{line}")
            if blob is None:
                continue
            (migrations / stem).write_bytes(blob)
            names.append(stem)
    return {"present": present, "missing": missing, "migrations": names}


def rebuild_registry(commit: str, workdir: Path) -> Dict[str, object]:
    """
    Apply that commit's migrations, then seed, then compute the registry digest.

    Seeding happens *after* migrating and that order is load-bearing rather than
    conventional: `archive/migrations/0018_mapping_relation_kind.sql:18-23`
    records that an earlier draft carried `UPDATE`s setting `relation_kind`,
    that they cannot work, and that `seed()` overwrites them. A rebuild that
    seeded first would silently lose every classification.
    """
    report: Dict[str, object] = {"commit": commit}
    database = workdir / "rebuild.sqlite"
    connection = sqlite3.connect(str(database))
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        migration_dir = workdir / "archive" / "migrations"
        applied = 0
        for path in sorted(migration_dir.glob("*.sql")):
            version_text, _, _ = path.stem.partition("_")
            connection.executescript(path.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations (version, name, checksum,"
                " applied_at) VALUES (?, ?, ?, ?)",
                (
                    int(version_text),
                    path.stem.partition("_")[2],
                    __import__("hashlib").sha256(
                        path.read_bytes()
                    ).hexdigest(),
                    "2026-01-01T00:00:00+00:00",
                ),
            )
            connection.execute(f"PRAGMA user_version = {int(version_text)}")
            applied += 1
        connection.commit()

        seed_module = _load(
            f"seed_{commit}", workdir / "registry_seed.py",
            (workdir / "core_registry.py", workdir / "data_contract.py"),
        )
        registry_module = _load(
            f"reg_{commit}", workdir / "core_registry.py",
            (workdir / "data_contract.py",),
        )
        seed_module.seed(registry_module.CoreRegistry(connection))
        connection.commit()

        # The distinct-row count uses the same column manifest as the identity
        # rather than naming columns here, so a state that predates migration
        # 0018 is counted on the columns it actually has instead of failing on
        # a name it never declared.
        present = {
            str(row[1])
            for row in connection.execute(
                "PRAGMA table_info(metric_concept_mapping)"
            ).fetchall()
        }
        mapping_columns = [
            "metric_id", "concept_id", "mapping_type", "effective_from",
            "effective_to", "relation_kind", "scope_json",
        ]
        projection = ", ".join(
            column if column in present else f"NULL AS {column}"
            for column in mapping_columns
        )
        rows = connection.execute(
            "SELECT COUNT(*) FROM metric_concept_mapping"
        ).fetchone()[0]
        distinct = connection.execute(
            f"SELECT COUNT(*) FROM (SELECT DISTINCT {projection}"
            " FROM metric_concept_mapping)"
        ).fetchone()[0]
        report.update({
            "migrations_applied": applied,
            "mapping_rows_physical": rows,
            "mapping_rows_distinct": distinct,
            "registry_state_identity": registry_state_identity(connection),
            "status": "RECONSTRUCTABLE",
        })
    except Exception as error:  # reported, never swallowed
        report.update({
            "status": "NOT_RECONSTRUCTABLE",
            "reason": f"{type(error).__name__}: {error}",
        })
    finally:
        # Closed on every path: Windows refuses to unlink an open file, so a
        # leaked handle would turn a reported failure into a harness crash.
        try:
            connection.close()
        except sqlite3.Error:
            pass
    return report


def _load(name: str, path: Path, extra_sys_path: Tuple[Path, ...]):
    import importlib.util

    for extra in extra_sys_path:
        text = extra.read_text(encoding="utf-8")
        (extra.parent / f"_shim_{extra.name}").write_text(text, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def compute_policy_identity(commit: str, workdir: Path,
                            manifest: Dict[str, List[str]]) -> Dict[str, object]:
    """
    The policy digest, if that commit's own manifest can be read.

    `resolver_policy_identity` refuses a missing file rather than digesting a
    hole, which is the right behaviour and is also the answer here: four of the
    five states predate `evidence_valuation_boundary.py`.
    """
    missing = list(manifest["missing"])
    if missing:
        return {
            "status": "NOT_MATERIALIZABLE",
            "missing_from_manifest": missing,
            "reason": (
                "the policy manifest names files this commit does not contain, "
                "so the code that would have read this registry is not in the "
                "repository in any form. No shim can supply a module that was "
                "never written without inventing the rules it contained."
            ),
            "resolver_policy_identity": None,
        }
    original = registry_identity.REPO_ROOT
    try:
        registry_identity.REPO_ROOT = workdir
        return {
            "status": "MATERIALIZABLE",
            "missing_from_manifest": [],
            "resolver_policy_identity": resolver_policy_identity(),
        }
    except Exception as error:
        return {
            "status": "NOT_MATERIALIZABLE",
            "missing_from_manifest": [],
            "reason": f"{type(error).__name__}: {error}",
            "resolver_policy_identity": None,
        }
    finally:
        registry_identity.REPO_ROOT = original


def main() -> None:
    corpus: Dict[str, object] = {
        "purpose": (
            "3.31 A4/A5: can each of 3.29's five states have its admission "
            "identities computed from its own material?"
        ),
        "states": {},
    }
    for label, commit in STATES:
        with tempfile.TemporaryDirectory(prefix="steva331_") as directory:
            workdir = Path(directory)
            manifest = materialise(commit, workdir)
            registry = rebuild_registry(commit, workdir)
            policy = compute_policy_identity(commit, workdir, manifest)
            corpus["states"][label] = {
                "commit": commit,
                "manifest": manifest,
                "registry": registry,
                "policy": policy,
            }
            print(
                f"{label:42s} registry={registry['status']:20s} "
                f"policy={policy['status']}",
                flush=True,
            )

    HARNESS.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(
        json.dumps(corpus, indent=1, sort_keys=True), encoding="utf-8"
    )
    print("\nwritten:", ARTIFACT)


if __name__ == "__main__":
    main()
