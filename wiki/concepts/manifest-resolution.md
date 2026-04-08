# Manifest Resolution Law

**Source:** `GLOSSARY.md`, `WHITEPAPER.md`

The Manifest Resolution Law is the operational core of Agent Hypervisor's Layer 3 Execution Governance. Because an agent never directly accesses tools, it can only submit a **Proposed Action** (an intent) for resolution against the [World Manifest](world-manifest.md).

## Resolution Process
Evaluation is utterly deterministic (No LLMs) and yields strictly one of three outcomes:

1. **ALLOW:** The proposed action is explicitly permitted for the current trust level, and it triggers no invariant violations. The action executes immediately.
2. **DENY:** The proposed action is explicitly denied, or it triggers an invariant violation (like the `TaintContainmentLaw` acting on derived output), or it's simply unrepresented in a background execution mode.
3. **ASK:** The proposed action does not violate an invariant, but lacks explicitly pre-compiled permissions in the manifest. When in Interactive Mode, it prompts the Human-in-the-Loop.

## Execution Modes
- **Background Execution Mode:** Operates autonomously. Fallback for unrepresented behaviors is always `DENY`.
- **Interactive Execution Mode:** An agent runs but intercepts `ASK` prompts. A human user views the full provenance chain and agent logic to either grant a localized one-shot execution or formal **Manifest Extension**.
- **Workflow Definition Mode:** Design-time development mode focused extensively on manifest extensions.
