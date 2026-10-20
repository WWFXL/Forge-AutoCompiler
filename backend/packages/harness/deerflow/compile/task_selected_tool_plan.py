"""显式任务指定CMake时接纳多入口仓库；不猜项目参数或外部依赖。"""

from __future__ import annotations

import hashlib
from pathlib import PurePosixPath

from deerflow.compile.tool_plan import ToolPlanNeedsAgent
from deerflow.compile.unified_plan_equivalent_observed import ObservedBuildAction, ObservedBuildActions, assemble_observed, observed_tool_actions

ALTERNATIVE_ENTRIES = frozenset({"Makefile", "makefile", "GNUmakefile", "configure", "configure.ac", "configure.in", "meson.build", "build.ninja", "BUILD", "BUILD.bazel", "SConstruct", "xmake.lua"})


def selected_tool_actions(task, source_root):
    """只改变存在其他入口时的系统选择；其余旧准入与固定装配保持。"""
    root = source_root.resolve(strict=True)
    names = {p.name for p in root.iterdir()}
    alternatives = sorted(names & ALTERNATIVE_ENTRIES)
    if task.build_system != "cmake" or "CMakeLists.txt" not in names or not alternatives:
        return observed_tool_actions(task, root)
    path = root / "CMakeLists.txt"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ToolPlanNeedsAgent("任务指定的CMake入口不是有界普通文件")
    targets = tuple(task.artifact_paths)
    if len({PurePosixPath(a).name for a in targets}) != len(targets):
        raise ToolPlanNeedsAgent("同名交付源需要显式定位")
    for target in targets:
        value = PurePosixPath(target)
        if not target or target == "." or value.as_posix() != target or value.is_absolute() or ".." in value.parts:
            raise ToolPlanNeedsAgent("交付路径不规范")
        if any(root.rglob(value.name)):
            raise ToolPlanNeedsAgent("源码已有同名交付候选，需明确产物来源：" + target)
    raw = path.read_bytes()
    source = "task-selected-tool-plan-v1：权威任务指定cmake；只核验有界根入口，不执行或解析源码指令"
    actions = ObservedBuildActions(
        reason="按显式任务选择CMake，不因并存其他入口猜测构建系统；依赖和配置适用性由真实执行及固定测试判定",
        steps=[
            ObservedBuildAction(step_id="configure", role="configure", command="cmake -S . -B build -DBUILD_TESTING=ON", source=source, expected="真实配置成功，默认功能由固定测试核验"),
            ObservedBuildAction(step_id="build", role="build", command="cmake --build build --parallel 2", requires=("configure",), source=source, expected="真实编译成功；完整原测试、精确交付和replay仍需独立通过"),
        ],
    )
    receipt = {
        "generator": "task-selected-tool-plan-v1",
        "selection_authority": "task.build_system",
        "build_system": "cmake",
        "alternative_entries": alternatives,
        "root_entries": sorted(names),
        "source_reads": [{"path": "CMakeLists.txt", "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}],
        "plan_sha256": assemble_observed(task, actions, revision=1).fingerprint(),
        "provider_calls": 0,
        "unresolved": ["外部依赖", "项目特定配置与测试功能", "交付源是否唯一"],
    }
    return actions, receipt
