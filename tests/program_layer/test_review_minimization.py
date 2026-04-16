"""
tests/program_layer/test_review_minimization.py — PL-3 test suite.

Coverage:
    1.  CandidateStep construction — valid, empty tool, non-dict params
    2.  CandidateStep serialization — to_dict / from_dict round-trip
    3.  ProgramDiff — empty diff, is_empty, to_dict / from_dict round-trip
    4.  ReviewedProgram construction — valid, type errors, minimized > original
    5.  ReviewedProgram serialization — to_dict / from_dict round-trip
    6.  Minimizer — no-op (already minimal), consecutive duplicate removal,
        None param removal, empty-string param removal, URL query stripping,
        capability surface narrowing, combined rules
    7.  ProgramStore — save/load round-trip, list_ids, list_all, nonexistent
    8.  propose_program — creates PROPOSED, identity minimized_steps
    9.  minimize_program — applies minimization, original_steps unchanged
    10. review_program — PROPOSED → REVIEWED, notes attached
    11. accept_program — REVIEWED → ACCEPTED, world validation enforced
    12. reject_program — REVIEWED → REJECTED, reason in notes
    13. Status transition enforcement — invalid transitions raise errors
    14. WorldValidationError — accept rejects unknown tools
    15. ReplayEngine — success, world-validation failure, empty minimized steps
    16. Determinism — same input always produces same minimized output
"""

from __future__ import annotations

import dataclasses
import json
import tempfile
from pathlib import Path

import pytest

from agent_hypervisor.program_layer.minimizer import Minimizer
from agent_hypervisor.program_layer.program_runner import ProgramRunner
from agent_hypervisor.program_layer.program_store import ProgramStore
from agent_hypervisor.program_layer.replay_engine import ReplayEngine
from agent_hypervisor.program_layer.review_lifecycle import (
    InvalidTransitionError,
    WorldValidationError,
    accept_program,
    minimize_program,
    propose_program,
    reject_program,
    review_program,
)
from agent_hypervisor.program_layer.review_models import (
    CapabilityChange,
    CandidateStep,
    ParamChange,
    ProgramDiff,
    ProgramMetadata,
    ProgramStatus,
    RemovedStep,
    ReviewedProgram,
    make_program_id,
)
from agent_hypervisor.program_layer.task_compiler import DeterministicTaskCompiler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_step(tool: str = "count_words", **params) -> CandidateStep:
    return CandidateStep(tool=tool, params=dict(params))


def make_metadata(
    trace_id: str | None = "trace-001",
    world_version: str = "1.0",
) -> ProgramMetadata:
    return ProgramMetadata(
        created_from_trace=trace_id,
        world_version=world_version,
        created_at="2026-01-01T00:00:00+00:00",
        reviewer_notes=None,
    )


def make_reviewed(
    steps: list[CandidateStep] | None = None,
    status: ProgramStatus = ProgramStatus.PROPOSED,
    program_id: str = "prog-test001",
) -> ReviewedProgram:
    if steps is None:
        steps = [make_step()]
    tup = tuple(steps)
    return ReviewedProgram(
        id=program_id,
        status=status,
        original_steps=tup,
        minimized_steps=tup,
        diff=ProgramDiff(),
        metadata=make_metadata(),
    )


def tmp_store() -> ProgramStore:
    """Return a ProgramStore backed by a fresh temp directory."""
    d = tempfile.mkdtemp()
    return ProgramStore(d)


# ---------------------------------------------------------------------------
# 1. CandidateStep construction
# ---------------------------------------------------------------------------


class TestCandidateStep:
    def test_valid_step(self):
        s = CandidateStep(tool="count_words")
        assert s.tool == "count_words"
        assert s.params == {}
        assert s.provenance is None
        assert s.capabilities_used is None

    def test_step_with_params(self):
        s = CandidateStep(tool="count_words", params={"input": "hello"})
        assert s.params["input"] == "hello"

    def test_step_with_provenance_and_caps(self):
        s = CandidateStep(
            tool="http_request",
            params={"url": "https://example.com"},
            provenance="trace-abc",
            capabilities_used=("http_request:any",),
        )
        assert s.provenance == "trace-abc"
        assert s.capabilities_used == ("http_request:any",)

    def test_empty_tool_raises(self):
        with pytest.raises(ValueError, match="non-empty string"):
            CandidateStep(tool="")

    def test_whitespace_tool_raises(self):
        with pytest.raises(ValueError, match="non-empty string"):
            CandidateStep(tool="   ")

    def test_non_dict_params_raises(self):
        with pytest.raises(TypeError, match="dict"):
            CandidateStep(tool="count_words", params=["a", "b"])  # type: ignore

    def test_frozen(self):
        s = CandidateStep(tool="count_words")
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            s.tool = "other"  # type: ignore


