"""
generate_manifest.py — Scaffold a workspace_v2.yaml manifest from a live AgentDojo suite.

Usage:
    python -m ah_defense.generate_manifest --suite workspace --output manifests/workspace_v2.yaml

    # Dry-run: print to stdout
    python -m ah_defense.generate_manifest --suite workspace

The generator introspects the suite's tool list (FunctionsRuntime) and produces a
draft YAML manifest with:
  - Tool → action mappings (predicates)
  - Parameter schemas from pydantic model_fields
  - Action class heuristics based on tool name patterns
  - Conservative defaults (fail-closed)

The output is a DRAFT. Review and adjust before use, especially:
  - Action classes for ambiguous tools (e.g. create_calendar_event has two paths)
  - taint_passthrough for tools whose outputs cannot carry attacker content
  - requires_approval for irreversible/external actions

Design principle (from docs):
  "Where Cursor generates modules → Agent Hypervisor generates World Manifests.
   Given a description of a business process, an LLM generates permitted actions
   and schemas. A human reviews and commits."
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from typing import Any

import yaml


# ── Type-annotation normaliser ────────────────────────────────────────────────

def _normalise_type(ann: Any) -> str:
    """Map Python type annotations to manifest schema types."""
    ann_str = str(ann)
    if "list" in ann_str.lower() or "List" in ann_str:
        return "list"
    if ann_str in ("str", "<class 'str'>", "typing.Optional[str]", "str | None"):
        return "str"
    if ann_str in ("int", "<class 'int'>"):
        return "int"
    if ann_str in ("bool", "<class 'bool'>"):
        return "bool"
    if "dict" in ann_str.lower():
        return "dict"
    return "str"  # conservative default


# ── Action class heuristics ───────────────────────────────────────────────────

# Maps tool name patterns to (action_class, risk_class, external_boundary, taint_passthrough)
_HEURISTICS: list[tuple[str, tuple[str, str, bool, bool]]] = [
    # Reads that return system-generated, non-content values
    ("get_current_day",          ("read_only", "low",      False, False)),
    ("list_files",               ("read_only", "low",      False, False)),
    ("search_files_by_filename", ("read_only", "low",      False, False)),
    # Content reads — can contain attacker-controlled text
    ("get_unread_emails",        ("read_only", "low",      False, True)),
    ("get_sent_emails",          ("read_only", "low",      False, True)),
    ("get_received_emails",      ("read_only", "low",      False, True)),
    ("get_draft_emails",         ("read_only", "low",      False, True)),
    ("search_emails",            ("read_only", "low",      False, True)),
    ("search_contacts_by_name",  ("read_only", "low",      False, True)),
    ("search_contacts_by_email", ("read_only", "low",      False, True)),
    ("search_calendar_events",   ("read_only", "low",      False, True)),
    ("get_day_calendar_events",  ("read_only", "low",      False, True)),
    ("get_file_by_id",           ("read_only", "low",      False, True)),
    ("search_files",             ("read_only", "low",      False, True)),
    # Reversible internal writes
    ("create_file",              ("reversible_internal",   "low",    False, True)),
    ("append_to_file",           ("reversible_internal",   "low",    False, True)),
    ("reschedule_calendar_event",("reversible_internal",   "medium", False, True)),
    ("cancel_calendar_event",    ("reversible_internal",   "medium", False, True)),
    # Irreversible internal
    ("delete_file",              ("irreversible_internal", "high",   False, False)),
    ("delete_email",             ("irreversible_internal", "high",   False, False)),
    # External boundary
    ("send_email",               ("external_boundary",     "critical", True, True)),
    ("share_file",               ("external_boundary",     "critical", True, True)),
    ("add_calendar_event_participants", ("external_boundary", "high", True, True)),
    # create_calendar_event is split by predicate — handled specially below
]

_HEURISTIC_MAP = dict(_HEURISTICS)


def _classify_tool(tool_name: str) -> tuple[str, str, bool, bool]:
    """Return (action_class, risk_class, external_boundary, taint_passthrough)."""
    if tool_name in _HEURISTIC_MAP:
        return _HEURISTIC_MAP[tool_name]
    # Default: conservative unknown write
    return ("reversible_internal", "medium", False, True)


# ── Parameter schema builder ──────────────────────────────────────────────────

def _build_schema(tool: Any) -> dict[str, Any]:
    """Extract required parameters from a Function's pydantic schema."""
    schema: dict[str, Any] = {}
    params_cls = tool.parameters
    if not hasattr(params_cls, "model_fields"):
        return schema
    for fname, finfo in params_cls.model_fields.items():
        required = finfo.is_required()
        ann = getattr(finfo, "annotation", None)
        type_str = _normalise_type(ann)
        schema[fname] = {
            "type": type_str,
            "required": required,
        }
    return schema


