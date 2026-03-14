"""
run_benchmark.py — Agent Hypervisor vs. AgentDojo Benchmark Runner

Runs the full benchmark matrix comparing:
  - baseline (no defense)
  - tool_filter (AgentDojo built-in)
  - spotlighting_with_delimiting (AgentDojo built-in)
  - agent_hypervisor (this implementation)

across suites and attacks, producing results for comparison.

Usage:
    # Small scope (5 user tasks x 3 injection tasks, ~1-2 min)
    python run_benchmark.py --model gpt-4o-mini-2024-07-18 \\
        --scope small --all-defenses --attack important_instructions

    # Medium scope (15 user tasks x 7 injection tasks, ~10-15 min)
    python run_benchmark.py --model gpt-4o-mini-2024-07-18 \\
        --scope medium --all-defenses --attack important_instructions

    # Full scope (40 user tasks x 14 injection tasks, ~1-2 hr)
    python run_benchmark.py --model gpt-4o-mini-2024-07-18 \\
        --scope full --all-defenses --attack important_instructions

    # No-attack utility test
    python run_benchmark.py --model gpt-4o-mini-2024-07-18 \\
        --suite workspace --no-attack

Environment:
    ANTHROPIC_API_KEY or OPENAI_API_KEY must be set for the chosen model.
    Create a .env file in the agentdojo-bench/ directory.
"""

from __future__ import annotations

import json
import logging
import sys
import warnings
from pathlib import Path
from typing import Literal

import click
from dotenv import load_dotenv
from rich import print as rprint
from rich.logging import RichHandler

# Add the bench directory to the path so ah_defense is importable
sys.path.insert(0, str(Path(__file__).parent))

from agentdojo.agent_pipeline.agent_pipeline import AgentPipeline, PipelineConfig, load_system_message
from agentdojo.agent_pipeline.tool_execution import ToolsExecutionLoop, ToolsExecutor, tool_result_to_str
from agentdojo.attacks.attack_registry import load_attack
from agentdojo.benchmark import (
    SuiteResults,
    benchmark_suite_with_injections,
    benchmark_suite_without_injections,
)
from agentdojo.logging import OutputLogger
from agentdojo.task_suite.load_suites import get_suite

from ah_defense.pipeline import build_ah_pipeline
from ah_defense.intent_validator import IntentValidator
from ah_defense.taint_tracker import TaintState
from ah_defense.canonicalizer import Canonicalizer
from ah_defense.pipeline import AHInputSanitizer, AHTaintGuard


# ---------------------------------------------------------------------------
# Defense names
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Scope presets
# ---------------------------------------------------------------------------

SCOPES: dict[str, dict] = {
    "small": {
        "user_tasks": ["user_task_0", "user_task_1", "user_task_2", "user_task_3", "user_task_4"],
        "injection_tasks": ["injection_task_0", "injection_task_1", "injection_task_2"],
        "description": "5 user tasks x 3 injection tasks (~15 task pairs)",
    },
    "medium": {
        "user_tasks": [
            "user_task_0", "user_task_1", "user_task_2", "user_task_3", "user_task_4",
            "user_task_5", "user_task_6", "user_task_7", "user_task_8", "user_task_9",
            "user_task_10", "user_task_11", "user_task_12", "user_task_13", "user_task_14",
        ],
        "injection_tasks": [
            "injection_task_0", "injection_task_1", "injection_task_2", "injection_task_3",
            "injection_task_4", "injection_task_5", "injection_task_6",
        ],
        "description": "15 user tasks x 7 injection tasks (~105 task pairs)",
    },
    "full": {
        "user_tasks": [],   # empty = all
        "injection_tasks": [],
        "description": "40 user tasks x 14 injection tasks (~560 task pairs)",
    },
}

DEFENSE_NONE = "none"
DEFENSE_TOOL_FILTER = "tool_filter"
DEFENSE_SPOTLIGHTING = "spotlighting_with_delimiting"
DEFENSE_AH = "agent_hypervisor"

ALL_DEFENSES = [DEFENSE_NONE, DEFENSE_TOOL_FILTER, DEFENSE_SPOTLIGHTING, DEFENSE_AH]
BUILTIN_DEFENSES = [DEFENSE_NONE, DEFENSE_TOOL_FILTER, DEFENSE_SPOTLIGHTING]


# ---------------------------------------------------------------------------
# Pipeline factory
# ---------------------------------------------------------------------------

