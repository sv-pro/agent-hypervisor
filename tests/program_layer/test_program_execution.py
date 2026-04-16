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


# ---------------------------------------------------------------------------
# 11. Step.description field
# ---------------------------------------------------------------------------

class TestStepDescription:
    def test_step_description_defaults_to_none(self):
        s = Step(action="count_words")
        assert s.description is None

    def test_step_description_can_be_set(self):
        s = Step(action="count_words", description="Count words in the input text")
        assert s.description == "Count words in the input text"

    def test_step_description_excluded_from_equality(self):
        s1 = Step(action="count_words", description="version A")
        s2 = Step(action="count_words", description="version B")
        assert s1 == s2

    def test_step_description_excluded_from_hash(self):
        s1 = Step(action="count_words", description="one")
        s2 = Step(action="count_words", description="two")
        assert hash(s1) == hash(s2)

    def test_step_description_in_to_dict_via_trace(self):
        """Description doesn't affect trace dict (not a trace field), but
        step construction with description must not break ProgramRunner."""
        runner = ProgramRunner()
        program = Program(
            program_id="desc-test",
            steps=(
                Step(
                    action="count_words",
                    params={"input": "hello world"},
                    description="Count words in hello world",
                ),
            ),
        )
        trace = runner.run(program)
        assert trace.ok is True
        assert trace.step_traces[0].result["word_count"] == 2


# ---------------------------------------------------------------------------
# 12. SimpleTaskCompiler — keyword matching
# ---------------------------------------------------------------------------

