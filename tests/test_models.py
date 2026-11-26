from __future__ import annotations

from datetime import datetime, timezone

import pytest

from data.models import (
    CountryExposure,
    ETFDetails,
    ETFMarketData,
    Holding,
    Quotation,
    SectorExposure,
    StockDetails,
    _get_float,
    _get_int,
    _get_str,
)


def test_holding_from_dict_validation() -> None:
    with pytest.raises(ValueError, match="missing mandatory property 'isin'"):
        Holding.from_dict({"name": "Apple", "weight_pct": 5.0})

    with pytest.raises(ValueError, match="missing mandatory property 'name'"):
        Holding.from_dict({"isin": "US0378331005", "weight_pct": 5.0})

    with pytest.raises(KeyError, match="missing mandatory key 'weight_pct'"):
        Holding.from_dict({"isin": "US0378331005", "name": "Apple"})

    holding = Holding.from_dict(
        {"isin": "US0378331005", "name": "Apple", "weight_pct": "5.5", "just_etf_ticker": "AAPL"}
    )
    assert holding.isin == "US0378331005"
    assert holding.name == "Apple"
    assert holding.weight_pct == 5.5
    assert holding.just_etf_ticker == "AAPL"


def test_sector_exposure_validation() -> None:
    with pytest.raises(ValueError, match="missing mandatory property 'sector_name'"):
        SectorExposure.from_dict({"weight_pct": 10.0})

    with pytest.raises(KeyError, match="missing mandatory key 'weight_pct'"):
        SectorExposure.from_dict({"sector_name": "Tech"})

    sec = SectorExposure.from_dict({"sector_name": "Tech", "weight_pct": "45.2"})
    assert sec.sector_name == "Tech"
    assert sec.weight_pct == 45.2


def test_country_exposure_validation() -> None:
    with pytest.raises(ValueError, match="missing mandatory property 'country_name'"):
        CountryExposure.from_dict({"weight_pct": 10.0})

    with pytest.raises(KeyError, match="missing mandatory key 'weight_pct'"):
        CountryExposure.from_dict({"country_name": "USA"})

    country = CountryExposure.from_dict({"country_name": "  United States  ", "weight_pct": "60.0"})
    assert country.country_name == "United States"
    assert country.weight_pct == 60.0


def test_dict_access_mixin() -> None:
    quote = Quotation(price=100.0, currency="EUR")
    assert quote["price"] == 100.0
    assert quote["currency"] == "EUR"
    with pytest.raises(AttributeError):
        _ = quote["non_existent_key"]


def test_quotation_to_dict() -> None:
    dt = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    quote = Quotation(
        price=150.0, currency="USD", timestamp=dt, native_price=150.0, native_currency="USD"
    )
    d = quote.to_dict()
    assert d["price"] == 150.0
    assert d["currency"] == "USD"
    assert d["timestamp"] == dt.isoformat()
    assert d["native_price"] == 150.0
    assert d["native_currency"] == "USD"


def test_etf_market_data_from_dict() -> None:
    data = {
        "price": "105.5",
        "currency": "EUR",
        "just_etf_ticker": "EXXT",
        "nav_price": "105.0",
        "fifty_two_week_high": "110.0",
        "fifty_two_week_low": "90.0",
        "fifty_two_week_change_pct": "15.0",
        "fifty_day_average": "102.0",
        "two_hundred_day_average": "98.0",
        "average_volume": "100000",
    }
    emd = ETFMarketData.from_dict(data)
    assert emd.price == 105.5
    assert emd.native_currency == "EUR"
    assert emd.just_etf_ticker == "EXXT"
    assert emd.nav_price == 105.0
    assert emd.average_volume == 100000
    assert emd.to_dict() is not None


def test_stock_details_to_dict() -> None:
    stock = StockDetails(market_cap=1000.0, currency="USD")
    assert stock.to_dict()["market_cap"] == 1000.0


def test_etf_details_from_and_to_dict() -> None:
    original = ETFDetails(
        holdings=[Holding(name="Apple", isin="US0378331005", weight_pct=4.5)],
        sector_breakdown=[SectorExposure(sector_name="Tech", weight_pct=100.0)],
        country_breakdown=[CountryExposure(country_name="USA", weight_pct=100.0)],
        ter_pct=0.15,
        inception_date="2020-01-01",
        fund_size_eur_m=500.0,
        holdings_count=100,
        replication="Physical",
        distribution_policy="Accumulating",
        index_name="S&P 500",
        fund_currency="USD",
        volatility_1y_pct=12.5,
    )
    serialized = original.to_dict()
    restored = ETFDetails.from_dict(serialized)
    assert restored.ter_pct == original.ter_pct
    assert restored.holdings[0].isin == original.holdings[0].isin
    assert restored.sector_breakdown[0].weight_pct == 100.0
    assert restored.volatility_1y_pct == 12.5


