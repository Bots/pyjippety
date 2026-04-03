from __future__ import annotations

import datetime as dt
import webbrowser
from dataclasses import dataclass
from typing import Callable

from .config import AssistantConfig


@dataclass(frozen=True)
class ActionResult:
    handled: bool
    message: str = ""
    side_effect: bool = False
    history_label: str | None = None


@dataclass(frozen=True)
class ActionDefinition:
    name: str
    matcher: Callable[[str], bool]
    handler: Callable[[str, AssistantConfig], ActionResult]


def _time_action(_: str, __: AssistantConfig) -> ActionResult:
    return ActionResult(
        handled=True,
        message=f"It is {dt.datetime.now().strftime('%I:%M %p').lstrip('0')}.",
        history_label="time",
    )


def _date_action(_: str, __: AssistantConfig) -> ActionResult:
    return ActionResult(
        handled=True,
        message=dt.datetime.now().strftime("Today is %A, %B %d, %Y."),
        history_label="date",
    )


def _sleep_action(_: str, __: AssistantConfig) -> ActionResult:
    return ActionResult(
        handled=True,
        message="Okay. Going to sleep.",
        history_label="sleep",
    )


def _open_website_action(prompt: str, config: AssistantConfig) -> ActionResult:
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


def _help_action(_: str, __: AssistantConfig) -> ActionResult:
    return ActionResult(
        handled=True,
        message=(
            "Local actions: tell the time, tell the date, open website <url>, "
            "and go to sleep."
        ),
        history_label="help_commands",
    )


ACTION_REGISTRY: tuple[ActionDefinition, ...] = (
    ActionDefinition(
        name="time",
        matcher=lambda text: text in {"what time is it", "what's the time", "tell me the time"},
        handler=_time_action,
    ),
    ActionDefinition(
        name="date",
        matcher=lambda text: text in {"what day is it", "what's the date", "tell me the date"},
        handler=_date_action,
    ),
    ActionDefinition(
        name="sleep",
        matcher=lambda text: text in {"go to sleep", "sleep mode", "sleep"},
        handler=_sleep_action,
    ),
    ActionDefinition(
        name="open_website",
        matcher=lambda text: text.startswith("open website "),
        handler=_open_website_action,
    ),
    ActionDefinition(
        name="help_commands",
        matcher=lambda text: text in {"help commands", "what can you do locally"},
        handler=_help_action,
    ),
)


def maybe_run_action(prompt: str, config: AssistantConfig) -> ActionResult:
    lowered = prompt.strip().lower()
    for action in ACTION_REGISTRY:
        if action.matcher(lowered):
            return action.handler(prompt, config)
    return ActionResult(handled=False)


__all__ = ["ACTION_REGISTRY", "ActionDefinition", "ActionResult", "maybe_run_action"]
