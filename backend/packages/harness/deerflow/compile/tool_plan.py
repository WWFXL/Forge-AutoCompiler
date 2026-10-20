"""从源码入口生成有界初始方案；不读取正确配方，不调用模型或执行源码。"""

from __future__ import annotations

import hashlib
import json
import shlex
from pathlib import Path, PurePosixPath

from deerflow.compile.plan_agent import PlanProposal, PlanTask
from deerflow.compile.plan_workflow import BuildPlan, PlanContractError, PlanStep


class ToolPlanNeedsAgent(PlanContractError):
    """入口不明确或实际执行失败时，保留材料并交由后续Agent处理。"""


def artifact_stage_command(artifacts: tuple[str, ...], search_root: str) -> str:
    """只暂存名称唯一的真实编译文件；位置由执行时观察确定，不猜历史路径。"""
    # 脚本属于显式artifact_stage配方，clean replay同样从空目录执行它。
    script = """import json, shutil
from pathlib import Path
root = Path.cwd().resolve()
search = root / SEARCH_ROOT
artifacts = ARTIFACTS
selected = []
for target in artifacts:
    matches = []
    for path in search.rglob(Path(target).name):
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            continue
        with path.open('rb') as stream:
            magic = stream.read(8)
        if magic.startswith(b'\\x7fELF') or magic == b'!<arch>\\n':
            matches.append(path)
    if len(matches) != 1:
        raise RuntimeError('交付源必须唯一: ' + target + ' candidates=' + str(matches))
    selected.append((matches[0], Path('/artifacts') / target))
for source, destination in selected:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    shutil.copymode(source, destination)
print('FORGE_TOOL_PLAN_STAGED', json.dumps(artifacts))
"""
    script = script.replace("SEARCH_ROOT", repr(search_root)).replace("ARTIFACTS", repr(artifacts))
    return "python3 -c " + shlex.quote(script)


def generate_tool_plan(task: PlanTask, source_root: Path) -> tuple[BuildPlan, dict]:
    """仅支持单个根入口的三类模板；不确定性不会伪装成已解析依赖。"""
    root = source_root.resolve(strict=True)
    names = {p.name for p in root.iterdir()}
    inspected = []

    def read(name):
        path = root / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
            raise ToolPlanNeedsAgent("入口不是可读取的有界普通文件：" + name)
        data = path.read_bytes()
        inspected.append({"path": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
        return data.decode(errors="replace")

    auto = names & {"configure", "configure.ac", "configure.in"}
    make = names & {"Makefile", "makefile", "GNUmakefile"}
    candidates = ([] if "CMakeLists.txt" not in names else ["cmake"]) + (["autotools"] if auto else []) + (["make"] if make and not auto else [])
    if len(candidates) != 1 or names & {"meson.build", "build.ninja", "BUILD", "BUILD.bazel", "SConstruct", "xmake.lua"}:
        raise ToolPlanNeedsAgent("根构建入口缺失、冲突或超出三系统模板范围")
    system = candidates[0]
    if system != task.build_system:
        raise ToolPlanNeedsAgent("源码入口与任务登记构建系统不一致")
    if len({PurePosixPath(a).name for a in task.artifact_paths}) != len(task.artifact_paths):
        raise ToolPlanNeedsAgent("同名交付源需要显式定位")
    for target in task.artifact_paths:
        if target != PurePosixPath(target).as_posix() or PurePosixPath(target).is_absolute() or ".." in PurePosixPath(target).parts or not target or target == ".":
            raise ToolPlanNeedsAgent("交付路径不规范")
        # 已有同名文件可能是预编译产物或脚本，不能冒充本次生成结果。
        if any(root.rglob(PurePosixPath(target).name)):
            raise ToolPlanNeedsAgent("源码已有同名交付候选，需明确产物来源：" + target)
    steps = []

    def add(step_id, role, command, requires=()):
        steps.append(PlanStep(step_id=step_id, role=role, command=command, requires=requires, source="tool-plan-v1：单根入口通用模板与源码哈希收据", expected="命令真实成功；最终由固定完整测试和严格交付/replay判断"))

    if system == "cmake":
        read("CMakeLists.txt")
        # BUILD_TESTING是CTest约定；项目自定义开关本版不猜测，固定测试仍可拒绝。
        add("configure", "configure", "cmake -S . -B build -DBUILD_TESTING=ON")
        add("build", "build", "cmake --build build --parallel 2", ("configure",))
        search_root = "build"
    elif system == "make":
        if len(make) != 1:
            raise ToolPlanNeedsAgent("多个Make入口需要显式选择")
        read(next(iter(make)))
        add("build", "build", "make -j2")
        search_root = "."
    else:
        if "configure" in names:
            read("configure")
        else:
            read("configure.ac" if "configure.ac" in names else "configure.in")
            add("bootstrap", "configure", "autoreconf -fi")
        add("configure", "configure", "sh ./configure", ("bootstrap",) if steps else ())
        add("build", "build", "make -j2", ("configure",))
        search_root = "."
    # 固定验证由系统逐字段装入，避免模型重写复杂引号；不读取其命令来推断配置。
    steps.extend(task.verification_steps)
    add("stage", "artifact_stage", artifact_stage_command(task.artifact_paths, search_root), tuple(s.step_id for s in task.verification_steps))
    plan = task.materialize(PlanProposal(reason="单根构建系统模板生成候选；未承诺依赖齐全或配置适配", steps=steps), revision=1)
    receipt = {
        "generator": "tool-plan-v1",
        "build_system": system,
        "source_reads": inspected,
        "root_entries": sorted(names),
        "fixed_verification_sha256": hashlib.sha256(json.dumps([s.model_dump(mode="json") for s in task.verification_steps], sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        "plan_sha256": plan.fingerprint(),
        "provider_calls": 0,
        "unresolved": ["镜像中的外部依赖是否齐全", "默认配置是否满足全部固定测试", "编译后交付源是否唯一"],
    }
    return plan, receipt