def make_pipeline(
    model: str,
    defense: str,
    suite_name: str,
    system_message: str,
) -> AgentPipeline:
    """
    Build the appropriate pipeline for a given defense.

    For builtin defenses (none, tool_filter, spotlighting):
        Delegates to AgentPipeline.from_config.

    For agent_hypervisor:
        Builds a fresh AH pipeline with per-execution TaintState.
        (Each call creates new state — required for benchmark isolation.)
    """
    if defense == DEFENSE_AH:
        from agentdojo.agent_pipeline.agent_pipeline import get_llm
        from agentdojo.models import MODEL_PROVIDERS, ModelsEnum

        # Build LLM element
        llm = get_llm(
            provider=MODEL_PROVIDERS[ModelsEnum(model)],
            model=model,
            model_id=None,
            tool_delimiter="tool",
        )

        manifests_dir = Path(__file__).parent / "ah_defense" / "manifests"

        pipeline = build_ah_pipeline(
            llm=llm,
            suite_name=suite_name,
            system_message=system_message,
            manifests_dir=manifests_dir,
        )
        pipeline.name = f"{model}-agent_hypervisor"
        return pipeline

    # Built-in defenses via AgentPipeline.from_config
    config = PipelineConfig(
        llm=model,
        model_id=None,
        defense=None if defense == DEFENSE_NONE else defense,
        system_message_name=None,
        system_message=system_message,
    )
    pipeline = AgentPipeline.from_config(config)
    pipeline.name = f"{model}-{defense}"
    return pipeline


# ---------------------------------------------------------------------------
# Result serialization
# ---------------------------------------------------------------------------

def suite_results_to_dict(results: SuiteResults) -> dict:
    """Convert SuiteResults to a JSON-serializable dict with string keys."""
    return {
        "utility_results": {
            f"{ut}:{it}": v
            for (ut, it), v in results["utility_results"].items()
        },
        "security_results": {
            f"{ut}:{it}": v
            for (ut, it), v in results["security_results"].items()
        },
        "injection_tasks_utility_results": dict(
            results["injection_tasks_utility_results"]
        ),
    }


