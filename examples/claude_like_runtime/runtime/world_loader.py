"""
world_loader.py — World Manifest loader (adapter).

Delegates to compile_world() in compiled_world.py.
Kept as the public import surface so existing callers don't change.

The compilation step is:
  World Manifest (YAML source) → compile_world() → CompiledWorld (runtime artifact)
"""

from runtime.compiled_world import CompiledWorld, compile_world  # noqa: F401 — re-export


def get_action_names(compiled_world: CompiledWorld) -> list:
    """Return the action space as a sorted list (for display)."""
    return sorted(compiled_world.action_space)
