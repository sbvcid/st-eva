"""The KO research lanes: The Coca-Cola Company, the first research case.

Four lanes are candidate research metrics and one is a diagnostic:

* ``RESEARCH_KO_REPORTED_REVENUE_MULTIPLE`` -- market capitalization over the
  trailing twelve months of KO's reported net operating revenues.
* ``RESEARCH_KO_REPORTED_OPERATING_PROFIT_PLUS_REPORTED_D_AND_A_MULTIPLE`` --
  market capitalization over the trailing twelve months of KO's reported
  operating income plus KO's reported depreciation and amortization.
* ``RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_PRODUCTION_SHAPE`` -- the filed
  enterprise-value bridge over the same operating denominator.
* ``RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_SHORT_TERM_BORROWINGS`` -- the same
  bridge with KO's total short-term borrowings in place of commercial paper.
* ``RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_DOUBLE_COUNTED_DIAGNOSTIC`` -- a
  diagnostic only. It measures what a bridge holding both commercial paper and
  loans and notes payable would overstate. It is not a candidate metric, it is
  not listed among the selectable research metrics, and its formula is
  deliberately written so that it cannot be mistaken for an acceptable
  enterprise-value definition.

None of these is a production metric, and none may be read as one. KO has no
production P/S and no production EV/EBITDA: the registry holds no mapping for
the element KO files for revenue, and the depreciation element is scoped to
other filers. The lanes read the same filed facts the production pipeline
reads and apply the same arithmetic; they differ only in the gate they apply
and in the names they publish under.

The difference between the two enterprise-value lanes is a difference of
scope, not a difference of arithmetic. ``us-gaap:NotesAndLoansPayable`` is
KO's balance-sheet line for its total short-term borrowings: KO's debt note
states that loans and notes payable consist primarily of commercial paper,
and the filed values satisfy NotesAndLoansPayable = CommercialPaper +
OtherShortTermBorrowings at every date at which both are reported. A bridge
that holds both therefore counts commercial paper twice, which is why the
diagnostic lane exists. A bridge that holds loans and notes payable *in place
of* commercial paper does not. The two candidate lanes also sample different
sets of dates, so the difference between their medians is not a measure of a
difference in debt.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from research_lane import (
    BRIDGE_SIGN_DEBT,
    BRIDGE_SIGN_LIQUID_FUNDS,
    CHANGE_RE_TAG,
    CHANGE_SCOPE_CHANGE,
    FORMULA_BRIDGE_COMPONENT,
    FORMULA_DEPRECIATION,
    FORMULA_DENOMINATOR,
    FORMULA_OPERATING_INCOME,
    FORMULA_SHARES,
    ResearchLaneConfig,
    ResearchLaneResult,
    ResearchRole,
    load_research_lane,
)

ROOT = Path(__file__).resolve().parent
CAPTURE_DIR = ROOT / "data" / "research_multiples" / "KO"

TICKER = "KO"
ISSUER_ID = "CIK0000021344"
ENTITY_NAME = "The Coca-Cola Company"
FISCAL_YEAR_END = 12

# ---------------------------------------------------------------------------
# The roles
# ---------------------------------------------------------------------------

REVENUE = ResearchRole(
    name="revenue",
    taxonomy="us-gaap",
    elements=("Revenues",),
    formula_role=FORMULA_DENOMINATOR,
    registry_metric_id="revenue",
    note=(
        "KO reports net operating revenues on us-gaap:Revenues. The core "
        "registry retired that element as a source of the `revenue` metric in "
        "decision 2.99, because the element's own definition is broader than "
        "the metric, so no production revenue role exists for KO on the "
        "element KO files. The registry's accepted revenue element, "
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax, is not "
        "filed by KO at all. The lane reads the element KO files and names "
        "what it reads."
    ),
)

OPERATING_INCOME = ResearchRole(
    name="operating_income",
    taxonomy="us-gaap",
    elements=("OperatingIncomeLoss",),
    formula_role=FORMULA_OPERATING_INCOME,
    registry_metric_id="operating_income",
    note=(
        "us-gaap:OperatingIncomeLoss is an EXACT IDENTITY mapping to the "
        "`operating_income` metric for every filer, so this role is "
        "registry-qualified. The role's values were re-presented by KO for "
        "the consolidation of Coca-Cola Beverages Africa; see the "
        "prior-period value revisions the lane records."
    ),
)

DEPRECIATION = ResearchRole(
    name="depreciation",
    taxonomy="us-gaap",
    elements=("DepreciationDepletionAndAmortization",),
    formula_role=FORMULA_DEPRECIATION,
    registry_metric_id="depreciation_and_amortization",
    note=(
        "KO's cash-flow line 'Depreciation and amortization' is carried on "
        "us-gaap:DepreciationDepletionAndAmortization. The registry maps that "
        "element to the `depreciation_and_amortization` metric for Apple and "
        "Nike alone, so for KO the standing is SCOPE_NOT_APPLICABLE and the "
        "role is not registry-qualified. The filed values are still evidence "
        "and a research lane may read them; the figure they produce is not the "
        "registry's EBITDA and is not named EBITDA. KO's separate "
        "us-gaap:Depreciation element is disclosed only annually and cannot "
        "carry a quarterly trailing window at all."
    ),
)

CASH = ResearchRole(
    name="cash",
    taxonomy="us-gaap",
    elements=("CashAndCashEquivalentsAtCarryingValue",),
    formula_role=FORMULA_BRIDGE_COMPONENT,
    registry_metric_id="cash",
    bridge_sign=BRIDGE_SIGN_LIQUID_FUNDS,
    note=(
        "us-gaap:CashAndCashEquivalentsAtCarryingValue is registry-qualified "
        "for KO."
    ),
)

MARKETABLE_SECURITIES = ResearchRole(
    name="marketable_securities_current",
    taxonomy="us-gaap",
    elements=("MarketableSecuritiesCurrent", "MarketableSecurities"),
    formula_role=FORMULA_BRIDGE_COMPONENT,
    registry_metric_id="marketable_securities_current",
    element_change_kind=CHANGE_RE_TAG,
    bridge_sign=BRIDGE_SIGN_LIQUID_FUNDS,
    note=(
        "The registry declares no `marketable_securities_current` metric, so "
        "it has no standing to rule on this component and the filed-bridge "
        "specification governs it. KO's 'Marketable securities' line is "
        "carried on us-gaap:MarketableSecuritiesCurrent through 2020-12-31 "
        "and on us-gaap:MarketableSecurities afterwards; the two carry the "
        "same filed value on the dates at which both are reported, so the "
        "change is a re-tagging of the same quantity and is disclosed as a "
        "basis break. KO's separate 'Short-term investments' line is not part "
        "of this component."
    ),
)

COMMERCIAL_PAPER = ResearchRole(
    name="commercial_paper",
    taxonomy="us-gaap",
    elements=("CommercialPaper",),
    formula_role=FORMULA_BRIDGE_COMPONENT,
    registry_metric_id="commercial_paper",
    bridge_sign=BRIDGE_SIGN_DEBT,
    note=(
        "The registry declares no `commercial_paper` metric, so it has no "
        "standing to rule on this component. KO does not carry a commercial "
        "paper line on the face of its balance sheet: KO's balance sheet "
        "carries 'Loans and notes payable' as the total of its short-term "
        "borrowings, and KO discloses commercial paper as a component of that "
        "line in its debt note. KO files this element annually only until "
        "2023, so a bridge that holds it is incomplete at most quarterly "
        "dates."
    ),
)

NOTES_AND_LOANS_PAYABLE = ResearchRole(
    name="notes_and_loans_payable",
    taxonomy="us-gaap",
    elements=("NotesAndLoansPayableCurrent", "NotesAndLoansPayable"),
    formula_role=FORMULA_BRIDGE_COMPONENT,
    registry_metric_id="notes_and_loans_payable",
    element_change_kind=CHANGE_RE_TAG,
    bridge_sign=BRIDGE_SIGN_DEBT,
    note=(
        "The registry declares no `notes_and_loans_payable` metric, so it has "
        "no standing to rule on this component. KO's balance-sheet line 'Loans "
        "and notes payable' is its total short-term borrowings: the debt note "
        "states that loans and notes payable consist primarily of commercial "
        "paper, and the filed values satisfy NotesAndLoansPayable = "
        "CommercialPaper + OtherShortTermBorrowings at every date at which "
        "both are reported. This role therefore REPLACES commercial paper in "
        "the bridge; a bridge holding both counts commercial paper twice."
    ),
)

LONG_TERM_DEBT_NONCURRENT = ResearchRole(
    name="long_term_debt_noncurrent",
    taxonomy="us-gaap",
    elements=(
        "LongTermDebtNoncurrent",
        "LongTermDebtAndCapitalLeaseObligations",
    ),
    formula_role=FORMULA_BRIDGE_COMPONENT,
    registry_metric_id="long_term_debt_noncurrent",
    element_change_kind=CHANGE_SCOPE_CHANGE,
    bridge_sign=BRIDGE_SIGN_DEBT,
    note=(
        "us-gaap:LongTermDebtNoncurrent is registry-qualified for KO and is "
        "filed through 2024-03-29. From 2023-12-31 KO carries the same line "
        "on us-gaap:LongTermDebtAndCapitalLeaseObligations, whose definition "
        "includes the lease obligation where the earlier element excluded it, "
        "so the element change is also a scope change and is disclosed as a "
        "basis break."
    ),
)

LONG_TERM_DEBT_CURRENT = ResearchRole(
    name="long_term_debt_current",
    taxonomy="us-gaap",
    elements=("LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"),
    formula_role=FORMULA_BRIDGE_COMPONENT,
    registry_metric_id="long_term_debt_current",
    element_change_kind=CHANGE_SCOPE_CHANGE,
    bridge_sign=BRIDGE_SIGN_DEBT,
    note=(
        "us-gaap:LongTermDebtCurrent is registry-qualified for KO and is "
        "filed through 2024-03-29. Its successor carries the current "
        "maturities of long-term debt from 2023-12-31 and, like its "
        "noncurrent counterpart, includes the lease obligation."
    ),
)

SHARES = ResearchRole(
    name="shares_outstanding",
    taxonomy="dei",
    elements=("EntityCommonStockSharesOutstanding",),
    formula_role=FORMULA_SHARES,
    registry_metric_id=None,
    note=(
        "Cover-page shares outstanding, taken as filed and never adjusted for "
        "a split, paired with the as-traded close. The registry declares no "
        "metric for it; the production rule for pairing it with the as-traded "
        "close governs the role."
    ),
)

BRIDGE_ROLES_COMMERCIAL_PAPER = (
    CASH,
    MARKETABLE_SECURITIES,
    COMMERCIAL_PAPER,
    LONG_TERM_DEBT_NONCURRENT,
    LONG_TERM_DEBT_CURRENT,
)
BRIDGE_ROLES_NOTES_AND_LOANS = (
    CASH,
    MARKETABLE_SECURITIES,
    NOTES_AND_LOANS_PAYABLE,
    LONG_TERM_DEBT_NONCURRENT,
    LONG_TERM_DEBT_CURRENT,
)
BRIDGE_ROLES_DOUBLE_COUNTED = (
    CASH,
    MARKETABLE_SECURITIES,
    COMMERCIAL_PAPER,
    NOTES_AND_LOANS_PAYABLE,
    LONG_TERM_DEBT_NONCURRENT,
    LONG_TERM_DEBT_CURRENT,
)


# ---------------------------------------------------------------------------
# The lanes
# ---------------------------------------------------------------------------


def _lane(
    lane_id: str,
    metric_id: str,
    metric_label: str,
    research_purpose: str,
    expression: str,
    numerator: str,
    denominator: str,
    denominator_roles: tuple[str, ...],
    bridge_roles: tuple[ResearchRole, ...],
    numerator_kind: str = "market_cap",
    candidate_metric: bool = True,
) -> ResearchLaneConfig:
    roles = (
        tuple(
            role
            for role in (
                REVENUE,
                OPERATING_INCOME,
                DEPRECIATION,
            )
            if role.name in denominator_roles
        )
        + bridge_roles
        + (SHARES,)
    )
    return ResearchLaneConfig(
        lane_id=lane_id,
        issuer_id=ISSUER_ID,
        instrument_id=TICKER,
        entity_name=ENTITY_NAME,
        fye_month=FISCAL_YEAR_END,
        capture_dir=CAPTURE_DIR,
        metric_id=metric_id,
        metric_label=metric_label,
        research_purpose=research_purpose,
        formula_expression=expression,
        formula_numerator=numerator,
        formula_denominator=denominator,
        denominator_roles=denominator_roles,
        roles=roles,
        numerator_kind=numerator_kind,
        candidate_metric=candidate_metric,
    )


LANE_CONFIGS: tuple[ResearchLaneConfig, ...] = (
    _lane(
        lane_id="ko_reported_revenue_multiple",
        metric_id="RESEARCH_KO_REPORTED_REVENUE_MULTIPLE",
        metric_label=(
            "KO reported-revenue multiple (research): market capitalization "
            "over the trailing twelve months of KO's reported net operating "
            "revenues"
        ),
        research_purpose=(
            "Research use only. A named alternative to a price-to-sales "
            "reference for KO, computed from the revenue element KO actually "
            "files. It is not a price-to-sales reference and it is not "
            "qualified for production use."
        ),
        expression=(
            "(as-traded close x cover-page shares outstanding) / TTM of "
            "us-gaap:Revenues"
        ),
        numerator=(
            "as-traded close on the evaluation date times the latest knowable "
            "cover-page shares outstanding"
        ),
        denominator=(
            "the trailing twelve months of us-gaap:Revenues, KO's reported "
            "net operating revenues, as four consecutive fiscal quarters"
        ),
        denominator_roles=("revenue",),
        bridge_roles=BRIDGE_ROLES_COMMERCIAL_PAPER,
    ),
    _lane(
        lane_id="ko_reported_operating_denominator_multiple",
        metric_id=(
            "RESEARCH_KO_REPORTED_OPERATING_PROFIT_PLUS_REPORTED_D_AND_A_MULTIPLE"
        ),
        metric_label=(
            "KO reported operating profit plus reported depreciation and "
            "amortization multiple (research): market capitalization over the "
            "trailing twelve months of KO's reported operating income plus "
            "KO's reported depreciation and amortization"
        ),
        research_purpose=(
            "Research use only. A named alternative operating denominator for "
            "KO, built from the two elements KO files. It is not EBITDA and it "
            "is not qualified for production use: the registry does not accept "
            "KO's depreciation element for the depreciation-and-amortization "
            "metric."
        ),
        expression=(
            "(as-traded close x cover-page shares outstanding) / TTM of "
            "(us-gaap:OperatingIncomeLoss + "
            "us-gaap:DepreciationDepletionAndAmortization)"
        ),
        numerator=(
            "as-traded close on the evaluation date times the latest knowable "
            "cover-page shares outstanding"
        ),
        denominator=(
            "the trailing twelve months of KO's reported operating income "
            "plus KO's reported depreciation and amortization, each a discrete "
            "fiscal quarter, summed over four consecutive quarters; a quarter "
            "missing either role is absent, not half a quarter"
        ),
        denominator_roles=("operating_income", "depreciation"),
        bridge_roles=BRIDGE_ROLES_COMMERCIAL_PAPER,
    ),
    _lane(
        lane_id="ko_filed_ev_bridge_multiple_production_shape",
        metric_id="RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_PRODUCTION_SHAPE",
        metric_label=(
            "KO filed enterprise-value bridge multiple, production shape "
            "(research): the filed bridge over the trailing twelve months of "
            "KO's reported operating income plus reported depreciation and "
            "amortization"
        ),
        research_purpose=(
            "Research use only. The filed enterprise-value bridge in the "
            "production component shape, so that a research figure and a "
            "production figure can be compared on the same bridge. It is not "
            "a production EV/EBITDA reference."
        ),
        expression=(
            "(market cap + total debt [long-term debt non-current + "
            "long-term debt current + commercial paper] - liquid funds [cash "
            "and cash equivalents + current marketable securities]) / TTM of "
            "(us-gaap:OperatingIncomeLoss + "
            "us-gaap:DepreciationDepletionAndAmortization)"
        ),
        numerator=(
            "the filed enterprise-value bridge: market capitalization plus "
            "total debt less liquid funds"
        ),
        denominator=(
            "the trailing twelve months of KO's reported operating income "
            "plus KO's reported depreciation and amortization"
        ),
        denominator_roles=("operating_income", "depreciation"),
        bridge_roles=BRIDGE_ROLES_COMMERCIAL_PAPER,
        numerator_kind="enterprise_value",
    ),
    _lane(
        lane_id="ko_filed_ev_bridge_multiple_short_term_borrowings",
        metric_id=(
            "RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_SHORT_TERM_BORROWINGS"
        ),
        metric_label=(
            "KO filed enterprise-value bridge multiple with loans and notes "
            "payable (research): the filed bridge, with KO's total short-term "
            "borrowings in place of commercial paper, over the trailing twelve "
            "months of KO's reported operating income plus reported "
            "depreciation and amortization"
        ),
        research_purpose=(
            "Research use only. The same filed bridge with KO's own 'Loans and "
            "notes payable' line in place of commercial paper. KO's line is "
            "its total short-term borrowings and includes commercial paper, "
            "so the substitution is scope-correct and a bridge holding both "
            "would double count. The two bridge lanes sample different dates, "
            "so the difference between their medians is not a difference in "
            "debt."
        ),
        expression=(
            "(market cap + total debt [long-term debt non-current + "
            "long-term debt current + loans and notes payable] - liquid funds "
            "[cash and cash equivalents + current marketable securities]) / "
            "TTM of (us-gaap:OperatingIncomeLoss + "
            "us-gaap:DepreciationDepletionAndAmortization)"
        ),
        numerator=(
            "the filed enterprise-value bridge with short-term borrowings "
            "read from KO's 'Loans and notes payable' line"
        ),
        denominator=(
            "the trailing twelve months of KO's reported operating income "
            "plus KO's reported depreciation and amortization"
        ),
        denominator_roles=("operating_income", "depreciation"),
        bridge_roles=BRIDGE_ROLES_NOTES_AND_LOANS,
        numerator_kind="enterprise_value",
    ),
    _lane(
        lane_id="ko_filed_ev_bridge_multiple_double_counted_diagnostic",
        metric_id=(
            "RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_DOUBLE_COUNTED_DIAGNOSTIC"
        ),
        metric_label=(
            "DIAGNOSTIC ONLY, NOT A CANDIDATE METRIC: a bridge holding "
            "commercial paper AND loans and notes payable in the short-term "
            "debt component, which counts KO's commercial paper twice"
        ),
        research_purpose=(
            "Diagnostic only. This lane exists to measure how far a bridge "
            "that counts commercial paper twice overstates the multiple. It "
            "is not a research metric, it is not offered as one, and its "
            "formula is not an acceptable enterprise-value definition."
        ),
        expression=(
            "(market cap + total debt [long-term debt non-current + "
            "long-term debt current + commercial paper + loans and notes "
            "payable] - liquid funds [cash and cash equivalents + current "
            "marketable securities]) / TTM of "
            "(us-gaap:OperatingIncomeLoss + "
            "us-gaap:DepreciationDepletionAndAmortization)"
        ),
        numerator=(
            "a bridge that is known to count commercial paper twice; a "
            "diagnostic measurement, not an enterprise-value definition"
        ),
        denominator=(
            "the trailing twelve months of KO's reported operating income "
            "plus KO's reported depreciation and amortization"
        ),
        denominator_roles=("operating_income", "depreciation"),
        bridge_roles=BRIDGE_ROLES_DOUBLE_COUNTED,
        numerator_kind="enterprise_value",
        candidate_metric=False,
    ),
)

#: The lanes that may be offered as research metrics. The diagnostic lane is
#: deliberately absent.
CANDIDATE_LANE_IDS: tuple[str, ...] = (
    "ko_reported_revenue_multiple",
    "ko_reported_operating_denominator_multiple",
    "ko_filed_ev_bridge_multiple_production_shape",
    "ko_filed_ev_bridge_multiple_short_term_borrowings",
)


def build_ko_research_lanes() -> List[ResearchLaneResult]:
    """Execute every KO research lane over the committed capture."""
    return [load_research_lane(config) for config in LANE_CONFIGS]


def _summary_payload(result: ResearchLaneResult) -> Dict[str, Any]:
    """The committed summary of one lane.

    Every evaluation date is listed with its value or its refusal, so a
    reader can see the whole sample, and the statistics can be recomputed
    from it. The full observation lineage is not committed: it is large, and
    the lane regenerates it exactly from the capture.
    """
    payload = result.to_dict()
    payload["observations"] = [
        {
            "evaluation_date": observation.evaluation_date,
            "status": observation.status,
            "value": observation.value,
            "reason_code": observation.reason_code,
            "price": observation.price,
            "shares_outstanding": observation.shares_outstanding,
            "market_cap": observation.market_cap,
            "enterprise_value": observation.enterprise_value,
            "denominator": (
                observation.denominator.get("value")
                if observation.denominator
                else None
            ),
            "content_hash": observation.content_hash,
        }
        for observation in result.observations
    ]
    payload["basis_breaks"] = payload["distribution"]["basis_breaks"]
    payload["observation_lineage"] = (
        "The committed summary carries one line per evaluation date. The full "
        "lineage -- every operand, accession, element, period, unit and "
        "usable date -- is regenerated exactly by the lane from the capture, "
        "whose files are hashed in the capture manifest."
    )
    return payload


def write_ko_research_outputs(output_dir: Path, include_lineage: bool = False) -> Dict[str, Any]:
    """Write the research tree: one summary per lane and an index.

    The output is a research artifact. It is written under the caller's
    directory and nowhere else; no production path is touched.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    results = build_ko_research_lanes()
    index: Dict[str, Any] = {
        "dataset": "KO research lane results",
        "purpose": (
            "Research use only. No figure here is a production reference, and "
            "nothing here is read by the production runner, the Investment "
            "Context or the Archive."
        ),
        "issuer": {"ticker": TICKER, "cik": ISSUER_ID, "entity_name": ENTITY_NAME},
        "methodology": "research-multiples/1.0",
        "logic_version": "research-multiples/1.0.0",
        "lanes": {},
        "candidate_lane_ids": list(CANDIDATE_LANE_IDS),
        "diagnostic_lane_ids": [
            result.lane_id for result in results if not result.candidate_metric
        ],
    }
    for result in results:
        payload = result.to_dict() if include_lineage else _summary_payload(result)
        path = output_dir / f"{result.lane_id}.json"
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        index["lanes"][result.lane_id] = {
            "metric_id": result.metric_id,
            "candidate_metric": result.candidate_metric,
            "status": result.distribution.status,
            "sample_count": result.distribution.sample_count,
            "total_evaluations": result.distribution.total_evaluations,
            "median": result.distribution.percentiles.get("median"),
            "mean": result.distribution.mean,
            "std": result.distribution.std,
            "period_start": result.distribution.period_start,
            "period_end": result.distribution.period_end,
            "rejection_counts": _rejection_counts(result.distribution),
            "prior_period_revisions": len(
                result.distribution.prior_period_revisions
            ),
            "input_set_id": result.input_set_id,
            "content_hash": result.content_hash,
            "file": path.name,
        }
    (output_dir / "manifest.json").write_text(
        json.dumps(index, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return index


def _rejection_counts(distribution: Any) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in distribution.excluded_observations:
        code = item["reason_code"]
        counts[code] = counts.get(code, 0) + 1
    return dict(sorted(counts.items()))
