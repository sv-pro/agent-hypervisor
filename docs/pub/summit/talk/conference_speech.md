# Conference Speech

## Opening (critical 30 seconds)

Let me start with something simple.

You deploy an agent to maintain a repository.

It reads files, runs tests, commits, pushes.

Three weeks later — it reads secrets, calls external APIs, pushes to the wrong remote.

Nobody approved that.

Nobody denied it either.

Because there was no boundary.

---

This talk is about one idea:

> What if unsafe actions were not denied —  
> but simply did not exist?

---

## Core idea

Most systems expose tools and filter behavior.

We do something else.

We derive a workflow boundary and construct the execution world from it.

> We do not restrict tools.  
> We construct the only tools that exist.

---

## Model

```
Observe → Profile → Manifest → Render → Enforce
```

---

## Key shift

From:

- permission checks

To:

- world construction

---

## Two levels

Some actions:
- do not exist

Others:
- exist but are denied

---

## Taint

Taint is not guessed.

It is computed:

- from provenance
- from data flow

> Tainted data cannot trigger external effects.

---

## Why this matters

Runtime control does not scale.

You review actions endlessly.

Design-time boundary:

- define once
- reuse many times

O(n) → O(1)

---

## Scope

This is not agent-level security.

This is workflow-level boundaries.

---

## Closing

This PoC does not make agents safe.

It makes unsafe behavior impossible to express.

That is a different class of system.

Thank you.