from __future__ import annotations

"""
ST-EVA 2.5 - the registry seed.

Sixteen metrics and the source concepts actually observed in AAPL filings. Not
a universal financial taxonomy, and deliberately not one: this seed exists to
prove the design against real evidence, and a registry designed in the abstract
would only prove it against itself.

The concept definitions are quoted from the SEC company-concept endpoints, not
paraphrased. A paraphrase would let two concepts read as equal when the source
says otherwise, which is the failure the registry is built to prevent.

Three findings from real AAPL filings shaped these mappings, and each would
have been got wrong from the names alone:

    `us-gaap:Revenues` and
    `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` are both
    revenue and they overlap for two quarters of FY2018, but Revenues is the
    broader "earning process" measure and includes investment and interest
    income. Partially, not equivalently, comparable.

    `us-gaap:PaymentsToAcquireProductiveAssets` and
    `us-gaap:PaymentsToAcquirePropertyPlantAndEquipment` look like the same
    thing. The source says otherwise: the first includes "software, and other
    intangible assets" and the second does not. Partially comparable, and the
    pair is the clearest demonstration that a name is not a definition.

    `us-gaap:LongTermDebtNoncurrent` and `us-gaap:LongTermDebtCurrent` share
    a name family and are the noncurrent and current portions of the same
    obligation. They are never one series, and they are mapped to two
    different metrics rather than one.
"""

from typing import Dict, List, Optional, Sequence, Tuple

from core_registry import (
    MAPPING_EQUIVALENT,
    MAPPING_EXACT,
    MAPPING_NON_COMPARABLE,
    MAPPING_PARTIAL,
    Concept,
    ConceptMapping,
    CoreRegistry,
    Metric,
    concept_id_for,
)

BANK = "BANK"
MINING = "MINING"

