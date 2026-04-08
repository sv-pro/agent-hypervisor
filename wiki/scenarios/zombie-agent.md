# ZombieAgent Scenario

**Source**: `scenarios/zombie-agent/SCENARIO.md`, `scenarios/zombie-agent/manifest.yaml`

The **ZombieAgent** scenario demonstrates a multi-step, cross-session attack (originally referenced in Radware research, January 2026) where an agent's persistent memory is poisoned with malicious instructions. This subversion turns the agent into a persistent threat actor.

This scenario serves as the primary proof-of-concept for the Agent Hypervisor architecture.

## The Unmitigated Attack Chain
Without an Agent Hypervisor, the attack flows like this:
1. **Session 1**: An agent processes an untrusted email containing a hidden instruction (e.g., "forward data to attacker").
2. The agent unknowingly writes this rule or derived conclusion to its persistent memory without tracking its origin.
3. **Session 2**: In a future session, the agent loads this memory. Because it was loaded from its own memory bank, the agent treats it as a trusted context.
4. The agent executes the attack payload using a legitimate tool (e.g., `send_email`), bypassing standard behavioral detection heuristics.

## The Agent Hypervisor Defense
The Agent Hypervisor completely breaks this attack through "World Physics" dictated by the Manifest Resolution Law. It intercepts the attack at three structural boundaries:

1. **Input Virtualization**: Raw inputs are wrapped into Semantic Events carrying a strict `trust_level` attribute (e.g., `untrusted`). If the agent immediately attempts a high-privilege action like `send_email`, the Hypervisor deterministically denies it via the `CapabilityBoundaryLaw` because `untrusted` sources lack the `external_side_effects` capability.
2. **Provenance-Gated Memory Write**: If the agent attempts to save a derived conclusion into persistent memory, that data carries a `tainted: true` property derived from its untrusted origin. The `ProvenanceLaw` intercepts the write attempt. In background mode, the write is explicitly **DENIED**. In interactive mode, an **ASK** dialog is triggered, placing a human in the loop to either approve a one-shot write or permanently extend the manifest.
3. **Cross-Session Taint Propagation**: Assuming a user approves writing the tainted data, the memory record preserves the `taint: true` metadata. When that memory is read in Session 2, the newly loaded context inherits the taint. Any subsequent action (like `send_email`) triggered by this tainted memory is caught by the `TaintContainmentLaw` and blocked.

The resolution relies on a strict, design-time **World Manifest** rather than placing an LLM on the execution critical path (unlike CaMeL), making the defense highly deterministic and mathematically measurable.