# ---------------------------------------------------------------------------
# 2. CandidateStep serialization
# ---------------------------------------------------------------------------


class TestCandidateStepSerialization:
    def test_to_dict_minimal(self):
        s = CandidateStep(tool="count_words")
        d = s.to_dict()
        assert d["tool"] == "count_words"
        assert d["params"] == {}
        assert d["provenance"] is None
        assert d["capabilities_used"] is None

    def test_round_trip(self):
        s = CandidateStep(
            tool="http_request",
            params={"url": "https://api.example.com/v1"},
            provenance="trace-xyz",
            capabilities_used=("http_request:api.example.com/*",),
        )
        restored = CandidateStep.from_dict(s.to_dict())
        assert restored.tool == s.tool
        assert restored.params == s.params
        assert restored.provenance == s.provenance
        assert restored.capabilities_used == s.capabilities_used

    def test_capabilities_serialized_as_list(self):
        s = CandidateStep(tool="read", capabilities_used=("read:local",))
        d = s.to_dict()
        assert isinstance(d["capabilities_used"], list)

    def test_from_dict_restores_caps_as_tuple(self):
        data = {"tool": "read", "params": {}, "provenance": None, "capabilities_used": ["read:local"]}
        s = CandidateStep.from_dict(data)
        assert isinstance(s.capabilities_used, tuple)


# ---------------------------------------------------------------------------
# 3. ProgramDiff
# ---------------------------------------------------------------------------


class TestProgramDiff:
    def test_empty_diff(self):
        d = ProgramDiff()
        assert d.is_empty
        assert d.removed_steps == ()
        assert d.param_changes == ()
        assert d.capability_reduction == ()

    def test_non_empty_diff(self):
        d = ProgramDiff(
            removed_steps=(RemovedStep(index=1, tool="count_words", reason="duplicate"),)
        )
        assert not d.is_empty

    def test_round_trip(self):
        diff = ProgramDiff(
            removed_steps=(RemovedStep(index=2, tool="normalize_text", reason="dup"),),
            param_changes=(
                ParamChange(step_index=0, field="url", before="https://x.com?q=1", after="https://x.com", reason="stripped qs"),
            ),
            capability_reduction=(
                CapabilityChange(step_index=0, before="http:any", after="http:x.com/*", reason="narrowed"),
            ),
        )
        restored = ProgramDiff.from_dict(diff.to_dict())
        assert restored.removed_steps[0].index == 2
        assert restored.param_changes[0].field == "url"
        assert restored.capability_reduction[0].before == "http:any"

    def test_json_serializable(self):
        diff = ProgramDiff(
            removed_steps=(RemovedStep(index=0, tool="t", reason="r"),)
        )
        json.dumps(diff.to_dict())  # must not raise


# ---------------------------------------------------------------------------
# 4. ReviewedProgram construction
# ---------------------------------------------------------------------------


