"""
tests/test_compiler.py — Unit tests for the World Manifest compiler.

Key property verified: same manifest → same artifacts, always.
These tests do not invoke an LLM. All assertions are deterministic.

Run with:
    pytest tests/test_compiler.py
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from compiler.loader import load, ManifestValidationError
from compiler.emitter import emit

MANIFESTS_DIR = Path(__file__).parent.parent / "manifests" / "examples"
EMAIL_MANIFEST = MANIFESTS_DIR / "email-safe-assistant.yaml"
MCP_MANIFEST = MANIFESTS_DIR / "mcp-gateway-demo.yaml"
BROWSER_MANIFEST = MANIFESTS_DIR / "browser-agent-demo.yaml"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_output(tmp_path: Path) -> Path:
    return tmp_path / "compiled"


@pytest.fixture
def email_manifest() -> dict:
    return load(EMAIL_MANIFEST)


@pytest.fixture
def mcp_manifest() -> dict:
    return load(MCP_MANIFEST)


@pytest.fixture
def browser_manifest() -> dict:
    return load(BROWSER_MANIFEST)


# ---------------------------------------------------------------------------
# Loader tests
# ---------------------------------------------------------------------------

class TestLoader:
    def test_loads_email_manifest(self) -> None:
        manifest = load(EMAIL_MANIFEST)
        assert manifest["manifest"]["name"] == "email-safe-assistant"

    def test_loads_mcp_manifest(self) -> None:
        manifest = load(MCP_MANIFEST)
        assert manifest["manifest"]["name"] == "mcp-gateway-demo"

    def test_loads_browser_manifest(self) -> None:
        manifest = load(BROWSER_MANIFEST)
        assert manifest["manifest"]["name"] == "browser-agent-demo"

    def test_missing_file_raises(self) -> None:
        with pytest.raises(ManifestValidationError, match="not found"):
            load("/nonexistent/path/manifest.yaml")

    def test_missing_required_section_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text("manifest:\n  name: test\n  version: '1.0.0'\n")
        with pytest.raises(ManifestValidationError, match="missing required section"):
            load(bad)

    def test_invalid_trust_level_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text(
            "manifest:\n  name: t\n  version: '1.0'\n"
            "actions:\n  - name: foo\n    reversible: true\n    side_effects: [internal_read]\n"
            "trust_channels:\n  - name: x\n    trust_level: INVALID\n    taint_by_default: false\n"
            "capability_matrix:\n  TRUSTED: [internal_read]\n"
        )
        with pytest.raises(ManifestValidationError, match="is invalid"):
            load(bad)

    def test_invalid_escalation_decision_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text(
            "manifest:\n  name: t\n  version: '1.0'\n"
            "actions:\n  - name: foo\n    reversible: true\n    side_effects: [internal_read]\n"
            "trust_channels:\n  - name: user\n    trust_level: TRUSTED\n    taint_by_default: false\n"
            "capability_matrix:\n  TRUSTED: [internal_read]\n"
            "escalation_conditions:\n  - id: e1\n    trigger: {}\n    decision: INVALID\n"
        )
        with pytest.raises(ManifestValidationError, match="invalid"):
            load(bad)


# ---------------------------------------------------------------------------
# Emitter: artifact completeness
# ---------------------------------------------------------------------------

EXPECTED_ARTIFACTS = {
    "policy_table.json",
    "capability_matrix.json",
    "taint_rules.json",
    "escalation_table.json",
    "provenance_schema.json",
    "action_schemas.json",
    "manifest_meta.json",
}


class TestEmitterArtifacts:
    def test_all_artifacts_written(self, email_manifest: dict, tmp_output: Path) -> None:
        written = emit(email_manifest, tmp_output)
        assert set(written.keys()) == EXPECTED_ARTIFACTS

    def test_all_artifacts_are_valid_json(self, email_manifest: dict, tmp_output: Path) -> None:
        written = emit(email_manifest, tmp_output)
        for name, path in written.items():
            data = json.loads(path.read_text())
            assert isinstance(data, dict), f"{name} should be a JSON object"

    def test_output_dir_is_created(self, email_manifest: dict, tmp_output: Path) -> None:
        assert not tmp_output.exists()
        emit(email_manifest, tmp_output)
        assert tmp_output.is_dir()


# ---------------------------------------------------------------------------
# Emitter: determinism invariant
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_manifest_same_output(self, email_manifest: dict, tmp_path: Path) -> None:
        """Core invariant: same manifest → identical artifacts on every run."""
        out1 = tmp_path / "run1"
        out2 = tmp_path / "run2"
        emit(email_manifest, out1)
        emit(email_manifest, out2)
        for artifact in EXPECTED_ARTIFACTS:
            content1 = (out1 / artifact).read_text()
            content2 = (out2 / artifact).read_text()
            assert content1 == content2, f"{artifact} differs between runs"

    def test_content_hash_changes_with_manifest(
        self, email_manifest: dict, mcp_manifest: dict, tmp_path: Path
    ) -> None:
        """Different manifests produce different content hashes."""
        out_email = tmp_path / "email"
        out_mcp = tmp_path / "mcp"
        emit(email_manifest, out_email)
        emit(mcp_manifest, out_mcp)
        hash_email = json.loads((out_email / "manifest_meta.json").read_text())["content_hash"]
        hash_mcp = json.loads((out_mcp / "manifest_meta.json").read_text())["content_hash"]
        assert hash_email != hash_mcp


# ---------------------------------------------------------------------------
# Emitter: policy_table
# ---------------------------------------------------------------------------

class TestPolicyTable:
    def test_allowed_tools_present(self, email_manifest: dict, tmp_output: Path) -> None:
        emit(email_manifest, tmp_output)
        data = json.loads((tmp_output / "policy_table.json").read_text())
        assert "read_email" in data["allowed_tools"]
        assert "send_email" in data["allowed_tools"]

    def test_allowed_tools_sorted(self, email_manifest: dict, tmp_output: Path) -> None:
        emit(email_manifest, tmp_output)
        data = json.loads((tmp_output / "policy_table.json").read_text())
        assert data["allowed_tools"] == sorted(data["allowed_tools"])

    def test_irreversible_tools_classified(self, email_manifest: dict, tmp_output: Path) -> None:
        emit(email_manifest, tmp_output)
        data = json.loads((tmp_output / "policy_table.json").read_text())
        assert "send_email" in data["irreversible_tools"]
        assert "read_email" not in data["irreversible_tools"]

    def test_tool_budget_limits(self, email_manifest: dict, tmp_output: Path) -> None:
        emit(email_manifest, tmp_output)
        data = json.loads((tmp_output / "policy_table.json").read_text())
        assert data["budgets"]["tool_limits"].get("send_email") == 3


# ---------------------------------------------------------------------------
# Emitter: capability_matrix
# ---------------------------------------------------------------------------

class TestCapabilityMatrix:
    def test_trusted_has_all_capabilities(self, email_manifest: dict, tmp_output: Path) -> None:
        emit(email_manifest, tmp_output)
        data = json.loads((tmp_output / "capability_matrix.json").read_text())
        trusted_caps = data["by_trust_level"]["TRUSTED"]
        assert "external_write" in trusted_caps

    def test_untrusted_limited_to_internal_read(self, email_manifest: dict, tmp_output: Path) -> None:
        emit(email_manifest, tmp_output)
        data = json.loads((tmp_output / "capability_matrix.json").read_text())
        untrusted_caps = data["by_trust_level"]["UNTRUSTED"]
        assert untrusted_caps == ["internal_read"]
        assert "external_write" not in untrusted_caps

    def test_reverse_index_present(self, email_manifest: dict, tmp_output: Path) -> None:
        emit(email_manifest, tmp_output)
        data = json.loads((tmp_output / "capability_matrix.json").read_text())
        assert "external_write" in data["by_side_effect"]
        assert "TRUSTED" in data["by_side_effect"]["external_write"]


# ---------------------------------------------------------------------------
# Emitter: escalation_table
# ---------------------------------------------------------------------------

class TestEscalationTable:
    def test_send_email_escalation_present(self, email_manifest: dict, tmp_output: Path) -> None:
        emit(email_manifest, tmp_output)
        data = json.loads((tmp_output / "escalation_table.json").read_text())
        ids = [c["id"] for c in data["conditions"]]
        assert "send-email-always-escalate" in ids

    def test_tainted_egress_deny_present(self, email_manifest: dict, tmp_output: Path) -> None:
        emit(email_manifest, tmp_output)
        data = json.loads((tmp_output / "escalation_table.json").read_text())
        deny_conditions = [c for c in data["conditions"] if c["decision"] == "deny"]
        assert len(deny_conditions) >= 1

    def test_mcp_code_execution_escalation(self, mcp_manifest: dict, tmp_output: Path) -> None:
        emit(mcp_manifest, tmp_output)
        data = json.loads((tmp_output / "escalation_table.json").read_text())
        ids = [c["id"] for c in data["conditions"]]
        assert "code-execution-escalate" in ids


# ---------------------------------------------------------------------------
# Emitter: taint_rules
# ---------------------------------------------------------------------------

class TestTaintRules:
    def test_email_taint_rule_present(self, email_manifest: dict, tmp_output: Path) -> None:
        emit(email_manifest, tmp_output)
        data = json.loads((tmp_output / "taint_rules.json").read_text())
        ids = [r["id"] for r in data["rules"]]
        assert "email-body-taint" in ids

    def test_taint_rule_has_propagation(self, email_manifest: dict, tmp_output: Path) -> None:
        emit(email_manifest, tmp_output)
        data = json.loads((tmp_output / "taint_rules.json").read_text())
        email_rule = next(r for r in data["rules"] if r["id"] == "email-body-taint")
        assert len(email_rule["propagation"]) > 0
        ops = [p["operation"] for p in email_rule["propagation"]]
        assert "summarize" in ops

    def test_taint_rule_has_sanitization_gate(self, email_manifest: dict, tmp_output: Path) -> None:
        emit(email_manifest, tmp_output)
        data = json.loads((tmp_output / "taint_rules.json").read_text())
        email_rule = next(r for r in data["rules"] if r["id"] == "email-body-taint")
        gate = email_rule["sanitization_gate"]
        assert gate is not None
        assert gate["requires"] == "human_approval"


# ---------------------------------------------------------------------------
# Emitter: action_schemas
# ---------------------------------------------------------------------------

class TestActionSchemas:
    def test_all_actions_indexed(self, email_manifest: dict, tmp_output: Path) -> None:
        emit(email_manifest, tmp_output)
        data = json.loads((tmp_output / "action_schemas.json").read_text())
        assert "send_email" in data["actions"]
        assert "read_email" in data["actions"]

    def test_send_email_is_irreversible(self, email_manifest: dict, tmp_output: Path) -> None:
        emit(email_manifest, tmp_output)
        data = json.loads((tmp_output / "action_schemas.json").read_text())
        assert data["actions"]["send_email"]["reversible"] is False

    def test_read_email_output_trust(self, email_manifest: dict, tmp_output: Path) -> None:
        emit(email_manifest, tmp_output)
        data = json.loads((tmp_output / "action_schemas.json").read_text())
        assert data["actions"]["read_email"]["output_trust"] == "UNTRUSTED"


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

class TestCLI:
    def test_cli_build_succeeds(self, tmp_path: Path) -> None:
        from compiler.cli import main
        rc = main(["build", str(EMAIL_MANIFEST), "--output", str(tmp_path / "out"), "--quiet"])
        assert rc == 0

    def test_cli_missing_manifest_exits_nonzero(self, tmp_path: Path) -> None:
        from compiler.cli import main
        rc = main(["build", str(tmp_path / "nonexistent.yaml"), "--quiet"])
        assert rc != 0
