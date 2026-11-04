"""简洁构建的行为回归：真实本机编译验证观察逻辑，Docker另作工程实跑。"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.plan_workflow import PlanContractError, PlanStep, _digest
from deerflow.compile.schemas import CommandResult
from deerflow.compile.simple_build_runtime import SimpleBuildWorkflow, observe_configuration, primary_artifacts, source_inventory, source_unchanged, validate_phase_command
from deerflow.compile.simple_build_task import BuildReference, PrimaryComponent, PublicBuildTask, assemble_simple_plan, simple_agent_packet
from deerflow.compile.unified_plan_equivalent_observed import ObservedBuildActions
from deerflow.config.paths import Paths


def task(**kwargs):
    return PublicBuildTask(plan_id="sample", repository_url="https://example.invalid/sample", commit_sha="a" * 40, image_id="sha256:" + "1" * 64, source_archive_sha256="b" * 64, build_system=kwargs.pop("build_system", "make"), **kwargs)


def reference(t):
    return BuildReference(task_sha256=_digest(t.model_dump(mode="json")), components=(PrimaryComponent(name="sample", artifact_names=("libsample.a",), kinds=("static_library",), evidence="Makefile:1"),))


def actions(command="make", **kwargs):
    return ObservedBuildActions(reason="工程夹具", steps=[dict(step_id="build", role="build", command=command, source="Makefile:1", expected="构建主库", **kwargs)])


class LocalRuntime:
    """保留真实退出码与日志；仅把固定容器仓库别名映射至临时夹具目录。"""

    def exec(self, session, command, *, workdir, timeout_seconds, log_path, strict_shell):
        assert strict_shell
        root = session.leadagent_repo_dir
        command = command.replace("/workspace/repo", root)
        process = subprocess.run(["bash", "-c", "set -euo pipefail\n" + command], cwd=workdir.replace("/workspace/repo", root), capture_output=True, text=True, timeout=timeout_seconds)
        output = process.stdout + process.stderr
        Path(log_path).write_text(output)
        return CommandResult(process.returncode, process.stdout, process.stderr, output, log_path)


@pytest.fixture
def runner(tmp_path):
    manager = CompileSessionManager(paths=Paths(base_dir=tmp_path / "data", workspace_root=tmp_path, host_workspace_root=str(tmp_path)))
    t = task()
    session = manager.create_session("simple-test", t.repository_url)
    session.commit_sha, session.image_id = t.commit_sha, t.image_id
    session.replay_source_archive_sha256 = t.source_archive_sha256
    session.build_system = session.selected_build_system = "make"
    session.status = "inspected"
    manager.save_session(session)
    root = Path(session.leadagent_repo_dir)
    root.mkdir(parents=True, exist_ok=True)
    (root / "sample.c").write_text("int sample(void) { return 7; }\n")
    (root / "Makefile").write_text("libsample.a: sample.c\n\tcc -c sample.c -o sample.o\n\tar rcs libsample.a sample.o\nclean:\n\trm -f sample.o libsample.a\n")
    return t, session, manager, root


def workflow(runner, proposal):
    t, session, manager, _ = runner
    return SimpleBuildWorkflow(plan=assemble_simple_plan(t, proposal), session=session, manager=manager, runtime=LocalRuntime(), reference=reference(t))


def test_public_task_has_no_reference_or_evaluation_script():
    t = task()
    packet = json.dumps(simple_agent_packet(t), ensure_ascii=False)
    assert "libsample.a" not in packet and "artifact_paths" not in packet and "verification_steps" not in packet
    with pytest.raises(ValidationError):
        PublicBuildTask(**t.model_dump(), reference="secret")


def test_wrong_model_path_and_stdout_no_longer_negate_real_build(runner):
    w = workflow(runner, actions(stdout_contains=("Build files have been written",), files_exist=("build/src/lib_json/libsample.a",)))
    assert len(w.plan.steps) == 1 and not w.plan.artifact_paths
    assert w.run()["status"] == "primary_completed"
    assert w.layers["primary_build_completed"] is True
    frozen = (w.directory / "primary-result.json").read_bytes()
    assert w.primary["artifacts"][0]["path"] == "libsample.a"
    assert (w.directory / "primary-result.json").read_bytes() == frozen


def test_true_build_failure_repaired_with_clean_preserves_failure(runner):
    w = workflow(runner, actions("make missing-target"))
    first = w.run()
    assert first["status"] == "needs_handoff"
    failed = first["handoff"]["recent_commands"][-1]
    assert failed["exit_code"] != 0
    w.apply_revision(handoff_id=first["handoff"]["handoff_id"], plan=assemble_simple_plan(w.plan.task, actions("make clean && make"), revision=2), reason="修正真实错误目标并正常重建")
    assert w.run()["status"] == "primary_completed"
    assert failed["command_id"] != w.completed["build"]
    assert Path(failed["log_path"]).is_file()


def test_dependency_change_physically_cleans_generated_outputs(runner):
    w = workflow(runner, actions("make missing-target"))
    h = w.run()["handoff"]
    (w.root / "stale-object.o").write_bytes(b"stale")
    p = actions()
    value = p.model_dump()
    value["steps"].insert(0, dict(step_id="dep", role="dependency", command="command -v cc", source="环境", expected="编译器存在"))
    p = ObservedBuildActions.model_validate(value)
    w.apply_revision(handoff_id=h["handoff_id"], plan=assemble_simple_plan(w.plan.task, p, revision=2), reason="依赖变化，需实际清理")
    assert any(s.step_id == "forge-generated-reset" for s in w.plan.steps)
    assert w.run()["status"] == "primary_completed"
    assert not (w.root / "stale-object.o").exists()
    assert (w.root / "sample.c").is_file()


@pytest.mark.parametrize("command", ["make clean && make", "make distclean && autoreconf -fi && ./configure"])
def test_scoped_cleanup_is_phase_prelude(command):
    validate_phase_command(PlanStep(step_id="test", role="configure" if "configure" in command else "build", command=command, source="fixture", expected="成功"))


@pytest.mark.parametrize("command", ["make && make clean", "make clean && apt-get install -y zlib1g-dev && make", "make clean && rm -rf src && make", "set +e; make clean; make"])
def test_cleanup_does_not_relax_other_guards(command):
    with pytest.raises(PlanContractError):
        validate_phase_command(PlanStep(step_id="test", role="build", command=command, source="fixture", expected="拒绝"))


def test_original_source_change_is_rejected(runner):
    w = workflow(runner, actions("printf 'corrupt' > sample.c; make"))
    with pytest.raises(PlanContractError, match="原源码/测试被修改"):
        w.run()


def test_precompiled_file_cannot_be_copied_as_new_build(runner):
    t, _, _, root = runner
    subprocess.run(["make"], cwd=root, check=True, capture_output=True)
    baseline = source_inventory(root)
    (root / "new").mkdir()
    shutil.copy2(root / "libsample.a", root / "new/libsample.a")
    import time

    observed = primary_artifacts(task=t, reference=reference(t), root=root, baseline=baseline, deadline=time.monotonic() + 5)
    assert observed["status"] == "failed"


def test_cmake_uses_actual_make_generator_not_guessed_ninja(tmp_path):
    (tmp_path / "CMakeLists.txt").write_text("project(dummy C)\n")
    b = tmp_path / "build"
    b.mkdir()
    (b / "CMakeCache.txt").write_text("CMAKE_GENERATOR:INTERNAL=Unix Makefiles\nCMAKE_HOME_DIRECTORY:INTERNAL=/workspace/repo\nCMAKE_CACHEFILE_DIR:INTERNAL=/workspace/repo/build\n")
    (b / "Makefile").write_text("all:\n")
    assert observe_configuration(tmp_path, "cmake")["status"] == "passed"
    assert not (b / "build.ninja").exists()
    (b / "Makefile").unlink()
    assert observe_configuration(tmp_path, "cmake")["status"] == "failed"


def test_source_replaced_with_same_content_still_rejected(tmp_path):
    p = tmp_path / "original.c"
    p.write_text("original")
    baseline = source_inventory(tmp_path)
    replacement = tmp_path / "replacement"
    replacement.write_text("original")
    replacement.replace(p)
    with pytest.raises(PlanContractError):
        source_unchanged(tmp_path, baseline)


def test_real_graph_filters_private_data_at_meter_replacement_boundary(tmp_path):
    from datetime import UTC, datetime, timedelta

    from test_plan_agent import ScriptedPlanModel, response

    from deerflow.compile.plan_agent import PlanAgentLedger
    from deerflow.compile.plan_agent_context import ContextCanaryMeter
    from deerflow.compile.simple_build_task import propose_simple

    meter = ContextCanaryMeter(
        PlanAgentLedger(tmp_path / "agent"),
        accepted_models=("test-model",),
        deadline=(datetime.now(UTC) + timedelta(hours=2)).isoformat(),
        packet=lambda: {"task": {"secret_reference": "DO_NOT_SEND"}, "verification_steps": ["PRIVATE_SCRIPT"], "source_packet": []},
    )
    model = ScriptedPlanModel(responses=[response("ObservedBuildActions", actions().model_dump(mode="json"))])
    plan, _ = propose_simple(model=model, task=task(), source_root=tmp_path, session_root=tmp_path, meter=meter)
    assert len(plan.steps) == 1
    raw = (tmp_path / "agent/request-1.json").read_text()
    assert "DO_NOT_SEND" not in raw and "PRIVATE_SCRIPT" not in raw
    actual = json.loads(json.loads(raw)["messages"][0]["content"])
    assert actual["task"]["task_version"] == "simple-build-v1"
    assert "verification_steps" not in actual
