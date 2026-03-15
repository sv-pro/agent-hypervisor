"""
agent_hypervisor.gateway — Tool Gateway / Execution Switch.

A centralized HTTP gateway that enforces provenance-based execution control
over agent tool calls, using the existing ProvenanceFirewall and PolicyEngine
as the enforcement engines.

Architecture:
    agent / client
         ↓  HTTP POST /tools/execute
    Tool Gateway   (gateway_server.py)
         ↓
    ExecutionRouter  (execution_router.py)
         ↓  PolicyEngine.evaluate()  +  ProvenanceFirewall.check()
    Provenance Firewall
         ↓  allow / deny / ask
    Tool Adapter   (tool_registry.py)
         ↓
    External System  (email · HTTP · filesystem)

Public surface:
    from agent_hypervisor.gateway.gateway_server import create_app
    from agent_hypervisor.gateway.tool_registry import ToolRegistry, ToolDefinition
    from agent_hypervisor.gateway.execution_router import ExecutionRouter, ArgSpec
    from agent_hypervisor.gateway.config_loader import load_config, GatewayConfig
"""
