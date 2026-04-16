"""
World state model returned by /world/current.
"""
from __future__ import annotations

from .models import WorldConfig
from .policy import (
    WORLD_INTENT_POLICY_SUMMARY,
    WORLD_TAINT_DEFAULTS,
    WORLD_TRUST_DEFAULTS,
)


def current_world(version: str) -> WorldConfig:
    return WorldConfig(
        trust_defaults=WORLD_TRUST_DEFAULTS,
        taint_defaults=WORLD_TAINT_DEFAULTS,
        intent_policy_summary=WORLD_INTENT_POLICY_SUMMARY,
        version=version,
    )
