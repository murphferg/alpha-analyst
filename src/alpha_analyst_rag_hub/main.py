import asyncio
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
from agent_framework.orchestrations import SequentialBuilder
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


def _event_metadata(event: object, sequence: int, t0: float, executor_starts: dict[str, float]) -> dict:
    def _safe_attr(obj: object, name: str):
        try:
            return getattr(obj, name)
        except Exception:
            return None

    event_type = str(getattr(event, "type", "unknown"))
    source_executor = _safe_attr(event, "source_executor_id")
    now = time.perf_counter()

    duration_ms = None
    if source_executor and event_type == "executor_invoked":
        executor_starts[source_executor] = now
    elif source_executor and event_type in {"executor_completed", "executor_failed"}:
        started = executor_starts.get(source_executor)
        if started is not None:
            duration_ms = round((now - started) * 1000, 2)

    metadata = {
        "seq": sequence,
        "event_type": event_type,
        "elapsed_ms": round((now - t0) * 1000, 2),
        "source_executor_id": source_executor,
        "request_id": _safe_attr(event, "request_id"),
        "request_type": str(_safe_attr(event, "request_type") or "") or None,
        "response_type": str(_safe_attr(event, "response_type") or "") or None,
        "duration_ms": duration_ms,
    }

    if event_type == "request_info":
        try:
            metadata["request_info"] = event.to_dict()
        except Exception:
            metadata["request_info"] = str(_safe_attr(event, "data"))
    else:
        metadata["data"] = str(_safe_attr(event, "data"))

    return metadata


async def run_alpha_audit(ticker: str) -> None:
    print(f"\n--- Alpha Analyst Inspector Workflow: {ticker.upper()} ---")

    client = OpenAIChatClient(
        base_url=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        model=os.getenv("AZURE_OPENAI_MODEL"),
    )

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

    workflow = SequentialBuilder(
        participants=[sec_agent, news_agent, lead_analyst, auditor],
        chain_only_agent_responses=True,
        intermediate_outputs=True,
    ).build()

    prompt = (
        f"Analyze {ticker.upper()} and produce an investment audit. "
        "Ensure the final lead report explicitly considers both SEC filing evidence and current news."
    )

    stream = workflow.run(prompt, stream=True, include_status_events=True)
    t0 = time.perf_counter()
    executor_starts: dict[str, float] = {}
    event_count = 0
    output_chunk_count = 0
    output_char_count = 0

    print("\n" + "=" * 68)
    print("Step Metadata")
    print("=" * 68)
    async for event in stream:
        event_count += 1
        event_type = str(getattr(event, "type", "unknown"))

        if event_type == "output":
            chunk = str(getattr(event, "data", "") or "")
            output_chunk_count += 1
            output_char_count += len(chunk)

            # Emit periodic progress for long generations instead of every token chunk.
            if output_chunk_count % 50 == 0:
                progress = {
                    "seq": event_count,
                    "event_type": "output_progress",
                    "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2),
                    "output_chunks": output_chunk_count,
                    "output_chars": output_char_count,
                }
                print(json.dumps(progress, default=str))
            continue

        metadata = _event_metadata(event, event_count, t0, executor_starts)

        data_str = metadata.get("data")
        if data_str is not None:
            data_preview = data_str[:220]
            if len(data_str) > 220:
                data_preview += "..."
            metadata["data_preview"] = data_preview
            metadata.pop("data", None)

        print(json.dumps(metadata, default=str))

    print(json.dumps({
        "event_type": "output_summary",
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2),
        "output_chunks": output_chunk_count,
        "output_chars": output_char_count,
    }))

    result = await stream.get_final_response()
    outputs = result.get_outputs()

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
    