# metric_id -> definition fields.
METRICS: Tuple[Metric, ...] = (
    Metric(
        metric_id="revenue",
        display_name="Revenue",
        statement="INCOME",
        semantic_definition=(
            "Revenue recognised in the reporting period from the filer's "
            "ordinary activities. Where a source reports a narrower concept "
            "than this, the mapping records that the figure is a component or "
            "a wider aggregate rather than treating the two as the same."
        ),
        unit_family="currency",
        normal_period_type="DURATION",
        comparability_group="income_statement_flows",
    ),
    Metric(
        metric_id="gross_profit",
        display_name="Gross profit",
        statement="INCOME",
        semantic_definition=(
            "Revenue less cost of revenue for the reporting period, as the "
            "filer reports it. Not computed by ST-EVA."
        ),
        unit_family="currency",
        normal_period_type="DURATION",
        comparability_group="income_statement_flows",
    ),
    Metric(
        metric_id="operating_income",
        display_name="Operating income",
        statement="INCOME",
        semantic_definition=(
            "Operating income for the reporting period. Not defined for a "
            "financial institution, whose operating result is not an "
            "operating-income concept."
        ),
        unit_family="currency",
        normal_period_type="DURATION",
        comparability_group="income_statement_flows",
        inapplicable_in=(BANK,),
    ),
    Metric(
        metric_id="r_and_d",
        display_name="Research and development expense",
        statement="INCOME",
        semantic_definition=(
            "Research and development expense recognised in the reporting "
            "period."
        ),
        unit_family="currency",
        normal_period_type="DURATION",
        comparability_group="income_statement_flows",
        inapplicable_in=(MINING,),
    ),
    Metric(
        metric_id="sga",
        display_name="Selling, general and administrative expense",
        statement="INCOME",
        semantic_definition=(
            "Selling, general and administrative expense recognised in the "
            "reporting period."
        ),
        unit_family="currency",
        normal_period_type="DURATION",
        comparability_group="income_statement_flows",
    ),
    Metric(
        metric_id="interest_expense",
        display_name="Interest expense",
        statement="INCOME",
        semantic_definition=(
            "Interest expense recognised in the reporting period. Gross and "
            "net interest are different quantities and are not one series."
        ),
        unit_family="currency",
        normal_period_type="DURATION",
        comparability_group="income_statement_flows",
    ),
    Metric(
        metric_id="income_tax",
        display_name="Income tax expense",
        statement="INCOME",
        semantic_definition="Income tax expense recognised in the period.",
        unit_family="currency",
        normal_period_type="DURATION",
        comparability_group="income_statement_flows",
    ),
    Metric(
        metric_id="net_income",
        display_name="Net income",
        statement="INCOME",
        semantic_definition=(
            "Net income for the reporting period as the filer reports it."
        ),
        unit_family="currency",
        normal_period_type="DURATION",
        comparability_group="income_statement_flows",
    ),
    Metric(
        metric_id="eps_diluted",
        display_name="Diluted earnings per share",
        statement="INCOME",
        semantic_definition=(
            "Diluted earnings per share for the reporting period. Per-share "
            "amounts are not strictly additive across periods."
        ),
        unit_family="per_share",
        normal_period_type="DURATION",
        comparability_group="per_share_amounts",
    ),
    Metric(
        metric_id="assets",
        display_name="Total assets",
        statement="BALANCE_SHEET",
        semantic_definition="Total assets at the balance sheet date.",
        unit_family="currency",
        normal_period_type="INSTANT",
        comparability_group="balance_sheet_totals",
    ),
    Metric(
        metric_id="cash",
        display_name="Cash and cash equivalents",
        statement="BALANCE_SHEET",
        semantic_definition=(
            "Cash and cash equivalents at the balance sheet date, excluding "
            "short-term investments, which are a different concept."
        ),
        unit_family="currency",
        normal_period_type="INSTANT",
        comparability_group="balance_sheet_current_assets",
    ),
    Metric(
        metric_id="long_term_debt_noncurrent",
        display_name="Long-term debt, excluding current maturities",
        statement="BALANCE_SHEET",
        semantic_definition=(
            "The noncurrent portion of long-term debt at the balance sheet "
            "date. A different quantity from the current portion, and never "
            "part of the same series."
        ),
        unit_family="currency",
        normal_period_type="INSTANT",
        comparability_group="debt_components",
    ),
    Metric(
        metric_id="long_term_debt_current",
        display_name="Current maturities of long-term debt",
        statement="BALANCE_SHEET",
        semantic_definition=(
            "The portion of long-term debt repayable within a year at the "
            "balance sheet date. A different quantity from the noncurrent "
            "portion."
        ),
        unit_family="currency",
        normal_period_type="INSTANT",
        comparability_group="debt_components",
    ),
    Metric(
        metric_id="debt",
        display_name="Total debt",
        statement="BALANCE_SHEET",
        semantic_definition=(
            "Borrowings classified as debt under this metric definition. No "
            "single standard concept states it, so it is a composition of "
            "declared components and the composition is recorded on each "
            "mapping."
        ),
        unit_family="currency",
        normal_period_type="INSTANT",
        comparability_group="balance_sheet_totals",
    ),
    Metric(
        metric_id="shares_outstanding",
        display_name="Shares outstanding",
        statement="MARKET",
        semantic_definition=(
            "Shares of the filer's registered security outstanding at a "
            "stated date. Distinct from a weighted-average diluted count over "
            "a period, and distinct from a listed-instrument count."
        ),
        unit_family="count",
        normal_period_type="INSTANT",
        comparability_group="share_counts",
    ),
    Metric(
        metric_id="operating_cash_flow",
        display_name="Operating cash flow",
        statement="CASH_FLOW",
        semantic_definition=(
            "Net cash from operating activities for the reporting period."
        ),
        unit_family="currency",
        normal_period_type="DURATION",
        comparability_group="cash_flows",
    ),
    Metric(
        metric_id="capex",
        display_name="Capital expenditure",
        statement="CASH_FLOW",
        semantic_definition=(
            "Cash outflow to acquire long-lived assets used in the normal "
            "conduct of business. Sources differ on whether software and "
            "intangibles are included, which the mapping records."
        ),
        unit_family="currency",
        normal_period_type="DURATION",
        comparability_group="cash_flows",
    ),
    Metric(
        metric_id="sbc",
        display_name="Share-based compensation",
        statement="CASH_FLOW",
        semantic_definition=(
            "Noncash expense for share-based payment arrangements for the "
            "reporting period."
        ),
        unit_family="currency",
        normal_period_type="DURATION",
        comparability_group="noncash_expenses",
    ),
)

