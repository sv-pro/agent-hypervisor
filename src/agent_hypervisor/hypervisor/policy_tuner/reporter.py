"""
reporter.py — Format TunerReport as JSON or Markdown text.

Two output formats:
  JSON     — machine-readable, full fidelity, suitable for tooling
  Markdown — human-readable summary for policy review sessions

Neither format triggers any action.  Reports are analysis artifacts
intended to support human policy review — not to drive automated changes.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Literal

from .models import Severity, TunerReport


# Severity ordering for sorting
_SEVERITY_ORDER = {Severity.high: 0, Severity.medium: 1, Severity.low: 2}


class TunerReporter:
    """
    Formats a TunerReport as JSON or Markdown.

    Usage:
        reporter = TunerReporter()
        print(reporter.render(report, format="markdown"))
        print(reporter.render(report, format="json"))
    """

    def render(
        self,
        report: TunerReport,
        format: Literal["json", "markdown"] = "markdown",
    ) -> str:
        if format == "json":
            return self._render_json(report)
        return self._render_markdown(report)

    # -----------------------------------------------------------------------
    # JSON
    # -----------------------------------------------------------------------

    def _render_json(self, report: TunerReport) -> str:
        data = report.to_dict()
        data["generated_at"] = datetime.now(timezone.utc).isoformat()
        return json.dumps(data, indent=2)

    # -----------------------------------------------------------------------
    # Markdown
    # -----------------------------------------------------------------------

    def _render_markdown(self, report: TunerReport) -> str:
        lines: list[str] = []
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        lines += [
            "# Policy Tuner Report",
            f"_Generated: {ts}_",
            "",
        ]

        # Summary
        lines += self._section_summary(report)

        # Top rules
        lines += self._section_top_rules(report)

        # Tuning signals
        lines += self._section_signals(report)

        # Policy smells
        lines += self._section_smells(report)

        # Suggestions
        lines += self._section_suggestions(report)

        lines.append("")
        lines.append("---")
        lines.append(
            "_This report is an analysis artifact. "
            "Suggestions must be reviewed by a human policy operator "
            "before any policy change is made._"
        )

        return "\n".join(lines)

    def _section_summary(self, report: TunerReport) -> list[str]:
        lines = [
            "## Summary",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Traces analyzed | {report.total_traces} |",
            f"| Approvals analyzed | {report.total_approvals} |",
            f"| Policy versions observed | {report.total_policy_versions} |",
        ]

        for verdict, count in sorted(report.verdict_counts.items()):
            lines.append(f"| Verdict: {verdict} | {count} |")

        lines += [
            "",
            f"| Output type | Count |",
            f"|-------------|-------|",
            f"| Tuning signals | {len(report.signals)} |",
            f"| Policy smells | {len(report.smells)} |",
            f"| Candidate suggestions | {len(report.suggestions)} |",
            "",
        ]

        # Signal severity breakdown
        high = sum(1 for s in report.signals if s.severity == Severity.high)
        med  = sum(1 for s in report.signals if s.severity == Severity.medium)
        low  = sum(1 for s in report.signals if s.severity == Severity.low)
        if report.signals:
            lines += [
                f"Signals by severity: **{high} high**, {med} medium, {low} low",
                "",
            ]

        return lines

    def _section_top_rules(self, report: TunerReport) -> list[str]:
        if not report.rule_verdict_counts:
            return []

        lines = ["## Rule Verdict Breakdown", ""]

        # Sort rules by total activity (desc)
        sorted_rules = sorted(
            report.rule_verdict_counts.items(),
            key=lambda kv: sum(kv[1].values()),
            reverse=True,
        )

        lines.append("| Rule | Allow | Ask | Deny | Total |")
        lines.append("|------|-------|-----|------|-------|")
        for rule, counts in sorted_rules[:15]:  # top 15
            allow = counts.get("allow", 0)
            ask   = counts.get("ask",   0)
            deny  = counts.get("deny",  0)
            total = allow + ask + deny
            lines.append(f"| `{rule}` | {allow} | {ask} | {deny} | {total} |")
        lines.append("")

        # Approval actor breakdown
        if report.approval_actor_counts:
            lines.append("### Approval Actors")
            lines.append("")
            lines.append("| Actor | Approval Count |")
            lines.append("|-------|----------------|")
            for actor, count in sorted(
                report.approval_actor_counts.items(),
                key=lambda kv: kv[1],
                reverse=True,
            ):
                lines.append(f"| {actor} | {count} |")
            lines.append("")

        return lines

    def _section_signals(self, report: TunerReport) -> list[str]:
        if not report.signals:
            return ["## Tuning Signals", "", "_No signals detected._", ""]

        lines = ["## Tuning Signals", ""]
        sorted_signals = sorted(
            report.signals,
            key=lambda s: (_SEVERITY_ORDER.get(s.severity, 9), s.category.value),
        )

        for sig in sorted_signals:
            severity_badge = _severity_badge(sig.severity)
            lines += [
                f"### {sig.id} — {sig.title}",
                "",
                f"**Category:** {sig.category.value}  "
                f"**Severity:** {severity_badge}",
                "",
                sig.description,
                "",
            ]
            if sig.related_rule:
                lines.append(f"**Related rule:** `{sig.related_rule}`")
            if sig.related_tools:
                lines.append(f"**Related tools:** {', '.join(f'`{t}`' for t in sig.related_tools)}")
            if sig.evidence:
                lines.append("")
                lines.append("**Evidence:**")
                lines.append("```")
                lines.append(json.dumps(sig.evidence[0], indent=2))
                lines.append("```")
            lines.append("")

        return lines

    def _section_smells(self, report: TunerReport) -> list[str]:
        if not report.smells:
            return ["## Policy Smells", "", "_No smells detected._", ""]

        lines = ["## Policy Smells", ""]
        sorted_smells = sorted(
            report.smells,
            key=lambda s: _SEVERITY_ORDER.get(s.severity, 9),
        )

        for smell in sorted_smells:
            severity_badge = _severity_badge(smell.severity)
            lines += [
                f"### {smell.id} — {smell.smell_type.value}",
                "",
                f"**Severity:** {severity_badge}",
                "",
                smell.description,
                "",
            ]
            if smell.evidence:
                lines.append("**Evidence:**")
                lines.append("```")
                lines.append(json.dumps(smell.evidence[0], indent=2))
                lines.append("```")
            lines.append("")

        return lines

    def _section_suggestions(self, report: TunerReport) -> list[str]:
        if not report.suggestions:
            return ["## Candidate Suggestions", "", "_No suggestions generated._", ""]

        lines = [
            "## Candidate Suggestions",
            "",
            "> **Important:** These are heuristic suggestions only.  "
            "A human policy operator must review each one before any change is made.",
            "",
        ]

        for sug in report.suggestions:
            confidence_badge = _severity_badge(sug.confidence)
            lines += [
                f"### {sug.id} — {sug.suggestion_type.value}",
                "",
                f"**Confidence:** {confidence_badge}",
                "",
                f"**Rationale:** {sug.rationale}",
                "",
                f"**Candidate action:** {sug.candidate_action}",
                "",
            ]
            if sug.related_rule:
                lines.append(f"**Related rule:** `{sug.related_rule}`")
            lines.append("")

        return lines


def _severity_badge(severity: Severity) -> str:
    badges = {
        Severity.high:   "🔴 high",
        Severity.medium: "🟡 medium",
        Severity.low:    "🟢 low",
    }
    return badges.get(severity, severity.value)
