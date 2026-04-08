"""Tests for the Capability DSL — parser and validator."""

from __future__ import annotations

import pytest

from safe_agent_runtime_pro.capabilities.examples import EXAMPLE_REGISTRY_DICT
from safe_agent_runtime_pro.capabilities.models import (
    ActorInputSource,
    ContextRefSource,
    EmailConstraint,
    EnumConstraint,
    LiteralSource,
    ResolverRefSource,
    TextConstraint,
)
from safe_agent_runtime_pro.capabilities.parser import parse_registry
from safe_agent_runtime_pro.capabilities.validator import ValidationError, validate


# ---------------------------------------------------------------------------
# Parser — tools
# ---------------------------------------------------------------------------


def test_parse_empty_registry():
    registry = parse_registry({})
    assert registry.tools == {}
    assert registry.capabilities == {}
    assert registry.resolvers == {}


def test_parse_tool_with_args():
    registry = parse_registry({"tools": {"send_email": {"args": ["to", "body"]}}})
    tool = registry.tools["send_email"]
    assert tool.args == frozenset({"to", "body"})


def test_parse_tool_empty_args_list():
    registry = parse_registry({"tools": {"read_data": {"args": []}}})
    assert registry.tools["read_data"].args == frozenset()


def test_parse_tool_no_args_key_gives_none():
    """Omitting 'args' entirely means arg-name validation is skipped."""
    registry = parse_registry({"tools": {"flexible": {}}})
    assert registry.tools["flexible"].args is None


# ---------------------------------------------------------------------------
# Parser — resolvers
# ---------------------------------------------------------------------------


def test_parse_resolver():
    registry = parse_registry(
        {"resolvers": {"escalation_lookup": {"returns": "email"}}}
    )
    r = registry.resolvers["escalation_lookup"]
    assert r.name == "escalation_lookup"
    assert r.returns == "email"


def test_parse_resolver_missing_returns_raises():
    with pytest.raises(ValueError, match="'returns' is required"):
        parse_registry({"resolvers": {"bad": {}}})


# ---------------------------------------------------------------------------
# Parser — value sources
# ---------------------------------------------------------------------------


def test_parse_literal_source():
    registry = parse_registry(
        {
            "tools": {"send_email": {"args": ["to"]}},
            "capabilities": {
                "cap": {
                    "base_tool": "send_email",
                    "args": {
                        "to": {"valueFrom": {"literal": {"value": "security@company.com"}}},
                    },
                }
            },
        }
    )
    src = registry.capabilities["cap"].args["to"].value_source
    assert isinstance(src, LiteralSource)
    assert src.value == "security@company.com"


def test_parse_actor_input_source():
    registry = parse_registry(
        {
            "tools": {"send_email": {"args": ["body"]}},
            "capabilities": {
                "cap": {
                    "base_tool": "send_email",
                    "args": {"body": {"valueFrom": {"actor_input": {}}}},
                }
            },
        }
    )
    src = registry.capabilities["cap"].args["body"].value_source
    assert isinstance(src, ActorInputSource)


def test_parse_context_ref_source():
    registry = parse_registry(
        {
            "tools": {"send_email": {"args": ["sender"]}},
            "capabilities": {
                "cap": {
                    "base_tool": "send_email",
                    "args": {
                        "sender": {
                            "valueFrom": {"context_ref": {"ref": "current_user_email"}}
                        }
                    },
                }
            },
        }
    )
    src = registry.capabilities["cap"].args["sender"].value_source
    assert isinstance(src, ContextRefSource)
    assert src.ref == "current_user_email"


def test_parse_resolver_ref_source():
    registry = parse_registry(
        {
            "tools": {"send_email": {"args": ["to", "body"]}},
            "resolvers": {"my_resolver": {"returns": "email"}},
            "capabilities": {
                "cap": {
                    "base_tool": "send_email",
                    "args": {
                        "to": {"valueFrom": {"resolver_ref": {"name": "my_resolver"}}},
                        "body": {"valueFrom": {"actor_input": {}}},
                    },
                }
            },
        }
    )
    src = registry.capabilities["cap"].args["to"].value_source
    assert isinstance(src, ResolverRefSource)
    assert src.name == "my_resolver"


