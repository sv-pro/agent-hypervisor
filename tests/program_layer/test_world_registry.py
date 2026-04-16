"""
test_world_registry.py — WorldRegistry + WorldDescriptor tests (SYS-2 light).

Covers:
    - WorldDescriptor construction and validation
    - YAML manifest loading (happy path, missing fields, malformed YAML)
    - WorldRegistry.list_worlds() sorting and filtering
    - WorldRegistry.get() with and without explicit version
    - Active-world pointer: set / get / clear / rollback on bad target
    - Stale active pointer returns None (does not raise)
    - default_registry() loads the bundled example worlds
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_hypervisor.program_layer import (
    WorldDescriptor,
    WorldLoadError,
    WorldNotFoundError,
    WorldRegistry,
    default_registry,
    load_world_from_yaml,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def strict_yaml(tmp_path: Path) -> Path:
    return _write(
        tmp_path / "world_strict.yaml",
        """
world_id: world_strict
version: "1.0"
description: strict
allowed_actions:
  - count_words
  - count_lines
""".strip(),
    )


@pytest.fixture
def balanced_yaml(tmp_path: Path) -> Path:
    return _write(
        tmp_path / "world_balanced.yaml",
        """
world_id: world_balanced
version: "1.0"
description: balanced
allowed_actions:
  - count_words
  - count_lines
  - normalize_text
  - word_frequency
