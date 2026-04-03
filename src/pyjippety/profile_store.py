from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HistoryEntry:
    time: str
    kind: str
    text: str


class ProfileStore:
    def __init__(self, env_path: Path) -> None:
        self.env_path = env_path

    @property
    def root(self) -> Path:
        return self.env_path.parent / "profiles"

    def profile_dir(self, name: str) -> Path:
        return self.root / (name.strip() or "default")

    def settings_path(self, name: str) -> Path:
        return self.profile_dir(name) / "settings.json"

    def history_path(self, name: str) -> Path:
        return self.profile_dir(name) / "history.json"

    def list_profiles(self) -> list[str]:
        profiles = ["default"]
        if self.root.exists():
            profiles.extend(sorted(path.name for path in self.root.iterdir() if path.is_dir()))
        return sorted(set(profiles))

    def load_settings(self, name: str) -> dict[str, str]:
        path = self.settings_path(name)
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return {str(key): str(value) for key, value in payload.items()}

    def save_settings(self, name: str, values: dict[str, str]) -> None:
        path = self.settings_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(values, indent=2), encoding="utf-8")

    def load_history(self, name: str) -> list[dict[str, str]]:
        path = self.history_path(name)
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        return [
            {
                "time": str(entry.get("time", "")),
                "kind": str(entry.get("kind", "")),
                "text": str(entry.get("text", "")),
            }
            for entry in payload
        ]

    def save_history(self, name: str, entries: list[dict[str, str]]) -> None:
        path = self.history_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entries[-100:], indent=2), encoding="utf-8")


__all__ = ["HistoryEntry", "ProfileStore"]
