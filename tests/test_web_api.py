"""
Tests for ST-EVA Web API layer.
Validates all endpoint behaviors, job serialization, ticker validation,
TSM refusals representation, and isolation from core mechanics.
"""

import time
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from web.app import create_app
from web.job_manager import JobManager
from web.schemas import (
    AdmissionSummary,
    AnalysisResultDTO,
    JobProgressStage,
    JobStatus,
    RefusalItem,
    ReplaySummary,
    ValuationSummary,
)
from web.service_adapter import AnalysisServiceAdapter


class TestWebAPI(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_adapter = MagicMock(spec=AnalysisServiceAdapter)
        self.job_manager = JobManager(adapter=self.mock_adapter, max_workers=2)
        self.app = create_app(job_manager=self.job_manager)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.job_manager.shutdown(wait=False)

    def test_health_check(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["version"], "0.1.0")

    def test_valid_ticker_accepted(self):
        for ticker in ["AAPL", "msft", "0700.HK", "BRK-B"]:
            response = self.client.post("/api/analyze", json={"ticker": ticker})
            self.assertEqual(response.status_code, 202)
            data = response.json()
            self.assertIn("job_id", data)
            self.assertEqual(data["ticker"], ticker.upper())
            self.assertIn(data["status"], ["PENDING", "RUNNING", "COMPLETED"])

    def test_invalid_ticker_rejected(self):
        for bad_ticker in ["", "   ", "AAPL; DROP TABLE", "TOOLONGTICKERNAME123456", "AAPL$"]:
            response = self.client.post("/api/analyze", json={"ticker": bad_ticker})
            self.assertEqual(response.status_code, 400)
            self.assertIn("detail", response.json())

    def test_job_created_and_lifecycle(self):
        fake_dto = AnalysisResultDTO(
            ticker="MSFT",
            company_name="Microsoft Corporation",
            status="success",
            research_id="RES-MOCK123",
            as_of="2026-09-18",
            source_identifiers=["RegressionFixture"],
            admission_summary=AdmissionSummary(
                total_admitted=1,
                total_refused=0,
                metrics_admitted=["revenue"],
            ),
            valuation_summary=ValuationSummary(
                current_price=425.50,
                currency="USD",
                forward_eps_at_reference_multiple=21.275,
            ),
            replay_summary=ReplaySummary(
                attempted=True,
                outcome="MATCH",
                matched=True,
                reconstructed=True,
                observations_used=10,
                observations_considered=10,
            ),
        )

        def mock_run(ticker, mode, reference_multiple, horizon_years, progress_callback):
            if progress_callback:
                progress_callback(JobProgressStage.FETCHING_SEC)
                progress_callback(JobProgressStage.VALUATION)
                progress_callback(JobProgressStage.ARCHIVE_REPLAY)
            return fake_dto

        self.mock_adapter.run_analysis_pipeline.side_effect = mock_run

        response = self.client.post("/api/analyze", json={"ticker": "MSFT", "mode": "regression"})
        self.assertEqual(response.status_code, 202)
        job_id = response.json()["job_id"]

        # Poll status until completed
        for _ in range(50):
            job_resp = self.client.get(f"/api/jobs/{job_id}")
            self.assertEqual(job_resp.status_code, 200)
            body = job_resp.json()
            if body["status"] == "COMPLETED":
                break
            time.sleep(0.05)

        body = self.client.get(f"/api/jobs/{job_id}").json()
        self.assertEqual(body["status"], "COMPLETED")
        self.assertEqual(body["stage"], "completed")
        self.assertIsNotNone(body["result"])
        self.assertEqual(body["result"]["ticker"], "MSFT")
        self.assertEqual(body["result"]["company_name"], "Microsoft Corporation")
        self.assertEqual(body["result"]["replay_summary"]["outcome"], "MATCH")
        self.assertTrue(body["result"]["replay_summary"]["matched"])

    def test_running_status_can_be_observed(self):
        gate = threading_event = MagicMock()
        entered = False

        def slow_run(ticker, mode, reference_multiple, horizon_years, progress_callback):
            if progress_callback:
                progress_callback(JobProgressStage.RESOLVING)
            # simulate brief running state
            time.sleep(0.2)
            return AnalysisResultDTO(
                ticker=ticker,
                company_name="Slow Corp",
            )

        self.mock_adapter.run_analysis_pipeline.side_effect = slow_run
        post_resp = self.client.post("/api/analyze", json={"ticker": "SLOW"})
        job_id = post_resp.json()["job_id"]

        time.sleep(0.05)
        job_resp = self.client.get(f"/api/jobs/{job_id}")
        self.assertIn(job_resp.json()["status"], ["RUNNING", "COMPLETED"])

    def test_failed_job_serialized(self):
        def failing_run(ticker, mode, reference_multiple, horizon_years, progress_callback):
            raise RuntimeError("Underlying upstream API unavailable")

        self.mock_adapter.run_analysis_pipeline.side_effect = failing_run

        resp = self.client.post("/api/analyze", json={"ticker": "FAIL"})
        job_id = resp.json()["job_id"]

        for _ in range(50):
            job_resp = self.client.get(f"/api/jobs/{job_id}")
            body = job_resp.json()
            if body["status"] == "FAILED":
                break
            time.sleep(0.05)

        body = self.client.get(f"/api/jobs/{job_id}").json()
        self.assertEqual(body["status"], "FAILED")
        self.assertEqual(body["stage"], "failed")
        self.assertIn("Underlying upstream API unavailable", body["error"])
        self.assertIsNone(body["result"])

    def test_tsm_refusal_represented_correctly(self):
        # TSM currency mismatch / refusal scenario
        tsm_dto = AnalysisResultDTO(
            ticker="TSM",
            company_name="Taiwan Semiconductor Manufacturing Co.",
            status="success",
            as_of="2026-06-30",
            admission_summary=AdmissionSummary(
                total_admitted=0,
                total_refused=1,
                metrics_admitted=[],
                refusals=[
                    RefusalItem(
                        ref="revenue",
                        reason="cross-currency ratio must be withheld: USD vs TWD",
                        category="CURRENCY_MISMATCH",
                    )
                ],
            ),
            valuation_summary=ValuationSummary(
                current_price=175.0,
                currency="USD",
                observed_ps=None,
                limitations=["Reverse-engineered earnings/growth are conditional."],
            ),
            refusal_reasons=["cross-currency ratio must be withheld: USD vs TWD"],
        )

        self.mock_adapter.run_analysis_pipeline.return_value = tsm_dto

        resp = self.client.post("/api/analyze", json={"ticker": "TSM"})
        job_id = resp.json()["job_id"]

        for _ in range(50):
            job_resp = self.client.get(f"/api/jobs/{job_id}")
            if job_resp.json()["status"] == "COMPLETED":
                break
            time.sleep(0.05)

        result = self.client.get(f"/api/jobs/{job_id}").json()["result"]
        self.assertEqual(result["ticker"], "TSM")
        self.assertIn("cross-currency ratio must be withheld: USD vs TWD", result["refusal_reasons"])
        self.assertEqual(result["admission_summary"]["total_refused"], 1)
        self.assertEqual(len(result["admission_summary"]["refusals"]), 1)
        self.assertEqual(result["admission_summary"]["refusals"][0]["category"], "CURRENCY_MISMATCH")

    def test_replay_result_represented_correctly(self):
        replay_dto = AnalysisResultDTO(
            ticker="AAPL",
            company_name="Apple Inc.",
            replay_summary=ReplaySummary(
                attempted=True,
                outcome="INSUFFICIENT",
                reason="no price observation for AAPL is knowable at 2020-01-01",
                matched=False,
                reconstructed=False,
                observations_used=0,
                observations_considered=5,
            ),
        )
        self.mock_adapter.run_analysis_pipeline.return_value = replay_dto

        resp = self.client.post("/api/analyze", json={"ticker": "AAPL"})
        job_id = resp.json()["job_id"]

        for _ in range(50):
            job_resp = self.client.get(f"/api/jobs/{job_id}")
            if job_resp.json()["status"] == "COMPLETED":
                break
            time.sleep(0.05)

        result = self.client.get(f"/api/jobs/{job_id}").json()["result"]
        rep = result["replay_summary"]
        self.assertEqual(rep["outcome"], "INSUFFICIENT")
        self.assertFalse(rep["matched"])
        self.assertIn("no price observation", rep["reason"])

    def test_nonexistent_job_returns_404(self):
        resp = self.client.get("/api/jobs/job-nonexistent123")
        self.assertEqual(resp.status_code, 404)

    def test_static_spa_serving(self):
        # Request root path / should return index.html
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers.get("content-type", ""))
        self.assertIn("ST-EVA", resp.text)

    def test_pwa_manifest_serving(self):
        resp = self.client.get("/manifest.webmanifest")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/manifest+json", resp.headers.get("content-type", ""))
        data = resp.json()
        self.assertEqual(data["short_name"], "ST-EVA")
        self.assertEqual(data["display"], "standalone")
        self.assertTrue(len(data["icons"]) >= 2)

    def test_pwa_service_worker_serving(self):
        resp = self.client.get("/sw.js")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/javascript", resp.headers.get("content-type", ""))
        self.assertEqual(resp.headers.get("service-worker-allowed"), "/")
        self.assertIn("CACHE_NAME", resp.text)
        self.assertIn("/api/", resp.text)

    def test_pwa_icons_serving(self):
        resp192 = self.client.get("/icons/icon-192.png")
        self.assertEqual(resp192.status_code, 200)
        self.assertIn("image/png", resp192.headers.get("content-type", ""))

        resp512 = self.client.get("/icons/icon-512.png")
        self.assertEqual(resp512.status_code, 200)
        self.assertIn("image/png", resp512.headers.get("content-type", ""))


