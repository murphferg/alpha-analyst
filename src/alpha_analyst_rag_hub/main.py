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

@tool(description="Searches the indexed SEC research database for specific financial facts.")
def search_sec_index(
    query: Annotated[str, Field(description="The specific question about financials")],
    ticker: Annotated[str, Field(description="The stock ticker (e.g., 'TSLA')")]
) -> str:
    """Queries the Azure AI Search vector index for context."""
    client = SearchClient(
        endpoint=os.getenv("AZURE_AI_SEARCH_ENDPOINT"),
        index_name="alpha-analyst-sec-index",
        credential=AzureKeyCredential(os.getenv("AZURE_AI_SEARCH_KEY"))
    )
    
    clean_ticker = ticker.upper().strip()
    results = client.search(search_text=query, filter=f"ticker eq '{clean_ticker}'", top=3)
    
    context = "\n".join([r['content'] for r in results])
    return f"Excerpts from {clean_ticker} index:\n{context}" if context else "No indexed data found."

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
        instructions="Expert in SEC filings. Use 'download_sec_filing' for new data and 'search_sec_index' for existing data.",
        client=client,
        tools=[download_sec_filing, search_sec_index]
    )

    # Specialist 2: News & Sentiment
    news_agent = Agent(
        name="NewsAgent",
        instructions="Real-time news analyst. Keep responses concise and focused on market impact.",
        client=client
    )

    # The Supervisor: Coordinates the specialists
    lead_analyst = Agent(
        name="LeadAnalyst",
        instructions=(
            "You are the Lead Investment Analyst. Delegate to 'SECAgent' for historical filings "
            "and 'NewsAgent' for headlines. Synthesize their findings into a final thesis."
        ),
        client=client,
        # 🏆 FIX: Use .as_tool() to make the agents serializable
        tools=[
            sec_agent.as_tool(), 
            news_agent.as_tool()
        ] 
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