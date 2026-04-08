"""
test_compiled_world.py — Verify the architecture sync patch.

Checks:
  1. action_space is explicit (frozenset in CompiledWorld)
  2. simulation_bindings are explicit (frozenset subset of action_space)
  3. absent semantics are preserved (absent actions return absence message)
  4. demo can run dry-run without errors (action spaces load and display)
"""

import sys
from pathlib import Path
import pytest

# Make runtime/tools importable
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from runtime.compiled_world import compile_world, CompiledWorld
from runtime.world_switcher import WorldSwitcher
from runtime.audit import AuditLogger
from tools.proxy import WorldProxy

WORLD_DIR = ROOT / "world"


# ---------------------------------------------------------------------------
# 1. action_space is explicit
# ---------------------------------------------------------------------------

def test_raw_world_action_space_is_frozenset():
    cw = compile_world(str(WORLD_DIR / "raw_world.yaml"))
    assert isinstance(cw.action_space, frozenset)


def test_raw_world_action_space_contents():
    cw = compile_world(str(WORLD_DIR / "raw_world.yaml"))
    assert "git_push" in cw.action_space
    assert "read_file" in cw.action_space
    assert "git_push_simulated" not in cw.action_space


def test_rendered_world_action_space_contents():
    cw = compile_world(str(WORLD_DIR / "rendered_world.yaml"))
    assert "read_file" in cw.action_space
    assert "git_push" not in cw.action_space
    assert "write_file" not in cw.action_space
    assert "run_command" not in cw.action_space


def test_simulated_world_action_space_contents():
    cw = compile_world(str(WORLD_DIR / "simulated_world.yaml"))
    assert "git_push_simulated" in cw.action_space
    assert "git_push" not in cw.action_space


def test_compiled_world_is_immutable():
    cw = compile_world(str(WORLD_DIR / "raw_world.yaml"))
    with pytest.raises((AttributeError, TypeError)):
        cw.action_space = frozenset()  # frozen dataclass must reject this


# ---------------------------------------------------------------------------
# 2. simulation_bindings are explicit
# ---------------------------------------------------------------------------

def test_raw_world_has_no_simulation_bindings():
    cw = compile_world(str(WORLD_DIR / "raw_world.yaml"))
    assert isinstance(cw.simulation_bindings, frozenset)
    assert len(cw.simulation_bindings) == 0


def test_rendered_world_all_actions_are_simulation_bound():
    cw = compile_world(str(WORLD_DIR / "rendered_world.yaml"))
    assert cw.simulation_bindings == cw.action_space


def test_simulated_world_all_actions_are_simulation_bound():
    cw = compile_world(str(WORLD_DIR / "simulated_world.yaml"))
    assert cw.simulation_bindings == cw.action_space


def test_simulation_bindings_are_subset_of_action_space():
    for fname in ("raw_world.yaml", "rendered_world.yaml", "simulated_world.yaml"):
        cw = compile_world(str(WORLD_DIR / fname))
        assert cw.simulation_bindings <= cw.action_space, (
            f"{fname}: simulation_bindings not a subset of action_space"
        )


def test_is_simulation_bound_method():
    cw = compile_world(str(WORLD_DIR / "simulated_world.yaml"))
    assert cw.is_simulation_bound("git_push_simulated")
    assert not cw.is_simulation_bound("git_push")  # absent entirely


# ---------------------------------------------------------------------------
# 3. absent semantics are preserved
# ---------------------------------------------------------------------------

def test_absent_action_returns_absence_message():
    cw = compile_world(str(WORLD_DIR / "rendered_world.yaml"))
    switcher = WorldSwitcher()
    switcher.switch(cw)
    audit = AuditLogger(verbose=False)
    proxy = WorldProxy(switcher, audit)

    result = proxy.execute("git_push", {})
    assert "does not exist" in result
    assert "rendered_world" in result
    assert "absent" in result


def test_absent_action_is_logged():
    cw = compile_world(str(WORLD_DIR / "rendered_world.yaml"))
    switcher = WorldSwitcher()
    switcher.switch(cw)
    audit = AuditLogger(verbose=False)
    proxy = WorldProxy(switcher, audit)

    proxy.execute("git_push", {})
    absent_events = [e for e in audit.events if e["event"] == "absent_action"]
    assert len(absent_events) == 1
    assert absent_events[0]["action"] == "git_push"
    assert absent_events[0]["world"] == "rendered_world"


def test_present_action_is_not_absent():
    cw = compile_world(str(WORLD_DIR / "rendered_world.yaml"))
    switcher = WorldSwitcher()
    switcher.switch(cw)
    audit = AuditLogger(verbose=False)
    proxy = WorldProxy(switcher, audit)

    # read_file exists in rendered_world — should not return absence message
    result = proxy.execute("read_file", {"path": "nonexistent_path_xyz.py"})
    assert "does not exist in this Compiled World" not in result


def test_is_present_method():
    cw = compile_world(str(WORLD_DIR / "rendered_world.yaml"))
    assert cw.is_present("read_file")
    assert not cw.is_present("git_push")


# ---------------------------------------------------------------------------
# 4. demo dry-run: all three worlds compile and display without errors
# ---------------------------------------------------------------------------

def test_all_worlds_compile(capsys):
    for fname in ("raw_world.yaml", "rendered_world.yaml", "simulated_world.yaml"):
        cw = compile_world(str(WORLD_DIR / fname))
        assert isinstance(cw, CompiledWorld)
        assert cw.name
        assert len(cw.action_space) > 0


def test_world_switcher_displays_action_space(capsys):
    cw = compile_world(str(WORLD_DIR / "simulated_world.yaml"))
    switcher = WorldSwitcher()
    switcher.switch(cw)
    out = capsys.readouterr().out
    assert "COMPILED WORLD" in out
    assert "ACTION SPACE" in out
    assert "git_push_simulated" in out
    assert "simulation binding" in out


def test_proxy_tool_defs_match_action_space():
    cw = compile_world(str(WORLD_DIR / "rendered_world.yaml"))
    switcher = WorldSwitcher()
    switcher.switch(cw)
    audit = AuditLogger(verbose=False)
    proxy = WorldProxy(switcher, audit)

    defs = proxy.get_anthropic_tool_defs()
    def_names = {d["name"] for d in defs}
    assert def_names == cw.action_space


# ---------------------------------------------------------------------------
# Manifest validation
# ---------------------------------------------------------------------------

def test_missing_action_space_field(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: bad_world\n")
    with pytest.raises(ValueError, match="action_space"):
        compile_world(str(bad))


def test_simulation_bindings_must_be_subset(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "name: bad\n"
        "action_space: [read_file]\n"
        "simulation_bindings: [git_push]\n"
    )
    with pytest.raises(ValueError, match="simulation_bindings"):
        compile_world(str(bad))
