from __future__ import annotations

import datetime as dt
import webbrowser
from dataclasses import dataclass
from typing import Mapping

from .config import AssistantConfig


@dataclass(frozen=True)
class ActionResult:
    handled: bool
    message: str = ""
    side_effect: bool = False
    history_label: str | None = None


def maybe_run_action(prompt: str, config: AssistantConfig) -> ActionResult:
    lowered = prompt.strip().lower()

    if lowered in {"what time is it", "what's the time", "tell me the time"}:
        return ActionResult(
            handled=True,
            message=f"It is {dt.datetime.now().strftime('%I:%M %p').lstrip('0')}.",
            history_label="time",
        )

    if lowered in {"what day is it", "what's the date", "tell me the date"}:
        return ActionResult(
            handled=True,
            message=dt.datetime.now().strftime("Today is %A, %B %d, %Y."),
            history_label="date",
        )

    if lowered in {"go to sleep", "sleep mode", "sleep"}:
        return ActionResult(
            handled=True,
            message="Okay. Going to sleep.",
            history_label="sleep",
        )

    if lowered.startswith("open website "):
        target = prompt.strip()[len("open website ") :].strip()
        if not target:
            return ActionResult(handled=True, message="Tell me which website to open.")
        url = target if target.startswith(("http://", "https://")) else f"https://{target}"
        if config.safe_tool_mode:
            return ActionResult(
                handled=True,
                message=f"Safe tool mode is on. I would open {url} after confirmation.",
                side_effect=True,
                history_label="open_website_blocked",
            )
        webbrowser.open(url)
        return ActionResult(
            handled=True,
            message=f"Opened {url}.",
            side_effect=True,
            history_label="open_website",
        )

    if lowered in {"help commands", "what can you do locally"}:
        return ActionResult(
            handled=True,
            message=(
                "Local actions: tell the time, tell the date, open website <url>, "
                "and go to sleep."
            ),
            history_label="help_commands",
        )

    return ActionResult(handled=False)


__all__ = ["ActionResult", "maybe_run_action"]
