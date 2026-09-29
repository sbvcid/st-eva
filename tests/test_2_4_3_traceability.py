"""
ST-EVA 2.4.3 regression tests.

Three findings from experiment 001, each of which failed against the 2.4.2 code
before it was fixed.

    S1  series comparability. Period span, basis, and observation type decide
        whether two points may be differenced at all. When they may not, the
        Context says so instead of producing a number.

    S2  refusal reasons must be machine-readable. A refusal that omits its
        cause is a guess waiting to happen.

    S3  a derived figure must be able to reach its own freshness, validation,
        and refusal state without a reader assembling it from three sections.

No ticker appears in any of these.
"""

import unittest

from investment_context import (
    DISCONTINUITY_RELATIVE_THRESHOLD,
    NOT_COMPARABLE,
    SERIES_COMPARABLE,
    NEGATIVE_INPUT,
    NON_POSITIVE_DENOMINATOR,
    period_span_bucket,
    reason_code_for,
    series_key,
    series_metadata,
)
from data_contract import (
    AvailabilityBasis,
    METRIC_CASH,
    METRIC_DEBT,
    METRIC_REVENUE,
    Observation,
    SourceType,
    Unit,
)
from st_eva_runner import (
    DeterministicMetricsEngine,
    MarketImpliedAssumptionsEngine,
    build_evidence,
    material_observations,
    metrics_observation,
)


RETRIEVED = "2026-09-28T12:00:00+00:00"


def reported(
    observation_id,
    metric,
    value,
    period_start,
    period_end,
    as_of=None,
    available_at="2026-08-01T12:00:00.000Z",
):
    return Observation(
        observation_id=observation_id,
        metric=metric,
        value=value,
        unit=Unit.CURRENCY.value,
        currency="USD",
        currency_basis="REPORTED",
        period_start=period_start,
        period_end=period_end,
        as_of=as_of or period_end,
        available_at=available_at,
        available_at_basis=AvailabilityBasis.ACCEPTANCE_DATETIME.value,
        provider="SecEdgar",
        source_type=SourceType.REGULATORY_FILING.value,
        source_url=None,
        definition="d",
        methodology="m",
        retrieved_at=RETRIEVED,
        raw={},
    )


def derived(
    observation_id,
    metric,
    value,
    period_start,
    period_end,
    derivation,
):
    observation = reported(
        observation_id, metric, value, period_start, period_end
    )
    return Observation(
        **{
            **{
                field: getattr(observation, field)
                for field in observation.__dataclass_fields__
            },
            "raw": {"derivation": derivation},
        }
    )


