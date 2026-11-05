"""读取已闭合真实轨迹生成阶段—事实—动作案例；原运行重叠，不增加实验分母。"""

from __future__ import annotations
import hashlib
import json
import sys
from pathlib import Path

BASE = Path("/home/yiwei/.codex/outputs")
SPECS = (
    dict(
        case="tool_submit_and_reset_limit",
        identity="cpp-build-main-system-comparison-flash-v1",
        slot=BASE
        / "forge-main-system-comparison-flash-v1/slot-43-libsrtp-strong_tool_agent",
        interpretation="configure/build均exit0，但submit引用失败diagnostic作为supporting而被拒；随后reset内嵌源码清单超过本机单参数长度，docker启动前E2BIG",
        outcome="9请求/0.0293838美元，主产物独立验收及后层未观察，cleanup成功；原未完成保留，不称编译器失败",
    ),
    dict(
        case="local_failure_to_agent",
        identity="cpp-build-main-system-comparison-flash-v1",
        slot=BASE
        / "forge-main-system-comparison-flash-v1/slot-31-double-conversion-forge",
        interpretation="规则升级下载超时，转Flash修订；SCons命令exit0但CMake配置观察未知，继续交接，最后回到CMake成功",
        outcome="8请求（1初始/7恢复），11条命令，709.12秒，主任务/交付/replay通过；失败与被拒进展不进入最终方案",
    ),
    dict(
        case="normal_workflow",
        identity="cpp-build-main-system-comparison-flash-v1",
        slot=BASE / "forge-main-system-comparison-flash-v1/slot-01-jsoncpp-forge",
        interpretation="阶段成功记录与有效主库支持继续；正常路径没有路由请求",
        outcome="新主任务、交付、重放通过",
    ),
    dict(
        case="exact_recipe",
        identity="cpp-build-main-system-comparison-flash-v1",
        slot=BASE
        / "forge-main-system-comparison-flash-v1/slot-02-jsoncpp-forge_experience",
        interpretation="完整公开任务精确命中，跳过初始规划；不是复用二进制",
        outcome="0模型，实际重建及新主任务/交付/重放通过",
    ),
    dict(
        case="prerequisite_version",
        identity="cpp-build-main-system-comparison-flash-v1",
        slot=BASE
        / "forge-main-system-comparison-flash-v1/slot-04-double-conversion-forge_experience",
        interpretation="configure退出1且日志实际工具3.28.3低于作者3.29；规则选择upgrade_cmake",
        outcome="实际安装后配置/构建，新主任务/交付/重放通过；非Jev标签",
    ),
    dict(
        case="command_role_gap",
        identity="cpp-build-two-level-system-comparison-flash-v1",
        slot=BASE
        / "forge-two-level-system-comparison-flash-v1/slot-04-double-conversion-forge_experience",
        interpretation="变量形式CMake构建exit0，handoff主组件passed，但旧角色识别未接受；不是缺产物",
        outcome="旧运行未完整，后层未观察；后续共同修复不回填旧终态",
    ),
    dict(
        case="tests_not_registered",
        identity="cpp-build-two-level-system-comparison-flash-v1",
        slot=BASE
        / "forge-two-level-system-comparison-flash-v1/slot-05-double-conversion-strong_tool_agent",
        interpretation="主库通过，但默认未开启BUILD_TESTING，CTest零测试；任务/测试准备衔接问题",
        outcome="旧full_completed=false，主构建/交付/构建重放通过；新任务范围不重标旧结果",
    ),
    dict(
        case="planning_metadata_rejection",
        identity="cpp-build-simple-project-reuse-flash-v1",
        slot=BASE
        / "forge-base-experience-comparison-v1/reuse/slot-08-highwayhash-forge",
        interpretation="已经给出make动作，非核心diagnostic_paths schema拒绝并纠正仍不合法；不是空规划",
        outcome="规划阶段停止，编译/测试/重放未观察，计费保留；后续共同修复单独记录",
    ),
)


def load(path):
    return json.loads(path.read_text())


def pointer(path):
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def main(output):
    cases = []
    for spec in SPECS:
        folder = spec["slot"]
        result = load(folder / "result.json")
        evidence = [pointer(folder / "result.json")]
        commands = []
        for path in folder.glob(".compile-sessions/*/*/session.json"):
            evidence.append(pointer(path))
            for record in load(path).get("commands", []):
                command = record.get("command", "")
                # 自动生成的重置清单留在原日志；案例只留有限命令预览和完整哈希。
                row = {
                    k: record.get(k)
                    for k in (
                        "command_id",
                        "role",
                        "exit_code",
                        "timed_out",
                        "duration_seconds",
                        "workdir",
                    )
                }
                row.update(
                    command_preview=command[:500],
                    command_sha256=hashlib.sha256(command.encode()).hexdigest(),
                )
                log = Path(record.get("log_path") or "/nonexistent")
                if log.is_file():
                    row["log"] = pointer(log)
                    row["output_tail"] = log.read_text(errors="replace")[-1200:]
                commands.append(row)
        decisions = []
        for path in sorted((folder / "state-routing").glob("decision-*.json")):
            decisions.append(load(path))
            evidence.append(pointer(path))
        handoffs = []
        for path in sorted(
            folder.glob(".compile-sessions/*/*/build-plan/handoff-*.json")
        ):
            value = load(path)
            handoffs.append(
                {
                    k: value.get(k)
                    for k in (
                        "step_id",
                        "reason",
                        "configuration_state",
                        "primary_components",
                    )
                }
            )
            evidence.append(pointer(path))
        cases.append(
            dict(
                case=spec["case"],
                identity=spec["identity"],
                overlap="same original runs; not new sample",
                interpretation=spec["interpretation"],
                outcome=spec["outcome"],
                result={
                    k: result.get(k)
                    for k in (
                        "status",
                        "layers",
                        "source_unchanged",
                        "cleanup",
                        "error_type",
                        "error",
                        "agent_usage",
                    )
                },
                decisions=decisions,
                handoffs=handoffs,
                commands=commands,
                evidence=evidence,
            )
        )
    output.write_text(
        json.dumps(
            dict(
                kind="derived_case_analysis",
                additional_provider_calls=0,
                additional_runs=0,
                cases=cases,
            ),
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    print(
        json.dumps(
            dict(cases=len(cases), provider_calls=0, new_runs=0), ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]))
