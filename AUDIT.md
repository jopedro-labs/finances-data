# Codebase Audit Report: `finances-data`

## Executive Summary
This document provides a factual, read-only comprehensive audit of the `finances-data` repository using `/home/jopedro/dev/repos/core-lib` as the engineering, tooling, and architectural benchmark. It documents missing runtime configurations, environment dependencies, CI/automation drift, bugs, type safety gaps, logging standard violations, and test coverage deficiencies across all modules and scripts.

---

## 1. Missing Local Files & Environment Setup

- [ ] **Missing Root `.env.example` Configuration Template**:
  - The repository relies on environment variables across `scripts/` (`notify_discord.py`, `quality_eval_agent.py`, `yahoo_health_check.py`) and GitHub Actions workflows (`just_etf_bot.yml`, `yahoo_bot.yml`), but provides no tracked `.env.example` template.
  - Runtime and automation scripts expect the following environment variables:
    - `INFRA_ALERTS_DISCORD_WEBHOOK`: Discord incoming webhook URL for CI/bot health notifications (used in `scripts/notify_discord.py` and `scripts/yahoo_health_check.py`). Optional locally, mandatory for automated alerts.
    - `TEST_RESULT`: Input result status flag (`"ok"` or `"error"`) parsed in `scripts/notify_discord.py` (defaults to `"error"` if unset).
    - `RUN_URL`: Hyperlink pointing to the workflow execution run URL, injected into Discord alert payloads. Optional.
    - `GITHUB_OUTPUT`: Local/runner path to step outputs in GitHub Actions environments. Used in `scripts/yahoo_health_check.py` to write `result=ok` or `result=error`.
    - `GEMINI_API_KEY`: API key for Google Gemini model evaluation in `scripts/quality_eval_agent.py`. Mandatory when executing the evaluation agent.
    - `GEMINI_MODEL`: Gemini model identifier in `scripts/quality_eval_agent.py` (defaults to `gemini-3.1-pro-preview` in `finances-data`, whereas `core-lib` standardizes on `gemini-2.5-flash`). Optional.
  - Acceptance Criteria: Create and commit `.env.example` documenting all 6 variables with clear usage descriptions and default values.

- [ ] **Missing Local Runtime Artifacts & Storage Directories**:
  - Missing local runtime directories expected by scripts and workflows:
    - `logs/`: `yahoo_bot.yml` uploads `logs/yahoo_monitor.log` upon failure, but `scripts/yahoo_health_check.py` does not initialize or configure file logging to `logs/yahoo_monitor.log`. Local executions fail if the directory does not exist or logging is not configured.
    - `reports/`: Created dynamically by `scripts/quality_eval_agent.py` (`reports/validation_gap_report.md`), but untracked in source control.
  - Acceptance Criteria: Add `.gitkeep` or automated `mkdir(exist_ok=True)` guards across logging/reporting utilities.

- [ ] **Gaps in `.gitignore` vs Benchmark (`core-lib`)**:
  - Inspecting `finances-data/.gitignore` against `/home/jopedro/dev/repos/core-lib/.gitignore` reveals critical missing ignore patterns:
    - Missing environment & secret files: `.env`, `.env.*`, `!.env.example`, `secrets/`.
    - Missing coverage artifacts: `.coverage`, `htmlcov/`.
    - Missing cache directories: `.ruff_cache/`.
    - Missing IDE paths: `.vscode/`.
    - Missing state directories: `reports/` (present in tree but not ignored in `.gitignore`).
  - Acceptance Criteria: Align `.gitignore` line-by-line with `core-lib`, preventing accidental commits of local `.env` secrets, coverage databases, and cache folders.

---

## 2. Bugs & Code Fragilities

- [ ] **Violation of Logging Standard — Ad-hoc `print()` and Unconfigured Logging in `scripts/`**:
  - `finances-data` completely bypasses `core_lib.logger` across its scripts, relying on raw `print()` statements:
    - `scripts/notify_discord.py`: Lines 19, 31, 33 use `print()`.
    - `scripts/yahoo_health_check.py`: Lines 24, 36, 42, 48, 54 use `print()`.
    - `scripts/quality_eval_agent.py`: Lines 21, 54, 61, 87, 94, 111, 114, 117 use `print()`.
  - Furthermore, `yahoo_bot.yml` attempts to upload `logs/yahoo_monitor.log` on failure, but `scripts/yahoo_health_check.py` never writes to a log file or configures a file logger.
  - Acceptance Criteria: Replace operational `print()` calls in `scripts/` with `core_lib.logger` (`get_logger`, `info`, `warning`, `error`, `exception`), configuring an operational file handler writing to `logs/yahoo_monitor.log` where expected by CI artifacts.

