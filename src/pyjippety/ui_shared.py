from __future__ import annotations

from dataclasses import dataclass


SURFACE = "#f3f0e8"
CARD = "#fffdf8"
CARD_ALT = "#f7f4ec"
BORDER = "#d8d1c2"
TEXT = "#1f2a30"
MUTED = "#67727b"
ACCENT = "#2f5d73"
ACCENT_ACTIVE = "#264b5d"
SUCCESS = "#4d7a64"
WARNING = "#b6823b"
ERROR = "#9c544f"
SUBTLE = "#ddd5c7"

PERSONALITY_PRESETS = {
    "Custom": {"system": "", "tts": ""},
    "Concise": {
        "system": "Answer in a concise, direct, low-fluff style.",
        "tts": "Speak clearly, calmly, and efficiently.",
    },
    "Friendly": {
        "system": "Answer warmly and clearly while staying practical and concise.",
        "tts": "Speak in a warm, friendly, natural tone.",
    },
    "Technical": {
        "system": "Answer like a practical senior technical assistant. Be precise and compact.",
        "tts": "Speak in a focused, confident, professional tone.",
    },
    "Chaotic Cartoon": {
        "system": "Answer with playful, original chaotic-cartoon energy while staying helpful. Do not imitate any existing character.",
        "tts": "Use an original cartoonish voice: nasal, mischievous, dry, and energetic without imitating any specific character.",
    },
}


@dataclass(frozen=True)
class SettingField:
    key: str
    label: str
    note: str = ""
    kind: str = "entry"
    secret: bool = False
    height: int = 3
    advanced: bool = False


@dataclass(frozen=True)
class SettingSection:
    title: str
    description: str
    fields: tuple[SettingField, ...]


SETTINGS_SECTIONS = (
    SettingSection(
        "Credentials",
        "The app needs one OpenAI key and one Picovoice key. The fields are stored in your local config file.",
        (
            SettingField("OPENAI_API_KEY", "OpenAI API key", "Used for chat, speech-to-text, and speech output.", secret=True),
            SettingField("PICOVOICE_ACCESS_KEY", "Picovoice access key", "Used by Porcupine for local wake-word detection.", secret=True),
        ),
    ),
    SettingSection(
        "Wake Word",
        "Choose a built-in Porcupine keyword or point to a custom `.ppn` file.",
        (
            SettingField("ASSISTANT_DISPLAY_NAME", "Display name", "Shown in the window and status summary."),
            SettingField("ASSISTANT_WAKE_WORD", "Wake word label", "Shown in the UI and spoken back to you."),
            SettingField("ASSISTANT_PORCUPINE_KEYWORD", "Built-in keyword", "Ignored if a custom `.ppn` path is set."),
            SettingField("ASSISTANT_PORCUPINE_KEYWORD_PATH", "Custom keyword file", "Absolute or relative path to a Picovoice `.ppn` file.", advanced=True),
            SettingField("ASSISTANT_AUDIO_DEVICE_INDEX", "Audio device index", "Choose a detected microphone or leave blank for the default device."),
            SettingField("ASSISTANT_EXIT_WORDS", "Exit words", "Comma-separated phrases that stop voice mode.", advanced=True),
            SettingField("ASSISTANT_CHIME_VOLUME", "Wake cue volume", advanced=True),
        ),
    ),
    SettingSection(
        "Models",
        "Pick the models your OpenAI project can access. Fallback lists are tried in order.",
        (
            SettingField("ASSISTANT_CHAT_MODEL", "Chat model"),
            SettingField("ASSISTANT_TRANSCRIPTION_MODEL", "Primary transcription model"),
            SettingField("ASSISTANT_TRANSCRIPTION_FALLBACK_MODELS", "Transcription fallbacks", "Comma-separated list, for example `gpt-4o-transcribe,whisper-1`.", advanced=True),
            SettingField("ASSISTANT_MEMORY_ENABLED", "Enable memory", "Store notes and recent exchanges for future context.", kind="bool"),
            SettingField("ASSISTANT_SAFE_TOOL_MODE", "Safe tool mode", "Blocks side-effect commands like opening websites unless you turn it off.", kind="bool"),
            SettingField("ASSISTANT_TTS_ENABLED", "Enable speech output", "Turn this off to keep replies in the log only.", kind="bool"),
            SettingField("ASSISTANT_MUTE_SPEECH", "Mute speech", "Keeps replies in the UI without audio playback.", kind="bool"),
            SettingField("ASSISTANT_LOW_VERBOSITY", "Low verbosity mode", "Biases replies toward shorter answers.", kind="bool"),
            SettingField("ASSISTANT_TTS_MODEL", "Primary speech model"),
            SettingField("ASSISTANT_TTS_FALLBACK_MODELS", "Speech fallbacks", "Comma-separated list, for example `tts-1,tts-1-hd`.", advanced=True),
            SettingField("ASSISTANT_TTS_VOICE", "Speech voice", advanced=True),
            SettingField("ASSISTANT_TTS_SPEED", "Speech speed", advanced=True),
        ),
    ),
    SettingSection(
        "Listening",
        "These values control how long the microphone waits and how aggressively it filters room noise.",
        (
            SettingField("ASSISTANT_LISTEN_TIMEOUT", "Listen timeout", advanced=True),
            SettingField("ASSISTANT_PHRASE_TIME_LIMIT", "Phrase time limit", advanced=True),
            SettingField("ASSISTANT_FOLLOW_UP_ENABLED", "Enable follow-up window", "Keeps listening briefly for clarifying questions.", kind="bool"),
            SettingField("ASSISTANT_FOLLOW_UP_TURN_LIMIT", "Follow-up turn limit"),
            SettingField("ASSISTANT_FOLLOW_UP_TIMEOUT", "Follow-up timeout"),
            SettingField("ASSISTANT_START_HIDDEN", "Start hidden in tray", kind="bool", advanced=True),
            SettingField("ASSISTANT_IDLE_TIMEOUT_SECONDS", "Idle timeout seconds", advanced=True),
            SettingField("ASSISTANT_AMBIENT_ADJUST_SECONDS", "Ambient calibration seconds", advanced=True),
            SettingField("ASSISTANT_ENERGY_THRESHOLD", "Energy threshold", advanced=True),
            SettingField("ASSISTANT_MEMORY_TURN_LIMIT", "Stored exchange limit", advanced=True),
            SettingField("ASSISTANT_MEMORY_FACT_LIMIT", "Stored note limit", advanced=True),
        ),
    ),
    SettingSection(
        "Prompting",
        "These fields shape how the assistant answers and how speech output sounds.",
        (
            SettingField("ASSISTANT_SYSTEM_PROMPT", "System prompt", kind="text", height=5, advanced=True),
            SettingField("ASSISTANT_TTS_INSTRUCTIONS", "Speech style instructions", kind="text", height=4, advanced=True),
        ),
    ),
)


__all__ = [
    "ACCENT",
    "ACCENT_ACTIVE",
    "BORDER",
    "CARD",
    "CARD_ALT",
    "ERROR",
    "MUTED",
    "PERSONALITY_PRESETS",
    "SETTINGS_SECTIONS",
    "SUBTLE",
    "SUCCESS",
    "SURFACE",
    "SettingField",
    "SettingSection",
    "TEXT",
    "WARNING",
]
