from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
APP_NAME = "PyJippety"
PACKAGE_NAME = "pyjippety"


def user_data_dir() -> Path:
    system = platform.system()
    if system == "Windows":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / APP_NAME
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / PACKAGE_NAME


def user_config_dir() -> Path:
    system = platform.system()
    if system == "Windows":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP_NAME
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / PACKAGE_NAME


def launcher_dir() -> Path:
    system = platform.system()
    if system == "Windows":
        return user_data_dir()
    if system == "Darwin":
        return Path.home() / "Applications"
    return Path.home() / ".local" / "bin"


def ensure_tk() -> None:
    try:
        import tkinter  # noqa: F401
    except Exception as exc:
        system = platform.system()
        if system == "Windows":
            hint = "Install a standard Python.org build with Tk included."
        elif system == "Darwin":
            hint = "Use a Python build with Tk support, such as the Python.org installer."
        else:
            hint = "Install python3-tk with your package manager and rerun the installer."
        raise SystemExit(f"Tkinter is missing. {hint}") from exc


def write_launcher(venv_dir: Path, config_file: Path) -> Path:
    scripts_dir = venv_dir / ("Scripts" if platform.system() == "Windows" else "bin")
    launchers = launcher_dir()
    launchers.mkdir(parents=True, exist_ok=True)

    if platform.system() == "Windows":
        target = scripts_dir / "pyjippety-ui.exe"
        if not target.exists():
            target = scripts_dir / "pyjippety-ui"
        launcher = launchers / f"{APP_NAME}.cmd"
        launcher.write_text(
            f'@echo off\nset "PYJIPPETY_ENV_FILE={config_file}"\n"{target}" %*\n',
            encoding="utf-8",
        )
        return launcher

    target = scripts_dir / "pyjippety-ui"
    suffix = ".command" if platform.system() == "Darwin" else ""
    launcher = launchers / f"{APP_NAME}{suffix if suffix else ''}"
    launcher.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f'export PYJIPPETY_ENV_FILE="{config_file}"\n'
        f'exec "{target}" "$@"\n',
        encoding="utf-8",
    )
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return launcher


def write_linux_desktop_entry(launcher: Path, icon_path: Path) -> Path:
    desktop_dir = Path.home() / ".local" / "share" / "applications"
    desktop_dir.mkdir(parents=True, exist_ok=True)
    desktop_path = desktop_dir / "pyjippety.desktop"
    desktop_path.write_text(
        "[Desktop Entry]\n"
        "Version=1.0\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        "Comment=Desktop voice assistant\n"
        f"Exec={launcher}\n"
        f"Icon={icon_path}\n"
        "Terminal=false\n"
        "Categories=Utility;\n",
        encoding="utf-8",
    )
    return desktop_path


def main() -> None:
    ensure_tk()
    python = Path(sys.executable)
    app_home = user_data_dir()
    config_home = user_config_dir()
    venv_dir = app_home / "venv"
    config_file = config_home / ".env"
    icon_path = app_home / "pyjippety-logo.png"

    app_home.mkdir(parents=True, exist_ok=True)
    config_home.mkdir(parents=True, exist_ok=True)

    subprocess.run([str(python), "-m", "venv", str(venv_dir)], check=True)
    scripts_dir = venv_dir / ("Scripts" if platform.system() == "Windows" else "bin")
    vpython = scripts_dir / ("python.exe" if platform.system() == "Windows" else "python")
    subprocess.run([str(vpython), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], check=True)
    subprocess.run([str(vpython), "-m", "pip", "install", str(PROJECT_DIR)], check=True)

    if not config_file.exists():
        shutil.copyfile(PROJECT_DIR / ".env.example", config_file)
    shutil.copyfile(PROJECT_DIR / "assets" / "pyjippety-logo.png", icon_path)

    launcher = write_launcher(venv_dir, config_file)
    desktop_path = write_linux_desktop_entry(launcher, icon_path) if platform.system() == "Linux" else None

    print()
    print(f"{APP_NAME} is installed.")
    print(f"Launcher: {launcher}")
    if desktop_path is not None:
        print(f"Desktop entry: {desktop_path}")
    print(f"Icon: {icon_path}")
    print(f"Config file: {config_file}")
    print()
    print("Next steps:")
    print(f"1. Launch {APP_NAME} from your applications menu or by running: {launcher}")
    print("2. Open the Setup tab and add your OpenAI and Picovoice keys.")


if __name__ == "__main__":
    main()
