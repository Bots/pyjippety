from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
DIST_DIR = PROJECT_DIR / "dist"
RELEASE_DIR = PROJECT_DIR / "release"
APP_NAME = "PyJippety"
PACKAGE_NAME = "pyjippety"
VERSION = "0.1.0"


def _run(args: list[str], **kwargs) -> None:
    subprocess.run(args, check=True, **kwargs)


def _normalize_arch() -> str:
    machine = platform.machine().lower()
    mapping = {
        "x86_64": "x64",
        "amd64": "x64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }
    return mapping.get(machine, machine)


def _appimage_arch() -> str:
    machine = platform.machine().lower()
    mapping = {
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "aarch64": "aarch64",
        "arm64": "aarch64",
    }
    return mapping.get(machine, machine)


def _bundle_path() -> Path:
    if platform.system() == "Darwin":
        app_bundle = DIST_DIR / f"{PACKAGE_NAME}.app"
        if app_bundle.exists():
            return app_bundle
    return DIST_DIR / PACKAGE_NAME


def _ensure_release_dir() -> None:
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)


def _package_windows() -> None:
    exe_name = f"{APP_NAME}-{_normalize_arch()}.exe"
    scripts_dir = PROJECT_DIR / ".venv" / "Scripts"
    python = scripts_dir / "python.exe"
    if not python.exists():
        python = Path(sys.executable)
    try:
        _run(
            [
                str(python),
                "-m",
                "PyInstaller",
                "--noconfirm",
                "--clean",
                "--windowed",
                "--onefile",
                "--name",
                APP_NAME,
                "--paths",
                str(PROJECT_DIR / "src"),
                "--add-data",
                f"{PROJECT_DIR / 'assets'};assets",
                str(PROJECT_DIR / "src" / "pyjippety" / "gui.py"),
            ]
        )
        onefile = DIST_DIR / f"{APP_NAME}.exe"
        if onefile.exists():
            shutil.copy2(onefile, RELEASE_DIR / exe_name)
    except subprocess.CalledProcessError:
        pass

    bundle = _bundle_path()
    archive = RELEASE_DIR / f"{PACKAGE_NAME}-windows-{_normalize_arch()}.zip"
    if archive.exists():
        archive.unlink()
    shutil.make_archive(str(archive.with_suffix("")), "zip", root_dir=bundle.parent, base_dir=bundle.name)


def _package_macos() -> None:
    bundle = _bundle_path()
    if not bundle.exists():
        raise SystemExit(f"Expected macOS bundle at {bundle}")
    dmg_path = RELEASE_DIR / f"{PACKAGE_NAME}-macos-{_normalize_arch()}.dmg"
    if dmg_path.exists():
        dmg_path.unlink()
    with tempfile.TemporaryDirectory() as temp_dir:
        staging = Path(temp_dir) / bundle.name
        if bundle.is_dir():
            shutil.copytree(bundle, staging)
        else:
            shutil.copy2(bundle, staging)
        _run(
            [
                "hdiutil",
                "create",
                "-volname",
                APP_NAME,
                "-srcfolder",
                str(staging.parent),
                "-ov",
                "-format",
                "UDZO",
                str(dmg_path),
            ]
        )
    archive = RELEASE_DIR / f"{PACKAGE_NAME}-macos-{_normalize_arch()}.tar.gz"
    if archive.exists():
        archive.unlink()
    _run(["tar", "-czf", str(archive), "-C", str(bundle.parent), bundle.name])


