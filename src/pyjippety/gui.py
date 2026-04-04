from __future__ import annotations

import logging
import os
import queue
import sys
import time
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from .config import AssistantConfig, env_file_path, load_environment, logs_dir_path
from .controller import AppController
from .tray import build_tray_manager
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
    WARNING,
)
from .views import PyjippetyViewMixin


class QueueLogHandler(logging.Handler):
    def __init__(self, log_queue: queue.Queue[str]) -> None:
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record: logging.LogRecord) -> None:
        self.log_queue.put(self.format(record))


class PyjippetyApp(PyjippetyViewMixin):
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
        self.mute_var = tk.BooleanVar(value=False)
        self.display_name_var = tk.StringVar(value="PyJippety")
        self.last_transcript_var = tk.StringVar(value="")
        self.stream_response_var = tk.StringVar(value="")
        self.status_hint_var = tk.StringVar(value="Ready")
        self.history_entries: list[dict[str, str]] = []
        self.last_response_text = ""
        self.device_map: dict[str, str] = {}
        self.logo_image: tk.PhotoImage | None = None
        self.logo_mark: tk.PhotoImage | None = None
        self.tray_manager = None
        self.window_hidden = False

        load_environment()
        self.config = AssistantConfig.from_env()
        self.controller = AppController(self)
        self._load_logo_assets()
        self._configure_theme()
        self._install_log_handler()
        self._build_layout()
        self.controller.load_profiles()
        self.reload_settings()
        self._init_tray()
        self.controller.maybe_show_setup_wizard()
        self._poll_logs()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<F8>", lambda _: self._toggle_voice_mode())
        self.root.bind("<Control-space>", lambda _: self.push_to_talk())
        self.root.bind("<Escape>", lambda _: self.interrupt_current_output())

    def _install_log_handler(self) -> None:
        handler = QueueLogHandler(self.log_queue)
        handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)s  %(message)s"))
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(handler)
        logs_dir = logs_dir_path()
        logs_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(logs_dir / "pyjippety.log", encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)s  %(message)s"))
        root_logger.addHandler(file_handler)
        self.log_handler = handler
        self.file_log_handler = file_handler

    def _init_tray(self) -> None:
        icon_path = None
        for path in self._candidate_logo_paths():
            if path.exists():
                icon_path = path
                break
        show_cb = lambda: self.root.after(0, self.show_window)
        hide_cb = lambda: self.root.after(0, self.hide_window)
        toggle_cb = lambda: self.root.after(0, self._toggle_voice_mode)
        quit_cb = lambda: self.root.after(0, self.quit_app)
        if icon_path is None:
            self.tray_manager = build_tray_manager(
                icon_path=Path(),
                on_show=show_cb,
                on_hide=hide_cb,
                on_toggle_voice=toggle_cb,
                on_quit=quit_cb,
            )
            return
        self.tray_manager = build_tray_manager(
            icon_path=icon_path,
            on_show=show_cb,
            on_hide=hide_cb,
            on_toggle_voice=toggle_cb,
            on_quit=quit_cb,
        )
        self.tray_manager.start()

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
        self.mute_var.set(values.get("ASSISTANT_MUTE_SPEECH", "false").strip().lower() in {"1", "true", "yes", "on"})

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
        values["ASSISTANT_MUTE_SPEECH"] = "true" if self.mute_var.get() else "false"
        return values

    def collect_form_values(self) -> dict[str, str]:
        return self._collect_form_values()

    def _build_environment(self) -> dict[str, str]:
        return self.controller.build_environment()

    def _refresh_active_config(self, environment: dict[str, str]) -> None:
        self.controller.refresh_active_config(environment)
        self.display_name_var.set(self.config.display_name)
        self.root.title(self.config.display_name)

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
        hints = {
            "Idle": "Waiting for you.",
            "Starting": "Initializing audio and wake word.",
            "Listening": "Waiting for the wake word.",
            "Follow-up": "Listening for a quick follow-up.",
            "Thinking": "Generating a response.",
            "Sleeping": "Background session paused.",
            "Stopping": "Finishing current session.",
            "Error": "Check the session log for details.",
        }
        self.status_hint_var.set(hints.get(text, ""))
        if self.tray_manager is not None:
            self.tray_manager.update_status(text)

    def set_status(self, text: str) -> None:
        self._set_status(text)

    def _append_log(self, message: str) -> None:
        self.log_view.configure(state="normal")
        self.log_view.insert("end", f"{message}\n")
        self.log_view.see("end")
        self.log_view.configure(state="disabled")

    def append_log(self, message: str) -> None:
        self._append_log(message)

    def clear_log(self) -> None:
        self.log_view.configure(state="normal")
        self.log_view.delete("1.0", "end")
        self.log_view.configure(state="disabled")

    def clear_memory(self) -> None:
        self.controller.clear_memory()

    def save_memory_notes(self) -> None:
        self.controller.save_memory_notes()

    def clear_history(self) -> None:
        self.history_entries = []
        self.controller.save_history()
        self.controller.render_history()
        self._append_log("History cleared.")
        self._refresh_recent_prompts()

    def switch_profile(self) -> None:
        self.reload_settings()
        self._append_log(f"Switched to profile '{self.profile_var.get()}'.")

    def save_as_profile(self) -> None:
        name = self.new_profile_entry.get().strip()
        if not name:
            return
        self.controller.save_profile_data(name, self._collect_form_values())
        self.profile_var.set(name)
        self.controller.load_profiles()
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

    def hide_window(self) -> None:
        self.window_hidden = True
        self.root.withdraw()
        if self.tray_manager is not None:
            self.tray_manager.notify_hidden()

    def show_window(self) -> None:
        self.window_hidden = False
        self.root.after(0, self.root.deiconify)
        self.root.after(0, self.root.lift)
        self.root.after(0, self.root.focus_force)

    def quit_app(self) -> None:
        if self.assistant is not None:
            self.assistant.request_stop()
        self.interrupt_current_output()
        if self.tray_manager is not None:
            self.tray_manager.stop()
        logging.getLogger().removeHandler(self.log_handler)
        logging.getLogger().removeHandler(self.file_log_handler)
        self.root.after(0, self.root.destroy)

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

    def on_toggle_mute(self) -> None:
        if self.assistant is not None and hasattr(self.assistant.speaker, "disabled"):
            self.assistant.speaker.disabled = self.mute_var.get()
        if self.manual_speaker is not None and hasattr(self.manual_speaker, "disabled"):
            self.manual_speaker.disabled = self.mute_var.get()
        self._append_log(f"Speech {'muted' if self.mute_var.get() else 'unmuted'}.")

    def repeat_last_answer(self) -> None:
        self.controller.repeat_last_answer()

    def copy_last_answer(self) -> None:
        self.controller.copy_last_answer()

    def clear_conversation(self) -> None:
        self.controller.clear_conversation()

    def test_wake_word(self) -> None:
        self.controller.test_wake_word()

    def open_config_folder(self) -> None:
        self.controller.open_config_folder()

    def open_logs_folder(self) -> None:
        self.controller.open_logs_folder()

    def export_current_profile(self) -> None:
        self.controller.export_current_profile()

    def resend_last_transcript(self) -> None:
        prompt = self.last_transcript_var.get().strip()
        if not prompt:
            return
        self.interrupt_current_output()
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
        self.controller.test_setup()

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
        for key, value in values.items():
            set_key(str(self.env_path), key, value, quote_mode="auto")
            os.environ[key] = value
        self.controller.save_profile_data(self.profile_var.get(), values)
        self._refresh_active_config(self._build_environment())
        self.controller.load_profiles()
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
        values.update(self.controller.load_profile_data(self.profile_var.get()))
        self._populate_form(values)
        self._refresh_active_config(self._build_environment())
        self._refresh_advanced_visibility()
        self.controller.load_history()
        self._append_log(f"Loaded settings from {self.env_path}.")
        if self.config.start_hidden and self.tray_manager is not None and getattr(self.tray_manager, "available", False):
            self.root.after(200, self.hide_window)

    def start_voice_mode(self) -> None:
        self.controller.start_voice_mode()

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

    def run_assistant_thread(self) -> None:
        self._run_assistant_thread()

    def stop_voice_mode(self) -> None:
        if self.assistant is None:
            self._append_log("Voice mode is not running.")
            self._set_status("Idle")
            return
        self.assistant.request_stop()
        self._append_log("Stop requested.")
        self._set_status("Stopping")

    def push_to_talk(self) -> None:
        self.interrupt_current_output()
        self.controller.push_to_talk()

    def ask_from_text(self) -> None:
        prompt = self.prompt_box.get("1.0", "end").strip()
        if not prompt:
            return
        self.interrupt_current_output()
        self.prompt_box.delete("1.0", "end")
        self._append_log(f"You: {prompt}")
        self.controller.record_history("prompt", prompt)
        self._refresh_recent_prompts()
        environment = self._build_environment()
        self._refresh_active_config(environment)
        self.manual_thread = threading.Thread(
            target=self.controller.run_manual_prompt,
            args=(prompt, environment),
            name="pyjippety-manual-prompt",
            daemon=True,
        )
        self.manual_thread.start()

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
        self.controller.record_history("transcript", transcript)

    def on_response(self, response: str) -> None:
        self.last_response_text = response
        self.controller.record_history("response", response)
        self._refresh_recent_prompts()

    def _on_close(self) -> None:
        if self.tray_manager is not None and getattr(self.tray_manager, "available", False):
            self.hide_window()
            return
        self.quit_app()

    def _refresh_recent_prompts(self) -> None:
        if not hasattr(self, "recent_prompts_frame"):
            return
        for child in self.recent_prompts_frame.winfo_children():
            child.destroy()
        prompts = self.controller.recent_prompts()
        if not prompts:
            tk.Label(
                self.recent_prompts_frame,
                text="No recent prompts yet.",
                bg=CARD,
                fg=MUTED,
            ).pack(anchor="w")
            return
        for prompt in prompts:
            ttk.Button(
                self.recent_prompts_frame,
                text=prompt[:36] + ("..." if len(prompt) > 36 else ""),
                command=lambda p=prompt: self._reuse_prompt(p),
                style="Secondary.TButton",
            ).pack(fill="x", pady=(0, 8))

    def _reuse_prompt(self, prompt: str) -> None:
        self.prompt_box.delete("1.0", "end")
        self.prompt_box.insert("1.0", prompt)

    def _refresh_recent_prompts(self) -> None:
        if not hasattr(self, "recent_prompts_frame"):
            return
        for child in self.recent_prompts_frame.winfo_children():
            child.destroy()
        prompts = self.controller.recent_prompts()
        if not prompts:
            tk.Label(
                self.recent_prompts_frame,
                text="No recent prompts yet.",
                bg=CARD,
                fg=MUTED,
            ).pack(anchor="w")
            return
        for prompt in prompts:
            ttk.Button(
                self.recent_prompts_frame,
                text=prompt[:36] + ("..." if len(prompt) > 36 else ""),
                command=lambda p=prompt: self._reuse_prompt(p),
                style="Secondary.TButton",
            ).pack(fill="x", pady=(0, 8))

    def _reuse_prompt(self, prompt: str) -> None:
        self.prompt_box.delete("1.0", "end")
        self.prompt_box.insert("1.0", prompt)


def main() -> None:
    root = tk.Tk()
    app = PyjippetyApp(root)
    app._append_log("Ready.")
    root.mainloop()


if __name__ == "__main__":
    main()
