"""
world_loader.py — Load world manifests from YAML.

A world manifest defines the ontological surface of a runtime:
which tools exist, and therefore what actions are possible.
"""

import yaml
from pathlib import Path


def load_world(path: str) -> dict:
    """Parse a world manifest YAML and return the world dict."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"World manifest not found: {path}")
    with open(p) as f:
        world = yaml.safe_load(f)
    _validate(world, path)
    return world


def get_tool_names(world: dict) -> list[str]:
    return list(world.get("tools", []))


def _validate(world: dict, path: str) -> None:
    for key in ("name", "description", "tools"):
        if key not in world:
            raise ValueError(f"World manifest '{path}' missing required key: '{key}'")
    if not isinstance(world["tools"], list):
        raise ValueError(f"World manifest '{path}': 'tools' must be a list")
