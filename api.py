import os
os.environ["OPENAI_API_KEY"] = "ollama"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

import hashlib
import json
import logging
import time
import uuid
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from crewai import Agent, Task, Crew, Process, LLM
import asyncio
from concurrent.futures import ThreadPoolExecutor
import uvicorn

from tools import memory_recall, network_scout, web_search
from tools.memory import MEMORY_TRIGGER_POLICY_V1, MemoryUnavailableError, extract_summary_and_facts, write_memory_record

app = FastAPI(title="M3 Council API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

executor = ThreadPoolExecutor(max_workers=3)
memory_write_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="memory-post-crew")
memory_logger = logging.getLogger("council.memory")
HANDOFF_SCHEMA_TEXT = "summary, evidence, open_questions, done"
QUALITY_GATE_RETRY_MAX = 1
CODING_REQUEST_HINTS = (
    "code",
    "coding",
    "bug",
    "fix",
    "debug",
    "refactor",
    "function",
    "class",
    "method",
    "api endpoint",
    "stack trace",
    "exception",
    "error:",
    "traceback",
    "typescript",
    "javascript",
    "python",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
)

class Query(BaseModel):
    task: str


def _extract_json_object(text: str):
    if not isinstance(text, str):
        return None
    text = text.strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for idx, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(text[idx:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _extract_task_output_text(task: Task) -> str:
    output = getattr(task, "output", None)
    if output is None:
        return ""
    raw = getattr(output, "raw", None)
    if isinstance(raw, str) and raw.strip():
        return raw
    text = str(output)
    return text if text != "None" else ""


def _parse_quality_gate_output(text: str):
    parsed = _extract_json_object(text)
    if not isinstance(parsed, dict):
        return None
    required = ("score", "critique", "pass", "suggestions")
    if any(key not in parsed for key in required):
        return None
    pass_value = parsed["pass"]
    if isinstance(pass_value, str):
        pass_value_lower = pass_value.strip().lower()
        if pass_value_lower in ("true", "false"):
            pass_value = pass_value_lower == "true"
    if not isinstance(pass_value, bool):
        return None
    score_value = parsed["score"]
    if isinstance(score_value, str):
        try:
            score_value = float(score_value.strip())
        except ValueError:
            return None
    if not isinstance(score_value, (int, float)):
        return None
    critique_value = parsed["critique"]
    if not isinstance(critique_value, str) or not critique_value.strip():
        return None
    suggestions_value = parsed["suggestions"]
    if isinstance(suggestions_value, str):
        suggestions_value = [suggestions_value]
    if not isinstance(suggestions_value, list):
        return None
    suggestions_value = [str(item).strip() for item in suggestions_value if str(item).strip()][:2]
    return {
        "score": max(0.0, min(10.0, float(score_value))),
        "critique": critique_value.strip(),
        "pass": pass_value,
        "suggestions": suggestions_value,
    }


def _is_coding_request(user_task: str) -> bool:
    normalized = user_task.lower()
    return any(hint in normalized for hint in CODING_REQUEST_HINTS)

def _emit_memory_write_failed_event(
    endpoint: str,
    request_id: str,
    task_hash: str,
    error: Exception,
    retry_count: int,
    duration_ms: int,
) -> None:
    event = {
        "event": "memory_write_failed",
        "endpoint": endpoint,
        "request_id": request_id,
        "task_hash": task_hash,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "retry_count": retry_count,
        "duration_ms": duration_ms,
        "policy_version": MEMORY_TRIGGER_POLICY_V1,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    memory_logger.error(json.dumps(event, ensure_ascii=True, sort_keys=True))


def _persist_memory_post_crew(user_task: str, final_output: str, endpoint: str, request_id: str) -> None:
    start = time.time()
    task_hash = hashlib.sha1(user_task.encode("utf-8")).hexdigest()
    summary, key_facts = extract_summary_and_facts(final_output)
    if not summary.strip():
        return
    try:
        write_memory_record(
            summary=summary,
            key_facts=key_facts,
            source="api_post_crew",
            task_hash=task_hash,
            endpoint=endpoint,
        )
    except (MemoryUnavailableError, ValueError) as error:
        duration_ms = int((time.time() - start) * 1000)
        _emit_memory_write_failed_event(
            endpoint=endpoint,
            request_id=request_id,
            task_hash=task_hash,
            error=error,
            retry_count=1,
            duration_ms=duration_ms,
        )


def _submit_memory_write_post_crew(user_task: str, final_output: str, endpoint: str, request_id: str) -> None:
    def _run() -> None:
        _persist_memory_post_crew(
            user_task=user_task,
            final_output=final_output,
            endpoint=endpoint,
            request_id=request_id,
        )

    future = memory_write_executor.submit(_run)

    def _log_unhandled_error(done_future) -> None:
        error = done_future.exception()
        if error is not None:
            _emit_memory_write_failed_event(
                endpoint=endpoint,
                request_id=request_id,
                task_hash=hashlib.sha1(user_task.encode("utf-8")).hexdigest(),
                error=error,
                retry_count=1,
                duration_ms=0,
            )

    future.add_done_callback(_log_unhandled_error)


def _run_crew_single_attempt(user_task: str, retry_critique: str = ""):
    llm_7b   = LLM(model="ollama/qwen2.5:7b",      base_url=OLLAMA_BASE_URL, temperature=0.7, keep_alive="-1")
    llm_code = LLM(model="ollama/deepseek-coder:6.7b", base_url=OLLAMA_BASE_URL, temperature=0.3, keep_alive="-1")
    llm_mod  = LLM(model="ollama/qwen2.5:32b",     base_url=OLLAMA_BASE_URL, temperature=0.3, keep_alive="-1")
    llm_critic = LLM(model="ollama/qwen2.5:14b",   base_url=OLLAMA_BASE_URL, temperature=0.3, keep_alive="-1")

    task_description = user_task
    if retry_critique:
        retry_instruction = (
            "Quality Gate rejected the previous output. This is your second and FINAL attempt. "
            "Be precise and grounded: deliver concrete facts with sources where possible, or "
            "explicitly state that no clear evidence was found. Do not hedge, speculate, or give vague summaries."
        )
        task_description = (
            f"{retry_instruction}\n\n{user_task}\n\n"
            f"Quality Gate critique to address: {retry_critique}"
        )

    researcher = Agent(
        role="Fast Researcher",
        goal="Quickly gather relevant facts and context",
        backstory=(
            "You are a fast, no-nonsense researcher. Use the Web Search Tool whenever "
            "external or up-to-date facts would improve accuracy, even if the user does "
            "not explicitly ask to search. Use Session Memory Recall Tool only when the "
            "task clearly requires history (for example: remember last time, update our "
            "previous plan, from earlier session, or clear internal relevance). "
            f"When handing off, keep schema strict: {HANDOFF_SCHEMA_TEXT}."
        ),
        llm=llm_7b,
        tools=[web_search, memory_recall],
        verbose=True
    )

    scout = Agent(
        role="Resource Scout",
        goal="Find files, folders, and local network resources when relevant",
        backstory=(
            "You know the user's entire Mac and any connected NAS. You only use tools "
            "when the task actually needs file/network discovery. Use Session Memory "
            "Recall Tool only when the task clearly requires history (for example: "
            "remember last time, update our previous plan, from earlier session, or "
            "clear internal relevance). When handing off, keep schema strict: "
            f"{HANDOFF_SCHEMA_TEXT}."
        ),
        llm=llm_7b,
        tools=[network_scout, memory_recall],
        verbose=True
    )

    coder = Agent(
        role="Expert Coder",
        goal="Write clean, correct code only when asked",
        backstory=(
            "You are a senior engineer. You only output code when the task requires it. "
            f"When handing off, keep schema strict: {HANDOFF_SCHEMA_TEXT}."
        ),
        llm=llm_code,
        verbose=True
    )

    quality_gate = Agent(
        role="Quality & Evidence Gate",
        goal="Review the full chain for hallucination risk, evidence support, consistency, and confidence.",
        backstory=(
            "You are a strict quality gate. You use no tools and do not claim external truth verification. "
            "You only assess whether downstream claims are supported by the provided chain context/evidence. "
            "Output ONLY this JSON object with keys: score, critique, pass, suggestions. "
            "Keep critique to one sentence and suggestions to max 2 items."
        ),
        llm=llm_critic,
        verbose=True
    )

    moderator = Agent(
        role="Supreme Moderator",
        goal="Synthesize everything and give ONE clear, final answer. NEVER delegate more work.",
        backstory="You are the final decision maker. Review what the team has done and give a polished, concise final answer. Stop after that.",
        llm=llm_mod,
        verbose=True
    )

    task_researcher = Task(
        description=task_description,
        agent=researcher,
        expected_output=f"Return ONLY a JSON object with keys: {HANDOFF_SCHEMA_TEXT}."
    )
    task_scout = Task(
        description="Review the previous handoff and add local file/network discovery only when relevant.",
        agent=scout,
        context=[task_researcher],
        expected_output=f"Return ONLY a JSON object with keys: {HANDOFF_SCHEMA_TEXT}."
    )
    use_coder = _is_coding_request(user_task)
    executed_tasks = [task_researcher, task_scout]
    if use_coder:
        task_coder = Task(
            description="Review the previous handoff and provide code-oriented analysis only when coding is required.",
            agent=coder,
            context=[task_scout],
            expected_output=f"Return ONLY a JSON object with keys: {HANDOFF_SCHEMA_TEXT}."
        )
        executed_tasks.append(task_coder)

    task_quality_gate = Task(
        description=(
            "Review the full chain for hallucination risk, evidence support, consistency, and confidence. "
            "Output ONLY valid JSON with keys: score (0-10), critique (1 sentence), "
            "pass (bool), suggestions (max 2 items)."
        ),
        agent=quality_gate,
        context=executed_tasks,
        expected_output=(
            '{"score": 0-10, "critique": "one sentence", "pass": true|false, '
            '"suggestions": ["item1", "item2"]}'
        )
    )
    task_moderator = Task(
        description="Provide the final answer using prior validated context. Never delegate.",
        agent=moderator,
        context=executed_tasks + [task_quality_gate],
        expected_output="Clear, useful final answer from the Supreme Moderator. Keep it natural and to the point."
    )
    crew_agents = [researcher, scout, quality_gate, moderator]
    if use_coder:
        crew_agents.insert(2, coder)
    crew_tasks = executed_tasks + [task_quality_gate, task_moderator]

    crew = Crew(
        agents=crew_agents,
        tasks=crew_tasks,
        process=Process.sequential,   # ← much more stable than hierarchical
        verbose=True
    )
    result = crew.kickoff()
    critic_payload = _parse_quality_gate_output(_extract_task_output_text(task_quality_gate))
    return result, critic_payload


def run_crew_sync(user_task: str, endpoint: str, request_id: str):
    result = None
    critic_payload = None
    retry_critique = ""
    for _ in range(QUALITY_GATE_RETRY_MAX + 1):
        result, critic_payload = _run_crew_single_attempt(user_task=user_task, retry_critique=retry_critique)
        if critic_payload is None:
            retry_critique = "Critic output was malformed. Return strict JSON and improve factual grounding."
            if retry_critique and _ < QUALITY_GATE_RETRY_MAX:
                continue
            break
        if critic_payload.get("pass") is False and _ < QUALITY_GATE_RETRY_MAX:
            retry_critique = critic_payload.get("critique", "").strip() or "Improve factual accuracy and confidence."
            continue
        break
    _submit_memory_write_post_crew(
        user_task=user_task,
        final_output=str(result),
        endpoint=endpoint,
        request_id=request_id,
    )
    return result

@app.post("/run-council")
async def run_council(query: Query):
    loop = asyncio.get_running_loop()
    request_id = str(uuid.uuid4())
    result = await loop.run_in_executor(executor, run_crew_sync, query.task, "/run-council", request_id)
    return {"result": str(result)}

@app.post("/v1/chat/completions")
async def openai_chat_completions(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    task = messages[-1]["content"] if messages else "Hello"
    loop = asyncio.get_running_loop()
    request_id = str(uuid.uuid4())
    result = await loop.run_in_executor(executor, run_crew_sync, task, "/v1/chat/completions", request_id)

    return {
        "id": f"chatcmpl-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "council-os",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": str(result)}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    }

@app.get("/v1/models")
async def list_models():
    return {"object": "list", "data": [{"id": "council-os", "object": "model", "created": int(time.time()), "owned_by": "council-os"}]}

@app.get("/v1/openapi.json")
async def openapi_spec():
    return {"openapi": "3.1.0", "info": {"title": "M3 Council", "version": "1.0"}}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)