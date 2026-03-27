"""Example capability registry definitions.

These definitions serve as documentation examples and test fixtures.
They correspond to the three worked examples in docs/capability-dsl.md.

Use ``parse_registry(EXAMPLE_REGISTRY_DICT)`` to obtain a typed registry,
then ``validate(registry)`` to confirm it is well-formed.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Full registry dict (YAML-equivalent, expressed as Python dicts)
# ---------------------------------------------------------------------------

EXAMPLE_REGISTRY_DICT: dict = {
    "tools": {
        "send_email": {"args": ["to", "body"]},
        "read_data": {"args": []},
        "summarize": {"args": ["content"]},
    },
    "resolvers": {
        "escalation_contact_lookup": {"returns": "email"},
        "primary_security_contact": {"returns": "email"},
    },
    "capabilities": {
        # ------------------------------------------------------------------
        # Example 1: literal-bound capability
        # 'to' is fixed at definition time. Actors supply only the body.
        # The destination address cannot be changed by the actor or by tainted
        # input — it is baked into the capability definition.
        # ------------------------------------------------------------------
        "send_report_to_security": {
            "base_tool": "send_email",
            "args": {
                "to": {
                    "valueFrom": {"literal": {"value": "security@company.com"}},
                },
                "body": {
                    "valueFrom": {"actor_input": {}},
                    "constraints": {"kind": "text", "max_length": 5000},
                },
            },
        },
        # ------------------------------------------------------------------
        # Example 2: domain-constrained actor input
        # The actor supplies the address but it must be within company.com.
        # An address outside that domain is rejected at validation time
        # (for literals) or enforcement time (for actor-supplied values).
        # ------------------------------------------------------------------
        "send_internal_email": {
            "base_tool": "send_email",
            "args": {
                "to": {
                    "valueFrom": {"actor_input": {}},
                    "constraints": {"kind": "email", "allow_domain": "company.com"},
                },
                "body": {
                    "valueFrom": {"actor_input": {}},
                    "constraints": {"kind": "text", "max_length": 5000},
                },
            },
        },
        # ------------------------------------------------------------------
        # Example 3: resolver-based indirect value
        # 'to' is resolved at call time by a named resolver. The actor cannot
        # supply or influence the destination address.
        # ------------------------------------------------------------------
        "send_escalation": {
            "base_tool": "send_email",
            "args": {
                "to": {
                    "valueFrom": {"resolver_ref": {"name": "escalation_contact_lookup"}},
                },
                "body": {
                    "valueFrom": {"actor_input": {}},
                    "constraints": {"kind": "text"},
                },
            },
        },
        # ------------------------------------------------------------------
        # Supplementary: summarize with a length cap
        # ------------------------------------------------------------------
        "summarize_text": {
            "base_tool": "summarize",
            "args": {
                "content": {
                    "valueFrom": {"actor_input": {}},
                    "constraints": {"kind": "text", "max_length": 10000},
                },
            },
        },
    },
}

__all__ = ["EXAMPLE_REGISTRY_DICT"]
