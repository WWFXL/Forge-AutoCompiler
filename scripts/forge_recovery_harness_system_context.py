#!/usr/bin/env python3
"""把真实系统接口与源码装配给离线优化器；独立一次提案，不执行比较。"""

from __future__ import annotations

import argparse
import ast
import difflib
import json
import subprocess
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.utils.function_calling import convert_to_openai_tool

from deerflow.compile.plan_agent_context import safe_readonly_tools
from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.recovery_harness import RecoveryHarness, RecoveryHarnessProposal
from deerflow.compile.simple_build_task import (
    SIMPLE_PROMPT,
    PublicBuildTask,
    SimpleBuildActions,
)
from forge_recovery_harness_r2 import FIXTURE as PREVIOUS_INPUT
from forge_recovery_harness_r2 import (
    MAX_OUTPUT,
    MODEL,
    PRICE,
    ROOT,
    load,
    richlab_model,
    save,
)
from forge_typed_evidence import digest

IDENTITY = "cpp-build-offline-recovery-harness-system-context-proposal-v1"
FIXTURE = ROOT / "benchmarks/fixtures/recovery-harness-system-context-v1"
PREVIOUS_OUTPUT = ROOT / "benchmarks/fixtures/recovery-harness-r2-gpt61sol-v1"
BASE_REVISION = "64978dd68b86398aa2daa1a44a8755f6b26338a9"
SHARED_LIMIT = Decimal("1.00")
SHARED_DEADLINE = "2026-11-10T18:24:13+00:00"
SHARED_START = "2026-11-10T14:24:13+00:00"
CONTEXT_NOTE = "docs/research/2026-11-10-recovery-optimizer-system-context.md"
PACKAGE = "backend/packages/harness/deerflow/compile/"
SOURCES = {
    PACKAGE + "simple_build_task.py": [
        "SimpleBuildAction",
        "SimpleBuildActions",
        "PublicBuildTask",
        "assemble_simple_plan",
        "validate_simple_revision",
        "simple_agent_packet",
        "propose_simple",
    ],
    PACKAGE + "plan_agent_context.py": ["normalized_read_path", "safe_readonly_tools"],
    PACKAGE + "plan_agent.py": ["readonly_plan_tools", "_read_text"],
    PACKAGE + "simple_build_runtime.py": [
        "observe_configuration",
        "configuration_entry",
        "validate_phase_command",
        "generated_reset_step",
        "primary_artifacts",
        "SimpleBuildWorkflow._configuration_observation",
        "SimpleBuildWorkflow._execute",
        "SimpleBuildWorkflow._request_handoff",
        "SimpleBuildWorkflow.run",
        "SimpleBuildWorkflow._retain_dependencies",
        "SimpleBuildWorkflow.validate_revision",
        "SimpleBuildWorkflow.apply_revision",
        "SimpleBuildWorkflow._apply_execution_revision",
        "SimpleBuildWorkflow._executable_verification",
        "SimpleBuildWorkflow.postchecks",
    ],
    PACKAGE + "plan_workflow.py": [
        "PlanStep",
        "PlanWorkflow._request_handoff",
        "PlanWorkflow._execute",
        "PlanWorkflow.run",
        "PlanWorkflow.apply_revision",
    ],
    PACKAGE + "operations.py": [
        "_shell_command_segments",
        "_command_invocation",
        "_infer_command_roles",
        "infer_command_roles",
    ],
    PACKAGE + "simple_planning_context.py": [
        "PlanningContext.compact_group",
        "PlanningContext.request",
    ],
    "scripts/forge_simple_system.py": ["run_simple_system"],
}
ADDITIONAL_PROMPT = """
用户要求补充当前系统实现后，独立重新分析原R2，而非强制产生更复杂的新版本。
implementation_reference是当前版本源码/接口与人工说明，不是轨迹或成功样本；原13次恢复和3条正常边界不增加。
科研入口的规划/恢复Agent只有只读工具和结构化方案输出，没有Bash、运行修订或联网工具；由Workflow执行修订。
源码片段有版本、路径、行号和文件哈希，但不是整个仓库；如信息不足请明确限制，不假定新能力。人工说明冲突时引用源码。
逐项复核prior_R2_proposal的诊断和建议：保留仍有必要的，指出重复底座、权限/阶段/目录/终止接口冲突或过度限制。
诊断可引用SYS:implementation与真实E53证据，明确哪些是已实现机制、哪些才是拟改提示策略；仅引用系统说明不足以证明性能改善。
对原R2的复核写入diagnoses的problem/proposed_change/expected_behavior，继续使用给定JSON接口，不增加新字段。
新的recovery_guidance整体替代附加指导，H0仍是基线；no_change指保持H0，不能默认采用原R2。
无需机械重述所有现有约束。保留必要读取与有证据的备选构建/获取路径，不为减少请求禁止合理修复。
不能通过提示赋予不存在的工具或跳过现有执行策略；也不能为配合接口关闭主要目标或修改源码/测试。
这次只提出待审指导，不比较、不修改论文，原R2及历史失败完整保留。输出前核对建议是否实际可由该Agent执行。
"""


