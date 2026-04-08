"""
test_bash_vs_capability_rendering.py

Deterministic unit tests for the Bash + Permissions vs Capability Rendering
comparison demo.

Tests verify three architectural properties:

  1. The naive string permission model allows the destructive 'git rm -rf .'
     scenario because the allowlist grants 'git:rm' without argument inspection.

  2. The capability rendering model omits git_rm (and all other destructive
     Git tools) from the actor-visible capability set for a safe task context.

  3. The comparison script's core logic correctly identifies:
       - Model A allows the destructive action
       - Model B blocks it at the rendering layer (no matching capability)
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the comparison modules importable from anywhere.
COMPARISONS = Path(__file__).parent.parent / "examples" / "comparisons"
if str(COMPARISONS) not in sys.path:
    sys.path.insert(0, str(COMPARISONS))

from bash_permissions_demo import (
    BashPermissions,
    GIT_PERMISSIONS,
    PROPOSED_COMMANDS,
    check_bash_permission,
)
from capability_rendering_demo import (
    CODE_UPDATE_CONTEXT,
    DESTRUCTIVE_INTENT,
    RAW_GIT_TOOLS,
    TaskContext,
    match_intent_to_capability,
    render_capabilities,
)


# ---------------------------------------------------------------------------
# Part 1: Naive permission model allows destructive git rm scenario
# ---------------------------------------------------------------------------

class TestNaivePermissionModel:

    def test_git_rm_is_allowed_by_prefix_match(self):
        """
        The destructive 'git rm -rf .' command matches the 'git:rm' allow rule.

        This is the core weakness: the checker sees the command token ('rm')
        but not the argument semantics ('-rf .').
        """
        decision = check_bash_permission("git rm -rf .", GIT_PERMISSIONS)
        assert decision.permitted is True, (
            "Expected 'git rm -rf .' to be ALLOWED by the naive permission model. "
            "This verifies the architectural weakness being demonstrated."
        )

    def test_matched_rule_is_git_rm(self):
        """The matched rule should be the 'git:rm' allowlist entry."""
        decision = check_bash_permission("git rm -rf .", GIT_PERMISSIONS)
        assert decision.matched_rule == "git:rm"

    def test_all_scenario_commands_are_allowed(self):
        """
        Every command in the canonical scenario — including the destructive one —
        passes the naive permission checker.
        """
        for cmd, _ in PROPOSED_COMMANDS:
            decision = check_bash_permission(cmd, GIT_PERMISSIONS)
            assert decision.permitted is True, (
                f"Expected {cmd!r} to be ALLOWED but got: {decision.reason}"
            )

    def test_legitimate_removal_also_allowed(self):
        """A benign 'git rm old_file.txt' is indistinguishable from the destructive case."""
        decision = check_bash_permission("git rm old_file.txt", GIT_PERMISSIONS)
        assert decision.permitted is True

    def test_unknown_command_is_denied(self):
        """Commands outside the allowlist are correctly denied."""
        decision = check_bash_permission("git rebase -i HEAD~5", GIT_PERMISSIONS)
        assert decision.permitted is False

    def test_restricted_permissions_deny_git_rm(self):
        """
        If 'git:rm' is removed from the allowlist, 'git rm -rf .' is denied.

        This shows the fix is possible — but at the cost of removing a
        legitimate operation.  String permissions cannot distinguish safe from
        unsafe variants of the same subcommand.
        """
        restricted = BashPermissions(allow=["git:add", "git:commit", "git:push"])
        decision = check_bash_permission("git rm -rf .", restricted)
        assert decision.permitted is False

    def test_wildcard_rule_allows_any_subcommand(self):
        """A 'git:*' wildcard allows everything — making the problem worse."""
        permissive = BashPermissions(allow=["git:*"])
        for cmd in ["git rm -rf .", "git reset --hard HEAD~100", "git push --force"]:
            decision = check_bash_permission(cmd, permissive)
            assert decision.permitted is True


# ---------------------------------------------------------------------------
# Part 2: Capability rendering omits dangerous actions from visible set
# ---------------------------------------------------------------------------

class TestCapabilityRendering:

    def test_destructive_tools_absent_from_rendered_set(self):
        """
        Destructive raw tools (git_rm, git_reset, etc.) produce no rendered
        capability for the code-update task context.
        """
        rendered = render_capabilities(RAW_GIT_TOOLS, CODE_UPDATE_CONTEXT)
        rendered_names = set(rendered.keys())

        # None of the destructive raw tool names should appear as capability names
        destructive_raw = {t.name for t in RAW_GIT_TOOLS if t.is_destructive}
        for raw_name in destructive_raw:
            assert raw_name not in rendered_names, (
                f"Destructive raw tool {raw_name!r} should not appear in "
                f"rendered capabilities but was found."
            )

    def test_safe_capabilities_are_rendered(self):
        """The three safe workflow capabilities are present in the rendered set."""
        rendered = render_capabilities(RAW_GIT_TOOLS, CODE_UPDATE_CONTEXT)
        assert "stage_changes" in rendered
        assert "commit_changes" in rendered
        assert "push_changes" in rendered

    def test_rendered_set_size(self):
        """Exactly three capabilities are rendered for the code-update context."""
        rendered = render_capabilities(RAW_GIT_TOOLS, CODE_UPDATE_CONTEXT)
        assert len(rendered) == 3, (
            f"Expected 3 rendered capabilities, got {len(rendered)}: "
            f"{list(rendered.keys())}"
        )

    def test_destructive_intent_has_no_match(self):
        """
        'git rm -rf .' finds no matching capability in the rendered set.

        This is the architectural guarantee: the dangerous action cannot
        be expressed because there is no capability to invoke.
        """
        rendered = render_capabilities(RAW_GIT_TOOLS, CODE_UPDATE_CONTEXT)
        match = match_intent_to_capability(DESTRUCTIVE_INTENT, rendered)
        assert match is None, (
            f"Expected NO matching capability for {DESTRUCTIVE_INTENT!r} "
            f"but got: {match}"
        )

    def test_safe_intents_do_match(self):
        """Legitimate workflow intents resolve to rendered capabilities."""
        rendered = render_capabilities(RAW_GIT_TOOLS, CODE_UPDATE_CONTEXT)
        assert match_intent_to_capability("stage changes",  rendered) is not None
        assert match_intent_to_capability("commit changes", rendered) is not None
        assert match_intent_to_capability("push changes",   rendered) is not None

    def test_empty_allowed_tools_produces_empty_set(self):
        """A context with no allowed tools produces an empty capability set."""
        empty_context = TaskContext(
            task_name="read-only",
            allowed_raw_tools=[],
        )
        rendered = render_capabilities(RAW_GIT_TOOLS, empty_context)
        assert rendered == {}

    def test_adding_git_rm_to_context_does_not_produce_capability(self):
        """
        Even if git_rm is added to allowed_raw_tools, it has no rendering entry
        and therefore still produces no capability.

        The render_map is the ontological boundary, not just the context filter.
        """
        context_with_rm = TaskContext(
            task_name="code-update-with-rm",
            allowed_raw_tools=["git_add", "git_commit", "git_push", "git_rm"],
        )
        rendered = render_capabilities(RAW_GIT_TOOLS, context_with_rm)
        # git_rm has no entry in the render_map, so it does not appear
        assert "git_rm" not in rendered
        # The three safe capabilities are still present
        assert len(rendered) == 3

    def test_derived_from_is_correct(self):
        """Each rendered capability correctly records its raw tool origin."""
        rendered = render_capabilities(RAW_GIT_TOOLS, CODE_UPDATE_CONTEXT)
        assert rendered["stage_changes"].derived_from == ["git_add"]
        assert rendered["commit_changes"].derived_from == ["git_commit"]
        assert rendered["push_changes"].derived_from == ["git_push"]


# ---------------------------------------------------------------------------
# Part 3: Comparison script core logic produces intended outcomes
# ---------------------------------------------------------------------------

class TestComparisonLogic:

    def test_model_a_allows_destructive_scenario(self):
        """
        The Model A logic (as used in the comparison script) reports that
        the destructive action is allowed.
        """
        destructive_allowed = False
        for cmd, _ in PROPOSED_COMMANDS:
            decision = check_bash_permission(cmd, GIT_PERMISSIONS)
            if "rm" in cmd and decision.permitted:
                destructive_allowed = True
        assert destructive_allowed is True

    def test_model_b_blocks_destructive_scenario(self):
        """
        The Model B logic (as used in the comparison script) reports that
        the destructive intent has no matching capability.
        """
        rendered = render_capabilities(RAW_GIT_TOOLS, CODE_UPDATE_CONTEXT)
        match = match_intent_to_capability(DESTRUCTIVE_INTENT, rendered)
        assert match is None

    def test_architectural_contrast_is_deterministic(self):
        """
        Run both models multiple times and confirm the outcome is always:
          Model A: destructive action allowed
          Model B: destructive action blocked
        This ensures the demo is suitable for automated CI and presentations.
        """
        for _ in range(10):
            # Model A
            decision = check_bash_permission("git rm -rf .", GIT_PERMISSIONS)
            assert decision.permitted is True

            # Model B
            rendered = render_capabilities(RAW_GIT_TOOLS, CODE_UPDATE_CONTEXT)
            match = match_intent_to_capability(DESTRUCTIVE_INTENT, rendered)
            assert match is None

    def test_scenario_uses_same_instruction_in_both_models(self):
        """
        Both models import the same UNTRUSTED_INSTRUCTION constant, ensuring
        the comparison is apples-to-apples.
        """
        from bash_permissions_demo import UNTRUSTED_INSTRUCTION as instr_a
        from capability_rendering_demo import UNTRUSTED_INSTRUCTION as instr_b
        assert instr_a == instr_b

    def test_git_rm_is_in_raw_tool_space(self):
        """git_rm exists in the raw tool space — this is the precondition for the demo."""
        raw_names = {t.name for t in RAW_GIT_TOOLS}
        assert "git_rm" in raw_names

    def test_git_rm_is_flagged_destructive(self):
        """git_rm is correctly flagged as destructive in the raw tool space."""
        git_rm = next(t for t in RAW_GIT_TOOLS if t.name == "git_rm")
        assert git_rm.is_destructive is True
