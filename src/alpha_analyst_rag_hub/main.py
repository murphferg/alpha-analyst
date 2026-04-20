import asyncio
import os
from typing import Annotated
from xmlrpc import client
from pydantic import Field
from dotenv import load_dotenv

# Microsoft Agent Framework 1.0 GA Standard Imports
from agent_framework import Agent, tool
from agent_framework.openai import OpenAIChatClient
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from azure.core.credentials import AzureKeyCredential
from sec_edgar_downloader import Downloader

# Load environment variables
load_dotenv()

# --- 1. TOOL DEFINITIONS ---

@tool(description="Downloads the latest 10-K filing for a company to local storage.")
def download_sec_filing(
    ticker: Annotated[str, Field(description="The stock ticker symbol (e.g., 'TSLA')")]
) -> str:
    """Uses sec-edgar-downloader to fetch filings for analysis."""
    # Ensure local directory exists
    email = "kevin.murphy@example.com" # Replace with your real email for SEC compliance
    dl = Downloader("AlphaAnalystProject", email, "data/sec_filings")
    
    try:
        dl.get("10-K", ticker.upper(), limit=1)
        return f"Successfully downloaded the latest 10-K for {ticker.upper()} to data/sec_filings."
    except Exception as e:
        return f"Error downloading filing for {ticker}: {str(e)}"


@tool(description="Performs a hybrid search (vector + keyword) for high-precision financial data.")
def search_sec_index(
    query: Annotated[str, Field(description="The question about financials")],
    ticker: Annotated[str, Field(description="The stock ticker (e.g., 'TSLA')")]
) -> str:
    # 1. Generate the embedding for the query
    embedding_response = aoai_client.embeddings.create(
        input=query,
        model="text-embedding-3-small"
    )
    query_vector = embedding_response.data[0].embedding

    # 2. Setup the Hybrid Query
    vector_query = VectorizedQuery(
        vector=query_vector, 
        k_nearest_neighbors=3, 
        fields="contentVector"
    )

    client = SearchClient(
        endpoint=os.getenv("AZURE_AI_SEARCH_ENDPOINT"),
        index_name="alpha-analyst-sec-index",
        credential=AzureKeyCredential(os.getenv("AZURE_AI_SEARCH_KEY"))
    )

    # 3. Execute Hybrid + Semantic Search
    results = client.search(
        search_text=query,             # The Keyword Path
        vector_queries=[vector_query], # The Vector Path
        filter=f"ticker eq '{ticker.upper()}'",
        query_type="semantic",         # Enable the L2 Ranker
        semantic_configuration_name="alpha-analyst-config",
        top=3
    )

    context = "\n".join([r['content'] for r in results])
    return f"High-precision data for {ticker.upper()}:\n{context}" if context else "No data found."

# --- 2. AGENT DEFINITIONS ---

async def main():
    # Initialize the high-performance /v1 Client
    client = OpenAIChatClient(
        base_url=os.getenv("AZURE_OPENAI_ENDPOINT"), # Ends in /openai/v1
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        model=os.getenv("AZURE_OPENAI_MODEL")        # Deployment name
    )

    # Specialist 1: Financial Data & SEC Filings
    sec_agent = Agent(
        name="SECAgent",
        # 🏆 FIX: Explicitly command the agent to use its tools
        instructions=(
            "You are an SEC Specialist. When asked about a company, you MUST FIRST use "
            "'search_sec_index' to look for data. If nothing is found, use 'download_sec_filing'. "
            "Do not apologize; simply execute the tools and report the findings."
        ),
        client=client,
        tools=[download_sec_filing, search_sec_index]
    )

    # Specialist 2: News & Sentiment
    news_agent = Agent(
        name="NewsAgent",
        # 🏆 FIX: Give it a baseline tool or clear role
        instructions="You are a News Analyst. Search for the latest headlines regarding the ticker provided.",
        client=client
    )

    # The Supervisor: Coordinates the specialists
    lead_analyst = Agent(
        name="LeadAnalyst",
        instructions=(
            "You are the Lead Analyst. Your specialists (SECAgent and NewsAgent) have "
            "access to real-time data tools. If they say they have 'limitations', "
            "order them to try their specific search tools again. Do not provide a "
            "final analysis until you have data from BOTH agents."
        ),
        client=client,
        tools=[sec_agent.as_tool(), news_agent.as_tool()]
    )

    # --- 3. EXECUTION ---
    print("--- 🏆 Alpha Analyst: Production Multi-Agent Run ---")
    
    user_query = (
        "Is Tesla's (TSLA) current news sentiment consistent with the "
        "risk factors listed in their latest indexed 10-K?"
    )

    # The LeadAnalyst orchestrates the specialists automatically
    response = await lead_analyst.run(user_query)
    
    print(f"\nFINAL ANALYSIS:\n{response.text}")

if __name__ == "__main__":
    asyncio.run(main())
    