class TestReviewedProgram:
    def test_valid(self):
        p = make_reviewed()
        assert p.id == "prog-test001"
        assert p.status == ProgramStatus.PROPOSED
        assert len(p.original_steps) == 1

    def test_empty_id_raises(self):
        with pytest.raises(ValueError, match="non-empty string"):
            make_reviewed(program_id="")

    def test_empty_original_steps_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            ReviewedProgram(
                id="prog-x",
                status=ProgramStatus.PROPOSED,
                original_steps=(),
                minimized_steps=(),
                diff=ProgramDiff(),
                metadata=make_metadata(),
            )

    def test_original_steps_not_tuple_raises(self):
        with pytest.raises(TypeError, match="tuple"):
            ReviewedProgram(
                id="prog-x",
                status=ProgramStatus.PROPOSED,
                original_steps=[make_step()],  # type: ignore
                minimized_steps=(),
                diff=ProgramDiff(),
                metadata=make_metadata(),
            )

    def test_minimized_longer_than_original_raises(self):
        step = make_step()
        with pytest.raises(ValueError, match="cannot have more steps"):
            ReviewedProgram(
                id="prog-x",
                status=ProgramStatus.PROPOSED,
                original_steps=(step,),
                minimized_steps=(step, step),
                diff=ProgramDiff(),
                metadata=make_metadata(),
            )

    def test_wrong_diff_type_raises(self):
        with pytest.raises(TypeError, match="ProgramDiff"):
            ReviewedProgram(
                id="prog-x",
                status=ProgramStatus.PROPOSED,
                original_steps=(make_step(),),
                minimized_steps=(make_step(),),
                diff="not-a-diff",  # type: ignore
                metadata=make_metadata(),
            )

    def test_frozen(self):
        p = make_reviewed()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            p.status = ProgramStatus.ACCEPTED  # type: ignore


# ---------------------------------------------------------------------------
# 5. ReviewedProgram serialization
# ---------------------------------------------------------------------------


class TestReviewedProgramSerialization:
    def test_round_trip(self):
        p = make_reviewed(
            steps=[
                CandidateStep(
                    tool="count_words",
                    params={"input": "hello world"},
                    provenance="trace-01",
                )
            ]
        )
        restored = ReviewedProgram.from_dict(p.to_dict())
        assert restored.id == p.id
        assert restored.status == p.status
        assert len(restored.original_steps) == 1
        assert restored.original_steps[0].tool == "count_words"

    def test_json_serializable(self):
        p = make_reviewed()
        json.dumps(p.to_dict())

    def test_status_as_string_in_dict(self):
        p = make_reviewed()
        assert p.to_dict()["status"] == "proposed"


# ---------------------------------------------------------------------------
# 6. Minimizer
# ---------------------------------------------------------------------------


