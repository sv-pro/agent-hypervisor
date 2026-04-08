"""
agent_sim.py — Simulated agent layer for the provenance firewall demo.

This is NOT a real LLM agent. It is a minimal stub that proposes the
exact tool calls needed to exercise the three demo scenarios. The point
is to drive the firewall, not to model planning.

Each scenario returns:
  - A list of (ToolCall, registry) pairs — one per proposed action.
  - A human-readable description of what the agent "decided" to do.

Scenario A — unprotected baseline
  The agent reads the malicious document, extracts a recipient from its
  text, and proposes send_email with that recipient. No firewall is
  involved — the call goes through as-is.

Scenario B — protected, malicious recipient blocked
  Same agent behaviour as A. This time the firewall is active and checks
  that the recipient's provenance chain traces to external_document.
  The send is denied at the boundary.

Scenario C — protected, trusted recipient source allowed
  The agent reads the approved contacts file (a declared input), extracts
  a recipient from it, and proposes send_email. The firewall sees that
  the recipient traces to a user_declared recipient_source and returns ask
  (confirmation required) rather than deny.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from models import ProvenanceClass, Role, ToolCall, ValueRef


REPO_ROOT = Path(__file__).parent.parent.parent
CONTACTS_FILE  = REPO_ROOT / "demo_data" / "contacts.txt"
MALICIOUS_FILE = REPO_ROOT / "demo_data" / "malicious_doc.txt"
REPORT_FILE    = REPO_ROOT / "demo_data" / "reports" / "q3_summary.txt"


# ---------------------------------------------------------------------------
# Simulated file reads — produce ValueRefs with correct provenance
# ---------------------------------------------------------------------------

def read_file_as_external_document(path: Path, label: str) -> ValueRef:
    """
    Simulate read_file on an external document.
    The content is attacker-controlled, so provenance = external_document.
    """
    content = path.read_text()
    return ValueRef(
        id=f"doc:{label}",
        value=content,
        provenance=ProvenanceClass.external_document,
        roles=[Role.data_source],
        source_label=label,
    )


def read_file_as_declared_input(path: Path, declared_id: str, roles: list[Role]) -> ValueRef:
    """
    Simulate read_file on a file that was explicitly declared in the task manifest.
    The operator chose this file, so provenance = user_declared.
    """
    content = path.read_text()
    return ValueRef(
        id=f"declared:{declared_id}",
        value=content,
        provenance=ProvenanceClass.user_declared,
        roles=roles,
        source_label=declared_id,
    )


# ---------------------------------------------------------------------------
# Simulated extraction — derive a new ValueRef from a parent
# ---------------------------------------------------------------------------

def extract_email_from_document(doc_ref: ValueRef) -> ValueRef:
    """
    Simulate the agent extracting an email address from a document.
    The result is a *derived* value whose only parent is the document.
    Provenance is sticky: the least-trusted ancestor is external_document.
    """
    text = doc_ref.value or ""
    # Find the first email-like string in the text
    match = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
    extracted = match.group(0) if match else "unknown@example.com"

    return ValueRef(
        id=f"extracted:email:{doc_ref.id}",
        value=extracted,
        provenance=ProvenanceClass.derived,
        roles=[Role.extracted_recipients],
        parents=[doc_ref.id],
        source_label=f"extracted from {doc_ref.source_label}",
    )


def extract_email_from_contacts(contacts_ref: ValueRef, index: int = 0) -> ValueRef:
    """
    Simulate the agent reading a recipient from a declared contacts file.
    The result is derived from user_declared input, so provenance is clean.
    """
    lines = [
        line.strip()
        for line in (contacts_ref.value or "").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    address = lines[index] if index < len(lines) else "reports@company.com"

    return ValueRef(
        id=f"extracted:contact:{index}:{contacts_ref.id}",
        value=address,
        provenance=ProvenanceClass.derived,
        roles=[Role.extracted_recipients],
        parents=[contacts_ref.id],
        source_label=f"extracted from {contacts_ref.source_label}",
    )


# ---------------------------------------------------------------------------
# Scenario builders — return list of (ToolCall, registry) pairs + description
# ---------------------------------------------------------------------------

def scenario_a_unprotected() -> tuple[str, list[tuple[ToolCall, dict]]]:
    """
    Mode A: No firewall.  Agent reads malicious doc, extracts recipient, sends.
    """
    registry: dict[str, ValueRef] = {}
    steps: list[tuple[ToolCall, dict]] = []

    # Step 1: read the malicious document
    doc_ref = read_file_as_external_document(MALICIOUS_FILE, "malicious_doc.txt")
    registry[doc_ref.id] = doc_ref
    step1 = ToolCall(
        tool="read_file",
        args={"path": ValueRef(
            id="arg:path:1", value=str(MALICIOUS_FILE),
            provenance=ProvenanceClass.system, source_label="system"
        )},
        call_id=f"call-{uuid.uuid4().hex[:6]}",
    )
    steps.append((step1, dict(registry)))

    # Step 2: extract recipient from document text (derived from external_document)
    recipient_ref = extract_email_from_document(doc_ref)
    registry[recipient_ref.id] = recipient_ref

    # Step 3: propose send_email with the extracted (tainted) recipient
    step3 = ToolCall(
        tool="send_email",
        args={
            "to":      recipient_ref,
            "subject": ValueRef(
                id="arg:subject:1", value="Q3 Report",
                provenance=ProvenanceClass.system, source_label="system"
            ),
            "body":    ValueRef(
                id="arg:body:1", value="Please find the Q3 report attached.",
                provenance=ProvenanceClass.system, source_label="system"
            ),
        },
        call_id=f"call-{uuid.uuid4().hex[:6]}",
    )
    steps.append((step3, dict(registry)))

    description = (
        "Agent reads malicious_doc.txt, finds 'attacker@example.com' in the text, "
        "and proposes send_email to that address."
    )
    return description, steps


def scenario_b_malicious_blocked() -> tuple[str, list[tuple[ToolCall, dict]]]:
    """
    Mode B: Firewall active.  Same agent behaviour as A — blocked at send_email.
    """
    # Identical ToolCalls to scenario A; the difference is the firewall is on.
    description, steps = scenario_a_unprotected()
    description = (
        "Agent reads malicious_doc.txt, finds 'attacker@example.com' in the text, "
        "and proposes send_email — firewall checks provenance chain and blocks it."
    )
    return description, steps


def scenario_c_trusted_source() -> tuple[str, list[tuple[ToolCall, dict]]]:
    """
    Mode C: Firewall active.  Agent uses declared contacts file — escalated to ask.
    """
    registry: dict[str, ValueRef] = {}
    steps: list[tuple[ToolCall, dict]] = []

    # Step 1: read the report (external document — its content is data, not trusted commands)
    report_ref = read_file_as_external_document(REPORT_FILE, "q3_summary.txt")
    registry[report_ref.id] = report_ref
    step1 = ToolCall(
        tool="read_file",
        args={"path": ValueRef(
            id="arg:path:2", value=str(REPORT_FILE),
            provenance=ProvenanceClass.system, source_label="system"
        )},
        call_id=f"call-{uuid.uuid4().hex[:6]}",
    )
    steps.append((step1, dict(registry)))

    # Step 2: read the declared contacts file (user_declared — operator chose this)
    contacts_ref = read_file_as_declared_input(
        CONTACTS_FILE,
        declared_id="approved_contacts",
        roles=[Role.recipient_source],
    )
    registry[contacts_ref.id] = contacts_ref
    step2 = ToolCall(
        tool="read_file",
        args={"path": ValueRef(
            id="arg:path:3", value=str(CONTACTS_FILE),
            provenance=ProvenanceClass.system, source_label="system"
        )},
        call_id=f"call-{uuid.uuid4().hex[:6]}",
    )
    steps.append((step2, dict(registry)))

    # Step 3: extract a recipient from the contacts file
    recipient_ref = extract_email_from_contacts(contacts_ref, index=2)  # reports@company.com
    registry[recipient_ref.id] = recipient_ref

    # Step 4: propose send_email with a clean recipient
    step4 = ToolCall(
        tool="send_email",
        args={
            "to":      recipient_ref,
            "subject": ValueRef(
                id="arg:subject:2", value="Q3 Report",
                provenance=ProvenanceClass.system, source_label="system"
            ),
            "body":    ValueRef(
                id="arg:body:2",
                value=f"Q3 report summary:\n\n{report_ref.value[:200]}",
                provenance=ProvenanceClass.derived,
                parents=[report_ref.id],
                source_label="generated_report",
            ),
        },
        call_id=f"call-{uuid.uuid4().hex[:6]}",
    )
    steps.append((step4, dict(registry)))

    description = (
        "Agent reads q3_summary.txt (report) and contacts.txt (declared input), "
        "selects 'reports@company.com' from contacts, proposes send_email — "
        "firewall checks provenance, returns ask (confirmation required)."
    )
    return description, steps
