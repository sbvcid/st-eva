"""
Archive reconstruction completeness for the consensus sample the context carries.

The archive interface states the rule this module tests:

    a snapshot that references facts the archive never saw cannot be replayed

The live path registers, beside the material evidence, the consensus sample the
selected estimate carries -- `numberOfAnalysts`, a low/high range, the revision
counts, the trend series and the in-series differences (17 observations). They
are not material evidence, so they never enter `EVIDENCE_METRICS`. They were,
however, being written into the context document without being archived, so a
consensus-bearing snapshot referenced 17 observations the archive did not hold
and could not be replayed.

These tests use the real saved products for AAPL, MSFT and MU -- the context
documents the live runs wrote -- not a synthetic stand-in. The three real
contexts are read directly; the end-to-end tests rebuild the run's observation
set from a real context, drive the ordinary live path and the ordinary replay,
and assert the consensus sample round-trips with matching provenance.

Nothing here changes the evidence-id contract: the 17 consensus observations
are archived beside the evidence, never inside it, so `evidence_ids` keeps its
order and its count.
"""

import json
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from archive import replay
from data_contract import (
    EVIDENCE_METRICS,
    MATERIAL_METRICS,
    METRIC_PRICE_HISTORY,
    METRIC_VOLUME_HISTORY,
    Observation,
)
from st_eva_runner import (
    CONSENSUS_EXTRA_METRICS,
    MarketData,
    consensus_sample_observations,
    market_data_from_observations,
    run_st_eva,
)
from web.service_adapter import AnalysisServiceAdapter, default_replay_doc_builder

# The real, committed context documents the live runs produced. MU is the
# archived snapshot the MU acceptance run wrote; AAPL and MSFT are the live
# context artifacts from the same baseline.
REAL_CONTEXTS = {
    "MU": REPO_ROOT / "history" / "mu_acceptance_20261016" / "stored_context_20261015.json",
    "AAPL": REPO_ROOT / "history" / "AAPL_context_20261015.json",
    "MSFT": REPO_ROOT / "history" / "MSFT_context_20261015.json",
}

# The 17 consensus observations the context registers beyond the material set.
EXPECTED_CONSENSUS_METRICS = sorted(CONSENSUS_EXTRA_METRICS)

# The 14 identifiers the evidence contract fixes, in order. The consensus
# sample must never enter this list.
EXPECTED_EVIDENCE_IDS = [
    "ev-price-001",
    "ev-current-eps-001",
    "ev-forward-eps-001",
    "ev-consensus-eps-001",
    "ev-pe-band-001",
    "ev-pfcf-band-001",
    "ev-ps-band-001",
    "ev-ev-ebitda-band-001",
    "ev-fcf-001",
    "ev-ebitda-001",
    "ev-revenue-001",
    "ev-enterprise-value-001",
    "ev-market-cap-001",
    "ev-metrics-001",
]


def _load_json(path):
    with open(path, encoding="utf-8-sig") as handle:
        return json.load(handle)


def _observation_entries(document):
    """Every observation the context references, keyed by observation id."""
    entries = {}
    for ref, entry in document.get("provenance", {}).get("refs", {}).items():
        if isinstance(entry, dict) and entry.get("kind") == "obs":
            obs_id = entry.get("observation_id") or ref.split(":", 1)[-1]
            entries[obs_id] = entry
    return entries


def _figure_value(document, metric, ref):
    for row in document.get("observed", {}).get(metric) or []:
        figure = row.get("figure") or {}
        if figure.get("ref") == ref:
            return figure.get("value")
    return None


