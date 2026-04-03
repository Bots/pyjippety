from __future__ import annotations

import logging
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

    def listen(self) -> str | None: ...


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


class CuePlayer(Protocol):
    def play_wake_cue(self) -> None: ...


class NullCuePlayer:
    def play_wake_cue(self) -> None:
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
    ) -> None:
        self.config = config
        self.detector = detector
        self.listener = listener
        self.responder = responder
        self.speaker = speaker
        self.cue_player = cue_player or NullCuePlayer()

    def handle_prompt(self, prompt: str) -> bool:
        LOGGER.info("Prompt: %s", prompt)
        if is_exit_command(prompt, self.config.exit_words):
            self.request_stop()
            LOGGER.info("Stop command received.")
            return False
        reply = self.responder.reply(prompt)
        self.speaker.say(reply)
        return True

    def request_stop(self) -> None:
        self.detector.request_stop()

    def run(self, once: bool = False) -> None:
        self.listener.calibrate()
        LOGGER.info("Listening for %s.", self.config.wake_word)
        try:
            while True:
                if not self.detector.wait_for_wake_word():
                    break
                self.cue_player.play_wake_cue()
                self.detector.pause()
                try:
                    prompt = self.listener.listen()
                finally:
                    self.detector.resume()
                if not prompt:
                    LOGGER.info("No prompt detected after wake word.")
                    if once:
                        break
                    continue

                keep_running = self.handle_prompt(prompt)
                if once or not keep_running:
                    break
        finally:
            self.detector.close()


__all__ = [
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
