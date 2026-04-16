"""
trace_storage.py — JSONL-backed persistent storage for ProgramTrace.

Each program execution trace is appended as a single JSON object on its own
line (JSON Lines / JSONL format).  Lines are never modified after they are
written — the file is append-only.

File format (one JSON object per line)::

    {"program_id":"p1","ok":true,"total_duration_seconds":0.012,
     "aborted_at_step":null,"step_traces":[...],"_stored_at":"2024-01-01T00:00:00+00:00"}

Thread safety:
    ProgramTraceStore is NOT thread-safe.  Use one instance per process or
    synchronise externally.  This matches the existing TraceStore semantics in
    hypervisor/storage/trace_store.py.

Usage::

    from program_layer.trace_storage import ProgramTraceStore

    store = ProgramTraceStore("traces/program_traces.jsonl")
    trace = runner.run(program)
    store.append(trace)

    recent = store.list_recent(limit=10)
    for entry in recent:
        print(entry["program_id"], entry["ok"])

Integration with the existing TraceStore:
    ProgramTraceStore is self-contained and does not import from
    hypervisor/storage/.  If you need both stores in one deployment, run them
    side by side or write a thin adapter.  Keeping the layers separate avoids
    a runtime → hypervisor dependency.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .program_trace import ProgramTrace


class ProgramTraceStore:
    """
    Append-only JSONL store for ProgramTrace objects.

    Each append() writes one line: the trace dict from ProgramTrace.to_dict()
    plus a ``_stored_at`` ISO-8601 timestamp.

    Args:
        path: path to the .jsonl file.  Parent directories are created
              on first write.  The file need not exist in advance.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def append(self, trace: ProgramTrace) -> None:
        """
        Append a ProgramTrace to the JSONL file.

        Creates the file (and parent directories) if it does not exist.

        Args:
            trace: the ProgramTrace to persist.

        Raises:
            TypeError: trace is not a ProgramTrace.
            OSError:   file cannot be opened for writing.
        """
        if not isinstance(trace, ProgramTrace):
            raise TypeError(
                f"ProgramTraceStore.append() requires a ProgramTrace, "
                f"got {type(trace).__name__!r}"
            )

        self._path.parent.mkdir(parents=True, exist_ok=True)

        entry = trace.to_dict()
        entry["_stored_at"] = datetime.now(tz=timezone.utc).isoformat()

        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def list_recent(
        self,
        limit: int = 50,
        ok: Optional[bool] = None,
        program_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Return trace entries, newest first, up to ``limit`` items.

        Optional filters (ANDed):
            ok          — match the ``ok`` field (True/False)
            program_id  — match the ``program_id`` field

        Filters are applied before the limit, so the result may contain
        fewer than ``limit`` items.

        Returns an empty list if the file does not exist.
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
                if ok is not None and entry.get("ok") != ok:
                    continue
                if program_id is not None and entry.get("program_id") != program_id:
                    continue
                entries.append(entry)

        return list(reversed(entries))[:limit]

    def count(self) -> int:
        """Return the total number of stored traces (reads the whole file)."""
        if not self._path.exists():
            return 0
        count = 0
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
        return count

    def path(self) -> Path:
        """Return the underlying file path."""
        return self._path
