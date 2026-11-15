"""
Domain models and structured data schemas for the finance-data repository.
Provides immutable, slot-optimized dataclasses supporting safe parsing,
serialization, and market data representation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


class DictAccessMixin:
    """Mixin providing dictionary-like item access (__getitem__) to dataclasses."""

    __slots__ = ()

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


def _get_float(data: dict[str, Any], key: str, default: float | None = None) -> float | None:
    val: Any = data.get(key)
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _get_int(data: dict[str, Any], key: str, default: int | None = None) -> int | None:
    val: Any = data.get(key)
    if val is None or val == "":
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _get_str(data: dict[str, Any], key: str, default: str | None = None) -> str | None:
    val: Any = data.get(key)
    if val is None or val == "":
        return default
    return str(val).strip() or default


@dataclass(frozen=True, slots=True)
class Quotation(DictAccessMixin):
    """Represents a market quotation and pricing details for a ticker at a point in time."""

    price: float
    currency: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    native_price: float | None = None
    native_currency: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "price": self.price,
            "currency": self.currency,
            "timestamp": self.timestamp.isoformat(),
            "native_price": self.native_price,
            "native_currency": self.native_currency,
        }


@dataclass(frozen=True, slots=True)
class Holding(DictAccessMixin):
    """Represents an individual stock or asset holding within an ETF."""

    name: str
    isin: str
    weight_pct: float
    just_etf_ticker: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Holding:
        if not data.get("isin"):
            raise ValueError("[models] Holding missing mandatory property 'isin'.")
        if not data.get("name"):
            raise ValueError("[models] Holding missing mandatory property 'name'.")
        if "weight_pct" not in data:
            raise KeyError("[models] Holding missing mandatory key 'weight_pct'.")

        return cls(
            name=str(data["name"]),
            isin=str(data["isin"]),
            weight_pct=_get_float(data, "weight_pct", 0.0) or 0.0,
            just_etf_ticker=_get_str(data, "just_etf_ticker") or _get_str(data, "just_etf"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SectorExposure(DictAccessMixin):
    """Represents sector breakdown weight within an ETF."""

    sector_name: str
    weight_pct: float

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SectorExposure:
        if not data.get("sector_name"):
            raise ValueError("[models] Sector exposure missing mandatory property 'sector_name'.")
        if "weight_pct" not in data:
            raise KeyError("[models] Sector exposure missing mandatory key 'weight_pct'.")

        return cls(
            sector_name=str(data["sector_name"]),
            weight_pct=_get_float(data, "weight_pct", 0.0) or 0.0,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CountryExposure(DictAccessMixin):
    """Represents country breakdown weight within an ETF."""

    country_name: str
    weight_pct: float

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CountryExposure:
        if not data.get("country_name"):
            raise ValueError("[models] Country exposure missing mandatory property 'country_name'.")
        if "weight_pct" not in data:
            raise KeyError("[models] Country exposure missing mandatory key 'weight_pct'.")

        raw_name: str = str(data["country_name"]).strip()

        return cls(
            country_name=raw_name,
            weight_pct=_get_float(data, "weight_pct", 0.0) or 0.0,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ETFMarketData(DictAccessMixin):
    """Market data for an ETF fetched from market and fund sources."""

    price: float | None = None
    native_currency: str | None = None
    just_etf_ticker: str | None = None
    nav_price: float | None = None
    fifty_two_week_high: float | None = None
    fifty_two_week_low: float | None = None
    fifty_two_week_change_pct: float | None = None
    fifty_day_average: float | None = None
    two_hundred_day_average: float | None = None
    average_volume: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ETFMarketData:
        return cls(
            price=_get_float(data, "price"),
            native_currency=_get_str(data, "currency"),
            just_etf_ticker=_get_str(data, "just_etf_ticker") or _get_str(data, "just_etf"),
            nav_price=_get_float(data, "nav_price"),
            fifty_two_week_high=_get_float(data, "fifty_two_week_high"),
            fifty_two_week_low=_get_float(data, "fifty_two_week_low"),
            fifty_two_week_change_pct=_get_float(data, "fifty_two_week_change_pct"),
            fifty_day_average=_get_float(data, "fifty_day_average"),
            two_hundred_day_average=_get_float(data, "two_hundred_day_average"),
            average_volume=_get_int(data, "average_volume"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class StockDetails(DictAccessMixin):
    """Fundamental metrics and valuation ratios for a stock ticker."""

    market_cap: float | None = None
    pe_ratio: float | None = None
    forward_pe: float | None = None
    dividend_yield_pct: float | None = None
    fifty_two_week_high: float | None = None
    fifty_two_week_low: float | None = None
    fifty_two_week_change_pct: float | None = None
    fifty_day_average: float | None = None
    two_hundred_day_average: float | None = None
    average_volume: int | None = None
    sector: str | None = None
    industry: str | None = None
    country: str | None = None
    price_to_book: float | None = None
    peg_ratio: float | None = None
    beta: float | None = None
    profit_margins_pct: float | None = None
    gross_margins_pct: float | None = None
    operating_margins_pct: float | None = None
    revenue_growth_pct: float | None = None
    earnings_growth_pct: float | None = None
    return_on_equity_pct: float | None = None
    return_on_assets_pct: float | None = None
    total_debt_to_equity: float | None = None
    free_cashflow: float | None = None
    short_ratio: float | None = None
    target_mean_price: float | None = None
    target_high_price: float | None = None
    target_low_price: float | None = None
    number_of_analyst_opinions: int | None = None
    recommendation_key: str | None = None
    eps_trailing_ttm: float | None = None
    eps_forward: float | None = None
    currency: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ETFDetails(DictAccessMixin):
    """Consolidates ETF holdings, sector exposure, country exposure, and fund metadata."""

    holdings: list[Holding]
    sector_breakdown: list[SectorExposure]
    country_breakdown: list[CountryExposure]
    ter_pct: float | None = None
    inception_date: str | None = None
    fund_size_eur_m: float | None = None
    holdings_count: int | None = None
    replication: str | None = None
    distribution_policy: str | None = None
    index_name: str | None = None
    fund_currency: str | None = None
    volatility_1y_pct: float | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ETFDetails:
        return cls(
            holdings=[
                Holding.from_dict(item)
                for item in data.get("holdings", [])
                if isinstance(item, dict)
            ],
            sector_breakdown=[
                SectorExposure.from_dict(item)
                for item in data.get("sector_breakdown", [])
                if isinstance(item, dict)
            ],
            country_breakdown=[
                CountryExposure.from_dict(item)
                for item in data.get("country_breakdown", [])
                if isinstance(item, dict)
            ],
            ter_pct=_get_float(data, "ter_pct"),
            inception_date=_get_str(data, "inception_date"),
            fund_size_eur_m=_get_float(data, "fund_size_eur_m"),
            holdings_count=_get_int(data, "holdings_count"),
            replication=_get_str(data, "replication"),
            distribution_policy=_get_str(data, "distribution_policy"),
            index_name=_get_str(data, "index_name"),
            fund_currency=_get_str(data, "fund_currency"),
            volatility_1y_pct=_get_float(data, "volatility_1y_pct"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)