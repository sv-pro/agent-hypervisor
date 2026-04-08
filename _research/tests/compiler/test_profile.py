import pytest
from agent_world_compiler.observe import ExecutionTrace, ToolCall
from agent_world_compiler.profile import profile_trace, build_manifest
from agent_world_compiler.schema import WorldManifest


def make_trace(calls):
    return ExecutionTrace(workflow_id="test", calls=[
        ToolCall(**c) for c in calls
    ])


class TestSafeCompression:
    """Profile must only include safe=True tool calls."""

    def test_excludes_unsafe_calls(self):
        trace = make_trace([
            {"tool": "read_file", "params": {"path": "docs/a.md"}, "safe": True},
            {"tool": "read_file", "params": {"path": "/etc/passwd"}, "safe": False},
        ])
        caps = profile_trace(trace)
        assert len(caps) == 1
        assert caps[0].tool == "read_file"
        # Only the safe path should appear
        assert "docs/a.md" in caps[0].constraints.get("paths", [])
        assert "/etc/passwd" not in caps[0].constraints.get("paths", [])

    def test_all_unsafe_yields_empty_profile(self):
        trace = make_trace([
            {"tool": "exec_shell", "params": {"command": "rm -rf /"}, "safe": False},
            {"tool": "read_file", "params": {"path": "/etc/shadow"}, "safe": False},
        ])
        caps = profile_trace(trace)
        assert caps == []

    def test_mixed_trace_only_safe(self):
        trace = make_trace([
            {"tool": "web_search", "params": {"domain": "docs.python.org"}, "safe": True},
            {"tool": "web_search", "params": {"domain": "evil.com"}, "safe": False},
        ])
        caps = profile_trace(trace)
        assert len(caps) == 1
        domains = caps[0].constraints.get("domains", [])
        assert any(d == "docs.python.org" for d in domains)
        assert not any(d == "evil.com" for d in domains)


class TestNoCapabilityExpansion:
    """Profile must never grant more than what was safely observed."""

    def test_no_unobserved_tool(self):
        trace = make_trace([
            {"tool": "read_file", "params": {"path": "docs/a.md"}, "safe": True},
        ])
        caps = profile_trace(trace)
        tool_names = [c.tool for c in caps]
        assert "exec_shell" not in tool_names
        assert "write_file" not in tool_names

    def test_no_unobserved_path(self):
        trace = make_trace([
            {"tool": "read_file", "params": {"path": "docs/a.md"}, "safe": True},
        ])
        caps = profile_trace(trace)
        paths = caps[0].constraints.get("paths", [])
        assert "docs/a.md" in paths
        assert "/etc/passwd" not in paths
        assert "docs/b.md" not in paths

    def test_no_unobserved_domain(self):
        trace = make_trace([
            {"tool": "web_search", "params": {"domain": "pypi.org"}, "safe": True},
        ])
        caps = profile_trace(trace)
        domains = caps[0].constraints.get("domains", [])
        assert any(d == "pypi.org" for d in domains)
        assert not any(d == "evil.com" for d in domains)


class TestBuildManifest:
    def test_returns_workflow_manifest(self):
        trace = make_trace([
            {"tool": "read_file", "params": {"path": "docs/a.md"}, "safe": True},
        ])
        manifest = build_manifest(trace)
        assert isinstance(manifest, WorldManifest)
        assert manifest.workflow_id == "test"

    def test_custom_workflow_id(self):
        trace = make_trace([
            {"tool": "read_file", "params": {"path": "docs/a.md"}, "safe": True},
        ])
        manifest = build_manifest(trace, workflow_id="my-workflow")
        assert manifest.workflow_id == "my-workflow"
