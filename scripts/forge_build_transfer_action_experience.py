#!/usr/bin/env python3
"""独立36槽迁移候选比较；只复用已付种子，共享原授权预算与截止。"""

from __future__ import annotations

import argparse
import copy
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

import forge_build_action_experience as first
from forge_build_action_experience_v2 import SEED_INPUTS

from deerflow.compile.transfer_action_experience import TransferActionBank

IDENTITY = "cpp-build-transfer-action-experience-flash-v1"
SESSION = first.SESSION.parent / "forge-transfer-action-experience-session-v1"
OUTPUT = SESSION.parent / "forge-transfer-action-experience-flash-v1"
MANIFEST = first.ROOT / "benchmarks/manifests" / (IDENTITY + ".json")
PREREG = "benchmarks/preregistrations/" + IDENTITY + ".md"


def prepare():
    candidate = copy.deepcopy(first.base.load(first.MANIFEST))
    candidate.update(
        identity=IDENTITY,
        issue=664,
        previous_comparison_identity=first.IDENTITY,
        seed_reuse={
            name: dict(path=str(path), sha256=first.base.digest(path))
            for name, path in SEED_INPUTS.items()
        },
        authorization_boundary="用户同意独立36次范围扩展；共享原10美元及原截止，原提炼成本0.164217美元只计一次，不重提炼。",
        launch_state="prepared_authorized_scope_extension_required_receipt",
        kind="source_facts_separated_transfer_action_candidates",
    )
    candidate["treatment"]["action_experience"] = (
        "固定13条短动作经验＋通用结构候选；来源专名保留待核对"
    )
    candidate["methods"] = candidate["treatment"]
    candidate["experience"]["transfer_boundary"] = (
        "通用输入和声明结构AND；错误片段OR且必须当前命中；来源专名不作跨项目必要词，自然语言前提仍未确认，不自动执行。"
    )
    paths = {
        *candidate["components"],
        str(Path(__file__).relative_to(first.ROOT)),
        "backend/packages/harness/deerflow/compile/transfer_action_experience.py",
        "backend/tests/test_transfer_action_experience.py",
        PREREG,
    }
    candidate["components"] = {
        path: first.base.digest(first.ROOT / path) for path in sorted(paths)
    }
    first.original.save(MANIFEST, candidate)
    print("独立36槽准备完成；只复用已付13条，0 Provider")


@contextmanager
def bindings():
    with ExitStack() as stack:
        for name, value in dict(
            IDENTITY=IDENTITY,
            SESSION=SESSION,
            OUTPUT=OUTPUT,
            MANIFEST=MANIFEST,
            ActionBank=TransferActionBank,
        ).items():
            stack.enter_context(patch.object(first, name, value))
        yield


def check_prepared():
    with bindings():
        protocol = first.check_prepared()
    for name, item in protocol["seed_reuse"].items():
        if first.base.digest(Path(item["path"])) != item["sha256"]:
            raise ValueError("原已付种子/费用/授权变化：" + name)
    return protocol


def run():
    check_prepared()
    with bindings():
        first.authorized_protocol()
        old_auth = first.base.load(SEED_INPUTS["authorization.json"])
        auth = first.base.load(SESSION / "authorization.json")
        if any(
            auth[k] != old_auth[k]
            for k in ("authorized_at_utc", "deadline_utc", "maximum_cost_usd")
        ):
            raise ValueError("不得重置原预算与时窗")
        if (
            auth.get("scope_extension_user_reply") != "同意授权"
            or auth.get("reuse_only") is not True
        ):
            raise ValueError("缺少用户范围扩展/不重提炼收据")
        for name in ("seed-bank.json", "distillation/result.json"):
            target = SESSION / name
            target.parent.mkdir(parents=True, exist_ok=True)
            first.original.save(target, first.base.load(SEED_INPUTS[name]))
        first.run()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "check-prepared", "run"])
    args = parser.parse_args()
    {"prepare": prepare, "check-prepared": check_prepared, "run": run}[args.action]()


if __name__ == "__main__":
    main()
