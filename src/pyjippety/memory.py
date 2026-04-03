from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .config import AssistantConfig


@dataclass
class MemoryState:
    facts: list[str]
    turns: list[dict[str, str]]


def memory_file_path(environment: Mapping[str, str] | None = None) -> Path:
    environment = environment or {}
    configured = environment.get("PYJIPPETY_MEMORY_FILE", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".config" / "pyjippety" / "memory.json"


class MemoryStore:
    def __init__(self, path: Path, config: AssistantConfig) -> None:
        self.path = path
        self.config = config
        self.state = self._load()

    def _load(self) -> MemoryState:
        if not self.path.exists():
            return MemoryState(facts=[], turns=[])
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return MemoryState(facts=[], turns=[])
        facts = [str(item).strip() for item in payload.get("facts", []) if str(item).strip()]
        turns = [
            {
                "user": str(item.get("user", "")).strip(),
                "assistant": str(item.get("assistant", "")).strip(),
            }
            for item in payload.get("turns", [])
            if str(item.get("user", "")).strip() or str(item.get("assistant", "")).strip()
        ]
        return MemoryState(facts=facts[: self.config.memory_fact_limit], turns=turns[-self.config.memory_turn_limit :])

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "facts": self.state.facts[: self.config.memory_fact_limit],
            "turns": self.state.turns[-self.config.memory_turn_limit :],
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def clear(self) -> None:
        self.state = MemoryState(facts=[], turns=[])
        self.save()

    def remember(self, note: str) -> None:
        cleaned = note.strip()
        if not cleaned:
            return
        facts = [item for item in self.state.facts if item.lower() != cleaned.lower()]
        facts.insert(0, cleaned)
        self.state.facts = facts[: self.config.memory_fact_limit]
        self.save()

    def add_turn(self, user: str, assistant: str) -> None:
        self.state.turns.append({"user": user.strip(), "assistant": assistant.strip()})
        self.state.turns = self.state.turns[-self.config.memory_turn_limit :]
        self.save()

    def build_context_block(self) -> str:
        parts: list[str] = []
        if self.state.facts:
            parts.append("Saved memory:")
            parts.extend(f"- {fact}" for fact in self.state.facts)
        if self.state.turns:
            parts.append("Recent conversation:")
            for turn in self.state.turns:
                if turn["user"]:
                    parts.append(f"User: {turn['user']}")
                if turn["assistant"]:
                    parts.append(f"Assistant: {turn['assistant']}")
        return "\n".join(parts)

    def memory_summary(self) -> str:
        if not self.state.facts and not self.state.turns:
            return "I am not storing anything yet."
        lines: list[str] = []
        if self.state.facts:
            lines.append("Saved notes:")
            lines.extend(f"- {fact}" for fact in self.state.facts)
        if self.state.turns:
            lines.append("Recent exchanges:")
            lines.extend(
                f"- {turn['user']}"
                for turn in self.state.turns[-3:]
                if turn["user"]
            )
        return "\n".join(lines)


def extract_memory_command(prompt: str) -> str | None:
    lowered = prompt.strip().lower()
    prefixes = (
        "remember that ",
        "remember ",
        "please remember that ",
        "please remember ",
    )
    for prefix in prefixes:
        if lowered.startswith(prefix):
            return prompt.strip()[len(prefix) :].strip()
    return None


def is_memory_query(prompt: str) -> bool:
    lowered = prompt.strip().lower()
    return lowered in {
        "what do you remember about me",
        "what do you remember",
        "show memory",
    }


class MemoryAwareResponder:
    def __init__(self, base_responder: Any, memory_store: MemoryStore | None) -> None:
        self.base_responder = base_responder
        self.memory_store = memory_store

    def reply(self, prompt: str) -> str:
        if self.memory_store is None:
            return self.base_responder.reply(prompt)

        note = extract_memory_command(prompt)
        if note:
            self.memory_store.remember(note)
            return "Okay. I will remember that."

        if is_memory_query(prompt):
            return self.memory_store.memory_summary()

        context = self.memory_store.build_context_block()
        enriched_prompt = prompt
        if context:
            enriched_prompt = f"{context}\n\nCurrent user request:\n{prompt}"
        reply = self.base_responder.reply(enriched_prompt)
        self.memory_store.add_turn(prompt, reply)
        return reply


def build_memory_store(
    config: AssistantConfig, environment: Mapping[str, str] | None = None
) -> MemoryStore | None:
    if not config.memory_enabled:
        return None
    return MemoryStore(memory_file_path(environment), config)


__all__ = [
    "MemoryAwareResponder",
    "MemoryState",
    "MemoryStore",
    "build_memory_store",
    "extract_memory_command",
    "is_memory_query",
    "memory_file_path",
]
