"""
SEC Agent — fetches recent SEC filings for a given ticker via the EDGAR full-text
search API and converts them to :class:`Document` objects.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import httpx

from models import Document

logger = logging.getLogger(__name__)

_EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
_DEFAULT_FORM_TYPES = ["10-K", "10-Q", "8-K"]


class SecAgent:
    """Retrieves recent SEC filings and converts them to :class:`Document` objects."""

    def __init__(
        self,
        user_agent: str = "AlphaAnalyst/1.0 contact@example.com",
        form_types: list[str] | None = None,
        lookback_days: int = 7,
    ) -> None:
        self._user_agent = user_agent
        self._form_types = form_types or _DEFAULT_FORM_TYPES
        self._lookback_days = lookback_days

    async def fetch(self, ticker: str) -> list[Document]:
        """Fetch recent SEC filings for *ticker*.

        Uses the EDGAR full-text search endpoint; filters by the configured
        form types and date range.
        """
        documents: list[Document] = []
        start_dt = datetime.utcnow() - timedelta(days=self._lookback_days)

        headers = {"User-Agent": self._user_agent}

        async with httpx.AsyncClient(timeout=20, headers=headers) as client:
            for form_type in self._form_types:
                docs = await self._fetch_form(client, ticker, form_type, start_dt)
                documents.extend(docs)

        logger.info("SecAgent fetched %d filings for %s.", len(documents), ticker)
        return documents

    async def _fetch_form(
        self,
        client: httpx.AsyncClient,
        ticker: str,
        form_type: str,
        start_dt: datetime,
    ) -> list[Document]:
        params = {
            "q": f'"{ticker}"',
            "dateRange": "custom",
            "startdt": start_dt.strftime("%Y-%m-%d"),
            "enddt": datetime.utcnow().strftime("%Y-%m-%d"),
            "forms": form_type,
        }

        try:
            response = await client.get(_EDGAR_SEARCH_URL, params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            logger.warning("EDGAR request failed for %s %s: %s", ticker, form_type, exc)
            return []

        hits: list[dict] = (data.get("hits") or {}).get("hits") or []
        documents: list[Document] = []

        for hit in hits:
            source = hit.get("_source") or {}
            entity_id = source.get("entity_id", "")
            accession_number = hit.get("_id", "")
            filing_date_str: str = source.get("filing_date") or source.get("file_date") or ""
            company_name: str = (source.get("display_names") or [""])[0]

            doc = Document(
                source="sec",
                ticker=ticker,
                title=f"{form_type} – {company_name}",
                content=source.get("file_date") or accession_number,
                published_at=_parse_date(filing_date_str),
                url=(
                    f"https://www.sec.gov/Archives/edgar/data/"
                    f"{entity_id}/{accession_number.replace('-', '')}"
                    f"/{accession_number}-index.htm"
                    if entity_id and accession_number
                    else None
                ),
                metadata={
                    "accession_number": accession_number,
                    "form_type": source.get("form_type", form_type),
                    "company_name": company_name,
                    "period_of_report": source.get("period_of_report"),
                },
            )
            documents.append(doc)

        return documents


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None
