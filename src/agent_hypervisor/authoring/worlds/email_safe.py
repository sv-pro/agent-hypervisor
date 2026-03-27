"""Email-safe world – summarize allowed; send_email unconditionally blocked."""

from safe_agent_runtime_pro.worlds.base import WorldConfig

EMAIL_SAFE_WORLD = WorldConfig(
    allowed_capabilities=frozenset({"read_data", "summarize"}),
    denied_capabilities=frozenset({"send_email"}),
    deny_tainted=True,
)

__all__ = ["EMAIL_SAFE_WORLD"]
