"""
config.py — Feature flags for the Program Layer.

All flags are module-level constants resolved once at import time.
Override by setting environment variables before the first import, or by
patching the module attribute in tests.

ENABLE_PROGRAM_LAYER
    Master toggle for program-layer features.  When False, callers should
    fall back to DirectExecutionPlan or skip program-layer processing
    entirely.  Default: True.

    Environment variable: AGENT_HYPERVISOR_ENABLE_PROGRAM_LAYER
    Set to "0", "false", "no", or "off" (case-insensitive) to disable.

    Override in code::

        import agent_hypervisor.program_layer.config as program_config
        program_config.ENABLE_PROGRAM_LAYER = False

    Override via environment::

        AGENT_HYPERVISOR_ENABLE_PROGRAM_LAYER=0 python my_script.py
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Feature flags
# ---------------------------------------------------------------------------

_OFF_VALUES = frozenset({"0", "false", "no", "off"})

ENABLE_PROGRAM_LAYER: bool = (
    os.environ.get("AGENT_HYPERVISOR_ENABLE_PROGRAM_LAYER", "1").strip().lower()
    not in _OFF_VALUES
)
"""
Master toggle for the program layer.  True by default.

Callers that need to conditionally use the program layer::

    from program_layer.config import ENABLE_PROGRAM_LAYER
    if ENABLE_PROGRAM_LAYER:
        runner = ProgramRunner(...)
        trace = runner.run(program)
    else:
        # fall back to direct execution
        ...
"""