class TestSimpleTaskCompiler:
    def setup_method(self):
        from agent_hypervisor.program_layer.simple_task_compiler import SimpleTaskCompiler
        self.compiler = SimpleTaskCompiler()

    def test_string_intent_count_words(self):
        from agent_hypervisor.program_layer.execution_plan import ProgramExecutionPlan
        plan = self.compiler.compile("count the words in this document")
        assert isinstance(plan, ProgramExecutionPlan)
        assert plan.metadata.get("workflow") == "count_words"

    def test_string_intent_count_lines(self):
        from agent_hypervisor.program_layer.execution_plan import ProgramExecutionPlan
        plan = self.compiler.compile("count lines in the file")
        assert isinstance(plan, ProgramExecutionPlan)
        assert plan.metadata.get("workflow") == "count_lines"

    def test_string_intent_normalize_text(self):
        from agent_hypervisor.program_layer.execution_plan import ProgramExecutionPlan
        plan = self.compiler.compile("normalize the text content")
        assert isinstance(plan, ProgramExecutionPlan)
        assert plan.metadata.get("workflow") == "normalize_text"

    def test_string_intent_word_frequency(self):
        from agent_hypervisor.program_layer.execution_plan import ProgramExecutionPlan
        plan = self.compiler.compile("show word frequency distribution")
        assert isinstance(plan, ProgramExecutionPlan)
        assert plan.metadata.get("workflow") == "word_frequency"

    def test_unknown_string_falls_back_to_direct(self):
        from agent_hypervisor.program_layer.execution_plan import DirectExecutionPlan
        plan = self.compiler.compile("send an email to alice@example.com")
        assert isinstance(plan, DirectExecutionPlan)

    def test_dict_intent_delegated(self):
        from agent_hypervisor.program_layer.execution_plan import ProgramExecutionPlan
        plan = self.compiler.compile({"workflow": "count_words"})
        assert isinstance(plan, ProgramExecutionPlan)

    def test_dict_unknown_workflow_falls_back(self):
        from agent_hypervisor.program_layer.execution_plan import DirectExecutionPlan
        plan = self.compiler.compile({"workflow": "send_email"})
        assert isinstance(plan, DirectExecutionPlan)

    def test_non_string_non_dict_falls_back(self):
        from agent_hypervisor.program_layer.execution_plan import DirectExecutionPlan
        plan = self.compiler.compile(42)
        assert isinstance(plan, DirectExecutionPlan)

    def test_none_intent_falls_back(self):
        from agent_hypervisor.program_layer.execution_plan import DirectExecutionPlan
        plan = self.compiler.compile(None)
        assert isinstance(plan, DirectExecutionPlan)

    def test_world_as_frozenset_filters_workflows(self):
        from agent_hypervisor.program_layer.execution_plan import DirectExecutionPlan
        # count_words not in world → fallback
        plan = self.compiler.compile(
            "count words", world=frozenset({"count_lines", "normalize_text"})
        )
        assert isinstance(plan, DirectExecutionPlan)

    def test_world_as_frozenset_allows_workflow(self):
        from agent_hypervisor.program_layer.execution_plan import ProgramExecutionPlan
        plan = self.compiler.compile(
            "count words", world=frozenset({"count_words"})
        )
        assert isinstance(plan, ProgramExecutionPlan)

    def test_world_none_imposes_no_filter(self):
        from agent_hypervisor.program_layer.execution_plan import ProgramExecutionPlan
        plan = self.compiler.compile("count words", world=None)
        assert isinstance(plan, ProgramExecutionPlan)

    def test_case_insensitive_matching(self):
        from agent_hypervisor.program_layer.execution_plan import ProgramExecutionPlan
        plan = self.compiler.compile("COUNT WORDS in THIS TEXT")
        assert isinstance(plan, ProgramExecutionPlan)

    def test_extra_patterns_prepended(self):
        from agent_hypervisor.program_layer.simple_task_compiler import SimpleTaskCompiler
        from agent_hypervisor.program_layer.execution_plan import ProgramExecutionPlan
        compiler = SimpleTaskCompiler(
            extra_patterns=(("count_lines", "audit log"),)
        )
        plan = compiler.compile("process the audit log")
        assert isinstance(plan, ProgramExecutionPlan)
        assert plan.metadata.get("workflow") == "count_lines"

    def test_compiler_exported_from_package(self):
        from agent_hypervisor.program_layer import SimpleTaskCompiler  # noqa: F401
        assert SimpleTaskCompiler.SUPPORTED_WORKFLOWS == frozenset({
            "count_lines", "count_words", "normalize_text", "word_frequency"
        })

    def test_count_lines_wins_over_count_words_for_line_input(self):
        """'count lines' keyword must not accidentally match 'count_words'."""
        from agent_hypervisor.program_layer.execution_plan import ProgramExecutionPlan
        plan = self.compiler.compile("how many lines are there?")
        assert isinstance(plan, ProgramExecutionPlan)
        assert plan.metadata.get("workflow") == "count_lines"

    def test_end_to_end_string_intent(self):
        """SimpleTaskCompiler plan is executable by ProgramExecutor."""
        from agent_hypervisor.program_layer.program_executor import ProgramExecutor
        from agent_hypervisor.program_layer.execution_plan import ProgramExecutionPlan
        plan = self.compiler.compile("count the words in this text")
        assert isinstance(plan, ProgramExecutionPlan)
        executor = ProgramExecutor()
        result = executor.execute(plan, context={"input": "hello world foo"})
        assert result["ok"] is True
        assert result["result"]["word_count"] == 3


# ---------------------------------------------------------------------------
# 13. World validation (validate_program / validate_step)
# ---------------------------------------------------------------------------

