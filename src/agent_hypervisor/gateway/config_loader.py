"""
config_loader.py — Load and validate gateway_config.yaml.

The gateway configuration controls:
  • which tools are registered
  • which policy YAML file to load for hot-reloadable rules
  • optional task manifest for structural ProvenanceFirewall checks
  • server host/port
  • trace buffer size

Usage:
    from agent_hypervisor.gateway.config_loader import load_config

    config = load_config("gateway_config.yaml")
    print(config.server.port)        # 8080
    print(config.policy_file)        # "policies/default_policy.yaml"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8080


@dataclass
class TracesConfig:
    max_entries: int = 1000


@dataclass
class StorageConfig:
    """
    Persistent storage configuration.

    backend: storage backend identifier; currently only "jsonl" is supported.
    path:    root directory for all storage files.
             Traces go to {path}/traces.jsonl
             Approvals go to {path}/approvals/{id}.json
             Policy history goes to {path}/policy_history.jsonl
    """
    backend: str = "jsonl"
    path: str = ".data"


@dataclass
class GatewayConfig:
    """
    Top-level gateway configuration.

    tools:          list of tool names to register on startup
    policy_file:    path to YAML policy file for PolicyEngine (hot-reloadable)
    task_manifest:  optional path to task manifest for ProvenanceFirewall
    server:         host and port settings
    traces:         trace buffer configuration
    storage:        persistent storage configuration
    """
    tools: list[str] = field(default_factory=lambda: ["send_email", "http_post", "read_file"])
    policy_file: str = "policies/default_policy.yaml"
    task_manifest: Optional[str] = None          # e.g. "manifests/task_allow_send.yaml"
    server: ServerConfig = field(default_factory=ServerConfig)
    traces: TracesConfig = field(default_factory=TracesConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)


def load_config(path: str | Path = "gateway_config.yaml") -> GatewayConfig:
    """
    Load GatewayConfig from a YAML file.

    Missing keys fall back to defaults. Unknown keys are ignored.
    Raises FileNotFoundError if the file does not exist.
    """
    raw = yaml.safe_load(Path(path).read_text()) or {}

    server_raw = raw.get("server", {})
    server = ServerConfig(
        host=server_raw.get("host", "127.0.0.1"),
        port=int(server_raw.get("port", 8080)),
    )

    traces_raw = raw.get("traces", {})
    traces = TracesConfig(
        max_entries=int(traces_raw.get("max_entries", 1000)),
    )

    storage_raw = raw.get("storage", {})
    storage = StorageConfig(
        backend=storage_raw.get("backend", "jsonl"),
        path=storage_raw.get("path", ".data"),
    )

    return GatewayConfig(
        tools=raw.get("tools", ["send_email", "http_post", "read_file"]),
        policy_file=raw.get("policy_file", "policies/default_policy.yaml"),
        task_manifest=raw.get("task_manifest"),
        server=server,
        traces=traces,
        storage=storage,
    )
