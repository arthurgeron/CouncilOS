import os
os.environ["OPENAI_API_KEY"] = "ollama"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from crewai import Agent, Task, Crew, Process, LLM
import asyncio
from concurrent.futures import ThreadPoolExecutor
import uvicorn
import time

from tools import network_scout

app = FastAPI(title="M3 Council API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

executor = ThreadPoolExecutor(max_workers=3)

class Query(BaseModel):
    task: str

def run_crew_sync(user_task: str):
    # === STRONG AGENTS (no more looping) ===
    llm_7b   = LLM(model="ollama/qwen2.5:7b",      base_url=OLLAMA_BASE_URL, temperature=0.7, keep_alive="-1")
    llm_14b  = LLM(model="ollama/qwen2.5:14b",     base_url=OLLAMA_BASE_URL, temperature=0.7, keep_alive="-1")
    llm_code = LLM(model="ollama/deepseek-coder:6.7b", base_url=OLLAMA_BASE_URL, temperature=0.3, keep_alive="-1")
    llm_mod  = LLM(model="ollama/qwen2.5:32b",     base_url=OLLAMA_BASE_URL, temperature=0.3, keep_alive="-1")

    researcher = Agent(
        role="Fast Researcher",
        goal="Quickly gather relevant facts and context",
        backstory="You are a fast, no-nonsense researcher. You give concise, useful information and never overthink.",
        llm=llm_7b,
        verbose=True
    )

    scout = Agent(
        role="Network & File Scout",
        goal="Find files, folders, and local network resources when relevant",
        backstory="You know the user's entire Mac and any connected NAS. You only use tools when the task actually needs file/network discovery.",
        llm=llm_14b,
        tools=[network_scout],
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
    return crew.kickoff()

# ====================== OPENWEBUI & COUNCIL ENDPOINTS (unchanged) ======================
@app.post("/run-council")
async def run_council(query: Query):
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(executor, run_crew_sync, query.task)
    return {"result": str(result)}

@app.post("/v1/chat/completions")
async def openai_chat_completions(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    task = messages[-1]["content"] if messages else "Hello"
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(executor, run_crew_sync, task)

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