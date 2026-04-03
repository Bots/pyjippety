import unittest

from pyjippety.bot import AssistantConfig, DesktopAssistant, is_exit_command


class FakeListener:
    def __init__(self, transcripts):
        self.transcripts = list(transcripts)
        self.calibrated = False

    def calibrate(self):
        self.calibrated = True

    def listen(self):
        if not self.transcripts:
            return None
        return self.transcripts.pop(0)


class FakeDetector:
    def __init__(self, wakeups=1):
        self.wakeups = wakeups
        self.calls = 0
        self.closed = False
        self.paused = 0
        self.resumed = 0
        self.stop_requested = 0

    def wait_for_wake_word(self):
        if self.calls >= self.wakeups:
            raise AssertionError("wait_for_wake_word called too many times")
        self.calls += 1
        return True

    def pause(self):
        self.paused += 1

    def resume(self):
        self.resumed += 1

    def request_stop(self):
        self.stop_requested += 1

    def close(self):
        self.closed = True


class FakeResponder:
    def __init__(self):
        self.prompts = []

    def reply(self, prompt):
        self.prompts.append(prompt)
        return f"echo:{prompt}"


class FakeSpeaker:
    def __init__(self):
        self.messages = []

    def say(self, text):
        self.messages.append(text)


class FakeCuePlayer:
    def __init__(self):
        self.wake_cues = 0

    def play_wake_cue(self):
        self.wake_cues += 1


class HelperTests(unittest.TestCase):
    def test_is_exit_command_normalizes_whitespace(self):
        self.assertTrue(
            is_exit_command("  Stop   Listening ", ("stop listening", "quit assistant"))
        )

    def test_config_round_trips_through_mapping(self):
        values = {
            "ASSISTANT_WAKE_WORD": "computer",
            "ASSISTANT_PORCUPINE_KEYWORD": "jarvis",
            "ASSISTANT_CHAT_MODEL": "gpt-4o-mini",
            "ASSISTANT_TRANSCRIPTION_MODEL": "whisper-1",
            "ASSISTANT_TRANSCRIPTION_FALLBACK_MODELS": "gpt-4o-transcribe, whisper-1",
            "ASSISTANT_SYSTEM_PROMPT": "Be brief",
            "ASSISTANT_LISTEN_TIMEOUT": "7",
            "ASSISTANT_PHRASE_TIME_LIMIT": "11",
            "ASSISTANT_TTS_ENABLED": "false",
            "ASSISTANT_TTS_MODEL": "tts-1",
            "ASSISTANT_TTS_FALLBACK_MODELS": "tts-1-hd",
            "ASSISTANT_TTS_VOICE": "alloy",
            "ASSISTANT_TTS_SPEED": "1.25",
            "ASSISTANT_TTS_INSTRUCTIONS": "Warm tone",
            "ASSISTANT_ENERGY_THRESHOLD": "450",
            "ASSISTANT_AMBIENT_ADJUST_SECONDS": "2.5",
            "ASSISTANT_AUDIO_DEVICE_INDEX": "3",
            "ASSISTANT_EXIT_WORDS": "Stop Listening, Quit Assistant",
        }

        config = AssistantConfig.from_mapping(values)
        round_trip = config.to_env_mapping()

        self.assertEqual(config.wake_word, "computer")
        self.assertEqual(config.transcription_fallback_models, ("gpt-4o-transcribe", "whisper-1"))
        self.assertFalse(config.tts_enabled)
        self.assertEqual(config.audio_device_index, 3)
        self.assertEqual(config.exit_words, ("stop listening", "quit assistant"))
        self.assertEqual(round_trip["ASSISTANT_WAKE_WORD"], "computer")
        self.assertEqual(round_trip["ASSISTANT_TTS_ENABLED"], "false")
        self.assertEqual(round_trip["ASSISTANT_AUDIO_DEVICE_INDEX"], "3")


class DesktopAssistantTests(unittest.TestCase):
    def test_handle_prompt_passes_prompt_to_responder(self):
        detector = FakeDetector()
        listener = FakeListener([])
        responder = FakeResponder()
        speaker = FakeSpeaker()
        cue_player = FakeCuePlayer()
        assistant = DesktopAssistant(
            AssistantConfig(), detector, listener, responder, speaker, cue_player
        )

        keep_running = assistant.handle_prompt("open my calendar")

        self.assertTrue(keep_running)
        self.assertEqual(responder.prompts, ["open my calendar"])
        self.assertEqual(speaker.messages, ["echo:open my calendar"])

    def test_handle_prompt_stops_on_exit_command(self):
        detector = FakeDetector()
        listener = FakeListener([])
        responder = FakeResponder()
        speaker = FakeSpeaker()
        cue_player = FakeCuePlayer()
        assistant = DesktopAssistant(
            AssistantConfig(), detector, listener, responder, speaker, cue_player
        )

        keep_running = assistant.handle_prompt("stop listening")

        self.assertFalse(keep_running)
        self.assertEqual(detector.stop_requested, 1)
        self.assertEqual(responder.prompts, [])
        self.assertEqual(speaker.messages, [])

    def test_run_waits_for_wake_word_then_processes_prompt(self):
        detector = FakeDetector()
        listener = FakeListener(["say hello"])
        responder = FakeResponder()
        speaker = FakeSpeaker()
        cue_player = FakeCuePlayer()
        assistant = DesktopAssistant(
            AssistantConfig(), detector, listener, responder, speaker, cue_player
        )

        assistant.run(once=True)

        self.assertTrue(listener.calibrated)
        self.assertEqual(detector.calls, 1)
        self.assertEqual(detector.paused, 1)
        self.assertEqual(detector.resumed, 1)
        self.assertEqual(cue_player.wake_cues, 1)
        self.assertTrue(detector.closed)
        self.assertEqual(responder.prompts, ["say hello"])
        self.assertEqual(speaker.messages, ["echo:say hello"])

    def test_run_handles_missing_prompt_after_wake_word(self):
        detector = FakeDetector()
        listener = FakeListener([None])
        responder = FakeResponder()
        speaker = FakeSpeaker()
        cue_player = FakeCuePlayer()
        assistant = DesktopAssistant(
            AssistantConfig(), detector, listener, responder, speaker, cue_player
        )

        assistant.run(once=True)

        self.assertEqual(responder.prompts, [])
        self.assertEqual(detector.paused, 1)
        self.assertEqual(detector.resumed, 1)
        self.assertEqual(cue_player.wake_cues, 1)
        self.assertEqual(speaker.messages, [])


if __name__ == "__main__":
    unittest.main()
