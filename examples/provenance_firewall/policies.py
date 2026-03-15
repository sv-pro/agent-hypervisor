"""
policies.py — Provenance-aware policy engine (the firewall).

The firewall sits between the simulated agent and actual tool execution.
It evaluates each ToolCall by inspecting the provenance chain of its
arguments and comparing them against the task manifest's declared grants.

Key rules:

  RULE-01  external_document cannot directly authorize outbound side-effects.
           A recipient extracted from a document carries tainted provenance.
           Even if the address looks harmless, the authorization source is
           untrusted — the document content is attacker-controlled.

  RULE-02  send_email.to must trace back to a declared recipient_source.
           If no ancestor in the provenance chain carries the recipient_source
           role AND comes from a user_declared input, the send is denied.

  RULE-03  Provenance is sticky through derivation.
           A derived value inherits the least-trusted provenance class among
           its parents. Wrapping an external value does not launder it.

  RULE-04  If the task manifest does not grant the tool at all, deny.

  RULE-05  If require_confirmation is set for a tool and all other checks
           pass, return ask instead of allow so a human can preview the call.

These rules are evaluated structurally — not as string matching — so they
catch any injection pattern regardless of the specific text used.
"""

from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any

from models import Decision, ProvenanceClass, Role, ToolCall, ValueRef, Verdict


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

    def __init__(self, task: dict, protection_enabled: bool = True) -> None:
        self._task = task
        self._protection_enabled = protection_enabled
        # Build declared-input lookup: source_label -> set of roles
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