# ── YAML renderer ─────────────────────────────────────────────────────────────

def _render_action(name: str, action_class: str, risk_class: str,
                   external_boundary: bool, taint_passthrough: bool,
                   description: str) -> str:
    caps_map = {
        "read_only": "[read_only]",
        "reversible_internal": "[internal_write]",
        "irreversible_internal": "[approve_irreversible]",
        "external_boundary": "[external_boundary]",
    }
    caps = caps_map.get(action_class, "[read_only]")
    irreversible = action_class == "irreversible_internal"
    requires_approval = False  # taint containment handles blocking; clean = user-requested

    lines = [
        f"  {name}:",
        f"    action_class: {action_class}",
        f"    risk_class: {risk_class}",
        f"    required_capabilities: {caps}",
        f"    requires_approval: {str(requires_approval).lower()}",
        f"    irreversible: {str(irreversible).lower()}",
        f"    external_boundary: {str(external_boundary).lower()}",
        f"    taint_passthrough: {str(taint_passthrough).lower()}",
        f"    description: {description!r}",
    ]
    return "\n".join(lines)


def _render_schema_entry(tool_name: str, schema: dict[str, Any]) -> str:
    if not schema:
        return f"  {tool_name}: {{}}"
    lines = [f"  {tool_name}:"]
    for param, constraints in schema.items():
        lines.append(f"    {param}:")
        lines.append(f"      type: {constraints['type']}")
        lines.append(f"      required: {str(constraints['required']).lower()}")
    return "\n".join(lines)


# ── Main generator ────────────────────────────────────────────────────────────

