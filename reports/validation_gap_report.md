# Software Quality Assurance & Test Engineering Assessment Report

**Repository Target:** `finances-data`  
**Execution Environment:** macOS (Darwin) | Python 3.13.0 | `pytest-9.1.1` | `pytest-cov-7.1.0`  
**Current Test Metrics:** 49 Passed | 0 Failed | 84% Total Line Coverage (356 Stmts, 58 Missed)

---

## 1. Executive Summary

An analysis of the test execution results and the codebase reveals a critical testing dichotomy:
1. **Module Imbalance:** `finances_data/just_etf/just_etf_client.py` has high synthetic test coverage (94%), while **`finances_data/yahoo_finance` has 0% coverage (untested)**, and `data/models.py` has **29% uncovered logic** (46 statements missed), primarily in factory methods (`from_dict`) and conversion helpers.
2. **Missing Boundary & Integration Verification:** The current test suite relies heavily on mocked, clean HTML strings. It lacks testing against messy real-world HTML structures, network flakes, rate-limit exhaustion, and upstream API changes from Yahoo Finance.
3. **Static Contract Drift:** `COUNTRY_ALIASES` in `data/common/constants.py` is disconnected from `_parse_countries()`, leaving unnormalized country labels without enforcement.

---

## 2. Evaluation Across the 5 Validation Pillars

| Pillar | Status | Score | Diagnostic Summary |
| :--- | :---: | :---: | :--- |
| **1. Unit Tests** | ⚠️ Partial | **B-** | Thorough DOM permutation tests for `just_etf_client.py`. However, `yahoo_finance_client.py` is completely unexercised, and `data/models.py` deserialization paths are untested. |
| **2. Integration Tests** | ❌ Deficient | **F** | All HTTP transactions are patched via `unittest.mock.patch`. Zero integration tests exist using VCR/cassettes or live sandbox endpoints for either JustETF or Yahoo Finance. |
| **3. Static Code Analysis** | ⚠️ At Risk | **C+** | Strict typing annotations exist in model declarations (`slots=True, frozen=True`), but extensive `Any` typings in `yahoo_finance_client.py` bypass type safety during dataframe extraction. |
| **4. Mutation Readiness** | ❌ Weak | **D** | Heavy use of `contextlib.suppress(ValueError)` and generic exception swallowing allows mutant code (e.g., regex boundary changes, numeric scaling errors) to survive undetected. |
| **5. Black-Box / Functional** | ⚠️ Minimal | **D+** | Synthetic canary script `yahoo_health_check.py` provides smoke coverage for `IWDA.AS`, but lacks automated execution in CI, negative assertions, or an equivalent for JustETF. |

---

### Pillar 1: Unit Testing

#### Current Coverage:
* `finances_data/just_etf/just_etf_client.py`: 94% coverage (185/197 statements).
* `data/models.py`: 71% coverage (110/156 statements).
* `finances_data/yahoo_finance/yahoo_finance_client.py`: **0% coverage (0/118 statements)**.

#### Gaps & Deficiencies:
* **Yahoo Finance Client completely skipped:** Methods `_fetch_ticker_market_data`, `get_quotation`, `get_stock_details`, and `get_etf_market_data` are not exercised in the test suite.
* **Uncovered Model Factory Logic:** `from_dict()` methods in `Holding`, `SectorExposure`, `CountryExposure`, `ETFMarketData`, and `ETFDetails` contain validation branches (`ValueError`, `KeyError`) and fallbacks (`_get_float`, `_get_int`, `_get_str`) that are completely unhit (lines 20, 24–30, 34–40, 44–47, 81–88, 108–113, 131–138, etc.).
* **Uncovered JustETF Parsing Branches:**
  * Lines 251–252: `except ValueError: continue` inside holdings weight parser.
  * Lines 310–311: `except ValueError: continue` inside sector weight parser.
  * Lines 375–376: `except ValueError: continue` inside country weight parser.
  * Lines 404–405, 415–418: Float conversion exception handling in DOM and text fallback TER parsers.

