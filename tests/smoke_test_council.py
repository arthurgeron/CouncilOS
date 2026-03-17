import json
import os
import sys
from urllib import error, request


BASE_URL = os.getenv("COUNCIL_BASE_URL", "http://localhost:8000")
TIMEOUT_SECONDS = int(os.getenv("COUNCIL_SMOKE_TIMEOUT", "90"))

# Exact curl examples from .cursor/skills/orchestration-smoke-test-runner/SKILL.md
RUN_COUNCIL_CURL = """curl -sS -X POST http://localhost:8000/run-council \
  -H "Content-Type: application/json" \
  -d '{"task":"Give a concise architecture summary of CouncilOS."}'"""

CHAT_COMPLETIONS_CURL = """curl -sS -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"council-os","messages":[{"role":"user","content":"Summarize CouncilOS in 3 bullets."}]}'"""

MISSING_INPUT_CURL = """curl -sS -X POST http://localhost:8000/run-council \
  -H "Content-Type: application/json" \
  -d '{}'"""

HANDOFF_SCHEMA_KEYS = ("summary", "evidence", "open_questions", "done")
NO_RELEVANT_MEMORY = "No relevant prior session memory found."
ROLE_BOUNDARIES = {
    "expert_coder": "Expert Coder (deepseek-coder:6.7b) remains code-only",
    "supreme_moderator": "Supreme Moderator (qwen2.5:32b) is terminal",
}


def _post_json(path: str, payload: dict):
    url = f"{BASE_URL}{path}"
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            raw = resp.read().decode("utf-8")
            return resp.getcode(), json.loads(raw)
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"raw_error": raw}
        return exc.code, parsed


def _iter_dict_nodes(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _iter_dict_nodes(value)
        return
    if isinstance(node, list):
        for item in node:
            yield from _iter_dict_nodes(item)


def _assert_handoff_schema_if_observable(response_obj: dict) -> None:
    for candidate in _iter_dict_nodes(response_obj):
        present = [key for key in HANDOFF_SCHEMA_KEYS if key in candidate]
        if present:
            missing = [key for key in HANDOFF_SCHEMA_KEYS if key not in candidate]
            assert not missing, f"Handoff schema incomplete, missing: {missing}"


def _assert_role_boundaries_if_observable(text: str) -> None:
    lower = text.lower()
    if "supreme moderator" in lower:
        assert "delegate more work" not in lower, ROLE_BOUNDARIES["supreme_moderator"]
    if "expert coder" in lower:
        assert "non-coding chatter" not in lower, ROLE_BOUNDARIES["expert_coder"]


def test_run_council_success_path() -> None:
    status, body = _post_json(
        "/run-council",
        {"task": "Give a concise architecture summary of CouncilOS."},
    )
    assert status == 200
    assert isinstance(body, dict)
    assert isinstance(body.get("result"), str) and body["result"].strip()
    _assert_handoff_schema_if_observable(body)
    _assert_role_boundaries_if_observable(body["result"])


def test_chat_completions_success_path() -> None:
    status, body = _post_json(
        "/v1/chat/completions",
        {
            "model": "council-os",
            "messages": [{"role": "user", "content": "Summarize CouncilOS in 3 bullets."}],
        },
    )
    assert status == 200
    assert isinstance(body, dict)
    assert body.get("object") == "chat.completion"
    assert isinstance(body.get("choices"), list) and body["choices"]
    content = body["choices"][0]["message"]["content"]
    assert isinstance(content, str) and content.strip()
    _assert_handoff_schema_if_observable(body)
    _assert_role_boundaries_if_observable(content)


def test_run_council_missing_input_failure_path() -> None:
    status, body = _post_json("/run-council", {})
    assert status >= 400, "Missing input must fail explicitly"
    assert isinstance(body, dict)
    assert any(key in body for key in ("detail", "error", "message")), body


def test_run_council_memory_integration_success_path() -> None:
    status, body = _post_json(
        "/run-council",
        {
            "task": (
                "remember last time and update our previous plan.\n"
                "session_summary: Prior session focused on minimal memory integration.\n"
                "key_facts: Keep sequential CrewAI | Preserve endpoint contracts"
            )
        },
    )
    assert status == 200
    assert isinstance(body, dict)
    assert isinstance(body.get("result"), str) and body["result"].strip()
    _assert_handoff_schema_if_observable(body)
    _assert_role_boundaries_if_observable(body["result"])


def test_chat_completions_memory_integration_success_path() -> None:
    status, body = _post_json(
        "/v1/chat/completions",
        {
            "model": "council-os",
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "from earlier session, remember last time and update our previous plan.\n"
                        "session_summary: Prior session focused on memory recall behavior.\n"
                        "key_facts: Use memory only when history is relevant | Keep responses concise"
                    ),
                }
            ],
        },
    )
    assert status == 200
    assert isinstance(body, dict)
    assert body.get("object") == "chat.completion"
    assert isinstance(body.get("choices"), list) and body["choices"]
    content = body["choices"][0]["message"]["content"]
    assert isinstance(content, str) and content.strip()
    _assert_handoff_schema_if_observable(body)
    _assert_role_boundaries_if_observable(content)


def test_run_council_memory_non_relevant_path() -> None:
    status, body = _post_json(
        "/run-council",
        {
            "task": (
                "Call Session Memory Recall Tool with this exact query first: "
                "'Generate a 3-word title for this text: fast release notes.' "
                "If memory is not relevant, include this exact line in your answer: "
                "'No relevant prior session memory found.' Then complete the title task."
            )
        },
    )
    assert status == 200
    assert isinstance(body, dict)
    result = str(body.get("result", ""))
    assert result.strip()
    assert "Memory unavailable:" not in result, result
    _assert_handoff_schema_if_observable(body)
    _assert_role_boundaries_if_observable(result)


