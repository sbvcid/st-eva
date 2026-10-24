"""
Adapter converting between external API requirements and existing ST-EVA core modules.
Does NOT modify or duplicate financial logic or validation rules.
"""

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import json

from sqlite_archive import SQLiteArchive
from core_registry import CoreRegistry
from registry_seed import seed
from archive import PRODUCTION_REFERENCE_REQUEST_KEY, replay
from st_eva_runner import (
    run_st_eva,
    build_context_from_observations,
    load_production_historical_references,
    SnapshotManager,
)
from web.schemas import (
    AdmissionSummary,
    AdmittedMetric,
    AnalysisResultDTO,
    CalculationInput,
    CoverageResponseDTO,
    CrossingDerivation,
    FamilyCoverageDTO,
    FiledFigure,
    IssuerCoverageDTO,
    JobProgressStage,
    ProductionHistoricalMultiplesDistributionDTO,
    ProductionHistoricalPfcfSummaryDTO,
    ProvenanceEntryDTO,
    RefusalItem,
    ReplaySummary,
    ReverseRequirementsReportDTO,
    ValuationSummary,
)


def _production_reference_payloads(
    ticker: str,
    request: Dict[str, Optional[int]],
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    The production distributions the archived run's references came from.

    The archive names the sources and the number of observations behind each
    reference. The count says which load of the dataset the run used: a
    distribution built with the furnished evidence and one built without it
    hold different numbers of observations, so a rebuild that reads the other
    load would report a reference the run did not select.
    """
    production_historical_pe = None
    production_historical_pfcf = None
    production_historical_multiples = None
    if "pe" in request:
        production_historical_pe, _, _ = load_production_historical_references(
            ticker,
            include_historical_pe=True,
        )
        expected = request.get("pe")
        observed = ((production_historical_pe or {}).get("distribution") or {}).get(
            "sample_count"
        )
        if (
            expected is not None
            and observed is not None
            and int(observed) != int(expected)
        ):
            production_historical_pe, _, _ = load_production_historical_references(
                ticker,
                include_historical_pe=True,
                enable_furnished_pe=False,
            )
    if "pfcf" in request:
        _, production_historical_pfcf, _ = load_production_historical_references(
            ticker,
            include_historical_pfcf=True,
        )
    if "multiples_ps" in request or "multiples_ev_ebitda" in request:
        _, _, production_historical_multiples = load_production_historical_references(
            ticker,
            include_historical_multiples=True,
        )
    return production_historical_pe, production_historical_pfcf, production_historical_multiples


def default_replay_doc_builder(
    observation_set: Any,
    as_of: str,
    generated_at: str,
    asset_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Helper adapting archive.replay observation set to build_context_from_observations."""
    metadata = asset_metadata or {}
    # The archive names the production reference sources the archived run had in
    # force. They are read here with the same loader a live run uses, so the
    # rebuild cannot select a reference the run did not use, nor miss the one
    # it did.
    request = metadata.get(PRODUCTION_REFERENCE_REQUEST_KEY) or {}
    production_historical_pe, production_historical_pfcf, production_historical_multiples = (
        _production_reference_payloads(observation_set.ticker, request)
    )
    return build_context_from_observations(
        [
            observation_set.get(identifier)
            for identifier in observation_set.ids()
        ],
        ticker=observation_set.ticker,
        as_of=as_of,
        generated_at=generated_at,
        asset_metadata=asset_metadata,
        production_historical_pe=production_historical_pe,
        production_historical_pfcf=production_historical_pfcf,
        production_historical_multiples=production_historical_multiples,
    )


# Where per-ticker archives live unless a caller says otherwise. Named so the
# default is visible at every use site and so a test can assert against it.
DEFAULT_ARCHIVES_DIR = "data/archives"


def _as_number(value: Any) -> Optional[float]:
    """
    The value when it is a real finite number, else None.

    The runner reports an absent operand with a sentinel (``UNAVAILABLE``), and
    an absent operand is an absence -- never 0, never a parse error. Only the
    market-cap operand is read through this so far, because it is the one the
    summary carries straight from the runner's snapshot.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _as_int(value: Any) -> Optional[int]:
    """A real integer observation count when the payload carries one, else None."""
    number = _as_number(value)
    if number is None or not float(number).is_integer():
        return None
    return int(number)


def _family_coverage(distribution: Optional[Dict[str, Any]]) -> FamilyCoverageDTO:
    """
    One family's coverage from the distribution's own payload.

    The gate is the distribution's own `usable_for_reference` flag -- the same
    flag `production_pe_for_reference` and its siblings gate on -- so the
    homepage states exactly the eligibility an analysis would apply. A thin
    sample keeps its INSUFFICIENT_OBSERVATIONS status and its refusal detail;
    a missing dataset keeps UNAVAILABLE. Neither ever renders as a zero
    multiple.
    """
    dist = distribution or {}
    return FamilyCoverageDTO(
        status=str(dist.get("status") or "UNAVAILABLE"),
        usable_for_reference=dist.get("usable_for_reference") is True,
        sample_count=_as_int(dist.get("sample_count")) or 0,
        min_observations_required=_as_int(dist.get("min_observations_required")),
        reason_detail=dist.get("reason_detail"),
    )


def coverage_summary() -> CoverageResponseDTO:
    """
    First-use coverage across every issuer the committed datasets establish.

    Tickers come from the three loaders' own ISSUER_CONFIGS (not a second
    hand-maintained list), and each family's state comes from
    `load_production_historical_references` -- the same pure, read-only load
    `run_st_eva` performs, with the same explicit UNAVAILABLE payloads for
    unestablished datasets. Nothing is fetched, nothing is written, and no
    median is recomputed here: the homepage reports the datasets' own
    qualification, so it cannot drift from what an analysis would use.
    """
    from historical_pe import ISSUER_CONFIGS as PE_CONFIGS
    from historical_pfcf import ISSUER_CONFIGS as PFCF_CONFIGS
    from historical_multiples import ISSUER_CONFIGS as MULTIPLES_CONFIGS
    from st_eva_runner import load_production_historical_references

    tickers = sorted(set(PE_CONFIGS) | set(PFCF_CONFIGS) | set(MULTIPLES_CONFIGS))

    issuers: Dict[str, IssuerCoverageDTO] = {}
    for ticker in tickers:
        pe_payload, pfcf_payload, multiples_payload = (
            load_production_historical_references(
                ticker,
                include_historical_pe=True,
                include_historical_pfcf=True,
                include_historical_multiples=True,
            )
        )
        multiples_distributions = (multiples_payload or {}).get("distributions") or {}
        issuers[ticker] = IssuerCoverageDTO(
            ticker=ticker,
            pe=_family_coverage((pe_payload or {}).get("distribution")),
            ps=_family_coverage(
                multiples_distributions.get("P_S_RATIO_REFERENCE")
            ),
            pfcf=_family_coverage((pfcf_payload or {}).get("distribution")),
            ev_ebitda=_family_coverage(
                multiples_distributions.get("EV_EBITDA_RATIO_REFERENCE")
            ),
        )
    return CoverageResponseDTO(issuers=issuers)


def _crossing_metric_names() -> List[str]:
    """
    The metrics the admission process decides on, in the order it decides them.

    Read from the admission module rather than restated here, so the list the
    API reports is the list the admission actually walked and cannot drift
    from it.
    """
    from evidence_valuation_boundary import V1_CROSSING_METRICS

    return list(V1_CROSSING_METRICS)


def _derivations_from_archive(
    in_force: List[Dict[str, Any]],
    observations_by_contract: Dict[str, Any],
    price_currency: Optional[str],
) -> Dict[str, Any]:
    """
    The figures the crossing derived, read back from the archive.

    The archive holds the decision and the figure each decision admitted, so
    the derivation can be recomputed from what was recorded rather than from
    what the run happened to be holding in memory. The rule is the admission
    module's own, so the two cannot drift: the same function that produced the
    crossing's figures produces these.
    """
    from evidence_valuation_boundary import (
        CrossingFigure,
        crossing_derivations_from_figures,
    )

    figures: Dict[str, CrossingFigure] = {}
    origins: Dict[str, Any] = {}
    for row in in_force:
        if row.get("admitted") != 1:
            continue
        observation = observations_by_contract.get(row.get("contract_id"))
        if observation is None:
            continue
        metric = str(row.get("metric") or "")
        figures[metric] = CrossingFigure(
            value=observation.value,
            currency=observation.currency,
            period_start=observation.period_start,
            period_end=observation.period_end,
        )
        raw = observation.raw if isinstance(observation.raw, dict) else {}
        fact = raw.get("sec_fact") if isinstance(raw.get("sec_fact"), dict) else {}
        origins[metric] = _ArchivedOrigin(
            accession=fact.get("accession"),
            form=fact.get("form"),
            concept=(
                f"{fact.get('taxonomy')}:{fact.get('tag')}"
                if fact.get("taxonomy") and fact.get("tag")
                else None
            ),
            available_at=observation.available_at,
            availability_class=row.get("availability_class"),
            mapping_type=row.get("mapping_type"),
        )
    return crossing_derivations_from_figures(figures, price_currency, origins)


class _ArchivedOrigin:
    """The provenance of one admitted figure, as the archive recorded it."""

    def __init__(
        self,
        accession=None,
        form=None,
        concept=None,
        available_at=None,
        availability_class=None,
        mapping_type=None,
    ) -> None:
        self.accession = accession
        self.form = form
        self.concept = concept
        self.available_at = available_at
        self.availability_class = availability_class
        self.mapping_type = mapping_type
        self.duration_days = None


def _crossing_derivations_dto(raw: Any) -> Dict[str, CrossingDerivation]:
    """
    The derived figures, with the inputs and the rule each was derived by.

    The run computed them; this reports them. Nothing is recomputed here, so
    the number the reader sees is the number the crossing produced.
    """
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, CrossingDerivation] = {}
    for name, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        inputs: List[AdmittedMetric] = []
        for item in entry.get("inputs") or []:
            if not isinstance(item, dict):
                continue
            inputs.append(
                AdmittedMetric(
                    metric=str(item.get("metric") or ""),
                    value=item.get("value"),
                    currency=item.get("currency"),
                    period_start=item.get("period_start"),
                    period_end=item.get("period_end"),
                    accession=item.get("accession"),
                    form=item.get("form"),
                    source_concept=item.get("concept"),
                    availability_class=item.get("availability_class"),
                    mapping_type=item.get("mapping_type"),
                    available_at=item.get("available_at"),
                )
            )
        out[str(name)] = CrossingDerivation(
            value=entry.get("value"),
            formula=entry.get("formula"),
            inputs=inputs,
        )
    return out


def _calculation_inputs(
    core_result: Dict[str, Any],
) -> List[CalculationInput]:
    """
    What each reported multiple was computed from, and on what basis.

    The engine's own input provenance is the source: the runner recorded, for
    every figure the engine was given, where it came from and on what basis.
    The observed multiple and the formula that produced it are read from the
    analysis, so the two cannot disagree.

    The figures the engine did *not* use are reported too, in their own basis,
    so a reader can see what was filed and why it did not become the input.
    """
    provenance = core_result.get("input_provenance") or {}
    observed = core_result.get("observed_valuation") or {}

    # The multiple, the input it divides by, and how the two combine.
    plan = (
        ("pe", "current_eps", "current_pe", "price / trailing diluted EPS"),
        ("pfcf", "current_fcf", "current_pfcf", "market capitalisation / trailing free cash flow"),
        ("ev_ebitda", "current_ebitda", "current_ev_ebitda",
         "enterprise value / trailing EBITDA"),
        ("ps", "current_revenue", "current_ps", "market capitalisation / trailing revenue"),
    )
    out: List[CalculationInput] = []
    for multiple, metric, observed_key, formula in plan:
        entry = provenance.get(metric) or {}
        raw_value = entry.get("value")
        is_number = isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool)
        filed = entry.get("filed_trailing") or {}
        filed_raw = filed.get("value")
        filed_is_number = isinstance(filed_raw, (int, float)) and not isinstance(
            filed_raw, bool
        )
        out.append(
            CalculationInput(
                multiple=multiple,
                input_metric=metric,
                value=float(raw_value) if is_number else None,
                value_state="AVAILABLE" if is_number else "UNAVAILABLE",
                source=entry.get("source"),
                basis=entry.get("basis"),
                currency=entry.get("currency"),
                period_start=entry.get("period_start"),
                period_end=entry.get("period_end"),
                formula=entry.get("formula") or formula,
                used_by_engine=bool(entry.get("used_by_engine")),
                observed_multiple=observed.get(observed_key),
                observed_multiple_formula=formula,
                note=entry.get("note"),
                components=[
                    AdmittedMetric(
                        metric=str(item.get("metric") or item.get("evidence_class") or ""),
                        value=item.get("value"),
                        currency=item.get("currency"),
                        period_start=item.get("period_start"),
                        period_end=item.get("period_end"),
                        accession=item.get("accession"),
                        form=item.get("form"),
                        available_at=item.get("usable_date") or item.get("knowable_from"),
                    )
                    for item in (entry.get("components") or [])
                    if isinstance(item, dict)
                ],
                filed_trailing=(
                    FiledFigure(
                        value=float(filed_raw) if filed_is_number else None,
                        source=filed.get("source"),
                        basis=filed.get("basis"),
                        currency=filed.get("currency"),
                        derivation=filed.get("derivation"),
                        usable_from=filed.get("usable_from"),
                        window=filed.get("window"),
                        used_by_engine=bool(filed.get("used_by_engine")),
                        agrees_with_engine_input=filed.get("agrees_with_engine_input"),
                        note=filed.get("note"),
                        components=[
                            AdmittedMetric(
                                metric=str(item.get("metric") or ""),
                                value=item.get("value"),
                                currency=item.get("currency"),
                                period_end=item.get("period_end"),
                                accession=item.get("accession"),
                                form=item.get("form"),
                                available_at=item.get("usable_date") or item.get("knowable_from"),
                            )
                            for item in (filed.get("components") or [])
                            if isinstance(item, dict)
                        ],
                        q4_evidence=[
                            AdmittedMetric(
                                metric=str(item.get("form") or ""),
                                value=item.get("value"),
                                currency=item.get("currency"),
                                period_end=item.get("period_end"),
                                accession=item.get("accession"),
                                form=item.get("form"),
                                available_at=item.get("usable_date"),
                            )
                            for item in (filed.get("q4_evidence") or [])
                            if isinstance(item, dict)
                        ],
                    )
                    if filed
                    else None
                ),
            )
        )
    return out


def _web_visible_analysis(core_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    The analysis payload as the API reports it, without verbatim duplication.

    The reverse requirements report already travels as its own contract field,
    and the production historical P/E dataset already travels as its compact
    summary, so repeating them inside `raw_analysis` doubles a multi-megabyte
    response for data no web consumer reads. What remains is what the interface
    actually uses (`evidence_ids`, `market_snapshot`, `data_quality`) plus the
    rest of the analysis verbatim.

    This is a presentation copy only. The runner result, the archive and the
    context document keep every byte, so nothing here changes what is stored or
    what the CLI and dossier report.
    """
    visible = dict(core_result)

    # The report is delivered in full through `reverse_requirements`.
    report = visible.get("reverse_requirements")
    if isinstance(report, dict):
        visible["reverse_requirements"] = {
            key: value
            for key, value in report.items()
            if key in {"formula_version", "fingerprint", "status", "status_reason", "matrix_size"}
        }

    # The production datasets' per-observation detail is not part of the API
    # contract; their eligibility state, identity and provenance are, and they
    # are in the `production_historical_*` payloads and the report's own
    # summary fields.
    for key in (
        "production_historical_pe",
        "production_historical_pfcf",
        "production_historical_multiples",
    ):
        production = visible.get(key)
        if isinstance(production, dict):
            slim = dict(production)
            slim.pop("observations", None)
            slim.pop("annual_observations", None)
            distribution = slim.get("distribution")
            if isinstance(distribution, dict):
                slim["distribution"] = {
                    key: value for key, value in distribution.items() if key != "observations"
                }
            distributions = slim.get("distributions")
            if isinstance(distributions, dict):
                slim["distributions"] = {
                    metric: {
                        dkey: dvalue
                        for dkey, dvalue in dist.items()
                        if dkey != "observations"
                    }
                    for metric, dist in distributions.items()
                    if isinstance(dist, dict)
                }
            visible[key] = slim

    return visible


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
        Load the canonical ST-EVA core registry into the archive.

        The seed is applied on every run, not only to an empty registry. The
        seed is the canonical declaration of the metric registry, it is
        idempotent -- every row is written with INSERT OR REPLACE and nothing
        is deleted -- and re-seeding an archive is an operation the seed
        itself anticipates.

        Seeding only an empty registry left an archive that was created before
        a declaration changed answering with a registry that no longer matched
        the code. The admission it then decided was a decision about a registry
        that was not the one in force, and the archive and the product could
        disagree about the same issuer for as long as the archive existed. A
        test run against a fresh database would see the new declaration and a
        real archive would not, which is exactly the difference between a test
        that passes and a product that works.
        """
        seed(CoreRegistry(archive.connection))

    def run_analysis_pipeline(
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

            horizons_to_use = reverse_horizons
            if horizons_to_use is None and horizon_years != 1.0:
                horizons_to_use = [horizon_years]

            core_result = run_st_eva(
                ticker=clean_ticker,
                mode=mode,
                reference_multiple=reference_multiple,
                reference_multiples=reference_multiples,
                horizon_years=horizon_years,
                reverse_horizons=horizons_to_use if horizons_to_use else (1.0, 2.0, 3.0, 5.0),
                required_returns=required_returns if required_returns else (0.08, 0.10, 0.12, 0.15),
                prefer_eps_anchor=prefer_eps_anchor,
                user_eps=user_eps,
                ps_multiple=ps_multiple,
                ev_ebitda_multiple=ev_ebitda_multiple,
                pfcf_multiple=pfcf_multiple,
                save_snapshot=False,
                context_path=str(temp_context_file),
                archive=archive,
                # The production point-in-time historical P/E distribution is
                # the observed reference this web path needs: without it a
                # live submission has no eligible exit multiple and returns an
                # uncomputable matrix. The P/FCF reconstruction is enabled for
                # the same reason, so the cash-flow reference and its implied
                # figure are available to issuers whose dataset exists, and
                # stated as unavailable otherwise. The runner keeps the vendor
                # band, an ineligible distribution and an unsupported ticker as
                # three separate explicit states, and adds no network
                # acquisition of its own: the datasets it reads are the frozen
                # SEC filing and pricing evidence under
                # data/historical_pe/{TICKER} and data/historical_pfcf/{TICKER}.
                include_historical_pe=True,
                include_historical_pfcf=True,
                # The P/S and EV/EBITDA reconstructions are enabled for the
                # same reason: the sales and enterprise-value references and
                # their implied figures come from the committed point-in-time
                # datasets, stated as unavailable where none is established.
                include_historical_multiples=True,
                # The filed income-statement dataset carries no reference
                # distribution: it is what the trailing revenue and trailing
                # EBITDA the sales and enterprise-value multiples are computed
                # from are built from, so the denominators are stated periods
                # rather than the provider's undeclared ones.
                include_historical_income=True,
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
                    # Replay must rebuild from the SAME eligible observation set
                    # that produced the stored context. Live vendor fundamentals
                    # are archive-first-seen when they are archived, which is
                    # after the data date, so replaying at the data date excludes
                    # them and reports a spurious DIVERGED even for a faithful
                    # rebuild. The knowledge instant the archive actually holds
                    # is its archival watermark; replaying there compares the
                    # stored document against a genuine rebuild of the same
                    # eligible observations. A real change in a material input
                    # (a different value, or a reference assumption the archive
                    # does not store) still reports DIVERGED, and a strict
                    # earlier point-in-time replay is unaffected.
                    watermark = archive.archival_watermark(clean_ticker)
                    replay_cutoff = watermark or as_of_date
                    # Reconcile the archive against the context THIS run just
                    # archived, not an unrelated snapshot that happens to share
                    # the as_of. An asset can carry several contexts for one
                    # data moment (two supplied reference multiples say), and a
                    # selection by as_of alone would compare the rebuild against
                    # whichever was archived first -- a false match against an
                    # older, differently-conditioned context. The context id is
                    # read from the artifact this run wrote, so the engine's
                    # result dict is not widened to carry it (its CLI output is
                    # a tested invariant).
                    target_context_id = None
                    try:
                        if temp_context_file.exists():
                            target_context_id = json.loads(
                                temp_context_file.read_text(encoding="utf-8")
                            ).get("context_id")
                    except Exception:
                        target_context_id = None
                    replay_res = replay(
                        archive,
                        clean_ticker,
                        replay_cutoff,
                        default_replay_doc_builder,
                        context_id=target_context_id,
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
                        availability_classes=[
                            {"observation_id": ref, "class": klass}
                            for ref, klass in replay_res.availability_classes
                        ],
                        field_diffs=[
                            {"field": d["field"], "stored": d["stored"], "rebuilt": d["rebuilt"]}
                            for d in replay_res.field_diffs
                        ],
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

            # Extract admissions summary from archive.
            #
            # The counts are rows and the lists are unique metric names, which
            # the contract fixes. The rows counted are the ones in force: a
            # decision that a later decision supersedes is history, and
            # counting it would report a metric as both admitted and refused
            # after the registry changed. A row nothing supersedes is in
            # force, and two such rows for one metric are two rows.
            admissions_list = archive.admissions_for(clean_ticker)
            superseded = {
                row.get("supersedes")
                for row in admissions_list
                if row.get("supersedes")
            }
            in_force = [
                row for row in admissions_list
                if row.get("admission_id") not in superseded
            ]

            observations_by_contract: Dict[str, Any] = {}
            try:
                for observation in archive.all_observations(clean_ticker):
                    # The archive's contract id is the observation's own
                    # `observation_id`; the row it was read from is the same
                    # identity, and the admission names that.
                    identifier = getattr(observation, "observation_id", None)
                    if identifier:
                        observations_by_contract[identifier] = observation
            except Exception:
                observations_by_contract = {}

            metrics_admitted: List[str] = []
            metrics_refused: List[str] = []
            admitted_metrics: List[AdmittedMetric] = []
            total_admitted = 0
            total_refused = 0

            for adm in in_force:
                if adm.get("admitted") == 1:
                    total_admitted += 1
                    metric_name = adm.get("metric")
                    if metric_name and metric_name not in metrics_admitted:
                        metrics_admitted.append(metric_name)
                    observation = observations_by_contract.get(adm.get("contract_id"))
                    fact = {}
                    if observation is not None:
                        raw = observation.raw if isinstance(observation.raw, dict) else {}
                        fact = raw.get("sec_fact") if isinstance(raw.get("sec_fact"), dict) else {}
                    admitted_metrics.append(
                        AdmittedMetric(
                            metric=metric_name or "",
                            value=(
                                float(observation.value)
                                if observation is not None
                                and isinstance(observation.value, (int, float))
                                else None
                            ),
                            currency=observation.currency if observation is not None else None,
                            period_start=(
                                observation.period_start if observation is not None else None
                            ),
                            period_end=(
                                observation.period_end if observation is not None else None
                            ),
                            accession=fact.get("accession"),
                            form=fact.get("form"),
                            source_concept=(
                                f"{fact.get('taxonomy')}:{fact.get('tag')}"
                                if fact.get("taxonomy") and fact.get("tag")
                                else None
                            ),
                            availability_class=adm.get("availability_class"),
                            mapping_type=adm.get("mapping_type"),
                            available_at=(
                                observation.available_at if observation is not None else None
                            ),
                            source_url=observation.source_url if observation is not None else None,
                            decided_at=adm.get("decided_at"),
                        )
                    )
                else:
                    total_refused += 1
                    metric_name = adm.get("metric")
                    if metric_name and metric_name not in metrics_refused:
                        metrics_refused.append(metric_name)
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
                metrics_refused=metrics_refused,
                refusals=refusal_items,
                admitted_metrics=admitted_metrics,
                derivations=_crossing_derivations_dto(
                    _derivations_from_archive(
                        in_force,
                        observations_by_contract,
                        (core_result.get("market_snapshot") or {}).get("currency"),
                    )
                ),
            )

            # Build ValuationSummary from core_result
            market_snap = core_result.get("market_snapshot", {})
            obs_val = core_result.get("observed_valuation", {})
            implied = core_result.get("market_implied_assumptions", {})
            ref_info = core_result.get("reference", {})
            data_quality = core_result.get("data_quality", {})
            fundamental = core_result.get("fundamental_snapshot", {})

            valuation_summary = ValuationSummary(
                analysis_type=core_result.get("analysis_type"),
                current_price=market_snap.get("price"),
                currency=market_snap.get("currency"),
                as_of=core_result.get("as_of"),
                forward_eps_at_reference_multiple=implied.get("forward_eps_at_reference_multiple"),
                eps_gap_vs_consensus=implied.get("eps_gap_vs_consensus"),
                required_eps_cagr=implied.get("required_eps_cagr_from_current_eps"),
                selected_pe=ref_info.get("multiple"),
                selected_pe_basis=ref_info.get("method"),
                selected_pfcf=ref_info.get("pfcf_multiple"),
                selected_pfcf_basis=ref_info.get("pfcf_method"),
                implied_fcf_at_reference_multiple=implied.get("fcf_at_reference_multiple"),
                market_cap=_as_number(fundamental.get("current_market_cap")),
                enterprise_value=_as_number(fundamental.get("current_enterprise_value")),
                revenue=_as_number(fundamental.get("current_revenue")),
                ebitda=_as_number(fundamental.get("current_ebitda")),
                fcf=_as_number(fundamental.get("current_fcf")),
                summary_horizon_years=horizon_years,
                observed_pe=obs_val.get("current_pe"),
                observed_ps=obs_val.get("current_ps"),
                observed_pfcf=obs_val.get("current_pfcf"),
                observed_ev_ebitda=obs_val.get("current_ev_ebitda"),
                consensus_forward_eps=core_result.get("consensus_cross_check", {}).get("consensus_forward_eps"),
                consensus_forward_eps_period=data_quality.get("consensus_forward_eps_period"),
                consensus_forward_eps_period_end=data_quality.get(
                    "consensus_forward_eps_period_end"
                ),
                limitations=core_result.get("limitations", []),
            )

            # Source identifiers
            source_identifiers = [
                market_snap.get("provider"),
                market_snap.get("source"),
                market_snap.get("source_type"),
            ]
            source_identifiers = [s for s in source_identifiers if s]

            # Build ReverseRequirementsReportDTO from core_result
            reverse_reqs_dto: Optional[ReverseRequirementsReportDTO] = None
            rr_data = core_result.get("reverse_requirements")
            production_pe_summary: Optional[Dict[str, Any]] = None
            if rr_data and isinstance(rr_data, dict):
                try:
                    reverse_reqs_dto = ReverseRequirementsReportDTO.model_validate(rr_data)
                except Exception as exc:
                    raise ValueError(
                        f"Reverse requirements contract validation failed: {exc}"
                    ) from exc
                # The compact production distribution statement, kept separate
                # from the vendor P/E band and from user assumptions.
                summary = rr_data.get("production_historical_pe_summary")
                if isinstance(summary, dict):
                    production_pe_summary = summary

            if production_pe_summary is None:
                # An unavailable or unsupported distribution is still a state the
                # API reports, not a silently absent block.
                raw_prod = core_result.get("production_historical_pe")
                if isinstance(raw_prod, dict):
                    prod_dist = raw_prod.get("distribution")
                    if isinstance(prod_dist, dict):
                        production_pe_summary = {
                            "status": prod_dist.get("status"),
                            "usable_for_reference": bool(prod_dist.get("usable_for_reference")),
                            "sample_count": prod_dist.get("sample_count"),
                            "min_observations_required": prod_dist.get("min_observations_required"),
                            "reason_code": prod_dist.get("reason_code"),
                            "reason_detail": prod_dist.get("reason_detail"),
                        }

            # The cash-flow reference's compact statement, built the same way
            # from the run's own payload: the distribution's identity and
            # eligibility, plus the reconstruction's current snapshot. Absent
            # when the payload is absent entirely.
            production_pfcf_summary: Optional[Dict[str, Any]] = None
            raw_pfcf = core_result.get("production_historical_pfcf")
            if isinstance(raw_pfcf, dict):
                from historical_pfcf import production_pfcf_summary

                production_pfcf_summary = production_pfcf_summary(raw_pfcf)

            # The report carries the cash-flow reference statement beside the
            # P/E one, so the scenario matrix and the export can state whether a
            # qualified P/FCF reference exists. The core report already emits it;
            # this keeps a legacy payload that predates that emission reporting
            # the same state rather than an absent one.
            if (
                reverse_reqs_dto is not None
                and reverse_reqs_dto.production_historical_pfcf_summary is None
                and production_pfcf_summary is not None
            ):
                reverse_reqs_dto = reverse_reqs_dto.model_copy(
                    update={
                        "production_historical_pfcf_summary": (
                            ProductionHistoricalPfcfSummaryDTO.model_validate(
                                production_pfcf_summary
                            )
                        )
                    }
                )

            # The sales and enterprise-value references' compact statement,
            # built the same way from the run's own payload: each
            # distribution's identity and eligibility. Absent when the payload
            # is absent entirely.
            production_multiples_summary: Optional[Dict[str, Any]] = None
            raw_multiples = core_result.get("production_historical_multiples")
            if isinstance(raw_multiples, dict):
                from historical_multiples import production_multiples_summary

                production_multiples_summary = production_multiples_summary(
                    raw_multiples
                )

            production_multiples_distributions: Optional[Dict[str, Any]] = None
            raw_multiples_distributions = (raw_multiples or {}).get(
                "distributions"
            )
            if isinstance(raw_multiples_distributions, dict):
                production_multiples_distributions = {
                    key: ProductionHistoricalMultiplesDistributionDTO.model_validate(
                        dist
                    )
                    for key, dist in raw_multiples_distributions.items()
                    if isinstance(dist, dict)
                }

            # Where each observed fundamental the multiples are computed from
            # came from and on what basis, so the UI and export can show the
            # observed financial period/source beside the reference multiple's
            # sampling period and the implied figure can be checked against
            # like-for-like facts. Absent when the run did not carry it.
            input_provenance: Optional[Dict[str, Any]] = None
            raw_input_provenance = core_result.get("input_provenance")
            if isinstance(raw_input_provenance, dict) and reverse_reqs_dto is not None:
                input_provenance = {
                    key: ProvenanceEntryDTO.model_validate(entry)
                    for key, entry in raw_input_provenance.items()
                    if isinstance(entry, dict)
                }
                if input_provenance:
                    reverse_reqs_dto = reverse_reqs_dto.model_copy(
                        update={"input_provenance": input_provenance}
                    )

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
                reverse_requirements=reverse_reqs_dto,
                production_historical_pe=production_pe_summary,
                production_historical_pfcf=production_pfcf_summary,
                production_historical_multiples=production_multiples_summary,
                production_historical_multiples_distributions=production_multiples_distributions,
                calculation_inputs=_calculation_inputs(core_result),
                raw_analysis=_web_visible_analysis(core_result),
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

