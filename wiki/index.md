# Agent Hypervisor Wiki

This is the curated, content-oriented catalog of the Agent Hypervisor knowledge base, reflecting the structural divide between the finalized canonical concepts, and the iterative "messy" research lab.

## Core Concepts & Architecture (Canonical)
- [Four-Layer Architecture](concepts/architecture.md) - Overview of the absolute boundaries comprising the hypervisor.
- [World Manifest](concepts/world-manifest.md) - The constitution dictating an agent's physics.
- [AI Aikido](concepts/ai-aikido.md) - Deploying stochastic systems at design-time to fabricate deterministic security.
- [Trust, Taint, and Provenance](concepts/trust-and-taint.md) - Mechanisms evaluating structured execution input mapping.
- [Manifest Resolution Law](concepts/manifest-resolution.md) - Real-time deterministic law dictating whether an action is Allow / Deny / Ask.

## Comparisons (Canonical)
- [Agent Hypervisor vs. CaMeL](comparisons/agent-hypervisor-vs-camel.md) - Delineating exactly how the architecture maps execution time against other LLM-boundary defense protocols.

## Scenarios (Canonical)
- [ZombieAgent](scenarios/zombie-agent.md) - Deep dive into neutralizing cross-session persistent memory poisoning.

## Code Documentation (Canonical)

### Packages
- [Code Index](code/index.md) - Package map, module index, and recurring architectural patterns
- [agent_hypervisor](code/agent_hypervisor.md) - Top-level public API: re-exported firewall models and sub-package map
- [runtime](code/runtime.md) - Layer 3 Execution Governance kernel: IRBuilder, taint, compile, channel, proxy, executor
- [compiler](code/compiler.md) - Layer 1 Base Ontology: manifest → deterministic policy artifacts; awc/ahc CLI
- [authoring](code/authoring.md) - Layer 2 Dynamic Ontology: Capability DSL, World presets, MCP integration
- [hypervisor](code/hypervisor.md) - PoC Gateway: HTTP server, ProvenanceFirewall, PolicyEngine, provenance graph
- [economic](code/economic.md) - Economic constraints: budget enforcement, cost estimation, pricing registry
- [program_layer](code/program_layer.md) - Optional execution abstraction: sandbox runtime, program executor
- [core](code/core.md) - Portable reference implementation: ManifestResolver, WorldManifest, invariants

### Module Deep-Dives
- [IR & IRBuilder](code/modules/ir.md) - Sealed execution intent; construction-time enforcement; ConstructionError hierarchy
- [Taint Engine](code/modules/taint.md) - Monotonic taint propagation; TaintedValue; TaintContext threading
- [Compile Phase](code/modules/compile.md) - compile_world() → CompiledPolicy; sealing; O(1) capability matrix
- [Channel & Source](code/modules/channel.md) - Sealed trust derivation; fail-closed defaults; trust from policy not caller
- [SafeMCPProxy](code/modules/proxy.md) - In-path MCP enforcement; single gateway; typed denial kinds
- [Executor](code/modules/executor.md) - Subprocess transport; worker boundary; SimulationExecutor
- [ProvenanceFirewall](code/modules/firewall.md) - Structural provenance rules; RULE-01 through RULE-05; ValueRef model
- [AH MCP Gateway](code/modules/mcp_gateway.md) - JSON-RPC 2.0 MCP gateway; manifest-driven tool visibility; 4-stage deterministic enforcement; SSE transport
- [Core Hypervisor](code/modules/core_hypervisor.md) - Reference ManifestResolver; physics laws; input virtualization

---

## The Lab & Archives
- [Research Index](_research/index.md) - Entering the `_research` space. Access prototyping reports, legacy tests, and working DSPy experiments. You can navigate here to evaluate working concepts for later promotion to canonical context.
