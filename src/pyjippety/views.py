from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from .ui_shared import (
    ACCENT,
    ACCENT_ACTIVE,
    BORDER,
    CARD,
    CARD_ALT,
    ERROR,
    MUTED,
    PERSONALITY_PRESETS,
    SETTINGS_SECTIONS,
    SUBTLE,
    SUCCESS,
    SURFACE,
    TEXT,
)


class PyjippetyViewMixin:
    def _configure_theme(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("App.TFrame", background=SURFACE)
        style.configure("Card.TFrame", background=CARD, relief="flat")
        style.configure("Section.TLabelframe", background=CARD, borderwidth=0)
        style.configure(
            "Section.TLabelframe.Label",
            background=CARD,
            foreground=TEXT,
            font=("TkDefaultFont", 10, "bold"),
        )
        style.configure("App.TLabel", background=SURFACE, foreground=TEXT)
        style.configure("Card.TLabel", background=CARD, foreground=TEXT)
        style.configure("Muted.TLabel", background=CARD, foreground=MUTED)
        style.configure(
            "Header.TLabel",
            background=SURFACE,
            foreground=TEXT,
            font=("TkHeadingFont", 20, "bold"),
        )
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

    def _build_layout(self) -> None:
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)

        header = ttk.Frame(self.root, style="App.TFrame", padding=(24, 20, 24, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        if self.logo_mark is not None:
            tk.Label(header, image=self.logo_mark, bg=SURFACE).grid(
                row=0, column=0, rowspan=2, sticky="w", padx=(0, 12)
            )

        ttk.Label(header, textvariable=self.display_name_var, style="Header.TLabel").grid(row=0, column=1, sticky="w")
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
        tk.Label(
            header,
            textvariable=self.status_hint_var,
            bg=SURFACE,
            fg=MUTED,
            justify="right",
        ).grid(row=2, column=2, sticky="e", pady=(6, 0))

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

        self.start_button = ttk.Button(action_grid, text="Start", command=self.start_voice_mode, style="Primary.TButton")
        self.start_button.grid(row=0, column=0, sticky="ew")
        self.stop_button = ttk.Button(action_grid, text="Stop", command=self.stop_voice_mode, style="Danger.TButton")
        self.stop_button.grid(row=0, column=1, sticky="ew", padx=(10, 0))
        self.push_to_talk_button = ttk.Button(action_grid, text="Push to talk", command=self.push_to_talk, style="Secondary.TButton")
        self.push_to_talk_button.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.interrupt_button = ttk.Button(action_grid, text="Interrupt", command=self.interrupt_current_output, style="Secondary.TButton")
        self.interrupt_button.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=(10, 0))
        self.test_button = ttk.Button(action_grid, text="Test setup", command=self.test_setup, style="Secondary.TButton")
        self.test_button.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.sleep_button = ttk.Button(action_grid, text="Sleep", command=self.sleep_voice_mode, style="Secondary.TButton")
        self.sleep_button.grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=(10, 0))
        self.wake_test_button = ttk.Button(action_grid, text="Wake cue", command=self.test_wake_word, style="Secondary.TButton")
        self.wake_test_button.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        ttk.Checkbutton(
            action_grid,
            text="Mute speech",
            variable=self.mute_var,
            command=self.on_toggle_mute,
            style="App.TCheckbutton",
        ).grid(row=3, column=1, sticky="w", padx=(10, 0), pady=(10, 0))

        setup_card = self._card(parent)
        setup_card.pack(fill="x", pady=(16, 0))
        tk.Label(setup_card, text="At a glance", bg=CARD, fg=TEXT, font=("TkDefaultFont", 12, "bold")).pack(anchor="w")
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
        tk.Label(prompt_card, text="Type a request", bg=CARD, fg=TEXT, font=("TkDefaultFont", 12, "bold")).grid(row=0, column=0, sticky="w")
        tk.Label(prompt_card, text="Quick way to test the assistant without using the wake word.", bg=CARD, fg=MUTED, justify="left").grid(row=1, column=0, sticky="w", pady=(4, 12))
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
        tk.Label(action_row, text="Ctrl+Enter sends", bg=CARD, fg=MUTED).grid(row=0, column=0, sticky="w")
        self.ask_button = ttk.Button(action_row, text="Ask", command=self.ask_from_text, style="Primary.TButton")
        self.ask_button.grid(row=0, column=1, sticky="e")
        action_row_two = tk.Frame(prompt_card, bg=CARD)
        action_row_two.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(action_row_two, text="Repeat", command=self.repeat_last_answer, style="Secondary.TButton").pack(side="left")
        ttk.Button(action_row_two, text="Copy answer", command=self.copy_last_answer, style="Secondary.TButton").pack(side="left", padx=(10, 0))
        ttk.Button(action_row_two, text="Clear view", command=self.clear_conversation, style="Secondary.TButton").pack(side="left", padx=(10, 0))

        recent_card = self._card(parent, padding=(18, 18))
        recent_card.grid(row=2, column=1, sticky="new", padx=(12, 4), pady=(0, 16))
        recent_card.grid_columnconfigure(0, weight=1)
        tk.Label(recent_card, text="Recent prompts", bg=CARD, fg=TEXT, font=("TkDefaultFont", 12, "bold")).grid(row=0, column=0, sticky="w")
        self.recent_prompts_frame = tk.Frame(recent_card, bg=CARD)
        self.recent_prompts_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))

        transcript_card = self._card(parent, padding=(18, 18))
        transcript_card.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 16))
        transcript_card.grid_columnconfigure(0, weight=1)
        tk.Label(transcript_card, text="Last transcript", bg=CARD, fg=TEXT, font=("TkDefaultFont", 12, "bold")).grid(row=0, column=0, sticky="w")
        tk.Label(transcript_card, text="Correct it and send again if speech recognition was close but not right.", bg=CARD, fg=MUTED).grid(row=1, column=0, sticky="w", pady=(4, 10))
        self.transcript_entry = ttk.Entry(transcript_card, textvariable=self.last_transcript_var, style="App.TEntry")
        self.transcript_entry.grid(row=2, column=0, sticky="ew", ipady=2)
        actions = tk.Frame(transcript_card, bg=CARD)
        actions.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        actions.grid_columnconfigure(0, weight=1)
        ttk.Button(actions, text="Send transcript", command=self.resend_last_transcript, style="Secondary.TButton").grid(row=0, column=1, sticky="e")
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
        tk.Label(log_header, text="Session log", bg=CARD, fg=TEXT, font=("TkDefaultFont", 12, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Button(log_header, text="Clear log", command=self.clear_log, style="Secondary.TButton").grid(row=0, column=1, sticky="e")
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
        side_card.grid(row=3, column=1, sticky="nsew", padx=(12, 4), pady=(0, 4))
        side_card.grid_columnconfigure(0, weight=1)
        side_card.grid_rowconfigure(5, weight=1)
        tk.Label(side_card, text="Notes", bg=CARD, fg=TEXT, font=("TkDefaultFont", 12, "bold")).grid(row=0, column=0, sticky="w")
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
        ttk.Button(memory_actions, text="Save notes", command=self.save_memory_notes, style="Secondary.TButton").pack(side="left")
        ttk.Button(memory_actions, text="Clear memory", command=self.clear_memory, style="Secondary.TButton").pack(side="left", padx=(10, 0))
        history_header = tk.Frame(side_card, bg=CARD)
        history_header.grid(row=4, column=0, sticky="ew")
        history_header.grid_columnconfigure(0, weight=1)
        tk.Label(history_header, text="Recent", bg=CARD, fg=TEXT, font=("TkDefaultFont", 12, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Button(history_header, text="Clear", command=self.clear_history, style="Secondary.TButton").grid(row=0, column=1, sticky="e")
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
        tk.Label(toolbar, text="Setup", bg=CARD, fg=TEXT, font=("TkDefaultFont", 12, "bold")).grid(row=0, column=0, sticky="w")
        tk.Label(toolbar, text="Profiles, presets, devices, and behavior live here.", bg=CARD, fg=MUTED, justify="left").grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 12))
        controls = tk.Frame(toolbar, bg=CARD)
        controls.grid(row=0, column=1, rowspan=2, sticky="e")
        controls.grid_columnconfigure(1, weight=1)
        controls.grid_columnconfigure(3, weight=1)
        tk.Label(controls, text="Profile", bg=CARD, fg=MUTED).grid(row=0, column=0, sticky="w")
        self.profile_combo = ttk.Combobox(controls, textvariable=self.profile_var, state="readonly", values=("default",), width=14)
        self.profile_combo.grid(row=0, column=1, sticky="ew")
        self.profile_combo.bind("<<ComboboxSelected>>", lambda _: self.switch_profile())
        self.new_profile_entry = ttk.Entry(controls, style="App.TEntry", width=14)
        self.new_profile_entry.grid(row=0, column=2, padx=(10, 0), sticky="ew", ipady=1)
        self.new_profile_entry.insert(0, "new-profile")
        ttk.Button(controls, text="Save as", command=self.save_as_profile, style="Secondary.TButton").grid(row=0, column=3, padx=(10, 0), sticky="ew")
        tk.Label(controls, text="Preset", bg=CARD, fg=MUTED).grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.preset_combo = ttk.Combobox(controls, textvariable=self.preset_var, state="readonly", values=tuple(PERSONALITY_PRESETS.keys()), width=14)
        self.preset_combo.grid(row=1, column=1, sticky="ew", pady=(10, 0))
        ttk.Button(controls, text="Apply preset", command=self.apply_preset, style="Secondary.TButton").grid(row=1, column=2, padx=(10, 0), sticky="ew", pady=(10, 0))
        ttk.Button(controls, text="Save", command=self.save_settings, style="Primary.TButton").grid(row=1, column=3, padx=(10, 0), sticky="ew", pady=(10, 0))
        ttk.Button(controls, text="Reload", command=self.reload_settings, style="Secondary.TButton").grid(row=1, column=4, padx=(10, 0), sticky="ew", pady=(10, 0))
        extras = tk.Frame(toolbar, bg=CARD)
        extras.grid(row=3, column=0, columnspan=2, sticky="w", pady=(12, 0))
        ttk.Button(extras, text="Open config folder", command=self.open_config_folder, style="Secondary.TButton").pack(side="left")
        ttk.Button(extras, text="Open logs folder", command=self.open_logs_folder, style="Secondary.TButton").pack(side="left", padx=(10, 0))
        ttk.Button(extras, text="Export profile", command=self.export_current_profile, style="Secondary.TButton").pack(side="left", padx=(10, 0))
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
        form.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
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

    def _build_settings_section(self, parent: ttk.Frame, section) -> None:
        card = self._card(parent, padding=(18, 18))
        card.pack(fill="x", padx=4, pady=(0, 16))
        self.section_cards.append((section, card))
        card.grid_columnconfigure(1, weight=1)
        tk.Label(card, text=section.title, bg=CARD, fg=TEXT, font=("TkDefaultFont", 12, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        tk.Label(card, text=section.description, bg=CARD, fg=MUTED, justify="left", wraplength=780).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 14))
        row_index = 2
        for field in section.fields:
            row_widget = self._build_setting_row(card, row_index, field)
            self.setting_rows.append((field, row_widget))
            row_index += 1

    def _build_setting_row(self, parent: tk.Frame, row: int, field) -> tuple[tk.Widget, tk.Widget]:
        label_frame = tk.Frame(parent, bg=CARD)
        label_frame.grid(row=row, column=0, sticky="nw", padx=(0, 18), pady=8)
        tk.Label(label_frame, text=field.label, bg=CARD, fg=TEXT, anchor="w").pack(anchor="w")
        if field.note:
            tk.Label(label_frame, text=field.note, bg=CARD, fg=MUTED, justify="left", wraplength=260).pack(anchor="w", pady=(4, 0))
        if field.kind == "bool":
            variable = tk.BooleanVar(value=False)
            self.bool_vars[field.key] = variable
            control = ttk.Checkbutton(parent, variable=variable, style="App.TCheckbutton")
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
            self.device_combo = ttk.Combobox(parent, textvariable=self.device_var, state="readonly", values=("Default device",))
            self.device_combo.grid(row=row, column=1, sticky="ew", pady=8, ipady=2)
            self.device_combo.bind("<<ComboboxSelected>>", lambda _: self._apply_device_selection())
            self.controller.load_microphones()
            return (label_frame, self.device_combo)
        widget = ttk.Entry(parent, style="App.TEntry", show="*" if field.secret else "")
        widget.grid(row=row, column=1, sticky="ew", pady=8, ipady=2)
        self.entry_widgets[field.key] = widget
        return (label_frame, widget)
