import unittest

from tools import memory as memory_module


class MemoryUnitTests(unittest.TestCase):
    def test_extract_memory_payload_structured(self) -> None:
        summary, facts = memory_module._extract_memory_payload(
            "session_summary: Plan migration done\nkey_facts: Keep API stable | Use deterministic contracts"
        )
        self.assertEqual(summary, "Plan migration done")
        self.assertEqual(facts, ["Keep API stable", "Use deterministic contracts"])

    def test_extract_memory_payload_fallback(self) -> None:
        summary, facts = memory_module._extract_memory_payload("We aligned on deterministic trigger behavior.")
        self.assertTrue(summary)
        self.assertTrue(facts)

    def test_trigger_rejects_keyword_only_false_positive(self) -> None:
        query = "generate title tags for remember last time content"
        self.assertFalse(memory_module.should_trigger_recall(query))

    def test_trigger_accepts_semantic_prior_context(self) -> None:
        query = "continue prior decisions from earlier session and compare what changed"
        self.assertTrue(memory_module.should_trigger_recall(query))

    def test_deterministic_id_derivation(self) -> None:
        summary = "  Keep   endpoint shape unchanged "
        facts = ["Use deterministic contract", "Bound retries"]
        first = memory_module._derive_memory_id(summary, facts)
        second = memory_module._derive_memory_id("keep endpoint shape unchanged", list(reversed(facts)))
        self.assertEqual(first, second)

    def test_normalize_legacy_payload_accepts_legacy_shapes(self) -> None:
        payload = {"summary": "Legacy summary", "key_facts": "legacy fact", "stored_at": "2026-01-01T00:00:00Z"}
        normalized = memory_module._normalize_legacy_payload(payload)
        self.assertIsNotNone(normalized)
        self.assertEqual(normalized["summary"], "Legacy summary")
        self.assertEqual(normalized["key_facts"], ["legacy fact"])

    def test_collect_prune_candidates_malformed_timestamp_oldest(self) -> None:
        ids = ["a", "b", "c"]
        metadatas = [
            {"stored_at": "2026-01-02T00:00:00+00:00"},
            {"stored_at": "not-a-timestamp"},
            {"stored_at": "2026-01-01T00:00:00+00:00"},
        ]
        candidates = memory_module._collect_prune_candidates(ids, metadatas)
        self.assertEqual(candidates[0][1], "b")
        self.assertEqual(candidates[1][1], "c")
        self.assertEqual(candidates[2][1], "a")

    def test_memory_executor_is_dedicated(self) -> None:
        thread_name_prefix = getattr(memory_module._MEMORY_EXECUTOR, "_thread_name_prefix", "")
        self.assertIn("memory", thread_name_prefix)


if __name__ == "__main__":
    unittest.main()
