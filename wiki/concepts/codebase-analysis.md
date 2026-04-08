# Codebase Structure: `src/core` vs `src/agent_hypervisor`

The repository splits the Agent Hypervisor implementation into two distinct architectural directories: the minimal reference implementation (`src/core`) and the comprehensive runtime package (`src/agent_hypervisor`).

## Summary of `src/core`
The `src/core` directory is the pure, dependency-free distillation of the Agent Hypervisor security philosophy.

- **Purpose**: It serves as the ultimate [Manifest Resolution](../concepts/manifest-resolution.md) engine. 
- **Implementation**: It is mathematically isolated, containing no external dependencies, no LLM integrations, and no physical sandbox execution code. 
- **Core Components**: Within `src/core/hypervisor.py`, it implements `TrustLevel`, `ProvenanceRecord`, `WorldManifest`, and the `ManifestResolver`.
- **Design Intent**: Modeled as a portable "specification in code." Because it lacks Python-specific dependencies, it serves as the reference blueprint that could be natively ported to Rust, Go, or TypeScript to operate at a lower systemic level.

## Summary of `src/agent_hypervisor`
The `src/agent_hypervisor` directory is the heavyweight, feature-complete Python framework that bridges the pure logic of the hypervisor with the physical reality of software execution.

- **Purpose**: It provides the execution runtime, proxy gateways, and full tooling necessary to drop an Agent Hypervisor over an active application.
- **Implementation**: It is a modular Python package containing several specialized sub-components:
  - **`hypervisor/gateway/`**: Execution routers and proxy layers to intercept LLM actions (e.g., Anthropic / OpenAI tool calls).
  - **`runtime/` & `program_layer/`**: Physical execution sandboxes, workflow compilers, and execution planners that interface with the host OS and environment.
  - **`semantic_compiler/`**: The tooling required to implement [AI Aikido](../concepts/ai-aikido.md)—using design-time LLM power to freeze boundaries into YAML matrices.
  - **`economic/`**: Integrations for token tracking, pricing profiles, and economic constraints.
- **Design Intent**: This is the practical integration codebase representing the physical layer of the [Four-Layer Architecture](../concepts/architecture.md), bringing the theoretical concepts to life on real hardware.

---

## Synthesis: Common Ground and Key Differences

### What's Common
Both codebases exist to enforce the same ontological physics: **they reject the permission paradigm in favor of verifiable capability projection.** Both systems share the fundamental vocabulary of the project (e.g., returning `Decision.ALLOW`, `DENY`, or `ASK`), rely heavily on rigorous provenance lineage (taint tracking), and prevent cross-boundary infection.

### What's Different
The distinction lies entirely in **abstraction versus execution**.

`src/core` is the mathematical brain—it evaluates an action strictly on paper without any capacity to actually execute it. It asks: *"Does this proposed event violate the World Manifest?"*

`src/agent_hypervisor` is the physical body—it compiles the world manifest, intercepts network requests, blocks actual process boundaries, and runs physical sandboxes. It enforces the brain's answer in the live systems environment.
