import os
import sys
import json
from typing import Annotated
from dotenv import load_dotenv

# GA 1.0 Production SDK
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    PromptAgentDefinition,
    FunctionTool,
    BingGroundingTool,
    BingGroundingSearchToolParameters,
    BingGroundingSearchConfiguration,
    MCPTool # 🏆 The "Truth Tool"
)

# RAG Infrastructure
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential

# 1. INITIALIZATION
load_dotenv()
credential = DefaultAzureCredential()

project_client = AIProjectClient(
    endpoint=os.getenv("AZURE_AI_PROJECT_ENDPOINT"),
    credential=credential
)

# 2. LOCAL RAG TOOL
def search_sec_index(query: str, ticker: str) -> str:
    """Searches internal SEC index for grounded 10-K data."""
    print(f"🔍 [SEC RAG]: Searching {ticker.upper()} for '{query}'...")
    search_client = SearchClient(
        endpoint=os.getenv("AZURE_AI_SEARCH_ENDPOINT"),
        index_name="alpha-analyst-sec-index",
        credential=AzureKeyCredential(os.getenv("AZURE_AI_SEARCH_KEY"))
    )
    try:
        results = search_client.search(
            search_text=query,
            filter=f"ticker eq '{ticker.upper()}'",
            query_type="semantic",
            semantic_configuration_name="alpha-analyst-config",
            top=12 
        )
        return "\n\n---\n\n".join([r['content'] for r in results]) or "DATA NOT FOUND."
    except Exception as e:
        return f"TOOL ERROR: {str(e)}"

# 3. BING GROUNDING (GA 1.0 Hierarchy)
# Resolve the Connection ID from the friendly Name
bing_conn = project_client.connections.get(name=os.getenv("BING_CONNECTION_NAME"))

# 🏆 FIX: project_connection_id is the definitive GA keyword
search_config = BingGroundingSearchConfiguration(
    project_connection_id=bing_conn.id
)

bing_params = BingGroundingSearchToolParameters(
    search_configurations=[search_config]
)
bing_tool = BingGroundingTool(bing_grounding=bing_params)

# 4. AGENT DEFINITIONS (Versioning Pattern)

# --- LEAD ANALYST ---
lead_analyst = project_client.agents.create_version(
    agent_name="LeadAnalyst",
    definition=PromptAgentDefinition(
        model=os.getenv("AZURE_OPENAI_MODEL"),
        instructions=(
            "You are the lead financial analyst. Build the final investment report by combining "
            "(1) SEC filing evidence and (2) external news context provided in the user prompt. "
            "Before finalizing, call search_sec_index to verify key financial claims from filings. "
            "Output sections: SEC Evidence, News Evidence, Integrated Analysis, and Final Verdict."
        ),
        tools=[
            FunctionTool(
                name="search_sec_index",
                description="Searches internal SEC index for grounded 10-K data.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query text."},
                        "ticker": {"type": "string", "description": "Stock ticker symbol, e.g. TSLA."}
                    },
                    "required": ["query", "ticker"],
                    "additionalProperties": False
                },
                strict=False
            )
        ]
    )
)

# --- NEWSAGENT ---
news_agent = project_client.agents.create_version(
    agent_name="NewsAgent",
    definition=PromptAgentDefinition(
        model=os.getenv("AZURE_OPENAI_MODEL"),
        instructions="Sentiment: Compare 10-K risks with live Bing News. Flag gaps.",
        tools=[bing_tool]
    )
)

# --- AUDITOR (The MCP Guardian) ---
auditor = project_client.agents.create_version(
    agent_name="Auditor",
    definition=PromptAgentDefinition(
        model=os.getenv("AZURE_OPENAI_MODEL"),
        instructions=(
            "Audit citations and logic. If you are unsure of the current Microsoft "
            "Agent SDK syntax, use the microsoft_learn_mcp tool to verify."
        ),
        tools=[MCPTool(
            server_label="microsoft_learn_mcp",
            server_url="https://learn.microsoft.com/api/mcp"
        )]
    )
)

