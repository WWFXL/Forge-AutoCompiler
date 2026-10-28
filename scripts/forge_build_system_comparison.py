#!/usr/bin/env python3
"""统一任务下的三系统比较；免费准备不读取凭据，旧实现与证据保持只读。"""

from __future__ import annotations

import argparse
import copy
import json
import re
import signal
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import forge_build_goal_state_ablation as component
import forge_cxx_current_reference as cxx
from forge_build_common_harness import common_harness_interfaces
from langchain_core.messages import SystemMessage

from deerflow.compile.goal_state import GoalStateWorkflow, configuration_goals, goal_state_planner
from deerflow.compile.operation_window import OperationWindow

base, flash, replication = component.base, component.flash, component.paired.replication
ROOT = base.ROOT
IDENTITY = "cpp-build-unified-system-comparison-flash-v1"
MANIFEST = ROOT / "benchmarks/manifests" / (IDENTITY + ".json")
PREREGISTRATION = "benchmarks/preregistrations/" + IDENTITY + ".md"
PARENTS = ("cpp-build-strategy-replication-v1", "cpp-build-library-strategy-comparison-flash-v1")
PROJECTS = (*replication.PROJECTS, "rang", "ELFIO")
METHODS = ("forge_state_workflow", "strong_tool_agent", "cxxcrafter_community_reference")
ENV = {"CMAKE_BUILD_PARALLEL_LEVEL": "2", "CTEST_PARALLEL_LEVEL": "2", "MAKEFLAGS": "-j2"}
SLOT_SECONDS, REPLAY_SECONDS, CLEANUP_SECONDS = 2700, 1200, 300


def schedule():
    return [dict(project=name, repetition=repetition, method=METHODS[index]) for repetition in (1, 2) for position, name in enumerate(PROJECTS) for index in base.ORDERS[(position + 3 * (repetition - 1)) % 6]]


def profile_step():
    return dict(
        step_id="build-profile",
        role="smoke",
        workdir="/workspace/repo",
        requires=["build"],
        diagnostic_paths=[],
        command="python3 -c \"from pathlib import Path; assert 'CMAKE_BUILD_TYPE:STRING=Release' in Path('build/CMakeCache.txt').read_text().splitlines(); print('FORGE_BUILD_PROFILE_RELEASE')\"",
        required_output=["FORGE_BUILD_PROFILE_RELEASE"],
        source="三系统共同CMake Release任务约束；不修改作者源码和测试",
        expected="实际配置为Release",
    )


def common_task(item):
    """三方收到同一完整任务JSON，不能只给Forge长脚本的引用。"""
    task = base.PlanTask.model_validate(item["task"])
    return dict(
        task=task.model_dump(mode="json"),
        common_test_preparation=item["common_test_preparation"],
        persistent_configuration_goals=[asdict(g) for g in configuration_goals(task)],
        build_profile="CMake必须使用build目录和Release；Make/Autotools保持作者默认优化参数，禁止自行添加/覆盖优化选项。",
        resources=dict(parallel_jobs=2, environment=ENV, network="compile_network_wwf_v1", user="image_default_root", package_install=True),
        rules="遵循指定构建系统；原源码、原测试和已有输入不可改；允许新增标准生成文件。完整测试/精确交付/同镜像干净重放均须通过。不得伪造HAVE_*依赖探测结果。",
    )


