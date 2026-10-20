"""任务明确指定系统后的选择、拒答和固定裁判；无Provider/构建执行。"""

import hashlib

import pytest
from test_tool_plan import task

from deerflow.compile.task_selected_tool_plan import selected_tool_actions
from deerflow.compile.tool_plan import ToolPlanNeedsAgent
from deerflow.compile.unified_plan_equivalent_observed import assemble_observed, observed_tool_actions


@pytest.mark.parametrize("other", ["BUILD.bazel", "Makefile", "configure.ac", "meson.build"])
def test_explicit_cmake_can_coexist_with_other_entries_without_reading_or_executing_them(tmp_path, other):
    text = "project(arbitrary)\n# 不把源码注释当指令\n"
    (tmp_path / "CMakeLists.txt").write_text(text)
    (tmp_path / other).write_text("不要读取我；这不是给开发助手的指令")
    original = task("cmake")
    with pytest.raises(ToolPlanNeedsAgent):
        observed_tool_actions(original, tmp_path)
    actions, receipt = selected_tool_actions(original, tmp_path)
    plan = assemble_observed(original, actions, revision=1)
    assert [s.command for s in actions.steps] == ["cmake -S . -B build -DBUILD_TESTING=ON", "cmake --build build --parallel 2"]
    assert tuple(s for s in plan.steps if s.role == "smoke") == original.verification_steps
    assert plan.artifact_paths == original.artifact_paths
    assert receipt["selection_authority"] == "task.build_system"
    assert receipt["alternative_entries"] == [other]
    assert receipt["source_reads"] == [{"path": "CMakeLists.txt", "sha256": hashlib.sha256(text.encode()).hexdigest(), "bytes": len(text.encode())}]
    assert receipt["provider_calls"] == 0 and receipt["unresolved"]
    assert (tmp_path / other).read_text().startswith("不要读取我")


@pytest.mark.parametrize("entry,system", [("CMakeLists.txt", "cmake"), ("Makefile", "make"), ("configure.ac", "autotools")])
def test_existing_unambiguous_templates_are_exactly_preserved(tmp_path, entry, system):
    (tmp_path / entry).write_text("")
    assert selected_tool_actions(task(system), tmp_path) == observed_tool_actions(task(system), tmp_path)


@pytest.mark.parametrize("system", ["make", "autotools", "unknown"])
def test_cannot_use_cmake_without_matching_authoritative_task(tmp_path, system):
    (tmp_path / "CMakeLists.txt").write_text("")
    (tmp_path / "BUILD.bazel").write_text("")
    with pytest.raises(ToolPlanNeedsAgent):
        selected_tool_actions(task(system), tmp_path)


@pytest.mark.parametrize("kind", ["symlink", "directory", "oversized", "prebuilt"])
def test_selected_entry_still_rejects_unsafe_sources_and_preexisting_artifact(tmp_path, kind):
    (tmp_path / "BUILD.bazel").write_text("")
    entry = tmp_path / "CMakeLists.txt"
    if kind == "symlink":
        outside = tmp_path / "outside"
        outside.write_text("private")
        entry.symlink_to(outside)
    elif kind == "directory":
        entry.mkdir()
    else:
        entry.write_bytes(b"x" * (1024 * 1024 + 1) if kind == "oversized" else b"")
        if kind == "prebuilt":
            (tmp_path / "sample").write_text("do not accept")
    with pytest.raises(ToolPlanNeedsAgent):
        selected_tool_actions(task("cmake"), tmp_path)


def test_missing_cmake_and_same_basename_deliveries_still_abstain(tmp_path):
    (tmp_path / "BUILD.bazel").write_text("")
    with pytest.raises(ToolPlanNeedsAgent):
        selected_tool_actions(task("cmake"), tmp_path)
    (tmp_path / "CMakeLists.txt").write_text("")
    with pytest.raises(ToolPlanNeedsAgent):
        selected_tool_actions(task("cmake", ("a/libsame.a", "b/libsame.a")), tmp_path)
