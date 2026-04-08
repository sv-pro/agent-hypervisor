# Trust, Taint, and Provenance

**Source:** `GLOSSARY.md`

Within Agent Hypervisor, the concepts of Trust, Taint, and Provenance mathematically track data as it enters, morphs, and leaves the agent.

## Trust Level
A property of an input channel, not the content.
The [World Manifest](world-manifest.md) defines trust levels per source (e.g. User = `trusted`, Email = `untrusted`).
A `derived` trust level means the data inherits its context from the provenance chain associated with it (e.g. loading memory).

## Taint
Taint is a property of data indicating it originated from an untrusted source, either directly or transitively. It is not an arbitrary label the agent can just wipe away—it persists and spreads structurally as operations occur on the data. [Layer 3 Governance](architecture.md) enforces exactly how taint propagates via static matrices. 

Under the non-overridable `TaintContainmentLaw`, tainted data is strictly forbidden from triggering actions with the `external_side_effects` capability.

## Provenance Chain
The absolute lineage of a data object. Tracking provenance guarantees that the taint metadata survives session boundaries.
A provenance chain records:
- The original source.
- Trust level at origin.
- Every transformation applied.
- All sessions crossed.

Every `memory_write` action requires the storage device to ingest the provenance chain alongside the block data. This entirely stops memory poisoning attacks like [ZombieAgent](../scenarios/zombie-agent.md), as malicious persistent payloads resurface with an unshakeable trace of their original untrusted nature.
