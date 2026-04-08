"""
tests/program_layer/test_program_layer.py — Phase 1 program layer tests.

Test coverage:
    1.  direct execution path still works exactly as before
    2.  simple program plan executes successfully (count_lines, count_words, etc.)
    3.  program cannot access forbidden builtins (__import__, eval, exec, open)
    4.  program cannot import modules
    5.  program cannot access network/subprocess/filesystem via name
    6.  timeout is enforced
    7.  only injected bindings are available
    8.  invalid program plan fails closed (missing program_source, bad language)
    9.  syntax error in program source fails closed
    10. DeterministicTaskCompiler generates correct plans for all workflows
    11. DeterministicTaskCompiler falls back to DirectExecutionPlan for unknown workflows
    12. execution_mode and plan_id appear in every result
    13. ProgramExecutor rejects non-ProgramExecutionPlan types
    14. SandboxRuntime: dunder attribute access is blocked
    15. Compiler top_n validation (word_frequency)

Run with:
    pytest tests/program_layer/test_program_layer.py -v
"""

from __future__ import annotations

import pytest

from program_layer import (
    DeterministicTaskCompiler,
    DirectExecutionPlan,
    ProgramExecutionPlan,
    ProgramExecutor,
    SandboxRuntime,
    SandboxRuntimeError,
    SandboxSecurityError,
    SandboxTimeoutError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_plan(source: str, timeout: float = 5.0, bindings=None) -> ProgramExecutionPlan:
    if bindings is None:
        bindings = ("read_input", "emit_result", "json_dumps", "json_loads")
    return ProgramExecutionPlan(
        plan_id="test-plan",
        program_source=source,
        language="python",
        allowed_bindings=bindings,
        timeout_seconds=timeout,
    )


def _run(source: str, input_value=None, timeout: float = 5.0, bindings=None):
    plan = _make_plan(source, timeout=timeout, bindings=bindings)
    executor = ProgramExecutor()
    return executor.execute(plan, context={"input": input_value})


# ---------------------------------------------------------------------------
# 1. Direct execution path is unchanged
# ---------------------------------------------------------------------------

class TestDirectExecutionUnchanged:
    """DirectExecutionPlan has no new code; verify the type is stable."""

    def test_direct_plan_type(self):
        plan = DirectExecutionPlan(plan_id="d1")
        assert plan.plan_type == "direct"

    def test_direct_plan_is_frozen(self):
        plan = DirectExecutionPlan(plan_id="d1")
        with pytest.raises((AttributeError, TypeError)):
            plan.plan_id = "d2"  # type: ignore[misc]

    def test_program_executor_rejects_direct_plan(self):
        plan = DirectExecutionPlan(plan_id="d1")
        with pytest.raises(TypeError, match="ProgramExecutionPlan"):
            ProgramExecutor().execute(plan)


# ---------------------------------------------------------------------------
# 2. Simple program plans execute successfully
# ---------------------------------------------------------------------------

class TestSimpleProgramExecution:
    def test_emit_result_returns_value(self):
        result = _run("emit_result(42)")
        assert result["ok"] is True
        assert result["result"] == 42

    def test_count_lines(self):
        text = "line one\nline two\nline three"
        result = _run(
            "emit_result({'lines': len(read_input().splitlines())})",
            input_value=text,
        )
        assert result["ok"] is True
        assert result["result"]["lines"] == 3

    def test_count_words(self):
        text = "hello world foo bar"
        result = _run(
            "emit_result(len(read_input().split()))",
            input_value=text,
        )
        assert result["ok"] is True
        assert result["result"] == 4

    def test_no_emit_returns_none(self):
        result = _run("x = 1 + 1")
        assert result["ok"] is True
        assert result["result"] is None

    def test_json_dumps_binding_works(self):
        result = _run(
            "emit_result(json_dumps({'a': 1}))",
            bindings=("emit_result", "json_dumps"),
        )
        assert result["ok"] is True
        assert '"a": 1' in result["result"]

    def test_json_loads_binding_works(self):
        result = _run(
            'emit_result(json_loads(\'{"x": 99}\'))',
            bindings=("emit_result", "json_loads"),
        )
        assert result["ok"] is True
        assert result["result"] == {"x": 99}

    def test_result_has_metadata_fields(self):
        result = _run("emit_result(1)")
        assert "plan_id" in result
        assert result["execution_mode"] == "program"
        assert "duration_seconds" in result
        assert result["duration_seconds"] >= 0


# ---------------------------------------------------------------------------
# 3. Forbidden builtins
# ---------------------------------------------------------------------------

class TestForbiddenBuiltins:
    def test_cannot_call_eval(self):
        result = _run("eval('1+1')")
        assert result["ok"] is False
        assert result["error_type"] == "security"
        assert "eval" in result["error"]

    def test_cannot_call_exec(self):
        result = _run("exec('x=1')")
        assert result["ok"] is False
        assert result["error_type"] == "security"

    def test_cannot_call_open(self):
        result = _run("open('/etc/passwd')")
        assert result["ok"] is False
        assert result["error_type"] == "security"

    def test_cannot_call_compile(self):
        result = _run("compile('', '', 'exec')")
        assert result["ok"] is False
        assert result["error_type"] == "security"

    def test_cannot_call_getattr(self):
        result = _run("getattr(str, '__class__')")
        assert result["ok"] is False
        assert result["error_type"] == "security"

    def test_cannot_call_globals(self):
        result = _run("globals()")
        assert result["ok"] is False
        assert result["error_type"] == "security"

    def test_cannot_call_locals(self):
        result = _run("locals()")
        assert result["ok"] is False
        assert result["error_type"] == "security"

    def test_import_dunder_not_in_builtins(self):
        # __import__ is not in safe builtins, so it's a NameError at runtime
        # But the AST validator catches the call-to-forbidden-name pattern.
        result = _run("__import__('os')")
        assert result["ok"] is False
        # Either security (AST catch) or runtime (NameError)
        assert result["error_type"] in ("security", "runtime")


# ---------------------------------------------------------------------------
# 4. Import statements are blocked
# ---------------------------------------------------------------------------

class TestImportsBlocked:
    def test_bare_import_blocked(self):
        result = _run("import os")
        assert result["ok"] is False
        assert result["error_type"] == "security"
        assert "import" in result["error"]

    def test_from_import_blocked(self):
        result = _run("from os import path")
        assert result["ok"] is False
        assert result["error_type"] == "security"

    def test_import_subprocess_blocked(self):
        result = _run("import subprocess")
        assert result["ok"] is False
        assert result["error_type"] == "security"

    def test_import_socket_blocked(self):
        result = _run("import socket")
        assert result["ok"] is False
        assert result["error_type"] == "security"


# ---------------------------------------------------------------------------
# 5. Network / subprocess / filesystem access blocked
# ---------------------------------------------------------------------------

class TestIsolation:
    def test_os_not_accessible(self):
        # 'os' is not a binding and import is blocked; accessing it is NameError
        result = _run("emit_result(os.getcwd())")
        assert result["ok"] is False
        # NameError → runtime error (os not in scope)
        assert result["error_type"] in ("security", "runtime")

    def test_subprocess_not_accessible(self):
        result = _run("subprocess.run(['ls'])")
        assert result["ok"] is False
        assert result["error_type"] in ("security", "runtime")

    def test_dunder_builtins_blocked_via_attribute(self):
        result = _run("x = ().__class__.__bases__[0].__subclasses__()")
        # __class__ and __bases__ are blocked by AST validator
        assert result["ok"] is False
        assert result["error_type"] == "security"


# ---------------------------------------------------------------------------
# 6. Timeout is enforced
# ---------------------------------------------------------------------------

class TestTimeout:
    def test_infinite_loop_times_out(self):
        result = _run("while True: pass", timeout=0.1)
        assert result["ok"] is False
        assert result["error_type"] == "timeout"
        assert "0.1" in result["error"]

    def test_fast_program_completes_before_timeout(self):
        result = _run("emit_result(sum(range(1000)))", timeout=5.0)
        assert result["ok"] is True
        assert result["result"] == sum(range(1000))

    def test_zero_timeout_raises_at_construction(self):
        with pytest.raises(ValueError, match="positive"):
            SandboxRuntime(allowed_bindings=(), timeout_seconds=0.0)


# ---------------------------------------------------------------------------
# 7. Only injected bindings are available
# ---------------------------------------------------------------------------

class TestBindingScope:
    def test_uninjected_binding_is_nameError(self):
        # emit_result is not in allowed_bindings → NameError → runtime error
        result = _run("emit_result(1)", bindings=("read_input",))
        assert result["ok"] is False
        assert result["error_type"] == "runtime"

    def test_only_allowed_bindings_visible(self):
        # read_input injected, json_dumps not — json_dumps must not be accessible
        result = _run(
            "emit_result(json_dumps({}))",
            bindings=("read_input", "emit_result"),
        )
        assert result["ok"] is False
        assert result["error_type"] == "runtime"

    def test_read_input_returns_provided_value(self):
        result = _run(
            "emit_result(read_input())",
            input_value="hello",
        )
        assert result["ok"] is True
        assert result["result"] == "hello"

    def test_read_input_returns_none_when_not_provided(self):
        result = _run("emit_result(read_input() is None)")
        assert result["ok"] is True
        assert result["result"] is True


# ---------------------------------------------------------------------------
# 8. Invalid plan fails closed
# ---------------------------------------------------------------------------

class TestInvalidPlanFailsClosed:
    def test_missing_program_source_fails(self):
        plan = ProgramExecutionPlan(
            plan_id="no-source",
            program_source=None,
            allowed_bindings=("emit_result",),
        )
        result = ProgramExecutor().execute(plan)
        assert result["ok"] is False
        assert result["error_type"] == "validation"
        assert "program_source" in result["error"]

    def test_empty_program_source_fails(self):
        plan = ProgramExecutionPlan(
            plan_id="empty-source",
            program_source="",
            allowed_bindings=("emit_result",),
        )
        result = ProgramExecutor().execute(plan)
        assert result["ok"] is False
        assert result["error_type"] == "validation"

    def test_unsupported_language_fails(self):
        plan = ProgramExecutionPlan(
            plan_id="wrong-lang",
            program_source="emit_result(1)",
            language="ruby",
            allowed_bindings=("emit_result",),
        )
        result = ProgramExecutor().execute(plan)
        assert result["ok"] is False
        assert result["error_type"] == "validation"
        assert "ruby" in result["error"]


# ---------------------------------------------------------------------------
# 9. Syntax errors fail closed
# ---------------------------------------------------------------------------

class TestSyntaxErrorFailsClosed:
    def test_invalid_syntax_fails_closed(self):
        result = _run("def (broken")
        assert result["ok"] is False
        assert result["error_type"] == "security"
        assert "syntax" in result["error"].lower()

    def test_unclosed_string_fails_closed(self):
        result = _run('emit_result("hello)')
        assert result["ok"] is False
        assert result["error_type"] == "security"


# ---------------------------------------------------------------------------
# 10. DeterministicTaskCompiler — correct plans for all workflows
# ---------------------------------------------------------------------------

class TestDeterministicTaskCompiler:
    def setup_method(self):
        self.compiler = DeterministicTaskCompiler()
        self.executor = ProgramExecutor()

    def _compile_and_run(self, workflow: str, input_text: str, **kwargs) -> dict:
        intent = {"workflow": workflow, **kwargs}
        plan = self.compiler.compile(intent)
        assert plan.plan_type == "program", f"Expected program plan for {workflow!r}"
        return self.executor.execute(plan, context={"input": input_text})

    def test_count_lines_workflow(self):
        result = self._compile_and_run("count_lines", "a\nb\nc")
        assert result["ok"] is True
        assert result["result"]["line_count"] == 3

    def test_count_lines_empty_input(self):
        result = self._compile_and_run("count_lines", "")
        assert result["ok"] is True
        assert result["result"]["line_count"] == 0

    def test_count_words_workflow(self):
        result = self._compile_and_run("count_words", "hello world foo")
        assert result["ok"] is True
        assert result["result"]["word_count"] == 3

    def test_normalize_text_workflow(self):
        result = self._compile_and_run("normalize_text", "  HELLO WORLD  \n\n  FOO  ")
        assert result["ok"] is True
        norm = result["result"]["normalized"]
        assert norm == norm.lower()
        assert not norm.startswith(" ")
        assert not norm.endswith(" ")

    def test_word_frequency_workflow(self):
        result = self._compile_and_run(
            "word_frequency", "the cat sat on the mat the cat", top_n=3
        )
        assert result["ok"] is True
        top = result["result"]["top_words"]
        # "the" should appear 3 times and be first
        assert top[0][0] == "the"
        assert top[0][1] == 3
        assert len(top) <= 3

    def test_word_frequency_default_top_n(self):
        text = " ".join(["word"] * 5)
        result = self._compile_and_run("word_frequency", text)
        assert result["ok"] is True

    def test_compiled_plan_has_correct_fields(self):
        plan = self.compiler.compile({"workflow": "count_lines"})
        assert isinstance(plan, ProgramExecutionPlan)
        assert plan.language == "python"
        assert plan.timeout_seconds > 0
        assert "read_input" in plan.allowed_bindings
        assert "emit_result" in plan.allowed_bindings
        assert plan.program_source is not None and len(plan.program_source) > 0
        assert plan.metadata.get("workflow") == "count_lines"

    def test_same_workflow_same_program(self):
        # Compiler is deterministic: same workflow → same program_source
        plan1 = self.compiler.compile({"workflow": "count_words"})
        plan2 = self.compiler.compile({"workflow": "count_words"})
        assert plan1.program_source == plan2.program_source

    def test_custom_timeout(self):
        plan = self.compiler.compile({"workflow": "count_lines", "timeout_seconds": 2.0})
        assert plan.timeout_seconds == 2.0


# ---------------------------------------------------------------------------
# 11. Compiler falls back to DirectExecutionPlan for unsupported workflows
# ---------------------------------------------------------------------------

class TestCompilerFallback:
    def setup_method(self):
        self.compiler = DeterministicTaskCompiler()

    def test_unknown_workflow_returns_direct_plan(self):
        plan = self.compiler.compile({"workflow": "summon_dragon"})
        assert plan.plan_type == "direct"
        assert isinstance(plan, DirectExecutionPlan)

    def test_missing_workflow_returns_direct_plan(self):
        plan = self.compiler.compile({})
        assert plan.plan_type == "direct"

    def test_non_dict_intent_returns_direct_plan(self):
        plan = self.compiler.compile("count my words please")
        assert plan.plan_type == "direct"

    def test_none_intent_returns_direct_plan(self):
        plan = self.compiler.compile(None)
        assert plan.plan_type == "direct"


# ---------------------------------------------------------------------------
# 12. Compiler parameter validation
# ---------------------------------------------------------------------------

class TestCompilerValidation:
    def setup_method(self):
        self.compiler = DeterministicTaskCompiler()

    def test_invalid_top_n_raises(self):
        with pytest.raises(ValueError, match="top_n"):
            self.compiler.compile({"workflow": "word_frequency", "top_n": 0})

    def test_top_n_too_large_raises(self):
        with pytest.raises(ValueError, match="top_n"):
            self.compiler.compile({"workflow": "word_frequency", "top_n": 200})

    def test_invalid_timeout_raises(self):
        with pytest.raises(ValueError, match="timeout_seconds"):
            self.compiler.compile({"workflow": "count_lines", "timeout_seconds": -1})


# ---------------------------------------------------------------------------
# 13. SandboxRuntime — direct unit tests
# ---------------------------------------------------------------------------

class TestSandboxRuntime:
    def setup_method(self):
        self.runtime = SandboxRuntime(
            allowed_bindings=("read_input", "emit_result", "json_dumps", "json_loads"),
            timeout_seconds=5.0,
        )

    def test_simple_arithmetic(self):
        result = self.runtime.run("emit_result(2 + 2)")
        assert result == 4

    def test_string_manipulation(self):
        result = self.runtime.run(
            "emit_result(read_input().upper())",
            input_value="hello",
        )
        assert result == "HELLO"

    def test_no_emit_returns_none(self):
        result = self.runtime.run("x = 42")
        assert result is None

    def test_global_statement_blocked(self):
        with pytest.raises(SandboxSecurityError, match="global"):
            self.runtime.run("global x\nx = 1")

    def test_nonlocal_blocked(self):
        with pytest.raises(SandboxSecurityError, match="nonlocal"):
            self.runtime.run(
                "def f():\n    nonlocal x\n    pass"
            )

    def test_safe_exception_handling(self):
        result = self.runtime.run(
            "try:\n    x = 1/0\nexcept ZeroDivisionError:\n    emit_result('caught')"
        )
        assert result == "caught"

    def test_runtime_exception_wraps_to_sandbox_error(self):
        with pytest.raises(SandboxRuntimeError, match="ZeroDivisionError"):
            self.runtime.run("x = 1/0")

    def test_dunder_class_attribute_blocked(self):
        with pytest.raises(SandboxSecurityError, match="__class__"):
            self.runtime.run("emit_result([].__class__)")

    def test_dunder_builtins_attribute_blocked(self):
        with pytest.raises(SandboxSecurityError, match="__builtins__"):
            self.runtime.run('emit_result(({}).__builtins__)')

    def test_json_round_trip(self):
        result = self.runtime.run(
            "emit_result(json_loads(json_dumps({'x': [1,2,3]})))"
        )
        assert result == {"x": [1, 2, 3]}
