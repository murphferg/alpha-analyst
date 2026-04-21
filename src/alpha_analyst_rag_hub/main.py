import asyncio
import inspect
import json
import os
import re
import sys
import time
from urllib.parse import quote_plus
from urllib.request import urlopen
from xml.etree import ElementTree

from dotenv import load_dotenv

from agent_framework import Agent, tool
from agent_framework.openai import OpenAIChatClient
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient


load_dotenv()


@tool(description="Searches internal SEC index for grounded 10-K evidence.")
def search_sec_index(query: str, ticker: str) -> str:
    """Searches internal SEC index for grounded 10-K data."""
    print(f"[tool] search_sec_index ticker={ticker.upper()} query={query}")
    search_client = SearchClient(
        endpoint=os.getenv("AZURE_AI_SEARCH_ENDPOINT"),
        index_name="alpha-analyst-sec-index",
        credential=AzureKeyCredential(os.getenv("AZURE_AI_SEARCH_KEY")),
    )
    try:
        results = search_client.search(
            search_text=query,
            filter=f"ticker eq '{ticker.upper()}'",
            query_type="semantic",
            semantic_configuration_name="alpha-analyst-config",
            top=8,
        )
        chunks = [r.get("content", "") for r in results if r.get("content")]
        return "\n\n---\n\n".join(chunks) if chunks else "DATA NOT FOUND IN SEC INDEX."
    except Exception as exc:
        return f"TOOL ERROR: {exc}"


@tool(description="Fetches recent market news headlines for a ticker from Google News RSS.")
def get_news_headlines(ticker: str) -> str:
    """Returns recent headlines and links for a ticker."""
    print(f"[tool] get_news_headlines ticker={ticker.upper()}")
    query = quote_plus(f"{ticker} stock earnings guidance risk")
    url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

    try:
        with urlopen(url, timeout=10) as response:
            xml_data = response.read()
        root = ElementTree.fromstring(xml_data)

        entries = []
        for item in root.findall("./channel/item")[:8]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            if title:
                clean_title = re.sub(r"\s+-\s+[^-]+$", "", title)
                entries.append(f"- {clean_title} ({link})")

        if not entries:
            return f"No recent news headlines found for {ticker.upper()}."

        return "\n".join(entries)
    except Exception as exc:
        return f"TOOL ERROR: Unable to fetch news for {ticker.upper()}: {exc}"


