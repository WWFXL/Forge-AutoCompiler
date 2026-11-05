"""从既有分析解释费用、单项目时间集中及工具异常；不启动实验。"""

import hashlib
import json
import sys
import tarfile
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend/packages/harness"))
from deerflow.compile.simple_build_runtime import generated_reset_step  # noqa: E402

HERE = Path(__file__).parent
RAW = Path("/home/yiwei/.codex/outputs/forge-main-system-comparison-flash-v1")


def read(p):
    return json.loads(p.read_text())


def pointer(p):
    return dict(path=str(p), sha256=hashlib.sha256(p.read_bytes()).hexdigest())


def main():
    summary = read(HERE / "summary.json")
    by_project = read(HERE / "by-project.json")
    contexts = read(HERE / "experience-contexts.json")
    groups = summary["summary"]["all"]
    before, after = groups["forge"], groups["forge_experience"]
    project = by_project["double-conversion"]
    time_gap = before["total_wall_seconds"] - after["total_wall_seconds"]
    project_gap = (
        project["forge"]["wall_seconds"] - project["forge_experience"]["wall_seconds"]
    )
    sensitivity = {
        method: dict(
            observed=sum(
                r[method]["observed"]
                for name, r in by_project.items()
                if name != "double-conversion"
            ),
            requests=sum(
                r[method]["requests"]
                for name, r in by_project.items()
                if name != "double-conversion"
            ),
            estimated_cost_usd=str(
                sum(
                    (
                        Decimal(r[method]["estimated_cost_usd"])
                        for name, r in by_project.items()
                        if name != "double-conversion"
                    ),
                    Decimal(0),
                )
            ),
            wall_seconds=sum(
                r[method]["wall_seconds"]
                for name, r in by_project.items()
                if name != "double-conversion"
            ),
        )
        for method in groups
    }
    folder = RAW / "slot-43-libsrtp-strong_tool_agent"
    result = read(folder / "result.json")
    sessions = list(folder.glob(".compile-sessions/*/*/session.json"))
    assert len(sessions) == 1
    session = read(sessions[0])
    fixture = read(ROOT / "benchmarks/fixtures/main-system-comparison-v1/tasks.json")
    source = next(x for x in fixture["projects"] if x["name"] == "libsrtp")
    with tarfile.open(source["source_archive"]) as archive:
        names = [
            m.name.removeprefix("./")
            for m in archive.getmembers()
            if m.isfile() or m.issym()
        ]
    command = generated_reset_step(dict.fromkeys(names)).command
    report = dict(
        interpretation="事后敏感性与原因解释；全部54槽主表不改，不增加效果分母",
        runtime_inventory=summary["inventory"],
        cost_scenario=dict(
            online_experience_usd=after["estimated_cost_usd"],
            historical_recipe_acquisition_usd="0.0150984",
            historical_bank_creation_usd="0.095129",
            total_if_all_historical_costs_assigned_once_usd=str(
                Decimal(after["estimated_cost_usd"])
                + Decimal("0.0150984")
                + Decimal("0.095129")
            ),
            newly_paid_historical_costs=False,
            bank_preparation_wall_time="not_independently_measured; not_imputed_as_zero",
        ),
        time_concentration=dict(
            all_base_minus_experience_seconds=time_gap,
            double_conversion_base_minus_experience_seconds=project_gap,
            fraction_of_total_difference=project_gap / time_gap,
            caution="该集中性不证明差值来自经验；包含下载延迟和观察器对构建入口切换的边界",
        ),
        sensitivity_excluding_double_conversion=sensitivity,
        retrieval=dict(
            tasks=len(contexts),
            empty=sum(x["context"].get("abstained", False) for x in contexts),
            context_bytes=sum(x["context"].get("bytes", 0) for x in contexts),
            task_internal_refreshes=0,
            caution="检索相关性不等于前提成立或实际采用；double-conversion条目主要是测试/依赖包经验，不是CMake版本升级经验",
        ),
        tool_failure=dict(
            slot=43,
            project="libsrtp",
            error_type=result["error_type"],
            error=result["error"],
            main_task_completed=False,
            independent_primary_validation="unobserved",
            successful_configure_and_build=[
                {k: c[k] for k in ("command_id", "role", "command", "exit_code")}
                for c in session["commands"]
                if c["role"] in {"configure", "build"} and c["exit_code"] == 0
            ],
            submit_rejection="supporting_command_id指定失败diagnostic，且不在所给recipe中；不是实际build命令ID",
            reset_source_paths=len(names),
            reset_command_utf8_bytes=len(command.encode()),
            mechanism="保护源码清单内嵌python3 -c，再通过docker exec参数传入；153264字节超过本机单参数约131072字节限制，进程启动前E2BIG",
            evidence=[
                pointer(folder / "result.json"),
                pointer(folder / "agent/events.jsonl"),
                pointer(sessions[0]),
                pointer(Path(source["source_archive"])),
            ],
            limits="make返回0及日志中库路径不代替独立主产物验收；源码终态未观察，cleanup成功；不修后补跑旧槽，不作模型编译能力劣势",
        ),
    )
    (HERE / "explanation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "time_fraction": project_gap / time_gap,
                "reset_bytes": len(command.encode()),
                "retrieval_tasks": len(contexts),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
