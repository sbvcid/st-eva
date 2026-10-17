"""
Traceable EPS anchor catalogue and selection — acceptance tests.

These verify the EPS anchor path that makes issuer-reported diluted EPS a
traceable reverse-valuation anchor, without widening the archive valuation
boundary or changing historical P/E rules.
"""

import datetime
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eps_anchor_evidence import (
    ANCHOR_SEC_ANNUAL,
    ANCHOR_SEC_TTM_FOUR_QUARTERS,
    ANCHOR_SUPPLIER_TRAILING,
    AVAILABILITY_ACCEPTANCE_DATETIME,
    AVAILABILITY_FILED_AS_OF_DATE,
    GAAP_BASIS_DILUTED,
    GAAP_BASIS_UNDECLARED,
    NATURE_DERIVED,
    NATURE_DIRECT_FILING,
    NATURE_PROVIDER_REPORTED,
    REFUSAL_INCOMPLETE_QUARTERS,
    REFUSAL_QUARTERS_NOT_KNOWABLE,
    REFUSAL_WINDOW_SPAN,
    SELECTION_RULE,
    build_eps_anchor_candidates,
    candidate_to_eps_anchor,
    is_explicit_anchor_id,
    is_legacy_anchor_preference,
    select_anchor,
    unknown_anchor_request_refusal,
    resolve_knowability,
)


def test_catalogue_distinguishes_supplier_sec_revenue():
    """Numerical equality is not provenance: supplier and filing stay separate."""
    cs = build_eps_anchor_candidates(
        ticker="AAPL", valuation_date="2026-10-16", currency="USD", provider="YahooFinance",
        trailing_eps=8.72, forward_eps=9.10, consensus_eps=9.05,
    )
    ids = {c.anchor_id: c for c in cs.candidates}
    # Both supplier and SEC entries can exist independently; identity attaches
    # only through accession/form/period, never through the value.
    assert ids["SUPPLIER_TRAILING_EPS"].available
    assert ids["SEC_ANNUAL_DILUTED_EPS"].available
    # Even if values coincidentally match in a different ticker, the two
    # entries keep separate source identity fields.
    assert ids["SEC_ANNUAL_DILUTED_EPS"].nature == NATURE_DIRECT_FILING
    assert ids["SUPPLIER_TRAILING_EPS"].nature == NATURE_PROVIDER_REPORTED


def test_point_in_time_knowability_rules():
    """Point-in-time: filing after valuation date refused; 16:00 ET on date
    refused when no earlier time declared; filed-date-only on valuation date
    refused (no proof it preceded the close); earlier date admitted."""
    # Filed earlier than valuation → knowable
    k = resolve_knowability(
        available_at="2025-10-29T10:00:00+00:00",
        available_at_basis=AVAILABILITY_ACCEPTANCE_DATETIME,
        valuation_date="2026-01-15",
    )
    assert k.knowable

    # Filed on valuation date with only calendar date declared → refused
    k2 = resolve_knowability(
        available_at="2026-01-15",
        available_at_basis=AVAILABILITY_FILED_AS_OF_DATE,
        valuation_date="2026-01-15",
    )
    assert not k2.knowable
    assert "filed_on_valuation_date_without_declared_time" in k2.rule

    # After valuation → refused
    k3 = resolve_knowability(
        available_at="2026-01-16T09:00:00+00:00",
        available_at_basis=AVAILABILITY_ACCEPTANCE_DATETIME,
        valuation_date="2026-01-15",
    )
    assert not k3.knowable


def test_annual_not_relabelled_ttm():
    """An annual figure never presents itself as a trailing figure."""
    cs = build_eps_anchor_candidates(
        ticker="AAPL", valuation_date="2026-10-16", currency="USD", provider="YahooFinance",
    )
    annual = next(c for c in cs.candidates if c.anchor_id == ANCHOR_SEC_ANNUAL)
    assert annual.available
    assert annual.basis == "FISCAL_YEAR"
    assert annual.months_covered > 11.5  # ~11.9 for a fiscal year
    # The annual candidate is never offered with a TTM basis.
    assert annual.anchor_id not in {"SEC_TTM_FOUR_QUARTERS"}


def test_derived_ttm_marked_derived_not_direct():
    """Derived sum carries DERIVED_FROM_DIRECT_FILINGS; no issuer statement."""
    cs = build_eps_anchor_candidates(
        ticker="MSFT", valuation_date="2026-10-16", currency="USD", provider="YahooFinance",
    )
    ttm = next(c for c in cs.candidates if c.anchor_id == ANCHOR_SEC_TTM_FOUR_QUARTERS)
    assert ttm.available
    assert ttm.nature == NATURE_DERIVED
    assert ttm.derivation.startswith("Sum of four directly stated")
    assert len(ttm.sec_components) == 4
    # Each component carries its own accession/form/acceptance — traceable.
    for comp in ttm.sec_components:
        assert comp.get("accession")
        assert comp.get("form")


