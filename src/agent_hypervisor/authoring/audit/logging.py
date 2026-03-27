"""Structured audit event logging."""

from __future__ import annotations

import json
from datetime import datetime, timezone


def log_event(tool: str, taint: bool, decision: str, reason: str) -> None:
    """Print a single tool execution decision as a JSON line."""
    record = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "tool": tool,
        "taint": taint,
        "decision": decision,
        "reason": reason,
    }
    print(json.dumps(record))


__all__ = ["log_event"]
