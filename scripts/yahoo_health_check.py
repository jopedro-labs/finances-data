"""Yahoo Finance API health check and monitoring script."""

from __future__ import annotations

import os
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

from core_lib.discord import DiscordNotificationError, DiscordNotifier
from core_lib.logger import logger

from finances_data.yahoo_finance import YahooFinanceClient, YahooFinanceError

LOG_FILE_PATH: Path = Path("logs/yahoo_monitor.log")


def _write_github_output(result: str) -> None:
    github_output: str | None = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"result={result}\n")


def _write_error_log(error_message: str, exc: BaseException | None = None) -> None:
    LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    timestamp: str = datetime.now(UTC).isoformat()
    log_entry: str = f"[{timestamp}] ERROR: {error_message}\n"
    if exc is not None:
        tb: str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        log_entry += f"Traceback:\n{tb}\n"
    with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
        f.write(log_entry)


def _notify(webhook_url: str, message: str) -> None:
    try:
        with DiscordNotifier(webhook_url=webhook_url) as notifier:
            notifier.send_message(message)
    except DiscordNotificationError as e:
        logger.warning(f"⚠️ Discord notification failed: {e}")


def main() -> None:
    """Run the Yahoo Finance health check and send a Discord notification with the result.

    Raises:
        SystemExit: 0 on success, 1 on any failure.
    """
    webhook_url: str | None = os.environ.get("INFRA_ALERTS_DISCORD_WEBHOOK")
    run_url: str = os.environ.get("RUN_URL", "")

    logger.info("🔍 Checking Yahoo Finance API status...")
    try:
        client: YahooFinanceClient = YahooFinanceClient()
        quote = client.get_quotation("IWDA.AS")
        if not quote or quote.price <= 0.0 or not quote.currency:
            raise YahooFinanceError(f"Health check received invalid quotation payload: {quote}")
        logger.info("✅ Yahoo Finance API is UP (quote retrieved successfully).")
        _write_github_output("ok")
        if webhook_url:
            _notify(webhook_url, f"✅ **Yahoo Finance Monitor**: API is operational.\n🔗 {run_url}")
        sys.exit(0)
    except YahooFinanceError as e:
        error_msg: str = f"Yahoo Finance API check failed: {e}"
        logger.error(f"❌ {error_msg}")
        _write_error_log(error_msg, exc=e)
        _write_github_output("error")
        if webhook_url:
            _notify(webhook_url, f"🚨 **Yahoo Finance Monitor**: Check failed.\n🔗 {run_url}")
        sys.exit(1)
    except Exception as e:
        error_msg = f"Unexpected error while checking Yahoo Finance API: {e}"
        logger.exception(f"❌ {error_msg}", exception=e)
        _write_error_log(error_msg, exc=e)
        _write_github_output("error")
        if webhook_url:
            _notify(webhook_url, f"🚨 **Yahoo Finance Monitor**: Unexpected error.\n🔗 {run_url}")
        sys.exit(1)


if __name__ == "__main__":
    main()
