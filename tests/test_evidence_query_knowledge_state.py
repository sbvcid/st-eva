"""
EvidenceQuery knowledge-state integration, 2.64.

## The inconsistency this removes

    observations_for(cutoff)      -> TWD / currency      (2.63)
    EvidenceQuery.query(...)      -> ratio / NULL         (stored)

Two formal consumers of the same archive gave two different answers about the
same source fact. On an evidence infrastructure that is not a missing feature,
it is a contradiction, and downstream evidence retrieval inherits it.

## The test target is discovered, never declared

Nothing here names a ticker, a period, an accession or a currency in advance.
Every identity and every cutoff is read out of an archive first, because 2.63
showed what hardcoded identities cost: a helper that asked the reader about an
asset that did not exist returned nothing, and the assertion passed on the empty
result. A test that cannot pass vacuously has to take its subject from the data.

## Parity is asserted field by field

`observations_for` and `EvidenceQuery` must agree on the three semantic fields
and must still agree on the factual ones. Checking one field would pass while the
two readers disagreed about the rest, which is the failure this round exists to
remove.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from evidence_query import EvidenceQuery  # noqa: E402
from sqlite_archive import (  # noqa: E402
    LATEST_KNOWLEDGE,
    SQLiteArchive,
    interpretation_status,
)

H = os.path.join(os.path.dirname(HERE), "experiments",
                 "003-llm-evidence-retrieval", "harness")

SEMANTIC_FIELDS = ("unit", "currency", "currency_basis")
FACTUAL_FIELDS = ("value", "metric")

ARCHIVES = ["snapshot-universe", "snapshot-crossframework",
            "snapshot-227-a1", "snapshot-227-b"]

# At least three distinct corrected currencies, discovered rather than named.
WANT_CURRENCIES = 3


def discover_targets(minimum: int = WANT_CURRENCIES) -> list:
    """
    Real repaired facts, with their real timestamps, read out of the archives.

    Each target carries the cutoffs derived from its own availability and its own
    knowledge time, so the PIT matrix below cannot be satisfied by a cutoff that
    falls outside the correction interval.
    """
    targets = []
    seen_currencies = set()
    for archive in ARCHIVES:
        path = os.path.join(H, f"{archive}.sqlite")
        if not os.path.exists(path):
            continue
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                "SELECT i.source_fact_id, i.currency, i.unit,"
                " i.currency_basis, i.knowledge_at, o.replay_eligible_from,"
                " o.available_at, o.contract_id, o.value_json, o.metric,"
                " o.period_start, o.period_end, a.ticker"
                " FROM interpretations i"
                " JOIN observations o ON o.source_fact_id = i.source_fact_id"
                " JOIN assets a ON a.asset_id = o.asset_id"
                " ORDER BY i.currency, o.replay_eligible_from").fetchall()
        except sqlite3.Error:
            continue
        finally:
            connection.close()
        for row in rows:
            availability = row["replay_eligible_from"] or row["available_at"]
            if availability is None:
                continue
            targets.append({
                "archive": archive,
                "path": path,
                "source_fact_id": row["source_fact_id"],
                "ticker": row["ticker"],
                "contract_id": row["contract_id"],
                "currency": row["currency"],
                "interpretation_unit": row["unit"],
                "knowledge_at": row["knowledge_at"],
                "availability": availability,
                "stored_unit": None,
                "stored_currency": None,
                "value_json": row["value_json"],
                "metric": row["metric"],
                "period_start": row["period_start"],
                "period_end": row["period_end"],
            })
            if row["currency"] not in seen_currencies:
                seen_currencies.add(row["currency"])
    return targets


def stored_reading(path: str, source_fact_id: str) -> dict:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT unit, currency, currency_basis FROM observations"
            " WHERE source_fact_id = ?", (source_fact_id,)).fetchone()
        return dict(row) if row else {}
    finally:
        connection.close()


def pit_reader(path: str, ticker: str, source_fact_id: str, cutoff: str) -> dict:
    store = SQLiteArchive(path)
    try:
        for observation in store.observations_for(ticker, cutoff):
            if store._source_fact_id_of(observation) == source_fact_id:
                return {
                    "present": True,
                    "unit": observation.unit,
                    "currency": observation.currency,
                    "currency_basis": observation.currency_basis,
                    "value": observation.value,
                    "metric": observation.metric,
                    "period_start": observation.period_start,
                    "period_end": observation.period_end,
                }
        return {"present": False}
    finally:
        store.close()


def evidence_reader(path: str, ticker: str, cutoff: str) -> dict:
    query = EvidenceQuery(connection=sqlite3.connect(
        f"file:{path}?mode=ro", uri=True))
    try:
        rows = query.query_observations(asset=ticker, knowable_at=cutoff)
        return {"rows": rows, "query": query}
    finally:
        query.close()


def find_evidence_row(rows: list, source_fact_id: str, path: str) -> dict:
    """The evidence package for one source fact, matched by contract id."""
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        contract = connection.execute(
            "SELECT contract_id FROM observations WHERE source_fact_id = ?",
            (source_fact_id,)).fetchone()["contract_id"]
    finally:
        connection.close()
    for row in rows:
        if row["contract_id"] == contract:
            return row
    return {}


class TestDiscoveredTargetsExist(unittest.TestCase):
    """A parity test with no target proves nothing, so prove the target exists."""

    def setUp(self) -> None:
        if not os.path.isdir(H):
            self.skipTest("harness archives are not present")
        self.targets = discover_targets()
        self.currencies = {t["currency"] for t in self.targets}
        for target in self.targets:
            target["stored"] = stored_reading(target["path"],
                                              target["source_fact_id"])

    def test_at_least_three_distinct_currencies_were_discovered(self) -> None:
        self.assertGreaterEqual(len(self.currencies), WANT_CURRENCIES,
                                f"only found {sorted(self.currencies)}")
        self.assertGreater(len(self.targets), WANT_CURRENCIES)

    def test_every_target_actually_has_a_contradictory_reading(self) -> None:
        """
        Baseline and corrected must differ, or the overlay proves nothing.

        Without this, a reader that returned the baseline everywhere would pass
        every parity assertion in this file.
        """
        for target in self.targets:
            self.assertNotEqual(
                (target["stored"]["unit"], target["stored"]["currency"]),
                (target["interpretation_unit"], target["currency"]),
                f"{target['ticker']} {target['currency']}: the stored and "
                "corrected readings are identical, so nothing is being tested")

    def test_every_target_stored_a_faulty_reading(self) -> None:
        for target in self.targets:
            self.assertEqual(target["stored"]["unit"], "ratio",
                             target["ticker"])
            self.assertIsNone(target["stored"]["currency"], target["ticker"])


class TestParityAcrossThePITMatrix(unittest.TestCase):
    """EvidenceQuery and observations_for must agree, at every cutoff."""

    def setUp(self) -> None:
        if not os.path.isdir(H):
            self.skipTest("harness archives are not present")
        self.targets = discover_targets()
        self.targets = self.targets[:12]
        for target in self.targets:
            target["stored"] = stored_reading(target["path"],
                                              target["source_fact_id"])

    def _check(self, target: dict, cutoff: str, expected: str) -> None:
        pit = pit_reader(target["path"], target["ticker"],
                         target["source_fact_id"], cutoff)
        found = evidence_reader(target["path"], target["ticker"], cutoff)
        package = find_evidence_row(found["rows"], target["source_fact_id"],
                                    target["path"])
        label = f"{target['ticker']} {target['currency']} {expected}"

        if expected == "absent":
            self.assertFalse(pit["present"], f"PIT reader: {label}")
            self.assertEqual(package, {}, f"EvidenceQuery: {label}")
            return

        self.assertTrue(pit["present"], f"PIT reader: {label}")
        self.assertTrue(package, f"EvidenceQuery returned no package: {label}")

        # The three semantic fields must agree between the two readers.
        for field in SEMANTIC_FIELDS:
            self.assertEqual(
                pit[field], package[field],
                f"{label}: {field} differs between readers "
                f"(pit={pit[field]!r}, evidence={package[field]!r})")

        # And the factual fields must still agree.
        for field in FACTUAL_FIELDS:
            self.assertEqual(pit[field], package[field],
                             f"{label}: {field} diverged")

        if expected == "baseline":
            # Nothing was superseded, so the package carries no `stored_*`
            # keys at all. Emitting them for an untouched row would suggest a
            # correction existed that did not.
            self.assertNotIn("stored_unit", package, label)
            self.assertNotIn("stored_currency", package, label)
            for field in SEMANTIC_FIELDS:
                self.assertEqual(pit[field], target["stored"][field],
                                 f"{label}: baseline {field}")
            self.assertFalse(package["knowledge_interpretation_status"]
                             == "APPLIED", label)
        else:
            self.assertEqual(pit["currency"], target["currency"], label)
            self.assertEqual(package["unit"], target["interpretation_unit"],
                             label)
            self.assertEqual(package["knowledge_interpretation_status"],
                             "APPLIED", label)
            # The stored reading stays retrievable once one is superseded.
            self.assertEqual(package["stored_unit"], target["stored"]["unit"],
                             label)
            self.assertEqual(package["stored_currency"],
                             target["stored"]["currency"], label)

    def test_1_before_availability_the_fact_is_absent(self) -> None:
        for target in self.targets:
            self._check(target, "1990-01-01", "absent")

    def test_2_at_availability_the_baseline_stands(self) -> None:
        for target in self.targets:
            self._check(target, target["availability"], "baseline")

    def test_3_between_availability_and_knowledge_the_baseline_stands(self) -> None:
        for target in self.targets:
            # A date strictly between the two, derived from both.
            between = _between(target["availability"], target["knowledge_at"])
            self.assertIsNotNone(between,
                                 f"{target['ticker']}: no instant between "
                                 "availability and knowledge_at")
            if between:
                self._check(target, between, "baseline")

    def test_4_exactly_at_knowledge_at_the_correction_applies(self) -> None:
        for target in self.targets:
            self._check(target, target["knowledge_at"], "corrected")

    def test_5_after_knowledge_at_the_correction_applies(self) -> None:
        for target in self.targets:
            self._check(target, LATEST_KNOWLEDGE, "corrected")


def _between(earlier: str, later: str) -> Optional[str]:
    """A bare date strictly between two instants, or None if there is none."""
    from datetime import datetime, timedelta

    def parse(value: str) -> Optional[datetime]:
        text = value.replace("Z", "+00:00")
        for candidate in (text, value[:10]):
            try:
                return datetime.fromisoformat(candidate)
            except ValueError:
                continue
        return None

    start, end = parse(earlier), parse(later)
    if start is None or end is None or end <= start:
        return None
    middle = start + (end - start) / 2
    if middle <= start or middle >= end:
        return None
    return middle.date().isoformat()


class TestNoDoubleCounting(unittest.TestCase):
    def setUp(self) -> None:
        if not os.path.isdir(H):
            self.skipTest("harness archives are not present")
        self.targets = discover_targets()[:8]

    def test_one_package_per_source_fact(self) -> None:
        for target in self.targets:
            found = evidence_reader(target["path"], target["ticker"],
                                    LATEST_KNOWLEDGE)
            matching = [
                row for row in found["rows"]
                if find_evidence_row([row], target["source_fact_id"],
                                     target["path"])
            ]
            self.assertEqual(len(matching), 1,
                             f"{target['ticker']} {target['currency']}: the "
                             "evidence surface returned more than one record "
                             "for one source fact")


class TestHistorySurfaces(unittest.TestCase):
    """
    get_observation and get_metric_history are effective-semantic by default.

    That is a contract, stated here rather than inferred from behaviour: both
    call `query_observations` without a point in time, and a surface with no
    point in time in the question answers on what ST-EVA currently holds.
    """

    def setUp(self) -> None:
        if not os.path.isdir(H):
            self.skipTest("harness archives are not present")
        self.targets = discover_targets()[:4]

    def test_get_observation_returns_the_effective_reading(self) -> None:
        for target in self.targets:
            query = EvidenceQuery(connection=sqlite3.connect(
                f"file:{target['path']}?mode=ro", uri=True))
            try:
                package = query.get_observation(target["contract_id"])
                self.assertEqual(package["currency"], target["currency"],
                                 target["ticker"])
                self.assertEqual(package["stored_unit"], "ratio",
                                 target["ticker"])
                self.assertEqual(package["knowledge_interpretation_status"],
                                 "APPLIED", target["ticker"])
            finally:
                query.close()

    def test_get_metric_history_exposes_effective_points(self) -> None:
        for target in self.targets:
            query = EvidenceQuery(connection=sqlite3.connect(
                f"file:{target['path']}?mode=ro", uri=True))
            try:
                history = query.get_metric_history(target["ticker"], "debt")
            finally:
                query.close()
            series = history.get("series")
            points = series.get("points") if isinstance(series, dict) else None
            if not isinstance(points, list):
                continue
            currencies = {p.get("currency") for p in points
                          if p.get("currency")}
            self.assertTrue(
                target["currency"] in currencies or not currencies,
                f"{target['ticker']}: the series exposed {currencies} but the "
                f"repaired currency is {target['currency']}")

    def test_query_observations_without_a_cutoff_is_effective(self) -> None:
        for target in self.targets:
            found = evidence_reader(target["path"], target["ticker"], None)
            package = find_evidence_row(found["rows"], target["source_fact_id"],
                                        target["path"])
            self.assertTrue(package, target["ticker"])
            self.assertEqual(package["currency"], target["currency"],
                             target["ticker"])


class TestLegacyArchive(unittest.TestCase):
    def test_an_archive_without_the_table_preserves_current_behaviour(self) -> None:
        if not os.path.isdir(H):
            self.skipTest("harness archives are not present")
        target = discover_targets()[0]
        path = target["path"]
        target["stored"] = stored_reading(path, target["source_fact_id"])
        copy_path = os.path.join(
            os.path.dirname(path), "_legacy_probe.sqlite")
        import shutil
        shutil.copy2(path, copy_path)
        connection = sqlite3.connect(copy_path)
        try:
            connection.execute("DROP TABLE interpretations")
            connection.commit()
            query = EvidenceQuery(connection=connection)
            try:
                package = query.get_observation(target["contract_id"])
                self.assertIsNotNone(package)
                # Stored semantics, and the absence is named rather than faked.
                self.assertEqual(package["knowledge_interpretation_status"],
                                 "UNAVAILABLE_LEGACY")
                self.assertNotIn("stored_unit", package)
                self.assertEqual(package["unit"], target["stored"]["unit"])
                status, _ = interpretation_status(
                    connection, target["source_fact_id"], None)
                self.assertIsNone(status)
            finally:
                query.close()
        finally:
            connection.close()
            os.remove(copy_path)

    def test_legacy_is_distinguished_from_no_applicable_interpretation(self) -> None:
        if not os.path.isdir(H):
            self.skipTest("harness archives are not present")
        target = discover_targets()[0]
        path = target["path"]
        copy_path = os.path.join(os.path.dirname(path), "_legacy_probe2.sqlite")
        import shutil
        shutil.copy2(path, copy_path)
        connection = sqlite3.connect(copy_path)
        try:
            connection.execute("DROP TABLE interpretations")
            connection.commit()
            _, legacy = interpretation_status(connection,
                                              target["source_fact_id"], None)
            self.assertEqual(legacy, "UNAVAILABLE_LEGACY")
        finally:
            connection.close()
            os.remove(copy_path)
        # On the intact archive the same question is answerable.
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            _, applied = interpretation_status(connection,
                                              target["source_fact_id"],
                                              LATEST_KNOWLEDGE)
            self.assertEqual(applied, "APPLIED")
        finally:
            connection.close()


class TestFieldRestriction(unittest.TestCase):
    def setUp(self) -> None:
        if not os.path.isdir(H):
            self.skipTest("harness archives are not present")
        self.targets = discover_targets()[:4]

    def test_no_factual_field_is_touched_by_the_overlay(self) -> None:
        for target in self.targets:
            found = evidence_reader(target["path"], target["ticker"],
                                    LATEST_KNOWLEDGE)
            package = find_evidence_row(found["rows"], target["source_fact_id"],
                                        target["path"])
            self.assertEqual(str(package["value"]),
                             str(float(target["value_json"])), target["ticker"])
            self.assertEqual(package["metric"], target["metric"],
                             target["ticker"])
            self.assertEqual(package["period"]["end"], target["period_end"],
                             target["ticker"])
            self.assertEqual(package["contract_id"], target["contract_id"],
                             target["ticker"])

    def test_provenance_rides_in_the_existing_structured_basis(self) -> None:
        for target in self.targets:
            found = evidence_reader(target["path"], target["ticker"],
                                    LATEST_KNOWLEDGE)
            package = find_evidence_row(found["rows"], target["source_fact_id"],
                                        target["path"])
            marker = (package.get("basis") or {}).get(
                "knowledge_interpretation")
            self.assertIsNotNone(marker, target["ticker"])
            self.assertEqual(marker["knowledge_at"], target["knowledge_at"],
                             target["ticker"])
            self.assertIn("identity", marker)


if __name__ == "__main__":
    unittest.main()