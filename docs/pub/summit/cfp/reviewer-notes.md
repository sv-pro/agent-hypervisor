# Reviewer Notes

This talk fits the secure-by-design track because it focuses on practical controls for designing and operating safer agentic systems, not abstract risk discussion alone.

It also aligns with current concerns around scope creep, least privilege, policy-as-code, runtime controls, and entitlement review, but presents them as one coherent architectural workflow rather than a checklist of isolated mitigations.

The session is grounded in a working PoC and makes a bounded claim: observed execution can be compiled into deterministic runtime boundaries for specific agent workflows, not that semantic safety or agent intent is solved in general.

The PoC already demonstrates:

- Observe -> Profile -> Manifest -> Enforce
- deterministic `ALLOW`, `DENY`, and `REQUIRE_APPROVAL` outcomes
- benign workflow support
- policy denial of unsafe exfiltration and over-scoped actions
