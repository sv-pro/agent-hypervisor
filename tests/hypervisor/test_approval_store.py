import pytest
import json
from pathlib import Path
from agent_hypervisor.hypervisor.storage.approval_store import ApprovalStore


@pytest.fixture
def store(tmp_path: Path) -> ApprovalStore:
    return ApprovalStore(tmp_path)


def test_create_and_get(store: ApprovalStore):
    record = {
        "approval_id": "req-1",
        "status": "pending",
        "tool": "send_email",
        "mock_extra": 42
    }
    store.create(record)

    fetched = store.get("req-1")
    assert fetched is not None
    assert fetched["approval_id"] == "req-1"
    assert fetched["status"] == "pending"
    assert fetched["tool"] == "send_email"
    assert fetched["mock_extra"] == 42


def test_get_not_found(store: ApprovalStore):
    assert store.get("does-not-exist") is None


def test_update_existing_record(store: ApprovalStore):
    record = {
        "approval_id": "req-2",
        "status": "pending",
        "tool": "delete_db"
    }
    store.create(record)

    # Partial update
    store.update("req-2", status="approved", actor="alice", resolved_at="2026-04-12T00:00:00Z")

    fetched = store.get("req-2")
    assert fetched is not None
    assert fetched["status"] == "approved"
    assert fetched["actor"] == "alice"
    assert fetched["resolved_at"] == "2026-04-12T00:00:00Z"
    assert fetched["tool"] == "delete_db"  # Unchanged


def test_update_raises_keyerror_if_not_found(store: ApprovalStore):
    with pytest.raises(KeyError, match="'missing' not found in store"):
        store.update("missing", status="approved")


def test_list_recent_sorting_and_filtering(store: ApprovalStore, tmp_path: Path):
    import time
    
    # Create records
    r1 = {"approval_id": "id-1", "status": "pending"}
    r2 = {"approval_id": "id-2", "status": "approved"}
    r3 = {"approval_id": "id-3", "status": "pending"}

    # Write slowly to ensure distinct st_mtime
    store.create(r1)
    time.sleep(0.01)
    store.create(r2)
    time.sleep(0.01)
    store.create(r3)

    # list_recent without filter returns all, newest first
    all_recent = store.list_recent()
    assert len(all_recent) == 3
    assert [r["approval_id"] for r in all_recent] == ["id-3", "id-2", "id-1"]

    # list_recent with filter
    pending = store.list_recent(status="pending")
    assert len(pending) == 2
    assert [r["approval_id"] for r in pending] == ["id-3", "id-1"]


def test_corrupted_json_handled_gracefully(store: ApprovalStore, tmp_path: Path):
    r1 = {"approval_id": "id-1", "status": "pending"}
    store.create(r1)
    
    # Manually create a corrupted file
    bad_path = store._record_path("bad")
    with open(bad_path, "w") as f:
        f.write("{invalid-json")
    
    # get() on corrupt returns None
    assert store.get("bad") is None

    # list_recent() ignores corrupt file
    all_recent = store.list_recent()
    assert len(all_recent) == 1
    assert all_recent[0]["approval_id"] == "id-1"
