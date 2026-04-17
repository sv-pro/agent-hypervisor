"""
test_scenario_cli.py — CLI tests for ``awc scenario ...``.

Exercises the ``scenario`` click subgroup added in SYS-3.  Only the CLI
surface is covered here; the underlying runner/registry/model logic is
validated in dedicated test files.

Covers:

    - ``scenario list`` over a custom directory.
    - ``scenario show`` prints a valid JSON dict.
    - ``scenario run`` exits 6 when worlds diverge; exit 0 when all agree.
    - ``scenario run --json`` emits the machine-readable ScenarioResult.
    - ``scenario run --trace-file`` appends a JSONL entry.
    - ``scenario run`` exits 1 when the scenario_id is unknown.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from agent_hypervisor.compiler.cli import cli


BUNDLED_WORLDS_DIR = (
    Path(__file__).resolve().parents[2]
    / "src" / "agent_hypervisor" / "program_layer" / "worlds"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def worlds_dir(tmp_path: Path) -> Path:
    d = tmp_path / "worlds"
    d.mkdir()
    for y in BUNDLED_WORLDS_DIR.glob("*.yaml"):
        shutil.copy(y, d / y.name)
    return d


@pytest.fixture
def diverging_scenarios_dir(tmp_path: Path) -> Path:
    """A scenarios dir that contains one divergent memory-write scenario."""
    d = tmp_path / "scenarios"
    d.mkdir()
    (d / "memory.yaml").write_text(
        yaml.safe_dump(
            {
                "scenario_id": "memory_write_test",
                "name": "memory write",
                "description": "divergent demo",
                "program_steps": [
                    {"tool": "count_words", "params": {"input": "alpha beta"}},
                    {"tool": "normalize_text", "params": {"input": "HELLO"}},
                ],
                "worlds": [
                    {"world_id": "world_strict", "version": "1.0"},
                    {"world_id": "world_balanced", "version": "1.0"},
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return d


@pytest.fixture
def agreeing_scenarios_dir(tmp_path: Path) -> Path:
    """A scenarios dir where both worlds allow every step (no divergence)."""
    d = tmp_path / "scenarios_agree"
    d.mkdir()
    (d / "agree.yaml").write_text(
        yaml.safe_dump(
            {
                "scenario_id": "both_allow",
                "name": "both allow",
                "program_steps": [
                    {"tool": "count_words", "params": {"input": "alpha beta"}},
                ],
                "worlds": [
                    {"world_id": "world_strict", "version": "1.0"},
                    {"world_id": "world_balanced", "version": "1.0"},
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return d


# ---------------------------------------------------------------------------
# scenario list / show
# ---------------------------------------------------------------------------


def test_scenario_list_empty_dir(runner, tmp_path: Path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = runner.invoke(
        cli, ["scenario", "list", "--scenarios-dir", str(empty)]
    )
    assert result.exit_code == 0, result.output
    assert "(no scenarios)" in result.output


def test_scenario_list_shows_scenarios(runner, diverging_scenarios_dir: Path):
    result = runner.invoke(
        cli, ["scenario", "list", "--scenarios-dir", str(diverging_scenarios_dir)]
    )
    assert result.exit_code == 0, result.output
    assert "memory_write_test" in result.output


def test_scenario_show_emits_valid_json(runner, diverging_scenarios_dir: Path):
    result = runner.invoke(
        cli,
        [
            "scenario", "show", "memory_write_test",
            "--scenarios-dir", str(diverging_scenarios_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output.strip())
    assert data["scenario_id"] == "memory_write_test"
    assert len(data["worlds"]) == 2


def test_scenario_show_unknown_id_exits_nonzero(runner, diverging_scenarios_dir):
    result = runner.invoke(
        cli,
        [
            "scenario", "show", "nope",
            "--scenarios-dir", str(diverging_scenarios_dir),
        ],
    )
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# scenario run — divergence
# ---------------------------------------------------------------------------


def test_scenario_run_divergent_exits_six(
    runner, diverging_scenarios_dir, worlds_dir
):
    result = runner.invoke(
        cli,
        [
            "scenario", "run", "memory_write_test",
            "--scenarios-dir", str(diverging_scenarios_dir),
            "--worlds-dir", str(worlds_dir),
        ],
    )
    # Exit code 6 == worlds disagreed (distinct from other program-layer codes).
    assert result.exit_code == 6, result.output
    # Both worlds and the divergence section must appear in stdout.
    assert "world_strict@1.0" in result.output
    assert "world_balanced@1.0" in result.output
    assert "Divergence" in result.output
    assert "normalize_text" in result.output


def test_scenario_run_agreement_exits_zero(
    runner, agreeing_scenarios_dir, worlds_dir
):
    result = runner.invoke(
        cli,
        [
            "scenario", "run", "both_allow",
            "--scenarios-dir", str(agreeing_scenarios_dir),
            "--worlds-dir", str(worlds_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "worlds agreed" in result.output.lower()


# ---------------------------------------------------------------------------
# scenario run — JSON and trace
# ---------------------------------------------------------------------------


def test_scenario_run_json_emits_result_dict(
    runner, diverging_scenarios_dir, worlds_dir
):
    result = runner.invoke(
        cli,
        [
            "scenario", "run", "memory_write_test",
            "--scenarios-dir", str(diverging_scenarios_dir),
            "--worlds-dir", str(worlds_dir),
            "--json",
        ],
    )
    # Worlds still diverge → exit 6, but JSON must have been emitted first.
    assert result.exit_code == 6, result.output
    data = json.loads(result.output.strip())
    assert data["scenario_id"] == "memory_write_test"
    assert len(data["world_results"]) == 2
    assert data["divergence"]["all_agree"] is False
    # run_id / ran_at present.
    assert data["run_id"].startswith("scn-")
    assert "ran_at" in data


def test_scenario_run_appends_to_trace_file(
    runner, diverging_scenarios_dir, worlds_dir, tmp_path: Path
):
    trace = tmp_path / "traces.jsonl"
    result = runner.invoke(
        cli,
        [
            "scenario", "run", "memory_write_test",
            "--scenarios-dir", str(diverging_scenarios_dir),
            "--worlds-dir", str(worlds_dir),
            "--trace-file", str(trace),
        ],
    )
    assert result.exit_code == 6, result.output
    assert trace.exists()
    lines = [l for l in trace.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["scenario_id"] == "memory_write_test"
    assert "_stored_at" in entry


# ---------------------------------------------------------------------------
# Unknown scenario
# ---------------------------------------------------------------------------


def test_scenario_run_unknown_exits_nonzero(
    runner, diverging_scenarios_dir, worlds_dir
):
    result = runner.invoke(
        cli,
        [
            "scenario", "run", "does_not_exist",
            "--scenarios-dir", str(diverging_scenarios_dir),
            "--worlds-dir", str(worlds_dir),
        ],
    )
    assert result.exit_code != 0
    assert "not found" in result.output.lower()
