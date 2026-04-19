import asyncio
import os
from dotenv import load_dotenv

from agent_framework import Agent, tool
from agent_framework.openai import OpenAIChatClient


from typing import Annotated
from pydantic import Field


from sec_edgar_downloader import Downloader
import os

# Initialize the downloader with your info (SEC requirement)
# Change the path to where you want the filings to land
dl = Downloader("AlphaAnalystProject", "kevin.murphy@example.com", "data/sec_filings")

@tool(description="Downloads and retrieves the latest 10-K filing for a company.")
def get_sec_filings(
    ticker: Annotated[str, Field(description="The stock ticker symbol (e.g., 'AAPL')")]
) -> str:
    """Downloads the latest 10-K and returns a confirmation path."""
    try:
        # Download the latest 10-K
        dl.get("10-K", ticker, limit=1, download_details=True)
        
        # Construct the expected path (sec-edgar-downloader uses a specific structure)
        base_path = f"data/sec_filings/sec-edgar-filings/{ticker}/10-K"
        
        # Find the latest accession number folder
        folders = sorted(os.listdir(base_path), reverse=True)
        if not folders:
            return f"No filings found for {ticker}."
            
        full_path = os.path.join(base_path, folders[0], "full-submission.txt")
        
        return f"Successfully downloaded the latest 10-K for {ticker}. File saved to: {full_path}"
    except Exception as e:
        return f"Error fetching filings for {ticker}: {str(e)}"
    

from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential

@tool(description="Searches the indexed SEC filings for specific financial insights.")
def search_sec_filings(
    query: Annotated[str, Field(description="The question about company financials")],
    ticker: Annotated[str, Field(description="The stock ticker symbol (e.g., 'TSLA')")]
) -> str:
    # 1. Standardize casing
    clean_ticker = ticker.upper().strip()
    
    # 2. Search logic
    client = SearchClient(
        endpoint=os.getenv("AZURE_AI_SEARCH_ENDPOINT"),
        index_name="alpha-analyst-sec-index",
        credential=AzureKeyCredential(os.getenv("AZURE_AI_SEARCH_KEY"))
    )
    
    # 3. Add count=True to debug if any docs exist
    results = client.search(
        search_text=query, 
        filter=f"ticker eq '{clean_ticker}'", 
        top=3
    )
    
    context = "\n".join([r['content'] for r in results])
    return f"Relevant excerpts from the {clean_ticker} 10-K:\n{context}" if context else f"No matching data found for ticker '{clean_ticker}'."

load_dotenv()

async def main():
    # 1. Initialize the Chat Client for the /v1 path
    # If your URL ends in /openai/v1, use base_url and REMOVE api_version
    client = OpenAIChatClient(
        base_url=os.getenv("AZURE_OPENAI_ENDPOINT"), # Use base_url for /v1 paths
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        model=os.getenv("AZURE_OPENAI_MODEL")        # Your deployment name
    )

    # 2. Define the News Agent
    news_agent = Agent(
        name="NewsAgent",
        instructions="You are a financial news analyst. Keep your responses concise.",
        client=client
    )

    # 2a. Run a test query
    print("--- Alpha Analyst: News Agent Test ---")
    try:
        # The .run() method is the standard entry point for Agent
        response = await news_agent.run("What is the current market sentiment for renewable energy stocks?")
        print(f"Agent Response: {response.text}")
    except Exception as e:
        print(f"Error detail: {e}")

    # 3. Define the SEC Filings Agent
    sec_agent = Agent(
        name="SECAgent",
        instructions=(
            "You are an expert financial analyst. Use 'get_sec_filings' to download new data "
            "and 'search_sec_filings' to query the research index for specific insights."
        ),
        client=client,
        tools=[get_sec_filings, search_sec_filings]
    )

    # 3a. Test SEC Filings Agent
    print("--- Alpha Analyst: Production RAG Test ---")
    # This query forces the agent to use the search tool against your Azure index
    query = "Search the research index for the 'TSLA' ticker and tell me what content is stored there."
    response = await sec_agent.run(query)
    
    print(f"\nSEC Agent Response:\n{response.text}")

if __name__ == "__main__":
    asyncio.run(main())
