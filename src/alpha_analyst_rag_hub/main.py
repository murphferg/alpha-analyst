import asyncio
import os
from typing import Annotated
from xmlrpc import client
from pydantic import Field
from dotenv import load_dotenv

# Microsoft Agent Framework 1.0 GA Standard Imports
from agent_framework import Agent, tool
from agent_framework.openai import OpenAIChatClient
from agent_framework.orchestrations import SequentialBuilder
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


@tool(description="Search SEC filings for financial tables.")
def search_sec_index(query: str, ticker: str) -> str:
    print(f"🔍 [AGENT CALL]: Searching {ticker} for '{query}'...")
    
    try:
        # (Existing search logic...)
        results = client.search(
            search_text=query,
            vector_queries=[vector_query],
            filter=f"ticker eq '{ticker.upper()}'",
            query_type="semantic",
            semantic_configuration_name="alpha-analyst-config",
            top=10
        )

        chunks = [r['content'] for r in results]
        
        if not chunks:
            # 🏆 FALLBACK: If semantic fails, try a simple keyword search
            print(f"⚠️ No semantic results for '{query}'. Trying keyword fallback...")
            results = client.search(
                search_text=query,
                filter=f"ticker eq '{ticker.upper()}'",
                top=5
            )
            chunks = [r['content'] for r in results]

        if not chunks:
            return f"SYSTEM ERROR: No data found in index for ticker {ticker.upper()} with query '{query}'."
            
        return "\n\n---\n\n".join(chunks)

    except Exception as e:
            # 🏆 THE SMOKING GUN: Print this to your VS Code terminal
            print(f"❌ AZURE SEARCH ERROR: {str(e)}")
            return f"TOOL ERROR: {str(e)}"            
    
# --- 2. AGENT DEFINITIONS ---

async def main():

    query = "Analyze Tesla (TSLA) based on indexed risk factors and provide an investment thesis."

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
            "You are a Senior Investment Researcher. You are forbidden from using your own memory. "
            "MISSION: You must find 4 specific metrics: GAAP Income, Cash, Auto Revenue, and Energy Revenue. \n\n"
            "EXECUTION PLAN:\n"
            "1. CALL 'search_sec_index' for 'Consolidated Statements of Operations' to find Income.\n"
            "2. CALL 'search_sec_index' for 'Consolidated Balance Sheets' to find Cash.\n"
            "3. CALL 'search_sec_index' for 'Segment Revenue' to find Auto/Energy splits.\n"
            "4. If a search returns SEC headers/boilerplate, RE-SEARCH using more specific terms like 'Table: Operating Income'.\n\n"
            "Only after you have the numbers, synthesize the Investment Thesis. "
            "If you fail to find a number, explicitly state: 'DATA NOT FOUND IN INDEX' so the Auditor can see the gap."
        ),
        client=client,
        tools=[search_sec_index]
    )

    # The Reviewer: A critical auditor to check the final analysis
    reviewer = Agent(
    name="Reviewer",
    instructions=(
        "You are a cynical Senior Investment Auditor. Your goal is to find errors. "
        "Review the provided analysis for: \n"
        "1. Missing Citations: Every financial claim must cite a 10-K section.\n"
        "2. Hallucinations: Does the news sentiment actually contradict the filing?\n"
        "3. Logic Gaps: Are the conclusions too optimistic?\n"
        "If the analysis is weak, provide a list of 'Action Items' for the Analyst."
    ),
    client=client
)

# --- 3. THE WORKFLOW ---
    
    # SequentialBuilder connects Analyst -> Reviewer
    workflow = (
        SequentialBuilder(participants=[lead_analyst, reviewer])
        .build()
    )

    print("--- 🧐 Alpha Analyst: Sequential Audit Workflow Starting ---")
    # --- 🛠️ DEBUG: Aggregating all outputs into final_messages ---
    run_result = await workflow.run(query)

    final_messages = []
    outputs = run_result.get_outputs()

    for final_output in outputs:
        # In Sequential workflows, each participant returns their message history
        if isinstance(final_output, list):
            for msg in final_output:
                final_messages.append(msg)
        else:
            # Fallback for single-message responses
            final_messages.append(final_output)

    # --- 🔦 INSPECTION PRINT ---
    print("\n" + "="*50)
    print("--- 🔬 ALPHA ANALYST: FULL CONVERSATION TRACE ---")
    print("="*50)

    for i, msg in enumerate(final_messages):
        role = getattr(msg, 'role', 'unknown').upper()
        name = getattr(msg, 'name', 'System')
        
        # 🏆 FIX: Specifically check for Tool/Function outputs
        if role == "TOOL":
            # Tool outputs are often in .content or .text depending on the wrapper
            content = getattr(msg, 'content', getattr(msg, 'text', "[[ EMPTY TOOL RESULT ]]"))
        else:
            content = getattr(msg, 'text', str(msg))
        
        print(f"[{i}] {role} - {name}:\n{content}\n" + "-"*30)

    print("--- END OF TRACE ---\n")
if __name__ == "__main__":
    asyncio.run(main())