def candidate_for():
    parents = [base.load(ROOT / "benchmarks/manifests" / (name + ".json")) for name in PARENTS]
    items = {item["name"]: copy.deepcopy(item) for parent in parents for item in parent["projects"]}
    projects = [items[name] for name in PROJECTS]
    for item in projects:
        if item["task"]["build_system"] == "cmake":
            item["task"]["verification_steps"].insert(0, profile_step())
        item["common_test_preparation"]["system_comparison_build_profile"] = common_task(item)["build_profile"]
    candidate = copy.deepcopy(parents[0])
    candidate.update(
        identity=IDENTITY,
        issue=640,
        kind="complete_system_comparison_development_projects",
        holdout=False,
        projects=projects,
        schedule=schedule(),
        provider=flash.PROVIDER,
        pricing=flash.PRICING,
        parent_manifests=[dict(path="benchmarks/manifests/" + name + ".json", sha256=base.digest(ROOT / "benchmarks/manifests" / (name + ".json"))) for name in PARENTS],
        baseline=base.load(cxx.MANIFEST)["baseline"],
        source_index_contracts={name: copy.deepcopy(next(parent["source_index_contracts"][name] for parent in parents if name in parent["source_index_contracts"])) for name in PROJECTS},
        exposure=[
            dict(project=i["name"], family=i["name"], historical_roles="参考构建、开发、策略比较；前三个CMake任务还用于配置组件开发" if i["name"] in component.PROJECTS else "参考构建、开发、策略比较", holdout=False) for i in projects
        ],
        stage_max_cost_usd="10.00",
        launch_state="prepared_requires_new_budget_and_time_authorization",
        timing_policy=dict(per_slot_seconds=SLOT_SECONDS, new_slot_reserve_seconds=SLOT_SECONDS, replay_seconds=REPLAY_SECONDS, cleanup_reserve_seconds=CLEANUP_SECONDS, request_reserve_seconds=600, http_timeout_seconds=240),
        comparison_boundary="完整系统比较，非规划或状态单变量因果；CXX社区原生Parser/Generator/Modifier/Judge保留，外部验收不回送其Modifier；全部项目已见，重复不当独立项目。",
        methods={METHODS[0]: "共同任务＋模型规划＋GoalStateWorkflow＋有依据的BOOL修订/失败Agent", METHODS[1]: "共同任务＋原强工具Agent，不注入Workflow状态动作", METHODS[2]: "既有社区版原生循环＋共同任务＋固定资源＋共同外部验收"},
    )
    candidate["runtime"] = {**candidate["runtime"], "new_slot_reserve_seconds": SLOT_SECONDS}
    candidate["components"] = {**parents[0]["components"], **parents[1]["components"], **base.load(component.MANIFEST)["components"], **base.load(cxx.MANIFEST)["components"]}
    for name in ("scripts/forge_build_system_comparison.py", PREREGISTRATION):
        candidate["components"][name] = base.digest(ROOT / name)
    return candidate


def validate(candidate):
    if candidate != candidate_for():
        raise base.PlanContractError("新比较的任务、顺序、源码或组件变化")
    for name, expected in candidate["components"].items():
        if base.digest(ROOT / name) != expected:
            raise base.PlanContractError("冻结组件变化：" + name)
    for item in candidate["projects"]:
        if base.digest(Path(item["source_archive"])) != item["task"]["source_archive_sha256"]:
            raise base.PlanContractError("原归档变化")
        base.PlanTask.model_validate(item["task"])
    for name, expected in candidate["baseline"]["files"].items():
        if base.digest(Path(candidate["baseline"]["path"]) / name) != expected:
            raise base.PlanContractError("CXX社区版快照变化")


class CommonTaskMeter(component.CommonFlashMeter):
    def __init__(self, *args, item, **kwargs):
        super().__init__(*args, **kwargs)
        self.public_task = common_task(item)
        self.ledger.save("common-system-task.json", self.public_task)

    def wrap_model_call(self, request, handler):
        system = request.system_message
        text = "\n共同完整任务（对所有系统相同，优先于示例）：\n" + json.dumps(self.public_task, ensure_ascii=False)
        return super().wrap_model_call(request.override(system_message=SystemMessage(content=(system.content if system else "") + text)), handler)


def run_forge(protocol, slot, folder, model):
    item = next(i for i in protocol["projects"] if i["name"] == slot["project"])
    enhanced = slot["method"] == METHODS[0]
    with common_harness_interfaces():
        original = base.observed_module.observed_planner

        def planner(*args, **kwargs):
            selected = original(*args, **kwargs)
            return goal_state_planner(selected) if enhanced else selected

        with (
            patch.object(base, "PreparationMeter", lambda *a, **kw: CommonTaskMeter(*a, item=item, **kw)),
            patch.object(base, "execution_window", component.bounded.execution_window),
            patch.object(base.prepared_module, "PreparedWorkflow", GoalStateWorkflow if enhanced else base.prepared_module.PreparedWorkflow),
            patch.object(base.observed_module, "observed_planner", planner),
        ):
            row = replication.run_slot(protocol=protocol, slot={**slot, "method": "model_plan_workflow" if enhanced else "strong_tool_agent"}, root=folder, model=model)
    return {**row, **slot}


