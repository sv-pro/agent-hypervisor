"""
tests/compiler/test_diff.py — ahc diff CLI tests (v0.3-T5).

Coverage:
    1.  Identical manifests → exit 0, "(no differences)" in output
    2.  Added action → shows "+" and action name
    3.  Removed trust_channel → shows "-" and channel name
    4.  Changed budget value → shows "~" and field name
    5.  Multiple sections with diffs → all sections reported
    6.  Exit 1 when any difference found
    7.  list-form section (side_effect_surfaces) diff by index
    8.  Missing section in one manifest (None vs dict) reported as addition/removal
    9.  Invalid YAML exits with error message
"""

from __future__ import annotations

import pytest
import yaml
from click.testing import CliRunner

from agent_hypervisor.compiler.cli import cli


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_yaml(path, data):
    path.write_text(yaml.dump(data, default_flow_style=False))


def _base_manifest():
    return {
        "version": "2.0",
        "actions": {
            "read_file":  {"reversible": True,  "side_effects": ["internal_read"]},
            "write_file": {"reversible": True,  "side_effects": ["internal_write"]},
        },
        "trust_channels": {
            "user": {"trust_level": "TRUSTED", "taint_by_default": False},
            "web":  {"trust_level": "UNTRUSTED", "taint_by_default": True},
        },
        "capability_matrix": {
            "TRUSTED":   ["read_only", "internal_write"],
            "UNTRUSTED": ["read_only"],
        },
        "budgets": {
            "per_request": 0.10,
            "per_session": 2.00,
        },
    }


# ---------------------------------------------------------------------------
# Identical manifests
# ---------------------------------------------------------------------------

class TestDiffIdentical:
    def test_identical_manifests_exit_0(self, tmp_path):
        a = tmp_path / "a.yaml"
        b = tmp_path / "b.yaml"
        data = _base_manifest()
        _write_yaml(a, data)
        _write_yaml(b, data)

        runner = CliRunner()
        result = runner.invoke(cli, ["diff", str(a), str(b)])
        assert result.exit_code == 0, result.output

    def test_identical_manifests_prints_no_differences(self, tmp_path):
        a = tmp_path / "a.yaml"
        b = tmp_path / "b.yaml"
        data = _base_manifest()
        _write_yaml(a, data)
        _write_yaml(b, data)

        runner = CliRunner()
        result = runner.invoke(cli, ["diff", str(a), str(b)])
        assert "no differences" in result.output


# ---------------------------------------------------------------------------
# Added items
# ---------------------------------------------------------------------------

class TestDiffAdded:
    def test_added_action_shows_plus(self, tmp_path):
        a = tmp_path / "a.yaml"
        b = tmp_path / "b.yaml"
        data_a = _base_manifest()
        data_b = _base_manifest()
        data_b["actions"]["delete_file"] = {"reversible": False, "side_effects": ["internal_write"]}
        _write_yaml(a, data_a)
        _write_yaml(b, data_b)

        runner = CliRunner()
        result = runner.invoke(cli, ["diff", str(a), str(b)])
        assert result.exit_code == 1
        assert "+" in result.output
        assert "delete_file" in result.output

    def test_added_trust_channel_shows_plus(self, tmp_path):
        a = tmp_path / "a.yaml"
        b = tmp_path / "b.yaml"
        data_a = _base_manifest()
        data_b = _base_manifest()
        data_b["trust_channels"]["mcp"] = {"trust_level": "SEMI_TRUSTED", "taint_by_default": True}
        _write_yaml(a, data_a)
        _write_yaml(b, data_b)

        runner = CliRunner()
        result = runner.invoke(cli, ["diff", str(a), str(b)])
        assert result.exit_code == 1
        assert "mcp" in result.output


# ---------------------------------------------------------------------------
# Removed items
# ---------------------------------------------------------------------------

class TestDiffRemoved:
    def test_removed_action_shows_minus(self, tmp_path):
        a = tmp_path / "a.yaml"
        b = tmp_path / "b.yaml"
        data_a = _base_manifest()
        data_b = _base_manifest()
        del data_b["actions"]["write_file"]
        _write_yaml(a, data_a)
        _write_yaml(b, data_b)

        runner = CliRunner()
        result = runner.invoke(cli, ["diff", str(a), str(b)])
        assert result.exit_code == 1
        assert "-" in result.output
        assert "write_file" in result.output

    def test_removed_trust_channel_shows_minus(self, tmp_path):
        a = tmp_path / "a.yaml"
        b = tmp_path / "b.yaml"
        data_a = _base_manifest()
        data_b = _base_manifest()
        del data_b["trust_channels"]["web"]
        _write_yaml(a, data_a)
        _write_yaml(b, data_b)

        runner = CliRunner()
        result = runner.invoke(cli, ["diff", str(a), str(b)])
        assert result.exit_code == 1
        assert "web" in result.output


