"""
Round-trip integration test: World Manifest v2 → loader_v2 → emitter → artifacts.

Verifies that the full compile pipeline produces all expected artifact files
with correct top-level structure. This is the integration test that was missing
after Phase 4 implementation (PR #118).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_hypervisor.compiler.emitter import emit
from agent_hypervisor.compiler.loader_v2 import load, load_typed


WORKSPACE_V2 = Path(__file__).parent.parent.parent / "manifests" / "workspace_v2.yaml"

EXPECTED_ARTIFACTS = {
    "policy_table.json": {"allowed_tools", "irreversible_tools", "budgets"},
    "capability_matrix.json": {"by_trust_level", "by_side_effect"},
    "taint_rules.json": {"rules"},
    "taint_state_machine.json": set(),  # structure varies; just check it exists and is valid JSON
    "escalation_table.json": {"conditions"},
    "provenance_schema.json": {"required_fields", "optional_fields"},
    "action_schemas.json": {"actions"},
    "manifest_meta.json": {"name", "version", "content_hash"},
}


def test_workspace_v2_exists():
    assert WORKSPACE_V2.exists(), f"workspace_v2.yaml not found at {WORKSPACE_V2}"


def test_roundtrip_emits_all_artifacts(tmp_path):
    raw = load(WORKSPACE_V2)
    written = emit(raw, tmp_path)
    assert set(written.keys()) == set(EXPECTED_ARTIFACTS.keys()), (
        f"Missing artifacts: {set(EXPECTED_ARTIFACTS) - set(written)}\n"
        f"Unexpected: {set(written) - set(EXPECTED_ARTIFACTS)}"
    )
    for name in EXPECTED_ARTIFACTS:
        assert (tmp_path / name).exists(), f"Artifact {name!r} was not written to disk"


def test_roundtrip_artifacts_are_valid_json(tmp_path):
    raw = load(WORKSPACE_V2)
    emit(raw, tmp_path)
    for name in EXPECTED_ARTIFACTS:
        content = (tmp_path / name).read_text(encoding="utf-8")
        try:
            json.loads(content)
        except json.JSONDecodeError as exc:
            pytest.fail(f"{name} is not valid JSON: {exc}")


def test_roundtrip_artifacts_have_expected_keys(tmp_path):
    raw = load(WORKSPACE_V2)
    emit(raw, tmp_path)
    for name, required_keys in EXPECTED_ARTIFACTS.items():
        if not required_keys:
            continue
        data = json.loads((tmp_path / name).read_text(encoding="utf-8"))
        missing = required_keys - set(data.keys())
        assert not missing, f"{name} is missing top-level keys: {missing}"


def test_roundtrip_is_deterministic(tmp_path):
    raw = load(WORKSPACE_V2)
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    emit(raw, out_a)
    emit(raw, out_b)
    for name in EXPECTED_ARTIFACTS:
        a = (out_a / name).read_text(encoding="utf-8")
        b = (out_b / name).read_text(encoding="utf-8")
        assert a == b, f"{name}: second emit produced different content (non-deterministic)"


def test_roundtrip_policy_table_contains_workspace_actions(tmp_path):
    raw = load(WORKSPACE_V2)
    emit(raw, tmp_path)
    policy = json.loads((tmp_path / "policy_table.json").read_text())
    manifest_actions = sorted(raw.get("actions", {}).keys())
    assert policy["allowed_tools"] == manifest_actions, (
        "policy_table.allowed_tools does not match manifest actions"
    )


def test_roundtrip_manifest_meta_hash_changes_with_content(tmp_path):
    import copy
    raw = load(WORKSPACE_V2)
    emit(raw, tmp_path)
    meta_a = json.loads((tmp_path / "manifest_meta.json").read_text())

    modified = copy.deepcopy(raw)
    modified["_test_sentinel"] = "changed"
    out_b = tmp_path / "b"
    emit(modified, out_b)
    meta_b = json.loads((out_b / "manifest_meta.json").read_text())

    assert meta_a["content_hash"] != meta_b["content_hash"], (
        "content_hash did not change when manifest content changed"
    )


def test_load_typed_roundtrip(tmp_path):
    """load_typed() parses the manifest; emit() compiles it — both must succeed."""
    manifest = load_typed(WORKSPACE_V2)
    assert manifest is not None

    raw = load(WORKSPACE_V2)
    written = emit(raw, tmp_path)
    assert len(written) == len(EXPECTED_ARTIFACTS)