def test_parse_unknown_source_kind_raises():
    with pytest.raises(ValueError, match="unknown value source kind"):
        parse_registry(
            {
                "tools": {"t": {"args": ["x"]}},
                "capabilities": {
                    "cap": {
                        "base_tool": "t",
                        "args": {"x": {"valueFrom": {"magic_source": {}}}},
                    }
                },
            }
        )


def test_parse_multiple_source_kinds_raises():
    with pytest.raises(ValueError, match="exactly one source kind"):
        parse_registry(
            {
                "tools": {"t": {"args": ["x"]}},
                "capabilities": {
                    "cap": {
                        "base_tool": "t",
                        "args": {
                            "x": {
                                "valueFrom": {
                                    "literal": {"value": "a"},
                                    "actor_input": {},
                                }
                            }
                        },
                    }
                },
            }
        )


# ---------------------------------------------------------------------------
# Parser — constraints
# ---------------------------------------------------------------------------


def test_parse_email_constraint_with_domain():
    registry = parse_registry(
        {
            "tools": {"t": {"args": ["to"]}},
            "capabilities": {
                "cap": {
                    "base_tool": "t",
                    "args": {
                        "to": {
                            "valueFrom": {"actor_input": {}},
                            "constraints": {"kind": "email", "allow_domain": "company.com"},
                        }
                    },
                }
            },
        }
    )
    c = registry.capabilities["cap"].args["to"].constraint
    assert isinstance(c, EmailConstraint)
    assert c.allow_domain == "company.com"


def test_parse_email_constraint_no_domain():
    registry = parse_registry(
        {
            "tools": {"t": {"args": ["to"]}},
            "capabilities": {
                "cap": {
                    "base_tool": "t",
                    "args": {
                        "to": {
                            "valueFrom": {"actor_input": {}},
                            "constraints": {"kind": "email"},
                        }
                    },
                }
            },
        }
    )
    c = registry.capabilities["cap"].args["to"].constraint
    assert isinstance(c, EmailConstraint)
    assert c.allow_domain is None


def test_parse_text_constraint_with_max_length():
    registry = parse_registry(
        {
            "tools": {"t": {"args": ["body"]}},
            "capabilities": {
                "cap": {
                    "base_tool": "t",
                    "args": {
                        "body": {
                            "valueFrom": {"actor_input": {}},
                            "constraints": {"kind": "text", "max_length": 1000},
                        }
                    },
                }
            },
        }
    )
    c = registry.capabilities["cap"].args["body"].constraint
    assert isinstance(c, TextConstraint)
    assert c.max_length == 1000


def test_parse_enum_constraint():
    registry = parse_registry(
        {
            "tools": {"t": {"args": ["priority"]}},
            "capabilities": {
                "cap": {
                    "base_tool": "t",
                    "args": {
                        "priority": {
                            "valueFrom": {"actor_input": {}},
                            "constraints": {"kind": "enum", "values": ["low", "medium", "high"]},
                        }
                    },
                }
            },
        }
    )
    c = registry.capabilities["cap"].args["priority"].constraint
    assert isinstance(c, EnumConstraint)
    assert c.values == ("low", "medium", "high")


def test_parse_unknown_constraint_kind_raises():
    with pytest.raises(ValueError, match="unknown constraint kind"):
        parse_registry(
            {
                "tools": {"t": {"args": ["x"]}},
                "capabilities": {
                    "cap": {
                        "base_tool": "t",
                        "args": {
                            "x": {
                                "valueFrom": {"actor_input": {}},
                                "constraints": {"kind": "phone_number"},
                            }
                        },
                    }
                },
            }
        )


def test_parse_allow_domain_on_text_raises():
    """allow_domain is only valid for kind=email."""
    with pytest.raises(ValueError, match="allow_domain"):
        parse_registry(
            {
                "tools": {"t": {"args": ["body"]}},
                "capabilities": {
                    "cap": {
                        "base_tool": "t",
                        "args": {
                            "body": {
                                "valueFrom": {"actor_input": {}},
                                "constraints": {
                                    "kind": "text",
                                    "allow_domain": "company.com",
                                },
                            }
                        },
                    }
                },
            }
        )