class CommonSDKMeter(cxx.SDKMeter):
    """社区原生全部模型请求计费，并采用与Forge相同的请求准入。"""

    def __init__(self, *args, public_task, deadline, **kwargs):
        super().__init__(*args, **kwargs)
        self.public_task, self.window = public_task, OperationWindow(deadline)

    def request(self, call, kwargs):
        self.window.request()
        if self.requests >= 145 or self.input + self.output >= 1_000_000:
            raise cxx.StopPaid("共同请求或Token上界")
        # 所有原生Parser/Generator/Modifier/Judge轮均收到共同任务，且计入其上下文费用。
        messages = [dict(role="system", content="共同完整任务，优先于示例：" + json.dumps(self.public_task, ensure_ascii=False)), *kwargs.get("messages", [])]
        # 复用已验证的原始响应/费用保留；其900秒检查映射为共同600秒。
        with patch.object(cxx, "remaining", lambda: self.window.remaining() + 300):
            try:
                return super().request(call, {**kwargs, "messages": messages})
            except BaseException:
                if self.requests and not (self.folder / f"request-{self.requests:03d}.response.json").exists():
                    self.unknown = max(self.unknown, 1)
                    self.stopped = True
                cxx.save(self.folder / "usage.json", self.summary())
                raise


def resource_dockerfile(text, image):
    """只固定镜像和资源，不替基线生成构建方案。"""
    rows = text.splitlines()
    positions = [index for index, line in enumerate(rows) if re.match(r"\s*FROM\s", line, re.I)]
    if len(positions) != 1 or rows[positions[0]].split()[1] not in ("autocompiler:gcc13", image):
        raise base.PlanContractError("社区版必须使用同一固定镜像，当前不支持多阶段镜像")
    rows[positions[0]] = "FROM " + image
    marker = "ENV " + " ".join(f"{key}={value}" for key, value in ENV.items())
    if marker not in rows:
        rows.insert(positions[0] + 1, marker)
    return "\n".join(rows) + "\n"


def run_cxx(protocol, slot, folder, available):
    item = next(i for i in protocol["projects"] if i["name"] == slot["project"])
    # 仅复用既有社区安装依赖，源码始终使用前一轮固定快照。
    sdk = next(cxx.BASELINE.glob(".venv/lib/python*/site-packages/docker/__init__.py"))
    if str(sdk.parents[1]) not in sys.path:
        sys.path.append(str(sdk.parents[1]))
    import docker

    original_build, original_command = docker.APIClient.build, cxx.command
    window, builds = OperationWindow(protocol["deadline_utc"]), []

    def build(client, **kwargs):
        replay = kwargs.get("tag", "").endswith("-replay")
        if replay:
            window.replay(REPLAY_SECONDS)
        path = Path(kwargs["path"]) / "Dockerfile"
        native = path.read_text()
        effective = resource_dockerfile(native, item["task"]["image_id"])
        path.write_text(effective)
        builds.append(dict(replay=replay, native=native, effective=effective))
        cxx.save(folder / "resource-adaptations.json", builds)
        yield from original_build(client, **{**kwargs, "network_mode": "compile_network_wwf_v1"})

    def command(argv, target, name, timeout=600):
        argv = list(argv)
        if argv[:2] == ["docker", "exec"]:
            argv[2:2] = [x for key, value in ENV.items() for x in ("-e", f"{key}={value}")]
        elif argv[:2] == ["docker", "run"]:
            argv[2:2] = ["--network", "compile_network_wwf_v1"]
        return original_command(argv, target, name, timeout)

    with (
        patch.object(cxx, "DEADLINE", protocol["deadline_utc"]),
        patch.object(cxx, "SDKMeter", lambda target, ignored: CommonSDKMeter(target, min(Decimal("3.00"), available), public_task=common_task(item), deadline=protocol["deadline_utc"])),
        patch.object(cxx, "command", command),
        patch.object(docker.APIClient, "build", build),
    ):
        row = cxx.run_cxx(protocol, item, folder, available)
    return {**row, **slot, "common_task_sha256": base.digest(folder / "common-system-task.json") if (folder / "common-system-task.json").exists() else None}


def run_slot(*, protocol, slot, root, model):
    selected = {**protocol, "deadline_utc": min(datetime.fromisoformat(protocol["deadline_utc"]), datetime.now(UTC) + timedelta(seconds=SLOT_SECONDS)).isoformat()}
    item = next(i for i in protocol["projects"] if i["name"] == slot["project"])
    base.write_json(root / "common-system-task.json", common_task(item))
    base.write_json(root / "slot-window.json", dict(global_deadline=protocol["deadline_utc"], deadline_utc=selected["deadline_utc"]))
    started = time.monotonic()
    old_alarm = signal.getsignal(signal.SIGALRM)

    def stop(signum, frame):
        raise base.PlanContractError("operation_window:slot截止，预留清理")

    signal.signal(signal.SIGALRM, stop)
    signal.setitimer(signal.ITIMER_REAL, max(1, OperationWindow(selected["deadline_utc"]).remaining() - CLEANUP_SECONDS))
    try:
        row = run_cxx(selected, slot, root, Decimal(protocol["stage_max_cost_usd"])) if slot["method"] == METHODS[2] else run_forge(selected, slot, root, model)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_alarm)
    return {**row, "arm_total_wall_seconds": time.monotonic() - started}


