"""JustETF canary health check and monitoring script."""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from core_lib.discord import DiscordNotificationError, DiscordNotifier
from core_lib.logger import logger

from finances_data.just_etf import JustETFClient, JustETFScrapeError

BENCHMARK_ISIN: str = "IE00B4L5Y983"
LOG_FILE_PATH: Path = Path("logs/just_etf_monitor.log")


def _write_github_output(result: str) -> None:
    github_output: str | None = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"result={result}\n")


def _write_error_log(error_message: str, exc: BaseException | None = None) -> None:
    LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    timestamp: str = datetime.now(timezone.utc).isoformat()
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
    """Run the JustETF live canary health check and send a Discord notification.

    Raises:
        SystemExit: 0 on success, 1 on any failure.
    """
    webhook_url: str | None = os.environ.get("INFRA_ALERTS_DISCORD_WEBHOOK")
    run_url: str = os.environ.get("RUN_URL", "")

    logger.info(f"🔍 Checking JustETF scraper canary status for benchmark ISIN {BENCHMARK_ISIN}...")
    try:
        client: JustETFClient = JustETFClient()
        details = client.get_etf_details(BENCHMARK_ISIN)
        if not details.holdings or details.ter_pct is None:
            raise JustETFScrapeError(
                f"Health check received incomplete ETF details for {BENCHMARK_ISIN}: "
                f"holdings count={len(details.holdings)}, ter={details.ter_pct}"
            )
        msg: str = (
            f"✅ JustETF scraper is UP (retrieved {len(details.holdings)} holdings, "
            f"TER {details.ter_pct}%)."
        )
        logger.info(msg)
        _write_github_output("ok")
        if webhook_url:
            _notify(webhook_url, f"✅ **JustETF Monitor**: Scraper is operational.\n🔗 {run_url}")
        sys.exit(0)
    except JustETFScrapeError as e:
        error_msg: str = f"JustETF scraper check failed: {e}"
        logger.error(f"❌ {error_msg}")
        _write_error_log(error_msg, exc=e)
        _write_github_output("error")
        if webhook_url:
            _notify(webhook_url, f"🚨 **JustETF Monitor**: Canary check failed.\n🔗 {run_url}")
        sys.exit(1)
    except Exception as e:
        error_msg = f"Unexpected error while checking JustETF scraper: {e}"
        logger.exception(f"❌ {error_msg}", exception=e)
        _write_error_log(error_msg, exc=e)
        _write_github_output("error")
        if webhook_url:
            _notify(webhook_url, f"🚨 **JustETF Monitor**: Unexpected error.\n🔗 {run_url}")
        sys.exit(1)


if __name__ == "__main__":
    main()
