"""Manifest: load, save, and validate world manifest declarations."""

import json
from pathlib import Path

import yaml

from .schema import WorldManifest, manifest_from_dict, manifest_to_dict, validate_manifest_dict


def load_manifest(path: Path | str) -> WorldManifest:
    """Load a WorldManifest from a YAML or JSON file.

    The file format is detected from the file extension (``.yaml`` / ``.yml``
    for YAML, ``.json`` for JSON).

    Args:
        path: Path to the manifest file.

    Returns:
        Parsed and validated WorldManifest.

    Raises:
        jsonschema.ValidationError: If the manifest fails schema validation.
    """
    path = Path(path)
    with path.open() as fh:
        if path.suffix in {".yaml", ".yml"}:
            data = yaml.safe_load(fh)
        else:
            data = json.load(fh)
    validate_manifest_dict(data)
    return manifest_from_dict(data)


def save_manifest(manifest: WorldManifest, path: Path | str) -> None:
    """Save a WorldManifest to a YAML file.

    Args:
        manifest: The manifest to serialize.
        path: Destination file path.
    """
    path = Path(path)
    data = manifest_to_dict(manifest)
    with path.open("w") as fh:
        yaml.dump(data, fh, default_flow_style=False, sort_keys=False)


def manifest_summary(manifest: WorldManifest) -> str:
    """Return a human-readable summary of a WorldManifest.

    Args:
        manifest: The manifest to summarize.

    Returns:
        Multi-line string describing the manifest's capabilities.
    """
    lines = [
        f"Workflow: {manifest.workflow_id}  (version {manifest.version})",
        f"Capabilities ({len(manifest.capabilities)}):",
    ]
    for cap in manifest.capabilities:
        if "paths" in cap.constraints:
            detail = "paths: " + ", ".join(cap.constraints["paths"])
        elif "domains" in cap.constraints:
            detail = "domains: " + ", ".join(cap.constraints["domains"])
        elif cap.constraints:
            detail = str(cap.constraints)
        else:
            detail = "unrestricted"
        lines.append(f"  - {cap.tool}: {detail}")
    return "\n".join(lines)
