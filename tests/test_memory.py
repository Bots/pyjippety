from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pyjippety.config import AssistantConfig
from pyjippety.memory import (
    MemoryAwareResponder,
    MemoryStore,
    build_memory_store,
    extract_memory_command,
    is_memory_query,
)


class FakeResponder:
    def __init__(self):
        self.prompts = []

    def reply(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "reply"


class MemoryTests(unittest.TestCase):
    def test_extract_memory_command(self):
        self.assertEqual(
            extract_memory_command("Remember that I prefer metric units"),
            "I prefer metric units",
        )

    def test_memory_query_detection(self):
        self.assertTrue(is_memory_query("what do you remember about me"))

    def test_memory_aware_responder_stores_note_without_model_call(self):
        with TemporaryDirectory() as temp_dir:
            store = MemoryStore(Path(temp_dir) / "memory.json", AssistantConfig())
            responder = FakeResponder()
            memory_responder = MemoryAwareResponder(responder, store)

            reply = memory_responder.reply("remember that my name is Sam")

            self.assertEqual(reply, "Okay. I will remember that.")
            self.assertEqual(store.state.facts, ["my name is Sam"])
            self.assertEqual(responder.prompts, [])

    def test_memory_aware_responder_uses_context_and_stores_turn(self):
        with TemporaryDirectory() as temp_dir:
            store = MemoryStore(Path(temp_dir) / "memory.json", AssistantConfig())
            store.remember("I prefer short answers.")
            responder = FakeResponder()
            memory_responder = MemoryAwareResponder(responder, store)

            reply = memory_responder.reply("What should I cook tonight?")

            self.assertEqual(reply, "reply")
            self.assertIn("Saved memory:", responder.prompts[0])
            self.assertIn("Current user request:\nWhat should I cook tonight?", responder.prompts[0])
            self.assertEqual(store.state.turns[-1]["user"], "What should I cook tonight?")

    def test_build_memory_store_respects_disabled_memory(self):
        config = AssistantConfig(memory_enabled=False)
        store = build_memory_store(config, {})
        self.assertIsNone(store)


if __name__ == "__main__":
    unittest.main()