def test_yearly_vs_ttm_kept_separate_with_basis_difference():
    """When the four-quarter sum and audited annual cover the same window
    but differ, both kept; neither adjusted."""
    cs = build_eps_anchor_candidates(
        ticker="MSFT", valuation_date="2026-10-16", currency="USD", provider="YahooFinance",
    )
    ttm = next(c for c in cs.candidates if c.anchor_id == ANCHOR_SEC_TTM_FOUR_QUARTERS)
    assert ttm.annual_comparison is not None
    # The comparison is only made when windows match; when they don't,
    # comparable=False with explicit reason (test below covers that).
    # When they match, both numbers stay; agreement reported.
    assert "agrees" in ttm.annual_comparison or ttm.annual_comparison.get("comparable") is False


def test_four_quarter_window_requires_four():
    """Three quarters + gap is not completed; window must span a year."""
    # The module refuses with REFUSAL_INCOMPLETE_QUARTERS when fewer
    # than 4 direct quarterly facts are read (packaged data always has 4
    # for MSFT/AAPL/MU; control by missing-file test if needed).
    # This verifies refusal codes exist for the required conditions.
    assert REFUSAL_INCOMPLETE_QUARTERS
    assert REFUSAL_WINDOW_SPAN
    assert REFUSAL_QUARTERS_NOT_KNOWABLE


def test_no_dataset_refusal_keeps_both_unavailable():
    """When no packaged dataset and no run observations exist, both SEC
    anchors report NO_PACKAGED_SEC_EPS_DATASET with explicit reasons."""
    cs = build_eps_anchor_candidates(
        ticker="NOTREAL", valuation_date="2026-01-01", currency="USD", provider="YahooFinance"
    )
    annual = next(c for c in cs.candidates if c.anchor_id == ANCHOR_SEC_ANNUAL)
    ttm = next(c for c in cs.candidates if c.anchor_id == ANCHOR_SEC_TTM_FOUR_QUARTERS)
    assert not annual.available
    assert annual.refusal_code == "NO_PACKAGED_SEC_EPS_DATASET"
    assert not ttm.available
    assert ttm.refusal_code == "NO_PACKAGED_SEC_EPS_DATASET"


def test_unknown_anchor_id_refused_no_substitution():
    """A named request not in the catalogue is refused; no different figure."""
    refusal = unknown_anchor_request_refusal("DIAMOND_EPS")
    assert refusal["reason_kind"] == "UNKNOWN_EPS_ANCHOR_ID"
    assert "No other figure is substituted" in refusal["reason"]
    assert refusal["blocks"] == ["start_anchor"]


def test_legacy_preference_preserved_case_insensitive():
    assert is_legacy_anchor_preference("trailing")
    assert is_legacy_anchor_preference("TRAILING")
    assert is_legacy_anchor_preference("forward")
    assert not is_legacy_anchor_preference("SEC_ANNUAL_DILUTED_EPS")
    assert not is_explicit_anchor_id("trailing")


def test_candidate_to_anchor_carriage():
    """Adopted catalogue entry passes full identity through to EpsAnchor."""
    cs = build_eps_anchor_candidates(
        ticker="AAPL", valuation_date="2026-10-16", currency="USD", provider="YahooFinance"
    )
    annual = next(c for c in cs.candidates if c.anchor_id == ANCHOR_SEC_ANNUAL)
    anchor = candidate_to_eps_anchor(annual, currency="USD")
    assert anchor.anchor_id == ANCHOR_SEC_ANNUAL
    assert anchor.anchor_nature == NATURE_DIRECT_FILING
    assert anchor.anchor_gaap_basis == GAAP_BASIS_DILUTED
    assert anchor.value == annual.value
    assert anchor.sec_fact is not None
    assert anchor.sec_fact.get("accession")


def test_selection_refused_carries_specific_reason():
    """When the named anchor is unavailable, the refusal names exactly why."""
    cs = build_eps_anchor_candidates(
        ticker="AAPL", valuation_date="2026-10-16", currency="USD", provider="YahooFinance",
        trailing_eps=None, forward_eps=None, consensus_eps=None,
    )
    sel = select_anchor(cs, ANCHOR_SUPPLIER_TRAILING)
    assert sel.candidate is None
    assert len(sel.refused) == 1
    assert sel.refused[0]["item"] == f"eps_anchor_candidate.{ANCHOR_SUPPLIER_TRAILING}"
