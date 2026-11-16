"""诊断顺序指导的真实提示接线与本机编译；不估计模型效果。"""

import importlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from test_plan_agent import ScriptedPlanModel, response
from test_recovery_environment import meter_at
from test_simple_build import actions, simple_actions, workflow

from deerflow.compile.plan_workflow import _digest
from deerflow.compile.recovery_environment import RecoveryEnvironment
from deerflow.compile.recovery_harness import RecoveryHarness
from deerflow.compile.simple_build_task import SIMPLE_PROMPT, BuildReference, PublicBuildTask, propose_simple

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
entry = importlib.import_module("forge_libffi_diagnostic_order")
pytest_plugins = ["test_simple_build"]


def local_material(monkeypatch):
    item = next(p for p in json.loads((entry.ROOT / "benchmarks/fixtures/planning-tool-p4-comparison-v1/tasks.json").read_text())["projects"] if p["name"] == "libffi")
    baseline = RecoveryHarness.model_validate_json((entry.ROOT / "benchmarks/fixtures/recovery-harness-system-context-gpt61sol-v1/candidate.json").read_text()).model_copy(update={"base_prompt_sha256": _digest(SIMPLE_PROMPT)})
    old = (entry.ROOT / "benchmarks/fixtures/dependency-diagnosis-guidance-v1/guidance.md").read_text()
    baseline = baseline.model_copy(update={"recovery_guidance": baseline.recovery_guidance + "\n\n" + old})
    t, r = PublicBuildTask.model_validate(item["task"]), BuildReference.model_validate(item["reference"])
    monkeypatch.setattr(entry, "previous_material", lambda: (t, r, Path("unused.tar"), baseline))
    return baseline, entry.material()


def test_material_preserves_old_guidance_and_adds_no_project_answer(monkeypatch):
    baseline, (task, reference, _, recovery) = local_material(monkeypatch)
    added = recovery.recovery_guidance.removeprefix(baseline.recovery_guidance + "\n\n")
    assert recovery.recovery_guidance.startswith(baseline.recovery_guidance + "\n\n")
    assert recovery.fingerprint() != baseline.fingerprint()
    assert all(answer not in added for answer in ("libffi", "libltdl", "ltdl.m4", "LT_SYS_SYMBOL_USCORE", "2.4.6"))
    assert len(recovery.recovery_guidance.encode()) <= 6000
    assert task.image_id == entry.IMAGE_ID
    assert reference.task_sha256 == _digest(task.model_dump(mode="json"))


@pytest.mark.parametrize("recover", [False, True])
def test_guidance_only_in_recovery_and_workflow_resumes(runner, monkeypatch, recover):
    _, (_, _, _, recovery) = local_material(monkeypatch)
    w = workflow(runner, actions("make missing-target"))
    meter = meter_at(w.root)
    calls = [response("SimpleBuildActions", simple_actions().model_dump(mode="json"))]
    kwargs = {}
    if recover:
        assert w.run()["status"] == "needs_handoff"
        calls.insert(0, response("search_build_files", dict(query="int sample", scope="project")))
        kwargs = dict(current_plan=w.plan, handoff=w.handoff, revision_validator=w.validate_revision, diagnostics=RecoveryEnvironment(w, meter))
    revised, reason = propose_simple(model=ScriptedPlanModel(responses=calls), task=w.plan.task, source_root=w.root, session_root=w.root, meter=meter, recovery_harness=recovery, **kwargs)
    sent = json.loads((w.root / "agent/request-1.json").read_text())
    system = sent["system_message"]["content"]
    added = (entry.ROOT / "benchmarks/fixtures/dependency-diagnostic-order-v1/guidance.md").read_text()
    assert (added in system) is recover
    if recover:
        second = json.loads((w.root / "agent/request-2.json").read_text())
        assert any(m["type"] == "tool" and "int sample(void)" in m["content"] for m in second["messages"])
        w.apply_revision(handoff_id=w.handoff["handoff_id"], plan=revised, reason=reason)
        assert w.run()["status"] == "primary_completed"
        assert (w.root / "libsample.a").is_file()


def test_old_authorization_cannot_start_new_attempt(tmp_path, monkeypatch):
    auth = dict(identity="cpp-build-libffi-index-autonomous-flash-v1", maximum_cost_usd="1.00", user_authorized=True, deadline_utc=(datetime.now(UTC) + timedelta(minutes=45)).isoformat())
    path = tmp_path / "auth.json"
    path.write_text(json.dumps(auth))
    monkeypatch.setattr(entry, "material", lambda: (None, None, None, None))
    monkeypatch.setattr(sys, "argv", ["entry", "--authorization", str(path), "--output", str(tmp_path / "attempt")])

    def forbidden(*args, **kwargs):
        pytest.fail("旧身份不能访问运行时或Provider")

    monkeypatch.setattr(entry.subprocess, "run", forbidden)
    monkeypatch.setattr(entry, "PlanThinkingDeepSeek", forbidden)
    with pytest.raises(ValueError, match="授权"):
        entry.main()
    assert not (tmp_path / "attempt").exists()
