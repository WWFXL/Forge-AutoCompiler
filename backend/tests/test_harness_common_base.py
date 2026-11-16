"""共同底座回归：真实编译与长脚本，不以检查数量估计模型收益。"""

import json
import subprocess

import pytest
from test_simple_build import LocalRuntime, actions, reference, runner  # noqa: F401

from deerflow.compile.docker_runtime import CompileDockerRuntime, RuntimeConfig
from deerflow.compile.plan_workflow import PlanContractError, PlanStep
from deerflow.compile.schemas import CompileSession
from deerflow.compile.simple_build_runtime import SimpleBuildWorkflow, configuration_entry, generated_reset_step, observe_configuration
from deerflow.compile.simple_build_task import SimpleBuildActions, assemble_simple_plan


def test_actual_make_entry_is_not_gated_by_initial_cmake_label(runner):  # noqa: F811
    task, session, manager, root = runner
    task = task.model_copy(update={"build_system": "cmake"})
    session.build_system = session.selected_build_system = "cmake"
    manager.save_session(session)
    w = SimpleBuildWorkflow(plan=assemble_simple_plan(task, actions()), session=session, manager=manager, runtime=LocalRuntime(), reference=reference(task))
    assert w.run()["status"] == "primary_completed"
    assert w.configuration["build_system"] == "make"
    assert w.plan.task.build_system == "cmake" and w.primary["status"] == "passed"


def test_scons_entry_ignores_stale_cmake_cache(tmp_path):
    (tmp_path / "CMakeCache.txt").write_text("incomplete cache")
    step = PlanStep(step_id="build", role="build", command="scons -j2", source="作者SConstruct", expected="主库")
    system, directory = configuration_entry(tmp_path, step, {"build_system": "cmake"})
    assert system == "scons"
    assert observe_configuration(tmp_path, system, directory=directory)["status"] == "not_applicable"


def test_explicit_cmake_directory_does_not_observe_an_unrelated_cache(tmp_path):
    (tmp_path / "old").mkdir()
    (tmp_path / "old/CMakeCache.txt").write_text("stale cache")
    step = PlanStep(step_id="build", role="build", command="cmake --build current", source="作者", expected="主库")
    assert configuration_entry(tmp_path, step, {"build_system": "cmake"}) == ("cmake", None)
    system, directory = configuration_entry(tmp_path, step, {"build_system": "cmake"}, build_directory="/workspace/repo/current")
    assert (system, directory) == ("cmake", "current")
    actual = observe_configuration(tmp_path, system, directory=directory)
    assert actual["status"] == "unknown" and actual["configurations"] == []


def test_preset_uses_cmake_reported_directory_and_checks_real_cache(tmp_path):
    (tmp_path / "CMakeLists.txt").write_text("project(sample C)\n")
    current = tmp_path / "out/preset build"
    current.mkdir(parents=True)
    (current / "CMakeCache.txt").write_text("CMAKE_GENERATOR:INTERNAL=Unix Makefiles\nCMAKE_HOME_DIRECTORY:INTERNAL=/workspace/repo\nCMAKE_CACHEFILE_DIR:INTERNAL=/workspace/repo/out/preset build\n")
    (current / "Makefile").write_text("all:\n")
    step = PlanStep(step_id="configure", role="configure", command="cmake --preset gcc", source="作者preset", expected="配置")
    system, directory = configuration_entry(tmp_path, step, {"build_system": "cmake"}, output="-- Build files have been written to: /workspace/repo/out/preset build\n")
    assert (system, directory) == ("cmake", "out/preset build")
    assert observe_configuration(tmp_path, system, directory=directory)["status"] == "passed"
    (current / "Makefile").unlink()
    assert observe_configuration(tmp_path, system, directory=directory)["status"] == "failed"
    with pytest.raises(PlanContractError):
        configuration_entry(tmp_path, step, {}, output="-- Build files have been written to: /tmp/outside\n")
    with pytest.raises(PlanContractError):
        configuration_entry(tmp_path, step, {}, output="-- Build files have been written to: /workspace/repo/../../outside\n")


