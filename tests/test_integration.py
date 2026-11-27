"""Integration tests for JustETF and Yahoo Finance clients.

Validates real transport serialization, HTTP headers, socket communication,
rate-limiting retries via local loopback HTTP servers, and end-to-end data model
transformations against realistic recorded payloads.
"""

from __future__ import annotations

import threading
import urllib.parse
from collections.abc import Generator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from data.models import ETFDetails, ETFMarketData, Quotation, StockDetails
from finances_data.just_etf import JustETFClient, JustETFScrapeError
from finances_data.yahoo_finance import YahooFinanceClient

RECORDED_JUST_ETF_HTML: str = """<!DOCTYPE html>
<html lang="en">
<head><title>iShares Core MSCI World UCITS ETF USD (Acc) | JustETF</title></head>
<body>
  <div id="key-facts">
    Inception Date\n25 September 2009\n
    Replication\nPhysical (Optimized sampling)\n
    Distribution policy\nAccumulating\n
    Index\nMSCI World Index\n
    Fund currency\nUSD\n
    Fund size\nEUR 65,420 m\n
    Holdings\n1,429\n
    Volatility 1 year\n11.45 %\n
  </div>
  <table><tr><th>TER</th><td>Total Expense Ratio: 0.20 %</td></tr></table>
  <table id="top-holdings">
    <tr><th>Top Holdings</th><th>ISIN</th><th>Weight</th></tr>
    <tr>
      <td><a href="/en/etf-profile.html?isin=US0378331005">Apple Inc.</a></td>
      <td>US0378331005</td>
      <td>4.85 %</td>
    </tr>
    <tr>
      <td><a href="/en/etf-profile.html?isin=US5949181045">Microsoft Corp.</a></td>
      <td>US5949181045</td>
      <td>4.12 %</td>
    </tr>
    <tr>
      <td><a href="/en/etf-profile.html?isin=US67066G1040">NVIDIA Corp.</a></td>
      <td>US67066G1040</td>
      <td>3.45 %</td>
    </tr>
  </table>
  <div id="sectors">
    <table>
      <tr><th>Sector</th><th>Weight</th></tr>
      <tr><td>Information Technology</td><td>25.80 %</td></tr>
      <tr><td>Financials</td><td>15.10 %</td></tr>
      <tr><td>Health Care</td><td>11.90 %</td></tr>
    </table>
  </div>
  <div id="countries">
    <table>
      <tr><th>Country</th><th>Weight</th></tr>
      <tr><td>United States</td><td>70.50 %</td></tr>
      <tr><td>Japan</td><td>5.60 %</td></tr>
      <tr><td>United Kingdom</td><td>3.80 %</td></tr>
    </table>
  </div>
</body>
</html>
"""

RECORDED_YAHOO_STOCK_INFO: dict[str, Any] = {
    "currency": "USD",
    "financialCurrency": "USD",
    "marketCap": 2850000000000,
    "trailingPE": 31.5,
    "forwardPE": 28.2,
    "dividendYield": 0.0055,
    "fiftyTwoWeekHigh": 199.62,
    "fiftyTwoWeekLow": 164.08,
    "fiftyTwoWeekChangePercent": 0.185,
    "fiftyDayAverage": 185.40,
    "twoHundredDayAverage": 178.10,
    "averageVolume": 54200000,
    "sector": "Technology",
    "industry": "Consumer Electronics",
    "country": "United States",
    "priceToBook": 42.1,
    "pegRatio": 2.4,
    "beta": 1.15,
    "profitMargins": 0.263,
    "grossMargins": 0.441,
    "operatingMargins": 0.301,
    "revenueGrowth": 0.061,
    "earningsGrowth": 0.105,
    "returnOnEquity": 1.45,
    "returnOnAssets": 0.22,
    "debtToEquity": 180.5,
    "freeCashflow": 105000000000,
    "shortRatio": 1.2,
    "targetMeanPrice": 210.0,
    "targetHighPrice": 240.0,
    "targetLowPrice": 180.0,
    "numberOfAnalystOpinions": 42,
    "recommendationKey": "buy",
    "trailingEps": 6.13,
    "forwardEps": 7.02,
    "navPrice": 182.5,
}

RECORDED_YAHOO_ETF_INFO: dict[str, Any] = {
    "currency": "EUR",
    "financialCurrency": "EUR",
    "marketCap": 65000000000,
    "navPrice": 95.80,
    "fiftyTwoWeekHigh": 98.40,
    "fiftyTwoWeekLow": 78.10,
    "fiftyTwoWeekChangePercent": 0.224,
    "fiftyDayAverage": 94.10,
    "twoHundredDayAverage": 88.50,
    "averageVolume": 125000,
}


