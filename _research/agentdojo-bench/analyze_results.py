"""
analyze_results.py — Parse benchmark result JSON files into comparison tables.

Reads result files produced by run_benchmark.py and generates:
  1. Markdown table comparing all defenses across suites and attacks
  2. Per-suite breakdowns
  3. Aggregate metrics across all suites

Usage:
    # Basic comparison table
    python analyze_results.py results/

    # With CaMeL reference numbers from paper
    python analyze_results.py results/ --include-camel-paper

    # Specific result files
    python analyze_results.py results/results_gpt-4o_important_instructions.json \\
                              results/results_gpt-4o_no_attack.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click


# ---------------------------------------------------------------------------
# CaMeL paper reference numbers (from the CaMeL paper, Table 1)
# These are included for comparison when --include-camel-paper is used.
# NOTE: reproduce these locally with `uv run main.py gpt-4o --run-attack`
# ---------------------------------------------------------------------------
CAMEL_PAPER_NUMBERS = {
    # model: gpt-4o-2024-05-13
    # workspace suite
    ("workspace", "important_instructions"): {"utility": 0.77, "asr": 0.0},  # CaMeL: ~77% utility, 0% ASR (provable)
    ("workspace", "tool_knowledge"):          {"utility": 0.77, "asr": 0.0},
}


def load_results_dir(results_dir: Path) -> dict[str, dict]:
    """Load all JSON result files from a directory."""
    all_results: dict[str, dict] = {}
    for f in sorted(results_dir.glob("results_*.json")):
        with open(f) as fp:
            data = json.load(fp)
        # File name format: results_{model}_{attack}.json
        parts = f.stem.split("_", maxsplit=2)
        if len(parts) >= 3:
            attack = parts[2]
        else:
            attack = "unknown"
        all_results[attack] = data
    return all_results


def compute_aggregate(suite_data: dict) -> dict:
    """Compute aggregate metrics across all suites for a defense."""
    all_utility = []
    all_asr = []
    for suite_name, defense_data in suite_data.items():
        for defense, data in defense_data.items():
            m = data.get("metrics", {})
            if "utility" in m:
                all_utility.append(m["utility"])
            if "asr" in m:
                all_asr.append(m["asr"])
    return {
        "utility": sum(all_utility) / len(all_utility) if all_utility else 0.0,
        "asr": sum(all_asr) / len(all_asr) if all_asr else 0.0,
    }


def generate_markdown_table(
    all_results: dict[str, dict],
    include_camel_paper: bool = False,
) -> str:
    """Generate a markdown comparison table from benchmark results.

    Args:
        all_results: Mapping of attack_name → suite_name → defense → {metrics, raw}
        include_camel_paper: Whether to append CaMeL paper reference numbers.

    Returns:
        Markdown table string.
    """
    lines = []

    # Collect all defenses and suites
    all_defenses: set[str] = set()
    all_suites: set[str] = set()
    all_attacks = list(all_results.keys())

    for attack_data in all_results.values():
        for suite_name, suite_data in attack_data.items():
            all_suites.add(suite_name)
            for defense in suite_data:
                all_defenses.add(defense)

    suites = sorted(all_suites)
    defenses = sorted(all_defenses, key=lambda d: [
        "none", "tool_filter", "spotlighting_with_delimiting", "agent_hypervisor"
    ].index(d) if d in [
        "none", "tool_filter", "spotlighting_with_delimiting", "agent_hypervisor"
    ] else 99)

    # Header
    lines.append("# Agent Hypervisor Benchmark Results")
    lines.append("")
    lines.append("## Comparison Table")
    lines.append("")

    # Build table
    # Columns: Defense | Suite | Utility (no attack) | Utility (under attack) | ASR
    header = "| Defense | Suite |"
    separator = "|---------|-------|"

    if "no_attack" in all_results:
        header += " Utility (clean) |"
        separator += "-----------------|"

    for attack in all_attacks:
        if attack != "no_attack":
            header += f" Utility ({attack}) |"
            separator += f"{''.join(['-'] * (len(attack) + 13))}|"
            header += f" ASR ({attack}) |"
            separator += f"{''.join(['-'] * (len(attack) + 7))}|"

    lines.append(header)
    lines.append(separator)

    for defense in defenses:
        for suite in suites:
            row = f"| {defense:<30} | {suite:<10} |"

            if "no_attack" in all_results:
                util = all_results["no_attack"].get(suite, {}).get(defense, {}).get("metrics", {}).get("utility")
                row += f" {util*100:>6.1f}%        |" if util is not None else "    N/A          |"

            for attack in all_attacks:
                if attack == "no_attack":
                    continue
                m = all_results[attack].get(suite, {}).get(defense, {}).get("metrics", {})
                util = m.get("utility")
                asr = m.get("asr")
                row += f" {util*100:>6.1f}%{' '*len(attack)+' ':<12}|" if util is not None else "    N/A              |"
                row += f" {asr*100:>6.1f}%{' '*len(attack):<6}|" if asr is not None else "  N/A     |"

            lines.append(row)

    # CaMeL reference
    if include_camel_paper:
        lines.append("")
        lines.append("### CaMeL Reference (paper numbers, gpt-4o-2024-05-13)")
        lines.append("")
        lines.append("| Suite | Attack | Utility | ASR |")
        lines.append("|-------|--------|---------|-----|")
        for (suite, attack), nums in CAMEL_PAPER_NUMBERS.items():
            lines.append(
                f"| {suite} | {attack} | {nums['utility']*100:.1f}% | {nums['asr']*100:.1f}% |"
            )
        lines.append("")
        lines.append(
            "> Note: CaMeL achieves 0% ASR via provable security (dual-LLM + capability tracking).\n"
            "> Agent Hypervisor achieves ASR reduction via manifest-driven taint containment\n"
            "> without LLMs on the security-critical path."
        )

    return "\n".join(lines)


def generate_per_suite_breakdown(all_results: dict[str, dict]) -> str:
    """Generate detailed per-suite breakdown."""
    lines = []
    lines.append("## Per-Suite Detailed Results")
    lines.append("")

    for attack, attack_data in sorted(all_results.items()):
        lines.append(f"### Attack: {attack}")
        lines.append("")

        for suite_name in sorted(attack_data.keys()):
            suite_data = attack_data[suite_name]
            lines.append(f"#### Suite: {suite_name}")
            lines.append("")
            lines.append("| Defense | Utility | ASR | Tasks |")
            lines.append("|---------|---------|-----|-------|")

            for defense in sorted(suite_data.keys()):
                m = suite_data[defense].get("metrics", {})
                util = m.get("utility", 0.0)
                asr = m.get("asr", 0.0)
                n = m.get("n_tasks", 0)
                lines.append(f"| {defense} | {util*100:.1f}% | {asr*100:.1f}% | {n} |")

            lines.append("")

    return "\n".join(lines)


@click.command()
@click.argument("results_path", type=Path)
@click.option(
    "--include-camel-paper",
    is_flag=True,
    default=False,
    help="Include CaMeL paper reference numbers in the table.",
)
@click.option(
    "--output", "-o",
    type=Path,
    default=None,
    help="Output markdown file. Default: print to stdout.",
)
def main(results_path: Path, include_camel_paper: bool, output: Path | None) -> None:
    """Generate comparison tables from benchmark results."""

    if results_path.is_dir():
        all_results = load_results_dir(results_path)
    elif results_path.is_file():
        with open(results_path) as f:
            data = json.load(f)
        # Single file: infer attack from filename
        parts = results_path.stem.split("_", maxsplit=2)
        attack = parts[2] if len(parts) >= 3 else "unknown"
        all_results = {attack: data}
    else:
        raise click.ClickException(f"Path not found: {results_path}")

    if not all_results:
        raise click.ClickException("No result files found.")

    table = generate_markdown_table(all_results, include_camel_paper)
    breakdown = generate_per_suite_breakdown(all_results)
    full_output = table + "\n\n" + breakdown

    if output:
        output.write_text(full_output)
        click.echo(f"Results written to {output}")
    else:
        click.echo(full_output)


if __name__ == "__main__":
    main()
