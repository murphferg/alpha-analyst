"""
Synthesis Agent — combines News and SEC documents via a retrieval-augmented
generation (RAG) chain to produce structured investment insights.
"""

from __future__ import annotations

import logging
from datetime import datetime

from models import Document, Insight
from chains.retrieval_chain import RetrievalChain

logger = logging.getLogger(__name__)

_INSIGHT_TYPES = ["Fundamental", "Sentiment", "TechnicalRisk"]

_SYNTHESIS_PROMPT_TEMPLATE = """
You are an expert financial analyst. Based on the following documents about {ticker},
produce a concise investment insight of type '{insight_type}'.

Documents:
{context}

Respond with:
- A one-sentence summary.
- A confidence score between 0.0 and 1.0.
- A brief detailed analysis (2-3 sentences).

Format your response as JSON with keys: summary, confidence_score, detailed_analysis.
"""


class SynthesisAgent:
    """Orchestrates the retrieval chain and LLM to generate investment insights."""

    def __init__(self, retrieval_chain: RetrievalChain) -> None:
        self._chain = retrieval_chain
        self._cache: dict[str, list[Insight]] = {}

    async def get_cached_insights(self, ticker: str) -> list[Insight]:
        """Return previously synthesised insights for *ticker*, or an empty list."""
        return self._cache.get(ticker, [])

    async def synthesize(self, ticker: str, documents: list[Document]) -> list[Insight]:
        """Run the full synthesis pipeline for *ticker* using *documents*.

        Returns a list of :class:`Insight` objects — one per insight type.
        """
        if not documents:
            logger.warning("No documents provided for synthesis of %s.", ticker)
            return []

        insights: list[Insight] = []

        for insight_type in _INSIGHT_TYPES:
            try:
                insight = await self._synthesize_one(ticker, insight_type, documents)
                insights.append(insight)
            except Exception:
                logger.exception(
                    "Failed to synthesise %s insight for %s.", insight_type, ticker
                )

        self._cache[ticker] = insights
        logger.info("Synthesised %d insights for %s.", len(insights), ticker)
        return insights

    async def _synthesize_one(
        self,
        ticker: str,
        insight_type: str,
        documents: list[Document],
    ) -> Insight:
        context = "\n\n".join(
            f"[{doc.source.upper()}] {doc.title}\n{doc.content[:500]}"
            for doc in documents[:10]
        )

        prompt = _SYNTHESIS_PROMPT_TEMPLATE.format(
            ticker=ticker,
            insight_type=insight_type,
            context=context,
        )

        result = await self._chain.run(prompt)

        return Insight(
            ticker=ticker,
            type=insight_type,
            summary=result.get("summary", ""),
            detailed_analysis=result.get("detailed_analysis"),
            confidence_score=float(result.get("confidence_score", 0.0)),
            sources=[doc.url for doc in documents if doc.url],
            generated_at=datetime.utcnow(),
        )
