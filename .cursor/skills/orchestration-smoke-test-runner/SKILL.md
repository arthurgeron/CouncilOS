---
name: orchestration-smoke-test-runner
description: Runs fast, deterministic smoke checks for CouncilOS orchestration and endpoints, including success and failure paths. Use after Python/orchestration changes to enforce testing-gates and prevent regressions.
---

# Orchestration Smoke Test Runner

## Triggers

- "run smoke tests"
- "validate /run-council"
- "check /v1/chat/completions"
- "post-change orchestration verification"

## When to Use

- After edits to orchestration, prompts, retries, tool routing, endpoint handlers, or Docker runtime setup.
- For local-first validation with Docker + Ollama + SearXNG.
- To enforce `.cursor/rules/testing-gates.mdc` and support `.cursor/rules/core-standards.mdc`, `.cursor/rules/council-orchestration-contracts.mdc`, and `.cursor/rules/llm-output-safety.mdc`.

## Step-by-step Process

1. Confirm prerequisites:
   - council service reachable,
   - Ollama reachable via configured base URL,
   - SearXNG reachable via configured base URL.
2. Run success-path smoke for `/run-council` with a stable prompt.
3. Run success-path smoke for `/v1/chat/completions` with equivalent intent.
4. Validate response shape and orchestration safety signals:
   - terminal completion,
   - no runaway loop symptoms,
   - handoff schema presence where observable (`summary`, `evidence`, `open_questions`, `done`).
5. Run one failure-path test:
   - timeout budget breach, malformed handoff, tool failure, or missing input.
6. Verify role-boundary behavior:
   - Expert Coder (deepseek-coder:6.7b) remains code-only,
   - Supreme Moderator (qwen2.5:32b) is terminal.
7. Report pass/fail with minimal reproduction commands and smallest next fix.

## Expected Output Format

```md
# CouncilOS Smoke Test Report

## Environment
- docker:
- ollama:
- searxng:

## Success Path
- /run-council: PASS|FAIL
- /v1/chat/completions: PASS|FAIL
- run-council curl:
  curl -sS -X POST http://localhost:8000/run-council \
    -H "Content-Type: application/json" \
    -d '{"task":"Give a concise architecture summary of CouncilOS."}'
- chat-completions curl:
  curl -sS -X POST http://localhost:8000/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{"model":"council-os","messages":[{"role":"user","content":"Summarize CouncilOS in 3 bullets."}]}'

## Failure Path
- scenario:
- expected:
- actual:
- result: PASS|FAIL
- timeout/missing-input curl:
  curl -sS -X POST http://localhost:8000/run-council \
    -H "Content-Type: application/json" \
    -d '{}'
- malformed-handoff probe curl:
  curl -sS -X POST http://localhost:8000/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{"model":"council-os","messages":[]}'

## Regressions and Next Patch
- issue:
- smallest safe fix:
```

## Examples

- Input: "I changed retry logic; validate quickly."
  - Output: Runs both endpoint smokes + timeout failure test and reports bounded-retry compliance.
- Input: "Search tool changed."
  - Output: Verifies SearXNG-backed path still succeeds and failure behavior is explicit, not silent.
