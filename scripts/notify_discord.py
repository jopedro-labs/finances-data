"""Generic Discord notifier script — reads result and message from environment variables."""

from __future__ import annotations

import os
import sys

from core_lib.discord import DiscordNotificationError, DiscordNotifier

_MESSAGES: dict[str, str] = {
    "ok": "✅ **JustETF Tests**: All tests passed.\n🔗 {run_url}",
    "error": "🚨 **JustETF Tests**: Test suite failed.\n🔗 {run_url}",
}


def main() -> None:
    webhook_url = os.environ.get("INFRA_ALERTS_DISCORD_WEBHOOK")
    if not webhook_url:
        print("INFRA_ALERTS_DISCORD_WEBHOOK not set, skipping.")
        sys.exit(0)

    result = os.environ.get("TEST_RESULT", "error")
    run_url = os.environ.get("RUN_URL", "")

    template = _MESSAGES.get(result, "⚠️ **JustETF Tests**: Unknown result.\n🔗 {run_url}")
    message = template.format(run_url=run_url)

    try:
        with DiscordNotifier(webhook_url=webhook_url) as notifier:
            notifier.send_message(message)
        print(f"Discord notification sent (result={result}).")
    except DiscordNotificationError as e:
        print(f"Discord notification failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()