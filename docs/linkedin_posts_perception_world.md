# LinkedIn Posts — Perception-Bounded World Series

---

## Post 1: Zombies Supervising Zombies

**The most popular AI safety pattern is also the most broken.**

The pattern: use one LLM to check the outputs of another LLM. A "safety model" reviews the "working model." Sounds reasonable. It isn't.

Both models share the same architecture. The same training methodology. The same class of failure modes. An adversarial input that bypasses one will statistically bypass the other. This isn't defense in depth. Defense in depth requires independent failure modes. Two LLMs from the same family are not independent. They are correlated copies.

This is zombies supervising zombies. Neither understands what it's checking. Neither has a ground truth to check against. Both are stochastic systems pretending to be deterministic gates.

A stochastic system cannot reliably constrain another stochastic system with the same failure modes.

And then there's the math that nobody talks about. A 99.9% success rate sounds excellent. At 1,000 agent actions per day, that's one failure daily. At 10,000 actions, one failure every 2.4 hours. Scale doesn't dilute the failure rate. It concentrates the impact.

Rare errors are expensive errors. They arrive after the system has earned trust. They arrive when the blast radius is largest. They arrive when remediation costs the most.

Probabilistic safety is delayed failure with a confidence interval.

The alternative is not more guardrails or better classifiers. It's a different architecture entirely: one where the enforcement layer is deterministic, operates on different principles than the agent, and doesn't share its failure modes.

You don't need a smarter guard. You need a world where the dangerous action doesn't exist.

---

## Post 2: The Flexibility Myth

**"We need the agent to be flexible."**

This is the sentence that kills agent safety programs. It sounds like a business requirement. It's actually an architectural abdication.

Here's what's actually true about business processes:

A support agent can offer 5%, 10%, or 15% discount. Not 50%. Not "whatever seems right." The discount tiers are defined. The approval thresholds are defined. The escalation paths are defined.

A financial analyst can read reports from three databases. Not "any database they can find." The data sources are enumerated. The access patterns are known. The output formats are specified.

Business is not flexible. Business is bounded. Every real business process has a finite set of valid actions, a finite set of valid parameters, and a finite set of valid outcomes. The "flexibility" people ask for usually means "I haven't defined the boundaries yet."

Undefined behavior is not flexibility. It is unmanaged risk.

When you give an agent `send_email(to, body)` because "it needs flexibility," you've created an unbounded action space. Any recipient. Any content. The agent can now exfiltrate data to any address on earth. Not because it's malicious. Because you defined a world where that action exists.

Compare: `send_report_to_security(body)`. Same capability for the actual task. Zero flexibility for abuse. The recipient isn't restricted. It's fixed. The concept of "arbitrary recipient" isn't forbidden — it's non-representable.

The right question is never "how do we make the agent flexible?" The right question is "what is the actual finite set of things this agent needs to do?"

Define that set. Render it as capabilities. Remove everything else.

That's not a limitation. That's engineering.

---

## Post 3: The Agent Doesn't See the Universe

**Every AI safety debate I've seen makes the same mistake: assuming the agent operates in the real world.**

It doesn't. No agent does.

An agent operates in its field of perception. Its "world" is the set of inputs it receives, the tools it can call, the memory it can access, and the abstractions it can represent. That's it. Everything outside that boundary doesn't exist — not metaphorically, structurally.

This changes the entire security problem.

If you assume the agent operates in an open world, you need guardrails. You need filters. You need monitors. You need classifiers. You need another LLM to watch the first one. You need all of this because you're trying to constrain behavior in an unbounded space. Every new attack is a new rule. Every bypass is a new patch. You're playing defense on an infinite field.

If you recognize the agent operates in a bounded perception field, you design the field. You don't filter behavior — you define reality. An action that doesn't exist in the world cannot be attempted. A concept that isn't representable cannot be expressed. A tool that isn't rendered cannot be called.

This isn't a guardrail. It's a different kind of system.

The distinction matters because it changes where safety lives. In the guardrail model, safety is a runtime property — it depends on the classifier catching the attack, the monitor noticing the anomaly, the supervisor model disagreeing with the working model. Every one of those checks is probabilistic.

In the perception-bounded model, safety is a design-time property. It lives in the world definition, which is reviewed by humans, compiled into deterministic artifacts, and enforced without any LLM in the path. Same world definition, same behavior. Always.

The most powerful security control isn't a better filter. It's defining what exists.

Design reality, not behavior.
