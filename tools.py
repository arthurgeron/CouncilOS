from crewai.tools import tool
import os, subprocess

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