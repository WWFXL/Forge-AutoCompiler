"""共同底座回归：真实编译与长脚本，不以检查数量估计模型收益。"""

import subprocess

from test_simple_build import LocalRuntime, actions, reference, runner  # noqa: F401

from deerflow.compile.docker_runtime import CompileDockerRuntime, RuntimeConfig
from deerflow.compile.plan_workflow import PlanStep
from deerflow.compile.schemas import CompileSession
from deerflow.compile.simple_build_runtime import SimpleBuildWorkflow, configuration_entry, generated_reset_step, observe_configuration
from deerflow.compile.simple_build_task import assemble_simple_plan


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


def test_active_cmake_directory_does_not_observe_an_unrelated_cache(tmp_path):
    (tmp_path / "old").mkdir()
    (tmp_path / "old/CMakeCache.txt").write_text("stale cache")
    step = PlanStep(step_id="build", role="build", command="cmake --build current", source="作者", expected="主库")
    system, directory = configuration_entry(tmp_path, step, {"build_system": "cmake"})
    assert (system, directory) == ("cmake", "current")
    actual = observe_configuration(tmp_path, system, directory=directory)
    assert actual["status"] == "unknown" and actual["configurations"] == []


def test_large_protected_list_is_not_a_shell_argument(tmp_path, monkeypatch):
    # 原失败为153264字节；此例更长，同时核验有空格/引号的原文件受到保护。
    baseline = {f"nested/{i:05d}-" + "x" * 75: {} for i in range(2400)}
    baseline["original ' file.c"] = {}
    (tmp_path / "original ' file.c").write_text("original")
    (tmp_path / "generated.o").write_text("remove")
    step = generated_reset_step(baseline)
    script = step.command.replace("/workspace/repo", str(tmp_path))
    real_run = subprocess.run
    seen = []

    def docker_substitute(command, **kwargs):
        seen.append(command)
        assert command[2] == "-i" and command[-2:] == ["bash", "-ls"]
        assert max(len(arg.encode()) for arg in command) < 65536
        assert kwargs["input"].startswith("set -euo pipefail\n")
        return real_run(["bash", "-s"], **kwargs)

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
