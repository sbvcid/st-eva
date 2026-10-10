"""
Adapter converting between external API requirements and existing ST-EVA core modules.
Does NOT modify or duplicate financial logic or validation rules.
"""

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import json

from sqlite_archive import SQLiteArchive
from core_registry import CoreRegistry
from registry_seed import seed
from archive import replay
from st_eva_runner import (
    run_st_eva,
    build_context_from_observations,
    SnapshotManager,
)
from web.schemas import (
    AdmissionSummary,
    AnalysisResultDTO,
    JobProgressStage,
    RefusalItem,
    ReplaySummary,
    ValuationSummary,
)


def default_replay_doc_builder(
    observation_set: Any,
    as_of: str,
    generated_at: str,
    asset_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Helper adapting archive.replay observation set to build_context_from_observations."""
    return build_context_from_observations(
        [
            observation_set.get(identifier)
            for identifier in observation_set.ids()
        ],
        ticker=observation_set.ticker,
        as_of=as_of,
        generated_at=generated_at,
        asset_metadata=asset_metadata,
    )


# Where per-ticker archives live unless a caller says otherwise. Named so the
# default is visible at every use site and so a test can assert against it.
DEFAULT_ARCHIVES_DIR = "data/archives"


class AnalysisServiceAdapter:
    """
    Adapter interfacing with ST-EVA production runner and SQLiteArchive.
    """

    def __init__(self, archives_dir: Optional[str] = None) -> None:
        # None means "the operator's real archive directory". Callers that must
        # not touch real data -- a test run, a dry run -- pass an explicit
        # directory instead, which is the only supported way to isolate.
        self.archives_dir = Path(archives_dir) if archives_dir else Path(DEFAULT_ARCHIVES_DIR)
        self.archives_dir.mkdir(parents=True, exist_ok=True)

    def get_archive_path(self, ticker: str) -> Path:
        safe_name = SnapshotManager.safe_ticker(ticker.upper().strip())
        return self.archives_dir / f"{safe_name}.sqlite"

    def get_archive(self, ticker: str) -> SQLiteArchive:
        """Opens or creates the archive for ticker and ensures registry baseline is seeded."""
        archive_path = self.get_archive_path(ticker)
        archive = SQLiteArchive(str(archive_path))
        self.ensure_registry_seeded(archive)
        return archive

    @staticmethod
    def ensure_registry_seeded(archive: SQLiteArchive) -> None:
        """
        Ensures the canonical ST-EVA core registry         baseline is seeded into the archive.
        Uses registry_seed.seed(CoreRegistry(archive.connection)).
        """
        row = archive.connection.execute(
            "SELECT COUNT(*) FROM metric_registry"
        ).fetchone()
        if row is None or row[0] == 0:
            seed(CoreRegistry(archive.connection))

    def run_analysis_pipeline(
        self,
        ticker: str,
        mode: str = "auto",
        reference_multiple: Optional[float] = None,
        horizon_years: float = 1.0,
        progress_callback: Optional[Callable[[JobProgressStage], None]] = None,
    ) -> AnalysisResultDTO:
        """
        Executes analysis using existing ST-EVA production runner and returns serialized DTO.
        """
        clean_ticker = ticker.upper().strip()

        if progress_callback:
            progress_callback(JobProgressStage.RESOLVING)

        archive = self.get_archive(clean_ticker)
        archive_path = self.get_archive_path(clean_ticker)

        temp_context_file = archive_path.with_suffix(".context.json")

        try:
            if progress_callback:
                progress_callback(JobProgressStage.FETCHING_SEC)

            # run_st_eva executes resolve, build_evidence, analyze, _build_context_if_requested,
            # and _archive_run (which performs 3.34 admission persistence).
            if progress_callback:
                progress_callback(JobProgressStage.ADMISSION)

            if progress_callback:
                progress_callback(JobProgressStage.VALUATION)

            core_result = run_st_eva(
                ticker=clean_ticker,
                mode=mode,
                reference_multiple=reference_multiple,
                horizon_years=horizon_years,
                save_snapshot=False,
                context_path=str(temp_context_file),
                archive=archive,
            )

            if core_result is None:
                raise ValueError(f"Could not acquire usable market data for ticker '{clean_ticker}'.")

            if progress_callback:
                progress_callback(JobProgressStage.ARCHIVE_REPLAY)

            # Run replay if price_date is available
            as_of_date = core_result.get("as_of")
            replay_summary = ReplaySummary()

            if as_of_date:
                try:
                    replay_res = replay(
                        archive,
                        clean_ticker,
                        as_of_date,
                        default_replay_doc_builder,
                    )
                    replay_summary = ReplaySummary(
                        attempted=True,
                        outcome=replay_res.outcome,
                        reason=replay_res.reason,
                        matched=replay_res.matched,
                        reconstructed=replay_res.reconstructed,
                        observations_used=replay_res.observations_used,
                        observations_considered=replay_res.observations_considered,
                        replay_fidelity=replay_res.replay_fidelity,
                        stored_document_hash=replay_res.stored_document_hash,
                        rebuilt_document_hash=replay_res.rebuilt_document_hash,
                    )
                except Exception as replay_err:
                    replay_summary = ReplaySummary(
                        attempted=True,
                        outcome="FAILED",
                        reason=f"Replay execution error: {replay_err}",
                    )

            # Read investment context if written to extract refusals / unavailable items
            refusal_items: List[RefusalItem] = []
            refusal_reasons: List[str] = []
            if temp_context_file.exists():
                try:
                    with temp_context_file.open("r", encoding="utf-8") as f:
                        ctx_doc = json.load(f)
                        for unav in ctx_doc.get("unavailable", []):
                            ref_str = unav.get("ref")
                            reason_str = unav.get("reason", "")
                            refusal_items.append(
                                RefusalItem(ref=ref_str, reason=reason_str)
                            )
                            if reason_str:
                                refusal_reasons.append(reason_str)
                except Exception:
                    pass

            # Extract admissions summary from archive
            admissions_list = archive.admissions_for(clean_ticker)
            metrics_admitted: List[str] = []
            total_admitted = 0
            total_refused = 0

            for adm in admissions_list:
                if adm.get("admitted") == 1:
                    total_admitted += 1
                    metric_name = adm.get("metric")
                    if metric_name and metric_name not in metrics_admitted:
                        metrics_admitted.append(metric_name)
                else:
                    total_refused += 1
                    refusals_json = adm.get("refusals_json")
                    if refusals_json:
                        try:
                            parsed_refs = json.loads(refusals_json)
                            for item in parsed_refs:
                                reason_str = item.get("reason") or item.get("label") or str(item)
                                refusal_items.append(
                                    RefusalItem(
                                        ref=adm.get("metric"),
                                        reason=reason_str,
                                        category=item.get("label"),
                                    )
                                )
                                refusal_reasons.append(reason_str)
                        except Exception:
                            refusal_reasons.append(str(refusals_json))

            admission_summary = AdmissionSummary(
                total_admitted=total_admitted,
                total_refused=total_refused,
                metrics_admitted=metrics_admitted,
                refusals=refusal_items,
            )

            # Build ValuationSummary from core_result
            market_snap = core_result.get("market_snapshot", {})
            obs_val = core_result.get("observed_valuation", {})
            implied = core_result.get("market_implied_assumptions", {})
            ref_info = core_result.get("reference", {})

            valuation_summary = ValuationSummary(
                analysis_type=core_result.get("analysis_type"),
                current_price=market_snap.get("price"),
                currency=market_snap.get("currency"),
                as_of=core_result.get("as_of"),
                forward_eps_at_reference_multiple=implied.get("forward_eps_at_reference_multiple"),
                eps_gap_vs_consensus=implied.get("eps_gap_vs_consensus"),
                required_eps_cagr=implied.get("required_eps_cagr_from_current_eps"),
                selected_pe=ref_info.get("multiple"),
                observed_pe=obs_val.get("current_pe"),
                observed_ps=obs_val.get("current_ps"),
                observed_pfcf=obs_val.get("current_pfcf"),
                observed_ev_ebitda=obs_val.get("current_ev_ebitda"),
                consensus_forward_eps=core_result.get("consensus_cross_check", {}).get("consensus_forward_eps"),
                limitations=core_result.get("limitations", []),
            )

            # Source identifiers
            source_identifiers = [
                market_snap.get("provider"),
                market_snap.get("source"),
                market_snap.get("source_type"),
            ]
            source_identifiers = [s for s in source_identifiers if s]

            dto = AnalysisResultDTO(
                ticker=core_result.get("ticker", clean_ticker),
                company_name=core_result.get("company_name", ""),
                status="success",
                research_id=core_result.get("research_id"),
                as_of=core_result.get("as_of"),
                source_identifiers=source_identifiers,
                admission_summary=admission_summary,
                valuation_summary=valuation_summary,
                replay_summary=replay_summary,
                refusal_reasons=sorted(list(set(refusal_reasons))),
                raw_analysis=core_result,
            )

            if progress_callback:
                progress_callback(JobProgressStage.COMPLETED)

            return dto

        finally:
            archive.close()
            if temp_context_file.exists():
                try:
                    temp_context_file.unlink()
                except Exception:
                    pass

