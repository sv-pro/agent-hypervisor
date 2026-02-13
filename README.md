# Agent Hypervisor: Hello World

> **Architectural Concept**: This is a minimal reference implementation of the [Agent Hypervisor](CONCEPT.md) pattern. It is not a product or a framework.

## Overview

This "Hello World" project demonstrates the core mechanism: **Intercepting agent intentions and enforcing a deterministic policy.**

The demo consists of:
- **`Agent`**: A stub that proposes actions (Intents).
- **`Hypervisor`**: The engine that evaluates these intents against the World Policy.
- **`Policy`**: A YAML file defining what is allowed in this virtual world.

## Usages

### Prerequisites
- Python 3.8+
- `pyyaml`

```bash
pip install pyyaml
```

### Run the Demo
The simulation runs through a series of safe, unsafe, and state-dependent scenarios.

```bash
python3 demo_scenarios.py
```

### Run Tests
Verify the deterministic nature of the hypervisor.

```bash
pytest
```

## Structure
- `CONCEPT.md`: The philosophical and architectural definition.
- `policy.yaml`: The "Laws of Physics" for this demo world.
- `hypervisor.py`: The code that enforces the policy.
- `agent_stub.py`: A simple agent loop.
