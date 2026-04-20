"""
profiles_catalog.py — Profile catalog loader and manager.

Responsibility:
    Load and manage the profiles-index.yaml catalog that lists all named
    capability profiles (WorldManifests) available to the gateway.

The catalog is the source of truth for the /ui/api/profiles* endpoints.
It does NOT replace SessionWorldResolver — it feeds it: callers use the
catalog to look up a manifest path, then pass that path to
SessionWorldResolver.register_session().

Catalog schema (profiles-index.yaml)::

    profiles:
      - id: email-assistant-v1
        description: "..."
        path: manifests/example_world.yaml
        tags: [email, read, send]

Invariants:
    - Profile ids must be unique within a catalog.
    - If the index file does not exist, load() raises FileNotFoundError.
    - If an entry's manifest path does not exist, get_profile() raises
      FileNotFoundError when trying to load the manifest.
    - The catalog never returns None — callers can depend on raised
      exceptions for error cases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from agent_hypervisor.compiler.manifest import load_manifest, save_manifest
from agent_hypervisor.compiler.schema import WorldManifest


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ProfileEntry:
    """A single entry in the profiles catalog."""

    id: str
    description: str
    path: Path            # absolute or relative to repo root
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "path": str(self.path),
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], base_dir: Path) -> "ProfileEntry":
        raw_path = data["path"]
        # Resolve relative paths against the catalog's base directory
        p = Path(raw_path)
        if not p.is_absolute():
            p = (base_dir / p).resolve()
        return cls(
            id=data["id"],
            description=data.get("description", ""),
            path=p,
            tags=data.get("tags", []),
        )


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


class ProfilesCatalog:
    """
    Manages a profiles-index.yaml catalog on disk.

    Usage::

        catalog = ProfilesCatalog(Path("manifests/profiles-index.yaml"))
        entries = catalog.list()
        entry = catalog.get("email-assistant-v1")
        manifest = catalog.load_manifest("email-assistant-v1")
        catalog.add(ProfileEntry(id="new-profile", ...), manifest)
    """

    def __init__(self, index_path: Path) -> None:
        self._index_path = Path(index_path).resolve()
        self._base_dir = self._index_path.parent
        self._entries: dict[str, ProfileEntry] = {}
        self._load()

    # ── Public API ────────────────────────────────────────────────────────

    def list(self) -> list[ProfileEntry]:
        """Return all catalog entries in declaration order."""
        return list(self._entries.values())

    def get(self, profile_id: str) -> Optional[ProfileEntry]:
        """Return the ProfileEntry for profile_id, or None if not found."""
        return self._entries.get(profile_id)

    def load_manifest(self, profile_id: str) -> WorldManifest:
        """
        Load and return the WorldManifest for profile_id.

        Raises:
            KeyError: If profile_id is not in the catalog.
            FileNotFoundError: If the manifest file does not exist on disk.
        """
        entry = self._entries.get(profile_id)
        if entry is None:
            raise KeyError(f"Profile not found: {profile_id!r}")
        return load_manifest(entry.path)

    def add(
        self,
        entry: ProfileEntry,
        manifest: WorldManifest,
        *,
        overwrite: bool = False,
    ) -> None:
        """
        Add a new profile to the catalog and write the manifest to disk.

        Args:
            entry:     The ProfileEntry to register.
            manifest:  The WorldManifest to write to entry.path.
            overwrite: If True, replace an existing entry with the same id.

        Raises:
            ValueError: If profile_id already exists and overwrite=False.
            OSError:    If writing the manifest file fails.
        """
        if entry.id in self._entries and not overwrite:
            raise ValueError(
                f"Profile {entry.id!r} already exists. "
                "Use overwrite=True to replace it."
            )
        # Resolve relative path against base dir
        resolved = entry.path
        if not resolved.is_absolute():
            resolved = (self._base_dir / resolved).resolve()
        actual_entry = ProfileEntry(
            id=entry.id,
            description=entry.description,
            path=resolved,
            tags=entry.tags,
        )
        # Write manifest file
        resolved.parent.mkdir(parents=True, exist_ok=True)
        save_manifest(manifest, resolved)
        # Register and persist catalog
        self._entries[entry.id] = actual_entry
        self._save()

    def reload(self) -> None:
        """Reload the catalog from disk."""
        self._load()

    @property
    def index_path(self) -> Path:
        return self._index_path

    # ── Internal ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        """Parse the index YAML and populate _entries."""
        data = yaml.safe_load(self._index_path.read_text(encoding="utf-8")) or {}
        entries: dict[str, ProfileEntry] = {}
        for raw in data.get("profiles", []):
            entry = ProfileEntry.from_dict(raw, self._base_dir)
            if entry.id in entries:
                raise ValueError(
                    f"Duplicate profile id {entry.id!r} in {self._index_path}"
                )
            entries[entry.id] = entry
        self._entries = entries

    def _save(self) -> None:
        """Write the current in-memory catalog back to the index YAML."""
        data = {
            "profiles": [
                {
                    "id": e.id,
                    "description": e.description,
                    # Store paths relative to the catalog directory for portability
                    "path": str(
                        Path(e.path).relative_to(self._base_dir)
                        if Path(e.path).is_relative_to(self._base_dir)
                        else e.path
                    ),
                    "tags": e.tags,
                }
                for e in self._entries.values()
            ]
        }
        self._index_path.write_text(
            yaml.dump(data, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
