from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock
import pandas as pd
import pytest

from finances_data.yahoo_finance import YahooFinanceClient, YahooFinanceError
from data.models import Quotation, StockDetails, ETFMarketData


@patch("yfinance.Ticker")
def test_get_quotation_success(mock_ticker: MagicMock) -> None:
    instance = MagicMock()
    instance.info = {"currency": "USD"}
    instance.history.return_value = pd.DataFrame([{"Close": 182.50}])
    mock_ticker.return_value = instance

    client = YahooFinanceClient()
    quote = client.get_quotation("AAPL")

    assert isinstance(quote, Quotation)
    assert quote.price == 182.50
    assert quote.currency == "USD"
    assert quote.native_price == 182.50
    assert quote.native_currency == "USD"


@patch("yfinance.Ticker")
def test_get_quotation_empty_history_raises_error(mock_ticker: MagicMock) -> None:
    instance = MagicMock()
    instance.info = {"currency": "USD"}
    instance.history.return_value = pd.DataFrame()
    mock_ticker.return_value = instance

    client = YahooFinanceClient()
    with pytest.raises(YahooFinanceError, match="No price history returned"):
        client.get_quotation("INVALID")


@patch("yfinance.Ticker")
def test_get_quotation_missing_close_price(mock_ticker: MagicMock) -> None:
    instance = MagicMock()
    instance.info = {"currency": "USD"}
    instance.history.return_value = pd.DataFrame([{"Open": 100.0}])
    mock_ticker.return_value = instance

    client = YahooFinanceClient()
    with pytest.raises(YahooFinanceError, match="Invalid or missing close price"):
        client.get_quotation("AAPL")


@patch("yfinance.Ticker")
def test_get_quotation_missing_currency(mock_ticker: MagicMock) -> None:
    instance = MagicMock()
    instance.info = {}
    instance.history.return_value = pd.DataFrame([{"Close": 100.0}])
    mock_ticker.return_value = instance

    client = YahooFinanceClient()
    with pytest.raises(YahooFinanceError, match="Currency information is missing"):
        client.get_quotation("AAPL")


@patch("yfinance.Ticker")
def test_get_info_exception_wrapped(mock_ticker: MagicMock) -> None:
    instance = MagicMock()
    type(instance).info = PropertyMock(side_effect=Exception("Network down"))
    mock_ticker.return_value = instance

    client = YahooFinanceClient()
    with pytest.raises(YahooFinanceError, match="Failed to retrieve info"):
        client.get_quotation("AAPL")


@patch("yfinance.Ticker")
def test_general_fetch_exception_wrapped(mock_ticker: MagicMock) -> None:
    mock_ticker.side_effect = Exception("Crash")

    client = YahooFinanceClient()
    with pytest.raises(YahooFinanceError, match="Failed to fetch market data"):
        client.get_quotation("AAPL")


@patch("yfinance.Ticker")
def test_get_stock_details_success(mock_ticker: MagicMock) -> None:
    instance = MagicMock()
    instance.info = {
        "marketCap": 3_000_000_000,
        "trailingPE": 28.5,
        "forwardPE": 25.0,
        "dividendYield": 0.0055,
        "fiftyTwoWeekHigh": 190.0,
        "fiftyTwoWeekLow": 130.0,
        "52WeekChange": 0.152,
        "fiftyDayAverage": 180.0,
        "twoHundredDayAverage": 170.0,
        "averageVolume": 50000000,
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "country": "United States",
        "priceToBook": 10.5,
        "pegRatio": 2.0,
        "beta": 1.2,
        "profitMargins": 0.2345,
        "grossMargins": 0.45,
        "operatingMargins": 0.30,
        "revenueGrowth": 0.08,
        "earningsGrowth": 0.10,
        "returnOnEquity": 0.40,
        "returnOnAssets": 0.20,
        "debtToEquity": 1.5,
        "freeCashflow": 1000000000,
        "shortRatio": 2.1,
        "targetMeanPrice": 200.0,
        "targetHighPrice": 220.0,
        "targetLowPrice": 160.0,
        "numberOfAnalystOpinions": 30,
        "recommendationKey": "buy",
        "trailingEps": 6.5,
        "forwardEps": 7.0,
        "currency": "USD",
    }
    mock_ticker.return_value = instance

    client = YahooFinanceClient()
    stock: StockDetails = client.get_stock_details("AAPL")

    assert stock.market_cap == 3_000_000_000.0
    assert stock.dividend_yield_pct == pytest.approx(0.55)
    assert stock.profit_margins_pct == pytest.approx(23.45)
    assert stock.fifty_two_week_change_pct == pytest.approx(15.2)
    assert stock.sector == "Technology"
    assert stock.currency == "USD"
    assert stock.pe_ratio == pytest.approx(28.5)
    assert stock.forward_pe == pytest.approx(25.0)
    assert stock.fifty_two_week_high == pytest.approx(190.0)
    assert stock.fifty_two_week_low == pytest.approx(130.0)
    assert stock.fifty_day_average == pytest.approx(180.0)
    assert stock.two_hundred_day_average == pytest.approx(170.0)
    assert stock.average_volume == 50_000_000
    assert stock.industry == "Consumer Electronics"
    assert stock.country == "United States"
    assert stock.price_to_book == pytest.approx(10.5)
    assert stock.peg_ratio == pytest.approx(2.0)
    assert stock.beta == pytest.approx(1.2)
    assert stock.gross_margins_pct == pytest.approx(45.0)
    assert stock.operating_margins_pct == pytest.approx(30.0)
    assert stock.revenue_growth_pct == pytest.approx(8.0)
    assert stock.earnings_growth_pct == pytest.approx(10.0)
    assert stock.return_on_equity_pct == pytest.approx(40.0)
    assert stock.return_on_assets_pct == pytest.approx(20.0)
    assert stock.total_debt_to_equity == pytest.approx(1.5)
    assert stock.free_cashflow == pytest.approx(1_000_000_000.0)
    assert stock.short_ratio == pytest.approx(2.1)
    assert stock.target_mean_price == pytest.approx(200.0)
    assert stock.target_high_price == pytest.approx(220.0)
    assert stock.target_low_price == pytest.approx(160.0)
    assert stock.number_of_analyst_opinions == 30
    assert stock.recommendation_key == "buy"
    assert stock.eps_trailing_ttm == pytest.approx(6.5)
    assert stock.eps_forward == pytest.approx(7.0)


