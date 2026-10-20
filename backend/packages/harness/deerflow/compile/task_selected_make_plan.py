"""任务明确指定Make时接纳唯一根Make入口；其他系统沿用已资格接口。"""

from __future__ import annotations

import hashlib
from pathlib import PurePosixPath

from deerflow.compile.task_selected_tool_plan import selected_tool_actions
from deerflow.compile.tool_plan import ToolPlanNeedsAgent
from deerflow.compile.unified_plan_equivalent_observed import ObservedBuildAction, ObservedBuildActions, assemble_observed


def selected_make_actions(task, source_root):
    if task.build_system != "make":
        return selected_tool_actions(task, source_root)
    root = source_root.resolve(strict=True)
    names = {p.name for p in root.iterdir()}
    entries = names & {"Makefile", "makefile", "GNUmakefile"}
    if len(entries) != 1:
        raise ToolPlanNeedsAgent("任务指定Make但缺少唯一根入口")
    entry = next(iter(entries))
    path = root / entry
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ToolPlanNeedsAgent("Make入口不是有界普通文件")
    if len({PurePosixPath(a).name for a in task.artifact_paths}) != len(task.artifact_paths):
        raise ToolPlanNeedsAgent("同名交付需要显式定位")
    for target in task.artifact_paths:
        value = PurePosixPath(target)
        if not target or target == "." or value.as_posix() != target or value.is_absolute() or ".." in value.parts or any(root.rglob(value.name)):
            raise ToolPlanNeedsAgent("交付路径不规范或源码已有同名候选")
    raw = path.read_bytes()
    actions = ObservedBuildActions(
        reason="权威任务选择唯一Make入口；不解析裁判或猜依赖/目标参数",
        steps=[ObservedBuildAction(step_id="build", role="build", command="make -j2", source="task-selected-make-v1：显式task.build_system与普通根入口", expected="默认编译真实通过；完整原测试/交付/replay仍独立核验")],
    )
    return actions, dict(
        generator="task-selected-make-v1",
        selection_authority="task.build_system",
        build_system="make",
        root_entries=sorted(names),
        source_reads=[dict(path=entry, sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))],
        plan_sha256=assemble_observed(task, actions, revision=1).fingerprint(),
        provider_calls=0,
        unresolved=["外部依赖", "默认目标适用性", "完整测试", "唯一交付源"],
    )
