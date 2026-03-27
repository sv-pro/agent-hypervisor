# Q&A Prep

## 1. Is this just another policy engine?

It is a policy engine, but with a specific trace-driven workflow for deriving bounded execution worlds from observed agent behavior.

## 2. Are you solving prompt injection?

No. The claim is narrower: some harmful execution paths become unavailable by construction.

## 3. Are capability profiles automatically correct?

No. They are drafts derived from traces and should be reviewed by humans.

## 4. Why not rely on approvals only?

Because repeated approvals lead to scope creep and permission fatigue.

## 5. Why is deterministic enforcement important?

Because identical input and identical manifest should produce identical decisions.

## 6. Is this production-ready?

No. This PoC demonstrates feasibility, not a finished platform.

## 7. What does the manifest represent?

A declarative description of what actions, resources, and trust conditions exist in the agent’s world.

## 8. What is the human role?

Humans review profiles and manifests at design time instead of being placed in every runtime decision.

## 9. Does this require MCP?

No. MCP is one motivating tool boundary, not a hard dependency of the architecture.

## 10. What is blocked in the PoC?

Secret access, tainted-data exfiltration, out-of-scope remote operations, and trust-violating shell execution.

## 11. What is still weak in the PoC?

Profile derivation is simple, manifest minimization is rough, and taint semantics are intentionally limited.

## 12. What is the next research step?

Stabilize recurring execution modes across multiple benign traces and improve manifest precision.
