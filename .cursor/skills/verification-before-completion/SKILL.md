---
name: verification-before-completion
description: Enforces mandatory verification for CouncilOS changes before declaring completion. Use after any orchestration, endpoint, agent, or runtime change to prevent regressions and silent failures.
---

# Verification Before Completion

## Triggers

- "verify before done"
- "is this safe to ship"
- "final check before completion"
- "confirm no regression"

## When to Use

- After any change touching `api.py`, `tools/**/*.py`, Docker runtime files, or SearXNG config.
- Before reporting task completion on CouncilOS endpoint or orchestration work.
- To enforce `.cursor/rules/testing-gates.mdc` with support from `orchestration-smoke-test-runner`, `council-architecture-review`, and `incident-triage-playbook`.

## Step-by-step Process

1. Confirm requested scope only; no unrequested refactors or behavior drift.
2. Validate architecture contracts remain intact:
   - Fast Researcher (qwen2.5:7b),
   - Network & File Scout (qwen2.5:14b),
   - Expert Coder (deepseek-coder:6.7b),
   - Supreme Moderator (qwen2.5:32b),
   - sequential CrewAI and terminal moderator.
3. Validate handoff schema compatibility where applicable: `summary`, `evidence`, `open_questions`, `done`.
4. Run success-path checks for both endpoints:
   - `/run-council`
   - `/v1/chat/completions`
5. Run at least one failure-path check:
   - timeout, malformed handoff, tool failure, or missing input.
6. Validate runtime dependencies if relevant:
   - Docker services healthy,
   - Ollama reachable,
   - SearXNG reachable and responding.
7. Report explicit pass/fail and any unverified items; never imply unrun checks passed.

## Expected Output Format

```md
# CouncilOS Verification Checklist

## Scope Check
- requested-only changes: PASS|FAIL
- behavior compatibility: PASS|FAIL

## Contract Check
- 4-agent boundaries: PASS|FAIL
- sequential + terminal moderator: PASS|FAIL
- handoff schema compatibility: PASS|FAIL

## Endpoint Validation
- /run-council success path: PASS|FAIL
- /v1/chat/completions success path: PASS|FAIL
- failure-path test: PASS|FAIL

## Runtime Validation
- docker: PASS|FAIL
- ollama: PASS|FAIL
- searxng: PASS|FAIL

## Final Status
- ready to complete: YES|NO
- blocking issue(s):
```

## Examples

- Input: "Done with retry changes, can we close?"
  Output: This runs endpoint success and failure checks, confirms bounded retries, and returns YES or NO with explicit blockers.

- Input: "I touched Docker and API."
  Output: This verifies runtime reachability plus contract and endpoint checks before completion.
