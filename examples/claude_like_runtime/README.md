# Claude-Like Runtime Demo: Rendering The Agent's Reality

This demo implements a core concept from the Agent Hypervisor: **Advertising tools is rendering the agent's reality.**

Rather than framing tool restrictions as "security policies" that deny access, this architecture demonstrates **ontological absence**. If a tool isn't advertised to the model, it simply does not exist in its rendered world.

## The Concept

We provide the identical prompt to the model across three distinct running contexts (worlds):

1. **`raw_world`**: The broad tool surface. The agent can modify files and execute real git commands.
2. **`rendered_world`**: A restricted tool surface (read-only). The push capabilities do not exist.
3. **`simulate_world`**: The restricted surface, but with a simulated side-effect tool (`git_push_simulated`) injected into reality.

When the agent attempts an action that isn't part of its current world ontology, the runtime proxy intercepts it. Instead of returning a "Permisson Denied" error, it responds with: `"Tool does not exist in current world"`. This underscores that the tool is ontologically missing, not blocked by an authority.

## Structure

- `world/*.yaml`: Manifests defining the ontology for each reality.
- `runtime/`: Components for loading manifests, switching worlds, and auditing actions.
- `tools/`: Implementations of real and simulated tools, along with the `proxy.py` that enforces reality.
- `scenarios/`: The common task provided to the agent.
- `main.py`: The entrypoint that runs the evaluation loop.

## Running the Demo

You need the `anthropic` Python package installed and an API key:

```bash
export ANTHROPIC_API_KEY="your-api-key"
python examples/claude_like_runtime/main.py
```

### Expected Output

- In the `raw_world`, Claude will attempt to interact with the repository and run real `git` commands.
- In the `rendered_world`, Claude will realize it lacks the required tools, attempting only read operations or reporting completion based on its limited capabilities.
- In the `simulate_world`, Claude will "push" its changes using the simulated tool, believing it has fully completed the task within the reality it was presented.
