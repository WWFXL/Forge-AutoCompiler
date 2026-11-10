#!/usr/bin/env python3
"""最新恢复轨迹的 R2 离线提案；不执行比较或修改论文。"""

from __future__ import annotations

import argparse
import difflib
import json
import time
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from deerflow.compile.plan_workflow import PlanContractError, _digest
from deerflow.compile.recovery_harness import (
    RECOVERY_OPTIMIZER_PROMPT,
    RecoveryHarness,
    RecoveryHarnessProposal,
)
from deerflow.compile.simple_build_task import SIMPLE_PROMPT
from forge_recovery_harness_proposal import ROOT, excerpt, load, save
from forge_typed_evidence import digest

IDENTITY = "cpp-build-offline-recovery-harness-proposal-r2-v1"
MODEL = "gpt-6.1-sol"
PRICE = Decimal("1.00")
SOURCE = Path("/home/yiwei/.codex/outputs/forge-recovery-harness-comparison-flash-v2")
FIXTURE = ROOT / "benchmarks/fixtures/recovery-harness-proposal-r2-v1"
MAX_OUTPUT = 8192
COMMON_REPAIRS = (
    "当前共同执行器已完成 #715/#717/#719：作者生成文档由独立参考声明，不由Agent自由改源码；"
    "原生轻量验证、运行时SONAME交付和真实运行失败的恢复交接已支持；"
    "修订结构与执行约束分别提供一次有界纠正；过大AI/Tool组可压缩为可追溯片段。"
    "各方法未来共用国内HTTPS APT镜像，250原软件包不变；网络仍可能失败，不表示候选能修复服务。"
    "新successful-rebuild-v1只要求同源码/镜像的干净构建、相同交付路径、有效非空类型与轻量命令成功，"
    "跨重建大小/哈希/输出差异仅诊断；原源码/测试和接受后的原交付完整性仍检查。"
    "这些是共同人工修复，不得算为R2新增能力，不改旧终态，也未取得修复后的新Agent恢复轨迹。"
)
OPTIMIZER_PROMPT = (
    RECOVERY_OPTIMIZER_PROMPT
    + """
本轮提出恢复候选R2，初始规划仍固定H0，线上构建/恢复仍用Flash；你只负责离线提案。
输入同时含H0、R1真实恢复和R1原指导。R1没有表现出总体优势；不要假定已有每条指导都应保留，允许删减、重写或no_change。
结合修订被拒的具体反馈、提交时机与最终动作分析；不能只按读取次数给无效标签，也不能将网络差异或共同修复误归因指导。
新指导将整体替代R1附加指导，而非在R1后继续累加；只保留有轨迹依据、当前底座仍需要的可迁移行为。
材料的整槽结局不是每次局部恢复的成功标签，normal_success_boundary无恢复；工程修复说明不是模型成功样本。
请给出完整可替换指导及引用证据的诊断，不能声称尚未比较的R2已有效。
"""
)


def evidence(key, kind, content, path):
    return dict(
        evidence_id=key,
        kind=kind,
        content=content,
        source_path=str(path),
        source_sha256=digest(path),
    )


def handoff(packet):
    """保留真正使用的状态键，尤其成功依赖 ID 与配置观察。"""
    keys = {
        "handoff_id",
        "reason",
        "step_id",
        "plan_sha256",
        "command_frontier",
        "configuration_state",
        "primary_components",
        "successful_dependencies",
        "return_contract",
    }
    value = {k: v for k, v in packet["handoff"].items() if k in keys}
    value["recent_commands"] = [
        {
            k: excerpt(v, 3000) if k in {"command", "output_tail"} else v
            for k, v in row.items()
            if k
            in {
                "command_id",
                "role",
                "command",
                "workdir",
                "exit_code",
                "output_tail",
                "log_sha256",
            }
        }
        for row in packet["handoff"].get("recent_commands", [])
    ]
    return dict(task=packet["task"], current_plan=packet["current_plan"], handoff=value)


def outcome(result):
    return {
        k: result.get(k)
        for k in (
            "status",
            "error_type",
            "error",
            "layers",
            "timings",
            "agent_usage",
            "cleanup",
        )
    }