def compute_metrics(results: SuiteResults) -> dict:
    """Compute summary metrics from SuiteResults."""
    utility_vals = list(results["utility_results"].values())
    security_vals = list(results["security_results"].values())

    avg_utility = sum(utility_vals) / len(utility_vals) if utility_vals else 0.0
    # AgentDojo convention: security() returns True when the injection SUCCEEDED (attack won).
    # ASR = fraction of tasks where the attack succeeded = mean(security_vals).
    asr = sum(security_vals) / len(security_vals) if security_vals else 0.0

    return {
        "utility": avg_utility,
        "asr": asr,
        "n_tasks": len(utility_vals),
        "n_passed_utility": sum(utility_vals),
        "n_failed_security": sum(1 for v in security_vals if v),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.option(
    "--model",
    default="gpt-4o-mini-2024-07-18",
    help="Model to use for benchmarking.",
)
@click.option(
    "--scope",
    default=None,
    type=click.Choice(["small", "medium", "full"]),
    help="Preset scope: small (5ut x 3it), medium (15ut x 7it), full (40ut x 14it). Overrides --user-task/--injection-task.",
)
@click.option(
    "--suite", "-s",
    "suites",
    multiple=True,
    default=("workspace",),
    type=click.Choice(["workspace", "travel", "banking", "slack"]),
    help="AgentDojo suite(s) to benchmark. Default: workspace.",
)
@click.option(
    "--defense", "-d",
    "defenses",
    multiple=True,
    default=("agent_hypervisor",),
    type=click.Choice(ALL_DEFENSES),
    help="Defense(s) to benchmark. Default: agent_hypervisor.",
)
@click.option(
    "--all-defenses",
    is_flag=True,
    default=False,
    help="Run all defenses (none, tool_filter, spotlighting, agent_hypervisor).",
)
@click.option(
    "--attack",
    default="important_instructions",
    help="Attack to use. Default: important_instructions.",
)
@click.option(
    "--no-attack",
    is_flag=True,
    default=False,
    help="Run without attack (utility-only benchmark).",
)
@click.option(
    "--user-task", "-ut",
    "user_tasks",
    multiple=True,
    default=(),
    help="Specific user task IDs to run (e.g. user_task_0). Default: all.",
)
@click.option(
    "--injection-task", "-it",
    "injection_tasks",
    multiple=True,
    default=(),
    help="Specific injection task IDs (e.g. injection_task_0). Default: all.",
)
@click.option(
    "--logdir",
    default="./runs",
    type=Path,
    help="Directory to save logs. Default: ./runs",
)
@click.option(
    "--output",
    default="./results",
    type=Path,
    help="Directory to save JSON results. Default: ./results",
)
@click.option(
    "--benchmark-version",
    default="v1.2.2",
    help="AgentDojo benchmark version. Default: v1.2.2",
)
@click.option(
    "--force-rerun", "-f",
    is_flag=True,
    default=False,
    help="Re-run tasks even if results already exist.",
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    default=False,
    help="Enable verbose logging.",
)
@click.option(
    "--debug-ah",
    is_flag=True,
    default=False,
    help="Enable AH pipeline DEBUG logging (shows taint/verdict per tool call).",
)
def main(
    model: str,
    scope: str | None,
    suites: tuple[str, ...],
    defenses: tuple[str, ...],
    all_defenses: bool,
    attack: str,
    no_attack: bool,
    user_tasks: tuple[str, ...],
    injection_tasks: tuple[str, ...],
    logdir: Path,
    output: Path,
    benchmark_version: str,
    force_rerun: bool,
    verbose: bool,
    debug_ah: bool,
) -> None:
    """Run Agent Hypervisor vs. AgentDojo benchmark."""

    # Setup
    if not load_dotenv(".env"):
        warnings.warn("No .env file found — API keys must be in environment")

    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    if debug_ah:
        logging.getLogger("ah_defense").setLevel(logging.DEBUG)

    if all_defenses:
        defenses = tuple(ALL_DEFENSES)

    # Apply scope preset (overrides --user-task / --injection-task)
    if scope is not None:
        preset = SCOPES[scope]
        user_tasks = tuple(preset["user_tasks"])
        injection_tasks = tuple(preset["injection_tasks"])
        rprint(f"[bold]Scope:[/bold] {scope} — {preset['description']}")

    logdir.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)

    system_message = load_system_message(None)
    attack_str = None if no_attack else attack
    result_file = output / f"results_{model}_{attack_str or 'no_attack'}.json"

    # Load existing partial results so we can accumulate across interrupted runs
    all_results: dict = {}
    if result_file.exists() and not force_rerun:
        with open(result_file) as f:
            all_results = json.load(f)

    for suite_name in suites:
        suite = get_suite(benchmark_version, suite_name)
        all_results.setdefault(suite_name, {})

        for defense in defenses:
            # Skip tool_filter for non-OpenAI models (it requires OpenAI)
            if defense == DEFENSE_TOOL_FILTER and not model.startswith("gpt-"):
                rprint(f"[yellow]Skipping tool_filter for non-OpenAI model {model}[/yellow]")
                continue

            rprint(f"\n[bold]Suite:[/bold] {suite_name}  "
                   f"[bold]Defense:[/bold] {defense}  "
                   f"[bold]Model:[/bold] {model}  "
                   f"[bold]Attack:[/bold] {attack_str or 'none'}")

            pipeline = make_pipeline(model, defense, suite_name, system_message)

            with OutputLogger(str(logdir)):
                if no_attack or attack_str is None:
                    results = benchmark_suite_without_injections(
                        pipeline,
                        suite,
                        user_tasks=list(user_tasks) if user_tasks else None,
                        logdir=logdir,
                        force_rerun=force_rerun,
                        benchmark_version=benchmark_version,
                    )
                else:
                    attacker = load_attack(attack_str, suite, pipeline)
                    results = benchmark_suite_with_injections(
                        pipeline,
                        suite,
                        attacker,
                        user_tasks=list(user_tasks) if user_tasks else None,
                        injection_tasks=list(injection_tasks) if injection_tasks else None,
                        logdir=logdir,
                        force_rerun=force_rerun,
                        benchmark_version=benchmark_version,
                    )

            metrics = compute_metrics(results)
            all_results[suite_name][defense] = {
                "metrics": metrics,
                "raw": suite_results_to_dict(results),
            }

            # Print summary
            rprint(f"  [green]Utility:[/green] {metrics['utility']*100:.1f}%  "
                   f"[red]ASR:[/red] {metrics['asr']*100:.1f}%  "
                   f"[dim]({metrics['n_tasks']} tasks)[/dim]")

            # Per-task security breakdown
            if verbose or debug_ah:
                for (ut, it), sec in results["security_results"].items():
                    util = results["utility_results"].get((ut, it), "?")
                    # security=True means attack succeeded (BREACHED), False means defended (SECURE)
                    status = "[red]BREACHED[/red]" if sec else "[green]SECURE[/green]"
                    rprint(f"    {status}  util={'✓' if util else '✗'}  {ut} × {it}")

            # Save intermediate results after each defense completes
            with open(result_file, "w") as f:
                json.dump(all_results, f, indent=2)
            rprint(f"  [dim]Intermediate results saved to {result_file}[/dim]")

    rprint(f"\n[bold green]Results saved to {result_file}[/bold green]")

    # Print summary table
    _print_summary_table(all_results, attack_str)


def _print_summary_table(all_results: dict, attack: str | None) -> None:
    """Print a markdown-style summary table."""
    rprint("\n[bold]== Summary Table ==[/bold]")
    header = f"{'Defense':<30} {'Suite':<12} {'Utility':>8} {'ASR':>8}"
    rprint(header)
    rprint("-" * len(header))

    for suite_name, suite_results in all_results.items():
        for defense, data in suite_results.items():
            m = data["metrics"]
            rprint(
                f"{defense:<30} {suite_name:<12} "
                f"{m['utility']*100:>7.1f}% "
                f"{m['asr']*100:>7.1f}%"
            )


if __name__ == "__main__":
    main()
