#!/usr/bin/env python3
"""
monitor.py — Standalone benchmark visualizer for AgentDojo runs.

Tails log_full_scope.txt and polls results/*.json — zero changes to
run_benchmark.py or ah_defense/.

Usage:
    python monitor.py                          # auto-detect latest log + results
    python monitor.py --log log_full_scope.txt --results results/
    python monitor.py --log log_ah_medium.txt  # any past log
"""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Label,
    RichLog,
    Static,
)
from rich.text import Text

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFENSES = ["none", "tool_filter", "spotlighting_with_delimiting", "agent_hypervisor"]
DEFENSE_SHORT = {
    "none": "none",
    "tool_filter": "tool_filt",
    "spotlighting_with_delimiting": "spotlt",
    "agent_hypervisor": "ah",
}

# Regex patterns against log lines
RE_TRACE = re.compile(
    r"(\d{2}:\d{2}:\d{2}) "
    r"\\\[([^\]]+)\]"           # model-defense
    r"\\\[([^\]]+)\]"           # suite
    r"(?:\\\[([^\]]+)\])?"      # user_task (optional in early lines)
    r"(?:\\\[([^\]]+)\])?"      # injection_task (optional)
    r" :([^:]+): "              # emoji role name
    r"\[?(.*)"                  # content (rest of line)
)
RE_HEADER = re.compile(
    r"Suite:\s*(\S+)\s+Defense:\s*(\S+)\s+Model:\s*(\S+)"
)
RE_METRICS = re.compile(
    r"Utility:\s*([\d.]+)%\s+ASR:\s*([\d.]+)%\s+\((\d+) tasks\)"
)
RE_SAVED = re.compile(r"Intermediate results saved to (.+)")

ROLE_ICONS = {
    "book": ("SYS", "dim"),
    "bust_in_silhouette": ("USR", "green"),
    "robot_face": ("AST", "cyan"),
    "wrench": ("TOL", "yellow"),
}

# ---------------------------------------------------------------------------
# State dataclasses
# ---------------------------------------------------------------------------

@dataclass
class TaskVerdict:
    utility: Optional[bool] = None
    security: Optional[bool] = None  # True = BREACHED


@dataclass
class DefenseState:
    name: str
    utility: Optional[float] = None
    asr: Optional[float] = None
    n_tasks: int = 0
    completed: bool = False
    verdicts: dict[tuple[str, str], TaskVerdict] = field(default_factory=dict)

    @property
    def n_completed(self) -> int:
        return len(self.verdicts)


@dataclass
class BenchState:
    log_path: Path
    results_dir: Path
    model: str = ""
    suite: str = ""
    attack: str = ""

    # Per-defense state
    defenses: dict[str, DefenseState] = field(default_factory=dict)

    # Currently active task
    active_defense: str = ""
    active_user_task: str = ""
    active_injection_task: str = ""

    # Live trace lines for the active task (max ~60)
    trace_lines: list[tuple[str, str, str]] = field(default_factory=list)  # (time, role, content)

    # Full expected task count (filled from results JSON or log header)
    total_tasks: int = 0  # per defense

    # Log reading position
    _log_pos: int = 0

    def get_or_create_defense(self, name: str) -> DefenseState:
        if name not in self.defenses:
            self.defenses[name] = DefenseState(name=name)
        return self.defenses[name]


# ---------------------------------------------------------------------------
# Log parser (incremental, called on each poll tick)
# ---------------------------------------------------------------------------

def _strip_rich(text: str) -> str:
    """Remove Rich markup tags from a string."""
    return re.sub(r"\[/?[^\]]*\]", "", text)


