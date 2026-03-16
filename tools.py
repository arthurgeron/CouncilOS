from crewai.tools import tool
import json
import os
import subprocess
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

@tool("Local Network & File Scout Tool")
def network_scout(query: str) -> str:
    """Search your files, network shares, or run safe local commands."""
    if "list" in query.lower():
        return os.listdir("/Users/zed/Documents")  # change path
    elif "ping" in query.lower():
        result = subprocess.run(["ping", "-c", "1", "192.168.1.1"], capture_output=True, text=True)
        return result.stdout
    # Add nmap, grep across shares, whatever you want — keep it read-only!
    return "Scout tool executed"


@tool("Web Search Tool")
def web_search(query: str) -> str:
    """Use this for fresh or external facts, even without explicit search requests."""
    base_url = os.getenv("SEARXNG_BASE_URL", "http://host.docker.internal:8081")
    timeout = float(os.getenv("SEARXNG_TIMEOUT", "8"))
    url = f"{base_url}/search?q={quote_plus(query)}&format=json"

    request = Request(url, headers={"User-Agent": "council-os/1.0"})
    try:
        with urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as error:
        return (
            "Web search failed. Verify SearXNG is reachable and healthy. "
            f"Attempted URL: {base_url} ({error})"
        )

    results = data.get("results", [])
    if not results:
        return "No web results found for this query."

    top_results = results[:5]
    lines = []
    for item in top_results:
        title = item.get("title", "Untitled")
        link = item.get("url", "")
        snippet = item.get("content", "").replace("\n", " ").strip()
        if len(snippet) > 220:
            snippet = f"{snippet[:217]}..."
        lines.append(f"- {title}\n  {link}\n  {snippet}")

    return "Top web results:\n" + "\n".join(lines)