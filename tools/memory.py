import hashlib
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime, timedelta, timezone
from typing import Any

from crewai.tools import tool


MEMORY_COLLECTION = "session_memory"
MEMORY_TRIGGER_POLICY_V1 = "MEMORY_TRIGGER_POLICY_V1"
NO_RELEVANT_MEMORY = "No relevant prior session memory found."

SUMMARY_MAX_LEN = 800
KEY_FACT_MAX_LEN = 120
KEY_FACT_MAX_ITEMS = 8
RECALL_N_RESULTS = 3
RECALL_MAX_DISTANCE = float(os.getenv("COUNCIL_RECALL_MAX_DISTANCE", "1.2"))
MAX_MEMORY_ITEMS = int(os.getenv("COUNCIL_MAX_MEMORY_ITEMS", "500"))
MAX_MEMORY_AGE_DAYS = int(os.getenv("COUNCIL_MAX_MEMORY_AGE_DAYS", "180"))

MEMORY_INIT_TIMEOUT_S = float(os.getenv("COUNCIL_MEMORY_INIT_TIMEOUT_S", "2.0"))
MEMORY_QUERY_TIMEOUT_S = float(os.getenv("COUNCIL_MEMORY_QUERY_TIMEOUT_S", "2.0"))
MEMORY_WRITE_TIMEOUT_S = float(os.getenv("COUNCIL_MEMORY_WRITE_TIMEOUT_S", "2.0"))
MEMORY_PRUNE_TIMEOUT_S = float(os.getenv("COUNCIL_MEMORY_PRUNE_TIMEOUT_S", "2.0"))

_MEMORY_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="memory")
_MEMORY_LOCK = threading.Lock()


class MemoryUnavailableError(RuntimeError):
    pass


def _normalize_text(value: str, max_len: int) -> str:
    normalized = re.sub(r"\s+", " ", (value or "").strip()).lower()
    return normalized[:max_len]


def _normalize_key_facts(key_facts: list[str]) -> list[str]:
    cleaned = [_normalize_text(item, KEY_FACT_MAX_LEN) for item in key_facts if item and item.strip()]
    return sorted(cleaned)[:KEY_FACT_MAX_ITEMS]


def _derive_memory_id(summary: str, key_facts: list[str]) -> str:
    normalized_summary = _normalize_text(summary, SUMMARY_MAX_LEN)
    normalized_facts = _normalize_key_facts(key_facts)
    payload = f"{normalized_summary}|{json.dumps(normalized_facts, ensure_ascii=True)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _future_with_timeout(callable_obj, timeout_s: float):
    future = _MEMORY_EXECUTOR.submit(callable_obj)
    return future.result(timeout=timeout_s)


def _with_retry(callable_obj, timeout_s: float, operation_name: str):
    last_error: Exception | None = None
    for _attempt in range(2):
        try:
            return _future_with_timeout(callable_obj, timeout_s)
        except TimeoutError as error:
            last_error = error
        except Exception as error:  # noqa: BLE001
            last_error = error
    raise MemoryUnavailableError(f"Memory unavailable: {operation_name} failed ({last_error})")


def _force_failure_if_enabled() -> None:
    if os.getenv("COUNCIL_MEMORY_FORCE_FAILURE", "0") == "1":
        raise MemoryUnavailableError("Memory unavailable: forced failure via COUNCIL_MEMORY_FORCE_FAILURE=1")


def _storage_dir() -> str:
    return os.getenv("COUNCIL_MEMORY_DIR", "/tmp/council_memory")


def _init_collection():
    _force_failure_if_enabled()
    try:
        import chromadb
    except Exception as error:  # noqa: BLE001
        raise MemoryUnavailableError(f"Memory unavailable: chromadb dependency missing ({error})") from error

    os.makedirs(_storage_dir(), exist_ok=True)
    client = _with_retry(lambda: chromadb.PersistentClient(path=_storage_dir()), MEMORY_INIT_TIMEOUT_S, "init")
    return _with_retry(
        lambda: client.get_or_create_collection(name=MEMORY_COLLECTION),
        MEMORY_INIT_TIMEOUT_S,
        "get_or_create_collection",
    )


