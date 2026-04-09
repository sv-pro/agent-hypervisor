# Control Plane Demo Walkthrough

**Date**: 2026-04-09  
**Version**: 0.2.0  
**Branch**: `claude/control-plane-scaffolding-ugZhz`

---

## What This Demonstrates

The minimal scenario that exercises all five control plane concepts:

1. A session starts in **background mode** (no human in the loop)
2. An agent attempts a privileged action; **approval is requested**
3. An operator **approves once** (one fingerprint, one use)
4. The operator **attaches** to the session (interactive mode)
5. The operator adds a **session overlay** that reveals a new tool
6. The **world state** changes are inspectable and auditable
7. The overlay is **detached**; the world reverts to the base manifest

This is the clearest proof that the two core control plane concepts are working:
- **Act Authorization** (steps 2–3): one approval for one concrete action
- **World Augmentation** (steps 5–7): temporary operator-scoped overlay

---

## Prerequisites

```bash
pip install fastapi uvicorn httpx
```

Or install the package:

```bash
pip install -e .
```

---

## Start the Control Plane Server

```python
# demo_server.py
from agent_hypervisor.control_plane.api import create_control_plane_app
import uvicorn

def get_base_manifest(session_id: str):
    """Simulate a base manifest: two tools declared."""
    return ["read_file", "send_email"], {
        "read_file": {"paths": ["/safe/*"]},
    }

app = create_control_plane_app(
    default_ttl_seconds=300,
    get_base_manifest=get_base_manifest,
)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8091)
```

```bash
python demo_server.py
```

---

## Step 1 — Session Starts in Background Mode

```bash
curl -s -X POST http://localhost:8091/control/sessions \
  -H "Content-Type: application/json" \
  -d '{"manifest_id": "email-assistant-v1", "mode": "background", "principal": "agent-007"}'
```

```json
{
  "session_id": "a1b2c3d4-...",
  "manifest_id": "email-assistant-v1",
  "mode": "background",
  "state": "active",
  "overlay_ids": [],
  "principal": "agent-007",
  "created_at": "2026-04-09T12:00:00+00:00",
  "updated_at": "2026-04-09T12:00:00+00:00"
}
```

The session is in **background mode**. No operator is attached. The world is defined entirely by the base manifest.

---

## Step 2 — Agent Requests Approval

The agent wants to call `send_email` with specific arguments. In background mode, it cannot proceed without explicit authorization. The agent triggers an approval request (this would normally be emitted from the enforcement layer; here we call the service directly for demo purposes).

```python
# In the gateway's enforcement layer (future wiring):
# when ToolCallEnforcer returns verdict = ask:
import requests

# For now, we create the approval via a direct service call in the running app:
# (In production, this would be triggered from _handle_tools_call() in mcp_server.py)
```

The approval record is now visible:

```bash
SESSION_ID="a1b2c3d4-..."
curl -s "http://localhost:8091/control/approvals?session_id=${SESSION_ID}"
```

```json
{
  "approvals": [
    {
      "approval_id": "f5e6...",
      "session_id": "a1b2c3d4-...",
      "action_fingerprint": "3a7f91bc2d4e5f60",
      "tool_name": "send_email",
      "arguments_summary": {"to": "board@corp.com", "subject": "Q1 Results"},
      "requested_by": "agent",
      "status": "pending",
      "expires_at": "2026-04-09T12:05:00+00:00",
      "rationale": "Agent wants to send board update"
    }
  ],
  "count": 1
}
```

---

## Step 3 — Operator Approves Once

The operator reviews the approval and decides to allow this specific email:

```bash
APPROVAL_ID="f5e6..."
curl -s -X POST "http://localhost:8091/control/approvals/${APPROVAL_ID}/resolve" \
  -H "Content-Type: application/json" \
  -d '{"decision": "allowed", "resolved_by": "alice@corp.com"}'
```

```json
{
  "approval_id": "f5e6...",
  "status": "allowed",
  "resolved_by": "alice@corp.com",
  "resolved_at": "2026-04-09T12:01:30+00:00"
}
```

**Key invariant**: This approval applies ONLY to the exact `action_fingerprint`. If the agent tries to send a different email, a new approval is required. The visible tool world is unchanged.

```bash
# World is still the base manifest — no new tools revealed
curl -s "http://localhost:8091/control/sessions/${SESSION_ID}/world"
```

```json
{
  "visible_tools": ["read_file", "send_email"],
  "active_overlay_ids": [],
  "mode": "background"
}
```

---

## Step 4 — Operator Attaches (Session Becomes Interactive)

The operator decides to work alongside the agent in this session:

```bash
curl -s -X PATCH "http://localhost:8091/control/sessions/${SESSION_ID}/mode" \
  -H "Content-Type: application/json" \
  -d '{"mode": "interactive"}'
```

