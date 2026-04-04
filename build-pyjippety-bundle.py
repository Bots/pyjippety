from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
VENV_DIR = PROJECT_DIR / ".venv"


def main() -> None:
    scripts_dir = VENV_DIR / ("Scripts" if platform.system() == "Windows" else "bin")
    venv_python = scripts_dir / ("python.exe" if platform.system() == "Windows" else "python")
    python = venv_python if venv_python.exists() else Path(sys.executable)

    subprocess.run([str(python), "-m", "pip", "install", "--upgrade", "pyinstaller"], check=True)
    separator = ";" if platform.system() == "Windows" else ":"
    subprocess.run(
        [
            str(python),
            "-m",
            "PyInstaller",
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
            "--hidden-import",
            "pyjippety.gui",
            "--collect-submodules",
            "pyjippety",
            "--collect-data",
            "pyjippety",
            str(PROJECT_DIR / "run-pyjippety-gui.py"),
        ],
        check=True,
    )
    print()
    print(f"Bundle created in {PROJECT_DIR / 'dist' / 'pyjippety'}")


if __name__ == "__main__":
    main()
