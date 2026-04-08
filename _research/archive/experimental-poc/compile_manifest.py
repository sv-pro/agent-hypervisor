"""
compile_manifest.py – compile a capability profile into a World Manifest.

A manifest is the declarative, human-readable policy artifact that the
enforcement engine consumes.  Compilation rules:

1. Every (tool, resource) pair from the profile becomes an allowed_action
   entry.
2. Any resource whose scheme is "repo://remote/*" is placed under
   approval_required as well as allowed.
3. A catch-all "deny undefined" constraint is always emitted.
4. Network calls and environment-variable reads are always denied unless
   the profile explicitly lists them.

Usage (module):
    from compiler.compile_manifest import compile_manifest
    manifest = compile_manifest(profile)

Usage (CLI):
    python -m awc.compiler.compile_manifest profiles/repo_safe_write.yaml
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from awc.compiler.profiler import CapabilityProfile, derive_profile
from awc.policy.taint import DEFAULT_INPUT_TRUST

_ALWAYS_DENIED = [
    {"action": "http_post", "reason": "Outbound HTTP calls are not part of the declared workflow."},
    {"action": "env_read", "reason": "Environment variable access is not part of the declared workflow."},
    {"action": "network_call", "reason": "Any network call outside git_push to origin is denied."},
]

_REMOTE_PATTERN = "repo://remote/"


def _needs_approval(resource: str) -> bool:
    return resource.startswith(_REMOTE_PATTERN)


def compile_manifest(
    profile: CapabilityProfile,
    manifest_id: str | None = None,
    author: str = "unknown",
) -> dict[str, Any]:
    """Return a manifest dict from a CapabilityProfile."""
    mid = manifest_id or profile.profile_id.replace("_", "-")

    allowed: list[dict] = []
    approval_required: list[dict] = []

    for tool in profile.allowed_tools:
        for resource in profile.allowed_resources:
            entry: dict[str, Any] = {
                "action": tool,
                "permitted_resources": [resource],
                "trust_required": "trusted",
                "taint_ok": False,
            }
            allowed.append(entry)
            if _needs_approval(resource):
                approval_required.append({
                    "action": tool,
                    "resource_pattern": resource,
                    "reason": "Remote resource access requires explicit operator approval.",
                })

    # deduplicate approval_required by (action, resource_pattern)
    seen: set[tuple[str, str]] = set()
    unique_approval: list[dict] = []
    for a in approval_required:
        key = (a["action"], a["resource_pattern"])
        if key not in seen:
            seen.add(key)
            unique_approval.append(a)

    manifest: dict[str, Any] = {
        "manifest_id": mid,
        "version": "1.0",
        "description": (
            f"World Manifest compiled from profile {profile.profile_id}. "
            f"Derived from: {', '.join(profile.derived_from)}."
        ),
        "provenance": {
            "author": author,
            "created": str(date.today()),
            "source_profile": f"fixtures/profiles/{profile.profile_id}.yaml",
            "source_traces": profile.derived_from,
        },
        "input_trust": DEFAULT_INPUT_TRUST,
        "allowed_actions": allowed,
        "approval_required": unique_approval,
        "denied_actions": _ALWAYS_DENIED,
        "capability_constraints": {
            "taint_propagation": "deny_external",
            "max_scope": "single_repo",
            "allow_network_calls": False,
            "allow_env_secrets": False,
            "undefined_actions": "deny",
        },
    }
    return manifest


def _load_profile_yaml(path: Path) -> CapabilityProfile:
    with path.open() as fh:
        data = yaml.safe_load(fh)
    return CapabilityProfile(
        profile_id=data["profile_id"],
        derived_from=data.get("derived_from", []),
        allowed_tools=data.get("allowed_tools", []),
        allowed_actions=data.get("allowed_actions", []),
        allowed_resources=data.get("allowed_resources", []),
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m awc.compiler.compile_manifest <profile.yaml> [manifest_id] [author]")
        sys.exit(1)

    profile_path = Path(sys.argv[1])
    manifest_id_arg = sys.argv[2] if len(sys.argv) > 2 else None
    author_arg = sys.argv[3] if len(sys.argv) > 3 else "Sergey Vlasov"

    if not profile_path.exists():
        print(f"Profile not found: {profile_path}")
        sys.exit(1)

    loaded_profile = _load_profile_yaml(profile_path)
    result = compile_manifest(loaded_profile, manifest_id=manifest_id_arg, author=author_arg)
    print(yaml.dump(result, default_flow_style=False, sort_keys=False, allow_unicode=True))
