---
name: incident-triage-playbook
description: Triage and contain CouncilOS runtime incidents such as timeouts, malformed handoffs, runaway loops, role leakage, tool failures, and deadlocks. Use during production-like debugging before making broader architecture changes.
---

# Incident Triage Playbook

## Triggers

- "triage timeout"
- "council stuck" or "deadlock"
- "malformed handoff"
- "role leakage" or "agent doing wrong job"
- "searxng failure" or "tool error"

## When to Use

- When `/run-council` or `/v1/chat/completions` regress, hang, or return low-signal output.
- After orchestration or prompt changes where failures are unclear.
- With these guardrails: `.cursor/rules/core-standards.mdc`, `.cursor/rules/council-orchestration-contracts.mdc`, `.cursor/rules/llm-output-safety.mdc`, `.cursor/rules/testing-gates.mdc`.
- Pair with skills: `orchestration-smoke-test-runner`, `council-architecture-review`, and `agent-contract-writer`.

## Step-by-step Triage Process

1. Stabilize first: reproduce with one minimal prompt and one endpoint at a time.
2. Classify incident: timeout, malformed handoff, runaway loop, role leakage, tool failure, or deadlock.
3. Verify baseline contracts:
   - Fast Researcher (qwen2.5:7b)
   - Network & File Scout (qwen2.5:14b)
   - Expert Coder (deepseek-coder:6.7b)
   - Supreme Moderator (qwen2.5:32b)
   - sequential CrewAI only, moderator terminal.
4. Validate handoff schema integrity at each transition:
   - `summary`, `evidence`, `open_questions`, `done`
5. Run fast smoke probes for `/run-council` and `/v1/chat/completions`, then one failure-path probe.
6. Isolate failing layer: endpoint contract, orchestration logic, tool adapter, model output quality, or infra wiring (Docker/Ollama/SearXNG).
7. Apply smallest safe diff fix, re-run smokes, and document residual risk.

## Common Issues & Quick Fixes

- **Timeouts:** lower prompt scope, tighten timeout budget, cap retries, remove redundant tool calls.
- **Malformed handoffs:** enforce schema validation + bounded repair, fail explicitly on second violation.
- **Runaway loops:** add unchanged-prompt guard and hard max-step terminal condition.
- **Role leakage:** restore strict boundaries; keep Expert Coder code-only and Supreme Moderator terminal.
- **SearXNG/tool failures:** verify service reachability/config, return explicit degraded-mode message, avoid silent fallback loops.
- **Deadlocks/stalls:** ensure each step has completion criteria and one terminal exit.

## Expected Output Format

```md
# CouncilOS Incident Report

## Incident Summary
- endpoint:
- symptom:
- severity:

## Reproduction
- minimal prompt:
- command:

## Root Cause
- layer: orchestration|endpoint|tool|infra|model
- evidence:

## Fix Applied (Smallest Safe Diff)
- change:
- why this is minimal:

## Verification
- /run-council: PASS|FAIL
- /v1/chat/completions: PASS|FAIL
- failure-path probe: PASS|FAIL

## Follow-ups
- contract update needed:
- test to add next:
```
