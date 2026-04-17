"""
test_scenario_registry.py — YAML-backed scenario registry tests.

Covers:

- Round-trip of a valid scenario YAML through ``load_scenario_from_yaml``.
- Programmatic ``to_dict → YAML text → load_scenario_from_yaml`` equivalence
  (scenario authoring and scenario loading agree on the schema).
- ``ScenarioRegistry.get`` resolves known ids and raises
  ``ScenarioNotFoundError`` for unknown ids.
- ``list_scenarios`` returns scenarios sorted by id and skips non-YAML files.
- Malformed YAML raises ``ScenarioLoadError`` with a useful message.
- The bundled registry contains the two demo scenarios.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from agent_hypervisor.program_layer import (
    Scenario,
    ScenarioLoadError,
    ScenarioNotFoundError,
    ScenarioRegistry,
    WorldRef,
    default_scenario_registry,
    load_scenario_from_yaml,
)
from agent_hypervisor.program_layer.review_models import CandidateStep


BUNDLED_SCENARIOS_DIR = (
    Path(__file__).resolve().parents[2]
    / "src" / "agent_hypervisor" / "program_layer" / "scenarios"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_yaml(path: Path, data: dict) -> Path:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def _minimal_yaml() -> dict:
    return {
        "scenario_id": "unit_test",
        "name": "Unit test scenario",
        "description": "tiny demo",
        "program_steps": [
            {"tool": "count_words", "params": {"input": "alpha beta"}},
        ],
        "worlds": [
            {"world_id": "world_strict", "version": "1.0"},
            {"world_id": "world_balanced", "version": "1.0"},
        ],
    }


# ---------------------------------------------------------------------------
# Load / round-trip
# ---------------------------------------------------------------------------


def test_load_scenario_from_yaml_happy_path(tmp_path: Path):
    path = _write_yaml(tmp_path / "s.yaml", _minimal_yaml())
    scenario = load_scenario_from_yaml(path)

    assert isinstance(scenario, Scenario)
    assert scenario.scenario_id == "unit_test"
    assert scenario.name == "Unit test scenario"
    assert scenario.description == "tiny demo"
    assert scenario.worlds == (
        WorldRef("world_strict", "1.0"),
        WorldRef("world_balanced", "1.0"),
    )
    assert scenario.program_steps is not None
    assert scenario.program_steps[0] == CandidateStep(
        tool="count_words", params={"input": "alpha beta"}
    )
    assert scenario.program_id is None


def test_load_missing_file_raises(tmp_path: Path):
    with pytest.raises(ScenarioLoadError, match="not found"):
        load_scenario_from_yaml(tmp_path / "nope.yaml")


def test_load_invalid_yaml_raises(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(":\n  - this is: not: valid: yaml:\n    garbage", encoding="utf-8")
    with pytest.raises(ScenarioLoadError):
        load_scenario_from_yaml(bad)


def test_load_missing_required_field_raises(tmp_path: Path):
    data = _minimal_yaml()
    del data["worlds"]
    path = _write_yaml(tmp_path / "s.yaml", data)
    with pytest.raises(ScenarioLoadError, match="worlds"):
        load_scenario_from_yaml(path)


def test_load_rejects_single_world(tmp_path: Path):
    data = _minimal_yaml()
    data["worlds"] = [data["worlds"][0]]
    path = _write_yaml(tmp_path / "s.yaml", data)
    with pytest.raises(ScenarioLoadError):
        load_scenario_from_yaml(path)


def test_load_rejects_latest_version(tmp_path: Path):
    data = _minimal_yaml()
    data["worlds"][0]["version"] = "latest"
    path = _write_yaml(tmp_path / "s.yaml", data)
    with pytest.raises(ScenarioLoadError):
        load_scenario_from_yaml(path)


def test_round_trip_via_to_dict(tmp_path: Path):
    """Authoring path: build a Scenario in code, dump to YAML, reload."""
    s = Scenario(
        scenario_id="rt",
        name="round trip",
        description="d",
        worlds=(
            WorldRef("world_strict", "1.0"),
            WorldRef("world_balanced", "1.0"),
        ),
        program_steps=(
            CandidateStep(tool="count_words", params={"input": "x"}),
        ),
    )
    path = tmp_path / "rt.yaml"
    path.write_text(yaml.safe_dump(s.to_dict(), sort_keys=False), encoding="utf-8")
    loaded = load_scenario_from_yaml(path)
    # Authoring and loading must agree on the wire-level representation.
    assert loaded.to_dict() == s.to_dict()


# ---------------------------------------------------------------------------
# ScenarioRegistry
# ---------------------------------------------------------------------------


def test_registry_list_scenarios_sorted(tmp_path: Path):
    _write_yaml(tmp_path / "b.yaml", {**_minimal_yaml(), "scenario_id": "b_scn"})
    _write_yaml(tmp_path / "a.yaml", {**_minimal_yaml(), "scenario_id": "a_scn"})
    # Non-YAML file should be ignored.
    (tmp_path / "notes.txt").write_text("ignore me", encoding="utf-8")
    # Dotfile should be ignored.
    (tmp_path / ".hidden.yaml").write_text("garbage", encoding="utf-8")

    reg = ScenarioRegistry(tmp_path)
    scenarios = reg.list_scenarios()
    assert [s.scenario_id for s in scenarios] == ["a_scn", "b_scn"]


def test_registry_get_returns_scenario(tmp_path: Path):
    _write_yaml(tmp_path / "s.yaml", _minimal_yaml())
    reg = ScenarioRegistry(tmp_path)
    s = reg.get("unit_test")
    assert s.scenario_id == "unit_test"


def test_registry_get_unknown_raises_not_found(tmp_path: Path):
    _write_yaml(tmp_path / "s.yaml", _minimal_yaml())
    reg = ScenarioRegistry(tmp_path)
    with pytest.raises(ScenarioNotFoundError):
        reg.get("nope")


def test_registry_missing_directory_raises_not_found(tmp_path: Path):
    reg = ScenarioRegistry(tmp_path / "no_such_dir")
    assert reg.list_scenarios() == []
    with pytest.raises(ScenarioNotFoundError):
        reg.get("any")


# ---------------------------------------------------------------------------
# Bundled scenarios
# ---------------------------------------------------------------------------


def test_default_registry_ships_two_scenarios():
    reg = default_scenario_registry()
    ids = sorted(s.scenario_id for s in reg.list_scenarios())
    assert ids == ["external_call_test", "memory_write_test"]


def test_default_registry_scenarios_parse_clean():
    reg = default_scenario_registry()
    for scenario_id in ("external_call_test", "memory_write_test"):
        s = reg.get(scenario_id)
        assert len(s.worlds) == 2
        assert s.program_steps is not None
        assert len(s.program_steps) >= 1


def test_bundled_scenarios_dir_matches():
    reg = default_scenario_registry()
    assert reg.scenarios_dir == BUNDLED_SCENARIOS_DIR
