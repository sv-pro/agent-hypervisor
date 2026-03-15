# Agent Hypervisor Examples

Runnable demonstrations of Agent Hypervisor concepts.

---

## Directory Structure

### [basic/](basic/) — Core Demonstrations

Simple examples showing fundamental hypervisor functionality.

**Start here** if you are new to Agent Hypervisor.

### [workarounds/](workarounds/) — Practical Workarounds

Tactical security patterns you can implement TODAY while Agent Hypervisor matures.

**Use these** if you need immediate security improvements in existing systems.

### [integrations/](integrations/) — Framework Integrations

Examples integrating Agent Hypervisor concepts with popular agent frameworks.

**Reference these** if you are using LangChain, the OpenAI API, or other frameworks.

---

## Quick Start

```bash
# Run basic demonstration
python examples/basic/01_simple_demo.py

# Try a workaround
python examples/workarounds/01_input_classification.py
```

---

## Complexity Levels

| Level | Directory | Time to Understand |
| --- | --- | --- |
| Beginner | basic/ | 10 minutes |
| Intermediate | workarounds/ | 15 minutes per pattern |
| Advanced | integrations/ | 20 minutes |

---

## Learning Path

1. Read [docs/CONCEPT.md](../docs/CONCEPT.md)
2. Run `examples/basic/01_simple_demo.py`
3. Review `examples/workarounds/README.md`
4. Check `examples/integrations/` for your framework

### [provenance_firewall/](provenance_firewall/) — Provenance-Aware Tool Execution Firewall

A runnable MVP demonstrating the core Agent Hypervisor security idea: a provenance-aware firewall that sits between an agent and its tools, blocking dangerous tool calls when their arguments originate from untrusted data sources.

**Run this** to see prompt injection blocked at the enforcement boundary rather than the model layer.

```bash
python examples/provenance_firewall/demo.py
```

Three modes are demonstrated:

| Mode | Description | Verdict |
| --- | --- | --- |
| A — Unprotected | Agent reads malicious doc, proposes send to `attacker@example.com` | ALLOW (baseline) |
| B — Protected | Same scenario with firewall on | DENY (external_document provenance) |
| C — Trusted source | Agent uses declared contacts file as recipient source | ASK (clean chain, confirmation required) |

See [provenance_firewall/README.md](provenance_firewall/README.md) for full details.

---

## Contributing Examples

See [CONTRIBUTING.md](../CONTRIBUTING.md). Most valuable contributions:

- Real-world use cases
- Framework integrations
- Additional workaround patterns
