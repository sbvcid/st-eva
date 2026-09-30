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
    REASON_COMPONENT_OF,
    REASON_DIFFERENT_QUANTITY,
    REASON_IDENTITY_MISMATCH,
    REASON_NOT_A_METRIC,
    Concept,
    ConceptMapping,
    CoreRegistry,
    DeclinedConcept,
    Metric,
    concept_id_for,
)

BANK = "BANK"
MINING = "MINING"
# A filer the SEC classifies under SIC major group 61 or 62. Declared separately
# from `BANK` because that is the label the filer carries, and this project's
# rule is that a claim is recorded at the strength the evidence supports: naming
# a filer "BANK" when its own submission says "Finance Services" would be a
# classification somebody made rather than one anybody published.
FINANCE_SERVICES = "FINANCE_SERVICES"

# The two financial models together, for the metrics a financial institution does
# not have. Written as a tuple at each use site rather than collapsed into one
# member, because the two names are both load-bearing: `BANK` is what a metric was
# declared against in 2.5, `FINANCE_SERVICES` is what a filer can be recorded as
# in 2.7, and merging them would silently re-point every earlier ruling at a
# vocabulary that did not exist when they were made.
FINANCIAL = (BANK, FINANCE_SERVICES)

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
            "filer reports it. Not computed by ST-EVA. A financial institution "
            "has no cost-of-revenue line against which to take this difference, "
            "so the metric has no meaning there rather than a missing value."
        ),
        unit_family="currency",
        normal_period_type="DURATION",
        comparability_group="income_statement_flows",
        # Declared on the definition, not on any issuer's empty data.
        #
        # The distinction this is here to keep is the one that gets lost: an
        # inapplicable metric and a metric with no observations are different
        # facts with different remedies, and only the first of them is a
        # statement about the company. A bank's income statement has interest
        # income and interest expense and no cost of sales, so "revenue less
        # cost of revenue" is undefined there -- the line does not exist to be
        # missing. Inheriting this from an empty observation count would get the
        # right answer for the wrong reason and would make the two collapse.
        inapplicable_in=FINANCIAL,
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
        inapplicable_in=FINANCIAL,
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
    # Added in 2.9, and it exists because `shares_outstanding` is not it.
    #
    # Three different share populations share almost identical names: shares
    # outstanding at a date, the weighted-average count over a period, and the
    # *diluted* version of that. The first was already registered and the
    # definition says so; the other two are not the same quantity and folding
    # them in would be a silent change of meaning.
    #
    # The diluted count is added separately because it is the denominator a
    # research question about "shares" almost always means, and because its
    # availability turns out to differ sharply by framework -- see the declines
    # in 2.9, where the US-GAAP element is EXACT and the IFRS one is declined
    # for being the basic count.
    Metric(
        metric_id="weighted_average_diluted_shares",
        display_name="Weighted-average diluted shares",
        statement="INCOME",
        semantic_definition=(
            "The weighted-average number of shares outstanding, diluted, used as "
            "the denominator of diluted earnings per share for the reporting "
            "period. Not shares outstanding at a date, and not the basic "
            "weighted-average count: the diluted figure is larger whenever there "
            "are dilutive instruments, and a series that mixed the two would be "
            "a series of two different populations."
        ),
        unit_family="count",
        normal_period_type="DURATION",
        comparability_group="share_counts",
    ),
    Metric(
        metric_id="equity",
        display_name="Shareholders' equity",
        statement="BALANCE_SHEET",
        semantic_definition=(
            "Total equity attributable to the owners of the parent at the "
            "balance sheet date. Distinct from total equity including "
            "non-controlling interests, which is a wider aggregate, and from "
            "total assets, which several standards' balance-sheet labels "
            "contain the word 'equity' in and which is not equity at all."
        ),
        unit_family="currency",
        normal_period_type="INSTANT",
        comparability_group="balance_sheet_totals",
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
# The second accounting framework. Foreign private issuers filing on Form 20-F
# report under IFRS as issued by the IASB, and the taxonomy those filings use is
# `ifrs-full`. It is a framework name and not a company name: nothing in this
# module may branch on it, and the mappings below are declared against the
# metric definitions rather than against any issuer's filing.
IFRS_FULL = "ifrs-full"

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
    # -- IFRS ------------------------------------------------------------
    #
    # A second accounting framework, not a second company. Every concept below
    # is declared for `ifrs-full` because that is the taxonomy that issues it;
    # nothing below mentions the issuer whose filing prompted the reading, and
    # the mappings are declared on the metric's own definition.
    #
    # Definitions are IFRS Foundation wording, trimmed for length. `Revenue` is
    # the one to read carefully: IFRS revenue is an aggregate of ordinary-activity
    # income that may include interest, dividend, royalty and grant income, while
    # the metric's exact US-GAAP concept is contracts-with-customers only. Similar
    # labels, different contents, which is the whole point of declaring them.
    Concept(
        concept_id=concept_id_for(IFRS_FULL, "Revenue"),
        taxonomy=IFRS_FULL,
        concept="Revenue",
        label="Revenue",
        source_definition=(
            "Income from the entity's ordinary activities, including sales of "
            "goods, rendering of services, and interest, dividend, royalty and "
            "grant income that the entity designates part of ordinary "
            "activities."
        ),
    ),
    Concept(
        concept_id=concept_id_for(IFRS_FULL, "ProfitLoss"),
        taxonomy=IFRS_FULL,
        concept="ProfitLoss",
        label="Profit (loss)",
        source_definition=(
            "The total of profit or loss for the period, including profit or "
            "loss attributable to non-controlling interests."
        ),
    ),
    Concept(
        concept_id=concept_id_for(
            IFRS_FULL, "ProfitLossAttributableToOwnersOfParent"
        ),
        taxonomy=IFRS_FULL,
        concept="ProfitLossAttributableToOwnersOfParent",
        label="Profit (loss) attributable to owners of the parent",
        source_definition=(
            "The portion of the profit or loss for the period attributable to "
            "the owners of the parent."
        ),
    ),
    Concept(
        concept_id=concept_id_for(IFRS_FULL, "Assets"),
        taxonomy=IFRS_FULL,
        concept="Assets",
        label="Assets",
        source_definition=(
            "A present economic resource controlled by the entity as a result "
            "of past events from which an economic benefit is expected to flow."
        ),
    ),
    Concept(
        concept_id=concept_id_for(IFRS_FULL, "CashAndCashEquivalents"),
        taxonomy=IFRS_FULL,
        concept="CashAndCashEquivalents",
        label="Cash and cash equivalents",
        source_definition=(
            "Short-term, highly liquid investments that are readily convertible "
            "to known amounts of cash and subject to an insignificant risk of "
            "changes in value. Short-term investments held for trading or "
            "short-term treasury management are a separate line."
        ),
    ),
    Concept(
        concept_id=concept_id_for(IFRS_FULL, "DilutedEarningsLossPerShare"),
        taxonomy=IFRS_FULL,
        concept="DilutedEarningsLossPerShare",
        label="Diluted earnings (loss) per share",
        source_definition=(
            "The weighted average number of ordinary shares outstanding used to "
            "calculate diluted earnings per share, from continuing operations "
            "unless the entity reports otherwise."
        ),
    ),
    Concept(
        concept_id=concept_id_for(IFRS_FULL, "NumberOfSharesIssuedAndFullyPaid"),
        taxonomy=IFRS_FULL,
        concept="NumberOfSharesIssuedAndFullyPaid",
        label="Number of shares issued and fully paid",
        source_definition=(
            "The number of shares of the entity that have been issued to "
            "holders and fully paid for."
        ),
    ),
    Concept(
        concept_id=concept_id_for(IFRS_FULL, "CurrentPortionOfLongtermBorrowings"),
        taxonomy=IFRS_FULL,
        concept="CurrentPortionOfLongtermBorrowings",
        label="Current portion of long-term borrowings",
        source_definition=(
            "The amount of long-term borrowings that is repayable within one "
            "year of the reporting date."
        ),
    ),
    Concept(
        concept_id=concept_id_for(IFRS_FULL, "LongtermBorrowings"),
        taxonomy=IFRS_FULL,
        concept="LongtermBorrowings",
        label="Long-term borrowings",
        source_definition=(
            "Interest-bearing liabilities repayable more than one year after "
            "the reporting date, excluding the current portion."
        ),
    ),
    # -- 2.9: the Core metrics that had no declared concept ----------------
    #
    # Every concept below was found by inventorying what these filers actually
    # report, not by matching a name. Seven Core metrics held nothing in 2.8
    # because the registry declared no concept to ask the source about, and
    # ingestion cannot close a registry gap no matter how hard it runs -- there
    # is nothing to ask for.
    Concept(
        concept_id=concept_id_for(US_GAAP, "GrossProfit"),
        taxonomy=US_GAAP,
        concept="GrossProfit",
        label="Gross Profit",
        source_definition=(
            "Revenue less cost of revenue, as presented on the statement of "
            "operations."
        ),
    ),
    Concept(
        concept_id=concept_id_for(US_GAAP, "OperatingIncomeLoss"),
        taxonomy=US_GAAP,
        concept="OperatingIncomeLoss",
        label="Operating Income (Loss)",
        source_definition=(
            "The result of operating activities, before interest, taxes and "
            "non-operating items, as presented by the filer."
        ),
    ),
    Concept(
        concept_id=concept_id_for(US_GAAP, "ResearchAndDevelopmentExpense"),
        taxonomy=US_GAAP,
        concept="ResearchAndDevelopmentExpense",
        label="Research and Development Expense",
        source_definition=(
            "Costs incurred in research and development activities, as "
            "presented on the statement of operations."
        ),
    ),
    Concept(
        concept_id=concept_id_for(US_GAAP, "InterestExpense"),
        taxonomy=US_GAAP,
        concept="InterestExpense",
        label="Interest Expense",
        source_definition=(
            "Interest incurred on the filer's borrowings, as presented."
        ),
    ),
    Concept(
        concept_id=concept_id_for(US_GAAP, "InterestExpenseDebt"),
        taxonomy=US_GAAP,
        concept="InterestExpenseDebt",
        label="Interest Expense, Debt",
        source_definition=(
            "Interest incurred on debt specifically, a component of total "
            "interest expense."
        ),
    ),
    Concept(
        concept_id=concept_id_for(US_GAAP, "IncomeTaxExpenseBenefit"),
        taxonomy=US_GAAP,
        concept="IncomeTaxExpenseBenefit",
        label="Income Tax Expense (Benefit)",
        source_definition=(
            "The income tax expense or benefit for the period, on an accrual "
            "basis and as presented."
        ),
    ),
    Concept(
        concept_id=concept_id_for(
            US_GAAP, "NetCashProvidedByUsedInOperatingActivities"
        ),
        taxonomy=US_GAAP,
        concept="NetCashProvidedByUsedInOperatingActivities",
        label="Net Cash Provided by (Used in) Operating Activities",
        source_definition=(
            "The net cash inflow or outflow from operating activities for the "
            "period, after adjustments for non-cash items."
        ),
    ),
    Concept(
        concept_id=concept_id_for(US_GAAP, "StockholdersEquity"),
        taxonomy=US_GAAP,
        concept="StockholdersEquity",
        label="Stockholders' Equity Attributable to Parent",
        source_definition=(
            "Equity attributable to the parent, excluding non-controlling "
            "interests."
        ),
    ),
    Concept(
        concept_id=concept_id_for(
            US_GAAP, "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"
        ),
        taxonomy=US_GAAP,
        concept=(
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"
        ),
        label="Stockholders Equity Including Portion Attributable to Noncontrolling Interest",
        source_definition=(
            "Total equity including the portion attributable to "
            "non-controlling interests."
        ),
    ),
    Concept(
        concept_id=concept_id_for(
            US_GAAP, "WeightedAverageNumberOfDilutedSharesOutstanding"
        ),
        taxonomy=US_GAAP,
        concept="WeightedAverageNumberOfDilutedSharesOutstanding",
        label="Weighted Average Number of Shares Outstanding, Diluted",
        source_definition=(
            "The weighted-average shares outstanding used to compute diluted "
            "earnings per share, including the dilutive effect of convertible "
            "and other instruments."
        ),
    ),
    # -- IFRS, for the same Core metrics ----------------------------------
    Concept(
        concept_id=concept_id_for(IFRS_FULL, "GrossProfit"),
        taxonomy=IFRS_FULL,
        concept="GrossProfit",
        label="Gross profit",
        source_definition=(
            "Revenue less cost of sales, as presented in the statement of "
            "profit or loss."
        ),
    ),
    Concept(
        concept_id=concept_id_for(IFRS_FULL, "ResearchAndDevelopmentExpense"),
        taxonomy=IFRS_FULL,
        concept="ResearchAndDevelopmentExpense",
        label="Research and development expense",
        source_definition=(
            "Expenses incurred on research and development activities, as "
            "recognised in profit or loss."
        ),
    ),
    Concept(
        concept_id=concept_id_for(IFRS_FULL, "InterestExpense"),
        taxonomy=IFRS_FULL,
        concept="InterestExpense",
        label="Finance costs -- interest expense",
        source_definition=(
            "Interest expense recognised in profit or loss, as presented."
        ),
    ),
    Concept(
        concept_id=concept_id_for(IFRS_FULL, "FinanceCosts"),
        taxonomy=IFRS_FULL,
        concept="FinanceCosts",
        label="Finance costs",
        source_definition=(
            "Finance costs recognised in profit or loss, which may include "
            "interest and items other than interest."
        ),
    ),
    Concept(
        concept_id=concept_id_for(IFRS_FULL, "IncomeTaxExpenseContinuingOperations"),
        taxonomy=IFRS_FULL,
        concept="IncomeTaxExpenseContinuingOperations",
        label="Income tax expense continuing operations",
        source_definition=(
            "The income tax expense relating to continuing operations."
        ),
    ),
    Concept(
        concept_id=concept_id_for(
            IFRS_FULL, "CashFlowsFromUsedInOperatingActivities"
        ),
        taxonomy=IFRS_FULL,
        concept="CashFlowsFromUsedInOperatingActivities",
        label="Cash flows from used in operating activities",
        source_definition=(
            "The net cash inflow or outflow from operating activities, after "
            "adjusting for non-cash items."
        ),
    ),
    Concept(
        concept_id=concept_id_for(IFRS_FULL, "EquityAttributableToOwnersOfParent"),
        taxonomy=IFRS_FULL,
        concept="EquityAttributableToOwnersOfParent",
        label="Equity attributable to owners of parent",
        source_definition=(
            "The portion of equity attributable to the owners of the parent."
        ),
    ),
    Concept(
        concept_id=concept_id_for(IFRS_FULL, "Equity"),
        taxonomy=IFRS_FULL,
        concept="Equity",
        label="Equity",
        source_definition=(
            "Total equity, including the portion attributable to "
            "non-controlling interests."
        ),
    ),
    Concept(
        concept_id=concept_id_for(IFRS_FULL, "WeightedAverageShares"),
        taxonomy=IFRS_FULL,
        concept="WeightedAverageShares",
        label="Weighted average number of ordinary shares",
        source_definition=(
            "The weighted-average number of ordinary shares outstanding during "
            "the period. IFRS presents the basic count as a standard element; "
            "the diluted count is disclosed in the earnings-per-share note "
            "rather than as an element of its own."
        ),
    ),
    Concept(
        concept_id=concept_id_for(
            US_GAAP, "SellingGeneralAndAdministrativeExpense"
        ),
        taxonomy=US_GAAP,
        concept="SellingGeneralAndAdministrativeExpense",
        label="Selling, General and Administrative Expense",
        source_definition=(
            "Selling, general and administrative expenses, as presented on the "
            "statement of operations."
        ),
    ),
    Concept(
        concept_id=concept_id_for(US_GAAP, "GeneralAndAdministrativeExpense"),
        taxonomy=US_GAAP,
        concept="GeneralAndAdministrativeExpense",
        label="General and Administrative Expense",
        source_definition=(
            "General and administrative expenses, excluding selling costs "
            "where the filer reports those separately."
        ),
    ),
    Concept(
        concept_id=concept_id_for(IFRS_FULL, "GeneralAndAdministrativeExpense"),
        taxonomy=IFRS_FULL,
        concept="GeneralAndAdministrativeExpense",
        label="General and administrative expense",
        source_definition=(
            "General and administrative expenses recognised in profit or loss, "
            "as presented. IFRS has no standard element combining selling and "
            "administrative costs."
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
    # -- IFRS ------------------------------------------------------------
    #
    # Four are EXACT, four are PARTIAL, and the notes say why in each case. The
    # rule applied throughout: EXACT only where the metric's own definition and
    # the source concept's own definition say the same thing, and PARTIAL
    # wherever one is a component or a wider aggregate of the other -- which is
    # what `CONTINUING_MAPPINGS` exists to make visible, because a series
    # spliced across a PARTIAL boundary would splice two different numbers into
    # one line.
    #
    # Two things are deliberately NOT mapped, and their absence is the point of
    # the exercise rather than an oversight:
    #
    #   `ifrs-full:RevenueFromContractsWithCustomers` is a *component* of
    #   `ifrs-full:Revenue`. Mapping both would put two IFRS figures into one
    #   metric for the same period, and the reader could not tell which line the
    #   issuer actually presented.
    #
    #   `ifrs-full:DilutedEarningsLossPerShareFromContinuingOperations` measures
    #   continuing operations only, and the metric is defined for the reporting
    #   period without that qualifier. It is a different quantity and forcing it
    #   in would be the exact failure this framework boundary exists to catch.
    ConceptMapping(
        metric_id="assets",
        concept_id=concept_id_for(IFRS_FULL, "Assets"),
        mapping_type=MAPPING_EXACT,
        notes=(
            "the metric is total assets at the balance sheet date and the "
            "IFRS element is a present economic resource controlled by the "
            "entity; neither framework admits a narrower reading of the line"
        ),
    ),
    ConceptMapping(
        metric_id="cash",
        concept_id=concept_id_for(IFRS_FULL, "CashAndCashEquivalents"),
        mapping_type=MAPPING_EXACT,
        notes=(
            "the metric definition already excludes short-term investments as a "
            "different concept, and the IFRS element draws the same line: "
            "trading and short-term treasury investments are a separate line. "
            "A definition written to be framework-neutral is satisfied by both "
            "frameworks, which is the strongest evidence available that it is"
        ),
    ),
    ConceptMapping(
        metric_id="eps_diluted",
        concept_id=concept_id_for(IFRS_FULL, "DilutedEarningsLossPerShare"),
        mapping_type=MAPPING_EXACT,
        notes=(
            "weighted-average diluted share count over the reporting period in "
            "both frameworks; the continuing-operations variant is a different "
            "quantity and is deliberately not mapped"
        ),
    ),
    ConceptMapping(
        metric_id="net_income",
        concept_id=concept_id_for(
            IFRS_FULL, "ProfitLossAttributableToOwnersOfParent"
        ),
        mapping_type=MAPPING_EXACT,
        notes=(
            "profit attributable to the owners of the parent, which is what the "
            "metric defines as net income as the filer reports it, and the "
            "same parent-only claim the US-GAAP net-income element makes"
        ),
    ),
    ConceptMapping(
        metric_id="revenue",
        concept_id=concept_id_for(IFRS_FULL, "Revenue"),
        mapping_type=MAPPING_PARTIAL,
        effective_from="2015-12-31",
        notes=(
            "IFRS revenue is an aggregate of ordinary-activity income and may "
            "carry interest, dividend, royalty and grant income, while the "
            "metric's exact US-GAAP concept is contracts-with-customers only, "
            "which is a component of it. Filers differ in whether they fold the "
            "other income in, so the two tags are not the same claim. A filer "
            "that reports the components separately makes the figures coincide; "
            "that is a fact about that filer and not a definition, and the "
            "mapping has to survive one that does not. Window: the earliest "
            "period this element is reported for by any filer using the "
            "taxonomy, with no end date because nothing observed here is "
            "evidence that it stopped"
        ),
    ),
    ConceptMapping(
        metric_id="net_income",
        concept_id=concept_id_for(IFRS_FULL, "ProfitLoss"),
        mapping_type=MAPPING_PARTIAL,
        effective_from="2015-12-31",
        notes=(
            "total profit including non-controlling interests, a wider "
            "aggregate than the parent-only net income the metric defines. "
            "Where a filer reports both, the two differ by exactly the "
            "non-controlling interest, which is the test for whether a series "
            "may continue across them. Window: earliest reported period for the "
            "element across filers using the taxonomy"
        ),
    ),
    ConceptMapping(
        metric_id="shares_outstanding",
        concept_id=concept_id_for(IFRS_FULL, "NumberOfSharesIssuedAndFullyPaid"),
        mapping_type=MAPPING_PARTIAL,
        effective_from="2016-12-31",
        notes=(
            "issued and fully paid is not the same claim as outstanding: the "
            "two are equal only where the filer holds no treasury shares, and "
            "the archive holds no evidence either way. The metric definition "
            "already excludes a weighted-average count over a period and a "
            "listed-instrument count; issued is a third thing. Window: earliest "
            "reported period for the element across filers using the taxonomy"
        ),
    ),
    ConceptMapping(
        metric_id="debt",
        concept_id=concept_id_for(IFRS_FULL, "CurrentPortionOfLongtermBorrowings"),
        mapping_type=MAPPING_PARTIAL,
        effective_from="2016-12-31",
        notes=(
            "one declared component of a composition, exactly as the US-GAAP "
            "current/non-current long-term pair already is. The metric states "
            "that no single standard concept declares debt, so the composition "
            "is recorded on each mapping and a series must not continue across "
            "a partial boundary. Window: earliest reported period for the "
            "element across filers using the taxonomy"
        ),
    ),
    ConceptMapping(
        metric_id="debt",
        concept_id=concept_id_for(IFRS_FULL, "LongtermBorrowings"),
        mapping_type=MAPPING_PARTIAL,
        effective_from="2020-12-31",
        notes=(
            "the non-current component of the same composition, and structurally "
            "the same shape as the US-GAAP declaration it sits beside -- which is "
            "the generalisation 2.7 was asked to demonstrate. Window: earliest "
            "reported period for the element across filers using the taxonomy"
        ),
    ),
    # -- 2.9: the seven Core metrics that had no declared concept ---------
    #
    # Each of these was added because 2.8's ledger said the metric held nothing
    # and the registry had no concept to ask the source about. The mapping types
    # are decided against the metric definition and the source definition, and
    # the interesting ones are the ones that are NOT exact.
    #
    # **`ifrs-full:WeightedAverageShares` is declined, not mapped, and that is
    # the finding of this block.** Both IFRS filers in the archive report it, and
    # it is nearly the name of the metric -- but IFRS presents the *basic*
    # weighted-average count as a standard element, and discloses the diluted
    # one in the earnings-per-share note instead. Mapping it would have given
    # every IFRS issuer a diluted share count that is not diluted, and a
    # research question about dilution would have been answered with the basic
    # number and no error anywhere to notice it.
    ConceptMapping(
        metric_id="gross_profit",
        concept_id=concept_id_for(US_GAAP, "GrossProfit"),
        mapping_type=MAPPING_EXACT,
        notes=(
            "revenue less cost of revenue, as presented -- which is the metric's "
            "own definition, in the same words"
        ),
    ),
    ConceptMapping(
        metric_id="gross_profit",
        concept_id=concept_id_for(IFRS_FULL, "GrossProfit"),
        mapping_type=MAPPING_EXACT,
        notes=(
            "the same construct in the second framework: revenue less cost of "
            "sales as presented. The element exists in IFRS filings from a "
            "financial institution, which does not make the metric meaningful "
            "for one -- applicability is a statement about the metric, and a "
            "filer tagging a similarly named element does not change that"
        ),
    ),
    ConceptMapping(
        metric_id="operating_income",
        concept_id=concept_id_for(US_GAAP, "OperatingIncomeLoss"),
        mapping_type=MAPPING_EXACT,
        notes=(
            "operating activities before interest, taxes and non-operating "
            "items, as presented. Declared inapplicable to a financial "
            "institution, where the subtotal is not a construct the framework "
            "provides and these filers report no element for it"
        ),
    ),
    ConceptMapping(
        metric_id="r_and_d",
        concept_id=concept_id_for(US_GAAP, "ResearchAndDevelopmentExpense"),
        mapping_type=MAPPING_EXACT,
        notes=(
            "research and development expense as presented, and the metric is "
            "that line and nothing else"
        ),
    ),
    ConceptMapping(
        metric_id="r_and_d",
        concept_id=concept_id_for(IFRS_FULL, "ResearchAndDevelopmentExpense"),
        mapping_type=MAPPING_EXACT,
        notes=(
            "the same line under the same name in the second framework, which "
            "is a useful result: an IFRS element can be EXACT where an element "
            "of the same name elsewhere is only PARTIAL"
        ),
    ),
    ConceptMapping(
        metric_id="interest_expense",
        concept_id=concept_id_for(US_GAAP, "InterestExpense"),
        mapping_type=MAPPING_EXACT,
        notes="interest incurred on borrowings, as presented, in total",
    ),
    ConceptMapping(
        metric_id="interest_expense",
        concept_id=concept_id_for(US_GAAP, "InterestExpenseDebt"),
        mapping_type=MAPPING_PARTIAL,
        effective_from="2013-06-29",
        notes=(
            "interest on debt specifically, which is one component of total "
            "interest expense. A wider series would splice the two"
        ),
    ),
    ConceptMapping(
        metric_id="interest_expense",
        concept_id=concept_id_for(IFRS_FULL, "InterestExpense"),
        mapping_type=MAPPING_EXACT,
        notes=(
            "interest expense as presented. Kept distinct from FinanceCosts, "
            "which is the wider measure and maps only partially"
        ),
    ),
    ConceptMapping(
        metric_id="interest_expense",
        concept_id=concept_id_for(IFRS_FULL, "FinanceCosts"),
        mapping_type=MAPPING_PARTIAL,
        effective_from="2015-12-31",
        notes=(
            "finance costs may include items other than interest, so the "
            "element is a wider measure than the metric. Mapping it EXACT would "
            "answer 'what did interest cost' with a number that also contains "
            "fair-value and currency movements. Window: earliest reported "
            "period for the element across filers using the taxonomy"
        ),
    ),
    ConceptMapping(
        metric_id="income_tax",
        concept_id=concept_id_for(US_GAAP, "IncomeTaxExpenseBenefit"),
        mapping_type=MAPPING_EXACT,
        notes=(
            "income tax expense on an accrual basis as presented. Distinct "
            "from taxes paid, which is a cash figure and a different question"
        ),
    ),
    ConceptMapping(
        metric_id="income_tax",
        concept_id=concept_id_for(IFRS_FULL, "IncomeTaxExpenseContinuingOperations"),
        mapping_type=MAPPING_PARTIAL,
        effective_from="2015-12-31",
        notes=(
            "the element is scoped to continuing operations, so it is narrower "
            "than 'income tax expense for the period' whenever a filer has "
            "discontinued operations. PARTIAL rather than EXACT for that reason "
            "and not for the framework. Window: earliest reported period across "
            "filers using the taxonomy"
        ),
    ),
    ConceptMapping(
        metric_id="operating_cash_flow",
        concept_id=concept_id_for(
            US_GAAP, "NetCashProvidedByUsedInOperatingActivities"
        ),
        mapping_type=MAPPING_EXACT,
        notes=(
            "net cash from operating activities after non-cash adjustments -- "
            "the same construct under a different element name in each "
            "framework, which is the clearest case in the registry of a metric "
            "being framework-neutral"
        ),
    ),
    ConceptMapping(
        metric_id="operating_cash_flow",
        concept_id=concept_id_for(
            IFRS_FULL, "CashFlowsFromUsedInOperatingActivities"
        ),
        mapping_type=MAPPING_EXACT,
        notes=(
            "the same construct in the second framework; the IFRS element name "
            "reads as the gross flows but the standard element is the net total"
        ),
    ),
    ConceptMapping(
        metric_id="equity",
        concept_id=concept_id_for(US_GAAP, "StockholdersEquity"),
        mapping_type=MAPPING_EXACT,
        notes=(
            "equity attributable to the parent, which is what the metric defines"
        ),
    ),
    ConceptMapping(
        metric_id="equity",
        concept_id=concept_id_for(
            US_GAAP, "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"
        ),
        mapping_type=MAPPING_PARTIAL,
        effective_from="2008-08-28",
        notes=(
            "total equity including non-controlling interests: a wider "
            "aggregate of the metric, and the two differ by exactly the "
            "non-controlling interest. Window: earliest reported period for the "
            "element across filers"
        ),
    ),
    ConceptMapping(
        metric_id="equity",
        concept_id=concept_id_for(IFRS_FULL, "EquityAttributableToOwnersOfParent"),
        mapping_type=MAPPING_EXACT,
        notes=(
            "the IFRS element for the same claim as us-gaap:StockholdersEquity, "
            "which is what makes this metric the cleanest cross-framework EXACT "
            "in the registry"
        ),
    ),
    ConceptMapping(
        metric_id="equity",
        concept_id=concept_id_for(IFRS_FULL, "Equity"),
        mapping_type=MAPPING_PARTIAL,
        effective_from="2014-12-31",
        notes=(
            "total equity including non-controlling interests, a wider "
            "aggregate than the metric. Declared as a component-of-attribution "
            "matter rather than a framework one: TSM reports both elements and "
            "they differ. Window: earliest reported period across filers using "
            "the taxonomy"
        ),
    ),
    ConceptMapping(
        metric_id="weighted_average_diluted_shares",
        concept_id=concept_id_for(
            US_GAAP, "WeightedAverageNumberOfDilutedSharesOutstanding"
        ),
        mapping_type=MAPPING_EXACT,
        notes=(
            "the diluted weighted-average count as the filer computes it for "
            "diluted earnings per share. The basic count is a different "
            "population and is declined rather than mapped"
        ),
    ),
    # -- sga, the last Core metric with no declared concept ----------------
    #
    # The metric's definition names selling, general *and* administrative. The
    # US-GAAP element that matches is the one that says all three; the one that
    # says only general and administrative is a narrower construct, and where a
    # filer reports the narrower one the mapping is PARTIAL. IFRS has no standard
    # element combining the three at all, so an IFRS filer's nearest element
    # covers administration alone.
    ConceptMapping(
        metric_id="sga",
        concept_id=concept_id_for(
            US_GAAP, "SellingGeneralAndAdministrativeExpense"
        ),
        mapping_type=MAPPING_EXACT,
        notes=(
            "selling, general and administrative expenses as presented, which "
            "is the metric's own definition in the same words"
        ),
    ),
    ConceptMapping(
        metric_id="sga",
        concept_id=concept_id_for(US_GAAP, "GeneralAndAdministrativeExpense"),
        mapping_type=MAPPING_PARTIAL,
        effective_from="2007-09-29",
        notes=(
            "general and administrative expenses without selling costs where "
            "the filer reports those separately: a narrower construct than the "
            "metric, and a wider one than administration alone. Window: "
            "earliest reported period for the element across filers"
        ),
    ),
    ConceptMapping(
        metric_id="sga",
        concept_id=concept_id_for(IFRS_FULL, "GeneralAndAdministrativeExpense"),
        mapping_type=MAPPING_PARTIAL,
        effective_from="2015-12-31",
        notes=(
            "IFRS has no standard element combining selling and administrative "
            "costs, so this element is administration alone and the metric is "
            "narrower still. PARTIAL on that basis and not on the framework. "
            "Window: earliest reported period for the element across filers "
            "using the taxonomy"
        ),
    ),
)

# Concepts considered for a metric and declined, with the reason recorded where a
# coverage figure can read it.
#
# Nine of them, and until 2.8 the reasoning lived only in the notes above. A
# reader of the archive could see what ST-EVA held and not what it had considered
# and rejected, which with 3.0% of a filer's concepts collected is most of what
# a coverage claim has to be honest about: "not collected" and "declined on
# purpose" are different sentences and they call for different work.
#
# Recorded as records rather than prose, and each carries a closed reason code
# because the distinction that matters is which *kind* of near-miss it is. A
# component of the metric is a different thing from a wider aggregate of it, and
# from a measure of something else entirely, and a coverage ledger that flattened
# them would lose the only information the record exists to keep.
DECLINES: Tuple[DeclinedConcept, ...] = (
    DeclinedConcept(
        concept_id=concept_id_for(IFRS_FULL, "RevenueFromContractsWithCustomers"),
        considered_for_metric="revenue",
        reason_code=REASON_COMPONENT_OF,
        reason=(
            "A component of ifrs-full:Revenue, not the revenue line. A filer that "
            "reports the two at the same value -- as this one does -- still "
            "presents them as separate lines, and mapping both would put two "
            "figures into one metric for one period with nothing to tell a "
            "reader which the filer actually presented."
        ),
        framework_basis=IFRS_FULL,
    ),
    DeclinedConcept(
        concept_id=concept_id_for(IFRS_FULL, "RevenueFromInterest"),
        considered_for_metric="revenue",
        reason_code=REASON_COMPONENT_OF,
        reason=(
            "Interest income reported inside ordinary-activity revenue. The "
            "metric is the revenue line as presented, and an IFRS element for "
            "one component of it is not that line -- it is the reason the "
            "revenue mapping is PARTIAL rather than EXACT."
        ),
        framework_basis=IFRS_FULL,
    ),
    DeclinedConcept(
        concept_id=concept_id_for(IFRS_FULL, "RevenueFromGovernmentGrants"),
        considered_for_metric="revenue",
        reason_code=REASON_COMPONENT_OF,
        reason=(
            "Government grants inside ordinary-activity revenue. A component of "
            "the revenue line, reported separately by a filer that chooses to."
        ),
        framework_basis=IFRS_FULL,
    ),
    DeclinedConcept(
        concept_id=concept_id_for(IFRS_FULL, "RevenueFromDividends"),
        considered_for_metric="revenue",
        reason_code=REASON_COMPONENT_OF,
        reason=(
            "Dividend income inside ordinary-activity revenue. A component of "
            "the revenue line, on the same reasoning as the interest and grant "
            "elements."
        ),
        framework_basis=IFRS_FULL,
    ),
    DeclinedConcept(
        concept_id=concept_id_for(
            IFRS_FULL, "DilutedEarningsLossPerShareFromContinuingOperations"
        ),
        considered_for_metric="eps_diluted",
        reason_code=REASON_DIFFERENT_QUANTITY,
        reason=(
            "Diluted earnings per share from continuing operations. The metric "
            "is diluted earnings per share for the reporting period with no "
            "such qualifier, so this is a different quantity and mapping it "
            "would put a continuing-operations figure in a total-period field."
        ),
        framework_basis=IFRS_FULL,
    ),
    DeclinedConcept(
        concept_id=concept_id_for(IFRS_FULL, "NumberOfSharesAuthorised"),
        considered_for_metric="shares_outstanding",
        reason_code=REASON_IDENTITY_MISMATCH,
        reason=(
            "Shares authorised. The metric counts shares outstanding, and "
            "authorised is a larger and different population: the gap between "
            "the two is unissued capital, which is a different fact."
        ),
        framework_basis=IFRS_FULL,
    ),
    DeclinedConcept(
        concept_id=concept_id_for(IFRS_FULL, "IssuedCapital"),
        considered_for_metric="shares_outstanding",
        reason_code=REASON_NOT_A_METRIC,
        reason=(
            "A currency amount, not a share count. Declined for share count and "
            "for every other count metric, and it would be easy to mistake for "
            "a share figure because it is reported in the equity statement."
        ),
        framework_basis=IFRS_FULL,
    ),
    DeclinedConcept(
        concept_id=concept_id_for(IFRS_FULL, "LoansAndAdvancesToCustomers"),
        considered_for_metric="revenue",
        reason_code=REASON_NOT_A_METRIC,
        reason=(
            "A financial institution's earning assets. No Core metric declares "
            "them, and they are the balance-sheet side of the business rather "
            "than a measure of revenue; a decline here says the concept is "
            "outside ST-EVA's scope, not that it was overlooked."
        ),
        framework_basis=IFRS_FULL,
    ),
    DeclinedConcept(
        concept_id=concept_id_for(IFRS_FULL, "InterestRevenueExpense"),
        considered_for_metric="revenue",
        reason_code=REASON_DIFFERENT_QUANTITY,
        reason=(
            "Interest income and expense presented as one net line by a "
            "financial institution. The metric is revenue recognised from "
            "ordinary activities as presented, and this element reports a "
            "different thing: interest, net of the cost of it."
        ),
        framework_basis=IFRS_FULL,
    ),
    # -- 2.9: the near misses that had to be declined ---------------------
    #
    # Every one of these was found by reading a candidate and asking whether it
    # measures the same thing. The first is the one that would have been easiest
    # to get wrong and the most damaging if it had been: an element whose name is
    # almost the metric's, reported by every IFRS filer in the archive, and
    # measuring a different population.
    DeclinedConcept(
        concept_id=concept_id_for(IFRS_FULL, "WeightedAverageShares"),
        considered_for_metric="weighted_average_diluted_shares",
        reason_code=REASON_IDENTITY_MISMATCH,
        reason=(
            "Almost the metric's name, and reported by both IFRS filers in the "
            "archive -- but it is the *basic* weighted-average count. IFRS "
            "presents the basic figure as a standard element and discloses the "
            "diluted one in the earnings-per-share note, so there is no standard "
            "element for the diluted count. Mapping this would have given every "
            "IFRS issuer a diluted share count that is not diluted, and a "
            "question about dilution would have been answered with the basic "
            "number and no error anywhere to notice it."
        ),
        framework_basis=IFRS_FULL,
    ),
    DeclinedConcept(
        concept_id=concept_id_for(
            US_GAAP, "WeightedAverageNumberOfSharesOutstandingBasic"
        ),
        considered_for_metric="weighted_average_diluted_shares",
        reason_code=REASON_IDENTITY_MISMATCH,
        reason=(
            "The basic weighted-average count. A different population from the "
            "diluted one by exactly the dilutive instruments, and the filer "
            "reports both side by side, so the difference is visible in the "
            "filing rather than inferable."
        ),
    ),
    DeclinedConcept(
        concept_id=concept_id_for(
            US_GAAP, "WeightedAverageNumberDilutedSharesOutstandingAdjustment"
        ),
        considered_for_metric="weighted_average_diluted_shares",
        reason_code=REASON_COMPONENT_OF,
        reason=(
            "The *adjustment* from the basic to the diluted count -- an "
            "increment, not a count. It is the difference between the two "
            "populations, which is a different quantity from either."
        ),
    ),
    DeclinedConcept(
        concept_id=concept_id_for(US_GAAP, "IncomeTaxesPaidNet"),
        considered_for_metric="income_tax",
        reason_code=REASON_DIFFERENT_QUANTITY,
        reason=(
            "Cash taxes paid during the period, on a cash basis. The metric is "
            "the accrual expense, and the two differ by the movement in tax "
            "payables and by the timing of every payment -- a question about "
            "which one was asked deserves a different answer."
        ),
    ),
    DeclinedConcept(
        concept_id=concept_id_for(
            IFRS_FULL, "IncomeTaxesPaidClassifiedAsOperatingActivities"
        ),
        considered_for_metric="income_tax",
        reason_code=REASON_DIFFERENT_QUANTITY,
        reason=(
            "Cash taxes paid, classified within the cash flow statement. A cash "
            "figure where the metric is an accrual expense, on the same "
            "reasoning as the US-GAAP cash-taxes element."
        ),
        framework_basis=IFRS_FULL,
    ),
    DeclinedConcept(
        concept_id=concept_id_for(US_GAAP, "LiabilitiesAndStockholdersEquity"),
        considered_for_metric="equity",
        reason_code=REASON_NOT_A_METRIC,
        reason=(
            "Total assets. The label contains 'equity' because the accounting "
            "identity is assets = liabilities + equity, and a name search on "
            "equity finds it readily. Mapping it would have reported the "
            "balance sheet's largest number as shareholders' equity, which is "
            "the kind of error no downstream check would catch."
        ),
    ),
    DeclinedConcept(
        concept_id=concept_id_for(IFRS_FULL, "EquityAndLiabilities"),
        considered_for_metric="equity",
        reason_code=REASON_NOT_A_METRIC,
        reason=(
            "Total assets, for the same reason as the US-GAAP element. The two "
            "frameworks even name it differently -- 'liabilities and "
            "stockholders' equity' against 'equity and liabilities' -- and "
            "neither of them means equity."
        ),
        framework_basis=IFRS_FULL,
    ),
    DeclinedConcept(
        concept_id=concept_id_for(
            US_GAAP, "UnrecognizedTaxBenefitsIncomeTaxPenaltiesAndInterestExpense"
        ),
        considered_for_metric="interest_expense",
        reason_code=REASON_NOT_A_METRIC,
        reason=(
            "Interest accrued on tax positions, disclosed in the tax footnote. "
            "It is interest, and it is nothing to do with the interest a "
            "borrower pays, and a name search for interest expense finds it "
            "readily."
        ),
    ),
    DeclinedConcept(
        concept_id=concept_id_for(US_GAAP, "SegmentReportingInformationOperatingIncomeLoss"),
        considered_for_metric="operating_income",
        reason_code=REASON_COMPONENT_OF,
        reason=(
            "Operating income for one reportable segment, not for the entity. "
            "A segment total and a consolidated total are the same *kind* of "
            "number and different quantities, and a series that mixed them "
            "would be a series of parts of a company."
        ),
    ),
    DeclinedConcept(
        concept_id=concept_id_for(US_GAAP, "EquityMethodInvestments"),
        considered_for_metric="equity",
        reason_code=REASON_NOT_A_METRIC,
        reason=(
            "The carrying amount of investments accounted for under the equity "
            "method. A filer whose business is largely joint ventures reports "
            "it as a large share of its balance sheet, so it is the kind of "
            "concept that a name search on 'equity' surfaces and the kind that "
            "must be declined rather than mapped."
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
    declines = 0
    for decline in DECLINES:
        registry.decline_concept_mapping(
            decline.concept_id,
            decline.considered_for_metric,
            decline.reason_code,
            decline.reason,
            decline.framework_basis,
        )
        declines += 1
    return {
        "metrics": len(METRICS),
        "concepts": len(CONCEPTS),
        "mappings": len(MAPPINGS),
        "declines": declines,
    }
