"""
conftest.py — pytest configuration for the Agent Hypervisor test suite.

Adds the repo root to sys.path so that test modules can import hypervisor
and agent_stub directly, regardless of which directory pytest is invoked from.
"""

import sys
import os

_root = os.path.dirname(__file__)

# Add src/ so tests can import hypervisor, agent_stub directly (e.g. `from hypervisor import Hypervisor`).
# Add repo root so conftest itself and any root-level helpers are importable.
sys.path.insert(0, os.path.join(_root, "src"))
sys.path.insert(0, _root)
