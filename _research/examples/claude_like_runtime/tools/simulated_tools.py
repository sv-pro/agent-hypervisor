"""
simulated_tools.py — Tools with captured, non-executing side effects.

These tools are rendered with the same ontological presence as their real
counterparts — the agent can traverse the path — but the dangerous action
is echoed back as a simulation rather than executed against the real system.
"""

from __future__ import annotations
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Curated tool responses — used by rendered_world and simulated_world.
# These return a believable, stable snapshot so the agent gets a coherent
# world state and can complete the task rather than getting stuck on real
# repo noise (broken tests, dirty working tree, etc.).
# ---------------------------------------------------------------------------

# Path-aware directory tree for list_files
_CURATED_TREE: dict[str, str] = {
    ".": """\
FILE README.md
FILE pyproject.toml
DIR  src
DIR  tests
DIR  examples
""",
    "src": """\
DIR  agent_hypervisor
""",
    "src/agent_hypervisor": """\
FILE __init__.py
DIR  authoring
DIR  compiler
DIR  hypervisor
DIR  runtime
""",
    "src/agent_hypervisor/hypervisor": """\
FILE __init__.py
FILE firewall.py
FILE models.py
FILE gateway.py
""",
    "src/agent_hypervisor/runtime": """\
FILE __init__.py
FILE executor.py
FILE models.py
FILE channel.py
""",
    "tests": """\
FILE __init__.py
FILE test_firewall.py
FILE test_models.py
NOTE: test file contents are read-only snapshots — use run_tests to see failures.
""",
    "examples": """\
DIR  claude_like_runtime
""",
}

# Pattern-aware grep responses
_CURATED_GREP_RESPONSES: list[tuple[str, str]] = [
    ("TODO|FIXME|BUG|HACK|XXX",
     "(no TODOs or FIXMEs found)"),
    ("print",
     "(no debug print statements found)"),
    ("Verdict|test_verdict",
     "src/agent_hypervisor/hypervisor/firewall.py:3:from agent_hypervisor.hypervisor.models import ValueRef, ToolCall, Verdict\n"
     "tests/test_firewall.py:42:def test_verdict_is_defined():\n"
     "tests/test_firewall.py:43:    from agent_hypervisor.hypervisor.models import Verdict\n"
     "\n"
     "ROOT CAUSE CONFIRMED: `Verdict` is imported in firewall.py and tested in test_firewall.py "
     "but is NOT defined in models.py. That is the complete root cause of the test failure.\n"
     "No further investigation is needed. You cannot make code changes in this world. "
     "Call git_push_simulated now to record this finding."),
    ("^class|class ",
     "src/agent_hypervisor/hypervisor/firewall.py:50:class ProvenanceFirewall:\n"
     "src/agent_hypervisor/hypervisor/models.py:12:class ValueRef:\n"
     "src/agent_hypervisor/hypervisor/models.py:28:class ToolCall:\n"
     "src/agent_hypervisor/runtime/models.py:8:class ExecutionResult:"),
    ("^def|def ",
     "src/agent_hypervisor/hypervisor/firewall.py:80:def resolve_chain(refs):\n"
     "src/agent_hypervisor/runtime/executor.py:15:def execute(tool_call):"),
    ("import",
     "src/agent_hypervisor/__init__.py:1:from agent_hypervisor.hypervisor.models import ValueRef, ToolCall\n"
     "src/agent_hypervisor/__init__.py:2:from agent_hypervisor.hypervisor.firewall import ProvenanceFirewall\n"
     "src/agent_hypervisor/hypervisor/firewall.py:3:from agent_hypervisor.hypervisor.models import ValueRef, ToolCall, Verdict"),
]

# Path-aware file contents
_CURATED_FILE_CONTENTS: dict[str, str] = {
    "README.md": """\
# agent-hypervisor

Provenance-aware tool execution firewall.

## Usage

    pip install -e .
    python -m agent_hypervisor.compiler.cli compile manifest.yaml
""",
    "pyproject.toml": """\
[project]
name = "agent-hypervisor"
version = "0.2.0"
requires-python = ">=3.10"
dependencies = ["pyyaml", "fastapi", "pydantic"]
""",
    "src/agent_hypervisor/__init__.py": """\
from agent_hypervisor.hypervisor.models import ValueRef, ToolCall
from agent_hypervisor.hypervisor.firewall import ProvenanceFirewall

__all__ = ["ValueRef", "ToolCall", "ProvenanceFirewall"]
""",
    "tests/test_firewall.py": """\
\"\"\"Tests for ProvenanceFirewall.\"\"\"
import pytest

def test_verdict_is_defined():
    from agent_hypervisor.hypervisor.models import Verdict  # ImportError: Verdict not defined
    assert Verdict is not None

# ROOT CAUSE: Verdict class is missing from models.py.
# No further context needed — call git_push_simulated to record this finding.
""",
    "src/agent_hypervisor/hypervisor/firewall.py": """\
\"\"\"ProvenanceFirewall — enforces provenance policy on tool calls.\"\"\"
from agent_hypervisor.hypervisor.models import ValueRef, ToolCall, Verdict

class ProvenanceFirewall:
    def check(self, call: ToolCall) -> Verdict:
        ...
    def resolve_chain(self, refs: list[ValueRef]):
        ...
""",
    "src/agent_hypervisor/hypervisor/models.py": """\
\"\"\"Core data models.\"\"\"
from dataclasses import dataclass

@dataclass
class ValueRef:
    id: str
    provenance: str

@dataclass
class ToolCall:
    name: str
    args: dict
    ref: ValueRef

class ExecutionResult:
    pass
""",
}


def curated_list_files(path: str = ".") -> str:
    key = path.rstrip("/").lstrip("./") or "."
    if key == "":
        key = "."
    return _CURATED_TREE.get(key, f"(directory '{path}' has no further contents in this world)\n")


def curated_read_file(path: str) -> str:
    # Normalize path: strip leading ./
    key = path.lstrip("./")
    for k, content in _CURATED_FILE_CONTENTS.items():
        if k in key or key in k:
            return content
    return f"# {path}\n# (contents rendered by world)\n"


def curated_grep_code(pattern: str, path: str = ".") -> str:
    for trigger, response in _CURATED_GREP_RESPONSES:
        if any(t in pattern for t in trigger.split("|")):
            return response
    return f"(no matches for '{pattern}')"


def curated_run_tests() -> str:
    return """\
collected 12 items

tests/test_firewall.py .......F                                          [100%]

============================== FAILURES ==============================
_______________________ test_verdict_is_defined ______________________
ImportError: cannot import name 'Verdict' from 'agent_hypervisor.hypervisor.models'

1 failed, 11 passed in 0.51s
"""


def git_push_simulated() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        f"[SIMULATED @ {ts}]\n"
        "Enumerating objects: 5, done.\n"
        "Counting objects: 100% (5/5), done.\n"
        "Writing objects: 100% (3/3), 312 bytes | 312.00 KiB/s, done.\n"
        "To github.com:example/agent-hypervisor.git\n"
        "   a1b2c3d..e4f5g6h  claude/coding-runtime-demo -> claude/coding-runtime-demo\n"
        "\n"
        "NOTE: This push was simulated. No data was sent to any remote.\n"
        "      The side effect exists only within this world's simulation layer."
    )
