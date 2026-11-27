"""Unit tests for automation and canary scripts in scripts/.

Covers environment variable parsing, command output logging, Discord webhook
dispatching, error fallbacks, and execution flow for:
- scripts/notify_discord.py
- scripts/yahoo_health_check.py
- scripts/just_etf_health_check.py
- scripts/quality_eval_agent.py
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from core_lib.discord import DiscordNotificationError

from data.models import ETFDetails, Holding, Quotation, SectorExposure
from finances_data.just_etf import JustETFScrapeError
from finances_data.yahoo_finance import YahooFinanceError
from scripts import (
    just_etf_health_check,
    notify_discord,
    quality_eval_agent,
    yahoo_health_check,
)

# ==============================================================================
# Tests for scripts/notify_discord.py
# ==============================================================================


def test_notify_discord_missing_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that notify_discord exits cleanly with code 0 when webhook URL is missing."""
    monkeypatch.delenv("INFRA_ALERTS_DISCORD_WEBHOOK", raising=False)

    with pytest.raises(SystemExit) as exc_info:
        notify_discord.main()
    assert exc_info.value.code == 0


def test_notify_discord_success_ok_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify successful Discord message dispatch when TEST_RESULT is 'ok'."""
    monkeypatch.setenv("INFRA_ALERTS_DISCORD_WEBHOOK", "https://discord.com/api/webhooks/mock")
    monkeypatch.setenv("TEST_RESULT", "ok")
    monkeypatch.setenv("RUN_URL", "https://github.com/org/repo/actions/runs/101")

    with patch("scripts.notify_discord.DiscordNotifier") as mock_notifier_cls:
        mock_instance: MagicMock = MagicMock()
        mock_notifier_cls.return_value.__enter__.return_value = mock_instance

        notify_discord.main()

        mock_notifier_cls.assert_called_once_with(
            webhook_url="https://discord.com/api/webhooks/mock"
        )
        mock_instance.send_message.assert_called_once()
        sent_payload: str = mock_instance.send_message.call_args[0][0]
        assert "All tests passed" in sent_payload
        assert "https://github.com/org/repo/actions/runs/101" in sent_payload


def test_notify_discord_success_error_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify failure Discord message dispatch when TEST_RESULT is 'error'."""
    monkeypatch.setenv("INFRA_ALERTS_DISCORD_WEBHOOK", "https://discord.com/api/webhooks/mock")
    monkeypatch.setenv("TEST_RESULT", "error")
    monkeypatch.setenv("RUN_URL", "https://github.com/org/repo/actions/runs/102")

    with patch("scripts.notify_discord.DiscordNotifier") as mock_notifier_cls:
        mock_instance: MagicMock = MagicMock()
        mock_notifier_cls.return_value.__enter__.return_value = mock_instance

        notify_discord.main()

        mock_instance.send_message.assert_called_once()
        sent_payload: str = mock_instance.send_message.call_args[0][0]
        assert "Test suite failed" in sent_payload
        assert "https://github.com/org/repo/actions/runs/102" in sent_payload


def test_notify_discord_unknown_result_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify message fallback formatting when TEST_RESULT has an unrecognized status value."""
    monkeypatch.setenv("INFRA_ALERTS_DISCORD_WEBHOOK", "https://discord.com/api/webhooks/mock")
    monkeypatch.setenv("TEST_RESULT", "unrecognized_status")
    monkeypatch.setenv("RUN_URL", "")

    with patch("scripts.notify_discord.DiscordNotifier") as mock_notifier_cls:
        mock_instance: MagicMock = MagicMock()
        mock_notifier_cls.return_value.__enter__.return_value = mock_instance

        notify_discord.main()

        sent_payload: str = mock_instance.send_message.call_args[0][0]
        assert "Unknown result" in sent_payload


def test_notify_discord_notification_error_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify notify_discord exits with status 1 when DiscordNotifier raises an exception."""
    monkeypatch.setenv("INFRA_ALERTS_DISCORD_WEBHOOK", "https://discord.com/api/webhooks/mock")

    with patch("scripts.notify_discord.DiscordNotifier") as mock_notifier_cls:
        mock_instance: MagicMock = MagicMock()
        mock_instance.send_message.side_effect = DiscordNotificationError("API timeout")
        mock_notifier_cls.return_value.__enter__.return_value = mock_instance

        with pytest.raises(SystemExit) as exc_info:
            notify_discord.main()
        assert exc_info.value.code == 1


