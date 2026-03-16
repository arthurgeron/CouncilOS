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


if __name__ == "__main__":
    tests = [
        test_run_council_success_path,
        test_chat_completions_success_path,
        test_run_council_missing_input_failure_path,
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