def test_split_configuration_checks_completion_only_at_phase_end(runner):  # noqa: F811
    task, session, manager, root = runner
    task = task.model_copy(update={"build_system": "autotools"})
    session.build_system = session.selected_build_system = "autotools"
    manager.save_session(session)
    # 使用真实Shell生成配置脚本/Makefile与主库；阶段观察不依赖脚本名白名单。
    makefile = (root / "Makefile").read_text()
    (root / "Makefile").unlink()
    (root / "generate.sh").write_text("#!/bin/sh\ncp configure.template configure\nchmod +x configure\n")
    (root / "configure.template").write_text("#!/bin/sh\nprintf configured > config.status\ncat > Makefile <<'EOF'\n" + makefile + "EOF\n")
    proposal = SimpleBuildActions(
        reason="生成后配置",
        steps=[
            dict(step_id="generate", role="configure", command="sh generate.sh", source="作者脚本", expected="生成configure"),
            dict(step_id="configure", role="configure", command="./configure", requires=["generate"], source="作者", expected="完成配置"),
            dict(step_id="build", role="build", command="make", requires=["configure"], source="作者", expected="主库"),
        ],
    )
    w = SimpleBuildWorkflow(plan=assemble_simple_plan(task, proposal), session=session, manager=manager, runtime=LocalRuntime(), reference=reference(task))
    assert w.run()["status"] == "primary_completed"
    assert w.handoffs_used == 0 and w.primary["status"] == "passed"
    events = [json.loads(line) for line in manager.local_logs_dir(w._session).joinpath("workflow.log").read_text().splitlines()]
    observed = [e for e in events if e.get("event") == "simple.configuration_observed"]
    assert observed[0]["status"] == "unknown" and observed[0]["phase_complete"] is False
    assert observed[1]["status"] == "passed" and observed[1]["phase_complete"] is True


@pytest.mark.parametrize("generation,configure", [("false", "touch config.status"), ("true", "true")])
def test_split_configuration_distinguishes_real_failure_from_unknown(runner, generation, configure):  # noqa: F811
    task, session, manager, root = runner
    task = task.model_copy(update={"build_system": "autotools"})
    session.build_system = session.selected_build_system = "autotools"
    manager.save_session(session)
    (root / "configure").write_text("#!/bin/sh\n" + configure + "\n")
    proposal = SimpleBuildActions(
        reason="配置反例",
        steps=[
            dict(step_id="generate", role="configure", command=generation, source="作者", expected="前置"),
            dict(step_id="configure", role="configure", command="sh configure", requires=["generate"], source="作者", expected="配置"),
            dict(step_id="build", role="build", command="make", requires=["configure"], source="作者", expected="主库"),
        ],
    )
    w = SimpleBuildWorkflow(plan=assemble_simple_plan(task, proposal), session=session, manager=manager, runtime=LocalRuntime(), reference=reference(task))
    result = w.run()
    if generation == "false":
        assert result["status"] == "needs_handoff" and not (root / "libsample.a").exists()
        assert result["handoff"]["reason"] == "step_failed_or_expectation_missing"
    else:
        # 真实Makefile存在；配置未知允许执行build，但仍须实际产出主库。
        assert result["status"] == "primary_completed" and w.primary["status"] == "passed"
        assert (root / "libsample.a").is_file() and w.handoffs_used == 0


