"""
sandbox_runtime.py — Minimal restricted execution environment for Phase 1.

Design principles:
    - Offline by default: no network, no subprocess, no filesystem.
    - Explicit bindings only: programs access only what is injected.
    - AST validation before exec(): forbidden operations fail at parse time.
    - Hard timeout via thread executor: programs cannot run indefinitely.
    - Fail closed: any security violation raises SandboxSecurityError, not silently
      falls through.

What programs CAN do:
    - Use a narrow set of safe built-in functions (see _SAFE_BUILTINS_NAMES).
    - Call injected binding functions: read_input(), emit_result(), json_dumps(),
      json_loads(), and any extras explicitly provided by the caller.
    - Perform arithmetic, string manipulation, loops, conditionals, list/dict ops.

What programs CANNOT do:
    - import (any module, including builtins via __import__)
    - eval / exec / compile
    - open / input / breakpoint
    - getattr / setattr / delattr / vars / dir / globals / locals
    - Access dunder attributes that expose interpreter internals
    - Spawn subprocesses or make network calls
    - Write to or read from the filesystem (no binding is injected for this)
    - Run for more than timeout_seconds wall-clock time

Timeout implementation note:
    Timeout is enforced by running exec() in a daemon worker thread. If the
    thread does not complete within timeout_seconds, a SandboxTimeoutError is
    raised in the calling thread. The worker thread is a daemon thread so it
    will not prevent process exit. A lingering thread (from a timed-out program)
    continues running until the process exits — this is a known CPython
    limitation when exec() is running a tight loop. The program result is never
    used after a timeout; the caller receives only the error.
"""

from __future__ import annotations

import ast
import builtins as _builtins_module
import json
import queue
import threading
from typing import Any

# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------

class SandboxError(Exception):
    """Base class for all sandbox execution errors."""


class SandboxSecurityError(SandboxError):
    """Raised when a program violates the sandbox security policy."""


class SandboxTimeoutError(SandboxError):
    """Raised when a program exceeds its wall-clock timeout."""


class SandboxRuntimeError(SandboxError):
    """Raised when a program raises an unhandled exception at runtime."""


# ---------------------------------------------------------------------------
# Safe builtins whitelist
# ---------------------------------------------------------------------------

# Only names on this list are exposed to sandbox programs via __builtins__.
# Everything else is absent — programs that reference an absent name get
# NameError, which is the correct failure mode.
_SAFE_BUILTINS_NAMES = frozenset({
    # Core types
    "bool", "bytes", "complex", "dict", "float", "frozenset", "int",
    "list", "set", "str", "tuple",
    # Type introspection (safe subset)
    "isinstance", "type",
    # Iteration helpers
    "all", "any", "enumerate", "filter", "iter", "map", "next",
    "range", "reversed", "sorted", "zip",
    # Math
    "abs", "divmod", "max", "min", "pow", "round", "sum",
    # String helpers
    "chr", "format", "hex", "oct", "ord", "repr",
    # Output (allowed but output goes to stdout — programs produce results
    # via emit_result(), not print, but we permit print for debugging)
    "print",
    # Length
    "len",
    # None/True/False are keywords in Python 3; included for completeness
    # (they are always in scope, not actually looked up via __builtins__)
    "None", "True", "False",
    # Safe exceptions
    "ArithmeticError", "AttributeError", "Exception", "IndexError",
    "KeyError", "NameError", "RuntimeError", "StopIteration",
    "TypeError", "ValueError", "ZeroDivisionError", "NotImplementedError",
    # Needed by emit_result / read_input to raise naturally
    "NotImplemented",
})

# Build the actual safe builtins dict once at import time.
_SAFE_BUILTINS: dict[str, Any] = {
    name: getattr(_builtins_module, name)
    for name in _SAFE_BUILTINS_NAMES
    if hasattr(_builtins_module, name)
}

# ---------------------------------------------------------------------------
# Forbidden names (secondary check in AST visitor)
# ---------------------------------------------------------------------------

_FORBIDDEN_CALL_NAMES = frozenset({
    "__import__", "eval", "exec", "compile",
    "open", "input", "breakpoint",
    "getattr", "setattr", "delattr",
    "globals", "locals", "vars", "dir",
    "reload", "memoryview",
    "classmethod", "staticmethod", "property", "super",
    "object",
})