def corpus(source=SOURCE):
    episodes = []
    for folder in sorted(source.glob("slot-*")):
        path = folder / "agent/events.jsonl"
        events = (
            [json.loads(line) for line in path.read_text().splitlines()]
            if path.exists()
            else []
        )
        starts = [i for i, e in enumerate(events) if e["event"] == "agent.started"]
        for pos, start in enumerate(starts):
            entry = events[start]
            if not entry.get("recovery"):
                continue
            end = starts[pos + 1] if pos + 1 < len(starts) else len(events)
            segment = events[start:end]
            seqs = [
                e["request_sequence"]
                for e in segment
                if e["event"] == "model.request_started"
            ]
            if not seqs:
                raise PlanContractError(
                    "恢复交接没有请求，须先明确其材料边界：" + folder.name
                )
            request_path = folder / "agent" / f"request-{seqs[0]}.json"
            packet = json.loads(load(request_path)["messages"][0]["content"])
            revision = entry["revision"]
            prefix = f"E53:{folder.name}:r{revision}"
            items = [
                evidence(
                    prefix + ":handoff",
                    "actual_recovery_handoff",
                    handoff(packet),
                    request_path,
                )
            ]
            tools = [
                (start + i + 1, e)
                for i, e in enumerate(segment)
                if e["event"] == "tool.completed"
            ]
            selected = tools if len(tools) <= 8 else tools[:4] + tools[-4:]
            for number, e in selected:
                items.append(
                    evidence(
                        prefix + f":event-{number}",
                        "visible_tool_feedback",
                        dict(
                            tool=e["name"],
                            result=excerpt(
                                e.get("result", {}).get("content", ""), 1800
                            ),
                        ),
                        path,
                    )
                )
            # 拒绝原因必须进入材料，不能仅保存最后一份看起来合法的动作。
            decisions = [
                e
                for e in segment
                if e["event"]
                in {"simple.proposal_rejected", "simple.proposal_accepted"}
            ]
            items.append(
                evidence(
                    prefix + ":decisions",
                    "proposal_acceptance_and_rejection",
                    decisions,
                    path,
                )
            )
            action = folder / "agent" / f"simple-actions-{revision}.json"
            if action.exists():
                items.append(
                    evidence(
                        prefix + ":actions",
                        "submitted_actions_not_necessarily_executed",
                        load(action),
                        action,
                    )
                )
            result_path = folder / "result.json"
            items.append(
                evidence(
                    prefix + ":outcome",
                    "whole_slot_outcome_not_local_recovery_label",
                    outcome(load(result_path)),
                    result_path,
                )
            )
            calls = [
                dict(tool=e["name"], arguments=e.get("args", {}))
                for e in segment
                if e["event"] == "tool.started"
            ]
            counts = Counter(
                json.dumps(c, ensure_ascii=False, sort_keys=True) for c in calls
            )
            episodes.append(
                dict(
                    trajectory_id=prefix,
                    slot=folder.name,
                    method=folder.name.rsplit("-", 1)[-1],
                    execution_method=load(result_path)["method"],
                    role="optimizer_development_recovery",
                    revision=revision,
                    requests=len(seqs),
                    tool_calls=len(calls),
                    read_frequencies=[
                        dict(**json.loads(key), count=count)
                        for key, count in counts.most_common()
                    ],
                    omitted_tool_feedback=len(tools) - len(selected),
                    evidence=items,
                )
            )
    # 每个构建系统一个正常成功边界；不按低费用筛选恢复，也不估失败发生率。
    for project in ("cglm", "massdns", "libmodbus"):
        folder = next(source.glob(f"slot-*-{project}-H0"))
        path = folder / "result.json"
        plan = next(folder.glob(".compile-sessions/*/*/build-plan/plan-1.json"))
        key = "E53:normal:" + project
        episodes.append(
            dict(
                trajectory_id=key,
                role="normal_success_boundary",
                evidence=[
                    evidence(key + ":plan", "normal_initial_plan", load(plan), plan),
                    evidence(
                        key + ":outcome",
                        "whole_slot_outcome",
                        outcome(load(path)),
                        path,
                    ),
                ],
            )
        )
    return dict(
        format="offline-recovery-corpus-r2-v1",
        episodes=episodes,
        holdout=False,
        selection="E53全部13次自然恢复交接（7槽、4项目）及三系统各一正常成功边界；失败与超时均保留。",
        historical_context=COMMON_REPAIRS,
        historical_cost_is_new_charge=False,
    )


