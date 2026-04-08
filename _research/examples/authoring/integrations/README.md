# Integration Examples

Examples integrating Agent Hypervisor concepts with popular agent frameworks.

---

## Planned Integrations

### LangChain

Wrap a LangChain agent so all tool calls are mediated by the Hypervisor before execution.
Demonstrates how to intercept `AgentAction` events and evaluate them as Intent Proposals.

### OpenAI Function Calling

Intercept OpenAI function-call responses before executing them — evaluate each proposed
function call against the World Policy.

### Raw API

Minimal integration without any framework dependency, suitable as a reference implementation
for other frameworks.

---

## Status

These integration examples are **planned but not yet implemented**.

If you have built an integration with a specific framework, contributions are welcome.
See [CONTRIBUTING.md](../../CONTRIBUTING.md).

---

## Design Principle

All integrations follow the same pattern:

```text
Framework Agent → proposes tool call
                ↓
        Agent Hypervisor.evaluate(intent)
                ↓
        ALLOWED → execute via framework
        BLOCKED → return error to agent
```

The Hypervisor sits between the agent's decision and execution — not inside the framework,
and not as a post-hoc filter on results.