class TestS1SeriesComparability(unittest.TestCase):
    """
    S1: only observations on the same period span, basis, and observation type
    may be differenced. Otherwise the Context reports the series as not
    comparable instead of inventing a change.
    """

    def test_period_span_buckets_a_quarter_from_a_year(self):
        self.assertEqual(period_span_bucket("2026-01-01", "2026-03-31"), "QUARTERLY")
        self.assertEqual(period_span_bucket("2025-04-01", "2026-03-30"), "ANNUAL")
        self.assertEqual(period_span_bucket(None, "2026-03-31"), "INSTANT")
        self.assertEqual(
            period_span_bucket("2026-01-01", "2026-06-30"), "CUMULATIVE",
            "six months is neither a quarter nor a year",
        )

    def test_a_quarter_is_never_differenced_against_a_year(self):
        series = [
            reported("q-1", METRIC_REVENUE, 70_000_000_000, "2025-03-30", "2025-06-28"),
            reported("fy-1", METRIC_REVENUE, 281_724_000_000, "2024-07-01", "2025-06-28"),
            reported("q-2", METRIC_REVENUE, 77_673_000_000, "2025-06-29", "2025-09-28"),
        ]
        report = series_metadata(series)[METRIC_REVENUE]
        self.assertEqual(report["series_status"], NOT_COMPARABLE)
        self.assertEqual(
            report["series_status_reason"], "PERIOD_SPAN_MISMATCH"
        )
        self.assertEqual(
            report["discontinuities"], [],
            "a 90-day quarter and a 364-day period must not be differenced",
        )

    def test_a_mixed_span_reports_the_groups_it_holds(self):
        series = [
            reported("q-1", METRIC_REVENUE, 70_000_000_000, "2025-03-30", "2025-06-28"),
            reported("q-2", METRIC_REVENUE, 77_673_000_000, "2025-06-29", "2025-09-28"),
            reported("fy-1", METRIC_REVENUE, 281_724_000_000, "2024-07-01", "2025-06-28"),
        ]
        report = series_metadata(series)[METRIC_REVENUE]
        spans = {
            bucket["period_span"]: bucket
            for bucket in report["bases"].values()
        }
        self.assertIn("QUARTERLY", spans)
        self.assertIn("ANNUAL", spans)
        self.assertEqual(spans["QUARTERLY"]["observations"], 2)
        self.assertEqual(spans["ANNUAL"]["observations"], 1)
        self.assertEqual(report["series_status_reason"], "PERIOD_SPAN_MISMATCH")

    def test_a_real_discontinuity_within_one_span_survives(self):
        """
        The fix must not swallow the finding it was meant to keep. Two
        comparable instants moving three-fold is a real discontinuity.
        """
        series = [
            reported("d-1", METRIC_DEBT, 8_470_000_000, None, "2026-04-26"),
            reported("d-2", METRIC_DEBT, 33_366_000_000, None, "2026-07-26"),
        ]
        report = series_metadata(series)[METRIC_DEBT]
        self.assertEqual(report["series_status"], SERIES_COMPARABLE)
        self.assertEqual(len(report["discontinuities"]), 1)
        self.assertEqual(
            report["discontinuities"][0]["from_period"], "2026-04-26"
        )
        self.assertAlmostEqual(
            report["discontinuities"][0]["relative_change"], 2.938, places=2
        )
        self.assertEqual(
            report["discontinuities"][0]["explanation"],
            "NOT_EXPLAINED_BY_ST_EVA",
        )

    def test_a_reported_and_a_constructed_window_are_not_differenced(self):
        series = [
            reported("q-1", METRIC_REVENUE, 70_000_000_000, "2025-03-30", "2025-06-28"),
            derived(
                "ttm-1", METRIC_REVENUE, 250_000_000_000,
                "2024-07-01", "2025-06-28", "ANNUAL_ROLL_FORWARD",
            ),
        ]
        report = series_metadata(series)[METRIC_REVENUE]
        self.assertEqual(report["discontinuities"], [])
        self.assertEqual(report["series_status"], NOT_COMPARABLE)

    def test_an_undated_vendor_point_cannot_open_a_comparable_span(self):
        undated = Observation(
            observation_id="cmp-revenue-yahoo",
            metric=METRIC_REVENUE,
            value=302_970_000_000.0,
            unit=Unit.CURRENCY.value,
            currency="USD",
            currency_basis="REPORTED",
            period_start=None,
            period_end=None,
            as_of="2026-07-31",
            available_at=None,
            available_at_basis=AvailabilityBasis.UNDECLARED.value,
            provider="YahooFinanceFundamentals",
            source_type=SourceType.API_LIVE.value,
            source_url=None,
            definition="d",
            methodology="m",
            retrieved_at=RETRIEVED,
            raw={},
        )
        series = [
            reported("f-1", METRIC_REVENUE, 26_914_000_000, "2021-02-01", "2022-01-30"),
            undated,
        ]
        report = series_metadata(series)[METRIC_REVENUE]
        self.assertEqual(report["series_status"], NOT_COMPARABLE)
        self.assertEqual(report["discontinuities"], [])

    def test_two_points_on_one_period_are_a_restatement_not_a_step(self):
        original = reported(
            "a-1", METRIC_DEBT, 4_834_000_000, "2006-09-30", "2007-09-29",
            available_at="2009-10-27T16:30:00.000Z",
        )
        restated = reported(
            "a-2", METRIC_DEBT, 6_119_000_000, "2006-09-30", "2007-09-29",
            available_at="2010-01-25T16:30:00.000Z",
        )
        report = series_metadata([original, restated])[METRIC_DEBT]
        self.assertEqual(
            report["discontinuities"], [],
            "two versions of one period are not a series step",
        )
        pairs = report["same_period_pairs"]
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["period_end"], "2007-09-29")
        self.assertEqual(pairs[0]["from_value"], 4_834_000_000.0)
        self.assertEqual(pairs[0]["to_value"], 6_119_000_000.0)
        self.assertEqual(pairs[0]["relationship"], "RESTATEMENT_OR_REVISION")

    def test_a_single_series_reports_its_thinness_not_incomparability(self):
        series = [
            reported("s-1", METRIC_DEBT, 1.0, None, "2026-01-25"),
        ]
        report = series_metadata(series)[METRIC_DEBT]
        self.assertEqual(report["series_status"], SERIES_COMPARABLE)
        self.assertEqual(
            report["comparability"], "SINGLE_OBSERVATION_NO_TREND"
        )

    def test_the_series_key_names_what_it_compared_on(self):
        key = series_key(
            reported("q", METRIC_REVENUE, 1.0, "2025-03-30", "2025-06-28")
        )
        self.assertEqual(key["period_span"], "QUARTERLY")
        self.assertEqual(key["observation_type"], "REPORTED_PERIOD")
        self.assertEqual(key["basis"], "REPORTED")