class TestMinimizer:
    def setup_method(self):
        self.m = Minimizer()

    def test_no_op_already_minimal(self):
        steps = [CandidateStep(tool="count_words", params={"input": "hello"})]
        minimized, diff = self.m.minimize(steps)
        assert len(minimized) == 1
        assert diff.is_empty

    def test_consecutive_duplicate_removed(self):
        step = CandidateStep(tool="count_words", params={"input": "hi"})
        minimized, diff = self.m.minimize([step, step])
        assert len(minimized) == 1
        assert len(diff.removed_steps) == 1
        assert diff.removed_steps[0].index == 1
        assert "duplicate" in diff.removed_steps[0].reason

    def test_non_consecutive_duplicates_kept(self):
        a = CandidateStep(tool="count_words", params={"input": "hi"})
        b = CandidateStep(tool="normalize_text", params={"input": "HI"})
        minimized, diff = self.m.minimize([a, b, a])
        assert len(minimized) == 3
        assert diff.is_empty

    def test_three_consecutive_duplicates(self):
        step = CandidateStep(tool="count_lines", params={"input": "x"})
        minimized, diff = self.m.minimize([step, step, step])
        assert len(minimized) == 1
        assert len(diff.removed_steps) == 2

    def test_none_param_removed(self):
        step = CandidateStep(tool="count_words", params={"input": "hi", "extra": None})
        minimized, diff = self.m.minimize([step])
        assert "extra" not in minimized[0].params
        assert len(diff.param_changes) == 1
        assert diff.param_changes[0].field == "extra"
        assert "None" in diff.param_changes[0].reason

    def test_empty_string_param_removed(self):
        step = CandidateStep(tool="count_words", params={"input": "hi", "tag": ""})
        minimized, diff = self.m.minimize([step])
        assert "tag" not in minimized[0].params
        assert any(c.field == "tag" for c in diff.param_changes)

    def test_url_query_string_stripped(self):
        step = CandidateStep(
            tool="http_request",
            params={"url": "https://api.example.com/v1/users?id=123&token=abc"},
        )
        minimized, diff = self.m.minimize([step])
        assert minimized[0].params["url"] == "https://api.example.com/v1/users"
        assert len(diff.param_changes) == 1
        assert diff.param_changes[0].before == "https://api.example.com/v1/users?id=123&token=abc"
        assert diff.param_changes[0].after == "https://api.example.com/v1/users"

    def test_url_without_query_not_changed(self):
        step = CandidateStep(
            tool="http_request",
            params={"url": "https://api.example.com/v1/users"},
        )
        minimized, diff = self.m.minimize([step])
        assert minimized[0].params["url"] == "https://api.example.com/v1/users"
        assert diff.is_empty

    def test_url_fragment_stripped(self):
        step = CandidateStep(
            tool="http_request",
            params={"url": "https://example.com/page#section"},
        )
        minimized, diff = self.m.minimize([step])
        assert "#" not in minimized[0].params["url"]

    def test_capability_narrowed_from_any(self):
        step = CandidateStep(
            tool="http_request",
            params={"url": "https://api.example.com/data"},
            capabilities_used=("http_request:any",),
        )
        minimized, diff = self.m.minimize([step])
        assert minimized[0].capabilities_used == ("http_request:api.example.com/*",)
        assert len(diff.capability_reduction) == 1
        assert diff.capability_reduction[0].before == "http_request:any"
        assert diff.capability_reduction[0].after == "http_request:api.example.com/*"

    def test_non_broad_capability_unchanged(self):
        step = CandidateStep(
            tool="http_request",
            params={"url": "https://api.example.com/data"},
            capabilities_used=("http_request:api.example.com/*",),
        )
        minimized, diff = self.m.minimize([step])
        assert minimized[0].capabilities_used == ("http_request:api.example.com/*",)
        assert len(diff.capability_reduction) == 0

    def test_no_capability_narrowing_without_url(self):
        step = CandidateStep(
            tool="do_thing",
            params={"input": "hello"},
            capabilities_used=("do_thing:any",),
        )
        minimized, diff = self.m.minimize([step])
        # No URL in params, so cannot narrow — cap stays as-is
        assert minimized[0].capabilities_used == ("do_thing:any",)
        assert len(diff.capability_reduction) == 0

    def test_original_steps_not_mutated(self):
        step = CandidateStep(
            tool="count_words",
            params={"input": "hello", "extra": None},
        )
        original = [step]
        self.m.minimize(original)
        assert original[0].params == {"input": "hello", "extra": None}

    def test_non_list_input_raises(self):
        with pytest.raises(TypeError, match="list"):
            self.m.minimize((make_step(),))  # type: ignore

    def test_wrong_element_type_raises(self):
        with pytest.raises(TypeError, match="CandidateStep"):
            self.m.minimize(["not-a-step"])  # type: ignore

    def test_deterministic(self):
        steps = [
            CandidateStep(tool="count_words", params={"input": "a", "x": None}),
            CandidateStep(tool="count_words", params={"input": "a", "x": None}),
            CandidateStep(tool="http_request", params={"url": "https://x.com?q=1"}),
        ]
        r1_steps, r1_diff = self.m.minimize(steps)
        r2_steps, r2_diff = self.m.minimize(steps)
        assert [s.to_dict() for s in r1_steps] == [s.to_dict() for s in r2_steps]
        assert r1_diff.to_dict() == r2_diff.to_dict()

    def test_empty_steps_list(self):
        minimized, diff = self.m.minimize([])
        assert minimized == []
        assert diff.is_empty


# ---------------------------------------------------------------------------
# 7. ProgramStore
# ---------------------------------------------------------------------------


