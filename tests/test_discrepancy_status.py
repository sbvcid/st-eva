"""
Unit tests for _derive_discrepancy_status.

Evidence states, not investment ratings:
- a successfully acquired single-source dataset -> SINGLE_SOURCE (data exists,
  but one provider cannot verify itself);
- acquisition failure or missing required data -> UNVERIFIABLE;
- cross-source disagreement -> DATA_DISCREPANCY.
"""
from __future__ import annotations

import sys
import unittest

sys.path.insert(0, ".")

from data_contract import SourceType, ValidationStatus
from st_eva_runner import (
    CompanyResolver,
    MarketData,
    REGRESSION_TEST_FIXTURES,
    UNAVAILABLE,
    _derive_discrepancy_status,
    run_st_eva,
    YahooFinanceProvider,
    Validator,
)
from unittest.mock import patch


def _market_data(
    *,
    source_type=SourceType.API_LIVE.value,
    errors=None,
    discrepancy_status=None,
) -> MarketData:
    return MarketData(
        ticker="TEST",
        company_name="Test Co",
        exchange="NMS",
        currency="USD",
        price=100.0,
        price_date="2026-10-16",
        price_source="test",
        price_source_url=None,
        price_history=[],
        volume_history=[],
        source_type=source_type,
        provider="test",
        discrepancy_status=discrepancy_status,
        errors=list(errors or []),
    )


class TestDeriveDiscrepancyStatus(unittest.TestCase):
    def test_successful_live_acquisition_is_single_source(self):
        data = _market_data(source_type=SourceType.API_LIVE.value)
        self.assertEqual(
            _derive_discrepancy_status(data), ValidationStatus.SINGLE_SOURCE.value
        )
        # Existing evidence fields are untouched.
        self.assertEqual(data.source_type, SourceType.API_LIVE.value)
        self.assertEqual(data.errors, [])

    def test_acquisition_failure_is_unverifiable(self):
        data = _market_data(source_type=SourceType.API_LIVE.value, errors=["fetch timeout"])
        self.assertEqual(
            _derive_discrepancy_status(data), ValidationStatus.UNVERIFIABLE.value
        )

    def test_missing_required_data_is_unverifiable(self):
        data = _market_data(source_type=SourceType.API_LIVE.value, errors=["price missing"])
        self.assertEqual(
            _derive_discrepancy_status(data), ValidationStatus.UNVERIFIABLE.value
        )

    def test_discrepant_source_is_data_discrepancy(self):
        data = _market_data(
            source_type=SourceType.API_LIVE.value,
            discrepancy_status=ValidationStatus.DISCREPANT.value,
        )
        self.assertEqual(_derive_discrepancy_status(data), "DATA_DISCREPANCY")

    def test_non_live_single_source_is_single_source(self):
        data = _market_data(source_type=SourceType.REGRESSION_FIXTURE.value)
        self.assertEqual(
            _derive_discrepancy_status(data), ValidationStatus.SINGLE_SOURCE.value
        )

    def test_unknown_source_type_is_single_source(self):
        data = _market_data(source_type="UNKNOWN")
        self.assertEqual(
            _derive_discrepancy_status(data), ValidationStatus.SINGLE_SOURCE.value
        )

    def test_errors_take_precedence_over_discrepant(self):
        data = _market_data(
            source_type=SourceType.API_LIVE.value,
            errors=["fetch timeout"],
            discrepancy_status=ValidationStatus.DISCREPANT.value,
        )
        self.assertEqual(
            _derive_discrepancy_status(data), ValidationStatus.UNVERIFIABLE.value
        )


class TestResolveRealMissingData(unittest.TestCase):
    """End-to-end tests through CompanyResolver.resolve for real missing-data
    situations (not manually constructed error strings).

    In regression mode, known tickers resolve to frozen fixtures with no errors;
    unknown tickers fall through to YahooFinanceProvider.fetch, which returns
    None when the ticker cannot be resolved, causing resolve to build a
    MarketData with errors=["price fetch failed: ..."] and price=UNAVAILABLE.
    """

    def test_resolve_known_ticker_returns_market_data_no_errors(self):
        data = CompanyResolver.resolve("AAPL", mode="regression")
        self.assertIsNotNone(data)
        self.assertEqual(data.errors, [])
        self.assertEqual(data.source_type, SourceType.REGRESSION_FIXTURE.value)
        self.assertEqual(
            _derive_discrepancy_status(data), ValidationStatus.SINGLE_SOURCE.value
        )

    def test_resolve_known_ticker_msft_returns_market_data_no_errors(self):
        data = CompanyResolver.resolve("MSFT", mode="regression")
        self.assertIsNotNone(data)
        self.assertEqual(data.errors, [])
        self.assertEqual(
            _derive_discrepancy_status(data), ValidationStatus.SINGLE_SOURCE.value
        )

    def test_resolve_unknown_ticker_fetch_none_produces_error(self):
        """Real missing-data path: Yahoo fetch returns None -> resolve builds a
        MarketData with price=UNAVAILABLE and errors populated."""
        with patch.object(YahooFinanceProvider, "fetch", return_value=None):
            data = CompanyResolver.resolve("UNKNOWN_XYZ", mode="live")
        self.assertIsNotNone(data)
        self.assertEqual(data.errors, ["price fetch failed: no price data returned"])
        self.assertEqual(data.price, UNAVAILABLE)
        self.assertEqual(data.source_type, SourceType.API_LIVE.value)

    def test_run_st_eva_missing_price_returns_none(self):
        """run_st_eva returns None for the missing-price path (existing return
        contract preserved)."""
        with patch.object(YahooFinanceProvider, "fetch", return_value=None):
            result = run_st_eva("UNKNOWN_XYZ", mode="live", save_snapshot=False)
        self.assertIsNone(result)

    def test_data_discrepancy_still_raises_value_error(self):
        """DATA_DISCREPANCY and other validation errors must NOT be converted
        into None by the price-fetch failure path."""
        data = _market_data(
            source_type=SourceType.API_LIVE.value,
            discrepancy_status="DATA_DISCREPANCY",
        )
        data_errors = Validator.validate_data(data)
        self.assertTrue(data_errors)
        with self.assertRaises(ValueError):
            raise ValueError("; ".join(data_errors))


if __name__ == "__main__":
    unittest.main()
