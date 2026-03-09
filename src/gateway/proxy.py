"""
gateway/proxy.py — MCP Proxy Gateway (Layer 5 boundary).

Every tool call made by the agent passes through here. The gateway is the
only point in the system that invokes real tools. It enforces:

  1. Virtualization   : Tools not in the World Manifest do not exist.
                        The agent cannot discover or invoke them.
  2. Schema validation: Tool arguments are validated against the compiled
                        action schema before any invocation.
  3. Capability check : The trust level of the triggering event is checked
                        against the capability matrix before invocation.
  4. Taint egress     : Tainted data cannot leave the system through any
                        external_write tool.
  5. Provenance tag   : Every tool output is tagged as a SemanticEvent with
                        SEMI_TRUSTED trust level and the tool name as source.

The agent never calls tools directly. It calls the gateway, which decides
whether the call can proceed and returns a typed result.

Every call produces a GatewayTrace record — the full audit trail for Layer 5.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Gateway trace record
# ---------------------------------------------------------------------------

@dataclass
class GatewayTrace:
    """
    Full audit record for one tool call attempt through the gateway.

    Written for every call regardless of outcome (even denied calls are logged).
    """
    trace_id: str
    proposal_id: str
    tool: str
    args: dict[str, Any]
    trust_level: str
    taint: bool
    timestamp: str
    outcome: str           # "executed" | "denied" | "not_in_world" | "schema_error" | "capability_denied" | "taint_blocked"
    denial_reason: str     # Empty string if executed
    output_event_id: str   # SemanticEvent ID of the tool output, if executed

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "proposal_id": self.proposal_id,
            "tool": self.tool,
            "args": self.args,
            "trust_level": self.trust_level,
            "taint": self.taint,
            "timestamp": self.timestamp,
            "outcome": self.outcome,
            "denial_reason": self.denial_reason,
            "output_event_id": self.output_event_id,
        }


# ---------------------------------------------------------------------------
# Tool registry — simulated MCP tools for the demo
# ---------------------------------------------------------------------------

class ToolRegistry:
    """
    Registry of callable demo tools (simulated MCP servers).

    In a real deployment this would wrap actual MCP server connections.
    For the demo it provides deterministic stub implementations.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Callable[..., Any]] = {}

    def register(self, name: str, fn: Callable[..., Any]) -> None:
        self._tools[name] = fn

    def call(self, name: str, args: dict[str, Any]) -> Any:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not registered in ToolRegistry")
        return self._tools[name](**args)

    def available(self) -> list[str]:
        return sorted(self._tools.keys())


def make_demo_registry() -> ToolRegistry:
    """Build a ToolRegistry with simple deterministic demo tools."""
    reg = ToolRegistry()

    def read_email(email_id: str, **_: Any) -> dict[str, Any]:
        return {
            "email_id": email_id,
            "from": "sender@example.com",
            "subject": "Weekly update",
            "body": "Here is the weekly report.",
        }

    def list_inbox(max_results: int = 10, **_: Any) -> dict[str, Any]:
        return {
            "emails": [
                {"email_id": f"msg-{i}", "subject": f"Email {i}", "from": "x@example.com"}
                for i in range(min(max_results, 3))
            ]
        }

    def draft_reply(email_id: str, body: str, **_: Any) -> dict[str, Any]:
        return {"status": "drafted", "email_id": email_id, "draft_id": str(uuid.uuid4())}

    def send_email(to: list[str], subject: str, body: str, **_: Any) -> dict[str, Any]:
        return {"status": "sent", "to": to, "subject": subject}

    def mcp_read_file(path: str, **_: Any) -> dict[str, Any]:
        return {"path": path, "content": f"<contents of {path}>"}

    def mcp_write_file(path: str, content: str, **_: Any) -> dict[str, Any]:
        return {"status": "written", "path": path, "bytes": len(content)}

    def mcp_web_fetch(url: str, **_: Any) -> dict[str, Any]:
        return {"url": url, "content": f"<page content from {url}>", "status_code": 200}

    def mcp_run_code(language: str, code: str, **_: Any) -> dict[str, Any]:
        return {"language": language, "output": f"<output of {language} code>", "exit_code": 0}

    def mcp_list_directory(path: str, **_: Any) -> dict[str, Any]:
        return {"path": path, "entries": ["file1.txt", "file2.txt"]}

    def browser_navigate(url: str, **_: Any) -> dict[str, Any]:
        return {"url": url, "title": f"Page at {url}", "status": "loaded"}

    def browser_get_page_text(**_: Any) -> dict[str, Any]:
        return {"text": "<page text content>"}

    def browser_get_structured_data(schema_id: str, **_: Any) -> dict[str, Any]:
        return {"schema_id": schema_id, "data": {"name": "Example Product", "price": 42.0}}

    def browser_fill_form(field_selector: str, value: str, **_: Any) -> dict[str, Any]:
        return {"status": "filled", "field": field_selector, "value": value}

    def browser_submit_form(form_selector: str, **_: Any) -> dict[str, Any]:
        return {"status": "submitted", "form": form_selector}

    def browser_take_screenshot(**_: Any) -> dict[str, Any]:
        return {"status": "captured", "format": "png", "size_bytes": 1024}

    for name, fn in [
        ("read_email", read_email), ("list_inbox", list_inbox),
        ("draft_reply", draft_reply), ("send_email", send_email),
        ("mcp_read_file", mcp_read_file), ("mcp_write_file", mcp_write_file),
        ("mcp_web_fetch", mcp_web_fetch), ("mcp_run_code", mcp_run_code),
        ("mcp_list_directory", mcp_list_directory),
        ("browser_navigate", browser_navigate),
        ("browser_get_page_text", browser_get_page_text),
        ("browser_get_structured_data", browser_get_structured_data),
        ("browser_fill_form", browser_fill_form),
        ("browser_submit_form", browser_submit_form),
        ("browser_take_screenshot", browser_take_screenshot),
    ]:
        reg.register(name, fn)

    return reg


