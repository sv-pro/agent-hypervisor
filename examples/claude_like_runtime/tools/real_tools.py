"""
real_tools.py — Real tool implementations with actual side effects.

These execute against the live filesystem and git state.
Only advertised in worlds where those side effects are ontologically present.
"""

from __future__ import annotations
import subprocess
from pathlib import Path

# Sandbox root: demo operates relative to the agent-hypervisor repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _safe_path(relative: str) -> Path:
    """Resolve a path and ensure it stays within the repo root."""
    resolved = (_REPO_ROOT / relative).resolve()
    if not str(resolved).startswith(str(_REPO_ROOT)):
        raise PermissionError(f"Path escape attempt blocked: {relative}")
    return resolved


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(cwd or _REPO_ROOT),
    )
    out = result.stdout.strip()
    err = result.stderr.strip()
    if result.returncode != 0 and err:
        return f"[exit {result.returncode}] {err}"
    return out or f"[exit {result.returncode}]"


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def read_file(path: str) -> str:
    try:
        return _safe_path(path).read_text(errors="replace")[:4000]
    except FileNotFoundError:
        return f"File not found: {path}"
    except Exception as e:
        return f"Error reading {path}: {e}"


def write_file(path: str, content: str) -> str:
    try:
        p = _safe_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"Written {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error writing {path}: {e}"


def run_command(cmd: str) -> str:
    import shlex
    try:
        return _run(shlex.split(cmd))
    except Exception as e:
        return f"Error running command: {e}"


def git_status() -> str:
    return _run(["git", "status", "--short"])


def git_commit(message: str) -> str:
    return _run(["git", "commit", "-am", message])


def git_push() -> str:
    return _run(["git", "push"])


def grep_code(pattern: str, path: str = ".") -> str:
    try:
        result = subprocess.run(
            ["grep", "-r", "--include=*.py", "-n", pattern, path],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
        )
        output = result.stdout.strip()
        return output[:3000] if output else f"No matches for '{pattern}' in {path}"
    except Exception as e:
        return f"Error grepping: {e}"


def list_files(path: str = ".") -> str:
    try:
        p = _safe_path(path)
        entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
        lines = [
            f"{'DIR ' if e.is_dir() else 'FILE'} {e.name}"
            for e in entries[:80]
        ]
        return "\n".join(lines) or "(empty)"
    except Exception as e:
        return f"Error listing {path}: {e}"


def run_tests() -> str:
    return _run(["python", "-m", "pytest", "tests/", "-q", "--tb=short"])
