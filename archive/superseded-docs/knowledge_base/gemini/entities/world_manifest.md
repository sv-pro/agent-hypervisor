# World Manifest

**Status:** `[DESIGN/PLANNING]`

## Definition
The World Manifest is a formal, structured document (intended to be YAML or DSL) defining everything that exists in the agent's virtualized universe. It is intended to be the source format that is compiled into the physical laws of the agent's world.

## Conceptual Structure
The architectural documents specify that the manifest should include:
- **Action Ontology:** The complete set of typed schemas for actions the agent can propose.
- **Trust Model:** Rules defining the trust levels of incoming channels and how they propagate.
- **Capability Matrix:** Rules establishing what capabilities are possible at different trust levels.
- **Taint Propagation Rules:** How contamination spreads through data transformations.
- **Escalation Conditions:** Cases where the agent's intent requires human review.
- **Provenance Schema:** Rules for how metadata regarding an object's origin follows it.

## Code Reality
While `src/hypervisor.py` uses a simple `policy.yaml` file to enforce physical laws, it is highly simplified compared to the full World Manifest concept. The current `policy.yaml` structure only supports `forbidden_patterns`, `allowed_tools`, and `max_files_opened`. The full World Manifest Compiler has not been built yet.
