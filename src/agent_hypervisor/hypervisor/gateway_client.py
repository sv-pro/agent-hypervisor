"""
gateway_client.py — Python client for the Agent Hypervisor Tool Gateway.

Provides a thin, zero-dependency HTTP client over the gateway's REST API.
Uses only Python stdlib (urllib.request + json), so it can be dropped into
any Python project without adding package dependencies.

Typical usage:

    from agent_hypervisor.gateway_client import GatewayClient

    client = GatewayClient("http://localhost:8080")

    # Direct execution
    result = client.execute_tool(
        tool="read_file",
        arguments={"path": {"value": "report.txt", "source": "system"}},
    )
    print(result["verdict"])  # "allow"
    print(result["result"])   # file contents

    # Approval workflow
    response = client.execute_tool(
        tool="send_email",
        arguments={
            "to":      {"value": "alice@company.com", "source": "user_declared"},
            "subject": {"value": "Q3 Report",         "source": "system"},
            "body":    {"value": "See attached.",      "source": "system"},
        },
    )
    if response["verdict"] == "ask":
        approval_id = response["approval_id"]
        print(f"Approval required: {approval_id}")

        final = client.submit_approval(approval_id, approved=True, actor="alice")
        print(final["result"])

    # Wrapped tool pattern
    guarded_send = client.wrap_tool("send_email")
    response = guarded_send(
        to={"value": "bob@company.com", "source": "user_declared"},
        subject={"value": "Hello", "source": "system"},
        body={"value": "Hi!", "source": "system"},
    )

Argument format:

    Each argument is a dict with these fields:
      value   — the argument value (str, int, list, …)
      source  — provenance class: "external_document" | "derived" |
                "user_declared" | "system"
      parents — list of argument names this value was derived from (optional)
      role    — semantic role: "recipient_source" | "data_source" | … (optional)
      label   — human-readable origin description (optional)

    Helper: use arg() to build these dicts concisely.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable, Optional


# ---------------------------------------------------------------------------
# Argument builder helper
# ---------------------------------------------------------------------------

def arg(
    value: Any,
    source: str = "external_document",
    *,
    parents: Optional[list[str]] = None,
    role: Optional[str] = None,
    label: str = "",
) -> dict:
    """
    Build an ArgSpec dict for use in execute_tool() arguments.

    Example:
        client.execute_tool("send_email", {
            "to":      arg("alice@company.com", "user_declared", role="recipient_source"),
            "subject": arg("Report", "system"),
            "body":    arg("See attached.", "system"),
        })
    """
    spec: dict[str, Any] = {"value": value, "source": source}
    if parents:
        spec["parents"] = parents
    if role:
        spec["role"] = role
    if label:
        spec["label"] = label
    return spec


# ---------------------------------------------------------------------------
# GatewayClient
# ---------------------------------------------------------------------------

class GatewayError(Exception):
    """Raised when the gateway returns an unexpected HTTP error."""
    def __init__(self, status: int, detail: str) -> None:
        self.status = status
        self.detail = detail
        super().__init__(f"Gateway error {status}: {detail}")


class GatewayClient:
    """
    HTTP client for the Agent Hypervisor Tool Gateway.

    All methods return parsed JSON dicts. HTTP 4xx responses from tool
    execution (deny, approval errors) are returned as normal dicts, not
    exceptions — callers should check response["verdict"].

    Other HTTP errors (5xx, network failures) raise GatewayError.

    Args:
        base_url: Base URL of the running gateway, e.g. "http://127.0.0.1:8080".
        timeout:  HTTP request timeout in seconds (default 30).
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8080",
        timeout: int = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Core methods
    # ------------------------------------------------------------------

    def status(self) -> dict:
        """Return gateway status (GET /)."""
        return self._request("GET", "/")

    def list_tools(self) -> list[dict]:
        """Return registered tools from GET /tools/list."""
        return self._request("POST", "/tools/list").get("tools", [])

    def execute_tool(
        self,
        tool: str,
        arguments: dict[str, dict],
        call_id: str = "",
        provenance: Optional[dict] = None,
    ) -> dict:
        """
        Execute a tool through the gateway.

        Arguments must be ArgSpec dicts — use the arg() helper or pass dicts
        directly. The gateway evaluates provenance policy and returns a verdict.

        Returns a dict with:
            verdict          — "allow" | "deny" | "ask"
            reason           — explanation
            matched_rule     — rule that determined verdict
            policy_version   — active policy hash
            trace_id         — link to trace log
            result           — tool output (only when allow)
            approval_id      — present when verdict == "ask"
            approval_required — True when verdict == "ask"

        Note: deny responses have HTTP status 403, but this method always
        returns a dict (no exception raised for deny verdicts).
        """
        body: dict[str, Any] = {"tool": tool, "arguments": arguments}
        if call_id:
            body["call_id"] = call_id
        if provenance:
            body["provenance"] = provenance
        return self._request("POST", "/tools/execute", body, allow_4xx=True)

    def submit_approval(
        self,
        approval_id: str,
        approved: bool,
        actor: str = "human-reviewer",
    ) -> dict:
        """
        Approve or reject a pending approval.

        When approved=True, the gateway executes the stored tool request and
        returns the result. When approved=False, the request is rejected.

        Returns the same dict structure as execute_tool().
        Raises GatewayError(404) if approval_id is not found.
        Raises GatewayError(409) if already resolved.
        """
        body = {"approved": approved, "actor": actor}
        return self._request(
            "POST", f"/approvals/{approval_id}", body, allow_4xx=True
        )

    def get_approvals(self, status: Optional[str] = None, limit: int = 50) -> list[dict]:
        """
        Return approval records from GET /approvals.

        Filter by status: "pending" | "approved" | "rejected" | "executed".
        """
        path = f"/approvals?limit={limit}"
        if status:
            path += f"&status={status}"
        return self._request("GET", path).get("approvals", [])

    def get_approval(self, approval_id: str) -> dict:
        """Return one approval record by id (GET /approvals/{id})."""
        return self._request("GET", f"/approvals/{approval_id}")

    def get_traces(self, limit: int = 50) -> list[dict]:
        """Return recent trace entries from GET /traces."""
        return self._request("GET", f"/traces?limit={limit}").get("traces", [])

    def reload_policy(self) -> dict:
        """Trigger a policy hot-reload (POST /policy/reload)."""
        return self._request("POST", "/policy/reload")

    # ------------------------------------------------------------------
    # Wrapped tool pattern
    # ------------------------------------------------------------------

    def wrap_tool(self, tool_name: str) -> Callable[..., dict]:
        """
        Return a callable that routes calls to tool_name through the gateway.

        Each keyword argument is an ArgSpec dict (use arg() to build them).

        Example:
            send = client.wrap_tool("send_email")
            response = send(
                to=arg("alice@company.com", "user_declared"),
                subject=arg("Q3 Report", "system"),
                body=arg("See attached.", "system"),
            )
            if response["verdict"] == "ask":
                client.submit_approval(response["approval_id"], approved=True)
        """
        def _wrapped(**kwargs: dict) -> dict:
            return self.execute_tool(tool_name, kwargs)
        _wrapped.__name__ = f"gateway_{tool_name}"
        return _wrapped

    # ------------------------------------------------------------------
    # HTTP transport
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[dict] = None,
        allow_4xx: bool = False,
    ) -> dict:
        """
        Make an HTTP request to the gateway and return the parsed JSON response.

        allow_4xx: if True, 4xx responses are returned as dicts rather than
                   raising GatewayError. Used for tool execution and approval
                   endpoints where deny (403) is a valid outcome.
        """
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers: dict[str, str] = {}
        if data is not None:
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            if allow_4xx and 400 <= exc.code < 500:
                try:
                    return json.loads(body_text)
                except json.JSONDecodeError:
                    return {"error": body_text, "status": exc.code}
            try:
                detail = json.loads(body_text).get("detail", body_text)
            except json.JSONDecodeError:
                detail = body_text
            raise GatewayError(exc.code, detail) from exc
        except urllib.error.URLError as exc:
            raise GatewayError(0, f"Connection failed: {exc.reason}") from exc
