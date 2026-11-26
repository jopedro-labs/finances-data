![Python 3.10+](https://img.shields.io/badge/python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)
![Version](https://img.shields.io/badge/version-0.1.0-58a6ff?style=flat-square)
![Test JustETF Client](https://github.com/jopedro-labs/finances-data/actions/workflows/just_etf_bot.yml/badge.svg)
![Monitor Yahoo Finance API](https://github.com/jopedro-labs/finances-data/actions/workflows/yahoo_bot.yml/badge.svg)
<br />
![Linter](https://img.shields.io/badge/linter-Ruff-000000?style=flat-square&logo=python&logoColor=white)
![Type Check](https://img.shields.io/badge/types-mypy%20strict-2A6DB2?style=flat-square&logo=python&logoColor=white)
![Pytest](https://img.shields.io/badge/Pytest-0A9EDC?style=flat-square&logo=pytest&logoColor=white)
![Gemini AI](https://img.shields.io/badge/Gemini_AI-8E75B2?style=flat-square&logo=googlegemini&logoColor=white)
![GNU Make](https://img.shields.io/badge/env-GNU%20Make-active?style=flat-square&logo=gnu-make&logoColor=white)
![MIT License](https://img.shields.io/badge/license-MIT-607D8B?style=flat-square)

Python client library for financial market data. Provides an ETF scraper for JustETF and a market data client for Yahoo Finance, with shared immutable domain models and autonomous code quality evaluation tools.

---

## Installation

```bash
pip install -e .

# with dev dependencies (pytest, ruff, mypy)
pip install -e ".[dev]"
```

---

## Modules & Tools

### `finances_data.just_etf`

HTTP scraper for [JustETF](https://www.justetf.com). Fetches full ETF profiles by ISIN using BeautifulSoup with a 3-level DOM fallback strategy per parser. Includes automatic retry on rate-limit (429) and transient server errors (500, 502, 503, 504).

```python
from finances_data.just_etf import JustETFClient

client = JustETFClient()
etf = client.get_etf_details("IE00B4L5Y983")  # iShares Core MSCI World

print(etf.ter_pct)             # 0.2
print(etf.fund_size_eur_m)     # e.g. 80000.0
print(etf.holdings[0].name)    # e.g. "Apple Inc."
print(etf.holdings[0].weight_pct)
```

Returns `ETFDetails` with:
- `holdings` — top holdings with name, ISIN, weight %
- `sector_breakdown` — sector weights
- `country_breakdown` — country weights
- `ter_pct`, `fund_size_eur_m`, `inception_date`, `replication`, `distribution_policy`, `index_name`, `fund_currency`, `volatility_1y_pct`, `holdings_count`

---

### `finances_data.yahoo_finance`

Client over `yfinance` for fetching live quotes, stock fundamentals, and ETF market data.

```python
from finances_data.yahoo_finance import YahooFinanceClient

client = YahooFinanceClient()

# Live market quote
quote = client.get_quotation("IWDA.AS")
print(quote.price, quote.currency)

# Stock fundamentals (~30 fields)
stock = client.get_stock_details("AAPL")
print(stock.pe_ratio, stock.sector, stock.dividend_yield_pct)

# ETF market data — price, NAV, moving averages, volume
etf = client.get_etf_market_data("IWDA.AS")
print(etf.fifty_two_week_high, etf.two_hundred_day_average)
```

---

### `data.models`

Immutable domain dataclasses (`frozen=True, slots=True`) shared across both clients.

| Class | Purpose |
|---|---|
| `Quotation` | Price, currency, timestamp for a ticker |
| `Holding` | ETF holding — name, ISIN, weight % |
| `SectorExposure` | Sector name + weight % |
| `CountryExposure` | Country name + weight % |
| `ETFMarketData` | ETF price, NAV, moving averages, volume |
| `StockDetails` | ~30 fundamental fields: P/E, margins, analyst targets, EPS |
| `ETFDetails` | Full ETF profile: holdings + breakdowns + metadata |

---

## Autonomous Quality Assurance & Test Gap Evaluation Agent

An internal developer utility (`scripts/quality_eval_agent.py`) powered by Gemini AI that acts as an autonomous quality assurance auditor within the repository.

### Core Validation Pillars Evaluated:

1. **Unit Tests:** Isolated verification and mocking via `pytest`.
2. **Integration Tests:** Component and adapter interaction verification.
3. **Static Code Analysis:** Type safety (`mypy`) and linting (`ruff`).
4. **Mutation Testing Readiness:** Assessment of test suite robustness against code changes.
5. **Black-Box Verification:** Functional and behavioral validation.

### Execution:

```bash
make quality-eval-agent
```

The agent automatically executes the test suite with coverage, gathers repository context, analyzes coverage gaps and validation metrics via the configured Gemini model (`GEMINI_MODEL`), and generates a structured markdown report under `reports/validation_gap_report.md`.

---
## GitHub Actions

### `just_etf_bot.yml` — Test JustETF Client

Triggers on push to `finances_data/just_etf/**` or `tests/test_just_etf.py`, and on `workflow_dispatch`.

- Runs `tests/test_just_etf.py` on Python 3.10
- On failure: uploads test output as artifact and opens a GitHub issue
- Always sends a Discord notification with result and run link

```bash
make run-just-etf-bot   # simulate locally with act
```

### `yahoo_bot.yml` — Monitor Yahoo Finance API

Triggers every Monday at 08:00 UTC and on `workflow_dispatch`.

- Fetches a live quote for `IWDA.AS` via `scripts/yahoo_health_check.py`
- On success or failure: sends a Discord notification with run link
- On failure: opens a GitHub issue

```bash
make run-yahoo-bot   # simulate locally with act
```

**Required secret:** `INFRA_ALERTS_DISCORD_WEBHOOK`

For local simulation, create a `.env` file (never commit it):

```
INFRA_ALERTS_DISCORD_WEBHOOK=https://discord.com/api/webhooks/...
```
---

## Requirements

- Python >= 3.10
- Core parsing/client libraries: `beautifulsoup4`, `yfinance`, `requests`
- Quality Evaluation Agent: Requires `google-generativeai` (or `google.genai`), `python-dotenv`, and an active `GEMINI_API_KEY`

---

## Development

```bash
git clone https://github.com/jopedro-labs/finances-data.git
cd finances-data
make install
```

Run all checks (lint, types, tests):

```bash
make check
```

Individual commands:

| Command                   | Description                              |
|---------------------------|------------------------------------------|
| `make lint`               | Lint with Ruff                           |
| `make lint-fix`           | Lint with auto-fix                       |
| `make type`               | Type check with mypy strict              |
| `make test`               | Run tests with pytest                    |
| `make quality-eval-agent` | Run AI quality audit & test gap analysis |
| `make check`              | Run all three in sequence                |

---

## License

Distributed under the MIT License.

Developed and maintained by **João Pedro** ([@JoPedro15](https://github.com/JoPedro15)).

> *Fueled by Espresso, CrossFit WODs, and powered by Gemini AI.* ☕🏋️‍♂️🤖