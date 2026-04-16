"""
program_store.py — JSON file-backed storage for ReviewedProgram (PL-3).

Each ReviewedProgram is stored as a single JSON file:

    {store_dir}/program_{id}.json

Files are written atomically (write to temp file → os.replace).
original_steps are immutable: once written, the field is never modified.
Status updates (review, accept, reject) overwrite the file with a new
ReviewedProgram instance that has the same original_steps.

Thread safety:
    ProgramStore is NOT thread-safe.  Use one instance per process or
    synchronise externally.  This matches the existing TraceStore semantics
    in hypervisor/storage/trace_store.py.

Usage::

    store = ProgramStore("programs/")
    store.save(program)
    loaded = store.load(program.id)
    ids = store.list_ids()
    summaries = store.list_all()
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .review_models import ReviewedProgram


class ProgramStore:
    """
    Filesystem-backed registry of ReviewedProgram objects.

    Args:
        directory: path to the directory where program JSON files are stored.
                   Created automatically on first save.
    """

    _PREFIX = "program_"
    _SUFFIX = ".json"

    def __init__(self, directory: str | Path) -> None:
        self._dir = Path(directory)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save(self, program: ReviewedProgram) -> Path:
        """
        Persist a ReviewedProgram to disk (atomic write).

        Overwrites any existing file for the same program id.

        Args:
            program: the ReviewedProgram to store.

        Returns:
            Path to the written file.

        Raises:
            TypeError: program is not a ReviewedProgram.
            OSError:   directory cannot be created or file cannot be written.
        """
        if not isinstance(program, ReviewedProgram):
            raise TypeError(
                f"ProgramStore.save() requires a ReviewedProgram, "
                f"got {type(program).__name__!r}"
            )

        self._dir.mkdir(parents=True, exist_ok=True)
        target = self._path_for(program.id)
        data = program.to_dict()

        # Atomic write: write to temp, then rename
        fd, tmp = tempfile.mkstemp(dir=self._dir, prefix=".tmp_", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
                f.write("\n")
            os.replace(tmp, target)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

        return target

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def load(self, program_id: str) -> ReviewedProgram:
        """
        Load a ReviewedProgram by id.

        Args:
            program_id: the program's unique id.

        Returns:
            The deserialized ReviewedProgram.

        Raises:
            KeyError:   no program with the given id exists.
            ValueError: the stored file is corrupt or schema is mismatched.
        """
        path = self._path_for(program_id)
        if not path.exists():
            raise KeyError(f"Program not found: {program_id!r}")

        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Corrupt program file for {program_id!r}: {exc}"
            ) from exc

        try:
            return ReviewedProgram.from_dict(data)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"Schema mismatch in program file for {program_id!r}: {exc}"
            ) from exc

    def exists(self, program_id: str) -> bool:
        """Return True if a program with the given id is stored."""
        return self._path_for(program_id).exists()

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list_ids(self) -> list[str]:
        """
        Return all stored program ids, sorted alphabetically.

        Returns an empty list if the directory does not exist.
        """
        if not self._dir.exists():
            return []
        ids: list[str] = []
        for path in sorted(self._dir.iterdir()):
            name = path.name
            if (
                name.startswith(self._PREFIX)
                and name.endswith(self._SUFFIX)
                and not name.startswith(".tmp_")
            ):
                prog_id = name[len(self._PREFIX) : -len(self._SUFFIX)]
                ids.append(prog_id)
        return ids

    def list_all(self) -> list[dict[str, Any]]:
        """
        Return summary dicts for all stored programs, newest-saved first.

        Each dict contains:
            id, status, step_count_original, step_count_minimized,
            created_at, created_from_trace

        Programs that fail to deserialize are silently skipped.
        """
        summaries: list[dict[str, Any]] = []
        for prog_id in self.list_ids():
            try:
                prog = self.load(prog_id)
                summaries.append(
                    {
                        "id": prog.id,
                        "status": prog.status.value,
                        "step_count_original": len(prog.original_steps),
                        "step_count_minimized": len(prog.minimized_steps),
                        "created_at": prog.metadata.created_at,
                        "created_from_trace": prog.metadata.created_from_trace,
                    }
                )
            except (KeyError, ValueError):
                continue
        return summaries

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _path_for(self, program_id: str) -> Path:
        return self._dir / f"{self._PREFIX}{program_id}{self._SUFFIX}"