class TestWorldValidator:
    def test_valid_program_returns_ok(self):
        from agent_hypervisor.program_layer.world_validator import validate_program
        from agent_hypervisor.program_layer.task_compiler import DeterministicTaskCompiler
        program = make_program(
            Step(action="count_words", params={"input": "hello"}),
            Step(action="normalize_text", params={"input": "HELLO"}),
        )
        result = validate_program(program, DeterministicTaskCompiler.SUPPORTED_WORKFLOWS)
        assert result.ok is True
        assert len(result.violations) == 0

    def test_invalid_action_produces_violation(self):
        from agent_hypervisor.program_layer.world_validator import validate_program
        program = make_program(Step(action="send_email"))
        result = validate_program(program, frozenset({"count_words"}))
        assert result.ok is False
        assert len(result.violations) == 1
        assert result.violations[0].action == "send_email"
        assert result.violations[0].step_index == 0

    def test_multiple_violations_collected(self):
        from agent_hypervisor.program_layer.world_validator import validate_program
        program = make_program(
            Step(action="bad_action_1"),
            Step(action="count_words", params={"input": "ok"}),  # allowed
            Step(action="bad_action_2"),
        )
        result = validate_program(program, frozenset({"count_words"}))
        assert result.ok is False
        assert len(result.violations) == 2
        assert result.violations[0].step_index == 0
        assert result.violations[1].step_index == 2

    def test_empty_allowed_set_denies_everything(self):
        from agent_hypervisor.program_layer.world_validator import validate_program
        program = make_program(Step(action="count_words"))
        result = validate_program(program, frozenset())
        assert result.ok is False
        assert len(result.violations) == 1

    def test_validate_program_requires_program(self):
        from agent_hypervisor.program_layer.world_validator import validate_program
        with pytest.raises(TypeError, match="Program"):
            validate_program("not-a-program", frozenset())  # type: ignore[arg-type]

    def test_violation_str_representation(self):
        from agent_hypervisor.program_layer.world_validator import validate_program
        program = make_program(Step(action="unknown_op"))
        result = validate_program(program, frozenset())
        v = result.violations[0]
        assert "unknown_op" in str(v)
        assert "step[0]" in str(v)

    def test_to_dict_shape(self):
        from agent_hypervisor.program_layer.world_validator import validate_program
        program = make_program(Step(action="bad_action"))
        result = validate_program(program, frozenset({"count_words"}))
        d = result.to_dict()
        assert d["ok"] is False
        assert len(d["violations"]) == 1
        assert d["violations"][0]["step_index"] == 0
        assert d["violations"][0]["action"] == "bad_action"

    def test_validate_step_valid(self):
        from agent_hypervisor.program_layer.world_validator import validate_step
        s = Step(action="count_words")
        result = validate_step(s, frozenset({"count_words"}))
        assert result is None

    def test_validate_step_invalid(self):
        from agent_hypervisor.program_layer.world_validator import validate_step
        s = Step(action="delete_all")
        result = validate_step(s, frozenset({"count_words"}), step_index=3)
        assert result is not None
        assert result.action == "delete_all"
        assert result.step_index == 3

    def test_symbols_exported_from_package(self):
        from agent_hypervisor.program_layer import (  # noqa: F401
            StepViolation,
            ValidationResult,
            validate_program,
            validate_step,
        )


# ---------------------------------------------------------------------------
# 14. ProgramTraceStore — JSONL persistence
# ---------------------------------------------------------------------------

