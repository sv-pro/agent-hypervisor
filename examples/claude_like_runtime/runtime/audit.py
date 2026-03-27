"""
audit.py — Structured event log for world/tool runtime activity.

Every world switch, tool call, result, and absence is recorded here.
The audit log is the ground truth of what the agent attempted and
what the world allowed.
"""

from __future__ import annotations
import json
from datetime import datetime, timezone


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3] + "Z"


class AuditLogger:
    def __init__(self, verbose: bool = True) -> None:
        self.verbose = verbose
        self.events: list[dict] = []

    def log_world_switch(self, world_name: str, tools: list[str]) -> None:
        event = {
            "ts": _ts(),
            "event": "world_switch",
            "world": world_name,
            "visible_tools": tools,
        }
        self.events.append(event)
        if self.verbose:
            print(f"[AUDIT] world_switch → {world_name}  tools={tools}")

    def log_tool_call(self, world_name: str, tool_name: str, inputs: dict) -> None:
        event = {
            "ts": _ts(),
            "event": "tool_call",
            "world": world_name,
            "tool": tool_name,
            "inputs": inputs,
        }
        self.events.append(event)
        if self.verbose:
            args_str = json.dumps(inputs, ensure_ascii=False)
            print(f"[AUDIT] tool_call   → {tool_name}({args_str})")

    def log_tool_result(self, world_name: str, tool_name: str, result: str) -> None:
        event = {
            "ts": _ts(),
            "event": "tool_result",
            "world": world_name,
            "tool": tool_name,
            "result_preview": result[:120],
        }
        self.events.append(event)
        if self.verbose:
            preview = result[:80].replace("\n", "\\n")
            print(f"[AUDIT] tool_result ← {tool_name}: {preview!r}")

    def log_absent_tool(self, world_name: str, tool_name: str) -> None:
        event = {
            "ts": _ts(),
            "event": "absent_tool",
            "world": world_name,
            "tool": tool_name,
        }
        self.events.append(event)
        if self.verbose:
            print(f"[AUDIT] absent_tool ! {tool_name} not in world '{world_name}'")

    def summary(self) -> None:
        calls = [e for e in self.events if e["event"] == "tool_call"]
        absences = [e for e in self.events if e["event"] == "absent_tool"]
        switches = [e for e in self.events if e["event"] == "world_switch"]
        print(
            f"\n[AUDIT SUMMARY] switches={len(switches)}  "
            f"calls={len(calls)}  absences={len(absences)}"
        )
