"""Yahoo Finance API health check and monitoring script."""

from __future__ import annotations

import os
import sys

from core_lib.discord import DiscordNotificationError, DiscordNotifier
from finances_data.yahoo_finance import YahooFinanceClient, YahooFinanceError


def _write_github_output(result: str) -> None:
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"result={result}\n")


def _notify(webhook_url: str, message: str) -> None:
    try:
        with DiscordNotifier(webhook_url=webhook_url) as notifier:
            notifier.send_message(message)
    except DiscordNotificationError as e:
        print(f"⚠️ Discord notification failed: {e}")


def main() -> None:
    """Run the Yahoo Finance health check and send a Discord notification with the result.

    Raises:
        SystemExit: 0 on success, 1 on any failure.
    """
    webhook_url = os.environ.get("INFRA_ALERTS_DISCORD_WEBHOOK")
    run_url = os.environ.get("RUN_URL", "")

    print("🔍 Checking Yahoo Finance API status...")
    try:
        client = YahooFinanceClient()
        quote = client.get_quotation("IWDA.AS")
        if quote:
            print("✅ Yahoo Finance API is UP (quote retrieved successfully).")
            _write_github_output("ok")
            if webhook_url:
                _notify(webhook_url, f"✅ **Yahoo Finance Monitor**: API is operational.\n🔗 {run_url}")
            sys.exit(0)
        else:
            print("⚠️ Yahoo Finance API returned an empty quote response.")
            _write_github_output("error")
            if webhook_url:
                _notify(webhook_url, f"⚠️ **Yahoo Finance Monitor**: Empty response.\n🔗 {run_url}")
            sys.exit(1)
    except YahooFinanceError as e:
        print(f"❌ Yahoo Finance API check failed: {e}")
        _write_github_output("error")
        if webhook_url:
            _notify(webhook_url, f"🚨 **Yahoo Finance Monitor**: Check failed.\n🔗 {run_url}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error while checking Yahoo Finance API: {e}")
        _write_github_output("error")
        if webhook_url:
            _notify(webhook_url, f"🚨 **Yahoo Finance Monitor**: Unexpected error.\n🔗 {run_url}")
        sys.exit(1)


if __name__ == "__main__":
    main()