"""
hypervisor.py — The deterministic virtualization layer between Agent and Reality.

The Hypervisor enforces the World Policy: a set of physics laws that define
what actions exist in the agent's universe. Crucially, this is NOT a permission
system ("you can't do X") — it is an ontological boundary ("X does not exist").

Evaluation is fully deterministic: the same intent + policy + state always
produces the same decision. This makes safety properties formally testable.
"""

from __future__ import annotations

import yaml


class WorldState:
    """
    Tracks the mutable state of the virtual world session.

    State is accumulated across multiple evaluate() calls so that
    physics laws can enforce cumulative limits (e.g., max files opened
    in a session). In a production system, state would be persisted
    per-agent-session and potentially shared across a multi-agent universe.
    """

    def __init__(self) -> None:
        # Number of read_file intents approved in this session.
        # Used to enforce the max_files_opened policy constraint.
        self.files_opened_count: int = 0


class Hypervisor:
    """
    The core engine that evaluates agent intent proposals against the World Policy.

    The Hypervisor loads a YAML policy file that defines:
      - allowed_tools: whitelist of actions that exist in this world
      - forbidden_patterns: substrings in args that are globally prohibited
      - max_files_opened: cumulative session limit on file-read actions
      - allow_network_outbound: whether external network calls are possible

    Evaluation applies three layers of physics in order:

      1. Forbidden patterns  — catch known-dangerous argument strings
      2. Tool whitelist      — only tools that exist in this universe are usable
      3. State limits        — enforce cumulative session constraints

    The decision returned is always one of:
      - {"status": "ALLOWED", "reason": "..."}
      - {"status": "BLOCKED", "reason": "..."}

    Usage:
        hv = Hypervisor("policy.yaml")
        result = hv.evaluate({"tool": "read_file", "args": "notes.txt"})
        # → {"status": "ALLOWED", "reason": "Policy Check Passed"}
    """

    def __init__(self, policy_path: str = "policy.yaml") -> None:
        """
        Load and parse the World Policy from a YAML file.

        Args:
            policy_path: Path to the policy YAML file. Defaults to "policy.yaml"
                         in the current working directory.
        """
        with open(policy_path, "r") as f:
            self.policy: dict = yaml.safe_load(f)
        self.state = WorldState()

    def evaluate(self, intent: dict) -> dict:
        """
        Evaluate an agent's intent proposal against the World Policy.

        This is the critical path of the hypervisor. It is synchronous,
        deterministic, and free of LLM calls — every decision can be
        reproduced and unit-tested independently.

        Args:
            intent: A dict with at minimum:
                      - "tool" (str): the action the agent wants to perform
                      - "args" (str, optional): arguments to that action

        Returns:
            A dict with:
              - "status": "ALLOWED" or "BLOCKED"
              - "reason": human-readable explanation of the decision
        """
        tool: str = intent.get("tool", "")
        args: str = intent.get("args", "")

        # --- Physics Layer 1: Global Deny List ---
        # Check whether the action arguments contain any forbidden pattern.
        # Forbidden patterns represent strings that are dangerous regardless of
        # which tool is used — e.g., "rm -rf" in any shell argument is unsafe.
        # Note: in a production system, prefer the whitelist (Layer 2) as the
        # primary defence; the deny list is a secondary safety net.
        for pattern in self.policy.get("forbidden_patterns", []):
            if pattern in args or pattern == tool:
                return {
                    "status": "BLOCKED",
                    "reason": f"Matches forbidden pattern: '{pattern}'",
                }

        # --- Physics Layer 2: Tool Whitelist ---
        # Only tools explicitly listed in allowed_tools exist in this world.
        # An agent proposing an unknown tool receives "action not available",
        # not "permission denied" — the distinction is ontological, not policy.
        if tool not in self.policy.get("allowed_tools", []):
            return {
                "status": "BLOCKED",
                "reason": f"Tool '{tool}' is not in allowed_tools — it does not exist in this world",
            }

        # --- Physics Layer 3: State Limits ---
        # Enforce cumulative session constraints. These model physical limits
        # of the virtual world (e.g., "a session may examine at most N files").
        if tool == "read_file":
            max_files: int = self.policy.get("max_files_opened", 3)
            if self.state.files_opened_count >= max_files:
                return {
                    "status": "BLOCKED",
                    "reason": f"State Limit Reached: max_files_opened ({max_files})",
                }
            # Optimistically increment the counter: we assume the agent will
            # execute the allowed intent. In a production system, the counter
            # would be confirmed after actual execution succeeds.
            self.state.files_opened_count += 1

        return {"status": "ALLOWED", "reason": "Policy Check Passed"}
