"""
Alpha Analyst RAG Hub — FastAPI entry point.

Starts the HTTP server that exposes:
  GET  /insights/{ticker}     → retrieve cached / live insights
  POST /synthesize/{ticker}   → trigger a fresh synthesis run
  GET  /health                → readiness probe
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI

from agents.news_agent import NewsAgent
from agents.sec_agent import SecAgent
from agents.synthesis_agent import SynthesisAgent
from chains.retrieval_chain import build_retrieval_chain
from models import Insight


# ── App lifecycle ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialise shared resources on startup and clean up on shutdown."""
    app.state.news_agent = NewsAgent()
    app.state.sec_agent = SecAgent()
    app.state.synthesis_agent = SynthesisAgent(
        retrieval_chain=build_retrieval_chain()
    )
    yield
    # Clean-up (e.g. close DB connections) goes here.


app = FastAPI(
    title="Alpha Analyst RAG Hub",
    version="0.1.0",
    description="Orchestrates News, SEC, and Synthesis agents to produce investment insights.",
    lifespan=lifespan,
)


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/insights/{ticker}", response_model=list[Insight])
async def get_insights(ticker: str) -> list[Insight]:
    """Return cached insights for *ticker*."""
    ticker = ticker.upper()
    synthesis_agent: SynthesisAgent = app.state.synthesis_agent
    return await synthesis_agent.get_cached_insights(ticker)


@app.post("/synthesize/{ticker}", response_model=list[Insight])
async def synthesize(ticker: str) -> list[Insight]:
    """Trigger a fresh synthesis run for *ticker* and return new insights."""
    ticker = ticker.upper()

    news_agent: NewsAgent = app.state.news_agent
    sec_agent: SecAgent = app.state.sec_agent
    synthesis_agent: SynthesisAgent = app.state.synthesis_agent

    # Run agents in parallel.
    import asyncio

    news_docs, sec_docs = await asyncio.gather(
        news_agent.fetch(ticker),
        sec_agent.fetch(ticker),
    )

    return await synthesis_agent.synthesize(ticker, news_docs + sec_docs)


# ── Dev server entrypoint ────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