---

### Pillar 2: Integration Testing

#### Current Coverage:
* None. All network requests in `test_just_etf.py` are intercepted at `requests.Session.get`.

#### Gaps & Deficiencies:
* **Synthetic DOM Bias:** The HTML snippets used in tests are simplified fragments (`<tr><td>...</td></tr>`). Real JustETF responses contain nested wrapper `div`s, script tags, cookie banners, tracking scripts, and obfuscated/minified layouts that are never validated.
* **No Yahoo Finance Contract Tests:** `yfinance` is a reverse-engineered wrapper over Yahoo's internal JSON endpoints. Without recorded contract tests or cassette replays, upstream API schema shifts will break the application undetected.
* **Session Lifecycle Verification:** There is no verification that `requests.Session` properly reuses TCP connections across successive `get_etf_details()` requests.

---

### Pillar 3: Static Code Analysis (Type Safety & Linting)

#### Current Coverage:
* Modern Python 3.10+ typing (`from __future__ import annotations`, `str | None`, `slots=True`, `frozen=True`).

#### Gaps & Deficiencies:
* **Type Erasure via `Any` in Yahoo Finance Client:**
  ```python
  history: Any = t.history(period="1d")
  latest_row: Any = history.iloc[-1]
  ```
  Pandas DataFrame and Series typing is completely bypassed with `Any`, preventing Mypy from verifying `.iloc[-1]` or `.get("Close")`.
* **String Conversion Blind Spots:**
  `str(link.get("href", ""))` in `_extract_isin_from_element`: In `BeautifulSoup`, multi-valued attributes or missing attributes can return `list[str]` or `None`, which string casting masks rather than handling explicitly.
* **Unenforced Schema Constraints:**
  `Holding(weight_pct=...)` allows negative percentages or values exceeding 100.0 without triggering static validation or runtime invariant errors.

---

### Pillar 4: Mutation Testing Readiness

#### Current Coverage:
* If run through `mutmut` or `cosmic-ray`, the test suite would exhibit a high mutant survival rate in boundary and fallback paths.

#### Gaps & Deficiencies:
* **Swallowed Conversions (`contextlib.suppress(ValueError)`):**
  In `_parse_fund_metadata`:
  ```python
  if fs_match:
      with contextlib.suppress(ValueError):
          meta["fund_size_eur_m"] = float(fs_match.group(1).replace(",", ""))
  ```
  Mutating `float(...)` to `None` or altering regex replacement logic survives because no test passes a malformed numeric format that explicitly triggers the suppressed block while verifying fallback state integrity.
* **Weak Assertion Depth:**
  Tests like `test_parse_sectors_via_div_id_fallback` only assert:
  ```python
  assert len(sectors) == 1
  assert sectors[0].sector_name == "Healthcare"
  ```
  It fails to assert `sectors[0].weight_pct == pytest.approx(12.0)`, allowing mutations in weight extraction to survive.
* **Fallback Short-Circuit Mutations:**
  In `_parse_holdings`, if the primary selector matches, fallback paths are skipped. Mutations in secondary (`table#top-holdings`) and tertiary (`generic table`) extraction loops are only tested through isolated artificial fragments rather than against real DOM structures that contain multiple conflicting tables.

---

### Pillar 5: Black-Box / Functional Verification

#### Current Coverage:
* `scripts/yahoo_health_check.py`: Smoke checks `IWDA.AS` via `YahooFinanceClient().get_quotation("IWDA.AS")`.

#### Gaps & Deficiencies:
* **No Functional Canary for JustETF:** There is no CLI or standalone script to run live end-to-end extraction on a representative set of ISINs (e.g., Equity ETF `IE00B3RBWM25`, Bond ETF `IE00B4L5ZY03`, Commodity ETF `DE000A0S9GB0`).
* **Unvalidated Domain Integrations:** No test runs the pipeline end-to-end: Extracting an ISIN with `JustETFClient`, fetching pricing via `YahooFinanceClient`, and parsing results into `ETFDetails` and `ETFMarketData`.
* **Unhandled Real-World HTTP 429 Scenarios:** `test_rate_limit_retry_with_header` tests a single 429 followed by a 200. It does not test retry exhaustion (exceeding `max_retries`) or backoff escalation when `Retry-After` is missing.