class TestProgramStore:
    def test_save_and_load_round_trip(self):
        store = tmp_store()
        prog = make_reviewed()
        store.save(prog)
        loaded = store.load(prog.id)
        assert loaded.id == prog.id
        assert loaded.status == prog.status

    def test_load_nonexistent_raises_key_error(self):
        store = tmp_store()
        with pytest.raises(KeyError):
            store.load("does-not-exist")

    def test_exists(self):
        store = tmp_store()
        prog = make_reviewed()
        assert not store.exists(prog.id)
        store.save(prog)
        assert store.exists(prog.id)

    def test_list_ids_empty(self):
        store = tmp_store()
        assert store.list_ids() == []

    def test_list_ids_after_save(self):
        store = tmp_store()
        p1 = make_reviewed(program_id="prog-aaa")
        p2 = make_reviewed(program_id="prog-bbb")
        store.save(p1)
        store.save(p2)
        ids = store.list_ids()
        assert "prog-aaa" in ids
        assert "prog-bbb" in ids

    def test_list_all_summary(self):
        store = tmp_store()
        prog = make_reviewed(steps=[make_step(), make_step("normalize_text")])
        store.save(prog)
        summaries = store.list_all()
        assert len(summaries) == 1
        s = summaries[0]
        assert s["id"] == prog.id
        assert s["status"] == "proposed"
        assert s["step_count_original"] == 2

    def test_overwrite_updates_status(self):
        store = tmp_store()
        prog = make_reviewed()
        store.save(prog)
        updated = dataclasses.replace(prog, status=ProgramStatus.REVIEWED)
        store.save(updated)
        loaded = store.load(prog.id)
        assert loaded.status == ProgramStatus.REVIEWED

    def test_save_wrong_type_raises(self):
        store = tmp_store()
        with pytest.raises(TypeError):
            store.save("not-a-program")  # type: ignore

    def test_file_is_valid_json(self):
        store = tmp_store()
        prog = make_reviewed()
        path = store.save(prog)
        data = json.loads(path.read_text())
        assert data["id"] == prog.id


# ---------------------------------------------------------------------------
# 8–12. Lifecycle functions
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_propose_creates_proposed_program(self):
        store = tmp_store()
        steps = [CandidateStep(tool="count_words", params={"input": "hello"})]
        prog = propose_program(steps, trace_id="t-001", world_version="1.0", store=store)
        assert prog.status == ProgramStatus.PROPOSED
        assert store.exists(prog.id)

    def test_propose_identity_minimized(self):
        store = tmp_store()
        steps = [CandidateStep(tool="count_words", params={"input": "hello", "extra": None})]
        prog = propose_program(steps, trace_id=None, world_version="1.0", store=store)
        # minimized_steps is identity copy of original before minimize_program() runs
        assert len(prog.minimized_steps) == len(prog.original_steps)
        assert prog.diff.is_empty

    def test_propose_empty_steps_raises(self):
        store = tmp_store()
        with pytest.raises(ValueError, match="at least one"):
            propose_program([], trace_id=None, world_version="1.0", store=store)

    def test_minimize_removes_none_params(self):
        store = tmp_store()
        steps = [CandidateStep(tool="count_words", params={"input": "hi", "x": None})]
        prog = propose_program(steps, trace_id=None, world_version="1.0", store=store)
        minimized = minimize_program(prog.id, store)
        assert "x" not in minimized.minimized_steps[0].params
        assert not minimized.diff.is_empty

    def test_minimize_does_not_change_original_steps(self):
        store = tmp_store()
        steps = [CandidateStep(tool="count_words", params={"input": "hi", "x": None})]
        prog = propose_program(steps, trace_id=None, world_version="1.0", store=store)
        minimized = minimize_program(prog.id, store)
        assert minimized.original_steps[0].params == {"input": "hi", "x": None}

    def test_review_transitions_to_reviewed(self):
        store = tmp_store()
        prog = propose_program(
            [make_step()], trace_id=None, world_version="1.0", store=store
        )
        reviewed = review_program(prog.id, store, notes="LGTM")
        assert reviewed.status == ProgramStatus.REVIEWED
        assert reviewed.metadata.reviewer_notes == "LGTM"

    def test_accept_transitions_to_accepted(self):
        store = tmp_store()
        prog = propose_program(
            [CandidateStep(tool="count_words", params={"input": "hello"})],
            trace_id=None,
            world_version="1.0",
            store=store,
        )
        review_program(prog.id, store)
        accepted = accept_program(
            prog.id, store,
            allowed_actions=DeterministicTaskCompiler.SUPPORTED_WORKFLOWS,
        )
        assert accepted.status == ProgramStatus.ACCEPTED

    def test_reject_transitions_to_rejected(self):
        store = tmp_store()
        prog = propose_program(
            [make_step()], trace_id=None, world_version="1.0", store=store
        )
        review_program(prog.id, store)
        rejected = reject_program(prog.id, store, reason="Out of scope")
        assert rejected.status == ProgramStatus.REJECTED
        assert "Out of scope" in rejected.metadata.reviewer_notes

    def test_explicit_program_id(self):
        store = tmp_store()
        prog = propose_program(
            [make_step()],
            trace_id=None,
            world_version="1.0",
            store=store,
            program_id="my-custom-id",
        )
        assert prog.id == "my-custom-id"