def source_excerpt(relative, symbol):
    """完整摘录指定定义，避免手写代码摘要代替实现。"""
    path = ROOT / relative
    text = path.read_text()
    node = ast.parse(text)
    for part in symbol.split("."):
        node = next(
            n
            for n in node.body
            if isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef))
            and n.name == part
        )
    start = min([node.lineno, *(d.lineno for d in node.decorator_list)])
    return dict(
        path=relative,
        symbol=symbol,
        file_sha256=digest(path),
        start_line=start,
        end_line=node.end_lineno,
        content="".join(text.splitlines(keepends=True)[start - 1 : node.end_lineno]),
    )


def prepare(output=FIXTURE):
    old = load(PREVIOUS_INPUT / "request.json")
    previous_usage = load(PREVIOUS_OUTPUT / "usage.json")
    implementation = dict(
        kind="implementation_reference_not_trajectory",
        source_revision=BASE_REVISION,
        coverage="科研SimpleBuild入口的关键源码片段及真实Schema；非完整仓库、非新Agent轨迹",
        explanation=dict(
            path=CONTEXT_NOTE,
            file_sha256=digest(ROOT / CONTEXT_NOTE),
            content=(ROOT / CONTEXT_NOTE).read_text(),
        ),
        execution_contract=dict(
            path="docs/compile_workflow_execution.md",
            file_sha256=digest(ROOT / "docs/compile_workflow_execution.md"),
            content=(ROOT / "docs/compile_workflow_execution.md").read_text(),
        ),
        public_task_schema=PublicBuildTask.model_json_schema(),
        output_schema=convert_to_openai_tool(SimpleBuildActions),
        readonly_tool_schemas=[
            convert_to_openai_tool(t) for t in safe_readonly_tools(ROOT, ROOT)
        ],
        source_excerpts=[
            source_excerpt(path, symbol)
            for path, symbols in SOURCES.items()
            for symbol in symbols
        ],
    )
    material = load(PREVIOUS_INPUT / "corpus.json")
    material["episodes"].append(
        dict(
            role="implementation_reference_not_trajectory",
            evidence=[
                dict(
                    evidence_id="SYS:implementation",
                    kind="versioned_system_implementation",
                    content=implementation,
                )
            ],
        )
    )
    packet = {
        **old["packet"],
        "corpus": material,
        "prior_R2_proposal": load(PREVIOUS_OUTPUT / "proposal.json"),
        "prior_R2_status": "reference_only_not_adopted_or_evaluated",
    }
    request = dict(
        system_prompt=old["system_prompt"] + ADDITIONAL_PROMPT, packet=packet
    )
    size = len(json.dumps(request, ensure_ascii=False).encode())
    prior = Decimal(previous_usage["estimated_cost_usd_completed_responses"])
    reserve = Decimal(size + MAX_OUTPUT + 4096) * PRICE / Decimal(1000000)
    if size > 500000 or prior + reserve > SHARED_LIMIT:
        raise PlanContractError("材料大小或累计预留超过共享预算")
    # 只绑定摘录中实际提供的系统文件；后续提案脚本/报告提交不改变该系统版本。
    paths = [*SOURCES, "docs/compile_workflow_execution.md"]
    for path in paths:
        original = subprocess.check_output(
            ["git", "show", f"{BASE_REVISION}:{path}"], cwd=ROOT
        )
        if original != (ROOT / path).read_bytes():
            raise PlanContractError("系统上下文偏离声明版本：" + path)
    output.mkdir(parents=True, exist_ok=False)
    for name, value in (
        ("request.json", request),
        ("corpus.json", material),
        ("implementation.json", implementation),
        ("baseline.json", old["packet"]["baseline"]),
        ("r1-reference.json", load(PREVIOUS_INPUT / "r1-reference.json")),
        ("r2-reference.json", load(PREVIOUS_OUTPUT / "candidate.json")),
    ):
        save(output / name, value)
    scope = dict(
        identity=IDENTITY,
        issue=723,
        requested_model=MODEL,
        maximum_requests=1,
        maximum_output_tokens=MAX_OUTPUT,
        prior_paid_usd=str(prior),
        shared_maximum_cost_usd=str(SHARED_LIMIT),
        shared_started_at=SHARED_START,
        shared_deadline=SHARED_DEADLINE,
        request_bytes=size,
        conservative_request_reserve_usd=str(reserve),
        system_revision=BASE_REVISION,
        request_sha256=digest(output / "request.json"),
        previous_request_sha256=digest(PREVIOUS_INPUT / "request.json"),
        previous_response_sha256=digest(PREVIOUS_OUTPUT / "proposal.json"),
        previous_usage_sha256=digest(PREVIOUS_OUTPUT / "usage.json"),
        fixture_sha256={p.name: digest(p) for p in output.iterdir()},
        components={
            p: digest(ROOT / p)
            for p in [
                *paths,
                CONTEXT_NOTE,
                "scripts/forge_recovery_harness_system_context.py",
            ]
        },
        recovery_episodes=13,
        normal_boundaries=3,
        implementation_references=1,
        comparisons_authorized=False,
        thesis_update_authorized=False,
        automatic_retry=False,
    )
    save(output / "scope.json", scope)
    return scope


