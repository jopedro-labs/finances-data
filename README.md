# finances-data

![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)
![Version](https://img.shields.io/badge/version-0.1.0-58a6ff?style=flat-square)
![Monitor JustETF Scraper](https://github.com/jopedro-labs/finances-data/actions/workflows/just_etf_bot.yml/badge.svg)
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
# Editable install
pip install -e .

# With dev dependencies (pytest, pytest-cov, ruff, mypy, google-genai)
pip install -e ".[dev]"
```

Or via GNU Make:

```bash
make install
```

---

## Repository Structure

```text
finances-data/
├── .gemini/
│   └── QUALITY_AGENT.MD           # Quality assurance spec and audit guidelines
├── .github/
│   └── workflows/
│       ├── ci.yml                 # Matrix CI testing across Python 3.10-3.13, ruff, mypy, AUDIT sync
│       ├── just_etf_bot.yml       # Scheduled canary monitor for JustETF scraper (Thursdays 20:00 UTC)
│       ├── yahoo_bot.yml          # Scheduled canary monitor for Yahoo Finance API (Thursdays 20:00 UTC)
│       └── publish.yml            # Automated PyPI publish workflow with version collision guards
├── data/
│   ├── common/
│   │   └── constants.py           # Country alias maps and shared normalization constants
│   └── models.py                  # Immutable domain models (Quotation, Holding, ETFMarketData, etc.)
├── finances_data/
│   ├── just_etf/
│   │   ├── just_etf_client.py     # Resilient JustETF scraper with 3-tier DOM fallback & rate-limit backoff
│   │   └── readme.md              # JustETF module documentation
│   └── yahoo_finance/
│       ├── yahoo_finance_client.py# Typed wrapper over yfinance for quotes, fundamentals, and ETF stats
│       └── readme.md              # Yahoo Finance module documentation
├── logs/                          # Runtime logs for canary health checks (gitignored)
├── reports/                       # Quality assessment and audit reports (gitignored)
├── scripts/
│   ├── just_etf_health_check.py   # Live canary health check for JustETF scraper
│   ├── notify_discord.py          # Discord webhook notification helper
│   ├── quality_eval_agent.py      # Autonomous AI code quality and gap analysis auditor
│   ├── validate_audit_sync.py     # Structural validator and change-sync guard for AUDIT.md
│   └── yahoo_health_check.py      # Live canary health check for Yahoo Finance API
├── tests/                         # Pytest test suite (100% statement coverage on core modules)
├── .env.example                   # Environment configuration template
├── AUDIT.md                       # Comprehensive codebase audit, technical debt, and backlog tracker
├── Makefile                       # Development, linting, testing, and canary runner targets
└── pyproject.toml                 # Package configuration, dependencies, ruff, mypy, and pytest options
```

---

## Modules & Usage

### `finances_data.just_etf`

HTTP scraper for [JustETF](https://www.justetf.com). Fetches full ETF profiles by ISIN using BeautifulSoup with a 3-level DOM fallback strategy per parser. Includes safe `Retry-After` parsing (supporting integers and HTTP-dates, capped to 10s) and bounded retries on HTTP 429 and transient errors (500, 502, 503, 504).

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
- `holdings` — top holdings with name, ISIN, weight % (bounded between 0.0 and 100.0)
- `sector_breakdown` — sector weights
- `country_breakdown` — country weights with canonical name mapping
- `ter_pct`, `fund_size_eur_m`, `inception_date`, `replication`, `distribution_policy`, `index_name`, `fund_currency`, `volatility_1y_pct`, `holdings_count`

---

### `finances_data.yahoo_finance`

Client over `yfinance` for fetching live quotes, stock fundamentals, and ETF market data, equipped with typed dictionary schemas (`YahooTickerInfo`, `YahooHistoryRow`), currency validation, and sanitized float conversions.

```python
from finances_data.yahoo_finance import YahooFinanceClient

client = YahooFinanceClient()

# Live market quote
quote = client.get_quotation("IWDA.AS")
print(quote.price, quote.currency)

# Stock fundamentals (~34 fields)
stock = client.get_stock_details("AAPL")
print(stock.pe_ratio, stock.sector, stock.dividend_yield_pct)

# ETF market data — price, NAV, moving averages, volume
etf = client.get_etf_market_data("IWDA.AS")
print(etf.fifty_two_week_high, etf.two_hundred_day_average)
```

---

### `data.models`

Immutable domain dataclasses (`frozen=True, slots=True`) shared across both clients, enforcing semantic domain invariants (e.g., non-negative prices and percentage bounds):

| Class | Purpose | Domain Invariants |
|---|---|---|
| `Quotation` | Price, currency, timestamp for a ticker | `price >= 0.0`, `native_price >= 0.0` |
| `Holding` | ETF holding — name, ISIN, weight % | `0.0 <= weight_pct <= 100.0` |
| `SectorExposure` | Sector name + weight % | `0.0 <= weight_pct <= 100.0` |
| `CountryExposure` | Country name + weight % | `0.0 <= weight_pct <= 100.0` |
| `ETFMarketData` | ETF price, NAV, moving averages, volume | `price >= 0.0`, `nav_price >= 0.0`, `average_volume >= 0` |
| `StockDetails` | ~34 fundamental metrics: P/E, margins, analyst targets, EPS | Type-safe conversions, null/nan sanitization |
| `ETFDetails` | Full ETF profile: holdings + breakdowns + metadata | Structured container with dict export |

---

## Health-Check Canary Scripts & Workflows

The repository maintains automated scheduled canaries to detect third-party API drift, JustETF DOM structure shifts, and anti-scraping challenges.

### GitHub Actions Workflows

- **`ci.yml`**: Multi-Python matrix (3.10, 3.11, 3.12, 3.13) verifying `ruff`, `mypy`, `pytest` with coverage, and enforcing `AUDIT.md` synchronization via `scripts/validate_audit_sync.py --enforce-sync`.
- **`just_etf_bot.yml`**: Scheduled health monitor running `scripts/just_etf_health_check.py` every Thursday at 20:00 UTC. Sends Discord alerts on failure and uploads error logs (`logs/just_etf_monitor.log`).
- **`yahoo_bot.yml`**: Scheduled health monitor running `scripts/yahoo_health_check.py` every Thursday at 20:00 UTC. Validates live quote resolution for `IWDA.AS`, posts alerts to Discord, and uploads error logs (`logs/yahoo_monitor.log`).
- **`publish.yml`**: Automated dispatch workflow publishing releases to PyPI with unbumped version and remote git tag collision guards.

### Running Canaries Locally

```bash
# Execute JustETF live canary check
make run-just-etf-health

# Execute Yahoo Finance live canary check
make run-yahoo-health
```

---

## Autonomous Quality Assurance & Test Gap Evaluation Agent

An internal developer utility (`scripts/quality_eval_agent.py`) powered by Google GenAI (`google-genai` SDK) that inspects the repository against `.gemini/QUALITY_AGENT.MD`.

### Core Validation Pillars Evaluated:

1. **Unit Tests:** Isolated verification and mocking via `pytest`.
2. **Integration Tests:** Component and adapter interaction verification.
3. **Static Code Analysis:** Type safety (`mypy` strict) and linting (`ruff` with `T20`, `B`, `UP`).
4. **Mutation Testing Readiness:** Heuristic assessment of test sensitivity against subtle logic mutations.
5. **Black-Box Verification:** Functional and behavioral validation.

### Execution:

```bash
make quality-eval-agent
```

Requirements: Copy `.env.example` to `.env` and configure `GEMINI_API_KEY`. The agent executes the test suite, gathers repository context, analyzes gaps via `GEMINI_MODEL` (default: `gemini-3.8-flash`), and outputs a structured markdown report to `reports/quality_agent_report.md`.

---

## AUDIT.md & Repository Maintenance Conventions

The repository uses `AUDIT.md` to track technical debt, bugs, and backlog items. It is strictly enforced via `scripts/validate_audit_sync.py`:

- **Structural Integrity**: Enforces header formatting, checkbox syntax (`- [x]` or `- [ ]`), and mandatory sections.
- **Change Synchronization**: Changes to `finances_data/`, `data/`, `scripts/`, `tests/`, or `.github/workflows/` require an update to `AUDIT.md` (or explicit `BYPASS_AUDIT_SYNC=1`).
- **Verification Target**: Run `make validate-audit` to assert consistency.

---

## Development Commands

All standard development tasks are orchestrated through GNU Make:

```bash
# Run lint, type checking, pytest with coverage, and audit sync validation
make check
```

| Command | Description |
|---|---|
| `make install` | Create `.venv` and install package with dev dependencies |
| `make lint` | Check code with Ruff (`E`, `F`, `I`, `UP`, `B`, `T20`) |
| `make lint-fix` | Auto-fix Ruff lint issues |
| `make type` | Type check codebase with Mypy in strict mode |
| `make test` | Run pytest suite with terminal coverage report |
| `make validate-audit` | Verify `AUDIT.md` syntax and synchronization status |
| `make quality-eval-agent`| Run autonomous AI quality auditor |
| `make run-just-etf-health`| Run live JustETF canary check |
| `make run-yahoo-health` | Run live Yahoo Finance canary check |
| `make clean-venv` | Remove `.venv` and installed stamp |

---

## License

Distributed under the MIT License.

Developed and maintained by **João Pedro** ([@JoPedro15](https://github.com/JoPedro15)).
