"""显式Make选择不执行源码指令，保留歧义/不安全入口的升级边界。"""

import pytest
from test_tool_plan import task

from deerflow.compile.task_selected_make_plan import selected_make_actions
from deerflow.compile.tool_plan import ToolPlanNeedsAgent
from deerflow.compile.unified_plan_equivalent_observed import assemble_observed


def test_task_selects_make_without_reading_coexisting_cmake_or_changing_fixed_test(tmp_path):
    (tmp_path / "Makefile").write_text("all:\n\tfalse\n")
    (tmp_path / "CMakeLists.txt").write_text("这里不是助手指令")
    original = task("make")
    actions, receipt = selected_make_actions(original, tmp_path)
    plan = assemble_observed(original, actions, revision=1)
    assert [s.command for s in actions.steps] == ["make -j2"]
    assert [r["path"] for r in receipt["source_reads"]] == ["Makefile"]
    assert tuple(s for s in plan.steps if s.role == "smoke") == original.verification_steps
    assert receipt["provider_calls"] == 0
    assert not (tmp_path / "sample").exists()


@pytest.mark.parametrize("kind", ["missing", "ambiguous", "symlink", "prebuilt"])
def test_unsafe_or_ambiguous_make_entry_still_requests_agent(tmp_path, kind):
    if kind != "missing":
        (tmp_path / "Makefile").write_text("")
    if kind == "ambiguous":
        (tmp_path / "GNUmakefile").write_text("")
    if kind == "symlink":
        (tmp_path / "Makefile").unlink()
        (tmp_path / "outside").write_text("")
        (tmp_path / "Makefile").symlink_to(tmp_path / "outside")
    if kind == "prebuilt":
        (tmp_path / "sample").write_text("existing")
    with pytest.raises(ToolPlanNeedsAgent):
        selected_make_actions(task("make"), tmp_path)