def check_authorization(prepared, authorization):
    scope = load(prepared / "scope.json")
    expected = dict(
        identity=IDENTITY,
        requested_model=MODEL,
        maximum_requests=1,
        shared_maximum_cost_usd=str(SHARED_LIMIT),
        prior_paid_usd=scope["prior_paid_usd"],
        started_at=SHARED_START,
        deadline=SHARED_DEADLINE,
        request_sha256=scope["request_sha256"],
    )
    if any(
        authorization.get(k) != v for k, v in expected.items()
    ) or not authorization.get("user_authorization"):
        raise PlanContractError("缺少独立新调用指令或共享预算/原截止不匹配")
    if (
        not datetime.fromisoformat(SHARED_START)
        <= datetime.now(UTC)
        < datetime.fromisoformat(SHARED_DEADLINE)
    ):
        raise PlanContractError("原共享时窗已结束或尚未开始")
    if (
        Decimal(scope["prior_paid_usd"])
        + Decimal(scope["conservative_request_reserve_usd"])
        > SHARED_LIMIT
    ):
        raise PlanContractError("累计费用预留不足")
    for name, expected_hash in scope["fixture_sha256"].items():
        if digest(prepared / name) != expected_hash:
            raise PlanContractError("固定材料变化：" + name)
    for name, expected_hash in scope["components"].items():
        if digest(ROOT / name) != expected_hash:
            raise PlanContractError("固定实现变化：" + name)
    return scope


def generate(prepared, output, authorization, model_factory):
    """只发送一次请求；先核验范围，已知费用先保存，再校验模型与输出。"""
    scope = check_authorization(prepared, authorization)
    output.mkdir(parents=True, exist_ok=False)
    save(output / "authorization.json", authorization)
    save(output / "scope.json", scope)
    request = load(prepared / "request.json")
    save(output / "request.json", request)
    save(
        output / "request-started.json",
        dict(
            identity=IDENTITY,
            started_at=datetime.now(UTC).isoformat(),
            automatic_retry=False,
        ),
    )
    started, known = time.monotonic(), False
    try:
        response = model_factory().invoke(
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
        total = Decimal(scope["prior_paid_usd"]) + cost
        actual = response.response_metadata.get(
            "model_name"
        ) or response.response_metadata.get("model")
        save(
            output / "usage.json",
            dict(
                **usage,
                estimated_cost_usd_completed_responses=str(cost),
                shared_cumulative_cost_usd=str(total),
                requested_model=MODEL,
                response_model=actual,
                seconds=time.monotonic() - started,
                actual_backend_confirmed=False,
            ),
        )
        known = True
        if (
            actual != MODEL
            or total > SHARED_LIMIT
            or datetime.now(UTC) >= datetime.fromisoformat(SHARED_DEADLINE)
        ):
            raise PlanContractError("模型标识、共享预算或原时窗超出边界")
        proposal = RecoveryHarnessProposal.model_validate_json(response.text)
        candidate = proposal.materialize(
            RecoveryHarness.model_validate(load(prepared / "baseline.json")),
            load(prepared / "corpus.json"),
        )
        if not proposal.no_change:
            candidate = candidate.model_copy(update=dict(name="R2_system_context"))
        save(output / "proposal.json", proposal.model_dump(mode="json"))
        save(output / "candidate.json", candidate.model_dump(mode="json"))
        (output / "recovery-guidance.txt").write_text(candidate.recovery_guidance)
        after = candidate.prompt(SIMPLE_PROMPT)
        (output / "prompt-R2-system-context.txt").write_text(after)
        for name, before in (
            ("H0", SIMPLE_PROMPT),
            (
                "R1",
                RecoveryHarness.model_validate(
                    load(prepared / "r1-reference.json")
                ).prompt(SIMPLE_PROMPT),
            ),
            (
                "R2-original",
                RecoveryHarness.model_validate(
                    load(prepared / "r2-reference.json")
                ).prompt(SIMPLE_PROMPT),
            ),
        ):
            (output / f"prompt-{name}.txt").write_text(before)
            (output / f"diff-{name}-R2-system-context.patch").write_text(
                "".join(
                    difflib.unified_diff(
                        before.splitlines(keepends=True),
                        after.splitlines(keepends=True),
                        fromfile=name,
                        tofile="R2-system-context",
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
                shared_cumulative_cost_usd=str(total),
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "generate"))
    parser.add_argument("--prepared", type=Path, default=FIXTURE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--authorization", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.prepared)
    else:
        if args.output is None or args.authorization is None:
            parser.error("generate需要--output和--authorization")
        result = generate(
            args.prepared, args.output, load(args.authorization), richlab_model
        ).model_dump(mode="json")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
