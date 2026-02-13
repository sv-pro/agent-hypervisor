import pytest
from hypervisor import Hypervisor

@pytest.fixture
def clean_hypervisor():
    # Helper to load the default policy for each test
    return Hypervisor("policy.yaml")

def test_allowed_tool(clean_hypervisor):
    intent = {"tool": "read_file", "args": "valid_file.txt"}
    result = clean_hypervisor.evaluate(intent)
    assert result["status"] == "ALLOWED"

def test_forbidden_pattern_rm_rf(clean_hypervisor):
    intent = {"tool": "execute_shell", "args": "rm -rf /"}
    result = clean_hypervisor.evaluate(intent)
    assert result["status"] == "BLOCKED"
    assert "forbidden pattern" in result["reason"].lower()

def test_forbidden_pattern_api_export(clean_hypervisor):
    intent = {"tool": "execute_shell", "args": "echo $API_KEY > api_key_export"}
    result = clean_hypervisor.evaluate(intent)
    assert result["status"] == "BLOCKED"
    assert "forbidden pattern" in result["reason"].lower()

def test_state_limit_enforcement(clean_hypervisor):
    # Open 3 files (allowed)
    for i in range(3):
        intent = {"tool": "read_file", "args": f"file_{i}.txt"}
        assert clean_hypervisor.evaluate(intent)["status"] == "ALLOWED"
    
    # Try 4th file (should block)
    intent = {"tool": "read_file", "args": "file_overflow.txt"}
    result = clean_hypervisor.evaluate(intent)
    assert result["status"] == "BLOCKED"
    assert "state limit reached" in result["reason"].lower()

def test_unknown_tool(clean_hypervisor):
    intent = {"tool": "format_disk", "args": "/dev/sda"}
    result = clean_hypervisor.evaluate(intent)
    assert result["status"] == "BLOCKED"
    assert "not in allowed_tools" in result["reason"].lower()
