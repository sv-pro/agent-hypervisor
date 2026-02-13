# Contributing to Agent Hypervisor

Thank you for your interest. Agent Hypervisor is an early-stage proof-of-concept exploring an architectural approach to AI agent security. At this stage, **conceptual feedback is the most valuable contribution**.

---

## Types of Contributions Welcome

### 1. Conceptual Feedback (Most Valuable Now)

- Is the "reality virtualization" abstraction compelling?
- Are there fundamental flaws in the approach?
- What attack vectors does this not address?
- How does this compare to your security approach?

Open a [Discussion](https://github.com/sv-pro/agent-hypervisor/discussions).

### 2. Documentation Improvements

- Clarifications to existing docs
- Additional examples or analogies
- Better diagrams
- Typo fixes

Open a [Pull Request](https://github.com/sv-pro/agent-hypervisor/pulls).

### 3. Code Examples

- Integration with agent frameworks (LangChain, LangGraph, raw API)
- Additional demo scenarios
- Physics law implementations

Add to the `examples/` directory via Pull Request.

### 4. Real-World Use Cases

- "I would use this for..."
- "This would solve my problem with..."
- "This doesn't address..."

Open an [Issue](https://github.com/sv-pro/agent-hypervisor/issues) with the `use-case` label.

---

## What We're NOT Looking For (Yet)

- ❌ Production-readiness improvements (it's a PoC)
- ❌ Enterprise feature requests
- ❌ Performance optimizations

Focus now is on **validating the architectural approach**.

---

## Development Setup

```bash
git clone https://github.com/sv-pro/agent-hypervisor.git
cd agent-hypervisor
pip install pyyaml pytest
pytest          # Run tests
python3 demo_scenarios.py  # Run demo
```

---

## Code Style

- Python 3.8+, type hints on all public APIs
- Docstrings that explain **why**, not just what
- Every safety property must be expressible as a deterministic unit test
- Keep it minimal — this is a PoC, not a framework

---

## Core Design Principles

When contributing code, keep these in mind:

1. **Deterministic** — no LLM calls or probabilistic logic in the evaluation path
2. **Educational** — code should teach the concept to a new reader
3. **Testable** — every Hypervisor decision must be reproducible in a unit test
4. **Minimal** — resist abstractions not needed for the current proof-of-concept

---

## Questions?

Start a [Discussion](https://github.com/sv-pro/agent-hypervisor/discussions).
