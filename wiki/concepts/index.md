# Concepts Index

This directory curates synthesized concepts detailing the fundamental logic, philosophy, and mechanics underpinning Agent Hypervisor. 

## Summaries

- **[Architecture](architecture.md)**: Details the Four-Layer Model (Execution Physics, Base Ontology, Dynamic Ontology Projection, Execution Governance).
  - *Reference sources*: [`WHITEPAPER.md`](../../WHITEPAPER.md), [`src/core/hypervisor.py`](../../src/core/hypervisor.py)

- **[AI Aikido](ai-aikido.md)**: The structural principle representing how LLMs are deployed at design-time to construct execution-time physics, isolating stochastic generation from the boundary execution.
  - *Reference sources*: [`WHITEPAPER.md`](../../WHITEPAPER.md)

- **[World Manifest](world-manifest.md)**: Defines the constitution and constraints an agent operates within.
  - *Reference sources*: [`GLOSSARY.md`](../../GLOSSARY.md), [`src/core/hypervisor.py: WorldManifest`](../../src/core/hypervisor.py)

- **[Trust and Taint](trust-and-taint.md)**: Structural mapping that dictates how data is assigned a trust level, and how its taint cascades across processes and sessions to prevent leakage.
  - *Reference sources*: [`GLOSSARY.md`](../../GLOSSARY.md), [`src/core/hypervisor.py: TrustLevel`](../../src/core/hypervisor.py)

- **[Manifest Resolution](manifest-resolution.md)**: The deterministic outcome law determining if a proposed action will be Allowed, Denied, or subjected to an Ask mechanism requiring human approval.
  - *Reference sources*: [`GLOSSARY.md`](../../GLOSSARY.md), [`src/core/hypervisor.py: ResolutionResult`](../../src/core/hypervisor.py)