def _observations_from_context(document, *, include_comparable=False):
    """
    Rebuild the run's observation objects from a saved context document.

    The document's own provenance payloads carry each observation's metric,
    unit, currency, period, provider, source type, methodology and identity, and
    the figure carries its value, so the reconstruction is the real acquisition
    evidence and not a re-invention of it.
    """
    wanted = (
        set(MATERIAL_METRICS)
        | set(CONSENSUS_EXTRA_METRICS)
        | {METRIC_PRICE_HISTORY, METRIC_VOLUME_HISTORY}
    )
    observations = []
    for ref, entry in document.get("provenance", {}).get("refs", {}).items():
        if not isinstance(entry, dict) or entry.get("kind") != "obs":
            continue
        metric = entry.get("metric")
        if metric not in wanted:
            continue
        obs_id = entry.get("observation_id") or ref.split(":", 1)[-1]
        if not include_comparable and obs_id.startswith("cmp-"):
            continue
        observations.append(
            Observation(
                observation_id=obs_id,
                metric=metric,
                value=_figure_value(document, metric, ref),
                unit=entry.get("unit") or "",
                currency=entry.get("currency"),
                currency_basis=entry.get("currency_basis") or "NOT_APPLICABLE",
                period_start=entry.get("period_start"),
                period_end=entry.get("period_end"),
                as_of=entry.get("as_of"),
                available_at=entry.get("available_at"),
                available_at_basis=entry.get("available_at_basis") or "UNDECLARED",
                provider=entry.get("provider") or "",
                source_type=entry.get("source_type") or "",
                source_url=entry.get("source_url"),
                definition=entry.get("definition") or "",
                methodology=entry.get("methodology") or "",
                retrieved_at=entry.get("retrieved_at") or "2026-10-15T00:00:00+00:00",
                raw=entry.get("raw"),
                observation_count=entry.get("observation_count"),
                basis=entry.get("basis"),
            )
        )
    return observations


class _StubProvider:
    """Serves an already-built view, so the test never touches the network."""

    def __init__(self, data):
        self._data = data

    def fetch(self, _ticker):
        return self._data


class RealContextEvidence(unittest.TestCase):
    """The 17 consensus observations exist in the three real saved products."""

    def test_every_real_context_carries_all_seventeen_consensus_metrics(self):
        for ticker, path in REAL_CONTEXTS.items():
            with self.subTest(ticker=ticker):
                self.assertTrue(path.exists(), f"missing real artifact {path}")
                document = _load_json(path)
                observed = document.get("observed", {})
                present = [m for m in EXPECTED_CONSENSUS_METRICS if m in observed]
                self.assertEqual(
                    present,
                    EXPECTED_CONSENSUS_METRICS,
                    f"{ticker} is missing consensus metrics from its real context",
                )

    def test_each_consensus_metric_carries_source_period_unit_and_identity(self):
        document = _load_json(REAL_CONTEXTS["MU"])
        entries = _observation_entries(document)
        for metric in EXPECTED_CONSENSUS_METRICS:
            with self.subTest(metric=metric):
                rows = document["observed"][metric]
                self.assertEqual(len(rows), 1)
                figure = rows[0]["figure"]
                ref = figure["ref"]
                entry = entries[ref.split(":", 1)[-1]]
                # Source identity and the source field path survive.
                self.assertTrue(entry.get("provider"))
                self.assertIn("Yahoo", entry["provider"])
                self.assertTrue(entry.get("methodology"))
                self.assertTrue(entry.get("observation_id"))
                # Unit is stated and matches the figure's own unit.
                self.assertTrue(entry.get("unit"))
                self.assertEqual(entry["unit"], figure.get("unit"))
                # The forecast period is the same for the sample and the trend
                # series it belongs to; the revision counts carry none.
                if metric not in {
                    "consensus_forward_eps_down_revisions_90d",
                }:
                    self.assertEqual(entry.get("period_end"), "2028-08-31")

    def test_a_count_and_a_range_are_not_given_a_currency(self):
        document = _load_json(REAL_CONTEXTS["MU"])
        entries = _observation_entries(document)
        for metric in (
            "consensus_forward_eps_analyst_count",
            "consensus_forward_eps_up_revisions_7d",
            "consensus_forward_eps_down_revisions_30d",
        ):
            with self.subTest(metric=metric):
                rows = document["observed"][metric]
                entry = entries[rows[0]["figure"]["ref"].split(":", 1)[-1]]
                self.assertEqual(entry.get("unit"), "count")
                self.assertIsNone(entry.get("currency"))

    def test_the_source_absent_revision_count_is_preserved_not_zeroed(self):
        # The source did not state a 90-day downward revision count for any of
        # the three; an absent value must stay absent, and the context marks it
        # unavailable rather than reading it as zero.
        for ticker, path in REAL_CONTEXTS.items():
            with self.subTest(ticker=ticker):
                document = _load_json(path)
                figure = document["observed"][
                    "consensus_forward_eps_down_revisions_90d"
                ][0]["figure"]
                self.assertIsNone(figure.get("value"))
                self.assertEqual(figure.get("provenance_kind"), "UNAVAILABLE")