def test_large_protected_list_is_not_a_shell_argument(tmp_path, monkeypatch):
    # 原失败为153264字节；此例更长，同时核验有空格/引号的原文件受到保护。
    baseline = {f"nested/{i:05d}-" + "x" * 75: {} for i in range(2400)}
    baseline["original ' file.c"] = {}
    (tmp_path / "original ' file.c").write_text("original")
    (tmp_path / "generated.o").write_text("remove")
    from deerflow.compile.generated_inputs import write_manifest

    write_manifest(tmp_path, baseline)
    step = generated_reset_step(baseline)
    assert len(step.command.encode()) < 2000
    assert "nested/" not in step.command
    script = step.command.replace("/workspace/repo", str(tmp_path))
    real_run = subprocess.run
    seen = []

    def docker_substitute(command, **kwargs):
        seen.append(command)
        assert max(len(arg.encode()) for arg in command) < 65536
        # 清理命令已缩短，正常走短命令通道；保留严格Shell语义。
        assert command[-2] == "-lc" and command[-1].startswith("set -euo pipefail\n")
        return real_run(["bash", "-c", command[-1]], **kwargs)

    monkeypatch.setattr(subprocess, "run", docker_substitute)
    session = CompileSession(session_id="large-script", thread_id="test", repo_url="https://example.invalid/repo", branch=None, image="test", status="ready", container_id="local-substitute")
    result = CompileDockerRuntime(config=RuntimeConfig()).exec(session, script, strict_shell=True)
    assert len(seen) == 1 and result.exit_code == 0
    assert "FORGE_GENERATED_RESET" in result.stdout
    assert (tmp_path / "original ' file.c").read_text() == "original"
    assert not (tmp_path / "generated.o").exists()


def test_long_script_keeps_strict_shell_failure(monkeypatch):
    real_run = subprocess.run

    def docker_substitute(command, **kwargs):
        return real_run(["bash", "-s"], **kwargs)

    monkeypatch.setattr(subprocess, "run", docker_substitute)
    session = CompileSession(session_id="strict", thread_id="test", repo_url="https://example.invalid/repo", branch=None, image="test", status="ready", container_id="local")
    result = CompileDockerRuntime(config=RuntimeConfig()).exec(session, "#" + "x" * 70000 + "\nfalse\nprintf BAD", strict_shell=True)
    assert result.exit_code != 0 and "BAD" not in result.stdout


@pytest.mark.parametrize("command", ["cat /repro", "cat '/repro/source.tar'", 'ls "/repro"'])
def test_real_repro_path_remains_restricted(command):
    from deerflow.compile.simple_build_runtime import validate_phase_command

    with pytest.raises(PlanContractError):
        validate_phase_command(PlanStep(step_id="inspect", role="configure", command=command, source="夹具", expected="禁止"))


def test_normal_reproducer_filename_is_not_repro_directory():
    from deerflow.compile.simple_build_runtime import validate_phase_command

    validate_phase_command(PlanStep(step_id="inspect", role="configure", command="test -f tests/reproducers.c", source="作者源码", expected="正常文件"))


def test_manifest_change_stops_before_deleting_generated_files(tmp_path):
    from deerflow.compile.generated_inputs import write_manifest

    write_manifest(tmp_path, ["source.c"])
    step = generated_reset_step(["source.c"])
    write_manifest(tmp_path, [])
    generated = tmp_path / "generated.o"
    generated.write_text("untouched")
    result = subprocess.run(["bash", "-c", step.command.replace("/workspace/repo", str(tmp_path))], capture_output=True, text=True)
    assert result.returncode != 0 and generated.read_text() == "untouched"


def test_clean_replay_recreates_manifest_from_original_files(tmp_path):
    from deerflow.compile.generated_inputs import SNAPSHOT_SCRIPT, manifest_bytes

    root = tmp_path / "repo"
    root.mkdir()
    (root / "tests").mkdir()
    (root / "tests/reproducers.c").write_text("source")
    (root / "link").symlink_to("tests", target_is_directory=True)
    (root / ".git").mkdir()
    (root / ".git/ignored").write_text("metadata")
    result = subprocess.run(["python3", "-c", SNAPSHOT_SCRIPT.replace("/workspace/repo", str(root))], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / ".forge-source-inputs.json").read_bytes() == manifest_bytes(["link", "tests/reproducers.c"])
    (root / "generated.o").write_text("generated")
    result = subprocess.run(["bash", "-c", generated_reset_step(["link", "tests/reproducers.c"]).command.replace("/workspace/repo", str(root))], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert (root / "tests/reproducers.c").is_file() and (root / "link").is_symlink()
    assert not (root / "generated.o").exists() and (root / ".git/ignored").exists()
