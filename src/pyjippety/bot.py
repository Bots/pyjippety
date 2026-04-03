from __future__ import annotations

import argparse
import logging

from .config import AssistantConfig, env_file_path, load_environment
from .integrations import build_live_assistant, build_openai_client, build_speaker
from .runtime import DesktopAssistant, is_exit_command


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


__all__ = [
    "AssistantConfig",
    "DesktopAssistant",
    "build_live_assistant",
    "build_openai_client",
    "build_speaker",
    "env_file_path",
    "is_exit_command",
    "load_environment",
    "main",
    "parse_args",
]


if __name__ == "__main__":
    main()
