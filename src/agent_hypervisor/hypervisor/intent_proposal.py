"""
boundary/intent_proposal.py — The typed Intent Proposal model (Layer 3 output).

An IntentProposal is the only thing an agent can emit. The agent cannot execute
actions directly — it proposes structured declarations of what it wants to do,
and the Hypervisor (Layer 4: World Policy) decides whether the intent can become
a consequence in the virtual world.

This is Invariant I-5 (Separation): the agent can only receive Semantic Events
(from Layer 3) and emit Intent Proposals (to Layer 4). All other interactions
are mediated by the hypervisor.

Fields:
    tool        : The action name the agent wants to invoke.
    args        : A dict of arguments for that action (typed, not raw strings).
    context     : Optional dict of reasoning context (for audit/trace — not used
                  in policy evaluation).
    source_event_id : The event_id of the SemanticEvent that triggered this intent
                  (for provenance chain linking: Invariant I-2).
    taint       : Whether this proposal is derived from tainted data.
                  Set by the agent interface based on the SemanticEvent(s) it read.
    trust_level : The trust level of the triggering SemanticEvent — propagated from
                  the input boundary, not chosen by the agent.
    proposal_id : Unique ID for this proposal (for audit log correlation).
    timestamp   : ISO 8601 UTC timestamp.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from boundary.semantic_event import TrustLevel


# ---------------------------------------------------------------------------
# Intent Proposal
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IntentProposal:
    """
    A structured declaration of what the agent wants to do.

    The agent proposes; the Hypervisor decides. The agent has no way to
    execute actions directly — it can only construct IntentProposals and
    submit them to Layer 4 (World Policy evaluation).

    Immutable by design: once constructed, a proposal cannot be altered
    by the agent. Any modification would require constructing a new proposal
    (which would get a new proposal_id and timestamp).
    """
    tool: str
    args: dict[str, Any]
    taint: bool
    trust_level: str

    # Provenance chain link — ties this proposal back to the SemanticEvent
    # that triggered it. Empty string if the proposal was not triggered by
    # a specific event (e.g. proactive agent action from user instruction).
    source_event_id: str = ""

    # Optional reasoning context for audit/trace. Not used in policy evaluation.
    context: dict[str, Any] = field(default_factory=dict)

    # Auto-populated identity fields
    proposal_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def is_tainted(self) -> bool:
        return self.taint

    def is_from_trusted_source(self) -> bool:
        return self.trust_level == TrustLevel.TRUSTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "tool": self.tool,
            "args": dict(self.args),
            "taint": self.taint,
            "trust_level": self.trust_level,
            "source_event_id": self.source_event_id,
            "context": dict(self.context),
            "timestamp": self.timestamp,
        }

    def __repr__(self) -> str:
        return (
            f"IntentProposal(tool={self.tool!r}, taint={self.taint}, "
            f"trust={self.trust_level}, args={self.args!r})"
        )


# ---------------------------------------------------------------------------
# Builder — construct IntentProposals from SemanticEvents
# ---------------------------------------------------------------------------

class IntentProposalBuilder:
    """
    Constructs IntentProposals with correct taint and trust propagation.

    The builder ensures that:
    - taint from the triggering SemanticEvent is propagated to the proposal
    - trust_level is inherited from the event, not chosen by the agent
    - source_event_id links the proposal back to its provenance chain

    Usage (from inside an agent):
        builder = IntentProposalBuilder(triggering_event)
        proposal = builder.build("send_email", {"to": ["x@y.com"], "body": summary})
    """

    def __init__(self, triggering_event: Any | None = None) -> None:
        """
        Args:
            triggering_event: The SemanticEvent that caused the agent to form
                              this intent. If None, the proposal is treated as
                              originating from a TRUSTED user instruction with
                              no taint. This should only be used for proposals
                              that genuinely do not derive from any external input.
        """
        if triggering_event is not None:
            self._taint = triggering_event.taint
            self._trust_level = triggering_event.trust_level
            self._source_event_id = triggering_event.provenance.event_id
        else:
            self._taint = False
            self._trust_level = TrustLevel.TRUSTED
            self._source_event_id = ""

    def build(
        self,
        tool: str,
        args: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> IntentProposal:
        """
        Construct an IntentProposal.

        Args:
            tool    : The action the agent wants to perform.
            args    : Arguments for the action (dict, not raw string).
            context : Optional reasoning context (for audit only).
        """
        return IntentProposal(
            tool=tool,
            args=args or {},
            taint=self._taint,
            trust_level=self._trust_level,
            source_event_id=self._source_event_id,
            context=context or {},
        )

    def with_elevated_taint(self) -> "IntentProposalBuilder":
        """
        Return a new builder that forces taint=True regardless of the source event.

        Use when the agent has combined tainted and untainted data and the
        output should be considered tainted (conservative propagation).
        """
        new = IntentProposalBuilder.__new__(IntentProposalBuilder)
        new._taint = True
        new._trust_level = TrustLevel.dominates(self._trust_level, TrustLevel.SEMI_TRUSTED)
        new._source_event_id = self._source_event_id
        return new
