"""
compiled_world.py — CompiledWorld: the central runtime artifact.

A CompiledWorld is produced by compile_world() from a World Manifest (YAML).
It is the immutable artifact consumed by the runtime. The raw manifest is not
re-read or re-interpreted during execution.

Compilation step:
  World Manifest (YAML) → compile_world() → CompiledWorld → Runtime

Structure
---------
  name               : world identity
  description        : human-readable summary
  action_space       : frozenset[str]  — closed set of actions that exist
  simulation_bindings: frozenset[str]  — actions routed to the simulation layer

Actions absent from action_space do not exist in this world.
They cannot be formed, dispatched, or referenced — they are ontologically absent.

Actions in simulation_bindings exist in the world but execute against simulated
state rather than the real execution environment. This is the simulation binding
declared at compile time, not a runtime policy decision.
"""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class CompiledWorld:
    """
    Immutable runtime artifact for one world configuration.

    Produced by compile_world() from a World Manifest. The runtime loads this
    once and does not re-read the source manifest during execution.

    action_space        — closed set of action names that ontologically exist.
                          Absent actions do not exist; they cannot be dispatched.
    simulation_bindings — subset of action_space bound to the simulation layer.
                          Present but not executed against real state.
    """

    name: str
    description: str
    action_space: frozenset
    simulation_bindings: frozenset

    def is_present(self, action: str) -> bool:
        """Return True if the action exists in this Compiled World."""
        return action in self.action_space

    def is_simulation_bound(self, action: str) -> bool:
        """Return True if the action is bound to the simulation layer."""
        return action in self.simulation_bindings


def compile_world(path: str) -> CompiledWorld:
    """
    Load a World Manifest YAML and compile it into a CompiledWorld.

    This is the compilation step: World Manifest (source) → CompiledWorld
    (runtime artifact). The result is an immutable, explicit representation
    of the closed action set and simulation bindings for this world.

    Raises
    ------
    FileNotFoundError  if the manifest path does not exist
    ValueError         if required manifest fields are missing or invalid
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"World manifest not found: {path}")
    with open(p) as f:
        manifest = yaml.safe_load(f)
    _validate_manifest(manifest, path)

    action_space = frozenset(manifest["action_space"])
    simulation_bindings = frozenset(manifest.get("simulation_bindings", []))

    # simulation_bindings must be a subset of action_space
    unknown = simulation_bindings - action_space
    if unknown:
        raise ValueError(
            f"World manifest '{path}': simulation_bindings references actions "
            f"not in action_space: {sorted(unknown)}"
        )

    return CompiledWorld(
        name=manifest["name"],
        description=manifest.get("description", ""),
        action_space=action_space,
        simulation_bindings=simulation_bindings,
    )


def _validate_manifest(manifest: dict, path: str) -> None:
    for key in ("name", "action_space"):
        if key not in manifest:
            raise ValueError(
                f"World manifest '{path}' missing required key: '{key}'"
            )
    if not isinstance(manifest["action_space"], list):
        raise ValueError(
            f"World manifest '{path}': 'action_space' must be a list"
        )