# Dunder attributes that expose interpreter internals and must never be
# accessed via attribute syntax.
_FORBIDDEN_ATTRS = frozenset({
    "__builtins__", "__import__", "__loader__", "__spec__",
    "__code__", "__globals__", "__closure__", "__dict__",
    "__class__", "__bases__", "__mro__", "__subclasses__",
})

# ---------------------------------------------------------------------------
# AST security validator
# ---------------------------------------------------------------------------

class _SecurityValidator(ast.NodeVisitor):
    """
    Walk the AST and raise SandboxSecurityError on any forbidden construct.

    Checked constructs:
        - ast.Import / ast.ImportFrom  → any import statement
        - ast.Call(func=Name(id=...))  → calls to forbidden built-in names
        - ast.Attribute(attr=...)      → access to forbidden dunder attributes
        - ast.Global                   → global declarations
        - ast.Nonlocal                 → nonlocal declarations
    """

    def visit_Import(self, node: ast.Import) -> None:
        raise SandboxSecurityError(
            "import statements are not allowed in the sandbox"
        )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        raise SandboxSecurityError(
            "from...import is not allowed in the sandbox"
        )

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            if node.func.id in _FORBIDDEN_CALL_NAMES:
                raise SandboxSecurityError(
                    f"call to '{node.func.id}' is not allowed in the sandbox"
                )
        elif isinstance(node.func, ast.Attribute):
            if node.func.attr in _FORBIDDEN_ATTRS:
                raise SandboxSecurityError(
                    f"access to attribute '{node.func.attr}' is not allowed "
                    "in the sandbox"
                )
        # Recurse into call arguments and function expression
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in _FORBIDDEN_ATTRS:
            raise SandboxSecurityError(
                f"access to attribute '{node.attr}' is not allowed in the sandbox"
            )
        self.generic_visit(node)

    def visit_Global(self, node: ast.Global) -> None:
        raise SandboxSecurityError(
            "'global' declarations are not allowed in the sandbox"
        )

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        raise SandboxSecurityError(
            "'nonlocal' declarations are not allowed in the sandbox"
        )


def _validate_ast(source: str) -> ast.Module:
    """
    Parse source and validate it against the security policy.

    Returns the parsed AST module on success.
    Raises SandboxSecurityError if any forbidden construct is present.
    Raises SandboxSecurityError (wrapping SyntaxError) if the source is invalid Python.
    """
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as exc:
        raise SandboxSecurityError(f"syntax error in program: {exc}") from exc
    _SecurityValidator().visit(tree)
    return tree


# ---------------------------------------------------------------------------
# Default binding factory — injected into every sandbox
# ---------------------------------------------------------------------------

def _make_default_bindings(
    input_value: Any,
    result_holder: list,
) -> dict[str, Any]:
    """
    Build the standard sandbox bindings.

    These are the bindings that appear in every sandbox regardless of the
    plan's allowed_bindings list.  They are the only safe way for a program
    to receive input and produce output.

    Bindings:
        read_input()         — returns the input value provided to the sandbox
        emit_result(value)   — stores value as the program's result
        json_dumps(obj)      — safe json.dumps (indent=2, default=str)
        json_loads(s)        — safe json.loads
    """

    def read_input() -> Any:
        return input_value

    def emit_result(value: Any) -> None:
        if result_holder:
            result_holder[0] = value
        else:
            result_holder.append(value)

    def json_dumps(obj: Any) -> str:
        return json.dumps(obj, indent=2, default=str)

    def json_loads(s: str) -> Any:
        return json.loads(s)

    return {
        "read_input": read_input,
        "emit_result": emit_result,
        "json_dumps": json_dumps,
        "json_loads": json_loads,
    }


# ---------------------------------------------------------------------------
# SandboxRuntime
# ---------------------------------------------------------------------------