# ---------------------------------------------------------------------------
# 13. Status transition enforcement
# ---------------------------------------------------------------------------


class TestTransitionEnforcement:
    def test_cannot_review_a_reviewed_program(self):
        store = tmp_store()
        prog = propose_program([make_step()], trace_id=None, world_version="1.0", store=store)
        review_program(prog.id, store)
        with pytest.raises(InvalidTransitionError):
            review_program(prog.id, store)

    def test_cannot_accept_a_proposed_program(self):
        store = tmp_store()
        prog = propose_program([make_step()], trace_id=None, world_version="1.0", store=store)
        with pytest.raises(InvalidTransitionError):
            accept_program(prog.id, store, allowed_actions={"count_words"})

    def test_cannot_reject_a_proposed_program(self):
        store = tmp_store()
        prog = propose_program([make_step()], trace_id=None, world_version="1.0", store=store)
        with pytest.raises(InvalidTransitionError):
            reject_program(prog.id, store)

    def test_cannot_accept_a_rejected_program(self):
        store = tmp_store()
        prog = propose_program([make_step()], trace_id=None, world_version="1.0", store=store)
        review_program(prog.id, store)
        reject_program(prog.id, store)
        with pytest.raises(InvalidTransitionError):
            accept_program(prog.id, store, allowed_actions={"count_words"})

    def test_cannot_review_an_accepted_program(self):
        store = tmp_store()
        prog = propose_program(
            [CandidateStep(tool="count_words")],
            trace_id=None, world_version="1.0", store=store,
        )
        review_program(prog.id, store)
        accept_program(prog.id, store, allowed_actions={"count_words"})
        with pytest.raises(InvalidTransitionError):
            review_program(prog.id, store)


# ---------------------------------------------------------------------------
# 14. WorldValidationError
# ---------------------------------------------------------------------------


class TestWorldValidation:
    def test_accept_rejects_unknown_tool(self):
        store = tmp_store()
        prog = propose_program(
            [CandidateStep(tool="forbidden_action")],
            trace_id=None,
            world_version="1.0",
            store=store,
        )
        review_program(prog.id, store)
        with pytest.raises(WorldValidationError, match="forbidden_action"):
            accept_program(prog.id, store, allowed_actions={"count_words"})

    def test_store_not_modified_on_validation_failure(self):
        store = tmp_store()
        prog = propose_program(
            [CandidateStep(tool="bad_tool")],
            trace_id=None,
            world_version="1.0",
            store=store,
        )
        review_program(prog.id, store)
        try:
            accept_program(prog.id, store, allowed_actions={"count_words"})
        except WorldValidationError:
            pass
        # Program must still be REVIEWED, not ACCEPTED
        reloaded = store.load(prog.id)
        assert reloaded.status == ProgramStatus.REVIEWED

    def test_accept_with_empty_minimized_steps_skips_validation(self):
        store = tmp_store()
        # Manually create a program with empty minimized_steps
        original = (CandidateStep(tool="count_words"),)
        prog = ReviewedProgram(
            id="prog-empty-min",
            status=ProgramStatus.REVIEWED,
            original_steps=original,
            minimized_steps=(),
            diff=ProgramDiff(),
            metadata=make_metadata(),
        )
        store.save(prog)
        # Should not raise even though minimized_steps is empty
        accepted = accept_program(prog.id, store, allowed_actions={"count_words"})
        assert accepted.status == ProgramStatus.ACCEPTED


# ---------------------------------------------------------------------------
# 15. ReplayEngine
# ---------------------------------------------------------------------------


