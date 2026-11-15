"""Yahoo Finance infrastructure module initialization."""

from __future__ import annotations

from finances_data.yahoo_finance.yahoo_finance_client import YahooFinanceClient, YahooFinanceError

__all__ = ["YahooFinanceClient", "YahooFinanceError"]
