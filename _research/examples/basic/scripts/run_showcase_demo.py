#!/usr/bin/env python3
"""
run_showcase_demo.py — Quickstart for the Agent Hypervisor showcase demo.

Runs the end-to-end governance demo with a single command.
No manual gateway setup required.

Usage:
    python scripts/run_showcase_demo.py

What it demonstrates:
    • A safe read call passes through with no friction
    • A prompt injection attempt is blocked deterministically
    • A legitimate sensitive action requires and receives human approval
    • Every decision is traced and linked to the active policy version

Dependencies:
    pip install fastapi uvicorn pyyaml
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DEMO = REPO_ROOT / "examples" / "showcase" / "showcase_demo.py"


def _check_deps() -> None:
    missing = []
    for pkg in ("fastapi", "uvicorn", "yaml"):
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        import_names = {"yaml": "pyyaml"}
        install = " ".join(import_names.get(p, p) for p in missing)
        print(f"Missing dependencies: {', '.join(missing)}")
        print(f"Install with:  pip install {install}")
        sys.exit(1)


def main() -> None:
    _check_deps()
    result = subprocess.run(
        [sys.executable, str(DEMO)],
        cwd=str(REPO_ROOT),
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
