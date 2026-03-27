"""
compare_bash_vs_rendering.py — Side-by-side architectural comparison.

Runs both models against the same untrusted instruction and prints a
structured, presentation-friendly comparison of the outcomes.

Usage:
    python examples/comparisons/compare_bash_vs_rendering.py

No external dependencies.  No shell execution.  No subprocess calls.
This is a pure architectural demonstration.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make sibling modules importable when run from any directory.
HERE = Path(__file__).parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from bash_permissions_demo import (
    BashPermissions,
    GIT_PERMISSIONS,
    PROPOSED_COMMANDS,
    UNTRUSTED_INSTRUCTION,
    check_bash_permission,
)
from capability_rendering_demo import (
    CODE_UPDATE_CONTEXT,
    DESTRUCTIVE_INTENT,
    RAW_GIT_TOOLS,
    match_intent_to_capability,
    render_capabilities,
)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

WIDE = 62

def header(title: str) -> None:
    print()
    print("=" * WIDE)
    print(title)
    print("=" * WIDE)


def section(title: str) -> None:
    print()
    print(f"--- {title} ---")


def result_line(label: str, value: str) -> None:
    print(f"  {label:<16} {value}")


# ---------------------------------------------------------------------------
# Model A — Bash + String Permissions
# ---------------------------------------------------------------------------

def run_model_a() -> bool:
    """Run the naive permission model.  Returns True if destructive action is allowed."""
    header("Model A: Bash + String-Based Permissions")

    section("Allowlist")
    for rule in GIT_PERMISSIONS.allow:
        print(f"  allow: {rule}")

    section("Permission check (agent-proposed commands)")
    all_allowed = True
    destructive_allowed = False
    for cmd, description in PROPOSED_COMMANDS:
        decision = check_bash_permission(cmd, GIT_PERMISSIONS)
        status = "ALLOWED" if decision.permitted else "DENIED "
        print(f"  [{status}]  {cmd!r}")
        print(f"             ({description})")
        print(f"             reason: {decision.reason}")
        if not decision.permitted:
            all_allowed = False
        if "rm" in cmd and decision.permitted:
            destructive_allowed = True

    section("Outcome")
    if all_allowed:
        print("  Result:      ALLOWED — all three commands pass, including 'git rm -rf .'")
        print("  Mechanism:   string prefix 'git:rm' matched the allow rule")
        print("  Consequence: destructive action remains expressible and executable")
        print()
        print("  Why this model is weak:")
        print("    Bash is a universal tool.  The permission checker sees")
        print("    command tokens ('git', 'rm') but not argument semantics")
        print("    ('-rf .').  The allowlist cannot distinguish 'remove one")
        print("    file' from 'remove everything'.  Any caller who can form")
        print("    a valid git:rm prefix can express any git rm invocation.")
    else:
        print("  Result:      some commands denied")

    return destructive_allowed


# ---------------------------------------------------------------------------
# Model B — Capability Rendering
# ---------------------------------------------------------------------------

def run_model_b() -> bool:
    """Run the capability rendering model.  Returns True if destructive action is blocked."""
    header("Model B: Capability Rendering")

    section("Raw tool space (system-level, before rendering)")
    for tool in RAW_GIT_TOOLS:
        tag = " [DESTRUCTIVE]" if tool.is_destructive else ""
        print(f"  {tool.name}{tag}")

    rendered = render_capabilities(RAW_GIT_TOOLS, CODE_UPDATE_CONTEXT)

    section(f"Capability rendering — task: {CODE_UPDATE_CONTEXT.task_name!r}")
    print(f"  {CODE_UPDATE_CONTEXT.description}")
    print()
    print("  Rendered actor-visible capabilities:")
    for cap in rendered.values():
        print(f"    {cap.name}")
        print(f"      derived from: {cap.derived_from}")

    destructive_tools = [t.name for t in RAW_GIT_TOOLS if t.is_destructive]
    print()
    print("  NOT rendered (absent from actor-visible world):")
    for name in destructive_tools:
        print(f"    {name}")

    section("Intent matching")
    print(f"  Attempted intent:  {DESTRUCTIVE_INTENT!r}")
    match = match_intent_to_capability(DESTRUCTIVE_INTENT, rendered)

    section("Outcome")
    if match is None:
        print("  Result:      NO MATCHING CAPABILITY")
        print("  Mechanism:   git_rm was never rendered into the actor-visible set")
        print("  Consequence: destructive action is not expressible in this world")
        print()
        print("  The agent's vocabulary contains only:")
        for name in rendered:
            print(f"    {name}")
        print()
        print("  There is no capability to invoke, no function to call,")
        print("  no argument to pass.  Execution governance (Layer 3)")
        print("  never sees this request — it was eliminated at render time.")
        return True
    else:
        print(f"  Result:      MATCHED (unexpected) — {match.name}")
        return False


# ---------------------------------------------------------------------------
# Architectural conclusion
# ---------------------------------------------------------------------------

def print_conclusion(model_a_destructive: bool, model_b_blocked: bool) -> None:
    header("Architectural Conclusion")
    print()
    print("  Model A (Bash + Permissions)")
    if model_a_destructive:
        print("    → 'git rm -rf .' was ALLOWED by the string permission checker.")
        print("    → The dangerous action was expressible, reachable, and executed.")
    else:
        print("    → (unexpected: destructive action was blocked)")

    print()
    print("  Model B (Capability Rendering)")
    if model_b_blocked:
        print("    → 'git rm -rf .' had NO matching capability.")
        print("    → The dangerous action could not be expressed in this world.")
    else:
        print("    → (unexpected: destructive action matched a capability)")

    print()
    print("  The difference is architectural, not configurational:")
    print()
    print("    Permissions try to STOP bad actions after they are formed.")
    print("    Rendering REMOVES them from the action space before formation.")
    print()
    print("    String permissions are brittle because Bash is universal:")
    print("    every git operation shares the same surface, and argument")
    print("    semantics are invisible to a prefix matcher.")
    print()
    print("    Capability rendering is stronger because the ontology defines")
    print("    what actions exist.  An action outside the ontology cannot be")
    print("    expressed, cannot be proposed, and cannot reach governance.")
    print()
    print("    In the Agent Hypervisor model:")
    print("      Layer 1 (Base Ontology)    — constructs safe capability vocabulary")
    print("      Layer 2 (Dynamic Projection) — renders context-appropriate subset")
    print("      Layer 3 (Execution Governance) — last-line policy + provenance check")
    print()
    print("    Layers 1 and 2 handle most dangerous actions by non-existence.")
    print("    Layer 3 handles edge cases and mixed-provenance situations.")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print()
    print("=" * WIDE)
    print("Comparison: Bash + Permissions  vs  Capability Rendering")
    print("=" * WIDE)
    print()
    print("Scenario:")
    print(f"  Untrusted instruction: {UNTRUSTED_INSTRUCTION!r}")
    print()
    print("  An agent with Git access receives this instruction from an")
    print("  untrusted source (external document, upstream agent, user input).")
    print("  Both models must decide: can the destructive action be taken?")

    model_a_result = run_model_a()
    model_b_result = run_model_b()
    print_conclusion(model_a_destructive=model_a_result, model_b_blocked=model_b_result)


if __name__ == "__main__":
    main()
