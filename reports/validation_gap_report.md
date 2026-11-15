# Software Quality Assurance & Verification Assessment Report

**Target Repository:** `finances-data`  
**Execution Environment:** macOS (Darwin) | Python 3.13.0 | `pytest-9.1.1` | `pytest-cov-7.1.0`  
**Current Test Metrics:** 78 Passed | 0 Failed | **100% Line Coverage (956/956 statements across source and tests)** | Execution time: 0.86s

---

## 1. Executive Summary

An audit of the test suite and repository source code indicates that previous coverage gaps have been closed at the unit level. The test suite achieves **100% statement coverage** across all modules (`data.models`, `finances_data.just_etf`, `finances_data.yahoo_finance`, and `data.common.constants`), with 78 unit tests executing in under one second.

The country alias dictionary in `data/common/constants.py` is integrated into `_parse_countries()`, all fields of `StockDetails` are explicitly asserted in `test_yahoo_finance.py`, and the model deserializers (`from_dict` and conversion helpers) have dedicated unit tests.

However, from an end-to-end reliability and software verification perspective, **100% line coverage does not imply zero defect risk**:
1. **Total Isolation from Upstream Schemas (Zero Integration Tests):** All 78 tests execute against synthetic HTML strings or mocked `unittest.mock` objects. Neither JustETF scraping nor `yfinance` network extraction is tested against live network contracts, serialized HTTP cassettes (VCR), or recorded real-world DOM snapshots.
2. **Web Scraping Fragility & Canary Asymmetry:** `scripts/yahoo_health_check.py` monitors Yahoo Finance against live markets via `yahoo_bot.yml`, but `just_etf_bot.yml` only runs the mocked unit tests (`test/test_just_etf.py`). There is no live canary or black-box health check for JustETF, leaving changes in JustETF's DOM structure undetected until runtime consumption.
3. **Mutation Testing Vulnerabilities in Exception Suppression:** While `contextlib.suppress(ValueError)` was removed from weight parsers, it remains in `_parse_fund_metadata` for `fund_size_eur_m`, `holdings_count`, and `volatility_1y_pct`. Numeric parsing mutations could survive without strict mutation verification.

---

## 2. Evaluation Across the 5 Validation Pillars

| Validation Pillar | Status | Grade | Diagnostic Summary |
|---|:---:|:---:|---|
| **1. Unit Tests** | 🟢 Saturated Coverage | **A** | 78 tests covering 100% of lines and branches. Explicit coverage of fallback cascades, error wrapping, type validations, and all 34 fields in `StockDetails`. |
| **2. Integration Tests** | 🔴 Non-Existent | **F** | Zero integration tests. All transport layers (`requests.Session.get`, `yfinance.Ticker`) are intercepted with `unittest.mock`. No VCR or contract replay mechanisms exist. |
| **3. Static Code Analysis** | 🟢 Solid | **A-** | Python 3.10+ typing (`slots=True, frozen=True`, union syntax). `COUNTRY_ALIASES` normalization is integrated into `_parse_countries`. Remaining risk: `Any` typing on Pandas DataFrame extraction in `yahoo_finance_client.py`. |
| **4. Mutation Testing Readiness** | 🟡 Moderate Resilience | **B** | Greatly improved assertion depth. However, metadata parsing uses `contextlib.suppress(ValueError)`, and HTML table fallback tests use minimal snippets rather than full nested DOM trees with decoy tables. |
| **5. Black-Box / Functional** | 🟠 Partial / Asymmetric | **C-** | `scripts/yahoo_health_check.py` validates `quote.price > 0.0` and currency presence on schedule, but no live black-box canary exists for `JustETFClient`. |

---

### Pillar 1: Unit Testing

#### Current Status
* **100% Line Coverage** (956 / 956 statements across production code and test files).
* Execution speed: 0.86 seconds for 78 tests.
* `test_just_etf.py` exercises:
  * 3-level fallback parsing for holdings, sectors, and countries.
  * 429 rate-limiting with explicit `Retry-After` headers and fallback defaults (60s).
  * Country alias normalization for aliases such as `"USA"` and `"UK"`.
  * Malformed DOM structures, missing percentage labels, and missing ISIN anchors.
* `test_yahoo_finance.py` exercises:
  * Missing close price, empty history dataframe, missing currency, and wrapped exceptions.
  * All 34 attributes in `StockDetails`.
  * Fallbacks between `52WeekChange` and `fiftyTwoWeekChangePercent` across stocks and ETFs.
  * Edge cases in private conversion helpers (`_safe_float`, `_safe_int`, `_safe_str`).
