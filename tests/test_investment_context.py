"""
ST-EVA 2.3-C tests.

The point of the phase is that a consumer can check every number in an
Investment Context without trusting ST-EVA. So the tests are mostly about
whether the document actually supports that, rather than about the shape of the
document.

Offline tests build a context from the static regression fixtures and synthetic
observations. Live tests are opt-in behind ST_EVA_LIVE=1.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from data_contract import (
    COMPARABLE_METRICS,
    METRIC_PRICE,
    METRIC_REVENUE,
   Observation,
   SourceType,
    AvailabilityBasis,
    Unit,
    ValidationStatus,
)
from cross_validation import cross_validate
import investment_context
from investment_context import (
    CONTEXT_SCHEMA_VERSION,
   KIND_OBSERVATION,
    KIND_REFERENCE,
   PROVENANCE_UNAVAILABLE,
    ContextBuilder,
    ContextError,
    ParityError,
    UnresolvedRefError,
    build_investment_context,
    check_conditional_figures_are_conditioned,
    check_data_quality_has_no_grade,
    check_derivations_declare_reasons,
    check_graph_acyclic,
    check_knowledge_cutoff,
    check_no_unavailable_value,
    check_no_verdict_vocabulary,
    check_operations_are_registered,
    check_references_resolve,
    compute_content_hash,
    derived_ref,
   recompute_derivation,
   split_ref,
    verify_document,
)
from operation_registry import (
    ArityError,
    MissingOperandError,
    ParameterError,
   UnknownOperationError,
    UnitRuleError,
    UnsupportedVersionError,
    evaluate,
    lookup,
    registered_operations,
    registry_contract,
    result_unit,
)
from sec_provider import SECProvider
from sqlite_archive import SQLiteArchive
from st_eva_runner import (
    CompanyResolver,
    DeterministicMetricsEngine,
    MarketImpliedAssumptionsEngine,
    MIN_BAND_OBSERVATIONS_FOR_REFERENCE,
    build_context_from_observations,
    build_evidence,
    material_observations,
    metrics_observation,
    run_st_eva,
)

REPO = Path(__file__).resolve().parent.parent


def _eligible_distribution(median="33.195873"):
    """An eligible production historical P/E distribution, as the loader emits it."""
    return {
        "distribution": {
            "status": "USABLE_FOR_REFERENCE",
            "usable_for_reference": True,
            "sample_count": 24,
            "total_evaluations": 27,
            "min_observations_required": 20,
            "period_start": "2021-07-28",
            "period_end": "2026-07-30",
            "percentiles": {
                "10th": 25.602182,
                "25th": 28.811204,
                "median": float(median),
                "75th": 35.400253,
                "90th": 36.088407,
            },
            "input_set_id": "e6719c725702af9b8cc44285a85fa89e1b4df175c0becbb46ac8a30dd847027c",
            "content_hash": "f3b133e4c5d42262d4ba1cb26266da05c3b4717f8862bcb26fded2c547df402d",
        }
    }


def build_context_for(ticker, **kwargs):
    """Build a context the same way the CLI does, from a fixture.

    `pe_band` replaces the fixture's vendor historical P/E band. A test that needs
    a band declaring an observation count can supply one without editing the
    shared fixture, and `resolve` builds a fresh view per call so nothing leaks
    between tests.
    """
    pe_band = kwargs.pop("pe_band", None)
    data = CompanyResolver.resolve(ticker, mode="regression")
    assert data is not None
    if pe_band is not None:
        data.historical_pe_band = dict(pe_band)
    metrics = DeterministicMetricsEngine.compute(
        data.price_history, data.volume_history
    )
    evidence = build_evidence(data, metrics)
    analysis = MarketImpliedAssumptionsEngine.analyze(data, **kwargs.pop("engine", {}))
    return build_investment_context(
        data=data,
        analysis=analysis,
        evidence=evidence,
        metrics=metrics,
        material_observations=list(material_observations(data).values())
        + [metrics_observation(data, metrics)],
        generated_at="2026-09-28T12:00:00+00:00",
        **kwargs,
    )


class TestOperationRegistry(unittest.TestCase):
    """The registry is the mechanism; it has to actually hold."""

    def test_every_operation_declares_its_full_contract(self):
        for operation_id in registered_operations():
            spec = lookup(operation_id)
            for field in (
                "operation_id",
                "version",
                "output_kind",
                "formula",
                "unit_rule",
                "missing_value_rule",
                "rationale",
            ):
                self.assertTrue(
                    getattr(spec, field),
                    f"{operation_id} declares no {field}",
                )
            self.assertTrue(
                spec.arity is not None or spec.arity_range is not None,
                f"{operation_id} declares no arity",
            )
            self.assertEqual(
                spec.missing_value_rule, "PROPAGATE",
                f"{operation_id} does not propagate a missing input",
            )

    def test_the_registry_is_embedded_in_the_document(self):
        contract = registry_contract()
        self.assertIn("operations", contract)
        self.assertIn("unit_rules", contract)
        self.assertEqual(
            len(contract["operations"]), len(registered_operations())
        )

    def test_an_unknown_operation_is_a_hard_error(self):
        with self.assertRaises(UnknownOperationError):
            evaluate("some_python_function", [1, 2])

    def test_an_unsupported_version_is_a_hard_error(self):
        with self.assertRaises(UnsupportedVersionError):
            evaluate("divide", [1, 2], version="99")

    def test_a_missing_input_propagates_and_never_substitutes(self):
        for operation, operands, units in (
            ("divide", [None, 2], ["currency", "per_share"]),
            ("multiply", [1, None], ["per_share", "multiple"]),
            ("mean", [None], ["ratio"]),
        ):
            with self.assertRaises(MissingOperandError):
                evaluate(operation, operands, units)

    def test_a_zero_is_never_substituted_for_a_missing_input(self):
        """The single most important rule, asserted against the arithmetic."""
        with self.assertRaises(MissingOperandError):
            evaluate("divide", [100.0, None], ["currency", "per_share"])

    def test_wrong_arity_is_rejected(self):
        with self.assertRaises(ArityError):
            evaluate("divide", [1.0])

    def test_an_undefined_unit_pair_is_rejected(self):
        with self.assertRaises(UnitRuleError):
            evaluate("divide", [1.0, 2.0], ["per_share", "currency"])
        with self.assertRaises(UnitRuleError):
            result_unit(lookup("subtract"), ["currency", "ratio"])

    def test_a_defined_unit_pair_yields_the_declared_result(self):
        self.assertEqual(
            result_unit(lookup("divide"), ["currency", "per_share"]),
            Unit.MULTIPLE.value,
        )
        self.assertEqual(
            result_unit(lookup("divide"), ["currency", "multiple"]),
            Unit.PER_SHARE.value,
        )

    def test_compound_growth_rate_matches_the_engine_expression(self):
        self.assertAlmostEqual(
            evaluate(
                "compound_growth_rate",
                [23.34, 5.0, 1.0],
                ["per_share", "per_share", "number"],
            ),
            (23.34 / 5.0) ** (1.0 / 1.0) - 1.0,
            places=12,
        )

    def test_a_parameter_out_of_range_is_rejected(self):
        with self.assertRaises(ParameterError):
            evaluate("percentile", [[1.0, 2.0]], ["ratio"], {"fraction": 1.5})
        with self.assertRaises(ParameterError):
            evaluate("percentile", [[1.0, 2.0]], ["ratio"], {})

    def test_a_folded_band_is_refused_rather_than_interpolated(self):
        folded = {
            "10th": 20.0,
            "25th": 25.0,
            "median": 22.0,
            "75th": 35.0,
            "90th": 40.0,
        }
        with self.assertRaises(ParameterError):
            evaluate(
                "percentile_position", [27.0, folded], ["multiple", "multiple"]
            )

    def test_percentile_position_agrees_with_the_engine(self):
        from st_eva_runner import interpolate_pe_percentile

        band = {
            "10th": 20.0,
            "25th": 25.0,
            "median": 30.0,
            "75th": 35.0,
            "90th": 40.0,
            "observations": 120,
        }
        for value in (5.0, 20.0, 22.5, 27.5, 30.0, 32.5, 40.0, 45.0):
            self.assertEqual(
                evaluate(
                    "percentile_position",
                    [value, band],
                    ["multiple", "multiple"],
                ),
                interpolate_pe_percentile(value, band),
                f"percentile position disagrees at {value}",
            )


class TestRefGrammar(unittest.TestCase):
    def test_a_bare_ref_parses(self):
        self.assertEqual(
            split_ref("der:implied_forward_eps"),
            ("der", "implied_forward_eps", None),
        )

    def test_a_named_selector_parses(self):
        self.assertEqual(
            split_ref("obs:ev-pe-band-001#median"),
            ("obs", "ev-pe-band-001", "median"),
        )

    def test_a_negative_index_parses(self):
        self.assertEqual(
            split_ref("obs:obs-price-history-001#-1"),
            ("obs", "obs-price-history-001", "-1"),
        )

    def test_a_malformed_ref_is_rejected(self):
        for bad in ("implied_forward_eps", "nope:thing", ":empty"):
            with self.assertRaises(ContextError, msg=bad):
                split_ref(bad)


class TestDocumentClosure(unittest.TestCase):
    """Every ref must resolve, and a missing one must be a hard failure."""

    def test_every_ref_in_a_real_context_resolves(self):
        document = build_context_for("MSFT")
        check_references_resolve(document)

    def test_every_derivation_operand_resolves(self):
        document = build_context_for("MSFT")
        refs = document["provenance"]["refs"]
        for ref, derivation in document["provenance"]["derivations"].items():
            for operand in derivation["operation"]["operands"]:
                self.assertIn(
                    operand.split("#")[0],
                    refs,
                    f"{ref} names an operand that does not resolve",
                )

    def test_a_dangling_ref_fails_loudly(self):
        document = build_context_for("MSFT")
        document["provenance"]["refs"]["obs:ev-forged-001"] = {
            "kind": "obs",
            "ref": "obs:ev-forged-001",
        }
        document["market_implied"]["figures"]["implied_forward_eps"][
            "ref"
        ] = "obs:ev-ghost-001"
        with self.assertRaises(UnresolvedRefError):
            check_references_resolve(document)

    def test_a_cycle_is_rejected(self):
        document = build_context_for("MSFT")
        derivations = document["provenance"]["derivations"]
        first = next(iter(derivations))
        derivations[first]["operation"]["operands"] = [first]
        with self.assertRaises(ContextError):
            check_graph_acyclic(document)

    def test_every_derivation_names_a_registered_operation(self):
        document = build_context_for("MSFT")
        check_operations_are_registered(document)

    def test_an_unregistered_operation_is_rejected(self):
        document = build_context_for("MSFT")
        derivation = next(
            iter(document["provenance"]["derivations"].values())
        )
        derivation["operation"]["op"] = "some_python_function"
        with self.assertRaises(ContextError):
            check_operations_are_registered(document)

    def test_provenance_is_singular_not_duplicated(self):
        """One ref, one record, so two copies cannot disagree."""
        document = build_context_for("MSFT")
        refs = document["provenance"]["refs"]
        self.assertEqual(len(refs), len(set(refs)))
        for ref, entry in refs.items():
            self.assertEqual(entry["ref"], ref)

    def test_a_derived_value_is_stored_in_exactly_one_place(self):
        """
        The address book holds an identity; the derived section holds the
        value. A second copy of the number could disagree with the first.
        """
        document = build_context_for("MSFT")
        for name, entry in document["derived"].items():
            if "value" in entry["figure"]:
                ref = entry["figure"]["ref"]
                stored = document["provenance"]["refs"][ref]
                self.assertNotIn(
                    "value",
                    stored,
                    f"{name}'s value is duplicated in the provenance table",
                )


class TestRecomputation(unittest.TestCase):
    """The central claim: a consumer can re-derive every number."""

    def test_every_deterministic_derivation_recomputes(self):
        document = build_context_for("MSFT")
        report = verify_document(document)
        self.assertGreater(report["recomputed"], 0)
        self.assertEqual(report["context_id"], document["context_id"])

    def test_recomputed_values_equal_the_stored_values(self):
        document = build_context_for("MSFT")
        for ref, derivation in document["provenance"]["derivations"].items():
            if not derivation.get("deterministic"):
                continue
            figure = document["derived"].get(split_ref(ref)[1], {}).get(
                "figure", {}
            )
            if "value" not in figure:
                continue
            recomputed = recompute_derivation(document, ref)
            self.assertIsNotNone(recomputed, f"{ref} did not recompute")
            self.assertAlmostEqual(
                float(recomputed),
                float(figure["value"]),
                places=6,
                msg=f"{ref}: recomputation disagrees with the stored value",
            )

    def test_the_headline_chain_reaches_a_raw_observation(self):
        """
        The user's example: implied EPS -> formula -> price and reference.
        The chain must terminate at an observation, in four hops.
        """
        document = build_context_for("MSFT")
        node = derived_ref("implied_to_consensus")
        hops = 0
        while node in document["provenance"]["derivations"] and hops < 10:
            derivation = document["provenance"]["derivations"][node]
            first = derivation["operation"]["operands"][0]
            if split_ref(first)[0] == KIND_OBSERVATION:
                break
            node = first.split("#")[0]
            hops += 1
        self.assertLessEqual(hops, 4, "the chain should reach an observation fast")
        self.assertEqual(
            split_ref(document["provenance"]["derivations"][
                derived_ref("implied_forward_eps")
            ]["operation"]["operands"][1])[0],
            KIND_REFERENCE,
            "implied EPS must name the reference it is conditional on",
        )

    def test_a_non_deterministic_derivation_must_declare_a_reason(self):
        document = build_context_for("MSFT")
        check_derivations_declare_reasons(document)
        for derivation in document["provenance"]["derivations"].values():
            if not derivation["deterministic"]:
                self.assertTrue(
                    derivation["non_deterministic_reason"],
                    "a non-recomputable derivation must say why",
                )

    def test_a_silent_non_deterministic_claim_is_rejected(self):
        document = build_context_for("MSFT")
        for derivation in document["provenance"]["derivations"].values():
            derivation["deterministic"] = False
            derivation["non_deterministic_reason"] = None
            break
        with self.assertRaises(ContextError):
            check_derivations_declare_reasons(document)

    def test_a_parity_failure_is_refused(self):
        """
        The engine is the authority and the registry is the check. A document
        must never state a number the published formula does not reproduce.
        """
        data = CompanyResolver.resolve("MSFT", mode="regression")
        metrics = DeterministicMetricsEngine.compute(
            data.price_history, data.volume_history
        )
        evidence = build_evidence(data, metrics)
        analysis = MarketImpliedAssumptionsEngine.analyze(data)
        # Corrupt a figure the engine actually computed. The MSFT fixture has no
        # trailing EPS, so current_pe is null and would be a vacuous test;
        # consensus_forward_pe is live.
        self.assertIsNotNone(
            analysis["observed_valuation"]["consensus_forward_pe"]
        )
        analysis["observed_valuation"]["consensus_forward_pe"] = 999.0
        with self.assertRaises(ParityError):
            build_investment_context(
                data=data,
                analysis=analysis,
                evidence=evidence,
                metrics=metrics,
                material_observations=list(
                    material_observations(data).values()
                )
                + [metrics_observation(data, metrics)],
            )


class TestUnavailableContract(unittest.TestCase):
    def test_an_unavailable_figure_carries_no_value(self):
        document = build_context_for("MSFT")
        check_no_unavailable_value(document)
        for name, entry in document["derived"].items():
            if entry["figure"]["provenance_kind"] == PROVENANCE_UNAVAILABLE:
                self.assertNotIn("value", entry["figure"])

    def test_an_unavailable_figure_is_not_null_but_absent(self):
        """
        The key is absent, not present-and-null. A consumer reading the value
        key gets "there is no number" rather than "the number is null", which
        is a weaker and more easily mishandled statement.
        """
        document = build_context_for("MSFT")
        entry = document["derived"]["current_pe"]
        self.assertNotIn("value", entry["figure"])
        self.assertEqual(
            entry["figure"]["provenance_kind"], PROVENANCE_UNAVAILABLE
        )

    def test_every_unavailable_item_states_a_reason(self):
        document = build_context_for("MSFT")
        self.assertTrue(document["unavailable"])
        for item in document["unavailable"]:
            self.assertTrue(item["reason"], item)
            self.assertTrue(item["reason_kind"], item)
            self.assertIn("blocks", item)

    def test_a_missing_input_names_what_it_blocks(self):
        """
        An absent input is not an isolated fact; it is why a dozen other
        figures are null. That edge has to be explicit.
        """
        document = build_context_for("MSFT")
        by_item = {item["item"]: item for item in document["unavailable"]}
        self.assertIn("trailing_eps", by_item)
        blocked = by_item["trailing_eps"]["blocks"]
        self.assertIn(derived_ref("current_pe"), blocked)
        self.assertIn(derived_ref("required_eps_cagr"), blocked)

    # The 2.2.3 engine names these figures differently from the context, so
    # the parity check is stated over an explicit mapping rather than a
    # coincidental name match.
    ENGINE_TO_CONTEXT_NAME = {
        "current_pe": "current_pe",
        "forward_pe": "forward_pe",
        "consensus_forward_pe": "consensus_forward_pe",
        "current_pfcf": "current_pfcf",
        "current_ev_ebitda": "current_ev_ebitda",
        "current_ps": "current_ps",
        "approx_historical_pe_percentile": "pe_percentile",
        "approx_historical_ps_percentile": "ps_percentile",
        "approx_historical_ev_ebitda_percentile": "ev_ebitda_percentile",
    }

    def test_engine_and_context_agree_on_what_is_missing(self):
        """The context invents no figure and drops none."""
        document = build_context_for("MSFT")
        result = run_st_eva("MSFT", mode="regression", save_snapshot=False)
        checked = 0
        for engine_key, context_name in self.ENGINE_TO_CONTEXT_NAME.items():
            if result["observed_valuation"].get(engine_key) is None:
                self.assertIn(
                    context_name,
                    document["derived"],
                    f"{engine_key} is null in the engine but absent from the "
                    "context entirely",
                )
                figure = document["derived"][context_name]["figure"]
                if figure["provenance_kind"] == PROVENANCE_UNAVAILABLE:
                    self.assertNotIn("value", figure)
                    checked += 1
        self.assertGreater(checked, 0, "the MSFT fixture exercises missing data")

    def test_a_context_with_unavailable_inputs_exists(self):
        document = build_context_for("MSFT")
        unavailable = [
            name
            for name, entry in document["derived"].items()
            if entry["figure"]["provenance_kind"] == PROVENANCE_UNAVAILABLE
        ]
        self.assertGreater(
            len(unavailable), 5,
            "the MSFT fixture is chosen because most of its inputs are absent",
        )

    def test_consensus_price_derivations_agree_on_missing_state(self):
        """When median PE cross check is unavailable, consensus price ratio/gap are retained with unavailable provenance."""
        document = build_context_for("MSFT")
        for key in ("consensus_price_at_median", "consensus_price_ratio", "consensus_price_gap"):
            self.assertIn(key, document["derived"])
            figure = document["derived"][key]["figure"]
            self.assertEqual(figure["provenance_kind"], PROVENANCE_UNAVAILABLE)
            self.assertNotIn("value", figure)


class TestConditionalContract(unittest.TestCase):
    def test_every_implied_figure_is_conditioned(self):
        document = build_context_for("MSFT")
        check_conditional_figures_are_conditioned(document)
        for name, entry in document["market_implied"]["figures"].items():
            self.assertTrue(
                entry["conditional_on"],
                f"{name} declares no conditional_on",
            )

    def test_an_unconditioned_figure_is_rejected(self):
        document = build_context_for("MSFT")
        entry = next(
            iter(document["market_implied"]["figures"].values())
        )
        entry["conditional_on"] = []
        with self.assertRaises(ContextError):
            check_conditional_figures_are_conditioned(document)

    def test_the_block_carries_a_conditional_statement(self):
        document = build_context_for("MSFT")
        self.assertTrue(
            document["market_implied"]["conditional_statement"]
        )

    def test_the_reference_states_its_basis_and_source(self):
        """
        The link 2.3-B found missing: the multiple every implied figure is
        conditional on had no provenance at all.
        """
        document = build_context_for("MSFT", engine={}, reference_multiple=30.0)
        reference = document["valuation_reference"]
        self.assertEqual(reference["basis"], "USER_SUPPLIED")
        self.assertTrue(reference["user_overridden"])
        self.assertIsNone(reference["source_ref"])
        self.assertEqual(reference["multiple"], 30.0)

        document = build_context_for("TENCENT")
        reference = document["valuation_reference"]
        self.assertIn(
            reference["basis"], ("HISTORICAL_MEDIAN", "USER_SUPPLIED", "NONE")
        )
        if reference["basis"] == "HISTORICAL_MEDIAN":
            self.assertTrue(
                reference["source_ref"],
                "a historical median must name the band it came from",
            )
            self.assertIn("eligibility_rule", reference)
            self.assertIn("eligible_as_reference", reference)

    def test_a_production_median_is_not_recorded_as_a_band_median(self):
        """
        The summary's production historical P/E median is not a vendor band
        statistic, so the context must not claim it came from the band.

        Deriving the basis from which number happens to be present would make
        exactly that false provenance claim: the extra figure here is
        price-implied, and its conditional_on names the same reference.

        The claim has to hold for *every* field that describes where the number
        came from, not only `source_ref`. `source_observation_count` was once
        read from the band whatever the basis was, so this same document could
        say the reference did not come from the band and then report the band's
        observation count as its own.
        """
        document = build_context_for(
            "MSFT",
            engine={"production_historical_pe": _eligible_distribution()},
        )
        reference = document["valuation_reference"]

        self.assertEqual(reference["basis"], "PRODUCTION_PE_MEDIAN")
        self.assertEqual(reference["multiple"], 33.195873)
        self.assertIsNone(
            reference["source_ref"],
            "a production median did not come from the vendor band",
        )
        self.assertEqual(
            reference["source_observation_count"],
            24,
            "the reference's own source is the production historical P/E "
            "distribution, which holds 24 observations",
        )
        self.assertTrue(reference["eligible_as_reference"])
        self.assertIn("production historical P/E distribution", reference["eligibility_rule"])
        self.assertEqual(
            reference["selection_method"], "production_historical_pe_median"
        )
        self.assertFalse(reference["user_overridden"])


class TestReferenceSourceObservationCount(unittest.TestCase):
    """
    `source_observation_count` is the observation count of the object the
    reference's own basis names, and of nothing else.

    The field used to be read from the vendor historical P/E band whatever the
    basis was, so a reference taken from the production distribution reported
    the band's count (7 for MSFT, 8 for AAPL) instead of its own (24, 36), and a
    supplied or unavailable reference reported the band's count although neither
    is based on any observations at all. Each case below pins one basis.
    """

    # An ineligible band that still declares a count: the shape a live
    # acquisition returns, and the object that used to be mistaken for the
    # reference's own source.
    VENDOR_BAND = {
        "median": 24.0,
        "10th": 20.0,
        "25th": 22.0,
        "75th": 27.0,
        "90th": 30.0,
        "observations": 7,
    }
    # An eligible band, so HISTORICAL_MEDIAN is reachable at all.
    ELIGIBLE_BAND = {
        "median": 30.0,
        "10th": 22.0,
        "25th": 26.0,
        "75th": 34.0,
        "90th": 38.0,
        "observations": 40,
    }

    def test_a_production_median_reports_the_distribution_count_not_the_bands(self):
        document = build_context_for(
            "MSFT",
            engine={"production_historical_pe": _eligible_distribution()},
            pe_band=self.VENDOR_BAND,
        )
        reference = document["valuation_reference"]

        self.assertEqual(reference["basis"], "PRODUCTION_PE_MEDIAN")
        self.assertEqual(
            reference["source_observation_count"],
            24,
            "the reference's source is the production distribution, which holds "
            "24 observations; the vendor band's 7 belongs to a different object",
        )
        self.assertNotEqual(
            reference["source_observation_count"],
            self.VENDOR_BAND["observations"],
            "the vendor band's count is not the reference's source count",
        )
        self.assertIsNone(reference["source_ref"], "the band did not supply the multiple")

    def test_a_production_median_keeps_its_count_with_no_band_present(self):
        document = build_context_for(
            "MSFT",
            engine={"production_historical_pe": _eligible_distribution()},
        )
        reference = document["valuation_reference"]

        self.assertEqual(reference["basis"], "PRODUCTION_PE_MEDIAN")
        self.assertEqual(
            reference["source_observation_count"],
            24,
            "the count belongs to the distribution, so a missing band cannot erase it",
        )

    def test_a_supplied_multiple_reports_no_source_observation_count(self):
        document = build_context_for(
            "MSFT",
            engine={"reference_multiple": 30.0},
            reference_multiple=30.0,
            pe_band=self.VENDOR_BAND,
        )
        reference = document["valuation_reference"]

        self.assertEqual(reference["basis"], "USER_SUPPLIED")
        self.assertIsNone(
            reference["source_observation_count"],
            "a multiple supplied on the command line is based on no observations, "
            "so the band's 7 is not its source count",
        )

    def test_an_unavailable_reference_reports_no_source_observation_count(self):
        document = build_context_for(
            "MSFT",
            engine={
                "production_historical_pe": {
                    "distribution": {
                        "status": "UNAVAILABLE",
                        "usable_for_reference": False,
                        "sample_count": 0,
                    }
                }
            },
            pe_band=self.VENDOR_BAND,
        )
        reference = document["valuation_reference"]

        self.assertEqual(reference["basis"], "NONE")
        self.assertIsNone(reference["multiple"])
        self.assertIsNone(
            reference["source_observation_count"],
            "no reference is in force, so there is no source whose count could be "
            "reported",
        )

    def test_a_historical_median_reports_the_band_it_was_read_from(self):
        document = build_context_for("MSFT", pe_band=self.ELIGIBLE_BAND)
        reference = document["valuation_reference"]

        self.assertEqual(reference["basis"], "HISTORICAL_MEDIAN")
        self.assertIsNotNone(
            reference["source_ref"], "a historical median names the band it came from"
        )
        self.assertEqual(
            reference["source_observation_count"],
            40,
            "the band is the reference here, so its own declared count is correct",
        )

    def test_an_eligible_reference_is_not_declared_on_an_ineligible_count(self):
        """
        The reported count and the reported eligibility must describe the same
        object.

        Before the fix this document claimed 7 observations and
        `eligible_as_reference: true` under a rule naming the production
        distribution -- a set of claims no single object satisfied, which is why
        the two fields have to be asserted together rather than one at a time.
        """
        document = build_context_for(
            "MSFT",
            engine={"production_historical_pe": _eligible_distribution()},
            pe_band=self.VENDOR_BAND,
        )
        reference = document["valuation_reference"]

        self.assertTrue(reference["eligible_as_reference"])
        self.assertIn(
            "production historical P/E distribution", reference["eligibility_rule"]
        )
        self.assertGreaterEqual(
            reference["source_observation_count"],
            MIN_BAND_OBSERVATIONS_FOR_REFERENCE,
            "an eligible reference cannot be based on fewer observations than its "
            "own threshold while the payload reports the thinner vendor band",
        )


class TestReferenceSourceStatistic(unittest.TestCase):
    """
    `source_statistic` names the statistic the reference actually is, and follows
    the basis for the same reason the observation count does.

    Both observed bases are a median of their distribution. An operator's multiple
    was never passed through a statistic, and an unavailable reference is not a
    statistic at all, so neither has one to name. Reporting `median` for those two
    described an object that was not in play -- the same mistake as reporting the
    vendor band's observation count, in the field beside it.
    """

    VENDOR_BAND = TestReferenceSourceObservationCount.VENDOR_BAND
    ELIGIBLE_BAND = TestReferenceSourceObservationCount.ELIGIBLE_BAND

    def test_an_observed_production_reference_names_its_statistic(self):
        document = build_context_for(
            "MSFT",
            engine={"production_historical_pe": _eligible_distribution()},
            pe_band=self.VENDOR_BAND,
        )
        reference = document["valuation_reference"]

        self.assertEqual(reference["basis"], "PRODUCTION_PE_MEDIAN")
        self.assertEqual(reference["source_statistic"], "median")
        self.assertEqual(reference["provenance_kind"], "OBSERVED")

    def test_a_historical_median_names_the_statistic_it_is(self):
        document = build_context_for("MSFT", pe_band=self.ELIGIBLE_BAND)
        reference = document["valuation_reference"]

        self.assertEqual(reference["basis"], "HISTORICAL_MEDIAN")
        self.assertEqual(reference["source_statistic"], "median")
        self.assertEqual(reference["provenance_kind"], "OBSERVED")

    def test_a_supplied_multiple_names_no_statistic(self):
        document = build_context_for(
            "MSFT",
            engine={"reference_multiple": 30.0},
            reference_multiple=30.0,
            pe_band=self.VENDOR_BAND,
        )
        reference = document["valuation_reference"]

        self.assertEqual(reference["basis"], "USER_SUPPLIED")
        self.assertIsNone(
            reference["source_statistic"],
            "a multiple supplied on the command line was never passed through a "
            "statistic, so it must not claim to be a median",
        )
        self.assertEqual(reference["selection_method"], "user_supplied_multiple")

    def test_an_unavailable_reference_names_no_statistic(self):
        document = build_context_for(
            "MSFT",
            engine={
                "production_historical_pe": {
                    "distribution": {
                        "status": "UNAVAILABLE",
                        "usable_for_reference": False,
                        "sample_count": 0,
                    }
                }
            },
            pe_band=self.VENDOR_BAND,
        )
        reference = document["valuation_reference"]

        self.assertEqual(reference["basis"], "NONE")
        self.assertIsNone(
            reference["source_statistic"],
            "no reference is in force, so there is no statistic it could be",
        )
        self.assertIsNone(reference["source_observation_count"])
        self.assertEqual(reference["provenance_kind"], "UNAVAILABLE")

    def test_the_published_block_and_the_registered_ref_agree(self):
        """
        The payload is published twice -- as the section and as provenance.refs --
        so a field resolved in one place has to reach both.
        """
        document = build_context_for("MSFT", pe_band=self.VENDOR_BAND)
        section = document["valuation_reference"]
        registered = document["provenance"]["refs"]["refc:valuation_reference"]

        for field in ("basis", "multiple", "source_statistic", "source_observation_count"):
            with self.subTest(field=field):
                self.assertEqual(registered[field], section[field])


class TestUnsupportedReferenceBasis(unittest.TestCase):
    """
    A basis the context does not know is refused, not defaulted.

    Every field in the reference block describes the reference's own source, so an
    unrecognised basis would be recorded with source information that describes
    nothing, and nothing downstream would notice. The old fall-through produced a
    mixture that contradicted itself: `selection_method: none` beside
    `source_statistic: median`.
    """

    def _builder(self):
        data = CompanyResolver.resolve("MSFT", mode="regression")
        metrics = DeterministicMetricsEngine.compute(
            data.price_history, data.volume_history
        )
        return ContextBuilder(
            data=data,
            analysis=MarketImpliedAssumptionsEngine.analyze(data),
            evidence=build_evidence(data, metrics),
            metrics=metrics,
        )

    def test_an_unknown_basis_is_refused_rather_than_defaulted(self):
        builder = self._builder()
        with self.assertRaises(ContextError) as caught:
            builder._register_reference(
                name="valuation_reference",
                multiple=20.0,
                source_metric="pe",
                source_ref=None,
                basis="FUTURE_BASIS",
            )
        message = str(caught.exception)
        self.assertIn("FUTURE_BASIS", message)
        self.assertIn("HISTORICAL_MEDIAN", message, "the supported set is named")

    def test_the_closed_set_matches_what_the_engine_produces(self):
        """
        The mapping is only a guard if it covers every basis the caller can emit.
        A basis in the mapping that no engine method produces would be dead, and a
        method without a basis would raise on a legitimate run.
        """
        supported = investment_context.REFERENCE_SOURCES
        self.assertEqual(
            sorted(supported),
            ["HISTORICAL_MEDIAN", "NONE", "PRODUCTION_PE_MEDIAN", "USER_SUPPLIED"],
            "the closed set changed; a new basis is a provenance decision, so this "
            "assertion is the place to record it",
        )
        for basis in sorted(supported):
            with self.subTest(basis=basis):
                builder = self._builder()
                ref = builder._register_reference(
                    name="valuation_reference",
                    multiple=20.0,
                    source_metric="pe",
                    source_ref=None,
                    basis=basis,
                )
                self.assertEqual(builder.refs[ref].payload["basis"], basis)


class TestReferenceProvenanceThroughTheApiPath(unittest.TestCase):
    """
    A null statistic and a null observation count have to survive the paths that
    actually carry a context: the replay builder the API calls, JSON
    serialization, the archive's stored form, and the document's own validator.
    """

    ASSET = "MSFT"
    AS_OF = "2026-06-30"

    def _price(self):
        return Observation(
            observation_id="ev-price-001",
            metric=METRIC_PRICE,
            value=425.5,
            unit=Unit.CURRENCY.value,
            currency="USD",
            currency_basis="REPORTED",
            period_start=None,
            period_end=self.AS_OF,
            as_of=self.AS_OF,
            available_at="2026-06-30T20:00:00.000Z",
            available_at_basis=AvailabilityBasis.OBSERVATION_INSTANT.value,
            provider="YahooFinance",
            source_type=SourceType.API_LIVE.value,
            source_url=None,
            definition="Observed current market price.",
            methodology="chart API",
            retrieved_at="2026-06-30T21:00:00+00:00",
            raw={"regular_market_price": 425.5},
            status=ValidationStatus.SINGLE_SOURCE,
        )

    def _replayed(self):
        return build_context_from_observations(
            [self._price()],
            ticker=self.ASSET,
            as_of=self.AS_OF,
            generated_at="2026-06-30T21:30:00+00:00",
        )

    def test_a_reference_with_no_source_survives_serialization_and_validation(self):
        document = self._replayed()
        reference = document["valuation_reference"]

        self.assertEqual(reference["basis"], "NONE")
        self.assertIsNone(reference["source_statistic"])
        self.assertIsNone(reference["source_observation_count"])

        # What atomic_json_write does for --context, and what the API returns.
        reloaded = json.loads(json.dumps(document, ensure_ascii=False))
        self.assertIsNone(reloaded["valuation_reference"]["source_statistic"])
        self.assertIsNone(reloaded["valuation_reference"]["source_observation_count"])
        verify_document(reloaded)

    def test_the_archive_store_keeps_the_null(self):
        store = SQLiteArchive(":memory:")
        self.addCleanup(store.close)

        store.record_context(
            self.ASSET, self._replayed(), replay_fidelity="SOURCE_DECLARED"
        )
        stored = store.context_at(self.ASSET, self.AS_OF)

        self.assertIsNotNone(stored, "the context was stored for this instant")
        self.assertIsNone(stored["valuation_reference"]["source_statistic"])
        self.assertIsNone(stored["valuation_reference"]["source_observation_count"])


class TestSecondaryReferenceProvenance(unittest.TestCase):
    """
    The three secondary references are references too, and follow the same rule as
    the valuation reference: an observed one carries the engine's median, names
    the band it came from, and is not confused with one that was supplied or is
    absent.

    They used to record `basis: NONE` with a null multiple in every case, because
    the context read `reference_multiples` from the `reference` block while the
    engine publishes it under `implied_assumptions` -- which is also where
    `validate_analysis` requires it and where the derivation strings name it. The
    reference the engine had selected from an eligible band was therefore invisible
    in the document, and the implied figures conditional on it were withheld.
    """

    BANDS = {
        "historical_pfcf_band": ("pfcf_reference", 20.0),
        "historical_ev_ebitda_band": ("ev_ebitda_reference", 18.0),
        "historical_ps_band": ("ps_reference", 5.0),
    }

    def _context(self, present=(), ineligible=(), **user):
        """
        A user multiple must reach `analyze` as well as the context builder.

        The builder's parity check compares the engine's value against its own
        recomputation, so a helper that supplied the multiple to only one of them
        would be asking the document to reconcile two different references. The
        runner passes it to both; so does this.
        """
        data = CompanyResolver.resolve("MSFT", mode="regression")
        for attribute, (_, median) in self.BANDS.items():
            if attribute in present:
                data.__setattr__(
                    attribute,
                    {"median": median, "10th": median * 0.7, "25th": median * 0.85,
                     "75th": median * 1.15, "90th": median * 1.3,
                     "observations": 2 if attribute in ineligible else 25},
                )
        # The numerators the implied-figure derivations divide.
        data.current_market_cap = 3_160_000_000_000.0
        data.current_enterprise_value = 3_190_000_000_000.0
        metrics = DeterministicMetricsEngine.compute(
            data.price_history, data.volume_history
        )
        analysis = MarketImpliedAssumptionsEngine.analyze(data, **user)
        document = build_investment_context(
            data=data,
            analysis=analysis,
            evidence=build_evidence(data, metrics),
            metrics=metrics,
            material_observations=list(material_observations(data).values())
            + [metrics_observation(data, metrics)],
            generated_at="2026-06-30T00:00:00+00:00",
            **user,
        )
        return document, analysis

    @staticmethod
    def _reference(document, name):
        return document["provenance"]["refs"][f"refc:{name}"]

    def test_the_engine_publishes_the_secondary_medians_under_implied_assumptions(self):
        """
        The location the reader depends on, asserted directly so a future move of
        the value cannot silently empty every secondary reference again.
        """
        _, analysis = self._context(present=tuple(self.BANDS))
        self.assertIsNone(
            (analysis.get("reference") or {}).get("reference_multiples"),
            "the reference block carries only the valuation reference's multiple",
        )
        self.assertEqual(
            (analysis.get("implied_assumptions") or {}).get("reference_multiples"),
            {"pe": None, "pfcf": 20.0, "ev_ebitda": 18.0, "ps": 5.0},
        )

    def test_an_observed_secondary_reference_names_its_band_and_its_multiple(self):
        document, _ = self._context(present=tuple(self.BANDS))

        for attribute, (name, median) in self.BANDS.items():
            with self.subTest(reference=name):
                reference = self._reference(document, name)
                self.assertEqual(reference["basis"], "HISTORICAL_MEDIAN")
                self.assertEqual(reference["multiple"], median)
                self.assertEqual(reference["source_statistic"], "median")
                self.assertEqual(reference["source_observation_count"], 25)
                self.assertEqual(reference["eligible_as_reference"], True)
                self.assertEqual(
                    reference["source_ref"],
                    {
                        "pfcf_reference": "obs:ev-pfcf-band-001",
                        "ev_ebitda_reference": "obs:ev-ev-ebitda-band-001",
                        "ps_reference": "obs:ev-ps-band-001",
                    }[name],
                    "a historical median must name the band it came from",
                )

    def test_one_observed_secondary_leaves_the_others_absent(self):
        document, _ = self._context(present=("historical_ps_band",))

        observed = self._reference(document, "ps_reference")
        self.assertEqual(observed["basis"], "HISTORICAL_MEDIAN")
        self.assertEqual(observed["multiple"], 5.0)
        self.assertEqual(observed["source_ref"], "obs:ev-ps-band-001")

        for name in ("pfcf_reference", "ev_ebitda_reference"):
            with self.subTest(reference=name):
                reference = self._reference(document, name)
                self.assertEqual(reference["basis"], "NONE")
                self.assertIsNone(reference["multiple"])
                self.assertIsNone(reference["source_ref"])
                self.assertIsNone(reference["source_observation_count"])

    def test_an_ineligible_secondary_band_is_not_a_reference(self):
        document, _ = self._context(
            present=("historical_ps_band",), ineligible=("historical_ps_band",)
        )
        reference = self._reference(document, "ps_reference")

        self.assertEqual(reference["basis"], "NONE")
        self.assertIsNone(reference["multiple"])
        self.assertIsNone(
            reference["source_ref"],
            "2 observations is below the rule, so the band did not supply the "
            "reference and must not be named as its source",
        )
        self.assertEqual(reference["eligible_as_reference"], False)

    def test_a_supplied_secondary_names_no_band(self):
        document, _ = self._context(present=("historical_ps_band",), ps_multiple=7.5)
        reference = self._reference(document, "ps_reference")

        self.assertEqual(reference["basis"], "USER_SUPPLIED")
        self.assertEqual(reference["multiple"], 7.5)
        self.assertIsNone(
            reference["source_ref"],
            "the multiple came from the operator, so the band is not its source",
        )
        self.assertIsNone(reference["source_statistic"])

    def test_the_implied_amounts_are_published_with_a_monetary_unit(self):
        """
        The implied amounts divide a monetary aggregate by a valuation multiple,
        so the result is money. They used to be withheld entirely, and the divide
        table maps (currency, multiple) to per_share -- correct for price over a
        P/E multiple, wrong here -- so enabling them without naming the operation
        would have published a total revenue labelled per share.
        """
        document, _ = self._context(present=tuple(self.BANDS))

        for name, numerator, median in (
            ("implied_fcf", 3_160_000_000_000.0, 20.0),
            ("implied_ebitda", 3_190_000_000_000.0, 18.0),
            ("implied_revenue", 3_160_000_000_000.0, 5.0),
        ):
            with self.subTest(figure=name):
                figure = document["derived"][name]["figure"]
                self.assertEqual(figure["unit"], "currency", name)
                self.assertEqual(figure["provenance_kind"], "CONDITIONAL")
                self.assertAlmostEqual(figure["value"], numerator / median, places=6)

    def test_the_registry_declares_the_implied_amount_operation_as_money(self):
        spec = lookup("amount_from_valuation_multiple")
        self.assertEqual(spec.output_unit, "currency")
        self.assertEqual(spec.arity, 2)


class TestScopeContract(unittest.TestCase):
    def test_data_quality_carries_no_grade(self):
        document = build_context_for("MSFT")
        check_data_quality_has_no_grade(document)
        for key in document["data_quality"]:
            for word in ("score", "grade", "quality", "completeness", "confidence"):
                self.assertNotIn(word, key.lower())

    def test_a_grade_in_data_quality_is_rejected(self):
        document = build_context_for("MSFT")
        document["data_quality"]["quality_score"] = 87
        with self.assertRaises(ContextError):
            check_data_quality_has_no_grade(document)

    def test_no_verdict_vocabulary_outside_the_non_claims(self):
        document = build_context_for("MSFT")
        check_no_verdict_vocabulary(document)

    def test_a_verdict_in_the_document_is_rejected(self):
        document = build_context_for("MSFT")
        document["derived"]["current_pe"]["figure"]["note"] = (
            "this looks undervalued"
        )
        with self.assertRaises(ContextError):
            check_no_verdict_vocabulary(document)

    def test_the_guard_matches_words_not_fragments(self):
        """
        `shareholders` contains `hold`. A guard that fires on a provider's own
        field name is a guard that gets switched off.
        """
        document = build_context_for("AAPL") if os.environ.get(
            "ST_EVA_LIVE"
        ) == "1" else build_context_for("MSFT")
        payload = json.dumps(document).lower()
        self.assertNotIn("sharehold", payload)
        check_no_verdict_vocabulary(document)

    def test_the_non_claims_block_may_use_the_words(self):
        document = build_context_for("MSFT")
        blob = json.dumps(document["scope"]["does_not_provide"]).lower()
        self.assertIn("buy/sell/hold", blob)

    def test_the_scope_states_what_is_not_provided(self):
        document = build_context_for("MSFT")
        provided = document["scope"]["does_not_provide"]
        self.assertTrue(len(provided) >= 6)
        self.assertIn("authority_note", document["scope"])


class TestPointInTime(unittest.TestCase):
    def test_knowledge_cutoff_is_the_latest_availability(self):
        document = build_context_for("MSFT")
        check_knowledge_cutoff(document)
        latest = None
        for entry in document["provenance"]["refs"].values():
            if entry.get("kind") != KIND_OBSERVATION:
                continue
            available_at = entry.get("available_at")
            if available_at and (latest is None or available_at > latest):
                latest = available_at
        self.assertEqual(document["knowledge_cutoff"], latest)

    def test_no_figure_is_from_after_the_context_as_of(self):
        document = build_context_for("MSFT")
        check_knowledge_cutoff(document)

    def test_an_understated_cutoff_is_rejected(self):
        document = build_context_for("MSFT")
        document["knowledge_cutoff"] = "1990-01-01"
        with self.assertRaises(ContextError):
            check_knowledge_cutoff(document)

    def test_a_future_fact_is_rejected(self):
        document = build_context_for("MSFT")
        for entry in document["provenance"]["refs"].values():
            if entry.get("kind") == KIND_OBSERVATION:
                entry["as_of"] = "2099-01-01"
                break
        with self.assertRaises(ContextError):
            check_knowledge_cutoff(document)


class TestVersioningAndDeterminism(unittest.TestCase):
    def test_the_two_schemas_are_named_independently(self):
        document = build_context_for("MSFT")
        self.assertIn("context_schema_version", document)
        self.assertEqual(
            document["context_schema_version"], CONTEXT_SCHEMA_VERSION
        )
        self.assertEqual(
            document["built_from"]["legacy_snapshot_schema_version"], "2.2.3"
        )
        self.assertEqual(
            document["built_from"]["contract_version"], "2.3-A"
        )
        self.assertEqual(
            document["built_from"]["cross_source_version"], "2.3-B"
        )

    def test_nothing_new_reuses_the_bare_schema_version(self):
        document = build_context_for("MSFT")
        self.assertNotIn("schema_version", document)

    def test_the_context_id_is_stable_across_builds(self):
        first = build_context_for("MSFT")
        second = build_context_for("MSFT")
        self.assertEqual(first["context_id"], second["context_id"])

    def test_the_content_hash_excludes_generated_at(self):
        document = build_context_for("MSFT")
        recomputed = compute_content_hash(document)
        self.assertEqual(recomputed, document["context_id"])
        document["generated_at"] = "2099-01-01T00:00:00+00:00"
        self.assertEqual(compute_content_hash(document), recomputed)

    def test_changing_a_value_changes_the_id(self):
        first = build_context_for("MSFT")
        document = build_context_for("TENCENT")
        self.assertNotEqual(first["context_id"], document["context_id"])

    def test_the_document_round_trips(self):
        document = build_context_for("MSFT")
        restored = json.loads(
            json.dumps(document, ensure_ascii=False, sort_keys=True)
        )
        self.assertEqual(
            json.dumps(document, sort_keys=True),
            json.dumps(restored, sort_keys=True),
        )
        check_references_resolve(restored)
        check_operations_are_registered(restored)

    def test_a_min_reader_version_is_declared(self):
        document = build_context_for("MSFT")
        self.assertTrue(document["min_reader_version"])


class TestValidationVerdictsInTheContext(unittest.TestCase):
    def _observation(self, observation_id, metric, value, period_end, available_at):
        return Observation(
            observation_id=observation_id,
            metric=metric,
            value=value,
            unit=Unit.CURRENCY.value,
            currency="USD",
            currency_basis="REPORTED",
            period_start="2025-06-29",
            period_end=period_end,
            as_of=period_end,
            available_at=available_at,
            available_at_basis="ACCEPTANCE_DATETIME",
            provider="Stub",
            source_type=SourceType.REGULATORY_FILING.value,
            source_url=None,
            definition="stub",
            methodology="stub",
            retrieved_at="2026-09-28T12:00:00+00:00",
            raw={
                "derivation": "ANNUAL_ROLL_FORWARD",
                "constituents": [],
                "period_type": "duration",
            },
        )

    def test_a_discrepancy_is_published_without_overwriting_either_side(self):
        vendor = self._observation(
            "cmp-revenue-yahoo-1",
            METRIC_REVENUE,
            466_823_000_000.0,
            "2026-06-27",
            "2026-07-31T10:01:02.000Z",
        )
        filing = self._observation(
            "cmp-revenue-sec-1",
            METRIC_REVENUE,
            400_000_000_000.0,
            "2026-06-27",
            "2026-07-31T10:01:02.000Z",
        )
        result = cross_validate(
            METRIC_REVENUE, vendor, filing, checked_at="2026-09-28T12:00:00+00:00"
        )
        self.assertEqual(result.status, ValidationStatus.DISCREPANT)

        data = CompanyResolver.resolve("MSFT", mode="regression")
        metrics = DeterministicMetricsEngine.compute(
            data.price_history, data.volume_history
        )
        evidence = build_evidence(data, metrics)
        analysis = MarketImpliedAssumptionsEngine.analyze(data)
        document = build_investment_context(
            data=data,
            analysis=analysis,
            evidence=evidence,
            metrics=metrics,
            material_observations=list(
                material_observations(data).values()
            )
            + [metrics_observation(data, metrics), vendor, filing],
            cross_validation={METRIC_REVENUE: result},
        )
        entry = document["validated_evidence"][METRIC_REVENUE]
        self.assertEqual(entry["status"], ValidationStatus.DISCREPANT.value)
        self.assertTrue(entry["comparable"])
        self.assertTrue(entry["vendor_ref"])
        self.assertTrue(entry["filing_ref"])
        self.assertIn("independence", entry)

        # Both sides survive the comparison, unchanged.
        for ref in (entry["vendor_ref"], entry["filing_ref"]):
            self.assertIn(ref, document["provenance"]["refs"])
        self.assertEqual(
            document["provenance"]["refs"][entry["vendor_ref"]]["value"],
            466_823_000_000.0,
        )
        self.assertEqual(
            document["provenance"]["refs"][entry["filing_ref"]]["value"],
            400_000_000_000.0,
        )

    def test_independence_is_never_promoted(self):
        document = build_context_for("MSFT")
        for entry in document["validated_evidence"].values():
            self.assertIn(
                entry["independence"],
                ("UNVERIFIED_INDEPENDENCE", "NOT_INDEPENDENT"),
                "a two-source agreement must never be reported as verified",
            )


class TestLegacyCompatibility(unittest.TestCase):
    """The frozen 2.2.3 contract."""

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, "st_eva_runner.py", *args],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def test_the_legacy_json_is_unchanged_by_the_context_flag(self):
        for ticker in ("MSFT", "TENCENT", "NU"):
            with self.subTest(ticker=ticker):
                without = self._run(
                    ticker, "--mode", "regression", "--no-snapshot", "--json"
                )
                self.assertEqual(without.returncode, 0, without.stderr[-400:])
                before = json.loads(without.stdout)

                with tempfile.TemporaryDirectory() as directory:
                    target = Path(directory) / "context.json"
                    with_context = self._run(
                        ticker,
                        "--mode",
                        "regression",
                        "--no-snapshot",
                        "--json",
                        "--context",
                        str(target),
                        "--context-sources",
                        "yahoo",
                    )
                    self.assertEqual(
                        with_context.returncode, 0, with_context.stderr[-400:]
                    )
                    after = json.loads(with_context.stdout)
                    self.assertTrue(target.exists())
                    context = json.loads(target.read_text(encoding="utf-8"))

                self.assertEqual(before, after)
                self.assertEqual(before["version_metadata"]["schema_version"], "2.2.3")
                self.assertNotIn("investment_context", before)
                self.assertEqual(context["context_schema_version"], CONTEXT_SCHEMA_VERSION)

    def test_the_evidence_ids_are_unchanged(self):
        result = run_st_eva("MSFT", mode="regression", save_snapshot=False)
        self.assertEqual(
            result["evidence_ids"],
            [
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
            ],
        )

    def test_a_snapshot_gains_the_context_without_losing_a_key(self):
        import st_eva_runner

        with tempfile.TemporaryDirectory() as directory:
            result = run_st_eva(
                "MSFT",
                mode="regression",
                history_dir=directory,
                context_path=str(Path(directory) / "ctx.json"),
                context_sources=("yahoo",),
            )
            self.assertIsNotNone(result)
            record = json.loads(
                next(Path(directory).glob("*_market_implied_assumptions.json"))
                .read_text(encoding="utf-8")
            )
            for key in (
                "research_id",
                "analysis",
                "market_metrics",
                "evidence",
                "limitations",
                "data_contract",
            ):
                self.assertIn(key, record)
            self.assertIn("investment_context", record)
            self.assertEqual(
                record["version_metadata"]["schema_version"], "2.2.3"
            )
            self.assertTrue(
                st_eva_runner.SnapshotManager(directory).update_outcome(
                    result["research_id"], {"t_plus_1_return": 0.01}
                )
            )


class TestContextBuilderSurface(unittest.TestCase):
    def test_the_context_module_does_not_import_the_engine(self):
        """
        The document must be able to describe the engine's output without
        being able to influence it.
        """
        import ast
        import inspect

        import investment_context

        tree = ast.parse(inspect.getsource(investment_context))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(
                    alias.name.split(".")[0] for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertNotIn("st_eva_runner", imported)
        self.assertNotIn("sec_provider", imported)
        self.assertNotIn("fundamental_provider", imported)

    def test_duplicate_refs_are_refused_at_build_time(self):
        """
        Two entries for one ref would let them disagree, so the builder refuses
        rather than letting a later one win.
        """
        data = CompanyResolver.resolve("MSFT", mode="regression")
        metrics = DeterministicMetricsEngine.compute(
            data.price_history, data.volume_history
        )
        builder = ContextBuilder(
            data=data,
            analysis=MarketImpliedAssumptionsEngine.analyze(data),
            evidence=build_evidence(data, metrics),
            metrics=metrics,
        )
        builder._register("obs:x", KIND_OBSERVATION, {"value": 1})
        with self.assertRaises(ContextError):
            builder._register("obs:x", KIND_OBSERVATION, {"value": 2})

    def test_a_ref_named_as_a_figure_must_exist(self):
        document = build_context_for("MSFT")
        with self.assertRaises(UnresolvedRefError):
            document["derived"]["current_pe"]["figure"]["ref"] = "obs:ghost"
            check_references_resolve(document)


@unittest.skipUnless(
    os.environ.get("ST_EVA_LIVE") == "1",
    "live context tests need ST_EVA_LIVE=1",
)
class TestLiveContexts(unittest.TestCase):
    """A real acquisition, end to end."""

    def test_a_live_context_is_traceable_and_recomputable(self):
        document = build_context_for("AAPL")
        check_references_resolve(document)
        check_graph_acyclic(document)
        report = verify_document(document)
        self.assertGreater(report["recomputed"], 0)

    def test_a_live_context_carries_cross_source_verdicts(self):
        data = CompanyResolver.resolve("AAPL", mode="live")
        self.assertIsNotNone(data)
        acquisition = SECProvider().fetch("AAPL")
        from cross_validation import cross_validate_all

        vendor = [
            observation
            for observation in (
                data.observations.get(identifier)
                for identifier in data.observations.ids()
            )
            if observation is not None
            and observation.observation_id.startswith("cmp-")
        ]
        verdicts = cross_validate_all(vendor, acquisition.observations)

        metrics = DeterministicMetricsEngine.compute(
            data.price_history, data.volume_history
        )
        document = build_investment_context(
            data=data,
            analysis=MarketImpliedAssumptionsEngine.analyze(data),
            evidence=build_evidence(data, metrics),
            metrics=metrics,
            material_observations=list(
                material_observations(data).values()
            )
            + [metrics_observation(data, metrics)],
            extra_observations=list(acquisition.observations),
            cross_validation=verdicts,
            cik=acquisition.company.cik,
        )
        self.assertEqual(set(document["validated_evidence"]), set(COMPARABLE_METRICS))
        for entry in document["validated_evidence"].values():
            self.assertIn(
                entry["independence"],
                ("UNVERIFIED_INDEPENDENCE", "NOT_INDEPENDENT"),
            )
        # The acquisition must actually have produced filing observations. A
        # provider that silently returns nothing still yields a document with
        # every expected key, all of them UNAVAILABLE, so asserting the keys
        # alone would not notice that the adapter is broken.
        self.assertEqual(acquisition.errors, ())
        filing = [
            observation
            for observation in acquisition.observations
            if observation.source_type == SourceType.REGULATORY_FILING.value
        ]
        self.assertGreater(
            len(filing), 20,
            "the SEC adapter returned no usable filing observations",
        )
        for observation in filing:
            self.assertTrue(observation.is_available, observation.metric)
        check_references_resolve(document)

    def test_all_three_fixtures_build_a_context(self):
        for ticker in ("MSFT", "TENCENT", "NU"):
            with self.subTest(ticker=ticker):
                document = build_context_for(ticker)
                check_references_resolve(document)
                check_no_unavailable_value(document)
                check_conditional_figures_are_conditioned(document)
                verify_document(document)


if __name__ == "__main__":
    unittest.main()
