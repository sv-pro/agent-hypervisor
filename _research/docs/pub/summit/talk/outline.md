# Talk Outline

## 1. Why current agent defenses break (4 min)

- Agentic systems expand the attack surface beyond prompts into tools, orchestration, and external side effects.
- Many defenses still act after dangerous input has already entered the reasoning loop.
- The result is reactive control over an already overpowered agent.

## 2. Scope creep as the practical failure mode (4 min)

- Repeated approvals and task variability gradually widen agent permissions.
- The gap grows between intended behavior and actual runtime power.
- This is an operational symptom teams can observe and measure.

## 3. The runtime-to-design bridge (5 min)

- Start from observed execution rather than a perfect up-front policy.
- Reduce traces into bounded capability profiles.
- Use those profiles as drafts for explicit least-privilege worlds.

## 4. World Manifests and compiled enforcement (6 min)

- Compile capability profiles into declarative manifests.
- Encode action boundaries, trust levels, approval gates, and taint constraints.
- Enforce deterministic outcomes: `ALLOW`, `DENY`, `REQUIRE_APPROVAL`.

## 5. Demo walkthrough (6 min)

- Show benign trace -> profile -> manifest -> enforcement.
- Show unsafe trace denied by multiple policy mechanisms.
- Highlight bounded autonomy rather than blanket blocking.

## 6. Practical takeaways (3 min)

- Log real execution.
- Identify recurring bounded modes.
- Convert them into manifests.
- Move sensitive decisions from runtime improvisation to deterministic policy.
