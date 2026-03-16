---
name: council-architecture-review
description: Reviews CouncilOS orchestration and architecture decisions for correctness, role boundaries, safety, and maintainability. Use when changing agent roles/models, CrewAI flow, API behavior, or Docker/Ollama/SearXNG integration.
---

# Council Architecture Review

## Triggers

- "review council architecture"
- "change agent roles/models"
- "new agent role"
- "redesign council"
- "add voting strategy"
- "refactor api.py orchestration"

## When to Use

- Before or after edits that affect: `api.py`, `tools/**/*.py`, `/run-council`, `/v1/chat/completions`, Docker wiring, or SearXNG integration.
- When validating strict sequential CrewAI flow with local Ollama + Docker + SearXNG.
- When checking compliance with `.cursor/rules/core-standards.mdc`, `.cursor/rules/council-orchestration-contracts.mdc`, `.cursor/rules/llm-output-safety.mdc`, and `.cursor/rules/testing-gates.mdc`.

## Step-by-step Process

1. Confirm architecture baseline is preserved:
   - Fast Researcher (qwen2.5:7b)
   - Network & File Scout (qwen2.5:14b)
   - Expert Coder (deepseek-coder:6.7b)
   - Supreme Moderator (qwen2.5:32b)
2. Verify CrewAI process is sequential only and Supreme Moderator is terminal (no delegation).
3. Validate role boundaries and tool scope; flag overlap, hidden side effects, or speculative behavior changes.
4. Validate handoff schema consistency in orchestration paths:
   - `summary`, `evidence`, `open_questions`, `done`
5. Check endpoint contract stability for `/run-council` and `/v1/chat/completions`.
6. Check safety controls: bounded retries, timeout budgets, malformed-handoff handling, explicit terminal states.
7. Check runtime assumptions: local-first Docker deployment, Ollama base URL wiring, SearXNG request compatibility.
8. Produce findings ordered by severity, then concrete fixes with smallest safe diff.

## Expected Output Format

```md
# Council Architecture Review

## Critical Findings
- [file/symbol] issue, production risk, required fix

## Important Findings
- [file/symbol] issue, impact, recommended fix

## Passed Checks
- Sequential CrewAI flow
- 4-agent boundary integrity
- Endpoint contract compatibility

## Recommended Next Patch
- 1-3 smallest safe diff changes only; avoid refactors unless required
```

## Examples

- Input: "I changed agent prompts and added fallback delegation."
  Output: This flags moderator delegation as a contract violation and proposes a terminal-only moderator fix.
- Input: "I moved search logic into coder."
  Output: This flags role leakage, reassigns discovery to Network & File Scout, and keeps Expert Coder code-only.
