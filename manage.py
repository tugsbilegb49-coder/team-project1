#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import signal
import sys


def main():
    """Run administrative tasks."""
    if hasattr(signal, 'SIGBREAK'):  # Windows: the launcher stops children with Ctrl+Break.
        signal.signal(signal.SIGBREAK, signal.default_int_handler)
    sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent / 'backend'))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            'available on your PYTHONPATH environment variable? Did you '
            'forget to activate a virtual environment?'
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
