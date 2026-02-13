"""
conftest.py — pytest configuration for the Agent Hypervisor test suite.

Adds the repo root to sys.path so that test modules can import hypervisor
and agent_stub directly, regardless of which directory pytest is invoked from.
"""

import sys
import os

# Ensure the repo root is on the path so tests can import hypervisor, agent_stub, etc.
sys.path.insert(0, os.path.dirname(__file__))