@patch("yfinance.Ticker")
def test_get_stock_details_exception(mock_ticker: MagicMock) -> None:
    instance = MagicMock()
    type(instance).info = PropertyMock(side_effect=Exception("Fail"))
    mock_ticker.return_value = instance

    client = YahooFinanceClient()
    with pytest.raises(YahooFinanceError, match="Failed to retrieve info"):
        client.get_stock_details("AAPL")


@patch("yfinance.Ticker")
def test_get_etf_market_data_success(mock_ticker: MagicMock) -> None:
    instance = MagicMock()
    instance.info = {
        "currency": "EUR",
        "navPrice": 102.5,
        "fiftyTwoWeekHigh": 110.0,
        "fiftyTwoWeekLow": 90.0,
        "52WeekChange": 0.12,
        "fiftyDayAverage": 101.0,
        "twoHundredDayAverage": 98.0,
        "averageVolume": 50000,
    }
    instance.history.return_value = pd.DataFrame([{"Close": 103.5}])
    mock_ticker.return_value = instance

    client = YahooFinanceClient()
    etf: ETFMarketData = client.get_etf_market_data("VWCE.DE")

    assert etf.price == 103.5
    assert etf.native_currency == "EUR"
    assert etf.nav_price == 102.5
    assert etf.fifty_two_week_change_pct == pytest.approx(12.0)
    assert etf.average_volume == 50000


@patch("yfinance.Ticker")
def test_get_etf_market_data_exception(mock_ticker: MagicMock) -> None:
    mock_ticker.side_effect = Exception("Fail")
    client = YahooFinanceClient()
    with pytest.raises(YahooFinanceError, match="Failed to fetch market data"):
        client.get_etf_market_data("VWCE.DE")


@patch("yfinance.Ticker")
def test_get_stock_details_fifty_two_week_fallback(mock_ticker: MagicMock) -> None:
    """When '52WeekChange' is absent, fiftyTwoWeekChangePercent is used instead."""
    instance = MagicMock()
    instance.info = {
        "fiftyTwoWeekChangePercent": 0.25,
        "currency": "USD",
    }
    mock_ticker.return_value = instance

    client = YahooFinanceClient()
    stock = client.get_stock_details("MSFT")
    assert stock.fifty_two_week_change_pct == pytest.approx(25.0)


@patch("yfinance.Ticker")
def test_get_etf_market_data_fifty_two_week_fallback(mock_ticker: MagicMock) -> None:
    """When '52WeekChange' is absent in ETF data, fiftyTwoWeekChangePercent is used."""
    instance = MagicMock()
    instance.info = {
        "currency": "EUR",
        "fiftyTwoWeekChangePercent": 0.10,
    }
    instance.history.return_value = pd.DataFrame([{"Close": 100.0}])
    mock_ticker.return_value = instance

    client = YahooFinanceClient()
    etf = client.get_etf_market_data("IWDA.AS")
    assert etf.fifty_two_week_change_pct == pytest.approx(10.0)


@patch("yfinance.Ticker")
def test_get_stock_details_outer_exception_wrapped(mock_ticker: MagicMock) -> None:
    """Non-YahooFinanceError raised after info fetch is wrapped into YahooFinanceError."""
    instance = MagicMock()
    instance.info = {"currency": "USD"}
    # Cause an unexpected exception when building StockDetails by making info.get crash
    instance.info = MagicMock()
    instance.info.get = MagicMock(side_effect=RuntimeError("unexpected"))
    mock_ticker.return_value = instance

    client = YahooFinanceClient()
    with pytest.raises(YahooFinanceError, match="Failed to fetch stock details"):
        client.get_stock_details("AAPL")


def test_safe_float_helpers() -> None:
    from finances_data.yahoo_finance.yahoo_finance_client import _safe_float, _safe_int, _safe_str

    assert _safe_float("not_a_float") is None
    assert _safe_float([1, 2, 3]) is None
    assert _safe_float(None) is None
    assert _safe_float("") is None
    assert _safe_float("2.5") == pytest.approx(2.5)
    assert _safe_float("2.5", scale=100.0) == pytest.approx(250.0)

    assert _safe_int("not_an_int") is None
    assert _safe_int("") is None
    assert _safe_int(None) is None
    assert _safe_int("42") == 42

    assert _safe_str("   ") is None
    assert _safe_str("") is None
    assert _safe_str(None) is None
    assert _safe_str("  hello  ") == "hello"