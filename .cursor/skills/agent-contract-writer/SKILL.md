---
name: agent-contract-writer
description: Writes or updates CouncilOS agent contracts and orchestration handoff definitions with strict role boundaries and deterministic outputs. Use when adding/changing prompts, responsibilities, retries, or handoff structure.
---

# Agent Contract Writer

## Triggers

- "write agent contracts"
- "update role prompts"
- "define handoff format"
- "tighten orchestration boundaries"

## When to Use

- When changing responsibilities, prompts, model routing, or failure handling in `api.py` and `tools/**/*.py`.
- When introducing new guardrails for sequential CrewAI operation.
- When ensuring consistency with `.cursor/rules/core-standards.mdc`, `.cursor/rules/council-orchestration-contracts.mdc`, and `.cursor/rules/llm-output-safety.mdc`.

## Step-by-step Process

1. Lock role map and model ownership:
   - Fast Researcher (qwen2.5:7b): fast context/facts.
   - Network & File Scout (qwen2.5:14b): local file/network discovery.
   - Expert Coder (deepseek-coder:6.7b): code generation only.
   - Supreme Moderator (qwen2.5:32b): final synthesis only.
2. Define contract fields per role:
   - objective, allowed_tools, forbidden_actions, completion_criteria, retry_policy, timeout_budget.
3. Define mandatory handoff schema for all non-terminal transitions:
   - `summary`, `evidence`, `open_questions`, `done`
4. Add deterministic rules:
   - bounded retries, no recursive delegation, explicit terminal state.
5. Add endpoint-compatibility notes:
   - no behavior drift for `/run-council` and `/v1/chat/completions`.
6. Add safety constraints:
   - no unverifiable claims as facts, no secret/path leakage, no cross-role contamination.
7. Produce contract patch text ready for direct insertion into prompts/config.

## Expected Output Format

```md
# CouncilOS Agent Contracts

## Role Contracts
### Fast Researcher (qwen2.5:7b)
- objective: Gather external facts and concise context for the task.
- allowed_tools: web_search
- forbidden_actions: Writing production code, delegating final decisions.
- completion_criteria: Returns evidence-backed context with no open factual blockers.
- retry_policy: max 2 retries for missing evidence.

### Network & File Scout (qwen2.5:14b)
- objective: Discover local files/network resources relevant to the request.
- allowed_tools: network_scout
- forbidden_actions: Final synthesis, speculative claims without discovery output.
- completion_criteria: Returns concrete paths/resources or explicit "not found".
- retry_policy: max 2 retries for transient tool failures.

### Expert Coder (deepseek-coder:6.7b)
- objective: Produce clean code changes only when coding is requested.
- allowed_tools: none unless explicitly provided
- forbidden_actions: Broad research, architecture arbitration, extra refactors.
- completion_criteria: Minimal behavior-preserving patch with clear rationale.
- retry_policy: max 1 retry for malformed output.

### Supreme Moderator (qwen2.5:32b)
- objective: Deliver one final synthesis from prior handoffs.
- allowed_tools: none
- forbidden_actions: Delegation, new work creation, recursive orchestration.
- completion_criteria: Final answer returned; process terminates.
- retry_policy: max 1 retry for malformed final response.

## Handoff Schema
- summary: string
- evidence: list
- open_questions: list
- done: boolean

## Runtime Guards
- max retries: per-role values from contracts
- timeout budgets: set per endpoint and per role, with strict total request cap
- terminal condition: Supreme Moderator returns one final answer and execution stops
```

## Examples
- Input: "Coder keeps answering non-code research questions."
  - Output: Adds explicit forbidden action for Expert Coder and reroutes research to Fast Researcher.
- Input: "Need safer handoffs."
  - Output: Adds required `summary`/`evidence`/`open_questions`/`done` schema plus malformed-output handling.
