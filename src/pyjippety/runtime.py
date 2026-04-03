from __future__ import annotations

import logging
import time
from typing import Protocol

from .config import AssistantConfig


LOGGER = logging.getLogger(__name__)


def normalize_text(text: str) -> str:
    return " ".join(text.lower().strip().split())


def is_exit_command(text: str, exit_words: tuple[str, ...]) -> bool:
    normalized = normalize_text(text)
    return normalized in exit_words


class TranscriptListener(Protocol):
    def calibrate(self) -> None: ...

    def listen(
        self, *, timeout: float | None = None, phrase_time_limit: float | None = None
    ) -> str | None: ...


class WakeWordDetector(Protocol):
    def wait_for_wake_word(self) -> bool: ...

    def pause(self) -> None: ...

    def resume(self) -> None: ...

    def request_stop(self) -> None: ...

    def close(self) -> None: ...


class Responder(Protocol):
    def reply(self, prompt: str) -> str: ...


class Speaker(Protocol):
    def say(self, text: str) -> None: ...

    def interrupt(self) -> None: ...


class CuePlayer(Protocol):
    def play_wake_cue(self) -> None: ...


class NullCuePlayer:
    def play_wake_cue(self) -> None:
        return


class AssistantEvents(Protocol):
    def on_state(self, state: str) -> None: ...

    def on_transcript(self, transcript: str) -> None: ...

    def on_response(self, response: str) -> None: ...


class NullEvents:
    def on_state(self, state: str) -> None:
        return

    def on_transcript(self, transcript: str) -> None:
        return

    def on_response(self, response: str) -> None:
        return


class DesktopAssistant:
    def __init__(
        self,
        config: AssistantConfig,
        detector: WakeWordDetector,
        listener: TranscriptListener,
        responder: Responder,
        speaker: Speaker,
        cue_player: CuePlayer | None = None,
        events: AssistantEvents | None = None,
    ) -> None:
        self.config = config
        self.detector = detector
        self.listener = listener
        self.responder = responder
        self.speaker = speaker
        self.cue_player = cue_player or NullCuePlayer()
        self.events = events or NullEvents()
        self.last_activity_at = time.monotonic()
        self.last_transcript = ""
        self.last_response = ""
        self.follow_up_open = False

    def handle_prompt(self, prompt: str) -> bool:
        LOGGER.info("Prompt: %s", prompt)
        self.last_activity_at = time.monotonic()
        self.last_transcript = prompt
        self.events.on_transcript(prompt)
        if is_exit_command(prompt, self.config.exit_words):
            self.request_stop()
            LOGGER.info("Stop command received.")
            return False
        reply = self.responder.reply(prompt)
        self.last_response = reply
        self.events.on_response(reply)
        self.speaker.say(reply)
        return True

    def request_stop(self) -> None:
        self.detector.request_stop()
        self.follow_up_open = False
        self.events.on_state("stopping")
        self.speaker.interrupt()

    def _listen_for_prompt(
        self, *, timeout: float | None = None, phrase_time_limit: float | None = None
    ) -> str | None:
        self.detector.pause()
        try:
            return self.listener.listen(
                timeout=timeout, phrase_time_limit=phrase_time_limit
            )
        finally:
            self.detector.resume()

    def _run_follow_up_turns(self) -> bool:
        if not self.config.follow_up_enabled:
            return True

        remaining_turns = max(self.config.follow_up_turn_limit, 0)
        self.follow_up_open = remaining_turns > 0
        if self.follow_up_open:
            self.events.on_state("follow_up")
        while remaining_turns > 0:
            prompt = self._listen_for_prompt(
                timeout=self.config.follow_up_timeout,
                phrase_time_limit=self.config.phrase_time_limit,
            )
            if not prompt:
                LOGGER.info("Follow-up window closed.")
                self.follow_up_open = False
                self.events.on_state("listening")
                return True
            keep_running = self.handle_prompt(prompt)
            if not keep_running:
                self.follow_up_open = False
                return False
            remaining_turns -= 1
        self.follow_up_open = False
        self.events.on_state("listening")
        return True

    def run(self, once: bool = False) -> None:
        self.listener.calibrate()
        LOGGER.info("Listening for %s.", self.config.wake_word)
        self.events.on_state("listening")
        try:
            while True:
                if not self.detector.wait_for_wake_word():
                    break
                self.last_activity_at = time.monotonic()
                self.cue_player.play_wake_cue()
                prompt = self._listen_for_prompt()
                if not prompt:
                    LOGGER.info("No prompt detected after wake word.")
                    if once:
                        break
                    continue

                keep_running = self.handle_prompt(prompt)
                if not keep_running:
                    break
                keep_running = self._run_follow_up_turns()
                if not keep_running:
                    break
                if once:
                    break
        finally:
            self.follow_up_open = False
            self.events.on_state("idle")
            self.detector.close()


__all__ = [
    "AssistantEvents",
    "CuePlayer",
    "DesktopAssistant",
    "NullCuePlayer",
    "Responder",
    "Speaker",
    "TranscriptListener",
    "WakeWordDetector",
    "is_exit_command",
    "normalize_text",
]
