# Hypervisor

**Status:** `[IMPLEMENTED]` (Minimal Proof-of-Concept)

## Definition
The Agent Hypervisor is a deterministic boundary layer that virtualizes the semantic reality of an AI agent. It is designed to evaluate an agent's proposed intents against a "World Policy" — a set of physical laws defining what actions exist in the agent's universe.

## Implementation (`src/hypervisor.py`)
In the codebase, the `Hypervisor` class represents the core engine. It loads a YAML policy file and evaluates an agent's intent proposal deterministically. 

**Core Responsibilities:**
- Apply a global deny list of forbidden patterns (e.g., preventing any command with "rm -rf").
- Enforce a tool whitelist (if a tool is not in the whitelist, it ontologically "does not exist").
- Track cumulative state constraints across a session (e.g., maximum number of files opened).

**Future Vision (`[DESIGN/PLANNING]`):**
The architectural specification envisions the Hypervisor as a much more complex "World Manifest Compiler" that handles deep semantic context, taint propagation, and data provenance. These advanced features are not yet implemented in the Python POC.
