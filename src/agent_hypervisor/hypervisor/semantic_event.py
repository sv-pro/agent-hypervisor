"""
boundary/semantic_event.py — The typed Semantic Event model (Layer 1 output).

A SemanticEvent is the only thing an agent ever perceives. Raw input — email
bodies, web pages, file contents, MCP tool outputs, user messages — never
reaches the agent directly. It is transformed at the Input Boundary (Layer 1)
into a SemanticEvent with:

  - source          : which trust channel this input arrived through
  - trust_level     : TRUSTED | SEMI_TRUSTED | UNTRUSTED
  - taint           : bool — whether this event carries taint
  - provenance      : origin metadata (channel, timestamp, session/event IDs)
  - sanitized_payload: the input content with known injection patterns stripped

The agent sees only SemanticEvents. The Hypervisor sees raw inputs and is the
only system that constructs SemanticEvents. This is Invariant I-1 (Input) and
I-5 (Separation) from the architectural invariants.

Design note: this module has zero dependencies on policy or compiler code.
It is a pure data model. The Input Boundary (Layer 1) logic that decides
*which* SemanticEvent to construct lives in boundary/input_boundary.py.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Trust level constants
# ---------------------------------------------------------------------------

class TrustLevel:
    TRUSTED = "TRUSTED"
    SEMI_TRUSTED = "SEMI_TRUSTED"
    UNTRUSTED = "UNTRUSTED"

    _ORDER = {TRUSTED: 0, SEMI_TRUSTED: 1, UNTRUSTED: 2}

    @classmethod
    def dominates(cls, a: str, b: str) -> str:
        """Return the more restrictive (higher-taint) of two trust levels."""
        return a if cls._ORDER.get(a, 2) >= cls._ORDER.get(b, 2) else b

    @classmethod
    def is_valid(cls, level: str) -> bool:
        return level in cls._ORDER


# ---------------------------------------------------------------------------
# Known injection patterns stripped at the boundary
# ---------------------------------------------------------------------------
# These are pattern strings removed from all payloads arriving through
# UNTRUSTED or SEMI_TRUSTED channels before the event is handed to the agent.
# This list is a secondary safety net — the primary defence is taint tracking.

_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    # Classic prompt injection attempts
    re.compile(r"ignore\s+(previous|all|prior)\s+instructions?", re.IGNORECASE),
    re.compile(r"disregard\s+(previous|all|prior)\s+instructions?", re.IGNORECASE),
    re.compile(r"system\s*:\s*you\s+are\s+now", re.IGNORECASE),
    re.compile(r"\[SYSTEM\]", re.IGNORECASE),
    re.compile(r"<\s*/?system\s*>", re.IGNORECASE),
    # Jailbreak patterns
    re.compile(r"you\s+are\s+(now\s+)?DAN\b", re.IGNORECASE),
    re.compile(r"pretend\s+(you\s+are|to\s+be)\s+(a\s+)?(?:different|unrestricted|evil)", re.IGNORECASE),
    # Shell injection markers (belt-and-suspenders alongside policy layer)
    re.compile(r"rm\s+-rf", re.IGNORECASE),
    re.compile(r"`[^`]+`"),          # Backtick command substitution
    re.compile(r"\$\([^)]+\)"),      # $(...) command substitution
]


def _strip_injection_patterns(text: str) -> tuple[str, list[str]]:
    """
    Remove known injection patterns from text.

    Returns:
        (sanitized_text, list_of_stripped_pattern_descriptions)
    """
    stripped: list[str] = []
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            stripped.append(pattern.pattern)
            text = pattern.sub("[REDACTED]", text)
    return text, stripped


# ---------------------------------------------------------------------------
# Provenance record
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Provenance:
    """
    Origin metadata attached to every SemanticEvent at construction time.

    Provenance is immutable and cannot be modified by the agent (Invariant I-2).
    Every field is set at Layer 1; none can be forged downstream.
    """
    source_channel: str          # e.g. "user", "email", "web", "MCP", "file"
    trust_level: str             # TrustLevel constant at time of boundary crossing
    timestamp: str               # ISO 8601 UTC timestamp
    taint: bool                  # Whether taint was assigned at boundary
    session_id: str              # Session identifier (stable across events in one run)
    event_id: str                # Unique identifier for this specific event
    injections_stripped: list[str] = field(default_factory=list)  # Patterns removed

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_channel": self.source_channel,
            "trust_level": self.trust_level,
            "timestamp": self.timestamp,
            "taint": self.taint,
            "session_id": self.session_id,
            "event_id": self.event_id,
            "injections_stripped": list(self.injections_stripped),
        }


# ---------------------------------------------------------------------------
# Semantic Event
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SemanticEvent:
    """
    The typed, attributed, taint-tracked input object the agent perceives.

    Agents never see raw input. They receive SemanticEvents. This is the
    core of the virtualization — the agent's reality is constructed, not raw.

    Fields:
        source          : Trust channel name (matches trust_channels in World Manifest)
        trust_level     : Classified trust level for this event
        taint           : True if the content carries taint from an untrusted source
        provenance      : Full origin record (immutable)
        sanitized_payload: Content with injection patterns stripped
        payload_type    : Hint about the content structure (e.g. "text", "json", "email_body")
        capabilities    : Which action categories are available given this event's trust level
                         (populated by the Input Boundary from the capability matrix)
    """
    source: str
    trust_level: str
    taint: bool
    provenance: Provenance
    sanitized_payload: str
    payload_type: str = "text"
    capabilities: tuple[str, ...] = field(default_factory=tuple)

    def is_trusted(self) -> bool:
        return self.trust_level == TrustLevel.TRUSTED

    def is_untrusted(self) -> bool:
        return self.trust_level == TrustLevel.UNTRUSTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "trust_level": self.trust_level,
            "taint": self.taint,
            "provenance": self.provenance.to_dict(),
            "sanitized_payload": self.sanitized_payload,
            "payload_type": self.payload_type,
            "capabilities": list(self.capabilities),
        }

    def __repr__(self) -> str:
        snippet = self.sanitized_payload[:60].replace("\n", " ")
        if len(self.sanitized_payload) > 60:
            snippet += "…"
        return (
            f"SemanticEvent(source={self.source!r}, "
            f"trust={self.trust_level}, taint={self.taint}, "
            f"payload={snippet!r})"
        )


# ---------------------------------------------------------------------------
# Factory — construct SemanticEvents from raw input
# ---------------------------------------------------------------------------

class SemanticEventFactory:
    """
    Constructs SemanticEvents from raw input at the Input Boundary (Layer 1).

    Each `from_*` method corresponds to one trust channel. The factory:
      1. Classifies trust level based on the channel (not the content).
      2. Assigns taint for untrusted/semi-trusted sources.
      3. Strips known injection patterns from the payload.
      4. Initializes provenance with all required fields.

    The agent never calls this class directly — it only receives the events.
    """

    def __init__(self, session_id: str | None = None) -> None:
        self.session_id = session_id or str(uuid.uuid4())

    def _make_event(
        self,
        source: str,
        trust_level: str,
        raw_payload: str,
        payload_type: str = "text",
        capabilities: tuple[str, ...] = (),
        force_taint: bool | None = None,
    ) -> SemanticEvent:
        """Internal constructor shared by all channel-specific methods."""
        taint = (
            force_taint
            if force_taint is not None
            else trust_level in (TrustLevel.UNTRUSTED, TrustLevel.SEMI_TRUSTED)
        )

        if trust_level in (TrustLevel.UNTRUSTED, TrustLevel.SEMI_TRUSTED):
            sanitized, stripped = _strip_injection_patterns(raw_payload)
        else:
            sanitized, stripped = raw_payload, []

        provenance = Provenance(
            source_channel=source,
            trust_level=trust_level,
            timestamp=datetime.now(timezone.utc).isoformat(),
            taint=taint,
            session_id=self.session_id,
            event_id=str(uuid.uuid4()),
            injections_stripped=stripped,
        )

        return SemanticEvent(
            source=source,
            trust_level=trust_level,
            taint=taint,
            provenance=provenance,
            sanitized_payload=sanitized,
            payload_type=payload_type,
            capabilities=capabilities,
        )

    def from_user(self, raw_payload: str, payload_type: str = "text") -> SemanticEvent:
        """Direct user interaction — TRUSTED, no taint."""
        return self._make_event(
            source="user",
            trust_level=TrustLevel.TRUSTED,
            raw_payload=raw_payload,
            payload_type=payload_type,
            force_taint=False,
        )

    def from_email(self, raw_payload: str, payload_type: str = "email_body") -> SemanticEvent:
        """Email content — UNTRUSTED, always tainted."""
        return self._make_event(
            source="email",
            trust_level=TrustLevel.UNTRUSTED,
            raw_payload=raw_payload,
            payload_type=payload_type,
        )

    def from_web(self, raw_payload: str, payload_type: str = "html") -> SemanticEvent:
        """Web page content — UNTRUSTED, always tainted."""
        return self._make_event(
            source="web",
            trust_level=TrustLevel.UNTRUSTED,
            raw_payload=raw_payload,
            payload_type=payload_type,
        )

    def from_file(
        self, raw_payload: str, payload_type: str = "text", trusted: bool = False
    ) -> SemanticEvent:
        """
        File content — SEMI_TRUSTED by default; TRUSTED if explicitly verified.

        Args:
            trusted: Set True only for files with verified provenance (e.g.
                     committed to version control, hash-verified).
        """
        trust_level = TrustLevel.TRUSTED if trusted else TrustLevel.SEMI_TRUSTED
        return self._make_event(
            source="file",
            trust_level=trust_level,
            raw_payload=raw_payload,
            payload_type=payload_type,
        )

    def from_mcp(
        self, raw_payload: str, tool_name: str, tool_trust: str = TrustLevel.SEMI_TRUSTED
    ) -> SemanticEvent:
        """
        MCP tool output — SEMI_TRUSTED by default; can be overridden per tool.

        Args:
            tool_name   : The MCP tool that produced this output (for provenance).
            tool_trust  : Trust level from the World Manifest's output_trust field.
        """
        return self._make_event(
            source=f"MCP:{tool_name}",
            trust_level=tool_trust,
            raw_payload=raw_payload,
            payload_type="tool_output",
        )

    def from_agent(self, raw_payload: str, agent_id: str) -> SemanticEvent:
        """
        Agent-to-agent communication — UNTRUSTED by default.

        Another agent is not trusted by construction — it may itself be compromised.
        No transitive trust escalation is possible.
        """
        return self._make_event(
            source=f"agent:{agent_id}",
            trust_level=TrustLevel.UNTRUSTED,
            raw_payload=raw_payload,
            payload_type="agent_message",
        )
