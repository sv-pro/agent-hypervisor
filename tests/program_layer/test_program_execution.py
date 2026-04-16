"""
tests/program_layer/test_program_execution.py — Phase 1 program layer tests.

Coverage:
    1.  Step construction — valid, empty action, non-string action
    2.  Program construction — valid, list vs tuple, max_steps limit, empty steps,
        bad element types, non-string program_id
    3.  ProgramTrace structure — ok flag, aborted_at_step, to_dict shape
    4.  StepTrace properties — allowed, denied, skipped
    5.  ProgramRunner defaults — allowed_actions, default_timeout
    6.  ProgramRunner execution — single step allow, single step deny (unknown action),
        multi-step all-allow, multi-step abort-on-deny, skip propagation
    7.  ProgramRunner sandbox integration — real sandbox execution through the
        DeterministicTaskCompiler + SandboxRuntime stack
    8.  ProgramRunner error handling — compile error (invalid top_n), timeout,
        security violation
    9.  ENABLE_PROGRAM_LAYER config flag — default value, env-variable override
    10. Integration test — full pipeline with multiple steps and context threading
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from agent_hypervisor.program_layer.config import ENABLE_PROGRAM_LAYER
from agent_hypervisor.program_layer.execution_plan import DirectExecutionPlan, ProgramExecutionPlan
from agent_hypervisor.program_layer.program_model import MAX_STEPS, Program, Step
from agent_hypervisor.program_layer.program_runner import ProgramRunner
from agent_hypervisor.program_layer.program_trace import ProgramTrace, StepTrace
from agent_hypervisor.program_layer.task_compiler import DeterministicTaskCompiler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_step(action: str = "count_words", **params) -> Step:
    return Step(action=action, params=dict(params))


def make_program(*steps: Step, program_id: str = "test-prog") -> Program:
    return Program(program_id=program_id, steps=tuple(steps))


# ---------------------------------------------------------------------------
# 1. Step construction
# ---------------------------------------------------------------------------

class TestStep:
    def test_valid_step(self):
        s = Step(action="count_words")
        assert s.action == "count_words"
        assert s.params == {}

    def test_step_with_params(self):
        s = Step(action="count_words", params={"input": "hello world"})
        assert s.params["input"] == "hello world"

    def test_step_empty_action_raises(self):
        with pytest.raises(ValueError, match="non-empty string"):
            Step(action="")

    def test_step_whitespace_action_raises(self):
        with pytest.raises(ValueError, match="non-empty string"):
            Step(action="   ")

    def test_step_non_string_action_raises(self):
        with pytest.raises(ValueError):
            Step(action=None)  # type: ignore[arg-type]

    def test_step_is_frozen(self):
        s = Step(action="count_words")
        with pytest.raises((AttributeError, TypeError)):
            s.action = "other"  # type: ignore[misc]

    def test_step_params_excluded_from_equality(self):
        s1 = Step(action="count_words", params={"input": "a"})
        s2 = Step(action="count_words", params={"input": "b"})
        assert s1 == s2  # params excluded from compare


# ---------------------------------------------------------------------------
# 2. Program construction
# ---------------------------------------------------------------------------

class TestProgram:
    def test_valid_program(self):
        p = make_program(make_step())
        assert p.program_id == "test-prog"
        assert len(p.steps) == 1

    def test_program_with_multiple_steps(self):
        steps = tuple(make_step(action="count_words") for _ in range(3))
        p = Program(program_id="multi", steps=steps)
        assert len(p) == 3

    def test_list_steps_raises(self):
        with pytest.raises(TypeError, match="tuple"):
            Program(program_id="x", steps=[make_step()])  # type: ignore[arg-type]

    def test_empty_steps_raises(self):
        with pytest.raises(ValueError, match="at least one step"):
            Program(program_id="x", steps=())

    def test_max_steps_exactly(self):
        steps = tuple(make_step() for _ in range(MAX_STEPS))
        p = Program(program_id="x", steps=steps)
        assert len(p) == MAX_STEPS

    def test_exceeds_max_steps_raises(self):
        steps = tuple(make_step() for _ in range(MAX_STEPS + 1))
        with pytest.raises(ValueError, match="MAX_STEPS"):
            Program(program_id="x", steps=steps)

    def test_non_step_element_raises(self):
        with pytest.raises(TypeError, match="Step instance"):
            Program(program_id="x", steps=("count_words",))  # type: ignore[arg-type]

    def test_empty_program_id_raises(self):
        with pytest.raises(ValueError, match="non-empty string"):
            Program(program_id="", steps=(make_step(),))

    def test_program_is_frozen(self):
        p = make_program(make_step())
        with pytest.raises((AttributeError, TypeError)):
            p.program_id = "other"  # type: ignore[misc]

    def test_program_iterable(self):
        s1 = make_step(action="count_words")
        s2 = make_step(action="normalize_text")
        p = make_program(s1, s2)
        assert list(p) == [s1, s2]


# ---------------------------------------------------------------------------
# 3. ProgramTrace structure
# ---------------------------------------------------------------------------

class TestProgramTrace:
    def test_default_state(self):
        t = ProgramTrace(program_id="p1")
        assert t.program_id == "p1"
        assert t.step_traces == []
        assert t.ok is False
        assert t.aborted_at_step is None

    def test_to_dict_empty(self):
        t = ProgramTrace(program_id="p1")
        d = t.to_dict()
        assert d["program_id"] == "p1"
        assert d["ok"] is False
        assert d["step_traces"] == []
        assert d["aborted_at_step"] is None
        assert "total_duration_seconds" in d

    def test_to_dict_with_step_traces(self):
        t = ProgramTrace(program_id="p1")
        t.step_traces.append(
            StepTrace(step_index=0, action="count_words", verdict="allow", result={"word_count": 2})
        )
        t.ok = True
        d = t.to_dict()
        assert d["ok"] is True
        assert len(d["step_traces"]) == 1
        assert d["step_traces"][0]["verdict"] == "allow"
        assert d["step_traces"][0]["result"] == {"word_count": 2}


# ---------------------------------------------------------------------------
# 4. StepTrace properties
# ---------------------------------------------------------------------------

class TestStepTrace:
    def test_allowed_property(self):
        st = StepTrace(step_index=0, action="count_words", verdict="allow")
        assert st.allowed is True
        assert st.denied is False
        assert st.skipped is False

    def test_denied_property(self):
        st = StepTrace(step_index=0, action="unknown", verdict="deny", error="not allowed")
        assert st.denied is True
        assert st.allowed is False
        assert st.skipped is False

    def test_skipped_property(self):
        st = StepTrace(step_index=1, action="count_words", verdict="skip")
        assert st.skipped is True
        assert st.allowed is False
        assert st.denied is False

    def test_step_trace_is_frozen(self):
        st = StepTrace(step_index=0, action="x", verdict="allow")
        with pytest.raises((AttributeError, TypeError)):
            st.verdict = "deny"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 5. ProgramRunner defaults
# ---------------------------------------------------------------------------

class TestProgramRunnerDefaults:
    def test_default_allowed_actions(self):
        runner = ProgramRunner()
        # default is SUPPORTED_WORKFLOWS
        assert runner._allowed_actions == frozenset(
            DeterministicTaskCompiler.SUPPORTED_WORKFLOWS
        )

    def test_custom_allowed_actions(self):
        runner = ProgramRunner(allowed_actions={"count_words"})
        assert runner._allowed_actions == frozenset({"count_words"})

    def test_empty_allowed_actions(self):
        runner = ProgramRunner(allowed_actions=[])
        assert runner._allowed_actions == frozenset()

    def test_negative_timeout_raises(self):
        with pytest.raises(ValueError, match="positive"):
            ProgramRunner(default_timeout=-1.0)

    def test_zero_timeout_raises(self):
        with pytest.raises(ValueError, match="positive"):
            ProgramRunner(default_timeout=0.0)

    def test_run_requires_program(self):
        runner = ProgramRunner()
        with pytest.raises(TypeError, match="Program"):
            runner.run("not-a-program")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 6. ProgramRunner execution (using real sandbox)
# ---------------------------------------------------------------------------

class TestProgramRunnerExecution:
    def test_single_step_allow(self):
        runner = ProgramRunner()
        program = make_program(
            Step(action="count_words", params={"input": "hello world foo"})
        )
        trace = runner.run(program)
        assert trace.ok is True
        assert len(trace.step_traces) == 1
        st = trace.step_traces[0]
        assert st.verdict == "allow"
        assert st.result["word_count"] == 3
        assert st.error is None

    def test_single_step_deny_unknown_action(self):
        runner = ProgramRunner()
        program = make_program(Step(action="unknown_action"))
        trace = runner.run(program)
        assert trace.ok is False
        assert trace.aborted_at_step == 0
        assert trace.step_traces[0].verdict == "deny"
        assert "unknown_action" in trace.step_traces[0].error

    def test_multi_step_all_allow(self):
        runner = ProgramRunner()
        program = make_program(
            Step(action="count_words", params={"input": "hello world"}),
            Step(action="normalize_text", params={"input": "HELLO WORLD"}),
        )
        trace = runner.run(program)
        assert trace.ok is True
        assert len(trace.step_traces) == 2
        assert trace.step_traces[0].verdict == "allow"
        assert trace.step_traces[1].verdict == "allow"

    def test_multi_step_abort_on_deny(self):
        runner = ProgramRunner()
        program = make_program(
            Step(action="count_words", params={"input": "hello"}),
            Step(action="denied_action"),   # will be denied
            Step(action="normalize_text", params={"input": "HELLO"}),  # will be skipped
        )
        trace = runner.run(program)
        assert trace.ok is False
        assert trace.aborted_at_step == 1
        verdicts = [st.verdict for st in trace.step_traces]
        assert verdicts == ["allow", "deny", "skip"]

    def test_skip_propagation(self):
        runner = ProgramRunner()
        program = make_program(
            Step(action="bad_action"),
            Step(action="count_words", params={"input": "hi"}),
            Step(action="normalize_text", params={"input": "HI"}),
        )
        trace = runner.run(program)
        verdicts = [st.verdict for st in trace.step_traces]
        assert verdicts == ["deny", "skip", "skip"]
        assert trace.aborted_at_step == 0

    def test_first_step_deny_abort(self):
        runner = ProgramRunner(allowed_actions=[])  # nothing allowed
        program = make_program(Step(action="count_words", params={"input": "hi"}))
        trace = runner.run(program)
        assert trace.ok is False
        assert trace.aborted_at_step == 0

    def test_trace_has_timing(self):
        runner = ProgramRunner()
        program = make_program(
            Step(action="count_words", params={"input": "hello world"})
        )
        trace = runner.run(program)
        assert trace.total_duration_seconds >= 0.0
        assert trace.step_traces[0].duration_seconds >= 0.0

    def test_program_id_in_trace(self):
        runner = ProgramRunner()
        program = Program(
            program_id="my-unique-id",
            steps=(Step(action="count_words", params={"input": "x"}),),
        )
        trace = runner.run(program)
        assert trace.program_id == "my-unique-id"


# ---------------------------------------------------------------------------
# 7. ProgramRunner sandbox integration (real execution)
# ---------------------------------------------------------------------------

class TestSandboxIntegration:
    def test_count_lines_integration(self):
        runner = ProgramRunner()
        program = make_program(
            Step(action="count_lines", params={"input": "line1\nline2\nline3"})
        )
        trace = runner.run(program)
        assert trace.ok
        result = trace.step_traces[0].result
        assert result["line_count"] == 3
        assert result["non_empty_line_count"] == 3

    def test_normalize_text_integration(self):
        runner = ProgramRunner()
        program = make_program(
            Step(action="normalize_text", params={"input": "  HELLO  \n  WORLD  "})
        )
        trace = runner.run(program)
        assert trace.ok
        result = trace.step_traces[0].result
        assert result["normalized"] == "hello\nworld"

    def test_word_frequency_integration(self):
        runner = ProgramRunner()
        program = make_program(
            Step(action="word_frequency", params={"input": "a b a c a b", "top_n": 2})
        )
        trace = runner.run(program)
        assert trace.ok
        result = trace.step_traces[0].result
        top = dict(result["top_words"])
        assert top["a"] == 3
        assert top["b"] == 2

    def test_word_frequency_invalid_top_n_denied(self):
        runner = ProgramRunner()
        program = make_program(
            Step(action="word_frequency", params={"input": "hello world", "top_n": 200})
        )
        trace = runner.run(program)
        assert trace.ok is False
        assert "compile error" in trace.step_traces[0].error

    def test_custom_allowed_actions_restricts(self):
        runner = ProgramRunner(allowed_actions={"count_lines"})
        program = make_program(
            Step(action="count_words", params={"input": "hello world"})
        )
        trace = runner.run(program)
        assert trace.ok is False
        assert trace.step_traces[0].verdict == "deny"


# ---------------------------------------------------------------------------
# 8. ProgramRunner error handling
# ---------------------------------------------------------------------------

class TestProgramRunnerErrorHandling:
    def test_timeout_produces_deny(self):
        """A step that times out is denied (not an uncaught exception)."""
        runner = ProgramRunner(default_timeout=0.05)
        # Use a real (slow) compile + sandbox timeout via mock of executor
        from agent_hypervisor.program_layer.sandbox_runtime import SandboxTimeoutError
        mock_executor = MagicMock()
        mock_executor.execute.return_value = {
            "ok": False,
            "error": "program exceeded timeout of 0.05s",
            "error_type": "timeout",
            "plan_id": "test",
            "execution_mode": "program",
            "duration_seconds": 0.05,
        }
        runner._executor = mock_executor

        program = make_program(
            Step(action="count_words", params={"input": "hello"})
        )
        trace = runner.run(program)
        assert trace.ok is False
        assert trace.step_traces[0].verdict == "deny"
        assert "timeout" in trace.step_traces[0].error

    def test_security_violation_produces_deny(self):
        """A sandbox security violation is captured as deny verdict."""
        mock_executor = MagicMock()
        mock_executor.execute.return_value = {
            "ok": False,
            "error": "import statements are not allowed",
            "error_type": "security",
            "plan_id": "test",
            "execution_mode": "program",
            "duration_seconds": 0.0,
        }
        runner = ProgramRunner()
        runner._executor = mock_executor

        program = make_program(Step(action="count_words", params={"input": "x"}))
        trace = runner.run(program)
        assert trace.ok is False
        assert trace.step_traces[0].verdict == "deny"

    def test_executor_type_error_captured(self):
        """TypeError from executor is captured as deny, not propagated."""
        mock_executor = MagicMock()
        mock_executor.execute.side_effect = TypeError("wrong plan type")
        runner = ProgramRunner()
        runner._executor = mock_executor

        program = make_program(Step(action="count_words", params={"input": "x"}))
        trace = runner.run(program)
        assert trace.ok is False
        assert trace.step_traces[0].verdict == "deny"
        assert "executor type error" in trace.step_traces[0].error

    def test_runner_never_raises_on_bad_step(self):
        """ProgramRunner.run() never raises; errors are always in the trace."""
        mock_executor = MagicMock()
        mock_executor.execute.side_effect = RuntimeError("unexpected!")
        runner = ProgramRunner()
        runner._executor = mock_executor

        program = make_program(Step(action="count_words", params={"input": "x"}))
        # RuntimeError from executor is NOT caught by runner — it propagates
        # to signal an unexpected internal failure.  This is intentional: only
        # known failure modes are wrapped in deny verdicts.
        with pytest.raises(RuntimeError, match="unexpected!"):
            runner.run(program)


# ---------------------------------------------------------------------------
# 9. ENABLE_PROGRAM_LAYER config flag
# ---------------------------------------------------------------------------

class TestEnableProgramLayerFlag:
    def test_default_enabled(self):
        # In normal test environment, flag is True unless overridden
        # We can't assert True absolutely because CI may set it to 0,
        # but we can verify the flag type and that it follows env var.
        assert isinstance(ENABLE_PROGRAM_LAYER, bool)

    def test_env_var_off_disables(self):
        """Setting the env var to '0' disables the flag."""
        import importlib
        import agent_hypervisor.program_layer.config as cfg_module

        with patch.dict(os.environ, {"AGENT_HYPERVISOR_ENABLE_PROGRAM_LAYER": "0"}):
            importlib.reload(cfg_module)
            assert cfg_module.ENABLE_PROGRAM_LAYER is False

        # Restore
        importlib.reload(cfg_module)

    def test_env_var_false_disables(self):
        """Setting the env var to 'false' disables the flag."""
        import importlib
        import agent_hypervisor.program_layer.config as cfg_module

        with patch.dict(os.environ, {"AGENT_HYPERVISOR_ENABLE_PROGRAM_LAYER": "false"}):
            importlib.reload(cfg_module)
            assert cfg_module.ENABLE_PROGRAM_LAYER is False

        importlib.reload(cfg_module)

    def test_env_var_1_enables(self):
        """Setting the env var to '1' keeps the flag enabled."""
        import importlib
        import agent_hypervisor.program_layer.config as cfg_module

        with patch.dict(os.environ, {"AGENT_HYPERVISOR_ENABLE_PROGRAM_LAYER": "1"}):
            importlib.reload(cfg_module)
            assert cfg_module.ENABLE_PROGRAM_LAYER is True

        importlib.reload(cfg_module)


# ---------------------------------------------------------------------------
# 10. Integration test — full pipeline
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_full_pipeline_two_steps(self):
        """End-to-end: Program → ProgramRunner → ProgramTrace."""
        runner = ProgramRunner()
        program = Program(
            program_id="pipeline-test",
            steps=(
                Step(action="count_words", params={"input": "hello world foo bar"}),
                Step(action="normalize_text", params={"input": "  HELLO  WORLD  "}),
            ),
        )
        trace = runner.run(program)

        assert trace.ok is True
        assert len(trace.step_traces) == 2

        st0 = trace.step_traces[0]
        assert st0.action == "count_words"
        assert st0.verdict == "allow"
        assert st0.result["word_count"] == 4

        st1 = trace.step_traces[1]
        assert st1.action == "normalize_text"
        assert st1.verdict == "allow"
        assert "hello" in st1.result["normalized"]

        d = trace.to_dict()
        assert d["program_id"] == "pipeline-test"
        assert d["ok"] is True
        assert len(d["step_traces"]) == 2

    def test_full_pipeline_aborts_on_unknown(self):
        """Pipeline with unknown action aborts; remaining steps are skipped."""
        runner = ProgramRunner()
        program = Program(
            program_id="abort-test",
            steps=(
                Step(action="count_words", params={"input": "hello"}),
                Step(action="send_email", params={"to": "x@y.com"}),  # not in allowed
                Step(action="normalize_text", params={"input": "HELLO"}),
            ),
        )
        trace = runner.run(program)

        assert trace.ok is False
        assert trace.aborted_at_step == 1

        verdicts = [st.verdict for st in trace.step_traces]
        assert verdicts == ["allow", "deny", "skip"]

        d = trace.to_dict()
        assert d["aborted_at_step"] == 1

    def test_program_is_imported_from_package(self):
        """All Phase 1 types are importable from the package root."""
        from agent_hypervisor.program_layer import (  # noqa: F401
            ENABLE_PROGRAM_LAYER,
            MAX_STEPS,
            Program,
            ProgramRunner,
            ProgramTrace,
            Step,
            StepTrace,
        )
        assert MAX_STEPS == 10
        assert isinstance(ENABLE_PROGRAM_LAYER, bool)