class TestReplayEngine:
    def setup_method(self):
        self.engine = ReplayEngine()

    def test_replay_accepted_program_succeeds(self):
        store = tmp_store()
        prog = propose_program(
            [CandidateStep(tool="count_words", params={"input": "hello world"})],
            trace_id=None,
            world_version="1.0",
            store=store,
        )
        review_program(prog.id, store)
        accepted = accept_program(
            prog.id, store,
            allowed_actions=DeterministicTaskCompiler.SUPPORTED_WORKFLOWS,
        )
        runner = ProgramRunner(allowed_actions=DeterministicTaskCompiler.SUPPORTED_WORKFLOWS)
        trace = self.engine.replay(
            accepted,
            runner=runner,
            context={"input": "hello world"},
        )
        assert trace.ok
        assert trace.program_id == accepted.id
        assert len(trace.step_traces) == 1
        assert trace.step_traces[0].verdict == "allow"

    def test_replay_fails_on_unknown_tool(self):
        prog = ReviewedProgram(
            id="prog-bad",
            status=ProgramStatus.ACCEPTED,
            original_steps=(CandidateStep(tool="unknown_tool"),),
            minimized_steps=(CandidateStep(tool="unknown_tool"),),
            diff=ProgramDiff(),
            metadata=make_metadata(),
        )
        trace = self.engine.replay(prog, allowed_actions={"count_words"})
        assert not trace.ok
        assert trace.step_traces[0].verdict == "deny"
        assert "world validation" in trace.step_traces[0].error

    def test_replay_empty_minimized_steps_ok(self):
        prog = ReviewedProgram(
            id="prog-empty",
            status=ProgramStatus.ACCEPTED,
            original_steps=(CandidateStep(tool="count_words"),),
            minimized_steps=(),
            diff=ProgramDiff(),
            metadata=make_metadata(),
        )
        trace = self.engine.replay(prog)
        assert trace.ok
        assert trace.step_traces == []

    def test_replay_wrong_type_raises(self):
        with pytest.raises(TypeError, match="ReviewedProgram"):
            self.engine.replay("not-a-program")  # type: ignore

    def test_replay_is_deterministic(self):
        prog = ReviewedProgram(
            id="prog-det",
            status=ProgramStatus.ACCEPTED,
            original_steps=(CandidateStep(tool="count_words", params={"input": "hi"}),),
            minimized_steps=(CandidateStep(tool="count_words", params={"input": "hi"}),),
            diff=ProgramDiff(),
            metadata=make_metadata(),
        )
        allowed = DeterministicTaskCompiler.SUPPORTED_WORKFLOWS
        runner = ProgramRunner(allowed_actions=allowed)
        t1 = self.engine.replay(prog, runner=ProgramRunner(allowed_actions=allowed), context={"input": "hi"})
        t2 = self.engine.replay(prog, runner=ProgramRunner(allowed_actions=allowed), context={"input": "hi"})
        assert t1.ok == t2.ok
        assert [st.verdict for st in t1.step_traces] == [st.verdict for st in t2.step_traces]

    def test_replay_uses_minimized_not_original(self):
        # original has a None param, minimized has it stripped
        original_step = CandidateStep(tool="count_words", params={"input": "hi", "junk": None})
        minimized_step = CandidateStep(tool="count_words", params={"input": "hi"})
        prog = ReviewedProgram(
            id="prog-min-replay",
            status=ProgramStatus.ACCEPTED,
            original_steps=(original_step,),
            minimized_steps=(minimized_step,),
            diff=ProgramDiff(),
            metadata=make_metadata(),
        )
        allowed = DeterministicTaskCompiler.SUPPORTED_WORKFLOWS
        trace = self.engine.replay(
            prog,
            runner=ProgramRunner(allowed_actions=allowed),
            context={"input": "hi"},
        )
        assert trace.ok


# ---------------------------------------------------------------------------
# 16. make_program_id
# ---------------------------------------------------------------------------


class TestMakeProgramId:
    def test_returns_string_starting_with_prog(self):
        pid = make_program_id()
        assert pid.startswith("prog-")

    def test_unique(self):
        ids = {make_program_id() for _ in range(100)}
        assert len(ids) == 100
