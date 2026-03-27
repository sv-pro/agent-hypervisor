"""
Execution Worker
================

Standalone subprocess that owns the real action handlers.

Run as: python worker.py   (expects JSON on stdin, writes JSON to stdout)

Protocol:
  stdin  → {"action_name": "...", "params": {...}}
  stdout → {"ok": true, "result": {...}}
       or {"ok": false, "error": "..."}
  stderr → [worker] log lines (pass-through to parent terminal)

Invariants:
  - Never does policy evaluation
  - Never accepts raw natural language
  - Fails closed on unknown action names (not in local registry → error)
  - Never dispatches via eval/exec
  - The only actions reachable here are those in _REGISTRY below

This registry is intentionally parallel to the world manifest ontology.
The main process validates that an action is allowed; the worker only checks
that the action name is known to it. Two independent closed sets.
"""

import json
import sys


# ── Closed handler registry ───────────────────────────────────────────────────
#
# This is the ONLY place handlers live. Nothing in the main process can call
# these functions directly — they are unreachable except through this script.
#
# To add a handler: add it here AND add it to world_manifest.yaml AND handle
# it in the main process ontology. All three must agree.

_REGISTRY = {
    "read_data": lambda p: {
        "data": p.get("query", ""),
        "source": "db",
    },
    "summarize": lambda p: {
        "summary": f"Summary of: {str(p.get('text', ''))[:50]}",
    },
    "send_email": lambda p: {
        "sent": True,
        "to": p.get("to", ""),
    },
    "download_report": lambda p: {
        "report": p.get("id", ""),
        "bytes": 0,
    },
    "post_webhook": lambda p: {
        "status": 200,
        "url": p.get("url", ""),
    },
}


def _respond(**kwargs: object) -> None:
    sys.stdout.write(json.dumps(kwargs))
    sys.stdout.flush()


def main() -> None:
    raw = sys.stdin.read()

    try:
        request = json.loads(raw)
    except json.JSONDecodeError as exc:
        _respond(ok=False, error=f"Invalid JSON from main process: {exc}")
        return

    action_name = request.get("action_name")
    params = request.get("params", {})

    if not isinstance(action_name, str):
        _respond(ok=False, error="action_name must be a string")
        return

    handler = _REGISTRY.get(action_name)
    if handler is None:
        # Fail closed: unknown action is not executed, even if main process
        # somehow sent it. This is the worker's own closed-world check.
        _respond(ok=False, error=f"Unknown action in worker registry: {action_name!r}")
        return

    try:
        result = handler(params)
        print(f"[worker] executed {action_name}", file=sys.stderr, flush=True)
        _respond(ok=True, result=result)
    except Exception as exc:  # noqa: BLE001
        _respond(ok=False, error=f"Handler raised: {exc}")


if __name__ == "__main__":
    main()
