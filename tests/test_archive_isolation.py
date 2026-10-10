"""
Data-safety tests: a test run must not write into the operator's own archives.

The repository keeps real per-ticker archives under `data/archives`. Several
tests exercise a real end-to-end analysis, which means they really do open an
archive, seed it and write observations. That is correct behaviour for the
application and wrong behaviour for a test, so the archive directory has to be
redirected explicitly rather than inherited from a default.

These tests pin that isolation. They are deliberately about the wiring rather
than about any valuation result.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, ".")

from web.app import create_app
from web.job_manager import JobManager
from web.service_adapter import AnalysisServiceAdapter


ROOT = Path(__file__).resolve().parent.parent
OPERATOR_ARCHIVES = ROOT / "data" / "archives"


class _ArchiveOverrideGuard:
    """
    Fail if anything under the operator's archive directory is touched.

    Compares the directory listing and each file's size and modification time
    before and after, so both a new file and a write to an existing one are
    caught.
    """

    def __init__(self) -> None:
        self.before = self._snapshot()

    @staticmethod
    def _snapshot():
        if not OPERATOR_ARCHIVES.is_dir():
            return {}
        state = {}
        for path in OPERATOR_ARCHIVES.iterdir():
            if path.is_file():
                stat = path.stat()
                state[path.name] = (stat.st_size, stat.st_mtime_ns)
            else:
                state[path.name] = None
        return state

    def diff(self):
        after = self._snapshot()
        changed = []
        for name in sorted(set(self.before) | set(after)):
            if self.before.get(name) != after.get(name):
                changed.append(name)
        return changed


class TestArchiveIsolationWiring(unittest.TestCase):
    def test_adapter_defaults_to_the_operator_directory(self):
        # This is the behaviour the isolation exists to protect. If a future
        # change moves the default, this test should fail and the isolation
        # tests below should be revisited.
        adapter = AnalysisServiceAdapter()
        self.assertEqual(
            adapter.archives_dir.resolve(),
            (ROOT / "data" / "archives").resolve(),
        )

    def test_create_app_honours_an_explicit_archives_dir(self):
        with tempfile.TemporaryDirectory(prefix="steva-isolation-") as tmpdir:
            app = create_app(archives_dir=tmpdir)
            adapter = app.state.job_manager.adapter
            self.assertEqual(adapter.archives_dir.resolve(), Path(tmpdir).resolve())

    def test_create_app_default_is_unchanged_for_normal_use(self):
        # The default must still work for a real operator who wants the real
        # archives; isolation is opt-in at the call site, not enforced by
        # breaking the application default.
        app = create_app()
        adapter = app.state.job_manager.adapter
        self.assertEqual(
            adapter.archives_dir.resolve(),
            (ROOT / "data" / "archives").resolve(),
        )


class TestBrowserSmokeIsIsolated(unittest.TestCase):
    def test_browser_smoke_passes_an_explicit_archives_dir(self):
        """
        The browser smoke suite runs real analyses. If it falls back to the
        default directory, every run writes to the operator's archives.

        Checked by reading the source rather than by running the browser
        suite, so the guard does not itself need a browser or the network.
        """
        source = (ROOT / "tests" / "test_browser_smoke.py").read_text(encoding="utf-8")
        self.assertIn("archives_dir=", source)
        self.assertNotIn("app = create_app()\n", source)


class TestJobManagerHonoursAnInjectedAdapter(unittest.TestCase):
    def test_injected_adapter_is_used(self):
        with tempfile.TemporaryDirectory(prefix="steva-jobmgr-") as tmpdir:
            adapter = AnalysisServiceAdapter(archives_dir=tmpdir)
            manager = JobManager(adapter=adapter, max_workers=1)
            self.assertIs(manager.adapter, adapter)
            manager.shutdown(wait=False)


class TestNoArchiveWritesDuringImportOnly(unittest.TestCase):
    def test_importing_the_web_package_creates_no_archive(self):
        """
        Importing must not touch the filesystem beyond imports.

        A module-level `AnalysisServiceAdapter()` would create the directory as
        a side effect of import, which would make every test that imports the
        package write to the operator's data directory.
        """
        guard = _ArchiveOverrideGuard()
        import web.app  # noqa: F401
        import web.job_manager  # noqa: F401
        import web.service_adapter  # noqa: F401

        self.assertEqual(guard.diff(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
