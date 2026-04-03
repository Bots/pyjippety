<p align="center">
  <img src="assets/pyjippety-logo.png" alt="PyJippety logo" width="132">
</p>

# PyJippety

`PyJippety` is a desktop voice assistant for Python.

It listens for a local wake word with Porcupine, records a follow-up prompt, sends that prompt to OpenAI for transcription and response generation, and can speak the answer back through OpenAI speech.

The project is built to work in two modes:

- normal desktop use through a small GUI
- developer use through a simple Python package and CLI

## What It Does

- local wake-word detection with Porcupine
- microphone capture for the spoken prompt
- OpenAI transcription with fallback model support
- OpenAI chat responses
- OpenAI speech output with fallback model support
- a local wake chime when the wake word is detected
- lightweight local memory for saved notes and recent exchanges
- local action plugins for simple desktop tasks
- desktop control panel for settings, profiles, logs, transcripts, typed testing, memory review, and history

## Desktop Install

For a normal Linux desktop install, run:

```bash
bash ./install-pyjippety.sh
```

The installer will:

- create an isolated app environment under `~/.local/share/pyjippety`
- create a persistent config file at `~/.config/pyjippety/.env`
- install a launcher at `~/.local/bin/pyjippety-ui`
- add a desktop entry so the app can appear in the applications menu

After install, open `PyJippety` from your applications menu or run:

```bash
~/.local/bin/pyjippety-ui
```

On Debian or Ubuntu, make sure the required system packages are installed first:

```bash
sudo apt update
sudo apt install portaudio19-dev python3-tk
```

## First Run

Open the app, go to the `Settings` tab, and fill in:

- `OpenAI API key`
- `Picovoice access key`

Then:

1. Save settings.
2. Start voice mode.
3. Say the wake word.
4. Speak your prompt.
5. If you want clarification, ask a quick follow-up right after the reply. You do not need the wake word again until the follow-up window closes.

If you want to test the assistant without using the wake word, use the typed request box in the `Workspace` tab.

Useful desktop shortcuts:

- `F8` toggles voice mode
- `Ctrl+Space` triggers push-to-talk
- `Escape` interrupts current output

The app keeps spoken output focused on actual replies. Wake-word detection uses a short local chime instead of speaking status messages back to you.

If you want the assistant to remember something, say or type:

```text
remember that I prefer short answers
```

You can also ask:

```text
what do you remember about me
```

## Developer Setup

If you want to run the project directly from source:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

You can also install from `requirements.txt`:

```bash
pip install -r requirements.txt
```

If you want a project-local config file during development:

```bash
cp .env.example .env
```

Run the desktop UI:

```bash
pyjippety-ui
```

Run the voice loop from the terminal:

```bash
pyjippety
```

Run one cycle only:

```bash
pyjippety --once
```

If you are running from source without installing entrypoints:

```bash
PYTHONPATH=src python -m pyjippety.gui
PYTHONPATH=src python -m pyjippety.bot
```

## How It Works

The runtime pipeline is intentionally simple:

1. Porcupine listens locally for a wake word.
2. Once triggered, the app records a single spoken prompt.
3. The prompt audio is sent to OpenAI transcription.
4. The transcript is sent to an OpenAI chat model.
5. The reply is spoken with OpenAI speech, or printed if speech is disabled or unavailable.
6. The app keeps listening for a small number of follow-up questions before returning to wake-word mode.

Wake-word detection stays on-device. The transcription, response, and speech steps use the OpenAI API.

The app also has lightweight local actions for requests such as checking the time, checking the date, opening a website, and going to sleep. When safe tool mode is enabled, side-effect actions stay blocked unless you turn that protection off.

## Interface

The desktop app is split into two focused areas:

- `Workspace`
  - start or stop voice mode
  - use push-to-talk
  - type requests directly
  - inspect and resend the last transcript
  - inspect live activity logs
- `Settings`
  - edit the common settings in a compact basic view
  - reveal model fallbacks, timing values, safe tool mode, idle timeout, memory limits, and prompt tuning through `Show advanced settings`
- `Memory`
  - review saved notes
  - edit those notes directly
  - inspect recent exchanges
- `History`
  - review prompts, responses, transcripts, and setup checks over time

The goal is to feel like a small desktop utility, not a chat dashboard.

