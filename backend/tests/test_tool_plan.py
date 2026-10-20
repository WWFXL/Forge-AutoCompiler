"""验证工具方案的任务边界、可执行暂存及未知状态处理。"""

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from deerflow.compile.plan_agent import PlanTask
from deerflow.compile.tool_plan import ToolPlanNeedsAgent, artifact_stage_command, generate_tool_plan


def task(system="make", artifacts=("sample",)):
    return PlanTask.model_validate(
        {
            "plan_id": "qualification-test",
            "repository_url": "https://example.org/repo",
            "commit_sha": "a" * 40,
            "image_id": "sha256:" + "b" * 64,
            "source_archive_sha256": "c" * 64,
            "build_system": system,
            "artifact_paths": artifacts,
            "verification_steps": [{"step_id": "check", "role": "smoke", "command": "printf '%s\\n' 'all fixed tests'", "source": "任务作者", "expected": "完整测试", "required_output": ["all fixed tests"], "requires": ["build"]}],
        }
    )


@pytest.mark.parametrize("system,filename,content", [("make", "Makefile", "all:\n\t$(CC) app.c -o sample\n"), ("cmake", "CMakeLists.txt", "project(example)\n"), ("autotools", "configure.ac", "AC_INIT(example,1)\n")])
def test_three_templates_preserve_fixed_tests_and_source(tmp_path, system, filename, content):
    (tmp_path / filename).write_text(content)
    original = task(system)
    plan, receipt = generate_tool_plan(original, tmp_path)
    assert tuple(s for s in plan.steps if s.role == "smoke") == original.verification_steps
    assert plan.artifact_paths == original.artifact_paths
    assert receipt["provider_calls"] == 0 and receipt["unresolved"]
    assert receipt["source_reads"] == [{"path": filename, "sha256": hashlib.sha256(content.encode()).hexdigest(), "bytes": len(content)}]
    assert (tmp_path / filename).read_text() == content


@pytest.mark.parametrize(
    "files,system",
    [
        ({}, "make"),
        ({"CMakeLists.txt": "", "Makefile": ""}, "cmake"),
        ({"Makefile": "", "meson.build": ""}, "make"),
        ({"Makefile": "", "GNUmakefile": ""}, "make"),
        ({"CMakeLists.txt": ""}, "make"),
        ({"Makefile": "", "sample": "prebuilt or script"}, "make"),
    ],
)
def test_uncertainty_abstains_without_guessing(tmp_path, files, system):
    for name, content in files.items():
        (tmp_path / name).write_text(content)
    with pytest.raises(ToolPlanNeedsAgent):
        generate_tool_plan(task(system), tmp_path)


def test_autotools_uses_existing_configure_without_regeneration(tmp_path):
    (tmp_path / "configure").write_text("#!/bin/sh\nexit 0\n")
    plan, _ = generate_tool_plan(task("autotools"), tmp_path)
    assert plan.steps[0].command == "sh ./configure"
    assert "autoreconf" not in " ".join(s.command for s in plan.steps)


def test_symlink_entry_does_not_read_outside_source(tmp_path):
    external = tmp_path / "external"
    external.write_text("private")
    root = tmp_path / "repo"
    root.mkdir()
    (root / "Makefile").symlink_to(external)
    with pytest.raises(ToolPlanNeedsAgent):
        generate_tool_plan(task(), root)


@pytest.mark.parametrize("artifacts", [("../escape",), ("/tmp/escape",), ("one/same", "two/same")])
def test_unsafe_or_same_basename_delivery_abstains(tmp_path, artifacts):
    (tmp_path / "Makefile").write_text("all:\n\ttrue\n")
    with pytest.raises(ToolPlanNeedsAgent):
        generate_tool_plan(task(artifacts=artifacts), tmp_path)


@pytest.mark.parametrize("count", [0, 2])
def test_runtime_staging_rejects_missing_or_ambiguous_products(tmp_path, count):
    for i in range(count):
        folder = tmp_path / str(i)
        folder.mkdir()
        (folder / "sample").write_bytes(b"!<arch>\n")
    result = subprocess.run(["bash", "-c", artifact_stage_command(("sample",), ".")], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode != 0 and "交付源必须唯一" in result.stderr


def test_staging_real_elf_and_preserves_mode(tmp_path):
    # 使用宿主临时交付路径替换常量，只测试配方执行语义，不触碰真实/artifacts。
    executable = tmp_path / "a dir" / "sample"
    executable.parent.mkdir()
    executable.write_bytes(Path(sys.executable).read_bytes())
    executable.chmod(0o755)
    delivery = tmp_path / "delivery"
    command = artifact_stage_command(("sample",), ".").replace("/artifacts", str(delivery))
    result = subprocess.run(["bash", "-c", command], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert (delivery / "sample").read_bytes() == executable.read_bytes()
    assert os.access(delivery / "sample", os.X_OK)


def test_recovery_stops_before_model_and_retains_handoff(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from forge_build_tool_plan_qualification import qualification_planner

    (tmp_path / "Makefile").write_text("all:\n\ttrue\n")
    plan, _ = generate_tool_plan(task(), tmp_path)
    meter = Mock()
    model = Mock(side_effect=AssertionError("不能调用模型"))
    with pytest.raises(ToolPlanNeedsAgent):
        qualification_planner(task=task(), source_root=tmp_path, meter=meter, current_plan=plan, handoff={"reason": "command_failed"}, model=model)
    assert meter.ledger.save.call_args.args[1]["handoff"] == {"reason": "command_failed"}
    model.assert_not_called()


def test_zero_provider_meter_rejects_before_network():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from forge_build_tool_plan_qualification import NoProviderMeter

    handler = Mock()
    with pytest.raises(ValueError, match="禁止调用模型"):
        NoProviderMeter.wrap_model_call(None, {}, handler)
    handler.assert_not_called()
