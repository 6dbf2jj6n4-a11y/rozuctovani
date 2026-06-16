#!/usr/bin/env python
"""Spravovaci skript Django projektu."""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Nepodarilo se importovat Django. Je nainstalovany "
            "a aktivovany virtualni prostredi?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
