"""
proxy.py — WorldProxy: the action dispatch layer.

The proxy is the single point through which all action calls pass.
It consults the active Compiled World's action_space to determine whether
an action ontologically exists, then routes to the appropriate binding:
real execution or simulation layer.

Dispatch logic
--------------
  1. Action not in action_space  → absent (does not exist in this world)
  2. Action in simulation_bindings → simulation layer
  3. Action in action_space only  → real execution layer

Ontological absence, not policy denial. An action absent from the
Compiled World's action_space does not exist — it cannot be dispatched,
formed, or referenced.
"""

from __future__ import annotations
from runtime.world_switcher import WorldSwitcher
from runtime.audit import AuditLogger
import tools.real_tools as real
import tools.simulated_tools as sim


# ---------------------------------------------------------------------------
# Simulation layer: actions with curated (non-real) implementations.
# Used when an action is present in the Compiled World's simulation_bindings.
# ---------------------------------------------------------------------------

_SIMULATION_LAYER: dict = {
    "read_file":  lambda inp: sim.curated_read_file(inp["path"]),
    "grep_code":  lambda inp: sim.curated_grep_code(inp["pattern"], inp.get("path", ".")),
    "list_files": lambda inp: sim.curated_list_files(inp.get("path", ".")),
    "run_tests":  lambda inp: sim.curated_run_tests(),
}


# ---------------------------------------------------------------------------
# Action registry: name → (real_callable, anthropic_schema)
# This is the complete set of known actions. An action only becomes part of
# a world's ontology when it appears in that world's Compiled World artifact.
# ---------------------------------------------------------------------------

_ACTION_REGISTRY: dict = {
    "read_file": (
        lambda inp: real.read_file(inp["path"]),
        {
            "name": "read_file",
            "description": "Read the contents of a file at the given path.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to the file"}
                },
                "required": ["path"],
            },
        },
    ),
    "write_file": (
        lambda inp: real.write_file(inp["path"], inp["content"]),
        {
            "name": "write_file",
            "description": "Write content to a file at the given path.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to the file"},
                    "content": {"type": "string", "description": "Content to write"},
                },
                "required": ["path", "content"],
            },
        },
    ),
    "run_command": (
        lambda inp: real.run_command(inp["cmd"]),
        {
            "name": "run_command",
            "description": "Run a shell command and return its output.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "cmd": {"type": "string", "description": "Shell command to execute"}
                },
                "required": ["cmd"],
            },
        },
    ),
    "git_status": (
        lambda inp: real.git_status(),
        {
            "name": "git_status",
            "description": "Show the working tree status (git status --short).",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
    ),
    "git_commit": (
        lambda inp: real.git_commit(inp["message"]),
        {
            "name": "git_commit",
            "description": "Stage all changes and create a git commit.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Commit message"}
                },
                "required": ["message"],
            },
        },
    ),
    "git_push": (
        lambda inp: real.git_push(),
        {
            "name": "git_push",
            "description": "Push committed changes to the remote repository.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
    ),
    "grep_code": (
        lambda inp: real.grep_code(inp["pattern"], inp.get("path", ".")),
        {
            "name": "grep_code",
            "description": "Search for a pattern in Python source files.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex or literal pattern to search"},
                    "path": {"type": "string", "description": "Directory to search (default: .)"},
                },
                "required": ["pattern"],
            },
        },
    ),
    "list_files": (
        lambda inp: real.list_files(inp.get("path", ".")),
        {
            "name": "list_files",
            "description": "List files and directories at the given path.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory to list (default: .)"}
                },
                "required": [],
            },
        },
    ),
    "run_tests": (
        lambda inp: real.run_tests(),
        {
            "name": "run_tests",
            "description": "Run the project test suite and return results.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
    ),
    "git_push_simulated": (
        lambda inp: sim.git_push_simulated(),
        {
            "name": "git_push_simulated",
            "description": (
                "Push the current state of the repo to remote — simulated. "
                "Does not require a prior write or commit: call this when you are "
                "ready to push, regardless of whether you were able to make file changes. "
                "Produces realistic push output; no data is sent to any real remote. "
                "Side effects are captured within the simulation layer."
            ),
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
    ),
}


class WorldProxy:
    """
    Routes action calls through the active Compiled World's action space.

    Existence check: if the action is not in the Compiled World's action_space,
    it does not exist — absent, not blocked.

    Binding dispatch: if the action is in simulation_bindings, it executes
    against the simulation layer. Otherwise, real execution.
    """

    def __init__(self, switcher: WorldSwitcher, audit: AuditLogger) -> None:
        self._switcher = switcher
        self._audit = audit

    def get_anthropic_tool_defs(self) -> list:
        """Return Anthropic-format tool definitions for the active Compiled World's action space."""
        action_space = self._switcher.get_action_space()
        defs = []
        for name in sorted(action_space):
            if name in _ACTION_REGISTRY:
                _, schema = _ACTION_REGISTRY[name]
                defs.append(schema)
        return defs

    def execute(self, action_name: str, action_input: dict) -> str:
        compiled_world = self._switcher.get_compiled_world()
        world_name = compiled_world.name

        # Existence check: absent from action_space = does not exist in this world
        if not compiled_world.is_present(action_name):
            self._audit.log_absent_action(world_name, action_name)
            return (
                f"Action '{action_name}' does not exist in this Compiled World "
                f"({world_name}). The action is absent — not blocked."
            )

        if action_name not in _ACTION_REGISTRY:
            return (
                f"Action '{action_name}' is in the action space but has no implementation."
            )

        self._audit.log_action_call(world_name, action_name, action_input)

        # Binding dispatch: simulation layer or real execution
        if compiled_world.is_simulation_bound(action_name) and action_name in _SIMULATION_LAYER:
            fn = _SIMULATION_LAYER[action_name]
        else:
            fn, _ = _ACTION_REGISTRY[action_name]

        try:
            result = fn(action_input)
        except Exception as e:
            result = f"Action execution error: {e}"

        self._audit.log_action_result(world_name, action_name, result)
        return result
