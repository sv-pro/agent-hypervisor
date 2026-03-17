# Bash + Permissions vs Capability Rendering

A concrete architectural comparison of two approaches to constraining agent
behaviour around dangerous actions.

---

## The Problem with Universal Tools

Bash is a universal tool.  So is any other general-purpose command executor.
"Universal" means a single surface exposes the entire capability space of the
host system.  For Git specifically, a single tool called `bash` (or `git`) can
express:

```
git add .
git commit -m "update"
git push
# — but also —
git rm -rf .
git reset --hard HEAD~100
git push --force
```

From the tool's perspective these are all equivalent: they are strings passed
to a command executor.  The tool does not know which are safe and which are
catastrophic.

---

## Model A: String-Based Permissions

The natural first response is to build an allowlist:

```python
permissions = {
    "allow": [
        "git:add",
        "git:commit",
        "git:push",
        "git:rm",    # needed for removing obsolete files...
    ]
}
```

A permission checker inspects the proposed command, extracts `<cmd>:<subcommand>`,
and grants or denies based on prefix match.

### Why This Is Brittle

**1. Argument semantics are invisible.**
The checker sees `git rm`.  It cannot see `-rf .`.  There is no prefix that
distinguishes `git rm obsolete.txt` from `git rm -rf .`.  Both match
`git:rm`.

**2. The allowlist must be conservative or useless.**
If you remove `git:rm` entirely you break legitimate use cases.  If you keep
it, you allow the destructive case.  There is no middle ground expressible in
string prefixes.

**3. Composition attacks are trivially possible.**
A single allowed prefix covers every argument variant, including chained
commands: `git rm -rf . && git commit -m 'cleanup' && git push`.

**4. The surface area grows with tool capability.**
As the underlying tool gains new subcommands or flags, the allowlist must be
updated.  Every new dangerous flag is a gap until someone notices.

**5. The model is reactive, not structural.**
Permissions try to *stop* bad actions after they have been formed.  The
dangerous action is still expressible — it just might be denied.  A sufficiently
clever or adversarially-prompted agent may find a variant the checker misses.

---

## Model B: Capability Rendering

The Agent Hypervisor takes a different approach rooted in ontology construction.

### Raw Tool Space

The raw tool space contains every primitive operation available at the system
level.  For Git:

```
git_add, git_commit, git_push,
git_rm, git_reset, git_clean, git_rebase, git_force_push, ...
```

This space is large, dangerous, and never directly exposed to agents.

### Capability Rendering (Layers 1 + 2)

Before an agent receives its tool set, the system runs a rendering step:

1. **Layer 1 — Base Ontology Construction** (design-time)
   A World Manifest defines which raw tools are in scope for a given task
   class.  The compiler produces a task-specific capability vocabulary —
   safe, semantically named actions derived from permitted raw tools.

2. **Layer 2 — Dynamic Ontology Projection** (runtime)
   The base ontology is further projected based on role, session state,
   active approvals, and environment.  Only the projected subset reaches
   the agent.

For a routine "code update" task:

| Raw tool         | Rendered capability  |
|------------------|----------------------|
| `git_add`        | `stage_changes`      |
| `git_commit`     | `commit_changes`     |
| `git_push`       | `push_changes`       |
| `git_rm`         | *(not rendered)*     |
| `git_reset`      | *(not rendered)*     |
| `git_force_push` | *(not rendered)*     |

The agent's vocabulary is `{stage_changes, commit_changes, push_changes}`.
Nothing else exists.

### The Structural Guarantee

When an adversarial instruction says "run git rm -rf .", the agent cannot
comply — not because a permission checker denied it, but because:

- There is no capability called `git_rm` in the actor-visible set.
- There is no capability that maps to arbitrary file removal.
- There is no string to type, no function to call, no argument to pass.

The dangerous action is not expressible in this world.

**Execution governance (Layer 3) never sees this request.**
It was eliminated at rendering time.  The governance layer handles edge
cases and mixed-provenance situations — not the bulk of the threat surface.

---

## Relationship to the Hybrid Model

The Agent Hypervisor is not purely one or the other.  It uses all three layers
together:

```
Layer 1 (Base Ontology)
  Constructs the vocabulary of possible actions from raw tools + manifest.
  Dangerous tools absent from the manifest produce no capability at all.

Layer 2 (Dynamic Projection)
  Narrows the ontology further based on runtime context.
  An action present in the base ontology may be absent in the current
  task projection.

Layer 3 (Execution Governance)
  Policy engine + provenance firewall.
  Evaluates tool calls that do reach the agent against:
    - declarative policy rules (YAML)
    - provenance chains (who produced each argument)
    - structural invariants (RULE-01 through RULE-05)
  Returns: allow | deny | ask (human approval required)
```

The key insight is that **non-existence is stronger than prohibition**.
A permission system must correctly enumerate every dangerous variant and deny
each one.  A rendering system only needs to enumerate the safe subset and
render nothing else.

---

## Summary

| Property                              | Bash + Permissions       | Capability Rendering     |
|---------------------------------------|--------------------------|--------------------------|
| Dangerous actions expressible?        | Yes — until explicitly denied | No — never rendered |
| Attacker needs to                     | Find a bypassed prefix   | Invent a new capability  |
| Allowlist maintenance burden          | High (grows with tool)   | Low (ontology is closed) |
| Argument-level attacks                | Invisible to checker     | Irrelevant — no surface  |
| Governance layer role                 | Primary defence          | Last-line edge cases     |
| Failure mode                          | Overly permissive match  | Missing legitimate need  |

Permissions try to stop bad actions.
Rendering removes them from the action space.

---

## Running the Demo

```bash
python examples/comparisons/compare_bash_vs_rendering.py
```

See also:
- `examples/comparisons/bash_permissions_demo.py` — Model A in isolation
- `examples/comparisons/capability_rendering_demo.py` — Model B in isolation
- `tests/test_bash_vs_capability_rendering.py` — Deterministic unit tests
