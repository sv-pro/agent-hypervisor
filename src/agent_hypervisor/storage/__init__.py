"""
storage — Lightweight persistence layer for the Agent Hypervisor gateway.

Three stores handle the three kinds of durable state:

  TraceStore    — append-only JSONL audit log of every tool evaluation
  ApprovalStore — directory-based store for mutable approval records
  PolicyStore   — append-only JSONL version history for policy reloads

All stores are designed to be:
  • file-based (no external database required)
  • deterministic and testable with temporary directories
  • minimal — no ORM, no migrations
"""

from .approval_store import ApprovalStore
from .policy_store import PolicyStore
from .trace_store import TraceStore

__all__ = ["TraceStore", "ApprovalStore", "PolicyStore"]
