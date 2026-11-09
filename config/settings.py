"""Compatibility entry point: all commands use the canonical backend settings."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'backend'))
from backend.config.settings import *  # noqa: F403,E402
