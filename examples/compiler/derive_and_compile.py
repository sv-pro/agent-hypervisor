"""
examples/derive_and_compile.py – demonstrates the full compiler pipeline:
  1. Derive a capability profile from the benign trace.
  2. Compile it into a World Manifest.
  3. Print both artefacts.
"""

from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]

from awc.compiler.profiler import derive_profile
from awc.compiler.compile_manifest import compile_manifest

REPO_ROOT = Path(__file__).resolve().parent.parent
BENIGN_TRACE = REPO_ROOT / "fixtures" / "traces" / "benign_repo_maintenance.json"


def main() -> None:
    print("=== Step 1: Derive capability profile ===")
    profile = derive_profile([BENIGN_TRACE], profile_id="repo_safe_write")
    print(yaml.dump(profile.to_dict(), default_flow_style=False, sort_keys=False))

    print("=== Step 2: Compile World Manifest ===")
    manifest = compile_manifest(profile, manifest_id="repo-safe-write", author="Sergey Vlasov")
    print(yaml.dump(manifest, default_flow_style=False, sort_keys=False))


if __name__ == "__main__":
    main()
