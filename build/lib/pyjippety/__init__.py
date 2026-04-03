"""Desktop voice assistant package."""

from importlib import import_module

__all__ = ["AssistantConfig", "DesktopAssistant", "is_exit_command"]


def __getattr__(name: str):
    if name in __all__:
        module = import_module(".bot", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
