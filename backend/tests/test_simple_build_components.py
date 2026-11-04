"""核心接入的行为检查；真实模型收益由后续固定版本比较回答。"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_plan_agent import ScriptedPlanModel, response
from test_simple_build import actions, runner, simple_actions, task, workflow  # noqa: F401

from deerflow.compile.plan_agent import PlanAgentLedger
from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.simple_build_agents import SimpleBuildMeter, SimpleToolBuildService
from deerflow.compile.simple_build_experience import SimpleStateTargetBank, verified_simple_recipe
from deerflow.compile.simple_build_task import assemble_simple_plan, propose_simple

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_simple_cxx_reference import resource_dockerfile  # noqa: E402


def test_recipe_keeps_all_public_identity_except_run_label():
    t = task()
    p = assemble_simple_plan(t, actions())
    validation = dict(layers=dict(full_completed=True, clean_replay="passed"), source_unchanged=True, cleanup=dict(succeeded=True))
    recipe = verified_simple_recipe(source_id="previous", plan=p, validation=validation)
    assert recipe.match(t.model_copy(update={"plan_id": "new-run"}))
    for change in (dict(common_clarification="不同目标"), dict(architecture="aarch64"), dict(parallel_jobs=1), dict(commit_sha="b" * 40)):
        assert not recipe.match(t.model_copy(update=change))
    with pytest.raises(PlanContractError):
        verified_simple_recipe(source_id="partial", plan=p, validation=validation | dict(source_unchanged=False))
    assert recipe.materialize(t).steps == p.steps


def test_cross_project_retrieval_uses_visible_source_and_failure_only():
    bank = SimpleStateTargetBank(
        [dict(source_id="other", family="other", build_system="cmake", observed_validation={})],
        [dict(source_id="other", stage="configure", conditions=["CMAKE_GENERATOR"], state="build.ninja missing", action="检查当前generator", not_applicable=["无缓存"])],
    )
    args = dict(build_system="cmake", family="target", stage="initial", mode="structured")
    assert bank.retrieve(**args, text=json.dumps(dict(task={}, source_packet=[dict(content="CMAKE_GENERATOR")])))["sources"] == ["other"]
    assert bank.retrieve(**args, text=json.dumps(dict(task={}, private_reference="CMAKE_GENERATOR")))["sources"] == []
    assert bank.retrieve(**(args | dict(stage="build")), text=json.dumps(dict(task={}, handoff=dict(error="build.ninja missing"))))["sources"] == []
    assert bank.retrieve(**(args | dict(family="other")), text=json.dumps(dict(task={}, source_packet=[dict(content="CMAKE_GENERATOR")])))["sources"] == []


def test_real_agent_graph_retrieves_once_and_keeps_snapshot_across_requests(tmp_path):
    class Bank:
        calls = 0

        def retrieve(self, **kwargs):
            self.calls += 1
            return dict(sources=["previous"], items=[dict(action="CHECK_CURRENT_GENERATOR")], bytes=30)

    (tmp_path / "README.md").write_text("actual source")
    bank = Bank()
    meter = SimpleBuildMeter(PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",), deadline="2099-01-01T00:00:00+00:00", packet=lambda: dict(source_packet=[], private_reference="NEVER_SEND"))
    model = ScriptedPlanModel(responses=[response("read_source", dict(path="README.md")), response("SimpleBuildActions", simple_actions().model_dump(mode="json"))])
    propose_simple(model=model, task=task(), source_root=tmp_path, session_root=tmp_path, meter=meter, experience_bank=bank, family="target")
    assert bank.calls == 1
    for i in (1, 2):
        raw = (tmp_path / "agent" / f"request-{i}.json").read_text()
        assert "CHECK_CURRENT_GENERATOR" in raw and "NEVER_SEND" not in raw
    assert meter.summary()["estimated_cost_usd_completed_responses"] == pytest.approx(0.0000066)


def test_tool_agent_uses_real_command_ids_and_shared_primary_check(runner):  # noqa: F811
    w = workflow(runner, actions())
    tracker = SimpleNamespace(observe_elapsed=lambda _: None, consume=lambda **_: None, remaining=lambda: SimpleNamespace(node_seconds=600))
    service = SimpleToolBuildService(w, SimpleNamespace(tracker=tracker, started_monotonic=w.started))
    diagnostic = service.execute("ls", "diagnostic", "/workspace/repo")
    assert diagnostic["exit_code"] == 0
    failed = service.execute("make absent", "build", "/workspace/repo")
    (w.root / "stale.o").write_text("stale")
    reset = json.loads({t.name: t for t in service.tools()}["reset_generated_outputs"].invoke({}))
    assert reset["exit_code"] == 0 and not (w.root / "stale.o").exists() and (w.root / "sample.c").is_file()
    succeeded = service.execute("make", "build", "/workspace/repo")
    assert not service.submit(succeeded["command_id"], [failed["command_id"], succeeded["command_id"]])["accepted"]
    assert service.submit(succeeded["command_id"], [reset["command_id"], succeeded["command_id"]])["accepted"]
    assert w.layers["primary_build_completed"] is True
    with pytest.raises(PlanContractError):
        service.execute("make", "build", "/workspace/repo")


def test_cxx_adaptation_changes_environment_but_preserves_native_build():
    text = "FROM autocompiler:gcc13\nCOPY project /workspace/repo\nWORKDIR /workspace/repo\nRUN make\n"
    new = resource_dockerfile(text, "sha256:fixed", 2)
    assert "RUN make\n" in new and "CTEST_PARALLEL_LEVEL=1" in new
    assert resource_dockerfile(new, "sha256:fixed", 2) == new
    with pytest.raises(PlanContractError):
        resource_dockerfile(text.replace("autocompiler:gcc13", "ubuntu"), "sha256:fixed", 2)
