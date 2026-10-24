"""
In-process background job manager for ST-EVA API.
Executes jobs in background worker threads to avoid blocking FastAPI event loop.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import threading
from typing import Dict, List, Optional
import uuid

from web.schemas import (
    AnalysisResultDTO,
    JobDetailResponse,
    JobProgressStage,
    JobStatus,
)
from web.service_adapter import AnalysisServiceAdapter


def utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobRecord:
    def __init__(self, job_id: str, ticker: str) -> None:
        self.job_id = job_id
        self.ticker = ticker
        self.status = JobStatus.PENDING
        self.stage = JobProgressStage.PENDING
        self.created_at = utc_iso_now()
        self.updated_at = self.created_at
        self.error: Optional[str] = None
        self.result: Optional[AnalysisResultDTO] = None

    def update_stage(self, stage: JobProgressStage) -> None:
        self.stage = stage
        self.updated_at = utc_iso_now()
        if stage in (
            JobProgressStage.RESOLVING,
            JobProgressStage.FETCHING_SEC,
            JobProgressStage.ADMISSION,
            JobProgressStage.VALUATION,
            JobProgressStage.ARCHIVE_REPLAY,
        ):
            self.status = JobStatus.RUNNING
        elif stage == JobProgressStage.COMPLETED:
            self.status = JobStatus.COMPLETED
        elif stage == JobProgressStage.FAILED:
            self.status = JobStatus.FAILED

    def set_result(self, result: AnalysisResultDTO) -> None:
        self.result = result
        self.status = JobStatus.COMPLETED
        self.stage = JobProgressStage.COMPLETED
        self.updated_at = utc_iso_now()

    def set_error(self, error: str) -> None:
        self.error = error
        self.status = JobStatus.FAILED
        self.stage = JobProgressStage.FAILED
        self.updated_at = utc_iso_now()

    def to_response(self) -> JobDetailResponse:
        return JobDetailResponse(
            job_id=self.job_id,
            ticker=self.ticker,
            status=self.status,
            stage=self.stage,
            created_at=self.created_at,
            updated_at=self.updated_at,
            error=self.error,
            result=self.result,
        )


class JobManager:
    """
    Manages in-process background job submission and status polling.
    """

    def __init__(
        self,
        adapter: Optional[AnalysisServiceAdapter] = None,
        max_workers: int = 4,
    ) -> None:
        self.adapter = adapter or AnalysisServiceAdapter()
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.jobs: Dict[str, JobRecord] = {}
        self.lock = threading.Lock()

    def submit_job(
        self,
        ticker: str,
        mode: str = "auto",
        reference_multiple: Optional[float] = None,
        reference_multiples: Optional[List[float]] = None,
        horizon_years: float = 1.0,
        reverse_horizons: Optional[List[float]] = None,
        required_returns: Optional[List[float]] = None,
        prefer_eps_anchor: Optional[str] = None,
        user_eps: Optional[float] = None,
        ps_multiple: Optional[float] = None,
        ev_ebitda_multiple: Optional[float] = None,
        pfcf_multiple: Optional[float] = None,
    ) -> JobRecord:
        job_id = f"job-{uuid.uuid4().hex[:12]}"
        record = JobRecord(job_id=job_id, ticker=ticker)

        with self.lock:
            self.jobs[job_id] = record

        self.executor.submit(
            self._execute_job,
            job_id,
            ticker,
            mode,
            reference_multiple,
            reference_multiples,
            horizon_years,
            reverse_horizons,
            required_returns,
            prefer_eps_anchor,
            user_eps,
            ps_multiple,
            ev_ebitda_multiple,
            pfcf_multiple,
        )
        return record

    def get_job(self, job_id: str) -> Optional[JobRecord]:
        with self.lock:
            return self.jobs.get(job_id)

    def _execute_job(
        self,
        job_id: str,
        ticker: str,
        mode: str,
        reference_multiple: Optional[float],
        reference_multiples: Optional[List[float]],
        horizon_years: float,
        reverse_horizons: Optional[List[float]],
        required_returns: Optional[List[float]],
        prefer_eps_anchor: Optional[str],
        user_eps: Optional[float],
        ps_multiple: Optional[float],
        ev_ebitda_multiple: Optional[float],
        pfcf_multiple: Optional[float],
    ) -> None:
        record = self.get_job(job_id)
        if not record:
            return

        def on_progress(stage: JobProgressStage) -> None:
            # The adapter announces COMPLETED just before it returns the result,
            # so completion is recorded by set_result instead. Without this a
            # poller could observe a completed job whose result is still None.
            if stage == JobProgressStage.COMPLETED:
                return
            with self.lock:
                record.update_stage(stage)

        try:
            on_progress(JobProgressStage.RESOLVING)
            func = getattr(self.adapter.run_analysis_pipeline, "side_effect", None) or self.adapter.run_analysis_pipeline
            call_kwargs = {
                "ticker": ticker,
                "mode": mode,
                "reference_multiple": reference_multiple,
                "horizon_years": horizon_years,
                "progress_callback": on_progress,
            }
            try:
                import inspect
                sig = inspect.signature(func)
                has_var_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
                param_names = set(sig.parameters.keys())
                if has_var_kwargs or "reference_multiples" in param_names:
                    call_kwargs["reference_multiples"] = reference_multiples
                if has_var_kwargs or "reverse_horizons" in param_names:
                    call_kwargs["reverse_horizons"] = reverse_horizons
                if has_var_kwargs or "required_returns" in param_names:
                    call_kwargs["required_returns"] = required_returns
                if has_var_kwargs or "prefer_eps_anchor" in param_names:
                    call_kwargs["prefer_eps_anchor"] = prefer_eps_anchor
                if has_var_kwargs or "user_eps" in param_names:
                    call_kwargs["user_eps"] = user_eps
                if has_var_kwargs or "ps_multiple" in param_names:
                    call_kwargs["ps_multiple"] = ps_multiple
                if has_var_kwargs or "ev_ebitda_multiple" in param_names:
                    call_kwargs["ev_ebitda_multiple"] = ev_ebitda_multiple
                if has_var_kwargs or "pfcf_multiple" in param_names:
                    call_kwargs["pfcf_multiple"] = pfcf_multiple
            except Exception:
                call_kwargs.update({
                    "reference_multiples": reference_multiples,
                    "reverse_horizons": reverse_horizons,
                    "required_returns": required_returns,
                    "prefer_eps_anchor": prefer_eps_anchor,
                    "user_eps": user_eps,
                    "ps_multiple": ps_multiple,
                    "ev_ebitda_multiple": ev_ebitda_multiple,
                    "pfcf_multiple": pfcf_multiple,
                })

            result = self.adapter.run_analysis_pipeline(**call_kwargs)
            with self.lock:
                record.set_result(result)
        except Exception as exc:
            with self.lock:
                record.set_error(str(exc))

    def shutdown(self, wait: bool = True) -> None:
        self.executor.shutdown(wait=wait)

