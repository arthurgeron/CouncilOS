---
name: systematic-debugging
description: Runs a structured, reproducible debugging workflow for CouncilOS incidents across orchestration, endpoints, agents, and tool integrations. Use when failures are unclear, intermittent, or cross multiple layers.
---

# Systematic Debugging

## Triggers

- "systematically debug this"
- "intermittent /run-council failure"
- "why is /v1/chat/completions hanging"
- "find root cause, not workaround"

## When to Use

- When failures span orchestration, endpoint behavior, model routing, or tool integrations.
- For CouncilOS stack issues involving Docker, Ollama, and SearXNG.
- With guardrails from `.cursor/rules/core-standards.mdc`, `.cursor/rules/council-orchestration-contracts.mdc`, `.cursor/rules/llm-output-safety.mdc`, and `.cursor/rules/testing-gates.mdc`.
- Pair with `incident-triage-playbook` for containment and `orchestration-smoke-test-runner` for validation.

## Step-by-step Process

1. Reproduce with one endpoint and one minimal prompt; record exact command and output.
2. Classify failure: timeout, malformed handoff, runaway loop, role leakage, tool failure, or deadlock.
3. Verify architecture invariants:
   - Fast Researcher (qwen2.5:7b),
   - Network & File Scout (qwen2.5:14b),
   - Expert Coder (deepseek-coder:6.7b),
   - Supreme Moderator (qwen2.5:32b),
   - sequential CrewAI only, moderator terminal.
4. Validate handoff schema at each transition: `summary`, `evidence`, `open_questions`, `done`.
5. Isolate layer by binary narrowing:
   - endpoint contract,
   - orchestration logic,
   - tool adapter (SearXNG/network),
   - model output quality,
   - Docker/Ollama reachability.
6. Form one hypothesis, apply one smallest safe diff, re-run the same reproduction.
7. Confirm fix on both `/run-council` and `/v1/chat/completions`, plus one failure-path probe.
8. Document root cause, evidence, fix, and follow-up test.

## Expected Output Format

```md
# CouncilOS Debug Report

## Reproduction
- endpoint:
- prompt:
- command:
- observed:

## Diagnosis
- failure class:
- failing layer:
- evidence:

## Fix (Smallest Safe Diff)
- change:
- why this fixes root cause:

## Verification
- /run-council: PASS|FAIL
- /v1/chat/completions: PASS|FAIL
- failure-path probe: PASS|FAIL

## Follow-up
- contract/rule update:
- smoke or test to add:
```

## Examples

- Input: "Requests sometimes hang for 90s."
  Output: This classifies a timeout, narrows the issue to retry budget, applies a bounded-retry fix, and verifies both endpoints.

- Input: "Coder is doing scouting work."
  Output: This flags role leakage, restores strict role boundaries, and verifies handoff schema plus terminal moderator behavior.
