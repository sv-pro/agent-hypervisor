"""
world_switcher.py — Manage the active world and surface transitions.

Switching a world changes which tools are ontologically present.
The visible tool surface is printed on every switch so the difference
between worlds is immediately observable.
"""

from __future__ import annotations
from runtime.world_loader import get_tool_names


class WorldSwitcher:
    def __init__(self) -> None:
        self._active: dict | None = None

    def switch(self, world: dict) -> None:
        self._active = world
        self._print_surface()

    def get_active_world(self) -> dict:
        if self._active is None:
            raise RuntimeError("No world loaded. Call switch() first.")
        return self._active

    def get_active_name(self) -> str:
        return self.get_active_world()["name"]

    def get_active_tools(self) -> list[str]:
        return get_tool_names(self.get_active_world())

    def get_active_mode(self) -> str:
        """Return 'curated' for sandboxed worlds, 'real' otherwise."""
        return self.get_active_world().get("mode", "real")

    def _print_surface(self) -> None:
        world = self._active
        tools = get_tool_names(world)
        bar = "─" * 52
        print(f"\n{bar}")
        print(f"  WORLD    : {world['name']}")
        print(f"  SURFACE  : {len(tools)} tool(s) rendered")
        for t in tools:
            print(f"             + {t}")
        print(f"{bar}\n")
