"""
world_switcher.py — Manage the active Compiled World and surface transitions.

Switching a world loads a new CompiledWorld artifact and changes the entire
action space: which actions ontologically exist and which bind to the
simulation layer. The action space is printed on every switch so the
difference between worlds is immediately observable.
"""

from __future__ import annotations
from runtime.compiled_world import CompiledWorld


class WorldSwitcher:
    def __init__(self) -> None:
        self._active: CompiledWorld | None = None

    def switch(self, compiled_world: CompiledWorld) -> None:
        self._active = compiled_world
        self._print_surface()

    def get_compiled_world(self) -> CompiledWorld:
        if self._active is None:
            raise RuntimeError("No Compiled World loaded. Call switch() first.")
        return self._active

    def get_active_name(self) -> str:
        return self.get_compiled_world().name

    def get_action_space(self) -> frozenset:
        """Return the closed action set for the active Compiled World."""
        return self.get_compiled_world().action_space

    def _print_surface(self) -> None:
        cw = self._active
        bar = "─" * 56

        def sim_tag(action: str) -> str:
            return "  [simulation binding]" if cw.is_simulation_bound(action) else ""

        print(f"\n{bar}")
        print(f"  COMPILED WORLD : {cw.name}")
        print(f"  ACTION SPACE   : {len(cw.action_space)} action(s)")
        for action in sorted(cw.action_space):
            print(f"    + {action}{sim_tag(action)}")
        print(f"{bar}\n")
