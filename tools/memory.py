import hashlib
import json
import os
from datetime import datetime, timezone

from crewai.tools import tool


HISTORY_HINTS = (
    "remember last time",
    "update our previous plan",
    "from earlier session",
    "previous session",
    "earlier session",
    "last time",
)


def _extract_memory_payload(query: str) -> tuple[str, list[str]]:
    summary = ""
    facts: list[str] = []

    for raw_line in query.splitlines():
        line = raw_line.strip()
        lower = line.lower()
        if lower.startswith("session_summary:"):
            summary = line.split(":", 1)[1].strip()[:280]
        elif lower.startswith("key_facts:"):
            raw_facts = line.split(":", 1)[1]
            facts = [part.strip()[:120] for part in raw_facts.split("|") if part.strip()][:8]

    return summary, facts


def _should_recall(query: str) -> bool:
    lowered = query.lower()
    return any(hint in lowered for hint in HISTORY_HINTS)


@tool("Session Memory Recall Tool")
def memory_recall(query: str) -> str:
    """
    Persist and recall short session summaries + key facts.

    Expected optional inline payload for storing memory:
    - session_summary: <short summary>
    - key_facts: fact A | fact B | fact C
    """
    try:
        import chromadb
    except Exception as error:
        return f"Memory tool unavailable: chromadb dependency missing ({error})."

    storage_dir = os.getenv("COUNCIL_MEMORY_DIR", "/tmp/council_memory")
    os.makedirs(storage_dir, exist_ok=True)

    client = chromadb.PersistentClient(path=storage_dir)
    collection = client.get_or_create_collection(name="session_memory")

    summary, facts = _extract_memory_payload(query)
    if summary or facts:
        payload = {
            "summary": summary,
            "key_facts": facts,
            "stored_at": datetime.now(timezone.utc).isoformat(),
        }
        payload_text = json.dumps(payload, ensure_ascii=True)
        payload_id = hashlib.sha1(payload_text.encode("utf-8")).hexdigest()
        collection.upsert(documents=[payload_text], ids=[payload_id], metadatas=[{"kind": "session_summary"}])

    if not _should_recall(query):
        return "Memory recall skipped: no clear history intent detected."

    recalled = collection.query(query_texts=[query], n_results=3)
    documents = recalled.get("documents", [[]])[0]
    if not documents:
        return "No prior session memory found."

    lines = []
    for item in documents:
        try:
            payload = json.loads(item)
        except json.JSONDecodeError:
            continue
        summary_text = str(payload.get("summary", "")).strip()[:280]
        key_facts = payload.get("key_facts", [])
        compact_facts = ", ".join([str(fact).strip()[:120] for fact in key_facts][:5])
        lines.append(
            f"{len(lines) + 1}. summary={summary_text or 'n/a'}; key_facts={compact_facts or 'n/a'}"
        )

    if not lines:
        return "No prior session memory found."
    return "Recalled session memory:\n" + "\n".join(lines)
