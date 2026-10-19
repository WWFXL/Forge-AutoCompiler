"""回顾审计必须区分未观察、失败与成功，并保留失败历史。"""

import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("validation_evidence_audit", Path(__file__).resolve().parents[2] / "scripts/forge_build_validation_evidence_audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def command(identifier, role, text):
    return {"command_id": identifier, "role": role, "command": text, "workdir": "/workspace/repo", "exit_code": 0, "timed_out": False}


def observe(commands=(), *, logs=None, attempts=(), status="completed"):
    task = {"artifact_paths": ["out.a"], "verification_steps": [{"command": "make check", "workdir": "/workspace/repo", "required_output": ["TOTAL: 8", "PASS: 8"]}]}
    return audit.layer_observations({"commands": list(commands), "status": status, "replay_attempts": list(attempts)}, task, logs or {}, source_unchanged=True, artifact_paths=[], cleanup=True)


def test_completed_state_does_not_invent_unobserved_checks():
    layers = observe()
    assert layers["latest_build_exit"] == layers["fixed_full_tests"] == layers["exact_artifact_set"] == layers["clean_replay"] == "not_observed"


def test_successful_exit_without_complete_test_output_is_failed():
    layers = observe([command("test", "smoke", "make check")], logs={"test": "No tests were found!!!"})
    assert layers["fixed_full_tests"] == "failed"


def test_protocol_plan_omitted_workdir_uses_original_schema_default():
    task = {"artifact_paths": ["out.a"], "verification_steps": [{"command": "make check", "required_output": ["all passed"]}]}
    layers = audit.layer_observations({"commands": [command("test", "smoke", "make check")]}, task, {"test": "all passed"}, source_unchanged=True, artifact_paths=[], cleanup=True)
    assert layers["fixed_full_tests"] == "passed"


@pytest.mark.parametrize("role", ["dependency", "configure", "build"])
def test_later_environment_or_build_command_invalidates_older_test(role):
    commands = [command("test", "smoke", "make check"), command("change", role, "change")]
    assert observe(commands, logs={"test": "TOTAL: 8\nPASS: 8"})["fixed_full_tests"] == "failed"


def test_latest_matching_test_failure_cannot_be_hidden_by_earlier_success():
    old, latest = command("old", "smoke", "make check"), command("new", "smoke", "make check")
    latest["exit_code"] = 1
    assert observe([old, latest], logs={"old": "TOTAL: 8\nPASS: 8", "new": "failed"})["fixed_full_tests"] == "failed"


def test_unreached_artifact_stage_differs_from_failed_exact_staging():
    assert observe()["exact_artifact_set"] == "not_observed"
    assert observe([command("stage", "artifact_stage", "cp out.a /artifacts/out.a")])["exact_artifact_set"] == "failed"


def test_passed_last_replay_preserves_previous_failure():
    attempts = [
        {"attempt_id": "first", "status": "failed", "failure_classification": "recipe_execution_failed", "cleanup_succeeded": True, "checks": [{"name": "build", "passed": False}]},
        {"attempt_id": "second", "status": "passed", "cleanup_succeeded": True, "verification_exit_code": 0, "checks": [{"name": "build", "passed": True}]},
    ]
    layers = observe(attempts=attempts)
    assert layers["clean_replay"] == "passed"
    assert layers["replay_attempts"][0]["failed_checks"] == ["build"]


def test_consumed_file_is_verified_against_bound_inventory(tmp_path):
    files = {"protocol.json": b"{}", "result.json": b"{}", "log.txt": b"original"}
    inventory = []
    for name, data in files.items():
        (tmp_path / name).write_bytes(data)
        inventory.append({"path": name, "type": "file", "size": len(data), "sha256": audit.sha(data)})
    canonical = audit.sha(json.dumps(inventory, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
    (tmp_path / "inventory.json").write_text(json.dumps(inventory))
    (tmp_path / "seal.json").write_text(json.dumps({"inventory_canonical_sha256": canonical}))
    frozen = audit.FrozenInput({"root": str(tmp_path), "inventory_sha256": canonical, "protocol_sha256": audit.sha(b"{}"), "result_sha256": audit.sha(b"{}")})
    assert frozen.read("log.txt") == b"original"
    (tmp_path / "log.txt").write_bytes(b"modified")
    with pytest.raises(ValueError, match="偏离冻结"):
        frozen.read("log.txt")