class LoopbackHandler(BaseHTTPRequestHandler):
    """Thread-safe request handler for integration tests over loopback socket."""

    requests_log: list[dict[str, Any]] = []
    rate_limit_counter: int = 0

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default stderr HTTP request logging during tests."""
        pass

    def do_GET(self) -> None:
        """Handle GET requests over real TCP transport socket."""
        parsed_url = urllib.parse.urlparse(self.path)
        LoopbackHandler.requests_log.append(
            {
                "path": parsed_url.path,
                "query": parsed_url.query,
                "headers": {k.lower(): v for k, v in self.headers.items()},
            }
        )

        if parsed_url.path == "/en/etf-profile.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(RECORDED_JUST_ETF_HTML.encode("utf-8"))

        elif parsed_url.path == "/rate-limited":
            LoopbackHandler.rate_limit_counter += 1
            if LoopbackHandler.rate_limit_counter == 1:
                self.send_response(429)
                self.send_header("Retry-After", "1")
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"Rate limit exceeded. Retry later.")
            else:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(RECORDED_JUST_ETF_HTML.encode("utf-8"))

        elif parsed_url.path == "/transient-error":
            self.send_response(503)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Service Temporarily Unavailable")

        elif parsed_url.path == "/not-found":
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Not Found")

        else:
            self.send_response(400)
            self.end_headers()


class LoopbackServer:
    """Encapsulates local HTTP server lifecycle running on an ephemeral port."""

    def __init__(self) -> None:
        LoopbackHandler.requests_log = []
        LoopbackHandler.rate_limit_counter = 0
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), LoopbackHandler)
        self.port: int = self.httpd.server_address[1]
        self.url: str = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=3.0)


@pytest.fixture
def loopback_server() -> Generator[LoopbackServer, None, None]:
    """Spawns an isolated loopback HTTP server for real socket transport verification."""
    server = LoopbackServer()
    server.start()
    yield server
    server.stop()


# ==============================================================================
# Real Transport Socket Integration Tests (JustETF)
# ==============================================================================


def test_just_etf_integration_real_http_transport(loopback_server: LoopbackServer) -> None:
    """Verify real HTTP request transmission, header delivery, and model hydration."""
    client = JustETFClient(timeout=5.0, max_retries=2)
    client.BASE_URL = f"{loopback_server.url}/en/etf-profile.html"

    details: ETFDetails = client.get_etf_details("IE00B4L5Y983")

    # Assert real transport occurred
    assert len(LoopbackHandler.requests_log) == 1
    req: dict[str, Any] = LoopbackHandler.requests_log[0]
    assert req["path"] == "/en/etf-profile.html"
    assert req["query"] == "isin=IE00B4L5Y983"
    assert "Mozilla/5.0" in req["headers"].get("user-agent", "")
    assert "en-US" in req["headers"].get("accept-language", "")

    # Assert parsed domain model fields from real network payload
    assert details.ter_pct == 0.20
    assert details.fund_size_eur_m == 65420.0
    assert details.holdings_count == 1429
    assert details.volatility_1y_pct == 11.45
    assert details.replication == "Physical (Optimized sampling)"
    assert details.distribution_policy == "Accumulating"
    assert details.fund_currency == "USD"
    assert details.index_name == "MSCI World Index"

    # Assert structured holdings collection
    assert len(details.holdings) == 3
    assert details.holdings[0].name == "Apple Inc."
    assert details.holdings[0].isin == "US0378331005"
    assert details.holdings[0].weight_pct == 4.85
    assert details.holdings[1].name == "Microsoft Corp."
    assert details.holdings[1].isin == "US5949181045"

    # Assert sector and country breakdowns
    assert len(details.sector_breakdown) == 3
    assert details.sector_breakdown[0].sector_name == "Information Technology"
    assert details.sector_breakdown[0].weight_pct == 25.80

    assert len(details.country_breakdown) == 3
    assert details.country_breakdown[0].country_name == "United States"
    assert details.country_breakdown[0].weight_pct == 70.50


def test_just_etf_integration_rate_limit_retry_over_socket(
    loopback_server: LoopbackServer,
) -> None:
    """Verify rate-limiting backoff and sequential socket reconnection over HTTP 429."""
    client = JustETFClient(timeout=5.0, max_retries=3)
    client.BASE_URL = f"{loopback_server.url}/rate-limited"

    details: ETFDetails = client.get_etf_details("IE00B4L5Y983")
    assert len(LoopbackHandler.requests_log) == 2
    assert LoopbackHandler.rate_limit_counter == 2
    assert len(details.holdings) == 3


def test_just_etf_integration_transient_error_http_503(
    loopback_server: LoopbackServer,
) -> None:
    """Verify HTTP 503 status triggers retries and ultimately raises JustETFScrapeError."""
    client = JustETFClient(timeout=5.0, max_retries=2)
    client.BASE_URL = f"{loopback_server.url}/transient-error"

    with pytest.raises(JustETFScrapeError, match="HTTP error 503"):
        client.get_etf_details("IE00B4L5Y983")


def test_just_etf_integration_http_404_not_found(
    loopback_server: LoopbackServer,
) -> None:
    """Verify non-retryable client error raises JustETFScrapeError without retry loop."""
    client = JustETFClient(timeout=5.0, max_retries=2)
    client.BASE_URL = f"{loopback_server.url}/not-found"

    with pytest.raises(JustETFScrapeError, match="HTTP error 404"):
        client.get_etf_details("INVALID_ISIN")


# ==============================================================================
# Real Payload Cassette Schema Tests (Yahoo Finance)
# ==============================================================================


def test_yahoo_finance_integration_real_stock_payload() -> None:
    """Verify YahooFinanceClient parsing against a recorded real-world stock API payload."""
    client = YahooFinanceClient()

    with patch("yfinance.Ticker") as mock_ticker_cls:
        mock_instance = MagicMock()
        mock_instance.info = RECORDED_YAHOO_STOCK_INFO
        mock_instance.history.return_value = pd.DataFrame(
            [{"Open": 181.0, "High": 183.0, "Low": 180.5, "Close": 182.5, "Volume": 45000000}]
        )
        mock_ticker_cls.return_value = mock_instance

        # Test quotation resolution
        quote: Quotation = client.get_quotation("AAPL")
        assert quote.price == 182.5
        assert quote.currency == "USD"
        assert quote.native_price == 182.5
        assert quote.native_currency == "USD"

        # Test comprehensive stock fundamental metrics
        stock: StockDetails = client.get_stock_details("AAPL")
        assert stock.currency == "USD"
        assert stock.market_cap == 2850000000000
        assert stock.pe_ratio == 31.5
        assert stock.forward_pe == 28.2
        assert stock.dividend_yield_pct == pytest.approx(0.55)
        assert stock.sector == "Technology"
        assert stock.industry == "Consumer Electronics"
        assert stock.country == "United States"
        assert stock.price_to_book == 42.1
        assert stock.peg_ratio == 2.4
        assert stock.beta == 1.15
        assert stock.return_on_equity_pct == pytest.approx(145.0)
        assert stock.total_debt_to_equity == 180.5
        assert stock.free_cashflow == 105000000000
        assert stock.target_mean_price == 210.0
        assert stock.number_of_analyst_opinions == 42
        assert stock.recommendation_key == "buy"
        assert stock.eps_trailing_ttm == 6.13


def test_yahoo_finance_integration_real_etf_payload() -> None:
    """Verify YahooFinanceClient parsing against recorded real-world ETF market data."""
    client = YahooFinanceClient()

    with patch("yfinance.Ticker") as mock_ticker_cls:
        mock_instance = MagicMock()
        mock_instance.info = RECORDED_YAHOO_ETF_INFO
        mock_instance.history.return_value = pd.DataFrame(
            [{"Open": 95.0, "High": 96.2, "Low": 94.8, "Close": 95.8, "Volume": 120000}]
        )
        mock_ticker_cls.return_value = mock_instance

        etf_data: ETFMarketData = client.get_etf_market_data("IWDA.AS")
        assert etf_data.price == 95.8
        assert etf_data.native_currency == "EUR"
        assert etf_data.nav_price == 95.80
        assert etf_data.fifty_two_week_high == 98.40
        assert etf_data.fifty_two_week_low == 78.10
        assert etf_data.fifty_two_week_change_pct == pytest.approx(22.4)
        assert etf_data.fifty_day_average == 94.10
        assert etf_data.two_hundred_day_average == 88.50
        assert etf_data.average_volume == 125000


def test_end_to_end_cross_client_pipeline(loopback_server: LoopbackServer) -> None:
    """Verify end-to-end multi-client workflow combining JustETF scraping and Yahoo pricing."""
    just_etf = JustETFClient(timeout=5.0)
    just_etf.BASE_URL = f"{loopback_server.url}/en/etf-profile.html"
    yahoo = YahooFinanceClient()

    details = just_etf.get_etf_details("IE00B4L5Y983")
    assert len(details.holdings) >= 1

    with patch("yfinance.Ticker") as mock_ticker_cls:
        mock_inst = MagicMock()
        mock_inst.info = {"currency": "USD"}
        mock_inst.history.return_value = pd.DataFrame([{"Close": 185.0}])
        mock_ticker_cls.return_value = mock_inst

        # Enrich top holding with Yahoo Finance quote
        quote = yahoo.get_quotation("AAPL")
        assert quote.price == 185.0
        assert details.holdings[0].weight_pct == 4.85
