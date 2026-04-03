from __future__ import annotations

import argparse
import io
import logging
import os
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol


LOGGER = logging.getLogger(__name__)
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


def load_environment() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    for path in candidate_env_paths():
        if path.exists():
            load_dotenv(path, override=True)


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
    paths = [config_path, env_file_path()]
    return tuple(paths)


def normalize_text(text: str) -> str:
    return " ".join(text.lower().strip().split())


def is_exit_command(text: str, exit_words: tuple[str, ...]) -> bool:
    normalized = normalize_text(text)
    return normalized in exit_words


def audio_to_wav_buffer(audio: Any) -> io.BytesIO:
    buffer = io.BytesIO(audio.get_wav_data())
    buffer.name = "microphone.wav"
    buffer.seek(0)
    return buffer


class DesktopAssistant:
    def __init__(
        self,
        config: AssistantConfig,
        detector: WakeWordDetector,
        listener: TranscriptListener,
        responder: Responder,
        speaker: Speaker,
    ) -> None:
        self.config = config
        self.detector = detector
        self.listener = listener
        self.responder = responder
        self.speaker = speaker

    def handle_prompt(self, prompt: str) -> bool:
        LOGGER.info("Prompt: %s", prompt)
        if is_exit_command(prompt, self.config.exit_words):
            self.request_stop()
            self.speaker.say("Stopping.")
            return False
        reply = self.responder.reply(prompt)
        self.speaker.say(reply)
        return True

    def request_stop(self) -> None:
        self.detector.request_stop()

    def run(self, once: bool = False) -> None:
        self.listener.calibrate()
        self.speaker.say(f"Listening for {self.config.wake_word}.")
        try:
            while True:
                if not self.detector.wait_for_wake_word():
                    break
                self.speaker.say("Yes?")
                self.detector.pause()
                try:
                    prompt = self.listener.listen()
                finally:
                    self.detector.resume()
                if not prompt:
                    self.speaker.say("I did not catch that.")
                    if once:
                        break
                    continue

                keep_running = self.handle_prompt(prompt)
                if once or not keep_running:
                    break
        finally:
            self.detector.close()


class ConsoleSpeaker:
    def say(self, text: str) -> None:
        LOGGER.info("Assistant: %s", text)
        print(f"Assistant: {text}")


class OpenAIResponder:
    def __init__(self, client: Any, config: AssistantConfig) -> None:
        self.client = client
        self.config = config

    def reply(self, prompt: str) -> str:
        response = self.client.responses.create(
            model=self.config.chat_model,
            instructions=self.config.system_prompt,
            input=prompt,
        )
        text = getattr(response, "output_text", "").strip()
        if text:
            return text
        return "I did not get a response back from the model."


class OpenAITranscribingListener:
    def __init__(self, client: Any, config: AssistantConfig) -> None:
        import speech_recognition as sr

        self.client = client
        self.config = config
        self.sr = sr
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = config.energy_threshold
        self.recognizer.dynamic_energy_threshold = True
        self.microphone = sr.Microphone(device_index=config.audio_device_index)

    def calibrate(self) -> None:
        LOGGER.info("Calibrating microphone for ambient noise.")
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(
                source, duration=self.config.ambient_adjust_seconds
            )

    def listen(self) -> str | None:
        try:
            with self.microphone as source:
                audio = self.recognizer.listen(
                    source,
                    timeout=self.config.listen_timeout,
                    phrase_time_limit=self.config.phrase_time_limit,
                )
        except self.sr.WaitTimeoutError:
            return None

        last_error: Exception | None = None
        for model in self._candidate_models():
            try:
                transcript = self.client.audio.transcriptions.create(
                    model=model,
                    file=audio_to_wav_buffer(audio),
                )
                text = getattr(transcript, "text", "").strip()
                if text:
                    return text
                return None
            except Exception as exc:
                last_error = exc
                LOGGER.warning("Transcription request failed for model %s: %s", model, exc)

        if last_error is not None:
            raise RuntimeError(
                "No accessible transcription model was available. "
                f"Tried: {', '.join(self._candidate_models())}"
            ) from last_error
        return None

    def _candidate_models(self) -> tuple[str, ...]:
        return unique_nonempty(
            [self.config.transcription_model, *self.config.transcription_fallback_models]
        )


