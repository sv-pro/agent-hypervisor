"""
suggestions.py — Generate conservative candidate suggestions from tuning signals and smells.

Suggestions are heuristic and conservative.  They describe candidate actions
for human policy operators to review — they are NEVER applied automatically.

Each suggestion is linked to one or more signals or smells that motivated it.
Confidence levels reflect how confident the heuristic is:
  high   — pattern is clear and well-evidenced
  medium — pattern is plausible but may have legitimate explanations
  low    — speculative; requires careful review before acting
"""

from __future__ import annotations

from .models import (
    PolicySmell,
    Severity,
    SmellType,
    Suggestion,
    SuggestionType,
    TunerReport,
    TuningSignal,
    SignalCategory,
)


class SuggestionGenerator:
    """
    Generates candidate suggestions from detected signals and smells.

    Usage:
        gen = SuggestionGenerator()
        report = gen.generate(report)   # mutates report.suggestions in place
    """

    def generate(self, report: TunerReport) -> TunerReport:
        """Populate report.suggestions from its signals and smells."""
        sug_id = self._sug_counter(report)

        for signal in report.signals:
            self._suggest_for_signal(report, signal, sug_id)

        for smell in report.smells:
            self._suggest_for_smell(report, smell, sug_id)

        return report

    # -----------------------------------------------------------------------
    # Signal → suggestion mapping
    # -----------------------------------------------------------------------

    def _suggest_for_signal(
        self,
        report: TunerReport,
        signal: TuningSignal,
        sug_id,
    ) -> None:
        category = signal.category
        title = signal.title

        if category == SignalCategory.friction:
            if "repeated ask" in title.lower():
                rule = signal.related_rule
                report.suggestions.append(Suggestion(
                    id=next(sug_id),
                    suggestion_type=SuggestionType.narrow_rule_scope,
                    rationale=signal.description,
                    candidate_action=(
                        f"Review rule '{rule}'. If a specific provenance+tool pattern "
                        "is consistently approved, consider adding a narrower allow rule "
                        "for that pattern to reduce approval friction."
                    ),
                    related_rule=rule,
                    confidence=Severity.medium,
                ))
                report.suggestions.append(Suggestion(
                    id=next(sug_id),
                    suggestion_type=SuggestionType.promote_approval_to_policy,
                    rationale=(
                        f"Rule '{rule}' triggers repeated asks. If the approved pattern "
                        "is consistently safe, promote it to an explicit allow in a "
                        "scoped task overlay."
                    ),
                    candidate_action=(
                        f"Audit approvals linked to rule '{rule}'. If all share the same "
                        "provenance pattern, encode that pattern as an explicit allow in "
                        "a task-scoped overlay policy."
                    ),
                    related_rule=rule,
                    confidence=Severity.low,
                ))

            elif "repeated deny" in title.lower():
                rule = signal.related_rule
                report.suggestions.append(Suggestion(
                    id=next(sug_id),
                    suggestion_type=SuggestionType.split_broad_rule,
                    rationale=signal.description,
                    candidate_action=(
                        f"Review rule '{rule}'. If some denied cases are legitimate use, "
                        "split the rule into a narrower deny and a separate allow for "
                        "the safe sub-pattern."
                    ),
                    related_rule=rule,
                    confidence=Severity.medium,
                ))

            elif "repeated manual approvals" in title.lower():
                tools = signal.related_tools
                tool = tools[0] if tools else ""
                report.suggestions.append(Suggestion(
                    id=next(sug_id),
                    suggestion_type=SuggestionType.promote_approval_to_policy,
                    rationale=signal.description,
                    candidate_action=(
                        f"The repeated approval pattern for '{tool}' has become routine. "
                        "Consider encoding the approved shape as explicit policy in a "
                        "task-scoped overlay to reduce manual approval load."
                    ),
                    related_rule=signal.related_rule,
                    confidence=Severity.medium,
                ))

            elif "repeated manual rejections" in title.lower():
                tools = signal.related_tools
                tool = tools[0] if tools else ""
                report.suggestions.append(Suggestion(
                    id=next(sug_id),
                    suggestion_type=SuggestionType.narrow_rule_scope,
                    rationale=signal.description,
                    candidate_action=(
                        f"The rejected pattern for '{tool}' should be encoded as an "
                        "explicit deny rule. This removes reliance on repeated human "
                        "rejection and makes the policy intent clear."
                    ),
                    related_rule=signal.related_rule,
                    confidence=Severity.high,
                ))

        elif category == SignalCategory.risk:
            if "repeated allow on side-effect" in title.lower():
                tools = signal.related_tools
                tool = tools[0] if tools else ""
                report.suggestions.append(Suggestion(
                    id=next(sug_id),
                    suggestion_type=SuggestionType.add_approval_requirement,
                    rationale=signal.description,
                    candidate_action=(
                        f"Add an approval requirement to the rule(s) allowing '{tool}'. "
                        "Repeated side-effect executions warrant human oversight unless "
                        "the provenance constraints are very tight."
                    ),
                    related_rule=signal.related_rule,
                    confidence=Severity.medium,
                ))

            elif "risky provenance" in title.lower() or "external/derived" in title.lower():
                tools = signal.related_tools
                tool = tools[0] if tools else ""
                report.suggestions.append(Suggestion(
                    id=next(sug_id),
                    suggestion_type=SuggestionType.reduce_allow_constrain_provenance,
                    rationale=signal.description,
                    candidate_action=(
                        f"Tighten the provenance constraint for '{tool}' allows. "
                        "Require user_declared or system provenance on sensitive arguments. "
                        "Reject or escalate requests where arguments trace to external_document."
                    ),
                    related_rule=signal.related_rule,
                    confidence=Severity.high,
                ))

            elif "heterogeneous provenance" in title.lower():
                rule = signal.related_rule
                report.suggestions.append(Suggestion(
                    id=next(sug_id),
                    suggestion_type=SuggestionType.split_broad_rule,
                    rationale=signal.description,
                    candidate_action=(
                        f"Split rule '{rule}' into multiple narrower rules, one per "
                        "provenance class or role combination. This makes the policy "
                        "intent explicit and reduces unintended coverage."
                    ),
                    related_rule=rule,
                    confidence=Severity.medium,
                ))

        elif category == SignalCategory.scope_drift:
            if "spans all observed policy versions" in title.lower():
                rule = signal.related_rule
                report.suggestions.append(Suggestion(
                    id=next(sug_id),
                    suggestion_type=SuggestionType.add_review_metadata,
                    rationale=signal.description,
                    candidate_action=(
                        f"Add a review comment or metadata tag to rule '{rule}' explaining "
                        "why it is long-lived and what use cases it is intended to cover. "
                        "If it was originally temporary, mark it as temporary."
                    ),
                    related_rule=rule,
                    confidence=Severity.low,
                ))

            elif "spans multiple policy versions" in title.lower():
                rule = signal.related_rule
                report.suggestions.append(Suggestion(
                    id=next(sug_id),
                    suggestion_type=SuggestionType.move_to_task_overlay,
                    rationale=signal.description,
                    candidate_action=(
                        f"The approval pattern for rule '{rule}' spans multiple policy "
                        "versions and may have started as a temporary exception. Consider "
                        "moving this behavior from the base policy into a task-scoped "
                        "overlay policy with explicit scope bounds."
                    ),
                    related_rule=rule,
                    confidence=Severity.medium,
                ))

            elif "repeatedly approves same shape" in title.lower():
                tools = signal.related_tools
                tool = tools[0] if tools else ""
                report.suggestions.append(Suggestion(
                    id=next(sug_id),
                    suggestion_type=SuggestionType.promote_approval_to_policy,
                    rationale=signal.description,
                    candidate_action=(
                        f"Encode the repeatedly approved '{tool}' pattern as explicit "
                        "policy to reduce approval fatigue. Review the actor's approvals "
                        "to confirm the pattern is consistently safe before encoding."
                    ),
                    related_rule=signal.related_rule,
                    confidence=Severity.low,
                ))

    # -----------------------------------------------------------------------
    # Smell → suggestion mapping
    # -----------------------------------------------------------------------

    def _suggest_for_smell(
        self,
        report: TunerReport,
        smell: PolicySmell,
        sug_id,
    ) -> None:
        smell_type = smell.smell_type

        if smell_type == SmellType.broad_allow_dangerous_sink:
            rule = smell.evidence[0].get("rule", "") if smell.evidence else ""
            report.suggestions.append(Suggestion(
                id=next(sug_id),
                suggestion_type=SuggestionType.narrow_rule_scope,
                rationale=smell.description,
                candidate_action=(
                    f"Narrow the scope of rule '{rule}' by tightening provenance, "
                    "role, or argument constraints. Ensure it only covers the minimum "
                    "necessary pattern for the intended use case."
                ),
                related_rule=rule,
                confidence=Severity.high,
            ))

        elif smell_type == SmellType.catch_all_deny_heterogeneous:
            rule = smell.evidence[0].get("rule", "") if smell.evidence else ""
            report.suggestions.append(Suggestion(
                id=next(sug_id),
                suggestion_type=SuggestionType.split_broad_rule,
                rationale=smell.description,
                candidate_action=(
                    f"Review deny rule '{rule}'. If it catches heterogeneous patterns, "
                    "split into distinct deny rules with explanatory comments for each "
                    "sub-pattern. This improves policy clarity and auditability."
                ),
                related_rule=rule,
                confidence=Severity.medium,
            ))
            report.suggestions.append(Suggestion(
                id=next(sug_id),
                suggestion_type=SuggestionType.improve_rule_explanation,
                rationale=smell.description,
                candidate_action=(
                    f"Add a description or rationale comment to rule '{rule}' explaining "
                    "what threat or use case it is blocking. This aids future review."
                ),
                related_rule=rule,
                confidence=Severity.low,
            ))

        elif smell_type == SmellType.approval_heavy_rule:
            rule = smell.evidence[0].get("rule", "") if smell.evidence else ""
            report.suggestions.append(Suggestion(
                id=next(sug_id),
                suggestion_type=SuggestionType.narrow_rule_scope,
                rationale=smell.description,
                candidate_action=(
                    f"Rule '{rule}' triggers approval for most requests. Identify "
                    "provenance patterns that are consistently safe and add a narrower "
                    "allow rule for those patterns. Keep the ask for genuinely ambiguous cases."
                ),
                related_rule=rule,
                confidence=Severity.medium,
            ))

        elif smell_type == SmellType.one_rule_many_provenance_shapes:
            rule = smell.evidence[0].get("rule", "") if smell.evidence else ""
            report.suggestions.append(Suggestion(
                id=next(sug_id),
                suggestion_type=SuggestionType.split_broad_rule,
                rationale=smell.description,
                candidate_action=(
                    f"Rule '{rule}' covers many distinct provenance patterns. Split it "
                    "into one rule per provenance class or role combination, with explicit "
                    "descriptions of the intended use case for each."
                ),
                related_rule=rule,
                confidence=Severity.medium,
            ))

        elif smell_type == SmellType.allow_side_effect_weak_provenance:
            evidence = smell.evidence[0] if smell.evidence else {}
            tool = evidence.get("tool", "")
            rule = evidence.get("rule", "")
            report.suggestions.append(Suggestion(
                id=next(sug_id),
                suggestion_type=SuggestionType.reduce_allow_constrain_provenance,
                rationale=smell.description,
                candidate_action=(
                    f"Review how '{tool}' is allowed with external_document provenance. "
                    "If this is a policy error, tighten the provenance constraint "
                    f"on rule '{rule}' to require user_declared or system provenance. "
                    "If intentional, add a documented exception with review metadata."
                ),
                related_rule=rule,
                confidence=Severity.high,
            ))

    # -----------------------------------------------------------------------
    # Counter generator
    # -----------------------------------------------------------------------

    def _sug_counter(self, report: TunerReport):
        def _gen():
            n = len(report.suggestions) + 1
            while True:
                yield f"sug-{n:03d}"
                n += 1
        return _gen()