def test_parse_allow_domain_on_enum_raises():
    with pytest.raises(ValueError, match="allow_domain"):
        parse_registry(
            {
                "tools": {"t": {"args": ["x"]}},
                "capabilities": {
                    "cap": {
                        "base_tool": "t",
                        "args": {
                            "x": {
                                "valueFrom": {"actor_input": {}},
                                "constraints": {
                                    "kind": "enum",
                                    "values": ["a"],
                                    "allow_domain": "company.com",
                                },
                            }
                        },
                    }
                },
            }
        )


def test_parse_missing_valuefrom_raises():
    with pytest.raises(ValueError, match="'valueFrom' is required"):
        parse_registry(
            {
                "tools": {"t": {"args": ["x"]}},
                "capabilities": {
                    "cap": {
                        "base_tool": "t",
                        "args": {"x": {"constraints": {"kind": "text"}}},
                    }
                },
            }
        )


def test_parse_missing_base_tool_raises():
    with pytest.raises(ValueError, match="'base_tool' is required"):
        parse_registry(
            {
                "tools": {"t": {"args": []}},
                "capabilities": {"cap": {"args": {}}},
            }
        )


# ---------------------------------------------------------------------------
# Validator — invalid base_tool
# ---------------------------------------------------------------------------


def test_validate_invalid_base_tool():
    registry = parse_registry(
        {
            "tools": {"read_data": {"args": []}},
            "capabilities": {
                "bad_cap": {"base_tool": "nonexistent_tool", "args": {}}
            },
        }
    )
    with pytest.raises(ValidationError, match="base_tool"):
        validate(registry)


# ---------------------------------------------------------------------------
# Validator — invalid resolver_ref
# ---------------------------------------------------------------------------


def test_validate_invalid_resolver_ref():
    registry = parse_registry(
        {
            "tools": {"send_email": {"args": ["to", "body"]}},
            "capabilities": {
                "cap": {
                    "base_tool": "send_email",
                    "args": {
                        "to": {
                            "valueFrom": {
                                "resolver_ref": {"name": "missing_resolver"}
                            }
                        },
                        "body": {"valueFrom": {"actor_input": {}}},
                    },
                }
            },
        }
    )
    with pytest.raises(ValidationError, match="resolver_ref"):
        validate(registry)


# ---------------------------------------------------------------------------
# Validator — invalid arg name
# ---------------------------------------------------------------------------


def test_validate_invalid_arg_name():
    """Capability arg not declared by the base tool must fail."""
    registry = parse_registry(
        {
            "tools": {"send_email": {"args": ["to", "body"]}},
            "capabilities": {
                "cap": {
                    "base_tool": "send_email",
                    "args": {
                        "to": {"valueFrom": {"actor_input": {}}},
                        "subject": {"valueFrom": {"actor_input": {}}},  # not declared
                    },
                }
            },
        }
    )
    with pytest.raises(ValidationError, match="subject"):
        validate(registry)


# ---------------------------------------------------------------------------
# Validator — literal email domain checks
# ---------------------------------------------------------------------------


def test_validate_literal_email_accepted_matching_domain():
    registry = parse_registry(
        {
            "tools": {"send_email": {"args": ["to"]}},
            "capabilities": {
                "cap": {
                    "base_tool": "send_email",
                    "args": {
                        "to": {
                            "valueFrom": {"literal": {"value": "security@company.com"}},
                            "constraints": {"kind": "email", "allow_domain": "company.com"},
                        }
                    },
                }
            },
        }
    )
    validate(registry)  # must not raise