def generate_manifest(suite_name: str, benchmark_version: str = "v1.2.2") -> str:
    """Generate a draft workspace_v2.yaml from a live AgentDojo suite.

    Returns the YAML string.
    """
    try:
        from agentdojo.task_suite.load_suites import get_suite
    except ImportError as exc:
        raise ImportError("agentdojo must be installed: pip install agentdojo") from exc

    suite = get_suite(benchmark_version, suite_name)
    tools = suite.tools

    # Build action list — handle create_calendar_event specially (split predicate)
    actions: list[tuple[str, str, str, bool, bool, str]] = []  # (name, class, risk, ext_boundary, taint_passthrough, desc)
    schemas: dict[str, dict[str, Any]] = {}
    predicates: dict[str, Any] = {}

    for tool in tools:
        tname = tool.name
        desc = (tool.description or "").split("\n")[0].strip()
        schema = _build_schema(tool)

        if tname == "create_calendar_event":
            # Split into two actions by participants arg
            actions.append((
                "create_calendar_event_personal",
                "reversible_internal", "low", False, True,
                "Create calendar event without external participants",
            ))
            actions.append((
                "create_calendar_event_with_participants",
                "external_boundary", "high", True, True,
                "Create calendar event with external participants (sends invites)",
            ))
            schemas["create_calendar_event_personal"] = {
                k: v for k, v in schema.items()
                if k in ("title", "start_time", "end_time", "description", "location")
            }
            schemas["create_calendar_event_with_participants"] = schema
            predicates["create_calendar_event"] = [
                {"action": "create_calendar_event_with_participants",
                 "match": {"arg_present": "participants"}},
                {"action": "create_calendar_event_personal",
                 "match": {"arg_absent": "participants"}},
            ]
        else:
            action_class, risk_class, external_boundary, taint_passthrough = _classify_tool(tname)
            actions.append((tname, action_class, risk_class, external_boundary, taint_passthrough, desc))
            schemas[tname] = schema
            predicates[tname] = [{"action": tname, "match": {}}]

    # ── Render ────────────────────────────────────────────────────────────────
    header = textwrap.dedent(f"""\
        # {suite_name}_v2.yaml — AUTO-GENERATED by generate_manifest.py
        # REVIEW BEFORE USE: adjust action_class, taint_passthrough, requires_approval.
        #
        # Generated from: AgentDojo suite '{suite_name}' ({benchmark_version})
        # Tools found: {len(tools)}
        #
        # Key decisions to review:
        #   - taint_passthrough=false tools: only system-generated, cannot carry attacker content
        #   - external_boundary=true tools: blocked by taint containment when context is tainted
        #   - requires_approval=false: rely on step-5 taint containment; clean context = user-requested
        #
        # Architecture: ontology-first, provenance-aware, deterministic enforcement.
        # Default behaviour: DENY everything not explicitly defined and permitted.

        version: "2.0"
        suite: {suite_name}

        defaults:
          unknown_action: deny
          unknown_tool: deny
          missing_capability: deny
          schema_mismatch: deny
          tainted_external: deny
          unknown_transformation_taint: preserve

        trust_channels:
          user:
            trust_level: trusted
            taints_by_default: false
            description: Direct human input via the user interface
          email:
            trust_level: untrusted
            taints_by_default: true
            description: Email content from external senders
          web:
            trust_level: untrusted
            taints_by_default: true
            description: Web page content fetched from the internet
          file:
            trust_level: semi_trusted
            taints_by_default: true
            description: File content from the local filesystem
          mcp:
            trust_level: semi_trusted
            taints_by_default: true
            description: Model Context Protocol tool outputs
          agent:
            trust_level: untrusted
            taints_by_default: true
            description: Input from another agent

        trust_levels:
          - untrusted
          - semi_trusted
          - trusted

        capabilities:
          untrusted:
            - read_only
          semi_trusted:
            - read_only
            - internal_write
          trusted:
            - read_only
            - internal_write
            - external_boundary
            - approve_irreversible

    """)

    # Schemas
    schema_lines = ["schemas:"]
    for tname in [a[0] for a in actions]:
        schema_lines.append(_render_schema_entry(tname, schemas.get(tname, {})))
    schemas_block = "\n".join(schema_lines)

    # Actions
    action_lines = ["actions:"]
    action_classes = {
        "read_only": "Read-only",
        "reversible_internal": "Reversible internal",
        "irreversible_internal": "Irreversible internal",
        "external_boundary": "External boundary",
    }
    current_class = None
    for name, action_class, risk_class, ext_boundary, taint_pt, desc in sorted(
        actions, key=lambda x: list(action_classes.keys()).index(x[1])
    ):
        if action_class != current_class:
            current_class = action_class
            action_lines.append(f"\n  # ── {action_classes[action_class]} ──")
        action_lines.append(_render_action(name, action_class, risk_class, ext_boundary, taint_pt, desc))
        action_lines.append("")
    actions_block = "\n".join(action_lines)

    # Predicates
    pred_lines = ["predicates:"]
    for tname, pred_list in predicates.items():
        pred_lines.append(f"  {tname}:")
        for pred in pred_list:
            match = pred["match"]
            if not match:
                pred_lines.append(f"    - action: {pred['action']}")
                pred_lines.append(f"      match: {{}}")
            else:
                pred_lines.append(f"    - action: {pred['action']}")
                for k, v in match.items():
                    pred_lines.append(f"      match:")
                    pred_lines.append(f"        {k}: {v}")
                    break
    predicates_block = "\n".join(pred_lines)

    footer = textwrap.dedent("""\

        taint_rules:
          - source_taint: tainted
            operation: summarize
            result: preserve
          - source_taint: tainted
            operation: quote
            result: preserve
          - source_taint: tainted
            operation: extract
            result: preserve
          - source_taint: tainted
            operation: derive
            result: preserve

        escalation_rules:
          # Retained for documentation; only fires if requires_approval=true above.
          send_email:
            condition: tainted
            reason: "send_email with tainted context denied — injection containment"
            rule_id: "ESC-WS-001"
          share_file:
            condition: tainted
            reason: "share_file with tainted context denied — injection containment"
            rule_id: "ESC-WS-002"

        provenance_policy:
          track_all_channels: true
          inter_agent_default_trust: untrusted
          propagate_through_summarize: true
          propagate_through_quote: true
          propagate_through_extract: true

        persistence_policy:
          episode_scoped: true
          persist_decisions: false
          persist_taint_state: false
    """)

    return "\n".join([header, schemas_block, "", actions_block, "", predicates_block, footer])


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate AH manifest from AgentDojo suite")
    parser.add_argument("--suite", default="workspace",
                        choices=["workspace", "travel", "banking", "slack"],
                        help="AgentDojo suite name")
    parser.add_argument("--benchmark-version", default="v1.2.2")
    parser.add_argument("--output", "-o", default=None,
                        help="Output file path. Default: print to stdout.")
    args = parser.parse_args()

    manifest_yaml = generate_manifest(args.suite, args.benchmark_version)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(manifest_yaml)
        print(f"Manifest written to {out_path}", file=sys.stderr)
    else:
        print(manifest_yaml)
