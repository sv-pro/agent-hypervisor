"""
policy_store.py — Persistent policy version history.

A new version entry is appended whenever the policy content changes.
The most recent entry is the currently active version.

Format: JSON Lines — one version record per line, UTF-8.

Version record fields:
    version_id    — first 8 hex chars of SHA-256(content)
    timestamp     — ISO 8601 UTC activation timestamp
    policy_file   — path to the source YAML file
    content_hash  — full SHA-256 for integrity checks
    rule_count    — number of rules loaded from this version
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


class PolicyStore:
    """
    Append-only policy version history.

    Args:
        path: Path to the .jsonl file.  Parent directories are created on init.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def record_version(self, record: dict) -> None:
        """Append a policy version record."""
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")

    def get_current(self) -> Optional[dict]:
        """Return the most recently recorded version, or None."""
        history = self.get_history(limit=1)
        return history[0] if history else None

    def get_history(self, limit: int = 20) -> list[dict]:
        """Return version history, newest first, up to *limit* entries."""
        if not self._path.exists():
            return []

        entries: list[dict] = []
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        return list(reversed(entries))[:limit]