---

## 3. High-Priority Testing Gaps & Missing Edge Cases

### 1. `finances_data/yahoo_finance/yahoo_finance_client.py`
* **Zero test coverage.** Needs a full test suite mocking `yfinance.Ticker`:
  * Valid stock fundamentals parsing (`get_stock_details`).
  * Empty history DataFrame handling (`history.empty` raising `YahooFinanceError`).
  * Missing currency handling (`currency_str is None` raising `YahooFinanceError`).
  * ETF parsing (`get_etf_market_data`), specifically testing the documented bug where `52WeekChange` vs `fiftyTwoWeekChangePercent` returns `None`.
  * Multiplier precision (`scale=100.0` for `dividend_yield_pct`, margins, and growth metrics).

### 2. `data/models.py`
* **Zero unit tests for serialization / deserialization:**
  * Mandatory field omissions: `Holding.from_dict` without `"isin"`, `"name"`, or `"weight_pct"`.
  * `SectorExposure.from_dict` and `CountryExposure.from_dict` validation checks.
  * `DictAccessMixin` tests verifying `obj["key"]` lookup and `AttributeError` / `KeyError` propagation.
  * Roundtrip integrity: `assert ETFDetails.from_dict(details.to_dict()) == details`.

### 3. `finances_data/just_etf/just_etf_client.py`
* **Missing edge-case tests:**
  * Inception date formats without years (e.g., `"TBD"`, `"N/A"`).
  * Out-of-bounds weight percentages (`"105.00 %"`, `"-5.00 %"`).
  * German/European number formats (`"1.234,56 m"` vs `"1,234.56 m"`).
  * Missing or malformed `Retry-After` headers containing strings instead of integers.
  * HTML with multiple tables where the holding table is preceded by advertising or disclaimer tables.

---

## 4. Concrete Remediation & Test Implementation Plan

### Step 1: Create `test/test_models.py`
Implement complete unit validation for `data/models.py` covering serialization, edge cases, and missing field errors:

```python
import pytest
from data.models import Holding, SectorExposure, CountryExposure, ETFDetails, Quotation

def test_holding_from_dict_validation() -> None:
    # Missing isin
    with pytest.raises(ValueError, match="missing mandatory property 'isin'"):
        Holding.from_dict({"name": "Apple", "weight_pct": 5.0})
    
    # Missing name
    with pytest.raises(ValueError, match="missing mandatory property 'name'"):
        Holding.from_dict({"isin": "US0378331005", "weight_pct": 5.0})
        
    # Missing weight_pct key
    with pytest.raises(KeyError, match="missing mandatory key 'weight_pct'"):
        Holding.from_dict({"isin": "US0378331005", "name": "Apple"})

def test_dict_access_mixin() -> None:
    h = Holding(name="Apple", isin="US0378331005", weight_pct=5.0)
    assert h["name"] == "Apple"
    assert h["isin"] == "US0378331005"
    with pytest.raises(AttributeError):
        _ = h["non_existent"]

def test_etf_details_roundtrip() -> None:
    details = ETFDetails(
        holdings=[Holding(name="Test", isin="US0000000000", weight_pct=100.0)],
        sector_breakdown=[SectorExposure(sector_name="Tech", weight_pct=100.0)],
        country_breakdown=[CountryExposure(country_name="USA", weight_pct=100.0)],
        ter_pct=0.20,
    )
    dumped = details.to_dict()
    restored = ETFDetails.from_dict(dumped)
    assert restored.ter_pct == details.ter_pct
    assert len(restored.holdings) == 1
    assert restored.holdings[0].isin == "US0000000000"
```

