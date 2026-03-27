"""
approval_store.py — Persistent store for approval records.

Each approval occupies one JSON file: ``{directory}/{approval_id}.json``.
Updates read the file, merge the new fields, and write it back.  This
gives O(1) access by id and leaves individual approval files readable
for debugging.

The stored format matches ``ApprovalRecord.to_store_dict()`` which
includes the serialised ``request`` field needed for re-execution on
restart.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


class ApprovalStore:
    """
    Directory-based persistent store for approval records.

    Each approval is stored as ``{directory}/{approval_id}.json``.

    Args:
        directory: Path to the directory.  Created on init if missing.
    """

    def __init__(self, directory: str | Path) -> None:
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _record_path(self, approval_id: str) -> Path:
        return self._dir / f"{approval_id}.json"

    def create(self, record: dict) -> None:
        """Write a new approval record to disk."""
        path = self._record_path(record["approval_id"])
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, default=str)

    def update(self, approval_id: str, **fields) -> None:
        """
        Update fields on an existing approval record (read–modify–write).

        Raises KeyError if the record does not exist.
        """
        path = self._record_path(approval_id)
        if not path.exists():
            raise KeyError(f"Approval '{approval_id}' not found in store")
        with open(path, encoding="utf-8") as f:
            record = json.load(f)
        record.update(fields)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, default=str)

    def get(self, approval_id: str) -> Optional[dict]:
        """Return one approval record dict, or None if not found."""
        path = self._record_path(approval_id)
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def list_recent(
        self,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """
        Return approval records sorted by file modification time, newest first.

        If *status* is given (e.g. ``"pending"``), only records with that
        status are returned.  *limit* caps the number returned.
        """
        records: list[dict] = []
        try:
            paths = sorted(
                self._dir.glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return []

        for path in paths:
            try:
                with open(path, encoding="utf-8") as f:
                    record = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue
            if status and record.get("status") != status:
                continue
            records.append(record)
            if len(records) >= limit:
                break

        return records
