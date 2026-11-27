"""Infrastructure client for fetching market data and asset details using yfinance."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any, TypedDict, cast

import pandas as pd
import yfinance as yf
from core_lib.logger import logger

from data.models import ETFMarketData, Quotation, StockDetails


class YahooTickerInfo(TypedDict, total=False):
    """Typed dictionary schema representing fields extracted from yfinance.Ticker.info."""

    currency: str
    financialCurrency: str
    marketCap: float | int
    trailingPE: float
    forwardPE: float
    dividendYield: float
    fiftyTwoWeekHigh: float
    fiftyTwoWeekLow: float
    fiftyTwoWeekChangePercent: float
    fiftyDayAverage: float
    twoHundredDayAverage: float
    averageVolume: int
    sector: str
    industry: str
    country: str
    priceToBook: float
    pegRatio: float
    beta: float
    profitMargins: float
    grossMargins: float
    operatingMargins: float
    revenueGrowth: float
    earningsGrowth: float
    returnOnEquity: float
    returnOnAssets: float
    debtToEquity: float
    freeCashflow: float | int
    shortRatio: float
    targetMeanPrice: float
    targetHighPrice: float
    targetLowPrice: float
    numberOfAnalystOpinions: int
    recommendationKey: str
    trailingEps: float
    forwardEps: float
    navPrice: float


class YahooHistoryRow(TypedDict, total=False):
    """Typed dictionary schema representing a single historical quotation row."""

    Open: float
    High: float
    Low: float
    Close: float
    Volume: int
    Dividends: float
    StockSplits: float


class YahooFinanceError(Exception):
    """Raised when fetching data from Yahoo Finance fails."""

    pass


class YahooFinanceClient:
    """Client for retrieving quotations, stock fundamentals, and ETF market data via yfinance."""

    def __init__(self) -> None:
        pass

    def _extract_ticker_info(self, t: yf.Ticker, ticker: str) -> YahooTickerInfo:
        """Extract and safely wrap yfinance.Ticker.info dictionary."""
        try:
            raw_info: Any = t.info
        except Exception as e:
            raise YahooFinanceError(
                f"Failed to retrieve info for ticker '{ticker}': {e}"
            ) from e

        if isinstance(raw_info, dict):
            return cast(YahooTickerInfo, raw_info)

        logger.warning(
            f"Ticker '{ticker}' returned non-dict info payload: {type(raw_info)}"
        )
        return cast(YahooTickerInfo, raw_info)

    def _extract_history_row(self, history: pd.DataFrame, ticker: str) -> YahooHistoryRow:
        """Validate and extract the latest historical row from yfinance DataFrame."""
        if not isinstance(history, pd.DataFrame) or history.empty:
            raise YahooFinanceError(f"No price history returned for ticker '{ticker}'.")

        row_series = history.iloc[-1]
        row_dict: dict[str, Any] = row_series.to_dict()
        return cast(YahooHistoryRow, row_dict)

    def _fetch_ticker_market_data(self, ticker: str) -> tuple[float, str, YahooTickerInfo]:
        """Helper to fetch info, history, price, and currency for a ticker efficiently."""
        try:
            t: yf.Ticker = yf.Ticker(ticker)
            info: YahooTickerInfo = self._extract_ticker_info(t, ticker)

            history: pd.DataFrame = t.history(period="1d")
            latest_row: YahooHistoryRow = self._extract_history_row(history, ticker)

            raw_close = latest_row.get("Close")
            price: float | None = _safe_float(raw_close)
            if price is None:
                logger.error(
                    f"Invalid or missing close price for ticker '{ticker}'. "
                    f"Raw close value: {raw_close}"
                )
                raise YahooFinanceError(
                    f"Invalid or missing close price for ticker '{ticker}'."
                )

            currency_str: Any = info.get("currency")
            if not currency_str:
                logger.error(
                    f"Currency information is missing for ticker '{ticker}'. "
                    f"Available keys: {list(info.keys())}"
                )
                raise YahooFinanceError(
                    f"Currency information is missing for ticker '{ticker}'."
                )
            currency: str = str(currency_str).strip().upper()

            fin_currency: Any = info.get("financialCurrency")
            if fin_currency:
                fin_curr_norm: str = str(fin_currency).strip().upper()
                if fin_curr_norm != currency:
                    logger.warning(
                        f"Currency mismatch detected for ticker '{ticker}': "
                        f"trading currency is '{currency}' while financial currency "
                        f"is '{fin_curr_norm}'."
                    )

            return price, currency, info
        except YahooFinanceError:
            raise
        except Exception as e:
            raise YahooFinanceError(
                f"Failed to fetch market data for ticker '{ticker}': {e}"
            ) from e

    def get_quotation(self, ticker: str) -> Quotation:
        """Fetches the latest quotation for a given ticker symbol."""
        price: float
        currency: str
        price, currency, _ = self._fetch_ticker_market_data(ticker)
        return Quotation(
            price=price,
            currency=currency,
            timestamp=datetime.now(UTC),
            native_price=price,
            native_currency=currency,
        )

    def get_stock_details(self, ticker: str) -> StockDetails:
        """Fetches fundamental metrics and valuation ratios for a stock ticker."""
        try:
            t: yf.Ticker = yf.Ticker(ticker)
            info: YahooTickerInfo = self._extract_ticker_info(t, ticker)

            change_52w: Any = info.get("52WeekChange")
            if change_52w is None:
                change_52w = info.get("fiftyTwoWeekChangePercent")

            return StockDetails(
                market_cap=_safe_float(info.get("marketCap")),
                pe_ratio=_safe_float(info.get("trailingPE")),
                forward_pe=_safe_float(info.get("forwardPE")),
                dividend_yield_pct=_safe_float(info.get("dividendYield"), scale=100.0),
                fifty_two_week_high=_safe_float(info.get("fiftyTwoWeekHigh")),
                fifty_two_week_low=_safe_float(info.get("fiftyTwoWeekLow")),
                fifty_two_week_change_pct=_safe_float(change_52w, scale=100.0),
                fifty_day_average=_safe_float(info.get("fiftyDayAverage")),
                two_hundred_day_average=_safe_float(info.get("twoHundredDayAverage")),
                average_volume=_safe_int(info.get("averageVolume")),
                sector=_safe_str(info.get("sector")),
                industry=_safe_str(info.get("industry")),
                country=_safe_str(info.get("country")),
                price_to_book=_safe_float(info.get("priceToBook")),
                peg_ratio=_safe_float(info.get("pegRatio")),
                beta=_safe_float(info.get("beta")),
                profit_margins_pct=_safe_float(info.get("profitMargins"), scale=100.0),
                gross_margins_pct=_safe_float(info.get("grossMargins"), scale=100.0),
                operating_margins_pct=_safe_float(info.get("operatingMargins"), scale=100.0),
                revenue_growth_pct=_safe_float(info.get("revenueGrowth"), scale=100.0),
                earnings_growth_pct=_safe_float(info.get("earningsGrowth"), scale=100.0),
                return_on_equity_pct=_safe_float(info.get("returnOnEquity"), scale=100.0),
                return_on_assets_pct=_safe_float(info.get("returnOnAssets"), scale=100.0),
                total_debt_to_equity=_safe_float(info.get("debtToEquity")),
                free_cashflow=_safe_float(info.get("freeCashflow")),
                short_ratio=_safe_float(info.get("shortRatio")),
                target_mean_price=_safe_float(info.get("targetMeanPrice")),
                target_high_price=_safe_float(info.get("targetHighPrice")),
                target_low_price=_safe_float(info.get("targetLowPrice")),
                number_of_analyst_opinions=_safe_int(info.get("numberOfAnalystOpinions")),
                recommendation_key=_safe_str(info.get("recommendationKey")),
                eps_trailing_ttm=_safe_float(info.get("trailingEps")),
                eps_forward=_safe_float(info.get("forwardEps")),
                currency=_safe_str(info.get("currency")),
            )
        except YahooFinanceError:
            raise
        except Exception as e:
            raise YahooFinanceError(
                f"Failed to fetch stock details for ticker '{ticker}': {e}"
            ) from e

    def get_etf_market_data(self, ticker: str) -> ETFMarketData:
        """Fetches market pricing and moving averages for an ETF ticker efficiently."""
        price: float
        currency: str
        info: YahooTickerInfo
        price, currency, info = self._fetch_ticker_market_data(ticker)

        change_52w: Any = info.get("52WeekChange")
        if change_52w is None:
            change_52w = info.get("fiftyTwoWeekChangePercent")

        return ETFMarketData(
            price=price,
            native_currency=currency,
            just_etf_ticker=None,
            nav_price=_safe_float(info.get("navPrice")),
            fifty_two_week_high=_safe_float(info.get("fiftyTwoWeekHigh")),
            fifty_two_week_low=_safe_float(info.get("fiftyTwoWeekLow")),
            fifty_two_week_change_pct=_safe_float(change_52w, scale=100.0),
            fifty_day_average=_safe_float(info.get("fiftyDayAverage")),
            two_hundred_day_average=_safe_float(info.get("twoHundredDayAverage")),
            average_volume=_safe_int(info.get("averageVolume")),
        )


def _safe_float(val: Any, scale: float = 1.0) -> float | None:
    if val is None or val == "":
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return f * scale
    except (ValueError, TypeError):
        return None


def _safe_int(val: Any) -> int | None:
    if val is None or val == "":
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return int(f)
    except (ValueError, TypeError):
        return None


def _safe_str(val: Any) -> str | None:
    if val is None or val == "":
        return None
    val_str = str(val).strip()
    if not val_str or val_str.lower() in ("nan", "none", "null"):
        return None
    return val_str