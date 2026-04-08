# World Manifest

**Source:** `GLOSSARY.md`, `WHITEPAPER.md`

The **World Manifest** is the formal specification of everything that exists in the agent's universe. It acts as a constitution rather than a simple configuration file. 

## Structure
A World Manifest compiles LLM and human intent into deterministic runtime artifacts. It defines:

1. **Base Ontology (Layer 1)**: Action definitions, schemas, and parameters that can ever exist. Actions outside this definition cannot be proposed.
2. **Trust Channels (Layer 1 & 3)**: Declarations mapping inputs (user, email, memory) to specific [Trust Levels](trust-and-taint.md) (trusted, untrusted, derived).
3. **Capabilities Matrix (Layer 2)**: Which permissions (capabilities like `read`, `memory_write`, `external_side_effects`) are granted to which trust levels.
4. **Taint Rules and Invariants (Layer 3)**: The logic defining how data contamination spreads locally, how provenance requirements are laid out, and physics-law non-overridable rules (like the `TaintContainmentLaw`).

## World Manifest Compiler
At design-time (employing [AI Aikido](ai-aikido.md)), the World Manifest is drafted, reviewed, and passed through the **World Manifest Compiler**. 

The Compiler removes any reliance on runtime LLM judgments by transforming the Manifest into strictly static artifacts:
- JSON Schema validators (L1)
- Capability projection tables (L2)
- Taint propagation matrices and escalation threshold evaluators (L3)

The runtime environment is purely deterministic boundary enforcement based on these compiled structures.
