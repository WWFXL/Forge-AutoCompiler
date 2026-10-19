"""受控工程夹具：真实编译、失败日志、脚本化修订与干净重建。"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tarfile
from pathlib import Path

import pytest

from deerflow.compile.plan_workflow import BuildPlan, PlanStep

REPO_ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(os.getenv("FORGE_RUN_PLAN_WORKFLOW_DOCKER") != "1", reason="显式设置 FORGE_RUN_PLAN_WORKFLOW_DOCKER=1 运行真实 Docker 工程测试")


def test_failed_test_log_survives_scripted_repair_and_cleanup(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "sample.c").write_text("int sample_add(int a, int b) { return a+b; }\n")
    (source / "Makefile").write_text(
        "libsample.a: sample.o\n\tar rcs $@ $^\n"
        "sample.o: sample.c\n\tcc -c sample.c -o sample.o\n"
        "check:\n\tmkdir -p tests\n\tprintf 'controlled-verification-log\\n' > tests/test-suite.log\n"
        "\ttest -f build/ready\n\tprintf 'tests passed\\n'\n"
    )
    for args in [
        ["init", "--quiet"],
        ["add", "."],
        ["-c", "user.name=Forge Prototype Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "受控工程夹具"],
    ]:
        subprocess.run(["git", *args], cwd=source, check=True, capture_output=True, timeout=20)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    archive_path = tmp_path / "source.tar"
    with tarfile.open(archive_path, "w") as archive:
        for name in ("Makefile", "sample.c"):
            archive.add(source / name, arcname=name)
    image = subprocess.check_output(["docker", "image", "inspect", "autocompiler:gcc13", "--format", "{{.Id}}"], text=True, timeout=20).strip()
    plan = BuildPlan(
        plan_id="controlled-fixture",
        repository_url="https://example.invalid/controlled-fixture.git",
        commit_sha=commit,
        image_id=image,
        source_archive_sha256=hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        build_system="make",
        artifact_paths=("libsample.a",),
        steps=(
            PlanStep(step_id="build", role="build", command="make -j2", source="Makefile:1", expected="生成静态库"),
            PlanStep(
                step_id="check",
                role="smoke",
                command="make check",
                source="Makefile:5",
                expected="既定测试通过",
                required_output=("tests passed",),
                diagnostic_paths=("tests/test-suite.log",),
            ),
            PlanStep(step_id="stage", role="artifact_stage", command="cp libsample.a /artifacts/", source="任务交付合同", expected="暂存静态库"),
        ),
    )
    prerequisite = PlanStep(step_id="generate", role="configure", command="mkdir -p build; touch build/ready", source="受控夹具的生成输入", expected="生成测试所需输入")
    repair = BuildPlan.model_validate({**plan.model_dump(), "revision": 2, "steps": (prerequisite, *plan.steps)})
    plan_path, repair_path = tmp_path / "plan.json", tmp_path / "repair.json"
    plan_path.write_text(plan.model_dump_json(indent=2))
    repair_path.write_text(repair.model_dump_json(indent=2))
    output = tmp_path / "run"
    completed = subprocess.run(
        [
            "uv",
            "run",
            "--no-sync",
            "python",
            str(REPO_ROOT / "scripts" / "forge_build_plan_prototype.py"),
            "--plan",
            str(plan_path),
            "--repair-plan",
            str(repair_path),
            "--source-archive",
            str(archive_path),
            "--output-root",
            str(output),
            "--verify",
        ],
        cwd=REPO_ROOT / "backend",
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr + (output / "result.json").read_text()
    result = json.loads((output / "result.json").read_text())
    assert result["initial"]["status"] == "needs_handoff"
    assert result["after_scripted_revision"]["status"] == "ready_for_verification"
    assert result["status"] == "verified" and result["session_status"] == "completed"
    assert result["cleanup"]["succeeded"]
    assert result["provider_calls"] == result["runtime_agent_calls"] == 0
    failed_command = result["initial"]["handoff"]["recent_commands"][-1]
    captures = list(output.rglob(f"plan-diagnostics/{failed_command['command_id']}/tests/test-suite.log"))
    assert len(captures) == 1 and captures[0].read_text() == "controlled-verification-log\n"
    assert [row["role"] for row in result["recipe"]["steps"]] == ["configure", "build", "artifact_stage"]
    assert failed_command["command_id"] not in [row["command_id"] for row in result["recipe"]["verification_steps"]]
