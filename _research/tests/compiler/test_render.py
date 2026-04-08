import pytest
from agent_world_compiler.schema import WorldManifest, CapabilityConstraint
from agent_world_compiler.render import render_manifest, RenderedTool, CapabilityViolation


def make_manifest(caps):
    return WorldManifest(
        workflow_id="test",
        capabilities=[CapabilityConstraint(**c) for c in caps],
    )


class TestDeterministicRenderingNames:
    def test_name_format(self):
        manifest = make_manifest([{"tool": "read_file", "constraints": {}}])
        rendered = render_manifest(manifest)
        assert "rendered__read_file" in rendered

    def test_name_is_deterministic(self):
        manifest = make_manifest([
            {"tool": "read_file", "constraints": {}},
            {"tool": "web_search", "constraints": {}},
        ])
        rendered1 = render_manifest(manifest)
        rendered2 = render_manifest(manifest)
        assert set(rendered1.keys()) == set(rendered2.keys())
        assert "rendered__read_file" in rendered1
        assert "rendered__web_search" in rendered1

    def test_rendered_tool_instance(self):
        manifest = make_manifest([{"tool": "my_tool", "constraints": {}}])
        rendered = render_manifest(manifest)
        assert isinstance(rendered["rendered__my_tool"], RenderedTool)


class TestCapabilityViolation:
    def test_raises_on_disallowed_path(self):
        manifest = make_manifest([
            {"tool": "read_file", "constraints": {"paths": ["docs/**"]}}
        ])
        rendered = render_manifest(manifest)
        tool = rendered["rendered__read_file"]
        with pytest.raises(CapabilityViolation):
            tool(path="/etc/passwd")

    def test_allows_permitted_path(self):
        manifest = make_manifest([
            {"tool": "read_file", "constraints": {"paths": ["docs/**"]}}
        ])
        rendered = render_manifest(manifest)
        tool = rendered["rendered__read_file"]
        result = tool(path="docs/index.md")
        assert result is not None

    def test_raises_on_disallowed_domain(self):
        manifest = make_manifest([
            {"tool": "web_search", "constraints": {"domains": ["docs.python.org"]}}
        ])
        rendered = render_manifest(manifest)
        tool = rendered["rendered__web_search"]
        with pytest.raises(CapabilityViolation):
            tool(domain="evil.com")

    def test_allows_permitted_domain(self):
        manifest = make_manifest([
            {"tool": "web_search", "constraints": {"domains": ["docs.python.org"]}}
        ])
        rendered = render_manifest(manifest)
        tool = rendered["rendered__web_search"]
        result = tool(domain="docs.python.org")
        assert result is not None
