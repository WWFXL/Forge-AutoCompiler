"""真实CMake配置偏离→直接修订→原测试→干净重建；仅为工程检查。"""

import hashlib
import json
import os
import subprocess
import sys
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_goal_state_comparison as comparison  # noqa: E402
import forge_build_prepared_arm as prepared  # noqa: E402

from deerflow.compile.build_task_checks import cmake_configuration_command  # noqa: E402
from deerflow.compile.goal_state import GoalStateWorkflow, goal_state_planner  # noqa: E402
from deerflow.compile.plan_agent import PlanTask  # noqa: E402
from deerflow.compile.plan_workflow import PlanStep  # noqa: E402
from deerflow.compile.unified_plan_equivalent_observed import ObservedBuildActions, assemble_observed  # noqa: E402

pytestmark = pytest.mark.skipif(os.getenv("FORGE_RUN_GOAL_STATE_DOCKER") != "1", reason="显式设置FORGE_RUN_GOAL_STATE_DOCKER=1运行实际Docker开发检查")


def test_real_configure_revision_build_tests_replay_cleanup(tmp_path):
    subprocess.run(["bash", str(comparison.ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    source = tmp_path / "source"
    source.mkdir()
    (source / "CMakeLists.txt").write_text(
        'cmake_minimum_required(VERSION 3.16)\nproject(sample C)\noption(BUILD_TESTS "Build original tests" OFF)\n'
        "add_library(sample STATIC sample.c)\nif(BUILD_TESTS)\n enable_testing()\n add_executable(sample_test sample_test.c)\n"
        " target_link_libraries(sample_test PRIVATE sample)\n add_test(NAME original_test COMMAND sample_test)\nendif()\n"
    )
    (source / "sample.c").write_text("int answer(void) { return 42; }\n")
    (source / "sample_test.c").write_text("extern int answer(void); int main(void) { return answer() == 42 ? 0 : 1; }\n")
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    subprocess.run(["git", "-C", str(source), "-c", "user.name=Forge Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "配置状态开发夹具"], check=True)
    commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    archive_path = tmp_path / "source.tar"
    with tarfile.open(archive_path, "w") as archive:
        for name in ("CMakeLists.txt", "sample.c", "sample_test.c"):
            archive.add(source / name, arcname=name)
    image = subprocess.check_output(["docker", "image", "inspect", "autocompiler:gcc13", "--format", "{{.Id}}"], text=True).strip()
    task = PlanTask(
        plan_id="goal-state-controlled-fixture",
        repository_url="https://example.invalid/goal-state-fixture.git",
        commit_sha=commit,
        source_archive_sha256=hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        image_id=image,
        build_system="cmake",
        artifact_paths=("libsample.a",),
        verification_steps=(
            PlanStep(
                step_id="check",
                role="smoke",
                command=cmake_configuration_command({"BUILD_TESTS": True}) + " && ctest --test-dir build --output-on-failure --no-tests=error",
                requires=("build",),
                source="原夹具任务",
                expected="原测试通过",
                required_output=("FORGE_TASK_CONFIGURATION_OK", "100% tests passed"),
            ),
        ),
    )
    item = dict(name="sample", task=task.model_dump(mode="json"), source_archive=str(archive_path), source_paths=["CMakeLists.txt"])
    proposal = ObservedBuildActions(
        reason="受控任务：初始故意关闭测试；不是自然模型错误",
        steps=[
            dict(step_id="configure", role="configure", command="cmake -S . -B build -DBUILD_TESTS=OFF", source="受控初始动作", expected="配置完成"),
            dict(step_id="build", role="build", command="cmake --build build --parallel 2", requires=("configure",), source="原CMake", expected="编译"),
        ],
    )

    def scripted(**kwargs):
        assert kwargs.get("current_plan") is None, "本夹具恢复应使用真实状态选择直接动作"
        return assemble_observed(task, proposal, revision=1), proposal.reason

    deadline = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    registry = comparison.base.FixedVerifierRegistry(item["task"])
    obligation = {"required": "原测试完整执行", "correct_reference_injected": False}
    with comparison.bounded.execution_window(deadline), patch.object(prepared, "PreparedWorkflow", GoalStateWorkflow):
        row = prepared.run_arm(
            item=item,
            arm="plan",
            protocol=dict(provider=comparison.flash.PROVIDER, deadline_utc=deadline),
            root=tmp_path,
            planner=goal_state_planner(scripted),
            meter_factory=lambda *a, **kw: comparison.flash.FlashMeter(*a, registry=registry, obligation=obligation, **kw),
            command_timeout_seconds=120,
            replay_timeout_seconds=120,
        )
    assert row["strict_completed"], row
    assert row["agent_usage"]["model_requests"] == row["agent_usage"]["recorded_tokens"] == 0
    assert row["cleanup"]["succeeded"]
    assert row["transitions"][0]["handoff"]["reason"] == "configuration_goal_violated"
    state = json.loads(next((tmp_path / "sample-plan").glob(".compile-sessions/*/*/session.json")).read_text())
    commands = state["commands"]
    assert len([c for c in commands if c["role"] == "build"]) == 1
    assert [c["role"] for c in commands if c["role"] in ("configure", "build")] == ["configure", "configure", "build"]
    assert state["replay_attempts"][-1]["status"] == "passed"
