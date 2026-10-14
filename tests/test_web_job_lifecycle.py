"""Web job lifecycle tests.

The adapter announces JobProgressStage.COMPLETED (through the progress callback)
just before it returns the result, so the job record must not become terminal on
that announcement alone: a poller must never observe a successful terminal state
whose result is still missing. These tests control the interleaving with events
rather than sleeps, so they do not depend on run timing.
"""

import threading
import unittest

from web.job_manager import JobManager
from web.schemas import JobProgressStage, JobStatus


class _GatedAdapter:
    """Announces COMPLETED, then blocks on a gate before returning or raising."""

    def __init__(self, result, announced, gate, error=None):
        self.result = result
        self.announced = announced
        self.gate = gate
        self.error = error

    def run_analysis_pipeline(self, **kwargs):
        callback = kwargs.get("progress_callback")
        if callback is not None:
            callback(JobProgressStage.COMPLETED)
        self.announced.set()
        self.gate.wait(5.0)
        if self.error is not None:
            raise self.error
        return self.result


class _FailingAdapter:
    """Raises before announcing anything."""

    def run_analysis_pipeline(self, **kwargs):
        raise RuntimeError("early boom")


class TestJobLifecycle(unittest.TestCase):
    def test_poller_never_sees_completed_without_a_result(self):
        announced, gate = threading.Event(), threading.Event()
        sentinel = object()
        manager = JobManager(
            adapter=_GatedAdapter(sentinel, announced, gate), max_workers=1
        )
        try:
            record = manager.submit_job("AAPL", mode="regression")
            self.assertTrue(announced.wait(5.0), "adapter never announced completion")

            # The adapter has announced COMPLETED but not returned yet: a poll
            # here must never show terminal success with a missing result.
            job = manager.get_job(record.job_id)
            self.assertIsNone(job.result)
            self.assertFalse(
                job.status == JobStatus.COMPLETED and job.result is None,
                "job reported COMPLETED before its result was written",
            )

            gate.set()
            manager.shutdown(wait=True)
            job = manager.get_job(record.job_id)
            self.assertEqual(job.status, JobStatus.COMPLETED)
            self.assertIs(job.result, sentinel)
        finally:
            gate.set()
            manager.shutdown(wait=True)

    def test_a_failure_after_the_completion_announcement_is_terminal(self):
        announced, gate = threading.Event(), threading.Event()
        manager = JobManager(
            adapter=_GatedAdapter(None, announced, gate, error=RuntimeError("late boom")),
            max_workers=1,
        )
        try:
            record = manager.submit_job("AAPL", mode="regression")
            self.assertTrue(announced.wait(5.0))
            gate.set()
            manager.shutdown(wait=True)
            job = manager.get_job(record.job_id)
            self.assertEqual(job.status, JobStatus.FAILED)
            self.assertIn("late boom", job.error or "")
            self.assertIsNone(job.result)
        finally:
            gate.set()
            manager.shutdown(wait=True)

    def test_an_early_failure_is_terminal(self):
        manager = JobManager(adapter=_FailingAdapter(), max_workers=1)
        try:
            record = manager.submit_job("AAPL", mode="regression")
            manager.shutdown(wait=True)
            job = manager.get_job(record.job_id)
            self.assertEqual(job.status, JobStatus.FAILED)
            self.assertIn("early boom", job.error or "")
        finally:
            manager.shutdown(wait=True)


if __name__ == "__main__":
    unittest.main()