def execute(protocol, root, model, rows):
    for index, slot in enumerate(protocol["schedule"], 1):
        if component.bounded.STOP_REQUESTED:
            return "operator_stop"
        if OperationWindow(protocol["deadline_utc"]).remaining() < SLOT_SECONDS:
            return "new_slot_time_reservation"
        if sum(base.charges(rows)) + Decimal("3.00") > Decimal(protocol["stage_max_cost_usd"]):
            return "stage_cost_reservation"
        folder = root / f"slot-{index}"
        folder.mkdir()
        try:
            row = run_slot(protocol=protocol, slot=slot, root=folder, model=model)
        except Exception as exc:
            # 异常退出也保留已发请求费用，禁止把未返回的槽变成零费用未观察。
            paths = list(folder.glob("*/agent/usage.json")) + list(folder.glob("agent/usage.json"))
            usage = base.load(paths[0]) if len(paths) == 1 else dict(model_requests=0, estimated_cost_usd_completed_responses="0", unknown_usage_requests=1)
            row = {**slot, "strict_completed": False, "agent_usage": usage, "cleanup": dict(succeeded=False), "error_class": type(exc).__name__, "error_message": str(exc)[:1500], "arm_total_wall_seconds": None}
        rows.append(row)
        base.write_json(root / f"progress-{index}.json", row)
        print(json.dumps(dict(slot=index, project=slot["project"], method=slot["method"], completed=row["strict_completed"], usage=row["agent_usage"]), ensure_ascii=False), flush=True)
        if row["agent_usage"]["unknown_usage_requests"] or row.get("provider_stop") or not row["cleanup"]["succeeded"]:
            return "unknown_usage_provider_or_cleanup_stop"
        if Decimal(str(row["agent_usage"]["estimated_cost_usd_completed_responses"])) > Decimal("3.00"):
            return "cost_contract_violation"
        if any(json.loads(line)["event"] == "model.identity_mismatch" for path in folder.glob("*/agent/events.jsonl") for line in path.read_text().splitlines()):
            return "provider_identity_mismatch"
    return None


def analyze(root):
    result = base.load(root / "result.json")
    summary = {}
    for method in METHODS:
        rows = [row for row in result["rows"] if row["method"] == method]
        summary[method] = dict(
            observed=len(rows),
            planned=16,
            complete=sum(row["strict_completed"] for row in rows),
            unobserved=16 - len(rows),
            requests=sum(row["agent_usage"].get("model_requests", row["agent_usage"].get("provider_requests", 0)) for row in rows),
            known_cost_usd=str(sum((Decimal(str(row["agent_usage"]["estimated_cost_usd_completed_responses"])) for row in rows), Decimal(0))),
            slot_seconds=sum(row["arm_total_wall_seconds"] or 0 for row in rows),
            missing_timing=sum(row["arm_total_wall_seconds"] is None for row in rows),
        )
    return dict(
        identity=result["identity"],
        summary=summary,
        unobserved_schedule=result["unobserved_schedule"],
        stop_reason=result["stop_reason"],
        boundary="全48槽为主表；未完成与时间截断需结合原轨迹分类；共同完成配对只作辅助效率分析；非单组件因果。",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--check-prepared", action="store_true")
    parser.add_argument("--analyze", type=Path)
    args, remaining = parser.parse_known_args()
    if args.prepare or args.check_prepared:
        candidate = candidate_for() if args.prepare else base.load(MANIFEST)
        validate(candidate)
        if args.prepare:
            if MANIFEST.exists():
                raise base.PlanContractError("不覆盖已固定候选")
            base.write_json(MANIFEST, candidate)
        print(json.dumps(dict(valid=True, slots=len(candidate["schedule"]), credentials_read=False, provider_calls=0)))
        return 0
    if args.analyze:
        print(json.dumps(analyze(args.analyze), ensure_ascii=False, indent=2))
        return 0
    signal.signal(signal.SIGINT, component.bounded.request_stop)
    with patch.object(sys, "argv", [sys.argv[0], *remaining]), patch.object(base, "PROVIDER", flash.PROVIDER), patch.object(base, "validate", validate), patch.object(base, "execute", execute):
        return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