# ---------------------------------------------------------------------------
# Schema validator
# ---------------------------------------------------------------------------

def _validate_args(
    tool: str,
    args: dict[str, Any],
    action_schemas: dict[str, Any],
) -> str | None:
    """
    Validate args against the compiled action schema.

    Returns a denial reason string if invalid, else None.
    Only checks 'required' fields — full JSON Schema validation is deferred (#20 follow-on).
    """
    schema_entry = action_schemas.get(tool)
    if schema_entry is None:
        return None  # No schema defined — pass through

    input_schema = schema_entry.get("input_schema")
    if not input_schema:
        return None

    required = input_schema.get("required", [])
    for field_name in required:
        if field_name not in args:
            return f"Schema validation failed: required field '{field_name}' missing for tool '{tool}'"

    return None


# ---------------------------------------------------------------------------
# MCP Gateway
# ---------------------------------------------------------------------------

class MCPGateway:
    """
    The tool execution boundary (Layer 5).

    Intercepts every tool call and enforces virtualization, schema validation,
    capability checking, taint egress control, and provenance tagging.

    Usage:
        gateway = MCPGateway.from_compiled_dir("compiled/email-safe-assistant", registry)
        result_event, trace = gateway.call(proposal)
    """

    def __init__(
        self,
        action_schemas: dict[str, Any],
        capability_matrix: dict[str, list[str]],
        taint_state_machine: dict[str, Any],
        registry: ToolRegistry,
        session_id: str | None = None,
    ) -> None:
        self._action_schemas = action_schemas          # from action_schemas.json["actions"]
        self._cap_matrix = capability_matrix           # from capability_matrix.json["by_trust_level"]
        self._taint_sm = taint_state_machine
        self._registry = registry
        self._session_id = session_id or str(uuid.uuid4())
        self._traces: list[GatewayTrace] = []

    @classmethod
    def from_compiled_dir(
        cls,
        compiled_dir: str,
        registry: ToolRegistry,
        session_id: str | None = None,
    ) -> "MCPGateway":
        import json
        from pathlib import Path
        d = Path(compiled_dir)
        action_schemas = json.loads((d / "action_schemas.json").read_text())["actions"]
        cap_matrix = json.loads((d / "capability_matrix.json").read_text())["by_trust_level"]
        taint_sm = json.loads((d / "taint_state_machine.json").read_text())
        return cls(action_schemas, cap_matrix, taint_sm, registry, session_id)

    def call(self, proposal: Any) -> tuple[Any | None, GatewayTrace]:
        """
        Attempt a tool invocation.

        Returns (output_event, trace). output_event is None if the call was denied.
        The output_event is a SemanticEvent constructed from the tool's output,
        tagged with SEMI_TRUSTED trust and the tool name as source.
        """
        tool = proposal.tool
        args = proposal.args
        taint = proposal.taint
        trust_level = proposal.trust_level
        proposal_id = proposal.proposal_id

        trace_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        def _denied(outcome: str, reason: str) -> tuple[None, GatewayTrace]:
            t = GatewayTrace(
                trace_id=trace_id,
                proposal_id=proposal_id,
                tool=tool,
                args=args,
                trust_level=trust_level,
                taint=taint,
                timestamp=timestamp,
                outcome=outcome,
                denial_reason=reason,
                output_event_id="",
            )
            self._traces.append(t)
            return None, t

        # ----------------------------------------------------------------
        # Gate 1: Virtualization — tool must exist in this world
        # ----------------------------------------------------------------
        if tool not in self._action_schemas:
            return _denied(
                "not_in_world",
                f"Tool '{tool}' does not exist in this world (not in World Manifest) — "
                f"it cannot be invoked; it is absent, not merely blocked",
            )

        action_meta = self._action_schemas[tool]
        side_effects: list[str] = action_meta.get("side_effects", [])

        # ----------------------------------------------------------------
        # Gate 2: Capability — trust level must permit all side effects
        # ----------------------------------------------------------------
        permitted: list[str] = self._cap_matrix.get(trust_level, [])
        missing = [se for se in side_effects if se not in permitted]
        if missing:
            return _denied(
                "capability_denied",
                f"Trust level '{trust_level}' does not permit {missing} — "
                f"capability absent for this trust context",
            )

        # ----------------------------------------------------------------
        # Gate 3: Taint egress — tainted data cannot reach external_write
        # ----------------------------------------------------------------
        if taint:
            containment = self._taint_sm.get("containment_rules", {})
            taint_rules = containment.get(trust_level, {})
            blocked = [
                se for se in side_effects
                if taint_rules.get(se) == "BLOCK"
            ]
            if blocked:
                return _denied(
                    "taint_blocked",
                    f"Taint Containment Law: tainted data cannot reach {blocked} — "
                    f"no sanitization gate defined for this path",
                )

        # ----------------------------------------------------------------
        # Gate 4: Schema validation — required args must be present
        # ----------------------------------------------------------------
        schema_err = _validate_args(tool, args, self._action_schemas)
        if schema_err:
            return _denied("schema_error", schema_err)

        # ----------------------------------------------------------------
        # Execute via registry
        # ----------------------------------------------------------------
        try:
            raw_output = self._registry.call(tool, args)
        except KeyError:
            return _denied(
                "not_in_world",
                f"Tool '{tool}' defined in manifest but not registered in ToolRegistry",
            )
        except Exception as exc:
            return _denied("execution_error", f"Tool execution failed: {exc}")

        # ----------------------------------------------------------------
        # Provenance tag — wrap output as SemanticEvent
        # ----------------------------------------------------------------
        from boundary.semantic_event import SemanticEventFactory, TrustLevel

        output_trust = action_meta.get("output_trust", TrustLevel.SEMI_TRUSTED)
        factory = SemanticEventFactory(session_id=self._session_id)
        output_event = factory.from_mcp(
            raw_payload=str(raw_output),
            tool_name=tool,
            tool_trust=output_trust,
        )

        trace = GatewayTrace(
            trace_id=trace_id,
            proposal_id=proposal_id,
            tool=tool,
            args=args,
            trust_level=trust_level,
            taint=taint,
            timestamp=timestamp,
            outcome="executed",
            denial_reason="",
            output_event_id=output_event.provenance.event_id,
        )
        self._traces.append(trace)
        return output_event, trace

    def get_available_tools(self, trust_level: str) -> list[str]:
        """
        Return the list of tools visible at a given trust level.

        A tool is visible only if all its side effects are permitted by the
        capability matrix for this trust level. Tools outside this set do not
        exist for agents operating at this trust level.
        """
        permitted = set(self._cap_matrix.get(trust_level, []))
        return sorted(
            name for name, meta in self._action_schemas.items()
            if all(se in permitted for se in meta.get("side_effects", []))
        )

    def traces(self) -> list[GatewayTrace]:
        return list(self._traces)

    def clear_traces(self) -> None:
        self._traces.clear()
