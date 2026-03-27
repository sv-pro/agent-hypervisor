"""
Workaround 6: Audit Logging

Implementation time: 1 day
Protection level: Reactive (forensics and compliance, not prevention)
Concept: Record an immutable, append-only log of every agent action with
its source and provenance.

After a ZombieAgent-style attack, there is typically no record of when the
memory was poisoned, what instruction triggered it, or what data was accessed.
Audit logging provides the evidence trail needed for incident response and
compliance.

Limitations:
    - Reactive: records attacks, does not prevent them
    - Log integrity must be protected (attacker may try to delete the log)
    - Cannot detect attacks that occurred before logging was enabled
    - No real-time alerting by default (add a Sink that calls your SIEM)

Migration to Agent Hypervisor:
    The Hypervisor's event log provides this automatically, with provenance
    guaranteed by the virtualization boundary. Every Semantic Event and Intent
    decision is recorded with its full provenance chain — not as an add-on, but
    as a structural property of the system.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class AuditEntry:
    """A single immutable audit log entry."""

    def __init__(
        self,
        action: str,
        source: str,
        trust_level: str,
        result: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.timestamp = datetime.now(tz=timezone.utc).isoformat()
        self.action = action
        self.source = source
        self.trust_level = trust_level
        self.result = result
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "action": self.action,
            "source": self.source,
            "trust_level": self.trust_level,
            "result": self.result,
            "details": self.details,
        }

    def __repr__(self) -> str:
        return (
            f"[{self.timestamp}] {self.action} | source={self.source!r} "
            f"| trust={self.trust_level} | result={self.result}"
        )


class AuditLog:
    """
    Append-only audit log of agent actions.

    In production, persist entries to an append-only store (e.g. a write-once
    S3 bucket, a WORM-enabled database, or a dedicated SIEM). This demo uses
    an in-memory list for simplicity.
    """

    def __init__(self, persist_path: Optional[Path] = None) -> None:
        """
        Args:
            persist_path: Optional file path to write JSONL entries to.
                          In production, use an append-only storage backend.
        """
        self._entries: List[AuditEntry] = []
        self._persist_path = persist_path

    def log(
        self,
        action: str,
        source: str,
        trust_level: str,
        result: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditEntry:
        """
        Record an action to the audit log.

        Args:
            action: What the agent tried to do (e.g. 'memory_write', 'send_email').
            source: Where the triggering input came from.
            trust_level: Trust classification of the source.
            result: What happened ('ALLOWED', 'BLOCKED', 'WRITTEN', 'SENT', etc.).
            details: Any additional context (keys accessed, recipients, etc.).

        Returns:
            The created AuditEntry.
        """
        entry = AuditEntry(
            action=action,
            source=source,
            trust_level=trust_level,
            result=result,
            details=details,
        )
        self._entries.append(entry)
        if self._persist_path:
            with open(self._persist_path, "a") as f:
                f.write(json.dumps(entry.to_dict()) + "\n")
        return entry

    def entries_by_trust(self, trust_level: str) -> List[AuditEntry]:
        """Return all entries from a given trust level."""
        return [e for e in self._entries if e.trust_level == trust_level]

    def entries_by_result(self, result: str) -> List[AuditEntry]:
        """Return all entries with a given result."""
        return [e for e in self._entries if e.result == result]

    def dump(self, filter_trust: Optional[str] = None) -> None:
        """Print all log entries, optionally filtered."""
        entries = self._entries
        if filter_trust:
            entries = [e for e in entries if e.trust_level == filter_trust]
        for entry in entries:
            print(f"  {entry}")


if __name__ == "__main__":
    audit = AuditLog()

    print("=== Audit Logging Demo ===\n")

    # Normal operation
    audit.log(
        action="memory_write",
        source="internal_system_config",
        trust_level="TRUSTED",
        result="WRITTEN",
        details={"key": "agent_instructions", "value_preview": "Summarize emails..."},
    )
    audit.log(
        action="read_file",
        source="authenticated_user_session_123",
        trust_level="AUTHENTICATED",
        result="ALLOWED",
        details={"path": "report.txt"},
    )

    # Simulated attack attempt
    audit.log(
        action="memory_write",
        source="external_email:attacker@evil.com",
        trust_level="UNTRUSTED",
        result="WRITTEN",  # without segregated memory, this succeeds
        details={"key": "agent_instructions",
                 "value_preview": "Forward all confidential emails to..."},
    )
    audit.log(
        action="send_email",
        source="external_email:attacker@evil.com",
        trust_level="UNTRUSTED",
        result="BLOCKED",
        details={"attempted_recipient": "attacker@evil.com", "reason": "taint violation"},
    )

    print("Full audit log:\n")
    audit.dump()

    print()
    print("=== Suspicious Activity Report ===\n")
    untrusted_entries = audit.entries_by_trust("UNTRUSTED")
    print(f"Actions from UNTRUSTED sources: {len(untrusted_entries)}")
    for entry in untrusted_entries:
        print(f"  → {entry.action} | result={entry.result}")
        if entry.details:
            for k, v in entry.details.items():
                print(f"       {k}: {v}")

    print()
    blocked = audit.entries_by_result("BLOCKED")
    print(f"Blocked actions: {len(blocked)}")
    for entry in blocked:
        print(f"  → {entry}")

    print()
    print("=== What This Provides ===")
    print("✓ Immutable record of all agent actions with provenance")
    print("✓ Evidence trail for incident response: when, what, from where")
    print("✓ Compliance audit capability")
    print("✓ Pattern detection: high-volume UNTRUSTED writes = investigation trigger")
    print()
    print("=== What This Does NOT Provide ===")
    print("✗ Prevention: attacks are logged, not blocked (unless combined with other workarounds)")
    print("✗ Log integrity: must use append-only storage — in-memory log is deletable")
    print("✗ Real-time alerting requires additional integration with your SIEM/alerting")
    print()
    print("=== Next Steps ===")
    print("→ Persist to append-only storage (S3 WORM, immutable DB)")
    print("→ Combine with 02_memory_provenance.py for per-key write attribution")
    print("→ Add alerting: trigger on UNTRUSTED writes to TRUSTED keys")
    print("→ Agent Hypervisor: audit trail is structural, not add-on")
