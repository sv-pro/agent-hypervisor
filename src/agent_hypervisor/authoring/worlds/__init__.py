"""Worlds – policy presets for SafeMCPProxy."""

from safe_agent_runtime_pro.worlds.base import BASE_WORLD, WorldConfig
from safe_agent_runtime_pro.worlds.email_safe import EMAIL_SAFE_WORLD

_REGISTRY = {
    "base": BASE_WORLD,
    "email_safe": EMAIL_SAFE_WORLD,
}


def load_world(name: str) -> WorldConfig:
    """Return a WorldConfig by name ('base' or 'email_safe')."""
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(f"Unknown world {name!r}. Available: base, email_safe") from None


__all__ = ["load_world", "WorldConfig"]