# Concepts observed in AAPL filings. Definitions are the SEC's own wording,
# trimmed only for length.
US_GAAP = "us-gaap"
DEI = "dei"
VENDOR = "vendor"

CONCEPTS: Tuple[Concept, ...] = (
    Concept(
        concept_id=concept_id_for(
            US_GAAP, "RevenueFromContractWithCustomerExcludingAssessedTax"
        ),
        taxonomy=US_GAAP,
        concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        label="Revenue from Contract with Customer, Excluding Assessed Tax",
        source_definition=(
            "Amount, excluding tax collected from customer, of revenue from "
            "satisfaction of performance obligation by transferring promised "
            "good or service to customer."
        ),
    ),
    Concept(
        concept_id=concept_id_for(US_GAAP, "Revenues"),
        taxonomy=US_GAAP,
        concept="Revenues",
        label="Revenues",
        source_definition=(
            "Amount of revenue recognized from goods sold, services rendered, "
            "insurance premiums, or other activities that constitute an "
            "earning process. Includes, but is not limited to, investment and "
            "interest income before taxes."
        ),
    ),
    Concept(
        concept_id=concept_id_for(US_GAAP, "SalesRevenueNet"),
        taxonomy=US_GAAP,
        concept="SalesRevenueNet",
        label="Sales Revenue, Net",
        source_definition=(
            "Revenue from the company's main business operations, net of "
            "returns and allowances."
        ),
    ),
    Concept(
        concept_id=concept_id_for(US_GAAP, "NetIncomeLoss"),
        taxonomy=US_GAAP,
        concept="NetIncomeLoss",
        label="Net Income (Loss)",
        source_definition=(
            "Net income (loss) attributable to the parent."
        ),
    ),
    Concept(
        concept_id=concept_id_for(US_GAAP, "EarningsPerShareDiluted"),
        taxonomy=US_GAAP,
        concept="EarningsPerShareDiluted",
        label="Earnings Per Share, Diluted",
        source_definition=(
            "The weighted average number of ordinary shares outstanding used "
            "to calculate diluted earnings per share."
        ),
    ),
    Concept(
        concept_id=concept_id_for(US_GAAP, "Assets"),
        taxonomy=US_GAAP,
        concept="Assets",
        label="Assets",
        source_definition="Assets at the end of the period.",
    ),
    Concept(
        concept_id=concept_id_for(US_GAAP, "CashAndCashEquivalentsAtCarryingValue"),
        taxonomy=US_GAAP,
        concept="CashAndCashEquivalentsAtCarryingValue",
        label="Cash and Cash Equivalents, at Carrying Value",
        source_definition=(
            "Cash and cash equivalents with a maturity of three months or "
            "less, net of related liabilities."
        ),
    ),
    Concept(
        concept_id=concept_id_for(
            US_GAAP, "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"
        ),
        taxonomy=US_GAAP,
        concept="CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        label="Cash, Cash Equivalents and Restricted Cash",
        source_definition=(
            "Cash, cash equivalents and restricted cash. Wider than cash "
            "alone because restricted amounts are included."
        ),
    ),
    Concept(
        concept_id=concept_id_for(US_GAAP, "LongTermDebtNoncurrent"),
        taxonomy=US_GAAP,
        concept="LongTermDebtNoncurrent",
        label="Long-term Debt, Excluding Current Maturities",
        source_definition=(
            "Amount after unamortized (discount) premium and debt issuance "
            "costs of long-term debt classified as noncurrent and excluding "
            "amounts to be repaid within one year or the normal operating "
            "cycle, if longer."
        ),
    ),
    Concept(
        concept_id=concept_id_for(US_GAAP, "LongTermDebtCurrent"),
        taxonomy=US_GAAP,
        concept="LongTermDebtCurrent",
        label="Long-term Debt, Current Maturities",
        source_definition=(
            "Amount after unamortized (discount) premium and debt issuance "
            "costs of long-term debt, classified as current."
        ),
    ),
    Concept(
        concept_id=concept_id_for(
            US_GAAP, "PaymentsToAcquirePropertyPlantAndEquipment"
        ),
        taxonomy=US_GAAP,
        concept="PaymentsToAcquirePropertyPlantAndEquipment",
        label="Payments to Acquire Property, Plant, and Equipment",
        source_definition=(
            "The cash outflow associated with the acquisition of long-lived, "
            "physical assets that are used in the normal conduct of business "
            "to produce goods and services and not intended for resale; "
            "includes cash outflows to pay for construction of "
            "self-constructed assets."
        ),
    ),
    Concept(
        concept_id=concept_id_for(US_GAAP, "PaymentsToAcquireProductiveAssets"),
        taxonomy=US_GAAP,
        concept="PaymentsToAcquireProductiveAssets",
        label="Payments to Acquire Productive Assets",
        source_definition=(
            "The cash outflow for purchases of and capital improvements on "
            "property, plant and equipment (capital expenditures), software, "
            "and other intangible assets."
        ),
    ),
    Concept(
        concept_id=concept_id_for(US_GAAP, "ShareBasedCompensation"),
        taxonomy=US_GAAP,
        concept="ShareBasedCompensation",
        label="Share-based Payment Arrangement, Noncash Expense",
        source_definition=(
            "Amount of noncash expense for share-based payment arrangement."
        ),
    ),
    Concept(
        concept_id=concept_id_for(DEI, "EntityCommonStockSharesOutstanding"),
        taxonomy=DEI,
        concept="EntityCommonStockSharesOutstanding",
        label="Entity Common Stock, Shares Outstanding",
        source_definition=(
            "Indicate number of shares or units of common stock outstanding as "
            "of the cover-page date of the document. The registrant, not the "
            "listed instrument, unless the two are the same."
        ),
    ),
    Concept(
        concept_id=concept_id_for(VENDOR, "trailingTotalRevenue"),
        taxonomy=VENDOR,
        concept="trailingTotalRevenue",
        label="Trailing total revenue (vendor field)",
        source_definition=(
            "Vendor trailing twelve month total revenue. The vendor publishes "
            "no window, so the mapping is declared equivalent on the evidence "
            "of the cross-source comparison rather than on the field name."
        ),
    ),
)

