# Summit Materials

This directory contains conference-supporting materials for the `agent-world-compiler-poc` repository.

The proposed talk is based on the PoC implemented in this repository. The core pattern:

```
Observe → Profile → Manifest → Enforce
```

The current PoC demonstrates:

- recording execution traces from agent/tool activity;
- deriving a bounded capability profile from a benign repository-maintenance trace using the profiler;
- compiling that profile into a World Manifest with explicit `input_trust` settings derived from the bootstrap trust model;
- enforcing deterministic `ALLOW`, `DENY`, and `REQUIRE_APPROVAL` decisions;
- blocking unsafe actions including secret access, tainted-data exfiltration, out-of-scope remote operations, and trust-violating execution paths.

## Contents

- `talk/conference_speech.md` — full spoken talk draft (10–15 min target)
- `cfp/abstract.md` — short and full CFP abstract
- `cfp/speaker_abstract.md` — short speaker summary (100–200 words)
- `cfp/bio.md` — speaker bio
- `cfp/learning-objectives.md` — learning objectives
- `cfp/reviewer-notes.md` — reviewer-facing fit and scope notes
- `talk/outline.md` — talk structure
- `talk/script-notes.md` — core speaking notes
- `talk/demo-plan.md` — how to present the PoC demo
- `talk/qa-prep.md` — likely questions and concise answers
- `slides/slide-outline.md` — planned slide flow
- `slides/diagrams.md` — diagrams to include
- `slides/speaker-notes.md` — notes by slide

## Positioning

This is not a claim to solve agent safety in general.

It is a bounded claim: observed agent execution can be compiled into deterministic runtime boundaries for specific workflows.

The value is not just that a manifest exists — it is that the manifest can be derived from evidence rather than guessed.

## Key concepts

**Bootstrap trust model** — the built-in default mapping from input source type to trust level (`repo_local: trusted`, `environment: untrusted`, `llm_output: untrusted`, `tool_output: conditional`). The starting assumption, not a user-authored artifact.

**Taint** — derived deterministically from input source provenance and propagated through `depends_on` execution dependencies. Not manually assigned.

**Safe compression** — the manifest may compress observed behavior (e.g., collapse resource URIs to prefixes), but must never introduce capabilities absent from the safe trace.

## Repository link

- PoC repository: https://github.com/sv-pro/agent-world-compiler-poc
