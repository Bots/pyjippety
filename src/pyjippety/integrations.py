from __future__ import annotations

import io
import logging
import math
import os
import struct
import tempfile
import threading
import wave
from contextlib import contextmanager
from typing import Any, Mapping

from .actions import maybe_run_action
from .config import AssistantConfig, unique_nonempty
from .memory import MemoryAwareResponder, build_memory_store
from .runtime import AssistantEvents, DesktopAssistant, Speaker


LOGGER = logging.getLogger(__name__)


@contextmanager
def _suppress_stderr_fd() -> Any:
    """Temporarily silence native library stderr noise during audio probing."""
    stderr_fd = None
    saved_fd = None
    devnull_fd = None
    try:
        stderr_fd = os.dup(2)
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull_fd, 2)
        yield
    finally:
        if stderr_fd is not None:
            os.dup2(stderr_fd, 2)
            os.close(stderr_fd)
        if devnull_fd is not None:
            os.close(devnull_fd)


def audio_to_wav_buffer(audio: Any) -> io.BytesIO:
    buffer = io.BytesIO(audio.get_wav_data())
    buffer.name = "microphone.wav"
    buffer.seek(0)
    return buffer


class ConsoleSpeaker:
    def say(self, text: str) -> None:
        LOGGER.info("Assistant: %s", text)
        print(f"Assistant: {text}")

    def interrupt(self) -> None:
        return


