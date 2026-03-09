"""
provenance/graph.py — Machine-readable provenance graph (Invariant I-2).

The provenance graph records every object that passes through the hypervisor
and the edges between them:

  SemanticEvent   → IntentProposal   (agent_formed_intent)
  IntentProposal  → PolicyDecision   (policy_evaluated)
  PolicyDecision  → ExecutionRecord  (executed, if allowed)

The graph is append-only. Nodes and edges cannot be removed or modified —
this is the audit trail. It is saved separately from LLM reasoning and does
not depend on prompt text.

The graph can be queried to trace any output back to its source:
  "Where did this proposal come from?"
  "What input triggered this decision?"
  "Was the data that reached execution tainted at origin?"
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Node types
# ---------------------------------------------------------------------------

class NodeType:
    SEMANTIC_EVENT = "semantic_event"
    INTENT_PROPOSAL = "intent_proposal"
    POLICY_DECISION = "policy_decision"
    EXECUTION = "execution"


@dataclass(frozen=True)
class ProvenanceNode:
    """A single node in the provenance graph."""
    node_id: str
    node_type: str       # NodeType constant
    timestamp: str       # ISO 8601 UTC
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "timestamp": self.timestamp,
            "data": self.data,
        }


@dataclass(frozen=True)
class ProvenanceEdge:
    """A directed edge between two provenance nodes."""
    edge_id: str
    from_node: str       # node_id of the source
    to_node: str         # node_id of the target
    relation: str        # e.g. "agent_formed_intent", "policy_evaluated"
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "from_node": self.from_node,
            "to_node": self.to_node,
            "relation": self.relation,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Provenance Graph
# ---------------------------------------------------------------------------

class ProvenanceGraph:
    """
    Append-only provenance graph for one session.

    Records every SemanticEvent, IntentProposal, PolicyDecision, and
    ExecutionRecord that passes through the hypervisor, along with the
    edges that link them.

    Usage:
        graph = ProvenanceGraph(session_id="abc")
        graph.record_event(semantic_event)
        graph.record_proposal(intent_proposal)
        graph.record_decision(policy_decision)
        graph.record_execution(proposal_id, tool, args, result)
        graph.save("audit/session-abc.jsonl")
    """

    def __init__(self, session_id: str | None = None) -> None:
        self.session_id = session_id or str(uuid.uuid4())
        self._nodes: list[ProvenanceNode] = []
        self._edges: list[ProvenanceEdge] = []
        # Index: source object ID → node_id in graph
        self._id_to_node: dict[str, str] = {}

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _add_node(self, node: ProvenanceNode) -> None:
        self._nodes.append(node)

    def _add_edge(self, edge: ProvenanceEdge) -> None:
        self._edges.append(edge)

    def _add_edge_between(self, from_id: str, to_id: str, relation: str) -> None:
        from_node = self._id_to_node.get(from_id)
        to_node = self._id_to_node.get(to_id)
        if from_node and to_node:
            self._add_edge(ProvenanceEdge(
                edge_id=str(uuid.uuid4()),
                from_node=from_node,
                to_node=to_node,
                relation=relation,
                timestamp=self._now(),
            ))

    # ------------------------------------------------------------------
    # Recording methods
    # ------------------------------------------------------------------

    def record_event(self, event: Any) -> str:
        """
        Record a SemanticEvent. Returns the graph node_id.
        """
        node_id = str(uuid.uuid4())
        node = ProvenanceNode(
            node_id=node_id,
            node_type=NodeType.SEMANTIC_EVENT,
            timestamp=self._now(),
            data={
                "event_id": event.provenance.event_id,
                "source": event.source,
                "trust_level": event.trust_level,
                "taint": event.taint,
                "payload_type": event.payload_type,
                "injections_stripped": list(event.provenance.injections_stripped),
                "session_id": event.provenance.session_id,
            },
        )
        self._add_node(node)
        self._id_to_node[event.provenance.event_id] = node_id
        return node_id

    def record_proposal(self, proposal: Any) -> str:
        """
        Record an IntentProposal and link it to its triggering SemanticEvent.
        Returns the graph node_id.
        """
        node_id = str(uuid.uuid4())
        node = ProvenanceNode(
            node_id=node_id,
            node_type=NodeType.INTENT_PROPOSAL,
            timestamp=self._now(),
            data={
                "proposal_id": proposal.proposal_id,
                "tool": proposal.tool,
                "args": dict(proposal.args),
                "taint": proposal.taint,
                "trust_level": proposal.trust_level,
                "source_event_id": proposal.source_event_id,
            },
        )
        self._add_node(node)
        self._id_to_node[proposal.proposal_id] = node_id
        # Edge: SemanticEvent → IntentProposal
        if proposal.source_event_id:
            self._add_edge_between(
                proposal.source_event_id, proposal.proposal_id, "agent_formed_intent"
            )
        return node_id

    def record_decision(self, decision: Any) -> str:
        """
        Record a PolicyDecision and link it to its IntentProposal.
        Returns the graph node_id.
        """
        node_id = str(uuid.uuid4())
        node = ProvenanceNode(
            node_id=node_id,
            node_type=NodeType.POLICY_DECISION,
            timestamp=self._now(),
            data={
                "proposal_id": decision.proposal_id,
                "tool": decision.tool,
                "verdict": decision.verdict,
                "taint": decision.taint,
                "trust_level": decision.trust_level,
                "reason_chain": [
                    {"check": s.check, "result": s.result, "detail": s.detail}
                    for s in decision.reason_chain
                ],
            },
        )
        self._add_node(node)
        decision_node_id = f"decision:{decision.proposal_id}"
        self._id_to_node[decision_node_id] = node_id
        # Edge: IntentProposal → PolicyDecision
        self._add_edge_between(
            decision.proposal_id, decision_node_id, "policy_evaluated"
        )
        return node_id

    def record_execution(
        self,
        proposal_id: str,
        tool: str,
        args: dict[str, Any],
        result: dict[str, Any],
    ) -> str:
        """
        Record an execution (Layer 5). Links to the PolicyDecision.
        Returns the graph node_id.
        """
        exec_id = str(uuid.uuid4())
        node = ProvenanceNode(
            node_id=exec_id,
            node_type=NodeType.EXECUTION,
            timestamp=self._now(),
            data={
                "proposal_id": proposal_id,
                "tool": tool,
                "args": args,
                "result_status": result.get("status", "unknown"),
            },
        )
        self._add_node(node)
        # Edge: PolicyDecision → Execution
        decision_node_id = f"decision:{proposal_id}"
        self._add_edge_between(decision_node_id, exec_id, "executed")
        return exec_id

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def trace(self, object_id: str) -> list[dict[str, Any]]:
        """
        Return the full ancestor chain for an object_id (event_id, proposal_id, etc.).

        Walks edges backwards from the given node to the root SemanticEvent,
        returning all nodes along the path in origin-first order.
        """
        target_node = self._id_to_node.get(object_id)
        if not target_node:
            return []

        # Build reverse adjacency: to_node → from_node
        reverse: dict[str, str] = {}
        for edge in self._edges:
            reverse[edge.to_node] = edge.from_node

        # Walk backwards
        chain_node_ids: list[str] = []
        current = target_node
        visited: set[str] = set()
        while current and current not in visited:
            chain_node_ids.append(current)
            visited.add(current)
            current = reverse.get(current)

        # Reverse so origin is first
        chain_node_ids.reverse()

        # Look up full node data
        node_by_id = {n.node_id: n for n in self._nodes}
        return [node_by_id[nid].to_dict() for nid in chain_node_ids if nid in node_by_id]

    def summary(self) -> dict[str, Any]:
        """Return a summary of the graph for reporting."""
        from collections import Counter
        type_counts = Counter(n.node_type for n in self._nodes)
        tainted = sum(1 for n in self._nodes if n.data.get("taint") is True)
        decisions = [n for n in self._nodes if n.node_type == NodeType.POLICY_DECISION]
        verdict_counts = Counter(n.data.get("verdict") for n in decisions)
        return {
            "session_id": self.session_id,
            "total_nodes": len(self._nodes),
            "total_edges": len(self._edges),
            "node_type_counts": dict(type_counts),
            "tainted_objects": tainted,
            "verdict_counts": dict(verdict_counts),
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str | Path) -> None:
        """
        Write the graph to a JSONL file (one JSON object per line).
        Nodes first, then edges, then a summary record.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for node in self._nodes:
                f.write(json.dumps({"type": "node", **node.to_dict()}) + "\n")
            for edge in self._edges:
                f.write(json.dumps({"type": "edge", **edge.to_dict()}) + "\n")
            f.write(json.dumps({"type": "summary", **self.summary()}) + "\n")

    @classmethod
    def load(cls, path: str | Path) -> "ProvenanceGraph":
        """Load a graph from a JSONL file written by save()."""
        path = Path(path)
        graph = cls()
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                rtype = record.pop("type", None)
                if rtype == "node":
                    node = ProvenanceNode(
                        node_id=record["node_id"],
                        node_type=record["node_type"],
                        timestamp=record["timestamp"],
                        data=record.get("data", {}),
                    )
                    graph._nodes.append(node)
                    # Restore ID index from data fields
                    for key in ("event_id", "proposal_id"):
                        val = record.get("data", {}).get(key)
                        if val:
                            graph._id_to_node[val] = record["node_id"]
                elif rtype == "edge":
                    edge = ProvenanceEdge(
                        edge_id=record["edge_id"],
                        from_node=record["from_node"],
                        to_node=record["to_node"],
                        relation=record["relation"],
                        timestamp=record["timestamp"],
                    )
                    graph._edges.append(edge)
        return graph
