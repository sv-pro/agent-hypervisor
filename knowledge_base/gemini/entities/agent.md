# Agent

**Status:** `[IMPLEMENTED]` (Minimal Stub)

## Definition
In the Agent Hypervisor architecture, an agent does not interact with the world directly. Instead, it receives virtualized information (Semantic Events) and proposes actions (Intent Proposals).

## Implementation (`src/agent_stub.py`)
The codebase provides a simple stand-in for an AI agent, `AgentStub`. 
- **Role:** Simulates the proposal mechanism without requiring a real LLM framework. 
- **Mechanism:** It constructs and returns an intent dict (containing the fields `agent`, `tool`, and `args`) which serves as input to the `Hypervisor.evaluate()`.
- **Knowledge:** The agent is deliberately unaware of the specific physical laws / policy evaluated by the Hypervisor. It reasons about goals, not permissions.

**Future Vision (`[DESIGN/PLANNING]`):**
A fully functional agent implementation would replace the stub, using tools like LangChain or raw LLM APIs to generate reasoning and subsequently output Intent Proposals based on Semantic Events.