class TestS2MachineReadableRefusalReasons(unittest.TestCase):
    """S2: a refusal carries a reason code, the input, and the condition."""

    def test_a_non_positive_denominator_is_named(self):
        code = reason_code_for(
            operation="divide",
            operand_states=[("available", 100.0), ("available", -1.0)],
            engine_value=None,
        )
        self.assertEqual(code["reason_kind"], NEGATIVE_INPUT)
        self.assertEqual(code["reason_code"], NON_POSITIVE_DENOMINATOR)
        self.assertEqual(code["operand_position"], 1)
        self.assertEqual(code["input_value"], -1.0)
        self.assertIn("input_ref", code)

    def test_a_missing_operand_is_reported_as_missing_not_as_negative(self):
        code = reason_code_for(
            operation="divide",
            operand_states=[("available", 100.0), ("unavailable", None)],
            engine_value=None,
        )
        self.assertNotEqual(code["reason_kind"], NEGATIVE_INPUT)
        self.assertEqual(code["reason_kind"], "MISSING_INPUT")

    def test_an_unexplained_absence_is_still_machine_readable(self):
        code = reason_code_for(
            operation="divide",
            operand_states=[("available", 100.0), ("available", 5.0)],
            engine_value=None,
        )
        self.assertEqual(code["reason_kind"], "NOT_AVAILABLE")
        self.assertEqual(code["reason_code"], "ENGINE_PRODUCED_NO_VALUE")
        self.assertIn("explanation", code)

    def test_every_reason_code_is_from_a_closed_vocabulary(self):
        from investment_context import REASON_CODES, REASON_KINDS

        for states, operation in (
            ([("available", 1.0), ("available", 0.0)], "divide"),
            ([("available", 1.0), ("unavailable", None)], "divide"),
            ([("available", 1.0), ("available", 2.0)], "divide"),
        ):
            code = reason_code_for(
                operation=operation,
                operand_states=states,
                engine_value=None,
            )
            self.assertIn(code["reason_kind"], REASON_KINDS)
            self.assertIn(code["reason_code"], REASON_CODES)

    def test_a_positive_engagement_claims_nothing(self):
        code = reason_code_for(
            operation="divide",
            operand_states=[("available", 10.0), ("available", 2.0)],
            engine_value=5.0,
        )
        self.assertIsNone(code)