def test_chat_completions_memory_non_relevant_path() -> None:
    status, body = _post_json(
        "/v1/chat/completions",
        {
            "model": "council-os",
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Call Session Memory Recall Tool with this exact query first: "
                        "'Generate 3 concise tags for this sentence.' "
                        "If memory is not relevant, include this exact line in your answer: "
                        "'No relevant prior session memory found.' Then complete the tags task."
                    ),
                }
            ],
        },
    )
    assert status == 200
    assert isinstance(body, dict)
    assert body.get("object") == "chat.completion"
    assert isinstance(body.get("choices"), list) and body["choices"]
    content = str(body["choices"][0]["message"]["content"])
    assert content.strip()
    assert NO_RELEVANT_MEMORY in content, content


def test_run_council_memory_failure_path() -> None:
    status, body = _post_json(
        "/run-council",
        {"task": "remember last time and continue our previous plan with context from earlier sessions"},
    )
    assert status == 200
    assert isinstance(body, dict)
    result_text = str(body.get("result", ""))
    assert result_text.strip()
    _assert_handoff_schema_if_observable(body)
    _assert_role_boundaries_if_observable(result_text)


def test_chat_completions_memory_failure_path() -> None:
    status, body = _post_json(
        "/v1/chat/completions",
        {
            "model": "council-os",
            "messages": [
                {
                    "role": "user",
                    "content": "from earlier session, compare prior decisions and continue previous plan",
                }
            ],
        },
    )
    assert status == 200
    assert isinstance(body, dict)
    content = body["choices"][0]["message"]["content"]
    assert isinstance(content, str) and content.strip()
    _assert_handoff_schema_if_observable(body)
    _assert_role_boundaries_if_observable(content)


def test_quality_gate_pass_fail_retry_behavior() -> None:
    import api as api_module

    original_runner = api_module._run_crew_single_attempt
    original_submit = api_module._submit_memory_write_post_crew

    try:
        # pass path: no retry
        pass_calls = []
        pass_responses = iter(
            [
                (
                    "pass-final",
                    {"score": 9.0, "critique": "Looks good.", "pass": True, "suggestions": []},
                ),
            ]
        )

        def _pass_runner(user_task: str, retry_critique: str = ""):
            pass_calls.append(retry_critique)
            return next(pass_responses)

        api_module._run_crew_single_attempt = _pass_runner
        api_module._submit_memory_write_post_crew = lambda **kwargs: None
        pass_result = api_module.run_crew_sync("test task", "/run-council", "req-pass")
        assert pass_result == "pass-final"
        assert pass_calls == [""], pass_calls

        # fail + retry path: exactly one retry with critique injection
        retry_calls = []
        retry_responses = iter(
            [
                (
                    "retry-first",
                    {
                        "score": 3.0,
                        "critique": "Needs stronger factual grounding.",
                        "pass": False,
                        "suggestions": ["Add verifiable evidence."],
                    },
                ),
                (
                    "retry-second",
                    {"score": 8.0, "critique": "Now sufficient.", "pass": True, "suggestions": []},
                ),
            ]
        )

        def _retry_runner(user_task: str, retry_critique: str = ""):
            retry_calls.append(retry_critique)
            return next(retry_responses)

        api_module._run_crew_single_attempt = _retry_runner
        retry_result = api_module.run_crew_sync("test task", "/run-council", "req-retry")
        assert retry_result == "retry-second"
        assert len(retry_calls) == 2, retry_calls
        assert retry_calls[0] == ""
        assert "Needs stronger factual grounding." in retry_calls[1]

        # bounded behavior: no second retry beyond max=1
        bounded_calls = []
        bounded_responses = iter(
            [
                (
                    "bounded-first",
                    {
                        "score": 2.0,
                        "critique": "First failure.",
                        "pass": False,
                        "suggestions": ["Improve evidence quality."],
                    },
                ),
                (
                    "bounded-second",
                    {
                        "score": 1.0,
                        "critique": "Still failing after retry.",
                        "pass": False,
                        "suggestions": ["Do not retry again."],
                    },
                ),
            ]
        )

        def _bounded_runner(user_task: str, retry_critique: str = ""):
            bounded_calls.append(retry_critique)
            return next(bounded_responses)

        api_module._run_crew_single_attempt = _bounded_runner
        bounded_result = api_module.run_crew_sync("test task", "/run-council", "req-bounded")
        assert bounded_result == "bounded-second"
        assert len(bounded_calls) == 2, bounded_calls
    finally:
        api_module._run_crew_single_attempt = original_runner
        api_module._submit_memory_write_post_crew = original_submit


if __name__ == "__main__":
    tests = [
        test_run_council_success_path,
        test_chat_completions_success_path,
        test_run_council_missing_input_failure_path,
        test_run_council_memory_integration_success_path,
        test_chat_completions_memory_integration_success_path,
        test_run_council_memory_non_relevant_path,
        test_chat_completions_memory_non_relevant_path,
        test_run_council_memory_failure_path,
        test_chat_completions_memory_failure_path,
        test_quality_gate_pass_fail_retry_behavior,
    ]
    failures = 0
    for test_fn in tests:
        try:
            test_fn()
            print(f"PASS: {test_fn.__name__}")
        except Exception as exc:  # noqa: BLE001 - intentional for tiny inline runner
            failures += 1
            print(f"FAIL: {test_fn.__name__}: {exc}")
    if failures:
        sys.exit(1)
    print("All smoke tests passed.")
