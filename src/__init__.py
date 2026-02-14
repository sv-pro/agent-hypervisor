"""
Agent Hypervisor - Deterministic Security for AI Agents

Virtualizes reality for AI agents, preventing entire classes of attacks
through architectural design rather than probabilistic filtering.
"""

__version__ = "0.1.0"

from .hypervisor import Hypervisor
from .agent_stub import AgentStub as Agent

__all__ = ["Hypervisor", "Agent"]