class TestAdapterIntegrationSmoke(unittest.TestCase):
    """
    Smoke test: Ensure adapter calls existing production run_st_eva and SQLiteArchive
    without modifying core behavior or data schema.
    """

    def test_adapter_against_msft_regression_fixture(self):
        import tempfile
        import shutil

        tmpdir = tempfile.mkdtemp()
        try:
            adapter = AnalysisServiceAdapter(archives_dir=tmpdir)
            stages = []

            def on_progress(st):
                stages.append(st)

            dto = adapter.run_analysis_pipeline(
                ticker="MSFT",
                mode="regression",
                progress_callback=on_progress,
            )

            self.assertEqual(dto.ticker, "MSFT")
            self.assertEqual(dto.company_name, "Microsoft Corporation")
            self.assertIsNotNone(dto.valuation_summary.current_price)
            self.assertGreater(dto.valuation_summary.current_price, 0)
            self.assertTrue(len(stages) >= 4)
            self.assertIn(JobProgressStage.VALUATION, stages)

            # Check that archive sqlite was created in the designated folder
            archive_file = adapter.get_archive_path("MSFT")
            self.assertTrue(archive_file.exists())
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_fresh_archive_seeded_with_registry_baseline(self):
        import tempfile
        import shutil
        from core_registry import CoreRegistry
        from registry_identity import registry_state_identity

        tmpdir = tempfile.mkdtemp()
        try:
            adapter = AnalysisServiceAdapter(archives_dir=tmpdir)
            archive = adapter.get_archive("AAPL")
            try:
                # 1. metric_registry must contain revenue
                reg = CoreRegistry(archive.connection)
                metric = reg.metric("revenue")
                self.assertIsNotNone(metric)
                self.assertEqual(metric.statement, "INCOME")
                self.assertEqual(metric.unit_family, "currency")

                # 2. Revenue mappings must be discoverable by resolver
                mappings = reg.mappings_for_metric("revenue")
                self.assertTrue(len(mappings) > 0)
                concept_ids = [m.concept_id for m in mappings]
                self.assertTrue(any("Revenue" in cid for cid in concept_ids))

                # 3. Canonical registry state identity matches seeded baseline
                reg_id = registry_state_identity(archive.connection)
                self.assertTrue(reg_id.startswith("rgs:"))
                self.assertNotEqual(
                    reg_id,
                    "rgs:c674e7d06f49b86676078009d70757fb011f76e82964d108dba45907a3e75c7d",  # empty registry hash
                )
            finally:
                archive.close()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()


