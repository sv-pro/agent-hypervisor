"""
operator_event_log.py — Append-only JSONL log for operator surface events.

Each line is a single JSON object recording one operator action.
The file is never modified after a line is written.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class OperatorEventLog:
    """
    Append-only JSONL log for operator surface events.

    Record schema:
        {
          "timestamp": "<ISO-8601>",
          "action": "<verb>",
          "target_type": "<world|program|scenario>",
          "target_id": "<id>",
          "result": "<ok|error|...>",
          "details": {...}       # optional
        }

    Parent directories are created on first write.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def log(
        self,
        action: str,
        target_type: str,
        target_id: str,
        result: str,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        record: dict[str, Any] = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "result": result,
        }
        if details:
            record["details"] = details
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def list_recent(
        self,
        limit: int = 50,
        action: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Return up to *limit* most recent records, newest last."""
        if not self._path.exists():
            return []
        records: list[dict[str, Any]] = []
        try:
            for line in self._path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if action is None or rec.get("action") == action:
                    records.append(rec)
        except OSError:
            return []
        return records[-limit:]
