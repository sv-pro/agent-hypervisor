"""draft.py — LLM-assisted World Manifest authoring.

Uses the Claude API at design-time to generate a manifest draft from a
natural-language description of the agent's world.

This implements the "AI Aikido" principle: LLM intelligence is used at
design-time to author the manifest. The generated YAML is a starting point
that the human reviews and refines before the v2 compiler accepts it.

The LLM is NEVER on the execution path. It participates only here, at
manifest authoring time.

Usage (CLI):
    ahc draft --description "Email assistant that can read and send emails"
    ahc draft --description "..." --output my_manifest.yaml

Usage (API):
    from compiler.draft import draft_manifest
    yaml_str = draft_manifest("Email assistant that can read and send emails")
"""

from __future__ import annotations

import os
from pathlib import Path

DRAFT_SYSTEM_PROMPT = """\
You are a security-focused World Manifest author for the Agent Hypervisor system.

Your task: generate a complete, valid World Manifest v2.0 YAML from a natural-language
description of an agent's world. The manifest defines what the agent can and cannot do.

The manifest must:
1. Be valid v2.0 format (version: "2.0" at the top)
2. Include a manifest.name and manifest.description
3. Include all required sections: actions, trust_channels, capability_matrix
4. Follow the fail-closed principle: deny everything not explicitly permitted
5. Include realistic world-model sections: entities, actors, data_classes, trust_zones,
   confirmation_classes, side_effect_surfaces, transition_policies

Security rules to follow:
- External-boundary actions (those that send data outside) must have taint_passthrough: true
- Irreversible actions must have requires_approval: true and confirmation_class: hard_confirm
- Trust channels for external content (email, web) must have taint_by_default: true
- The capability_matrix must follow least-privilege (UNTRUSTED gets read_only at most)
- Transition policies must include at least one deny for internal → external zone crossing

Output ONLY the YAML manifest, no prose before or after. Start with the version: "2.0" line.
"""

DRAFT_USER_TEMPLATE = """\
Generate a World Manifest v2.0 for the following agent:

{description}

The manifest should be complete and production-ready, with all sections filled in.
Include realistic entities, actors, data classes, trust zones, and observability specs.
Follow the security rules strictly.
"""


def draft_manifest(
    description: str,
    *,
    model: str = "claude-opus-4-6",
    api_key: str | None = None,
) -> str:
    """Generate a manifest YAML draft from a natural-language description.

    Uses the Claude API at design-time. The LLM is not on the execution path.

    Args:
        description: Natural-language description of the agent and its world.
        model:       Claude model to use (default: claude-opus-4-6).
        api_key:     Anthropic API key. Falls back to ANTHROPIC_API_KEY env var.

    Returns:
        YAML string for the draft manifest. May contain TODO markers where the
        LLM could not infer a value — review before compiling.

    Raises:
        ImportError: if the anthropic package is not installed.
        ValueError: if no API key is available.
    """
    try:
        import anthropic  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "The 'anthropic' package is required for ahc draft. "
            "Install it with: pip install anthropic"
        ) from exc

    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise ValueError(
            "No Anthropic API key found. Set ANTHROPIC_API_KEY or pass --api-key."
        )

    client = anthropic.Anthropic(api_key=key)
    message = client.messages.create(
        model=model,
        max_tokens=4096,
        system=DRAFT_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": DRAFT_USER_TEMPLATE.format(description=description),
            }
        ],
    )

    raw = message.content[0].text.strip()

    # Strip markdown code fences if the model wrapped the YAML
    if raw.startswith("```"):
        lines = raw.split("\n")
        # Remove opening fence
        lines = lines[1:]
        # Remove closing fence
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines)

    return raw


def draft_manifest_to_file(
    description: str,
    output: str | Path,
    *,
    model: str = "claude-opus-4-6",
    api_key: str | None = None,
) -> Path:
    """Draft a manifest and write it to a file.

    Returns the path to the written file.
    """
    yaml_str = draft_manifest(description, model=model, api_key=api_key)
    path = Path(output)
    path.write_text(yaml_str)
    return path