- [ ] **Deprecated `google-generativeai` SDK in `quality_eval_agent.py` and `pyproject.toml`**:
  - `scripts/quality_eval_agent.py` imports deprecated `google.generativeai as genai` (line 14) and specifies `model_name = os.environ.get("GEMINI_MODEL", "gemini-3.1-pro-preview")`.
  - `pyproject.toml` declares `"google-generativeai>=0.4"` under optional dev dependencies.
  - In `core-lib`, `scripts/quality_eval_agent.py` and `pyproject.toml` were modernized to the official Google GenAI SDK (`from google import genai`) with `"google-genai>=0.1.1"` and default model `"gemini-2.5-flash"`.
  - Acceptance Criteria: Migrate `scripts/quality_eval_agent.py` to `google-genai`, update `pyproject.toml` dependencies, and align default `GEMINI_MODEL` with `core-lib`.

- [ ] **Hardcoded Rate-Limit Sleep & Timeout Fragility in `JustETFClient`**:
  - In `finances_data/just_etf/just_etf_client.py` (lines 75-78):
    ```python
    if response.status_code == 429:
        retry_after: int = int(response.headers.get("Retry-After", 60))
        time.sleep(retry_after)
        response = self.session.get(url, timeout=self.timeout)
    ```
    If JustETF returns a 429 without a `Retry-After` header or with an excessively high duration (e.g., 3600), the thread blocks synchronously for 60+ seconds.
    If the subsequent retry also returns 429, no further retry occurs, and `response.status_code != 200` raises `JustETFScrapeError`.
    Furthermore, non-numeric `Retry-After` headers (e.g., HTTP date format `Wed, 21 Oct 2026 07:28:00 GMT`) will trigger an unhandled `ValueError` when calling `int(...)`.
  - Acceptance Criteria: Add safe parsing for `Retry-After` (handling non-numeric/date formats and capping maximum sleep backoff to e.g. 10s) and incorporate retry attempts within a bounded loop.

- [ ] **Unhandled Exceptions & Missing Validation in Metadata Conversion**:
  - In `finances_data/just_etf/just_etf_client.py` (lines 144-159):
    `_parse_fund_metadata()` relies on `with contextlib.suppress(ValueError):` for `fund_size_eur_m`, `holdings_count`, and `volatility_1y_pct`.
    If parsing fails due to unexpected formatting, fields silently default to `None` with zero diagnostic logging, masking upstream DOM structure changes.
  - In `finances_data/yahoo_finance/yahoo_finance_client.py` (lines 40-45):
    `latest_row: Any = history.iloc[-1]` assumes history is non-empty after checking `if history.empty:`. However, if history returns columns with `NaN` or unaligned dates, `price` is returned as `None` or raises `YahooFinanceError("Invalid or missing close price...")` without capturing underlying ticker currency context.
  - Acceptance Criteria: Add explicit debug/warning logs via `core_lib.logger` when fallback suppressions occur, and enrich exception messages with ticker metadata.

- [ ] **Broad `Any` Typing and Pandas Type Erasure in Yahoo Finance Client**:
  - In `finances_data/yahoo_finance/yahoo_finance_client.py`:
    `t.info` and `t.history(period="1d")` return untyped `Any` structures (`history: Any`, `latest_row: Any`, `info: dict[str, Any]`).
    `info.get(...)` accesses are repeated without typed dictionary contracts or data schema wrappers.
  - In `pyproject.toml`, `[[tool.mypy.overrides]]` disables type checking for `yfinance.*` and `bs4.*` with `ignore_missing_imports = true`, leaving data transformations weakly checked.
  - Acceptance Criteria: Introduce structural typing protocols or `TypedDict` representations for `yfinance` response payloads, eliminating untyped attribute access.

- [ ] **Missing Domain Range Bounds on Financial Data Models**:
  - In `data/models.py`:
    `Holding`, `SectorExposure`, and `CountryExposure` accept negative weights or weights exceeding 100% (e.g., `Holding(weight_pct=-15.0)` or `SectorExposure(weight_pct=150.0)`).
    `Quotation` and `ETFMarketData` accept negative prices or volume figures without validation.
  - Acceptance Criteria: Add invariant validation in model factories (`from_dict` and `__post_init__` checks) asserting `0.0 <= weight_pct <= 100.0` and `price >= 0.0`.

- [ ] **Migration from `TODO.md` — Workflow Scheduling Alignment**:
  - `TODO.md` specified:
    - `workflows should run on Thursdays`
    - `**Item 3:** Analyze quality report from AI Agent`
    - `criar um guia para o Claude AGENT`
  - In `finances-data/.github/workflows/yahoo_bot.yml`, the cron is currently set to Mondays (`cron: '0 8 * * 1'`).
  - `.github/workflows/just_etf_bot.yml` has no `schedule` trigger configured at all (only `push` on paths and `workflow_dispatch`).
  - Acceptance Criteria: Update `yahoo_bot.yml` and add scheduled execution to `just_etf_bot.yml` on Thursdays (`0 8 * * 4`). Consolidate the findings from `reports/validation_gap_report.md` into backlog tasks, and document guidelines for Claude Agent execution.

---

## 3. Test Coverage Gaps

