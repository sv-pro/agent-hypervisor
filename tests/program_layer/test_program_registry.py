"""
tests/program_layer/test_program_registry.py — ProgramRegistry persistence tests.

Coverage:
    1.  store() returns the program's id
    2.  load() round-trip — stored program survives a fresh registry instance
    3.  store() overwrites an existing entry (status update)
    4.  load() raises KeyError for unknown id
    5.  store() rejects non-ReviewedProgram input with TypeError
    6.  directory is created automatically on first store()
    7.  registry directory is durable across process-restart simulation
        (two separate ProgramRegistry instances pointing at the same directory)
    8.  multiple programs stored and retrieved independently
    9.  stored file is valid JSON readable without the registry API
    10. load() raises ValueError for corrupt JSON
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from agent_hypervisor.program_layer.interfaces import ProgramRegistry
from agent_hypervisor.program_layer.review_models import (
    CandidateStep,
    ProgramDiff,
    ProgramMetadata,
    ProgramStatus,
    ReviewedProgram,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _meta() -> ProgramMetadata:
    return ProgramMetadata(
        created_from_trace="trace-001",
        world_version="1.0",
        created_at="2026-01-01T00:00:00+00:00",
        reviewer_notes=None,
    )


def _program(
    prog_id: str = "prog-reg00001",
    status: ProgramStatus = ProgramStatus.PROPOSED,
) -> ReviewedProgram:
    step = CandidateStep(tool="count_words", params={"input": "hello"})
    tup = (step,)
    return ReviewedProgram(
        id=prog_id,
        status=status,
        original_steps=tup,
        minimized_steps=tup,
        diff=ProgramDiff(),
        metadata=_meta(),
    )


def _registry() -> tuple[ProgramRegistry, Path]:
    d = Path(tempfile.mkdtemp())
    return ProgramRegistry(d), d


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestProgramRegistryStore:
    def test_store_returns_program_id(self):
        reg, _ = _registry()
        prog = _program()
        returned_id = reg.store(prog)
        assert returned_id == prog.id

    def test_store_rejects_non_reviewed_program(self):
        reg, _ = _registry()
        with pytest.raises(TypeError, match="ReviewedProgram"):
            reg.store("not a program")  # type: ignore

    def test_store_rejects_none(self):
        reg, _ = _registry()
        with pytest.raises(TypeError, match="ReviewedProgram"):
            reg.store(None)  # type: ignore

    def test_store_creates_directory_automatically(self):
        base = Path(tempfile.mkdtemp())
        new_dir = base / "registry" / "nested"
        assert not new_dir.exists()

        reg = ProgramRegistry(new_dir)
        reg.store(_program())

        assert new_dir.exists()

    def test_store_overwrites_existing_entry(self):
        reg, _ = _registry()
        prog = _program(prog_id="prog-ow00001", status=ProgramStatus.PROPOSED)
        reg.store(prog)

        updated = ReviewedProgram(
            id=prog.id,
            status=ProgramStatus.ACCEPTED,
            original_steps=prog.original_steps,
            minimized_steps=prog.minimized_steps,
            diff=prog.diff,
            metadata=_meta(),
        )
        reg.store(updated)

        loaded = reg.load(prog.id)
        assert loaded.status == ProgramStatus.ACCEPTED


class TestProgramRegistryLoad:
    def test_load_round_trip(self):
        reg, _ = _registry()
        prog = _program()
        reg.store(prog)

        loaded = reg.load(prog.id)

        assert loaded.id == prog.id
        assert loaded.status == prog.status
        assert len(loaded.original_steps) == len(prog.original_steps)
        assert loaded.original_steps[0].tool == prog.original_steps[0].tool

    def test_load_raises_key_error_for_unknown_id(self):
        reg, _ = _registry()
        with pytest.raises(KeyError):
            reg.load("prog-doesnotexist")

    def test_load_raises_value_error_for_corrupt_json(self):
        reg, directory = _registry()
        prog = _program(prog_id="prog-corrupt01")
        reg.store(prog)

        # Corrupt the file after storing
        corrupt_path = directory / f"program_{prog.id}.json"
        corrupt_path.write_text("{ invalid json !!!", encoding="utf-8")

        with pytest.raises(ValueError, match="Corrupt"):
            reg.load(prog.id)


class TestProgramRegistryDurability:
    def test_survives_fresh_registry_instance(self):
        """Two separate ProgramRegistry objects on same dir — simulates restart."""
        d = Path(tempfile.mkdtemp())
        prog = _program(prog_id="prog-dur000001")

        writer = ProgramRegistry(d)
        writer.store(prog)

        reader = ProgramRegistry(d)
        loaded = reader.load(prog.id)

        assert loaded.id == prog.id
        assert loaded.status == prog.status

    def test_stored_file_is_valid_json(self):
        """Registry file must be human-readable without the registry API."""
        _, directory = _registry()
        prog = _program(prog_id="prog-json0001")

        reg = ProgramRegistry(directory)
        reg.store(prog)

        json_file = directory / f"program_{prog.id}.json"
        assert json_file.exists()
        data = json.loads(json_file.read_text(encoding="utf-8"))
        assert data["id"] == prog.id

    def test_multiple_programs_stored_independently(self):
        reg, _ = _registry()
        p1 = _program(prog_id="prog-multi001")
        p2 = _program(prog_id="prog-multi002")
        p3 = _program(prog_id="prog-multi003")

        reg.store(p1)
        reg.store(p2)
        reg.store(p3)

        assert reg.load("prog-multi001").id == "prog-multi001"
        assert reg.load("prog-multi002").id == "prog-multi002"
        assert reg.load("prog-multi003").id == "prog-multi003"

    def test_load_does_not_affect_other_programs(self):
        reg, _ = _registry()
        p1 = _program(prog_id="prog-iso00001")
        p2 = _program(prog_id="prog-iso00002")

        reg.store(p1)
        reg.store(p2)

        # Update p1; p2 must be unchanged
        updated_p1 = ReviewedProgram(
            id=p1.id,
            status=ProgramStatus.REJECTED,
            original_steps=p1.original_steps,
            minimized_steps=p1.minimized_steps,
            diff=p1.diff,
            metadata=_meta(),
        )
        reg.store(updated_p1)

        assert reg.load(p2.id).status == ProgramStatus.PROPOSED
