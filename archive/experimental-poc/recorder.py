"""
recorder.py – Stage 1 of the Agent World Compiler pipeline.

A TraceRecorder sits between an agent and its tools.  Each time the agent
calls a tool, the caller records the event with ``record()``.  When the
workflow is complete, ``save()`` writes the trace to a JSON file that the
profiler (Stage 2) can consume.

Trace schema produced::

    {
      "trace_id":    str,        # stable identifier for this recording
      "workflow":    str,        # human label for the workflow being recorded
      "description": str,        # optional free-text description
      "recorded_at": ISO-8601,   # wall-clock timestamp when recording started
      "steps": [
        {
          "step_id":       str,        # "step-NNN", auto-assigned
          "tool":          str,        # tool name  (e.g. "git_commit")
          "action":        str,        # logical action (e.g. "write")
          "resource":      str,        # target URI   (e.g. "repo://local/commits")
          "input_sources": list[str],  # provenance labels (e.g. ["repo_local"])
          "depends_on":    list[str],  # step_ids this step depends on
          "metadata":      dict,       # arbitrary caller-supplied data
        },
        ...
      ]
    }

Usage::

    from awc.observe import TraceRecorder

    recorder = TraceRecorder(workflow="repo_maintenance")
    step_id = recorder.record(
        tool="fs_read",
        action="read",
        resource="repo://local/src/main.py",
        input_sources=["repo_local"],
    )
    recorder.save("traces/my_trace.json")

The recorder does **not** execute tool calls – it only records them.  It is
the caller's responsibility to call the real tool and then record the result.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TraceRecorder:
    """Records agent tool calls into a trace consumable by the AWC profiler.

    Parameters
    ----------
    workflow:
        Short label identifying the workflow being recorded
        (e.g. ``"repo_maintenance"``).
    trace_id:
        Stable identifier for this trace.  Auto-generated (UUID4) if omitted.
    description:
        Optional free-text description stored in the trace metadata.
    """

    def __init__(
        self,
        workflow: str,
        trace_id: str | None = None,
        description: str = "",
    ) -> None:
        self.workflow = workflow
        self.trace_id = trace_id or f"trace-{uuid.uuid4().hex[:12]}"
        self.description = description
        self._recorded_at: str = datetime.now(timezone.utc).isoformat()
        self._steps: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def record(
        self,
        tool: str,
        action: str,
        resource: str,
        input_sources: list[str],
        depends_on: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Append one tool-call event to the trace.

        Parameters
        ----------
        tool:
            Name of the tool that was called (e.g. ``"git_commit"``).
        action:
            Logical action category (e.g. ``"write"``, ``"read"``, ``"exec"``).
        resource:
            URI of the target resource (e.g. ``"repo://local/commits"``).
        input_sources:
            Provenance labels for data flowing into this call.  Must use the
            labels from the canonical trust map: ``"repo_local"``,
            ``"environment"``, ``"llm_output"``, ``"tool_output"``.
        depends_on:
            Step IDs that this call depends on.  Taint propagates from these
            steps during profiling.  Pass an empty list (the default) if the
            call is independent.
        metadata:
            Arbitrary extra data to store alongside the step (e.g. exit code,
            byte counts).  Not used by the pipeline; useful for debugging.

        Returns
        -------
        str
            The ``step_id`` assigned to this step (``"step-NNN"``).
        """
        step_id = f"step-{len(self._steps) + 1:03d}"
        step: dict[str, Any] = {
            "step_id": step_id,
            "tool": tool,
            "action": action,
            "resource": resource,
            "input_sources": list(input_sources),
            "depends_on": list(depends_on or []),
        }
        if metadata:
            step["metadata"] = dict(metadata)
        self._steps.append(step)
        return step_id

    def steps(self) -> list[dict[str, Any]]:
        """Return a copy of all recorded steps."""
        return [dict(s) for s in self._steps]

    def to_dict(self) -> dict[str, Any]:
        """Serialise the trace to a plain dict (matches the fixture schema)."""
        return {
            "trace_id": self.trace_id,
            "workflow": self.workflow,
            "description": self.description,
            "recorded_at": self._recorded_at,
            "steps": [dict(s) for s in self._steps],
        }

    def save(self, path: str | Path) -> Path:
        """Write the trace as a JSON file and return the resolved path.

        The parent directory is created if it does not exist.
        """
        dest = Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("w") as fh:
            json.dump(self.to_dict(), fh, indent=2)
        return dest

    def __len__(self) -> int:
        return len(self._steps)

    def __repr__(self) -> str:
        return (
            f"TraceRecorder(workflow={self.workflow!r}, "
            f"trace_id={self.trace_id!r}, steps={len(self._steps)})"
        )
