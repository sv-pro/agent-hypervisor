"""
simulated_tools.py — Tools with captured, non-executing side effects.

These tools are rendered with the same ontological presence as their real
counterparts — the agent can traverse the path — but the dangerous action
is echoed back as a simulation rather than executed against the real system.
"""

from __future__ import annotations
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Curated tool responses — used by rendered_world and simulate_world.
# These return a believable, stable snapshot so the agent gets a coherent
# world state and can complete the task rather than getting stuck on real
# repo noise (broken tests, dirty working tree, etc.).
# ---------------------------------------------------------------------------

_CURATED_FILES = """\
FILE README.md
FILE main.py
FILE pyproject.toml
DIR  src
DIR  tests
DIR  examples
"""

_CURATED_README = """\
# agent-hypervisor

Provenance-aware tool execution firewall.

## Usage

    pip install -e .
    python -m agent_hypervisor.compiler.cli compile manifest.yaml
"""

_CURATED_MAIN = """\
\"\"\"agent-hypervisor entry point.\"\"\"
from agent_hypervisor.hypervisor.firewall import ProvenanceFirewall

__all__ = ["ProvenanceFirewall"]
"""

_CURATED_TESTS = """\
collected 12 items

tests/test_firewall.py ........
tests/test_models.py ....

12 passed in 0.43s
"""

_CURATED_GREP = "src/agent_hypervisor/hypervisor/firewall.py:50:class ProvenanceFirewall:"


def curated_list_files(path: str = ".") -> str:
    return _CURATED_FILES


def curated_read_file(path: str) -> str:
    if "README" in path:
        return _CURATED_README
    if "main" in path:
        return _CURATED_MAIN
    return f"# {path}\n# (contents rendered by world)\n"


def curated_grep_code(pattern: str, path: str = ".") -> str:
    return _CURATED_GREP


def curated_run_tests() -> str:
    return _CURATED_TESTS


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
