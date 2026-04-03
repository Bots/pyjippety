from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
VENV_DIR = PROJECT_DIR / ".venv"


def main() -> None:
    scripts_dir = VENV_DIR / ("Scripts" if platform.system() == "Windows" else "bin")
    python = scripts_dir / ("python.exe" if platform.system() == "Windows" else "python")
    if not python.exists():
        raise SystemExit(f"Expected a virtual environment at {VENV_DIR}. Create it first, then rerun.")

    subprocess.run([str(python), "-m", "pip", "install", "--upgrade", "pyinstaller"], check=True)
    pyinstaller = scripts_dir / ("pyinstaller.exe" if platform.system() == "Windows" else "pyinstaller")
    separator = ";" if platform.system() == "Windows" else ":"
    subprocess.run(
        [
            str(pyinstaller),
            "--noconfirm",
            "--clean",
            "--windowed",
            "--onedir",
            "--name",
            "pyjippety",
            "--paths",
            str(PROJECT_DIR / "src"),
            "--add-data",
            f"{PROJECT_DIR / 'assets'}{separator}assets",
            str(PROJECT_DIR / "src" / "pyjippety" / "gui.py"),
        ],
        check=True,
    )
    print()
    print(f"Bundle created in {PROJECT_DIR / 'dist' / 'pyjippety'}")


if __name__ == "__main__":
    main()
