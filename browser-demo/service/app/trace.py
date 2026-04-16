"""
Trace storage: appends trace entries to a JSONL file.
Also keeps the N most-recent entries in memory for fast /trace/recent queries.
"""
from __future__ import annotations

import json
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import TraceEntry

_MAX_MEMORY = 200   # keep last N entries in memory


class TraceStore:
    def __init__(self, path: Path, max_memory: int = _MAX_MEMORY) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._recent: deque[TraceEntry] = deque(maxlen=max_memory)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    def append(self, entry: TraceEntry) -> None:
        with self._lock:
            self._recent.append(entry)
            with open(self._path, "a") as fh:
                fh.write(entry.model_dump_json() + "\n")

    # ------------------------------------------------------------------
    def recent(self, limit: int = 50) -> list[TraceEntry]:
        with self._lock:
            entries = list(self._recent)
        return entries[-limit:]

    # ------------------------------------------------------------------
    def update_approval(self, trace_id: str, approved: bool) -> Optional[TraceEntry]:
        """
        Update the `approved` field on an existing in-memory trace entry.
        The on-disk JSONL is append-only; we append an amendment record.
        """
        with self._lock:
            for i, entry in enumerate(self._recent):
                if entry.trace_id == trace_id:
                    updated = entry.model_copy(update={"approved": approved})
                    # Replace in deque (deques don't support index assignment)
                    entries = list(self._recent)
                    entries[i] = updated
                    self._recent = deque(entries, maxlen=self._recent.maxlen)
                    # Append amendment
                    amendment = {
                        "__amendment__": True,
                        "trace_id": trace_id,
                        "approved": approved,
                        "amended_at": _now(),
                    }
                    with open(self._path, "a") as fh:
                        fh.write(json.dumps(amendment) + "\n")
                    return updated
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
