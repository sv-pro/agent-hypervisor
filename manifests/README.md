# World Manifests

This directory contains World Manifest files for the Agent Hypervisor.

A World Manifest is a YAML document authored at design-time that defines what exists in an agent's universe: which tools are available, which trust levels apply to input channels, how taint propagates, and what requires human approval before execution.

The manifest is compiled by `ahc build` (M2) into deterministic runtime artifacts. No LLM is involved at runtime.

---

## Files

| File | Purpose |
|---|---|
| [`schema.yaml`](schema.yaml) | Annotated reference schema — all fields documented inline. Start here. |
| [`examples/email-safe-assistant.yaml`](examples/email-safe-assistant.yaml) | Email assistant hardened against prompt injection from email content. |
| [`examples/mcp-gateway-demo.yaml`](examples/mcp-gateway-demo.yaml) | MCP-connected agent with file system, web fetch, and code runner tools. |
| [`examples/browser-agent-demo.yaml`](examples/browser-agent-demo.yaml) | Web browsing agent hardened against page-injected instructions and unauthorized form submission. |

---

## Security properties covered by the examples

| Scenario | Prompt injection | Tainted egress | Tool abuse | MCP injection |
|---|---|---|---|---|
| email-safe-assistant | ✅ | ✅ | ✅ | — |
| mcp-gateway-demo | ✅ | ✅ | ✅ | ✅ |
| browser-agent-demo | ✅ | ✅ | ✅ | — |

---

## How to write a manifest

1. Copy `schema.yaml` and remove the annotation comments.
2. Fill in the `manifest`, `actions`, `trust_channels`, `capability_matrix`, `taint_rules`, `escalation_conditions`, `provenance_schema`, and `budgets` sections.
3. Review: every action that is irreversible should have an escalation condition. Every untrusted channel should have taint rules covering all likely operations.
4. Run `ahc build your-manifest.yaml` (M2, not yet implemented) to compile to runtime artifacts.

See [docs/GLOSSARY.md](../docs/GLOSSARY.md) for term definitions and [ARCHITECTURE.md](../docs/ARCHITECTURE.md) for the compilation path.