### Step 2: Create `test/test_yahoo_finance.py`
Implement complete unit test coverage for `YahooFinanceClient` using `unittest.mock`:

```python
from unittest.mock import MagicMock, patch
import pandas as pd
import pytest
from finances_data.yahoo_finance import YahooFinanceClient, YahooFinanceError

@patch("yfinance.Ticker")
def test_get_quotation_success(mock_ticker: MagicMock) -> None:
    mock_instance = MagicMock()
    mock_instance.info = {"currency": "USD"}
    df = pd.DataFrame([{"Close": 150.25}])
    mock_instance.history.return_value = df
    mock_ticker.return_value = mock_instance

    client = YahooFinanceClient()
    quote = client.get_quotation("AAPL")
    assert quote.price == 150.25
    assert quote.currency == "USD"
    assert quote.native_currency == "USD"

@patch("yfinance.Ticker")
def test_get_quotation_empty_history_raises(mock_ticker: MagicMock) -> None:
    mock_instance = MagicMock()
    mock_instance.info = {"currency": "USD"}
    mock_instance.history.return_value = pd.DataFrame()
    mock_ticker.return_value = mock_instance

    client = YahooFinanceClient()
    with pytest.raises(YahooFinanceError, match="No price history returned"):
        client.get_quotation("INVALID")

@patch("yfinance.Ticker")
def test_get_stock_details_scaling(mock_ticker: MagicMock) -> None:
    mock_instance = MagicMock()
    mock_instance.info = {
        "marketCap": 2000000000,
        "trailingPE": 25.5,
        "dividendYield": 0.015,
        "profitMargins": 0.205,
    }
    mock_ticker.return_value = mock_instance

    client = YahooFinanceClient()
    details = client.get_stock_details("AAPL")
    assert details.market_cap == 2000000000.0
    assert details.dividend_yield_pct == pytest.approx(1.5)
    assert details.profit_margins_pct == pytest.approx(20.5)
```

### Step 3: Fill Remaining Uncovered Lines in `just_etf_client.py`
Add explicit tests in `test/test_just_etf.py` to trigger the suppressed/handled exceptions on lines 251–252, 310–311, 375–376, 404–405, and 415–418:

```python
def test_parse_holdings_invalid_float_conversion(client: JustETFClient) -> None:
    html = """
    <tr data-testid="top-holdings_row_0">
        <td><a href="?isin=US67066G1040">NVIDIA</a></td>
        <td>invalid_pct %</td>
    </tr>
    """
    assert client._parse_holdings(_soup(html)) == []

def test_parse_sectors_invalid_float_conversion(client: JustETFClient) -> None:
    html = '<tr data-testid="sector_row_0"><td>Tech</td><td>NaN %</td></tr>'
    assert client._parse_sectors(_soup(html)) == []

def test_parse_countries_invalid_float_conversion(client: JustETFClient) -> None:
    html = '<tr data-testid="country_row_0"><td>USA</td><td>... %</td></tr>'
    assert client._parse_countries(_soup(html)) == []

def test_parse_ter_invalid_float_conversion(client: JustETFClient) -> None:
    html = "<table><tr><th>TER</th><td>invalid %</td></tr></table>"
    assert client._parse_ter(_soup(html)) is None
```

### Step 4: Add Integration Cassette Recording (`pytest-recording` / `vcrpy`)
1. Configure `vcrpy` in `test/conftest.py` with secret sanitization.
2. Record real response payloads from JustETF profile endpoints (`IE00B3RBWM25`, `IE00B4L5ZY03`) and Yahoo Finance ticker endpoints.
3. Add a nightly or scheduled CI step that executes tests in replay mode and flags DOM drift when cassettes are invalidated.

### Step 5: Enforce Quality Gates in CI
Update `pyproject.toml` and CI pipeline:
```toml
[tool.pytest.ini_options]
addopts = "--strict-markers --cov=finances_data --cov=data --cov-report=term-missing --cov-fail-under=95"

[tool.mypy]
strict = true
disallow_untyped_defs = true
disallow_any_generics = true
```