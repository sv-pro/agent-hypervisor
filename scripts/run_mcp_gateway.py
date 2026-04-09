"""
run_mcp_gateway.py — Start the Agent Hypervisor MCP Gateway.

Usage:
    python scripts/run_mcp_gateway.py
    python scripts/run_mcp_gateway.py --manifest manifests/example_world.yaml
    python scripts/run_mcp_gateway.py --manifest manifests/read_only_world.yaml --no-policy
    python scripts/run_mcp_gateway.py --host 0.0.0.0 --port 9000

The gateway enforces the given WorldManifest YAML at the MCP protocol level:
  - tools/list returns only manifest-declared tools (undeclared tools do not exist)
  - tools/call is deterministically checked against the manifest + optional policy

By default, the bundled provenance firewall policy is loaded. Pass --no-policy
to run manifest-only enforcement without the policy layer.
"""

import argparse
import sys
from pathlib import Path

# Ensure the src tree is importable when run directly from the repo root.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import uvicorn

from agent_hypervisor.hypervisor.mcp_gateway import create_mcp_app


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Agent Hypervisor MCP Gateway",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--manifest",
        default="manifests/example_world.yaml",
        help="Path to the WorldManifest YAML (default: manifests/example_world.yaml)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8090,
        help="Bind port (default: 8090)",
    )
    parser.add_argument(
        "--no-policy",
        action="store_true",
        help="Disable the default provenance firewall policy (manifest-only enforcement)",
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"Error: manifest not found: {manifest_path}", file=sys.stderr)
        sys.exit(1)

    use_default_policy = not args.no_policy
    app = create_mcp_app(manifest_path, use_default_policy=use_default_policy)

    policy_label = "default provenance policy" if use_default_policy else "manifest-only"
    print(f"Agent Hypervisor MCP Gateway")
    print(f"  manifest : {manifest_path}")
    print(f"  policy   : {policy_label}")
    print(f"  endpoint : http://{args.host}:{args.port}/mcp")
    print(f"  health   : http://{args.host}:{args.port}/mcp/health")
    print()

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
