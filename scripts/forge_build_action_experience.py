#!/usr/bin/env python3
"""准备三组短动作经验比较；每次规划/恢复任务选一次，复用既有构建底座。"""

from __future__ import annotations

import argparse
import copy
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import forge_build_common_harness as common
import forge_build_conditioned_experience as previous
from langchain_core.messages import SystemMessage

from deerflow.compile.action_experience import (
    ActionBank,
    ActionExtraction,
    TaskExperience,
    validate_action_extraction,
)
from deerflow.compile.build_experience import EXPERIENCE_PROMPT
from deerflow.compile.goal_state import GoalStateWorkflow, goal_state_planner

original, base, system, ROOT = (
    previous.original,
    previous.base,
    previous.system,
    previous.ROOT,
)
IDENTITY = "cpp-build-task-action-experience-flash-v1"
EXTRACT_ID = "cpp-build-task-action-distillation-richlab-v1"
SESSION = Path("/home/yiwei/.codex/outputs/forge-task-action-experience-session-v1")
OUTPUT = SESSION.parent / "forge-task-action-experience-flash-v1"
MANIFEST = ROOT / "benchmarks/manifests" / (IDENTITY + ".json")
PREREG = "benchmarks/preregistrations/" + IDENTITY + ".md"
METHODS = ("no_experience", "source_experience", "action_experience")
INPUTS = {
    "sources": previous.SESSION / "sources.json",
    "facts": previous.SESSION / "archive-facts.json",
    "old_bank": previous.OLD_BANK,
}
PROMPT = """你是离线构建经验提炼Agent。根据固定历史来源，最多提炼两条短动作经验，也允许零条。
每条只回答：什么前提下→当前源码/反馈要核对什么→优先做什么→应观察什么。目标是替代一次具体读取/判断/无效尝试，而不是增加通用建议。
check_before_action写最小的当前项目证据核对，允许复用上下文已有证据，不要求为核对而再读所有文件；expected_observation是待验证预期，不是已发生事实。
保留失败动作、实际反馈、实际修订；没有真实修订写null，不虚构成功。outcome区分局部effective、ineffective、未执行hypothesis。
command_ids和evidence_ids只引用给定真实命令/过程；引用成功命令不证明修复因果，更不代表完整任务通过。
不重复固定验收要求；不照搬项目路径/选项/target。清理动作必须先确认路径为本次生成物，不能按Makefile等名字递归删除作者文件。
applicability列必要文件basename、声明中的短字面词、仅恢复适用的当前错误片段；必要信号AND、错误片段OR，未知则放弃，不凭空扩大适用范围。
每条约200中文字，连同证据不超过3200 UTF-8字节。只返回schema JSON，不输出Markdown："""


def meter_class(item, task, bank, mode):
    class ActionMeter(system.CommonTaskMeter):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, item=item, **kwargs)
            self.experience_packet = self.packet
            self.experience = TaskExperience(
                task=task, family=item["name"], bank=bank, mode=mode, ledger=self.ledger
            )
            self.packet = lambda: self.experience.attach(self.experience_packet())

        def _before_request(self):
            sequence = super()._before_request()
            self.experience.used(sequence)
            return sequence

        def wrap_model_call(self, request, handler):
            message = request.system_message
            return super().wrap_model_call(
                request.override(
                    system_message=SystemMessage(
                        content=(message.content if message else "") + EXPERIENCE_PROMPT
                    )
                ),
                handler,
            )

    return ActionMeter


@contextmanager
def task_interfaces():
    propose = common.propose_received

    def task_propose(**kwargs):
        meter = kwargs["meter"]
        meter.experience.begin(meter.experience_packet())
        # 内部结构纠错仍由同一次propose处理，共用当前快照。
        return propose(**kwargs)

    with (
        patch.object(common, "propose_received", task_propose),
        common.common_harness_interfaces(),
    ):
        yield


def run_slot(protocol, slot, root, model, bank):
    item = next(i for i in protocol["projects"] if i["name"] == slot["project"])
    task = base.PlanTask.model_validate(item["task"])
    mode = "none" if slot["method"] == METHODS[0] else "structured"
    if slot["method"] == METHODS[2]:
        bank = ActionBank(
            list(bank.sources.values()),
            bank.entries,
            base.load(INPUTS["facts"]),
            root / "selection.jsonl",
        )
    with task_interfaces():
        planner = base.observed_module.observed_planner
        with (
            patch.object(base, "PreparationMeter", meter_class(item, task, bank, mode)),
            patch.object(
                base, "execution_window", system.component.bounded.execution_window
            ),
            patch.object(base.prepared_module, "PreparedWorkflow", GoalStateWorkflow),
            patch.object(
                base.observed_module,
                "observed_planner",
                lambda *a, **kw: goal_state_planner(planner(*a, **kw)),
            ),
        ):
            row = system.replication.run_slot(
                protocol=protocol,
                slot={**slot, "method": "model_plan_workflow"},
                root=root,
                model=model,
            )
    return {**row, **slot, "experience_mode": mode, "experience_scope": "agent_task"}