def prepare(output):
    output.mkdir(parents=True, exist_ok=False)
    material = corpus()
    base = RecoveryHarness(
        name="H0_recovery", base_prompt_sha256=_digest(SIMPLE_PROMPT)
    )
    previous_path = (
        ROOT / "benchmarks/fixtures/recovery-harness-proposal-v1/proposal.json"
    )
    previous = load(previous_path)
    prior = RecoveryHarness(
        name="R1_current_base_reference_only",
        base_prompt_sha256=base.base_prompt_sha256,
        recovery_guidance=previous["recovery_guidance"],
    )
    request = dict(
        system_prompt=OPTIMIZER_PROMPT,
        packet=dict(
            base_prompt=SIMPLE_PROMPT,
            baseline=base.model_dump(mode="json"),
            prior_R1_guidance=prior.recovery_guidance,
            prior_R1_status="not_adopted; reference only, not an unchanged runnable historical harness",
            common_repairs=COMMON_REPAIRS,
            corpus=material,
        ),
    )
    save(output / "corpus.json", material)
    save(output / "baseline.json", base.model_dump(mode="json"))
    save(output / "r1-reference.json", prior.model_dump(mode="json"))
    save(output / "request.json", request)
    size = len(json.dumps(request, ensure_ascii=False).encode())
    if size > 400000:
        raise PlanContractError("提案材料超过400000字节预留")
    recoveries = [
        e for e in material["episodes"] if e["role"] == "optimizer_development_recovery"
    ]
    scope = dict(
        identity=IDENTITY,
        issue=721,
        phase="prepared_not_authorized_for_provider",
        requested_model=MODEL,
        accepted_response_models=[MODEL],
        input_usd_per_million=str(PRICE),
        output_usd_per_million=str(PRICE),
        maximum_requests=1,
        maximum_output_tokens=MAX_OUTPUT,
        proposed_maximum_cost_usd="1.00",
        automatic_retry=False,
        comparisons_authorized=False,
        thesis_update_authorized=False,
        request_bytes=size,
        conservative_request_reserve_usd=str(
            Decimal(size + MAX_OUTPUT + 4096) / Decimal(1000000)
        ),
        request_sha256=digest(output / "request.json"),
        fixture_sha256={p.name: digest(p) for p in output.iterdir()},
        source_inventory_file_sha256=digest(SOURCE / "inventory.json"),
        source_inventory_canonical_sha256=load(SOURCE / "seal.json")[
            "inventory_canonical_sha256"
        ],
        previous_proposal_sha256=digest(previous_path),
        recovery_episodes=len(recoveries),
        recovery_slots=len({e["slot"] for e in recoveries}),
        historical_requests=sum(e["requests"] for e in recoveries),
        current_base_prompt_sha256=base.base_prompt_sha256,
        components={
            p: digest(ROOT / p)
            for p in (
                "scripts/forge_recovery_harness_r2.py",
                "scripts/forge_recovery_harness_proposal.py",
                "backend/packages/harness/deerflow/compile/recovery_harness.py",
                "backend/packages/harness/deerflow/compile/simple_build_task.py",
            )
        },
    )
    save(output / "scope.json", scope)
    return scope


def check_authorization(prepared, authorization):
    scope = load(prepared / "scope.json")
    for key, value in (
        ("identity", IDENTITY),
        ("requested_model", MODEL),
        ("maximum_requests", 1),
        ("maximum_cost_usd", "1.00"),
        ("request_sha256", scope["request_sha256"]),
    ):
        if authorization.get(key) != value:
            raise PlanContractError("缺少本轮一次提案授权或范围变化：" + key)
    if not authorization.get("user_authorization") or datetime.now(
        UTC
    ) >= datetime.fromisoformat(authorization["deadline"]):
        raise PlanContractError("缺少用户授权原文或有效截止时间")
    started = datetime.fromisoformat(authorization["started_at"])
    deadline = datetime.fromisoformat(authorization["deadline"])
    if (
        started.tzinfo is None
        or deadline.tzinfo is None
        or not 0 < (deadline - started).total_seconds() <= 4 * 3600
        or datetime.now(UTC) < started
    ):
        raise PlanContractError("一次提案授权时窗须在确认起4小时内")
    for name, expected in scope["fixture_sha256"].items():
        if digest(prepared / name) != expected:
            raise PlanContractError("准备材料变化：" + name)
    for name, expected in scope["components"].items():
        if digest(ROOT / name) != expected:
            raise PlanContractError("准备后组件变化：" + name)
    if (
        scope["requested_model"] != MODEL
        or scope["accepted_response_models"] != [MODEL]
        or Decimal(scope["conservative_request_reserve_usd"])
        > Decimal(authorization["maximum_cost_usd"])
    ):
        raise PlanContractError("模型身份或费用预留不足")
    return scope


