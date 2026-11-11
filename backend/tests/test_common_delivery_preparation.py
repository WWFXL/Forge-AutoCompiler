"""准备生成物、产物变体和隔离轻量运行的共同机制回归。"""

import os

import pytest
from test_common_verification_recipe import ArtifactRuntime, dependency_failure, executable_workflow, revise, step
from test_simple_build import reference, runner  # noqa: F401

from deerflow.compile import operations
from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.simple_build_runtime import SimpleBuildWorkflow
from deerflow.compile.simple_build_task import BuildReference, SimpleBuildActions, assemble_simple_plan


def test_reset_precedes_dependency_generated_configure_and_recipe(runner):  # noqa: F811
    t, session, manager, root = runner
    bootstrap = step("bootstrap", "dependency", "printf '#!/bin/sh\\nexit 0\\n' > configure && chmod +x configure")
    initial = SimpleBuildActions(reason="准备生成配置入口", steps=[bootstrap, step("configure", "configure", "./configure"), step("build", "build", "make absent")])
    w = SimpleBuildWorkflow(plan=assemble_simple_plan(t, initial), session=session, manager=manager, runtime=ArtifactRuntime(), reference=reference(t))
    assert w.run()["status"] == "needs_handoff"
    old = w.completed["bootstrap"]
    revise(w, [bootstrap, step("configure", "configure", "./configure && test -f Makefile"), step("build", "build", "make")])
    assert [s.step_id for s in w.plan.steps][:2] == ["forge-generated-reset", "bootstrap"]
    assert w.run()["status"] == "primary_completed"
    assert w.completed["bootstrap"] != old and (root / "configure").is_file()
    assert [r.role for r in w._session.commands if r.command_id in w.completed.values()] == ["dependency", "dependency", "configure", "build"]
    # 还原到空生成物状态，以最终接受配方真实执行，不能依赖旧configure。
    for s in w.plan.steps:
        record, _ = w._post_command(s, 30)
        assert record.exit_code == 0
    w.check_source()


def test_dependency_conflicts_reported_together(runner):  # noqa: F811
    w = dependency_failure(runner)
    with pytest.raises(PlanContractError, match="install,other"):
        revise(w, [step("install", "dependency", "command -v make"), step("other", "dependency", "command -v ld"), step("build", "build", "make")])


def test_same_component_variants_keep_evidence_and_stage_one(runner):  # noqa: F811
    t, session, manager, root = runner
    proposal = SimpleBuildActions(
        reason="发布与未strip版本", steps=[step("build", "build", "make && mkdir -p generated/unstripped && printf 'int variant(void){return 1;}' | cc -x c -c -o variant.o - && ar rcs generated/unstripped/libsample.a sample.o variant.o")]
    )
    w = SimpleBuildWorkflow(plan=assemble_simple_plan(t, proposal), session=session, manager=manager, runtime=ArtifactRuntime(), reference=reference(t))
    assert w.run()["status"] == "primary_completed"
    assert len(w.primary["components"][0]["candidates"]) == 2
    assert [p["path"] for p in w.primary["artifacts"]] == ["libsample.a"]
    assert w.postchecks(replay=False, validation_scope="main_build")["layers"]["delivery"] == "passed"


def test_missing_native_entry_is_reference_preparation_error(runner):  # noqa: F811
    w = executable_workflow(runner)
    w.reference = BuildReference.model_validate(w.reference.model_dump() | dict(executable_smokes=[]))
    with pytest.raises(PlanContractError, match="运行前补全"):
        w.reference.require_main_build_verification()
    reference(w.plan.task).require_main_build_verification()  # 纯库无运行入口，不虚构命令。


def test_smoke_cwd_does_not_pollute_delivery_and_files_are_readable(runner, monkeypatch):  # noqa: F811
    w = executable_workflow(runner)
    data = w.reference.model_dump()
    smoke = data["executable_smokes"][0]["step"]
    smoke.update(workdir="/artifacts", command="/artifacts/sample -V && python3 -c \"import os; fd=os.open('history.txt', os.O_CREAT|os.O_WRONLY, 0o600); os.write(fd,b'history'); os.close(fd)\"")
    w.reference = BuildReference.model_validate(data)
    monkeypatch.setattr(operations, "submit_build_result_impl", lambda **_: None)
    w.postchecks(validation_scope="main_build")
    assert w.layers["executable_smoke"] == "passed"
    history = w.root / ".forge-verification/version/history.txt"
    assert history.read_text() == "history" and history.stat().st_uid == os.getuid()
    assert sorted(p.name for p in w.root.parent.parent.joinpath("artifacts").iterdir()) == ["sample"]
