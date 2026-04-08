# AI Aikido

**Status:** `[DESIGN/PLANNING]`

## Definition
AI Aikido is a core design philosophy described in the Agent Hypervisor documentation. It is the practice of leveraging the stochastic intelligence of Large Language Models (LLMs) to create deterministic artifacts, which are then relied on at runtime.

## Concept
Rather than attempting to make stochastic decision-making safe at runtime via behavioral guardrails, AI Aikido uses the LLM to write the "physics engine" of the agent's universe before the agent ever executes. 

**Analogy:** The LLM's stochastic intelligence builds the deterministic cage in which the agents subsequently operate. Intelligence designs the physical laws, but it does not govern those laws at runtime.

## Application Examples
1. **Parser Generation:**
   An LLM is used to generate strict regular expressions and JSON Schema validators based on analyzing real-world inputs and edge cases.
2. **Automated World Manifest Creation:**
   An LLM translates a human business description into explicit capabilities, physics rules, and taint propagation tables inside a World Manifest.
3. **Context-Aware Taint Rules:**
   An LLM reads data logic flow and identifies exactly which data transitions preserve taint, and which clear it.

All these rules and scripts are compiled down into purely deterministic logic executed at runtime, making them mathematically verifiable and completely deterministic. This system solves the paradox of relying on AI to protect AI.
