"""Infrastructure client for scraping ETF details, holdings, and exposures from JustETF."""

from __future__ import annotations

import email.utils
import re
import time
from datetime import UTC, datetime
from typing import Any

import requests
from bs4 import BeautifulSoup, Tag
from core_lib.logger import logger
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from data.common.constants import COUNTRY_ALIASES
from data.models import CountryExposure, ETFDetails, Holding, SectorExposure


class JustETFScrapeError(Exception):
    """Raised when scraping or parsing JustETF data fails."""

    pass


class JustETFClient:
    """Scraper client for retrieving ETF holdings, sector and country exposures,
    Total Expense Ratio (TER), and fund metadata from JustETF profile pages.
    """

    BASE_URL: str = "https://www.justetf.com/en/etf-profile.html"
    DEFAULT_HEADERS: dict[str, str] = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    MAX_RETRY_AFTER_SECONDS: float = 10.0
    DEFAULT_RETRY_AFTER_SECONDS: float = 1.0

    def __init__(self, timeout: float = 10.0, max_retries: int = 3) -> None:
        """Initializes the JustETF client with configurable timeout and retry adapters.

        Args:
            timeout: Request timeout in seconds.
            max_retries: Maximum number of connection retries for transient errors.
        """
        self.timeout: float = timeout
        self.max_retries: int = max_retries
        self.session: requests.Session = requests.Session()
        self.session.headers.update(self.DEFAULT_HEADERS)

        retries: Retry = Retry(
            total=max_retries,
            backoff_factor=1.0,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False,
        )
        adapter: HTTPAdapter = HTTPAdapter(max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _parse_retry_after(self, retry_after_header: str | None) -> float:
        """Parse Retry-After header safely, supporting integer seconds or HTTP-date.

        Capped at MAX_RETRY_AFTER_SECONDS and clamped to non-negative floats.
        """
        if not retry_after_header:
            return self.DEFAULT_RETRY_AFTER_SECONDS

        cleaned_header: str = retry_after_header.strip()
        try:
            seconds = float(cleaned_header)
            return min(max(0.0, seconds), self.MAX_RETRY_AFTER_SECONDS)
        except ValueError:
            pass

        try:
            target_dt: datetime = email.utils.parsedate_to_datetime(cleaned_header)
            now_dt: datetime = datetime.now(UTC)
            if target_dt.tzinfo is None:
                target_dt = target_dt.replace(tzinfo=UTC)
            delta: float = (target_dt - now_dt).total_seconds()
            return min(max(0.0, delta), self.MAX_RETRY_AFTER_SECONDS)
        except Exception as e:
            logger.warning(
                f"Failed to parse Retry-After header value '{retry_after_header}': {e}. "
                f"Defaulting to {self.DEFAULT_RETRY_AFTER_SECONDS}s backoff."
            )
            return self.DEFAULT_RETRY_AFTER_SECONDS

    def get_etf_details(self, isin: str) -> ETFDetails:
        """Fetches and parses comprehensive ETF details for a given ISIN from JustETF.

        Args:
            isin: International Securities Identification Number of the ETF.

        Returns:
            An ETFDetails instance containing holdings, exposures, TER, and metadata.

        Raises:
            JustETFScrapeError: If network requests fail or parsing encounters an error.
        """
        url: str = f"{self.BASE_URL}?isin={isin}"
        response: requests.Response | None = None
        attempts: int = 0
        max_attempts: int = max(1, self.max_retries)

        while attempts < max_attempts:
            attempts += 1
            try:
                response = self.session.get(url, timeout=self.timeout)
            except requests.RequestException as e:
                raise JustETFScrapeError(
                    f"Network error fetching JustETF page for {isin}: {e}"
                ) from e

            if response.status_code == 429:
                if attempts >= max_attempts:
                    logger.warning(
                        f"Rate limit exceeded (HTTP 429) for ISIN {isin} after {attempts} attempts."
                    )
                    break
                sleep_seconds: float = self._parse_retry_after(
                    response.headers.get("Retry-After")
                )
                logger.warning(
                    f"Rate limited (HTTP 429) fetching ISIN {isin}. "
                    f"Sleeping for {sleep_seconds:.1f}s before retry ({attempts}/{max_attempts})."
                )
                time.sleep(sleep_seconds)
                continue

            break

        if response is None or response.status_code != 200:
            status = response.status_code if response is not None else "unknown"
            raise JustETFScrapeError(
                f"HTTP error {status} while fetching ISIN {isin}"
            )

        try:
            soup: BeautifulSoup = BeautifulSoup(response.text, "html.parser")
            holdings: list[Holding] = self._parse_holdings(soup)
            sectors: list[SectorExposure] = self._parse_sectors(soup)
            countries: list[CountryExposure] = self._parse_countries(soup)
            ter_pct: float | None = self._parse_ter(soup)
            fund_meta: dict[str, Any] = self._parse_fund_metadata(soup)

            return ETFDetails(
                holdings=holdings,
                sector_breakdown=sectors,
                country_breakdown=countries,
                ter_pct=ter_pct,
                inception_date=fund_meta.get("inception_date"),
                fund_size_eur_m=fund_meta.get("fund_size_eur_m"),
                holdings_count=fund_meta.get("holdings_count"),
                replication=fund_meta.get("replication"),
                distribution_policy=fund_meta.get("distribution_policy"),
                index_name=fund_meta.get("index_name"),
                fund_currency=fund_meta.get("fund_currency"),
                volatility_1y_pct=fund_meta.get("volatility_1y_pct"),
            )
        except JustETFScrapeError:
            raise
        except Exception as e:
            raise JustETFScrapeError(
                f"Failed to parse JustETF response for ISIN {isin}: {e}"
            ) from e

    def _parse_fund_metadata(self, soup: BeautifulSoup) -> dict[str, Any]:
        """Extracts fund-level metadata from the JustETF key facts section.

        Args:
            soup: Parsed BeautifulSoup object of the ETF profile page.

        Returns:
            A dictionary containing extracted metadata fields (inception date, replication, etc.).
        """
        meta: dict[str, Any] = {}
        text: str = soup.get_text(separator="\n", strip=True)

        patterns: dict[str, str] = {
            "inception_date": r"Inception(?:/\s*Listing)?\s*Date\s*\n([^\n]+)",
            "replication": r"Replication\s*\n([^\n]+)",
            "distribution_policy": r"Distribution policy\s*\n([^\n]+)",
            "index_name": r"Index\s*\n([^\n]+)",
            "fund_currency": r"Fund currency\s*\n([^\n]+)",
        }
        for key, pattern in patterns.items():
            m: re.Match[str] | None = re.search(pattern, text)
            if m:
                val: str = m.group(1).strip()
                if key == "inception_date" and not re.search(r"\d{4}", val):
                    continue  # Skip invalid or non-date strings
                meta[key] = val

        fs_match: re.Match[str] | None = re.search(r"Fund size\s*\n?EUR\s*([\d,]+)\s*m", text)
        if fs_match:
            raw_fs = fs_match.group(1).replace(",", "")
            try:
                meta["fund_size_eur_m"] = float(raw_fs)
            except ValueError as e:
                logger.warning(
                    f"Failed to parse 'fund_size_eur_m' with raw value '{raw_fs}': {e}"
                )

        hc_match: re.Match[str] | None = re.search(r"Holdings\s*\n([\d,]+)", text)
        if not hc_match:
            hc_match = re.search(r"out of ([\d,]+)", text)
        if hc_match:
            raw_hc = hc_match.group(1).replace(",", "")
            try:
                meta["holdings_count"] = int(raw_hc)
            except ValueError as e:
                logger.warning(
                    f"Failed to parse 'holdings_count' with raw value '{raw_hc}': {e}"
                )

        vol_match: re.Match[str] | None = re.search(
            r"Volatility 1 year[^\n]*\n?([\d.,]+)\s*%", text
        )
        if vol_match:
            raw_vol = vol_match.group(1).replace(",", ".")
            try:
                meta["volatility_1y_pct"] = float(raw_vol)
            except ValueError as e:
                logger.warning(
                    f"Failed to parse 'volatility_1y_pct' with raw value '{raw_vol}': {e}"
                )

        return meta

    def _extract_isin_from_element(self, element: Tag | Any) -> str:
        """Extracts an ISIN code from HTML anchor hrefs or text content within a tag.

        Args:
            element: BeautifulSoup Tag element representing a table row or container.

        Returns:
            The extracted ISIN string, or an empty string if not found.
        """
        if not element:
            return ""

        anchors: list[Tag] = [element] if element.name == "a" else []
        anchors.extend(element.find_all("a"))

        for link in anchors:
            href: str = str(link.get("href", ""))
            match: re.Match[str] | None = re.search(r"([A-Z]{2}[A-Z0-9]{9}\d)", href.upper())
            if match:
                return match.group(1)

        match_raw: re.Match[str] | None = re.search(
            r"([A-Z]{2}[A-Z0-9]{9}\d)", str(element).upper()
        )
        if match_raw:
            return match_raw.group(1)

        return ""

    def _extract_holdings_from_rows(self, rows: list[Tag]) -> list[Holding]:
        """Extracts Holding domain objects from HTML table row elements.

        Args:
            rows: List of BeautifulSoup Tag elements representing table rows.

        Returns:
            List of parsed Holding objects with valid ISINs and weight percentages.
        """
        holdings: list[Holding] = []
        for row in rows:
            cols: list[Tag] = row.find_all(["td", "th"])
            if len(cols) >= 2:
                name: str = cols[0].get_text(strip=True)
                if not name or name.lower() in [
                    "name",
                    "holding",
                    "weight",
                    "components",
                ]:
                    continue

                isin: str = self._extract_isin_from_element(row)
                if not isin:
                    continue  # Skip holdings without a valid ISIN to comply with type contracts

                weight_text: str = cols[-1].get_text(strip=True)
                match: re.Match[str] | None = re.search(r"(\d+[.,]?\d*)\s*%", weight_text)
                if match:
                    weight_pct: float = float(match.group(1).replace(",", "."))
                    holdings.append(
                        Holding(
                            name=name,
                            isin=isin,
                            weight_pct=weight_pct,
                            just_etf_ticker=None,
                        )
                    )
        return holdings

    def _parse_holdings(self, soup: BeautifulSoup) -> list[Holding]:
        """Parses the top holdings table from the ETF profile page.

        Args:
            soup: Parsed BeautifulSoup object of the ETF profile page.

        Returns:
            A list of Holding domain objects.
        """
        # Tier 1: Look for data-testid rows
        rows: list[Tag] = soup.find_all(
            "tr", {"data-testid": lambda x: bool(x and "top-holdings_row" in str(x))}
        )
        if rows:
            holdings: list[Holding] = self._extract_holdings_from_rows(rows)
            if holdings:
                return holdings

        # Tier 2: Look for table with id="top-holdings"
        container_res: Any = soup.find("table", {"id": "top-holdings"})
        container: Tag | None = container_res if isinstance(container_res, Tag) else None
        if isinstance(container, Tag):
            holdings = self._extract_holdings_from_rows(container.find_all("tr"))
            if holdings:
                return holdings

        # Tier 3: Heuristic fallback loop disambiguating against decoy tables
        for table in soup.find_all("table"):
            header_text: str = table.get_text().lower()
            if (
                ("top holdings" in header_text or "holding" in header_text)
                and "sector" not in header_text
                and "country" not in header_text
            ):
                candidate_holdings: list[Holding] = self._extract_holdings_from_rows(
                    table.find_all("tr")
                )
                if candidate_holdings:
                    return candidate_holdings

        return []

    def _extract_sectors_from_rows(self, rows: list[Tag]) -> list[SectorExposure]:
        """Extracts SectorExposure domain objects from HTML table row elements.

        Args:
            rows: List of BeautifulSoup Tag elements representing table rows.

        Returns:
            List of parsed SectorExposure objects with normalized percentages.
        """
        sectors: list[SectorExposure] = []
        for row in rows:
            cols: list[Tag] = row.find_all(["td", "th"])
            if len(cols) >= 2:
                sector_name: str = cols[0].get_text(strip=True)
                if not sector_name or sector_name.lower() in [
                    "sector",
                    "name",
                    "breakdown",
                    "sector breakdown",
                ]:
                    continue

                weight_text: str = cols[-1].get_text(strip=True)
                match: re.Match[str] | None = re.search(r"(\d+[.,]?\d*)\s*%", weight_text)
                if match:
                    weight_pct: float = float(match.group(1).replace(",", "."))
                    sectors.append(
                        SectorExposure(
                            sector_name=sector_name,
                            weight_pct=weight_pct,
                        )
                    )
        return sectors

    def _parse_sectors(self, soup: BeautifulSoup) -> list[SectorExposure]:
        """Parses the sector breakdown table from the ETF profile page.

        Args:
            soup: Parsed BeautifulSoup object of the ETF profile page.

        Returns:
            A list of SectorExposure domain objects.
        """
        # Tier 1: Look for data-testid rows
        rows: list[Tag] = soup.find_all(
            "tr",
            {
                "data-testid": lambda x: bool(
                    x and "sector" in str(x).lower() and "row" in str(x).lower()
                )
            },
        )
        if rows:
            sectors: list[SectorExposure] = self._extract_sectors_from_rows(rows)
            if sectors:
                return sectors

        # Tier 2: Look for div container with id="sectors"
        container_res: Any = soup.find("div", {"id": "sectors"})
        container: Tag | None = container_res if isinstance(container_res, Tag) else None
        if isinstance(container, Tag):
            sectors = self._extract_sectors_from_rows(container.find_all("tr"))
            if sectors:
                return sectors

        # Tier 3: Heuristic fallback loop disambiguating against decoy tables
        for table in soup.find_all("table"):
            header_text: str = table.get_text().lower()
            if "sector" in header_text and "country" not in header_text:
                candidate_sectors: list[SectorExposure] = self._extract_sectors_from_rows(
                    table.find_all("tr")
                )
                if candidate_sectors:
                    return candidate_sectors

        return []

    def _extract_countries_from_rows(self, rows: list[Tag]) -> list[CountryExposure]:
        """Extracts CountryExposure domain objects from HTML table row elements.

        Args:
            rows: List of BeautifulSoup Tag elements representing table rows.

        Returns:
            List of parsed CountryExposure objects with canonical country mapping.
        """
        countries: list[CountryExposure] = []
        for row in rows:
            cols: list[Tag] = row.find_all(["td", "th"])
            if len(cols) >= 2:
                country_name: str = cols[0].get_text(strip=True)
                if not country_name or country_name.lower() in [
                    "country",
                    "countries",
                    "region",
                    "name",
                    "region breakdown",
                    "country breakdown",
                ]:
                    continue

                weight_text: str = cols[-1].get_text(strip=True)
                match: re.Match[str] | None = re.search(r"(\d+[.,]?\d*)\s*%", weight_text)
                if match:
                    weight_pct: float = float(match.group(1).replace(",", "."))
                    normalized_name: str = COUNTRY_ALIASES.get(country_name.upper(), country_name)
                    countries.append(
                        CountryExposure(
                            country_name=normalized_name,
                            weight_pct=weight_pct,
                        )
                    )
        return countries

    def _parse_countries(self, soup: BeautifulSoup) -> list[CountryExposure]:
        """Parses the country or region breakdown table from the ETF profile page.

        Args:
            soup: Parsed BeautifulSoup object of the ETF profile page.

        Returns:
            A list of CountryExposure domain objects.
        """
        # Tier 1: Look for data-testid rows
        rows: list[Tag] = soup.find_all(
            "tr",
            {
                "data-testid": lambda x: bool(
                    x and "countr" in str(x).lower() and "row" in str(x).lower()
                )
            },
        )
        if rows:
            countries: list[CountryExposure] = self._extract_countries_from_rows(rows)
            if countries:
                return countries

        # Tier 2: Look for div container with id="countries"
        container_res: Any = soup.find("div", {"id": "countries"})
        container: Tag | None = container_res if isinstance(container_res, Tag) else None
        if isinstance(container, Tag):
            countries = self._extract_countries_from_rows(container.find_all("tr"))
            if countries:
                return countries

        # Tier 3: Heuristic fallback loop disambiguating against decoy tables
        for table in soup.find_all("table"):
            header_text: str = table.get_text().lower()
            if (
                "country" in header_text
                or "countries" in header_text
                or "region" in header_text
            ) and "sector" not in header_text:
                candidate_countries: list[CountryExposure] = self._extract_countries_from_rows(
                    table.find_all("tr")
                )
                if candidate_countries:
                    return candidate_countries

        return []

    def _parse_ter(self, soup: BeautifulSoup) -> float | None:
        """Parses the Total Expense Ratio (TER) percentage from the ETF profile page.

        Args:
            soup: Parsed BeautifulSoup object of the ETF profile page.

        Returns:
            The TER percentage as a float, or None if not found.
        """
        for label in soup.find_all(
            string=re.compile(r"\bTER\b|\bTotal\s*Expense\s*Ratio\b", re.IGNORECASE)
        ):
            parent: Tag | None = label.parent
            if parent:
                search_scope: Tag = parent.parent if parent.parent else parent
                text_content: str = search_scope.get_text(separator=" ")
                match: re.Match[str] | None = re.search(
                    r"(?:\bTER\b|\bTotal\s*Expense\s*Ratio\b)[^%]*?(\d+[.,]?\d*)\s*%",
                    text_content,
                    re.IGNORECASE,
                )
                if match:
                    return float(match.group(1).replace(",", "."))

        fallback_match: re.Match[str] | None = re.search(
            r"(?:\bTER\b|\bTotal\s*Expense\s*Ratio\b)[^%]*?(\d+[.,]?\d*)\s*%",
            soup.get_text(separator=" "),
            re.IGNORECASE,
        )
        if fallback_match:
            return float(fallback_match.group(1).replace(",", "."))

        return None
