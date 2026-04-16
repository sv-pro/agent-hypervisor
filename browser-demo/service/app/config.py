"""
Service configuration.

Priority (highest to lowest):
  1. Environment variables  (AH_HOST, AH_PORT, AH_SESSION_TOKEN, …)
  2. config.yaml / config.yml in the working directory
  3. ~/.agent-hypervisor/config.yaml
  4. Built-in defaults
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

VERSION = "0.1.0"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 17841
DEFAULT_SESSION_TOKEN = "demo-local-token"
DEFAULT_BOOTSTRAP_PATH = Path.home() / ".agent-hypervisor" / "bootstrap.json"


@dataclass
class ServiceConfig:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    session_token: str = DEFAULT_SESSION_TOKEN
    bootstrap_enabled: bool = True
    bootstrap_path: Path = field(default_factory=lambda: DEFAULT_BOOTSTRAP_PATH)
    trace_store_path: Path = field(default_factory=lambda: Path("./data/traces.jsonl"))
    memory_store_path: Path = field(default_factory=lambda: Path("./data/memory.json"))
    version: str = VERSION

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


def load_config(config_file: Optional[str] = None) -> ServiceConfig:
    """Load config from file then override with environment variables."""
    config = ServiceConfig()

    # Candidate config file locations
    candidates: list[Path] = []
    if config_file:
        candidates.append(Path(config_file))
    candidates += [
        Path("config.yaml"),
        Path("config.yml"),
        Path.home() / ".agent-hypervisor" / "config.yaml",
    ]

    for path in candidates:
        if path.exists():
            with open(path) as fh:
                data = yaml.safe_load(fh) or {}
            _apply_yaml(config, data)
            break

    # Environment variable overrides
    if v := os.getenv("AH_HOST"):
        config.host = v
    if v := os.getenv("AH_PORT"):
        config.port = int(v)
    if v := os.getenv("AH_SESSION_TOKEN"):
        config.session_token = v
    if v := os.getenv("AH_BOOTSTRAP_PATH"):
        config.bootstrap_path = Path(v)
    if v := os.getenv("AH_TRACE_STORE_PATH"):
        config.trace_store_path = Path(v)
    if v := os.getenv("AH_MEMORY_STORE_PATH"):
        config.memory_store_path = Path(v)

    return config


def _apply_yaml(config: ServiceConfig, data: dict) -> None:
    mapping = {
        "host": ("host", str),
        "port": ("port", int),
        "session_token": ("session_token", str),
        "bootstrap_enabled": ("bootstrap_enabled", bool),
        "bootstrap_path": ("bootstrap_path", Path),
        "trace_store_path": ("trace_store_path", Path),
        "memory_store_path": ("memory_store_path", Path),
    }
    for yaml_key, (attr, cast) in mapping.items():
        if yaml_key in data:
            setattr(config, attr, cast(data[yaml_key]))
