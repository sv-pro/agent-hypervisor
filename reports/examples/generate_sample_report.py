#!/usr/bin/env python3
"""
generate_sample_report.py — Generate sample policy tuner reports from synthetic data.

Run this to produce example JSON and Markdown reports showing what the
policy tuner produces on representative runtime data.

Usage:
    python reports/examples/generate_sample_report.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running from repo root
_REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from agent_hypervisor.policy_tuner import (
    PolicyAnalyzer,
    SuggestionGenerator,
    TunerReporter,
)

# ---------------------------------------------------------------------------
# Synthetic data representing a realistic deployment scenario
# ---------------------------------------------------------------------------

TRACES = [
    # Scenario 1: ask-email rule triggers frequently — routine email approvals
    *[
        {
            "trace_id": f"t-ask-email-{i:03d}",
            "timestamp": "2024-01-15T10:00:00Z",
            "tool": "send_email",
            "final_verdict": "ask",
            "matched_rule": "ask-email-declared-recipient",
            "policy_version": "v2",
            "arg_provenance": {"to": "user_declared:task_manifest", "subject": "system:hardcoded"},
        }
        for i in range(8)
    ],

    # Scenario 2: External recipient denied — the firewall is working
    *[
        {
            "trace_id": f"t-deny-external-{i:03d}",
            "timestamp": "2024-01-15T10:05:00Z",
            "tool": "send_email",
            "final_verdict": "deny",
            "matched_rule": "deny-email-external-recipient",
            "policy_version": "v2",
            "arg_provenance": {"to": f"external_document:doc{i}.txt"},
        }
        for i in range(5)
    ],

    # Scenario 3: Read file always allowed — no issues
    *[
        {
            "trace_id": f"t-allow-read-{i:03d}",
            "timestamp": "2024-01-15T10:10:00Z",
            "tool": "read_file",
            "final_verdict": "allow",
            "matched_rule": "allow-read-file",
            "policy_version": "v2",
            "arg_provenance": {"path": "user_declared:task_manifest"},
        }
        for i in range(12)
    ],

    # Scenario 4: HTTP POST allowed — repeated side-effect, warrants review
    *[
        {
            "trace_id": f"t-allow-http-{i:03d}",
            "timestamp": "2024-01-15T10:15:00Z",
            "tool": "http_post",
            "final_verdict": "allow",
            "matched_rule": "allow-http-post-declared",
            "policy_version": "v2",
            "arg_provenance": {
                "url": "user_declared:task_manifest",
                "body": f"derived:compute{i}",
            },
        }
        for i in range(6)
    ],

    # Scenario 5: One suspicious allow — external document reaching http_post
    {
        "trace_id": "t-risky-allow-001",
        "timestamp": "2024-01-15T10:20:00Z",
        "tool": "http_post",
        "final_verdict": "allow",
        "matched_rule": "allow-http-post-declared",
        "policy_version": "v2",
        "arg_provenance": {
            "url": "external_document:prompt_injection.html",
            "body": "system:template",
        },
    },

    # Scenario 6: Deny with heterogeneous provenance — catch-all smell
    *[
        {
            "trace_id": f"t-deny-broad-{i:03d}",
            "timestamp": "2024-01-15T10:25:00Z",
            "tool": "write_file",
            "final_verdict": "deny",
            "matched_rule": "deny-write-untrusted",
            "policy_version": "v1",
            "arg_provenance": {
                "path": "user_declared:task_manifest",
                "content": f"external_document:source{i}.txt",
            },
        }
        for i in range(4)
    ],

    # Scenario 7: Same rule active in older version (v1)
    *[
        {
            "trace_id": f"t-v1-ask-{i:03d}",
            "timestamp": "2024-01-10T08:00:00Z",
            "tool": "send_email",
            "final_verdict": "ask",
            "matched_rule": "ask-email-declared-recipient",
            "policy_version": "v1",
            "arg_provenance": {"to": "user_declared:task_manifest"},
        }
        for i in range(4)
    ],
]

APPROVALS = [
    # Scenario A: Same email approval shape approved many times by alice
    *[
        {
            "approval_id": f"ap-alice-{i:03d}",
            "tool": "send_email",
            "status": "approved",
            "matched_rule": "ask-email-declared-recipient",
            "policy_version": "v2",
            "actor": "alice",
            "arg_provenance": {
                "to": "user_declared:task_manifest",
                "subject": "system:hardcoded",
            },
        }
        for i in range(7)
    ],

    # Scenario B: HTTP post also approved repeatedly
    *[
        {
            "approval_id": f"ap-http-{i:03d}",
            "tool": "http_post",
            "status": "approved",
            "matched_rule": "ask-http-post-review",
            "policy_version": "v2",
            "actor": "bob",
            "arg_provenance": {
                "url": "user_declared:task_manifest",
                "body": "derived:report",
            },
        }
        for i in range(4)
    ],

    # Scenario C: Some pending approvals
    *[
        {
            "approval_id": f"ap-pending-{i:03d}",
            "tool": "send_email",
            "status": "pending",
            "matched_rule": "ask-email-declared-recipient",
            "policy_version": "v2",
            "actor": None,
            "arg_provenance": {"to": "user_declared:task_manifest"},
        }
        for i in range(2)
    ],

    # Scenario D: Repeated rejections — should be explicit deny
    *[
        {
            "approval_id": f"ap-reject-{i:03d}",
            "tool": "send_email",
            "status": "rejected",
            "matched_rule": "ask-email-declared-recipient",
            "policy_version": "v1",
            "actor": "alice",
            "arg_provenance": {
                "to": "user_declared:task_manifest",
                "body": "external_document:report.txt",
            },
        }
        for i in range(3)
    ],
]

POLICY_HISTORY = [
    {
        "version_id": "a1b2c3d4",
        "timestamp": "2024-01-08T00:00:00Z",
        "policy_file": "policies/default_policy.yaml",
        "content_hash": "a1b2c3d4" * 8,
        "rule_count": 6,
    },
    {
        "version_id": "e5f6a7b8",
        "timestamp": "2024-01-12T09:30:00Z",
        "policy_file": "policies/default_policy.yaml",
        "content_hash": "e5f6a7b8" * 8,
        "rule_count": 8,
    },
]


def main():
    out_dir = Path(__file__).parent

    analyzer = PolicyAnalyzer()
    report   = analyzer.analyze(TRACES, APPROVALS, POLICY_HISTORY)
    report   = SuggestionGenerator().generate(report)
    reporter = TunerReporter()

    # Write Markdown
    md_path = out_dir / "sample_policy_tuner_report.md"
    md_output = reporter.render(report, format="markdown")
    md_path.write_text(md_output, encoding="utf-8")
    print(f"Markdown report written to: {md_path}")

    # Write JSON
    json_path = out_dir / "sample_policy_tuner_report.json"
    json_output = reporter.render(report, format="json")
    json_path.write_text(json_output, encoding="utf-8")
    print(f"JSON report written to: {json_path}")

    # Summary
    data = json.loads(json_output)
    print(f"\nSummary:")
    print(f"  Traces:      {report.total_traces}")
    print(f"  Approvals:   {report.total_approvals}")
    print(f"  Versions:    {report.total_policy_versions}")
    print(f"  Signals:     {len(report.signals)}")
    print(f"  Smells:      {len(report.smells)}")
    print(f"  Suggestions: {len(report.suggestions)}")


if __name__ == "__main__":
    main()
