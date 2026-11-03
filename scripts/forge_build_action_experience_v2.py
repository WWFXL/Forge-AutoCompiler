#!/usr/bin/env python3
"""修复后三组比较：复用已提炼种子，原v1及全部未观察槽保持。"""

from __future__ import annotations

import argparse
import copy
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

import forge_build_action_experience as first

IDENTITY = "cpp-build-task-action-experience-flash-v2"
SESSION = first.SESSION.parent / "forge-task-action-experience-session-v2"
OUTPUT = SESSION.parent / "forge-task-action-experience-flash-v2"
MANIFEST = first.ROOT / "benchmarks/manifests" / (IDENTITY + ".json")
PREREG = "benchmarks/preregistrations/" + IDENTITY + ".md"
SEED_INPUTS = {
    name: first.SESSION / name
    for name in ("seed-bank.json", "distillation/result.json", "authorization.json")
}


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
        authorization_boundary="须用户确认修复后独立身份；共享原10美元及原截止，不重提炼、不覆盖v1。",
        launch_state="prepared_requires_scope_extension",
    )
    paths = {
        *candidate["components"],
        str(Path(__file__).relative_to(first.ROOT)),
        PREREG,
    }
    candidate["components"] = {
        path: first.base.digest(first.ROOT / path) for path in sorted(paths)
    }
    first.original.save(MANIFEST, candidate)
    print("独立v2准备完成：同36槽，复用原13条种子；0 Provider，尚未授权启动")


@contextmanager
def bindings():
    with ExitStack() as stack:
        for name, value in dict(
            IDENTITY=IDENTITY, SESSION=SESSION, OUTPUT=OUTPUT, MANIFEST=MANIFEST
        ).items():
            stack.enter_context(patch.object(first, name, value))
        yield


def check_prepared():
    with bindings():
        protocol = first.check_prepared()
    for name, item in protocol["seed_reuse"].items():
        if first.base.digest(Path(item["path"])) != item["sha256"]:
            raise ValueError("已冻结复用材料变化：" + name)
    return protocol


def run():
    check_prepared()
    with bindings():
        # 新授权仍需明确绑定v2；检查通过前不得建立正式材料或读凭据。
        first.authorized_protocol()
        old_auth = first.base.load(SEED_INPUTS["authorization.json"])
        auth = first.base.load(SESSION / "authorization.json")
        if any(
            auth[k] != old_auth[k]
            for k in ("authorized_at_utc", "deadline_utc", "maximum_cost_usd")
        ):
            raise ValueError("v2只能共享原预算与原时窗，不得重置")
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