def test_holding_sector_country_to_dict() -> None:
    holding = Holding(name="Apple", isin="US0378331005", weight_pct=5.5, just_etf_ticker="AAPL")
    d = holding.to_dict()
    assert d["name"] == "Apple"
    assert d["isin"] == "US0378331005"
    assert d["weight_pct"] == 5.5
    assert d["just_etf_ticker"] == "AAPL"

    sector = SectorExposure(sector_name="Tech", weight_pct=30.0)
    sd = sector.to_dict()
    assert sd["sector_name"] == "Tech"
    assert sd["weight_pct"] == 30.0

    country = CountryExposure(country_name="USA", weight_pct=60.0)
    cd = country.to_dict()
    assert cd["country_name"] == "USA"
    assert cd["weight_pct"] == 60.0


def test_helper_parsers() -> None:
    d = {"f": "12.34", "i": "42", "s": " hello ", "bad_f": "abc", "bad_i": "xyz"}
    assert _get_float(d, "f") == 12.34
    assert _get_float(d, "missing", 5.0) == 5.0
    assert _get_float(d, "bad_f") is None

    assert _get_int(d, "i") == 42
    assert _get_int(d, "missing", 10) == 10
    assert _get_int(d, "bad_i") is None

    assert _get_str(d, "s") == "hello"
    assert _get_str(d, "missing", "default") == "default"
    assert _get_str(d, "bad_f") == "abc"


def test_domain_range_bounds_invariants() -> None:
    # Holding bounds
    with pytest.raises(ValueError, match="between 0.0 and 100.0"):
        Holding(name="Apple", isin="US0378331005", weight_pct=-1.0)
    with pytest.raises(ValueError, match="between 0.0 and 100.0"):
        Holding(name="Apple", isin="US0378331005", weight_pct=100.1)
    with pytest.raises(ValueError, match="between 0.0 and 100.0"):
        Holding.from_dict({"name": "Apple", "isin": "US0378331005", "weight_pct": -5.0})
    with pytest.raises(ValueError, match="between 0.0 and 100.0"):
        Holding.from_dict({"name": "Apple", "isin": "US0378331005", "weight_pct": 105.0})
    with pytest.raises(ValueError, match="valid float"):
        Holding.from_dict({"name": "Apple", "isin": "US0378331005", "weight_pct": "invalid"})

    # SectorExposure bounds
    with pytest.raises(ValueError, match="between 0.0 and 100.0"):
        SectorExposure(sector_name="Tech", weight_pct=-0.5)
    with pytest.raises(ValueError, match="between 0.0 and 100.0"):
        SectorExposure(sector_name="Tech", weight_pct=105.0)
    with pytest.raises(ValueError, match="between 0.0 and 100.0"):
        SectorExposure.from_dict({"sector_name": "Tech", "weight_pct": -5.0})
    with pytest.raises(ValueError, match="between 0.0 and 100.0"):
        SectorExposure.from_dict({"sector_name": "Tech", "weight_pct": 150.0})
    with pytest.raises(ValueError, match="valid float"):
        SectorExposure.from_dict({"sector_name": "Tech", "weight_pct": "invalid"})

    # CountryExposure bounds
    with pytest.raises(ValueError, match="between 0.0 and 100.0"):
        CountryExposure(country_name="USA", weight_pct=-0.1)
    with pytest.raises(ValueError, match="between 0.0 and 100.0"):
        CountryExposure(country_name="USA", weight_pct=100.5)
    with pytest.raises(ValueError, match="between 0.0 and 100.0"):
        CountryExposure.from_dict({"country_name": "USA", "weight_pct": -1.0})
    with pytest.raises(ValueError, match="between 0.0 and 100.0"):
        CountryExposure.from_dict({"country_name": "USA", "weight_pct": 101.0})
    with pytest.raises(ValueError, match="valid float"):
        CountryExposure.from_dict({"country_name": "USA", "weight_pct": "invalid"})

    # Quotation bounds
    with pytest.raises(ValueError, match="must be non-negative"):
        Quotation(price=-10.0, currency="USD")
    with pytest.raises(ValueError, match="native_price must be non-negative"):
        Quotation(price=10.0, currency="USD", native_price=-5.0)

    # ETFMarketData bounds
    with pytest.raises(ValueError, match="price must be non-negative"):
        ETFMarketData(price=-1.0)
    with pytest.raises(ValueError, match="nav_price must be non-negative"):
        ETFMarketData(nav_price=-10.0)
    with pytest.raises(ValueError, match="average_volume must be non-negative"):
        ETFMarketData(average_volume=-50)
