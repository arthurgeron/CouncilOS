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

class Query(BaseModel):
    task: str

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


def run_crew_sync(user_task: str, endpoint: str, request_id: str):
    # === STRONG AGENTS (no more looping) ===
    llm_7b   = LLM(model="ollama/qwen2.5:7b",      base_url=OLLAMA_BASE_URL, temperature=0.7, keep_alive="-1")
    llm_14b  = LLM(model="ollama/qwen2.5:14b",     base_url=OLLAMA_BASE_URL, temperature=0.7, keep_alive="-1")
    llm_code = LLM(model="ollama/deepseek-coder:6.7b", base_url=OLLAMA_BASE_URL, temperature=0.3, keep_alive="-1")
    llm_mod  = LLM(model="ollama/qwen2.5:32b",     base_url=OLLAMA_BASE_URL, temperature=0.3, keep_alive="-1")

    researcher = Agent(
        role="Fast Researcher",
        goal="Quickly gather relevant facts and context",
        backstory=(
            "You are a fast, no-nonsense researcher. Use the Web Search Tool whenever "
            "external or up-to-date facts would improve accuracy, even if the user does "
            "not explicitly ask to search. Use Session Memory Recall Tool only when the "
            "task clearly requires history (for example: remember last time, update our "
            "previous plan, from earlier session, or clear internal relevance). "
            "When handing off, keep schema strict: summary, evidence, open_questions, done."
        ),
        llm=llm_7b,
        tools=[web_search, memory_recall],
        verbose=True
    )

    scout = Agent(
        role="Network & File Scout",
        goal="Find files, folders, and local network resources when relevant",
        backstory=(
            "You know the user's entire Mac and any connected NAS. You only use tools "
            "when the task actually needs file/network discovery. Use Session Memory "
            "Recall Tool only when the task clearly requires history (for example: "
            "remember last time, update our previous plan, from earlier session, or "
            "clear internal relevance). When handing off, keep schema strict: summary, "
            "evidence, open_questions, done."
        ),
        llm=llm_14b,
        tools=[network_scout, memory_recall],
        verbose=True
    )

    coder = Agent(
        role="Expert Coder",
        goal="Write clean, correct code only when asked",
        backstory="You are a senior engineer. You only output code when the task requires it. Otherwise you stay quiet.",
        llm=llm_code,
        verbose=True
    )

    moderator = Agent(
        role="Supreme Moderator",
        goal="Synthesize everything and give ONE clear, final answer. NEVER delegate more work.",
        backstory="You are the final decision maker. Review what the team has done and give a polished, concise final answer. Stop after that.",
        llm=llm_mod,
        verbose=True
    )

    task = Task(
        description=user_task,
        agent=researcher,
        expected_output="Clear, useful final answer from the Supreme Moderator. Keep it natural and to the point."
    )

    crew = Crew(
        agents=[researcher, scout, coder, moderator],
        tasks=[task],
        process=Process.sequential,   # ← much more stable than hierarchical
        verbose=True
    )
    result = crew.kickoff()
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
