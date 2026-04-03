from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


DEFAULT_SYSTEM_PROMPT = (
    "You are a desktop voice assistant. Answer clearly, helpfully, and briefly."
)
TRUE_ENV_VALUES = {"1", "true", "yes", "on"}


def parse_csv(raw: str) -> tuple[str, ...]:
    return tuple(chunk.strip() for chunk in raw.split(",") if chunk.strip())


def parse_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in TRUE_ENV_VALUES


def parse_optional_int(raw: str | None) -> int | None:
    if raw is None:
        return None
    value = raw.strip()
    return int(value) if value else None


def unique_nonempty(values: list[str]) -> tuple[str, ...]:
    unique_values: list[str] = []
    for value in values:
        if value and value not in unique_values:
            unique_values.append(value)
    return tuple(unique_values)


@dataclass(frozen=True)
class AssistantConfig:
    wake_word: str = "porcupine"
    porcupine_keyword: str | None = "porcupine"
    porcupine_keyword_path: str | None = None
    chat_model: str = "gpt-4o-mini"
    transcription_model: str = "gpt-4o-mini-transcribe"
    transcription_fallback_models: tuple[str, ...] = (
        "gpt-4o-transcribe",
        "whisper-1",
    )
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    listen_timeout: float = 5.0
    phrase_time_limit: float = 10.0
    tts_model: str = "gpt-4o-mini-tts"
    tts_fallback_models: tuple[str, ...] = ("tts-1", "tts-1-hd")
    tts_voice: str = "alloy"
    tts_speed: float = 1.0
    tts_instructions: str | None = None
    tts_enabled: bool = True
    energy_threshold: int = 300
    ambient_adjust_seconds: float = 1.0
    audio_device_index: int | None = None
    exit_words: tuple[str, ...] = (
        "quit assistant",
        "exit assistant",
        "stop listening",
    )

    @classmethod
    def from_env(cls) -> "AssistantConfig":
        return cls.from_mapping(os.environ)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> "AssistantConfig":
        exit_words = parse_csv(values.get("ASSISTANT_EXIT_WORDS", ""))
        keyword_path = values.get("ASSISTANT_PORCUPINE_KEYWORD_PATH", "").strip() or None
        return cls(
            wake_word=values.get("ASSISTANT_WAKE_WORD", "porcupine"),
            porcupine_keyword=values.get(
                "ASSISTANT_PORCUPINE_KEYWORD",
                "porcupine" if not keyword_path else "",
            )
            or None,
            porcupine_keyword_path=keyword_path,
            chat_model=values.get("ASSISTANT_CHAT_MODEL", cls.chat_model),
            transcription_model=values.get(
                "ASSISTANT_TRANSCRIPTION_MODEL", cls.transcription_model
            ),
            transcription_fallback_models=parse_csv(
                values.get(
                    "ASSISTANT_TRANSCRIPTION_FALLBACK_MODELS",
                    "gpt-4o-transcribe,whisper-1",
                )
            )
            or cls.transcription_fallback_models,
            system_prompt=values.get("ASSISTANT_SYSTEM_PROMPT", cls.system_prompt),
            listen_timeout=float(
                values.get("ASSISTANT_LISTEN_TIMEOUT", str(cls.listen_timeout))
            ),
            phrase_time_limit=float(
                values.get("ASSISTANT_PHRASE_TIME_LIMIT", str(cls.phrase_time_limit))
            ),
            tts_model=values.get("ASSISTANT_TTS_MODEL", cls.tts_model),
            tts_fallback_models=parse_csv(
                values.get("ASSISTANT_TTS_FALLBACK_MODELS", "tts-1,tts-1-hd")
            )
            or cls.tts_fallback_models,
            tts_voice=values.get("ASSISTANT_TTS_VOICE", cls.tts_voice),
            tts_speed=float(values.get("ASSISTANT_TTS_SPEED", str(cls.tts_speed))),
            tts_instructions=values.get("ASSISTANT_TTS_INSTRUCTIONS", "").strip() or None,
            tts_enabled=parse_bool(values.get("ASSISTANT_TTS_ENABLED"), True),
            energy_threshold=int(
                values.get("ASSISTANT_ENERGY_THRESHOLD", str(cls.energy_threshold))
            ),
            ambient_adjust_seconds=float(
                values.get(
                    "ASSISTANT_AMBIENT_ADJUST_SECONDS",
                    str(cls.ambient_adjust_seconds),
                )
            ),
            audio_device_index=parse_optional_int(values.get("ASSISTANT_AUDIO_DEVICE_INDEX")),
            exit_words=tuple(word.lower() for word in exit_words) or cls.exit_words,
        )

    def to_env_mapping(self) -> dict[str, str]:
        return {
            "ASSISTANT_WAKE_WORD": self.wake_word,
            "ASSISTANT_PORCUPINE_KEYWORD": self.porcupine_keyword or "",
            "ASSISTANT_PORCUPINE_KEYWORD_PATH": self.porcupine_keyword_path or "",
            "ASSISTANT_CHAT_MODEL": self.chat_model,
            "ASSISTANT_TRANSCRIPTION_MODEL": self.transcription_model,
            "ASSISTANT_TRANSCRIPTION_FALLBACK_MODELS": ",".join(
                self.transcription_fallback_models
            ),
            "ASSISTANT_SYSTEM_PROMPT": self.system_prompt,
            "ASSISTANT_LISTEN_TIMEOUT": str(self.listen_timeout),
            "ASSISTANT_PHRASE_TIME_LIMIT": str(self.phrase_time_limit),
            "ASSISTANT_TTS_ENABLED": "true" if self.tts_enabled else "false",
            "ASSISTANT_TTS_MODEL": self.tts_model,
            "ASSISTANT_TTS_FALLBACK_MODELS": ",".join(self.tts_fallback_models),
            "ASSISTANT_TTS_VOICE": self.tts_voice,
            "ASSISTANT_TTS_SPEED": str(self.tts_speed),
            "ASSISTANT_TTS_INSTRUCTIONS": self.tts_instructions or "",
            "ASSISTANT_ENERGY_THRESHOLD": str(self.energy_threshold),
            "ASSISTANT_AMBIENT_ADJUST_SECONDS": str(self.ambient_adjust_seconds),
            "ASSISTANT_AUDIO_DEVICE_INDEX": (
                str(self.audio_device_index) if self.audio_device_index is not None else ""
            ),
            "ASSISTANT_EXIT_WORDS": ",".join(self.exit_words),
        }

    def summary_lines(self) -> tuple[str, ...]:
        keyword = self.porcupine_keyword_path or self.porcupine_keyword or "unset"
        return (
            f"Wake word label: {self.wake_word}",
            f"Porcupine keyword: {keyword}",
            f"Chat model: {self.chat_model}",
            f"Transcribe model: {self.transcription_model}",
            f"TTS model: {self.tts_model}",
            f"TTS enabled: {'yes' if self.tts_enabled else 'no'}",
        )


def env_file_path() -> Path:
    configured = os.getenv("PYJIPPETY_ENV_FILE", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path(".env")


def candidate_env_paths() -> tuple[Path, ...]:
    config_path = Path.home() / ".config" / "pyjippety" / ".env"
    configured = os.getenv("PYJIPPETY_ENV_FILE", "").strip()
    if configured:
        return (env_file_path(),)
    return (config_path, env_file_path())


def load_environment() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    for path in candidate_env_paths():
        if path.exists():
            load_dotenv(path, override=True)


__all__ = [
    "AssistantConfig",
    "candidate_env_paths",
    "env_file_path",
    "load_environment",
    "parse_bool",
    "parse_csv",
    "parse_optional_int",
    "unique_nonempty",
]