* `test_models.py` exercises:
  * Missing mandatory keys (`isin`, `name`, `weight_pct`, `sector_name`, `country_name`).
  * Roundtrip serialization (`to_dict` -> `from_dict`).
  * `DictAccessMixin` behavior and lookup errors.

---

### Pillar 2: Integration Testing

#### Current Status: 0% Coverage
Every call to external APIs and websites is intercepted using `unittest.mock.patch`:
* `requests.Session.get` in `test_just_etf.py`.
* `yfinance.Ticker` in `test_yahoo_finance.py`.

#### Vulnerabilities:
1. **JustETF DOM Schema Invalidation:** Scrapers break when websites adjust their class names, table IDs, nesting structures, or bot-mitigation policies (e.g., Cloudflare challenges). Because all unit tests supply clean, isolated HTML fragments, any change to JustETF's real DOM structure will not be caught by CI.
2. **`yfinance` API Drift:** `yfinance` wraps Yahoo Finance internal endpoints without official SLAs. Key names change frequently (e.g., the historical mismatch between `52WeekChange` and `fiftyTwoWeekChangePercent`). Without recorded HTTP cassette tests, upstream breaking changes bypass the test suite.
3. **Session Transport Properties:** TCP connection pooling, retry adapters (`HTTPAdapter`), and custom headers (`User-Agent`) are never validated against an active HTTP server stack.

---

### Pillar 3: Static Code Analysis (Type Safety & Linting)

#### Current Status: Clean
* Domain models use `@dataclass(frozen=True, slots=True)` preventing attribute injection and maintaining immutability.
* Ruff and Mypy (strict) are configured in `pyproject.toml`.
* `COUNTRY_ALIASES` in `data/common/constants.py` is actively imported and used in `finances_data/just_etf/just_etf_client.py:382`.

#### Remaining Risks:
1. **Pandas Type Erasure in `yahoo_finance_client.py`:**
   ```python
   history: Any = t.history(period="1d")
   latest_row: Any = history.iloc[-1]
   price: float | None = _safe_float(latest_row.get("Close"))
   ```
   Using `Any` circumvents Mypy's type checker, preventing detection of breaking changes in future Pandas major versions (e.g., deprecation of `.get()` on `pd.Series`).
2. **Semantic Bounds Invariants:**
   `Holding(weight_pct=-50.0)` and `SectorExposure(weight_pct=150.0)` are valid according to type checkers, but are invalid in financial domain logic.

---

### Pillar 4: Mutation Testing Readiness

#### Current Status: Solid Baseline, Targeted Residual Mutation Risks
The suite asserts exact values across all fields in `StockDetails`, validates percentage calculations, and verifies regex fallback paths.

#### Residual Mutant Survivability Areas:
1. **Suppressed Metadata Conversions:**
   In `_parse_fund_metadata`:
   ```python
   fs_match = re.search(r"Fund size\s*\n?EUR\s*([\d,]+)\s*m", text)
   if fs_match:
       with contextlib.suppress(ValueError):
           meta["fund_size_eur_m"] = float(fs_match.group(1).replace(",", ""))
   ```
   If a mutant modifies the replacement logic `replace(",", "")` to a no-op, or swaps `float(...)` to return a constant, the exception is swallowed silently if conversion fails.
2. **Synthetic DOM Isolation vs. Conflicting Decoy Tables:**
   Fallback tests provide HTML containing *only* the target fallback table. If an HTML document contains an irrelevant table *preceding* the target table, the heuristic loop:
   ```python
   if ("top holdings" in header_text or "holding" in header_text) and "sector" not in header_text:
   ```
   could lock onto a decoy table. Mutating the ordering or filtering logic would not be caught by existing single-table test fixtures.

---

### Pillar 5: Black-Box / Functional Verification

#### Current Status: Asymmetrical
* **Yahoo Finance:** Has an operational canary in `scripts/yahoo_health_check.py` triggered weekly via `.github/workflows/yahoo_bot.yml`, asserting that `IWDA.AS` yields a quote where `price > 0.0` and `currency` is present.
* **JustETF:** **Has no functional or live smoke canary.** `.github/workflows/just_etf_bot.yml` runs only mocked unit tests. If JustETF updates its anti-scraping logic or DOM structure, CI remains green while actual scraping fails in production.

---

## 3. High-Priority Testing Gaps & Missing Edge Cases

### Gap 1: Absence of Recorded Integration Cassettes (VCR)
Neither client is verified against actual recorded responses from JustETF or Yahoo Finance. Real HTML responses contain megabytes of minified JavaScript, tracking scripts, and complex DOM hierarchies that behave differently from short synthetic snippets.

### Gap 2: Missing JustETF Functional Live Canary
`TODO.md` notes that workflows should run on Thursdays. While Yahoo Finance runs on Mondays, JustETF lacks any scheduled live smoke check to detect DOM drift.

