#!/usr/bin/env python3
"""
run_policy_tuner.py — CLI entrypoint for the trace-driven policy tuner.

Reads persisted runtime data from storage, runs the policy analyzer and
suggestion generator, and prints a human-readable report.

Usage:
    python scripts/run_policy_tuner.py
    python scripts/run_policy_tuner.py --format json
    python scripts/run_policy_tuner.py --format markdown
    python scripts/run_policy_tuner.py --output reports/policy_tuner_report.md
    python scripts/run_policy_tuner.py --format json --output reports/report.json
    python scripts/run_policy_tuner.py --data-dir /path/to/custom/.data

Options:
    --format      Output format: markdown (default) or json
    --output      Write output to this file path (also prints to stdout)
    --data-dir    Path to the data directory containing traces.jsonl,
                  approvals/, and policy_history.jsonl (default: .data)
    --trace-limit Max number of trace entries to load (default: 5000)
    --no-color    Disable colored terminal output
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running from repo root without installing
_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from agent_hypervisor.policy_tuner import (
    PolicyAnalyzer,
    SuggestionGenerator,
    TunerReporter,
)
from agent_hypervisor.storage.approval_store import ApprovalStore
from agent_hypervisor.storage.policy_store import PolicyStore
from agent_hypervisor.storage.trace_store import TraceStore


def load_data(
    data_dir: Path,
    trace_limit: int,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Load traces, approvals, and policy history from the data directory."""
    trace_path    = data_dir / "traces.jsonl"
    approval_dir  = data_dir / "approvals"
    policy_path   = data_dir / "policy_history.jsonl"

    trace_store   = TraceStore(trace_path)
    approval_store = ApprovalStore(approval_dir)
    policy_store  = PolicyStore(policy_path)

    traces         = trace_store.list_recent(limit=trace_limit)
    approvals      = approval_store.list_recent(limit=10_000)
    policy_history = policy_store.get_history(limit=100)

    return traces, approvals, policy_history


def print_data_summary(
    traces: list[dict],
    approvals: list[dict],
    policy_history: list[dict],
) -> None:
    print(f"[policy-tuner] Loaded {len(traces)} traces, "
          f"{len(approvals)} approvals, "
          f"{len(policy_history)} policy versions",
          file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze runtime traces and produce policy tuning recommendations.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="Write output to this file (also prints to stdout)",
    )
    parser.add_argument(
        "--data-dir",
        metavar="DIR",
        default=".data",
        help="Path to data directory (default: .data)",
    )
    parser.add_argument(
        "--trace-limit",
        metavar="N",
        type=int,
        default=5000,
        help="Max trace entries to load (default: 5000)",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored terminal output",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(
            f"[policy-tuner] WARNING: data directory '{data_dir}' does not exist. "
            "Running with empty data.",
            file=sys.stderr,
        )

    # Load data
    traces, approvals, policy_history = load_data(data_dir, args.trace_limit)
    print_data_summary(traces, approvals, policy_history)

    # Run analysis
    analyzer = PolicyAnalyzer()
    report   = analyzer.analyze(traces, approvals, policy_history)

    # Generate suggestions
    gen    = SuggestionGenerator()
    report = gen.generate(report)

    print(
        f"[policy-tuner] Analysis complete: "
        f"{len(report.signals)} signals, "
        f"{len(report.smells)} smells, "
        f"{len(report.suggestions)} suggestions",
        file=sys.stderr,
    )

    # Render
    reporter = TunerReporter()
    output   = reporter.render(report, format=args.format)

    # Print to stdout
    print(output)

    # Optionally write to file
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        print(f"[policy-tuner] Report written to: {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
