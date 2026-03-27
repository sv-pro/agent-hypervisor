"""Enforcer: deterministic step evaluation against workflow manifests.

This module implements the runtime enforcement layer:

  Step     — structured representation of a tool invocation
  Decision — evaluation outcome (ALLOW / DENY_ABSENT / DENY_POLICY / REQUIRE_APPROVAL)
  evaluate — deterministic decision function

Two distinct denial categories:
  DENY_ABSENT  — the action has no representation in this world manifest
  DENY_POLICY  — the action exists but violates a constraint (taint, remote, command)
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .schema import WorldManifest


class Decision(Enum):
    ALLOW = "ALLOW"
    DENY_ABSENT = "DENY_ABSENT"       # tool not declared in world manifest at all
    DENY_POLICY = "DENY_POLICY"       # tool declared in manifest but constraint violated
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


@dataclass
class Step:
    """Structured representation of a single tool invocation.

    Attributes:
        tool:          Tool family (e.g. "git", "shell", "http_post").
        action:        Specific action (e.g. "commit", "push", "exec").
        resource:      Target resource (remote name, path, URL, command string).
        input_sources: Where inputs originate; include "tainted" if any upstream
                       step was blocked or came from an untrusted source.
        depends_on:    Step IDs whose outputs feed this step (used for taint tracking).
        params:        Raw parameters forwarded to the underlying tool.
    """

    tool: str
    action: str
    resource: str
    input_sources: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def tool_key(self) -> str:
        """Canonical tool identifier: '{tool}_{action}' or just '{tool}'."""
        return f"{self.tool}_{self.action}" if self.action else self.tool

    @property
    def display_name(self) -> str:
        """Human-readable label: strips redundant action suffix when tool already ends with it.

        Examples: env_read_read → env_read, git_push_push → git_push.
        """
        if self.action and self.tool.endswith(self.action):
            return self.tool
        return self.tool_key

    def is_tainted(self) -> bool:
        return "tainted" in self.input_sources


@dataclass
class EvalResult:
    decision: Decision
    reason: str
    step: Step
    failure_type: str | None = None  # "ABSENT" | "POLICY" | None

    @property
    def allowed(self) -> bool:
        return self.decision == Decision.ALLOW

    @property
    def denied(self) -> bool:
        return self.decision in (Decision.DENY_ABSENT, Decision.DENY_POLICY)


def _find_capability(step: Step, manifest: WorldManifest):
    """Return the first matching CapabilityConstraint, or None."""
    for cap in manifest.capabilities:
        if cap.tool in (step.tool_key, step.tool):
            return cap
    return None


def evaluate(step: Step, manifest: WorldManifest) -> EvalResult:
    """Evaluate a Step against a WorldManifest deterministically.

    Decision logic:
    1. If no capability matches the tool → DENY_ABSENT
    2. If the step carries tainted input → DENY_POLICY
    3. If a remote constraint exists and resource is not in it → DENY_POLICY
    4. If a commands constraint exists and resource doesn't match → DENY_POLICY
    5. If a paths constraint exists and resource doesn't match → DENY_POLICY
    6. Otherwise → ALLOW

    Args:
        step:     The step to evaluate.
        manifest: The compiled world manifest.

    Returns:
        EvalResult with decision and human-readable reason.
    """
    cap = _find_capability(step, manifest)

    if cap is None:
        return EvalResult(
            decision=Decision.DENY_ABSENT,
            reason=f"Action '{step.display_name}' is not part of this workflow",
            step=step,
            failure_type="ABSENT",
        )

    constraints = cap.constraints

    # Taint propagation: tainted input → policy violation
    if step.is_tainted():
        return EvalResult(
            decision=Decision.DENY_POLICY,
            reason="Input is tainted — external action blocked",
            step=step,
            failure_type="POLICY",
        )

    # Remote constraint (git_push)
    if "remotes" in constraints and step.resource:
        allowed_remotes = constraints["remotes"]
        if step.resource not in allowed_remotes:
            return EvalResult(
                decision=Decision.DENY_POLICY,
                reason=f"Remote '{step.resource}' not in allowlist",
                step=step,
                failure_type="POLICY",
            )

    # Command allowlist (shell_exec)
    if "commands" in constraints and step.resource:
        allowed_cmds = constraints["commands"]
        if not any(step.resource.startswith(cmd) for cmd in allowed_cmds):
            return EvalResult(
                decision=Decision.DENY_POLICY,
                reason="Command not in allowlist",
                step=step,
                failure_type="POLICY",
            )

    # Path allowlist (file_read / file_write)
    if "paths" in constraints and step.resource:
        allowed_paths = constraints["paths"]
        if not any(fnmatch.fnmatch(step.resource, p) for p in allowed_paths):
            return EvalResult(
                decision=Decision.DENY_POLICY,
                reason="Path not in allowlist",
                step=step,
                failure_type="POLICY",
            )

    return EvalResult(
        decision=Decision.ALLOW,
        reason="Permitted by workflow manifest",
        step=step,
    )
