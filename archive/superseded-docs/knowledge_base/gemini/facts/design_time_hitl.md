# Design-Time Human-in-the-Loop (HITL)

**Status:** `[DESIGN/PLANNING]`

## Concept
Traditional Human-in-the-Loop architectures place the human element in an ongoing evaluation role at runtime to review potentially dangerous decisions (an $O(n)$ cost model). The Agent Hypervisor whitepaper emphasizes that human judgment should be **amortized across design-time rather than expended at runtime**. 

## The Three Modes of Human Involvement
1. **Design-Time Human (Scales)**: 
   The primary focus of effort. The human approves rules, capability matrices, and generated parsers. The human reviews the World Manifest outlining the agent's conceptual reality parameters. One design-time decision implicitly regulates thousands of runtime cases.
2. **Runtime Human (Exception, Not Rule)**: 
   The `require_approval` intent decision serves as a safety relief valve, not the standard operating procedure. High volumes of runtime escalations represent systemic feedback signaling that the World Manifest must be improved at design-time.
3. **Iteration-Time Human (Feedback Loop)**: 
   The human reviews the aggregate runtime logs (e.g., logs revealing specific parser bypass attempts, taint ambiguity rates, or unhandled rule escalations) and subsequently collaborates with the LLM (using AI Aikido) to regenerate better, smarter rules.

By moving HITL up the pipeline into the deterministic compilation phase, the process achieves logarithmic cost scaling.