MAPPINGS: Tuple[ConceptMapping, ...] = (
    # Revenue. Three source concepts, three different claims.
    #
    # The contract-revenue concept is the filer's own revenue line, so it maps
    # EXACTLY. The other two are wider measures and map only PARTIALLY; the
    # windows record when each held, because a series that crosses between them
    # is not one series.
    ConceptMapping(
        metric_id="revenue",
        concept_id=concept_id_for(
            US_GAAP, "RevenueFromContractWithCustomerExcludingAssessedTax"
        ),
        mapping_type=MAPPING_EXACT,
        effective_from="2017-09-30",
        notes="the filer's own contract-revenue line, 117 facts to 2026-06-27",
    ),
    ConceptMapping(
        metric_id="revenue",
        concept_id=concept_id_for(US_GAAP, "Revenues"),
        mapping_type=MAPPING_PARTIAL,
        effective_from="2016-09-24",
        effective_to="2018-09-29",
        notes=(
            "wider earning-process measure including investment and interest "
            "income; overlaps the contract-revenue concept for two quarters, so "
            "the series does not continue across the change"
        ),
    ),
    ConceptMapping(
        metric_id="revenue",
        concept_id=concept_id_for(US_GAAP, "SalesRevenueNet"),
        mapping_type=MAPPING_PARTIAL,
        effective_from="2007-09-29",
        effective_to="2018-06-30",
        notes="net sales revenue, a third concept and a third window",
    ),
    ConceptMapping(
        metric_id="revenue",
        concept_id=concept_id_for(VENDOR, "trailingTotalRevenue"),
        mapping_type=MAPPING_EQUIVALENT,
        notes=(
            "cross-taxonomy equivalence, evidenced by the 2.3-B cross-source "
            "verdict for this issuer rather than by the field name"
        ),
    ),
    ConceptMapping(
        metric_id="net_income",
        concept_id=concept_id_for(US_GAAP, "NetIncomeLoss"),
        mapping_type=MAPPING_EXACT,
    ),
    ConceptMapping(
        metric_id="eps_diluted",
        concept_id=concept_id_for(US_GAAP, "EarningsPerShareDiluted"),
        mapping_type=MAPPING_EXACT,
    ),
    ConceptMapping(
        metric_id="assets",
        concept_id=concept_id_for(US_GAAP, "Assets"),
        mapping_type=MAPPING_EXACT,
    ),
    ConceptMapping(
        metric_id="cash",
        concept_id=concept_id_for(US_GAAP, "CashAndCashEquivalentsAtCarryingValue"),
        mapping_type=MAPPING_EXACT,
    ),
    ConceptMapping(
        metric_id="cash",
        concept_id=concept_id_for(
            US_GAAP,
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        ),
        mapping_type=MAPPING_PARTIAL,
        effective_from="2016-09-24",
        notes="includes restricted cash, so it is wider than cash alone",
    ),
    # Debt. The two portions are different quantities and are deliberately
    # mapped to two different metrics rather than summed by the registry.
    ConceptMapping(
        metric_id="long_term_debt_noncurrent",
        concept_id=concept_id_for(US_GAAP, "LongTermDebtNoncurrent"),
        mapping_type=MAPPING_EXACT,
        effective_from="2014-09-27",
    ),
    ConceptMapping(
        metric_id="long_term_debt_current",
        concept_id=concept_id_for(US_GAAP, "LongTermDebtCurrent"),
        mapping_type=MAPPING_EXACT,
        effective_from="2014-09-27",
    ),
    ConceptMapping(
        metric_id="debt",
        concept_id=concept_id_for(US_GAAP, "LongTermDebtNoncurrent"),
        mapping_type=MAPPING_PARTIAL,
        effective_from="2014-09-27",
        notes="a component of total debt, never the total on its own",
    ),
    ConceptMapping(
        metric_id="debt",
        concept_id=concept_id_for(US_GAAP, "LongTermDebtCurrent"),
        mapping_type=MAPPING_PARTIAL,
        effective_from="2014-09-27",
        notes="a component of total debt, never the total on its own",
    ),
    # Capital expenditure. The clearest demonstration that a name is not a
    # definition: these two read alike, and the SEC says one includes software
    # and intangibles while the other does not.
    ConceptMapping(
        metric_id="capex",
        concept_id=concept_id_for(
            US_GAAP, "PaymentsToAcquirePropertyPlantAndEquipment"
        ),
        mapping_type=MAPPING_EXACT,
        effective_from="2013-09-28",
    ),
    ConceptMapping(
        metric_id="capex",
        concept_id=concept_id_for(US_GAAP, "PaymentsToAcquireProductiveAssets"),
        mapping_type=MAPPING_PARTIAL,
        effective_from="2007-09-29",
        effective_to="2014-09-27",
        notes=(
            "includes software and other intangible assets, which the "
            "property-and-equipment concept does not, so the series does not "
            "continue across the change"
        ),
    ),
    ConceptMapping(
        metric_id="sbc",
        concept_id=concept_id_for(US_GAAP, "ShareBasedCompensation"),
        mapping_type=MAPPING_EXACT,
        effective_from="2007-09-29",
    ),
    ConceptMapping(
        metric_id="shares_outstanding",
        concept_id=concept_id_for(DEI, "EntityCommonStockSharesOutstanding"),
        mapping_type=MAPPING_EXACT,
        notes=(
            "the registrant's registered security; a listed-instrument count "
            "is a different quantity and is not mapped here"
        ),
    ),
)


def seed(registry: CoreRegistry) -> Dict[str, int]:
    """Load the registry seed. Idempotent."""
    for metric in METRICS:
        registry.add_metric(metric, inapplicable_in=metric.inapplicable_in)
    for concept in CONCEPTS:
        registry.add_concept(concept)
    for mapping in MAPPINGS:
        registry.add_mapping(mapping)
    return {
        "metrics": len(METRICS),
        "concepts": len(CONCEPTS),
        "mappings": len(MAPPINGS),
    }
