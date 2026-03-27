# Slide Outline

## Slide 1 — Title

**From Behavior to Boundaries: Compiling Observed Agent Execution into Least-Privilege Worlds**

- Who I am
- What this talk is about
- One-sentence thesis: observed execution can be compiled into deterministic runtime boundaries

## Slide 2 — The problem

- Agentic security is not just about prompts
- The attack surface now includes tools, orchestration, memory, and external side effects
- Reactive filtering happens too late

## Slide 3 — The practical failure mode

- Scope creep
- Repeated approvals
- Permission fatigue
- Growing gap between intended behavior and actual runtime power

## Slide 4 — The shift in mindset

- Old question: "Can the agent do X?"
- Better question: "Does X exist in the agent’s world?"
- Security as world definition, not only behavior filtering

## Slide 5 — The pipeline

- Observe
- Profile
- Manifest
- Enforce
- Why this is a runtime-to-design bridge

## Slide 6 — What the PoC actually does

- Benign trace
- Derived capability profile
- Compiled World Manifest
- Deterministic policy outcomes

## Slide 7 — Benign workflow

- Show `repo_safe_write`
- Explain allowed actions
- Explain why remote push requires approval

## Slide 8 — Unsafe workflow

- `env_read` denied
- tainted exfiltration denied
- out-of-scope remote denied
- untrusted shell execution denied

## Slide 9 — Why this matters

- Bounded autonomy
- Least privilege by construction
- Policy-as-code
- Deterministic runtime behavior

## Slide 10 — Limits

- This does not solve semantic intent in general
- Profiles are drafts, not truth
- Manifest quality depends on review and iteration

## Slide 11 — Practical adoption path

- Log real execution
- Identify recurring bounded workflows
- Create capability profiles
- Compile into manifests
- Move sensitive decisions to design time

## Slide 12 — Close

- Main claim
- What the PoC proves
- What the next step is
