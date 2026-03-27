"""Tests for worlds – load_world() and WorldConfig."""

import pytest

from safe_agent_runtime_pro.worlds import load_world, WorldConfig


def test_load_world_base():
    world = load_world("base")
    assert isinstance(world.allowed_capabilities, frozenset)
    assert "read_data" in world.allowed_capabilities
    assert world.deny_tainted is True


def test_load_world_email_safe():
    world = load_world("email_safe")
    assert "read_data" in world.allowed_capabilities
    assert "summarize" in world.allowed_capabilities
    assert "send_email" in world.denied_capabilities
    assert world.deny_tainted is True


def test_load_world_unknown():
    with pytest.raises(KeyError, match="Unknown world"):
        load_world("does_not_exist")


def test_to_proxy_kwargs():
    world = load_world("base")
    kwargs = world.to_proxy_kwargs()
    assert "allowed_capabilities" in kwargs
    assert "denied_capabilities" in kwargs
    assert "deny_tainted" in kwargs
    assert isinstance(kwargs["allowed_capabilities"], list)


def test_world_config_immutable():
    world = load_world("base")
    with pytest.raises((AttributeError, TypeError)):
        world.deny_tainted = False  # type: ignore[misc]
