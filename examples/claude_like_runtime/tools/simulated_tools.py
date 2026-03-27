"""
simulated_tools.py — Tools with captured, non-executing side effects.

These tools are rendered with the same ontological presence as their real
counterparts — the agent can traverse the path — but the dangerous action
is echoed back as a simulation rather than executed against the real system.
"""

from __future__ import annotations
from datetime import datetime, timezone


def git_push_simulated() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        f"[SIMULATED @ {ts}]\n"
        "Enumerating objects: 5, done.\n"
        "Counting objects: 100% (5/5), done.\n"
        "Writing objects: 100% (3/3), 312 bytes | 312.00 KiB/s, done.\n"
        "To github.com:example/agent-hypervisor.git\n"
        "   a1b2c3d..e4f5g6h  claude/coding-runtime-demo -> claude/coding-runtime-demo\n"
        "\n"
        "NOTE: This push was simulated. No data was sent to any remote.\n"
        "      The side effect exists only within this world's simulation layer."
    )
