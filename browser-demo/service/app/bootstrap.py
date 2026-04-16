"""
Bootstrap file writer.

When the service starts it writes a JSON file containing connection info.
The extension (or any other client) can read this file to discover the service.

Default path: ~/.agent-hypervisor/bootstrap.json
Override via AH_BOOTSTRAP_PATH env var or bootstrap_path in config.yaml.
"""
from __future__ import annotations

import json
from pathlib import Path

from .config import ServiceConfig


def write_bootstrap(config: ServiceConfig) -> Path:
    """Write bootstrap.json and return its path."""
    path = config.bootstrap_path
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "host": config.host,
        "port": config.port,
        "base_url": config.base_url,
        "session_token": config.session_token,
        "version": config.version,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def remove_bootstrap(config: ServiceConfig) -> None:
    """Remove bootstrap.json on service shutdown."""
    try:
        config.bootstrap_path.unlink(missing_ok=True)
    except OSError:
        pass
