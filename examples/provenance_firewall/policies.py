"""
policies.py — Provenance-aware policy engine (the firewall).

The firewall sits between the simulated agent and actual tool execution.
It evaluates each ToolCall by inspecting the provenance chain of its
arguments and comparing them against the task manifest's declared grants.

Core rules (also expressed declaratively in policies/default_policy.yaml):

  RULE-01  external_document cannot directly authorize outbound side-effects.
  RULE-02  send_email.to must trace back to a declared recipient_source.
  RULE-03  Provenance is sticky through derivation.
  RULE-04  If the task manifest does not grant the tool at all, deny.
  RULE-05  If require_confirmation is set, return ask.
  RULE-D1  Mixed-provenance recipient list (clean + tainted) → deny.
  RULE-E1  http_post url derived from external_document → deny.

Declarative rules in policies/default_policy.yaml are evaluated first.
Existing Python checks remain as a fallback.  Decision.matched_rule records
which rule determined the verdict.
"""

from __future__ import annotations

import warnings
import yaml
from pathlib import Path
from typing import Any

from models import Decision, ProvenanceClass, Role, ToolCall, ValueRef, Verdict


# Default location for the declarative policy file.
_DEFAULT_POLICY_PATH = Path(__file__).parent.parent.parent / "policies" / "default_policy.yaml"

# Verdict strictness order for "strictest wins" resolution.
_VERDICT_RANK = {Verdict.deny: 0, Verdict.ask: 1, Verdict.allow: 2}


class PolicyLoader:
    """Load and cache the declarative YAML rule set."""

    def __init__(self, path: str | Path | None = None) -> None:
        p = Path(path) if path else _DEFAULT_POLICY_PATH
        try:
            data = yaml.safe_load(p.read_text())
            self._rules: list[dict] = data.get("rules", []) if data else []
        except FileNotFoundError:
            warnings.warn(f"Policy file not found at {p}; declarative rules disabled.")
            self._rules = []

    def rules(self) -> list[dict]:
        return self._rules


# Trust ordering — lower index = less trusted. Used in RULE-03.
_TRUST_ORDER = [
    ProvenanceClass.external_document,
    ProvenanceClass.derived,
    ProvenanceClass.user_declared,
    ProvenanceClass.system,
]


def _least_trusted(classes: list[ProvenanceClass]) -> ProvenanceClass:
    """Return the least-trusted provenance class among a list."""
    if not classes:
        return ProvenanceClass.external_document
    return min(classes, key=lambda c: _TRUST_ORDER.index(c))


def resolve_chain(ref: ValueRef, registry: dict[str, ValueRef]) -> list[ValueRef]:
    """
    Walk the derivation graph and return all ancestors of ref (including ref).

    Cycles are silently broken (shouldn't occur in a well-formed DAG).
    """
    seen: set[str] = set()
    result: list[ValueRef] = []

    def walk(r: ValueRef) -> None:
        if r.id in seen:
            return
        seen.add(r.id)
        result.append(r)
        for pid in r.parents:
            parent = registry.get(pid)
            if parent:
                walk(parent)

    walk(ref)
    return result


def _provenance_summary(ref: ValueRef, registry: dict[str, ValueRef]) -> str:
    chain = resolve_chain(ref, registry)
    labels = [f"{v.provenance.value}:{v.source_label or v.id}" for v in chain]
    return " <- ".join(labels)