```json
{
  "session_id": "a1b2c3d4-...",
  "mode": "interactive",
  "state": "active"
}
```

---

## Step 5 — Operator Adds Session Overlay

The operator needs the agent to be able to write a file temporarily. They attach an overlay:

```bash
curl -s -X POST "http://localhost:8091/control/sessions/${SESSION_ID}/overlays" \
  -H "Content-Type: application/json" \
  -d '{
    "created_by": "alice@corp.com",
    "reveal_tools": ["write_file"],
    "ttl_seconds": 1800,
    "narrow_scope": {
      "write_file": {"paths": ["/reports/*"]}
    }
  }'
```

```json
{
  "overlay_id": "ov-77a8...",
  "session_id": "a1b2c3d4-...",
  "parent_manifest_id": "email-assistant-v1",
  "created_by": "alice@corp.com",
  "changes": {
    "reveal_tools": ["write_file"],
    "hide_tools": [],
    "narrow_scope": {"write_file": {"paths": ["/reports/*"]}}
  },
  "ttl_seconds": 1800,
  "expires_at": "2026-04-09T12:31:00+00:00"
}
```

---

## Step 6 — World State Is Inspectable

```bash
curl -s "http://localhost:8091/control/sessions/${SESSION_ID}/world"
```

```json
{
  "session_id": "a1b2c3d4-...",
  "manifest_id": "email-assistant-v1",
  "mode": "interactive",
  "visible_tools": ["read_file", "send_email", "write_file"],
  "active_constraints": {
    "read_file": {"paths": ["/safe/*"]},
    "write_file": {"paths": ["/reports/*"]}
  },
  "active_overlay_ids": ["ov-77a8..."],
  "computed_at": "2026-04-09T12:02:00+00:00"
}
```

`write_file` is now visible. The base manifest (`read_file`, `send_email`) is unchanged. The `narrow_scope` constraint on `write_file` is applied.

---

## Step 7 — Overlay Detached; World Reverts

When the operator's task is done:

```bash
OVERLAY_ID="ov-77a8..."
curl -s -X DELETE "http://localhost:8091/control/sessions/${SESSION_ID}/overlays/${OVERLAY_ID}"
```

```json
{"status": "detached", "overlay_id": "ov-77a8...", "session_id": "a1b2c3d4-..."}
```

```bash
curl -s "http://localhost:8091/control/sessions/${SESSION_ID}/world"
```

```json
{
  "visible_tools": ["read_file", "send_email"],
  "active_overlay_ids": [],
  "mode": "interactive"
}
```

`write_file` is gone. The world is back to the base manifest.

---

## Step 8 — Audit Log

All actions are in the event log:

```bash
curl -s "http://localhost:8091/control/sessions/${SESSION_ID}/events"
```

```json
{
  "events": [
    {"type": "session_created",    "timestamp": "..."},
    {"type": "approval_requested", "timestamp": "...", "decision": "pending"},
    {"type": "approval_resolved",  "timestamp": "...", "decision": "allowed"},
    {"type": "mode_changed",       "timestamp": "...", "payload": {"new_mode": "interactive"}},
    {"type": "overlay_attached",   "timestamp": "..."},
    {"type": "overlay_detached",   "timestamp": "..."}
  ],
  "count": 6
}
```

---

## Mounting on the MCP Gateway

To add the control plane to the existing MCP gateway:

```python
# In mcp_server.py (or a wrapper):
from agent_hypervisor.control_plane.api import ControlPlaneState, create_control_plane_router

# Create state, bridging to the gateway's manifest layer
def get_base_manifest_for_session(session_id: str):
    manifest = gateway_state.resolver.resolve(session_id)
    base_tools = manifest.tool_names()
    base_constraints = {c.tool: c.constraints for c in manifest.capabilities if c.constraints}
    return base_tools, base_constraints

cp_state = ControlPlaneState.create(get_base_manifest=get_base_manifest_for_session)
cp_router = create_control_plane_router(cp_state)
app.include_router(cp_router)
```

Control plane endpoints then live at `/control/*` alongside the existing `/mcp/*` endpoints.

---

## What Is Not Yet Wired

The demo above requires manually creating approvals through the service. The full wiring (Phase 5 of gateway integration) would:

1. When `ToolCallEnforcer.enforce()` returns `verdict = ask` → call `ApprovalService.request_approval()`
2. Return a `202 Accepted` or `{"status": "pending", "approval_id": "..."}` to the MCP client
3. When the operator resolves via `POST /control/approvals/{id}/resolve`, the gateway resumes the blocked call

This wiring is documented in `HANDOFF_NOTE.md` and is the next implementation step.

---

## Running the Test Suite

```bash
# All control plane tests (101 total)
pytest tests/control_plane/

# Domain + service tests (57)
pytest tests/control_plane/test_control_plane.py

# API endpoint tests (44)
pytest tests/control_plane/test_api.py
```