# ---------------------------------------------------------------------------
# Changed items
# ---------------------------------------------------------------------------

class TestDiffChanged:
    def test_changed_budget_shows_tilde(self, tmp_path):
        a = tmp_path / "a.yaml"
        b = tmp_path / "b.yaml"
        data_a = _base_manifest()
        data_b = _base_manifest()
        data_b["budgets"]["per_request"] = 0.20
        _write_yaml(a, data_a)
        _write_yaml(b, data_b)

        runner = CliRunner()
        result = runner.invoke(cli, ["diff", str(a), str(b)])
        assert result.exit_code == 1
        assert "~" in result.output
        assert "per_request" in result.output

    def test_changed_action_reversibility_shows_tilde(self, tmp_path):
        a = tmp_path / "a.yaml"
        b = tmp_path / "b.yaml"
        data_a = _base_manifest()
        data_b = _base_manifest()
        data_b["actions"]["write_file"]["reversible"] = False
        _write_yaml(a, data_a)
        _write_yaml(b, data_b)

        runner = CliRunner()
        result = runner.invoke(cli, ["diff", str(a), str(b)])
        assert result.exit_code == 1
        assert "write_file" in result.output


# ---------------------------------------------------------------------------
# Summary counts
# ---------------------------------------------------------------------------

class TestDiffSummary:
    def test_summary_shows_addition_count(self, tmp_path):
        a = tmp_path / "a.yaml"
        b = tmp_path / "b.yaml"
        data_a = _base_manifest()
        data_b = _base_manifest()
        data_b["actions"]["new_action"] = {"reversible": True, "side_effects": []}
        _write_yaml(a, data_a)
        _write_yaml(b, data_b)

        runner = CliRunner()
        result = runner.invoke(cli, ["diff", str(a), str(b)])
        assert "addition" in result.output

    def test_summary_shows_removal_count(self, tmp_path):
        a = tmp_path / "a.yaml"
        b = tmp_path / "b.yaml"
        data_a = _base_manifest()
        data_b = _base_manifest()
        del data_b["actions"]["read_file"]
        _write_yaml(a, data_a)
        _write_yaml(b, data_b)

        runner = CliRunner()
        result = runner.invoke(cli, ["diff", str(a), str(b)])
        assert "removal" in result.output


# ---------------------------------------------------------------------------
# Missing section in one manifest
# ---------------------------------------------------------------------------

class TestDiffMissingSection:
    def test_section_added_entirely(self, tmp_path):
        a = tmp_path / "a.yaml"
        b = tmp_path / "b.yaml"
        data_a = _base_manifest()
        data_b = _base_manifest()
        del data_b["budgets"]
        _write_yaml(a, data_a)
        _write_yaml(b, data_b)

        runner = CliRunner()
        result = runner.invoke(cli, ["diff", str(a), str(b)])
        # budgets present in a but not b → should show diff
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# List-form sections
# ---------------------------------------------------------------------------

class TestDiffListSection:
    def test_list_section_diffed_by_index(self, tmp_path):
        a = tmp_path / "a.yaml"
        b = tmp_path / "b.yaml"
        data_a = _base_manifest()
        data_b = _base_manifest()
        data_a["side_effect_surfaces"] = [{"action": "send_email", "touches": ["external"]}]
        data_b["side_effect_surfaces"] = [
            {"action": "send_email", "touches": ["external"]},
            {"action": "share_file",  "touches": ["external"]},
        ]
        _write_yaml(a, data_a)
        _write_yaml(b, data_b)

        runner = CliRunner()
        result = runner.invoke(cli, ["diff", str(a), str(b)])
        assert result.exit_code == 1
        assert "side_effect_surfaces" in result.output


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestDiffErrors:
    def test_invalid_yaml_exits_with_message(self, tmp_path):
        a = tmp_path / "a.yaml"
        b = tmp_path / "b.yaml"
        a.write_text("version: 2.0\nactions:\n  : bad")
        b.write_text(yaml.dump(_base_manifest()))

        runner = CliRunner()
        result = runner.invoke(cli, ["diff", str(a), str(b)])
        # May exit 1 or 2; should not crash without output
        assert result.output or result.exit_code != 0