def test_validate_literal_email_rejected_wrong_domain():
    registry = parse_registry(
        {
            "tools": {"send_email": {"args": ["to"]}},
            "capabilities": {
                "cap": {
                    "base_tool": "send_email",
                    "args": {
                        "to": {
                            "valueFrom": {"literal": {"value": "attacker@evil.com"}},
                            "constraints": {"kind": "email", "allow_domain": "company.com"},
                        }
                    },
                }
            },
        }
    )
    with pytest.raises(ValidationError, match="allow_domain"):
        validate(registry)


def test_validate_literal_email_no_domain_constraint_passes():
    registry = parse_registry(
        {
            "tools": {"send_email": {"args": ["to"]}},
            "capabilities": {
                "cap": {
                    "base_tool": "send_email",
                    "args": {
                        "to": {
                            "valueFrom": {"literal": {"value": "anyone@anywhere.com"}},
                            "constraints": {"kind": "email"},
                        }
                    },
                }
            },
        }
    )
    validate(registry)  # no domain restriction → must not raise


# ---------------------------------------------------------------------------
# Validator — tool with no declared args skips arg-name check
# ---------------------------------------------------------------------------


def test_validate_tool_no_args_key_skips_arg_name_check():
    """Tool that omits 'args' entirely: capability args are accepted without name check."""
    registry = parse_registry(
        {
            "tools": {"flexible_tool": {}},  # no 'args' key → args=None
            "capabilities": {
                "cap": {
                    "base_tool": "flexible_tool",
                    "args": {"any_arg": {"valueFrom": {"actor_input": {}}}},
                }
            },
        }
    )
    validate(registry)  # must not raise


def test_validate_tool_empty_args_rejects_undeclared_arg():
    """Tool with args=[] explicitly takes no parameters; any cap arg is invalid."""
    registry = parse_registry(
        {
            "tools": {"strict_tool": {"args": []}},
            "capabilities": {
                "cap": {
                    "base_tool": "strict_tool",
                    "args": {"unexpected": {"valueFrom": {"actor_input": {}}}},
                }
            },
        }
    )
    with pytest.raises(ValidationError, match="unexpected"):
        validate(registry)


# ---------------------------------------------------------------------------
# Worked examples — parse + validate
# ---------------------------------------------------------------------------


def test_example_registry_parses_and_validates():
    """All capabilities in the example registry must parse and validate cleanly."""
    registry = parse_registry(EXAMPLE_REGISTRY_DICT)
    validate(registry)


def test_example_send_report_to_security():
    """Example 1: literal-bound capability."""
    registry = parse_registry(EXAMPLE_REGISTRY_DICT)
    validate(registry)

    cap = registry.capabilities["send_report_to_security"]
    assert cap.base_tool == "send_email"

    to_arg = cap.args["to"]
    assert isinstance(to_arg.value_source, LiteralSource)
    assert to_arg.value_source.value == "security@company.com"
    assert to_arg.constraint is None  # no constraint on a literal fixed address

    body_arg = cap.args["body"]
    assert isinstance(body_arg.value_source, ActorInputSource)
    assert isinstance(body_arg.constraint, TextConstraint)
    assert body_arg.constraint.max_length == 5000


def test_example_send_internal_email():
    """Example 2: domain-constrained actor input."""
    registry = parse_registry(EXAMPLE_REGISTRY_DICT)
    validate(registry)

    cap = registry.capabilities["send_internal_email"]
    assert cap.base_tool == "send_email"

    to_arg = cap.args["to"]
    assert isinstance(to_arg.value_source, ActorInputSource)
    assert isinstance(to_arg.constraint, EmailConstraint)
    assert to_arg.constraint.allow_domain == "company.com"


def test_example_send_escalation():
    """Example 3: resolver-based indirect value."""
    registry = parse_registry(EXAMPLE_REGISTRY_DICT)
    validate(registry)

    cap = registry.capabilities["send_escalation"]
    assert cap.base_tool == "send_email"

    to_arg = cap.args["to"]
    assert isinstance(to_arg.value_source, ResolverRefSource)
    assert to_arg.value_source.name == "escalation_contact_lookup"

    # The resolver must be declared in the registry.
    assert "escalation_contact_lookup" in registry.resolvers
    assert registry.resolvers["escalation_contact_lookup"].returns == "email"
