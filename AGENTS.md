# AGENTS.md

## Cursor Cloud specific instructions

### Repository structure

This is a multi-project repository (not a workspace-managed monorepo) containing:

| Sub-project | Language | Path | Package Manager |
|---|---|---|---|
| **alpha_analyst_rag_hub** (core RAG pipeline) | Python 3.12 | `src/alpha_analyst_rag_hub/` | Poetry (v2+) |
| **alpha-analyst-vsai** (Writer-Reviewer hosted agent) | Python 3.12 | `alpha-analyst-vsai/` | pip + venv |
| **AlphaAnalyst.Gateway** (ASP.NET Web API) | C# / .NET 10 | `src/AlphaAnalyst.Gateway/AlphaAnalyst.Gateway/` | NuGet |
| **AlphaAnalyst.Ingestion** (Worker Service) | C# / .NET 10 | `src/AlphaAnalyst.Ingestion/AlphaAnalyst.Ingestion/` | NuGet |

### Running services

- **Gateway API**: `dotnet run` from `src/AlphaAnalyst.Gateway/AlphaAnalyst.Gateway/` — serves on `http://localhost:5082` (default). Test endpoint: `GET /weatherforecast`.
- **Ingestion Worker**: `dotnet run` from `src/AlphaAnalyst.Ingestion/AlphaAnalyst.Ingestion/` — background worker (logs every second).
- **alpha-analyst-vsai**: `cd alpha-analyst-vsai && source .venv/bin/activate && python main.py` — requires `PROJECT_ENDPOINT` env var (Azure Foundry).
- **alpha_analyst_rag_hub**: `cd src/alpha_analyst_rag_hub && poetry run python main.py TSLA` — requires Azure OpenAI + Azure AI Search credentials.

### Environment variables required

The Python projects depend on external Azure services. Required env vars:

- **alpha_analyst_rag_hub**: `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_MODEL`, `AZURE_OPENAI_EMBEDDING_MODEL`, `AZURE_AI_SEARCH_ENDPOINT`, `AZURE_AI_SEARCH_KEY`
- **alpha-analyst-vsai**: `PROJECT_ENDPOINT`, `MODEL_DEPLOYMENT_NAME`

### Linting and testing

- No dedicated linter config (ruff/pylint/flake8/mypy) exists. Use `python3 -m py_compile <file>` for syntax checks.
- No automated tests exist in this repo.
- .NET projects compile cleanly with `dotnet build`.

### Gotchas

- When working in the `alpha_analyst_rag_hub` directory, always use `poetry run` to run commands inside the Poetry virtualenv (located at `src/alpha_analyst_rag_hub/.venv/` due to `in-project = true`).
- The `alpha-analyst-vsai` project has its own separate venv at `alpha-analyst-vsai/.venv/`. Do not mix the two virtual environments — deactivate one before activating the other.
- .NET SDK is installed at `$HOME/.dotnet`. Ensure `PATH` includes it: `export PATH="$HOME/.dotnet:$PATH"`.
- The .NET projects target `net10.0` (.NET 10 Preview). The standard `dotnet` from system packages will not work; use the installed SDK.
- The .NET Gateway and Ingestion projects are scaffolds (weather forecast template / timer worker) and not yet integrated with the AI pipeline.
