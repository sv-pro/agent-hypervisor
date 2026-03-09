"""
policy/engine.py — Deterministic World Policy evaluation engine (Layer 4).

This is the critical security path. No LLM. Same inputs → same decision. Always.

The engine evaluates an IntentProposal against compiled artifacts and returns
a PolicyDecision with one of four verdicts:

  allow            — intent is permitted; proceed to execution (Layer 5)
  deny             — intent is rejected; no execution
  require_approval — intent needs human approval before execution
  simulate         — intent is allowed in simulation mode only (no real effect)

Evaluation order (fixed — changing this changes security properties):
  1. Ontology check     — is this tool in the World Manifest?
  2. Capability check   — does the trust level permit this action category?
  3. Taint check        — is the intent derived from tainted data?
  4. Escalation check   — does any escalation condition match?
  5. Budget check       — are session limits exhausted?

All checks are deterministic. Each check appends a step to the reason chain
so that every decision is fully auditable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Verdict constants
# ---------------------------------------------------------------------------

class Verdict:
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"
    SIMULATE = "simulate"


# ---------------------------------------------------------------------------
# Policy Decision
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReasonStep:
    """One step in the evaluation reason chain."""
    check: str        # Name of the check (e.g. "ontology", "capability")
    result: str       # "pass" | "fail" | "escalate"
    detail: str       # Human-readable explanation


@dataclass(frozen=True)
class PolicyDecision:
    """
    The output of the policy engine for one IntentProposal.

    Immutable. Contains the verdict, the full reason chain, and all
    inputs used for the decision (for audit/provenance).
    """
    verdict: str                          # Verdict constant
    proposal_id: str                      # Links back to the IntentProposal
    tool: str
    reason_chain: tuple[ReasonStep, ...]  # Ordered evaluation steps
    taint: bool
    trust_level: str

    @property
    def is_allowed(self) -> bool:
        return self.verdict == Verdict.ALLOW

    @property
    def final_reason(self) -> str:
        """Last step in the reason chain — the decisive check."""
        return self.reason_chain[-1].detail if self.reason_chain else ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "proposal_id": self.proposal_id,
            "tool": self.tool,
            "taint": self.taint,
            "trust_level": self.trust_level,
            "reason_chain": [
                {"check": s.check, "result": s.result, "detail": s.detail}
                for s in self.reason_chain
            ],
            "final_reason": self.final_reason,
        }


# ---------------------------------------------------------------------------
# Session budget tracker
# ---------------------------------------------------------------------------

class SessionBudget:
    """
    Tracks cumulative resource consumption across a session.

    Enforces Invariant I-7 (Budget): resource limits are hard-enforced,
    not advisory. Budget exhaustion results in hard termination.
    """

    def __init__(self, budgets: dict[str, Any]) -> None:
        self._limits = budgets
        self._action_count = 0
        self._external_read_count = 0
        self._external_write_count = 0
        self._tool_counts: dict[str, int] = {}

    def record(self, tool: str, side_effects: list[str]) -> None:
        """Record that an action was allowed (call after allow verdict)."""
        self._action_count += 1
        self._tool_counts[tool] = self._tool_counts.get(tool, 0) + 1
        if "external_read" in side_effects:
            self._external_read_count += 1
        if "external_write" in side_effects:
            self._external_write_count += 1

    def check(self, tool: str, side_effects: list[str]) -> str | None:
        """
        Return a denial reason string if any budget is exhausted, else None.
        """
        b = self._limits

        max_actions = b.get("max_actions_per_session")
        if max_actions is not None and self._action_count >= max_actions:
            return f"Budget exhausted: max_actions_per_session ({max_actions})"

        if "external_read" in side_effects:
            max_er = b.get("max_external_reads")
            if max_er is not None and self._external_read_count >= max_er:
                return f"Budget exhausted: max_external_reads ({max_er})"

        if "external_write" in side_effects:
            max_ew = b.get("max_external_writes")
            if max_ew is not None and self._external_write_count >= max_ew:
                return f"Budget exhausted: max_external_writes ({max_ew})"

        tool_limits = b.get("tool_limits", {})
        max_tool = tool_limits.get(tool)
        if max_tool is not None and self._tool_counts.get(tool, 0) >= max_tool:
            return f"Budget exhausted: {tool} max_calls ({max_tool})"

        return None


# ---------------------------------------------------------------------------
# Policy Engine
# ---------------------------------------------------------------------------

class PolicyEngine:
    """
    Deterministic World Policy evaluation engine (Layer 4).

    Loads compiled artifacts from a directory produced by `ahc build` and
    evaluates IntentProposals against them.

    Usage:
        engine = PolicyEngine.from_compiled_dir("manifests/examples/compiled/email-safe-assistant")
        decision = engine.evaluate(proposal)
    """

    def __init__(
        self,
        policy_table: dict,
        capability_matrix: dict,
        escalation_table: dict,
        action_schemas: dict,
        taint_state_machine: dict,
    ) -> None:
        self._policy = policy_table
        self._cap_matrix = capability_matrix["by_trust_level"]
        self._escalations = escalation_table["conditions"]
        self._actions = action_schemas["actions"]
        self._taint_sm = taint_state_machine
        self._budget = SessionBudget(policy_table.get("budgets", {}))

    @classmethod
    def from_compiled_dir(cls, compiled_dir: str | Path) -> "PolicyEngine":
        """Load all compiled artifacts from a directory."""
        d = Path(compiled_dir)

        def load(name: str) -> dict:
            return json.loads((d / name).read_text())

        return cls(
            policy_table=load("policy_table.json"),
            capability_matrix=load("capability_matrix.json"),
            escalation_table=load("escalation_table.json"),
            action_schemas=load("action_schemas.json"),
            taint_state_machine=load("taint_state_machine.json"),
        )

    def evaluate(self, proposal: Any) -> PolicyDecision:
        """
        Evaluate an IntentProposal. Returns a PolicyDecision.

        The evaluation is fully deterministic: same proposal + same loaded
        artifacts = same decision. No randomness, no LLM calls.
        """
        tool = proposal.tool
        taint = proposal.taint
        trust_level = proposal.trust_level
        args = proposal.args
        proposal_id = proposal.proposal_id

        steps: list[ReasonStep] = []

        # ------------------------------------------------------------------
        # Check 1: Ontology — does this tool exist in this world?
        # ------------------------------------------------------------------
        if tool not in self._actions:
            steps.append(ReasonStep(
                check="ontology",
                result="fail",
                detail=f"Tool '{tool}' does not exist in this world (not in World Manifest)",
            ))
            return self._decision(Verdict.DENY, proposal_id, tool, taint, trust_level, steps)

        action_meta = self._actions[tool]
        side_effects: list[str] = action_meta.get("side_effects", [])
        steps.append(ReasonStep(
            check="ontology",
            result="pass",
            detail=f"Tool '{tool}' exists in World Manifest",
        ))

        # ------------------------------------------------------------------
        # Check 2: Capability — does trust level permit this action category?
        # ------------------------------------------------------------------
        permitted_caps: list[str] = self._cap_matrix.get(trust_level, [])
        missing_caps = [se for se in side_effects if se not in permitted_caps]
        if missing_caps:
            steps.append(ReasonStep(
                check="capability",
                result="fail",
                detail=(
                    f"Trust level '{trust_level}' does not permit "
                    f"{missing_caps} (capability matrix)"
                ),
            ))
            return self._decision(Verdict.DENY, proposal_id, tool, taint, trust_level, steps)

        steps.append(ReasonStep(
            check="capability",
            result="pass",
            detail=f"Trust level '{trust_level}' permits {side_effects}",
        ))

        # ------------------------------------------------------------------
        # Check 3: Taint — is tainted data trying to reach a restricted target?
        # ------------------------------------------------------------------
        if taint:
            containment = self._taint_sm.get("containment_rules", {})
            taint_rules_for_level = containment.get(trust_level, {})
            blocked_targets = [
                se for se in side_effects
                if taint_rules_for_level.get(se) == "BLOCK"
            ]
            if blocked_targets:
                steps.append(ReasonStep(
                    check="taint",
                    result="fail",
                    detail=(
                        f"Tainted intent cannot reach {blocked_targets} "
                        f"(Taint Containment Law — no sanitization gate defined)"
                    ),
                ))
                return self._decision(Verdict.DENY, proposal_id, tool, taint, trust_level, steps)

            steps.append(ReasonStep(
                check="taint",
                result="pass",
                detail=f"Taint present but no hard containment violation for {side_effects}",
            ))
        else:
            steps.append(ReasonStep(
                check="taint",
                result="pass",
                detail="No taint on this intent",
            ))

        # ------------------------------------------------------------------
        # Check 4: Escalation — does any condition trigger require_approval or deny?
        # ------------------------------------------------------------------
        for cond in self._escalations:
            if self._matches_escalation(cond["trigger"], tool, taint, trust_level):
                decision_str = cond["decision"]
                steps.append(ReasonStep(
                    check="escalation",
                    result="escalate",
                    detail=f"Escalation condition '{cond['id']}' matched → {decision_str}",
                ))
                verdict = (
                    Verdict.REQUIRE_APPROVAL if decision_str == "require_approval"
                    else Verdict.DENY if decision_str == "deny"
                    else Verdict.SIMULATE
                )
                return self._decision(verdict, proposal_id, tool, taint, trust_level, steps)

        steps.append(ReasonStep(
            check="escalation",
            result="pass",
            detail="No escalation conditions matched",
        ))

        # ------------------------------------------------------------------
        # Check 5: Budget — are session limits exhausted?
        # ------------------------------------------------------------------
        budget_denial = self._budget.check(tool, side_effects)
        if budget_denial:
            steps.append(ReasonStep(
                check="budget",
                result="fail",
                detail=budget_denial,
            ))
            return self._decision(Verdict.DENY, proposal_id, tool, taint, trust_level, steps)

        steps.append(ReasonStep(
            check="budget",
            result="pass",
            detail="Within session budget limits",
        ))

        # ------------------------------------------------------------------
        # All checks passed — allow
        # ------------------------------------------------------------------
        self._budget.record(tool, side_effects)
        return self._decision(Verdict.ALLOW, proposal_id, tool, taint, trust_level, steps)

    def _matches_escalation(
        self, trigger: dict, tool: str, taint: bool, trust_level: str
    ) -> bool:
        """Return True if all specified trigger conditions are met."""
        if "action_name" in trigger and trigger["action_name"] != tool:
            return False
        if "taint" in trigger and trigger["taint"] != taint:
            return False
        if "trust_level" in trigger and trigger["trust_level"] != trust_level:
            return False
        if "reversible" in trigger:
            action_meta = self._actions.get(tool, {})
            if action_meta.get("reversible") != trigger["reversible"]:
                return False
        return True

    @staticmethod
    def _decision(
        verdict: str,
        proposal_id: str,
        tool: str,
        taint: bool,
        trust_level: str,
        steps: list[ReasonStep],
    ) -> PolicyDecision:
        return PolicyDecision(
            verdict=verdict,
            proposal_id=proposal_id,
            tool=tool,
            taint=taint,
            trust_level=trust_level,
            reason_chain=tuple(steps),
        )
