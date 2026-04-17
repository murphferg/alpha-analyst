# Alpha Analyst — Architecture

## Overview

Alpha Analyst is a cloud-native investment research platform that automatically ingests financial data (SEC filings, news articles), processes it through a Retrieval-Augmented Generation (RAG) pipeline, and exposes AI-generated insights via a REST API.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Client / UI                                     │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │ HTTPS
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     AlphaAnalyst.Gateway  (C# .NET Web API)                 │
│                                                                             │
│  GET  /api/insights/{ticker}          →  fetch insights from RAG Hub        │
│  POST /api/insights/{ticker}/synthesize  →  trigger fresh synthesis         │
│  GET  /api/audit                      →  read-only audit trail              │
└──────────────────────┬──────────────────────────────────────────────────────┘
                       │ HTTP (internal)
                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                  alpha_analyst_rag_hub  (Python FastAPI)                     │
│                                                                             │
│  agents/                                                                    │
│    news_agent.py       — fetches & normalises news articles                  │
│    sec_agent.py        — fetches & normalises SEC filings                    │
│    synthesis_agent.py  — orchestrates RAG chain, caches results             │
│                                                                             │
│  chains/                                                                    │
│    retrieval_chain.py  — wraps LangChain LLM (OpenAI / stub)               │
│                                                                             │
│  eval/                                                                      │
│    ragas_eval.py       — RAGAS-based quality evaluation                      │
└──────────────────────────────────────────────────────────────────────────────┘
        ▲ Background polling
        │
┌───────────────────────────────────────────────────────────────────────────┐
│               AlphaAnalyst.Ingestion  (C# .NET Worker Service)            │
│                                                                           │
│  Workers/SecFilingWorker.cs  — polls EDGAR full-text search API           │
│  Workers/NewsWorker.cs       — polls NewsAPI.org                          │
│                                                                           │
│  → publishes to Azure Service Bus topics:                                 │
│      sec-filings   (consumed by RAG Hub)                                  │
│      news-articles (consumed by RAG Hub)                                  │
└───────────────────────────────────────────────────────────────────────────┘
```

## Components

### AlphaAnalyst.Ingestion
- **Runtime**: .NET 10 Worker Service
- **Purpose**: Periodically polls external data sources (SEC EDGAR, NewsAPI) for fresh financial data and publishes structured messages to Azure Service Bus.
- **Workers**:
  - `SecFilingWorker` — fetches 10-K, 10-Q, and 8-K filings from the EDGAR full-text search API.
  - `NewsWorker` — fetches news articles for a configured list of tickers from NewsAPI.org.

### alpha_analyst_rag_hub
- **Runtime**: Python 3.11+ / FastAPI + uvicorn
- **Purpose**: Orchestrates AI agents to retrieve, embed, and synthesise financial documents into investment insights using RAG (Retrieval-Augmented Generation).
- **Key modules**:
  - `agents/news_agent.py` — fetches and normalises news.
  - `agents/sec_agent.py` — fetches and normalises SEC filings.
  - `agents/synthesis_agent.py` — combines document context and runs the LLM synthesis chain.
  - `chains/retrieval_chain.py` — wraps LangChain `ChatOpenAI` (or a configurable stub).
  - `eval/ragas_eval.py` — RAGAS evaluation suite for faithfulness, relevancy, and context recall.

### AlphaAnalyst.Gateway
- **Runtime**: .NET 10 ASP.NET Core Web API
- **Purpose**: Public-facing API gateway that proxies requests to the RAG Hub and exposes an audit trail.
- **Controllers**:
  - `InsightsController` — `GET /api/insights/{ticker}` and `POST /api/insights/{ticker}/synthesize`.
  - `AuditController` — `GET /api/audit` and `GET /api/audit/{id}`.

## Data Flow

```
SEC EDGAR API ──► SecFilingWorker ──┐
                                    ├──► Azure Service Bus ──► RAG Hub ──► Cosmos DB (insights)
NewsAPI ────────► NewsWorker ───────┘                              │
                                                                   ▼
Client ─────────────────────────────────────────────► Gateway ──► RAG Hub
```

## Infrastructure (Azure)

All resources are provisioned via Bicep (`infrastructure/main.bicep`):

| Resource | Purpose |
|---|---|
| Azure Container Apps | Hosts Ingestion, RAG Hub, and Gateway |
| Azure Container Registry | Stores Docker images |
| Azure Service Bus | Decouples Ingestion from RAG Hub |
| Azure Cosmos DB | Stores insights and audit entries |
| Azure Key Vault | Stores API keys and secrets |
| Azure Application Insights | Distributed tracing and monitoring |
| Azure Log Analytics | Centralised log aggregation |

## Local Development

```bash
# Copy and fill in your API keys
cp .env.example .env

# Start all services
docker compose up --build

# Gateway API docs
open http://localhost:5000/openapi/v1.json

# RAG Hub Swagger UI
open http://localhost:8000/docs
```

## Environment Variables

| Variable | Service | Description |
|---|---|---|
| `NEWS_API_KEY` | Ingestion, RAG Hub | [NewsAPI.org](https://newsapi.org) API key |
| `OPENAI_API_KEY` | RAG Hub | OpenAI API key |
| `OPENAI_MODEL` | RAG Hub | Model to use (default: `gpt-4o-mini`) |
| `LLM_BACKEND` | RAG Hub | `openai` or `stub` (default: `stub`) |
