"""
analyzer.py — Heuristic analysis of runtime data to detect tuning signals and smells.

Works offline against persisted traces, approvals, and policy history.
All heuristics are explicit and threshold-driven — no probabilistic models.

Threshold constants are defined at module level for easy tuning.

Signal detection passes:
  1. Friction signals    — repeated asks, denies, approvals on same pattern
  2. Risk signals        — allows on dangerous sinks, weak provenance
  3. Scope drift signals — task-scoped behavior across long-lived policy use
  4. Rule quality smells — broad allows, catch-all denies, approval-heavy rules

A single Analyzer instance is stateless after construction — call analyze()
with raw data loaded from the stores.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .models import (
    PolicySmell,
    Severity,
    SignalCategory,
    SmellType,
    TunerReport,
    TuningSignal,
)

# ---------------------------------------------------------------------------
# Threshold constants — adjust these to tune sensitivity
# ---------------------------------------------------------------------------

# Minimum count for a pattern to be considered a repeated signal
MIN_REPEAT_COUNT = 3

# Tools that carry outbound side-effect risk
SIDE_EFFECT_TOOLS = {"send_email", "http_post", "write_file", "post_slack", "webhook"}

# Provenance classes considered dangerous to allow through side-effect tools
RISKY_PROVENANCES = {"external_document", "derived"}

# Minimum number of distinct provenance shapes on one rule to flag breadth
MIN_PROVENANCE_DIVERSITY = 3

# Minimum approval count on a single rule/shape before flagging approval-heavy
MIN_APPROVAL_HEAVY_COUNT = MIN_REPEAT_COUNT

# Minimum number of distinct actors approving same shape to flag normalization
MIN_DISTINCT_ACTORS = 2


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _provenance_summary(arg_provenance: dict[str, str]) -> str:
    """Produce a stable string key from an arg_provenance dict."""
    return "|".join(f"{k}={v}" for k, v in sorted(arg_provenance.items()))


def _extract_provenances(arg_provenance: dict[str, str]) -> set[str]:
    """Return the set of provenance class tokens from an arg_provenance dict.

    Values may be like 'external_document:doc.txt' — we take the class part.
    """
    return {v.split(":")[0] for v in arg_provenance.values() if v}


def _has_risky_provenance(arg_provenance: dict[str, str]) -> bool:
    return bool(_extract_provenances(arg_provenance) & RISKY_PROVENANCES)


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------

class PolicyAnalyzer:
    """
    Analyzes persisted runtime data and populates a TunerReport.

    Usage:
        analyzer = PolicyAnalyzer()
        report = analyzer.analyze(traces, approvals, policy_history)
    """

    def analyze(
        self,
        traces: list[dict],
        approvals: list[dict],
        policy_history: list[dict],
    ) -> TunerReport:
        """
        Run all heuristic passes and return a populated TunerReport.

        Args:
            traces:         List of trace entry dicts from TraceStore.
            approvals:      List of approval record dicts from ApprovalStore.
            policy_history: List of policy version dicts from PolicyStore.
        """
        report = TunerReport()
        self._collect_summary(report, traces, approvals, policy_history)
        self._detect_friction_signals(report, traces, approvals)
        self._detect_risk_signals(report, traces)
        self._detect_scope_drift_signals(report, traces, approvals, policy_history)
        self._detect_rule_quality_smells(report, traces, approvals)
        return report

    # -----------------------------------------------------------------------
    # Pass 0: Summary metrics
    # -----------------------------------------------------------------------

    def _collect_summary(
        self,
        report: TunerReport,
        traces: list[dict],
        approvals: list[dict],
        policy_history: list[dict],
    ) -> None:
        report.total_traces = len(traces)
        report.total_approvals = len(approvals)
        report.total_policy_versions = len(policy_history)

        verdict_counts: Counter[str] = Counter()
        rule_verdict: dict[str, Counter[str]] = defaultdict(Counter)

        for t in traces:
            v = t.get("final_verdict", "unknown")
            verdict_counts[v] += 1
            rule = t.get("matched_rule", "")
            if rule:
                rule_verdict[rule][v] += 1

        report.verdict_counts = dict(verdict_counts)
        report.rule_verdict_counts = {
            rule: dict(counts) for rule, counts in rule_verdict.items()
        }

        actor_counts: Counter[str] = Counter()
        for a in approvals:
            actor = a.get("actor") or a.get("approved_by", "")
            if actor:
                actor_counts[actor] += 1
        report.approval_actor_counts = dict(actor_counts)

    # -----------------------------------------------------------------------
    # Pass 1: Friction signals
    # -----------------------------------------------------------------------

    def _detect_friction_signals(
        self,
        report: TunerReport,
        traces: list[dict],
        approvals: list[dict],
    ) -> None:
        sig_id = self._sig_counter(report)

        # 1a. Repeated ask on same rule
        ask_by_rule: Counter[str] = Counter()
        for t in traces:
            if t.get("final_verdict") == "ask":
                rule = t.get("matched_rule", "")
                if rule:
                    ask_by_rule[rule] += 1

        for rule, count in ask_by_rule.items():
            if count >= MIN_REPEAT_COUNT:
                report.signals.append(TuningSignal(
                    id=next(sig_id),
                    category=SignalCategory.friction,
                    severity=Severity.medium,
                    title=f"Repeated ask on rule '{rule}'",
                    description=(
                        f"Rule '{rule}' has triggered an 'ask' verdict {count} times. "
                        "Frequent asks on the same rule suggest the policy may need "
                        "narrowing (to allow a known-safe pattern) or explicit scoped "
                        "approval promotion."
                    ),
                    evidence=[{"rule": rule, "ask_count": count}],
                    related_rule=rule,
                ))

        # 1b. Repeated deny on same rule
        deny_by_rule: Counter[str] = Counter()
        for t in traces:
            if t.get("final_verdict") == "deny":
                rule = t.get("matched_rule", "")
                if rule:
                    deny_by_rule[rule] += 1

        for rule, count in deny_by_rule.items():
            if count >= MIN_REPEAT_COUNT:
                report.signals.append(TuningSignal(
                    id=next(sig_id),
                    category=SignalCategory.friction,
                    severity=Severity.low,
                    title=f"Repeated deny on rule '{rule}'",
                    description=(
                        f"Rule '{rule}' has denied {count} requests. High deny counts "
                        "may indicate legitimate use cases being blocked — review whether "
                        "the rule is too broad or if a safe sub-pattern should be allowed."
                    ),
                    evidence=[{"rule": rule, "deny_count": count}],
                    related_rule=rule,
                ))

        # 1c. Repeated manual approvals on same request shape (tool + prov summary)
        approval_shape_count: Counter[str] = Counter()
        approval_shape_evidence: dict[str, list[str]] = defaultdict(list)

        for a in approvals:
            if a.get("status") in ("approved", "executed"):
                tool = a.get("tool", "")
                prov = _provenance_summary(a.get("arg_provenance", {}))
                shape_key = f"{tool}|{prov}"
                approval_shape_count[shape_key] += 1
                approval_shape_evidence[shape_key].append(a.get("approval_id", ""))

        for shape_key, count in approval_shape_count.items():
            if count >= MIN_REPEAT_COUNT:
                tool_name = shape_key.split("|")[0]
                report.signals.append(TuningSignal(
                    id=next(sig_id),
                    category=SignalCategory.friction,
                    severity=Severity.medium,
                    title=f"Repeated manual approvals for '{tool_name}'",
                    description=(
                        f"The same request shape for '{tool_name}' has been manually "
                        f"approved {count} times. Repeated approvals on the same shape "
                        "suggest the exception has become routine — consider promoting "
                        "it to explicit scoped policy."
                    ),
                    evidence=[{
                        "shape": shape_key,
                        "approval_count": count,
                        "approval_ids": approval_shape_evidence[shape_key][:5],
                    }],
                    related_tools=[tool_name],
                ))

        # 1d. Repeated manual rejections on same shape
        rejection_shape_count: Counter[str] = Counter()
        for a in approvals:
            if a.get("status") == "rejected":
                tool = a.get("tool", "")
                prov = _provenance_summary(a.get("arg_provenance", {}))
                shape_key = f"{tool}|{prov}"
                rejection_shape_count[shape_key] += 1

        for shape_key, count in rejection_shape_count.items():
            if count >= MIN_REPEAT_COUNT:
                tool_name = shape_key.split("|")[0]
                report.signals.append(TuningSignal(
                    id=next(sig_id),
                    category=SignalCategory.friction,
                    severity=Severity.medium,
                    title=f"Repeated manual rejections for '{tool_name}'",
                    description=(
                        f"The same request shape for '{tool_name}' has been manually "
                        f"rejected {count} times. This pattern should be encoded as an "
                        "explicit deny rule rather than relying on repeated human rejection."
                    ),
                    evidence=[{"shape": shape_key, "rejection_count": count}],
                    related_tools=[tool_name],
                ))

    # -----------------------------------------------------------------------
    # Pass 2: Risk signals
    # -----------------------------------------------------------------------

    def _detect_risk_signals(
        self,
        report: TunerReport,
        traces: list[dict],
    ) -> None:
        sig_id = self._sig_counter(report)

        # 2a. Repeated allow on dangerous (side-effect) tool
        allow_side_effect: dict[str, list[dict]] = defaultdict(list)
        for t in traces:
            if (
                t.get("final_verdict") == "allow"
                and t.get("tool") in SIDE_EFFECT_TOOLS
            ):
                allow_side_effect[t["tool"]].append(t)

        for tool, tool_traces in allow_side_effect.items():
            count = len(tool_traces)
            if count >= MIN_REPEAT_COUNT:
                versions = list({t.get("policy_version", "") for t in tool_traces if t.get("policy_version")})
                report.signals.append(TuningSignal(
                    id=next(sig_id),
                    category=SignalCategory.risk,
                    severity=Severity.high,
                    title=f"Repeated allow on side-effect tool '{tool}'",
                    description=(
                        f"Tool '{tool}' (a side-effect tool) has been allowed {count} "
                        "times. Review whether all of these executions were intentional "
                        "and confirm the provenance constraints are sufficient."
                    ),
                    evidence=[{
                        "tool": tool,
                        "allow_count": count,
                        "sample_trace_ids": [t.get("trace_id", "") for t in tool_traces[:3]],
                    }],
                    related_tools=[tool],
                    related_policy_versions=versions,
                ))

        # 2b. Allow on side-effect tool with risky provenance
        risky_allows: dict[str, list[dict]] = defaultdict(list)
        for t in traces:
            if (
                t.get("final_verdict") == "allow"
                and t.get("tool") in SIDE_EFFECT_TOOLS
                and _has_risky_provenance(t.get("arg_provenance", {}))
            ):
                risky_allows[t["tool"]].append(t)

        for tool, tool_traces in risky_allows.items():
            count = len(tool_traces)
            prov_shapes = {
                _provenance_summary(t.get("arg_provenance", {}))
                for t in tool_traces
            }
            report.signals.append(TuningSignal(
                id=next(sig_id),
                category=SignalCategory.risk,
                severity=Severity.high,
                title=f"Allow on side-effect tool '{tool}' with external/derived provenance",
                description=(
                    f"Tool '{tool}' was allowed {count} time(s) with arguments derived "
                    "from external_document or derived provenance. This may indicate "
                    "insufficient provenance constraints or an overly broad allow rule."
                ),
                evidence=[{
                    "tool": tool,
                    "count": count,
                    "provenance_shapes": list(prov_shapes)[:5],
                }],
                related_tools=[tool],
            ))

        # 2c. Broad allow on heterogeneous provenance (one rule allows many prov shapes)
        rule_prov_shapes: dict[str, set[str]] = defaultdict(set)
        for t in traces:
            if t.get("final_verdict") == "allow":
                rule = t.get("matched_rule", "")
                prov = _provenance_summary(t.get("arg_provenance", {}))
                if rule:
                    rule_prov_shapes[rule].add(prov)

        for rule, shapes in rule_prov_shapes.items():
            if len(shapes) >= MIN_PROVENANCE_DIVERSITY:
                report.signals.append(TuningSignal(
                    id=next(sig_id),
                    category=SignalCategory.risk,
                    severity=Severity.medium,
                    title=f"Broad allow rule '{rule}' matches heterogeneous provenance",
                    description=(
                        f"Rule '{rule}' has allowed requests with {len(shapes)} distinct "
                        "provenance shapes. A single rule covering many different provenance "
                        "patterns may be too permissive — consider splitting into narrower rules."
                    ),
                    evidence=[{
                        "rule": rule,
                        "distinct_provenance_shapes": len(shapes),
                        "sample_shapes": list(shapes)[:3],
                    }],
                    related_rule=rule,
                ))

    # -----------------------------------------------------------------------
    # Pass 3: Scope / lifecycle drift signals
    # -----------------------------------------------------------------------

    def _detect_scope_drift_signals(
        self,
        report: TunerReport,
        traces: list[dict],
        approvals: list[dict],
        policy_history: list[dict],
    ) -> None:
        sig_id = self._sig_counter(report)

        # 3a. Same rule used across many policy versions (rule outlived version changes)
        rule_versions: dict[str, set[str]] = defaultdict(set)
        for t in traces:
            rule = t.get("matched_rule", "")
            version = t.get("policy_version", "")
            if rule and version:
                rule_versions[rule].add(version)

        # Flag rules present across all observed versions (may have fossilized)
        n_versions = len(policy_history)
        if n_versions >= 2:
            for rule, versions in rule_versions.items():
                if len(versions) >= n_versions:
                    report.signals.append(TuningSignal(
                        id=next(sig_id),
                        category=SignalCategory.scope_drift,
                        severity=Severity.low,
                        title=f"Rule '{rule}' spans all observed policy versions",
                        description=(
                            f"Rule '{rule}' appears in traces across all {n_versions} "
                            "observed policy versions. A rule that survives every policy "
                            "update may encode long-lived scope that should be reviewed — "
                            "especially if it was originally intended as temporary."
                        ),
                        evidence=[{
                            "rule": rule,
                            "versions_seen": list(versions),
                            "total_policy_versions": n_versions,
                        }],
                        related_rule=rule,
                        related_policy_versions=list(versions),
                    ))

        # 3b. Repeated approvals suggest a temporary exception became routine
        # (already partially covered in friction; here we focus on policy version drift)
        approval_rule_counts: Counter[str] = Counter()
        approval_rule_versions: dict[str, set[str]] = defaultdict(set)
        for a in approvals:
            if a.get("status") in ("approved", "executed"):
                rule = a.get("matched_rule", "")
                version = a.get("policy_version", "")
                if rule:
                    approval_rule_counts[rule] += 1
                    if version:
                        approval_rule_versions[rule].add(version)

        for rule, count in approval_rule_counts.items():
            versions = approval_rule_versions[rule]
            if count >= MIN_REPEAT_COUNT and len(versions) >= 2:
                report.signals.append(TuningSignal(
                    id=next(sig_id),
                    category=SignalCategory.scope_drift,
                    severity=Severity.medium,
                    title=f"Approval pattern for rule '{rule}' spans multiple policy versions",
                    description=(
                        f"Rule '{rule}' has been approved {count} time(s) across "
                        f"{len(versions)} policy versions. This pattern suggests a "
                        "temporary exception has become a routine workflow that may "
                        "benefit from explicit policy encoding."
                    ),
                    evidence=[{
                        "rule": rule,
                        "approval_count": count,
                        "policy_versions": list(versions),
                    }],
                    related_rule=rule,
                    related_policy_versions=list(versions),
                ))

        # 3c. Same actor repeatedly approving the same shape — normalization risk
        actor_shape: dict[str, Counter[str]] = defaultdict(Counter)
        for a in approvals:
            if a.get("status") in ("approved", "executed"):
                actor = a.get("actor") or a.get("approved_by", "")
                if not actor:
                    continue
                tool = a.get("tool", "")
                prov = _provenance_summary(a.get("arg_provenance", {}))
                actor_shape[actor][f"{tool}|{prov}"] += 1

        for actor, shape_counts in actor_shape.items():
            for shape, count in shape_counts.items():
                if count >= MIN_REPEAT_COUNT:
                    tool_name = shape.split("|")[0]
                    report.signals.append(TuningSignal(
                        id=next(sig_id),
                        category=SignalCategory.scope_drift,
                        severity=Severity.low,
                        title=f"Actor '{actor}' repeatedly approves same shape for '{tool_name}'",
                        description=(
                            f"Actor '{actor}' has approved the same request shape for "
                            f"'{tool_name}' {count} times. Repeated approvals by the same "
                            "reviewer on the same shape may indicate approval fatigue or "
                            "normalization — consider explicit policy encoding."
                        ),
                        evidence=[{
                            "actor": actor,
                            "shape": shape,
                            "approval_count": count,
                        }],
                        related_tools=[tool_name],
                    ))

    # -----------------------------------------------------------------------
    # Pass 4: Rule quality / policy smell detection
    # -----------------------------------------------------------------------

    def _detect_rule_quality_smells(
        self,
        report: TunerReport,
        traces: list[dict],
        approvals: list[dict],
    ) -> None:
        smell_id = self._smell_counter(report)

        # 4a. Broad allow on dangerous sink
        for rule, verdicts in report.rule_verdict_counts.items():
            allow_count = verdicts.get("allow", 0)
            if allow_count < MIN_REPEAT_COUNT:
                continue
            # Check if any of those allows were on side-effect tools
            rule_tools = {
                t.get("tool", "")
                for t in traces
                if t.get("matched_rule") == rule and t.get("final_verdict") == "allow"
            }
            if rule_tools & SIDE_EFFECT_TOOLS:
                report.smells.append(PolicySmell(
                    id=next(smell_id),
                    smell_type=SmellType.broad_allow_dangerous_sink,
                    severity=Severity.high,
                    description=(
                        f"Rule '{rule}' has allowed {allow_count} executions on side-effect "
                        f"tool(s) {rule_tools & SIDE_EFFECT_TOOLS}. Broad allow on a "
                        "dangerous sink warrants review — scope may be too wide."
                    ),
                    evidence=[{
                        "rule": rule,
                        "allow_count": allow_count,
                        "side_effect_tools": list(rule_tools & SIDE_EFFECT_TOOLS),
                    }],
                ))

        # 4b. Catch-all deny on heterogeneous cases
        for rule, verdicts in report.rule_verdict_counts.items():
            deny_count = verdicts.get("deny", 0)
            if deny_count < MIN_REPEAT_COUNT:
                continue
            # Check provenance diversity on this deny rule
            deny_prov_shapes = {
                _provenance_summary(t.get("arg_provenance", {}))
                for t in traces
                if t.get("matched_rule") == rule and t.get("final_verdict") == "deny"
            }
            if len(deny_prov_shapes) >= MIN_PROVENANCE_DIVERSITY:
                report.smells.append(PolicySmell(
                    id=next(smell_id),
                    smell_type=SmellType.catch_all_deny_heterogeneous,
                    severity=Severity.medium,
                    description=(
                        f"Rule '{rule}' denies {deny_count} requests across "
                        f"{len(deny_prov_shapes)} distinct provenance shapes. A single "
                        "deny rule matching many different patterns may be a catch-all — "
                        "consider whether distinct sub-patterns need different handling."
                    ),
                    evidence=[{
                        "rule": rule,
                        "deny_count": deny_count,
                        "distinct_shapes": len(deny_prov_shapes),
                    }],
                ))

        # 4c. Approval-heavy rule — ask is the dominant verdict
        for rule, verdicts in report.rule_verdict_counts.items():
            ask_count = verdicts.get("ask", 0)
            total = sum(verdicts.values())
            if ask_count >= MIN_APPROVAL_HEAVY_COUNT and total > 0:
                ask_ratio = ask_count / total
                if ask_ratio > 0.7:
                    report.smells.append(PolicySmell(
                        id=next(smell_id),
                        smell_type=SmellType.approval_heavy_rule,
                        severity=Severity.medium,
                        description=(
                            f"Rule '{rule}' routes {ask_count}/{total} ({ask_ratio:.0%}) "
                            "of its verdicts to 'ask'. A rule that almost always asks may "
                            "need narrowing (to allow safe sub-patterns) or splitting "
                            "to reduce approval load."
                        ),
                        evidence=[{
                            "rule": rule,
                            "ask_count": ask_count,
                            "total": total,
                            "ask_ratio": round(ask_ratio, 2),
                        }],
                    ))

        # 4d. Allow with many different provenance shapes (one rule covers too much)
        rule_prov_shapes: dict[str, set[str]] = defaultdict(set)
        for t in traces:
            rule = t.get("matched_rule", "")
            if rule and t.get("final_verdict") == "allow":
                rule_prov_shapes[rule].add(
                    _provenance_summary(t.get("arg_provenance", {}))
                )

        for rule, shapes in rule_prov_shapes.items():
            if len(shapes) >= MIN_PROVENANCE_DIVERSITY:
                report.smells.append(PolicySmell(
                    id=next(smell_id),
                    smell_type=SmellType.one_rule_many_provenance_shapes,
                    severity=Severity.medium,
                    description=(
                        f"Rule '{rule}' matches {len(shapes)} distinct provenance shapes "
                        "in allow verdicts. One rule covering many different provenance "
                        "patterns may be encoding unrelated use cases — consider splitting."
                    ),
                    evidence=[{
                        "rule": rule,
                        "distinct_allow_shapes": len(shapes),
                        "sample_shapes": list(shapes)[:3],
                    }],
                ))

        # 4e. Allow on side-effect tool with weak (external_document) provenance
        for t in traces:
            if (
                t.get("final_verdict") == "allow"
                and t.get("tool") in SIDE_EFFECT_TOOLS
            ):
                prov_classes = _extract_provenances(t.get("arg_provenance", {}))
                if "external_document" in prov_classes:
                    rule = t.get("matched_rule", "")
                    report.smells.append(PolicySmell(
                        id=next(smell_id),
                        smell_type=SmellType.allow_side_effect_weak_provenance,
                        severity=Severity.high,
                        description=(
                            f"A '{t.get('tool')}' execution was allowed with "
                            "external_document provenance in its arguments. This is a "
                            "high-risk pattern — arguments from external documents "
                            "reaching side-effect tools may indicate prompt injection risk."
                        ),
                        evidence=[{
                            "trace_id": t.get("trace_id", ""),
                            "tool": t.get("tool", ""),
                            "arg_provenance": t.get("arg_provenance", {}),
                            "rule": rule,
                        }],
                    ))

    # -----------------------------------------------------------------------
    # Counter generators
    # -----------------------------------------------------------------------

    def _sig_counter(self, report: TunerReport):
        """Return a generator that produces incrementing signal ids."""
        def _gen():
            n = len(report.signals) + 1
            while True:
                yield f"sig-{n:03d}"
                n += 1
        return _gen()

    def _smell_counter(self, report: TunerReport):
        """Return a generator that produces incrementing smell ids."""
        def _gen():
            n = len(report.smells) + 1
            while True:
                yield f"smell-{n:03d}"
                n += 1
        return _gen()
