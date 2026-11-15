"""JustETF infrastructure module initialization."""

from __future__ import annotations

from finances_data.just_etf.just_etf_client import JustETFClient, JustETFScrapeError

__all__ = ["JustETFClient", "JustETFScrapeError"]
