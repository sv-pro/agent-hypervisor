# Implemented Physics

**Status:** `[IMPLEMENTED]`

## Overview
The Agent Hypervisor acts as the fundamental boundary layer preventing the virtualized agent from acting erroneously. Within the `src/hypervisor.py` proof of concept (POC), three basic physical laws constrain the universe's ontology. 

## The Physics Layers
1. **Forbidden Patterns (`Physics Layer 1`):** 
   A rudimentary deny-list targeting the intent's `args`. If the args contain any string mapped within `forbidden_patterns` inside the `policy.yaml` configuration (e.g., `rm -rf`), the intent simply throws a `BLOCKED` status. It is considered a dangerous fallback net, but an essential component of the POC constraints.
2. **Tool Whitelist (`Physics Layer 2`):**
   Tools explicitly listed in `allowed_tools` define the scope of the world. Only tools explicitly mapped can run; intents targeting tools not inside the configuration represent ontological impossibilities and are subsequently rejected as conceptually non-existent.
3. **State Limits (`Physics Layer 3`):**
   The Hypervisor accumulates metrics tracking state anomalies across execution bounds. Currently, an action constraint tracks how many `read_file` intents have been requested during the active session. The hard limit is defined by the configuration integer `max_files_opened`. Further intents reaching the boundary threshold are `BLOCKED`.