class PorcupineWakeWordDetector:
    def __init__(self, access_key: str, config: AssistantConfig) -> None:
        import pvporcupine
        from pvrecorder import PvRecorder

        porcupine_args: dict[str, Any] = {"access_key": access_key}
        if config.porcupine_keyword_path:
            porcupine_args["keyword_paths"] = [config.porcupine_keyword_path]
        else:
            porcupine_args["keywords"] = [config.porcupine_keyword or "porcupine"]

        self.porcupine = pvporcupine.create(**porcupine_args)
        recorder_args: dict[str, Any] = {
            "frame_length": self.porcupine.frame_length,
        }
        if config.audio_device_index is not None:
            recorder_args["device_index"] = config.audio_device_index

        self.recorder = PvRecorder(**recorder_args)
        self._stop_requested = False
        self.recorder.start()

    def wait_for_wake_word(self) -> bool:
        while not self._stop_requested:
            frame = self.recorder.read()
            if self.porcupine.process(frame) >= 0:
                LOGGER.info("Wake word detected.")
                return True
        return False

    def pause(self) -> None:
        if not self._stop_requested:
            self.recorder.stop()

    def resume(self) -> None:
        if not self._stop_requested:
            self.recorder.start()

    def request_stop(self) -> None:
        self._stop_requested = True

    def close(self) -> None:
        if hasattr(self, "recorder"):
            try:
                self.recorder.stop()
            except Exception:
                pass
            self.recorder.delete()
        if hasattr(self, "porcupine"):
            self.porcupine.delete()


class OpenAISpeaker:
    def __init__(self, client: Any, config: AssistantConfig) -> None:
        import pyaudio

        self.client = client
        self.config = config
        self.pyaudio = pyaudio
        self.disabled = False

    def say(self, text: str) -> None:
        LOGGER.info("Assistant: %s", text)
        if self.disabled:
            print(f"Assistant: {text}")
            return

        last_error: Exception | None = None
        for model in self._candidate_models():
            try:
                self._speak_with_model(model, text)
                return
            except Exception as exc:
                last_error = exc
                LOGGER.warning("TTS request failed for model %s: %s", model, exc)

        self.disabled = True
        LOGGER.warning(
            "Disabling TTS after repeated failures; falling back to console output."
        )
        if last_error is not None:
            LOGGER.warning("Last TTS error: %s", last_error)
        print(f"Assistant: {text}")

    def _candidate_models(self) -> tuple[str, ...]:
        return unique_nonempty([self.config.tts_model, *self.config.tts_fallback_models])

    def _speak_with_model(self, model: str, text: str) -> None:
        with tempfile.NamedTemporaryFile(suffix=".wav") as temp_file:
            with self.client.audio.speech.with_streaming_response.create(
                model=model,
                voice=self.config.tts_voice,
                input=text,
                instructions=self.config.tts_instructions,
                response_format="wav",
                speed=self.config.tts_speed,
            ) as response:
                response.stream_to_file(temp_file.name)

            self._play_wav_file(temp_file.name)

    def _play_wav_file(self, path: str) -> None:
        pa = self.pyaudio.PyAudio()
        try:
            with wave.open(path, "rb") as wav_file:
                stream = pa.open(
                    format=pa.get_format_from_width(wav_file.getsampwidth()),
                    channels=wav_file.getnchannels(),
                    rate=wav_file.getframerate(),
                    output=True,
                )
                try:
                    chunk = 4096
                    data = wav_file.readframes(chunk)
                    while data:
                        stream.write(data)
                        data = wav_file.readframes(chunk)
                finally:
                    stream.stop_stream()
                    stream.close()
        finally:
            pa.terminate()


def build_speaker(client: Any, config: AssistantConfig) -> Speaker:
    if not config.tts_enabled:
        LOGGER.warning("TTS disabled by configuration; using console output only.")
        return ConsoleSpeaker()

    try:
        return OpenAISpeaker(client, config)
    except Exception as exc:
        LOGGER.warning(
            "TTS initialization failed (%s). Falling back to console output only.",
            exc,
        )
        return ConsoleSpeaker()


def build_openai_client(environment: Mapping[str, str] | None = None) -> Any:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "The openai package is not installed. Run `pip install -e .` first."
        ) from exc

    environment = environment or os.environ
    api_key = environment.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    return OpenAI(api_key=api_key)


def build_live_assistant(
    config: AssistantConfig, environment: Mapping[str, str] | None = None
) -> DesktopAssistant:
    environment = environment or os.environ
    picovoice_access_key = environment.get("PICOVOICE_ACCESS_KEY")
    if not picovoice_access_key:
        raise RuntimeError("PICOVOICE_ACCESS_KEY is not set.")

    client = build_openai_client(environment)
    return DesktopAssistant(
        config=config,
        detector=PorcupineWakeWordDetector(picovoice_access_key, config),
        listener=OpenAITranscribingListener(client, config),
        responder=OpenAIResponder(client, config),
        speaker=build_speaker(client, config),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Wake-word desktop voice assistant")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process a single utterance and exit.",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_environment()
    args = parse_args()
    config = AssistantConfig.from_env()
    assistant = build_live_assistant(config)
    assistant.run(once=args.once)


if __name__ == "__main__":
    main()
