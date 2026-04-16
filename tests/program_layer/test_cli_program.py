"""
test_cli_program.py — CLI wrapper tests for PL-3.

Exercises the `awc program ...` subcommands defined in
``agent_hypervisor.compiler.cli``.  Each test invokes the CLI via
``click.testing.CliRunner`` and inspects the exit code and stdout.

The underlying Python API (review_lifecycle, ReplayEngine, ProgramStore)
is covered exhaustively by ``test_review_minimization.py``.  These tests
only verify the thin CLI surface: argument parsing, JSON input handling,
error exit codes, and happy-path end-to-end wiring.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from agent_hypervisor.compiler.cli import cli


def _write_steps_json(path: Path, steps: list[dict]) -> Path:
    path.write_text(json.dumps(steps), encoding="utf-8")
    return path


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def store_dir(tmp_path: Path) -> Path:
    d = tmp_path / "programs"
    d.mkdir()
    return d


@pytest.fixture
def steps_file(tmp_path: Path) -> Path:
    # Two identical consecutive steps (dedup target) + a URL-with-query step
    # (param reduction target).  "count_words" is in SUPPORTED_WORKFLOWS so
    # world validation on accept passes.
    steps = [
        {"tool": "count_words", "params": {"input": "hello world"}},
        {"tool": "count_words", "params": {"input": "hello world"}},  # duplicate
        {
            "tool": "normalize_text",
            "params": {"input": "HELLO", "url": "https://api.example.com/v1?x=1"},
        },
    ]
    return _write_steps_json(tmp_path / "steps.json", steps)


# ---------------------------------------------------------------------------
# propose
# ---------------------------------------------------------------------------


def test_propose_creates_program_and_prints_id(runner, store_dir, steps_file):
    result = runner.invoke(
        cli,
        [
            "program", "propose",
            "--steps-json", str(steps_file),
            "--trace-id", "trace-1",
            "--world-version", "1.0",
            "--store", str(store_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    prog_id = result.output.strip()
    assert prog_id.startswith("prog-")
    assert (store_dir / f"program_{prog_id}.json").exists()


def test_propose_rejects_empty_array(runner, store_dir, tmp_path):
    empty = _write_steps_json(tmp_path / "empty.json", [])
    result = runner.invoke(
        cli,
        [
            "program", "propose",
            "--steps-json", str(empty),
            "--world-version", "1.0",
            "--store", str(store_dir),
        ],
    )
    assert result.exit_code == 1
    assert "non-empty" in result.output.lower()


def test_propose_rejects_invalid_step_schema(runner, store_dir, tmp_path):
    bad = _write_steps_json(tmp_path / "bad.json", [{"not_a_tool": "x"}])
    result = runner.invoke(
        cli,
        [
            "program", "propose",
            "--steps-json", str(bad),
            "--world-version", "1.0",
            "--store", str(store_dir),
        ],
    )
    assert result.exit_code == 1
    assert "invalid step" in result.output.lower()


# ---------------------------------------------------------------------------
# Lifecycle happy path: propose → minimize → review → accept → replay
# ---------------------------------------------------------------------------


def _propose(runner, store_dir, steps_file) -> str:
    result = runner.invoke(
        cli,
        [
            "program", "propose",
            "--steps-json", str(steps_file),
            "--trace-id", "trace-1",
            "--world-version", "1.0",
            "--store", str(store_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    return result.output.strip()


def test_minimize_prints_diff(runner, store_dir, steps_file):
    prog_id = _propose(runner, store_dir, steps_file)
    result = runner.invoke(
        cli,
        ["program", "minimize", "--id", prog_id, "--store", str(store_dir)],
    )
    assert result.exit_code == 0, result.output
    # The duplicate should show up in the diff output
    assert "REMOVED" in result.output
    assert "consecutive duplicate" in result.output


def test_minimize_empty_diff_is_reported(runner, store_dir, tmp_path):
    steps = [{"tool": "count_words", "params": {"input": "hi"}}]
    steps_file = _write_steps_json(tmp_path / "one.json", steps)
    prog_id = _propose(runner, store_dir, steps_file)
    result = runner.invoke(
        cli,
        ["program", "minimize", "--id", prog_id, "--store", str(store_dir)],
    )
    assert result.exit_code == 0, result.output
    assert "no changes" in result.output.lower()


def test_review_transitions_proposed_to_reviewed(runner, store_dir, steps_file):
    prog_id = _propose(runner, store_dir, steps_file)
    runner.invoke(cli, ["program", "minimize", "--id", prog_id, "--store", str(store_dir)])

    result = runner.invoke(
        cli,
        [
            "program", "review", "--id", prog_id,
            "--notes", "looks fine",
            "--store", str(store_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "reviewed" in result.output


def test_accept_requires_reviewed_status(runner, store_dir, steps_file):
    """accept on a PROPOSED program should fail with invalid-transition exit code."""
    prog_id = _propose(runner, store_dir, steps_file)
    result = runner.invoke(
        cli,
        ["program", "accept", "--id", prog_id, "--store", str(store_dir)],
    )
    assert result.exit_code == 2, result.output
    assert "cannot transition" in result.output.lower()


def test_end_to_end_propose_minimize_review_accept_replay(runner, store_dir, steps_file):
    prog_id = _propose(runner, store_dir, steps_file)

    assert runner.invoke(
        cli, ["program", "minimize", "--id", prog_id, "--store", str(store_dir)]
    ).exit_code == 0

    assert runner.invoke(
        cli, ["program", "review", "--id", prog_id, "--store", str(store_dir)]
    ).exit_code == 0

    accept_result = runner.invoke(
        cli, ["program", "accept", "--id", prog_id, "--store", str(store_dir)]
    )
    assert accept_result.exit_code == 0, accept_result.output
    assert "accepted" in accept_result.output

    replay_result = runner.invoke(
        cli, ["program", "replay", "--id", prog_id, "--store", str(store_dir)]
    )
    # Replay may succeed (exit 0) or fail deterministically (exit 4) depending
    # on whether the sandboxed workflow handler produces a usable result in
    # this test environment.  Either way the command must print a valid
    # ProgramTrace dict and never crash.
    assert replay_result.exit_code in (0, 4), replay_result.output
    parsed = json.loads(replay_result.output.splitlines()[-1]) if False else None
    # Stdout contains JSON followed by a trailing newline — parse the whole lot
    # up to the newline-only tail.
    json_text = replay_result.output.strip()
    trace = json.loads(json_text)
    assert trace["program_id"] == prog_id
    assert "step_traces" in trace
    assert "ok" in trace


# ---------------------------------------------------------------------------
# reject
# ---------------------------------------------------------------------------


def test_reject_transitions_reviewed_to_rejected(runner, store_dir, steps_file):
    prog_id = _propose(runner, store_dir, steps_file)
    runner.invoke(cli, ["program", "minimize", "--id", prog_id, "--store", str(store_dir)])
    runner.invoke(cli, ["program", "review", "--id", prog_id, "--store", str(store_dir)])

    result = runner.invoke(
        cli,
        [
            "program", "reject", "--id", prog_id,
            "--reason", "not needed",
            "--store", str(store_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "rejected" in result.output


# ---------------------------------------------------------------------------
# list / show / unknown-id
# ---------------------------------------------------------------------------


def test_list_empty_store(runner, store_dir):
    result = runner.invoke(cli, ["program", "list", "--store", str(store_dir)])
    assert result.exit_code == 0
    assert "no programs" in result.output.lower()


def test_list_shows_saved_programs(runner, store_dir, steps_file):
    prog_id = _propose(runner, store_dir, steps_file)
    result = runner.invoke(cli, ["program", "list", "--store", str(store_dir)])
    assert result.exit_code == 0, result.output
    assert prog_id in result.output
    assert "proposed" in result.output


def test_show_prints_valid_json(runner, store_dir, steps_file):
    prog_id = _propose(runner, store_dir, steps_file)
    result = runner.invoke(
        cli, ["program", "show", "--id", prog_id, "--store", str(store_dir)]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output.strip())
    assert data["id"] == prog_id
    assert data["status"] == "proposed"
    assert len(data["original_steps"]) == 3


@pytest.mark.parametrize(
    "subcommand, extra_args",
    [
        ("minimize", []),
        ("review", []),
        ("accept", []),
        ("reject", []),
        ("replay", []),
        ("show", []),
    ],
)
def test_unknown_id_exits_with_error(runner, store_dir, subcommand, extra_args):
    result = runner.invoke(
        cli,
        ["program", subcommand, "--id", "prog-doesnotexist", "--store", str(store_dir)]
        + extra_args,
    )
    assert result.exit_code != 0
    assert "not found" in result.output.lower()
