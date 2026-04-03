from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable


class NullTrayManager:
    available = False

    def start(self) -> None:
        return

    def stop(self) -> None:
        return

    def update_status(self, status: str) -> None:
        return

    def notify_hidden(self) -> None:
        return


class TrayManager:
    available = True

    def __init__(
        self,
        *,
        icon_path: Path,
        on_show: Callable[[], None],
        on_hide: Callable[[], None],
        on_toggle_voice: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        import pystray
        from PIL import Image

        self.pystray = pystray
        self.Image = Image
        self.icon_path = icon_path
        self.on_show = on_show
        self.on_hide = on_hide
        self.on_toggle_voice = on_toggle_voice
        self.on_quit = on_quit
        self.status = "Idle"
        self.icon = pystray.Icon(
            "pyjippety",
            self.Image.open(icon_path),
            title=self._title(),
            menu=self._build_menu(),
        )
        self._thread: threading.Thread | None = None

    def _title(self) -> str:
        return f"PyJippety: {self.status}"

    def _build_menu(self) -> Any:
        Menu = self.pystray.Menu
        Item = self.pystray.MenuItem
        return Menu(
            Item("Show", lambda *_: self.on_show()),
            Item("Hide", lambda *_: self.on_hide()),
            Item("Start/Stop Voice", lambda *_: self.on_toggle_voice()),
            Item("Quit", lambda *_: self.on_quit()),
        )

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self.icon.run, name="pyjippety-tray", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        try:
            self.icon.stop()
        except Exception:
            pass

    def update_status(self, status: str) -> None:
        self.status = status
        self.icon.title = self._title()
        try:
            self.icon.update_menu()
        except Exception:
            pass

    def notify_hidden(self) -> None:
        try:
            self.icon.notify("PyJippety is still running in the background.", "PyJippety")
        except Exception:
            pass


def build_tray_manager(**kwargs: Any) -> TrayManager | NullTrayManager:
    try:
        return TrayManager(**kwargs)
    except Exception:
        return NullTrayManager()


__all__ = ["NullTrayManager", "TrayManager", "build_tray_manager"]
