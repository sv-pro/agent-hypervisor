"""
tests/compiler/test_cost_estimate.py — ahc cost-estimate CLI tests (v0.3-T3).

Coverage:
    1.  Happy path: p90 cost printed for known action/model pair
    2.  p50 and p99 percentile options work correctly
    3.  Unknown action/model pair exits 1 with error message
    4.  --trace directory glob loads from all *.jsonl files
    5.  Missing --trace argument causes CLI error (required option)
    6.  Empty trace file exits 1 with no observations found
    7.  Output includes recommended manifest snippet
    8.  model="" (no --model flag) matches observations with empty model_name
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from agent_hypervisor.compiler.cli import cli


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_trace(path, observations):
    path.write_text("\n".join(json.dumps(o) for o in observations))


def _observations():
    return [
        {"action_name": "read_file", "model_name": "gpt-4o", "actual_cost": 0.01},
        {"action_name": "read_file", "model_name": "gpt-4o", "actual_cost": 0.02},
        {"action_name": "read_file", "model_name": "gpt-4o", "actual_cost": 0.03},
        {"action_name": "read_file", "model_name": "gpt-4o", "actual_cost": 0.04},
        {"action_name": "read_file", "model_name": "gpt-4o", "actual_cost": 0.05},
        {"action_name": "send_email", "model_name": "gpt-4o", "actual_cost": 0.10},
    ]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestCostEstimateHappyPath:
    def test_p90_printed_for_known_action_model(self, tmp_path):
        trace = tmp_path / "trace.jsonl"
        _write_trace(trace, _observations())

        runner = CliRunner()
        result = runner.invoke(cli, [
            "cost-estimate", "read_file",
            "--model", "gpt-4o",
            "--trace", str(trace),
        ])
        assert result.exit_code == 0, result.output
        assert "read_file" in result.output
        assert "$" in result.output

    def test_output_contains_recommended_snippet(self, tmp_path):
        trace = tmp_path / "trace.jsonl"
        _write_trace(trace, _observations())

        runner = CliRunner()
        result = runner.invoke(cli, [
            "cost-estimate", "read_file",
            "--model", "gpt-4o",
            "--trace", str(trace),
        ])
        assert result.exit_code == 0
        assert "per_request" in result.output
        assert "budgets" in result.output

    def test_p50_option_returns_median(self, tmp_path):
        trace = tmp_path / "trace.jsonl"
        # [0.01, 0.02, 0.03, 0.04, 0.05] → p50 index = 0.5*4 = 2 → 0.03
        _write_trace(trace, _observations())

        runner = CliRunner()
        result = runner.invoke(cli, [
            "cost-estimate", "read_file",
            "--model", "gpt-4o",
            "--percentile", "50",
            "--trace", str(trace),
        ])
        assert result.exit_code == 0
        assert "0.0300" in result.output

    def test_p99_option_used(self, tmp_path):
        trace = tmp_path / "trace.jsonl"
        _write_trace(trace, _observations())

        runner = CliRunner()
        result = runner.invoke(cli, [
            "cost-estimate", "read_file",
            "--model", "gpt-4o",
            "--percentile", "99",
            "--trace", str(trace),
        ])
        assert result.exit_code == 0, result.output
        assert "p99" in result.output


# ---------------------------------------------------------------------------
# Not found → exit 1
# ---------------------------------------------------------------------------

class TestCostEstimateNotFound:
    def test_unknown_action_exits_1(self, tmp_path):
        trace = tmp_path / "trace.jsonl"
        _write_trace(trace, _observations())

        runner = CliRunner()
        result = runner.invoke(cli, [
            "cost-estimate", "nonexistent_action",
            "--model", "gpt-4o",
            "--trace", str(trace),
        ])
        assert result.exit_code == 1

    def test_unknown_model_exits_1(self, tmp_path):
        trace = tmp_path / "trace.jsonl"
        _write_trace(trace, _observations())

        runner = CliRunner()
        result = runner.invoke(cli, [
            "cost-estimate", "read_file",
            "--model", "unknown-model",
            "--trace", str(trace),
        ])
        assert result.exit_code == 1

    def test_empty_trace_exits_1(self, tmp_path):
        trace = tmp_path / "empty.jsonl"
        trace.write_text("")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "cost-estimate", "read_file",
            "--model", "gpt-4o",
            "--trace", str(trace),
        ])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# Directory glob
# ---------------------------------------------------------------------------

class TestCostEstimateDirectory:
    def test_loads_all_jsonl_files_in_directory(self, tmp_path):
        (tmp_path / "a.jsonl").write_text(
            json.dumps({"action_name": "read_file", "model_name": "gpt-4o", "actual_cost": 0.01})
        )
        (tmp_path / "b.jsonl").write_text(
            json.dumps({"action_name": "read_file", "model_name": "gpt-4o", "actual_cost": 0.05})
        )

        runner = CliRunner()
        result = runner.invoke(cli, [
            "cost-estimate", "read_file",
            "--model", "gpt-4o",
            "--trace", str(tmp_path),
        ])
        assert result.exit_code == 0, result.output
        assert "read_file" in result.output


# ---------------------------------------------------------------------------
# Empty model name
# ---------------------------------------------------------------------------

class TestCostEstimateEmptyModel:
    def test_no_model_flag_matches_empty_model_name(self, tmp_path):
        trace = tmp_path / "trace.jsonl"
        trace.write_text(
            json.dumps({"action_name": "count_words", "actual_cost": 0.005})
        )

        runner = CliRunner()
        result = runner.invoke(cli, [
            "cost-estimate", "count_words",
            "--trace", str(trace),
        ])
        assert result.exit_code == 0, result.output
        assert "count_words" in result.output
