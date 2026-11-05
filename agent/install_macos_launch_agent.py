#!/usr/bin/env python3
"""Install or remove user-level macOS autostart entries for this project.

Run this only after reviewing the privacy policy, signing in with
`agent/main.py --login`, and granting the desired macOS permissions.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import plistlib
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"
LABELS = {
    "backend": "com.workeractivity.django-api",
    "agent": "com.workeractivity.desktop-agent",
    "camera": "com.workeractivity.camera-monitor",
}


def process_spec(kind: str) -> tuple[Path, list[str], Path]:
    if kind == "backend":
        backend_root = PROJECT_ROOT / "backend"
        return (
            backend_root / ".venv" / "bin" / "python",
            [str(backend_root / "manage.py"), "runserver", "127.0.0.1:8000", "--noreload"],
            backend_root,
        )
    python = PROJECT_ROOT / ".venv" / "bin" / "python"
    script = PROJECT_ROOT / ("agent/main.py" if kind == "agent" else "main.py")
    return python, [str(script)], PROJECT_ROOT


def plist_contents(label: str, python: Path, arguments: list[str], working_directory: Path) -> dict:
    return {
        "Label": label,
        "ProgramArguments": [str(python), *arguments],
        "WorkingDirectory": str(working_directory),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Interactive",
        "StandardOutPath": str(PROJECT_ROOT / "data" / f"{label}.out.log"),
        "StandardErrorPath": str(PROJECT_ROOT / "data" / f"{label}.err.log"),
    }


def unload(label: str) -> None:
    subprocess.run(
        ["launchctl", "bootout", f"gui/{os.getuid()}/{label}"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def install() -> None:
    root_python = PROJECT_ROOT / ".venv" / "bin" / "python"
    backend_python = PROJECT_ROOT / "backend" / ".venv" / "bin" / "python"
    if not root_python.exists() or not backend_python.exists():
        raise SystemExit("Project or backend virtual environment not found. Create both before enabling autostart.")
    if not (PROJECT_ROOT / "agent" / ".agent_tokens.json").exists():
        raise SystemExit("Run `python3 agent/main.py --login` before enabling autostart.")

    LAUNCH_AGENTS.mkdir(parents=True, exist_ok=True)
    (PROJECT_ROOT / "data").mkdir(exist_ok=True)
    for kind, label in LABELS.items():
        destination = LAUNCH_AGENTS / f"{label}.plist"
        unload(label)
        with destination.open("wb") as stream:
            python, arguments, working_directory = process_spec(kind)
            plistlib.dump(plist_contents(label, python, arguments, working_directory), stream)
        subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(destination)], check=True)
        print(f"Installed {kind} autostart: {destination}")


def uninstall() -> None:
    for label in LABELS.values():
        unload(label)
        destination = LAUNCH_AGENTS / f"{label}.plist"
        if destination.exists():
            destination.unlink()
        print(f"Removed {label}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Install user-level macOS monitoring autostart entries")
    parser.add_argument("--uninstall", action="store_true", help="Remove the entries created by this script")
    args = parser.parse_args()
    if sys.platform != "darwin":
        raise SystemExit("This installer must be run on macOS.")
    if args.uninstall:
        uninstall()
    else:
        install()


if __name__ == "__main__":
    main()
