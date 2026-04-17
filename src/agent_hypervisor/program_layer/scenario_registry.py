"""
scenario_registry.py — YAML-backed registry for ``Scenario`` definitions.

Mirrors the shape of ``world_registry.WorldRegistry``: a directory of YAML
files, each describing exactly one ``Scenario``.  No active-pointer state is
kept — scenarios are lookups by id, nothing more.

Expected YAML shape::

    scenario_id: memory_write_test
    name: "Safe vs strict memory write"
    description: "..."
    program_steps:
      - tool: count_words
        params: {input: "hello world"}
      - tool: normalize_text
        params: {input: "HELLO WORLD"}
    worlds:
      - world_id: world_strict
        version: "1.0"
      - world_id: world_balanced
        version: "1.0"

Either ``program_steps`` (inline) or ``program_id`` (reference) must be
present (but not both) — the same invariant enforced by ``Scenario``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml

from .review_models import CandidateStep
from .scenario_model import Scenario, WorldRef


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ScenarioNotFoundError(KeyError):
    """Raised when a requested scenario_id is not present in the registry."""


class ScenarioLoadError(ValueError):
    """Raised when a scenario YAML file is malformed or fails validation."""


# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------


def load_scenario_from_yaml(path: str | Path) -> Scenario:
    """Load a single ``Scenario`` from a YAML manifest file.

    Raises:
        ScenarioLoadError: file missing, unparseable, or schema-invalid.
    """
    p = Path(path)
    if not p.exists():
        raise ScenarioLoadError(f"Scenario manifest not found: {path}")

    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ScenarioLoadError(f"Invalid YAML in {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ScenarioLoadError(f"Scenario manifest at {path} must be a mapping")

    for required in ("scenario_id", "worlds"):
        if required not in raw:
            raise ScenarioLoadError(f"{path}: missing required field {required!r}")

    raw_worlds = raw["worlds"]
    if not isinstance(raw_worlds, list) or not raw_worlds:
        raise ScenarioLoadError(
            f"{path}: 'worlds' must be a non-empty list of (world_id, version) mappings"
        )
    worlds: list[WorldRef] = []
    for i, w in enumerate(raw_worlds):
        if not isinstance(w, dict):
            raise ScenarioLoadError(
                f"{path}: worlds[{i}] must be a mapping with world_id and version"
            )
        try:
            worlds.append(WorldRef.from_dict(w))
        except (KeyError, TypeError, ValueError) as exc:
            raise ScenarioLoadError(f"{path}: worlds[{i}]: {exc}") from exc

    steps: Optional[tuple[CandidateStep, ...]] = None
    raw_steps = raw.get("program_steps")
    if raw_steps is not None:
        if not isinstance(raw_steps, list) or not raw_steps:
            raise ScenarioLoadError(
                f"{path}: 'program_steps' must be a non-empty list of step mappings"
            )
        try:
            steps = tuple(
                CandidateStep.from_dict(_normalise_step(s, i, path))
                for i, s in enumerate(raw_steps)
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ScenarioLoadError(f"{path}: program_steps: {exc}") from exc

    try:
        return Scenario(
            scenario_id=str(raw["scenario_id"]),
            name=str(raw.get("name") or raw["scenario_id"]),
            description=str(raw.get("description") or ""),
            program_id=(
                str(raw["program_id"]) if raw.get("program_id") is not None else None
            ),
            program_steps=steps,
            worlds=tuple(worlds),
            input=raw.get("input"),
        )
    except (TypeError, ValueError) as exc:
        raise ScenarioLoadError(f"{path}: {exc}") from exc


def _normalise_step(s: Any, i: int, path: Path) -> dict[str, Any]:
    if not isinstance(s, dict):
        raise ScenarioLoadError(
            f"{path}: program_steps[{i}] must be a mapping, got {type(s).__name__!r}"
        )
    return s


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class ScenarioRegistry:
    """Directory-backed registry of ``Scenario`` definitions.

    Args:
        scenarios_dir: directory containing one YAML file per scenario.

    The registry is read-only.  There is no ``save``/``activate`` surface —
    the scenario YAMLs are treated as the source of truth.
    """

    def __init__(self, scenarios_dir: str | Path) -> None:
        self._scenarios_dir = Path(scenarios_dir)

    @property
    def scenarios_dir(self) -> Path:
        return self._scenarios_dir

    def list_scenarios(self) -> list[Scenario]:
        """Return all scenarios under ``scenarios_dir``, sorted by id.

        Files that fail to parse are skipped silently so a single corrupt
        file does not poison the listing — a subsequent ``get()`` on that
        specific id will raise the underlying ``ScenarioLoadError``.
        """
        if not self._scenarios_dir.exists():
            return []

        out: list[Scenario] = []
        for p in sorted(self._scenarios_dir.iterdir()):
            if p.name.startswith("."):
                continue
            if p.suffix not in (".yaml", ".yml"):
                continue
            try:
                out.append(load_scenario_from_yaml(p))
            except ScenarioLoadError:
                continue
        out.sort(key=lambda s: s.scenario_id)
        return out

    def get(self, scenario_id: str) -> Scenario:
        """Load a scenario by id.

        Raises:
            ScenarioNotFoundError: no YAML file produced a scenario with that id.
            ScenarioLoadError:     a file matched the id but failed to parse.
        """
        if not self._scenarios_dir.exists():
            raise ScenarioNotFoundError(
                f"Scenario {scenario_id!r}: directory does not exist: "
                f"{self._scenarios_dir}"
            )
        last_load_error: Optional[ScenarioLoadError] = None
        for p in sorted(self._scenarios_dir.iterdir()):
            if p.suffix not in (".yaml", ".yml") or p.name.startswith("."):
                continue
            try:
                s = load_scenario_from_yaml(p)
            except ScenarioLoadError as exc:
                last_load_error = exc
                continue
            if s.scenario_id == scenario_id:
                return s
        if last_load_error is not None:
            raise last_load_error
        raise ScenarioNotFoundError(
            f"Scenario {scenario_id!r} not found under {self._scenarios_dir}"
        )


# ---------------------------------------------------------------------------
# Convenience: bundled scenarios
# ---------------------------------------------------------------------------


def _bundled_scenarios_dir() -> Path:
    return Path(__file__).parent / "scenarios"


def default_scenario_registry() -> ScenarioRegistry:
    """Registry over the bundled example scenarios (``program_layer/scenarios/``)."""
    return ScenarioRegistry(_bundled_scenarios_dir())
