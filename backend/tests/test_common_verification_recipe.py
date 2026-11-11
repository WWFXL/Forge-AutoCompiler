"""共同修复的行为回归：真实Shell/编译，模型与Docker收益另行实测。"""

import hashlib

import pytest
from test_simple_build import LocalRuntime, actions, reference, runner, workflow  # noqa: F401

from deerflow.compile import operations
from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.schemas import ReplayVerificationResult
from deerflow.compile.simple_build_runtime import SimpleBuildWorkflow
from deerflow.compile.simple_build_task import BuildReference, SimpleBuildActions, assemble_simple_plan, simple_agent_packet


def step(name, role, command):
    return dict(step_id=name, role=role, command=command, source="工程夹具作者说明", expected="以真实执行为准")


def revise(w, steps, **kwargs):
    proposal = SimpleBuildActions(reason="修复真实失败", steps=steps, **kwargs)
    plan = assemble_simple_plan(w.plan.task, proposal, revision=w.plan.revision + 1)
    w.apply_revision(handoff_id=w.handoff["handoff_id"], plan=plan, reason=proposal.reason)


def dependency_failure(runner):  # noqa: F811
    t, session, manager, _ = runner
    proposal = SimpleBuildActions(reason="工程反例", steps=[step("install", "dependency", "command -v cc"), step("other", "dependency", "command -v ar"), step("build", "build", "make absent")])
    w = SimpleBuildWorkflow(plan=assemble_simple_plan(t, proposal), session=session, manager=manager, runtime=LocalRuntime(), reference=reference(t))
    assert w.run()["status"] == "needs_handoff"
    return w


def test_omitted_successful_dependencies_remain_without_reinstallation(runner):  # noqa: F811
    w = dependency_failure(runner)
    succeeded = dict(w.completed)
    failed_id = w._session.commands[-1].command_id
    assert {s["step_id"] for s in w.handoff["successful_dependencies"]} == {"install", "other"}
    revise(w, [step("build", "build", "make")])
    assert [s.step_id for s in w.plan.steps[:2]] == ["install", "other"]
    assert w.completed == succeeded
    assert w.run()["status"] == "primary_completed"
    assert all(w.completed[k] == v for k, v in succeeded.items())
    assert len([r for r in w._session.commands if r.role == "dependency"]) == 2
    assert failed_id not in w.completed.values()


def test_only_omitting_dependencies_cannot_retry_the_same_failure(runner):  # noqa: F811
    w = dependency_failure(runner)
    with pytest.raises(PlanContractError, match="没有改变实际执行动作"):
        revise(w, [step("build", "build", "make absent")])
    assert len(w._session.commands) == 3


def test_replacing_successful_dependency_needs_explicit_reason(runner):  # noqa: F811
    w = dependency_failure(runner)
    replacement = [step("install", "dependency", "command -v cc && command -v make"), step("build", "build", "make")]
    with pytest.raises(PlanContractError, match="不能隐式覆盖"):
        revise(w, replacement)
    revise(w, replacement, discard_dependencies={"install": "扩展必要工具检查"})
    assert w.completed == {"other": w._session.commands[1].command_id}
    assert w.run()["status"] == "primary_completed"
    assert len([r for r in w._session.commands if r.role == "dependency" and r.command.startswith("command -v")]) == 3


def test_explicit_removal_preserves_other_successful_dependencies(runner):  # noqa: F811
    w = dependency_failure(runner)
    other_id = w.completed["other"]
    revise(w, [step("build", "build", "make")], discard_dependencies={"install": "编译器由基础镜像提供；独立重放仍需核验"})
    assert "install" not in {s.step_id for s in w.plan.steps}
    assert w.completed["other"] == other_id
    assert w.run()["status"] == "primary_completed"


def test_unknown_discard_and_renamed_dependency_are_rejected(runner):  # noqa: F811
    w = dependency_failure(runner)
    with pytest.raises(PlanContractError, match="只能引用"):
        revise(w, [step("build", "build", "make")], discard_dependencies={"invented": "没有实际记录"})
    with pytest.raises(PlanContractError, match="不要改名"):
        revise(w, [step("renamed", "dependency", "command -v cc"), step("build", "build", "make")])


class ArtifactRuntime(LocalRuntime):
    def exec(self, session, command, **kwargs):
        return super().exec(session, command.replace("/artifacts", session.leadagent_artifacts_dir), **kwargs)


