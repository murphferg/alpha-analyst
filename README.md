# alpha-analyst

> AI-powered investment research platform — automatically ingests SEC filings and financial news, processes them through a RAG pipeline, and serves investment insights via a REST API.

## Repository Structure

```
/alpha-analyst
├── .github/workflows      # CI/CD pipelines (GitHub Actions)
├── docs/                  # Architecture diagrams and design specs
├── shared/                # Shared JSON schemas / contracts
│
├── src/
│   ├── AlphaAnalyst.Ingestion/     # C# .NET Background Service
│   │   ├── Workers/
│   │   │   ├── SecFilingWorker.cs  # SEC EDGAR fetcher
│   │   │   └── NewsWorker.cs       # News article fetcher
│   │   └── AlphaAnalyst.Ingestion.csproj
│   │
│   ├── alpha_analyst_rag_hub/      # Python FastAPI RAG service
│   │   ├── agents/                 # News, SEC, Synthesis agents
│   │   ├── chains/                 # LangChain retrieval chain
│   │   ├── eval/                   # RAGAS evaluation
│   │   └── main.py
│   │
│   └── AlphaAnalyst.Gateway/       # C# .NET Web API
│       ├── Controllers/
│       │   ├── InsightsController.cs
│       │   └── AuditController.cs
│       └── AlphaAnalyst.Gateway.csproj
│
├── infrastructure/        # Azure Bicep templates
├── docker-compose.yml     # Full-stack local development
└── README.md
```

## Quick Start (Docker Compose)

```bash
# 1. Copy environment template and fill in your keys
cp .env.example .env

# 2. Start all services
docker compose up --build

# Gateway API  → http://localhost:5000/openapi/v1.json
# RAG Hub UI   → http://localhost:8000/docs
```

## Services

| Service | Tech | Port | Description |
|---|---|---|---|
| Ingestion | .NET 10 Worker | — | Polls SEC EDGAR & NewsAPI, publishes to Service Bus |
| RAG Hub | Python / FastAPI | 8000 | Agents + LangChain synthesis |
| Gateway | .NET 10 Web API | 5000 | Public REST API (Insights + Audit) |

## Development

### .NET services

```bash
# Build all .NET projects
dotnet build AlphaAnalyst.slnx

# Run gateway locally
dotnet run --project src/AlphaAnalyst.Gateway

# Run ingestion locally
dotnet run --project src/AlphaAnalyst.Ingestion
```

### Python RAG Hub

```bash
cd src/alpha_analyst_rag_hub

# Install dependencies (requires Poetry)
poetry install

# Run dev server (stub LLM — no API key needed)
LLM_BACKEND=stub poetry run uvicorn main:app --reload

# Run with OpenAI
OPENAI_API_KEY=sk-... LLM_BACKEND=openai poetry run uvicorn main:app --reload
```

## Architecture

See [docs/architecture.md](docs/architecture.md) for a full component diagram and data-flow description.

## Infrastructure

Azure resources are defined in [infrastructure/main.bicep](infrastructure/main.bicep) and can be deployed with:

```bash
az deployment group create \
  --resource-group rg-alpha-analyst-dev \
  --template-file infrastructure/main.bicep \
  --parameters infrastructure/main.bicepparam
```
