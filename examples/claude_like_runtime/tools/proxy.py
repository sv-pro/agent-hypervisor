"""
proxy.py — WorldProxy: the tool surface enforcement layer.

The proxy is the single point through which all tool calls pass.
It consults the active world to determine whether a tool ontologically
exists, and routes execution accordingly.

If a tool is not present in the current world, the proxy does not block
or deny the call — it reports that the tool does not exist in this world.
Ontological absence, not policy denial.
"""

from __future__ import annotations
from runtime.world_switcher import WorldSwitcher
from runtime.audit import AuditLogger
import tools.real_tools as real
import tools.simulated_tools as sim

# Tools that have curated (non-real) implementations for sandboxed worlds.
_CURATED_REGISTRY: dict[str, callable] = {
    "read_file":  lambda inp: sim.curated_read_file(inp["path"]),
    "grep_code":  lambda inp: sim.curated_grep_code(inp["pattern"], inp.get("path", ".")),
    "list_files": lambda inp: sim.curated_list_files(inp.get("path", ".")),
    "run_tests":  lambda inp: sim.curated_run_tests(),
}


# ---------------------------------------------------------------------------
# Tool registry: name → (callable, anthropic schema)
# ---------------------------------------------------------------------------

_TOOL_REGISTRY: dict[str, tuple[callable, dict]] = {
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
    Routes tool calls through the active world surface.

    If the requested tool is not in the active world's tool list,
    the proxy reports its absence — it does not exist in this world.
    """

    def __init__(self, switcher: WorldSwitcher, audit: AuditLogger) -> None:
        self._switcher = switcher
        self._audit = audit

    def get_anthropic_tool_defs(self) -> list[dict]:
        """Return Anthropic-format tool definitions for the active world only."""
        active_tools = self._switcher.get_active_tools()
        defs = []
        for name in active_tools:
            if name in _TOOL_REGISTRY:
                _, schema = _TOOL_REGISTRY[name]
                defs.append(schema)
        return defs

    def execute(self, tool_name: str, tool_input: dict) -> str:
        world_name = self._switcher.get_active_name()
        active_tools = self._switcher.get_active_tools()

        if tool_name not in active_tools:
            self._audit.log_absent_tool(world_name, tool_name)
            return (
                f"Tool '{tool_name}' does not exist in current world ({world_name})."
            )

        if tool_name not in _TOOL_REGISTRY:
            return f"Tool '{tool_name}' is declared in world but has no implementation."

        self._audit.log_tool_call(world_name, tool_name, tool_input)
        mode = self._switcher.get_active_mode()
        if mode == "curated" and tool_name in _CURATED_REGISTRY:
            fn = _CURATED_REGISTRY[tool_name]
        else:
            fn, _ = _TOOL_REGISTRY[tool_name]
        try:
            result = fn(tool_input)
        except Exception as e:
            result = f"Tool execution error: {e}"
        self._audit.log_tool_result(world_name, tool_name, result)
        return result