def _extract_facts_from_text(text: str) -> list[str]:
    lines = [line.strip("-• ").strip() for line in text.splitlines() if line.strip()]
    facts = [item[:KEY_FACT_MAX_LEN] for item in lines if len(item) > 8]
    if facts:
        return facts[:KEY_FACT_MAX_ITEMS]
    chunks = [chunk.strip() for chunk in re.split(r"[.!?;\n]+", text) if chunk.strip()]
    return [chunk[:KEY_FACT_MAX_LEN] for chunk in chunks[:KEY_FACT_MAX_ITEMS]]


def extract_summary_and_facts(text: str) -> tuple[str, list[str]]:
    summary = re.sub(r"\s+", " ", text).strip()[:SUMMARY_MAX_LEN]
    facts = _extract_facts_from_text(text)
    if not facts and summary:
        facts = [summary[:KEY_FACT_MAX_LEN]]
    return summary, facts


def _extract_memory_payload(query: str) -> tuple[str, list[str]]:
    summary = ""
    facts: list[str] = []
    for raw_line in query.splitlines():
        line = raw_line.strip()
        lower = line.lower()
        if lower.startswith("session_summary:"):
            summary = line.split(":", 1)[1].strip()[:SUMMARY_MAX_LEN]
        elif lower.startswith("key_facts:"):
            raw_facts = line.split(":", 1)[1]
            facts = [part.strip()[:KEY_FACT_MAX_LEN] for part in raw_facts.split("|") if part.strip()][:KEY_FACT_MAX_ITEMS]
    if summary or facts:
        return summary, facts
    return extract_summary_and_facts(query)


def _semantic_trigger_score(query: str) -> float:
    query_norm = f" {query.lower()} "
    prior_ref = bool(re.search(r"\b(previous|prior|earlier|last time|chat history|before)\b", query_norm))
    continuation = bool(re.search(r"\b(continue|update|revisit|resume|again)\b", query_norm))
    comparison = bool(re.search(r"\b(compare|difference|changed|versus|decision)\b", query_norm))
    meta_task = bool(re.search(r"\b(title|tags|categorize|format|follow-up questions)\b", query_norm))

    score = 0.0
    if prior_ref:
        score += 0.45
    if continuation:
        score += 0.30
    if comparison:
        score += 0.20
    if meta_task:
        score -= 0.60
    return score


def should_trigger_recall(query: str) -> bool:
    return _semantic_trigger_score(query) >= 0.50


def _parse_stored_at(stored_at: str) -> float:
    try:
        return datetime.fromisoformat(stored_at.replace("Z", "+00:00")).timestamp()
    except Exception:  # noqa: BLE001
        return float("-inf")


def _normalize_legacy_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    summary = payload.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return None
    key_facts = payload.get("key_facts", [])
    if isinstance(key_facts, str):
        key_facts = [key_facts]
    if not isinstance(key_facts, list):
        key_facts = []
    cleaned_facts = [str(fact).strip()[:KEY_FACT_MAX_LEN] for fact in key_facts if str(fact).strip()]
    return {
        "summary": summary.strip()[:SUMMARY_MAX_LEN],
        "key_facts": cleaned_facts[:KEY_FACT_MAX_ITEMS],
        "stored_at": str(payload.get("stored_at", "")),
    }


def _collect_prune_candidates(ids: list[str], metadatas: list[dict[str, Any]]) -> list[tuple[float, str]]:
    candidates = []
    for idx, item_id in enumerate(ids):
        metadata = metadatas[idx] if idx < len(metadatas) else {}
        stored_at = str((metadata or {}).get("stored_at", ""))
        candidates.append((_parse_stored_at(stored_at), item_id))
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates


def _prune_collection(collection) -> None:
    def _do_get():
        return collection.get(include=["metadatas"])

    current = _with_retry(_do_get, MEMORY_PRUNE_TIMEOUT_S, "prune_get")
    ids = current.get("ids", []) or []
    metadatas = current.get("metadatas", []) or []
    if not ids:
        return

    now_utc = datetime.now(timezone.utc)
    delete_ids = []
    if MAX_MEMORY_AGE_DAYS > 0:
        cutoff = now_utc - timedelta(days=MAX_MEMORY_AGE_DAYS)
        cutoff_ts = cutoff.timestamp()
        for ts, item_id in _collect_prune_candidates(ids, metadatas):
            if ts == float("-inf") or ts < cutoff_ts:
                delete_ids.append(item_id)

    remaining_ids = [item_id for item_id in ids if item_id not in set(delete_ids)]
    overflow = max(0, len(remaining_ids) - MAX_MEMORY_ITEMS)
    if overflow > 0:
        ordered = _collect_prune_candidates(ids, metadatas)
        for _, item_id in ordered:
            if item_id in delete_ids:
                continue
            delete_ids.append(item_id)
            overflow -= 1
            if overflow == 0:
                break

    if delete_ids:
        _with_retry(lambda: collection.delete(ids=sorted(set(delete_ids))), MEMORY_PRUNE_TIMEOUT_S, "prune_delete")


