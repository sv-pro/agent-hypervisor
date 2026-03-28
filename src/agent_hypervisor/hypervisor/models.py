"""
models.py — Core data model for the provenance-aware tool execution firewall.

Three key types:

  ValueRef   — a value with full provenance: where it came from, what roles it
               plays, and which other values it was derived from.

  ToolCall   — a proposed tool invocation with structured argument references
               (each argument is a ValueRef, not a raw string).

  Decision   — the firewall verdict for one ToolCall: allow / deny / ask,
               plus a reason and the violated rules if denied.

Provenance classes (ordered by trust, least to most):
  external_document  — content from files, network, or other agent outputs
  derived            — computed/extracted from one or more parents
  user_declared      — explicitly declared by the operator in the task manifest
  system             — hardcoded by the system itself (no user influence)

Roles describe the intended use of a value inside the task:
  recipient_source      — a value that names email recipients
  extracted_recipients  — recipients extracted from a document
  report_source         — a document being summarised
  data_source           — raw data being processed
  generated_report      — the agent's own output
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ProvenanceClass(str, Enum):
    external_document = "external_document"
    derived           = "derived"
    user_declared     = "user_declared"
    system            = "system"


class Role(str, Enum):
    recipient_source     = "recipient_source"
    extracted_recipients = "extracted_recipients"
    report_source        = "report_source"
    data_source          = "data_source"
    generated_report     = "generated_report"


class Verdict(str, Enum):
    allow  = "allow"
    deny   = "deny"
    ask    = "ask"
    replan = "replan"   # budget exceeded; a cheaper execution path may exist


@dataclass
class ValueRef:
    """
    A value with attached provenance metadata.

    Every value the agent works with — file contents, extracted strings,
    computed summaries, contact addresses — must be wrapped in a ValueRef
    so the firewall can trace where it came from before it is used.
    """
    id: str
    value: Any                              # the actual value (str, list, etc.)
    provenance: ProvenanceClass
    roles: list[Role] = field(default_factory=list)
    parents: list[str] = field(default_factory=list)   # ValueRef ids
    source_label: str = ""                  # human-readable source description

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "value": self.value,
            "provenance": self.provenance.value,
            "roles": [r.value for r in self.roles],
            "parents": self.parents,
            "source_label": self.source_label,
        }


@dataclass
class ToolCall:
    """
    A proposed tool invocation.

    args maps argument names to ValueRefs rather than raw values,
    so the firewall can inspect provenance per-argument.
    """
    tool: str
    args: dict[str, ValueRef]
    call_id: str = ""

    def to_dict(self) -> dict:
        return {
            "call_id": self.call_id,
            "tool": self.tool,
            "args": {k: v.to_dict() for k, v in self.args.items()},
        }


@dataclass
class Decision:
    """
    The firewall verdict for one ToolCall.

    verdict:        allow | deny | ask
    reason:         single human-readable explanation of the decision
    violated_rules: list of rule ids that caused a deny (empty if allowed/ask)
    arg_provenance: per-argument provenance summary for trace logs
    """
    verdict: Verdict
    tool: str
    call_id: str
    reason: str
    violated_rules: list[str] = field(default_factory=list)
    arg_provenance: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict.value,
            "tool": self.tool,
            "call_id": self.call_id,
            "reason": self.reason,
            "violated_rules": self.violated_rules,
            "arg_provenance": self.arg_provenance,
        }
