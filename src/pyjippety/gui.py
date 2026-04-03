from __future__ import annotations

import logging
import os
import queue
import threading
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk

from .config import AssistantConfig, env_file_path, load_environment
from .integrations import (
    OpenAIResponder,
    build_live_assistant,
    build_openai_client,
    build_speaker,
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
            SettingField("ASSISTANT_AUDIO_DEVICE_INDEX", "Audio device index", "Leave blank to use the default input/output device.", advanced=True),
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
        self.entry_widgets: dict[str, ttk.Entry] = {}
        self.text_widgets: dict[str, tk.Text] = {}
        self.bool_vars: dict[str, tk.BooleanVar] = {}
        self.setting_rows: list[tuple[SettingField, tuple[tk.Widget, tk.Widget]]] = []
        self.section_cards: list[tuple[SettingSection, tk.Widget]] = []
        self.env_path = env_file_path()

        load_environment()
        self.config = AssistantConfig.from_env()
        self._configure_theme()
        self._install_log_handler()
        self._build_layout()
        self.reload_settings()
        self._poll_logs()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

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
        header.grid_columnconfigure(0, weight=1)

        ttk.Label(header, text="PyJippety", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Desktop voice assistant",
            style="Subheader.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        self.status_badge = tk.Label(
            header,
            text="Idle",
            bg=CARD_ALT,
            fg=TEXT,
            padx=14,
            pady=8,
            font=("TkDefaultFont", 10, "bold"),
        )
        self.status_badge.grid(row=0, column=1, rowspan=2, sticky="e")

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
            text="Assistant",
            bg=CARD,
            fg=TEXT,
            font=("TkDefaultFont", 12, "bold"),
        ).pack(anchor="w")
        tk.Label(
            session_card,
            text="Start or stop wake-word listening, then use the workspace to test prompts and adjust settings.",
            bg=CARD,
            fg=MUTED,
            justify="left",
            wraplength=250,
        ).pack(anchor="w", pady=(6, 14))

        self.start_button = ttk.Button(
            session_card,
            text="Start voice mode",
            command=self.start_voice_mode,
            style="Primary.TButton",
        )
        self.start_button.pack(fill="x")

        self.stop_button = ttk.Button(
            session_card,
            text="Stop voice mode",
            command=self.stop_voice_mode,
            style="Danger.TButton",
        )
        self.stop_button.pack(fill="x", pady=(10, 0))

        self.save_button = ttk.Button(
            session_card,
            text="Save settings",
            command=self.save_settings,
            style="Secondary.TButton",
        )
        self.save_button.pack(fill="x", pady=(18, 0))

        self.reload_button = ttk.Button(
            session_card,
            text="Reload settings",
            command=self.reload_settings,
            style="Secondary.TButton",
        )
        self.reload_button.pack(fill="x", pady=(10, 0))

        setup_card = self._card(parent)
        setup_card.pack(fill="x", pady=(16, 0))

        tk.Label(
            setup_card,
            text="Current setup",
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

        install_card = self._card(parent)
        install_card.pack(fill="x", pady=(16, 0))

        tk.Label(
            install_card,
            text="Config file",
            bg=CARD,
            fg=TEXT,
            font=("TkDefaultFont", 12, "bold"),
        ).pack(anchor="w")
        tk.Label(
            install_card,
            text=str(self.env_path),
            bg=CARD,
            fg=MUTED,
            justify="left",
            wraplength=250,
        ).pack(anchor="w", pady=(6, 0))
        tk.Label(
            install_card,
            text="The installer uses this file automatically, so the app can be launched from a desktop shortcut.",
            bg=CARD,
            fg=MUTED,
            justify="left",
            wraplength=250,
        ).pack(anchor="w", pady=(10, 0))

        memory_card = self._card(parent)
        memory_card.pack(fill="x", pady=(16, 0))
        tk.Label(
            memory_card,
            text="Memory",
            bg=CARD,
            fg=TEXT,
            font=("TkDefaultFont", 12, "bold"),
        ).pack(anchor="w")
        self.memory_summary = tk.Label(
            memory_card,
            text="",
            justify="left",
            anchor="nw",
            bg=CARD,
            fg=MUTED,
            wraplength=250,
        )
        self.memory_summary.pack(fill="x", pady=(8, 10))
        ttk.Button(
            memory_card,
            text="Clear memory",
            command=self.clear_memory,
            style="Secondary.TButton",
        ).pack(fill="x")

    def _build_content(self, parent: ttk.Frame) -> None:
        notebook = ttk.Notebook(parent, style="Notebook.TNotebook")
        notebook.grid(row=0, column=0, sticky="nsew")

        workspace = ttk.Frame(notebook, style="App.TFrame")
        settings = ttk.Frame(notebook, style="App.TFrame")
        notebook.add(workspace, text="Workspace")
        notebook.add(settings, text="Settings")

        self._build_workspace_tab(workspace)
        self._build_settings_tab(settings)

    def _build_workspace_tab(self, parent: ttk.Frame) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        prompt_card = self._card(parent, padding=(18, 18))
        prompt_card.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 16))
        prompt_card.grid_columnconfigure(0, weight=1)

        tk.Label(
            prompt_card,
            text="Try a typed request",
            bg=CARD,
            fg=TEXT,
            font=("TkDefaultFont", 12, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            prompt_card,
            text="Use this when you want to test replies without waiting for the wake word.",
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
            text="Tip: press Ctrl+Enter to send.",
            bg=CARD,
            fg=MUTED,
        ).grid(row=0, column=0, sticky="w")
        self.ask_button = ttk.Button(
            action_row,
            text="Send request",
            command=self.ask_from_text,
            style="Primary.TButton",
        )
        self.ask_button.grid(row=0, column=1, sticky="e")

        log_card = self._card(parent, padding=(18, 18))
        log_card.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
        log_card.grid_columnconfigure(0, weight=1)
        log_card.grid_rowconfigure(1, weight=1)

        log_header = tk.Frame(log_card, bg=CARD)
        log_header.grid(row=0, column=0, sticky="ew")
        log_header.grid_columnconfigure(0, weight=1)
        tk.Label(
            log_header,
            text="Activity",
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

    def _build_settings_tab(self, parent: ttk.Frame) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        toolbar = self._card(parent, padding=(18, 14))
        toolbar.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 16))
        toolbar.grid_columnconfigure(0, weight=1)
        tk.Label(
            toolbar,
            text="Settings",
            bg=CARD,
            fg=TEXT,
            font=("TkDefaultFont", 12, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            toolbar,
            text="Changes take effect immediately for typed requests and the next time you start voice mode.",
            bg=CARD,
            fg=MUTED,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        button_row = tk.Frame(toolbar, bg=CARD)
        button_row.grid(row=0, column=1, rowspan=2, sticky="e")
        ttk.Button(button_row, text="Save", command=self.save_settings, style="Primary.TButton").pack(side="left")
        ttk.Button(button_row, text="Reload", command=self.reload_settings, style="Secondary.TButton").pack(side="left", padx=(10, 0))
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

        widget = ttk.Entry(
            parent,
            style="App.TEntry",
            show="*" if field.secret else "",
        )
        widget.grid(row=row, column=1, sticky="ew", pady=8, ipady=2)
        self.entry_widgets[field.key] = widget
        return (label_frame, widget)

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

    def _populate_form(self, values: dict[str, str]) -> None:
        for key, widget in self.entry_widgets.items():
            widget.delete(0, "end")
            widget.insert(0, values.get(key, ""))
        for key, widget in self.text_widgets.items():
            widget.delete("1.0", "end")
            widget.insert("1.0", values.get(key, ""))
        for key, variable in self.bool_vars.items():
            variable.set(values.get(key, "").strip().lower() in {"1", "true", "yes", "on"})

    def _collect_form_values(self) -> dict[str, str]:
        values: dict[str, str] = {}
        for key, widget in self.entry_widgets.items():
            values[key] = widget.get().strip()
        for key, widget in self.text_widgets.items():
            values[key] = widget.get("1.0", "end").strip().replace("\n", " ")
        for key, variable in self.bool_vars.items():
            values[key] = "true" if variable.get() else "false"
        return values

    def _build_environment(self) -> dict[str, str]:
        environment = dict(os.environ)
        environment.update(self._collect_form_values())
        return environment

    def _refresh_active_config(self, environment: dict[str, str]) -> None:
        self.config = AssistantConfig.from_mapping(environment)
        summary_lines = list(self.config.summary_lines())
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
            return
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
            "Thinking": ("#f2eadb", WARNING),
            "Stopping": ("#f2eadb", WARNING),
            "Error": ("#f3e4e2", ERROR),
        }
        bg, fg = colors.get(text, (CARD_ALT, TEXT))
        self.status_badge.configure(text=text, bg=bg, fg=fg)
        running = text in {"Starting", "Listening", "Thinking", "Stopping"}
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
        except queue.Empty:
            pass

        self.root.after(120, self._poll_logs)

    def save_settings(self) -> None:
        from dotenv import set_key

        values = self._collect_form_values()
        self.env_path.parent.mkdir(parents=True, exist_ok=True)
        self.env_path.touch(exist_ok=True)
        for key in self._all_setting_keys():
            set_key(str(self.env_path), key, values.get(key, ""), quote_mode="auto")
            os.environ[key] = values.get(key, "")
        self._refresh_active_config(self._build_environment())
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
        self._populate_form(values)
        self._refresh_active_config(self._build_environment())
        self._refresh_advanced_visibility()
        self._append_log(f"Loaded settings from {self.env_path}.")

    def start_voice_mode(self) -> None:
        if self.assistant_thread and self.assistant_thread.is_alive():
            self._append_log("Voice mode is already running.")
            return

        environment = self._build_environment()
        self._refresh_active_config(environment)
        self._set_status("Starting")
        try:
            self.assistant = build_live_assistant(self.config, environment=environment)
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

    def ask_from_text(self) -> None:
        prompt = self.prompt_box.get("1.0", "end").strip()
        if not prompt:
            return
        self.prompt_box.delete("1.0", "end")
        self._append_log(f"You: {prompt}")
        environment = self._build_environment()
        self._refresh_active_config(environment)
        threading.Thread(
            target=self._run_manual_prompt,
            args=(prompt, environment),
            name="pyjippety-manual-prompt",
            daemon=True,
        ).start()

    def _run_manual_prompt(self, prompt: str, environment: dict[str, str]) -> None:
        self.ui_queue.put(("status", "Thinking"))
        try:
            config = AssistantConfig.from_mapping(environment)
            client = build_openai_client(environment)
            memory_store = build_memory_store(config, environment)
            reply = MemoryAwareResponder(
                OpenAIResponder(client, config), memory_store
            ).reply(prompt)
            self.log_queue.put(f"PyJippety: {reply}")
            try:
                build_speaker(client, config).say(reply)
            except Exception as exc:
                self.log_queue.put(f"Speech failed: {exc}")
        except Exception as exc:
            self.log_queue.put(f"Prompt failed: {exc}")
        finally:
            next_status = (
                "Listening"
                if self.assistant_thread and self.assistant_thread.is_alive()
                else "Idle"
            )
            self.ui_queue.put(("status", next_status))

    def _on_close(self) -> None:
        if self.assistant is not None:
            self.assistant.request_stop()
        logging.getLogger().removeHandler(self.log_handler)
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = PyjippetyApp(root)
    app._append_log("Ready.")
    root.mainloop()


if __name__ == "__main__":
    main()
