# AGENTS.md

## Scope
These instructions apply to the entire repository tree.

## Execution protocol for all agents (Codex, Claude, others)
1. Treat `NEXT_TASKS.md` as the single source of truth for sequencing.
2. Work strictly top-to-bottom through tasks unless a task is explicitly blocked.
3. Keep exactly one task marked as in progress at any time (`[-]`).
4. Complete each task in its own branch and pull request.
5. After opening a PR for a task:
   - mark the task as done (`[x]`),
   - add PR number/link next to the task,
   - set the next task to in progress if work continues.
6. Do not silently skip tasks; if blocked, record blocker details under the task.
7. Prefer small, reviewable PRs that include tests or checks relevant to the task.

## Documentation hygiene
- If task scope changes, update `NEXT_TASKS.md` in the same PR.
- Keep roadmap/status docs synchronized with implementation claims.
