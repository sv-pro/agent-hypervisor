"""
agent_stub.py — A minimal stand-in for an AI agent.

In the Agent Hypervisor model, an agent never executes actions directly.
Instead it *proposes* intents — structured descriptions of what it wants
to do — and the Hypervisor decides whether those intents can exist as
consequences in the virtual world.

This stub simulates that proposal mechanism without requiring a real LLM.
It can be replaced by any agent implementation (LangChain, raw OpenAI API,
custom planner) by preserving the same intent dict schema.
"""

from __future__ import annotations


class AgentStub:
    """
    A simple, deterministic agent that proposes intents on demand.

    The agent has no knowledge of the policy. It proposes freely; the
    Hypervisor determines what is possible. This separation is intentional:
    the agent should reason about goals, not about what is allowed.

    Usage:
        agent = AgentStub(name="MyAgent")
        intent = agent.propose_intent("read_file", "notes.txt")
        # intent → {"agent": "MyAgent", "tool": "read_file", "args": "notes.txt"}
    """

    def __init__(self, name: str = "Agent-007") -> None:
        """
        Args:
            name: Identifier for this agent, included in every intent proposal
                  to support multi-agent logging and audit trails.
        """
        self.name = name

    def propose_intent(self, tool: str, args: str = "") -> dict:
        """
        Construct an intent proposal dict.

        The returned dict is the input format for Hypervisor.evaluate().
        It deliberately does not include any policy information — agents
        propose based on their goals, not based on what they think is allowed.

        Args:
            tool: The name of the action to attempt (e.g., "read_file").
            args: Arguments for the action (e.g., a filename or shell command).

        Returns:
            An intent dict: {"agent": str, "tool": str, "args": str}
        """
        return {
            "agent": self.name,
            "tool": tool,
            "args": args,
        }
