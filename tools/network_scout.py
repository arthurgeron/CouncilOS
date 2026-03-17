import os
import subprocess
from shlex import split

from crewai.tools import tool


def _extract_ping_target(query: str) -> str:
    try:
        parts = split(query)
    except ValueError:
        return ""
    for index, part in enumerate(parts[:-1]):
        if part.lower() == "ping":
            return parts[index + 1].strip()
    return ""


@tool("Local Network & File Scout Tool")
def network_scout(query: str) -> str:
    """Search your files, network shares, or run safe local commands."""
    if "list" in query.lower():
        try:
            entries = sorted(os.listdir("."))
        except OSError as error:
            return f"List failed: {error}"
        return "\n".join(entries) if entries else "(empty directory)"
    if "ping" in query.lower():
        target = _extract_ping_target(query)
        if not target:
            return "Ping skipped: provide an explicit target, e.g. 'ping example.com'."
        result = subprocess.run(
            ["ping", "-c", "1", target],
            capture_output=True,
            text=True,
        )
        return result.stdout
    return "Scout tool executed"
