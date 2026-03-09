#!/usr/bin/env python3
"""Legacy entry point — delegates to generate_artifacts.py quick mode.

Kept for backward compatibility with any external callers.
"""
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.exit(subprocess.call(
    [sys.executable, str(root / "scripts" / "ci" / "generate_artifacts.py"), "quick"],
    cwd=str(root),
))
