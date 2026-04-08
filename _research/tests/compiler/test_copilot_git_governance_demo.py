"""
test_copilot_git_governance_demo.py

Deterministic unit tests for the Copilot / coding-agent governance PoC.

Tests verify five architectural properties:

  1. destructive_delete is absent from the code-update rendered world.
  2. The git rm scenario produces NO MATCHING CAPABILITY in code-update.
  3. The force_push scenario produces NO MATCHING CAPABILITY in release-safe.
  4. A safe commit/push-only action is ALLOWED in code-update.
  5. All scenario verdicts are deterministic across repeated evaluations.

These tests are intended to be run as part of CI and to serve as
documentation of the demo's invariants.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the integrations module importable from any working directory.
INTEGRATIONS = Path(__file__).parent.parent / "examples" / "integrations"
if str(INTEGRATIONS) not in sys.path:
    sys.path.insert(0, str(INTEGRATIONS))

from copilot_git_governance_demo import (
    SCENARIOS,
    RAW_GIT_TOOLS,
    GovernanceVerdict,
    RenderedCapability,
    Scenario,
    SemanticCandidate,
    build_git_world,
    build_reporting_world,
    evaluate_action,
    extract_semantic_candidates,
    run_faq_option_1,
    run_faq_option_2,
    run_faq_option_3,
    run_faq_option_4,
    run_faq_option_5,
    run_faq_option_6,
    _PERMISSIONS_ALLOWLIST,
    _permissions_check_fragments,
)


# ---------------------------------------------------------------------------
# 1. destructive_delete is absent from code-update rendered world
# ---------------------------------------------------------------------------

class TestCodeUpdateRenderedWorld:

    def _world(self):
        return build_git_world(
            task_name="code-update",
            description="Stage, commit, and push code changes.",
            allowed_capabilities=["stage_changes", "commit_changes", "push_changes"],
        )

    def test_destructive_delete_absent(self):
        """
        destructive_delete must not appear in the code-update capability set.

        This is the primary architectural guarantee: the dangerous action
        does not exist in the actor-visible world.
        """
        world = self._world()
        assert "destructive_delete" not in world.capabilities, (
            "destructive_delete should be absent from code-update rendered world."
        )

    def test_force_push_absent(self):
        """force_push is also absent from the code-update world."""
        world = self._world()
        assert "force_push" not in world.capabilities

    def test_destructive_reset_absent(self):
        """destructive_reset is absent from the code-update world."""
        world = self._world()
        assert "destructive_reset" not in world.capabilities

    def test_safe_capabilities_present(self):
        """The three safe capabilities are present in code-update."""
        world = self._world()
        assert "stage_changes" in world.capabilities
        assert "commit_changes" in world.capabilities
        assert "push_changes" in world.capabilities

    def test_exactly_three_capabilities(self):
        """Exactly three capabilities are rendered for code-update."""
        world = self._world()
        assert len(world.capabilities) == 3, (
            f"Expected 3 capabilities, got {len(world.capabilities)}: "
            f"{list(world.capabilities.keys())}"
        )

    def test_derived_from_is_correct(self):
        """Each capability correctly records its raw tool origin."""
        world = self._world()
        assert world.capabilities["stage_changes"].derived_from == ["git_add"]
        assert world.capabilities["commit_changes"].derived_from == ["git_commit"]
        assert world.capabilities["push_changes"].derived_from == ["git_push"]

    def test_git_rm_raw_tool_exists_but_not_rendered(self):
        """
        git_rm exists in the raw tool space but produces no capability.

        This verifies the architectural claim: the raw tool space is broader
        than the rendered world.  Presence in the raw space does not imply
        presence in the actor-visible world.
        """
        world = self._world()
        raw_names = {t.name for t in world.raw_tools}
        assert "git_rm" in raw_names, "git_rm must exist in the raw tool space"
        assert "destructive_delete" not in world.capabilities, (
            "git_rm must not appear in the rendered capability set"
        )


# ---------------------------------------------------------------------------
# 2. git rm scenario produces NO MATCHING CAPABILITY in code-update
# ---------------------------------------------------------------------------

class TestGitRmScenario:

    def _world(self):
        return build_git_world(
            task_name="code-update",
            description="Stage, commit, and push code changes.",
            allowed_capabilities=["stage_changes", "commit_changes", "push_changes"],
        )

    def test_git_rm_compound_action_denied(self):
        """
        The canonical destructive action produces NO MATCHING CAPABILITY.

        This is the central claim of the PoC: the action string
        'git rm -rf . && git commit -m "cleanup" && git push'
        cannot be expressed in the code-update world.
        """
        world = self._world()
        action = 'git rm -rf . && git commit -m "cleanup" && git push'
        verdict = evaluate_action(action, world)
        assert verdict.allowed is False, (
            f"Expected NO MATCHING CAPABILITY but got ALLOWED. "
            f"Candidates: {[r.candidate.name for r in verdict.candidate_results]}"
        )
        assert verdict.reason == GovernanceVerdict.DENY

    def test_git_rm_compound_produces_destructive_candidate(self):
        """The compound action generates a destructive_delete semantic candidate."""
        candidates = extract_semantic_candidates(
            'git rm -rf . && git commit -m "cleanup" && git push'
        )
        names = [c.name for c in candidates]
        assert "destructive_delete" in names, (
            f"Expected destructive_delete in candidates, got: {names}"
        )

    def test_destructive_candidate_is_not_present_in_world(self):
        """The destructive_delete candidate has no matching capability."""
        world = self._world()
        action = 'git rm -rf . && git commit -m "cleanup" && git push'
        verdict = evaluate_action(action, world)
        absent = [r for r in verdict.candidate_results if not r.is_present]
        absent_names = [r.candidate.name for r in absent]
        assert "destructive_delete" in absent_names, (
            f"Expected destructive_delete to be absent, got present: {absent_names}"
        )

    def test_standalone_git_rm_denied(self):
        """Even a simple 'git rm file.txt' is not expressible."""
        world = self._world()
        verdict = evaluate_action("git rm file.txt", world)
        assert verdict.allowed is False

    def test_git_reset_denied(self):
        """git reset is also not expressible in the code-update world."""
        world = self._world()
        verdict = evaluate_action("git reset --hard HEAD", world)
        assert verdict.allowed is False

    def test_git_clean_denied(self):
        """git clean is also not expressible in the code-update world."""
        world = self._world()
        verdict = evaluate_action("git clean -fd", world)
        assert verdict.allowed is False


# ---------------------------------------------------------------------------
# 3. force_push scenario produces NO MATCHING CAPABILITY in release-safe
# ---------------------------------------------------------------------------

class TestReleaseSafeScenario:

    def _world(self):
        return build_git_world(
            task_name="release-safe",
            description="Prepare and publish a release.",
            allowed_capabilities=[
                "stage_changes", "commit_changes", "push_changes", "create_release_tag"
            ],
        )

    def test_force_push_not_expressible(self):
        """
        git push --force produces NO MATCHING CAPABILITY in release-safe.

        The release workflow can tag and push normally, but history-rewriting
        is outside this world.
        """
        world = self._world()
        verdict = evaluate_action("git push --force", world)
        assert verdict.allowed is False, (
            "Expected NO MATCHING CAPABILITY for git push --force in release-safe."
        )

    def test_force_push_flag_variant_also_denied(self):
        """git push -f (short flag) is also not expressible."""
        world = self._world()
        verdict = evaluate_action("git push -f", world)
        assert verdict.allowed is False

    def test_force_push_absent_from_rendered_world(self):
        """force_push has no entry in the release-safe capability set."""
        world = self._world()
        assert "force_push" not in world.capabilities

    def test_create_release_tag_present(self):
        """create_release_tag is available in the release-safe world."""
        world = self._world()
        assert "create_release_tag" in world.capabilities

    def test_normal_push_allowed_in_release_safe(self):
        """A normal git push (without --force) is expressible."""
        world = self._world()
        verdict = evaluate_action("git push", world)
        assert verdict.allowed is True

    def test_release_safe_has_four_capabilities(self):
        """release-safe renders exactly four capabilities."""
        world = self._world()
        assert len(world.capabilities) == 4, (
            f"Expected 4 capabilities, got {len(world.capabilities)}"
        )

    def test_destructive_tools_still_absent(self):
        """Destructive tools are absent even in the more capable release-safe world."""
        world = self._world()
        for absent in ("destructive_delete", "destructive_reset", "force_push"):
            assert absent not in world.capabilities, (
                f"{absent} should be absent from release-safe world"
            )


# ---------------------------------------------------------------------------
# 4. Safe commit/push only action is ALLOWED in code-update
# ---------------------------------------------------------------------------

class TestSafeActionsAllowed:

    def _world(self):
        return build_git_world(
            task_name="code-update",
            description="Stage, commit, and push code changes.",
            allowed_capabilities=["stage_changes", "commit_changes", "push_changes"],
        )

    def test_git_add_allowed(self):
        """git add resolves to stage_changes and is expressible."""
        world = self._world()
        verdict = evaluate_action("git add .", world)
        assert verdict.allowed is True

    def test_git_commit_allowed(self):
        """git commit resolves to commit_changes and is expressible."""
        world = self._world()
        verdict = evaluate_action('git commit -m "fix: update handler"', world)
        assert verdict.allowed is True

    def test_git_push_allowed(self):
        """git push (without --force) resolves to push_changes and is expressible."""
        world = self._world()
        verdict = evaluate_action("git push", world)
        assert verdict.allowed is True

    def test_full_safe_workflow_allowed(self):
        """A complete safe workflow (add, commit, push) is expressible."""
        world = self._world()
        action = 'git add . && git commit -m "update" && git push'
        verdict = evaluate_action(action, world)
        assert verdict.allowed is True, (
            f"Expected ALLOWED for safe workflow, got: {verdict.reason}. "
            f"Candidates: {[r.candidate.name for r in verdict.candidate_results]}"
        )

    def test_all_candidates_present_in_safe_workflow(self):
        """Every semantic candidate in the safe workflow has a matching capability."""
        world = self._world()
        action = 'git add . && git commit -m "update" && git push'
        verdict = evaluate_action(action, world)
        for result in verdict.candidate_results:
            assert result.is_present, (
                f"Expected {result.candidate.name} to be PRESENT in code-update world"
            )


# ---------------------------------------------------------------------------
# 5. Determinism — verdicts are stable across repeated evaluations
# ---------------------------------------------------------------------------

class TestDeterminism:

    def test_git_rm_scenario_is_deterministic(self):
        """
        The git rm verdict is identical across 20 evaluations.

        This verifies the demo is suitable for CI and presentations.
        """
        world = build_git_world(
            task_name="code-update",
            description="...",
            allowed_capabilities=["stage_changes", "commit_changes", "push_changes"],
        )
        action = 'git rm -rf . && git commit -m "cleanup" && git push'
        verdicts = [evaluate_action(action, world) for _ in range(20)]
        assert all(not v.allowed for v in verdicts)
        assert all(v.reason == GovernanceVerdict.DENY for v in verdicts)

    def test_force_push_scenario_is_deterministic(self):
        """The force_push verdict is identical across 20 evaluations."""
        world = build_git_world(
            task_name="release-safe",
            description="...",
            allowed_capabilities=[
                "stage_changes", "commit_changes", "push_changes", "create_release_tag"
            ],
        )
        verdicts = [evaluate_action("git push --force", world) for _ in range(20)]
        assert all(not v.allowed for v in verdicts)

    def test_safe_workflow_is_deterministic(self):
        """The safe workflow verdict is identical across 20 evaluations."""
        world = build_git_world(
            task_name="code-update",
            description="...",
            allowed_capabilities=["stage_changes", "commit_changes", "push_changes"],
        )
        action = 'git add . && git commit -m "update" && git push'
        verdicts = [evaluate_action(action, world) for _ in range(20)]
        assert all(v.allowed for v in verdicts)

    def test_canonical_scenario_objects_produce_expected_verdicts(self):
        """
        The SCENARIOS list used in the demo produces the expected verdicts.

        code-update   → denied (destructive action)
        release-safe  → denied (force push)
        reporting     → denied (arbitrary email)
        """
        expected = [False, False, False]
        for scenario, expected_allowed in zip(SCENARIOS, expected):
            verdict = evaluate_action(scenario.attempted_action, scenario.world)
            assert verdict.allowed == expected_allowed, (
                f"Scenario {scenario.name!r}: expected allowed={expected_allowed}, "
                f"got allowed={verdict.allowed}. Reason: {verdict.reason}"
            )


# ---------------------------------------------------------------------------
# 6. Reporting scenario — ontological narrowing beyond Git
# ---------------------------------------------------------------------------

class TestReportingScenario:

    def _world(self):
        return build_reporting_world()

    def test_arbitrary_email_not_expressible(self):
        """
        send_email to an arbitrary external recipient produces NO MATCHING CAPABILITY.

        The raw send_email tool is not rendered; only purpose-bound forms are.
        """
        world = self._world()
        verdict = evaluate_action('send_email("external@evil.com", body)', world)
        assert verdict.allowed is False

    def test_purpose_bound_capabilities_present(self):
        """The reporting world has only purpose-bound rendered capabilities."""
        world = self._world()
        assert "send_report_to_security" in world.capabilities
        assert "send_report_to_finance" in world.capabilities

    def test_generic_send_email_absent(self):
        """The generic send_email capability is not in the reporting world."""
        world = self._world()
        assert "send_email" not in world.capabilities

    def test_reporting_world_has_exactly_two_capabilities(self):
        """Exactly two purpose-bound capabilities are rendered."""
        world = self._world()
        assert len(world.capabilities) == 2


# ---------------------------------------------------------------------------
# 7. Semantic matcher correctness
# ---------------------------------------------------------------------------

class TestSemanticMatcher:

    def test_git_rm_maps_to_destructive_delete(self):
        candidates = extract_semantic_candidates("git rm -rf .")
        names = [c.name for c in candidates]
        assert "destructive_delete" in names

    def test_git_push_force_maps_to_force_push(self):
        candidates = extract_semantic_candidates("git push --force")
        names = [c.name for c in candidates]
        assert "force_push" in names

    def test_git_push_f_maps_to_force_push(self):
        candidates = extract_semantic_candidates("git push -f")
        names = [c.name for c in candidates]
        assert "force_push" in names

    def test_git_push_without_force_maps_to_push_changes(self):
        candidates = extract_semantic_candidates("git push")
        names = [c.name for c in candidates]
        assert "push_changes" in names
        assert "force_push" not in names

    def test_git_add_maps_to_stage_changes(self):
        candidates = extract_semantic_candidates("git add .")
        names = [c.name for c in candidates]
        assert "stage_changes" in names

    def test_git_commit_maps_to_commit_changes(self):
        candidates = extract_semantic_candidates('git commit -m "msg"')
        names = [c.name for c in candidates]
        assert "commit_changes" in names

    def test_git_reset_maps_to_destructive_reset(self):
        candidates = extract_semantic_candidates("git reset --hard HEAD")
        names = [c.name for c in candidates]
        assert "destructive_reset" in names

    def test_git_clean_maps_to_destructive_clean(self):
        candidates = extract_semantic_candidates("git clean -fd")
        names = [c.name for c in candidates]
        assert "destructive_clean" in names

    def test_compound_action_produces_multiple_candidates(self):
        """A shell pipeline produces a candidate per component."""
        action = 'git rm -rf . && git commit -m "cleanup" && git push'
        candidates = extract_semantic_candidates(action)
        names = [c.name for c in candidates]
        assert "destructive_delete" in names
        assert "commit_changes" in names
        assert "push_changes" in names

    def test_send_email_maps_to_send_email(self):
        candidates = extract_semantic_candidates('send_email("x@y.com", body)')
        names = [c.name for c in candidates]
        assert "send_email" in names

    def test_rm_rf_maps_to_destructive_delete(self):
        """rm -rf (without git) also maps to destructive_delete."""
        candidates = extract_semantic_candidates("rm -rf .")
        names = [c.name for c in candidates]
        assert "destructive_delete" in names, (
            f"Expected destructive_delete from 'rm -rf .', got: {names}"
        )


# ---------------------------------------------------------------------------
# 8. FAQ layer — executable objection scenarios
# ---------------------------------------------------------------------------

class TestFAQLayer:
    """
    Verify the invariants underlying each FAQ scenario.

    These tests confirm the structural properties that make each FAQ
    scenario's output correct and deterministic.
    """

    def _world(self):
        return build_git_world(
            task_name="code-update",
            description="Stage, commit, and push code changes.",
            allowed_capabilities=["stage_changes", "commit_changes", "push_changes"],
        )

    # --- FAQ option 1: permissions vs rendering ---

    def test_faq1_permissions_allow_destructive(self):
        """
        The permissions model ALLOWS git rm in the canonical allowlist.

        This is the core claim of FAQ option 1: the same action that is
        blocked by the rendered world passes the permissions model.
        """
        action = 'git rm -rf . && git commit && git push'
        results = _permissions_check_fragments(action, _PERMISSIONS_ALLOWLIST)
        # git:rm must be present and permitted
        git_rm_results = [(frag, perm, ok) for frag, perm, ok in results if perm == "git:rm"]
        assert git_rm_results, "git:rm fragment not found in permissions check"
        assert all(ok for _, _, ok in git_rm_results), (
            "git:rm must be permitted by the permissions allowlist"
        )

    def test_faq1_rendered_world_blocks_destructive(self):
        """
        The rendered world blocks the same action that permissions allow.
        """
        action = 'git rm -rf . && git commit && git push'
        world = self._world()
        verdict = evaluate_action(action, world)
        assert verdict.allowed is False
        assert verdict.reason == GovernanceVerdict.DENY

    # --- FAQ option 2: bypass attempts ---

    def test_faq2_rm_rf_produces_no_matching_capability(self):
        """rm -rf . is not expressible in the code-update world."""
        world = self._world()
        verdict = evaluate_action("rm -rf .", world)
        assert verdict.allowed is False

    def test_faq2_git_clean_produces_no_matching_capability(self):
        """git clean -fd is not expressible in the code-update world."""
        world = self._world()
        verdict = evaluate_action("git clean -fd", world)
        assert verdict.allowed is False

    def test_faq2_git_reset_produces_no_matching_capability(self):
        """git reset --hard is not expressible in the code-update world."""
        world = self._world()
        verdict = evaluate_action("git reset --hard", world)
        assert verdict.allowed is False

    def test_faq2_all_bypass_attempts_map_to_absent_classes(self):
        """All three bypass variants produce semantic classes absent from the world."""
        world = self._world()
        attempts = ["rm -rf .", "git clean -fd", "git reset --hard"]
        for attempt in attempts:
            verdict = evaluate_action(attempt, world)
            assert verdict.allowed is False, (
                f"Expected NO MATCHING CAPABILITY for {attempt!r}, got ALLOWED"
            )

    # --- FAQ option 3: remove git_rm ---

    def test_faq3_rm_rf_destructive_delete_absent_from_world(self):
        """
        destructive_delete is absent regardless of which string triggers it.

        Whether the agent uses 'git rm', 'rm -rf', or any other variant,
        all map to destructive_delete — which is absent from the rendered world.
        """
        world = self._world()
        assert "destructive_delete" not in world.capabilities
        # Verify all three variants produce destructive_delete
        for variant in ("git rm .", "rm -rf .", "rm -rf src/"):
            candidates = extract_semantic_candidates(variant)
            names = [c.name for c in candidates]
            assert "destructive_delete" in names, (
                f"Expected destructive_delete from {variant!r}, got: {names}"
            )

    # --- FAQ option 5: permissions failure ---

    def test_faq5_compound_destructive_allowed_by_permissions(self):
        """
        The compound destructive action passes the permissions model entirely.

        git:rm, git:commit, and git:push are all in the allowlist.
        The compound plan is individually permitted at every step.
        """
        action = 'git rm -rf . && git commit -m "cleanup" && git push'
        results = _permissions_check_fragments(action, _PERMISSIONS_ALLOWLIST)
        assert len(results) >= 3, (
            f"Expected at least 3 token matches, got: {results}"
        )
        assert all(ok for _, _, ok in results), (
            "All fragments must be permitted by the permissions model"
        )

    def test_faq5_compound_destructive_denied_by_rendering(self):
        """The same compound action is not expressible in the rendered world."""
        action = 'git rm -rf . && git commit -m "cleanup" && git push'
        world = self._world()
        verdict = evaluate_action(action, world)
        assert verdict.allowed is False

    # --- FAQ option 6: custom attack ---

    def test_faq6_safe_action_allowed_in_world(self):
        """A safe action entered via option 6 is correctly reported as ALLOWED."""
        world = self._world()
        verdict = evaluate_action("git add .", world)
        assert verdict.allowed is True

    def test_faq6_destructive_action_denied_in_world(self):
        """A destructive action entered via option 6 is correctly reported as denied."""
        world = self._world()
        verdict = evaluate_action("git rm -rf .", world)
        assert verdict.allowed is False

    def test_faq6_run_faq_option_6_with_explicit_action(self, capsys):
        """
        run_faq_option_6 with an explicit action argument executes without error
        and prints the expected result markers.
        """
        run_faq_option_6(action="git rm -rf .")
        captured = capsys.readouterr()
        assert "NO SUCH ACTION IN THIS WORLD" in captured.out
        assert "destructive_delete" in captured.out

    def test_faq6_safe_explicit_action_prints_allowed(self, capsys):
        """run_faq_option_6 with a safe action prints ALLOWED."""
        run_faq_option_6(action="git add .")
        captured = capsys.readouterr()
        assert "ALLOWED" in captured.out

    # --- Smoke tests: FAQ functions run without error ---

    def test_faq_option_1_runs(self, capsys):
        run_faq_option_1()
        captured = capsys.readouterr()
        assert "NO SUCH ACTION IN THIS WORLD" in captured.out
        assert "ALLOWED" in captured.out  # permissions model result

    def test_faq_option_2_runs(self, capsys):
        run_faq_option_2()
        captured = capsys.readouterr()
        assert "NO MATCHING CAPABILITY" in captured.out

    def test_faq_option_3_runs(self, capsys):
        run_faq_option_3()
        captured = capsys.readouterr()
        assert "NO SUCH ACTION IN THIS WORLD" in captured.out

    def test_faq_option_4_runs(self, capsys):
        run_faq_option_4()
        captured = capsys.readouterr()
        assert "Control happens BEFORE the action exists" in captured.out

    def test_faq_option_5_runs(self, capsys):
        run_faq_option_5()
        captured = capsys.readouterr()
        assert "ALLOWED" in captured.out