# ==============================================================================
# Tests for scripts/yahoo_health_check.py
# ==============================================================================


def test_yahoo_health_check_write_github_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify output file generation for GitHub Actions step outputs."""
    out_file: Path = tmp_path / "github_output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))

    yahoo_health_check._write_github_output("ok")
    assert out_file.read_text(encoding="utf-8") == "result=ok\n"

    # With GITHUB_OUTPUT unset, function executes without raising
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    yahoo_health_check._write_github_output("error")


def test_yahoo_health_check_write_error_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify diagnostic log persistence to file with and without traceback."""
    log_file: Path = tmp_path / "logs" / "yahoo_monitor.log"
    monkeypatch.setattr(yahoo_health_check, "LOG_FILE_PATH", log_file)

    # Log without exception
    yahoo_health_check._write_error_log("Test simple error")
    content: str = log_file.read_text(encoding="utf-8")
    assert "ERROR: Test simple error" in content
    assert "Traceback" not in content

    # Log with exception
    try:
        raise ValueError("Diagnostic root cause")
    except ValueError as exc:
        yahoo_health_check._write_error_log("Failure with traceback", exc=exc)

    updated_content: str = log_file.read_text(encoding="utf-8")
    assert "Failure with traceback" in updated_content
    assert "Diagnostic root cause" in updated_content
    assert "Traceback:" in updated_content


