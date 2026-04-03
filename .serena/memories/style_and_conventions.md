# Style and conventions
- Keep the codebase small and dependency-light; avoid new dependencies unless directly required by the voice pipeline.
- Use type hints and dataclasses for configuration/state.
- Separate hardware/runtime adapters from core orchestration logic so unit tests can use fakes.
- Prefer stdlib `unittest` for lightweight tests in this repo.
- Keep comments sparse and only where behavior would otherwise be unclear.