### Gap 3: Domain Invariant Bounds
Model factory methods (`from_dict`) do not validate whether `weight_pct` is bounded within `0.0 <= weight_pct <= 100.0`, allowing invalid portfolio states to be instantiated.

---

## 4. Concrete Remediation & Test Implementation Plan

### Step 1: Implement Recorded Integration Replays (VCR.py / `pytest-recording`)

Add `pytest-recording` to dependencies and configure cassette replays against real-world assets:

```python
# test/test_integration_contracts.py
import pytest
from finances_data.just_etf import JustETFClient
from finances_data.yahoo_finance import YahooFinanceClient

@pytest.mark.vcr
def test_just_etf_real_dom_contract() -> None:
    """Verifies parsing against a recorded, real-world JustETF profile page."""
    client = JustETFClient()
    # Vanguard FTSE All-World UCITS ETF (USD) Accumulating
    details = client.get_etf_details("IE00BK5BQT80")

    assert details.ter_pct is not None
    assert 0.0 < details.ter_pct < 1.0
    assert len(details.holdings) >= 10
    assert len(details.sector_breakdown) >= 5
    assert len(details.country_breakdown) >= 5
    assert details.fund_currency in ("USD", "EUR")


@pytest.mark.vcr
def test_yahoo_finance_real_api_contract() -> None:
    """Verifies parsing against recorded live Yahoo Finance endpoints."""
    client = YahooFinanceClient()
    stock = client.get_stock_details("AAPL")
    assert stock.market_cap is not None and stock.market_cap > 1e11
    assert stock.currency == "USD"
    assert stock.sector == "Technology"
```

### Step 2: Implement a JustETF Functional Live Health Check

Create `scripts/just_etf_health_check.py` to run periodically in CI:

```python
"""JustETF live scraper health check and monitoring script."""

from __future__ import annotations
import os
import sys
from finances_data.just_etf import JustETFClient, JustETFScrapeError

def main() -> None:
    isin = "IE00B4L5Y983"  # iShares Core MSCI World
    print(f"🔍 Validating JustETF scraper against live profile for {isin}...")
    try:
        client = JustETFClient(timeout=15.0)
        details = client.get_etf_details(isin)
        if not details.holdings or not details.sector_breakdown or details.ter_pct is None:
            raise JustETFScrapeError(f"Scraper returned incomplete profile: {details}")
        print("✅ JustETF scraper is operational (holdings, sectors, and TER parsed).")
        sys.exit(0)
    except Exception as e:
        print(f"❌ JustETF scraper health check failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
```

Update `.github/workflows/just_etf_bot.yml` to execute this script on a weekly schedule (matching the Thursday schedule requested in `TODO.md`), notifying Discord upon failure.

### Step 3: Add Multi-Table Decoy DOM Tests to Prevent Parser Lock-On

Add a test in `test/test_just_etf.py` verifying that parsing does not lock onto preceding non-holdings tables that match loose heuristics:

```python
def test_parse_holdings_skips_preceding_decoy_table(client: JustETFClient) -> None:
    html = """
    <html><body>
      <table id="disclaimer-table">
        <tr><th>Important Holdings Information</th></tr>
        <tr><td>Past performance is no guarantee of future results.</td></tr>
      </table>
      <table id="top-holdings">
        <tr><td><a href="?isin=IE00B3RBWM25">Vanguard FTSE</a></td><td>1.25 %</td></tr>
      </table>
    </body></html>
    """
    holdings = client._parse_holdings(_soup(html))
    assert len(holdings) == 1
    assert holdings[0].isin == "IE00B3RBWM25"
    assert holdings[0].weight_pct == pytest.approx(1.25)
```

### Step 4: Enforce Domain Range Constraints on Weights

Add range validation to `Holding.from_dict`, `SectorExposure.from_dict`, and `CountryExposure.from_dict`:

```python
# In data/models.py
weight = _get_float(data, "weight_pct", 0.0) or 0.0
if not (0.0 <= weight <= 100.0):
    raise ValueError(f"[models] Invalid weight_pct {weight}. Must be between 0.0 and 100.0.")
```

And add corresponding test assertions:

```python
def test_holding_weight_range_validation() -> None:
    with pytest.raises(ValueError, match="Must be between 0.0 and 100.0"):
        Holding.from_dict({"isin": "US0378331005", "name": "Apple", "weight_pct": -5.0})

    with pytest.raises(ValueError, match="Must be between 0.0 and 100.0"):
        Holding.from_dict({"isin": "US0378331005", "name": "Apple", "weight_pct": 105.0})
```