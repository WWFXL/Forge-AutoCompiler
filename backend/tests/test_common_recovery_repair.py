"""共同修复只检验真实行为与反馈，不产生模型效果观察。"""

import hashlib
import json

import pytest
from test_common_verification_recipe import ArtifactRuntime, executable_workflow
from test_plan_agent import ScriptedPlanModel, response
from test_simple_build import LocalRuntime, actions, reference, runner, simple_actions, task  # noqa: F401
from test_simple_planning import request, run

from deerflow.compile import operations
from deerflow.compile.plan_agent import PlanAgentLedger
from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.simple_build_agents import SimpleBuildMeter
from deerflow.compile.simple_build_runtime import SimpleBuildWorkflow, source_inventory, source_unchanged
from deerflow.compile.simple_build_task import BuildReference, GeneratedDocument, SimpleBuildActions, assemble_simple_plan, propose_simple, simple_agent_packet


def step(name, role, command):
    return dict(step_id=name, role=role, command=command, source="工程夹具作者说明", expected="以真实执行为准")


def test_latest_oversized_reasoning_group_is_preserved_offline_and_compacted(tmp_path):
    (tmp_path / "README.md").write_text("Use make to build the main library")
    first = response("read_source", dict(path="README.md"))
    first.additional_kwargs["reasoning_content"] = "真实原始推理" * 8000
    plan, meter = run(tmp_path, [first, response("SimpleBuildActions", simple_actions().model_dump(mode="json"))])
    sent = request(tmp_path, 2)
    assert plan.steps[-1].command == "make" and meter.summary()["model_requests"] == 2
    assert len(json.dumps({k: v for k, v in sent.items() if k != "tools"}, ensure_ascii=False).encode()) <= 49000
    assert all(m["type"] != "tool" for m in sent["messages"])
    compact = json.loads(sent["messages"][-1]["content"])
    assert compact["context_compaction"] and "Use make" in compact["evidence"][0]["result"]["content"]
    original_path = tmp_path / "agent" / compact["original_record"]
    original_bytes = original_path.read_bytes()
    original = json.loads(original_bytes)
    assert original[0]["additional_kwargs"]["reasoning_content"] == first.additional_kwargs["reasoning_content"]
    assert len([m for m in original if m["type"] == "tool"]) == 1
    model = ScriptedPlanModel(responses=[first, response("SimpleBuildActions", simple_actions("make all").model_dump(mode="json"))])
    revised, _ = propose_simple(model=model, task=plan.task, source_root=tmp_path, session_root=tmp_path, meter=meter, current_plan=plan, handoff=dict(handoff_id="controlled", plan_sha256=plan.fingerprint()))
    assert revised.steps[-1].command == "make all" and meter.summary()["model_requests"] == 4
    assert original_path.read_bytes() == original_bytes
    assert len(list((tmp_path / "agent").glob("context-request-*-group-*.json"))) == 2


