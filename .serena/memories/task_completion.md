# Task completion checklist
- Run `PYTHONPATH=src python -m unittest discover -s tests`.
- Run `python -m compileall src tests`.
- If dependencies are installed locally, do a manual microphone smoke test with `pc-siri --once` after setting `.env`.
- Report any remaining environment prerequisites explicitly, especially OpenAI and Picovoice credentials plus audio system packages.