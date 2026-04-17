"""
Retrieval Chain — wraps a LangChain LLM + output parser into a simple async interface.

The :func:`build_retrieval_chain` factory reads configuration from environment
variables so that the LLM backend is swappable without code changes.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)


class RetrievalChain:
    """Thin wrapper around a LangChain chat model that accepts a prompt and
    returns a parsed JSON dict."""

    def __init__(self, llm: Any) -> None:
        self._llm = llm

    async def run(self, prompt: str) -> dict[str, Any]:
        """Invoke the LLM with *prompt* and parse the JSON response.

        Falls back to a stub response when the LLM is unavailable.
        """
        try:
            response = await self._llm.ainvoke(prompt)
            text = response.content if hasattr(response, "content") else str(response)
            return _extract_json(text)
        except Exception as exc:
            logger.warning("LLM call failed (%s); returning stub response.", exc)
            return {
                "summary": "LLM unavailable – stub response.",
                "confidence_score": 0.0,
                "detailed_analysis": None,
            }


def build_retrieval_chain() -> RetrievalChain:
    """Instantiate and return a :class:`RetrievalChain` configured from env vars.

    Supported backends (set ``LLM_BACKEND``):
    - ``openai`` (default): uses ``langchain_openai.ChatOpenAI``
    - ``stub``: returns canned responses (useful for tests / local dev without an API key)
    """
    backend = os.getenv("LLM_BACKEND", "stub").lower()

    if backend == "openai":
        try:
            from langchain_openai import ChatOpenAI  # type: ignore[import-untyped]

            llm = ChatOpenAI(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                temperature=0.2,
                api_key=os.getenv("OPENAI_API_KEY", ""),
            )
            logger.info("RetrievalChain using OpenAI backend (%s).", llm.model_name)
            return RetrievalChain(llm)
        except ImportError:
            logger.warning("langchain-openai not installed; falling back to stub backend.")

    logger.info("RetrievalChain using stub backend.")
    return RetrievalChain(_StubLLM())


# ── Helpers ──────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict[str, Any]:
    """Extract the first JSON object found in *text*."""
    match = re.search(r"\{.*?\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {"summary": text.strip(), "confidence_score": 0.5, "detailed_analysis": None}


class _StubLLM:
    """Minimal stub that mimics a LangChain chat model for testing."""

    async def ainvoke(self, prompt: str) -> "_StubResponse":  # noqa: ARG002
        return _StubResponse(
            '{"summary": "Stub insight.", '
            '"confidence_score": 0.5, '
            '"detailed_analysis": "This is a stub response for local development."}'
        )


class _StubResponse:
    def __init__(self, content: str) -> None:
        self.content = content
