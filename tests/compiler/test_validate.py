"""
tests/compiler/test_validate.py — ahc validate tests (v0.3-T1).

Coverage:
  - Required field detection (v1 and v2)
  - Type checks (reversible must be bool, trust_level must be valid, etc.)
  - Cross-reference validation (entity → data_class, surface → action, zone → zone)
  - Unknown action detection in side_effect_surfaces
  - Budget sanity: per_request/per_session must be positive
  - Budget sanity: warn when budget declared but no model pricing
  - Valid workspace_v2.yaml passes with no errors
  - CLI: ahc validate exits 0 for valid, 1 for errors
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from agent_hypervisor.compiler.validator import validate, ValidationResult


WORKSPACE_V2 = Path(__file__).parent.parent.parent / "manifests" / "workspace_v2.yaml"


def _write_manifest(tmp_path: Path, content: dict | str, name: str = "test.yaml") -> Path:
    p = tmp_path / name
    if isinstance(content, dict):
        p.write_text(yaml.dump(content))
    else:
        p.write_text(content)
    return p


MINIMAL_V2 = {
    "version": "2.0",
    "manifest": {"name": "test-world"},
    "actions": {
        "read_inbox": {
            "reversible": True,
            "side_effects": ["internal_read"],
        }
    },
    "trust_channels": {
        "user": {"trust_level": "TRUSTED", "taint_by_default": False},
    },
    "capability_matrix": {
        "TRUSTED": ["read_only"],
    },
}


# ── File-level errors ──────────────────────────────────────────────────────────

def test_missing_file_returns_error(tmp_path):
    result = validate(tmp_path / "nonexistent.yaml")
    assert not result.ok
    assert any("not found" in e.lower() for e in result.errors)


def test_bad_yaml_returns_error(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("key: [\nunclosed")
    result = validate(p)
    assert not result.ok
    assert any("yaml" in e.lower() for e in result.errors)


# ── v2 required fields ─────────────────────────────────────────────────────────

def test_v2_valid_minimal_passes(tmp_path):
    import copy
    p = _write_manifest(tmp_path, copy.deepcopy(MINIMAL_V2))
    result = validate(p)
    assert result.ok, result.errors


def test_v2_missing_actions_is_error(tmp_path):
    import copy
    m = copy.deepcopy(MINIMAL_V2)
    del m["actions"]
    p = _write_manifest(tmp_path, m)
    result = validate(p)
    assert not result.ok
    assert any("actions" in e for e in result.errors)


def test_v2_missing_trust_channels_is_error(tmp_path):
    import copy
    m = copy.deepcopy(MINIMAL_V2)
    del m["trust_channels"]
    p = _write_manifest(tmp_path, m)
    result = validate(p)
    assert not result.ok
    assert any("trust_channels" in e for e in result.errors)


def test_v2_missing_capability_matrix_is_error(tmp_path):
    import copy
    m = copy.deepcopy(MINIMAL_V2)
    del m["capability_matrix"]
    p = _write_manifest(tmp_path, m)
    result = validate(p)
    assert not result.ok


# ── v2 action validation ───────────────────────────────────────────────────────

def test_v2_action_missing_reversible_is_error(tmp_path):
    import copy
    m = copy.deepcopy(MINIMAL_V2)
    del m["actions"]["read_inbox"]["reversible"]
    p = _write_manifest(tmp_path, m)
    result = validate(p)
    assert not result.ok
    assert any("reversible" in e for e in result.errors)


def test_v2_action_missing_side_effects_is_error(tmp_path):
    import copy
    m = copy.deepcopy(MINIMAL_V2)
    del m["actions"]["read_inbox"]["side_effects"]
    p = _write_manifest(tmp_path, m)
    result = validate(p)
    assert not result.ok
    assert any("side_effects" in e for e in result.errors)


def test_v2_action_unknown_side_effect_is_error(tmp_path):
    import copy
    m = copy.deepcopy(MINIMAL_V2)
    m["actions"]["read_inbox"]["side_effects"] = ["unknown_side_effect"]
    p = _write_manifest(tmp_path, m)
    result = validate(p)
    assert not result.ok
    assert any("unknown_side_effect" in e for e in result.errors)


# ── v2 trust_channels validation ──────────────────────────────────────────────

def test_v2_channel_missing_trust_level_is_error(tmp_path):
    import copy
    m = copy.deepcopy(MINIMAL_V2)
    del m["trust_channels"]["user"]["trust_level"]
    p = _write_manifest(tmp_path, m)
    result = validate(p)
    assert not result.ok
    assert any("trust_level" in e for e in result.errors)


def test_v2_channel_invalid_trust_level_is_error(tmp_path):
    import copy
    m = copy.deepcopy(MINIMAL_V2)
    m["trust_channels"]["user"]["trust_level"] = "SUPER_TRUSTED"
    p = _write_manifest(tmp_path, m)
    result = validate(p)
    assert not result.ok


def test_v2_channel_missing_taint_by_default_is_error(tmp_path):
    import copy
    m = copy.deepcopy(MINIMAL_V2)
    del m["trust_channels"]["user"]["taint_by_default"]
    p = _write_manifest(tmp_path, m)
    result = validate(p)
    assert not result.ok
    assert any("taint_by_default" in e for e in result.errors)


# ── v2 cross-reference validation ─────────────────────────────────────────────

def test_v2_entity_references_undeclared_data_class(tmp_path):
    import copy
    m = copy.deepcopy(MINIMAL_V2)
    m["data_classes"] = {"sensitive": {"taint_label": "high", "confirmation": "required"}}
    m["entities"] = {"inbox": {"type": "document", "data_class": "nonexistent_class"}}
    p = _write_manifest(tmp_path, m)
    result = validate(p)
    assert not result.ok
    assert any("nonexistent_class" in e for e in result.errors)


def test_v2_entity_references_declared_data_class_passes(tmp_path):
    import copy
    m = copy.deepcopy(MINIMAL_V2)
    m["data_classes"] = {"sensitive": {"taint_label": "high", "confirmation": "required"}}
    m["entities"] = {"inbox": {"type": "document", "data_class": "sensitive"}}
    p = _write_manifest(tmp_path, m)
    result = validate(p)
    assert result.ok, result.errors


def test_v2_side_effect_surface_references_undeclared_action(tmp_path):
    import copy
    m = copy.deepcopy(MINIMAL_V2)
    m["side_effect_surfaces"] = {"write_surf": {"action": "nonexistent_action"}}
    p = _write_manifest(tmp_path, m)
    result = validate(p)
    assert not result.ok
    assert any("nonexistent_action" in e for e in result.errors)


def test_v2_side_effect_surface_references_declared_action_passes(tmp_path):
    import copy
    m = copy.deepcopy(MINIMAL_V2)
    m["side_effect_surfaces"] = {"read_surf": {"action": "read_inbox"}}
    p = _write_manifest(tmp_path, m)
    result = validate(p)
    assert result.ok, result.errors


# ── Budget sanity checks ───────────────────────────────────────────────────────

def test_v2_budget_negative_per_request_is_error(tmp_path):
    import copy
    m = copy.deepcopy(MINIMAL_V2)
    m["budgets"] = {"per_request": -0.10}
    p = _write_manifest(tmp_path, m)
    result = validate(p)
    assert not result.ok
    assert any("per_request" in e for e in result.errors)


def test_v2_budget_zero_per_session_is_error(tmp_path):
    import copy
    m = copy.deepcopy(MINIMAL_V2)
    m["budgets"] = {"per_session": 0.0}
    p = _write_manifest(tmp_path, m)
    result = validate(p)
    assert not result.ok


def test_v2_budget_without_model_pricing_warns(tmp_path):
    import copy
    m = copy.deepcopy(MINIMAL_V2)
    m["budgets"] = {"per_request": 0.10, "per_session": 1.0}
    # no economic.model_pricing
    p = _write_manifest(tmp_path, m)
    result = validate(p)
    assert result.ok  # warnings don't block
    assert len(result.warnings) > 0
    assert any("model_pricing" in w for w in result.warnings)


def test_v2_budget_with_model_pricing_no_warning(tmp_path):
    import copy
    m = copy.deepcopy(MINIMAL_V2)
    m["budgets"] = {"per_request": 0.10, "per_session": 1.0}
    m["economic"] = {
        "model_pricing": {
            "claude-sonnet-4-6": {"input_per_1k": 0.003, "output_per_1k": 0.015}
        }
    }
    p = _write_manifest(tmp_path, m)
    result = validate(p)
    assert result.ok, result.errors
    assert len(result.warnings) == 0


# ── workspace_v2.yaml must pass ───────────────────────────────────────────────

def test_workspace_v2_is_valid():
    assert WORKSPACE_V2.exists(), f"workspace_v2.yaml not found at {WORKSPACE_V2}"
    result = validate(WORKSPACE_V2)
    assert result.ok, f"workspace_v2.yaml has errors:\n" + "\n".join(result.errors)


# ── CLI integration ───────────────────────────────────────────────────────────

def test_cli_validate_valid_manifest(tmp_path):
    import copy
    from click.testing import CliRunner
    from agent_hypervisor.compiler.cli import cli

    p = _write_manifest(tmp_path, copy.deepcopy(MINIMAL_V2))
    runner = CliRunner()
    result = runner.invoke(cli, ["validate", str(p)])
    assert result.exit_code == 0, result.output
    assert "✓" in result.output


def test_cli_validate_invalid_manifest_exits_1(tmp_path):
    import copy
    from click.testing import CliRunner
    from agent_hypervisor.compiler.cli import cli

    m = copy.deepcopy(MINIMAL_V2)
    del m["actions"]
    p = _write_manifest(tmp_path, m)
    runner = CliRunner()
    result = runner.invoke(cli, ["validate", str(p)])
    assert result.exit_code == 1
    assert "error" in result.output.lower()


def test_cli_validate_strict_flag_treats_warnings_as_errors(tmp_path):
    import copy
    from click.testing import CliRunner
    from agent_hypervisor.compiler.cli import cli

    m = copy.deepcopy(MINIMAL_V2)
    m["budgets"] = {"per_request": 0.10}  # will warn about missing model_pricing
    p = _write_manifest(tmp_path, m)
    runner = CliRunner()
    result = runner.invoke(cli, ["validate", str(p), "--strict"])
    assert result.exit_code == 2
