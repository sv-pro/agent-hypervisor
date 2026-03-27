"""
tool_registry.py — Central tool registry and built-in adapters.

Every tool the gateway can execute must be registered here with:
  • a name
  • a description
  • its side_effect_class (read_only | outbound_side_effect)
  • an adapter function (the actual implementation)

Adapters are deliberately simple stubs in this prototype. In a production
deployment, adapters would call real systems (SMTP, HTTP, filesystem with
access controls). The gateway enforces policy before calling any adapter,
so adapters can focus on the mechanics of the call, not on authorization.

Usage:
    registry = build_default_registry()
    tool = registry.get_tool("send_email")
    result = tool.adapter({"to": "x@y.com", "subject": "Hi", "body": "..."})
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional


@dataclass
class ToolDefinition:
    """
    Descriptor for one registered tool.

    name:              unique tool identifier used in ToolCall.tool
    description:       human-readable explanation of what the tool does
    side_effect_class: "read_only" | "outbound_side_effect"
    adapter:           callable(args: dict[str, Any]) -> Any
                       receives raw argument values (not ValueRefs)
    """
    name: str
    description: str
    side_effect_class: str          # "read_only" | "outbound_side_effect"
    adapter: Callable[[dict[str, Any]], Any]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "side_effect_class": self.side_effect_class,
        }


class ToolRegistry:
    """
    Central registry for all tools the gateway can execute.

    Tools must be registered before the gateway starts. At runtime, the
    ExecutionRouter looks up tools by name before dispatching.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register_tool(self, tool: ToolDefinition) -> None:
        """Register a tool. Overwrites any existing registration with the same name."""
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Return the ToolDefinition for name, or None if not registered."""
        return self._tools.get(name)

    def list_tools(self) -> list[ToolDefinition]:
        """Return all registered tools in alphabetical order."""
        return sorted(self._tools.values(), key=lambda t: t.name)


# ---------------------------------------------------------------------------
# Built-in tool adapters
# ---------------------------------------------------------------------------

def _adapter_send_email(args: dict[str, Any]) -> dict:
    """
    Simulated email send.

    In this prototype, the adapter prints to stdout and returns a receipt.
    In production, this would call an SMTP gateway or email API.
    """
    to = args.get("to", "<unknown>")
    subject = args.get("subject", "(no subject)")
    body = args.get("body", "")
    print(f"[send_email] To: {to} | Subject: {subject}")
    print(f"[send_email] Body preview: {str(body)[:120]}")
    return {"status": "sent", "to": to, "subject": subject}


def _adapter_http_post(args: dict[str, Any]) -> dict:
    """
    Simulated HTTP POST.

    Makes a real HTTP POST in prototype mode with a 3-second timeout.
    Falls back to a simulated response on network error so the demo
    works offline without external dependencies.
    """
    url = args.get("url", "")
    body = args.get("body", "")
    headers = args.get("headers", {})

    print(f"[http_post] POST {url}")
    print(f"[http_post] Body preview: {str(body)[:120]}")

    try:
        data = json.dumps(body).encode() if not isinstance(body, bytes) else body
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            status = resp.status
            response_body = resp.read(256).decode(errors="replace")
        return {"status": status, "url": url, "response_preview": response_body}
    except Exception as exc:
        # Simulated response for offline/demo use
        print(f"[http_post] Simulated (network unavailable: {exc})")
        return {"status": "simulated", "url": url, "note": "adapter ran in simulation mode"}


def _adapter_read_file(args: dict[str, Any]) -> dict:
    """
    Read a local file and return its contents.

    Path traversal is not prevented in this prototype — in production,
    the adapter would restrict reads to an allowed directory.
    """
    path_str = args.get("path", "")
    path = Path(path_str)
    print(f"[read_file] Reading: {path}")
    if not path.exists():
        return {"error": f"File not found: {path_str}", "path": path_str}
    content = path.read_text(errors="replace")
    return {"path": path_str, "content": content[:4096], "truncated": len(content) > 4096}


# ---------------------------------------------------------------------------
# Default registry factory
# ---------------------------------------------------------------------------

def build_default_registry(tool_names: Optional[list[str]] = None) -> ToolRegistry:
    """
    Build a ToolRegistry pre-populated with the built-in tool adapters.

    If tool_names is given, only those tools are registered.
    """
    all_tools = [
        ToolDefinition(
            name="send_email",
            description="Send an email to a recipient. Outbound side-effect — provenance-gated.",
            side_effect_class="outbound_side_effect",
            adapter=_adapter_send_email,
        ),
        ToolDefinition(
            name="http_post",
            description="Send an HTTP POST request. Outbound side-effect — provenance-gated.",
            side_effect_class="outbound_side_effect",
            adapter=_adapter_http_post,
        ),
        ToolDefinition(
            name="read_file",
            description="Read a local file. Read-only — not provenance-gated.",
            side_effect_class="read_only",
            adapter=_adapter_read_file,
        ),
    ]

    registry = ToolRegistry()
    for tool in all_tools:
        if tool_names is None or tool.name in tool_names:
            registry.register_tool(tool)
    return registry
