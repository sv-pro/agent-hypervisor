# Contributing to Agent Hypervisor

Agent Hypervisor is an early-stage architectural concept and proof-of-concept implementation. At this stage, the most valuable contributions are conceptual feedback, implementation ideas, and documentation improvements.

---

## Ways to Contribute

### Providing Conceptual Feedback

If you have thoughts on the Agent Hypervisor approach — whether you agree, disagree, or see gaps — please open a [Discussion](https://github.com/sv-pro/agent-hypervisor/discussions). The most useful feedback addresses:

- Whether the ontological framing (existence vs. permission) holds up under real-world agent architectures
- Scenarios where the current model breaks or is insufficient
- Comparisons with approaches not covered in [VS_EXISTING_SOLUTIONS.md](docs/VS_EXISTING_SOLUTIONS.md)

### Reporting Bugs

Open an [Issue](https://github.com/sv-pro/agent-hypervisor/issues) using the **Bug Report** template. Include:

- Python version and OS
- Steps to reproduce
- Expected vs. actual output

### Suggesting Features

Open an [Issue](https://github.com/sv-pro/agent-hypervisor/issues) using the **Feature Request** template. Frame suggestions in terms of the architecture: which layer does this affect (Universe, Hypervisor, Physics Laws, Agent Interface)?

### Improving Documentation

Documentation PRs are welcome without prior discussion. The bar for acceptance is: is it accurate, and does it make the concept clearer?

### Code Contributions

For non-trivial code changes, please open an Issue or Discussion first to align on approach before writing code. This is a proof-of-concept codebase; the priority is clarity and educational value over features.

---

## Development Setup

**Requirements**: Python 3.8+

```bash
# Clone the repo
git clone https://github.com/sv-pro/agent-hypervisor.git
cd agent-hypervisor

# Install dependencies
pip install pyyaml pytest

# Run the demo
python3 demo_scenarios.py

# Run tests
pytest
```

---

## Running Tests

```bash
pytest
```

Tests live in `tests/`. Each test is self-contained and uses a fresh `Hypervisor` instance. Tests are also usage examples — reading them is a good way to understand the API.

---

## Code Style

- Follow [PEP 8](https://peps.python.org/pep-0008/)
- Add type hints to all function signatures
- Write docstrings that explain **why**, not just what
- Keep it minimal: this is a proof-of-concept, not a framework
- Every safety property should be expressible as a deterministic unit test

---

## Core Design Principles

When contributing code, keep these in mind:

1. **Deterministic**: No LLM calls or probabilistic logic in the critical evaluation path
2. **Educational**: Code should teach the concept to someone reading it for the first time
3. **Testable**: Every decision the Hypervisor makes should be reproducible in a unit test
4. **Minimal**: Resist adding abstractions that aren't needed for the current proof-of-concept

---

## Questions?

Start a [Discussion](https://github.com/sv-pro/agent-hypervisor/discussions) — we're interested in hearing from security researchers, agent framework developers, and anyone working on the AI safety problem.
