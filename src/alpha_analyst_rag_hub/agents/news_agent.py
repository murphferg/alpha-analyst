"""
News Agent — fetches and pre-processes financial news articles for a given ticker.

In production, replace the HTTP call with a real NewsAPI / Marketaux client;
the stub below illustrates the contract the rest of the system depends on.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from models import Document

logger = logging.getLogger(__name__)


class NewsAgent:
    """Retrieves recent news articles and converts them to :class:`Document` objects."""

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://newsapi.org/v2",
        lookback_hours: int = 24,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._lookback_hours = lookback_hours

    async def fetch(self, ticker: str) -> list[Document]:
        """Fetch articles mentioning *ticker* from the past ``lookback_hours`` hours.

        Returns an empty list and logs a warning when no API key is configured.
        """
        if not self._api_key:
            logger.warning(
                "NEWS_API_KEY is not set – skipping news fetch for %s.", ticker
            )
            return []

        from_dt = datetime.now(timezone.utc) - timedelta(hours=self._lookback_hours)

        params = {
            "q": ticker,
            "from": from_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": 20,
            "apiKey": self._api_key,
        }

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(f"{self._base_url}/everything", params=params)
            response.raise_for_status()
            data = response.json()

        articles: list[dict] = data.get("articles") or []
        documents: list[Document] = []

        for article in articles:
            doc = Document(
                source="news",
                ticker=ticker,
                title=article.get("title") or "",
                content=article.get("content") or article.get("description") or "",
                published_at=_parse_dt(article.get("publishedAt")),
                url=article.get("url"),
                metadata={
                    "author": article.get("author"),
                    "source_name": (article.get("source") or {}).get("name"),
                },
            )
            documents.append(doc)

        logger.info("NewsAgent fetched %d articles for %s.", len(documents), ticker)
        return documents


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.rstrip("Z")).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