## Configuration

Most users should manage settings from the desktop UI. The app writes them to:

```text
~/.config/pyjippety/.env
```

For manual editing, the main settings are:

- `OPENAI_API_KEY`
- `PICOVOICE_ACCESS_KEY`
- `ASSISTANT_WAKE_WORD`
- `ASSISTANT_PORCUPINE_KEYWORD`
- `ASSISTANT_PORCUPINE_KEYWORD_PATH`
- `ASSISTANT_CHAT_MODEL`
- `ASSISTANT_TRANSCRIPTION_MODEL`
- `ASSISTANT_TRANSCRIPTION_FALLBACK_MODELS`
- `ASSISTANT_TTS_ENABLED`
- `ASSISTANT_TTS_MODEL`
- `ASSISTANT_TTS_FALLBACK_MODELS`
- `ASSISTANT_TTS_VOICE`
- `ASSISTANT_TTS_SPEED`
- `ASSISTANT_SYSTEM_PROMPT`
- `ASSISTANT_TTS_INSTRUCTIONS`
- `ASSISTANT_MEMORY_ENABLED`
- `ASSISTANT_MEMORY_TURN_LIMIT`
- `ASSISTANT_MEMORY_FACT_LIMIT`
- `ASSISTANT_LISTEN_TIMEOUT`
- `ASSISTANT_PHRASE_TIME_LIMIT`
- `ASSISTANT_FOLLOW_UP_ENABLED`
- `ASSISTANT_FOLLOW_UP_TURN_LIMIT`
- `ASSISTANT_FOLLOW_UP_TIMEOUT`
- `ASSISTANT_SAFE_TOOL_MODE`
- `ASSISTANT_IDLE_TIMEOUT_SECONDS`
- `ASSISTANT_AMBIENT_ADJUST_SECONDS`
- `ASSISTANT_ENERGY_THRESHOLD`
- `ASSISTANT_AUDIO_DEVICE_INDEX`
- `ASSISTANT_EXIT_WORDS`

Notes:

- If you use a custom wake word such as `computer`, point `ASSISTANT_PORCUPINE_KEYWORD_PATH` to a Picovoice `.ppn` file.
- If your OpenAI project cannot access the default transcription or speech models, the app will try configured fallback models.
- If speech is disabled or all speech models fail, replies stay visible in the UI log.
- Memory is stored locally in the user config area and reused as context for later prompts when memory is enabled.
- Profiles store their own settings, memory file, and action history under `~/.config/pyjippety/profiles/<profile-name>/`.
- Idle timeout stops voice mode after inactivity and puts the app into a sleeping state until you start it again.

## Bundle for Distribution

To build a redistributable desktop bundle:

```bash
bash ./build-pyjippety-bundle.sh
```

This uses PyInstaller in one-folder mode and writes the output to:

```text
dist/pyjippety
```

## Testing

```bash
PYTHONPATH=src python -m unittest discover -s tests
python -m compileall src tests
```

## Troubleshooting

### ALSA warnings on Linux

Some Linux systems print ALSA warnings even when the app still works. These messages are often noisy rather than fatal.

### OpenAI model access errors

If you see `403 Forbidden` or `model_not_found`, your OpenAI project likely does not have access to the configured model. Change the primary model in the UI or set a compatible fallback list.

### No spoken output

If speech fails, the app will fall back to text output in the log. Check the speech model settings and your OpenAI project access.

### Wake word does not trigger

Check:

- your Picovoice access key
- the chosen built-in keyword
- the custom `.ppn` path if you are using one
- your microphone device selection

## Project Layout

```text
src/pyjippety/
  bot.py            CLI entrypoint
  actions.py        lightweight local command plugins
  config.py         config parsing and env loading
  memory.py         local memory storage and memory-aware prompting
  runtime.py        assistant orchestration
  integrations.py   OpenAI, Porcupine, audio, and wake chime adapters
  gui.py            desktop frontend
tests/
  test_bot.py       assistant loop tests
  test_memory.py    memory behavior tests
install-pyjippety.sh
build-pyjippety-bundle.sh
```

## Current Scope

This is a phrase-based assistant, not a full duplex realtime conversation agent.

That keeps the app simpler to install, easier to reason about, and easier to package as a desktop utility.
