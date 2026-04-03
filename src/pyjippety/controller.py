from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from .config import AssistantConfig
from .integrations import (
    OpenAITranscribingListener,
    OpenAIResponder,
    build_live_assistant,
    build_openai_client,
    build_speaker,
    list_microphones,
)
from .memory import MemoryAwareResponder, build_memory_store, memory_file_path
from .profile_store import ProfileStore


class AppController:
    def __init__(self, app: Any) -> None:
        self.app = app
        self.profile_store = ProfileStore(app.env_path)

    def build_environment(self) -> dict[str, str]:
        environment = dict(os.environ)
        environment.update(self.app._collect_form_values())
        environment["PYJIPPETY_PROFILE"] = self.app.profile_var.get().strip() or "default"
        return environment

    def refresh_active_config(self, environment: dict[str, str]) -> None:
        self.app.config = AssistantConfig.from_mapping(environment)
        summary_lines = list(self.app.config.summary_lines())
        summary_lines.insert(0, f"Profile: {environment.get('PYJIPPETY_PROFILE', 'default')}")
        summary_lines.append(
            f"OpenAI key: {'set' if environment.get('OPENAI_API_KEY') else 'missing'}"
        )
        summary_lines.append(
            f"Picovoice key: {'set' if environment.get('PICOVOICE_ACCESS_KEY') else 'missing'}"
        )
        self.app.config_summary.configure(text="\n".join(summary_lines))
        self.refresh_memory_summary(environment)

    def refresh_memory_summary(self, environment: dict[str, str]) -> None:
        store = build_memory_store(self.app.config, environment)
        if store is None:
            self.app.memory_summary.configure(text="Memory is off.")
            self.app.memory_notes_box.delete("1.0", "end")
            return
        self.app.memory_notes_box.delete("1.0", "end")
        self.app.memory_notes_box.insert("1.0", "\n".join(store.state.facts))
        self.app.memory_summary.configure(
            text=(
                f"File: {memory_file_path(environment)}\n"
                f"Notes: {len(store.state.facts)}\n"
                f"Recent exchanges: {len(store.state.turns)}"
            )
        )

    def load_profiles(self) -> None:
        profiles = self.profile_store.list_profiles()
        self.app.profile_combo["values"] = profiles
        if self.app.profile_var.get() not in profiles:
            self.app.profile_var.set("default")

    def load_history(self) -> None:
        self.app.history_entries = self.profile_store.load_history(self.app.profile_var.get())
        self.render_history()

    def save_history(self) -> None:
        self.profile_store.save_history(
            self.app.profile_var.get(), self.app.history_entries[-100:]
        )

    def record_history(self, kind: str, text: str) -> None:
        self.app.history_entries.append(
            {
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "kind": kind,
                "text": text,
            }
        )
        self.app.history_entries = self.app.history_entries[-100:]
        self.save_history()
        self.render_history()

    def render_history(self) -> None:
        if not hasattr(self.app, "history_view"):
            return
        self.app.history_view.configure(state="normal")
        self.app.history_view.delete("1.0", "end")
        for entry in self.app.history_entries:
            self.app.history_view.insert(
                "end",
                f"[{entry['time']}] {entry['kind']}: {entry['text']}\n\n",
            )
        self.app.history_view.configure(state="disabled")

    def load_profile_data(self, name: str) -> dict[str, str]:
        return self.profile_store.load_settings(name)

    def save_profile_data(self, name: str, values: dict[str, str]) -> None:
        self.profile_store.save_settings(name, values)

    def load_microphones(self) -> None:
        devices = list_microphones()
        self.app.device_map = {"Default device": ""}
        values = ["Default device"]
        for index, name in devices:
            label = f"{index}: {name}"
            self.app.device_map[label] = str(index)
            values.append(label)
        if hasattr(self.app, "device_combo"):
            self.app.device_combo["values"] = values

    def maybe_show_setup_wizard(self) -> None:
        environment = self.build_environment()
        if environment.get("OPENAI_API_KEY") and environment.get("PICOVOICE_ACCESS_KEY"):
            return
        self.app.root.after(250, self.app.show_setup_wizard)

    def save_memory_notes(self) -> None:
        environment = self.build_environment()
        self.refresh_active_config(environment)
        store = build_memory_store(self.app.config, environment)
        if store is None:
            self.app.append_log("Memory is disabled.")
            return
        notes = [
            line.strip()
            for line in self.app.memory_notes_box.get("1.0", "end").splitlines()
            if line.strip()
        ]
        store.state.facts = notes[: self.app.config.memory_fact_limit]
        store.save()
        self.refresh_memory_summary(environment)
        self.app.append_log("Saved memory notes.")
        self.record_history("memory", "saved notes")

    def clear_memory(self) -> None:
        environment = self.build_environment()
        self.refresh_active_config(environment)
        store = build_memory_store(self.app.config, environment)
        if store is None:
            self.app.append_log("Memory is disabled.")
            return
        store.clear()
        self.refresh_memory_summary(environment)
        self.app.append_log("Memory cleared.")
        self.record_history("memory", "cleared")

    def start_voice_mode(self) -> None:
        if self.app.assistant_thread and self.app.assistant_thread.is_alive():
            self.app.append_log("Voice mode is already running.")
            return
        environment = self.build_environment()
        self.refresh_active_config(environment)
        self.app.set_status("Starting")
        try:
            self.app.assistant = build_live_assistant(
                self.app.config, environment=environment, events=self.app
            )
        except Exception as exc:
            self.app.append_log(f"Startup failed: {exc}")
            self.app.set_status("Error")
            return
        self.app.assistant_thread = threading.Thread(
            target=self.app.run_assistant_thread,
            name="pyjippety-voice",
            daemon=True,
        )
        self.app.assistant_thread.start()
        self.app.set_status("Listening")

    def run_manual_prompt(self, prompt: str, environment: dict[str, str]) -> None:
        self.app.ui_queue.put(("status", "Thinking"))
        self.app.ui_queue.put(("stream", ""))
        try:
            config = AssistantConfig.from_mapping(environment)
            client = build_openai_client(environment)
            memory_store = build_memory_store(config, environment)
            responder = MemoryAwareResponder(OpenAIResponder(client, config), memory_store)
            speaker = build_speaker(client, config)
            self.app.manual_speaker = speaker
            buffer = {"text": ""}

            def on_delta(delta: str) -> None:
                buffer["text"] += delta
                self.app.ui_queue.put(("stream", buffer["text"][-400:]))

            reply = responder.stream_reply(prompt, on_delta)
            self.app.log_queue.put(f"PyJippety: {reply}")
            self.record_history("response", reply)
            try:
                speaker.say(reply)
            except Exception as exc:
                self.app.log_queue.put(f"Speech failed: {exc}")
        except Exception as exc:
            self.app.log_queue.put(f"Prompt failed: {exc}")
        finally:
            self.app.manual_speaker = None
            next_status = (
                "Listening"
                if self.app.assistant_thread and self.app.assistant_thread.is_alive()
                else "Idle"
            )
            self.app.ui_queue.put(("status", next_status))

    def push_to_talk(self) -> None:
        if self.app.manual_thread and self.app.manual_thread.is_alive():
            return
        environment = self.build_environment()
        self.refresh_active_config(environment)
        self.app.append_log("Push-to-talk started.")

        def run_push_to_talk() -> None:
            self.app.ui_queue.put(("status", "Thinking"))
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
                    self.app.log_queue.put("Push-to-talk timed out.")
                    return
                self.app.ui_queue.put(("transcript", transcript))
                self.app.log_queue.put(f"You: {transcript}")
                self.record_history("transcript", transcript)
                self.run_manual_prompt(transcript, environment)
            except Exception as exc:
                self.app.log_queue.put(f"Push-to-talk failed: {exc}")
            finally:
                self.app.ui_queue.put(("status", "Idle"))

        self.app.manual_thread = threading.Thread(
            target=run_push_to_talk, name="pyjippety-push-to-talk", daemon=True
        )
        self.app.manual_thread.start()

    def test_setup(self) -> None:
        environment = self.build_environment()
        self.app.append_log("Running setup checks...")

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
                self.app.log_queue.put(result)
                self.record_history("setup-test", result)

        threading.Thread(target=run_checks, name="pyjippety-setup-test", daemon=True).start()


__all__ = ["AppController"]
