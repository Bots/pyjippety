from __future__ import annotations

import json
import logging
import os
import queue
import sys
import time
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk

from .config import AssistantConfig, env_file_path, load_environment
from .integrations import (
    OpenAITranscribingListener,
    OpenAIResponder,
    build_live_assistant,
    build_openai_client,
    build_speaker,
    list_microphones,
)
from .memory import MemoryAwareResponder, build_memory_store, memory_file_path


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
    "Custom": {
        "system": "",
        "tts": "",
    },
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
            SettingField("ASSISTANT_WAKE_WORD", "Wake word label", "Shown in the UI and spoken back to you."),
            SettingField("ASSISTANT_PORCUPINE_KEYWORD", "Built-in keyword", "Ignored if a custom `.ppn` path is set."),
            SettingField("ASSISTANT_PORCUPINE_KEYWORD_PATH", "Custom keyword file", "Absolute or relative path to a Picovoice `.ppn` file.", advanced=True),
            SettingField("ASSISTANT_AUDIO_DEVICE_INDEX", "Audio device index", "Choose a detected microphone or leave blank for the default device."),
            SettingField("ASSISTANT_EXIT_WORDS", "Exit words", "Comma-separated phrases that stop voice mode.", advanced=True),
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


class QueueLogHandler(logging.Handler):
    def __init__(self, log_queue: queue.Queue[str]) -> None:
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record: logging.LogRecord) -> None:
        self.log_queue.put(self.format(record))


class PyjippetyApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("PyJippety")
        self.root.geometry("1220x820")
        self.root.minsize(1080, 720)
        self.root.configure(bg=SURFACE)

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.ui_queue: queue.Queue[tuple[str, str | None]] = queue.Queue()
        self.assistant = None
        self.assistant_thread: threading.Thread | None = None
        self.manual_thread: threading.Thread | None = None
        self.manual_speaker = None
        self.entry_widgets: dict[str, ttk.Entry] = {}
        self.text_widgets: dict[str, tk.Text] = {}
        self.bool_vars: dict[str, tk.BooleanVar] = {}
        self.setting_rows: list[tuple[SettingField, tuple[tk.Widget, tk.Widget]]] = []
        self.section_cards: list[tuple[SettingSection, tk.Widget]] = []
        self.env_path = env_file_path()
        self.profile_var = tk.StringVar(value="default")
        self.preset_var = tk.StringVar(value="Custom")
        self.device_var = tk.StringVar(value="")
        self.last_transcript_var = tk.StringVar(value="")
        self.stream_response_var = tk.StringVar(value="")
        self.history_entries: list[dict[str, str]] = []
        self.device_map: dict[str, str] = {}
        self.logo_image: tk.PhotoImage | None = None
        self.logo_mark: tk.PhotoImage | None = None

        load_environment()
        self.config = AssistantConfig.from_env()
        self._load_logo_assets()
        self._configure_theme()
        self._install_log_handler()
        self._build_layout()
        self._load_profiles()
        self.reload_settings()
        self._maybe_show_setup_wizard()
        self._poll_logs()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<F8>", lambda _: self._toggle_voice_mode())
        self.root.bind("<Control-space>", lambda _: self.push_to_talk())
        self.root.bind("<Escape>", lambda _: self.interrupt_current_output())

    def _configure_theme(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("App.TFrame", background=SURFACE)
        style.configure("Card.TFrame", background=CARD, relief="flat")
        style.configure("Section.TLabelframe", background=CARD, borderwidth=0)
        style.configure("Section.TLabelframe.Label", background=CARD, foreground=TEXT, font=("TkDefaultFont", 10, "bold"))
        style.configure("App.TLabel", background=SURFACE, foreground=TEXT)
        style.configure("Card.TLabel", background=CARD, foreground=TEXT)
        style.configure("Muted.TLabel", background=CARD, foreground=MUTED)
        style.configure("Header.TLabel", background=SURFACE, foreground=TEXT, font=("TkHeadingFont", 20, "bold"))
        style.configure("Subheader.TLabel", background=SURFACE, foreground=MUTED)
        style.configure("Primary.TButton", padding=(14, 10), background=ACCENT, foreground=CARD)
        style.map("Primary.TButton", background=[("active", ACCENT_ACTIVE)])
        style.configure("Secondary.TButton", padding=(12, 10), background=CARD_ALT, foreground=TEXT)
        style.map("Secondary.TButton", background=[("active", SUBTLE)])
        style.configure("Danger.TButton", padding=(12, 10), background="#ede1df", foreground=ERROR)
        style.map("Danger.TButton", background=[("active", "#e5d1ce")])
        style.configure("Notebook.TNotebook", background=SURFACE, borderwidth=0)
        style.configure("Notebook.TNotebook.Tab", padding=(16, 10), background=CARD_ALT, foreground=TEXT)
        style.map("Notebook.TNotebook.Tab", background=[("selected", CARD)], foreground=[("selected", TEXT)])
        style.configure("App.TEntry", fieldbackground=CARD, bordercolor=BORDER, padding=8)
        style.configure("App.TCheckbutton", background=CARD, foreground=TEXT)

    def _candidate_logo_paths(self) -> tuple[Path, ...]:
        candidates: list[Path] = []
        if getattr(sys, "_MEIPASS", None):
            candidates.append(Path(sys._MEIPASS) / "assets" / "pyjippety-logo.png")
        candidates.append(Path.home() / ".local" / "share" / "pyjippety" / "pyjippety-logo.png")
        candidates.append(Path(__file__).resolve().parents[2] / "assets" / "pyjippety-logo.png")
        return tuple(candidates)

    def _load_logo_assets(self) -> None:
        for path in self._candidate_logo_paths():
            if not path.exists():
                continue
            try:
                self.logo_image = tk.PhotoImage(file=str(path))
                self.logo_mark = self.logo_image.subsample(4, 4)
                self.root.iconphoto(True, self.logo_image)
                return
            except Exception:
                continue

    def _install_log_handler(self) -> None:
        handler = QueueLogHandler(self.log_queue)
        handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)s  %(message)s"))
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(handler)
        self.log_handler = handler

    def _build_layout(self) -> None:
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)

        header = ttk.Frame(self.root, style="App.TFrame", padding=(24, 20, 24, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        if self.logo_mark is not None:
            tk.Label(header, image=self.logo_mark, bg=SURFACE).grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 12))

        ttk.Label(header, text="PyJippety", style="Header.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(
            header,
            text="Desktop voice assistant",
            style="Subheader.TLabel",
        ).grid(row=1, column=1, sticky="w", pady=(2, 0))

        self.status_badge = tk.Label(
            header,
            text="Idle",
            bg=CARD_ALT,
            fg=TEXT,
            padx=14,
            pady=8,
            font=("TkDefaultFont", 10, "bold"),
        )
        self.status_badge.grid(row=0, column=2, rowspan=2, sticky="e")

        body = ttk.Frame(self.root, style="App.TFrame", padding=(24, 8, 24, 24))
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        sidebar = ttk.Frame(body, style="App.TFrame")
        sidebar.grid(row=0, column=0, sticky="nsw", padx=(0, 18))
        content = ttk.Frame(body, style="App.TFrame")
        content.grid(row=0, column=1, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(0, weight=1)

        self._build_sidebar(sidebar)
        self._build_content(content)

    def _card(self, parent: tk.Widget, padding: tuple[int, int] = (16, 16)) -> tk.Frame:
        return tk.Frame(
            parent,
            bg=CARD,
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER,
            padx=padding[0],
            pady=padding[1],
        )

    def _build_sidebar(self, parent: ttk.Frame) -> None:
        session_card = self._card(parent)
        session_card.pack(fill="x")

        tk.Label(
            session_card,
            text="Live session",
            bg=CARD,
            fg=TEXT,
            font=("TkDefaultFont", 12, "bold"),
        ).pack(anchor="w")
        tk.Label(
            session_card,
            text="Start listening, push one question through, or stop the session.",
            bg=CARD,
            fg=MUTED,
            justify="left",
            wraplength=250,
        ).pack(anchor="w", pady=(6, 14))
        action_grid = tk.Frame(session_card, bg=CARD)
        action_grid.pack(fill="x")
        action_grid.grid_columnconfigure(0, weight=1)
        action_grid.grid_columnconfigure(1, weight=1)

        self.start_button = ttk.Button(
            action_grid,
            text="Start",
            command=self.start_voice_mode,
            style="Primary.TButton",
        )
        self.start_button.grid(row=0, column=0, sticky="ew")

        self.stop_button = ttk.Button(
            action_grid,
            text="Stop",
            command=self.stop_voice_mode,
            style="Danger.TButton",
        )
        self.stop_button.grid(row=0, column=1, sticky="ew", padx=(10, 0))

        self.push_to_talk_button = ttk.Button(
            action_grid,
            text="Push to talk",
            command=self.push_to_talk,
            style="Secondary.TButton",
        )
        self.push_to_talk_button.grid(row=1, column=0, sticky="ew", pady=(10, 0))

        self.interrupt_button = ttk.Button(
            action_grid,
            text="Interrupt",
            command=self.interrupt_current_output,
            style="Secondary.TButton",
        )
        self.interrupt_button.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=(10, 0))

        self.test_button = ttk.Button(
            action_grid,
            text="Test setup",
            command=self.test_setup,
            style="Secondary.TButton",
        )
        self.test_button.grid(row=2, column=0, sticky="ew", pady=(10, 0))

        self.sleep_button = ttk.Button(
            action_grid,
            text="Sleep",
            command=self.sleep_voice_mode,
            style="Secondary.TButton",
        )
        self.sleep_button.grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=(10, 0))

        setup_card = self._card(parent)
        setup_card.pack(fill="x", pady=(16, 0))

        tk.Label(
            setup_card,
            text="At a glance",
            bg=CARD,
            fg=TEXT,
            font=("TkDefaultFont", 12, "bold"),
        ).pack(anchor="w")

        self.config_summary = tk.Label(
            setup_card,
            text="",
            justify="left",
            anchor="nw",
            bg=CARD,
            fg=MUTED,
            wraplength=250,
        )
        self.config_summary.pack(fill="x", pady=(10, 0))

        tk.Label(
            setup_card,
            text="F8 starts or stops listening. Ctrl+Space uses push-to-talk. Escape interrupts playback.",
            bg=CARD,
            fg=MUTED,
            justify="left",
            wraplength=250,
        ).pack(anchor="w", pady=(10, 0))

    def _build_content(self, parent: ttk.Frame) -> None:
        notebook = ttk.Notebook(parent, style="Notebook.TNotebook")
        notebook.grid(row=0, column=0, sticky="nsew")

        workspace = ttk.Frame(notebook, style="App.TFrame")
        settings = ttk.Frame(notebook, style="App.TFrame")
        notebook.add(workspace, text="Use")
        notebook.add(settings, text="Setup")

        self._build_workspace_tab(workspace)
        self._build_settings_tab(settings)

    def _build_workspace_tab(self, parent: ttk.Frame) -> None:
        parent.grid_columnconfigure(0, weight=2)
        parent.grid_columnconfigure(1, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        prompt_card = self._card(parent, padding=(18, 18))
        prompt_card.grid(row=0, column=0, columnspan=2, sticky="ew", padx=4, pady=(4, 16))
        prompt_card.grid_columnconfigure(0, weight=1)

        tk.Label(
            prompt_card,
            text="Type a request",
            bg=CARD,
            fg=TEXT,
            font=("TkDefaultFont", 12, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            prompt_card,
            text="Quick way to test the assistant without using the wake word.",
            bg=CARD,
            fg=MUTED,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(4, 12))

        self.prompt_box = tk.Text(
            prompt_card,
            height=4,
            wrap="word",
            bg="#fffdf9",
            fg=TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
            padx=10,
            pady=10,
        )
        self.prompt_box.grid(row=2, column=0, sticky="ew")
        self.prompt_box.bind("<Control-Return>", lambda _: self.ask_from_text())

        action_row = tk.Frame(prompt_card, bg=CARD)
        action_row.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        action_row.grid_columnconfigure(0, weight=1)
        tk.Label(
            action_row,
            text="Ctrl+Enter sends",
            bg=CARD,
            fg=MUTED,
        ).grid(row=0, column=0, sticky="w")
        self.ask_button = ttk.Button(
            action_row,
            text="Ask",
            command=self.ask_from_text,
            style="Primary.TButton",
        )
        self.ask_button.grid(row=0, column=1, sticky="e")

        transcript_card = self._card(parent, padding=(18, 18))
        transcript_card.grid(row=1, column=0, columnspan=2, sticky="ew", padx=4, pady=(0, 16))
        transcript_card.grid_columnconfigure(0, weight=1)
        tk.Label(
            transcript_card,
            text="Last transcript",
            bg=CARD,
            fg=TEXT,
            font=("TkDefaultFont", 12, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            transcript_card,
            text="Correct it and send again if speech recognition was close but not right.",
            bg=CARD,
            fg=MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(4, 10))
        self.transcript_entry = ttk.Entry(
            transcript_card,
            textvariable=self.last_transcript_var,
            style="App.TEntry",
        )
        self.transcript_entry.grid(row=2, column=0, sticky="ew", ipady=2)
        actions = tk.Frame(transcript_card, bg=CARD)
        actions.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        actions.grid_columnconfigure(0, weight=1)
        ttk.Button(
            actions,
            text="Send transcript",
            command=self.resend_last_transcript,
            style="Secondary.TButton",
        ).grid(row=0, column=1, sticky="e")
        self.stream_label = tk.Label(
            actions,
            textvariable=self.stream_response_var,
            bg=CARD,
            fg=MUTED,
            justify="left",
            anchor="w",
            wraplength=640,
        )
        self.stream_label.grid(row=0, column=0, sticky="w", padx=(0, 12))

        log_card = self._card(parent, padding=(18, 18))
        log_card.grid(row=2, column=0, sticky="nsew", padx=4, pady=(0, 4))
        log_card.grid_columnconfigure(0, weight=1)
        log_card.grid_rowconfigure(1, weight=1)

        log_header = tk.Frame(log_card, bg=CARD)
        log_header.grid(row=0, column=0, sticky="ew")
        log_header.grid_columnconfigure(0, weight=1)
        tk.Label(
            log_header,
            text="Session log",
            bg=CARD,
            fg=TEXT,
            font=("TkDefaultFont", 12, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(
            log_header,
            text="Clear log",
            command=self.clear_log,
            style="Secondary.TButton",
        ).grid(row=0, column=1, sticky="e")

        self.log_view = tk.Text(
            log_card,
            wrap="word",
            bg="#fffdf9",
            fg=TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            padx=10,
            pady=10,
        )
        self.log_view.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self.log_view.configure(state="disabled")
        side_card = self._card(parent, padding=(18, 18))
        side_card.grid(row=2, column=1, sticky="nsew", padx=(12, 4), pady=(0, 4))
        side_card.grid_columnconfigure(0, weight=1)
        side_card.grid_rowconfigure(5, weight=1)

        tk.Label(
            side_card,
            text="Notes",
            bg=CARD,
            fg=TEXT,
            font=("TkDefaultFont", 12, "bold"),
        ).grid(row=0, column=0, sticky="w")
        self.memory_summary = tk.Label(
            side_card,
            text="",
            justify="left",
            anchor="nw",
            bg=CARD,
            fg=MUTED,
            wraplength=300,
        )
        self.memory_summary.grid(row=1, column=0, sticky="ew", pady=(8, 10))
        self.memory_notes_box = tk.Text(
            side_card,
            height=6,
            wrap="word",
            bg="#fffdf9",
            fg=TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
            padx=10,
            pady=10,
        )
        self.memory_notes_box.grid(row=2, column=0, sticky="ew")
        memory_actions = tk.Frame(side_card, bg=CARD)
        memory_actions.grid(row=3, column=0, sticky="ew", pady=(10, 14))
        ttk.Button(
            memory_actions,
            text="Save notes",
            command=self.save_memory_notes,
            style="Secondary.TButton",
        ).pack(side="left")
        ttk.Button(
            memory_actions,
            text="Clear memory",
            command=self.clear_memory,
            style="Secondary.TButton",
        ).pack(side="left", padx=(10, 0))

        history_header = tk.Frame(side_card, bg=CARD)
        history_header.grid(row=4, column=0, sticky="ew")
        history_header.grid_columnconfigure(0, weight=1)
        tk.Label(
            history_header,
            text="Recent",
            bg=CARD,
            fg=TEXT,
            font=("TkDefaultFont", 12, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(
            history_header,
            text="Clear",
            command=self.clear_history,
            style="Secondary.TButton",
        ).grid(row=0, column=1, sticky="e")
        self.history_view = tk.Text(
            side_card,
            wrap="word",
            bg="#fffdf9",
            fg=TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            padx=10,
            pady=10,
        )
        self.history_view.grid(row=5, column=0, sticky="nsew", pady=(10, 0))
        self.history_view.configure(state="disabled")

    def _build_settings_tab(self, parent: ttk.Frame) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        toolbar = self._card(parent, padding=(18, 14))
        toolbar.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 16))
        toolbar.grid_columnconfigure(1, weight=1)
        tk.Label(
            toolbar,
            text="Setup",
            bg=CARD,
            fg=TEXT,
            font=("TkDefaultFont", 12, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            toolbar,
            text="Profiles, presets, devices, and behavior live here.",
            bg=CARD,
            fg=MUTED,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 12))

        controls = tk.Frame(toolbar, bg=CARD)
        controls.grid(row=0, column=1, rowspan=2, sticky="e")
        controls.grid_columnconfigure(1, weight=1)
        controls.grid_columnconfigure(3, weight=1)

        tk.Label(controls, text="Profile", bg=CARD, fg=MUTED).grid(row=0, column=0, sticky="w")
        self.profile_combo = ttk.Combobox(
            controls,
            textvariable=self.profile_var,
            state="readonly",
            values=("default",),
            width=14,
        )
        self.profile_combo.grid(row=0, column=1, sticky="ew")
        self.profile_combo.bind("<<ComboboxSelected>>", lambda _: self.switch_profile())

        self.new_profile_entry = ttk.Entry(controls, style="App.TEntry", width=14)
        self.new_profile_entry.grid(row=0, column=2, padx=(10, 0), sticky="ew", ipady=1)
        self.new_profile_entry.insert(0, "new-profile")
        ttk.Button(
            controls,
            text="Save as",
            command=self.save_as_profile,
            style="Secondary.TButton",
        ).grid(row=0, column=3, padx=(10, 0), sticky="ew")

        tk.Label(controls, text="Preset", bg=CARD, fg=MUTED).grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.preset_combo = ttk.Combobox(
            controls,
            textvariable=self.preset_var,
            state="readonly",
            values=tuple(PERSONALITY_PRESETS.keys()),
            width=14,
        )
        self.preset_combo.grid(row=1, column=1, sticky="ew", pady=(10, 0))
        ttk.Button(
            controls,
            text="Apply preset",
            command=self.apply_preset,
            style="Secondary.TButton",
        ).grid(row=1, column=2, padx=(10, 0), sticky="ew", pady=(10, 0))
        ttk.Button(
            controls,
            text="Save",
            command=self.save_settings,
            style="Primary.TButton",
        ).grid(row=1, column=3, padx=(10, 0), sticky="ew", pady=(10, 0))
        ttk.Button(
            controls,
            text="Reload",
            command=self.reload_settings,
            style="Secondary.TButton",
        ).grid(row=1, column=4, padx=(10, 0), sticky="ew", pady=(10, 0))

        self.show_advanced_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            toolbar,
            text="Show advanced settings",
            variable=self.show_advanced_var,
            command=self._refresh_advanced_visibility,
            style="App.TCheckbutton",
        ).grid(row=2, column=0, sticky="w", pady=(10, 0))

        canvas = tk.Canvas(parent, bg=SURFACE, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        form = ttk.Frame(canvas, style="App.TFrame")
        form.bind(
            "<Configure>",
            lambda _: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        window = canvas.create_window((0, 0), window=form, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")
        parent.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(window, width=max(event.width - 24, 300)),
        )

        for section in SETTINGS_SECTIONS:
            self._build_settings_section(form, section)
        self._refresh_advanced_visibility()

    def _build_settings_section(self, parent: ttk.Frame, section: SettingSection) -> None:
        card = self._card(parent, padding=(18, 18))
        card.pack(fill="x", padx=4, pady=(0, 16))
        self.section_cards.append((section, card))
        card.grid_columnconfigure(1, weight=1)

        tk.Label(
            card,
            text=section.title,
            bg=CARD,
            fg=TEXT,
            font=("TkDefaultFont", 12, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        tk.Label(
            card,
            text=section.description,
            bg=CARD,
            fg=MUTED,
            justify="left",
            wraplength=780,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 14))

        row_index = 2
        for field in section.fields:
            row_widget = self._build_setting_row(card, row_index, field)
            self.setting_rows.append((field, row_widget))
            row_index += 1

    def _build_setting_row(
        self, parent: tk.Frame, row: int, field: SettingField
    ) -> tuple[tk.Widget, tk.Widget]:
        label_frame = tk.Frame(parent, bg=CARD)
        label_frame.grid(row=row, column=0, sticky="nw", padx=(0, 18), pady=8)
        tk.Label(
            label_frame,
            text=field.label,
            bg=CARD,
            fg=TEXT,
            anchor="w",
        ).pack(anchor="w")
        if field.note:
            tk.Label(
                label_frame,
                text=field.note,
                bg=CARD,
                fg=MUTED,
                justify="left",
                wraplength=260,
            ).pack(anchor="w", pady=(4, 0))

        if field.kind == "bool":
            variable = tk.BooleanVar(value=False)
            self.bool_vars[field.key] = variable
            control = ttk.Checkbutton(
                parent,
                variable=variable,
                style="App.TCheckbutton",
            )
            control.grid(row=row, column=1, sticky="w", pady=8)
            return (label_frame, control)

        if field.kind == "text":
            widget = tk.Text(
                parent,
                height=field.height,
                wrap="word",
                bg="#fffdf9",
                fg=TEXT,
                relief="flat",
                highlightthickness=1,
                highlightbackground=BORDER,
                highlightcolor=ACCENT,
                padx=10,
                pady=10,
            )
            widget.grid(row=row, column=1, sticky="ew", pady=8)
            self.text_widgets[field.key] = widget
            return (label_frame, widget)

        if field.key == "ASSISTANT_AUDIO_DEVICE_INDEX":
            self.device_combo = ttk.Combobox(
                parent,
                textvariable=self.device_var,
                state="readonly",
                values=("Default device",),
            )
            self.device_combo.grid(row=row, column=1, sticky="ew", pady=8, ipady=2)
            self.device_combo.bind("<<ComboboxSelected>>", lambda _: self._apply_device_selection())
            self._load_microphones()
            return (label_frame, self.device_combo)

        widget = ttk.Entry(
            parent,
            style="App.TEntry",
            show="*" if field.secret else "",
        )
        widget.grid(row=row, column=1, sticky="ew", pady=8, ipady=2)
        self.entry_widgets[field.key] = widget
        return (label_frame, widget)

    def _apply_device_selection(self) -> None:
        return

    def _refresh_advanced_visibility(self) -> None:
        show_advanced = self.show_advanced_var.get()
        for field, widgets in self.setting_rows:
            if not field.advanced:
                continue
            for widget in widgets:
                if show_advanced:
                    widget.grid()
                else:
                    widget.grid_remove()
        for section, card in self.section_cards:
            has_basic_fields = any(not field.advanced for field in section.fields)
            if show_advanced or has_basic_fields:
                card.pack(fill="x", padx=4, pady=(0, 16))
            else:
                card.pack_forget()

    def _all_setting_keys(self) -> list[str]:
        return [field.key for section in SETTINGS_SECTIONS for field in section.fields]

    def _profiles_root(self) -> Path:
        return self.env_path.parent / "profiles"

    def _profile_dir(self, name: str | None = None) -> Path:
        profile_name = (name or self.profile_var.get()).strip() or "default"
        return self._profiles_root() / profile_name

    def _profile_settings_path(self, name: str | None = None) -> Path:
        return self._profile_dir(name) / "settings.json"

    def _history_path(self, name: str | None = None) -> Path:
        return self._profile_dir(name) / "history.json"

    def _load_profiles(self) -> None:
        profiles = ["default"]
        root = self._profiles_root()
        if root.exists():
            profiles.extend(sorted(path.name for path in root.iterdir() if path.is_dir()))
        deduped = sorted(set(profiles))
        self.profile_combo["values"] = deduped
        if self.profile_var.get() not in deduped:
            self.profile_var.set("default")

    def _load_profile_data(self, name: str) -> dict[str, str]:
        path = self._profile_settings_path(name)
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return {str(key): str(value) for key, value in payload.items()}

    def _save_profile_data(self, name: str, values: dict[str, str]) -> None:
        path = self._profile_settings_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(values, indent=2), encoding="utf-8")

    def _load_history(self) -> None:
        path = self._history_path()
        if not path.exists():
            self.history_entries = []
            self._render_history()
            return
        try:
            self.history_entries = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            self.history_entries = []
        self._render_history()

    def _save_history(self) -> None:
        path = self._history_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.history_entries[-100:], indent=2), encoding="utf-8")

    def _record_history(self, kind: str, text: str) -> None:
        self.history_entries.append(
            {
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "kind": kind,
                "text": text,
            }
        )
        self.history_entries = self.history_entries[-100:]
        self._save_history()
        self._render_history()

    def _render_history(self) -> None:
        if not hasattr(self, "history_view"):
            return
        self.history_view.configure(state="normal")
        self.history_view.delete("1.0", "end")
        for entry in self.history_entries:
            self.history_view.insert(
                "end",
                f"[{entry['time']}] {entry['kind']}: {entry['text']}\n\n",
            )
        self.history_view.configure(state="disabled")

    def _load_microphones(self) -> None:
        devices = list_microphones()
        self.device_map = {"Default device": ""}
        values = ["Default device"]
        for index, name in devices:
            label = f"{index}: {name}"
            self.device_map[label] = str(index)
            values.append(label)
        if hasattr(self, "device_combo"):
            self.device_combo["values"] = values

    def _maybe_show_setup_wizard(self) -> None:
        environment = self._build_environment()
        if environment.get("OPENAI_API_KEY") and environment.get("PICOVOICE_ACCESS_KEY"):
            return
        self.root.after(250, self.show_setup_wizard)

    def _populate_form(self, values: dict[str, str]) -> None:
        for key, widget in self.entry_widgets.items():
            widget.delete(0, "end")
            widget.insert(0, values.get(key, ""))
        if hasattr(self, "device_combo"):
            target_index = values.get("ASSISTANT_AUDIO_DEVICE_INDEX", "")
            selected = "Default device"
            for label, index in self.device_map.items():
                if index == target_index:
                    selected = label
                    break
            self.device_var.set(selected)
        for key, widget in self.text_widgets.items():
            widget.delete("1.0", "end")
            widget.insert("1.0", values.get(key, ""))
        for key, variable in self.bool_vars.items():
            variable.set(values.get(key, "").strip().lower() in {"1", "true", "yes", "on"})

    def _collect_form_values(self) -> dict[str, str]:
        values: dict[str, str] = {}
        for key, widget in self.entry_widgets.items():
            values[key] = widget.get().strip()
        if hasattr(self, "device_combo"):
            values["ASSISTANT_AUDIO_DEVICE_INDEX"] = self.device_map.get(
                self.device_var.get(), ""
            )
        for key, widget in self.text_widgets.items():
            values[key] = widget.get("1.0", "end").strip().replace("\n", " ")
        for key, variable in self.bool_vars.items():
            values[key] = "true" if variable.get() else "false"
        return values

    def _build_environment(self) -> dict[str, str]:
        environment = dict(os.environ)
        environment.update(self._collect_form_values())
        environment["PYJIPPETY_PROFILE"] = self.profile_var.get().strip() or "default"
        return environment

    def _refresh_active_config(self, environment: dict[str, str]) -> None:
        self.config = AssistantConfig.from_mapping(environment)
        summary_lines = list(self.config.summary_lines())
        summary_lines.insert(0, f"Profile: {environment.get('PYJIPPETY_PROFILE', 'default')}")
        summary_lines.append(
            f"OpenAI key: {'set' if environment.get('OPENAI_API_KEY') else 'missing'}"
        )
        summary_lines.append(
            f"Picovoice key: {'set' if environment.get('PICOVOICE_ACCESS_KEY') else 'missing'}"
        )
        self.config_summary.configure(text="\n".join(summary_lines))
        self._refresh_memory_summary(environment)

    def _refresh_memory_summary(self, environment: dict[str, str]) -> None:
        store = build_memory_store(self.config, environment)
        if store is None:
            self.memory_summary.configure(text="Memory is off.")
            self.memory_notes_box.delete("1.0", "end")
            return
        self.memory_notes_box.delete("1.0", "end")
        self.memory_notes_box.insert("1.0", "\n".join(store.state.facts))
        self.memory_summary.configure(
            text=(
                f"File: {memory_file_path(environment)}\n"
                f"Notes: {len(store.state.facts)}\n"
                f"Recent exchanges: {len(store.state.turns)}"
            )
        )

    def _set_status(self, text: str) -> None:
        colors = {
            "Idle": (CARD_ALT, TEXT),
            "Starting": ("#e8efe9", SUCCESS),
            "Listening": ("#e8efe9", SUCCESS),
            "Follow-up": ("#e8efe9", SUCCESS),
            "Thinking": ("#f2eadb", WARNING),
            "Sleeping": ("#eef0f2", MUTED),
            "Stopping": ("#f2eadb", WARNING),
            "Error": ("#f3e4e2", ERROR),
        }
        bg, fg = colors.get(text, (CARD_ALT, TEXT))
        self.status_badge.configure(text=text, bg=bg, fg=fg)
        running = text in {"Starting", "Listening", "Follow-up", "Thinking", "Stopping"}
        self.start_button.configure(state="disabled" if running else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")

    def _append_log(self, message: str) -> None:
        self.log_view.configure(state="normal")
        self.log_view.insert("end", f"{message}\n")
        self.log_view.see("end")
        self.log_view.configure(state="disabled")

    def clear_log(self) -> None:
        self.log_view.configure(state="normal")
        self.log_view.delete("1.0", "end")
        self.log_view.configure(state="disabled")

    def clear_memory(self) -> None:
        environment = self._build_environment()
        self._refresh_active_config(environment)
        store = build_memory_store(self.config, environment)
        if store is None:
            self._append_log("Memory is disabled.")
            return
        store.clear()
        self._refresh_memory_summary(environment)
        self._append_log("Memory cleared.")
        self._record_history("memory", "cleared")

    def save_memory_notes(self) -> None:
        environment = self._build_environment()
        self._refresh_active_config(environment)
        store = build_memory_store(self.config, environment)
        if store is None:
            self._append_log("Memory is disabled.")
            return
        notes = [
            line.strip()
            for line in self.memory_notes_box.get("1.0", "end").splitlines()
            if line.strip()
        ]
        store.state.facts = notes[: self.config.memory_fact_limit]
        store.save()
        self._refresh_memory_summary(environment)
        self._append_log("Saved memory notes.")
        self._record_history("memory", "saved notes")

    def clear_history(self) -> None:
        self.history_entries = []
        self._save_history()
        self._render_history()
        self._append_log("History cleared.")

    def switch_profile(self) -> None:
        self.reload_settings()
        self._append_log(f"Switched to profile '{self.profile_var.get()}'.")

    def save_as_profile(self) -> None:
        name = self.new_profile_entry.get().strip()
        if not name:
            return
        self._save_profile_data(name, self._collect_form_values())
        self.profile_var.set(name)
        self._load_profiles()
        self.reload_settings()
        self._append_log(f"Saved profile '{name}'.")

    def apply_preset(self) -> None:
        preset = PERSONALITY_PRESETS.get(self.preset_var.get(), PERSONALITY_PRESETS["Custom"])
        if "ASSISTANT_SYSTEM_PROMPT" in self.text_widgets:
            self.text_widgets["ASSISTANT_SYSTEM_PROMPT"].delete("1.0", "end")
            self.text_widgets["ASSISTANT_SYSTEM_PROMPT"].insert("1.0", preset["system"])
        if "ASSISTANT_TTS_INSTRUCTIONS" in self.text_widgets:
            self.text_widgets["ASSISTANT_TTS_INSTRUCTIONS"].delete("1.0", "end")
            self.text_widgets["ASSISTANT_TTS_INSTRUCTIONS"].insert("1.0", preset["tts"])
        self._append_log(f"Applied preset '{self.preset_var.get()}'.")

    def _toggle_voice_mode(self) -> None:
        if self.assistant_thread and self.assistant_thread.is_alive():
            self.stop_voice_mode()
        else:
            self.start_voice_mode()

    def sleep_voice_mode(self) -> None:
        self.stop_voice_mode()
        self._set_status("Sleeping")
        self._append_log("Voice mode is sleeping.")

    def interrupt_current_output(self) -> None:
        if self.assistant is not None:
            self.assistant.speaker.interrupt()
        if self.manual_speaker is not None:
            try:
                self.manual_speaker.interrupt()
            except Exception:
                pass
        self._append_log("Output interrupted.")

    def resend_last_transcript(self) -> None:
        prompt = self.last_transcript_var.get().strip()
        if not prompt:
            return
        self.prompt_box.delete("1.0", "end")
        self.prompt_box.insert("1.0", prompt)
        self.ask_from_text()

    def show_setup_wizard(self) -> None:
        wizard = tk.Toplevel(self.root)
        wizard.title("PyJippety setup")
        wizard.configure(bg=CARD)
        wizard.transient(self.root)
        wizard.grab_set()
        tk.Label(
            wizard,
            text="Finish setup",
            bg=CARD,
            fg=TEXT,
            font=("TkDefaultFont", 13, "bold"),
        ).pack(anchor="w", padx=18, pady=(18, 6))
        tk.Label(
            wizard,
            text="Add your OpenAI key, Picovoice key, and wake word. You can change everything later.",
            bg=CARD,
            fg=MUTED,
            justify="left",
            wraplength=420,
        ).pack(anchor="w", padx=18)
        fields = [
            ("OPENAI_API_KEY", "OpenAI API key"),
            ("PICOVOICE_ACCESS_KEY", "Picovoice access key"),
            ("ASSISTANT_WAKE_WORD", "Wake word label"),
        ]
        entries: dict[str, ttk.Entry] = {}
        for key, label in fields:
            tk.Label(wizard, text=label, bg=CARD, fg=TEXT).pack(anchor="w", padx=18, pady=(12, 4))
            entry = ttk.Entry(wizard, style="App.TEntry", show="*" if "KEY" in key else "")
            entry.pack(fill="x", padx=18)
            source = self.entry_widgets.get(key)
            if source is not None:
                entry.insert(0, source.get())
            entries[key] = entry

        def finish() -> None:
            for key, entry in entries.items():
                if key in self.entry_widgets:
                    self.entry_widgets[key].delete(0, "end")
                    self.entry_widgets[key].insert(0, entry.get().strip())
            self.save_settings()
            wizard.destroy()

        controls = tk.Frame(wizard, bg=CARD)
        controls.pack(fill="x", padx=18, pady=18)
        ttk.Button(controls, text="Save", command=finish, style="Primary.TButton").pack(side="right")
        ttk.Button(controls, text="Skip", command=wizard.destroy, style="Secondary.TButton").pack(side="right", padx=(0, 10))

    def test_setup(self) -> None:
        environment = self._build_environment()
        self._append_log("Running setup checks...")

        def run_checks() -> None:
            config = AssistantConfig.from_mapping(environment)
            results = [
                f"OpenAI key: {'present' if environment.get('OPENAI_API_KEY') else 'missing'}",
                f"Picovoice key: {'present' if environment.get('PICOVOICE_ACCESS_KEY') else 'missing'}",
                f"Microphones detected: {len(list_microphones())}",
            ]
            try:
                client = build_openai_client(environment)
                results.append("OpenAI client: ready")
                build_speaker(client, config).interrupt()
            except Exception as exc:
                results.append(f"OpenAI client: {exc}")
            try:
                listener = OpenAITranscribingListener(build_openai_client(environment), config)
                listener.calibrate()
                results.append("Microphone calibration: ok")
            except Exception as exc:
                results.append(f"Microphone calibration: {exc}")
            for result in results:
                self.log_queue.put(result)
                self._record_history("setup-test", result)

        threading.Thread(target=run_checks, name="pyjippety-setup-test", daemon=True).start()

    def _poll_logs(self) -> None:
        try:
            while True:
                self._append_log(self.log_queue.get_nowait())
        except queue.Empty:
            pass

        try:
            while True:
                event, value = self.ui_queue.get_nowait()
                if event == "status" and value is not None:
                    self._set_status(value)
                elif event == "assistant_stopped":
                    self.assistant = None
                    self.assistant_thread = None
                elif event == "transcript" and value is not None:
                    self.last_transcript_var.set(value)
                elif event == "stream" and value is not None:
                    self.stream_response_var.set(value)
        except queue.Empty:
            pass

        if (
            self.assistant_thread
            and self.assistant_thread.is_alive()
            and self.config.idle_timeout_seconds > 0
            and self.assistant is not None
            and not self.assistant.follow_up_open
            and (time.monotonic() - self.assistant.last_activity_at)
            > self.config.idle_timeout_seconds
        ):
            self.sleep_voice_mode()

        self.root.after(120, self._poll_logs)

    def save_settings(self) -> None:
        from dotenv import set_key

        values = self._collect_form_values()
        self.env_path.parent.mkdir(parents=True, exist_ok=True)
        self.env_path.touch(exist_ok=True)
        for key in self._all_setting_keys():
            set_key(str(self.env_path), key, values.get(key, ""), quote_mode="auto")
            os.environ[key] = values.get(key, "")
        self._save_profile_data(self.profile_var.get(), values)
        self._refresh_active_config(self._build_environment())
        self._load_profiles()
        self._append_log(f"Saved settings to {self.env_path}.")

    def reload_settings(self) -> None:
        from dotenv import dotenv_values

        values = dict(AssistantConfig().to_env_mapping())
        values.update(
            {
                "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
                "PICOVOICE_ACCESS_KEY": os.getenv("PICOVOICE_ACCESS_KEY", ""),
            }
        )
        if self.env_path.exists():
            values.update(
                {
                    key: value
                    for key, value in dotenv_values(self.env_path).items()
                    if value is not None
                }
            )
        for key in self._all_setting_keys():
            if key in os.environ:
                values[key] = os.environ[key]
        values.update(self._load_profile_data(self.profile_var.get()))
        self._populate_form(values)
        self._refresh_active_config(self._build_environment())
        self._refresh_advanced_visibility()
        self._load_history()
        self._append_log(f"Loaded settings from {self.env_path}.")

    def start_voice_mode(self) -> None:
        if self.assistant_thread and self.assistant_thread.is_alive():
            self._append_log("Voice mode is already running.")
            return

        environment = self._build_environment()
        self._refresh_active_config(environment)
        self._set_status("Starting")
        try:
            self.assistant = build_live_assistant(
                self.config, environment=environment, events=self
            )
        except Exception as exc:
            self._append_log(f"Startup failed: {exc}")
            self._set_status("Error")
            return

        self.assistant_thread = threading.Thread(
            target=self._run_assistant_thread,
            name="pyjippety-voice",
            daemon=True,
        )
        self.assistant_thread.start()
        self._set_status("Listening")

    def _run_assistant_thread(self) -> None:
        try:
            assert self.assistant is not None
            self.assistant.run()
        except Exception as exc:
            self.log_queue.put(f"Voice mode crashed: {exc}")
            self.ui_queue.put(("status", "Error"))
        else:
            self.ui_queue.put(("status", "Idle"))
        finally:
            self.ui_queue.put(("assistant_stopped", None))

    def stop_voice_mode(self) -> None:
        if self.assistant is None:
            self._append_log("Voice mode is not running.")
            self._set_status("Idle")
            return
        self.assistant.request_stop()
        self._append_log("Stop requested.")
        self._set_status("Stopping")

    def push_to_talk(self) -> None:
        if self.manual_thread and self.manual_thread.is_alive():
            return
        environment = self._build_environment()
        self._refresh_active_config(environment)
        self._append_log("Push-to-talk started.")

        def run_push_to_talk() -> None:
            self.ui_queue.put(("status", "Thinking"))
            try:
                config = AssistantConfig.from_mapping(environment)
                client = build_openai_client(environment)
                listener = OpenAITranscribingListener(client, config)
                listener.calibrate()
                transcript = listener.listen(
                    timeout=config.listen_timeout,
                    phrase_time_limit=config.phrase_time_limit,
                )
                if not transcript:
                    self.log_queue.put("Push-to-talk timed out.")
                    return
                self.ui_queue.put(("transcript", transcript))
                self.log_queue.put(f"You: {transcript}")
                self._record_history("transcript", transcript)
                self._run_manual_prompt(transcript, environment)
            except Exception as exc:
                self.log_queue.put(f"Push-to-talk failed: {exc}")
            finally:
                self.ui_queue.put(("status", "Idle"))

        self.manual_thread = threading.Thread(
            target=run_push_to_talk, name="pyjippety-push-to-talk", daemon=True
        )
        self.manual_thread.start()

    def ask_from_text(self) -> None:
        prompt = self.prompt_box.get("1.0", "end").strip()
        if not prompt:
            return
        self.prompt_box.delete("1.0", "end")
        self._append_log(f"You: {prompt}")
        self._record_history("prompt", prompt)
        environment = self._build_environment()
        self._refresh_active_config(environment)
        self.manual_thread = threading.Thread(
            target=self._run_manual_prompt,
            args=(prompt, environment),
            name="pyjippety-manual-prompt",
            daemon=True,
        )
        self.manual_thread.start()

    def _run_manual_prompt(self, prompt: str, environment: dict[str, str]) -> None:
        self.ui_queue.put(("status", "Thinking"))
        self.ui_queue.put(("stream", ""))
        try:
            config = AssistantConfig.from_mapping(environment)
            client = build_openai_client(environment)
            memory_store = build_memory_store(config, environment)
            responder = MemoryAwareResponder(OpenAIResponder(client, config), memory_store)
            speaker = build_speaker(client, config)
            self.manual_speaker = speaker
            buffer = {"text": ""}
            reply = responder.stream_reply(
                prompt,
                lambda delta: self.ui_queue.put(
                    ("stream", (buffer.__setitem__("text", buffer["text"] + delta) or buffer["text"][-400:]))
                ),
            )
            self.log_queue.put(f"PyJippety: {reply}")
            self._record_history("response", reply)
            try:
                speaker.say(reply)
            except Exception as exc:
                self.log_queue.put(f"Speech failed: {exc}")
        except Exception as exc:
            self.log_queue.put(f"Prompt failed: {exc}")
        finally:
            self.manual_speaker = None
            next_status = (
                "Listening"
                if self.assistant_thread and self.assistant_thread.is_alive()
                else "Idle"
            )
            self.ui_queue.put(("status", next_status))

    def on_state(self, state: str) -> None:
        mapping = {
            "listening": "Listening",
            "follow_up": "Follow-up",
            "stopping": "Stopping",
            "idle": "Idle",
        }
        self.ui_queue.put(("status", mapping.get(state, state.title())))

    def on_transcript(self, transcript: str) -> None:
        self.ui_queue.put(("transcript", transcript))
        self._record_history("transcript", transcript)

    def on_response(self, response: str) -> None:
        self._record_history("response", response)

    def _on_close(self) -> None:
        if self.assistant is not None:
            self.assistant.request_stop()
        self.interrupt_current_output()
        logging.getLogger().removeHandler(self.log_handler)
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = PyjippetyApp(root)
    app._append_log("Ready.")
    root.mainloop()


if __name__ == "__main__":
    main()
