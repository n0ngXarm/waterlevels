"""PyInstaller console entry point; no arguments opens the desktop app."""
from aqua_command.cli import main

if __name__ == '__main__':
    raise SystemExit(main())