class ConsensusArchivalContract(unittest.TestCase):
    """
    A consensus-bearing run archives every observation its context references,
    and its replay reproduces the context exactly.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="consensus-archive-")
        self.archives_dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.document = _load_json(REAL_CONTEXTS["MU"])
        self.observations = _observations_from_context(self.document)
        self.data = market_data_from_observations(
            self.observations,
            ticker="MU",
            company_name="Micron Technology",
            exchange="NMS",
            as_of="2026-10-15",
        )

    def _run_live(self):
        adapter = AnalysisServiceAdapter(archives_dir=str(self.archives_dir))
        archive = adapter.get_archive("MU")
        self.addCleanup(archive.close)
        context_file = self.archives_dir / "MU.context.json"
        with patch(
            "st_eva_runner.YahooFinanceProvider",
            return_value=_StubProvider(self.data),
        ), patch(
            "st_eva_runner._acquire_sec_evidence",
            return_value={
                "observations": [],
                "documents": [],
                "cik": None,
                "entity_name": None,
                "cross_validation": {},
                "acquired": False,
            },
        ):
            core = run_st_eva(
                ticker="MU",
                mode="live",
                reference_multiple=None,
                reverse_horizons=[1.0, 2.0, 3.0, 5.0],
                required_returns=[0.08, 0.10, 0.12, 0.15],
                save_snapshot=False,
                context_path=str(context_file),
                archive=archive,
                include_historical_pe=False,
            )
        return adapter, archive, context_file, core

    def _archived_observation_ids(self, adapter):
        connection = sqlite3.connect(str(adapter.get_archive_path("MU")))
        try:
            rows = connection.execute(
                "SELECT o.contract_id FROM observations o"
                " JOIN assets a ON a.asset_id = o.asset_id WHERE a.ticker = 'MU'"
            ).fetchall()
        finally:
            connection.close()
        return {row[0] for row in rows}

    def test_the_archive_holds_every_observation_the_context_references(self):
        adapter, _archive, context_file, _core = self._run_live()
        document = _load_json(context_file)
        referenced = set(_observation_entries(document))
        archived = self._archived_observation_ids(adapter)
        missing = referenced - archived
        self.assertEqual(missing, set(), f"context references un-archived facts: {missing}")

    def test_the_seventeen_consensus_observations_are_archived(self):
        adapter, _archive, _context_file, _core = self._run_live()
        archived = self._archived_observation_ids(adapter)
        expected_ids = {
            entry.get("observation_id")
            for metric, entry in _observation_entries(self.document).items()
            if entry.get("metric") in CONSENSUS_EXTRA_METRICS
        }
        self.assertEqual(len(expected_ids), 17)
        self.assertTrue(expected_ids.issubset(archived), expected_ids - archived)

    def test_the_context_snapshot_reads_back_unchanged(self):
        _adapter, archive, context_file, _core = self._run_live()
        written = _load_json(context_file)
        stored = archive.context_by_id("MU", written["context_id"])
        self.assertIsNotNone(stored)
        self.assertEqual(stored, written)

    def test_the_replay_reproduces_the_consensus_bearing_context(self):
        _adapter, archive, context_file, _core = self._run_live()
        written = _load_json(context_file)
        watermark = archive.archival_watermark("MU")
        result = replay(
            archive,
            "MU",
            watermark,
            default_replay_doc_builder,
            context_id=written["context_id"],
        )
        self.assertEqual(result.outcome, "MATCH")
        self.assertTrue(result.matched)
        self.assertEqual(
            result.document["context_id"], written["context_id"]
        )

    def test_the_rebuilt_consensus_provenance_matches_the_stored_one(self):
        _adapter, archive, context_file, _core = self._run_live()
        written = _load_json(context_file)
        watermark = archive.archival_watermark("MU")
        result = replay(
            archive,
            "MU",
            watermark,
            default_replay_doc_builder,
            context_id=written["context_id"],
        )
        self.assertIsNotNone(result.document)
        stored_entries = _observation_entries(written)
        rebuilt_entries = _observation_entries(result.document)
        for metric in EXPECTED_CONSENSUS_METRICS:
            with self.subTest(metric=metric):
                stored_row = written["observed"][metric][0]
                rebuilt_row = result.document["observed"][metric][0]
                self.assertEqual(rebuilt_row["figure"], stored_row["figure"])
                stored_entry = stored_entries[
                    stored_row["figure"]["ref"].split(":", 1)[-1]
                ]
                rebuilt_entry = rebuilt_entries[
                    rebuilt_row["figure"]["ref"].split(":", 1)[-1]
                ]
                for field in (
                    "metric",
                    "provider",
                    "source_type",
                    "unit",
                    "currency",
                    "currency_basis",
                    "period_end",
                    "methodology",
                    "observation_id",
                ):
                    self.assertEqual(
                        rebuilt_entry.get(field),
                        stored_entry.get(field),
                        f"{metric}.{field} diverged",
                    )

    def test_evidence_ids_keep_their_order_and_never_include_consensus(self):
        _adapter, _archive, _context_file, core = self._run_live()
        self.assertEqual(core["evidence_ids"], EXPECTED_EVIDENCE_IDS)
        self.assertEqual(len(core["evidence_ids"]), len(EVIDENCE_METRICS))
        # The consensus *average* is material evidence and belongs in the list.
        # The 17 consensus *sample* observations do not, and must not have
        # leaked in beside it.
        sample_ids = {
            entry.get("observation_id")
            for entry in _observation_entries(self.document).values()
            if entry.get("metric") in CONSENSUS_EXTRA_METRICS
        }
        self.assertEqual(len(sample_ids), 17)
        self.assertEqual(set(core["evidence_ids"]) & sample_ids, set())

    def test_a_context_without_a_consensus_sample_is_unchanged(self):
        # A run whose observation set carries no consensus sample archives and
        # replays exactly as before: the fix adds observations only when the
        # context actually references them.
        without = [
            observation
            for observation in self.observations
            if observation.metric not in CONSENSUS_EXTRA_METRICS
        ]
        data = market_data_from_observations(
            without, ticker="MU", company_name="Micron Technology",
            exchange="NMS", as_of="2026-10-15",
        )
        adapter = AnalysisServiceAdapter(archives_dir=str(self.archives_dir))
        archive = adapter.get_archive("MU")
        self.addCleanup(archive.close)
        context_file = self.archives_dir / "MU.context.json"
        with patch(
            "st_eva_runner.YahooFinanceProvider", return_value=_StubProvider(data)
        ), patch(
            "st_eva_runner._acquire_sec_evidence",
            return_value={
                "observations": [], "documents": [], "cik": None,
                "entity_name": None, "cross_validation": {}, "acquired": False,
            },
        ):
            run_st_eva(
                ticker="MU", mode="live", reference_multiple=None,
                reverse_horizons=[1.0], required_returns=[0.10],
                save_snapshot=False, context_path=str(context_file),
                archive=archive, include_historical_pe=False,
            )
        written = _load_json(context_file)
        self.assertNotIn("consensus_forward_eps_low", written["observed"])
        watermark = archive.archival_watermark("MU")
        result = replay(
            archive, "MU", watermark, default_replay_doc_builder,
            context_id=written["context_id"],
        )
        self.assertEqual(result.outcome, "MATCH")


class ConsensusSampleSelection(unittest.TestCase):
    """The selection helper picks exactly the consensus metrics."""

    def _observation(self, metric):
        return Observation(
            observation_id=f"obs-{metric}-001",
            metric=metric,
            value=1.0,
            unit="count",
            currency=None,
            currency_basis="NOT_APPLICABLE",
            period_start=None,
            period_end=None,
            as_of=None,
            available_at=None,
            available_at_basis="UNDECLARED",
            provider="YahooFinanceFundamentals",
            source_type="API_LIVE",
            source_url=None,
            definition="",
            methodology="",
            retrieved_at="2026-10-15T00:00:00+00:00",
        )

    def test_selects_only_the_consensus_metrics(self):
        observations = [
            self._observation("consensus_forward_eps_analyst_count"),
            self._observation("revenue"),
            self._observation("consensus_forward_eps_low"),
            self._observation("price"),
        ]
        selected = consensus_sample_observations(observations)
        self.assertEqual(
            [o.metric for o in selected],
            ["consensus_forward_eps_analyst_count", "consensus_forward_eps_low"],
        )

    def test_none_is_dropped_and_nothing_else_is_picked_up(self):
        self.assertEqual(consensus_sample_observations([]), [])
        self.assertEqual(
            consensus_sample_observations([None, None]), []
        )


if __name__ == "__main__":
    unittest.main()