def write_memory_record(
    summary: str,
    key_facts: list[str],
    source: str = "api_post_crew",
    task_hash: str = "",
    endpoint: str = "",
) -> dict[str, Any]:
    _force_failure_if_enabled()
    normalized_summary = summary.strip()[:SUMMARY_MAX_LEN]
    if not normalized_summary:
        raise ValueError("summary is required for memory write")
    created_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "summary": normalized_summary,
        "key_facts": [fact.strip()[:KEY_FACT_MAX_LEN] for fact in key_facts if fact.strip()][:KEY_FACT_MAX_ITEMS],
        "stored_at": created_at,
    }
    payload_id = _derive_memory_id(payload["summary"], payload["key_facts"])
    metadata = {
        "kind": "session_summary",
        "stored_at": created_at,
        "source": source[:64],
        "task_hash": task_hash[:64],
        "endpoint": endpoint[:64],
    }
    payload_text = json.dumps(payload, ensure_ascii=True)

    with _MEMORY_LOCK:
        collection = _init_collection()
        _prune_collection(collection)
        _with_retry(
            lambda: collection.upsert(documents=[payload_text], ids=[payload_id], metadatas=[metadata]),
            MEMORY_WRITE_TIMEOUT_S,
            "write_upsert",
        )
        _prune_collection(collection)
    return {"id": payload_id, "retry_count": 1}


@tool("Session Memory Write Tool")
def memory_write(query: str) -> str:
    """Persist a short session summary and key facts."""
    summary, facts = _extract_memory_payload(query)
    if not summary:
        return "Memory unavailable: summary is required for memory write."
    try:
        result = write_memory_record(summary=summary, key_facts=facts, source="agent_tool")
    except MemoryUnavailableError as error:
        return str(error)
    return f"Memory written: id={result['id']}"


@tool("Session Memory Recall Tool")
def memory_recall(query: str) -> str:
    """Recall relevant prior session memory with deterministic filtering."""
    if not should_trigger_recall(query):
        return NO_RELEVANT_MEMORY

    try:
        with _MEMORY_LOCK:
            collection = _init_collection()
            recalled = _with_retry(
                lambda: collection.query(
                    query_texts=[query],
                    n_results=RECALL_N_RESULTS,
                    include=["documents", "metadatas", "distances"],
                ),
                MEMORY_QUERY_TIMEOUT_S,
                "recall_query",
            )
    except MemoryUnavailableError as error:
        return str(error)

    documents = (recalled.get("documents") or [[]])[0]
    metadatas = (recalled.get("metadatas") or [[]])[0]
    distances = (recalled.get("distances") or [[]])[0]
    ids = (recalled.get("ids") or [[]])[0]

    rows = []
    for index, item in enumerate(documents):
        try:
            payload = json.loads(item)
        except json.JSONDecodeError:
            continue
        normalized = _normalize_legacy_payload(payload)
        if normalized is None:
            continue
        distance = float(distances[index]) if index < len(distances) else 999.0
        if distance > RECALL_MAX_DISTANCE:
            continue
        metadata = metadatas[index] if index < len(metadatas) else {}
        stored_at = str((metadata or {}).get("stored_at") or normalized.get("stored_at", ""))
        row_id = ids[index] if index < len(ids) else _derive_memory_id(normalized["summary"], normalized["key_facts"])
        rows.append((distance, _parse_stored_at(stored_at), str(row_id), normalized))

    if not rows:
        return NO_RELEVANT_MEMORY

    rows.sort(key=lambda row: (row[0], -row[1], row[2]))
    lines = []
    for _, _, _, payload in rows[:RECALL_N_RESULTS]:
        compact_facts = ", ".join(payload["key_facts"][:5])
        lines.append(
            f"{len(lines) + 1}. summary={payload['summary'] or 'n/a'}; key_facts={compact_facts or 'n/a'}"
        )
    if not lines:
        return NO_RELEVANT_MEMORY
    return "Recalled session memory:\n" + "\n".join(lines)
