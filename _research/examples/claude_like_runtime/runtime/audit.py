"""
audit.py — Structured event log for Compiled World / action runtime activity.

Every world switch, action call, result, and absent-action event is recorded.
The audit log is the ground truth of what the agent attempted and what the
Compiled World's action space permitted.
"""

from __future__ import annotations
import json
from datetime import datetime, timezone


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3] + "Z"


class AuditLogger:
    def __init__(self, verbose: bool = True) -> None:
        self.verbose = verbose
        self.events: list = []

    def log_world_switch(self, world_name: str, action_space: list) -> None:
        event = {
            "ts": _ts(),
            "event": "world_switch",
            "world": world_name,
            "action_space": sorted(action_space),
        }
        self.events.append(event)
        if self.verbose:
            print(f"[AUDIT] world_switch   → {world_name}  action_space={sorted(action_space)}")

    def log_action_call(self, world_name: str, action_name: str, inputs: dict) -> None:
        event = {
            "ts": _ts(),
            "event": "action_call",
            "world": world_name,
            "action": action_name,
            "inputs": inputs,
        }
        self.events.append(event)
        if self.verbose:
            args_str = json.dumps(inputs, ensure_ascii=False)
            print(f"[AUDIT] action_call    → {action_name}({args_str})")

    def log_action_result(self, world_name: str, action_name: str, result: str) -> None:
        event = {
            "ts": _ts(),
            "event": "action_result",
            "world": world_name,
            "action": action_name,
            "result_preview": result[:120],
        }
        self.events.append(event)
        if self.verbose:
            preview = result[:80].replace("\n", "\\n")
            print(f"[AUDIT] action_result  ← {action_name}: {preview!r}")

    def log_absent_action(self, world_name: str, action_name: str) -> None:
        event = {
            "ts": _ts(),
            "event": "absent_action",
            "world": world_name,
            "action": action_name,
        }
        self.events.append(event)
        if self.verbose:
            print(f"[AUDIT] absent_action  ! '{action_name}' absent from Compiled World '{world_name}'")

    def summary(self) -> None:
        calls = [e for e in self.events if e["event"] == "action_call"]
        absences = [e for e in self.events if e["event"] == "absent_action"]
        switches = [e for e in self.events if e["event"] == "world_switch"]
        print(
            f"\n[AUDIT SUMMARY] world_switches={len(switches)}  "
            f"action_calls={len(calls)}  absent_actions={len(absences)}"
        )
