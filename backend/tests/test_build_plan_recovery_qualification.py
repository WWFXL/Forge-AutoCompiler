"""受控注入不改任务义务，静态停止及真实恢复调用保持边界。"""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
spec = importlib.util.spec_from_file_location("recovery_qualification", Path(__file__).resolve().parents[2] / "scripts/forge_build_plan_recovery_qualification.py")
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


def reference(name):
    rows = [("configure", "configure", "./configure"), ("build", "build", "make -j2"), ("check", "smoke", "make check"), ("stage", "artifact_stage", "cp out.a /artifacts/out.a")]
    if name == "libite":
        rows.insert(0, ("bootstrap", "configure", "autoreconf -if"))
    return {
        "plan_id": "qualification",
        "revision": 1,
        "repository_url": "https://example.com/repo.git",
        "commit_sha": "a" * 40,
        "image_id": "sha256:" + "b" * 64,
        "source_archive_sha256": "c" * 64,
        "build_system": {"miniz": "cmake", "pigz": "make", "libite": "autotools"}[name],
        "artifact_paths": ["out.a"],
        "steps": [{"step_id": identifier, "role": role, "command": command, "source": "fixture", "expected": "exit0", "required_output": ["all passed"] if role == "smoke" else []} for identifier, role, command in rows],
    }


@pytest.mark.parametrize("name", recovery.NAMES)
def test_fault_changes_only_designated_command_metadata_and_preserves_fixed_tests(name):
    original = recovery.BuildPlan.model_validate(reference(name))
    altered = recovery.controlled_plan(reference(name), name)
    assert altered.model_dump(exclude={"steps"}) == original.model_dump(exclude={"steps"})
    for before, after in zip(original.steps, altered.steps):
        if before.step_id == recovery.FAULTS[name]["changed_step"]:
            assert after.command == recovery.FAULTS[name]["command"]
            assert after.model_dump(exclude={"command", "source", "expected"}) == before.model_dump(exclude={"command", "source", "expected"})
        else:
            assert after == before


def test_initial_manual_plan_is_unpaid_and_static_control_never_calls_model(monkeypatch):
    events, files = [], []
    meter = SimpleNamespace(ledger=SimpleNamespace(append=lambda *args, **kwargs: events.append((args, kwargs)), save=lambda *args: files.append(args)))
    monkeypatch.setattr(recovery, "propose_with_context", lambda **kwargs: pytest.fail("静态控制不可调用模型"))
    planner = recovery.qualification_planner(reference("miniz"), "miniz", "static")
    plan, _ = planner(meter=meter, current_plan=None)
    assert plan.steps[1].command == recovery.FAULTS["miniz"]["command"]
    assert len(files) == 1 and events[0][0] == ("qualification.initial_plan",)
    with pytest.raises(recovery.PlanContractError, match=recovery.STATIC_STOP):
        planner(meter=meter, current_plan=plan, handoff={"reason": "actual failure"})


def test_repair_delegates_given_failure_context_without_correct_reference(monkeypatch):
    received = []
    monkeypatch.setattr(recovery, "propose_with_context", lambda **kwargs: received.append(kwargs) or "delegated")
    planner = recovery.qualification_planner(reference("miniz"), "miniz", "repair")
    bad = recovery.controlled_plan(reference("miniz"), "miniz")
    arguments = {"current_plan": bad, "handoff": {"reason": "actual failure"}, "task": "fixed-task", "model": "metered-model"}
    assert planner(**arguments) == "delegated"
    assert received == [arguments] and "reference" not in received[0]


def test_static_observation_requires_exact_fault_exit_and_cleaned_unchanged_session(tmp_path):
    folder = tmp_path / "case"
    root = folder / ".compile-sessions/thread/session"
    (root / "logs").mkdir(parents=True)
    metadata = root / "session.json"
    command = {"command_id": "bad", "command": recovery.FAULTS["miniz"]["command"], "exit_code": 2, "timed_out": False}
    metadata.write_text(json.dumps({"commands": [command]}))
    (root / "logs/workflow.log").write_text(json.dumps({"event": "plan.step", "step_id": "build", "command_id": "bad", "expected_satisfied": False}) + "\n")
    row = {
        "transitions": [{"status": "needs_handoff"}],
        "strict_completed": False,
        "error_message": recovery.STATIC_STOP,
        "cleanup": {"succeeded": True},
        "fixed_sources_unchanged": True,
        "agent_usage": {"cost_and_usage_complete": True, "model_requests": 0},
    }
    assert recovery.inspect_recovery(folder, row, "miniz", "static")["expected_observation"]
    command["command"] = "different failure"
    metadata.write_text(json.dumps({"commands": [command]}))
    assert not recovery.inspect_recovery(folder, row, "miniz", "static")["expected_observation"]


def test_gate_has_normal_static_and_repair_for_each_system_but_real_only_repairs():
    gate, real = recovery.make_schedule(True), recovery.make_schedule(False)
    assert len(gate) == 9 and len(real) == 3
    assert [row["mode"] for row in gate] == ["normal", "static", "repair"] * 3
    assert [row["project"] for row in real] == recovery.NAMES and all(row["mode"] == "repair" for row in real)


def test_legacy_source_receipts_keep_original_seal_format_and_detect_tampering(tmp_path):
    import hashlib

    source = tmp_path / "source.json"
    source.write_text("fixed source")
    rows = [{"path": "source.json", "size": source.stat().st_size, "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}]
    canonical = hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    (tmp_path / "inventory.json").write_text(json.dumps(rows))
    (tmp_path / "seal.json").write_text(json.dumps({"inventory_canonical_sha256": canonical}))
    assert recovery.audit_frozen(tmp_path)["inventory_canonical_sha256"] == canonical
    source.write_text("changed source")
    with pytest.raises(recovery.PlanContractError, match="冻结文件已变化"):
        recovery.audit_frozen(tmp_path)