class SandboxRuntime:
    """
    Minimal restricted execution environment.

    Usage::

        runtime = SandboxRuntime(
            allowed_bindings=("read_input", "emit_result", "json_dumps"),
            timeout_seconds=5.0,
        )
        result = runtime.run(
            program_source="emit_result({'count': len(read_input().split())})",
            input_value="hello world foo",
        )
        # result == {'count': 3}

    The ``allowed_bindings`` parameter controls which binding names the program
    can see.  Any binding not in this set is not injected into the program's
    local namespace.

    The ``input_value`` parameter is the data the program receives via
    ``read_input()``.  It must be JSON-serialisable or a plain Python value;
    it is never evaluated — it is passed as-is to ``read_input()``.

    Additional bindings can be supplied via ``extra_bindings``.  These are
    subject to the same ``allowed_bindings`` filter.

    Raises:
        SandboxSecurityError  — forbidden construct in program, or syntax error
        SandboxTimeoutError   — program exceeded timeout_seconds
        SandboxRuntimeError   — program raised an unhandled exception at runtime
    """

    def __init__(
        self,
        allowed_bindings: tuple[str, ...],
        timeout_seconds: float = 5.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError(f"timeout_seconds must be positive, got {timeout_seconds!r}")
        self._allowed_bindings = frozenset(allowed_bindings)
        self._timeout_seconds = timeout_seconds

    def run(
        self,
        program_source: str,
        input_value: Any = None,
        extra_bindings: dict[str, Any] | None = None,
    ) -> Any:
        """
        Validate and execute ``program_source`` in the sandbox.

        Returns the value passed to ``emit_result()``.
        Returns ``None`` if the program never calls ``emit_result()``.

        The execution order is:
            1. AST validation (security policy check — no exec() yet)
            2. Compile to code object
            3. Build restricted globals + filtered local bindings
            4. Execute in a thread with timeout
            5. Return result from emit_result() or None
        """
        # Step 1 & 2: validate and compile
        tree = _validate_ast(program_source)
        try:
            code = compile(tree, filename="<sandbox>", mode="exec")
        except Exception as exc:
            raise SandboxSecurityError(
                f"failed to compile sandbox program: {exc}"
            ) from exc

        # Step 3: build execution environment
        result_holder: list = []
        default_bindings = _make_default_bindings(input_value, result_holder)

        # Merge extra_bindings (caller-supplied) with defaults
        all_bindings: dict[str, Any] = {**default_bindings}
        if extra_bindings:
            all_bindings.update(extra_bindings)

        # Filter: only expose bindings that are in allowed_bindings
        safe_locals: dict[str, Any] = {
            name: value
            for name, value in all_bindings.items()
            if name in self._allowed_bindings
        }

        # Restricted globals: safe builtins only, no module-level access
        safe_globals: dict[str, Any] = {"__builtins__": _SAFE_BUILTINS}

        # Step 4: execute in a daemon thread with timeout.
        #
        # We use a raw daemon thread (not ThreadPoolExecutor) so that the
        # thread does not prevent the calling thread from returning after a
        # timeout.  ThreadPoolExecutor.__exit__ calls shutdown(wait=True),
        # which would block indefinitely if the sandboxed program is in a
        # tight loop.  A daemon thread is silently abandoned when the timeout
        # fires; it will be reaped when the process exits.
        exc_queue: queue.Queue[BaseException] = queue.Queue(maxsize=1)

        def _run() -> None:
            try:
                exec(code, safe_globals, safe_locals)  # noqa: S102
            except BaseException as _exc:  # noqa: BLE001
                try:
                    exc_queue.put_nowait(_exc)
                except queue.Full:
                    pass

        worker = threading.Thread(target=_run, daemon=True)
        worker.start()
        worker.join(timeout=self._timeout_seconds)

        if worker.is_alive():
            # Thread is still running — timeout exceeded.
            # The thread runs until the process exits (daemon=True).
            raise SandboxTimeoutError(
                f"program exceeded timeout of {self._timeout_seconds}s"
            )

        # Thread finished — check for exceptions
        try:
            exc = exc_queue.get_nowait()
        except queue.Empty:
            exc = None

        if exc is not None:
            if isinstance(exc, SandboxError):
                raise exc
            raise SandboxRuntimeError(
                f"program raised an unhandled exception: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        # Step 5: return result
        return result_holder[0] if result_holder else None
