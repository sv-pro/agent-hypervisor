"""
trace_store.py — Persistent trace log backed by a JSONL file.

Each trace entry is a single JSON object written as one line.  The file
grows indefinitely; reads scan from the end to return the most-recent N
entries.  No entry is ever modified after it is written.

Format: JSON Lines — one JSON object per line, UTF-8.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


class TraceStore:
    """
    Append-only persistent trace log.

    Args:
        path: Path to the .jsonl file.  Parent directories are created on init.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, entry: dict) -> None:
        """Append one trace entry.  Thread-unsafe; single-process only."""
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def list_recent(
        self,
        limit: int = 50,
        verdict: Optional[str] = None,
        tool: Optional[str] = None,
        approval_id: Optional[str] = None,
    ) -> list[dict]:
        """
        Return trace entries, newest first, up to *limit* items.

        Optional filters (all are ANDed):
            verdict     — match ``final_verdict`` field
            tool        — match ``tool`` field
            approval_id — match ``approval_id`` field

        Filters are applied before the limit so the result may contain
        fewer than *limit* items.
        """
        if not self._path.exists():
            return []

        entries: list[dict] = []
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if verdict and entry.get("final_verdict") != verdict:
                    continue
                if tool and entry.get("tool") != tool:
                    continue
                if approval_id and entry.get("approval_id") != approval_id:
                    continue
                entries.append(entry)

        return list(reversed(entries))[:limit]
