"""
world_registry.py — Lightweight world registry for SYS-2 light.

A **World** here is the set of actions a reviewed program is permitted to use.
It is deliberately narrower than the full CompiledPolicy — just enough to
demonstrate that "a reviewed program does not carry authority; authority
lives in the currently active World."

Each world is declared in a YAML file:

    world_id: world_strict
    version: "1.0"
    description: "Basic measurement only"
    allowed_actions:
      - count_words
      - count_lines

The registry loads worlds from a directory and tracks exactly one "active"
world via a small JSON file.  Switching worlds is atomic: the new world is
loaded and validated before the active pointer is updated, so a failed load
never corrupts state.

Design notes:
    - WorldDescriptor is frozen and carries allowed_actions as a frozenset.
    - The registry does NOT execute anything.  It only loads and indexes.
    - "Active world" is advisory metadata, not an authority boost — every
      replay/preview still validates independently.

Usage::

    registry = WorldRegistry(worlds_dir="src/agent_hypervisor/program_layer/worlds/")
    worlds = registry.list_worlds()
    registry.set_active("world_strict", "1.0")
    active = registry.get_active()
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class WorldNotFoundError(KeyError):
    """Raised when a requested world_id/version does not exist in the registry."""


class WorldLoadError(ValueError):
    """Raised when a world YAML file is malformed or fails schema validation."""


# ---------------------------------------------------------------------------
# WorldDescriptor
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorldDescriptor:
    """
    Immutable description of a World.

    Fields:
        world_id         — stable identifier (e.g. "world_strict")
        version          — semver-ish string (e.g. "1.0")
        allowed_actions  — frozenset of action names the world permits
        manifest_path    — filesystem path the descriptor was loaded from
        description      — human-readable summary
        created_at       — ISO-8601 timestamp (from YAML or load time)

    ``allowed_actions`` is the authoritative boundary.  Any reviewed
    program whose minimized_steps reference an action outside this set is
    incompatible with this world.
    """

    world_id: str
    version: str
    allowed_actions: frozenset[str]
    manifest_path: Optional[str] = field(default=None)
    description: str = field(default="")
    created_at: str = field(default="")

    def __post_init__(self) -> None:
        if not isinstance(self.world_id, str) or not self.world_id.strip():
            raise ValueError(
                f"WorldDescriptor.world_id must be a non-empty string, "
                f"got {self.world_id!r}"
            )
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError(
                f"WorldDescriptor.version must be a non-empty string, "
                f"got {self.version!r}"
            )
        if not isinstance(self.allowed_actions, frozenset):
            raise TypeError(
                f"WorldDescriptor.allowed_actions must be a frozenset, "
                f"got {type(self.allowed_actions).__name__!r}"
            )

    @property
    def key(self) -> tuple[str, str]:
        """(world_id, version) — the lookup key used inside the registry."""
        return (self.world_id, self.version)

    def to_dict(self) -> dict[str, Any]:
        return {
            "world_id": self.world_id,
            "version": self.version,
            "allowed_actions": sorted(self.allowed_actions),
            "manifest_path": self.manifest_path,
            "description": self.description,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorldDescriptor":
        return cls(
            world_id=data["world_id"],
            version=str(data["version"]),
            allowed_actions=frozenset(data.get("allowed_actions", ())),
            manifest_path=data.get("manifest_path"),
            description=data.get("description", ""),
            created_at=data.get("created_at", ""),
        )


# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------


def load_world_from_yaml(path: str | Path) -> WorldDescriptor:
    """
    Load a single WorldDescriptor from a YAML manifest file.

    Required fields in the YAML:
        world_id         — string
        version          — string (or number, coerced to string)
        allowed_actions  — list of string action names

    Optional:
        description      — human-readable summary
        created_at       — ISO-8601 timestamp (defaults to file mtime)

    Raises:
        WorldLoadError: file missing, unparseable, or schema-invalid.
    """
    p = Path(path)
    if not p.exists():
        raise WorldLoadError(f"World manifest not found: {path}")

    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise WorldLoadError(f"Invalid YAML in {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise WorldLoadError(f"World manifest at {path} must be a mapping")

    for required in ("world_id", "version", "allowed_actions"):
        if required not in raw:
            raise WorldLoadError(f"{path}: missing required field {required!r}")

    actions = raw["allowed_actions"]
    if not isinstance(actions, list) or not all(isinstance(a, str) for a in actions):
        raise WorldLoadError(
            f"{path}: allowed_actions must be a list of strings"
        )

    created_at = raw.get("created_at") or datetime.fromtimestamp(
        p.stat().st_mtime, tz=timezone.utc
    ).isoformat()

    try:
        return WorldDescriptor(
            world_id=str(raw["world_id"]),
            version=str(raw["version"]),
            allowed_actions=frozenset(actions),
            manifest_path=str(p.resolve()),
            description=raw.get("description", ""),
            created_at=created_at,
        )
    except (TypeError, ValueError) as exc:
        raise WorldLoadError(f"{path}: {exc}") from exc


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class WorldRegistry:
    """
    Directory-backed registry of WorldDescriptor objects.

    Lookup layout:
        {worlds_dir}/
            world_strict.yaml
            world_balanced.yaml
            .active.json   # written by set_active()

    A single YAML file describes one (world_id, version) pair.  Multiple
    versions of the same world_id are supported by adding more YAML files.

    Args:
        worlds_dir:  directory containing world YAML manifests.
        active_file: optional custom path for the active-world pointer.
                     Defaults to ``{worlds_dir}/.active.json``.

    Thread safety:
        Not thread-safe.  Use one instance per process or synchronise externally.
    """

    _ACTIVE_FILENAME = ".active.json"

    def __init__(
        self,
        worlds_dir: str | Path,
        active_file: Optional[str | Path] = None,
    ) -> None:
        self._worlds_dir = Path(worlds_dir)
        self._active_file = (
            Path(active_file) if active_file is not None
            else self._worlds_dir / self._ACTIVE_FILENAME
        )

    @property
    def worlds_dir(self) -> Path:
        return self._worlds_dir

    # ------------------------------------------------------------------
    # List / load
    # ------------------------------------------------------------------

    def list_worlds(self) -> list[WorldDescriptor]:
        """
        Return all worlds defined under ``worlds_dir``, sorted by (id, version).

        Files that fail to parse are skipped silently so a corrupt file does
        not break the whole registry — but ``get()`` will still raise for
        that specific world.
        """
        if not self._worlds_dir.exists():
            return []

        out: list[WorldDescriptor] = []
        for path in sorted(self._worlds_dir.iterdir()):
            if path.name.startswith("."):
                continue
            if path.suffix not in (".yaml", ".yml"):
                continue
            try:
                out.append(load_world_from_yaml(path))
            except WorldLoadError:
                continue
        out.sort(key=lambda w: w.key)
        return out

    def get(
        self,
        world_id: str,
        version: Optional[str] = None,
    ) -> WorldDescriptor:
        """
        Load a world by id (and optionally version).

        If ``version`` is None, the most recent version found (lexicographic
        last) is returned.  Raises WorldNotFoundError if no match exists.
        """
        candidates = [w for w in self.list_worlds() if w.world_id == world_id]
        if not candidates:
            raise WorldNotFoundError(
                f"No world with id {world_id!r} under {self._worlds_dir}"
            )
        if version is None:
            return candidates[-1]  # lexicographic latest
        for w in candidates:
            if w.version == version:
                return w
        versions = sorted(w.version for w in candidates)
        raise WorldNotFoundError(
            f"World {world_id!r} has no version {version!r}. "
            f"Available: {versions}"
        )

    # ------------------------------------------------------------------
    # Active-world pointer
    # ------------------------------------------------------------------

    def get_active(self) -> Optional[WorldDescriptor]:
        """
        Return the currently active world, or None if none is set.

        If the active pointer references a world that no longer exists,
        returns None (stale pointers do not raise).
        """
        if not self._active_file.exists():
            return None
        try:
            data = json.loads(self._active_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

        world_id = data.get("world_id")
        version = data.get("version")
        if not world_id or not version:
            return None
        try:
            return self.get(world_id, version)
        except WorldNotFoundError:
            return None

    def set_active(self, world_id: str, version: str) -> WorldDescriptor:
        """
        Mark ``(world_id, version)`` as the active world.

        Loads and validates the target world first.  If loading fails, the
        active pointer is left unchanged.  On success, the pointer file is
        rewritten atomically.

        Returns the newly active WorldDescriptor.
        """
        # Validate by loading before writing — this is the rollback guarantee.
        target = self.get(world_id, version)

        payload = {
            "world_id": target.world_id,
            "version": target.version,
            "activated_at": datetime.now(tz=timezone.utc).isoformat(),
        }

        self._worlds_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=self._worlds_dir, prefix=".tmp_active_", suffix=".json"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
                f.write("\n")
            os.replace(tmp, self._active_file)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

        return target

    def clear_active(self) -> None:
        """Remove the active-world pointer if present."""
        try:
            self._active_file.unlink()
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------------------
# Convenience: default bundled-worlds registry
# ---------------------------------------------------------------------------


def _bundled_worlds_dir() -> Path:
    """Return the directory holding worlds shipped with the package."""
    return Path(__file__).parent / "worlds"


def default_registry(active_file: Optional[str | Path] = None) -> WorldRegistry:
    """
    Registry over the bundled example worlds (program_layer/worlds/).

    Useful for demos and tests.  For real usage the caller should construct
    WorldRegistry with its own directory.
    """
    return WorldRegistry(_bundled_worlds_dir(), active_file=active_file)