def parse_log_chunk(state: BenchState, new_lines: list[str]) -> bool:
    """Parse new log lines into state. Returns True if anything changed."""
    changed = False

    for raw in new_lines:
        line = raw.rstrip("\n")

        # Suite/Defense/Model header line
        m = RE_HEADER.search(line)
        if m:
            state.suite = m.group(1)
            defense_name = m.group(2)
            state.model = m.group(3)
            ds = state.get_or_create_defense(defense_name)
            if state.active_defense != defense_name:
                state.active_defense = defense_name
                state.trace_lines = []
            changed = True
            continue

        # Metrics summary line emitted after each defense
        m = RE_METRICS.search(_strip_rich(line))
        if m and state.active_defense:
            ds = state.get_or_create_defense(state.active_defense)
            ds.utility = float(m.group(1)) / 100
            ds.asr = float(m.group(2)) / 100
            ds.n_tasks = int(m.group(3))
            ds.completed = True
            state.total_tasks = max(state.total_tasks, ds.n_tasks)
            changed = True
            continue

        # Trace line
        m = RE_TRACE.match(line)
        if m:
            ts = m.group(1)
            model_defense = m.group(2)   # e.g. gpt-4o-mini-2024-07-18-none
            suite = m.group(3)
            user_task = m.group(4) or ""
            inj_task = m.group(5) or ""
            emoji_role = m.group(6).strip()
            content = _strip_rich(m.group(7))[:120]

            # Derive defense from model_defense tag
            defense = _infer_defense(model_defense)
            if defense and defense != state.active_defense:
                state.active_defense = defense
                state.trace_lines = []

            # Detect task switch
            task_changed = (
                user_task and inj_task and
                (user_task != state.active_user_task or inj_task != state.active_injection_task)
            )
            if task_changed:
                state.active_user_task = user_task
                state.active_injection_task = inj_task
                state.trace_lines = []

            # Add to trace
            icon, color = ROLE_ICONS.get(emoji_role, ("???", "white"))
            state.trace_lines.append((ts, f"[{color}]{icon}[/{color}]", content))
            if len(state.trace_lines) > 80:
                state.trace_lines = state.trace_lines[-80:]

            changed = True

    return changed


def _infer_defense(model_defense: str) -> str:
    """Extract defense name from combined model-defense string."""
    for d in sorted(DEFENSES, key=len, reverse=True):
        if model_defense.endswith(d):
            return d
    return ""


def poll_log(state: BenchState) -> bool:
    """Read new bytes from log file since last position. Returns True if changed."""
    try:
        with open(state.log_path, "r", errors="replace") as f:
            f.seek(state._log_pos)
            new_text = f.read()
            state._log_pos = f.tell()
        if not new_text:
            return False
        new_lines = new_text.splitlines(keepends=True)
        return parse_log_chunk(state, new_lines)
    except FileNotFoundError:
        return False


