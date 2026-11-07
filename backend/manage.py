#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import signal
import sys


def main() -> None:
    if hasattr(signal, 'SIGBREAK'):  # Windows: the launcher stops children with Ctrl+Break.
        signal.signal(signal.SIGBREAK, signal.default_int_handler)
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            'Django is not installed. Activate backend/.venv and run pip install -r requirements.txt.'
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