class ProvenanceFirewall:
    """
    The firewall gateway.

    Usage:
        fw = ProvenanceFirewall.from_manifest("manifests/task_allow_send.yaml")
        decision = fw.check(tool_call, registry)

    Pass protection_enabled=False to run in unprotected / baseline mode.
    """

    def __init__(
        self,
        task: dict,
        protection_enabled: bool = True,
        policy_loader: PolicyLoader | None = None,
    ) -> None:
        self._task = task
        self._protection_enabled = protection_enabled
        self._policy = policy_loader or PolicyLoader()
        # Build declared-input lookup: source_label -> list of roles
        self._declared: dict[str, list[Role]] = {}
        for inp in task.get("declared_inputs", []):
            label = inp.get("id", "")
            roles = [Role(r) for r in inp.get("roles", [])]
            self._declared[label] = roles

    @classmethod
    def from_manifest(cls, path: str | Path, protection_enabled: bool = True) -> "ProvenanceFirewall":
        data = yaml.safe_load(Path(path).read_text())
        return cls(task=data, protection_enabled=protection_enabled)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def check(self, call: ToolCall, registry: dict[str, ValueRef]) -> Decision:
        """Evaluate a ToolCall and return a Decision."""
        if not self._protection_enabled:
            return self._allow(call, "Protection disabled — unprotected baseline mode")

        grant = self._find_grant(call.tool)

        # Try declarative policy rules first.
        dec = self._evaluate_rules(call, registry, grant)
        if dec is not None:
            return dec

        # --- Python fallback (covers any case not yet expressed in YAML) ---

        # RULE-04: tool not granted at all
        if grant is None or not grant.get("allowed", False):
            return self._deny(
                call, registry,
                reason=f"Tool '{call.tool}' is not granted in this task manifest",
                rules=["RULE-04"],
            )

        if call.tool == "send_email":
            return self._check_send_email(call, registry, grant)

        if call.tool in ("write_file", "http_post"):
            return self._check_side_effect(call, registry, grant)

        # read_only tools: always allow if granted
        return self._allow(call, f"Tool '{call.tool}' is read-only and granted")

    # ------------------------------------------------------------------
    # Declarative rule evaluation
    # ------------------------------------------------------------------

    def _evaluate_rules(
        self, call: ToolCall, registry: dict[str, ValueRef], grant: dict | None
    ) -> Decision | None:
        """
        Iterate declarative YAML rules in order.  Return the first Decision
        whose condition matches, or None to fall through to Python logic.
        """
        best: Decision | None = None

        for rule in self._policy.rules():
            applies_to = rule.get("applies_to", ["*"])
            if "*" not in applies_to and call.tool not in applies_to:
                continue

            cond = rule.get("condition", {})
            matched, ctx = self._eval_condition(cond, call, registry, grant)
            if not matched:
                continue

            verdict_str = rule.get("verdict", "deny")
            verdict = Verdict(verdict_str)
            template = rule.get("reason_template", "")
            reason = template.strip().format_map({
                "tool": call.tool,
                "arg": ctx.get("arg", ""),
                "source": ctx.get("source", ""),
                "least_trusted": ctx.get("least_trusted", ""),
            })
            rule_id = rule.get("id", "")

            if verdict == Verdict.deny:
                dec = Decision(
                    verdict=Verdict.deny,
                    tool=call.tool,
                    call_id=call.call_id,
                    reason=reason,
                    violated_rules=[rule_id],
                    arg_provenance=self._arg_provenance(call, registry),
                    matched_rule=rule_id,
                )
                return dec  # deny short-circuits immediately
            else:
                candidate = Decision(
                    verdict=verdict,
                    tool=call.tool,
                    call_id=call.call_id,
                    reason=reason,
                    arg_provenance=self._arg_provenance(call, registry),
                    matched_rule=rule_id,
                )
                if best is None or _VERDICT_RANK[verdict] < _VERDICT_RANK[best.verdict]:
                    best = candidate

        return best

    def _eval_condition(
        self, cond: dict, call: ToolCall, registry: dict[str, ValueRef], grant: dict | None
    ) -> tuple[bool, dict]:
        """
        Evaluate one condition block.  Returns (matched, context_dict).
        context_dict provides interpolation values for reason_template.
        """
        ctype = cond.get("type")
        ctx: dict[str, str] = {}

        if ctype == "tool_not_granted":
            return (grant is None or not grant.get("allowed", False)), ctx

        if ctype == "recipient_provenance":
            to_ref = call.args.get("to")
            if to_ref is None:
                return False, ctx
            chain = resolve_chain(to_ref, registry)
            chain_prov = [v.provenance for v in chain]
            required = ProvenanceClass(cond["has_provenance"])
            unless_role_str = cond.get("unless_has_declared_role")
            unless_role = Role(unless_role_str) if unless_role_str else None

            has_required = required in chain_prov
            if not has_required:
                return False, ctx

            if unless_role and self._find_declared_recipient_source(chain):
                return False, ctx

            ctx["source"] = to_ref.source_label
            return True, ctx

        if ctype == "mixed_provenance":
            arg_name = cond.get("recipient_arg", "to")
            tainted_class = ProvenanceClass(cond.get("tainted_class", "external_document"))
            ref = call.args.get(arg_name)
            if ref is None:
                return False, ctx
            chain = resolve_chain(ref, registry)
            provs = {v.provenance for v in chain}
            has_tainted = tainted_class in provs
            has_clean = ProvenanceClass.user_declared in provs or ProvenanceClass.system in provs
            return (has_tainted and has_clean), ctx

        if ctype == "no_declared_source":
            required_role = Role(cond.get("required_role", "recipient_source"))
            to_ref = call.args.get("to")
            if to_ref is None:
                return False, ctx
            chain = resolve_chain(to_ref, registry)
            chain_prov = [v.provenance for v in chain]
            found = self._find_declared_recipient_source(chain)
            if found:
                return False, ctx
            ctx["least_trusted"] = _least_trusted(chain_prov).value
            return True, ctx

        if ctype == "any_arg_has_provenance":
            target_prov = ProvenanceClass(cond["provenance_class"])
            arg_name_filter = cond.get("arg_name")
            args_to_check = (
                {arg_name_filter: call.args[arg_name_filter]}
                if arg_name_filter and arg_name_filter in call.args
                else call.args
            )
            for arg_name, ref in args_to_check.items():
                chain = resolve_chain(ref, registry)
                if any(v.provenance == target_prov for v in chain):
                    ctx["arg"] = arg_name
                    ctx["source"] = ref.source_label
                    return True, ctx
            return False, ctx

        if ctype == "require_confirmation":
            return bool(grant and grant.get("require_confirmation", False)), ctx

        return False, ctx

    # ------------------------------------------------------------------
    # Per-tool checks
    # ------------------------------------------------------------------

    def _check_send_email(
        self, call: ToolCall, registry: dict[str, ValueRef], grant: dict
    ) -> Decision:
        to_ref = call.args.get("to")
        if to_ref is None:
            return self._deny(call, registry, reason="Missing 'to' argument", rules=["RULE-02"])

        chain = resolve_chain(to_ref, registry)
        chain_prov = [v.provenance for v in chain]
        least_trusted_prov = _least_trusted(chain_prov)

        # RULE-01: external_document anywhere in the chain is a hard block
        # unless a declared recipient_source also appears in the chain.
        has_external_doc = ProvenanceClass.external_document in chain_prov

        # RULE-02: check for a declared recipient_source ancestor
        declared_recipient_source = self._find_declared_recipient_source(chain)

        if has_external_doc and not declared_recipient_source:
            return self._deny(
                call, registry,
                reason=(
                    f"Recipient provenance traces to external_document "
                    f"(source: {to_ref.source_label!r}) — "
                    "external documents cannot authorize outbound email"
                ),
                rules=["RULE-01", "RULE-02"],
            )

        if not declared_recipient_source:
            return self._deny(
                call, registry,
                reason=(
                    "Recipient has no declared recipient_source in provenance chain "
                    f"(least trusted: {least_trusted_prov.value})"
                ),
                rules=["RULE-02"],
            )

        # RULE-05: require_confirmation → ask
        if grant.get("require_confirmation", False):
            to_val = to_ref.value
            return Decision(
                verdict=Verdict.ask,
                tool=call.tool,
                call_id=call.call_id,
                reason=(
                    f"Recipient '{to_val}' traces to declared source "
                    f"'{declared_recipient_source}' — confirmation required before sending"
                ),
                arg_provenance=self._arg_provenance(call, registry),
            )

        return self._allow(
            call,
            f"Recipient traces to declared recipient_source '{declared_recipient_source}'",
            registry=registry,
        )

    def _check_side_effect(
        self, call: ToolCall, registry: dict[str, ValueRef], grant: dict
    ) -> Decision:
        """Generic side-effect check for write_file / http_post."""
        # Any arg derived from external_document → deny
        for arg_name, ref in call.args.items():
            chain = resolve_chain(ref, registry)
            if any(v.provenance == ProvenanceClass.external_document for v in chain):
                return self._deny(
                    call, registry,
                    reason=(
                        f"Argument '{arg_name}' traces to external_document — "
                        "external content cannot drive side-effect tools"
                    ),
                    rules=["RULE-01"],
                )
        if grant.get("require_confirmation", False):
            return Decision(
                verdict=Verdict.ask,
                tool=call.tool,
                call_id=call.call_id,
                reason=f"Tool '{call.tool}' is a side-effect action — confirmation required",
                arg_provenance=self._arg_provenance(call, registry),
            )
        return self._allow(call, f"Tool '{call.tool}' granted with clean provenance", registry=registry)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_grant(self, tool: str) -> dict | None:
        for g in self._task.get("action_grants", []):
            if g.get("tool") == tool:
                return g
        return None

    def _find_declared_recipient_source(self, chain: list[ValueRef]) -> str | None:
        """
        Return the source_label of the first ancestor that:
          - has provenance user_declared
          - and is declared in the manifest with role recipient_source
        """
        for ref in chain:
            if ref.provenance == ProvenanceClass.user_declared:
                declared_roles = self._declared.get(ref.source_label, [])
                if Role.recipient_source in declared_roles:
                    return ref.source_label
            # Also check roles directly on the ValueRef
            if Role.recipient_source in ref.roles and ref.provenance == ProvenanceClass.user_declared:
                return ref.source_label
        return None

    def _arg_provenance(self, call: ToolCall, registry: dict[str, ValueRef]) -> dict[str, str]:
        return {k: _provenance_summary(v, registry) for k, v in call.args.items()}

    def _allow(
        self, call: ToolCall, reason: str, registry: dict[str, ValueRef] | None = None
    ) -> Decision:
        return Decision(
            verdict=Verdict.allow,
            tool=call.tool,
            call_id=call.call_id,
            reason=reason,
            arg_provenance=self._arg_provenance(call, registry) if registry else {},
        )

    def _deny(
        self, call: ToolCall, registry: dict[str, ValueRef], reason: str, rules: list[str]
    ) -> Decision:
        return Decision(
            verdict=Verdict.deny,
            tool=call.tool,
            call_id=call.call_id,
            reason=reason,
            violated_rules=rules,
            arg_provenance=self._arg_provenance(call, registry),
        )