class OpenAIResponder:
    def __init__(self, client: Any, config: AssistantConfig) -> None:
        self.client = client
        self.config = config

    def reply(self, prompt: str) -> str:
        action_result = maybe_run_action(prompt, self.config)
        if action_result.handled:
            return action_result.message
        instructions = self.config.system_prompt
        if self.config.low_verbosity:
            instructions = (
                f"{instructions}\n\nKeep responses brief unless the user explicitly asks for detail."
            )
        response = self.client.responses.create(
            model=self.config.chat_model,
            instructions=instructions,
            input=prompt,
        )
        text = getattr(response, "output_text", "").strip()
        if text:
            return text
        return "I did not get a response back from the model."

    def stream_reply(self, prompt: str, on_text: Any) -> str:
        action_result = maybe_run_action(prompt, self.config)
        if action_result.handled:
            if action_result.message:
                on_text(action_result.message)
            return action_result.message
        instructions = self.config.system_prompt
        if self.config.low_verbosity:
            instructions = (
                f"{instructions}\n\nKeep responses brief unless the user explicitly asks for detail."
            )

        chunks: list[str] = []
        with self.client.responses.stream(
            model=self.config.chat_model,
            instructions=instructions,
            input=prompt,
        ) as stream:
            for event in stream:
                event_type = getattr(event, "type", "")
                if event_type == "response.output_text.delta":
                    delta = getattr(event, "delta", "")
                    if delta:
                        chunks.append(delta)
                        on_text(delta)
            stream.get_final_response()
        return "".join(chunks).strip() or "I did not get a response back from the model."


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

    def listen(
        self, *, timeout: float | None = None, phrase_time_limit: float | None = None
    ) -> str | None:
        try:
            with self.microphone as source:
                audio = self.recognizer.listen(
                    source,
                    timeout=timeout if timeout is not None else self.config.listen_timeout,
                    phrase_time_limit=(
                        phrase_time_limit
                        if phrase_time_limit is not None
                        else self.config.phrase_time_limit
                    ),
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
        recorder_args: dict[str, Any] = {"frame_length": self.porcupine.frame_length}
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
        self.player = LocalAudioPlayer(self.pyaudio)

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
        request_args = {
            "model": model,
            "voice": self.config.tts_voice,
            "input": text,
            "response_format": "wav",
            "speed": self.config.tts_speed,
        }
        if self.config.tts_instructions is not None:
            request_args["instructions"] = self.config.tts_instructions

        with tempfile.NamedTemporaryFile(suffix=".wav") as temp_file:
            with self.client.audio.speech.with_streaming_response.create(
                **request_args
            ) as response:
                response.stream_to_file(temp_file.name)

            self._play_wav_file(temp_file.name)

    def _play_wav_file(self, path: str) -> None:
        with wave.open(path, "rb") as wav_file:
            self.player.play_wav_stream(
                channels=wav_file.getnchannels(),
                sample_width=wav_file.getsampwidth(),
                sample_rate=wav_file.getframerate(),
                frames=_read_wav_frames(wav_file),
            )

    def interrupt(self) -> None:
        self.player.interrupt()


class LocalAudioPlayer:
    def __init__(self, pyaudio_module: Any | None = None) -> None:
        if pyaudio_module is None:
            import pyaudio as pyaudio_module

        self.pyaudio = pyaudio_module
        self._stream = None
        self._lock = threading.Lock()
        self._stop_requested = False

    def play_wav_stream(
        self,
        *,
        channels: int,
        sample_width: int,
        sample_rate: int,
        frames: bytes,
    ) -> None:
        self._stop_requested = False
        pa = self.pyaudio.PyAudio()
        try:
            stream = pa.open(
                format=pa.get_format_from_width(sample_width),
                channels=channels,
                rate=sample_rate,
                output=True,
            )
            try:
                with self._lock:
                    self._stream = stream
                chunk = 4096
                offset = 0
                while offset < len(frames):
                    if self._stop_requested:
                        break
                    next_offset = min(offset + chunk, len(frames))
                    stream.write(frames[offset:next_offset])
                    offset = next_offset
            finally:
                with self._lock:
                    self._stream = None
                stream.stop_stream()
                stream.close()
        finally:
            pa.terminate()

    def interrupt(self) -> None:
        self._stop_requested = True
        with self._lock:
            if self._stream is not None:
                try:
                    self._stream.stop_stream()
                except Exception:
                    pass


def _read_wav_frames(wav_file: wave.Wave_read) -> bytes:
    chunks: list[bytes] = []
    block_size = 4096
    data = wav_file.readframes(block_size)
    while data:
        chunks.append(data)
        data = wav_file.readframes(block_size)
    return b"".join(chunks)


class WakeChimePlayer:
    def __init__(self, volume: float = 1.0) -> None:
        self.player = LocalAudioPlayer()
        self._frames = generate_wake_chime(volume)

    def play_wake_cue(self) -> None:
        try:
            self.player.play_wav_stream(
                channels=1,
                sample_width=2,
                sample_rate=24000,
                frames=self._frames,
            )
        except Exception as exc:
            LOGGER.warning("Wake chime playback failed: %s", exc)


def generate_wake_chime(volume: float = 1.0) -> bytes:
    sample_rate = 24000
    amplitude = max(0.0, min(volume, 2.0)) * 0.2
    frequencies = (720.0, 540.0)
    segment_duration = 0.11
    gap_duration = 0.012
    frames = bytearray()

    def append_tone(frequency: float, duration: float) -> None:
        total_samples = int(sample_rate * duration)
        for index in range(total_samples):
            progress = index / max(total_samples - 1, 1)
            envelope = min(progress * 4.5, 1.0) * min((1.0 - progress) * 4.0, 1.0)
            sample = amplitude * envelope * math.sin(
                2 * math.pi * frequency * (index / sample_rate)
            )
            frames.extend(struct.pack("<h", int(sample * 32767)))

    def append_silence(duration: float) -> None:
        frames.extend(b"\x00\x00" * int(sample_rate * duration))

    append_tone(frequencies[0], segment_duration)
    append_silence(gap_duration)
    append_tone(frequencies[1], segment_duration)
    return bytes(frames)


def build_speaker(client: Any, config: AssistantConfig) -> Speaker:
    if not config.tts_enabled or config.mute_speech:
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


def list_microphones() -> list[tuple[int, str]]:
    try:
        import speech_recognition as sr
    except ImportError:
        return []
    try:
        with _suppress_stderr_fd():
            names = sr.Microphone.list_microphone_names()
    except Exception:
        return []
    return list(enumerate(names))


def build_live_assistant(
    config: AssistantConfig,
    environment: Mapping[str, str] | None = None,
    events: AssistantEvents | None = None,
) -> DesktopAssistant:
    environment = environment or os.environ
    picovoice_access_key = environment.get("PICOVOICE_ACCESS_KEY")
    if not picovoice_access_key:
        raise RuntimeError("PICOVOICE_ACCESS_KEY is not set.")

    client = build_openai_client(environment)
    memory_store = build_memory_store(config, environment)
    return DesktopAssistant(
        config=config,
        detector=PorcupineWakeWordDetector(picovoice_access_key, config),
        listener=OpenAITranscribingListener(client, config),
        responder=MemoryAwareResponder(OpenAIResponder(client, config), memory_store),
        speaker=build_speaker(client, config),
        cue_player=WakeChimePlayer(config.chime_volume),
        events=events,
    )


__all__ = [
    "ConsoleSpeaker",
    "LocalAudioPlayer",
    "MemoryAwareResponder",
    "OpenAIResponder",
    "OpenAISpeaker",
    "OpenAITranscribingListener",
    "PorcupineWakeWordDetector",
    "WakeChimePlayer",
    "audio_to_wav_buffer",
    "build_live_assistant",
    "build_openai_client",
    "build_speaker",
    "generate_wake_chime",
]