def generate(prepared, output, authorization, model_factory):
    """核验一次性授权后才建立模型；原目录存在时不再读取凭据。"""
    scope = check_authorization(prepared, authorization)
    output.mkdir(parents=True, exist_ok=False)
    save(output / "authorization.json", authorization)
    save(output / "scope.json", scope)
    save(output / "request.json", load(prepared / "request.json"))
    save(
        output / "request-started.json",
        dict(
            identity=IDENTITY,
            started_at=datetime.now(UTC).isoformat(),
            automatic_retry=False,
        ),
    )
    started = time.monotonic()
    known = False
    try:
        request = load(prepared / "request.json")
        model = model_factory()
        response = model.invoke(
            [
                SystemMessage(content=request["system_prompt"]),
                HumanMessage(content=json.dumps(request["packet"], ensure_ascii=False)),
            ]
        )
        save(output / "response.json", response.model_dump(mode="json"))
        usage = response.usage_metadata
        if not usage or any(
            type(usage.get(k)) is not int or usage[k] < 0
            for k in ("input_tokens", "output_tokens")
        ):
            raise PlanContractError("未知用量，停止，不重试")
        cost = (
            Decimal(usage["input_tokens"] + usage["output_tokens"])
            * PRICE
            / Decimal(1000000)
        )
        actual = response.response_metadata.get(
            "model_name"
        ) or response.response_metadata.get("model")
        save(
            output / "usage.json",
            dict(
                **usage,
                estimated_cost_usd_completed_responses=str(cost),
                requested_model=MODEL,
                response_model=actual,
                seconds=time.monotonic() - started,
                actual_backend_confirmed=False,
            ),
        )
        known = True
        if (
            actual != MODEL
            or cost > Decimal(authorization["maximum_cost_usd"])
            or datetime.now(UTC) >= datetime.fromisoformat(authorization["deadline"])
        ):
            raise PlanContractError(
                "模型标识、费用或时窗超出边界；不自动接受旧路由别名"
            )
        proposal = RecoveryHarnessProposal.model_validate_json(response.text)
        candidate = proposal.materialize(
            RecoveryHarness.model_validate(load(prepared / "baseline.json")),
            load(prepared / "corpus.json"),
        )
        if not proposal.no_change:
            candidate = candidate.model_copy(update=dict(name="R2_recovery"))
        save(output / "proposal.json", proposal.model_dump(mode="json"))
        save(output / "candidate.json", candidate.model_dump(mode="json"))
        before = SIMPLE_PROMPT
        prior = RecoveryHarness.model_validate(
            load(prepared / "r1-reference.json")
        ).prompt(before)
        after = candidate.prompt(before)
        for name, text in (
            ("prompt-H0.txt", before),
            ("prompt-R1-current-base-reference.txt", prior),
            ("prompt-R2.txt", after),
        ):
            (output / name).write_text(text)
        for name, previous in (("H0", before), ("R1", prior)):
            (output / f"diff-{name}-R2.patch").write_text(
                "".join(
                    difflib.unified_diff(
                        previous.splitlines(keepends=True),
                        after.splitlines(keepends=True),
                        fromfile=name,
                        tofile="R2",
                    )
                )
            )
        save(
            output / "completed.json",
            dict(
                identity=IDENTITY,
                state="no_change"
                if proposal.no_change
                else "awaiting_user_candidate_review",
                candidate_sha256=candidate.fingerprint(),
                comparisons_started=0,
                thesis_updated=False,
                estimated_cost_usd=str(cost),
            ),
        )
        return candidate
    except Exception as error:
        save(
            output / "failure.json",
            dict(
                identity=IDENTITY,
                category=type(error).__name__,
                unknown_usage=not known,
                automatic_retry=False,
            ),
        )
        raise


def richlab_model():
    """仅在有效授权及唯一目录建立后读取现有 RichLab 凭据。"""
    import tomllib

    from forge_planner_model_comparison import RichLabPlanner

    config = tomllib.loads(Path("/home/yiwei/.codex/config.toml").read_text())
    endpoint = config["model_providers"][config["model_provider"]]["base_url"]
    key = load(Path("/home/yiwei/.codex/auth.json"))["OPENAI_API_KEY"]
    return RichLabPlanner(
        model=MODEL,
        api_key=key,
        base_url=endpoint,
        use_responses_api=True,
        max_tokens=MAX_OUTPUT,
        max_retries=0,
        timeout=240,
        reasoning_effort="low",
        store=False,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "propose"))
    parser.add_argument("--prepared", type=Path, default=FIXTURE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--authorization", type=Path)
    args = parser.parse_args()
    if args.mode == "prepare":
        print(json.dumps(prepare(args.prepared), ensure_ascii=False))
    else:
        if args.output is None or args.authorization is None:
            parser.error("propose需要独立输出目录及用户授权收据")
        result = generate(
            args.prepared, args.output, load(args.authorization), richlab_model
        )
        print(
            json.dumps(
                dict(candidate_sha256=result.fingerprint(), comparisons_started=0),
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