# 5. EXECUTION (Responses API Workflow)
def run_alpha_audit(ticker: str):
    print(f"\n--- 🧐 Alpha Analyst Audit: {ticker.upper()} ---")
    
    with project_client.get_openai_client() as openai_client:
        def extract_response_text(response) -> str:
            if getattr(response, "output_text", None):
                return response.output_text

            parts = []
            for item in (getattr(response, "output", None) or []):
                for content in (getattr(item, "content", None) or []):
                    text_value = getattr(content, "text", None)
                    if text_value:
                        parts.append(text_value)
            return "\n".join(parts).strip()

        def invoke_agent(agent, user_prompt: str) -> str:
            print(f"▶️  Invoking: {agent.name}...")

            conversation = openai_client.conversations.create(
                items=[{"role": "user", "content": user_prompt}]
            )

            response = openai_client.responses.create(
                conversation=conversation.id,
                extra_body={
                    "agent_reference": {"name": agent.name, "type": "agent_reference"}
                }
            )

            while response.status in ["requires_action", "in_progress"]:
                if response.status == "requires_action":
                    outputs = []
                    for tc in response.required_action.submit_tool_outputs.tool_calls:
                        fn = getattr(tc, "function", None)
                        fn_name = getattr(fn, "name", None)

                        if fn_name == "search_sec_index":
                            try:
                                args = json.loads(fn.arguments or "{}")
                            except json.JSONDecodeError:
                                args = {}

                            query = args.get("query", "latest filing updates")
                            sec_ticker = args.get("ticker", ticker)
                            res = search_sec_index(query, sec_ticker)
                            outputs.append({"tool_call_id": tc.id, "output": res})
                        else:
                            outputs.append({
                                "tool_call_id": tc.id,
                                "output": f"Tool '{fn_name or 'unknown'}' is not executed by local runner."
                            })

                    if outputs:
                        response = openai_client.responses.submit_tool_outputs(
                            conversation=conversation.id,
                            response_id=response.id,
                            tool_outputs=outputs
                        )
                    else:
                        response = openai_client.responses.get(
                            conversation=conversation.id,
                            response_id=response.id
                        )
                else:
                    response = openai_client.responses.get(
                        conversation=conversation.id,
                        response_id=response.id
                    )

            final_text = extract_response_text(response)
            preview = final_text[:150] if final_text else "(no text output)"
            print(f"[{agent.name}]: {preview}...")
            return final_text

        def invoke_model(user_prompt: str) -> str:
            response = openai_client.responses.create(
                model=os.getenv("AZURE_OPENAI_MODEL"),
                input=user_prompt
            )
            return extract_response_text(response)

        news_summary = invoke_agent(
            news_agent,
            (
                f"For {ticker}, summarize the most material current news and sentiment signals. "
                "Focus on drivers that may affect revenue, margin, risk, or valuation."
            )
        )

        sec_snapshot = search_sec_index(
            "GAAP income cash revenue segment revenue risk factors",
            ticker
        )

        lead_prompt = (
            f"Perform a comprehensive audit of {ticker}. Use SEC filing evidence and incorporate "
            "the following external news summary before generating your report.\n\n"
            "REQUIRED: Reference both SEC and News in each conclusion.\n"
            "Output sections: SEC Evidence, News Evidence, Integrated Analysis, Final Verdict.\n\n"
            f"SEC EVIDENCE SNAPSHOT:\n{sec_snapshot}\n\n"
            f"NEWS SUMMARY:\n{news_summary}"
        )

        lead_report = invoke_agent(lead_analyst, lead_prompt)

        if not lead_report.strip():
            lead_report = invoke_model(
                "You are the LeadAnalyst. Produce the final report using BOTH SEC and NEWS context below. "
                "Cite source type per claim (SEC or NEWS).\n\n"
                f"{lead_prompt}"
            )

        auditor_report = invoke_agent(
            auditor,
            (
                f"Audit this lead analyst report for citation quality, unsupported claims, and logic gaps.\n\n"
                f"LEAD REPORT:\n{lead_report}"
            )
        )

        print("\n" + "="*60 + "\n--- 🔬 FINAL LEAD ANALYST REPORT ---\n" + "="*60)
        print(lead_report)

        print("\n" + "="*60 + "\n--- 🧪 AUDITOR REVIEW ---\n" + "="*60)
        print(auditor_report)

if __name__ == "__main__":
    run_alpha_audit(sys.argv[1] if len(sys.argv) > 1 else "TSLA")
    