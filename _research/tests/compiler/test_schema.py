import pytest
import jsonschema
from agent_world_compiler.schema import (
    WorldManifest, CapabilityConstraint,
    manifest_to_dict, manifest_from_dict, validate_manifest_dict
)


class TestManifestSerialization:
    def test_round_trip(self):
        manifest = WorldManifest(
            workflow_id="test",
            capabilities=[
                CapabilityConstraint(tool="read_file", constraints={"paths": ["docs/**"]})
            ]
        )
        d = manifest_to_dict(manifest)
        restored = manifest_from_dict(d)
        assert restored.workflow_id == manifest.workflow_id
        assert restored.capabilities[0].tool == "read_file"

    def test_validate_valid(self):
        d = {
            "workflow_id": "test",
            "version": "1.0",
            "capabilities": [{"tool": "read_file", "constraints": {}}],
            "metadata": {}
        }
        validate_manifest_dict(d)  # should not raise

    def test_validate_missing_workflow_id(self):
        d = {"version": "1.0", "capabilities": []}
        with pytest.raises(jsonschema.ValidationError):
            validate_manifest_dict(d)