class TestS3DerivedFigureTraceability(unittest.TestCase):
    """S3: a derived figure reaches its own state without a reader assembling it."""

    def test_a_derived_figure_carries_state_flags_only_when_something_is_wrong(self):
        from investment_context import ContextBuilder, PROVENANCE_UNAVAILABLE

        import unittest as _unittest

        from st_eva_runner import (
            CompanyResolver,
            DeterministicMetricsEngine,
            MarketImpliedAssumptionsEngine,
            build_evidence,
            material_observations,
            metrics_observation,
        )

        data = CompanyResolver.resolve("MSFT", mode="regression")
        metrics = DeterministicMetricsEngine.compute(
            data.price_history, data.volume_history
        )
        evidence = build_evidence(data, metrics)
        analysis = MarketImpliedAssumptionsEngine.analyze(data)
        materials = list(material_observations(data).values())
        document = build_document(
            data, analysis, evidence, metrics, materials
        )

        # Every derived figure states its validation state.
        for name, entry in document["derived"].items():
            self.assertIn("validation_state", entry)
            self.assertIn("validation_refs", entry)
            # `state_flags` is deliberately optional: present only when there is
            # something to say, so a clean figure is not padded with an empty
            # array that would have to be read to learn it is empty.
            if "state_flags" in entry:
                self.assertTrue(entry["state_flags"])

        current_pe = document["derived"]["current_pe"]
        self.assertEqual(current_pe["validation_state"], "UNVALIDATED")
        flags = {flag["kind"] for flag in current_pe["state_flags"]}
        self.assertIn("UNVALIDATED_INPUTS", flags)

        # A figure whose inputs are all derived or constant has nothing to flag
        # beyond its validation state, and does not carry the key.
        self.assertNotIn(
            "state_flags", document["derived"]["consensus_price_gap"]
        )

        # An unavailable derived figure reaches its refusal.
        required = document["derived"]["required_eps_cagr"]
        self.assertEqual(
            required["figure"]["provenance_kind"], PROVENANCE_UNAVAILABLE
        )
        refusals = [
            item
            for item in document["unavailable"]
            if item["ref"] == "der:required_eps_cagr"
        ]
        self.assertEqual(len(refusals), 1)
        self.assertIn("reason_kind", refusals[0])
        self.assertIn("reason_code", refusals[0])

    def test_a_negative_denominator_refusal_names_its_input(self):
        """
        The NU shape: free cash flow is present and negative, so the ratio is
        refused for a reason a machine can read.
        """
        from investment_context import (
            ContextBuilder,
        )
        from st_eva_runner import (
            CompanyResolver,
            DeterministicMetricsEngine,
            MarketImpliedAssumptionsEngine,
            build_evidence,
            material_observations,
            metrics_observation,
        )

        data = CompanyResolver.resolve("AAPL", mode="regression")
        data.current_fcf = -136_683_000_000.0
        metrics = DeterministicMetricsEngine.compute(
            data.price_history, data.volume_history
        )
        evidence = build_evidence(data, metrics)
        analysis = MarketImpliedAssumptionsEngine.analyze(data)
        materials = list(material_observations(data).values())
        builder = ContextBuilder(
            data=data,
            analysis=analysis,
            evidence=evidence,
            metrics=metrics,
            material_observations=materials
            + [metrics_observation(data, metrics)],
            generated_at=RETRIEVED,
        )
        document = builder.build()
        builder.validate(document)
        refusal = next(
            item
            for item in document["unavailable"]
            if item["ref"] == "der:current_pfcf"
        )
        self.assertEqual(refusal["reason_kind"], NEGATIVE_INPUT)
        self.assertEqual(refusal["reason_code"], NON_POSITIVE_DENOMINATOR)
        self.assertEqual(refusal["input_ref"], "obs:ev-fcf-001")
        self.assertEqual(refusal["input_value"], -136_683_000_000.0)
        self.assertEqual(refusal["condition"], "DIVISOR_MUST_BE_POSITIVE")
        self.assertIn("no interpretation", refusal["reason"])
        self.assertEqual(
            refusal["blocks"], [],
            "the input is present; this is not a missing-data case",
        )