def test_structure_and_revision_feedback_have_separate_bounded_chances(runner, tmp_path):  # noqa: F811
    t, session, manager, root = runner
    initial = SimpleBuildActions(reason="夹具", steps=[step("deps", "dependency", "command -v cc"), step("build", "build", "make absent")])
    w = SimpleBuildWorkflow(plan=assemble_simple_plan(t, initial), session=session, manager=manager, runtime=LocalRuntime(), reference=reference(t))
    assert w.run()["status"] == "needs_handoff"
    revised = dict(reason="真实修订", steps=[step("deps", "dependency", "command -v cc && command -v ar"), step("build", "build", "make")])
    meter = SimpleBuildMeter(PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",), deadline="2099-01-01T00:00:00+00:00", packet=lambda: {})
    corrected = {**revised, "discard_dependencies": {"deps": "增加必要工具检查"}}
    model = ScriptedPlanModel(responses=[response("SimpleBuildActions", {}), response("SimpleBuildActions", revised), response("SimpleBuildActions", corrected)])
    plan, reason = propose_simple(model=model, task=t, source_root=root, session_root=root, meter=meter, current_plan=w.plan, handoff=w.handoff, revision_validator=w.validate_revision)
    assert "discard_dependencies" in (tmp_path / "agent/request-3.json").read_text()
    w.apply_revision(handoff_id=w.handoff["handoff_id"], plan=plan, reason=reason)
    assert w.run()["status"] == "primary_completed" and meter.summary()["model_requests"] == 3


def test_repeated_revision_error_stops_after_one_feedback(tmp_path):
    current = assemble_simple_plan(task(), simple_actions("make absent"))
    handoff = dict(handoff_id="controlled", plan_sha256=current.fingerprint())
    meter = SimpleBuildMeter(PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",), deadline="2099-01-01T00:00:00+00:00", packet=lambda: {})

    def reject(_):
        raise PlanContractError("受控修订错误")

    model = ScriptedPlanModel(responses=[response("SimpleBuildActions", simple_actions().model_dump(mode="json"))] * 3)
    with pytest.raises(PlanContractError, match="受控修订错误"):
        propose_simple(model=model, task=current.task, source_root=tmp_path, session_root=tmp_path, meter=meter, current_plan=current, handoff=handoff, revision_validator=reject)
    assert meter.summary()["model_requests"] == 2 and not (tmp_path / "agent/request-3.json").exists()


def test_only_independently_declared_document_content_can_change(tmp_path):
    (tmp_path / "README.md").write_text("old")
    (tmp_path / "README.md.in").write_text("new")
    (tmp_path / "source.c").write_text("original")
    baseline = source_inventory(tmp_path)
    document = GeneratedDocument(path="README.md", template="README.md.in", sha256=hashlib.sha256(b"new").hexdigest(), source="CMakeLists.txt configure_file")
    (tmp_path / "README.md").write_text("new")
    source_unchanged(tmp_path, baseline, (document,))
    (tmp_path / "README.md").write_text("unreviewed")
    with pytest.raises(PlanContractError):
        source_unchanged(tmp_path, baseline, (document,))
    (tmp_path / "README.md").write_text("new")
    (tmp_path / "source.c").write_text("changed")
    with pytest.raises(PlanContractError):
        source_unchanged(tmp_path, baseline, (document,))
    for path in ("source.c", "tests/expected.txt", "../README.md"):
        with pytest.raises(ValueError):
            GeneratedDocument.model_validate({**document.model_dump(), "path": path})
    assert "generated_documents" not in simple_agent_packet(task())


def test_generated_document_is_reported_separately_from_protected_inputs(runner):  # noqa: F811
    t, session, manager, root = runner
    (root / "README.md").write_text("old")
    (root / "README.md.in").write_text("new")
    document = GeneratedDocument(path="README.md", template="README.md.in", sha256=hashlib.sha256(b"new").hexdigest(), source="作者生成声明")
    ref = reference(t).model_copy(update={"generated_documents": (document,)})
    w = SimpleBuildWorkflow(plan=assemble_simple_plan(t, actions()), session=session, manager=manager, runtime=LocalRuntime(), reference=ref)
    (root / "README.md").write_text("new")
    report = w.source_protection()
    assert report["protected_inputs_unchanged"] and report["generated_document_changes"][0]["path"] == "README.md"
    assert report["generated_document_changes"][0]["content_changed"]
    (root / "README.md").chmod(0o755)
    with pytest.raises(PlanContractError):
        w.check_source()


def test_same_content_document_rewrite_is_still_reported(runner):  # noqa: F811
    t, session, manager, root = runner
    (root / "README.md").write_text("same")
    (root / "README.md.in").write_text("same")
    document = GeneratedDocument(path="README.md", template="README.md.in", sha256=hashlib.sha256(b"same").hexdigest(), source="作者生成声明")
    ref = reference(t).model_copy(update={"generated_documents": (document,)})
    w = SimpleBuildWorkflow(plan=assemble_simple_plan(t, actions()), session=session, manager=manager, runtime=LocalRuntime(), reference=ref)
    (root / "replacement.md").write_text("same")
    (root / "replacement.md").replace(root / "README.md")
    rewritten = w.source_protection()["generated_document_changes"][0]
    assert not rewritten["content_changed"] and rewritten["file_identity_changed"]


def test_main_build_missing_native_smoke_does_not_guess_flags(runner, monkeypatch):  # noqa: F811
    w = executable_workflow(runner)
    w.reference = w.reference.model_copy(update={"executable_smokes": ()})
    monkeypatch.setattr(operations, "submit_build_result_impl", lambda **_: pytest.fail("不能猜参数"))
    result = w.postchecks(validation_scope="main_build")
    assert result["verification_issue"]["kind"] == "missing_native_verification"
    assert result["layers"]["clean_replay"] == "not_started"


def test_assertion_failure_stays_an_evaluator_issue(runner, monkeypatch):  # noqa: F811
    w = executable_workflow(runner, expected="wrong-output")
    monkeypatch.setattr(operations, "submit_build_result_impl", lambda **_: pytest.fail("断言未通过"))
    result = w.postchecks(validation_scope="main_build", recover_delivery=True)
    assert result["verification_issue"]["kind"] == "output_assertion_failed"
    assert not result["verification_issue"]["recoverable"] and w.status == "primary_completed"


def test_delivery_execution_failure_returns_to_recovery_and_keeps_checks(runner, monkeypatch):  # noqa: F811
    w = executable_workflow(runner, flag="--unsupported")
    monkeypatch.setattr(operations, "submit_build_result_impl", lambda **_: pytest.fail("程序尚未运行成功"))
    original_ref = w.reference
    w.postchecks(validation_scope="main_build", recover_delivery=True)
    assert w.status == "needs_handoff" and w.handoff["reason"] == "delivery_execution_failed"
    assert w.handoff["delivery_failure"]["recoverable"]
    assert w.handoff["recent_commands"][-1]["exit_code"] == 37
    assert w.reference == original_ref and w.layers["primary_build_completed"] is True


def test_delivery_failure_can_repair_environment_and_resume_same_verifier(runner, monkeypatch, tmp_path):  # noqa: F811
    t, session, manager, root = runner
    ready = tmp_path / "runtime.ready"
    (root / "sample.c").write_text("#include <stdio.h>\n#include <unistd.h>\nint main(void){if(access(" + json.dumps(str(ready)) + ',F_OK))return 37;puts("sample-v1");return 0;}\n')
    ref = BuildReference(
        task_sha256=reference(t).task_sha256,
        components=[dict(name="sample", artifact_names=["sample"], kinds=["executable"], evidence="夹具作者")],
        executable_smokes=[dict(artifact_name="sample", step={**step("run", "smoke", "/artifacts/sample"), "required_output": ["sample-v1"]})],
    )
    initial = SimpleBuildActions(reason="主构建", steps=[step("build", "build", "cc sample.c -o sample")])
    w = SimpleBuildWorkflow(plan=assemble_simple_plan(t, initial), session=session, manager=manager, runtime=ArtifactRuntime(), reference=ref)
    monkeypatch.setattr(operations, "submit_build_result_impl", lambda **_: None)
    assert w.run()["status"] == "primary_completed"
    w.postchecks(validation_scope="main_build", recover_delivery=True)
    assert w.status == "needs_handoff"
    first = (w.directory / "primary-result.json").read_bytes()
    revised = SimpleBuildActions(reason="补足运行环境", steps=[step("ready", "dependency", "touch " + str(ready)), *initial.steps])
    w.apply_revision(handoff_id=w.handoff["handoff_id"], plan=assemble_simple_plan(t, revised, revision=2), reason=revised.reason)
    assert w.run()["status"] == "primary_completed"
    result = w.postchecks(validation_scope="main_build", recover_delivery=True)
    assert result["layers"]["executable_smoke"] == "passed" and w.reference == ref
    assert (w.directory / "primary-result.json").read_bytes() == first
    assert json.loads((w.directory / "postcheck-result-r1.json").read_text())["layers"]["executable_smoke"] == "failed"


def test_soname_is_staged_and_native_smoke_has_consistent_short_timeout(runner, monkeypatch):  # noqa: F811
    t, session, manager, root = runner
    (root / "main.c").write_text("extern int sample(void); int main(void){return sample()!=7;}\n")
    ref = BuildReference(
        task_sha256=reference(t).task_sha256,
        components=[dict(name="lib", artifact_names=["libsample.so.1.0"], kinds=["shared_library"], evidence="夹具作者"), dict(name="main", artifact_names=["main"], kinds=["executable"], evidence="夹具作者")],
        executable_smokes=[dict(artifact_name="main", step={**step("run", "smoke", "/artifacts/main"), "required_output": ["main-ok"]})],
    )
    (root / "main.c").write_text('#include <stdio.h>\nextern int sample(void); int main(void){puts("main-ok");return sample()!=7;}\n')
    proposal = SimpleBuildActions(reason="共享库夹具", steps=[step("build", "build", "cc -fPIC -shared -Wl,-soname,libsample.so.1 sample.c -o libsample.so.1.0 && cc main.c -L. -l:libsample.so.1.0 -o main")])
    w = SimpleBuildWorkflow(plan=assemble_simple_plan(t, proposal), session=session, manager=manager, runtime=ArtifactRuntime(), reference=ref)
    assert w.run()["status"] == "primary_completed"
    monkeypatch.setattr(operations, "submit_build_result_impl", lambda **_: None)
    result = w.postchecks(validation_scope="main_build")
    assert result["layers"]["executable_smoke"] == "passed"
    assert (w.root.parent.parent / "artifacts/libsample.so.1").is_file()
    smoke = [r for r in w._session.commands if r.role == "smoke"][-1]
    assert smoke.timeout_seconds <= 30 and "LD_LIBRARY_PATH" in smoke.command