def _write_deb_metadata(control_dir: Path) -> None:
    (control_dir / "control").write_text(
        "\n".join(
            [
                f"Package: {PACKAGE_NAME}",
                f"Version: {VERSION}",
                "Section: utils",
                "Priority: optional",
                f"Architecture: {'amd64' if _normalize_arch() == 'x64' else _normalize_arch()}",
                "Maintainer: Bots",
                "Depends: python3, portaudio19-dev",
                "Description: PyJippety desktop voice assistant",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _package_linux() -> None:
    bundle = _bundle_path()
    archive = RELEASE_DIR / f"{PACKAGE_NAME}-linux-{_normalize_arch()}.tar.gz"
    if archive.exists():
        archive.unlink()
    _run(["tar", "-czf", str(archive), "-C", str(bundle.parent), bundle.name])

    deb_root = RELEASE_DIR / "deb-root"
    if deb_root.exists():
        shutil.rmtree(deb_root)
    control_dir = deb_root / "DEBIAN"
    app_dir = deb_root / "opt" / PACKAGE_NAME
    bin_dir = deb_root / "usr" / "bin"
    applications_dir = deb_root / "usr" / "share" / "applications"
    icons_dir = deb_root / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps"
    for path in (control_dir, app_dir, bin_dir, applications_dir, icons_dir):
        path.mkdir(parents=True, exist_ok=True)
    _write_deb_metadata(control_dir)
    shutil.copytree(bundle, app_dir, dirs_exist_ok=True)
    (bin_dir / "pyjippety-ui").write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f'exec "/opt/{PACKAGE_NAME}/{PACKAGE_NAME}" "$@"\n',
        encoding="utf-8",
    )
    os.chmod(bin_dir / "pyjippety-ui", 0o755)
    (applications_dir / "pyjippety.desktop").write_text(
        "[Desktop Entry]\n"
        "Version=1.0\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        "Comment=Desktop voice assistant\n"
        "Exec=pyjippety-ui\n"
        "Icon=pyjippety\n"
        "Terminal=false\n"
        "Categories=Utility;\n",
        encoding="utf-8",
    )
    shutil.copy2(PROJECT_DIR / "assets" / "pyjippety-logo.png", icons_dir / "pyjippety.png")
    deb_path = RELEASE_DIR / f"{PACKAGE_NAME}-linux-{_normalize_arch()}.deb"
    if deb_path.exists():
        deb_path.unlink()
    _run(["dpkg-deb", "--build", str(deb_root), str(deb_path)])
    _package_appimage(bundle)


def _package_appimage(bundle: Path) -> None:
    appimagetool = os.environ.get("APPIMAGETOOL") or shutil.which("appimagetool")
    if not appimagetool:
        return
    appdir = RELEASE_DIR / "AppDir"
    if appdir.exists():
        shutil.rmtree(appdir)
    (appdir / "usr" / "lib" / PACKAGE_NAME).mkdir(parents=True, exist_ok=True)
    shutil.copytree(bundle, appdir / "usr" / "lib" / PACKAGE_NAME, dirs_exist_ok=True)
    shutil.copy2(PROJECT_DIR / "assets" / "pyjippety-logo.png", appdir / "pyjippety.png")
    desktop_file = appdir / "pyjippety.desktop"
    desktop_file.write_text(
        "[Desktop Entry]\n"
        "Version=1.0\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        "Comment=Desktop voice assistant\n"
        "Exec=pyjippety-ui\n"
        "Icon=pyjippety\n"
        "Terminal=false\n"
        "Categories=Utility;\n",
        encoding="utf-8",
    )
    (appdir / "AppRun").write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        f'exec "$HERE/usr/lib/{PACKAGE_NAME}/{PACKAGE_NAME}" "$@"\n',
        encoding="utf-8",
    )
    os.chmod(appdir / "AppRun", 0o755)
    appimage_path = RELEASE_DIR / f"{PACKAGE_NAME}-linux-{_normalize_arch()}.AppImage"
    if appimage_path.exists():
        appimage_path.unlink()
    command = [appimagetool]
    if appimagetool.endswith(".AppImage"):
        command.append("--appimage-extract-and-run")
    command.extend([str(appdir), str(appimage_path)])
    env = dict(os.environ)
    env["ARCH"] = _appimage_arch()
    _run(command, env=env)


def _package_flatpak() -> None:
    manifest = PROJECT_DIR / "packaging" / "flatpak" / "com.bots.PyJippety.yml"
    if not manifest.exists():
        return
    if shutil.which("flatpak-builder") is None or shutil.which("flatpak") is None:
        return
    build_root = RELEASE_DIR / "flatpak-build"
    repo_dir = RELEASE_DIR / "flatpak-repo"
    bundle_path = RELEASE_DIR / f"{PACKAGE_NAME}-linux-{_normalize_arch()}.flatpak"
    for path in (build_root, repo_dir):
        if path.exists():
            shutil.rmtree(path)
    _run(
        [
            "flatpak",
            "--user",
            "remote-add",
            "--if-not-exists",
            "flathub",
            "https://flathub.org/repo/flathub.flatpakrepo",
        ]
    )
    _run(["flatpak-builder", "--force-clean", "--repo", str(repo_dir), str(build_root), str(manifest)])
    _run(["flatpak", "build-bundle", str(repo_dir), str(bundle_path), "com.bots.PyJippety"])


def main() -> None:
    _ensure_release_dir()
    system = platform.system()
    if system == "Windows":
        _package_windows()
    elif system == "Darwin":
        _package_macos()
    else:
        _package_linux()
        _package_flatpak()
    print(f"Release artifacts written to {RELEASE_DIR}")


if __name__ == "__main__":
    main()
