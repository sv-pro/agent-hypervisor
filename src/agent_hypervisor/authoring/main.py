"""CLI entrypoint: python -m safe_agent_runtime_pro --world email_safe"""

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Safe MCP Gateway")
    parser.add_argument("--world", default="email_safe", help="World policy (base, email_safe)")
    args = parser.parse_args()

    from safe_agent_runtime_pro.integrations.mcp.server import run_mcp_gateway
    run_mcp_gateway(world=args.world)


if __name__ == "__main__":
    main()