def test_yahoo_health_check_notify(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify safe notification wrapper absorbs DiscordNotificationError without raising."""
    with patch("scripts.yahoo_health_check.DiscordNotifier") as mock_notifier_cls:
        mock_instance: MagicMock = MagicMock()
        mock_instance.send_message.side_effect = DiscordNotificationError("Network down")
        mock_notifier_cls.return_value.__enter__.return_value = mock_instance

        # Should not raise exception
        yahoo_health_check._notify("https://discord.com/mock", "Test message")
        mock_instance.send_message.assert_called_once_with("Test message")


def test_yahoo_health_check_main_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify successful execution flow for Yahoo Finance health canary."""
    out_file: Path = tmp_path / "gh_out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    monkeypatch.setenv("INFRA_ALERTS_DISCORD_WEBHOOK", "https://discord.com/mock")
    monkeypatch.setenv("RUN_URL", "https://github.com/run/1")

    valid_quote: Quotation = Quotation(
        price=95.5,
        currency="EUR",
        timestamp=datetime.now(UTC),
        native_price=95.5,
        native_currency="EUR",
    )

    with patch("scripts.yahoo_health_check.YahooFinanceClient") as mock_client_cls, patch(
        "scripts.yahoo_health_check._notify"
    ) as mock_notify:
        mock_client: MagicMock = MagicMock()
        mock_client.get_quotation.return_value = valid_quote
        mock_client_cls.return_value = mock_client

        with pytest.raises(SystemExit) as exc_info:
            yahoo_health_check.main()
        assert exc_info.value.code == 0
        assert "result=ok" in out_file.read_text(encoding="utf-8")
        mock_notify.assert_called_once()
        assert "operational" in mock_notify.call_args[0][1]


def test_yahoo_health_check_main_invalid_quote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify detection and failure exit when quotation has non-positive price or empty currency."""
    log_file: Path = tmp_path / "yahoo.log"
    monkeypatch.setattr(yahoo_health_check, "LOG_FILE_PATH", log_file)
    monkeypatch.setenv("INFRA_ALERTS_DISCORD_WEBHOOK", "https://discord.com/mock")

    invalid_quote: Quotation = Quotation(
        price=0.0,
        currency="",
        timestamp=datetime.now(UTC),
    )

    with patch("scripts.yahoo_health_check.YahooFinanceClient") as mock_client_cls, patch(
        "scripts.yahoo_health_check._notify"
    ) as mock_notify:
        mock_client: MagicMock = MagicMock()
        mock_client.get_quotation.return_value = invalid_quote
        mock_client_cls.return_value = mock_client

        with pytest.raises(SystemExit) as exc_info:
            yahoo_health_check.main()
        assert exc_info.value.code == 1
        mock_notify.assert_called_once()
        assert "Check failed" in mock_notify.call_args[0][1]


def test_yahoo_health_check_main_client_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify handling when client raises YahooFinanceError."""
    log_file: Path = tmp_path / "yahoo.log"
    monkeypatch.setattr(yahoo_health_check, "LOG_FILE_PATH", log_file)

    with patch("scripts.yahoo_health_check.YahooFinanceClient") as mock_client_cls:
        mock_client: MagicMock = MagicMock()
        mock_client.get_quotation.side_effect = YahooFinanceError("Rate limit exceeded")
        mock_client_cls.return_value = mock_client

        with pytest.raises(SystemExit) as exc_info:
            yahoo_health_check.main()
        assert exc_info.value.code == 1
        assert "Rate limit exceeded" in log_file.read_text(encoding="utf-8")


def test_yahoo_health_check_main_unexpected_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify handling when an unexpected generic exception occurs."""
    log_file: Path = tmp_path / "yahoo.log"
    monkeypatch.setattr(yahoo_health_check, "LOG_FILE_PATH", log_file)
    monkeypatch.setenv("INFRA_ALERTS_DISCORD_WEBHOOK", "https://discord.com/mock")

    with patch("scripts.yahoo_health_check.YahooFinanceClient") as mock_client_cls, patch(
        "scripts.yahoo_health_check._notify"
    ) as mock_notify:
        mock_client: MagicMock = MagicMock()
        mock_client.get_quotation.side_effect = RuntimeError("Kernel failure")
        mock_client_cls.return_value = mock_client

        with pytest.raises(SystemExit) as exc_info:
            yahoo_health_check.main()
        assert exc_info.value.code == 1
        mock_notify.assert_called_once()
        assert "Unexpected error" in mock_notify.call_args[0][1]


# ==============================================================================
# Tests for scripts/just_etf_health_check.py
# ==============================================================================


def test_just_etf_health_check_write_github_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify output step persistence for JustETF monitor."""
    out_file: Path = tmp_path / "just_etf_out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))

    just_etf_health_check._write_github_output("ok")
    assert out_file.read_text(encoding="utf-8") == "result=ok\n"


def test_just_etf_health_check_write_error_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify error file logging for JustETF canary."""
    log_file: Path = tmp_path / "logs" / "just_etf_monitor.log"
    monkeypatch.setattr(just_etf_health_check, "LOG_FILE_PATH", log_file)

    just_etf_health_check._write_error_log("Scraping failure sample")
    content: str = log_file.read_text(encoding="utf-8")
    assert "ERROR: Scraping failure sample" in content


def test_just_etf_health_check_notify(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify discord notification failure warning logging."""
    with patch("scripts.just_etf_health_check.DiscordNotifier") as mock_notifier_cls:
        mock_instance: MagicMock = MagicMock()
        mock_instance.send_message.side_effect = DiscordNotificationError("Timeout")
        mock_notifier_cls.return_value.__enter__.return_value = mock_instance

        just_etf_health_check._notify("https://discord.com/mock", "Message")
        mock_instance.send_message.assert_called_once()


def test_just_etf_health_check_main_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify successful execution flow for JustETF canary health check."""
    out_file: Path = tmp_path / "gh_out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    monkeypatch.setenv("INFRA_ALERTS_DISCORD_WEBHOOK", "https://discord.com/mock")

    sample_details: ETFDetails = ETFDetails(
        holdings=[Holding(name="Apple Inc.", isin="US0378331005", weight_pct=4.5)],
        sector_breakdown=[SectorExposure(sector_name="Technology", weight_pct=25.0)],
        country_breakdown=[],
        ter_pct=0.20,
    )

    with patch("scripts.just_etf_health_check.JustETFClient") as mock_client_cls, patch(
        "scripts.just_etf_health_check._notify"
    ) as mock_notify:
        mock_client: MagicMock = MagicMock()
        mock_client.get_etf_details.return_value = sample_details
        mock_client_cls.return_value = mock_client

        with pytest.raises(SystemExit) as exc_info:
            just_etf_health_check.main()
        assert exc_info.value.code == 0
        assert "result=ok" in out_file.read_text(encoding="utf-8")
        mock_notify.assert_called_once()
        assert "operational" in mock_notify.call_args[0][1]


def test_just_etf_health_check_main_incomplete_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify failure exit when details lack holdings or TER percentage."""
    log_file: Path = tmp_path / "just_etf.log"
    monkeypatch.setattr(just_etf_health_check, "LOG_FILE_PATH", log_file)

    incomplete_details: ETFDetails = ETFDetails(
        holdings=[],
        sector_breakdown=[],
        country_breakdown=[],
        ter_pct=None,
    )

    with patch("scripts.just_etf_health_check.JustETFClient") as mock_client_cls:
        mock_client: MagicMock = MagicMock()
        mock_client.get_etf_details.return_value = incomplete_details
        mock_client_cls.return_value = mock_client

        with pytest.raises(SystemExit) as exc_info:
            just_etf_health_check.main()
        assert exc_info.value.code == 1
        assert "incomplete ETF details" in log_file.read_text(encoding="utf-8")


def test_just_etf_health_check_main_scrape_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify failure exit when client raises JustETFScrapeError."""
    log_file: Path = tmp_path / "just_etf.log"
    monkeypatch.setattr(just_etf_health_check, "LOG_FILE_PATH", log_file)
    monkeypatch.setenv("INFRA_ALERTS_DISCORD_WEBHOOK", "https://discord.com/mock")

    with patch("scripts.just_etf_health_check.JustETFClient") as mock_client_cls, patch(
        "scripts.just_etf_health_check._notify"
    ) as mock_notify:
        mock_client: MagicMock = MagicMock()
        mock_client.get_etf_details.side_effect = JustETFScrapeError("HTTP 503 Service Unavailable")
        mock_client_cls.return_value = mock_client

        with pytest.raises(SystemExit) as exc_info:
            just_etf_health_check.main()
        assert exc_info.value.code == 1
        mock_notify.assert_called_once()
        assert "Canary check failed" in mock_notify.call_args[0][1]


def test_just_etf_health_check_main_unexpected_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify handling when an unexpected exception occurs in JustETF check."""
    log_file: Path = tmp_path / "just_etf.log"
    monkeypatch.setattr(just_etf_health_check, "LOG_FILE_PATH", log_file)
    monkeypatch.setenv("INFRA_ALERTS_DISCORD_WEBHOOK", "https://discord.com/mock")

    with patch("scripts.just_etf_health_check.JustETFClient") as mock_client_cls, patch(
        "scripts.just_etf_health_check._notify"
    ) as mock_notify:
        mock_client: MagicMock = MagicMock()
        mock_client.get_etf_details.side_effect = OSError("Connection aborted")
        mock_client_cls.return_value = mock_client

        with pytest.raises(SystemExit) as exc_info:
            just_etf_health_check.main()
        assert exc_info.value.code == 1
        mock_notify.assert_called_once()
        assert "Unexpected error" in mock_notify.call_args[0][1]


# ==============================================================================
# Tests for scripts/quality_eval_agent.py
# ==============================================================================


def test_load_quality_specification(tmp_path: Path) -> None:
    """Verify quality spec loading from candidate paths and error handling when missing."""
    spec_file: Path = tmp_path / "QUALITY_AGENT.MD"
    spec_file.write_text("# Quality Spec Content", encoding="utf-8")

    loaded: str = quality_eval_agent.load_quality_specification([spec_file])
    assert loaded == "# Quality Spec Content"

    with pytest.raises(FileNotFoundError):
        quality_eval_agent.load_quality_specification([tmp_path / "MISSING.MD"])


def test_quality_agent_subprocesses(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify run_pytest, run_ruff, and run_mypy subprocess wrappers."""
    fake_cp: subprocess.CompletedProcess[str] = subprocess.CompletedProcess(
        args=["cmd"], returncode=0, stdout="Success output", stderr="Warning output"
    )

    with patch("subprocess.run", return_value=fake_cp):
        c1, o1 = quality_eval_agent.run_pytest()
        assert c1 == 0
        assert "Success output" in o1
        assert "Warning output" in o1

        c2, o2 = quality_eval_agent.run_ruff()
        assert c2 == 0
        assert "Success output" in o2

        c3, o3 = quality_eval_agent.run_mypy()
        assert c3 == 0
        assert "Success output" in o3


def test_gather_codebase_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify recursive scanning and file content gathering with exclusion filters."""
    repo_dir: Path = tmp_path / "mock_repo"
    repo_dir.mkdir()
    (repo_dir / "src.py").write_text("print('hello')", encoding="utf-8")
    (repo_dir / "unreadable.py").write_text("code", encoding="utf-8")
    ignored_sub: Path = repo_dir / ".git"
    ignored_sub.mkdir()
    (ignored_sub / "config").write_text("ignored", encoding="utf-8")

    monkeypatch.chdir(repo_dir)

    original_open = open

    def mock_open_fn(file: Any, *args: Any, **kwargs: Any) -> Any:
        if "unreadable.py" in str(file):
            raise PermissionError("Access denied")
        return original_open(file, *args, **kwargs)

    with patch("builtins.open", side_effect=mock_open_fn):
        context: str = quality_eval_agent.gather_codebase_context()
        assert "=== FILE: ./src.py ===" in context
        assert "print('hello')" in context
        assert ".git" not in context


def test_evaluate_with_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify Gemini client initialization, prompt dispatch, and response extraction."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GEMINI_API_KEY environment variable is not set"):
        quality_eval_agent.evaluate_with_gemini("spec", "context", "test", "ruff", "mypy")

    monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")

    with patch("scripts.quality_eval_agent.genai.Client") as mock_client_cls:
        mock_client: MagicMock = MagicMock()
        mock_response: MagicMock = MagicMock()
        mock_response.text = "# Gemini Generated Report"
        mock_client.models.generate_content.return_value = mock_response
        mock_client_cls.return_value = mock_client

        result: str = quality_eval_agent.evaluate_with_gemini(
            "spec", "context", "test", "ruff", "mypy"
        )
        assert result == "# Gemini Generated Report"
        mock_client_cls.assert_called_once_with(api_key="test-key-123")

        # Handle None text response
        mock_response.text = None
        assert quality_eval_agent.evaluate_with_gemini("spec", "ctx", "t", "r", "m") == ""


def test_build_fallback_report() -> None:
    """Verify Markdown structural formatting of fallback report."""
    report: str = quality_eval_agent.build_fallback_report(
        test_output="Pytest 10 passed",
        ruff_output="Ruff 0 errors",
        mypy_output="Mypy 0 errors",
        error_message="Quota exceeded",
    )
    assert "Code Quality & Test Gap Evaluation Report (Fallback)" in report
    assert "Quota exceeded" in report
    assert "Pytest 10 passed" in report
    assert "Ruff 0 errors" in report
    assert "Mypy 0 errors" in report


def test_quality_eval_agent_main_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify main execution paths including success, missing spec, fallback, and status codes."""
    report_path: Path = tmp_path / "reports" / "test_report.md"
    monkeypatch.setattr(quality_eval_agent, "REPORT_PATH", report_path)

    # Case 1: Missing spec file triggers exit(1)
    with patch(
        "scripts.quality_eval_agent.load_quality_specification",
        side_effect=FileNotFoundError("Spec missing"),
    ):
        with pytest.raises(SystemExit) as exc_info:
            quality_eval_agent.main()
        assert exc_info.value.code == 1

    # Case 2: Full success execution
    monkeypatch.setenv("GEMINI_API_KEY", "valid-key")
    with patch(
        "scripts.quality_eval_agent.load_quality_specification", return_value="# Spec"
    ), patch("scripts.quality_eval_agent.run_pytest", return_value=(0, "Tests OK")), patch(
        "scripts.quality_eval_agent.run_ruff", return_value=(0, "Ruff OK")
    ), patch(
        "scripts.quality_eval_agent.run_mypy", return_value=(0, "Mypy OK")
    ), patch(
        "scripts.quality_eval_agent.gather_codebase_context", return_value="Context"
    ), patch(
        "scripts.quality_eval_agent.evaluate_with_gemini", return_value="# AI Report"
    ):
        with pytest.raises(SystemExit) as exc_info:
            quality_eval_agent.main()
        assert exc_info.value.code == 0
        assert report_path.read_text(encoding="utf-8") == "# AI Report"

    # Case 3: Gemini evaluation failure with fallback report and missing key
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with patch(
        "scripts.quality_eval_agent.load_quality_specification", return_value="# Spec"
    ), patch("scripts.quality_eval_agent.run_pytest", return_value=(0, "Tests OK")), patch(
        "scripts.quality_eval_agent.run_ruff", return_value=(0, "Ruff OK")
    ), patch(
        "scripts.quality_eval_agent.run_mypy", return_value=(0, "Mypy OK")
    ), patch(
        "scripts.quality_eval_agent.gather_codebase_context", return_value="Context"
    ), patch(
        "scripts.quality_eval_agent.evaluate_with_gemini", side_effect=RuntimeError("AI Error")
    ):
        with pytest.raises(SystemExit) as exc_info:
            quality_eval_agent.main()
        assert exc_info.value.code == 1
        assert "Fallback" in report_path.read_text(encoding="utf-8")

    # Case 4: Pytest reported failures (exit code non-zero)
    monkeypatch.setenv("GEMINI_API_KEY", "valid-key")
    with patch(
        "scripts.quality_eval_agent.load_quality_specification", return_value="# Spec"
    ), patch("scripts.quality_eval_agent.run_pytest", return_value=(2, "Tests Failed")), patch(
        "scripts.quality_eval_agent.run_ruff", return_value=(0, "Ruff OK")
    ), patch(
        "scripts.quality_eval_agent.run_mypy", return_value=(0, "Mypy OK")
    ), patch(
        "scripts.quality_eval_agent.gather_codebase_context", return_value="Context"
    ), patch(
        "scripts.quality_eval_agent.evaluate_with_gemini", return_value="# Report"
    ):
        with pytest.raises(SystemExit) as exc_info:
            quality_eval_agent.main()
        assert exc_info.value.code == 2

    # Case 5: Static analysis checks reported issues, still concludes successfully
    with patch(
        "scripts.quality_eval_agent.load_quality_specification", return_value="# Spec"
    ), patch("scripts.quality_eval_agent.run_pytest", return_value=(0, "Tests OK")), patch(
        "scripts.quality_eval_agent.run_ruff", return_value=(1, "Ruff Issues")
    ), patch(
        "scripts.quality_eval_agent.run_mypy", return_value=(1, "Mypy Issues")
    ), patch(
        "scripts.quality_eval_agent.gather_codebase_context", return_value="Context"
    ), patch(
        "scripts.quality_eval_agent.evaluate_with_gemini", return_value="# Report"
    ):
        with pytest.raises(SystemExit) as exc_info:
            quality_eval_agent.main()
        assert exc_info.value.code == 0