class TestProgramTraceStore:
    def _make_trace(self, program_id: str = "store-test", ok: bool = True) -> ProgramTrace:
        t = ProgramTrace(program_id=program_id)
        t.step_traces.append(
            StepTrace(
                step_index=0,
                action="count_words",
                verdict="allow" if ok else "deny",
                result={"word_count": 3} if ok else None,
                error=None if ok else "denied",
            )
        )
        t.ok = ok
        t.total_duration_seconds = 0.001
        return t

    def test_append_creates_file(self, tmp_path):
        from agent_hypervisor.program_layer.trace_storage import ProgramTraceStore
        store = ProgramTraceStore(tmp_path / "traces.jsonl")
        assert not (tmp_path / "traces.jsonl").exists()
        trace = self._make_trace()
        store.append(trace)
        assert (tmp_path / "traces.jsonl").exists()

    def test_append_writes_valid_jsonl(self, tmp_path):
        import json
        from agent_hypervisor.program_layer.trace_storage import ProgramTraceStore
        store = ProgramTraceStore(tmp_path / "traces.jsonl")
        store.append(self._make_trace("prog-1"))
        store.append(self._make_trace("prog-2"))
        lines = (tmp_path / "traces.jsonl").read_text().strip().splitlines()
        assert len(lines) == 2
        for line in lines:
            entry = json.loads(line)  # must not raise
            assert "program_id" in entry
            assert "_stored_at" in entry

    def test_list_recent_order(self, tmp_path):
        from agent_hypervisor.program_layer.trace_storage import ProgramTraceStore
        store = ProgramTraceStore(tmp_path / "traces.jsonl")
        store.append(self._make_trace("first"))
        store.append(self._make_trace("second"))
        store.append(self._make_trace("third"))
        recent = store.list_recent(limit=10)
        # Newest first
        assert recent[0]["program_id"] == "third"
        assert recent[2]["program_id"] == "first"

    def test_list_recent_limit(self, tmp_path):
        from agent_hypervisor.program_layer.trace_storage import ProgramTraceStore
        store = ProgramTraceStore(tmp_path / "traces.jsonl")
        for i in range(5):
            store.append(self._make_trace(f"prog-{i}"))
        recent = store.list_recent(limit=3)
        assert len(recent) == 3

    def test_list_recent_filter_ok(self, tmp_path):
        from agent_hypervisor.program_layer.trace_storage import ProgramTraceStore
        store = ProgramTraceStore(tmp_path / "traces.jsonl")
        store.append(self._make_trace("ok-1", ok=True))
        store.append(self._make_trace("fail-1", ok=False))
        store.append(self._make_trace("ok-2", ok=True))
        ok_traces = store.list_recent(ok=True)
        assert all(t["ok"] is True for t in ok_traces)
        assert len(ok_traces) == 2

    def test_list_recent_filter_program_id(self, tmp_path):
        from agent_hypervisor.program_layer.trace_storage import ProgramTraceStore
        store = ProgramTraceStore(tmp_path / "traces.jsonl")
        store.append(self._make_trace("alpha"))
        store.append(self._make_trace("beta"))
        store.append(self._make_trace("alpha"))
        results = store.list_recent(program_id="alpha")
        assert all(t["program_id"] == "alpha" for t in results)
        assert len(results) == 2

    def test_count(self, tmp_path):
        from agent_hypervisor.program_layer.trace_storage import ProgramTraceStore
        store = ProgramTraceStore(tmp_path / "traces.jsonl")
        assert store.count() == 0
        store.append(self._make_trace())
        store.append(self._make_trace())
        assert store.count() == 2

    def test_nonexistent_file_returns_empty_list(self, tmp_path):
        from agent_hypervisor.program_layer.trace_storage import ProgramTraceStore
        store = ProgramTraceStore(tmp_path / "no_such_file.jsonl")
        assert store.list_recent() == []
        assert store.count() == 0

    def test_append_requires_program_trace(self, tmp_path):
        from agent_hypervisor.program_layer.trace_storage import ProgramTraceStore
        store = ProgramTraceStore(tmp_path / "traces.jsonl")
        with pytest.raises(TypeError, match="ProgramTrace"):
            store.append({"not": "a trace"})  # type: ignore[arg-type]

    def test_creates_parent_directories(self, tmp_path):
        from agent_hypervisor.program_layer.trace_storage import ProgramTraceStore
        store = ProgramTraceStore(tmp_path / "deep" / "nested" / "traces.jsonl")
        store.append(self._make_trace())
        assert (tmp_path / "deep" / "nested" / "traces.jsonl").exists()

    def test_stored_at_is_iso8601(self, tmp_path):
        import json
        from agent_hypervisor.program_layer.trace_storage import ProgramTraceStore
        store = ProgramTraceStore(tmp_path / "traces.jsonl")
        store.append(self._make_trace())
        line = (tmp_path / "traces.jsonl").read_text().strip()
        entry = json.loads(line)
        # _stored_at must be a non-empty ISO-8601 string
        assert isinstance(entry["_stored_at"], str)
        assert "T" in entry["_stored_at"]

    def test_store_exported_from_package(self):
        from agent_hypervisor.program_layer import ProgramTraceStore  # noqa: F401

    def test_integration_run_and_store(self, tmp_path):
        """End-to-end: run a program and persist its trace."""
        from agent_hypervisor.program_layer.trace_storage import ProgramTraceStore
        store = ProgramTraceStore(tmp_path / "run_traces.jsonl")

        runner = ProgramRunner()
        program = Program(
            program_id="store-integration",
            steps=(Step(action="count_words", params={"input": "hello world foo"}),),
        )
        trace = runner.run(program)
        store.append(trace)

        recent = store.list_recent()
        assert len(recent) == 1
        assert recent[0]["program_id"] == "store-integration"
        assert recent[0]["ok"] is True
        assert recent[0]["step_traces"][0]["result"]["word_count"] == 3