class TestS2ReasonCodeCoverage(unittest.TestCase):
    """
    A to E: every refusal in a real context is machine-readable, and the code
    comes from the closed vocabulary rather than being invented per call site.

    The two classes covered here are the observation-level and reference-level
    refusals, which are the ones a derived figure never passes through and
    which were therefore the easiest to leave uncoded.
    """

    TICKERS = ("MSFT", "TENCENT", "MU", "NU")

    def _documents(self):
        from st_eva_runner import CompanyResolver

        for ticker in self.TICKERS:
            data = CompanyResolver.resolve(ticker, mode="regression")
            metrics = DeterministicMetricsEngine.compute(
                data.price_history, data.volume_history
            )
            evidence = build_evidence(data, metrics)
            analysis = MarketImpliedAssumptionsEngine.analyze(data)
            materials = list(material_observations(data).values())
            yield ticker, build_document(
                data, analysis, evidence, metrics, materials
            )

    def test_a_observation_level_refusals_carry_a_code(self):
        """A: NOT_REPORTED_BY_SOURCE always names why."""
        seen = 0
        for ticker, document in self._documents():
            for item in document["unavailable"]:
                if item["reason_kind"] != "NOT_REPORTED_BY_SOURCE":
                    continue
                seen += 1
                self.assertEqual(
                    item["reason_code"],
                    "SOURCE_DID_NOT_REPORT",
                    f"{ticker}: {item['item']} has no reason_code",
                )
        self.assertGreater(seen, 0, "no observation-level refusals were exercised")

    def test_b_reference_level_refusals_carry_a_code(self):
        """B: NO_REFERENCE_AVAILABLE always names why."""
        seen = 0
        for ticker, document in self._documents():
            for item in document["unavailable"]:
                if item["reason_kind"] != "NO_REFERENCE_AVAILABLE":
                    continue
                seen += 1
                self.assertEqual(
                    item["reason_code"],
                    "REFERENCE_NOT_AVAILABLE",
                    f"{ticker}: {item['item']} has no reason_code",
                )
        self.assertGreater(seen, 0, "no reference-level refusals were exercised")

    def test_c_derived_figure_refusals_keep_kind_and_code(self):
        """C: the derived path is unchanged by this fix."""
        expected = {
            "MISSING_INPUT": "INPUT_OBSERVATION_UNAVAILABLE",
            "NEGATIVE_INPUT": "NON_POSITIVE_DENOMINATOR",
            "INSUFFICIENT_OBSERVATIONS": "SERIES_TOO_THIN",
            "ENGINE_PRODUCED_NO_VALUE": "ENGINE_PRODUCED_NO_VALUE",
        }
        seen = set()
        for ticker, document in self._documents():
            for item in document["unavailable"]:
                if not item["ref"].startswith("der:"):
                    continue
                seen.add(item["reason_kind"])
                self.assertIn(
                    item["reason_kind"],
                    expected,
                    f"{ticker}: {item['ref']} has an unexpected reason_kind",
                )
                self.assertEqual(
                    item["reason_code"],
                    expected[item["reason_kind"]],
                    f"{ticker}: {item['ref']} reason_code moved",
                )
        self.assertIn("MISSING_INPUT", seen, "no derived refusal was exercised")

    def test_d_every_reason_code_comes_from_the_vocabulary(self):
        """
        D and E: the code is a member of REASON_CODES, and it is a real string
        rather than None, empty, or a per-site invention.
        """
        from investment_context import REASON_CODES, REASON_KINDS

        for ticker, document in self._documents():
            for item in document["unavailable"]:
                code = item.get("reason_code")
                self.assertIn(
                    code,
                    REASON_CODES,
                    f"{ticker}: {item['item']} code {code!r} is not in the "
                    "vocabulary",
                )
                self.assertIsInstance(code, str)
                self.assertTrue(
                    code.strip(),
                    f"{ticker}: {item['item']} has an empty code",
                )
                self.assertIn(item["reason_kind"], REASON_KINDS)
                self.assertTrue(
                    item.get("reason"),
                    f"{ticker}: {item['item']} has no explanation",
                )

    def test_the_vocabulary_was_not_widened(self):
        """
        The fix wires existing codes to existing kinds. It must not have
        introduced a kind or a code to get there.
        """
        from investment_context import REASON_CODES, REASON_KINDS

        self.assertEqual(
            len(REASON_KINDS), 7, "REASON_KINDS changed size"
        )
        self.assertEqual(
            len(REASON_CODES), 8, "REASON_CODES changed size"
        )
        self.assertEqual(
            set(REASON_CODES) - {
                "SOURCE_DID_NOT_REPORT",
                "INPUT_OBSERVATION_UNAVAILABLE",
                "REFERENCE_NOT_AVAILABLE",
                "SERIES_TOO_THIN",
                "OPERAND_CURRENCIES_DIFFER",
                "NON_POSITIVE_DENOMINATOR",
                "NON_POSITIVE_NUMERATOR",
                "ENGINE_PRODUCED_NO_VALUE",
            },
            set(),
            "REASON_CODES gained a member",
        )


def build_document(data, analysis, evidence, metrics, materials):
    from investment_context import build_investment_context

    return build_investment_context(
        data=data,
        analysis=analysis,
        evidence=evidence,
        metrics=metrics,
        material_observations=materials
        + [metrics_observation(data, metrics)],
        generated_at=RETRIEVED,
    )


if __name__ == "__main__":
    unittest.main()