def executable_workflow(runner, flag="-V", expected="sample-v1"):  # noqa: F811
    t, session, manager, root = runner
    (root / "sample.c").write_text('#include <stdio.h>\n#include <string.h>\nint main(int n,char **v){if(n==2&&!strcmp(v[1],"-V")){puts("sample-v1");return 0;}return 37;}\n')
    ref = BuildReference(
        task_sha256=reference(t).task_sha256,
        components=[dict(name="sample", artifact_names=["sample"], kinds=["executable"], evidence="夹具Makefile")],
        executable_smokes=[dict(artifact_name="sample", step={**step("version", "smoke", "/artifacts/sample " + flag), "required_output": [expected]})],
    )
    p = SimpleBuildActions(reason="主程序", steps=[step("build", "build", "cc sample.c -o sample")])
    w = SimpleBuildWorkflow(plan=assemble_simple_plan(t, p), session=session, manager=manager, runtime=ArtifactRuntime(), reference=ref)
    assert w.run()["status"] == "primary_completed"
    return w


@pytest.mark.parametrize("flag,expected", [("--version", "sample-v1"), ("-V", "wrong-output")])
def test_invalid_smoke_is_rejected_before_replay(runner, monkeypatch, flag, expected):  # noqa: F811
    w = executable_workflow(runner, flag, expected)
    monkeypatch.setattr(operations, "submit_build_result_impl", lambda **_: pytest.fail("失败smoke不应提交"))
    result = w.postchecks(validation_scope="main_build")
    assert result["layers"]["executable_smoke"] == "failed"
    assert result["layers"]["final_verification_passed"] is False
    assert result["layers"]["clean_replay"] == "not_started" and not result["replay_attempts"]
    assert w.layers["primary_build_completed"] is True


def test_native_smoke_uses_actual_success_record_and_stays_private(runner, monkeypatch):  # noqa: F811
    w = executable_workflow(runner)

    def submit(**kwargs):
        policy = kwargs["executable_verification_policy"]
        policy.validate()
        evidence = operations._successful_command_for_artifact(session=w._session, supporting_command_id=kwargs["supporting_command_id"], artifact_path="sample", policy=policy)
        assert evidence is not None and evidence.output.startswith("sample-v1\n")
        assert evidence.output_sha256 == hashlib.sha256(evidence.output.encode()).hexdigest()
        assert evidence.command_id not in kwargs["recipe_command_ids"]
        assert evidence.command_id in kwargs["verification_command_ids"]
        assert [r.command_id for r in w._session.commands if r.command_id in kwargs["recipe_command_ids"]] == kwargs["recipe_command_ids"]

    monkeypatch.setattr(operations, "submit_build_result_impl", submit)
    result = w.postchecks(validation_scope="main_build")
    assert result["layers"]["executable_smoke"] == "passed"
    assert result["layers"]["clean_replay"] == "not_started"
    assert "executable_smokes" not in simple_agent_packet(w.plan.task)


@pytest.mark.parametrize("attempt_status", [None, "failed", "passed"])
def test_replay_label_requires_an_actual_new_attempt(runner, monkeypatch, attempt_status):  # noqa: F811
    w = workflow(runner, actions())
    w.runtime = ArtifactRuntime()
    assert w.run()["status"] == "primary_completed"

    def submit(**kwargs):
        current = w.manager.load_session(w.session_id, w.thread_id)
        if attempt_status:
            current.replay_attempts.append(ReplayVerificationResult(attempt_id="actual", status=attempt_status, image="test", image_id=current.image_id, commit_sha=current.commit_sha, recipe_sha256="a" * 64))
        current.status = "verified" if attempt_status == "passed" else "verification_failed"
        w.manager.save_session(current)

    monkeypatch.setattr(operations, "submit_build_result_impl", submit)
    result = w.postchecks(validation_scope="main_build")
    assert result["layers"]["clean_replay"] == (attempt_status or "not_started")
    assert result["layers"]["final_verification_passed"] is (attempt_status == "passed")


def test_smoke_reference_rejects_unbound_components(runner):  # noqa: F811
    t = runner[0]
    value = reference(t).model_dump()
    value["executable_smokes"] = [dict(artifact_name="other", step={**step("version", "smoke", "/artifacts/other -V"), "required_output": ["other"]})]
    with pytest.raises(ValueError, match="可执行组件"):
        BuildReference.model_validate(value)
