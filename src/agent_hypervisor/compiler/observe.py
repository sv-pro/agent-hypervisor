"""Observe: load and validate structured execution traces."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ToolCall:
    """A single tool invocation recorded during workflow execution."""

    tool: str
    params: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    safe: bool = True  # annotated in trace; True if execution was benign


@dataclass
class ExecutionTrace:
    """A structured record of tool calls made by a workflow."""

    workflow_id: str
    calls: list[ToolCall] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def trace_from_dict(data: dict) -> ExecutionTrace:
    """Parse an ExecutionTrace from a dict.

    Expected format::

        {
          "workflow_id": "...",
          "metadata": {...},
          "calls": [
            {"tool": "read_file", "params": {"path": "docs/index.md"},
             "result": null, "safe": true}
          ]
        }
    """
    calls = [
        ToolCall(
            tool=call["tool"],
            params=call.get("params", {}),
            result=call.get("result"),
            safe=call.get("safe", True),
        )
        for call in data.get("calls", [])
    ]
    return ExecutionTrace(
        workflow_id=data["workflow_id"],
        calls=calls,
        metadata=data.get("metadata", {}),
    )


def load_trace(path: Path | str) -> ExecutionTrace:
    """Load an ExecutionTrace from a JSON file.

    Args:
        path: Path to the JSON trace file.

    Returns:
        Parsed ExecutionTrace.
    """
    path = Path(path)
    with path.open() as fh:
        data = json.load(fh)
    return trace_from_dict(data)