def prepare():
    """只固定现有材料、任务和实现；不读取授权/凭据，不创建正式运行目录。"""
    candidate = copy.deepcopy(base.load(previous.MANIFEST))
    for key in (
        "authorization_sha256",
        "deadline_utc",
        "facts_sha256",
        "source_material_sha256",
    ):
        candidate.pop(key, None)
    projects = candidate["projects"]
    candidate.update(
        identity=IDENTITY,
        issue=662,
        kind="short_action_experience_with_task_snapshot",
        extraction_identity=EXTRACT_ID,
        authorization_required=True,
        stage_max_cost_usd="10.00",
        inputs={
            name: dict(path=str(path), sha256=base.digest(path))
            for name, path in INPUTS.items()
        },
        seed_sources=dict(
            path=str(INPUTS["sources"]),
            sha256=base.digest(INPUTS["sources"]),
            count=12,
            families=8,
        ),
        exposure=[
            dict(
                project=p["name"],
                family=p["name"],
                holdout=False,
                historical_roles="E35/E36/E37及开发已暴露；本轮不吸收评价轨迹",
            )
            for p in projects
        ],
        schedule=[
            dict(project=name, repetition=r, method=METHODS[(j + i + r - 1) % 3])
            for r in (1, 2)
            for i, name in enumerate(original.TARGETS)
            for j in range(3)
        ],
        treatment=dict(
            zip(
                METHODS,
                ("无经验", "原24条＋来源级检索", "新短动作经验＋逐条信号选择"),
                strict=True,
            )
        ),
        experience=dict(
            scope="initial_planning_or_one_recovery_episode",
            refresh_within_task=False,
            bank_update=False,
            old_top_k=3,
            old_limit_bytes=12000,
            action_top_k=2,
            action_limit_bytes=6000,
        ),
        strata={
            p["name"]: "explicit_configuration"
            if p["task"]["build_system"] == "cmake"
            else "make_or_bootstrap"
            for p in projects
        },
        interpretation_boundary="固定六个已暴露项目；按作者构建系统前瞻分层，不代表难度/迁移成功真值。B-C为经验材料、选择和额度的组合；所有组共用每任务快照，不隔离快照因果。旧E37不合并分母。",
    )
    candidate["methods"] = candidate["treatment"]
    candidate["comparison_boundary"] = candidate["interpretation_boundary"]
    candidate["launch_state"] = "prepared_requires_new_budget_and_time_authorization"
    paths = {
        *candidate["components"],
        "scripts/forge_build_action_experience.py",
        "scripts/forge_analyze_action_experience.py",
        "backend/packages/harness/deerflow/compile/action_experience.py",
        PREREG,
    }
    candidate["components"] = {path: base.digest(ROOT / path) for path in sorted(paths)}
    original.save(MANIFEST, candidate)
    print("准备完成：36槽／12次提炼；Provider请求0；新付费授权尚未绑定")


def check_prepared():
    protocol = base.load(MANIFEST)
    for path, sha in protocol["components"].items():
        if base.digest(ROOT / path) != sha:
            raise ValueError("准备组件变化：" + path)
    for name, value in protocol["inputs"].items():
        if base.digest(Path(value["path"])) != value["sha256"]:
            raise ValueError("固定输入变化：" + name)
    for item in protocol["projects"]:
        if (
            base.digest(Path(item["source_archive"]))
            != item["task"]["source_archive_sha256"]
        ):
            raise ValueError("源码归档变化")
    return protocol


def authorized_protocol():
    protocol = check_prepared()
    auth = base.load(SESSION / "authorization.json")
    if (
        auth["identities"] != [EXTRACT_ID, IDENTITY]
        or Decimal(auth["maximum_cost_usd"]) != Decimal("10")
        or auth.get("automatic_retry") is not False
    ):
        raise ValueError("需要本轮两身份、10美元硬上限及无自动重试的明确授权")
    start, deadline = (
        datetime.fromisoformat(auth[k]) for k in ("authorized_at_utc", "deadline_utc")
    )
    if (
        not start <= datetime.now(UTC) < deadline
        or (deadline - start).total_seconds() > 8 * 3600
    ):
        raise ValueError("需要确认起最多8小时的有效时窗")
    if auth["accepted_response_models"] != ["gpt-5.6", "gpt-6-astra"] or auth[
        "pricing"
    ] != dict(input_usd_per_million="1", output_usd_per_million="1"):
        raise ValueError("提炼路由/响应披露或计价授权不符")
    binding = dict(
        candidate_sha256=base.digest(MANIFEST),
        authorization_sha256=base.digest(SESSION / "authorization.json"),
    )
    path = SESSION / "paid-scope.json"
    if path.exists():
        if base.load(path) != binding:
            raise ValueError("本轮已绑定另一授权或候选，不续用身份")
    else:
        original.save(path, binding)
    protocol.update(binding)
    return protocol


@contextmanager
def paid_bindings():
    """仅为本次调用绑定旧运行器；退出还原，不修改历史脚本或冻结材料。"""
    authorized_protocol()  # 在旧运行器可能读取凭据前验证新范围。
    bindings = dict(
        SESSION=SESSION,
        OUTPUT=OUTPUT,
        IDENTITY=IDENTITY,
        EXTRACT_ID=EXTRACT_ID,
        MANIFEST=MANIFEST,
        METHODS=METHODS,
        OLD_BANK=INPUTS["old_bank"],
        PROMPT=PROMPT,
        ProcessExtraction=ActionExtraction,
        validate_process_extraction=validate_action_extraction,
        check_prepared=authorized_protocol,
    )
    with ExitStack() as stack:
        for name, value in bindings.items():
            stack.enter_context(patch.object(previous, name, value))
        stack.enter_context(patch.object(original, "run_slot", run_slot))
        yield


def extract():
    with paid_bindings():
        if not (SESSION / "sources.json").exists():
            original.save(SESSION / "sources.json", base.load(INPUTS["sources"]))
        previous.extract()


def run():
    with paid_bindings():
        if not (SESSION / "archive-facts.json").exists():
            original.save(SESSION / "archive-facts.json", base.load(INPUTS["facts"]))
        previous.run()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=["prepare", "check-prepared", "extract", "run"]
    )
    args = parser.parse_args()
    {
        "prepare": prepare,
        "check-prepared": check_prepared,
        "extract": extract,
        "run": run,
    }[args.action]()


if __name__ == "__main__":
    main()