def _extract_text(output: object) -> str:
    if isinstance(output, list):
        parts = [_extract_text(item) for item in output]
        return "\n\n".join([p for p in parts if p.strip()])

    text = getattr(output, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()

    role = getattr(output, "role", None)
    msg_content = getattr(output, "content", None)
    if role is not None and msg_content is not None:
        rendered = str(msg_content)
        return f"[{role}] {rendered}"

    content = getattr(output, "content", None)
    if content is not None:
        return str(content)
    return str(output)


async def _run_agent_step(step: int, agent: Agent, prompt: str, t0: float) -> tuple[str, dict]:
    start = time.perf_counter()
    print(json.dumps({
        "step": step,
        "agent": agent.name,
        "event_type": "step_started",
        "elapsed_ms": round((start - t0) * 1000, 2),
        "prompt_chars": len(prompt),
    }))

    stream = agent.run(prompt, stream=True)
    output_chunks = 0
    output_chars = 0

    async for chunk in stream:
        text = getattr(chunk, "text", None)
        if isinstance(text, str) and text:
            output_chunks += 1
            output_chars += len(text)

    response = await stream.get_final_response()
    text = _extract_text(response)

    end = time.perf_counter()
    metadata = {
        "step": step,
        "agent": agent.name,
        "event_type": "step_completed",
        "elapsed_ms": round((end - t0) * 1000, 2),
        "duration_ms": round((end - start) * 1000, 2),
        "output_chunks": output_chunks,
        "output_chars": output_chars,
        "response_chars": len(text),
    }
    print(json.dumps(metadata))

    return text, metadata


async def run_alpha_audit(ticker: str) -> None:
    print(f"\n--- Alpha Analyst Inspector Workflow: {ticker.upper()} ---")

    client_kwargs = {
        "base_url": os.getenv("AZURE_OPENAI_ENDPOINT"),
        "api_key": os.getenv("AZURE_OPENAI_API_KEY"),
    }
    client_sig = inspect.signature(OpenAIChatClient)
    if "model" in client_sig.parameters:
        client_kwargs["model"] = os.getenv("AZURE_OPENAI_MODEL")
    elif "model_id" in client_sig.parameters:
        client_kwargs["model_id"] = os.getenv("AZURE_OPENAI_MODEL")

    client = OpenAIChatClient(**client_kwargs)

    sec_agent = Agent(
        name="SECFilingAnalyst",
        client=client,
        instructions=(
            "You are an SEC filings analyst. Use search_sec_index to gather evidence for revenue, "
            "cash, profitability, and risk factors. Return only concise evidence bullets with SEC labels."
        ),
        tools=[search_sec_index],
    )

    news_agent = Agent(
        name="NewsAgent",
        client=client,
        instructions=(
            "You are a market news analyst. Use get_news_headlines and summarize sentiment and key "
            "near-term business implications."
        ),
        tools=[get_news_headlines],
    )

    lead_analyst = Agent(
        name="LeadAnalyst",
        client=client,
        instructions=(
            "You are the lead analyst. Before generating a report, incorporate both prior SEC evidence "
            "and prior news analysis from earlier participants. You may call tools again if needed. "
            "Output sections: SEC Evidence, News Evidence, Integrated Analysis, Final Verdict."
        ),
        tools=[search_sec_index, get_news_headlines],
    )

    auditor = Agent(
        name="Auditor",
        client=client,
        instructions=(
            "You are an auditor. Review the lead report for unsupported claims, weak citations, and "
            "logic gaps. Return a concise audit checklist."
        ),
    )

    t0 = time.perf_counter()

    print("\n" + "=" * 68)
    print("Step Metadata")
    print("=" * 68)

    base_prompt = (
        f"Analyze {ticker.upper()} and produce an investment audit. "
        "Ensure the final lead report explicitly considers both SEC filing evidence and current news."
    )

    sec_report, _ = await _run_agent_step(
        1,
        sec_agent,
        (
            f"{base_prompt}\n\n"
            "Focus only on SEC filing evidence and cite which parts are SEC-derived."
        ),
        t0,
    )

    news_report, _ = await _run_agent_step(
        2,
        news_agent,
        (
            f"{base_prompt}\n\n"
            "Focus only on news/sentiment and near-term business implications."
        ),
        t0,
    )

    lead_report, _ = await _run_agent_step(
        3,
        lead_analyst,
        (
            f"{base_prompt}\n\n"
            "Use the context below before generating your final report.\n\n"
            f"SEC EVIDENCE:\n{sec_report}\n\n"
            f"NEWS EVIDENCE:\n{news_report}"
        ),
        t0,
    )

    auditor_report, _ = await _run_agent_step(
        4,
        auditor,
        (
            "Audit the lead report for unsupported claims, weak citations, and logic gaps.\n\n"
            f"LEAD REPORT:\n{lead_report}"
        ),
        t0,
    )

    outputs = [sec_report, news_report, lead_report, auditor_report]

    print("\n" + "=" * 68)
    print("Workflow Trace")
    print("=" * 68)
    for index, item in enumerate(outputs, start=1):
        message = _extract_text(item)
        print(f"\n[{index}]\n{message}\n")

    if outputs:
        print("=" * 68)
        print("Final Output")
        print("=" * 68)
        print(_extract_text(outputs[-1]))


if __name__ == "__main__":
    asyncio.run(run_alpha_audit(sys.argv[1] if len(sys.argv) > 1 else "TSLA"))
    