"""Unit tests for JustETFClient — targets 100% line/branch coverage of just_etf_client.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests
from bs4 import BeautifulSoup

from finances_data.just_etf import JustETFClient, JustETFScrapeError
from data.models import ETFDetails


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(status: int, text: str = "", headers: dict | None = None) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.text = text
    r.headers = headers or {}
    return r


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client() -> JustETFClient:
    return JustETFClient(timeout=5.0, max_retries=2)


@pytest.fixture
def full_html() -> str:
    """HTML that exercises all successful parsing paths.

    Metadata lines must be unindented so that get_text(separator='\\n', strip=True)
    produces 'Key\\nValue' pairs that match the client's regexes exactly.
    """
    return (
        "<html><body>"
        "<div id='key-facts'>"
        "Inception Date\n22 May 2012\n"
        "Replication\nPhysical (Full replication)\n"
        "Distribution policy\nDistributing\n"
        "Index\nFTSE All-World\n"
        "Fund currency\nUSD\n"
        "Fund size\nEUR 23,794 m\n"
        "Holdings\n3,797\n"
        "Volatility 1 year\n10.96 %\n"
        "</div>"
        "<table><tr><th>TER</th><td>Total Expense Ratio: 0.14 %</td></tr></table>"
        "<tr data-testid='top-holdings_row_0'>"
        "<td><a href='/en/etf-profile.html?isin=US67066G1040'>NVIDIA Corp.</a></td>"
        "<td>5.01 %</td></tr>"
        "<tr data-testid='top-holdings_row_1'>"
        "<td><a href='/en/etf-profile.html?isin=US0378331005'>Apple Inc.</a></td>"
        "<td>4.52 %</td></tr>"
        "<tr data-testid='sector_row_0'><td>Technology</td><td>38.27 %</td></tr>"
        "<tr data-testid='sector_row_1'><td>Finance</td><td>17.87 %</td></tr>"
        "<tr data-testid='country_row_0'><td>United States</td><td>60.33 %</td></tr>"
        "<tr data-testid='country_row_1'><td>Japan</td><td>6.04 %</td></tr>"
        "</body></html>"
    )


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def test_client_initialises_defaults() -> None:
    c = JustETFClient()
    assert c.timeout == 10.0
    assert c.session is not None


def test_client_initialises_custom_params() -> None:
    c = JustETFClient(timeout=5.0, max_retries=2)
    assert c.timeout == 5.0


# ---------------------------------------------------------------------------
# get_etf_details — happy path
# ---------------------------------------------------------------------------

@patch("requests.Session.get")
def test_get_etf_details_success(mock_get: MagicMock, client: JustETFClient, full_html: str) -> None:
    mock_get.return_value = _make_response(200, full_html)

    details: ETFDetails = client.get_etf_details("IE00B3RBWM25")

    assert isinstance(details, ETFDetails)
    assert details.ter_pct == 0.14
    assert details.inception_date == "22 May 2012"
    assert details.fund_size_eur_m == 23794.0
    assert details.holdings_count == 3797
    assert details.replication == "Physical (Full replication)"
    assert details.distribution_policy == "Distributing"
    assert details.index_name == "FTSE All-World"
    assert details.fund_currency == "USD"
    assert details.volatility_1y_pct == 10.96

    assert len(details.holdings) == 2
    assert details.holdings[0].name == "NVIDIA Corp."
    assert details.holdings[0].isin == "US67066G1040"
    assert details.holdings[0].weight_pct == 5.01
    assert details.holdings[1].name == "Apple Inc."
    assert details.holdings[1].isin == "US0378331005"

    assert len(details.sector_breakdown) == 2
    assert details.sector_breakdown[0].sector_name == "Technology"
    assert details.sector_breakdown[0].weight_pct == 38.27

    assert len(details.country_breakdown) == 2
    assert details.country_breakdown[0].country_name == "United States"
    assert details.country_breakdown[0].weight_pct == 60.33


# ---------------------------------------------------------------------------
# get_etf_details — HTTP / network errors
# ---------------------------------------------------------------------------

@patch("requests.Session.get")
def test_get_etf_details_http_error(mock_get: MagicMock, client: JustETFClient) -> None:
    mock_get.return_value = _make_response(404)
    with pytest.raises(JustETFScrapeError, match="HTTP error 404"):
        client.get_etf_details("INVALID")


@patch("requests.Session.get")
def test_get_etf_details_500_error(mock_get: MagicMock, client: JustETFClient) -> None:
    mock_get.return_value = _make_response(500)
    with pytest.raises(JustETFScrapeError, match="HTTP error 500"):
        client.get_etf_details("IE00B3RBWM25")


@patch("requests.Session.get")
def test_get_etf_details_request_exception(mock_get: MagicMock, client: JustETFClient) -> None:
    mock_get.side_effect = requests.RequestException("timeout")
    with pytest.raises(JustETFScrapeError, match="Network error fetching JustETF page"):
        client.get_etf_details("IE00B3RBWM25")


# ---------------------------------------------------------------------------
# get_etf_details — 429 rate-limit + retry
# ---------------------------------------------------------------------------

@patch("time.sleep", return_value=None)
@patch("requests.Session.get")
def test_rate_limit_retry_with_header(mock_get: MagicMock, mock_sleep: MagicMock, client: JustETFClient, full_html: str) -> None:
    mock_get.side_effect = [
        _make_response(429, headers={"Retry-After": "2"}),
        _make_response(200, full_html),
    ]
    details = client.get_etf_details("IE00B3RBWM25")
    assert isinstance(details, ETFDetails)
    assert mock_get.call_count == 2
    mock_sleep.assert_called_once_with(2)


@patch("time.sleep", return_value=None)
@patch("requests.Session.get")
def test_rate_limit_retry_without_header_defaults_60(mock_get: MagicMock, mock_sleep: MagicMock, client: JustETFClient, full_html: str) -> None:
    """When Retry-After header is absent the client sleeps 60 seconds."""
    mock_get.side_effect = [
        _make_response(429, headers={}),
        _make_response(200, full_html),
    ]
    client.get_etf_details("IE00B3RBWM25")
    mock_sleep.assert_called_once_with(60)


@patch("time.sleep", return_value=None)
@patch("requests.Session.get")
def test_rate_limit_then_non_200(mock_get: MagicMock, mock_sleep: MagicMock, client: JustETFClient) -> None:
    """429 followed by another non-200 still raises JustETFScrapeError."""
    mock_get.side_effect = [
        _make_response(429, headers={"Retry-After": "1"}),
        _make_response(503),
    ]
    with pytest.raises(JustETFScrapeError, match="HTTP error 503"):
        client.get_etf_details("IE00B3RBWM25")


# ---------------------------------------------------------------------------
# get_etf_details — parse failure path
# ---------------------------------------------------------------------------

@patch("requests.Session.get")
def test_parse_failure_wrapped(mock_get: MagicMock, client: JustETFClient) -> None:
    mock_get.return_value = _make_response(200, "<html><body></body></html>")
    with patch.object(client, "_parse_holdings", side_effect=Exception("DOM Corrupt")):
        with pytest.raises(JustETFScrapeError, match="Failed to parse JustETF response"):
            client.get_etf_details("IE00B3RBWM25")


@patch("requests.Session.get")
def test_justetf_scrape_error_propagates(mock_get: MagicMock, client: JustETFClient) -> None:
    """JustETFScrapeError raised inside the parse block is re-raised as-is."""
    mock_get.return_value = _make_response(200, "<html><body></body></html>")
    with patch.object(client, "_parse_holdings", side_effect=JustETFScrapeError("inner")):
        with pytest.raises(JustETFScrapeError, match="inner"):
            client.get_etf_details("IE00B3RBWM25")


# ---------------------------------------------------------------------------
# _parse_fund_metadata
# ---------------------------------------------------------------------------

def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def test_parse_fund_metadata_full(client: JustETFClient, full_html: str) -> None:
    meta = client._parse_fund_metadata(_soup(full_html))
    assert meta["inception_date"] == "22 May 2012"
    assert meta["replication"] == "Physical (Full replication)"
    assert meta["distribution_policy"] == "Distributing"
    assert meta["index_name"] == "FTSE All-World"
    assert meta["fund_currency"] == "USD"
    assert meta["fund_size_eur_m"] == 23794.0
    assert meta["holdings_count"] == 3797
    assert meta["volatility_1y_pct"] == 10.96


def test_parse_fund_metadata_empty(client: JustETFClient) -> None:
    meta = client._parse_fund_metadata(_soup("<html><body></body></html>"))
    assert meta == {}


def test_parse_fund_metadata_inception_date_skips_non_date(client: JustETFClient) -> None:
    """inception_date must contain a 4-digit year; non-date strings are skipped."""
    html = "<html><body>Inception Date\nPhysical replication\n</body></html>"
    meta = client._parse_fund_metadata(_soup(html))
    assert "inception_date" not in meta


def test_parse_fund_metadata_holdings_out_of_fallback(client: JustETFClient) -> None:
    """'out of N' pattern covers the fallback holdings_count branch."""
    html = "<html><body>Showing top 10 out of 3,500 holdings\n</body></html>"
    meta = client._parse_fund_metadata(_soup(html))
    assert meta["holdings_count"] == 3500


def test_parse_fund_metadata_volatility_comma_decimal(client: JustETFClient) -> None:
    html = "<html><body>Volatility 1 year\n12,34 %\n</body></html>"
    meta = client._parse_fund_metadata(_soup(html))
    assert meta["volatility_1y_pct"] == pytest.approx(12.34)


# ---------------------------------------------------------------------------
# _parse_ter
# ---------------------------------------------------------------------------

def test_parse_ter_from_dom(client: JustETFClient) -> None:
    html = "<table><tr><th>TER</th><td>0.14 %</td></tr></table>"
    assert client._parse_ter(_soup(html)) == pytest.approx(0.14)


def test_parse_ter_from_full_label(client: JustETFClient) -> None:
    html = "<p>Total Expense Ratio: 0.20 %</p>"
    assert client._parse_ter(_soup(html)) == pytest.approx(0.20)


def test_parse_ter_global_fallback(client: JustETFClient) -> None:
    """When DOM traversal finds no match the global text fallback is used."""
    html = "<html><body>TER 0.07 %</body></html>"
    assert client._parse_ter(_soup(html)) == pytest.approx(0.07)


def test_parse_ter_none_when_absent(client: JustETFClient) -> None:
    assert client._parse_ter(_soup("<html><body>nothing here</body></html>")) is None


def test_parse_ter_comma_decimal(client: JustETFClient) -> None:
    html = "<p>TER 0,22 %</p>"
    assert client._parse_ter(_soup(html)) == pytest.approx(0.22)


def test_parse_ter_parent_has_no_grandparent(client: JustETFClient) -> None:
    """TER label whose parent is the root element (no grandparent) still parses."""
    html = "<TER>TER 0.10 %</TER>"
    assert client._parse_ter(_soup(html)) == pytest.approx(0.10)


def test_parse_ter_fallback_when_dom_traversal_finds_no_number(client: JustETFClient) -> None:
    """DOM traversal finds label but no %-number; global text fallback kicks in."""
    html = "<p>TER info only</p><body>Total Expense Ratio 0.33 %</body>"
    assert client._parse_ter(_soup(html)) == pytest.approx(0.33)


# ---------------------------------------------------------------------------
# _extract_isin_from_element
# ---------------------------------------------------------------------------

def test_extract_isin_from_href(client: JustETFClient) -> None:
    soup = _soup('<tr><td><a href="/etf?isin=IE00B3RBWM25">Vanguard</a></td></tr>')
    row = soup.find("tr")
    assert client._extract_isin_from_element(row) == "IE00B3RBWM25"


def test_extract_isin_from_anchor_directly(client: JustETFClient) -> None:
    soup = _soup('<a href="/etf?isin=US67066G1040">NVIDIA</a>')
    anchor = soup.find("a")
    assert client._extract_isin_from_element(anchor) == "US67066G1040"


def test_extract_isin_from_raw_text(client: JustETFClient) -> None:
    """Falls back to raw element text when no anchor href contains an ISIN."""
    soup = _soup("<td>US0378331005 Apple</td>")
    td = soup.find("td")
    assert client._extract_isin_from_element(td) == "US0378331005"


def test_extract_isin_returns_empty_when_none(client: JustETFClient) -> None:
    assert client._extract_isin_from_element(None) == ""


def test_extract_isin_returns_empty_when_no_isin(client: JustETFClient) -> None:
    soup = _soup("<tr><td>No ISIN here</td></tr>")
    assert client._extract_isin_from_element(soup.find("tr")) == ""


# ---------------------------------------------------------------------------
# _parse_holdings — fallback strategies
# ---------------------------------------------------------------------------

def test_parse_holdings_via_data_testid(client: JustETFClient, full_html: str) -> None:
    holdings = client._parse_holdings(_soup(full_html))
    assert len(holdings) == 2
    assert holdings[0].isin == "US67066G1040"


def test_parse_holdings_via_table_id_fallback(client: JustETFClient) -> None:
    html = """
    <table id="top-holdings">
        <tr><td><a href="?isin=FR0010959676">Amundi ETF</a></td><td>3.50 %</td></tr>
    </table>
    """
    holdings = client._parse_holdings(_soup(html))
    assert len(holdings) == 1
    assert holdings[0].isin == "FR0010959676"
    assert holdings[0].weight_pct == pytest.approx(3.50)


def test_parse_holdings_via_generic_table_fallback(client: JustETFClient) -> None:
    html = """
    <table>
        <tr><th>Top Holdings</th><th>Weight</th></tr>
        <tr><td><a href="?isin=IE00BKM4GZ66">iShares Core</a></td><td>2.10 %</td></tr>
    </table>
    """
    holdings = client._parse_holdings(_soup(html))
    assert len(holdings) == 1
    assert holdings[0].isin == "IE00BKM4GZ66"


def test_parse_holdings_skips_header_rows(client: JustETFClient) -> None:
    html = """
    <table id="top-holdings">
        <tr><th>Name</th><th>Weight</th></tr>
        <tr><td><a href="?isin=IE00B3RBWM25">Vanguard FTSE</a></td><td>1.00 %</td></tr>
    </table>
    """
    holdings = client._parse_holdings(_soup(html))
    assert all(h.name != "Name" for h in holdings)


def test_parse_holdings_skips_rows_without_isin(client: JustETFClient) -> None:
    html = """
    <tr data-testid="top-holdings_row_0">
        <td>No ISIN row</td><td>1.00 %</td>
    </tr>
    """
    holdings = client._parse_holdings(_soup(html))
    assert holdings == []


def test_parse_holdings_skips_rows_without_percentage(client: JustETFClient) -> None:
    html = """
    <tr data-testid="top-holdings_row_0">
        <td><a href="?isin=US67066G1040">NVIDIA</a></td><td>not a percent</td>
    </tr>
    """
    holdings = client._parse_holdings(_soup(html))
    assert holdings == []


def test_parse_holdings_returns_empty_on_no_tables(client: JustETFClient) -> None:
    holdings = client._parse_holdings(_soup("<html><body></body></html>"))
    assert holdings == []


# ---------------------------------------------------------------------------
# _parse_sectors — fallback strategies
# ---------------------------------------------------------------------------

def test_parse_sectors_via_data_testid(client: JustETFClient, full_html: str) -> None:
    sectors = client._parse_sectors(_soup(full_html))
    assert len(sectors) == 2
    assert sectors[0].sector_name == "Technology"


def test_parse_sectors_via_div_id_fallback(client: JustETFClient) -> None:
    html = """
    <div id="sectors">
        <tr><td>Healthcare</td><td>12.00 %</td></tr>
    </div>
    """
    sectors = client._parse_sectors(_soup(html))
    assert len(sectors) == 1
    assert sectors[0].sector_name == "Healthcare"


def test_parse_sectors_via_generic_table_fallback(client: JustETFClient) -> None:
    html = """
    <table>
        <tr><th>Sector</th><th>Weight</th></tr>
        <tr><td>Energy</td><td>5.50 %</td></tr>
    </table>
    """
    sectors = client._parse_sectors(_soup(html))
    assert len(sectors) == 1
    assert sectors[0].sector_name == "Energy"


def test_parse_sectors_skips_header_rows(client: JustETFClient) -> None:
    html = """
    <div id="sectors">
        <tr><td>Sector Breakdown</td><td>100 %</td></tr>
        <tr><td>Industrials</td><td>10.00 %</td></tr>
    </div>
    """
    sectors = client._parse_sectors(_soup(html))
    assert all(s.sector_name != "Sector Breakdown" for s in sectors)


def test_parse_sectors_returns_empty_on_no_match(client: JustETFClient) -> None:
    assert client._parse_sectors(_soup("<html><body></body></html>")) == []


def test_parse_sectors_skips_rows_without_percentage(client: JustETFClient) -> None:
    html = """
    <tr data-testid="sector_row_0"><td>Technology</td><td>no percent</td></tr>
    """
    assert client._parse_sectors(_soup(html)) == []


# ---------------------------------------------------------------------------
# _parse_countries — fallback strategies
# ---------------------------------------------------------------------------

def test_parse_countries_via_data_testid(client: JustETFClient, full_html: str) -> None:
    countries = client._parse_countries(_soup(full_html))
    assert len(countries) == 2
    assert countries[0].country_name == "United States"


def test_parse_countries_via_div_id_fallback(client: JustETFClient) -> None:
    html = """
    <div id="countries">
        <tr><td>Germany</td><td>8.00 %</td></tr>
    </div>
    """
    countries = client._parse_countries(_soup(html))
    assert len(countries) == 1
    assert countries[0].country_name == "Germany"


def test_parse_countries_via_generic_table_fallback(client: JustETFClient) -> None:
    html = """
    <table>
        <tr><th>Countries</th><th>Weight</th></tr>
        <tr><td>France</td><td>4.50 %</td></tr>
    </table>
    """
    countries = client._parse_countries(_soup(html))
    assert len(countries) == 1
    assert countries[0].country_name == "France"


def test_parse_countries_via_region_table_fallback(client: JustETFClient) -> None:
    html = """
    <table>
        <tr><th>Region</th><th>Weight</th></tr>
        <tr><td>Asia Pacific</td><td>20.00 %</td></tr>
    </table>
    """
    countries = client._parse_countries(_soup(html))
    assert len(countries) == 1
    assert countries[0].country_name == "Asia Pacific"


def test_parse_countries_skips_header_rows(client: JustETFClient) -> None:
    html = """
    <div id="countries">
        <tr><td>Country Breakdown</td><td>100 %</td></tr>
        <tr><td>United Kingdom</td><td>5.00 %</td></tr>
    </div>
    """
    countries = client._parse_countries(_soup(html))
    assert all(c.country_name != "Country Breakdown" for c in countries)


def test_parse_countries_returns_empty_on_no_match(client: JustETFClient) -> None:
    assert client._parse_countries(_soup("<html><body></body></html>")) == []


def test_parse_countries_skips_rows_without_percentage(client: JustETFClient) -> None:
    html = """
    <tr data-testid="country_row_0"><td>Spain</td><td>no percent</td></tr>
    """
    assert client._parse_countries(_soup(html)) == []


# ---------------------------------------------------------------------------
# End-to-end: empty HTML returns ETFDetails with empty lists
# ---------------------------------------------------------------------------

@patch("requests.Session.get")
def test_empty_html_returns_empty_details(mock_get: MagicMock, client: JustETFClient) -> None:
    mock_get.return_value = _make_response(200, "<html><body></body></html>")
    details = client.get_etf_details("IE00B3RBWM25")
    assert details.holdings == []
    assert details.sector_breakdown == []
    assert details.country_breakdown == []
    assert details.ter_pct is None