#!/usr/bin/env python3
"""新身份共同测试准备/分层时间准入；先开发探针，再固定跨项目三策略比较。"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import time
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/packages/harness"), str(ROOT / "scripts")]

import forge_build_prepared_arm as prepared_module  # noqa: E402
import forge_build_rtorrent_common as common_module  # noqa: E402
from forge_build_cxx_comparison import classified_prepared_arm  # noqa: E402
from forge_build_native_round import run_strategy as native_run_strategy  # noqa: E402
from forge_build_rtorrent_fixed_contract import (
    FixedVerifierRegistry,
    contract_interfaces,
)  # noqa: E402
from forge_build_rtorrent_generation_observation_probe import (
    PaidNativeMeter as PreviousMeter,
    RUNTIME as PREVIOUS_RUNTIME,
)  # noqa: E402
from forge_build_rtorrent_canary import PROVIDER  # noqa: E402
from forge_build_rtorrent_template_reset_gate_v2 import HostIdentityRuntime  # noqa: E402
from forge_build_unified_plan import METHODS  # noqa: E402
from forge_typed_evidence import digest, seal, write_json  # noqa: E402
from deerflow.compile import (
    operations,
    unified_plan_equivalent_observed as observed_module,
)  # noqa: E402
from deerflow.compile.agent_workflow_runtime import AgentWorkflowExecutionMiddleware  # noqa: E402
from deerflow.compile.generated_file_boundary import FileBoundary  # noqa: E402
from deerflow.compile.generation_observation_actions import assemble_generation_actions  # noqa: E402
from deerflow.compile.operation_window import OperationWindow  # noqa: E402
from deerflow.compile.plan_agent import PlanTask  # noqa: E402
from deerflow.compile.plan_agent_provenance import run_tool_agent_automatic  # noqa: E402
from deerflow.compile.plan_agent_v2 import PlanThinkingDeepSeek  # noqa: E402
from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402
from deerflow.compile.task_selected_make_plan import selected_make_actions  # noqa: E402

PROBE = "cpp-build-rtorrent-test-preparation-probe-v1"
COMPARISON = "cpp-build-test-preparation-comparison-v1"
PROJECTS = ("yaml-cpp", "snappy", "simdutf", "tinyxml2", "check", "libtommath")
ORDERS = ((0, 1, 2), (2, 1, 0), (1, 2, 0), (0, 2, 1), (2, 0, 1), (1, 0, 2))
RUNTIME = {
    **PREVIOUS_RUNTIME,
    "new_request_reserve_seconds": 600,
    "cleanup_reserve_seconds": 300,
    "new_slot_reserve_seconds": 3900,
    "provider_http_timeout_seconds": 240,
}
PREPARATION_PROMPT = (
    "\ncommon_test_preparation是与所有策略相同的任务准备义务和原作者文件证据，不是可执行正确方案。"
    "普通默认build不一定生成测试程序；必须在固定测试前用作者标准目标构建它们。"
    "测试准备属于构建：主项目测试准备用build角色，依赖测试准备用dependency角色；最终主build动作保留step_id=build。"
    "Workflow只提供准备/配置/编译动作，固定测试与交付由系统装配；强工具也必须先准备相同测试，再运行run_fixed_tests。"
    "失败时依据真实日志修订，完整作者测试、源码保护、精确交付与clean replay均保持。"
)


def load(path):
    return json.loads(Path(path).read_text())


def schedule(identity):
    if identity == PROBE:
        return [dict(project="rtorrent", method=METHODS[1], repetition=1)]
    return [
        dict(project=name, method=METHODS[index], repetition=1)
        for name, order in zip(PROJECTS, ORDERS, strict=True)
        for index in order
    ]


def preparation_obligation(item):
    """只从冻结源码摘录测试构建声明；不读取人工参考方案。"""
    evidence = []
    with tarfile.open(item["source_archive"]) as archive:
        members = {
            m.name.removeprefix("./"): m for m in archive.getmembers() if m.isfile()
        }
        paths = (
            ["test/Makefile.am", "vendor-libtorrent/test/Makefile.am"]
            if item["name"] == "rtorrent"
            else ["CMakeLists.txt", "Makefile", "tests/Makefile.am", "test/Makefile.am"]
        )
        for path in paths:
            if path not in members:
                continue
            raw = archive.extractfile(members[path]).read()
            lines = raw.decode(errors="replace").splitlines()
            selected = set()
            for index, line in enumerate(lines):
                if any(
                    word in line.lower()
                    for word in (
                        "check_programs",
                        "tests =",
                        "test:",
                        "check:",
                        "add_test",
                        "build_test",
                        "testing",
                        "test_programs",
                    )
                ):
                    selected.update(
                        range(max(0, index - 1), min(len(lines), index + 14))
                    )
            snippet = "\n".join(f"{i + 1}: {lines[i]}" for i in sorted(selected))[:3500]
            if snippet:
                evidence.append(
                    dict(
                        path=path,
                        sha256=hashlib.sha256(raw).hexdigest(),
                        excerpt=snippet,
                        excerpt_is_partial=True,
                    )
                )
    return dict(
        required="构建并运行固定任务要求的全部原作者测试；不能仅完成默认make/cmake build。构建测试程序和判断测试结果为两个阶段。",
        fixed_verification_steps=[
            dict(
                step_id=s["step_id"],
                workdir=s["workdir"],
                required_output=s["required_output"],
            )
            for s in item["task"]["verification_steps"]
        ],
        author_build_declarations=evidence,
        extra_rtorrent_obligation="两个源码树的test/Makefile.am均声明check_PROGRAMS=$(TESTS)：依赖9个及主项目3个程序，原323叶。标准Automake check目标会构建这些程序；不能改作者输入或省略测试。"
        if item["name"] == "rtorrent"
        else None,
        generated_from="frozen_source_archive_only",
        correct_reference_injected=False,
    )


class PreparationMeter(PreviousMeter):
    def __init__(self, *args, obligation, **kwargs):
        original = kwargs.pop("packet")
        super().__init__(
            *args,
            packet=lambda: {**original(), "common_test_preparation": obligation},
            **kwargs,
        )
        self.window = OperationWindow(self.deadline)
        self.ledger.save("common-test-preparation.json", obligation)
        self.ledger.append("operation_window.policy", **RUNTIME)

    def _before_request(self):
        self.window.request()
        if self.unknown_usage_requests or Decimal(str(self.cost_usd)) + Decimal(
            "0.80"
        ) > Decimal("3.00"):
            raise PlanContractError("下一完整响应费用不足或存在未知用量")
        return AgentWorkflowExecutionMiddleware._before_request(self)

    def wrap_model_call(self, request, handler):
        system = request.system_message
        from langchain_core.messages import SystemMessage

        bounded = request.override(
            system_message=SystemMessage(
                content=(system.content if system else "") + PREPARATION_PROMPT
            )
        )
        return super().wrap_model_call(bounded, handler)


@contextmanager
def execution_window(deadline):
    window = OperationWindow(deadline)

    class WindowRuntime(HostIdentityRuntime):
        def __init__(self, *, manager, config):
            super().__init__(
                manager=manager,
                config=replace(config, network="none", cleanup_timeout_seconds=120),
            )

        def exec(
            self,
            session,
            command,
            workdir=None,
            timeout_seconds=600,
            log_path=None,
            strict_shell=False,
        ):
            bounded = window.command_timeout(timeout_seconds)
            self.manager.log_event(
                session,
                "operation_window.command",
                requested_seconds=timeout_seconds,
                admitted_seconds=bounded,
                deadline_utc=deadline,
            )
            return super().exec(
                session,
                command,
                workdir=workdir,
                timeout_seconds=bounded,
                log_path=log_path,
                strict_shell=strict_shell,
            )

    original_replay = operations.verify_clean_replay_impl

    def replay(**kwargs):
        maximum = (
            kwargs.get("timeout_seconds")
            or operations.get_compile_services().runtime.config.replay_timeout_seconds
        )
        kwargs["timeout_seconds"] = window.replay(maximum)
        return original_replay(**kwargs)

    with (
        patch.object(prepared_module, "CompileDockerRuntime", WindowRuntime),
        patch.object(common_module, "HostIdentityRuntime", WindowRuntime),
        patch.object(operations, "verify_clean_replay_impl", replay),
        patch.dict(
            os.environ,
            {"FORGE_HOST_UID": str(os.getuid()), "FORGE_HOST_GID": str(os.getgid())},
        ),
    ):
        yield


def run_slot(*, protocol, slot, root, model):
    item = next(p for p in protocol["projects"] if p["name"] == slot["project"])
    obligation = item["common_test_preparation"]

    def factory(*args, **kwargs):
        return PreparationMeter(*args, obligation=obligation, **kwargs)

    started = time.monotonic()
    with execution_window(protocol["deadline_utc"]):
        if item["name"] == "rtorrent":
            boundary = FileBoundary.model_validate(item["file_boundary"])

            def assemble(task, proposal, *, revision):
                return assemble_generation_actions(
                    task, proposal, revision=revision, boundary=boundary
                )

            with patch.object(observed_module, "assemble_observed", assemble):
                row = native_run_strategy(
                    method=slot["method"],
                    item=item,
                    protocol=protocol,
                    root=root,
                    model=model,
                    meter_factory=factory,
                )
        else:
            registry = FixedVerifierRegistry(item["task"])
            with contract_interfaces(registry):
                planner = observed_module.observed_planner(
                    "tool" if slot["method"] == METHODS[0] else "model",
                    generator=selected_make_actions,
                )
                row = classified_prepared_arm(
                    item=item,
                    arm="tool" if slot["method"] == METHODS[2] else "plan",
                    protocol=protocol,
                    root=root,
                    model=model,
                    meter_factory=lambda *a, **kw: factory(*a, registry=registry, **kw),
                    planner=planner,
                    tool_runner=run_tool_agent_automatic,
                    command_timeout_seconds=1200,
                    replay_timeout_seconds=1200,
                )
    return {**row, **slot, "arm_total_wall_seconds": time.monotonic() - started}


def validate(candidate):
    if (
        candidate["identity"] not in (PROBE, COMPARISON)
        or candidate["schedule"] != schedule(candidate["identity"])
        or candidate["runtime"] != RUNTIME
        or candidate["provider"] != PROVIDER
    ):
        raise PlanContractError("身份、调度、资源或模型不符")
    for name, sha in candidate["components"].items():
        if digest(ROOT / name) != sha:
            raise PlanContractError("冻结组件变化：" + name)
    for item in candidate["projects"]:
        if digest(Path(item["source_archive"])) != item["task"][
            "source_archive_sha256"
        ] or item["common_test_preparation"] != preparation_obligation(item):
            raise PlanContractError("冻结源码或共同测试准备材料变化")
        PlanTask.model_validate(item["task"])
    if any(k in candidate for k in ("reference", "recovery_actions")):
        raise PlanContractError("真实候选不得含人工正确参考")


def append_budget(root, event):
    """已完阶段可在收尾时闭合；只有新阶段需要执行时间准入。"""
    auth = load(root / "authorization.json")
    with (root / "budget-events.jsonl").open("a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.seek(0)
        rows = [json.loads(line) for line in handle if line.strip()]
        active, spent = {}, Decimal(0)
        for row in rows:
            if row["event"] == "stage.started":
                if row["identity"] in active:
                    raise PlanContractError("阶段重复")
                active[row["identity"]] = row
            else:
                prior = active.pop(row["identity"])
                cost = Decimal(row["charged_cost_usd"])
                if not 0 <= cost <= Decimal(prior["reserved_cost_usd"]):
                    raise PlanContractError("阶段费用超限")
                spent += cost
        if event["event"] == "stage.started":
            OperationWindow(auth["deadline_utc"]).request()
            if (
                active
                or any(row["identity"] == event["identity"] for row in rows)
                or spent + Decimal(event["reserved_cost_usd"])
                > Decimal(auth["max_new_provider_cost_usd"])
            ):
                raise PlanContractError("共享预算、活动阶段或身份冲突")
        else:
            prior = active.get(event["identity"])
            if not prior or not 0 <= Decimal(event["charged_cost_usd"]) <= Decimal(
                prior["reserved_cost_usd"]
            ):
                raise PlanContractError("共享账本无法闭合")
        handle.seek(0, 2)
        handle.write(
            json.dumps(
                {**event, "at_utc": datetime.now(UTC).isoformat()}, ensure_ascii=False
            )
            + "\n"
        )
        handle.flush()
        os.fsync(handle.fileno())


def charges(rows):
    known = sum(
        (
            Decimal(str(r["agent_usage"]["estimated_cost_usd_completed_responses"]))
            for r in rows
        ),
        Decimal(0),
    )
    unknown = sum(r["agent_usage"]["unknown_usage_requests"] for r in rows)
    return known, Decimal("0.80") * unknown


def execute(protocol, root, model, rows):
    for index, slot in enumerate(protocol["schedule"], 1):
        try:
            OperationWindow(protocol["deadline_utc"]).admit("new_slot", 3900)
        except PlanContractError:
            return "new_slot_time_reservation"
        if sum(charges(rows)) + Decimal("3.00") > Decimal(
            protocol["stage_max_cost_usd"]
        ):
            return "stage_cost_reservation"
        folder = root / f"slot-{index}"
        folder.mkdir()
        row = run_slot(protocol=protocol, slot=slot, root=folder, model=model)
        rows.append(row)
        write_json(root / f"progress-{index}.json", row)
        print(
            json.dumps(
                dict(
                    slot=index,
                    project=slot["project"],
                    method=slot["method"],
                    strict=row["strict_completed"],
                    error=row.get("error_message"),
                    usage=row["agent_usage"],
                ),
                ensure_ascii=False,
            ),
            flush=True,
        )
        if (
            not row["cleanup"]["succeeded"]
            or row["agent_usage"]["unknown_usage_requests"]
        ):
            return "cleanup_or_unknown_usage"
        if Decimal(
            str(row["agent_usage"]["estimated_cost_usd_completed_responses"])
        ) > Decimal("3.00"):
            return "cost_contract_violation"
        if any(
            json.loads(line)["event"] == "model.identity_mismatch"
            for p in folder.glob("*/agent/events.jsonl")
            for line in p.read_text().splitlines()
        ):
            return "provider_identity_mismatch"
        if row.get("error_class") not in (
            None,
            "PlanContractError",
            "ValueError",
            "AgentWorkflowBudgetExceeded",
            "ValidationError",
            "StructuredOutputValidationError",
            "GraphRecursionError",
        ):
            return "unexpected_runtime_error"
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--authorization-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    candidate = load(args.candidate)
    validate(candidate)
    auth = load(args.authorization_root / "authorization.json")
    bound = auth["experiments"].get(candidate["identity"])
    if (
        auth.get("user_authorized") is not True
        or auth.get("automatic_retry") is not False
        or bound != digest(args.candidate)
    ):
        raise PlanContractError("缺少当前用户授权及精确候选绑定")
    OperationWindow(auth["deadline_utc"]).request()
    if args.output_root.exists():
        raise PlanContractError("证据目录已存在，不续跑旧身份")
    if args.validate_only:
        print(json.dumps(dict(valid=True, credentials_read=False, provider_calls=0)))
        return 0
    subprocess.run(
        ["bash", str(ROOT / "scripts/require-docker-runtime.sh")],
        check=True,
        timeout=30,
    )
    protocol = {
        **candidate,
        "deadline_utc": auth["deadline_utc"],
        "candidate_sha256": digest(args.candidate),
    }
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", protocol)
    write_json(root / "authorization.json", auth)
    write_json(
        root / "execution.json",
        dict(
            release=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], text=True
            ).strip()
        ),
    )
    append_budget(
        args.authorization_root,
        dict(
            event="stage.started",
            identity=candidate["identity"],
            reserved_cost_usd=protocol["stage_max_cost_usd"],
            evidence_root=str(root),
        ),
    )
    rows, complete, reason = [], False, "initialization_not_completed"
    try:
        from dotenv import load_dotenv

        for path in (ROOT / ".env", ROOT / "backend/.env"):
            if not os.environ.get("DEEPSEEK_API_KEY") and path.is_file():
                load_dotenv(path, override=False)
        key = os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise PlanContractError("当前授权Provider凭据不可用")
        model = PlanThinkingDeepSeek(
            model=PROVIDER["model"],
            api_key=key,
            base_url="https://api.deepseek.com",
            max_tokens=32768,
            max_retries=0,
            timeout=240,
            reasoning_effort="low",
            extra_body={"thinking": {"type": "enabled"}},
        )
        reason = execute(protocol, root, model, rows)
        complete = True
    finally:
        known, unknown = charges(rows)
        write_json(
            root / "result.json",
            dict(
                identity=candidate["identity"],
                kind=candidate["kind"],
                rows=rows,
                unobserved_schedule=protocol["schedule"][len(rows) :],
                stop_reason=reason,
                lifecycle_complete=complete,
                known_estimated_cost_usd=str(known),
                unknown_usage_reservation_usd=str(unknown),
            ),
        )
        inventory = seal(
            root,
            protocol,
            ROOT,
            sum(r["agent_usage"]["unknown_usage_requests"] for r in rows),
        )
        if complete:
            append_budget(
                args.authorization_root,
                dict(
                    event="stage.completed",
                    identity=candidate["identity"],
                    charged_cost_usd=str(known + unknown),
                    inventory_sha256=inventory["inventory_canonical_sha256"],
                ),
            )
    return 0 if len(rows) == len(protocol["schedule"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