def poll_results(state: BenchState) -> bool:
    """Reload results JSON files to get completed metrics."""
    changed = False
    for jf in state.results_dir.glob("results_*.json"):
        try:
            data = json.loads(jf.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        for suite_name, suite_data in data.items():
            for defense_name, defense_data in suite_data.items():
                ds = state.get_or_create_defense(defense_name)
                m = defense_data.get("metrics", {})
                if m:
                    ds.utility = m.get("utility")
                    ds.asr = m.get("asr")
                    ds.n_tasks = m.get("n_tasks", 0)
                    ds.completed = True
                    state.total_tasks = max(state.total_tasks, ds.n_tasks)

                    # Load per-task verdicts
                    raw = defense_data.get("raw", {})
                    for key, util_val in raw.get("utility_results", {}).items():
                        ut, it = key.split(":", 1)
                        tv = ds.verdicts.setdefault((ut, it), TaskVerdict())
                        tv.utility = bool(util_val)
                    for key, sec_val in raw.get("security_results", {}).items():
                        ut, it = key.split(":", 1)
                        tv = ds.verdicts.setdefault((ut, it), TaskVerdict())
                        tv.security = bool(sec_val)
                    changed = True
    return changed


# ---------------------------------------------------------------------------
# Textual TUI
# ---------------------------------------------------------------------------

POLL_INTERVAL = 2.0  # seconds


class ProgressPanel(Static):
    """Left sidebar: per-defense progress bars + metrics table."""

    def __init__(self, state: BenchState, **kwargs):
        super().__init__(**kwargs)
        self._state = state

    def render(self) -> Text:
        s = self._state
        lines: list[str] = []

        lines.append(f"[bold]Model:[/bold] {s.model or '…'}")
        lines.append(f"[bold]Suite:[/bold] {s.suite or '…'}")
        lines.append("")

        total = max(s.total_tasks, 1)

        for d in DEFENSES:
            ds = s.defenses.get(d)
            short = DEFENSE_SHORT[d]
            if ds is None:
                lines.append(f"[dim]{short:<10}  pending[/dim]")
                continue

            done = ds.n_completed
            pct = min(done / total, 1.0) if total else 0
            bar_len = 14
            filled = int(pct * bar_len)
            bar = "█" * filled + "░" * (bar_len - filled)

            if ds.completed:
                util_str = f"{ds.utility*100:.0f}%" if ds.utility is not None else "—"
                asr_str  = f"{ds.asr*100:.0f}%"    if ds.asr  is not None else "—"
                color = "green" if d == "agent_hypervisor" else "white"
                lines.append(
                    f"[{color}]{short:<10}[/{color}] [{bar}] "
                    f"[green]{util_str}[/green] [red]{asr_str}[/red]"
                )
            elif d == s.active_defense:
                lines.append(
                    f"[cyan]{short:<10}[/cyan] [{bar}] "
                    f"[dim]{done}/{total}[/dim] [cyan]◀ running[/cyan]"
                )
            else:
                lines.append(f"[dim]{short:<10}[/dim] [dim][{bar}][/dim]")

        lines.append("")
        lines.append("[bold]Defense   Util   ASR[/bold]")
        lines.append("─" * 26)
        for d in DEFENSES:
            ds = s.defenses.get(d)
            short = DEFENSE_SHORT[d]
            if ds and ds.completed:
                u = f"{ds.utility*100:.1f}%" if ds.utility is not None else "—"
                a = f"{ds.asr*100:.1f}%"     if ds.asr  is not None else "—"
                lines.append(f"{short:<10} [green]{u:>5}[/green]  [red]{a:>5}[/red]")
            else:
                lines.append(f"[dim]{short:<10}  —      —[/dim]")

        return Text.from_markup("\n".join(lines))


class TracePanel(RichLog):
    """Right panel: live conversation trace."""
    pass


class MatrixView(Static):
    """Full-screen matrix: rows=user_tasks, cols=injection_tasks."""

    def __init__(self, state: BenchState, defense: str, **kwargs):
        super().__init__(**kwargs)
        self._state = state
        self._defense = defense

    def render(self) -> Text:
        s = self._state
        ds = s.defenses.get(self._defense)
        short = DEFENSE_SHORT.get(self._defense, self._defense)

        if ds is None or not ds.verdicts:
            return Text.from_markup(
                f"[bold]Matrix — {short}[/bold]\n\n[dim]No data yet.[/dim]"
            )

        # Collect axes
        user_tasks = sorted({ut for ut, _ in ds.verdicts})
        inj_tasks  = sorted({it for _, it in ds.verdicts})

        # Short labels: user_task_3 → ut3
        def ut_short(s): return "ut" + s.split("_")[-1]
        def it_short(s): return "it" + s.split("_")[-1]

        lines: list[str] = [f"[bold]Matrix — {short}[/bold]   ✓=defended  ✗=breached  ?=pending\n"]

        # Header row
        header = "      " + "  ".join(f"{it_short(it):>3}" for it in inj_tasks)
        lines.append(f"[dim]{header}[/dim]")

        for ut in user_tasks:
            row = f"[dim]{ut_short(ut):<5}[/dim]"
            for it in inj_tasks:
                verdict = ds.verdicts.get((ut, it))
                if verdict is None:
                    cell = "[dim] ? [/dim]"
                elif verdict.security:          # True = BREACHED
                    cell = "[red] ✗ [/red]"
                else:
                    cell = "[green] ✓ [/green]"
                row += cell
            lines.append(row)

        total = len(ds.verdicts)
        breached = sum(1 for v in ds.verdicts.values() if v.security)
        lines.append(f"\n[dim]{total} tasks  |  breached: {breached}  |  defended: {total-breached}[/dim]")
        return Text.from_markup("\n".join(lines))


class BenchMonitorApp(App):
    CSS = """
    Screen { layout: horizontal; }
    #sidebar {
        width: 34;
        border-right: solid $primary-darken-2;
        padding: 1 1;
    }
    #main { width: 1fr; }
    #trace-label {
        background: $primary-darken-3;
        color: $text;
        padding: 0 1;
        height: 1;
    }
    TracePanel { height: 1fr; border: none; }
    MatrixView { height: 1fr; padding: 1 2; }
    Footer { height: 1; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("m", "toggle_matrix", "Matrix"),
        Binding("left", "prev_defense", "Prev defense"),
        Binding("right", "next_defense", "Next defense"),
        Binding("p", "toggle_pause", "Pause"),
    ]

    _paused: reactive[bool] = reactive(False)
    _show_matrix: reactive[bool] = reactive(False)
    _matrix_defense_idx: reactive[int] = reactive(0)

    def __init__(self, state: BenchState):
        super().__init__()
        self._state = state
        self._progress = None
        self._trace = None
        self._matrix_view = None
        self._label = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id="sidebar"):
                self._progress = ProgressPanel(self._state)
                yield self._progress
            with Vertical(id="main"):
                self._label = Label("", id="trace-label")
                yield self._label
                self._trace = TracePanel(highlight=True, markup=True, wrap=True)
                yield self._trace
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(POLL_INTERVAL, self._tick)
        self._tick()  # immediate first update

    def _tick(self) -> None:
        if self._paused:
            return
        s = self._state
        log_changed = poll_log(s)
        res_changed = poll_results(s)

        if log_changed or res_changed:
            self._refresh_progress()
            if log_changed and not self._show_matrix:
                self._refresh_trace()

    def _refresh_progress(self) -> None:
        if self._progress:
            self._progress.refresh()

    def _refresh_trace(self) -> None:
        s = self._state
        if self._trace is None:
            return

        if self._label:
            active = s.active_defense
            short = DEFENSE_SHORT.get(active, active)
            ut = s.active_user_task or "…"
            it = s.active_injection_task or "…"
            pause_str = "  [PAUSED]" if self._paused else ""
            self._label.update(
                f" {short}  |  {ut} × {it}{pause_str}"
            )

        self._trace.clear()
        for ts, role_markup, content in s.trace_lines:
            self._trace.write(Text.from_markup(f"[dim]{ts}[/dim] {role_markup}  {content}"))

    def action_toggle_pause(self) -> None:
        self._paused = not self._paused
        self._refresh_trace()

    def action_toggle_matrix(self) -> None:
        self._show_matrix = not self._show_matrix
        main = self.query_one("#main", Vertical)
        if self._show_matrix:
            if self._trace:
                self._trace.display = False
            defense = DEFENSES[self._matrix_defense_idx % len(DEFENSES)]
            if self._matrix_view:
                self._matrix_view.remove()
            self._matrix_view = MatrixView(self._state, defense)
            main.mount(self._matrix_view)
            if self._label:
                self._label.update(
                    f" Matrix: {DEFENSE_SHORT[defense]}  "
                    f"[← →] switch defense   [m] back to trace"
                )
        else:
            if self._matrix_view:
                self._matrix_view.remove()
                self._matrix_view = None
            if self._trace:
                self._trace.display = True
            self._refresh_trace()

    def action_prev_defense(self) -> None:
        if self._show_matrix:
            self._matrix_defense_idx = (self._matrix_defense_idx - 1) % len(DEFENSES)
            self._refresh_matrix()

    def action_next_defense(self) -> None:
        if self._show_matrix:
            self._matrix_defense_idx = (self._matrix_defense_idx + 1) % len(DEFENSES)
            self._refresh_matrix()

    def _refresh_matrix(self) -> None:
        if not self._show_matrix or self._matrix_view is None:
            return
        defense = DEFENSES[self._matrix_defense_idx % len(DEFENSES)]
        self._matrix_view._defense = defense
        self._matrix_view.refresh()
        if self._label:
            self._label.update(
                f" Matrix: {DEFENSE_SHORT[defense]}  "
                f"[← →] switch defense   [m] back to trace"
            )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _find_log(bench_dir: Path) -> Path:
    candidates = sorted(bench_dir.glob("log_*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    if candidates:
        return candidates[0]
    raise FileNotFoundError(f"No log_*.txt found in {bench_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentDojo benchmark monitor")
    parser.add_argument("--log", type=Path, default=None, help="Log file to tail")
    parser.add_argument("--results", type=Path, default=None, help="Results directory to poll")
    args = parser.parse_args()

    bench_dir = Path(__file__).parent
    log_path = args.log or _find_log(bench_dir)
    results_dir = args.results or bench_dir / "results"

    print(f"Monitoring: {log_path}")
    print(f"Results:    {results_dir}")

    state = BenchState(log_path=log_path, results_dir=results_dir)

    # Do an initial full parse of existing log content
    poll_log(state)
    poll_results(state)

    app = BenchMonitorApp(state)
    app.run()


if __name__ == "__main__":
    main()
