"""源码合同拒绝不能掩盖实际清理，也不能被改成严格成功。"""

import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_full_strategy_cleanup_continuation as new  # noqa: E402


def fixture(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "Makefile").write_text("changed")
    (tmp_path / "original-source-hashes.json").write_text(json.dumps({"Makefile": "original"}))
    sr = tmp_path / ".compile-sessions/thread/session"
    (sr / "logs").mkdir(parents=True)
    (sr / "session.json").write_text(json.dumps({"session_id": "session", "container_id": "id", "container_name": "name", "leadagent_repo_dir": str(workspace), "replay_attempts": [{"container_name": "replay"}]}))
    events = [{"event": "container.cleanup.removed", "exit_code": 0, "session_id": "session", "container_id": "id"}, {"event": "finalize.completed", "session_id": "session"}]
    (sr / "logs/workflow.log").write_text("\n".join(json.dumps(e) for e in events))
    row = {"strict_completed": False, "cleanup_error_class": "PlanContractError", "error_message": "原始源码或测试被修改", "cleanup": {"succeeded": False}}
    return row, sr


def test_source_rejection_with_real_cleanup_is_separate(tmp_path):
    row, _ = fixture(tmp_path)
    inspector = Mock(return_value=True)
    receipt = new.cleanup_receipt(tmp_path, row, inspect=inspector)
    assert receipt["physical_cleanup_succeeded"] and receipt["source_contract_rejected"]
    assert not receipt["strict_completed"] and not row["cleanup"]["succeeded"]
    assert inspector.call_count == 3


@pytest.mark.parametrize("fault", ["live_container", "missing_removed", "wrong_session", "wrong_container", "no_finalize", "sources_unchanged", "different_error", "strict_success"])
def test_no_classification_without_all_physical_and_source_evidence(tmp_path, fault):
    row, sr = fixture(tmp_path)
    inspector = Mock(return_value=fault != "live_container")
    events = [json.loads(line) for line in (sr / "logs/workflow.log").read_text().splitlines()]
    if fault == "missing_removed":
        events = events[1:]
    elif fault == "wrong_session":
        events[0]["session_id"] = "another"
    elif fault == "wrong_container":
        events[0]["container_id"] = "another"
    elif fault == "no_finalize":
        events = events[:1]
    elif fault == "sources_unchanged":
        (tmp_path / "original-source-hashes.json").write_text(json.dumps({"Makefile": new.digest(tmp_path / "repo/Makefile")}))
    elif fault == "different_error":
        row["error_message"] = "other"
    elif fault == "strict_success":
        row["strict_completed"] = True
    (sr / "logs/workflow.log").write_text("\n".join(json.dumps(e) for e in events))
    assert new.cleanup_receipt(tmp_path, row, inspect=inspector) is None


def test_adapter_preserves_original_receipt_and_failure(tmp_path, monkeypatch):
    folder = tmp_path / "negative-plan"
    folder.mkdir()
    row, _ = fixture(folder)
    (folder / "result.json").write_text(json.dumps(row))
    original = (folder / "result.json").read_bytes()
    monkeypatch.setattr(new, "run_arm", lambda **kwargs: row)
    inspect = new.cleanup_receipt
    monkeypatch.setattr(new, "cleanup_receipt", lambda folder, row: inspect(folder, row, inspect=lambda ref: True))
    actual = new.classified_arm(root=tmp_path, item={"name": "negative"}, arm="plan")
    assert not actual["strict_completed"] and actual["cleanup"]["succeeded"]
    assert not actual["legacy_cleanup"]["succeeded"]
    assert (folder / "result.json").read_bytes() == original
