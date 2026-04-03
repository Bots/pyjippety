# Project overview
- Purpose: desktop Python voice assistant that uses Porcupine for wake-word detection, OpenAI for prompt transcription and chat responses, and local text-to-speech for playback.
- Stack: Python 3.11+, OpenAI Python SDK, pvporcupine, pvrecorder, SpeechRecognition, PyAudio, pyttsx3, python-dotenv.
- Layout: `src/pc_siri/` contains the package and CLI entrypoint, `tests/` contains stdlib unittest coverage, `README.md` documents setup and runtime configuration, `.env.example` lists required environment variables.
- Runtime shape: wait for Porcupine wake word, record one follow-up prompt, transcribe with OpenAI, answer with Responses API, speak locally, then return to waiting.