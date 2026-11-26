#!/usr/bin/env python3
"""Standalone CLI application entry point."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mappo.cli import run  # noqa: E402

if __name__ == "__main__":
    run()
