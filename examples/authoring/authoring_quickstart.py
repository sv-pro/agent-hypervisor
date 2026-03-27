"""Authoring quickstart.

Shows how to define, parse, and validate capabilities using the pro DSL.
No runtime enforcement is exercised here — this is purely the authoring side.

Run:
    python examples/authoring_quickstart.py
"""

from __future__ import annotations

from safe_agent_runtime_pro.capabilities.examples import EXAMPLE_REGISTRY_DICT
from safe_agent_runtime_pro.capabilities.parser import parse_registry
from safe_agent_runtime_pro.capabilities.validator import validate
from safe_agent_runtime_pro.worlds import load_world

# ---------------------------------------------------------------------------
# Step 1: Define your capabilities as a dict (or load from YAML)
# ---------------------------------------------------------------------------

# We reuse the built-in example dict here. In your project this would come
# from a YAML file via:
#
#   import yaml
#   from safe_agent_runtime_pro.capabilities.parser import parse_registry
#   with open("capabilities.yaml") as f:
#       data = yaml.safe_load(f)
#   registry = parse_registry(data)
#
# You can also build the dict in Python directly.

registry_dict: dict = EXAMPLE_REGISTRY_DICT

# ---------------------------------------------------------------------------
# Step 2: Parse the dict into a typed registry
# ---------------------------------------------------------------------------

registry = parse_registry(registry_dict)

print("=== Tools ===")
for name, tool in registry.tools.items():
    args_display = list(tool.args) if tool.args is not None else "(untyped)"
    print(f"  {name}: args={args_display}")

print()
print("=== Resolvers ===")
for name, resolver in registry.resolvers.items():
    print(f"  {name}: returns={resolver.returns}")

print()
print("=== Capabilities ===")
for name, cap in registry.capabilities.items():
    print(f"  {name} (base_tool={cap.base_tool})")
    for arg_name, arg_def in cap.args.items():
        source_type = type(arg_def.value_source).__name__
        constraint_type = type(arg_def.constraint).__name__ if arg_def.constraint else "none"
        print(f"    {arg_name}: source={source_type}, constraint={constraint_type}")

# ---------------------------------------------------------------------------
# Step 3: Validate the registry (semantic checks)
# ---------------------------------------------------------------------------

print()
print("=== Validation ===")
try:
    validate(registry)
    print("  OK — all capability definitions are well-formed")
except Exception as e:
    print(f"  INVALID: {e}")

# ---------------------------------------------------------------------------
# Step 4: What you'd do next — load a world and pass it to core
# ---------------------------------------------------------------------------

print()
print("=== World config (for passing to SafeMCPProxy) ===")
world = load_world("email_safe")
proxy_kwargs = world.to_proxy_kwargs()
for key, value in proxy_kwargs.items():
    print(f"  {key}: {value}")

print()
print("Next step: pass proxy_kwargs to SafeMCPProxy from safe-agent-runtime-core.")
print("The registry above tells you what capabilities exist and how args are constrained.")
print("The world config tells core which capabilities are allowed at runtime.")