""".strip(),
    )


@pytest.fixture
def registry(tmp_path: Path, strict_yaml: Path, balanced_yaml: Path) -> WorldRegistry:
    return WorldRegistry(worlds_dir=tmp_path)


# ---------------------------------------------------------------------------
# WorldDescriptor
# ---------------------------------------------------------------------------


def test_world_descriptor_roundtrip():
    w = WorldDescriptor(
        world_id="w1",
        version="1.0",
        allowed_actions=frozenset({"a", "b"}),
        description="desc",
    )
    data = w.to_dict()
    assert data["allowed_actions"] == ["a", "b"]  # sorted
    round = WorldDescriptor.from_dict(data)
    assert round.world_id == "w1"
    assert round.version == "1.0"
    assert round.allowed_actions == frozenset({"a", "b"})


def test_world_descriptor_rejects_empty_id():
    with pytest.raises(ValueError):
        WorldDescriptor(world_id="", version="1.0", allowed_actions=frozenset())


def test_world_descriptor_rejects_empty_version():
    with pytest.raises(ValueError):
        WorldDescriptor(world_id="w1", version="", allowed_actions=frozenset())


def test_world_descriptor_rejects_non_frozenset_actions():
    with pytest.raises(TypeError):
        WorldDescriptor(
            world_id="w1", version="1.0", allowed_actions={"a"}  # set, not frozenset
        )


# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------


def test_load_world_from_yaml_happy_path(strict_yaml: Path):
    w = load_world_from_yaml(strict_yaml)
    assert w.world_id == "world_strict"
    assert w.version == "1.0"
    assert w.allowed_actions == frozenset({"count_words", "count_lines"})
    assert w.description == "strict"
    assert w.manifest_path is not None
    assert w.created_at  # populated from file mtime


def test_load_world_missing_file(tmp_path: Path):
    with pytest.raises(WorldLoadError):
        load_world_from_yaml(tmp_path / "nope.yaml")


def test_load_world_missing_required_field(tmp_path: Path):
    bad = _write(tmp_path / "bad.yaml", "world_id: only_id\n")
    with pytest.raises(WorldLoadError):
        load_world_from_yaml(bad)


def test_load_world_bad_actions_type(tmp_path: Path):
    bad = _write(
        tmp_path / "bad.yaml",
        "world_id: x\nversion: 1.0\nallowed_actions: not_a_list\n",
    )
    with pytest.raises(WorldLoadError):
        load_world_from_yaml(bad)


def test_load_world_non_mapping(tmp_path: Path):
    bad = _write(tmp_path / "bad.yaml", "- just a list\n- not a mapping\n")
    with pytest.raises(WorldLoadError):
        load_world_from_yaml(bad)


def test_load_world_malformed_yaml(tmp_path: Path):
    bad = _write(tmp_path / "bad.yaml", "world_id: [unclosed\n")
    with pytest.raises(WorldLoadError):
        load_world_from_yaml(bad)


# ---------------------------------------------------------------------------
# Registry listing
# ---------------------------------------------------------------------------


def test_list_worlds_returns_sorted(registry: WorldRegistry):
    worlds = registry.list_worlds()
    keys = [w.key for w in worlds]
    assert keys == sorted(keys)
    ids = {w.world_id for w in worlds}
    assert ids == {"world_strict", "world_balanced"}


def test_list_worlds_skips_hidden_and_non_yaml(
    tmp_path: Path, strict_yaml: Path
):
    # Dotfile + non-YAML should not appear
    _write(tmp_path / ".hidden.yaml", "ignored: true\n")
    _write(tmp_path / "notes.txt", "not yaml")
    worlds = WorldRegistry(tmp_path).list_worlds()
    assert [w.world_id for w in worlds] == ["world_strict"]


def test_list_worlds_skips_corrupt_files(tmp_path: Path, strict_yaml: Path):
    _write(tmp_path / "broken.yaml", "world_id: missing_version\n")
    worlds = WorldRegistry(tmp_path).list_worlds()
    assert [w.world_id for w in worlds] == ["world_strict"]


def test_list_worlds_empty_dir(tmp_path: Path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert WorldRegistry(empty).list_worlds() == []


def test_list_worlds_missing_dir(tmp_path: Path):
    assert WorldRegistry(tmp_path / "does_not_exist").list_worlds() == []


# ---------------------------------------------------------------------------
# Registry.get
# ---------------------------------------------------------------------------


def test_get_by_id_and_version(registry: WorldRegistry):
    w = registry.get("world_strict", "1.0")
    assert w.world_id == "world_strict"
    assert w.version == "1.0"


def test_get_latest_when_version_omitted(registry: WorldRegistry):
    w = registry.get("world_balanced")  # only one version → returns it
    assert w.world_id == "world_balanced"


def test_get_unknown_id_raises(registry: WorldRegistry):
    with pytest.raises(WorldNotFoundError):
        registry.get("does_not_exist")


def test_get_unknown_version_raises(registry: WorldRegistry):
    with pytest.raises(WorldNotFoundError):
        registry.get("world_strict", "99.0")


def test_get_latest_version_picks_lexicographic_last(tmp_path: Path):
    _write(
        tmp_path / "w_a.yaml",
        "world_id: w\nversion: \"1.0\"\nallowed_actions: [a]\n",
    )
    _write(
        tmp_path / "w_b.yaml",
        "world_id: w\nversion: \"2.0\"\nallowed_actions: [a, b]\n",
    )
    w = WorldRegistry(tmp_path).get("w")
    assert w.version == "2.0"


# ---------------------------------------------------------------------------
# Active-world pointer
# ---------------------------------------------------------------------------


def test_get_active_returns_none_initially(registry: WorldRegistry):
    assert registry.get_active() is None


def test_set_and_get_active(registry: WorldRegistry):
    registry.set_active("world_strict", "1.0")
    active = registry.get_active()
    assert active is not None
    assert active.world_id == "world_strict"
    assert active.version == "1.0"


def test_set_active_fails_on_unknown_target_and_leaves_state_intact(
    registry: WorldRegistry,
):
    registry.set_active("world_strict", "1.0")
    with pytest.raises(WorldNotFoundError):
        registry.set_active("does_not_exist", "1.0")
    # Previous active pointer must still be valid
    active = registry.get_active()
    assert active is not None
    assert active.world_id == "world_strict"


def test_clear_active_removes_pointer(registry: WorldRegistry):
    registry.set_active("world_strict", "1.0")
    registry.clear_active()
    assert registry.get_active() is None


def test_clear_active_when_nothing_set_is_safe(registry: WorldRegistry):
    # must not raise
    registry.clear_active()
    assert registry.get_active() is None


def test_stale_active_pointer_returns_none(
    tmp_path: Path, strict_yaml: Path, balanced_yaml: Path
):
    registry = WorldRegistry(tmp_path)
    registry.set_active("world_strict", "1.0")
    # Delete the world file out from under the pointer
    strict_yaml.unlink()
    # Re-list so the in-memory state reflects the deletion
    assert registry.get_active() is None


def test_corrupt_active_file_returns_none(tmp_path: Path, strict_yaml: Path):
    registry = WorldRegistry(tmp_path)
    (tmp_path / ".active.json").write_text("{not valid json", encoding="utf-8")
    assert registry.get_active() is None


def test_custom_active_file_location(tmp_path: Path, strict_yaml: Path):
    pointer = tmp_path / "pointer.json"
    registry = WorldRegistry(worlds_dir=tmp_path, active_file=pointer)
    registry.set_active("world_strict", "1.0")
    assert pointer.exists()
    assert not (tmp_path / ".active.json").exists()


# ---------------------------------------------------------------------------
# Bundled default registry
# ---------------------------------------------------------------------------


def test_default_registry_exposes_bundled_worlds(tmp_path: Path):
    # Redirect the active-pointer file so tests can't pollute the package dir.
    registry = default_registry(active_file=tmp_path / "active.json")
    ids = {w.world_id for w in registry.list_worlds()}
    assert {"world_strict", "world_balanced"} <= ids
