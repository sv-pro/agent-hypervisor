"""
scenario_trace_store.py — Append-only JSONL store for ``ScenarioResult``.

Every call to ``run_scenario`` can append one line to a persistent trace
file.  Lines are never modified after they are written (SYS-3 step 7:
"append-only, comparable across worlds").

Matches the existing ``ProgramTraceStore`` shape so downstream audit code
can share reader patterns.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .scenario_model import ScenarioResult


class ScenarioTraceStore:
    """Append-only JSONL store for ``ScenarioResult`` records.

    Each ``append`` writes one line: the result dict from
    ``ScenarioResult.to_dict()`` plus a ``_stored_at`` ISO-8601 timestamp.

    Args:
        path: path to the .jsonl file.  Parent directories are created on
              first write.  The file need not exist in advance.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def append(self, result: ScenarioResult) -> None:
        if not isinstance(result, ScenarioResult):
            raise TypeError(
                "ScenarioTraceStore.append() requires a ScenarioResult, "
                f"got {type(result).__name__!r}"
            )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        entry = result.to_dict()
        entry["_stored_at"] = datetime.now(tz=timezone.utc).isoformat()
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def list_recent(
        self,
        limit: int = 50,
        scenario_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Return up to ``limit`` entries, newest first.

        ``scenario_id`` filters by the ``scenario_id`` field when provided.
        """
        if not self._path.exists():
            return []

        entries: list[dict[str, Any]] = []
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if scenario_id is not None and entry.get("scenario_id") != scenario_id:
                    continue
                entries.append(entry)

        return list(reversed(entries))[:limit]

    def count(self) -> int:
        if not self._path.exists():
            return 0
        n = 0
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    n += 1
        return n

    def path(self) -> Path:
        return self._path