- [ ] **Absence of Real / Recorded Integration Tests (0% Integration Coverage)**:
  - Both `test_just_etf.py` and `test_yahoo_finance.py` rely entirely on `unittest.mock` (`unittest.mock.patch` of `requests.Session.get` and `yfinance.Ticker`).
  - There are zero tests running against live endpoints, recorded VCR cassettes (`pytest-recording` / `vcrpy`), or real HTTP DOM pages.
  - Changes in JustETF DOM markup or Yahoo Finance API field definitions pass the entire unit test suite undetected.
  - Acceptance Criteria: Introduce integration test fixtures with recorded cassettes or loopback HTTP servers validating real transport serialization, headers, and response formats.

- [ ] **Missing Functional Live Canary for JustETF**:
  - `scripts/yahoo_health_check.py` acts as a live canary for Yahoo Finance in CI (`yahoo_bot.yml`), but no equivalent live check exists for JustETF.
  - `.github/workflows/just_etf_bot.yml` merely runs mocked unit tests on push.
  - Acceptance Criteria: Create `scripts/just_etf_health_check.py` fetching a benchmark ETF (e.g., `IE00B4L5Y983`) against the live website, validating holdings, sectors, and TER parsing, and integrate it into `just_etf_bot.yml`.

- [ ] **Decoy DOM Heuristic Vulnerabilities in Scraper Tests**:
  - `test/test_just_etf.py` tests fallback table selectors using isolated, single-table HTML snippets.
  - If a live JustETF page includes disclaimer tables, advertisement banners, or other non-holding tables containing the word "Holdings" prior to the actual table, heuristic parsing could bind to the wrong element.
  - Acceptance Criteria: Add integration/unit test fixtures featuring complex multi-table HTML structures with decoy tables to verify robust parser disambiguation.

- [ ] **Missing Out-of-Process CLI Black-Box Tests for Automation Scripts**:
  - None of the scripts in `scripts/` (`notify_discord.py`, `quality_eval_agent.py`, `yahoo_health_check.py`) have dedicated unit or CLI invocation tests in `test/`.
  - Missing coverage for CLI exit codes (`0` vs `1`), environment variable absence handling, and error output propagation.
  - Acceptance Criteria: Add test modules (e.g., `test/test_scripts.py`) testing script execution, parameter passing, and environment variable fallbacks via `subprocess` or runner mocks.

---

## 4. Tooling, CI/CD & Repository Alignment with `core-lib`

- [ ] **`Makefile` Discrepancies and Missing Targets**:
  - Compared to `/home/jopedro/dev/repos/core-lib/Makefile`:
    - `finances-data/Makefile` uses naked `python3 -m pip install` and system `python3` instead of a contained virtual environment (`.venv/bin/python3`, `.venv/.installed` stamp).
    - Missing `validate-audit` target: `core-lib` enforces AUDIT.md integrity and sync checks via `make validate-audit` and `scripts/validate_audit_sync.py`.
    - Inconsistent workflow run targets: `Makefile` in `finances-data` targets `.github/just_etf_bot.yml` and `.github/yahoo_bot.yml` (missing `workflows/` directory in path, which breaks `act` execution).
    - Missing `clean-venv` target.
  - Acceptance Criteria: Modernize `Makefile` with `.venv` isolation, `.installed` stamp, `validate-audit`, and corrected `act` paths matching `core-lib`.

- [ ] **CI Workflow Configuration Drift (`.github/workflows/ci.yml`)**:
  - In `finances-data/.github/workflows/ci.yml`:
    - Missing `permissions: contents: read` block.
    - Lint and type check steps run only against `finances_data` (`ruff check finances_data`, `mypy finances_data`), ignoring `data/`, `scripts/`, and `test/`.
    - Missing AUDIT.md validation step (`python scripts/validate_audit_sync.py --enforce-sync`).
  - Acceptance Criteria: Update `ci.yml` to specify explicit permissions, inspect `finances_data data scripts test`, and run AUDIT synchronization checks.

- [ ] **Missing AUDIT Integrity & Sync Script (`scripts/validate_audit_sync.py`)**:
  - `core-lib` includes `scripts/validate_audit_sync.py` to ensure that `AUDIT.md` maintains required section headers, valid checkbox syntax, and is updated whenever monitored paths are changed.
  - `finances-data` currently lacks this validation script and its accompanying test suite (`test/test_validate_audit_sync.py`).
  - Acceptance Criteria: Introduce `scripts/validate_audit_sync.py` and unit tests in `finances-data`, configured to monitor `finances_data/`, `data/`, `scripts/`, `pyproject.toml`, and `.github/workflows/`.

- [ ] **`pyproject.toml` Tooling Alignment & Dependency Tightening**:
  - In `finances-data/pyproject.toml`:
    - `name = "finances-data"` (uses hyphen), but `core_lib` is declared as `jopedro-core-lib>=0.2.0`.
    - `[tool.mypy]` specifies `files = ["finances_data", "data"]`, omitting `scripts` and `test`.
    - `[tool.ruff.lint]` select only `["E", "F", "I", "UP"]`, whereas enforcing print rules (`"T20"`) or bug detection (`"B"`) would safeguard logger standards.
    - Test directory naming convention: `test/` is used instead of standard `tests/` used in `core-lib`.
  - Acceptance Criteria: Align `pyproject.toml` tool configuration, expand mypy/ruff inspection coverage, and evaluate standardizing directory naming to `tests/`.
