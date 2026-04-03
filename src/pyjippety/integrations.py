from __future__ import annotations

import io
import logging
import math
import os
import struct
import tempfile
import wave
from typing import Any, Mapping

from .config import AssistantConfig, unique_nonempty
from .memory import MemoryAwareResponder, build_memory_store
from .runtime import DesktopAssistant, Speaker


LOGGER = logging.getLogger(__name__)


def audio_to_wav_buffer(audio: Any) -> io.BytesIO:
    buffer = io.BytesIO(audio.get_wav_data())
    buffer.name = "microphone.wav"
    buffer.seek(0)
    return buffer


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
        player = LocalAudioPlayer(self.pyaudio)
        with wave.open(path, "rb") as wav_file:
            player.play_wav_stream(
                channels=wav_file.getnchannels(),
                sample_width=wav_file.getsampwidth(),
                sample_rate=wav_file.getframerate(),
                frames=_read_wav_frames(wav_file),
            )


class LocalAudioPlayer:
    def __init__(self, pyaudio_module: Any | None = None) -> None:
        if pyaudio_module is None:
            import pyaudio as pyaudio_module

        self.pyaudio = pyaudio_module

    def play_wav_stream(
        self,
        *,
        channels: int,
        sample_width: int,
        sample_rate: int,
        frames: bytes,
    ) -> None:
        pa = self.pyaudio.PyAudio()
        try:
            stream = pa.open(
                format=pa.get_format_from_width(sample_width),
                channels=channels,
                rate=sample_rate,
                output=True,
            )
            try:
                stream.write(frames)
            finally:
                stream.stop_stream()
                stream.close()
        finally:
            pa.terminate()


def _read_wav_frames(wav_file: wave.Wave_read) -> bytes:
    chunks: list[bytes] = []
    block_size = 4096
    data = wav_file.readframes(block_size)
    while data:
        chunks.append(data)
        data = wav_file.readframes(block_size)
    return b"".join(chunks)


class WakeChimePlayer:
    def __init__(self) -> None:
        self.player = LocalAudioPlayer()
        self._frames = generate_wake_chime()

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


def generate_wake_chime() -> bytes:
    sample_rate = 24000
    amplitude = 0.24
    frequencies = (880.0, 1320.0)
    segment_duration = 0.085
    gap_duration = 0.018
    frames = bytearray()

    def append_tone(frequency: float, duration: float) -> None:
        total_samples = int(sample_rate * duration)
        for index in range(total_samples):
            progress = index / max(total_samples - 1, 1)
            envelope = min(progress * 6, 1.0) * min((1.0 - progress) * 7, 1.0)
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
    memory_store = build_memory_store(config, environment)
    return DesktopAssistant(
        config=config,
        detector=PorcupineWakeWordDetector(picovoice_access_key, config),
        listener=OpenAITranscribingListener(client, config),
        responder=MemoryAwareResponder(OpenAIResponder(client, config), memory_store),
        speaker=build_speaker(client, config),
        cue_player=WakeChimePlayer(),
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
