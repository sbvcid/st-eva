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

    def test_reverse_requirements_matrix_in_adapter_dto(self):
        import tempfile
        import shutil

        tmpdir = tempfile.mkdtemp()
        try:
            adapter = AnalysisServiceAdapter(archives_dir=tmpdir)
            dto = adapter.run_analysis_pipeline(
                ticker="MSFT",
                mode="regression",
            )
            self.assertIsNotNone(dto.reverse_requirements)
            rr = dto.reverse_requirements
            self.assertEqual(rr.formula_version, "reverse-requirements/1.1")
            self.assertEqual(rr.status, "COMPUTED")
            self.assertGreater(rr.matrix_size, 0)
            self.assertEqual(len(rr.reverse_requirements_matrix), rr.matrix_size)

            # Check scenario row attributes
            first = rr.reverse_requirements_matrix[0]
            self.assertIsNotNone(first.horizon_years)
            self.assertIsNotNone(first.required_return)
            self.assertIsNotNone(first.exit_multiple)
            self.assertIsNotNone(first.start_eps)
            self.assertIsNotNone(first.required_exit_price)
            self.assertIsNotNone(first.required_terminal_eps)
            self.assertIn("REQUIRED_RETURN_EXCLUDES_DIVIDENDS", first.flags)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_adapter_passes_custom_assumptions_to_engine(self):
        import tempfile
        import shutil

        tmpdir = tempfile.mkdtemp()
        try:
            adapter = AnalysisServiceAdapter(archives_dir=tmpdir)
            dto = adapter.run_analysis_pipeline(
                ticker="MSFT",
                mode="regression",
                reference_multiple=27.5,
                reverse_horizons=[3.0],
                required_returns=[0.12],
            )
            self.assertIsNotNone(dto.reverse_requirements)
            rr = dto.reverse_requirements
            # Check that 27.5 exit multiple scenario exists for horizon 3.0 and return 0.12
            matching = [
                s for s in rr.reverse_requirements_matrix
                if s.horizon_years == 3.0 and s.required_return == 0.12 and abs(s.exit_multiple.value - 27.5) < 1e-6
            ]
            self.assertTrue(len(matching) >= 1)
            target = matching[0]
            self.assertEqual(target.exit_multiple.source, "user_supplied")
            expected_price = 425.50 * (1.12 ** 3)
            self.assertAlmostEqual(target.required_exit_price, expected_price, places=2)
            self.assertIsNotNone(target.required_eps_cagr)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_summary_headline_basis_is_reported(self):
        import tempfile
        import shutil

        tmpdir = tempfile.mkdtemp()
        try:
            adapter = AnalysisServiceAdapter(archives_dir=tmpdir)

            # A user-supplied reference P/E is reported with that exact basis,
            # and the headline implied EPS reconciles to price / selected P/E.
            dto_user = adapter.run_analysis_pipeline(
                ticker="MSFT",
                mode="regression",
                reference_multiple=27.5,
            )
            vs = dto_user.valuation_summary
            self.assertEqual(vs.selected_pe_basis, "user_supplied_multiple")
            self.assertAlmostEqual(vs.selected_pe, 27.5, places=6)
            self.assertAlmostEqual(vs.summary_horizon_years, 1.0, places=6)
            self.assertIsNotNone(vs.current_price)
            self.assertAlmostEqual(
                vs.forward_eps_at_reference_multiple,
                vs.current_price / 27.5,
                places=6,
            )

            # The summary horizon is reported so the headline CAGR's basis is
            # unambiguous, and can differ from the matrix horizons.
            dto_h = adapter.run_analysis_pipeline(
                ticker="MSFT",
                mode="regression",
                reference_multiple=27.5,
                horizon_years=3.0,
            )
            self.assertAlmostEqual(
                dto_h.valuation_summary.summary_horizon_years, 3.0, places=6
            )
            # Whatever method selects the summary P/E, it is one the UI can
            # label, and it is never the production point-in-time distribution.
            self.assertIn(
                dto_h.valuation_summary.selected_pe_basis,
                {"user_supplied_multiple", "historical_pe_median", "none"},
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_uncomputable_scenario_preserved_with_reason(self):
        import tempfile
        import shutil

        tmpdir = tempfile.mkdtemp()
        try:
            adapter = AnalysisServiceAdapter(archives_dir=tmpdir)
            # MSFT fixture starting anchor is forward EPS covering 12 months.
            # A 1.0-year horizon leaves 0.0 growth years, which is uncomputable for CAGR.
            dto = adapter.run_analysis_pipeline(
                ticker="MSFT",
                mode="regression",
                reverse_horizons=[1.0],
                required_returns=[0.10],
            )
            self.assertIsNotNone(dto.reverse_requirements)
            rr = dto.reverse_requirements
            scenarios = rr.reverse_requirements_matrix
            self.assertTrue(len(scenarios) > 0)
            short_scen = scenarios[0]
            self.assertIsNone(short_scen.required_eps_cagr)
            self.assertIn("GROWTH_WINDOW_TOO_SHORT_FOR_CAGR", short_scen.flags)
            self.assertTrue(any("too short to annualise" in n for n in short_scen.comparison_notes))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_uncomputable_matrix_when_non_positive_eps(self):
        import tempfile
        import shutil

        tmpdir = tempfile.mkdtemp()
        try:
            adapter = AnalysisServiceAdapter(archives_dir=tmpdir)
            # Supply negative user EPS -> uncomputable matrix
            dto = adapter.run_analysis_pipeline(
                ticker="MSFT",
                mode="regression",
                user_eps=-10.0,
            )
            self.assertIsNotNone(dto.reverse_requirements)
            rr = dto.reverse_requirements
            self.assertEqual(rr.status, "NOT_COMPUTED")
            self.assertIsNotNone(rr.status_reason)
            self.assertEqual(rr.matrix_size, 0)
            self.assertEqual(len(rr.reverse_requirements_matrix), 0)
            self.assertTrue(any(u.get("item") == "start_eps_candidate.user" for u in rr.unavailable))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_api_analyze_with_custom_assumptions_end_to_end(self):
        import tempfile
        import shutil

        tmpdir = tempfile.mkdtemp()
        try:
            adapter = AnalysisServiceAdapter(archives_dir=tmpdir)
            job_mgr = JobManager(adapter=adapter, max_workers=2)
            app = create_app(job_manager=job_mgr)
            client = TestClient(app)

            resp = client.post(
                "/api/analyze",
                json={
                    "ticker": "MSFT",
                    "mode": "regression",
                    "reference_multiple": 25.0,
                    "reverse_horizons": [3.0],
                    "required_returns": [0.10],
                    "prefer_eps_anchor": "forward",
                },
            )
            self.assertEqual(resp.status_code, 202)
            job_id = resp.json()["job_id"]

            # The real pipeline includes the production historical P/E build, so
            # wait for a terminal state instead of a fixed number of polls.
            deadline = time.time() + 120.0
            body = {}
            while time.time() < deadline:
                job_resp = client.get(f"/api/jobs/{job_id}")
                body = job_resp.json()
                if body["status"] in ("COMPLETED", "FAILED"):
                    break
                time.sleep(0.1)

            self.assertEqual(body.get("status"), "COMPLETED", body.get("error"))
            result = body.get("result")
            self.assertIsNotNone(result)
            self.assertIsNotNone(result.get("reverse_requirements"))
            rr = result["reverse_requirements"]
            self.assertEqual(rr["formula_version"], "reverse-requirements/1.1")
            self.assertEqual(rr["status"], "COMPUTED")
            matrix = rr["reverse_requirements_matrix"]
            matching = [s for s in matrix if s["horizon_years"] == 3.0 and s["required_return"] == 0.10 and s["exit_multiple"]["value"] == 25.0]
            self.assertTrue(len(matching) >= 1)
            self.assertEqual(matching[0]["exit_multiple"]["source"], "user_supplied")
            job_mgr.shutdown(wait=False)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_api_returns_scenario_provenance_and_calculation_steps(self):
        import tempfile
        import shutil

        tmpdir = tempfile.mkdtemp()
        try:
            adapter = AnalysisServiceAdapter(archives_dir=tmpdir)
            dto = adapter.run_analysis_pipeline(
                ticker="MSFT",
                mode="regression",
                reference_multiple=25.0,
                reverse_horizons=[3.0],
                required_returns=[0.10],
            )
            self.assertIsNotNone(dto.reverse_requirements)
            rr = dto.reverse_requirements
            scenarios = rr.reverse_requirements_matrix
            self.assertTrue(len(scenarios) > 0)
            scen = scenarios[0]

            # Calculation steps verification
            self.assertEqual(len(scen.calculation_steps), 4)
            for step in scen.calculation_steps:
                self.assertTrue(step.reproducible)
                self.assertIsNotNone(step.formula_expression)
                self.assertIsInstance(step.operands, dict)

            # Sourced evidence verification
            self.assertIsNotNone(scen.evidence)
            self.assertEqual(scen.evidence.price_evidence.value, 425.50)
            self.assertEqual(scen.evidence.price_evidence.observation_id, "ev-price-001")
            self.assertIsNotNone(scen.evidence.eps_evidence)
            self.assertIsNotNone(scen.evidence.multiple_evidence)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_dto_validation_failure_raises_explicit_error_and_fails_job(self):
        import tempfile
        import shutil

        tmpdir = tempfile.mkdtemp()
        try:
            adapter = AnalysisServiceAdapter(archives_dir=tmpdir)
            job_mgr = JobManager(adapter=adapter, max_workers=2)
            app = create_app(job_manager=job_mgr)
            client = TestClient(app)

            # Return malformed reverse_requirements dict that violates DTO schema
            with patch("web.service_adapter.run_st_eva") as mock_runner:
                mock_runner.return_value = {
                    "ticker": "MSFT",
                    "mode": "regression",
                    "as_of": "2026-09-18",
                    "company_name": "Microsoft Corporation",
                    "summary": {"valuation": {"market_price": 425.50}},
                    "metrics": {},
                    "admissions": {},
                    "valuation": {"current_price": 425.50},
                    "reverse_requirements": {
                        "formula_version": "reverse-requirements/1.1",
                        "matrix_size": "INVALID_NOT_AN_INT",
                    },
                }

                resp = client.post("/api/analyze", json={"ticker": "MSFT", "mode": "regression"})
                self.assertEqual(resp.status_code, 202)
                job_id = resp.json()["job_id"]

                for _ in range(50):
                    job_resp = client.get(f"/api/jobs/{job_id}")
                    if job_resp.json()["status"] in ["FAILED", "COMPLETED"]:
                        break
                    time.sleep(0.05)

                final_resp = client.get(f"/api/jobs/{job_id}").json()
                self.assertEqual(final_resp["status"], "FAILED")
                self.assertIn("Reverse requirements contract validation failed", final_resp.get("error", ""))
            job_mgr.shutdown(wait=False)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_production_pfcf_reference_flows_through_the_web_path(self):
        """The cash-flow reference reaches the API with its own basis and state."""
        import tempfile
        import shutil

        tmpdir = tempfile.mkdtemp()
        try:
            adapter = AnalysisServiceAdapter(archives_dir=tmpdir)
            dto = adapter.run_analysis_pipeline(ticker="MSFT", mode="regression")

            vs = dto.valuation_summary
            self.assertEqual(vs.selected_pfcf_basis, "production_historical_pfcf_median")
            self.assertAlmostEqual(vs.selected_pfcf, 41.578319, places=6)
            # The MSFT regression fixture carries no vendor trailing FCF, so the
            # observed vendor multiple stays absent here; the reconstruction's
            # own current snapshot below is what carries the current figure.

            pfcf = dto.production_historical_pfcf
            self.assertIsNotNone(pfcf)
            self.assertEqual(pfcf.status, "USABLE_FOR_REFERENCE")
            self.assertTrue(pfcf.usable_for_reference)
            self.assertEqual(pfcf.sample_count, 23)
            self.assertEqual(pfcf.total_evaluations, 27)
            self.assertEqual(pfcf.min_observations_required, 20)
            self.assertEqual(pfcf.period_start, "2021-07-30")
            self.assertEqual(pfcf.period_end, "2026-07-30")
            self.assertAlmostEqual(pfcf.percentiles["median"], 41.578319, places=6)
            # The reconstruction's current snapshot, with its own date: the
            # canonical series' last trading day, not the live price date.
            self.assertAlmostEqual(pfcf.current_pfcf, 58.673194, places=6)
            self.assertEqual(pfcf.current_pfcf_as_of, "2026-10-06")

            # The P/E summary stays what it was; the two references are
            # separate blocks, never merged.
            pe = dto.production_historical_pe
            self.assertIsNotNone(pe)
            self.assertEqual(pe.status, "USABLE_FOR_REFERENCE")
            self.assertEqual(pe.sample_count, 24)
            # The raw payload no longer carries per-observation detail.
            raw = dto.raw_analysis.get("production_historical_pfcf") or {}
            self.assertNotIn("observations", raw.get("distribution") or {})
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_references_are_isolated_per_ticker(self):
        """Each ticker's web result carries only its own references and consensus."""
        import tempfile
        import shutil

        tmpdir = tempfile.mkdtemp()
        try:
            adapter = AnalysisServiceAdapter(archives_dir=tmpdir)
            aapl = adapter.run_analysis_pipeline(ticker="AAPL", mode="regression")
            msft = adapter.run_analysis_pipeline(ticker="MSFT", mode="regression")

            # Each ticker's cash-flow reference is its own distribution's median.
            self.assertEqual(aapl.valuation_summary.selected_pfcf_basis, "production_historical_pfcf_median")
            self.assertAlmostEqual(aapl.valuation_summary.selected_pfcf, 25.343981, places=6)
            self.assertEqual(aapl.production_historical_pfcf.sample_count, 35)
            self.assertEqual(aapl.production_historical_pfcf.period_start, "2018-02-02")
            self.assertAlmostEqual(
                aapl.production_historical_pfcf.percentiles["median"], 25.343981, places=6
            )
            self.assertEqual(msft.valuation_summary.selected_pfcf_basis, "production_historical_pfcf_median")
            self.assertAlmostEqual(msft.valuation_summary.selected_pfcf, 41.578319, places=6)
            self.assertEqual(msft.production_historical_pfcf.period_start, "2021-07-30")
            self.assertAlmostEqual(
                msft.production_historical_pfcf.percentiles["median"], 41.578319, places=6
            )
            # The P/E references are equally isolated: each ticker's median is
            # its own distribution's, never the other company's.
            self.assertAlmostEqual(aapl.valuation_summary.selected_pe, 28.44563, places=6)
            self.assertAlmostEqual(msft.valuation_summary.selected_pe, 33.195873, places=6)
            # The consensus periods differ by company calendar in live runs
            # (2027-09-30 for AAPL, 2028-06-30 for MSFT); the regression
            # fixtures carry no declared period metadata, so that distinction
            # is asserted by the live validation artifacts instead.
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()


